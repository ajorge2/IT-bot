"""
FastAPI backend — the single entry point for the chatbot UI and Teams bot.

Endpoints:
  POST /chat          — main query endpoint
  POST /ingest        — trigger re-ingestion (admin; requires secret header)
  GET  /health        — liveness probe

Security:
  - Admin endpoints gated by X-Admin-Secret header
  - All inputs validated by Pydantic models
  - No user-controlled strings ever interpolated into SQL
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Header, Depends, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import settings
from app.audit import log as audit_log
from app.retrieval.pipeline import retrieve
from app.generation.handler import generate_answer

log = logging.getLogger(__name__)

app = FastAPI(
    title="IT Knowledge Base Chatbot",
    description="Internal IT self-service chatbot for financial firm employees.",
)

app.mount("/ui", StaticFiles(directory="frontend", html=True), name="frontend")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    user_id: str = Field(..., min_length=1, max_length=128)   # for audit trail


class CitationOut(BaseModel):
    index: int
    document_title: str
    source_url: str
    source_system: str
    document_type: str
    last_updated: str
    doc_slug: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    confidence_score: float
    low_confidence: bool
    disclaimer: str
    ticket_draft: dict | None
    timestamp: str


class IngestResponse(BaseModel):
    documents_loaded: int
    chunks_indexed: int
    triggered_at: str


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def require_admin(x_admin_secret: str | None = Header(default=None)) -> None:
    if x_admin_secret != settings.API_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request) -> ChatResponse:
    """
    Main query endpoint. Runs the full retrieval + generation pipeline.
    """
    audit_log.info(
        "chat.request",
        user_id=req.user_id,
        query_len=len(req.query),
        client_ip=request.client.host if request.client else "unknown",
    )

    chunks, top_similarity = retrieve(req.query)
    response = generate_answer(req.query, chunks)

    audit_log.info(
        "chat.response",
        user_id=req.user_id,
        low_confidence=response.low_confidence,
        pre_llm_top_similarity=top_similarity,
        post_llm_confidence_score=response.confidence_score,
        num_citations=len(response.citations),
    )

    return ChatResponse(
        answer=response.answer,
        citations=[
            CitationOut(
                index=c.index,
                document_title=c.document_title,
                source_url=c.source_url,
                source_system=c.source_system,
                document_type=c.document_type,
                last_updated=c.last_updated,
                doc_slug=c.doc_slug,
            )
            for c in response.citations
        ],
        confidence_score=response.confidence_score,
        low_confidence=response.low_confidence,
        disclaimer=response.disclaimer,
        ticket_draft=response.ticket_draft,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


_SAMPLE_DIR = Path("data/sample")
_VALID_SOURCES = {"confluence", "sharepoint"}


@app.get("/sample-doc/{source}/{slug}")
def sample_doc(source: str, slug: str) -> dict:
    if source not in _VALID_SOURCES:
        raise HTTPException(status_code=404, detail="Not found")
    path = (_SAMPLE_DIR / source / slug).with_suffix(".txt")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    text = path.read_text(encoding="utf-8")
    meta: dict = {}
    lines = text.splitlines()
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("---"):
            body_start = i + 1
            break
        if ": " in line:
            key, _, value = line.partition(": ")
            meta[key.strip().lower().replace(" ", "_")] = value.strip()
    body = "\n".join(lines[body_start:]).strip()
    return {"title": meta.get("title", slug), "body": body,
            "source_system": source, "document_type": meta.get("document_type", ""),
            "last_updated": meta.get("last_updated", "")}


@app.post("/ingest", response_model=IngestResponse, dependencies=[Depends(require_admin)])
def ingest(clear_first: bool = False) -> IngestResponse:
    """
    Trigger re-ingestion from all configured sources.
    Requires X-Admin-Secret header.
    clear_first=true performs a full re-index (drops existing vectors first).
    """
    from app.ingestion.indexer import run_ingestion

    audit_log.info("ingest.triggered", clear_first=clear_first)
    result = run_ingestion(clear_first=clear_first)
    return IngestResponse(
        documents_loaded=result["documents_loaded"],
        chunks_indexed=result["chunks_indexed"],
        triggered_at=datetime.now(timezone.utc).isoformat(),
    )
