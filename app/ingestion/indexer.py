"""
Orchestrates the full ingestion pipeline:
  load → chunk → embed → upsert into FAISS + SQLite → build BM25 index
"""
import logging
import pickle
from pathlib import Path
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi
from openai import OpenAI

from app.config import settings
from app.audit import log as audit_log
from app.ingestion.loaders import load_all_sources
from app.ingestion.chunker import chunk_documents
from app.vectorstore.faiss_store import FAISSStore

log = logging.getLogger(__name__)

openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)


def run_ingestion(clear_first: bool = False) -> dict[str, int]:
    audit_log.info("ingestion.started", clear_first=clear_first)

    # 1. Load
    docs: list[Document] = load_all_sources()

    # 2. Chunk
    chunks: list[Document] = chunk_documents(docs)

    # 3. Embed + store
    store = FAISSStore()

    if clear_first:
        store.clear()
        audit_log.info("ingestion.cleared_vector_store")

    texts = [c.page_content for c in chunks]
    metadatas = [c.metadata for c in chunks]

    response = openai_client.embeddings.create(input=texts, model=settings.OPENAI_EMBEDDING_MODEL)
    vectors = [item.embedding for item in response.data]
    store.upsert(texts=texts, embeddings=vectors, metadatas=metadatas)

    # 4. Build and persist BM25 index
    corpus_rows = store.fetch_all_contents()
    corpus = [row["content"].lower().split() for row in corpus_rows]
    bm25 = BM25Okapi(corpus)
    bm25_path = Path(settings.BM25_INDEX_PATH)
    bm25_path.parent.mkdir(parents=True, exist_ok=True)
    with open(bm25_path, "wb") as f:
        pickle.dump({"bm25": bm25, "corpus_rows": corpus_rows}, f)
    audit_log.info("ingestion.bm25_index_saved", path=str(bm25_path))

    result = {"documents_loaded": len(docs), "chunks_indexed": len(chunks)}
    audit_log.info("ingestion.completed", **result)
    return result
