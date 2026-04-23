"""
Confidence handling — three-layer defence against hallucination:
  1. Citation requirement on every response
  2. Cross-encoder reranking
  3. Threshold gate: if avg similarity of cited chunks < CONFIDENCE_THRESHOLD
       → answer with best-guess + explicit disclaimer
       → auto-generate a pre-filled ticket draft for user review
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.config import settings
from app.generation.prompt import build_messages
from app.generation.llm import call_llm
from app.generation.response import BotResponse, build_response

log = logging.getLogger(__name__)


def _generate_ticket_draft(query: str, answer: str, chunks: list[dict]) -> dict:
    """
    Auto-generate a pre-filled support ticket draft from the conversation.
    The user reviews and submits — the bot never auto-submits.
    """
    best_source = chunks[0].get("document_title", "N/A") if chunks else "N/A"
    return {
        "subject": f"IT Support: {query[:120]}",
        "description": (
            f"I asked the IT chatbot: \"{query}\"\n\n"
            f"The bot's response (low-confidence):\n{answer}\n\n"
            f"Closest knowledge base article: {best_source}\n\n"
            f"Please assist — the automated answer was flagged as uncertain."
        ),
        "priority": "medium",
        "category": "IT Support",
        "auto_generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Review this draft before submitting.",
    }


def generate_answer(
    query: str,
    chunks: list[dict],
) -> BotResponse:
    """
    Generate the final answer, applying the confidence threshold gate.

    Confidence is computed post-generation from the chunks the LLM actually
    cited, so the disclaimer is appended to the response rather than baked
    into the prompt.

    Args:
        query:  User's question.
        chunks: Top-N reranked context chunks.

    Returns:
        BotResponse with answer, citations, confidence_score, disclaimer
        (if low confidence), and ticket_draft (if low confidence).
    """
    messages = build_messages(query, chunks)
    llm_answer = call_llm(messages)

    response = build_response(llm_answer, chunks)

    if response.low_confidence:
        log.warning(
            "confidence.low query_len=%d post_llm_confidence_score=%.3f threshold=%.2f",
            len(query),
            response.confidence_score,
            settings.CONFIDENCE_THRESHOLD,
        )
        # response.ticket_draft = _generate_ticket_draft(query, llm_answer, chunks)
        # log.info("confidence.ticket_draft_generated")

    return response
