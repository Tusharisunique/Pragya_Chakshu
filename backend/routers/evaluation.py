"""
PRAGYA CHAKSHU — EVALUATION BENCHMARK ROUTER
Endpoints for Capability 2 Evaluation Mode benchmark metrics.
"""

from fastapi import APIRouter, HTTPException, Query
from backend.analytics.evaluation import run_evaluation_benchmark

router = APIRouter(prefix="/cases", tags=["evaluation"])


@router.get("/{case_id}/evaluation/benchmark")
def get_evaluation_benchmark(
    case_id: str, threshold: float = Query(default=25.0, ge=0.0, le=100.0)
):
    """
    Computes precision, recall, and F1 metrics against the unrevealed ground truth
    at the given confidence score threshold (0-40 scale).
    """
    results = run_evaluation_benchmark(case_id=case_id, threshold=threshold)
    return results
