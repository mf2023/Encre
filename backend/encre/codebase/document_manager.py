#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DISCLAIMER: Users must comply with applicable AI regulations.
# Non-compliance may result in service termination or legal liability.

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
import httpx

# This module implements the reference-document store used by Encre to attach
# local files and web pages to a workspace.  Documents are persisted under
# ``<data_dir>/documents`` (an ``index.json`` manifest plus the raw content in
# ``files/``) and can be rendered into a single context string for the model.


class EncreDocument:
    """In-memory model describing a single reference document (local file or URL)."""
    id: str
    name: str
    source: str
    status: str
    original_url: str
    original_path: str
    content_path: str
    file_type: str
    size: int
    added_at: float

    def __init__(
        self,
        id: str = "",
        name: str = "",
        source: str = "",
        status: str = "ready",
        original_url: str = "",
        original_path: str = "",
        content_path: str = "",
        file_type: str = "",
        size: int = 0,
        added_at: float = 0.0,
    ) -> None:
        """Create a document with the given metadata (fields default to empty)."""
        self.id = id
        self.name = name
        self.source = source
        self.status = status
        self.original_url = original_url
        self.original_path = original_path
        self.content_path = content_path
        self.file_type = file_type
        self.size = size
        self.added_at = added_at

    def to_dict(self) -> dict[str, Any]:
        """Serialise the document metadata to a plain dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "status": self.status,
            "original_url": self.original_url,
            "original_path": self.original_path,
            "content_path": self.content_path,
            "file_type": self.file_type,
            "size": self.size,
            "added_at": self.added_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EncreDocument":
        """Reconstruct an :class:`EncreDocument` from a metadata dictionary."""
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            source=d.get("source", ""),
            status=d.get("status", "ready"),
            original_url=d.get("original_url", ""),
            original_path=d.get("original_path", ""),
            content_path=d.get("content_path", ""),
            file_type=d.get("file_type", ""),
            size=d.get("size", 0),
            added_at=d.get("added_at", 0.0),
        )


_MAX_CRAWL_PAGES = 30


def _strip_html(html: str) -> str:
    """Strip scripts/styles/nav/footer and tags from HTML, returning plain text."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<nav[^>]*>.*?</nav>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<footer[^>]*>.*?</footer>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:100000]


def _extract_same_domain_links(html: str, base_url: str, domain: str) -> set[str]:
    """Extract same-domain HTTP(S) links from an HTML page (for crawling)."""
    links: set[str] = set()
    for m in re.finditer(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE):
        href = m.group(1).strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.netloc == domain and parsed.scheme in ("http", "https"):
            clean = parsed._replace(fragment="").geturl()
            links.add(clean)
    return links


def crawl_url_to_text(name: str, url: str) -> str:
    """Fetch a web page and crawl up to ``_MAX_CRAWL_PAGES`` same-domain links.

    Returns a Markdown-ish concatenation of each page's stripped text.
    """
    if httpx is None:
        raise RuntimeError("httpx is required for URL documents. Install with: pip install httpx")
    parsed = urlparse(url)
    domain = parsed.netloc
    resp = httpx.get(url, follow_redirects=True, timeout=30)
    resp.raise_for_status()
    html = resp.text
    links = _extract_same_domain_links(html, url, domain)
    lines: list[str] = []
    lines.append(f"# {name or domain}")
    lines.append(f"Source: {url}")
    lines.append("")
    lines.append(f"## {url}")
    lines.append(_strip_html(html))
    visited = {url}
    count = 0
    for link in sorted(links):
        if count >= _MAX_CRAWL_PAGES:
            break
        if link in visited:
            continue
        visited.add(link)
        try:
            sub = httpx.get(link, follow_redirects=True, timeout=15)
            sub.raise_for_status()
            lines.append("")
            lines.append(f"## {link}")
            lines.append(_strip_html(sub.text))
            count += 1
        except Exception:
            pass
    return "\n".join(lines)


