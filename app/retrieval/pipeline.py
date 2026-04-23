"""
Full hybrid retrieval pipeline:
  dense search → sparse search → RRF fusion → cross-encoder rerank

Returns the top-N chunks ready to be passed to the LLM.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from app.config import settings
from app.retrieval.dense import dense_search
from app.retrieval.sparse import sparse_search
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.reranker import rerank
from app.vectorstore.faiss_store import FAISSStore

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_store() -> FAISSStore:
    return FAISSStore()


def retrieve(query: str) -> tuple[list[dict], float]:
    """
    Run the full retrieval pipeline for a query.

    Returns:
        (top_chunks, top_similarity_score)
        - top_chunks: list of chunk dicts (top-N, reranked)
        - top_similarity_score: cosine similarity of the best dense hit,
          logged as a pre-LLM signal. Confidence gating uses post-LLM
          average similarity of cited chunks (computed in response.py).
    """
    store = _get_store()

    # Step 1: Dense retrieval
    dense_results = dense_search(query, store, top_k=settings.RETRIEVAL_TOP_K)

    # Step 2: Sparse retrieval
    sparse_results = sparse_search(query, top_k=settings.RETRIEVAL_TOP_K)

    # Step 3: Fetch full metadata for sparse-only hits (BM25 only has id + content)
    sparse_ids_without_meta = [
        r["id"] for r in sparse_results
        if not any(d["id"] == r["id"] for d in dense_results)
    ]
    if sparse_ids_without_meta:
        extra_rows = store.fetch_by_ids(sparse_ids_without_meta)
        extra_map = {r["id"]: r for r in extra_rows}
        for r in sparse_results:
            if r["id"] in extra_map:
                r.update(extra_map[r["id"]])

    # Step 4: RRF fusion
    fused = reciprocal_rank_fusion(dense_results, sparse_results)

    # Step 5: Rerank
    top_chunks = rerank(query, fused, top_n=settings.RETRIEVAL_FINAL_TOP_N)

    # Best dense similarity — logged as pre-LLM signal only
    top_similarity = dense_results[0]["similarity"] if dense_results else 0.0

    log.info(
        "retrieval.complete query_len=%d dense=%d sparse=%d fused=%d reranked=%d top_sim=%.3f",
        len(query),
        len(dense_results),
        len(sparse_results),
        len(fused),
        len(top_chunks),
        top_similarity,
    )

    # Per-result breakdown — emitted at DEBUG so production logs stay clean.
    # Enable with LOG_LEVEL=DEBUG during golden set eval.
    if log.isEnabledFor(logging.DEBUG):
        for rank, r in enumerate(dense_results, start=1):
            log.debug(
                "retrieval.dense rank=%d id=%s sim=%.4f title=%r",
                rank, r["id"], r.get("similarity", 0), r.get("document_title", ""),
            )
        for rank, r in enumerate(sparse_results, start=1):
            log.debug(
                "retrieval.sparse rank=%d id=%s bm25=%.4f title=%r",
                rank, r["id"], r.get("bm25_score", 0), r.get("document_title", ""),
            )
        for rank, r in enumerate(fused, start=1):
            log.debug(
                "retrieval.fused rank=%d id=%s rrf=%.6f dense_rank=%s sparse_rank=%s title=%r",
                rank, r["id"], r.get("rrf_score", 0),
                r.get("dense_rank", "—"), r.get("sparse_rank", "—"),
                r.get("document_title", ""),
            )
        for rank, r in enumerate(top_chunks, start=1):
            log.debug(
                "retrieval.reranked rank=%d id=%s rerank=%.4f rrf=%.6f dense_rank=%s sparse_rank=%s title=%r",
                rank, r["id"], r.get("rerank_score", 0), r.get("rrf_score", 0),
                r.get("dense_rank", "—"), r.get("sparse_rank", "—"),
                r.get("document_title", ""),
            )

    return top_chunks, top_similarity
