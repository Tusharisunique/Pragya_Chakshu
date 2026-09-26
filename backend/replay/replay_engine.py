import uuid
from datetime import datetime
import json
from backend.adapters.evolution_forum import stream_forum_posts, get_username_by_uid
from backend.adapters.evolution_market import (
    stream_market_vendors,
    stream_market_listings,
)
from backend.adapters.normalizer import (
    normalize_post_event,
    normalize_vendor_event,
    normalize_listing_event,
)
from backend.database.sqlite import get_connection
from backend.database.neo4j_client import (
    merge_persona_node,
    merge_post_node,
    merge_identifier_node,
    merge_listing_node,
)


def ingest_forum_posts(case_id, limit=20):
    conn = get_connection()
    cursor = conn.cursor()
    ingested_count = 0
    now = datetime.utcnow().isoformat()

    cursor.execute(
        "SELECT count(distinct source_record_id) FROM normalized_events WHERE case_id=? AND event_type='post_observed'",
        (case_id,),
    )
    offset_row = cursor.fetchone()
    offset = offset_row[0] if offset_row else 0

    for post in stream_forum_posts(offset=offset, limit=limit):
        uid = post.get("uid")
        username = get_username_by_uid(uid)
        normalized_event = normalize_post_event(post, case_id, username)

        cursor.execute(
            """
            INSERT INTO normalized_events 
            (event_id, case_id, event_type, timestamp_occurred, timestamp_ingested, source_dataset, source_record_id, provenance, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                normalized_event["event_id"],
                case_id,
                normalized_event["event_type"],
                normalized_event["timestamp_occurred"],
                now,
                normalized_event["source_dataset"],
                normalized_event["source_record_id"],
                normalized_event["provenance"],
                normalized_event["payload_json"],
            ),
        )

        payload = json.loads(normalized_event["payload_json"])

        # Persona handling for forum user
        cursor.execute(
            "SELECT persona_id FROM personas WHERE case_id=? AND raw_uid=?",
            (case_id, uid),
        )
        persona_row = cursor.fetchone()

        if persona_row:
            persona_id = persona_row["persona_id"]
            cursor.execute(
                "UPDATE personas SET last_seen=MAX(last_seen, ?) WHERE persona_id=?",
                (normalized_event["timestamp_occurred"], persona_id),
            )
        else:
            persona_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO personas (persona_id, case_id, canonical_handle, platform, first_seen, last_seen, provenance, raw_uid)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    persona_id,
                    case_id,
                    username,
                    "Evolution Forum",
                    normalized_event["timestamp_occurred"],
                    normalized_event["timestamp_occurred"],
                    "RESEARCH",
                    uid,
                ),
            )
            merge_persona_node(
                persona_id, username, "Evolution Forum", "RESEARCH", case_id
            )

        merge_post_node(
            post.get("pid"),
            post.get("tid"),
            post.get("seq_id"),
            normalized_event["timestamp_occurred"],
            payload["clean_text"][:100],
            "RESEARCH",
            persona_id,
            case_id,
        )

        for ident in payload["identifiers"]:
            cursor.execute(
                "SELECT identifier_id FROM identifiers WHERE persona_id=? AND identifier_type=? AND normalized_value=?",
                (persona_id, ident["type"], ident["normalized_value"]),
            )
            ident_row = cursor.fetchone()
            if ident_row:
                identifier_id = ident_row["identifier_id"]
            else:
                identifier_id = str(uuid.uuid4())
                cursor.execute(
                    """
                    INSERT INTO identifiers (identifier_id, persona_id, identifier_type, raw_value, normalized_value, provenance, first_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        identifier_id,
                        persona_id,
                        ident["type"],
                        ident["raw_value"],
                        ident["normalized_value"],
                        "RESEARCH",
                        normalized_event["timestamp_occurred"],
                    ),
                )

            merge_identifier_node(
                identifier_id,
                ident["type"],
                ident["normalized_value"],
                "RESEARCH",
                persona_id,
                post_pid=post.get("pid"),
                case_id=case_id,
            )

        ingested_count += 1

    conn.commit()
    conn.close()
    return {
        "ingested_count": ingested_count,
        "dataset": "forum_posts",
        "status": "success",
    }


