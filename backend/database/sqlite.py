import sqlite3
import os
from backend.config import SQLITE_DB_PATH


def get_connection():
    os.makedirs(os.path.dirname(SQLITE_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    os.makedirs(os.path.dirname(SQLITE_DB_PATH), exist_ok=True)
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS cases (
        case_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        status TEXT CHECK(status IN ('OPEN','ACTIVE','REVIEW','RESOLVED','ARCHIVED')),
        owner_id TEXT,
        created_at TIMESTAMP,
        updated_at TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS normalized_events (
        event_id TEXT PRIMARY KEY,
        case_id TEXT,
        event_type TEXT NOT NULL,
        timestamp_occurred TIMESTAMP NOT NULL,
        timestamp_ingested TIMESTAMP,
        source_dataset TEXT NOT NULL,
        source_record_id TEXT NOT NULL,
        provenance TEXT CHECK(provenance IN ('RESEARCH','DERIVED','SYNTHETIC')),
        payload_json TEXT NOT NULL,
        FOREIGN KEY(case_id) REFERENCES cases(case_id)
    );

    CREATE TABLE IF NOT EXISTS personas (
        persona_id TEXT PRIMARY KEY,
        case_id TEXT,
        canonical_handle TEXT NOT NULL,
        platform TEXT NOT NULL,
        first_seen TIMESTAMP,
        last_seen TIMESTAMP,
        provenance TEXT NOT NULL,
        raw_uid INTEGER,
        raw_vid INTEGER,
        FOREIGN KEY(case_id) REFERENCES cases(case_id)
    );

    CREATE TABLE IF NOT EXISTS identifiers (
        identifier_id TEXT PRIMARY KEY,
        persona_id TEXT,
        identifier_type TEXT CHECK(identifier_type IN ('PGP_KEY','BTC_ADDRESS','ONION_URL','EMAIL','JABBER')),
        raw_value TEXT NOT NULL,
        normalized_value TEXT NOT NULL,
        provenance TEXT NOT NULL,
        first_seen TIMESTAMP,
        FOREIGN KEY(persona_id) REFERENCES personas(persona_id)
    );

    CREATE TABLE IF NOT EXISTS evidence (
        evidence_id TEXT PRIMARY KEY,
        case_id TEXT,
        relationship_id TEXT NOT NULL,
        source_persona_id TEXT,
        target_persona_id TEXT,
        evidence_type TEXT NOT NULL,
        polarity TEXT CHECK(polarity IN ('SUPPORTING','CONFLICTING')),
        confidence_weight REAL,
        description TEXT,
        provenance TEXT CHECK(provenance IN ('RESEARCH','DERIVED','SYNTHETIC')),
        source_event_id TEXT,
        challenge_status TEXT DEFAULT 'ACTIVE' CHECK(challenge_status IN ('ACTIVE','CHALLENGED')),
        created_at TIMESTAMP,
        FOREIGN KEY(case_id) REFERENCES cases(case_id),
        FOREIGN KEY(source_persona_id) REFERENCES personas(persona_id),
        FOREIGN KEY(target_persona_id) REFERENCES personas(persona_id)
    );

    CREATE TABLE IF NOT EXISTS evidence_challenges (
        challenge_id TEXT PRIMARY KEY,
        evidence_id TEXT,
        case_id TEXT,
        investigator_id TEXT,
        action TEXT CHECK(action IN ('CHALLENGE','RESTORE')),
        reason TEXT,
        previous_score REAL,
        new_score REAL,
        timestamp TIMESTAMP,
        FOREIGN KEY(evidence_id) REFERENCES evidence(evidence_id),
        FOREIGN KEY(case_id) REFERENCES cases(case_id)
    );

    CREATE TABLE IF NOT EXISTS stylometric_profiles (
        profile_id TEXT PRIMARY KEY,
        persona_id TEXT UNIQUE,
        sample_count INTEGER,
        avg_sentence_len REAL,
        sentence_len_var REAL,
        avg_word_len REAL,
        yules_k REAL,
        simpsons_d REAL,
        punctuation_vector_json TEXT,
        ngram_frequency_json TEXT,
        updated_at TIMESTAMP,
        FOREIGN KEY(persona_id) REFERENCES personas(persona_id)
    );

    CREATE TABLE IF NOT EXISTS replay_sessions (
        session_id TEXT PRIMARY KEY,
        case_id TEXT,
        status TEXT CHECK(status IN ('STOPPED','RUNNING','PAUSED')),
        speed REAL DEFAULT 1.0,
        current_cursor_timestamp TIMESTAMP,
        events_replayed INTEGER DEFAULT 0,
        started_at TIMESTAMP,
        updated_at TIMESTAMP,
        FOREIGN KEY(case_id) REFERENCES cases(case_id)
    );

    CREATE TABLE IF NOT EXISTS ground_truth_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id INTEGER,
        username TEXT,
        uid INTEGER,
        vid INTEGER,
        used_in_evaluation INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS investigator_notes (
        note_id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        entity_label TEXT,
        investigator_id TEXT DEFAULT 'investigator_1',
        note_text TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(case_id) REFERENCES cases(case_id)
    );

    -- Indexes for query performance (correlation engine, infra lookup, owner filter)
    CREATE INDEX IF NOT EXISTS idx_personas_case     ON personas(case_id);
    CREATE INDEX IF NOT EXISTS idx_identifiers_persona ON identifiers(persona_id);
    CREATE INDEX IF NOT EXISTS idx_evidence_case     ON evidence(case_id);
    CREATE INDEX IF NOT EXISTS idx_evidence_pair     ON evidence(source_persona_id, target_persona_id);
    CREATE INDEX IF NOT EXISTS idx_events_case       ON normalized_events(case_id, event_type);
    CREATE INDEX IF NOT EXISTS idx_cases_owner       ON cases(owner_id);
    """)

    # Runtime migration: safely add owner_id column to existing DBs
    try:
        cursor.execute("ALTER TABLE cases ADD COLUMN owner_id TEXT")
    except Exception:
        pass  # Column already exists - safe to ignore

    conn.commit()
    conn.close()
