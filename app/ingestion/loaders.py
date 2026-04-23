"""
Document loaders — LangChain loaders for Confluence and SharePoint.
Returns a flat list of LangChain Document objects with normalised metadata.
"""
import logging
from typing import Any

from langchain_core.documents import Document

from app.config import settings

log = logging.getLogger(__name__)

how_to_terms = ["how-to", "how to", "howto", "instructions", "guide", "directions"]

# ---------------------------------------------------------------------------
# Confluence
# ---------------------------------------------------------------------------

def load_confluence() -> list[Document]:
    from langchain_community.document_loaders import ConfluenceLoader

    loader = ConfluenceLoader(
        url=settings.confluence_url,
        username=settings.confluence_username,
        api_key=settings.confluence_api_token,
        space_key=settings.confluence_space_key,
        include_attachments=False,
        limit=50,
    )
    raw_docs = loader.load()

    docs: list[Document] = []
    for doc in raw_docs:
        docs.append(
            Document(
                page_content=doc.page_content,
                metadata={
                    "source_system": "confluence",
                    "document_title": doc.metadata.get("title", ""),
                    "source_url": doc.metadata.get("source", ""),
                    "last_updated": doc.metadata.get("when", ""),
                    "document_type": _infer_doc_type_confluence(doc.metadata),
                },
            )
        )
    log.info("Confluence: loaded %d documents", len(docs))
    return docs


def _infer_doc_type_confluence(meta: dict[str, Any]) -> str:
    labels = [lbl.lower() for lbl in meta.get("labels", [])]
    if "policy" in labels:
        return "policy"
    if any(term in labels for term in how_to_terms):
        return "how-to"
    return "general"


# ---------------------------------------------------------------------------
# SharePoint
# ---------------------------------------------------------------------------

def load_sharepoint() -> list[Document]:
    from langchain_community.document_loaders.sharepoint import SharePointLoader

    loader = SharePointLoader(
        o365_credentials={
            "client_id": settings.sharepoint_client_id,
            "client_secret": settings.sharepoint_client_secret,
            "tenant_id": settings.sharepoint_tenant_id,
        },
        site_url=settings.sharepoint_site_url,
        recursive=True,
    )
    raw_docs = loader.load()

    docs: list[Document] = []
    for doc in raw_docs:
        docs.append(
            Document(
                page_content=doc.page_content,
                metadata={
                    "source_system": "sharepoint",
                    "document_title": doc.metadata.get("title", doc.metadata.get("name", "")),
                    "source_url": doc.metadata.get("source", ""),
                    "last_updated": doc.metadata.get("lastModifiedDateTime", ""),
                    "document_type": _infer_doc_type_sharepoint(doc.metadata),
                },
            )
        )
    log.info("SharePoint: loaded %d documents", len(docs))
    return docs


def _infer_doc_type_sharepoint(meta: dict[str, Any]) -> str:
    name = meta.get("name", "").lower()
    if "policy" in name:
        return "policy"
    if any(term in name for term in how_to_terms):
        return "how-to"
    return "general"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def load_all_sources() -> list[Document]:
    if settings.USE_SAMPLE_DATA:
        from app.ingestion.sample_loader import load_all_sample_sources
        log.info("USE_SAMPLE_DATA=true — loading from data/sample/ instead of live connectors")
        return load_all_sample_sources()

    docs: list[Document] = []
    errors: list[str] = []

    for name, loader_fn in [
        ("Confluence", load_confluence),
        ("SharePoint", load_sharepoint),
    ]:
        try:
            docs.extend(loader_fn())
        except Exception as exc:
            log.error("%s loader failed: %s", name, exc, exc_info=True)
            errors.append(name)

    if errors:
        log.warning("Sources that failed to load: %s", errors)
    log.info("Total documents loaded: %d", len(docs))
    return docs
