"""
Sparse retrieval — BM25 over the full corpus.
Catches exact term matches (error codes, product names, ticket numbers).

The BM25 index is built in-memory each query from the stored corpus.
At 2,000–5,000 vectors this is fast enough; if it becomes a bottleneck
cache the corpus and rebuild only after ingestion.
"""
from __future__ import annotations

import logging
from rank_bm25 import BM25Okapi

from app.config import settings
from app.vectorstore.pgvector_store import VectorStore

log = logging.getLogger(__name__)


def _tokenise(text: str) -> list[str]:
    """Lowercase whitespace tokenisation — sufficient for IT terminology."""
    return text.lower().split()


def sparse_search(
    query: str,
    store: VectorStore,
    top_k: int | None = None,
) -> list[dict]:
    """
    Run BM25 over the full corpus and return top_k results.

    Returns list of dicts with keys:
        id, content, bm25_score
    """
    k = top_k or settings.retrieval_top_k

    corpus_rows = store.fetch_all_contents()
    if not corpus_rows:
        log.warning("BM25: empty corpus")
        return []

    corpus = [_tokenise(row["content"]) for row in corpus_rows]
    bm25 = BM25Okapi(corpus)

    query_tokens = _tokenise(query)
    scores = bm25.get_scores(query_tokens)

    # Pair scores with row ids, sort descending
    scored = sorted(
        zip(scores, corpus_rows),
        key=lambda x: x[0],
        reverse=True,
    )[:k]

    return [
        {"id": row["id"], "content": row["content"], "bm25_score": float(score)}
        for score, row in scored
        if score > 0  # BM25 score of 0 means zero term overlap
    ]
