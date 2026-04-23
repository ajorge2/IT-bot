"""
FAISS-backed vector store with SQLite for metadata.

FAISS handles vector similarity search via an HNSW index.
SQLite stores all chunk text and metadata, keyed by the FAISS sequential ID.

Vectors are L2-normalised before indexing so that inner product == cosine similarity.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from app.config import settings

log = logging.getLogger(__name__)


class FAISSStore:
    def __init__(self) -> None:
        self._index_path = Path(settings.FAISS_INDEX_PATH)
        self._db_path = Path(settings.FAISS_DB_PATH)
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._index = self._load_or_create_index()
        self._conn = self._init_db()
        log.info("FAISSStore ready — %d vectors indexed", self._index.ntotal)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _load_or_create_index(self) -> faiss.Index:
        if self._index_path.exists():
            log.info("Loading existing FAISS index from %s", self._index_path)
            return faiss.read_index(str(self._index_path))

        log.info("Creating new FAISS HNSW index (dim=%d, M=%d)", settings.EMBEDDING_DIM, settings.FAISS_HNSW_M)
        index = faiss.IndexHNSWFlat(settings.EMBEDDING_DIM, settings.FAISS_HNSW_M)
        index.hnsw.efConstruction = settings.FAISS_HNSW_EF_CONSTRUCTION
        index.hnsw.efSearch = settings.FAISS_HNSW_EF_SEARCH
        return index

    def _init_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS kb_chunks (
                faiss_id     INTEGER PRIMARY KEY,
                content      TEXT NOT NULL,
                source_system  TEXT,
                document_title TEXT,
                source_url     TEXT,
                last_updated   TEXT,
                document_type  TEXT,
                chunk_index    INTEGER,
                total_chunks   INTEGER
            )
        """)
        conn.commit()
        return conn

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert(
        self,
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        vectors = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(vectors)

        # FAISS assigns sequential IDs starting from current ntotal
        start_id = self._index.ntotal

        rows = [
            (
                start_id + i,
                text,
                meta.get("source_system"),
                meta.get("document_title"),
                meta.get("source_url"),
                meta.get("last_updated"),
                meta.get("document_type"),
                meta.get("chunk_index"),
                meta.get("total_chunks"),
            )
            for i, (text, meta) in enumerate(zip(texts, metadatas))
        ]
        self._conn.executemany(
            """INSERT OR REPLACE INTO kb_chunks
               (faiss_id, content, source_system, document_title, source_url,
                last_updated, document_type, chunk_index, total_chunks)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        self._conn.commit()

        self._index.add(vectors)
        faiss.write_index(self._index, str(self._index_path))
        log.info("Upserted %d chunks — total indexed: %d", len(texts), self._index.ntotal)

    def clear(self) -> None:
        self._conn.execute("DELETE FROM kb_chunks")
        self._conn.commit()
        self._index = faiss.IndexHNSWFlat(settings.EMBEDDING_DIM, settings.FAISS_HNSW_M)
        self._index.hnsw.efConstruction = settings.FAISS_HNSW_EF_CONSTRUCTION
        self._index.hnsw.efSearch = settings.FAISS_HNSW_EF_SEARCH
        if self._index_path.exists():
            self._index_path.unlink()
        log.warning("FAISSStore cleared")

    # ------------------------------------------------------------------
    # Read — dense retrieval
    # ------------------------------------------------------------------

    def similarity_search(
        self,
        query_embedding: list[float],
        top_k: int,
    ) -> list[dict[str, Any]]:
        if self._index.ntotal == 0:
            return []

        query = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(query)

        k = min(top_k, self._index.ntotal)
        distances, faiss_ids = self._index.search(query, k)

        results = []
        for dist, fid in zip(distances[0], faiss_ids[0]):
            if fid == -1:
                continue
            row = self._conn.execute(
                """SELECT faiss_id, content, source_system, document_title,
                          source_url, last_updated, document_type, chunk_index
                   FROM kb_chunks WHERE faiss_id = ?""",
                (int(fid),),
            ).fetchone()
            if row:
                results.append({
                    "id":             row[0],
                    "content":        row[1],
                    "source_system":  row[2],
                    "document_title": row[3],
                    "source_url":     row[4],
                    "last_updated":   row[5],
                    "document_type":  row[6],
                    "chunk_index":    row[7],
                    "similarity":     float(dist),
                })
        return results

    # ------------------------------------------------------------------
    # Read — sparse retrieval corpus
    # ------------------------------------------------------------------

    def fetch_all_contents(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT faiss_id, content FROM kb_chunks ORDER BY faiss_id"
        ).fetchall()
        return [{"id": r[0], "content": r[1]} for r in rows]

    def fetch_by_ids(self, ids: list[int]) -> list[dict[str, Any]]:
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        rows = self._conn.execute(
            f"""SELECT faiss_id, content, source_system, document_title,
                       source_url, last_updated, document_type, chunk_index
                FROM kb_chunks WHERE faiss_id IN ({placeholders})""",
            ids,
        ).fetchall()
        cols = ["id", "content", "source_system", "document_title",
                "source_url", "last_updated", "document_type", "chunk_index"]
        return [dict(zip(cols, row)) for row in rows]
