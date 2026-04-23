from app.config import settings


def build_messages(
    query: str,
    chunks: list[dict],
) -> list[dict[str, str]]:
    """
    Build the OpenAI-compatible messages list for the LLM call.

    Args:
        query:  The user's question.
        chunks: Retrieved context chunks (from retrieval pipeline).

    Returns:
        List of {"role": ..., "content": ...} dicts.
    """
    context_blocks = []
    for i, chunk in enumerate(chunks, start=1):
        title = chunk.get("document_title", "Unknown")
        url = chunk.get("source_url", "")
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

    return [
        {"role": "system", "content": settings.SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
