#!/usr/bin/env python3

"""Rust-backed workspace code index wrapper."""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from encre.native import build_code_context as native_build_code_context
from encre.native import build_code_index as native_build_code_index
from encre.native import load_code_index as native_load_code_index
from encre.native import search_code_index as native_search_code_index
from encre.native import update_code_index as native_update_code_index

logger = logging.getLogger("encre.codebase.indexer")


@dataclass
class ModuleInfo:
    path: str
    name: str
    imports: list[str] = field(default_factory=list)
    imported_by: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    language: str = ""
    loc: int = 0


class EncreCodeIndex:
    """Compatibility wrapper around the native Rust code index."""

    _KNOWN_EXTS: ClassVar[set[str]] = {
        ".py", ".pyi", ".pyx",
        ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
        ".rs", ".go",
        ".java", ".rb", ".php",
        ".c", ".cpp", ".h", ".hpp", ".cc", ".cxx",
        ".swift", ".kt", ".scala",
        ".sh", ".bash", ".zsh",
        ".sql",
        ".html", ".htm", ".css", ".scss", ".sass", ".less",
        ".json", ".yaml", ".yml", ".toml",
        ".md", ".rst",
    }
    _MAX_FILE_SIZE: int = 2 * 1024 * 1024

    def __init__(self, workspace: str) -> None:
        self.workspace: str = workspace
        self._modules: dict[str, ModuleInfo] = {}
        self._depgraph: dict[str, set[str]] = {}
        self._reverse_depgraph: dict[str, set[str]] = {}
        self._inverted_index: dict[str, list[str]] = {}
        self._total_docs: int = 0
        self._indexed: bool = False
        self._file_mtimes: dict[str, float] = {}
        self._watcher_task: asyncio.Task | None = None
        self._has_git: bool = False
        self._has_gitignore: bool = False
        self._gitignored_count: int = 0
        self._need_reindex: bool = False
        self._query_ready: bool = False

    def _load_from_native_payload(self, data: dict) -> None:
        self._modules.clear()
        for path, mod_data in data.get("modules", {}).items():
            self._modules[path] = ModuleInfo(**mod_data)
        self._file_mtimes = data.get("file_mtimes", {})
        self._has_git = data.get("has_git", False)
        self._has_gitignore = data.get("has_gitignore", False)
        self._gitignored_count = data.get("gitignored_count", 0)
        self._inverted_index = {}
        self._total_docs = len(self._modules)
        self._depgraph = {path: set() for path in self._modules}
        self._reverse_depgraph = {path: set() for path in self._modules}
        for mod in self._modules.values():
            for importer in mod.imported_by:
                self._reverse_depgraph.setdefault(mod.path, set()).add(importer)
                self._depgraph.setdefault(importer, set()).add(mod.path)
        self._query_ready = False
        self._indexed = True

    def scan(self, progress_cb: callable | None = None) -> None:
        ws = Path(self.workspace).resolve()
        if not ws.exists():
            self._indexed = True
            return
        if progress_cb:
            progress_cb("_build_native_index", 0, 1)
        data = json.loads(native_build_code_index(self.workspace))
        self._load_from_native_payload(data)
        self.prepare_query()
        if progress_cb:
            total = len(self._modules)
            progress_cb("_done", total, max(total, 1))

    def scan_incremental(self, progress_cb: callable | None = None) -> None:
        ws = Path(self.workspace).resolve()
        if not ws.exists():
            self._indexed = True
            return
        if not self._indexed:
            self.scan(progress_cb=progress_cb)
            return
        if progress_cb:
            progress_cb("_update_native_index", 0, 1)
        data = json.loads(native_update_code_index(self.workspace))
        self._load_from_native_payload(data)
        self.prepare_query()
        if progress_cb:
            total = len(self._modules)
            progress_cb("_done", total, max(total, 1))

    async def watch(self) -> asyncio.Task | None:
        try:
            import watchfiles
        except ImportError:
            return None

        if self._watcher_task is not None and not self._watcher_task.done():
            return self._watcher_task

        ws = Path(self.workspace).resolve()
        if not ws.exists():
            return None

        async def _watcher_loop() -> None:
            try:
                async for _changes in watchfiles.awatch(str(ws)):
                    self.scan_incremental()
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        self._watcher_task = asyncio.create_task(_watcher_loop())
        return self._watcher_task

    def stop_watch(self) -> None:
        if self._watcher_task is not None and not self._watcher_task.done():
            self._watcher_task.cancel()
            self._watcher_task = None

    def load(self) -> bool:
        storage = Path(self.workspace) / ".encre" / "code_index.json"
        if not storage.exists():
            return False
        try:
            data = json.loads(native_load_code_index(self.workspace))
            if data.get("workspace") != self.workspace:
                return False
            self._load_from_native_payload(data)
            return True
        except Exception:
            try:
                data = json.loads(storage.read_text(encoding="utf-8"))
                if data.get("workspace") != self.workspace:
                    return False
                self._load_from_native_payload(data)
                return True
            except Exception:
                self._modules.clear()
                self._file_mtimes.clear()
                return False

    def _ensure_query_ready(self) -> None:
        if self._query_ready:
            return
        self._query_ready = True

    def prepare_query(self) -> None:
        self._ensure_query_ready()

    def build_dependency_graph(self) -> dict[str, set[str]]:
        if not self._indexed:
            self.scan()
        self._ensure_query_ready()
        return dict(self._depgraph)

    def get_importers(self, file_path: str) -> list[str]:
        if not self._indexed:
            self.scan()
        self._ensure_query_ready()
        return list(self._reverse_depgraph.get(file_path, set()))

    def find_relevant(self, query: str, limit: int = 10) -> list[tuple[str, float]]:
        if not self._indexed:
            self.scan()
        if not query.strip():
            return []
        raw = json.loads(native_search_code_index(self.workspace, query, limit))
        return [(str(path), float(score)) for path, score in raw]

    def build_context(self, file_path: str) -> str:
        if not self._indexed:
            self.scan()
        try:
            return native_build_code_context(self.workspace, file_path)
        except Exception:
            return ""

    def get_module_info(self, file_path: str) -> ModuleInfo | None:
        if not self._indexed:
            self.scan()
        return self._modules.get(file_path)

    def list_all_modules(self) -> list[ModuleInfo]:
        if not self._indexed:
            self.scan()
        return list(self._modules.values())

    def search_by_name(self, query: str, limit: int = 50) -> list[ModuleInfo]:
        if not self._indexed:
            self.scan()
        q = query.lower().strip()
        if not q:
            return []
        results = [
            mod for mod in self._modules.values()
            if q in mod.path.lower() or q in mod.name.lower()
        ]
        results.sort(key=lambda mod: mod.path.lower())
        return results[:limit]
