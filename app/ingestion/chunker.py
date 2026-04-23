"""
Chunking — RecursiveCharacterTextSplitter with tiktoken for accurate token counting.
"""

import logging
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings

log = logging.getLogger(__name__)


def chunk_documents(docs: list[Document]) -> list[Document]:
    """
    Split documents into chunks, preserving all metadata from the parent.
    Adds chunk_index to metadata so ordering is recoverable.
    """
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=settings.CHUNK_TOKENS,
        chunk_overlap=settings.CHUNK_OVERLAP_TOKENS,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks: list[Document] = []
    for doc in docs:
        split_docs = splitter.split_documents([doc])
        for idx, chunk in enumerate(split_docs):
            chunk.metadata["chunk_index"] = idx
            chunk.metadata["total_chunks"] = len(split_docs)
            chunks.append(chunk)

    log.info("Chunked %d documents into %d chunks", len(docs), len(chunks))
    return chunks
