from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import uuid
from datetime import datetime
from backend.database.sqlite import get_connection
from backend.database.neo4j_client import merge_case_node, delete_case_from_graph

router = APIRouter(prefix="/cases", tags=["cases"])

class CaseCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    owner_id: Optional[str] = "default_user"

class CaseUpdate(BaseModel):
    status: Optional[str] = None
    description: Optional[str] = None

@router.post("")
def create_case(case: CaseCreate):
    case_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    owner = (case.owner_id or "default_user").strip()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO cases (case_id, name, description, status, owner_id, created_at, updated_at)
        VALUES (?, ?, ?, 'OPEN', ?, ?, ?)
    """, (case_id, case.name, case.description, owner, now, now))
    conn.commit()
    conn.close()
    
    merge_case_node(case_id, case.name, 'OPEN')
    
    return {
        "case_id": case_id,
        "name": case.name,
        "description": case.description,
        "status": "OPEN",
        "owner_id": owner,
        "created_at": now,
    }

@router.get("")
def get_cases(owner_id: Optional[str] = None):
    """Returns all cases. If owner_id is provided, returns only cases owned by that user."""
    conn = get_connection()
    cursor = conn.cursor()
    if owner_id and owner_id.strip():
        cursor.execute(
            "SELECT * FROM cases WHERE owner_id=? ORDER BY created_at DESC",
            (owner_id.strip(),),
        )
    else:
        # No filter — used by admin/debug paths only; frontend always passes owner_id
        cursor.execute("SELECT * FROM cases ORDER BY created_at DESC")
    cases = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return cases

@router.get("/{case_id}")
def get_case(case_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cases WHERE case_id=?", (case_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    return dict(row)

@router.patch("/{case_id}")
def update_case(case_id: str, case_update: CaseUpdate):
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    
    updates = []
    params = []
    if case_update.status:
        updates.append("status=?")
        params.append(case_update.status)
    if case_update.description is not None:
        updates.append("description=?")
        params.append(case_update.description)
        
    if not updates:
        return {"status": "no updates provided"}
        
    updates.append("updated_at=?")
    params.append(now)
    params.append(case_id)
    
    query = f"UPDATE cases SET {', '.join(updates)} WHERE case_id=?"
    cursor.execute(query, params)
    conn.commit()
    
    cursor.execute("SELECT * FROM cases WHERE case_id=?", (case_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        merge_case_node(row['case_id'], row['name'], row['status'])
        return dict(row)
    raise HTTPException(status_code=404, detail="Case not found")


@router.delete("/{case_id}")
def delete_case(case_id: str):
    """Permanently deletes a case and ALL associated data (events, personas, evidence, notes)."""
    conn = get_connection()
    cursor = conn.cursor()

    # Verify case exists
    cursor.execute("SELECT case_id FROM cases WHERE case_id=?", (case_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Case not found")

    # Delete all related data in dependency order
    # identifiers are linked to personas, not case_id directly — handle separately
    cursor.execute(
        "SELECT persona_id FROM personas WHERE case_id=?", (case_id,)
    )
    persona_ids = [r[0] for r in cursor.fetchall()]
    if persona_ids:
        placeholders = ",".join("?" * len(persona_ids))
        cursor.execute(f"DELETE FROM identifiers WHERE persona_id IN ({placeholders})", persona_ids)
        cursor.execute(f"DELETE FROM stylometric_profiles WHERE persona_id IN ({placeholders})", persona_ids)

    for table in ["investigator_notes", "evidence_challenges", "evidence",
                  "replay_sessions", "normalized_events", "personas", "cases"]:
        cursor.execute(f"DELETE FROM {table} WHERE case_id=?", (case_id,))

    conn.commit()
    conn.close()

    # Remove from graph engine
    try:
        delete_case_from_graph(case_id)
    except Exception:
        pass  # Graph cleanup is best-effort

    return {"status": "deleted", "case_id": case_id}
