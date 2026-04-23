"""
Dense retrieval — cosine similarity via FAISS HNSW index.
Returns top-K candidates with similarity scores.
"""
from openai import OpenAI

from app.config import settings
from app.vectorstore.faiss_store import FAISSStore

openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)


def dense_search(
    query: str,
    store: FAISSStore,
    top_k: int | None = None,
) -> list[dict]:
    k = top_k or settings.RETRIEVAL_TOP_K
    response = openai_client.embeddings.create(input=[query], model=settings.OPENAI_EMBEDDING_MODEL)
    query_vec = response.data[0].embedding

    results = store.similarity_search(query_embedding=query_vec, top_k=k)
    return results
