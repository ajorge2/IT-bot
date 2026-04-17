"""
LLM call — supports Anthropic SDK (default) and any OpenAI-compatible endpoint.
Set LLM_PROVIDER=anthropic (default) or LLM_PROVIDER=openai_compatible in .env.

The system prompt is marked for prompt caching on the Anthropic path — it's a
static prefix sent with every request, so it's the right breakpoint to cache.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from app.config import settings, LLMProvider

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Client factories (one instance per process, reused across requests)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_anthropic_client():
    import anthropic
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


@lru_cache(maxsize=1)
def _get_openai_client():
    from openai import AzureOpenAI, OpenAI
    if settings.llm_api_version:
        return AzureOpenAI(
            api_key=settings.llm_api_key,
            azure_endpoint=settings.llm_base_url,
            api_version=settings.llm_api_version,
        )
    return OpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def call_llm(messages: list[dict[str, str]]) -> str:
    """
    Call the configured LLM with the given messages list.
    Messages follow the OpenAI role/content format — system message is extracted
    and handled appropriately per provider.
    Returns the assistant's text response.
    """
    if settings.llm_provider == LLMProvider.anthropic:
        return _call_anthropic(messages)
    return _call_openai_compatible(messages)


# ---------------------------------------------------------------------------
# Anthropic path
# ---------------------------------------------------------------------------

def _call_anthropic(messages: list[dict[str, str]]) -> str:
    """
    Call Claude via the Anthropic SDK.
    - System message is passed as a top-level `system` parameter with
      cache_control so the static prefix is cached after the first call.
    - Uses streaming + get_final_message() to avoid HTTP timeout on large outputs.
    """
    system_blocks = [m for m in messages if m["role"] == "system"]
    user_messages  = [m for m in messages if m["role"] != "system"]

    system_text = system_blocks[0]["content"] if system_blocks else ""

    client = _get_anthropic_client()

    # Stream + get_final_message gives timeout protection without needing to
    # handle individual events.
    with client.messages.stream(
        model=settings.llm_deployment,
        max_tokens=1024,
        temperature=0.0,
        system=[
            {
                "type": "text",
                "text": system_text,
                # Cache the system prompt — it's static across every request.
                # Short prompts silently won't cache (< 4096 tokens on Opus 4.7)
                # but will cache automatically once the prompt grows.
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=user_messages,
    ) as stream:
        response = stream.get_final_message()

    text = next((b.text for b in response.content if b.type == "text"), "")

    log.info(
        "llm.call provider=anthropic model=%s tokens_in=%d tokens_out=%d "
        "cache_created=%d cache_read=%d",
        settings.llm_deployment,
        response.usage.input_tokens,
        response.usage.output_tokens,
        getattr(response.usage, "cache_creation_input_tokens", 0),
        getattr(response.usage, "cache_read_input_tokens", 0),
    )
    return text


# ---------------------------------------------------------------------------
# OpenAI-compatible path (Azure OpenAI, standard OpenAI, Ollama, etc.)
# ---------------------------------------------------------------------------

def _call_openai_compatible(messages: list[dict[str, str]]) -> str:
    client = _get_openai_client()
    response = client.chat.completions.create(
        model=settings.llm_deployment,
        messages=messages,  # type: ignore[arg-type]
        temperature=0.0,
        max_tokens=1024,
    )
    content = response.choices[0].message.content or ""
    log.info(
        "llm.call provider=openai_compatible tokens_in=%d tokens_out=%d",
        response.usage.prompt_tokens if response.usage else -1,
        response.usage.completion_tokens if response.usage else -1,
    )
    return content
