from __future__ import annotations


import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class StoredEvent:
    """A single evolution-domain event persisted to the event log."""

    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    created_at: float = field(default_factory=time.time)


EventHandler = Callable[[StoredEvent], None]


class EventStore:
    """Append-only JSONL event store with in-process pub/sub handlers.

    Events are serialized one JSON object per line to ``path``.  Subscribers
    registered via :meth:`register_handler` are invoked synchronously on
    publish, and ``replay`` / ``project`` provide read access to history.
    """

    def __init__(self, path: str | None = None) -> None:
        self._path = path or self._default_path()
        self._handlers: dict[str, list[EventHandler]] = {}
        self._ensure_file()

    def publish(self, event: StoredEvent) -> None:
        for handler in self._handlers.get(event.event_type, []):
            try:
                handler(event)
            except Exception:
                pass
        self._append_to_file(event)

    def register_handler(self, event_type: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def unregister_handler(self, event_type: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def replay(
        self,
        event_type: str | None = None,
        session_id: str | None = None,
        limit: int | None = None,
    ) -> list[StoredEvent]:
        """Return stored events, newest first, optionally filtered."""
        events = []
        for event in self._iterate():
            if event_type and event.event_type != event_type:
                continue
            if session_id and event.session_id != session_id:
                continue
            events.append(event)
            if limit and len(events) >= limit:
                break
        events.reverse()
        return events

    def project(self, state: dict[str, Any], event: StoredEvent) -> dict[str, Any]:
        """Fold *event* into an accumulator state (reduce-style projection)."""
        state = dict(state)
        state[event.event_type] = event.payload
        return state

    def wire_hooks(self, hook_system: Any) -> None:
        """Bridge registered handlers onto an external hook bus."""
        for et in list(self._handlers.keys()):
            def _handler(event, _et: str = et) -> None:
                self.publish(event)
            try:
                hook_system.on(et, _handler)
            except Exception:
                pass

    def _append_to_file(self, event: StoredEvent) -> None:
        try:
            from encre.secure_io import append_jsonl

            append_jsonl(self._path, event.__dict__)
        except (OSError, IOError):
            pass

    def _iterate(self) -> list[StoredEvent]:
        result: list[StoredEvent] = []
        try:
            from encre.secure_io import read_jsonl

            for data in read_jsonl(self._path):
                try:
                    result.append(StoredEvent(**data))
                except (KeyError, TypeError):
                    continue
        except (OSError, IOError):
            pass
        return result

    def _ensure_file(self) -> None:
        if not os.path.isfile(self._path):
            try:
                with open(self._path, "w", encoding="utf-8") as f:
                    f.write("")
            except OSError:
                pass

    def _default_path(self) -> str:
        # Keep the event log beside ``evolution/state.json`` instead of in the
        # separate ``~/.encre`` root -- same data, previously two locations.
        try:
            from encre.paths import get_data_dir

            return str(get_data_dir("evolution", ensure=False) / "events.jsonl")
        except Exception:  # pragma: no cover - defensive
            return str(
                Path.home() / ".dunimd" / "encre" / "evolution" / "events.jsonl"
            )
