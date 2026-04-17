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
from app.vectorstore.pgvector_store import VectorStore

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_store() -> VectorStore:
    return VectorStore()


def retrieve(query: str) -> tuple[list[dict], float]:
    """
    Run the full retrieval pipeline for a query.

    Returns:
        (top_chunks, top_similarity_score)
        - top_chunks: list of chunk dicts (top-N, reranked)
        - top_similarity_score: cosine similarity of the best dense hit
          (used for confidence threshold check)
    """
    store = _get_store()

    # Step 1: Dense retrieval
    dense_results = dense_search(query, store, top_k=settings.retrieval_top_k)

    # Step 2: Sparse retrieval
    sparse_results = sparse_search(query, store, top_k=settings.retrieval_top_k)

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
    top_chunks = rerank(query, fused, top_n=settings.retrieval_final_top_n)

    # Top similarity score from the best dense hit (before reranking)
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

    return top_chunks, top_similarity