class EncreDocumentManager:
    """Manage CRUD and persistence of reference documents for a workspace."""
    def __init__(self, data_dir: str) -> None:
        """Initialise storage directories and load any persisted document index."""
        self._base_dir = Path(data_dir) / "documents"
        self._files_dir = self._base_dir / "files"
        self._index_path = self._base_dir / "index.json"
        self._documents: dict[str, EncreDocument] = {}
        self._load()

    def _ensure_dirs(self) -> None:
        """Create the ``files/`` storage directory if it does not exist."""
        self._files_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        """Load the document index manifest from disk into memory."""
        if not self._index_path.exists():
            return
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
            for item in data.get("documents", []):
                doc = EncreDocument.from_dict(item)
                self._documents[doc.id] = doc
        except Exception:
            self._documents.clear()

    def _save(self) -> None:
        """Persist the current document manifest to ``index.json``."""
        self._ensure_dirs()
        data = {
            "documents": [doc.to_dict() for doc in self._documents.values()],
        }
        self._index_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_content(self, doc: EncreDocument) -> str:
        """Read a document's textual content from its stored file (or original path)."""
        if not doc.content_path:
            if doc.source == "local" and doc.original_path:
                try:
                    p = Path(doc.original_path)
                    if p.exists():
                        return p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass
            return ""
        content_file = self._files_dir / doc.content_path
        if content_file.exists():
            try:
                return content_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
        return ""

    def add_from_local(self, name: str, file_path: str) -> EncreDocument:
        """Add a local file as a document, copying its bytes into storage."""
        src = Path(file_path)
        if not src.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        doc_id = uuid.uuid4().hex[:12]
        file_ext = src.suffix.lower()
        size = src.stat().st_size

        # Persist a copy under documents/files/ so the content survives even
        # if the user later moves or deletes the source file.
        self._ensure_dirs()
        content_file = f"{doc_id}{file_ext}"
        try:
            (self._files_dir / content_file).write_bytes(src.read_bytes())
        except Exception:
            content_file = ""

        doc = EncreDocument(
            id=doc_id,
            name=name or src.stem,
            source="local",
            original_path=str(src.resolve()),
            content_path=content_file,
            file_type=file_ext,
            size=size,
            added_at=time.time(),
        )
        self._documents[doc.id] = doc
        self._save()
        return doc

    def add_from_url(self, name: str, url: str) -> EncreDocument:
        """Crawl a URL (and same-domain links) to text and store it as a document."""
        full_text = crawl_url_to_text(name, url)
        doc_id = uuid.uuid4().hex[:12]
        parsed = urlparse(url)
        ext = Path(url.split("?")[0].split("#")[0]).suffix.lower() or ".html"
        content_file = f"{doc_id}.txt"
        self._ensure_dirs()
        (self._files_dir / content_file).write_text(full_text, encoding="utf-8")
        doc = EncreDocument(
            id=doc_id,
            name=name or parsed.netloc,
            source="url",
            original_url=url,
            content_path=content_file,
            file_type=ext,
            size=len(full_text.encode("utf-8")),
            added_at=time.time(),
        )
        self._documents[doc.id] = doc
        self._save()
        return doc

    def add_pending_url(self, name: str, url: str) -> EncreDocument:
        """Create a placeholder document with ``status="loading"`` for async crawl."""
        doc_id = uuid.uuid4().hex[:12]
        parsed = urlparse(url)
        domain = parsed.netloc
        ext = Path(url.split("?")[0].split("#")[0]).suffix.lower() or ".html"
        doc = EncreDocument(
            id=doc_id,
            name=name or domain,
            source="url",
            status="loading",
            original_url=url,
            file_type=ext,
            added_at=time.time(),
        )
        self._documents[doc.id] = doc
        self._save()
        return doc

    def finish_url_crawl(self, doc_id: str, full_text: str) -> EncreDocument | None:
        """Finalise a pending URL document once crawling completes."""
        doc = self._documents.get(doc_id)
        if doc is None:
            return None
        content_file = f"{doc_id}.txt"
        self._ensure_dirs()
        (self._files_dir / content_file).write_text(full_text, encoding="utf-8")
        doc.content_path = content_file
        doc.status = "ready"
        doc.size = len(full_text.encode("utf-8"))
        self._save()
        return doc

    def remove(self, doc_id: str) -> bool:
        """Remove a document (and its stored content file) from the manager."""
        doc = self._documents.pop(doc_id, None)
        if doc is None:
            return False
        if doc.content_path:
            cf = self._files_dir / doc.content_path
            if cf.exists():
                cf.unlink()
        self._save()
        return True

    def list_all(self) -> list[dict[str, Any]]:
        """Return metadata dictionaries for all stored documents."""
        return [doc.to_dict() for doc in self._documents.values()]

    def get(self, doc_id: str) -> dict[str, Any] | None:
        """Return a single document's metadata dict, or ``None`` if not found."""
        doc = self._documents.get(doc_id)
        return doc.to_dict() if doc else None

    def build_context(self) -> str:
        """Render all documents into a single reference-context string for the model."""
        parts: list[str] = []
        for doc in self._documents.values():
            content = self._read_content(doc)
            if not content:
                content = f"(Location: {doc.original_path or doc.original_url})"
            title = f"[{doc.name}]"
            if doc.source == "local":
                title += f" ({doc.original_path})"
            else:
                title += f" ({doc.original_url})"
            parts.append(f"--- {title} ---")
            parts.append(content[:8000])
            parts.append("")
        if not parts:
            return ""
        return "=== Reference Documents ===\n" + "\n".join(parts)
