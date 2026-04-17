"""
Embedding model wrapper — provider-agnostic interface.
All providers keep data inside the private cloud boundary.

Supported providers (set EMBEDDING_PROVIDER in .env):
  - azure_openai   : Azure OpenAI managed endpoint
  - bedrock        : AWS Bedrock Titan Embeddings
  - self_hosted    : Local BGE-large-en-v1.5 via sentence-transformers
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache

from app.config import settings, EmbeddingProvider


class BaseEmbedder(ABC):
    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        ...


class AzureOpenAIEmbedder(BaseEmbedder):
    def __init__(self) -> None:
        from openai import AzureOpenAI

        self._client = AzureOpenAI(
            api_key=settings.azure_openai_api_key,
            azure_endpoint=settings.azure_openai_endpoint,
            api_version=settings.azure_openai_api_version,
        )
        self._deployment = settings.azure_openai_embedding_deployment

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # Batch in groups of 16 to respect token limits
        results: list[list[float]] = []
        batch_size = 16
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = self._client.embeddings.create(input=batch, model=self._deployment)
            results.extend([item.embedding for item in resp.data])
        return results

    def embed_query(self, text: str) -> list[float]:
        resp = self._client.embeddings.create(input=[text], model=self._deployment)
        return resp.data[0].embedding


class BedrockEmbedder(BaseEmbedder):
    def __init__(self) -> None:
        import boto3

        session_kwargs: dict = {"region_name": settings.aws_region}
        if settings.aws_access_key_id:
            session_kwargs["aws_access_key_id"] = settings.aws_access_key_id
            session_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

        self._client = boto3.client("bedrock-runtime", **session_kwargs)

    def _embed(self, text: str) -> list[float]:
        import json

        body = json.dumps({"inputText": text})
        resp = self._client.invoke_model(
            modelId="amazon.titan-embed-text-v1",
            contentType="application/json",
            accept="application/json",
            body=body,
        )
        return json.loads(resp["body"].read())["embedding"]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class SelfHostedBGEEmbedder(BaseEmbedder):
    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(settings.bge_model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self._model.encode([text], normalize_embeddings=True)[0].tolist()


@lru_cache(maxsize=1)
def get_embedder() -> BaseEmbedder:
    """Return a cached embedder instance for the configured provider."""
    provider = settings.embedding_provider
    if provider == EmbeddingProvider.azure_openai:
        return AzureOpenAIEmbedder()
    elif provider == EmbeddingProvider.bedrock:
        return BedrockEmbedder()
    elif provider == EmbeddingProvider.self_hosted:
        return SelfHostedBGEEmbedder()
    else:
        raise ValueError(f"Unknown embedding provider: {provider}")
