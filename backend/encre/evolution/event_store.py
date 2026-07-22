from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class StoredEvent:
    """A single event in the append-only event store."""

    event_type: str
    data: dict[str, Any]
    session_id: str = ""
    turn_number: int = 0
    timestamp: float = field(default_factory=time.time)
    sequence: int = 0


EventHandler = Callable[[StoredEvent], None]


class EventStore:
    """Append-only event store for agent lifecycle events.

    Provides publish / replay / projection semantics on top of a persistent
    JSONL file.  Integrates with the existing ``EncreHookSystem`` to capture
    agent lifecycle events automatically.

    Usage::

        store = EventStore()
        store.register_handler("pre_tool_exec", my_handler)
        store.publish(StoredEvent("pre_tool_exec", {...}))
        store.replay("pre_tool_exec", limit=10)
        store.project("tool_usage", projector_fn)
    """

    def __init__(self, path: str | None = None) -> None:
        self._path = path or self._default_path()
        self._handlers: dict[str, list[EventHandler]] = {}
        self._sequence: int = 0
        self._ensure_file()

    def publish(self, event: StoredEvent) -> None:
        event.sequence = self._sequence
        self._sequence += 1
        self._append_to_file(event)
        for handler in self._handlers.get(event.event_type, []):
            try:
                handler(event)
            except Exception:
                pass

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
        limit: int = 0,
    ) -> list[StoredEvent]:
        """Replay events from the store, optionally filtered by type or session."""
        events: list[StoredEvent] = []
        for event in self._iterate():
            if event_type and event.event_type != event_type:
                continue
            if session_id and event.session_id != session_id:
                continue
            events.append(event)
            if limit and len(events) >= limit:
                break
        return events

    def project(
        self,
        projector: Callable[[list[StoredEvent]], dict[str, Any]],
        event_type: str | None = None,
    ) -> dict[str, Any]:
        """Run a projector function over the event stream.

        ``projector`` receives all matching events and returns a summary dict.
        """
        events = self.replay(event_type=event_type)
        return projector(events)

    def wire_hooks(self, hook_system: Any) -> None:
        """Connect the event store to an ``EncreHookSystem`` instance.

        Subscribes to all hook events and publishes them as ``StoredEvent``
        records.
        """
        event_types = [
            "pre_tool_exec", "post_tool_exec", "on_turn_start", "on_turn_end",
            "pre_model_request", "post_model_response", "on_error",
            "on_backend_error", "on_rate_limit", "pre_compact", "post_compact",
            "pre_sub_agent", "post_sub_agent",
        ]
        for et in event_types:
            handler_id = f"event_store_{et}"

            def _make_handler(_et: str = et):
                async def _handler(name: str, context: dict[str, Any], extra: Any = None) -> None:
                    self.publish(StoredEvent(
                        event_type=_et,
                        data={"name": name, "context": context, "extra": extra},
                    ))
                return _handler

            hook_system.register_handler(et, _make_handler(), handler_id=handler_id)

    def _append_to_file(self, event: StoredEvent) -> None:
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "event_type": event.event_type,
                    "data": event.data,
                    "session_id": event.session_id,
                    "turn_number": event.turn_number,
                    "timestamp": event.timestamp,
                    "sequence": event.sequence,
                }, ensure_ascii=False) + "\n")
        except (OSError, IOError):
            pass

    def _iterate(self) -> list[StoredEvent]:
        events: list[StoredEvent] = []
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        events.append(StoredEvent(
                            event_type=d["event_type"],
                            data=d.get("data", {}),
                            session_id=d.get("session_id", ""),
                            turn_number=d.get("turn_number", 0),
                            timestamp=d.get("timestamp", 0.0),
                            sequence=d.get("sequence", 0),
                        ))
                    except (json.JSONDecodeError, KeyError):
                        continue
        except (OSError, IOError):
            pass
        return events

    def _ensure_file(self) -> None:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        if not os.path.isfile(self._path):
            try:
                with open(self._path, "w", encoding="utf-8") as f:
                    f.write("")
            except OSError:
                pass

    def _default_path(self) -> str:
        from encre.config import get_data_dir
        return str(get_data_dir() / "events" / "event_store.jsonl")
