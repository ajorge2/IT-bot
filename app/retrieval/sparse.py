"""
Sparse retrieval — BM25 over the full corpus.
Catches exact term matches (error codes, product names, ticket numbers).

The BM25 index is built during ingestion and loaded from disk at query time.
"""
import logging
import pickle
from functools import lru_cache
from pathlib import Path

from app.config import settings

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _load_bm25():
    path = Path(settings.BM25_INDEX_PATH)
    if not path.exists():
        return None, []
    with open(path, "rb") as f:
        data = pickle.load(f)
    return data["bm25"], data["corpus_rows"]


def sparse_search(query: str, top_k: int | None = None) -> list[dict]:
    """
    Run BM25 over the full corpus and return top_k results.

    Returns list of dicts with keys:
        id, content, bm25_score
    """
    k = top_k or settings.RETRIEVAL_TOP_K

    bm25, corpus_rows = _load_bm25()
    if bm25 is None:
        log.warning("BM25: index not found at %s — run ingestion first", settings.BM25_INDEX_PATH)
        return []

    query_tokens = query.lower().split()
    scores = bm25.get_scores(query_tokens)

    scored = sorted(
        zip(scores, corpus_rows),
        key=lambda x: x[0],
        reverse=True,
    )[:k]

    return [
        {"id": row["id"], "content": row["content"], "bm25_score": float(score)}
        for score, row in scored
        if score > 0
    ]
