"""
LLM call — Anthropic Claude via the Anthropic SDK.
System prompt is marked for prompt caching to reduce token cost on repeated requests.
"""
import anthropic
import logging

from app.config import settings

log = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def call_llm(messages: list[dict[str, str]]) -> str:
    system_blocks = [m for m in messages if m["role"] == "system"]
    user_messages  = [m for m in messages if m["role"] != "system"]
    system_text = system_blocks[0]["content"] if system_blocks else ""


    with client.messages.stream(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=1024,
        temperature=0.0,
        system=[
            {
                "type": "text",
                "text": system_text,
                "cache_control": {
                    "type": "ephemeral",
                    "ttl": "5m"
                },
            }
        ],
        messages=user_messages,
    ) as stream:
        response = stream.get_final_message()

    text = next((b.text for b in response.content if b.type == "text"), "")

    log.info(
        "llm.call model=%s tokens_in=%d tokens_out=%d cache_created=%d cache_read=%d",
        settings.ANTHROPIC_MODEL,
        response.usage.input_tokens,
        response.usage.output_tokens,
        getattr(response.usage, "cache_creation_input_tokens", 0),
        getattr(response.usage, "cache_read_input_tokens", 0),
    )
    return text
