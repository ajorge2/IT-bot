"""
Dense retrieval — cosine similarity via FAISS HNSW index.
Returns top-K candidates with similarity scores.
"""
import voyageai

from app.config import settings
from app.vectorstore.faiss_store import FAISSStore

voyage = voyageai.Client(api_key=settings.VOYAGE_API_KEY)


def dense_search(
    query: str,
    store: FAISSStore,
    top_k: int | None = None,
) -> list[dict]:
    """
    Embed the query and retrieve top_k chunks by cosine similarity.

    Returns list of dicts with keys:
        id, content, source_system, document_title, source_url,
        last_updated, document_type, chunk_index, similarity
    """
    k = top_k or settings.RETRIEVAL_TOP_K
    query_vec = voyage.embed([query], model=settings.VOYAGE_MODEL, input_type="query").embeddings[0]

    results = store.similarity_search(query_embedding=query_vec, top_k=k)
    return results