def ingest_market_vendors(case_id, limit=20):
    conn = get_connection()
    cursor = conn.cursor()
    ingested_count = 0
    now = datetime.utcnow().isoformat()

    cursor.execute(
        "SELECT count(distinct source_record_id) FROM normalized_events WHERE case_id=? AND event_type='vendor_observed'",
        (case_id,),
    )
    offset_row = cursor.fetchone()
    offset = offset_row[0] if offset_row else 0

    for vendor in stream_market_vendors(offset=offset, limit=limit):
        vid = vendor.get("vid")
        username = vendor.get("username", "")
        if not username:
            continue

        normalized_event = normalize_vendor_event(vendor, case_id)

        cursor.execute(
            """
            INSERT INTO normalized_events 
            (event_id, case_id, event_type, timestamp_occurred, timestamp_ingested, source_dataset, source_record_id, provenance, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                normalized_event["event_id"],
                case_id,
                normalized_event["event_type"],
                normalized_event["timestamp_occurred"],
                now,
                normalized_event["source_dataset"],
                normalized_event["source_record_id"],
                normalized_event["provenance"],
                normalized_event["payload_json"],
            ),
        )

        payload = json.loads(normalized_event["payload_json"])

        # Vendor Persona handling
        cursor.execute(
            "SELECT persona_id FROM personas WHERE case_id=? AND raw_vid=?",
            (case_id, vid),
        )
        persona_row = cursor.fetchone()

        if persona_row:
            persona_id = persona_row["persona_id"]
            cursor.execute(
                "UPDATE personas SET last_seen=MAX(last_seen, ?) WHERE persona_id=?",
                (normalized_event["timestamp_occurred"], persona_id),
            )
        else:
            persona_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO personas (persona_id, case_id, canonical_handle, platform, first_seen, last_seen, provenance, raw_vid)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    persona_id,
                    case_id,
                    username,
                    "Evolution Market",
                    normalized_event["timestamp_occurred"],
                    normalized_event["timestamp_occurred"],
                    "RESEARCH",
                    vid,
                ),
            )
            merge_persona_node(
                persona_id, username, "Evolution Market", "RESEARCH", case_id
            )

        for ident in payload["identifiers"]:
            cursor.execute(
                "SELECT identifier_id FROM identifiers WHERE persona_id=? AND identifier_type=? AND normalized_value=?",
                (persona_id, ident["type"], ident["normalized_value"]),
            )
            ident_row = cursor.fetchone()
            if ident_row:
                identifier_id = ident_row["identifier_id"]
            else:
                identifier_id = str(uuid.uuid4())
                cursor.execute(
                    """
                    INSERT INTO identifiers (identifier_id, persona_id, identifier_type, raw_value, normalized_value, provenance, first_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        identifier_id,
                        persona_id,
                        ident["type"],
                        ident["raw_value"],
                        ident["normalized_value"],
                        "RESEARCH",
                        normalized_event["timestamp_occurred"],
                    ),
                )

            merge_identifier_node(
                identifier_id,
                ident["type"],
                ident["normalized_value"],
                "RESEARCH",
                persona_id,
            )

        ingested_count += 1

    conn.commit()
    conn.close()
    return {
        "ingested_count": ingested_count,
        "dataset": "market_vendors",
        "status": "success",
    }


