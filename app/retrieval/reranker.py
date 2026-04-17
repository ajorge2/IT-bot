"""
Cross-encoder reranker — ms-marco-MiniLM-L-6-v2 (self-hostable, no data egress).
Re-scores the RRF-fused candidates before passing the final top-N to the LLM.

This is the biggest single accuracy lever in the pipeline.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from sentence_transformers import CrossEncoder

from app.config import settings

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_cross_encoder() -> CrossEncoder:
    log.info("Loading cross-encoder: %s", settings.reranker_model)
    return CrossEncoder(settings.reranker_model)


def rerank(
    query: str,
    candidates: list[dict],
    top_n: int | None = None,
) -> list[dict]:
    """
    Re-score candidates using the cross-encoder.

    Args:
        query:      The user's original query string.
        candidates: List of dicts from RRF, each must have a 'content' key.
        top_n:      Number of results to return after reranking.

    Returns:
        top_n candidates sorted by cross-encoder score descending,
        with 'rerank_score' added to each dict.
    """
    n = top_n or settings.retrieval_final_top_n
    if not candidates:
        return []

    cross_encoder = _get_cross_encoder()
    pairs = [(query, c["content"]) for c in candidates]
    scores = cross_encoder.predict(pairs)

    for candidate, score in zip(candidates, scores):
        candidate["rerank_score"] = float(score)

    reranked = sorted(candidates, key=lambda c: c["rerank_score"], reverse=True)
    return reranked[:n]
