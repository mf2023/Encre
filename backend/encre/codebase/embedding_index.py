#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Rust-backed semantic code embedding index wrapper."""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from encre.codebase.ast_index import EncreASTIndex
from encre.native import build_embedding_slices as native_build_embedding_slices
from encre.native import load_embedding_index as native_load_embedding_index
from encre.native import save_embedding_index as native_save_embedding_index
from encre.native import search_embedding_index as native_search_embedding_index

logger = logging.getLogger("encre.codebase.embedding_index")

EmbeddingFn = Callable[[list[str]], list[list[float]]]


@dataclass
class EmbeddingSlice:
    file: str
    start_line: int
    end_line: int
    symbol: str
    kind: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmbeddingSlice:
        return cls(
            file=str(data["file"]),
            start_line=int(data["start_line"]),
            end_line=int(data["end_line"]),
            symbol=str(data.get("symbol", "")),
            kind=str(data.get("kind", "module")),
            text=str(data.get("text", "")),
        )


@dataclass
class EmbeddingHit:
    file: str
    start_line: int
    end_line: int
    symbol: str
    kind: str
    score: float
    text: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EmbeddingHit:
        return cls(
            file=str(data["file"]),
            start_line=int(data["start_line"]),
            end_line=int(data["end_line"]),
            symbol=str(data.get("symbol", "")),
            kind=str(data.get("kind", "module")),
            score=float(data.get("score", 0.0)),
            text=str(data.get("text", "")),
        )


class OpenAICompatibleEmbedding:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        model: str = "text-embedding-3-small",
        timeout: float = 60.0,
    ) -> None:
        self.api_key: str = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "OpenAICompatibleEmbedding requires an API key. Pass "
                "api_key=... or set the OPENAI_API_KEY environment variable."
            )
        self.base_url: str = base_url.rstrip("/")
        self.model: str = model
        self.timeout: float = timeout

    def __call__(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        import httpx

        payload: dict[str, Any] = {"model": self.model, "input": texts}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/embeddings"
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=self.timeout)
        except httpx.HTTPError as e:
            raise RuntimeError(f"Embedding request to {url} failed: {e}") from e
        if resp.status_code >= 400:
            raise RuntimeError(f"Embedding API error {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        items = data.get("data", [])
        if not isinstance(items, list) or len(items) != len(texts):
            raise RuntimeError(f"Embedding API returned unexpected payload shape: {data!r}")
        return [list(item["embedding"]) for item in items]


class EncreEmbeddingIndex:
    _META_NAME: str = "embedding_index.json"

    def __init__(
        self,
        workspace: str,
        ast_index: EncreASTIndex | None = None,
        embedding_fn: EmbeddingFn | None = None,
        embedding_dim: int | None = None,
        max_text_chars: int = 4000,
    ) -> None:
        self.workspace: str = workspace
        self._ast: EncreASTIndex = ast_index if ast_index is not None else EncreASTIndex(workspace)
        self._embedding_fn: EmbeddingFn | None = embedding_fn
        self._embedding_dim: int | None = embedding_dim
        self._max_text_chars: int = max_text_chars
        self._slices: list[EmbeddingSlice] = []
        self._vectors: list[list[float]] = []
        self._file_mtimes: dict[str, float] = {}
        self._indexed: bool = False
        self._lock = threading.Lock()
        self.load()

    @property
    def available(self) -> bool:
        return len(self._slices) > 0 and len(self._vectors) > 0

    @property
    def slice_count(self) -> int:
        return len(self._slices)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._embedding_fn is None:
            dim = self._embedding_dim or 0
            return [[0.0] * dim for _ in texts]
        raw = self._embedding_fn(texts)
        if not raw:
            return []
        if self._embedding_dim is None:
            self._embedding_dim = len(raw[0])
        return [list(map(float, row)) for row in raw]

    def scan(self) -> None:
        if not self._ast._indexed:
            self._ast.scan()
        payload = json.loads(native_build_embedding_slices(self.workspace, self._max_text_chars))
        slices = [EmbeddingSlice.from_dict(item) for item in payload.get("slices", [])]
        vectors = self._embed([sl.text for sl in slices]) if slices else []
        with self._lock:
            self._slices = slices
            self._vectors = vectors
            self._file_mtimes = {
                str(k): float(v) for k, v in payload.get("file_mtimes", {}).items()
            }
            self._indexed = True
        native_save_embedding_index(
            self.workspace,
            json.dumps([sl.to_dict() for sl in self._slices], ensure_ascii=False),
            json.dumps(self._vectors, ensure_ascii=False),
            json.dumps(self._file_mtimes, ensure_ascii=False),
            int(self._embedding_dim or 0),
        )

    def scan_incremental(self) -> None:
        if not self._indexed:
            self.scan()
            return
        if not self._ast._indexed:
            self._ast.scan()

        payload = json.loads(native_build_embedding_slices(self.workspace, self._max_text_chars))
        next_file_mtimes = {
            str(k): float(v) for k, v in payload.get("file_mtimes", {}).items()
        }
        next_slices = [EmbeddingSlice.from_dict(item) for item in payload.get("slices", [])]

        changed_files = {
            rel for rel, mtime in next_file_mtimes.items()
            if self._file_mtimes.get(rel) != mtime
        }
        deleted_files = set(self._file_mtimes) - set(next_file_mtimes)
        touched_files = changed_files | deleted_files
        if not touched_files:
            return

        kept_slices: list[EmbeddingSlice] = []
        kept_vectors: list[list[float]] = []
        for idx, sl in enumerate(self._slices):
            if sl.file in touched_files:
                continue
            kept_slices.append(sl)
            if idx < len(self._vectors):
                kept_vectors.append(self._vectors[idx])

        changed_slices = [sl for sl in next_slices if sl.file in changed_files]
        changed_vectors = self._embed([sl.text for sl in changed_slices]) if changed_slices else []

        with self._lock:
            self._slices = kept_slices + changed_slices
            self._vectors = kept_vectors + changed_vectors
            self._file_mtimes = next_file_mtimes
            self._indexed = True

        self.save()

    def search(self, query: str, k: int = 10) -> list[EmbeddingHit]:
        if not query:
            return []
        if not self._indexed:
            self.scan()
        q_vec = self._embed([query])
        if not q_vec:
            return []
        raw = json.loads(native_search_embedding_index(self.workspace, json.dumps(q_vec[0]), k))
        return [EmbeddingHit.from_dict(item) for item in raw]

    def _meta_path(self) -> Path:
        return Path(self.workspace) / ".encre" / self._META_NAME

    def save(self) -> None:
        native_save_embedding_index(
            self.workspace,
            json.dumps([sl.to_dict() for sl in self._slices], ensure_ascii=False),
            json.dumps(self._vectors, ensure_ascii=False),
            json.dumps(self._file_mtimes, ensure_ascii=False),
            int(self._embedding_dim or 0),
        )

    def load(self) -> bool:
        meta = self._meta_path()
        if not meta.exists():
            return False
        try:
            payload = json.loads(native_load_embedding_index(self.workspace))
        except Exception:
            return False
        with self._lock:
            self._slices = [EmbeddingSlice.from_dict(item) for item in payload.get("slices", [])]
            self._vectors = [
                [float(value) for value in row]
                for row in payload.get("vectors", [])
            ]
            self._file_mtimes = {
                str(k): float(v) for k, v in payload.get("file_mtimes", {}).items()
            }
            dim = int(payload.get("embedding_dim") or 0)
            self._embedding_dim = dim or self._embedding_dim
            self._indexed = True
        return True
