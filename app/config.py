"""
Central configuration — all settings read from environment variables.
Never import secrets directly; always go through this module.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # --- FAISS + SQLite store ---
    FAISS_INDEX_PATH: str = "data/faiss.index"
    FAISS_DB_PATH: str = "data/chunks.db"
    BM25_INDEX_PATH: str = "data/bm25.pkl"
    EMBEDDING_DIM: int = 1024
    FAISS_HNSW_M: int = 16
    FAISS_HNSW_EF_CONSTRUCTION: int = 200
    FAISS_HNSW_EF_SEARCH: int = 50

    # --- Voyage AI (embeddings) ---
    VOYAGE_API_KEY: str
    VOYAGE_MODEL: str = "voyage-finance-2"

    # --- Anthropic ---
    ANTHROPIC_API_KEY: str
    ANTHROPIC_MODEL: str = "claude-opus-4-7"
    SYSTEM_PROMPT: str = """You are an IT support assistant for a financial firm.
Answer ONLY using the provided context documents below.
When using information from a document, cite it inline using its number, e.g. [1] or [2].
If you are uncertain or the context is insufficient, state that clearly.
If context documents contain conflicting information, explicitly flag the conflict and cite which documents disagree rather than silently picking one.
At the end of your answer, list only the documents you cited with their title and URL.
Do not invent information not present in the context.
Do not speculate about information not provided."""

    # --- Chunking ---
    CHUNK_TOKENS: int = 512
    CHUNK_OVERLAP_TOKENS: int = 50

    # --- Retrieval ---
    RRF_K: int = 60
    RETRIEVAL_TOP_K: int = 20
    RETRIEVAL_FINAL_TOP_N: int = 5
    CONFIDENCE_THRESHOLD: float = 0.6

    # --- Reranker ---
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # --- API Security ---
    API_SECRET_KEY: str

    # --- Simulation mode ---
    USE_SAMPLE_DATA: bool = True


settings = Settings()
