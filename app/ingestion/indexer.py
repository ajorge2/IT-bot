"""
Orchestrates the full ingestion pipeline:
  load → chunk → embed → upsert into pgvector

Called by the nightly re-index script and can be triggered manually.
"""
from __future__ import annotations

import logging
from langchain_core.documents import Document

from app.audit import log as audit_log
from app.ingestion.loaders import load_all_sources
from app.ingestion.chunker import chunk_documents
from app.embeddings.embedder import get_embedder
from app.vectorstore.pgvector_store import VectorStore

log = logging.getLogger(__name__)


def run_ingestion(clear_first: bool = False) -> dict[str, int]:
    """
    Run the full ingestion pipeline.

    Args:
        clear_first: If True, drop and recreate the vectors table before indexing.
                     Use only for full re-index, not incremental updates.

    Returns:
        {"documents_loaded": int, "chunks_indexed": int}
    """
    audit_log.info("ingestion.started", clear_first=clear_first)

    # 1. Load
    docs: list[Document] = load_all_sources()

    # 2. Chunk
    chunks: list[Document] = chunk_documents(docs)

    # 3. Embed + store
    embedder = get_embedder()
    store = VectorStore()

    if clear_first:
        store.clear()
        audit_log.info("ingestion.cleared_vector_store")

    texts = [c.page_content for c in chunks]
    metadatas = [c.metadata for c in chunks]

    vectors = embedder.embed_documents(texts)
    store.upsert(texts=texts, embeddings=vectors, metadatas=metadatas)

    result = {"documents_loaded": len(docs), "chunks_indexed": len(chunks)}
    audit_log.info("ingestion.completed", **result)
    return result
