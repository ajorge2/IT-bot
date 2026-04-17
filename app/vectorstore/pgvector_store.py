"""
pgvector-backed vector store.

Schema (auto-created on first use):
  - id           SERIAL PRIMARY KEY
  - content      TEXT
  - embedding    VECTOR(N)
  - source_system TEXT
  - document_title TEXT
  - source_url   TEXT
  - last_updated TEXT
  - document_type TEXT
  - chunk_index  INT
  - total_chunks INT
  - created_at   TIMESTAMPTZ DEFAULT now()

All SQL is parameterised — no user-controlled string interpolation.
"""
from __future__ import annotations

import logging
from typing import Any

import psycopg2
from pgvector.psycopg2 import register_vector

from app.config import settings

log = logging.getLogger(__name__)


class VectorStore:
    def __init__(self) -> None:
        self._conn_str = str(settings.database_url)
        self._conn = self._connect()
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _connect(self) -> psycopg2.extensions.connection:
        conn = psycopg2.connect(self._conn_str)
        register_vector(conn)
        return conn

    def _cursor(self):
        try:
            self._conn.isolation_level  # cheap ping
        except psycopg2.OperationalError:
            self._conn = self._connect()
        return self._conn.cursor()

    # ------------------------------------------------------------------
    # Schema bootstrap
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        with self._cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kb_chunks (
                    id             SERIAL PRIMARY KEY,
                    content        TEXT        NOT NULL,
                    embedding      VECTOR(1024),
                    source_system  TEXT,
                    document_title TEXT,
                    source_url     TEXT,
                    last_updated   TEXT,
                    document_type  TEXT,
                    chunk_index    INT,
                    total_chunks   INT,
                    created_at     TIMESTAMPTZ DEFAULT now()
                );
            """)
            # HNSW index for fast approximate nearest-neighbour search
            cur.execute("""
                CREATE INDEX IF NOT EXISTS kb_chunks_embedding_idx
                ON kb_chunks
                USING hnsw (embedding vector_cosine_ops);
            """)
        self._conn.commit()
        log.info("pgvector schema ready")

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert(
        self,
        texts: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Insert chunks. Uses INSERT — call clear() before a full re-index."""
        with self._cursor() as cur:
            for text, emb, meta in zip(texts, embeddings, metadatas):
                cur.execute(
                    """
                    INSERT INTO kb_chunks
                        (content, embedding, source_system, document_title,
                         source_url, last_updated, document_type,
                         chunk_index, total_chunks)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        text,
                        emb,
                        meta.get("source_system"),
                        meta.get("document_title"),
                        meta.get("source_url"),
                        meta.get("last_updated"),
                        meta.get("document_type"),
                        meta.get("chunk_index"),
                        meta.get("total_chunks"),
                    ),
                )
        self._conn.commit()
        log.info("Upserted %d chunks", len(texts))

    def clear(self) -> None:
        """Delete all chunks — used before a full re-index."""
        with self._cursor() as cur:
            cur.execute("TRUNCATE TABLE kb_chunks RESTART IDENTITY;")
        self._conn.commit()
        log.warning("Vector store cleared")

    # ------------------------------------------------------------------
    # Read — dense retrieval
    # ------------------------------------------------------------------

    def similarity_search(
        self,
        query_embedding: list[float],
        top_k: int,
        source_system: str | None = None,
        max_age_days: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Return top_k chunks by cosine similarity.
        Optionally filter by source_system and/or last_updated age.
        """
        filters: list[str] = []
        filter_params: list[Any] = []

        if source_system:
            filters.append("source_system = %s")
            filter_params.append(source_system)

        if max_age_days is not None:
            # Multiply interval by integer — avoids embedding the param inside a string literal
            filters.append("last_updated::date >= CURRENT_DATE - INTERVAL '1 day' * %s")
            filter_params.append(max_age_days)

        where_clause = ("WHERE " + " AND ".join(filters)) if filters else ""

        sql = f"""
            SELECT
                id,
                content,
                source_system,
                document_title,
                source_url,
                last_updated,
                document_type,
                chunk_index,
                1 - (embedding <=> %s::vector) AS similarity
            FROM kb_chunks
            {where_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        # embedding appears twice: once for similarity score, once for ORDER BY
        params: list[Any] = [query_embedding] + filter_params + [query_embedding, top_k]

        with self._cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]

        return [dict(zip(cols, row)) for row in rows]

    def fetch_all_contents(self) -> list[dict[str, Any]]:
        """Return id + content for all chunks — used to build BM25 corpus."""
        with self._cursor() as cur:
            cur.execute("SELECT id, content FROM kb_chunks ORDER BY id;")
            rows = cur.fetchall()
        return [{"id": r[0], "content": r[1]} for r in rows]

    def fetch_by_ids(self, ids: list[int]) -> list[dict[str, Any]]:
        """Fetch full chunk rows by a list of ids."""
        if not ids:
            return []
        with self._cursor() as cur:
            cur.execute(
                "SELECT id, content, source_system, document_title, source_url, "
                "last_updated, document_type, chunk_index "
                "FROM kb_chunks WHERE id = ANY(%s)",
                (ids,),
            )
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in rows]
