"""
Dense retrieval — cosine similarity via pgvector.
Returns top-K candidates with similarity scores.
"""
from __future__ import annotations

from app.config import settings
from app.embeddings.embedder import get_embedder
from app.vectorstore.pgvector_store import VectorStore


def dense_search(
    query: str,
    store: VectorStore,
    top_k: int | None = None,
) -> list[dict]:
    """
    Embed the query and retrieve top_k chunks by cosine similarity.

    Returns list of dicts with keys:
        id, content, source_system, document_title, source_url,
        last_updated, document_type, chunk_index, similarity
    """
    k = top_k or settings.retrieval_top_k
    embedder = get_embedder()
    query_vec = embedder.embed_query(query)

    results = store.similarity_search(query_embedding=query_vec, top_k=k)
    return results
