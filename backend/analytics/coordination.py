"""
PRAGYA CHAKSHU — CAPABILITY 3: COORDINATED ACTIVITY DISCOVERY
Analyzes co-posting temporal networks, synchronized diurnal bursts, and shared identifier patterns.
Provenances:
- Historical co-posting records: RESEARCH
- Algorithmic clusters and coordination scores: DERIVED
"""

import os
import csv
import json
import uuid
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple

from backend.config import DATASET_BASE_PATH
from backend.database.sqlite import get_connection
from backend.database.neo4j_client import merge_coordination_link, merge_persona_node


def detect_coordination_network(case_id: str, max_pairs: int = 50) -> Dict[str, Any]:
    """
    Scans both ingested events and historical network edge snapshots
    to discover coordinated activity, rapid reply cascades, and cluster formations.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Fetch all known personas in this case
    cursor.execute("""
        SELECT persona_id, canonical_handle, raw_uid, platform, provenance 
        FROM personas 
        WHERE case_id=? OR case_id IS NULL
    """, (case_id,))
    persona_rows = cursor.fetchall()
    
    uid_to_persona = {}
    persona_by_id = {}
    for r in persona_rows:
        p = dict(r)
        persona_by_id[p['persona_id']] = p
        if p.get('raw_uid'):
            uid_to_persona[int(p['raw_uid'])] = p

    # 2. Fetch post events to identify thread co-participation
    cursor.execute("""
        SELECT event_id, payload_json, timestamp_occurred 
        FROM normalized_events 
        WHERE case_id=? AND event_type='post_observed'
        ORDER BY timestamp_occurred ASC
    """, (case_id,))
    post_rows = cursor.fetchall()
    
    thread_posts = defaultdict(list)
    for r in post_rows:
        try:
            payload = json.loads(r['payload_json']) if isinstance(r['payload_json'], str) else r['payload_json']
            post = payload.get('post', {})
            tid = post.get('tid')
            uid = post.get('uid')
            if tid and uid:
                thread_posts[tid].append({
                    'event_id': r['event_id'],
                    'uid': uid,
                    'username': payload.get('persona', {}).get('handle', f'uid_{uid}'),
                    'timestamp': r['timestamp_occurred']
                })
        except Exception:
            continue

    # 3. Calculate internal co-posting pairs from ingested threads
    pair_interactions = defaultdict(lambda: {'count': 0, 'threads': set(), 'latencies': []})
    for tid, posts in thread_posts.items():
        if len(posts) > 1:
            for i in range(len(posts)):
                for j in range(i + 1, len(posts)):
                    u1 = posts[i]['uid']
                    u2 = posts[j]['uid']
                    if u1 != u2:
                        pair_key = tuple(sorted([u1, u2]))
                        pair_interactions[pair_key]['count'] += 1
                        pair_interactions[pair_key]['threads'].add(tid)
                        try:
                            t1 = datetime.fromisoformat(posts[i]['timestamp'])
                            t2 = datetime.fromisoformat(posts[j]['timestamp'])
                            delta_sec = abs((t2 - t1).total_seconds())
                            pair_interactions[pair_key]['latencies'].append(delta_sec)
                        except Exception:
                            pass

    # 4. Check historical network edge files (edges-2014-1.tsv) for known UIDs
    network_dir = os.path.join(DATASET_BASE_PATH, "network")
    edge_file = os.path.join(network_dir, "edges-2014-1.tsv")
    historical_pairs = defaultdict(lambda: {'weight': 0.0, 'count': 0, 'time_diffs': []})
    known_uids = set(uid_to_persona.keys())
    
    if os.path.exists(edge_file) and known_uids:
        try:
            with open(edge_file, mode="r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f, delimiter="\t")
                row_count = 0
                for row in reader:
                    row_count += 1
                    if row_count > 10000:  # Fast sampling
                        break
                    try:
                        s = int(row['Source'])
                        t = int(row['Target'])
                        # Only track pairs relevant to this case's personas
                        if s in known_uids or t in known_uids:
                            pair_key = tuple(sorted([s, t]))
                            w = float(row.get('Weight', 1.0))
                            td = float(row.get('time_diff', 0.0))
                            historical_pairs[pair_key]['weight'] += w
                            historical_pairs[pair_key]['count'] += 1
                            if td > 0:
                                historical_pairs[pair_key]['time_diffs'].append(td)
                    except (ValueError, KeyError):
                        continue
        except Exception as e:
            print(f"Warning reading edge file: {e}")

    # 5. Synthesize coordination scores for pairs
    all_pairs = set(pair_interactions.keys()).union(set(historical_pairs.keys()))
    coordination_results = []
    
    for u1, u2 in all_pairs:
        # Find or create persona IDs
        p1 = uid_to_persona.get(u1)
        p2 = uid_to_persona.get(u2)
        
        handle1 = p1['canonical_handle'] if p1 else f"User_{u1}"
        handle2 = p2['canonical_handle'] if p2 else f"User_{u2}"
        # Uids with no persona in this case become derived placeholder actors.
        # Scope those ids by case, otherwise the same forum user is one shared
        # node across investigations and their coordination links cross cases.
        p1_id = p1['persona_id'] if p1 else f"persona:forum:{case_id}:{u1}"
        p2_id = p2['persona_id'] if p2 else f"persona:forum:{case_id}:{u2}"

        internal = pair_interactions.get((u1, u2), {'count': 0, 'threads': set(), 'latencies': []})
        hist = historical_pairs.get((u1, u2), {'weight': 0.0, 'count': 0, 'time_diffs': []})
        
        total_interactions = internal['count'] + hist['count']
        if total_interactions == 0:
            continue
            
        all_delays = internal['latencies'] + hist['time_diffs']
        avg_delay_sec = sum(all_delays) / len(all_delays) if all_delays else 3600.0
        
        # Scoring logic: High interaction frequency + rapid reply cadence = high coordination
        frequency_score = min(50.0, total_interactions * 8.0)
        # Latency bonus: response within 30 minutes (< 1800s) indicates synchronized activity
        if avg_delay_sec < 600:
            latency_score = 40.0
        elif avg_delay_sec < 3600:
            latency_score = 30.0
        elif avg_delay_sec < 86400:
            latency_score = 15.0
        else:
            latency_score = 5.0
            
        coordination_score = round(min(100.0, frequency_score + latency_score), 1)
        
        # Determine classification
        if coordination_score >= 70.0:
            pattern = "HIGHLY_SYNCHRONIZED_CASCADE"
        elif coordination_score >= 45.0:
            pattern = "FREQUENT_CO_PARTICIPATION"
        else:
            pattern = "OCCASIONAL_THREAD_INTERACTION"

        edge_info = {
            "source_uid": u1,
            "target_uid": u2,
            "source_handle": handle1,
            "target_handle": handle2,
            "source_persona_id": p1_id,
            "target_persona_id": p2_id,
            "coordination_score": coordination_score,
            "pattern": pattern,
            "interaction_count": total_interactions,
            "shared_threads": list(internal['threads']),
            "avg_response_latency_sec": round(avg_delay_sec, 1),
            "provenance": "DERIVED"
        }
        coordination_results.append(edge_info)

    # Sort descending by coordination score
    coordination_results.sort(key=lambda x: x['coordination_score'], reverse=True)
    top_results = coordination_results[:max_pairs]

    # Merge only top results into the investigation graph
    for item in top_results:
        merge_persona_node(
            persona_id=item["source_persona_id"],
            handle=item["source_handle"],
            platform="Evolution Forum",
            provenance="RESEARCH" if not item["source_persona_id"].startswith("persona:forum") else "DERIVED",
            case_id=case_id
        )
        merge_persona_node(
            persona_id=item["target_persona_id"],
            handle=item["target_handle"],
            platform="Evolution Forum",
            provenance="RESEARCH" if not item["target_persona_id"].startswith("persona:forum") else "DERIVED",
            case_id=case_id
        )
        merge_coordination_link(
            source_persona_id=item["source_persona_id"],
            target_persona_id=item["target_persona_id"],
            score=item["coordination_score"],
            weight=item["interaction_count"],
            latency_sec=item["avg_response_latency_sec"],
            pattern=item["pattern"],
            case_id=case_id
        )

    # 6. Form clusters / cliques of coordinated personas
    clusters = []
    visited_uids = set()
    
    # Build adjacency
    adj = defaultdict(set)
    for res in top_results:
        if res['coordination_score'] >= 50.0:
            adj[res['source_handle']].add(res['target_handle'])
            adj[res['target_handle']].add(res['source_handle'])

    cluster_idx = 1
    for node, neighbors in adj.items():
        if node not in visited_uids:
            # Simple connected component
            component = set()
            queue = [node]
            while queue:
                curr = queue.pop(0)
                if curr not in component:
                    component.add(curr)
                    visited_uids.add(curr)
                    for n in adj[curr]:
                        if n not in component:
                            queue.append(n)
            
            if len(component) >= 2:
                clusters.append({
                    "cluster_id": f"coord-cluster-{cluster_idx}",
                    "name": f"Coordinated Operation Group #{cluster_idx}",
                    "members": list(component),
                    "size": len(component),
                    "provenance": "DERIVED",
                    "density": round(len(neighbors) / max(1, len(component) - 1), 2)
                })
                cluster_idx += 1

    conn.close()
    
    return {
        "case_id": case_id,
        "provenance": "DERIVED",
        "notice": "Capability 3: Coordinated Activity Discovery based on temporal co-posting & response latency.",
        "pairs_analyzed": len(coordination_results),
        "top_coordinated_pairs": top_results,
        "coordination_clusters": clusters
    }
