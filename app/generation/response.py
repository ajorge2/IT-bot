"""
Response construction — parses which chunks the LLM cited, filters citations
to only those, and computes confidence from their similarity scores.
Citations are always present regardless of confidence level (non-negotiable).
"""
import re
from dataclasses import dataclass, field

from app.config import settings


@dataclass
class Citation:
    index: int
    document_title: str
    source_url: str
    source_system: str
    document_type: str
    last_updated: str
    doc_slug: str = ""


@dataclass
class BotResponse:
    answer: str
    citations: list[Citation]
    confidence_score: float
    low_confidence: bool
    disclaimer: str
    ticket_draft: dict | None = None

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
            "confidence_score": self.confidence_score,
            "low_confidence": self.low_confidence,
            "disclaimer": self.disclaimer,
            "ticket_draft": self.ticket_draft,
        }


def _parse_cited_indices(answer: str) -> set[int]:
    """Extract [N] citation references from the LLM's answer text."""
    return {int(m) for m in re.findall(r'\[(\d+)\]', answer)}


def _compute_confidence(cited_indices: set[int], chunks: list[dict]) -> float:
    """
    Average cosine similarity of the chunks the LLM actually cited.
    Falls back to all dense-retrieved chunks if no cited chunk has a similarity score
    (e.g. all cited chunks came from sparse-only retrieval).
    """
    cited_chunks = [chunks[i - 1] for i in cited_indices if 1 <= i <= len(chunks)]
    similarities = [c["similarity"] for c in cited_chunks if "similarity" in c]
    if similarities:
        return sum(similarities) / len(similarities)
    all_similarities = [c["similarity"] for c in chunks if "similarity" in c]
    return sum(all_similarities) / len(all_similarities) if all_similarities else 0.0


def build_response(
    llm_answer: str,
    chunks: list[dict],
) -> BotResponse:
    """
    Build a structured BotResponse from the raw LLM output and retrieved chunks.

    Parses which chunks the LLM cited, filters citations to only those,
    and computes confidence from their similarity scores.
    """
    cited_indices = _parse_cited_indices(llm_answer)

    citations = [
        Citation(
            index=i,
            document_title=chunks[i - 1].get("document_title", "Unknown"),
            source_url=chunks[i - 1].get("source_url", ""),
            source_system=chunks[i - 1].get("source_system", ""),
            document_type=chunks[i - 1].get("document_type", ""),
            last_updated=chunks[i - 1].get("last_updated", ""),
            doc_slug=chunks[i - 1].get("doc_slug", ""),
        )
        for i in sorted(cited_indices)
        if 1 <= i <= len(chunks)
    ]

    confidence_score = _compute_confidence(cited_indices, chunks)
    low_confidence = confidence_score < settings.CONFIDENCE_THRESHOLD

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
        confidence_score=confidence_score,
        low_confidence=low_confidence,
        disclaimer=disclaimer,
    )