def ingest_market_listings(case_id, limit=20):
    conn = get_connection()
    cursor = conn.cursor()
    ingested_count = 0
    now = datetime.utcnow().isoformat()

    cursor.execute(
        "SELECT count(distinct source_record_id) FROM normalized_events WHERE case_id=? AND event_type='listing_observed'",
        (case_id,),
    )
    offset_row = cursor.fetchone()
    offset = offset_row[0] if offset_row else 0

    for listing in stream_market_listings(offset=offset, limit=limit):
        lid = listing.get("lid")
        vid = listing.get("vid")
        title = listing.get("title", "")
        price = listing.get("price", "")
        pclass = listing.get("product_class", "")

        normalized_event = normalize_listing_event(listing, case_id)

        cursor.execute(
            """
            INSERT INTO normalized_events 
            (event_id, case_id, event_type, timestamp_occurred, timestamp_ingested, source_dataset, source_record_id, provenance, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                normalized_event["event_id"],
                case_id,
                normalized_event["event_type"],
                normalized_event["timestamp_occurred"],
                now,
                normalized_event["source_dataset"],
                normalized_event["source_record_id"],
                normalized_event["provenance"],
                normalized_event["payload_json"],
            ),
        )

        # Link listing to vendor persona if present, otherwise create placeholder
        cursor.execute(
            "SELECT persona_id FROM personas WHERE case_id=? AND raw_vid=?",
            (case_id, vid),
        )
        persona_row = cursor.fetchone()
        if persona_row:
            persona_id = persona_row["persona_id"]
        else:
            persona_id = str(uuid.uuid4())
            handle = f"Vendor_{vid}"
            cursor.execute(
                """
                INSERT INTO personas (persona_id, case_id, canonical_handle, platform, first_seen, last_seen, provenance, raw_vid)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    persona_id,
                    case_id,
                    handle,
                    "Evolution Market",
                    normalized_event["timestamp_occurred"],
                    normalized_event["timestamp_occurred"],
                    "RESEARCH",
                    vid,
                ),
            )
            merge_persona_node(
                persona_id, handle, "Evolution Market", "RESEARCH", case_id
            )

        merge_listing_node(
            lid, vid, title, price, pclass, "RESEARCH", persona_id, case_id
        )

        payload = json.loads(normalized_event["payload_json"])
        for ident in payload["identifiers"]:
            cursor.execute(
                "SELECT identifier_id FROM identifiers WHERE persona_id=? AND identifier_type=? AND normalized_value=?",
                (persona_id, ident["type"], ident["normalized_value"]),
            )
            ident_row = cursor.fetchone()
            if ident_row:
                identifier_id = ident_row["identifier_id"]
            else:
                identifier_id = str(uuid.uuid4())
                cursor.execute(
                    """
                    INSERT INTO identifiers (identifier_id, persona_id, identifier_type, raw_value, normalized_value, provenance, first_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        identifier_id,
                        persona_id,
                        ident["type"],
                        ident["raw_value"],
                        ident["normalized_value"],
                        "RESEARCH",
                        normalized_event["timestamp_occurred"],
                    ),
                )

            merge_identifier_node(
                identifier_id,
                ident["type"],
                ident["normalized_value"],
                "RESEARCH",
                persona_id,
            )

        ingested_count += 1

    conn.commit()
    conn.close()
    return {
        "ingested_count": ingested_count,
        "dataset": "market_listings",
        "status": "success",
    }


def ingest_initial_events(case_id, limit=20, source="forum"):
    if source == "vendors":
        return ingest_market_vendors(case_id, limit=limit)
    elif source == "listings":
        return ingest_market_listings(case_id, limit=limit)
    elif source == "all":
        r1 = ingest_forum_posts(case_id, limit=limit)
        r2 = ingest_market_vendors(case_id, limit=limit)
        r3 = ingest_market_listings(case_id, limit=limit)
        return {
            "ingested_count": r1["ingested_count"]
            + r2["ingested_count"]
            + r3["ingested_count"],
            "breakdown": {
                "forum_posts": r1["ingested_count"],
                "vendors": r2["ingested_count"],
                "listings": r3["ingested_count"],
            },
            "status": "success",
        }
    else:
        return ingest_forum_posts(case_id, limit=limit)
