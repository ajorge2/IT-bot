"""
Prompt construction — manual, auditable, owned code.
The system prompt is non-negotiable per the architecture spec.
"""
from __future__ import annotations

SYSTEM_PROMPT = """You are an IT support assistant for a financial firm.
Answer ONLY using the provided context documents below.
If you are uncertain or the context is insufficient, state that clearly and add an explicit disclaimer.
Always cite your source by document title and URL at the end of your answer.
Do not invent information not present in the context.
Do not speculate about information not provided."""


def build_messages(
    query: str,
    chunks: list[dict],
    low_confidence: bool = False,
) -> list[dict[str, str]]:
    """
    Build the OpenAI-compatible messages list for the LLM call.

    Args:
        query:          The user's question.
        chunks:         Retrieved context chunks (from retrieval pipeline).
        low_confidence: If True, prepend a disclaimer instruction to the user message.

    Returns:
        List of {"role": ..., "content": ...} dicts.
    """
    # Format each chunk as a numbered context block with source metadata
    context_blocks = []
    for i, chunk in enumerate(chunks, start=1):
        title = chunk.get("document_title", "Unknown")
        url = chunk.get("source_url", "")
        system = chunk.get("source_system", "")
        doc_type = chunk.get("document_type", "")
        updated = chunk.get("last_updated", "")

        header = f"[{i}] {title}"
        if url:
            header += f" | {url}"
        if doc_type:
            header += f" | Type: {doc_type}"
        if updated:
            header += f" | Last updated: {updated}"

        context_blocks.append(f"{header}\n{chunk['content']}")

    context_text = "\n\n---\n\n".join(context_blocks)

    user_content = f"Context documents:\n\n{context_text}\n\n---\n\nQuestion: {query}"

    if low_confidence:
        user_content = (
            "NOTE: Retrieval confidence is LOW. Answer with your best effort "
            "but clearly state the uncertainty and add an explicit disclaimer "
            "that this information may not be accurate.\n\n"
        ) + user_content

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
