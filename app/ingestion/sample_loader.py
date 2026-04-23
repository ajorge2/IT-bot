"""
Sample data loader — substitutes for real Confluence/SharePoint/ticket connectors
when USE_SAMPLE_DATA=true. Reads from data/sample/ and returns the same
list[Document] format as the real loaders, with identical metadata schema.
"""
from __future__ import annotations

import logging
from pathlib import Path

from langchain_core.documents import Document

log = logging.getLogger(__name__)

SAMPLE_DIR = Path(__file__).parent.parent.parent / "data" / "sample"


def _parse_txt_header(text: str) -> tuple[dict, str]:
    """
    Extract the header fields (Title, Source URL, etc.) from the sample .txt files
    and return (metadata_dict, body_text).
    """
    meta: dict = {}
    lines = text.splitlines()
    body_start = 0

    for i, line in enumerate(lines):
        if line.startswith("---"):
            body_start = i + 1
            break
        if ": " in line:
            key, _, value = line.partition(": ")
            key = key.strip().lower().replace(" ", "_")
            meta[key] = value.strip()

    body = "\n".join(lines[body_start:]).strip()
    return meta, body


def _doc_type_from_path(path: Path) -> str:
    parent = path.parent.name
    if parent == "sharepoint":
        return "policy"
    name = path.stem.lower()
    if "policy" in name:
        return "policy"
    return "how-to"


def _source_system_from_path(path: Path) -> str:
    return path.parent.name   # "confluence" or "sharepoint"


def load_sample_confluence() -> list[Document]:
    docs: list[Document] = []
    for txt_file in sorted((SAMPLE_DIR / "confluence").glob("*.txt")):
        text = txt_file.read_text(encoding="utf-8")
        meta, body = _parse_txt_header(text)
        docs.append(Document(
            page_content=body,
            metadata={
                "source_system": "confluence",
                "document_title": meta.get("title", txt_file.stem),
                "source_url": meta.get("source_url", ""),
                "last_updated": meta.get("last_updated", ""),
                "document_type": meta.get("document_type", "how-to"),
            },
        ))
    log.info("Sample Confluence: loaded %d documents", len(docs))
    return docs


def load_sample_sharepoint() -> list[Document]:
    docs: list[Document] = []
    for txt_file in sorted((SAMPLE_DIR / "sharepoint").glob("*.txt")):
        text = txt_file.read_text(encoding="utf-8")
        meta, body = _parse_txt_header(text)
        docs.append(Document(
            page_content=body,
            metadata={
                "source_system": "sharepoint",
                "document_title": meta.get("title", txt_file.stem),
                "source_url": meta.get("source_url", ""),
                "last_updated": meta.get("last_updated", ""),
                "document_type": meta.get("document_type", "policy"),
            },
        ))
    log.info("Sample SharePoint: loaded %d documents", len(docs))
    return docs


def load_all_sample_sources() -> list[Document]:
    docs: list[Document] = []
    for name, fn in [
        ("confluence", load_sample_confluence),
        ("sharepoint", load_sample_sharepoint),
    ]:
        try:
            docs.extend(fn())
        except Exception as exc:
            log.error("Sample loader '%s' failed: %s", name, exc, exc_info=True)
    log.info("Sample data total: %d documents", len(docs))
    return docs
