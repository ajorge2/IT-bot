"""
Central configuration — all settings read from environment variables.
Never import secrets directly; always go through this module.
"""
from __future__ import annotations

import json
from enum import Enum
from pydantic import Field, PostgresDsn, AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingProvider(str, Enum):
    azure_openai = "azure_openai"
    bedrock = "bedrock"
    self_hosted = "self_hosted"


class LLMProvider(str, Enum):
    anthropic = "anthropic"
    openai_compatible = "openai_compatible"   # Azure OpenAI, OpenAI, Ollama, etc.


class TicketProvider(str, Enum):
    servicenow = "servicenow"
    jira = "jira"
    freshservice = "freshservice"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- Database ---
    database_url: PostgresDsn

    # --- Embedding ---
    embedding_provider: EmbeddingProvider = EmbeddingProvider.azure_openai

    # Azure OpenAI
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_embedding_deployment: str = "text-embedding-3-small"
    azure_openai_api_version: str = "2024-02-01"

    # AWS Bedrock
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # Self-hosted BGE
    bge_model_name: str = "BAAI/bge-large-en-v1.5"

    # --- LLM ---
    llm_provider: LLMProvider = LLMProvider.anthropic

    # Anthropic
    anthropic_api_key: str = ""
    llm_deployment: str = "claude-opus-4-7"

    # OpenAI-compatible (Azure OpenAI, Ollama, etc.) — only needed when llm_provider=openai_compatible
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_api_version: str = ""

    # --- Confluence ---
    confluence_url: str = ""
    confluence_username: str = ""
    confluence_api_token: str = ""
    confluence_space_key: str = "IT"

    # --- SharePoint ---
    sharepoint_tenant_id: str = ""
    sharepoint_client_id: str = ""
    sharepoint_client_secret: str = ""
    sharepoint_site_url: str = ""

    # --- Ticketing ---
    ticket_provider: TicketProvider = TicketProvider.servicenow
    ticket_base_url: str = ""
    ticket_api_user: str = ""
    ticket_api_password: str = ""
    ticket_api_token: str = ""          # Jira alternative

    # --- Retrieval ---
    retrieval_top_k: int = 20
    retrieval_final_top_n: int = 5
    confidence_threshold: float = 0.6
    ticket_max_age_days: int = 548      # ~18 months

    # --- Reranker ---
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # --- API Security ---
    api_secret_key: str
    allowed_origins: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        v = self.allowed_origins.strip()
        if not v:
            return []
        if v.startswith("["):
            return json.loads(v)
        return [o.strip() for o in v.split(",") if o.strip()]

    # --- Simulation mode ---
    use_sample_data: bool = False   # set USE_SAMPLE_DATA=true to skip real connectors


settings = Settings()
