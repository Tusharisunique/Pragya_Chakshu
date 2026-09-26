"""
PRAGYA CHAKSHU — EVALUATION MODE BENCHMARK ENGINE
Computes rigorous forensic evaluation metrics (Precision, Recall, F1 Score, Confusion Matrix)
by comparing analytical correlations against the hidden ground truth (user-matching.tsv).

PROVENANCE & INTEGRITY RULES:
- Ground truth is strictly segregated from Investigator Mode.
- Analytical scores never have access to ground truth.
- Evaluation metrics are computed strictly for audit and benchmark purposes.
"""

from typing import Dict, List, Any, Optional
from backend.database.sqlite import get_connection
from backend.analytics.correlation import evaluate_persona_correlation

# Each independent supporting signal type beyond the first adds this much to a
# pair's score. A single weak signal should not be enough to claim that two
# accounts belong to the same person.
CORROBORATION_BONUS = 8.0

# Evidence confidence_weight is recorded on a 0-40 scale, not a percentage. The
# strongest single-signal tier the correlator emits is 25, so 25 is the natural
# cut: it keeps every well-supported link and drops weak ones. The previous
# default of 40 rejected everything, and callers passing 10 accepted everything.
DEFAULT_SCORE_THRESHOLD = 25.0


def run_evaluation_benchmark(case_id: str, threshold: float = DEFAULT_SCORE_THRESHOLD) -> Dict[str, Any]:
    """
    Evaluates all correlated persona pairs in the case against the ground truth matches.
    Computes TP, FP, FN, Precision, Recall, and F1 score at the specified confidence threshold.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Fetch known ground truth matches (uid <-> vid)
    cursor.execute("""
        SELECT match_id, username, uid, vid 
        FROM ground_truth_matches
    """)
    gt_rows = cursor.fetchall()

    # Map (uid, vid) -> match_id
    gt_pair_set = set()
    gt_by_username = {}
    for r in gt_rows:
        u = r["uid"]
        v = r["vid"]
        if u is not None and v is not None:
            gt_pair_set.add((int(u), int(v)))
        if r["username"]:
            gt_by_username[r["username"].lower()] = dict(r)

    # 2. Fetch all personas in this case
    cursor.execute(
        """
        SELECT persona_id, canonical_handle, platform, raw_uid, raw_vid, provenance 
        FROM personas 
        WHERE case_id=? OR case_id IS NULL
    """,
        (case_id,),
    )
    persona_rows = cursor.fetchall()
    personas = [dict(r) for r in persona_rows]

    # Map persona_id -> persona dict
    persona_map = {p["persona_id"]: p for p in personas}

    # 3. Find ground-truth positive pairs actually present in this case's dataset
    forum_personas = [p for p in personas if p.get("raw_uid") is not None]
    market_personas = [p for p in personas if p.get("raw_vid") is not None]

    case_ground_truth_pairs = set()
    for fp in forum_personas:
        for mp in market_personas:
            f_uid = int(fp["raw_uid"])
            m_vid = int(mp["raw_vid"])
            if (f_uid, m_vid) in gt_pair_set or fp["canonical_handle"].lower() == mp[
                "canonical_handle"
            ].lower():
                case_ground_truth_pairs.add((fp["persona_id"], mp["persona_id"]))

    # 4. Fetch or calculate correlations for candidate pairs in the case
    cursor.execute(
        """
        SELECT source_persona_id, target_persona_id, evidence_type, polarity,
               confidence_weight
        FROM evidence 
        WHERE case_id=? AND challenge_status='ACTIVE'
    """,
        (case_id,),
    )
    evidence_rows = cursor.fetchall()

    # If pre-stored evidence exists, use it directly; otherwise evaluate candidate pairs
    predicted_pairs = {}
    if evidence_rows:
        # Aggregate per pair, keeping polarity strictly separate.
        # CONFLICTING evidence is evidence *against* a shared identity, so it can
        # never create a prediction. Treating it as a prediction was the main
        # reason precision collapsed: the case held 3281 conflicting rows against
        # 318 supporting ones, and every one of them became a claimed match.
        support = {}
        against = {}
        for r in evidence_rows:
            pair = (r["source_persona_id"], r["target_persona_id"])
            weight = float(r["confidence_weight"] or 0.0)
            if r["polarity"] == "SUPPORTING":
                rec = support.setdefault(pair, {"weight": 0.0, "types": set()})
                rec["weight"] = max(rec["weight"], weight)
                rec["types"].add(r["evidence_type"])
            else:
                against[pair] = against.get(pair, 0) + 1

        for pair, rec in support.items():
            # Independent signal types corroborate one another, so each extra
            # type beyond the first strengthens the link.
            score = min(100.0, rec["weight"] + CORROBORATION_BONUS * (len(rec["types"]) - 1))
            if score < threshold:
                continue
            src, tgt = pair
            fp = persona_map.get(src, {})
            mp = persona_map.get(tgt, {})
            predicted_pairs[pair] = {
                "score": round(score, 1),
                "signal_types": sorted(t for t in rec["types"] if t),
                "conflicting_signals": against.get(pair, 0),
                "forum_handle": fp.get("canonical_handle", "Unknown"),
                "market_handle": mp.get("canonical_handle", "Unknown"),
                "forum_uid": fp.get("raw_uid"),
                "market_vid": mp.get("raw_vid"),
            }
    else:
        for fp in forum_personas:
            for mp in market_personas:
                p_res = evaluate_persona_correlation(
                    case_id, fp["persona_id"], mp["persona_id"]
                )
                if p_res:
                    score = p_res.get(
                        "correlation_score",
                        p_res.get("score", p_res.get("analytical_score", 0.0)),
                    )
                    if score >= threshold:
                        predicted_pairs[(fp["persona_id"], mp["persona_id"])] = {
                            "score": score,
                            "forum_handle": fp["canonical_handle"],
                            "market_handle": mp["canonical_handle"],
                            "forum_uid": fp["raw_uid"],
                            "market_vid": mp["raw_vid"],
                        }

    # 5. Compute Confusion Matrix
    tp_pairs = []
    fp_pairs = []

    for (p1, p2), pred_info in predicted_pairs.items():
        is_gt = (p1, p2) in case_ground_truth_pairs or (
            p2,
            p1,
        ) in case_ground_truth_pairs
        item = {
            **pred_info,
            "source_persona_id": p1,
            "target_persona_id": p2,
            "verified_ground_truth": is_gt,
        }
        if is_gt:
            tp_pairs.append(item)
        else:
            fp_pairs.append(item)

    # False Negatives: Ground truth pairs in this case that were NOT predicted above threshold
    fn_pairs = []
    for p1, p2 in case_ground_truth_pairs:
        if (p1, p2) not in predicted_pairs and (p2, p1) not in predicted_pairs:
            fp = persona_map.get(p1, {})
            mp = persona_map.get(p2, {})
            fn_pairs.append(
                {
                    "source_persona_id": p1,
                    "target_persona_id": p2,
                    "forum_handle": fp.get("canonical_handle", "Unknown"),
                    "market_handle": mp.get("canonical_handle", "Unknown"),
                    "forum_uid": fp.get("raw_uid"),
                    "market_vid": mp.get("raw_vid"),
                    "score_achieved": 0.0,
                }
            )

    tp_count = len(tp_pairs)
    fp_count = len(fp_pairs)
    fn_count = len(fn_pairs)

    # Precision, Recall, F1
    precision = round(tp_count / max(1, (tp_count + fp_count)) * 100.0, 1)
    recall = round(tp_count / max(1, (tp_count + fn_count)) * 100.0, 1)
    if precision + recall > 0:
        f1_score = round(2 * (precision * recall) / (precision + recall), 1)
    else:
        f1_score = 0.0

    conn.close()

    return {
        "case_id": case_id,
        "evaluation_mode": True,
        "threshold": threshold,
        "metrics": {
            "true_positives": tp_count,
            "false_positives": fp_count,
            "false_negatives": fn_count,
            "total_case_ground_truth": len(case_ground_truth_pairs),
            "precision_percent": precision,
            "recall_percent": recall,
            "f1_score": f1_score,
        },
        "true_positive_predictions": tp_pairs,
        "false_positive_predictions": fp_pairs,
        "missed_ground_truth_predictions": fn_pairs,
    }
