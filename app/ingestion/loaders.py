"""
Document loaders — LangChain loaders for Confluence, SharePoint, and tickets.
Returns a flat list of LangChain Document objects with normalised metadata.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any

from langchain_core.documents import Document

from app.config import settings, TicketProvider

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Confluence
# ---------------------------------------------------------------------------

def load_confluence() -> list[Document]:
    """Load all pages from the configured Confluence space."""
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
    if "how-to" in labels or "howto" in labels:
        return "how-to"
    return "how-to"


# ---------------------------------------------------------------------------
# SharePoint
# ---------------------------------------------------------------------------

def load_sharepoint() -> list[Document]:
    """Load documents from the configured SharePoint site via Microsoft Graph."""
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
    return "how-to"


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------

def load_tickets() -> list[Document]:
    """Load resolved tickets, discarding those older than TICKET_MAX_AGE_DAYS."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=settings.ticket_max_age_days)

    if settings.ticket_provider == TicketProvider.servicenow:
        return _load_servicenow(cutoff)
    elif settings.ticket_provider == TicketProvider.jira:
        return _load_jira(cutoff)
    elif settings.ticket_provider == TicketProvider.freshservice:
        return _load_freshservice(cutoff)
    else:
        raise ValueError(f"Unknown ticket provider: {settings.ticket_provider}")


def _load_servicenow(cutoff: datetime.datetime) -> list[Document]:
    import httpx

    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    url = (
        f"{settings.ticket_base_url}/api/now/table/incident"
        f"?sysparm_query=state=6^resolved_atON{cutoff_str}@javascript:gs.dateGenerate('{cutoff_str}')"
        f"&sysparm_fields=number,short_description,description,resolution_notes,resolved_at,sys_id"
        f"&sysparm_limit=1000"
    )
    resp = httpx.get(
        url,
        auth=(settings.ticket_api_user, settings.ticket_api_password),
        timeout=30,
    )
    resp.raise_for_status()

    docs = []
    for ticket in resp.json().get("result", []):
        resolved_at = ticket.get("resolved_at", "")
        content = (
            f"Issue: {ticket.get('short_description', '')}\n\n"
            f"Details: {ticket.get('description', '')}\n\n"
            f"Resolution: {ticket.get('resolution_notes', '')}"
        )
        docs.append(
            Document(
                page_content=content,
                metadata={
                    "source_system": "tickets",
                    "document_title": f"Ticket {ticket.get('number', '')}",
                    "source_url": f"{settings.ticket_base_url}/nav_to.do?uri=incident.do?sys_id={ticket.get('sys_id', '')}",
                    "last_updated": resolved_at,
                    "document_type": "ticket resolution",
                },
            )
        )
    log.info("ServiceNow: loaded %d resolved tickets", len(docs))
    return docs


def _load_jira(cutoff: datetime.datetime) -> list[Document]:
    import httpx

    cutoff_str = cutoff.strftime("%Y-%m-%d")
    jql = f'status = Done AND resolved >= "{cutoff_str}" ORDER BY resolved DESC'
    url = f"{settings.ticket_base_url}/rest/api/3/search"
    headers = {"Authorization": f"Bearer {settings.ticket_api_token}"}
    resp = httpx.get(
        url,
        params={"jql": jql, "fields": "summary,description,comment,resolutiondate,key", "maxResults": 1000},
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()

    docs = []
    for issue in resp.json().get("issues", []):
        fields = issue.get("fields", {})
        desc = fields.get("description") or ""
        if isinstance(desc, dict):
            desc = desc.get("content", [{}])[0].get("content", [{}])[0].get("text", "")
        content = f"Issue: {fields.get('summary', '')}\n\nDetails: {desc}"
        docs.append(
            Document(
                page_content=content,
                metadata={
                    "source_system": "tickets",
                    "document_title": f"Ticket {issue.get('key', '')}",
                    "source_url": f"{settings.ticket_base_url}/browse/{issue.get('key', '')}",
                    "last_updated": fields.get("resolutiondate", ""),
                    "document_type": "ticket resolution",
                },
            )
        )
    log.info("Jira: loaded %d resolved tickets", len(docs))
    return docs


def _load_freshservice(cutoff: datetime.datetime) -> list[Document]:
    import httpx, base64

    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    token = base64.b64encode(f"{settings.ticket_api_token}:X".encode()).decode()
    url = f"{settings.ticket_base_url}/api/v2/tickets"
    headers = {"Authorization": f"Basic {token}"}
    params = {"query": f'"status:5 AND updated_at:>\\"{cutoff_str}\\"', "per_page": 100}
    resp = httpx.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()

    docs = []
    for ticket in resp.json().get("tickets", []):
        content = (
            f"Issue: {ticket.get('subject', '')}\n\n"
            f"Details: {ticket.get('description_text', '')}"
        )
        docs.append(
            Document(
                page_content=content,
                metadata={
                    "source_system": "tickets",
                    "document_title": f"Ticket #{ticket.get('id', '')}",
                    "source_url": f"{settings.ticket_base_url}/helpdesk/tickets/{ticket.get('id', '')}",
                    "last_updated": ticket.get("updated_at", ""),
                    "document_type": "ticket resolution",
                },
            )
        )
    log.info("Freshservice: loaded %d resolved tickets", len(docs))
    return docs


def load_all_sources() -> list[Document]:
    """Load all configured sources and return combined document list."""
    if settings.use_sample_data:
        from app.ingestion.sample_loader import load_all_sample_sources
        log.info("USE_SAMPLE_DATA=true — loading from data/sample/ instead of live connectors")
        return load_all_sample_sources()

    docs: list[Document] = []
    errors: list[str] = []

    for name, loader_fn in [
        ("Confluence", load_confluence),
        ("SharePoint", load_sharepoint),
        ("Tickets", load_tickets),
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
