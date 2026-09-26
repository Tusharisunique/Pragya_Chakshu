"""
PRAGYA CHAKSHU -- NEW FRONTEND-REQUIRED ENDPOINTS
Implements:
  GET /api/cases/{case_id}/personas/{persona_id}/timeline
  GET /api/cases/{case_id}/next-steps
  GET /api/cases/{case_id}/export/csv
  GET /api/cases/{case_id}/personas        (persona list with identifiers)
  GET /api/cases/{case_id}/search          (unified search)
  GET /api/cases/{case_id}/infrastructure  (infra indicators)
  POST /api/cases/{case_id}/correlation/run (correlation trigger alias)
"""

import json
import csv
import io
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from backend.database.sqlite import get_connection

router = APIRouter(prefix="/cases", tags=["frontend"])


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: safe JSON parse
# ─────────────────────────────────────────────────────────────────────────────
def _parse_payload(raw) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# 1. PERSONA LIST WITH IDENTIFIERS
#    GET /api/cases/{case_id}/personas
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/{case_id}/personas")
def list_personas(case_id: str):
    """
    Returns all personas for a case, each enriched with their identifiers,
    confidence score derived from evidence, and last-seen timestamp.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Verify case exists
    cursor.execute("SELECT case_id FROM cases WHERE case_id=?", (case_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Case not found")

    cursor.execute(
        "SELECT * FROM personas WHERE case_id=? ORDER BY first_seen ASC",
        (case_id,),
    )
    personas = [dict(r) for r in cursor.fetchall()]

    # Enrich each persona with identifiers
    for p in personas:
        pid = p["persona_id"]
        cursor.execute(
            """SELECT identifier_id, identifier_type, normalized_value as identifier_value, provenance
               FROM identifiers WHERE persona_id=?""",
            (pid,),
        )
        p["identifiers"] = [dict(r) for r in cursor.fetchall()]

        # Derive a confidence label from evidence
        cursor.execute(
            """SELECT AVG(confidence_weight) as avg_conf
               FROM evidence
               WHERE (source_persona_id=? OR target_persona_id=?)
                 AND challenge_status='ACTIVE'""",
            (pid, pid),
        )
        row = cursor.fetchone()
        avg = row["avg_conf"] if row and row["avg_conf"] is not None else 0
        if avg >= 15:
            p["confidence"] = "high"
        elif avg >= 5:
            p["confidence"] = "medium"
        else:
            p["confidence"] = "low"

    conn.close()
    return personas


# ─────────────────────────────────────────────────────────────────────────────
# 2. TIMELINE LOG PER PERSONA
#    GET /api/cases/{case_id}/personas/{persona_id}/timeline
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/{case_id}/personas/{persona_id}/timeline")
def get_persona_timeline(case_id: str, persona_id: str):
    """
    Returns a chronological list of events associated with a given persona,
    derived from normalized_events. Covers first_seen, posts, listings,
    identifier discoveries, and infrastructure linkages.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Get persona basics
    cursor.execute(
        "SELECT * FROM personas WHERE case_id=? AND persona_id=?",
        (case_id, persona_id),
    )
    persona = cursor.fetchone()
    if not persona:
        conn.close()
        raise HTTPException(status_code=404, detail="Persona not found")

    persona = dict(persona)
    raw_uid = persona.get("raw_uid")
    raw_vid = persona.get("raw_vid")
    handle  = persona.get("canonical_handle", "")
    platform = persona.get("platform", "")

    events: list[dict] = []

    # First-seen synthetic event
    if persona.get("first_seen"):
        events.append({
            "timestamp":   persona["first_seen"],
            "event_type":  "first_seen",
            "description": f"{handle} first observed on {platform}.",
            "details":     {"handle": handle, "platform": platform},
        })

    # Pull matching normalized events
    cursor.execute(
        """SELECT event_type, timestamp_occurred, payload_json, provenance
           FROM normalized_events
           WHERE case_id=?
           ORDER BY timestamp_occurred ASC""",
        (case_id,),
    )
    for row in cursor.fetchall():
        payload = _parse_payload(row["payload_json"])
        matched = False
        description = ""
        details: dict = {}
        etype = row["event_type"]

        if raw_uid and etype == "post_observed":
            orig = payload.get("original_post", payload)
            if str(orig.get("uid", "")) == str(raw_uid):
                matched = True
                text = (payload.get("clean_text") or payload.get("text", ""))[:100]
                description = f'Post observed on {platform}: "{text[:80]}..."' if text else f"Post activity on {platform}."
                details = {"platform": platform, "text": text[:80]}

        elif raw_vid and etype in ("vendor_observed", "listing_observed"):
            if str(payload.get("vid", "")) == str(raw_vid):
                matched = True
                title = payload.get("title", "")
                desc  = (payload.get("clean_description") or payload.get("description", ""))[:80]
                description = f'Listing "{title}" detected.' if title else f"Vendor activity detected: {desc}"
                details = {"title": title, "desc": desc, "platform": platform}

        elif etype == "pgp_observed" and (
            handle.lower() in str(payload).lower()
            or str(raw_uid) in str(payload)
            or str(raw_vid) in str(payload)
        ):
            matched = True
            fp = payload.get("fingerprint", "")
            description = f"PGP key observed: {fp[:24]}..." if fp else "PGP key activity."
            details = {"fingerprint": fp[:24]}

        elif etype == "infrastructure_cluster_observed" and (
            handle.lower() in str(payload).lower()
        ):
            matched = True
            description = "Infrastructure cluster linked to actor."
            details = {}

        if matched:
            events.append({
                "timestamp":   row["timestamp_occurred"],
                "event_type":  etype,
                "description": description,
                "details":     details,
                "provenance":  row["provenance"],
            })

    # Identifier discoveries as timeline events
    cursor.execute(
        "SELECT identifier_type, normalized_value, provenance FROM identifiers WHERE persona_id=?",
        (persona_id,),
    )
    for irow in cursor.fetchall():
        events.append({
            "timestamp":   persona.get("first_seen", ""),
            "event_type":  "identifier_found",
            "description": f"{irow['identifier_type']} discovered: {irow['normalized_value'][:40]}",
            "details":     {"identifier_type": irow["identifier_type"],
                            "value": irow["normalized_value"][:40]},
            "provenance":  irow["provenance"],
        })

    # Last-seen
    if persona.get("last_seen") and persona["last_seen"] != persona.get("first_seen"):
        events.append({
            "timestamp":   persona["last_seen"],
            "event_type":  "last_seen",
            "description": f"Last recorded activity from {handle} on {platform}.",
            "details":     {"handle": handle, "platform": platform},
        })

    conn.close()

    # Sort by timestamp (None/empty last)
    events.sort(key=lambda e: (e.get("timestamp") or ""), reverse=False)

    return {
        "case_id":    case_id,
        "persona_id": persona_id,
        "handle":     handle,
        "platform":   platform,
        "total":      len(events),
        "events":     events,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. NEXT STEPS (relationship-driven suggestions)
#    GET /api/cases/{case_id}/next-steps
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/{case_id}/next-steps")
def get_next_steps(case_id: str):
    """
    Returns an ordered list of suggested investigative next steps, derived
    from the current graph/evidence state of the case.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT case_id, name FROM cases WHERE case_id=?", (case_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Case not found")

    suggestions: list[dict] = []

    # Count actors, evidence, identifiers
    cursor.execute("SELECT COUNT(*) FROM personas WHERE case_id=?", (case_id,))
    actor_count = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM evidence WHERE case_id=? AND challenge_status='ACTIVE'",
        (case_id,),
    )
    evidence_count = cursor.fetchone()[0]

    cursor.execute(
        """SELECT COUNT(*) FROM identifiers i
           JOIN personas p ON i.persona_id=p.persona_id
           WHERE p.case_id=?""",
        (case_id,),
    )
    id_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM investigator_notes WHERE case_id=?", (case_id,))
    note_count = cursor.fetchone()[0]

    # ── Suggestion derivation ───────────────────────────────────────────

    if actor_count == 0:
        suggestions.append({
            "key": "ingest_dataset",
            "params": {},
            "suggestion": "Ingest a dataset to begin discovering threat actors.",
            "reason": "No actors have been loaded yet.",
            "related_entity_ids": [],
            "priority": 0,
        })
    else:
        # Shared identifier signals
        cursor.execute(
            """SELECT i.normalized_value, i.identifier_type, COUNT(DISTINCT p.persona_id) as shared_by
               FROM identifiers i
               JOIN personas p ON i.persona_id=p.persona_id
               WHERE p.case_id=?
               GROUP BY i.normalized_value
               HAVING shared_by > 1
               ORDER BY shared_by DESC
               LIMIT 3""",
            (case_id,),
        )
        shared_ids = cursor.fetchall()
        for si in shared_ids:
            id_type  = si["identifier_type"]
            id_val   = si["normalized_value"][:32] + "..."
            id_count_shared = si["shared_by"]
            suggestions.append({
                "key": "shared_identifier",
                "params": {
                    "type": id_type,
                    "value": id_val,
                    "count": id_count_shared,
                },
                "suggestion": f"{id_type} '{id_val}' links {id_count_shared} actors -- review cross-platform persona linkages.",
                "reason": f"Shared {id_type.lower()} is a strong attribution signal.",
                "related_entity_ids": [],
                "priority": 1,
            })

        # High-confidence evidence leads
        cursor.execute(
            """SELECT e.relationship_id, e.confidence_weight, pa.canonical_handle as ha, pb.canonical_handle as hb
               FROM evidence e
               LEFT JOIN personas pa ON e.source_persona_id=pa.persona_id
               LEFT JOIN personas pb ON e.target_persona_id=pb.persona_id
               WHERE e.case_id=? AND e.challenge_status='ACTIVE' AND e.confidence_weight >= 15
               ORDER BY e.confidence_weight DESC
               LIMIT 3""",
            (case_id,),
        )
        leads = cursor.fetchall()
        for lead in leads:
            if lead["ha"] and lead["hb"]:
                suggestions.append({
                    "key": "high_confidence_link",
                    "params": {
                        "a": lead["ha"],
                        "b": lead["hb"],
                        "score": round(float(lead["confidence_weight"]), 1),
                    },
                    "suggestion": f"High-confidence link between {lead['ha']} and {lead['hb']} (score {round(float(lead['confidence_weight']), 1)}) -- verify this attribution.",
                    "reason": "Multi-signal stylometric and behavioural correlation above threshold.",
                    "related_entity_ids": [lead["relationship_id"] or ""],
                    "priority": 2,
                })

        # If evidence but no notes
        if evidence_count > 0 and note_count == 0:
            suggestions.append({
                "key": "add_notes",
                "params": {},
                "suggestion": "No investigator notes recorded yet -- add observations to key actors for the final report.",
                "reason": "Notes improve the forensic dossier quality.",
                "related_entity_ids": [],
                "priority": 3,
            })

        # Infrastructure
        cursor.execute(
            """SELECT COUNT(*) FROM normalized_events
               WHERE case_id=? AND event_type='infrastructure_cluster_observed'""",
            (case_id,),
        )
        infra_count = cursor.fetchone()[0]
        if infra_count > 0:
            suggestions.append({
                "key": "infra_clusters",
                "params": {},
                "suggestion": "Infrastructure clusters detected -- check the Infrastructure tab for hidden service indicators.",
                "reason": "Shared .onion hosting is a strong attribution anchor.",
                "related_entity_ids": [],
                "priority": 4,
            })

        # Export prompt
        if evidence_count > 0:
            suggestions.append({
                "key": "export_dossier",
                "params": {},
                "suggestion": "Generate a Summary and export a forensic dossier to document current findings.",
                "reason": "The investigation has enough data for a meaningful report.",
                "related_entity_ids": [],
                "priority": 5,
            })

    conn.close()

    # Sort by priority and deduplicate
    suggestions.sort(key=lambda s: s["priority"])

    return {
        "case_id":     case_id,
        "total":       len(suggestions),
        "suggestions": [s["suggestion"] for s in suggestions],
        "full":        suggestions,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. CSV EXPORT
#    GET /api/cases/{case_id}/export/csv
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/{case_id}/export/csv")
def export_case_csv(case_id: str):
    """
    Exports case data as CSV: one sheet per entity type (personas, identifiers,
    evidence, notes) combined into a multi-section flat file.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM cases WHERE case_id=?", (case_id,))
    case_row = cursor.fetchone()
    if not case_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Case not found")

    output = io.StringIO()
    writer = csv.writer(output)

    # ── Section 1: Case Metadata ──────────────────────────────────────
    writer.writerow(["## CASE METADATA"])
    writer.writerow(["case_id", "name", "description", "status", "created_at", "updated_at"])
    c = dict(case_row)
    writer.writerow([c.get("case_id"), c.get("name"), c.get("description"),
                     c.get("status"), c.get("created_at"), c.get("updated_at")])
    writer.writerow([])

    # ── Section 2: Personas ───────────────────────────────────────────
    writer.writerow(["## PERSONAS / ACTOR PROFILES"])
    writer.writerow(["persona_id", "canonical_handle", "platform", "first_seen", "last_seen", "provenance"])
    cursor.execute("SELECT * FROM personas WHERE case_id=?", (case_id,))
    for row in cursor.fetchall():
        r = dict(row)
        writer.writerow([r.get("persona_id"), r.get("canonical_handle"), r.get("platform"),
                         r.get("first_seen"), r.get("last_seen"), r.get("provenance")])
    writer.writerow([])

    # ── Section 3: Identifiers ────────────────────────────────────────
    writer.writerow(["## IDENTIFIERS (PGP / WALLET / ONION)"])
    writer.writerow(["identifier_id", "persona_id", "identifier_type", "identifier_value", "provenance"])
    cursor.execute(
        """SELECT i.identifier_id, i.persona_id, i.identifier_type, i.normalized_value, i.provenance
           FROM identifiers i
           JOIN personas p ON i.persona_id=p.persona_id
           WHERE p.case_id=?""",
        (case_id,),
    )
    for row in cursor.fetchall():
        r = dict(row)
        writer.writerow([r.get("identifier_id"), r.get("persona_id"),
                         r.get("identifier_type"), r.get("normalized_value"), r.get("provenance")])
    writer.writerow([])

    # ── Section 4: Evidence / Correlations ───────────────────────────
    writer.writerow(["## EVIDENCE / ATTRIBUTION LINKS"])
    writer.writerow(["evidence_id", "source_persona", "target_persona", "evidence_type",
                     "confidence_weight", "polarity", "challenge_status", "provenance"])
    cursor.execute(
        """SELECT e.evidence_id, pa.canonical_handle as src, pb.canonical_handle as tgt,
                  e.evidence_type, e.confidence_weight, e.polarity, e.challenge_status, e.provenance
           FROM evidence e
           LEFT JOIN personas pa ON e.source_persona_id=pa.persona_id
           LEFT JOIN personas pb ON e.target_persona_id=pb.persona_id
           WHERE e.case_id=?""",
        (case_id,),
    )
    for row in cursor.fetchall():
        r = dict(row)
        writer.writerow([r.get("evidence_id"), r.get("src"), r.get("tgt"),
                         r.get("evidence_type"), r.get("confidence_weight"),
                         r.get("polarity"), r.get("challenge_status"), r.get("provenance")])
    writer.writerow([])

    # ── Section 5: Investigator Notes ────────────────────────────────
    writer.writerow(["## INVESTIGATOR NOTES"])
    writer.writerow(["note_id", "investigator_id", "entity_type", "entity_label", "note_text", "created_at"])
    cursor.execute(
        "SELECT * FROM investigator_notes WHERE case_id=? ORDER BY created_at ASC",
        (case_id,),
    )
    for row in cursor.fetchall():
        r = dict(row)
        writer.writerow([r.get("note_id"), r.get("investigator_id"), r.get("entity_type"),
                         r.get("entity_label"), r.get("note_text"), r.get("created_at")])

    conn.close()

    csv_bytes = output.getvalue().encode("utf-8")
    filename  = f"pragya_chakshu_{case_id[:8]}_{datetime.utcnow().strftime('%Y%m%d')}.csv"

    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5. INFRASTRUCTURE INDICATORS
#    GET /api/cases/{case_id}/infrastructure
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/{case_id}/infrastructure")
def get_infrastructure(case_id: str):
    """
    Returns hidden service / infrastructure indicators associated with this case.
    Pulls from identifiers (ONION_URL) and synthetic infrastructure cluster events.
    """
    conn = get_connection()
    cursor = conn.cursor()

    indicators: list[dict] = []

    # Onion URLs from identifiers
    cursor.execute(
        """SELECT i.identifier_id, i.normalized_value as url, 'ONION_URL' as indicator_type,
                  p.canonical_handle as linked_actor, i.provenance
           FROM identifiers i
           JOIN personas p ON i.persona_id=p.persona_id
           WHERE p.case_id=? AND i.identifier_type='ONION_URL'""",
        (case_id,),
    )
    for row in cursor.fetchall():
        r = dict(row)
        indicators.append({
            "indicator_type": r["indicator_type"],
            "indicator_value": r["url"],
            "linked_actor": r["linked_actor"],
            "provenance": r["provenance"],
            "scan_date": None,
        })

    # Infrastructure cluster events
    cursor.execute(
        """SELECT payload_json, timestamp_occurred
           FROM normalized_events
           WHERE case_id=? AND event_type='infrastructure_cluster_observed'
           ORDER BY timestamp_occurred DESC""",
        (case_id,),
    )
    for row in cursor.fetchall():
        payload = _parse_payload(row["payload_json"])
        cluster = payload.get("cluster", payload)
        for node in cluster.get("nodes", []):
            if node.get("type") in ("hidden_service", "onion"):
                indicators.append({
                    "indicator_type": "ONION_CLUSTER",
                    "indicator_value": node.get("id", ""),
                    "linked_actor": None,
                    "provenance": "SYNTHETIC",
                    "scan_date": row["timestamp_occurred"],
                })

    conn.close()
    return indicators


# ─────────────────────────────────────────────────────────────────────────────
# 6. CORRELATION RUN  (non-blocking background task)
#    POST /api/cases/{case_id}/correlation/run  → returns job_id immediately
#    GET  /api/cases/{case_id}/correlation/status → poll for progress
# ─────────────────────────────────────────────────────────────────────────────
import threading
import time as _time

# In-process job registry: { case_id: { status, done, total, computed, found, error, started_at } }
_corr_jobs: dict = {}
_corr_lock = threading.Lock()


def _run_correlation_bg(case_id: str):
    """Background worker — evaluates all candidate persona pairs for a case."""
    from backend.analytics.correlation import evaluate_persona_correlation

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT persona_id, canonical_handle, platform FROM personas WHERE case_id=?",
            (case_id,),
        )
        personas = [dict(r) for r in cursor.fetchall()]
        conn.close()

        # Build candidate pairs
        pairs = [
            (personas[i], personas[j])
            for i in range(len(personas))
            for j in range(i + 1, len(personas))
            if (personas[i]["platform"] != personas[j]["platform"])
            or (personas[i]["canonical_handle"].lower() == personas[j]["canonical_handle"].lower())
        ]

        with _corr_lock:
            _corr_jobs[case_id]["total"] = len(pairs)

        computed = 0
        found = 0
        for p_a, p_b in pairs:
            try:
                result = evaluate_persona_correlation(case_id, p_a["persona_id"], p_b["persona_id"])
                computed += 1
                if result and result.get("correlation_score", 0) > 0:
                    found += 1
            except Exception:
                computed += 1  # count even on error so progress advances

            with _corr_lock:
                _corr_jobs[case_id]["computed"] = computed
                _corr_jobs[case_id]["found"]    = found

        with _corr_lock:
            _corr_jobs[case_id]["status"] = "done"
            _corr_jobs[case_id]["done"]   = True

    except Exception as exc:
        with _corr_lock:
            _corr_jobs[case_id]["status"] = "error"
            _corr_jobs[case_id]["error"]  = str(exc)
            _corr_jobs[case_id]["done"]   = True


