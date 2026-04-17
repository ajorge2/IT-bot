"""
Response construction — injects citations and structures the final output.
Citations are always present regardless of confidence level (non-negotiable).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Citation:
    index: int
    document_title: str
    source_url: str
    source_system: str
    document_type: str
    last_updated: str


@dataclass
class BotResponse:
    answer: str
    citations: list[Citation]
    low_confidence: bool
    disclaimer: str
    ticket_draft: dict | None = None    # populated by confidence handler if needed

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "citations": [
                {
                    "index": c.index,
                    "document_title": c.document_title,
                    "source_url": c.source_url,
                    "source_system": c.source_system,
                    "document_type": c.document_type,
                    "last_updated": c.last_updated,
                }
                for c in self.citations
            ],
            "low_confidence": self.low_confidence,
            "disclaimer": self.disclaimer,
            "ticket_draft": self.ticket_draft,
        }


def build_response(
    llm_answer: str,
    chunks: list[dict],
    low_confidence: bool,
) -> BotResponse:
    """
    Build a structured BotResponse from the raw LLM output and retrieved chunks.

    Citations are always injected — every response cites its sources.
    """
    citations = [
        Citation(
            index=i + 1,
            document_title=chunk.get("document_title", "Unknown"),
            source_url=chunk.get("source_url", ""),
            source_system=chunk.get("source_system", ""),
            document_type=chunk.get("document_type", ""),
            last_updated=chunk.get("last_updated", ""),
        )
        for i, chunk in enumerate(chunks)
    ]

    disclaimer = ""
    if low_confidence:
        disclaimer = (
            "I couldn't find a great match for your question in the knowledge base, "
            "so this answer may not be fully accurate. "
            "If it doesn't help, contact the IT Helpdesk at ext. 4357 or submit a ticket."
        )

    return BotResponse(
        answer=llm_answer,
        citations=citations,
        low_confidence=low_confidence,
        disclaimer=disclaimer,
    )