@router.post("/{case_id}/correlation/run")
def run_correlation_alias(case_id: str):
    """
    Triggers correlation evaluation as a background job.
    Returns immediately with { job_id, status: 'running' }.
    Poll GET /correlation/status for progress.
    """
    # If already running for this case, return current status
    with _corr_lock:
        existing = _corr_jobs.get(case_id)
        if existing and not existing.get("done", True):
            return {
                "status": "already_running",
                "case_id": case_id,
                **existing,
            }

        # Start a fresh job
        _corr_jobs[case_id] = {
            "status":     "running",
            "done":       False,
            "total":      0,
            "computed":   0,
            "found":      0,
            "error":      None,
            "started_at": _time.time(),
        }

    t = threading.Thread(target=_run_correlation_bg, args=(case_id,), daemon=True)
    t.start()

    return {
        "status":   "running",
        "case_id":  case_id,
        "message":  "Correlation started in background. Poll /correlation/status for progress.",
    }


@router.get("/{case_id}/correlation/status")
def get_correlation_status(case_id: str):
    """
    Returns progress of the background correlation job for this case.
    Poll until done=True.
    """
    with _corr_lock:
        job = _corr_jobs.get(case_id)

    if not job:
        # No job started yet — check if evidence already exists (pre-computed)
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM evidence WHERE case_id=? AND challenge_status='ACTIVE'",
            (case_id,),
        )
        count = cursor.fetchone()[0]
        conn.close()
        if count > 0:
            return {"status": "done", "done": True, "computed": count, "found": count, "total": count, "message": "Pre-existing correlation data found."}
        return {"status": "not_started", "done": False, "computed": 0, "found": 0, "total": 0}

    with _corr_lock:
        snap = dict(job)

    elapsed = round(_time.time() - snap.pop("started_at", _time.time()), 1)
    total   = max(snap["total"], 1)
    pct     = round(snap["computed"] / total * 100, 1) if snap["total"] > 0 else 0

    return {
        **snap,
        "case_id":     case_id,
        "elapsed_s":   elapsed,
        "progress_pct": pct,
        "message": (
            f"Complete: {snap['computed']} pairs evaluated, {snap['found']} correlations found."
            if snap["done"] else
            f"Running: {snap['computed']}/{snap['total']} pairs ({pct}%)..."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. UNIFIED SEARCH
#    GET /api/cases/{case_id}/search?q=...
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/{case_id}/search")
def search_case(case_id: str, q: str = ""):
    """
    Searches across personas (handle, platform) and identifiers (value)
    for the given query string. Returns a merged result list.
    """
    if not q.strip():
        return {"case_id": case_id, "query": q, "results": []}

    conn = get_connection()
    cursor = conn.cursor()
    like = f"%{q}%"
    results: list[dict] = []

    cursor.execute(
        """SELECT persona_id, canonical_handle, platform, first_seen, provenance
           FROM personas
           WHERE case_id=? AND (canonical_handle LIKE ? OR platform LIKE ?)""",
        (case_id, like, like),
    )
    for row in cursor.fetchall():
        r = dict(row)
        results.append({
            "type": "persona",
            "id": r["persona_id"],
            "label": r["canonical_handle"],
            "sublabel": r["platform"],
            "first_seen": r["first_seen"],
        })

    cursor.execute(
        """SELECT i.identifier_id, i.identifier_type, i.normalized_value, p.canonical_handle, p.persona_id
           FROM identifiers i
           JOIN personas p ON i.persona_id=p.persona_id
           WHERE p.case_id=? AND i.normalized_value LIKE ?""",
        (case_id, like),
    )
    for row in cursor.fetchall():
        r = dict(row)
        results.append({
            "type": "identifier",
            "id": r["identifier_id"],
            "label": r["normalized_value"],
            "sublabel": f"{r['identifier_type']} -- {r['canonical_handle']}",
            "persona_id": r["persona_id"],
        })

    conn.close()
    return {"case_id": case_id, "query": q, "total": len(results), "results": results}
