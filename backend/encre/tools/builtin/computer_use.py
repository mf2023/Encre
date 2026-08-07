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

"""Unified ``computer_use`` tool -- single schema for browser & desktop.

This is the tool Codex / Manus / Claude Code all expose to their
models: a *single* ``action`` field with a curated enum, and a
``target`` field that picks browser or desktop behind the scenes.

Compared to calling the ``browser`` and ``desktop`` tools directly,
``computer_use`` gives the agent three things:

1. A smaller, curated action surface that's easy to plan against.
2. A trajectory buffer that remembers the last ``N`` actions --
   ``computer_use`` action ``"trajectory"`` returns the history so a
   multi-step loop can avoid repeating itself.
3. A step budget (default 200) that the session enforces -- beyond it
   the tool refuses to dispatch and returns an explicit error.

Use this tool for visual / interactive automation where the agent
needs a single, model-friendly API.  Use ``browser`` / ``desktop``
directly for fine-grained scripting where you know exactly which
backend you want.
"""

import json
import logging
from typing import Any

from encre.tools.base import build_tool

logger = logging.getLogger("encre.tools.computer_use")

# Process-wide session.  A long-lived agent process can accumulate a
# lot of actions, so we cap the in-memory trajectory at 200 entries.
_session: Any = None


def _get_session() -> Any:
    """Get session."""
    global _session, _engine_requester
    if _session is None:
        from encre.computer.computer_use import EncreComputerUseSession

        # Try to share the underlying EncreBrowserSession with the
        # browser tool to avoid creating two separate Chromium processes.
        browser_session = None
        try:
            from encre.tools.builtin.browser import _get_session as _browser_get_session
            browser_session = _browser_get_session()
        except Exception:
            pass

        _session = EncreComputerUseSession(
            engine_requester=_engine_requester,
            browser_session=browser_session,
        )
    elif _engine_requester is not None and getattr(
        _session, "_engine_requester", None,
    ) is None:
        # Session pre-dated the requester registration; propagate now.
        _session.set_engine_requester(_engine_requester)
    return _session


# Module-level engine-requester storage.  The agent's
# ``_install_requester_on_computer_use`` calls
# ``set_engine_requester(req)`` once at startup; from then on
# any new / existing singleton session picks it up via
# ``_get_session``.  This is necessary because the tool wrapper
# (``EncreComputerUseTool``) is a thin object built by
# ``build_tool`` and cannot carry the requester as an attribute.
_engine_requester: Any | None = None


def set_engine_requester(requester: Any) -> None:
    """Install an engine-install requester on the lazily-created
    computer-use session.

    Called by :class:`EncreAgent` during ``__init__`` so any
    subsequent browser action that needs the chromium binary
    will route the install prompt through the requester instead
    of raising an error to the LLM.

    Does NOT eagerly create the session — the requester is stored
    and propagated on first actual use via :func:`_get_session`.
    """
    global _engine_requester
    _engine_requester = requester
    if _session is not None and hasattr(_session, "set_engine_requester"):
        _session.set_engine_requester(requester)


def _action_enum() -> list[str]:
    """Action enum."""
    from encre.computer.computer_use import VALID_ACTIONS
    return sorted(VALID_ACTIONS)


async def _computer_use_execute(**kwargs: Any) -> str:
    """Dispatch one computer-use action and return a JSON envelope.

    The envelope is always a JSON object with the same shape as
    :meth:`EncreComputerUseSession.dispatch` returns.  Special ``action``
    values:

    * ``"trajectory"`` -- return the recorded trajectory without
      dispatching anything.
    * ``"reset"`` -- close the session and forget the trajectory.
    * ``"list_actions"`` -- return the canonical action enum so the
      agent can re-discover what's available.
    """
    action = str(kwargs.get("action") or "").strip().lower()
    session = _get_session()

    if action == "list_actions":
        return json.dumps({"actions": _action_enum()}, ensure_ascii=False)

    if action == "trajectory":
        return json.dumps({
            "trajectory": session.trajectory_dict(),
            "recent_summary": session.trajectory.recent_summary(20),
        }, ensure_ascii=False)

    if action == "reset":
        try:
            await session.close()
        finally:
            global _session
            _session = None
        return json.dumps({"success": True, "reset": True}, ensure_ascii=False)

    if action == "cancel":
        session.cancel()
        return json.dumps({
            "success": True,
            "cancelled": True,
            "is_cancelled": session.is_cancelled,
        }, ensure_ascii=False)

    if action == "recent_screenshots":
        try:
            n = int(kwargs.get("n") or 5)
        except (TypeError, ValueError):
            n = 5
        n = max(0, min(n, session.max_steps))
        return json.dumps({
            "success": True,
            "steps": session.trajectory.recent_with_screenshots(n),
            "total_screenshot_bytes":
                session.trajectory.total_screenshot_bytes(),
        }, ensure_ascii=False)

    if action == "compress_trajectory":
        try:
            keep = int(kwargs.get("keep_screenshots") or 5)
        except (TypeError, ValueError):
            keep = 5
        keep = max(0, min(keep, session.max_steps))
        cleared = session.trajectory.compress(
            strategy="window", keep_screenshots=keep,
        )
        return json.dumps({
            "success": True,
            "cleared": cleared,
            "total_screenshot_bytes":
                session.trajectory.total_screenshot_bytes(),
        }, ensure_ascii=False)

    if action == "save_state":
        state = await session.save_state()
        # Strip the desktop screenshot from JSON output -- it's binary.
        if "desktop_screenshot_png" in state:
            png = state.pop("desktop_screenshot_png")
            if isinstance(png, bytes | bytearray):
                state["desktop_screenshot_bytes"] = len(png)
        return json.dumps({
            "success": True,
            "state": state,
        }, ensure_ascii=False)

    if action == "load_state":
        state = kwargs.get("state")
        if not isinstance(state, dict):
            return json.dumps({
                "success": False,
                "error": "load_state requires a 'state' object",
            }, ensure_ascii=False)
        try:
            await session.load_state(state)
        except Exception as exc:
            return json.dumps({
                "success": False,
                "error": f"load_state failed: {exc}",
            }, ensure_ascii=False)
        return json.dumps({
            "success": True,
            "loaded": True,
        }, ensure_ascii=False)

    if action == "register_macro":
        name = kwargs.get("name") or kwargs.get("macro_name")
        actions = kwargs.get("actions")
        if not isinstance(name, str) or not name:
            return json.dumps({
                "success": False,
                "error": "register_macro requires 'name'",
            }, ensure_ascii=False)
        if not isinstance(actions, list):
            return json.dumps({
                "success": False,
                "error": "register_macro requires 'actions' as a list",
            }, ensure_ascii=False)
        try:
            session.register_macro(name, actions)
        except Exception as exc:
            return json.dumps({
                "success": False,
                "error": str(exc),
            }, ensure_ascii=False)
        return json.dumps({
            "success": True,
            "registered": name,
            "step_count": len(actions),
        }, ensure_ascii=False)

    if action == "execute_macro":
        name = kwargs.get("name") or kwargs.get("macro_name")
        if not isinstance(name, str) or not name:
            return json.dumps({
                "success": False,
                "error": "execute_macro requires 'name'",
            }, ensure_ascii=False)
        try:
            results = await session.execute_macro(
                name, stop_on_failure=bool(kwargs.get("stop_on_failure", True)),
            )
        except KeyError as exc:
            return json.dumps({
                "success": False,
                "error": str(exc),
            }, ensure_ascii=False)
        return json.dumps({
            "success": True,
            "macro": name,
            "results": results,
        }, ensure_ascii=False)

    if action == "replay_trajectory":
        steps = kwargs.get("steps")
        if not isinstance(steps, list):
            return json.dumps({
                "success": False,
                "error": "replay_trajectory requires 'steps' as a list",
            }, ensure_ascii=False)
        try:
            start = int(kwargs.get("start") or 0)
        except (TypeError, ValueError):
            start = 0
        results = await session.replay(
            steps, start=start,
            stop_on_failure=bool(kwargs.get("stop_on_failure", True)),
        )
        return json.dumps({
            "success": True,
            "results": results,
        }, ensure_ascii=False)

    if action == "metrics":
        return json.dumps({
            "success": True,
            "metrics": session.metrics(),
        }, ensure_ascii=False)

    if action == "set_no_op_as_failure":
        # Toggle whether expect_change == False turns into a
        # ``NO_CHANGE`` failure (True) or a success-with-warning (False).
        enabled = bool(kwargs.get("enabled", True))
        session.no_op_as_failure = enabled
        return json.dumps({
            "success": True,
            "no_op_as_failure": session.no_op_as_failure,
        }, ensure_ascii=False)

    # ---- macro library meta-actions ----
    # These expose the persistent MacroLibrary so an agent can
    # register / search / list / save shared action sequences
    # across sessions.

    if action == "library_register":
        from encre.computer.computer_use import MacroLibrary
        name = kwargs.get("name")
        actions = kwargs.get("actions")
        if not isinstance(name, str) or not name:
            return json.dumps({
                "success": False,
                "error": "library_register requires 'name'",
            }, ensure_ascii=False)
        if not isinstance(actions, list):
            return json.dumps({
                "success": False,
                "error": "library_register requires 'actions' as a list",
            }, ensure_ascii=False)
        try:
            lib = session.ensure_macro_library()
            entry = lib.register(
                name, actions,
                category=str(kwargs.get("category", "general")),
                description=str(kwargs.get("description", "")),
                author=str(kwargs.get("author", "")),
                tags=list(kwargs.get("tags") or []),
                overwrite=bool(kwargs.get("overwrite", False)),
            )
            lib.save()
        except (KeyError, TypeError, ValueError) as exc:
            return json.dumps({
                "success": False,
                "error": str(exc),
            }, ensure_ascii=False)
        return json.dumps({
            "success": True,
            "entry": entry.to_dict(),
        }, ensure_ascii=False)

    if action == "library_search":
        from encre.computer.computer_use import MacroLibrary
        try:
            lib = session.ensure_macro_library()
        except Exception:
            lib = MacroLibrary()
        results = lib.search(
            query=kwargs.get("query"),
            category=kwargs.get("category"),
            tag=kwargs.get("tag"),
        )
        return json.dumps({
            "success": True,
            "results": [e.to_dict() for e in results],
            "total": len(results),
        }, ensure_ascii=False)

    if action == "library_list":
        from encre.computer.computer_use import MacroLibrary
        try:
            lib = session.ensure_macro_library()
        except Exception:
            lib = MacroLibrary()
        return json.dumps({
            "success": True,
            "entries": [e.to_dict() for e in lib.list()],
            "total": len(lib),
        }, ensure_ascii=False)

    if action == "library_save":
        from encre.computer.computer_use import MacroLibrary
        try:
            lib = session.ensure_macro_library()
            count = lib.save()
        except Exception as exc:
            return json.dumps({
                "success": False,
                "error": str(exc),
            }, ensure_ascii=False)
        return json.dumps({
            "success": True,
            "saved": count,
            "path": lib.path,
        }, ensure_ascii=False)

    if action == "library_remove":
        from encre.computer.computer_use import MacroLibrary
        name = kwargs.get("name")
        if not isinstance(name, str) or not name:
            return json.dumps({
                "success": False,
                "error": "library_remove requires 'name'",
            }, ensure_ascii=False)
        try:
            lib = session.ensure_macro_library()
            removed = lib.remove(name)
            if removed:
                lib.save()
        except Exception as exc:
            return json.dumps({
                "success": False,
                "error": str(exc),
            }, ensure_ascii=False)
        return json.dumps({
            "success": True,
            "removed": removed,
        }, ensure_ascii=False)

    # ---- cross-session bundle ----
    if action == "export_bundle":
        include_state = bool(kwargs.get("include_state", True))
        source = str(kwargs.get("source", ""))
        try:
            bundle = await session.export_bundle(
                include_state=include_state, source=source,
            )
        except Exception as exc:
            return json.dumps({
                "success": False,
                "error": f"export_bundle failed: {exc}",
            }, ensure_ascii=False)
        return json.dumps({
            "success": True,
            "bundle": bundle,
        }, ensure_ascii=False)

    if action == "replay_bundle":
        bundle = kwargs.get("bundle")
        if not isinstance(bundle, dict):
            return json.dumps({
                "success": False,
                "error": "replay_bundle requires 'bundle' as an object",
            }, ensure_ascii=False)
        try:
            start = int(kwargs.get("start") or 0)
        except (TypeError, ValueError):
            start = 0
        variables = kwargs.get("variables")
        results = await session.replay_bundle(
            bundle, start=start,
            stop_on_failure=bool(kwargs.get("stop_on_failure", True)),
            variables=variables if isinstance(variables, dict) else None,
            restore_state=bool(kwargs.get("restore_state", True)),
        )
        return json.dumps({
            "success": True,
            "results": results,
        }, ensure_ascii=False)

    # All other actions go through the dispatcher.
    raw_result = await session.dispatch(kwargs)
    # Return a *model-friendly* envelope: strip base64 screenshots,
    # truncate bulky text fields, and attach a one-line ``summary`` so
    # the LLM has something it can actually parse.  Callers can opt
    # back into the full payload with ``include_screenshot_b64=True``
    # and ``include_full_result=True`` (debugging / VLM only).
    return _summarize_for_model(
        raw_result, action, kwargs,
    )


# ---------------------------------------------------------------------------
# Model-facing summary helper
# ---------------------------------------------------------------------------

#: Hard ceiling for embedded text fields (``get_all_text``, ``get_text``,
#: ``get_html``, ``evaluate_js`` string results, etc.).  Anything longer
#: is truncated with a trailing ``"...(truncated, N bytes omitted)"``
#: marker so the model can ask for the full result on demand.
MAX_TEXT_CHARS = 8_000

#: Keys whose string values are treated as "text" payloads by the
#: summariser.  When we see one of these in ``result`` (top level or
#: nested) we truncate to :data:`MAX_TEXT_CHARS`.
_TEXT_RESULT_KEYS = frozenset({
    "text", "html", "innerText", "innerHTML",
    "inner_html", "value", "output", "data",
    "markdown", "rendered", "extracted",
})


def _truncate_string(value: Any, limit: int = MAX_TEXT_CHARS) -> tuple[Any, bool]:
    """Return ``(value, was_truncated)`` with strings bounded to ``limit``."""
    if isinstance(value, str) and len(value) > limit:
        return (
            value[:limit] + f"\n...(truncated, {len(value) - limit} bytes omitted)",
            True,
        )
    return value, False


def _scrub_payload(value: Any, *, limit: int) -> tuple[Any, dict[str, int]]:
    """Walk a JSON-like value, truncating long strings and counting cuts.

    Returns the cleaned value plus a small stats dict the summariser
    uses to build a human-readable note.  Truncation only happens for
    string values that look like text payloads (i.e. are *not* base64
    screenshots -- we leave those to the caller to decide).
    """
    stats = {"strings_truncated": 0, "bytes_saved": 0}
    if isinstance(value, str):
        if len(value) > limit and _looks_like_text(value):
            saved = len(value) - limit
            stats["strings_truncated"] += 1
            stats["bytes_saved"] += saved
            return (
                value[:limit] + f"\n...(truncated, {saved} bytes omitted)",
                stats,
            )
        return value, stats
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and k in _TEXT_RESULT_KEYS:
                new_v, sub = _scrub_payload(v, limit=limit)
                stats["strings_truncated"] += sub["strings_truncated"]
                stats["bytes_saved"] += sub["bytes_saved"]
                cleaned[k] = new_v
            else:
                new_v, sub = _scrub_payload(v, limit=limit)
                stats["strings_truncated"] += sub["strings_truncated"]
                stats["bytes_saved"] += sub["bytes_saved"]
                cleaned[k] = new_v
        return cleaned, stats
    if isinstance(value, list):
        cleaned_list: list[Any] = []
        for item in value:
            new_item, sub = _scrub_payload(item, limit=limit)
            stats["strings_truncated"] += sub["strings_truncated"]
            stats["bytes_saved"] += sub["bytes_saved"]
            cleaned_list.append(new_item)
        return cleaned_list, stats
    return value, stats


def _looks_like_text(value: str) -> bool:
    """Heuristic: is this string a text payload (not a base64 blob)?

    Base64 screenshots are pure ASCII alphanumerics + ``+/=`` and have
    a very low whitespace / non-alnum ratio; natural text has a lot
    more variation.  We use a simple character-class ratio instead of
    a regex so this stays fast on large strings.
    """
    if not value:
        return False
    sample = value[:512]
    alnum = sum(c.isalnum() for c in sample)
    slash_eq = sum(c in "+/=" for c in sample)
    if alnum + slash_eq == 0:
        return False
    # base64 → ≥98% alnum+slash+eq, no whitespace, no newlines
    if "\n" in sample or "  " in sample:
        return True
    text_like = alnum + slash_eq
    return not (text_like / max(1, len(sample)) > 0.98 and slash_eq < 2)


def _make_summary(result: dict[str, Any], action: str) -> str:
    """Build a one-line human-readable summary of an action result.

    The summary is what the LLM actually reads; we keep it short
    (<= 200 chars) and structured (``verb: target -> outcome``) so
    it's easy to scan when the model is building a multi-step plan.
    """
    if not isinstance(result, dict):
        return f"{action}: done"
    if not result.get("success", True):
        kind = result.get("failure_kind") or result.get("error") or "failed"
        return f"{action}: failed ({kind})"
    page_changed = result.get("page_changed")
    if page_changed is True:
        return f"{action}: ok, page changed"
    if page_changed is False:
        return f"{action}: ok but page did NOT change (possible dead element)"
    return f"{action}: ok"


def _summarize_for_model(
    result: Any, action: str, kwargs: dict[str, Any],
) -> str:
    """Convert a raw dispatch result into a model-friendly JSON envelope.

    Goals
    -----
    1. Never hand the LLM a multi-kilobyte base64 string.  Screenshots
       are replaced by ``screenshot_captured`` + ``screenshot_length``.
    2. Never hand the LLM 200 KB of page text.  String fields under
       :data:`_TEXT_RESULT_KEYS` are truncated to :data:`MAX_TEXT_CHARS`
       bytes.
    3. Always include a one-line ``summary`` so the model can read the
       outcome without parsing the full envelope.
    4. Honour the caller's opt-ins (``include_screenshot_b64``,
       ``include_full_result``, ``max_text_chars``) for debugging.
    """
    # Default: do NOT include any base64 screenshot in the model envelope.
    include_b64 = bool(kwargs.get("include_screenshot_b64", False))
    include_full = bool(kwargs.get("include_full_result", False))
    max_chars = max(0, int(kwargs["max_text_chars"])) if isinstance(kwargs.get("max_text_chars"), int) else MAX_TEXT_CHARS

    if not isinstance(result, dict):
        # Non-dict result (shouldn't happen, but be defensive).
        envelope: dict[str, Any] = {
            "success": True,
            "action": action,
            "result": result,
            "summary": _make_summary({"success": True}, action),
        }
        return json.dumps(envelope, ensure_ascii=False)

    envelope = dict(result)  # shallow copy so we don't mutate caller's view

    # 1. Strip / summarise the screenshot payload.
    b64 = envelope.pop("screenshot_b64", None)
    if b64:
        envelope["screenshot_captured"] = True
        envelope["screenshot_length"] = len(b64)
        if include_b64:
            envelope["screenshot_b64"] = b64
        else:
            envelope["screenshot_b64"] = (
                f"<omitted: {len(b64)} bytes of base64 PNG; "
                "the screenshot is held in the session trajectory and "
                "fed to the VLM, not the LLM>"
            )
    else:
        envelope.setdefault("screenshot_captured", False)

    # 1b. Strip / summarise the active-window PrintWindow payload.
    aw_b64 = envelope.pop("active_window_b64", None)
    if aw_b64:
        envelope["active_window_captured"] = True
        envelope["active_window_png_bytes"] = len(aw_b64)
        if not include_b64:
            envelope["active_window_b64"] = (
                f"<omitted: {len(aw_b64)} bytes of base64 PNG; "
                "the active-window screenshot is held in the session "
                "trajectory and fed to the VLM, not the LLM>"
            )

    # 2. Truncate bulky text in the ``result`` sub-payload.
    if "result" in envelope and not include_full:
        cleaned, stats = _scrub_payload(envelope["result"], limit=max_chars)
        envelope["result"] = cleaned
        if stats["strings_truncated"]:
            envelope.setdefault("notes", []).append(
                f"truncated {stats['strings_truncated']} string(s), "
                f"saved {stats['bytes_saved']} bytes; ask for the full "
                "result by calling computer_use with "
                "include_full_result=true"
            )

    # 3. Build / refresh the summary line.
    envelope["summary"] = _make_summary(envelope, action)

    return json.dumps(envelope, ensure_ascii=False)



# Lazy list so the schema is correct at tool-construction time without
# having to import computer_use at module load.
def _build_schema() -> dict[str, Any]:
    """Build schema."""
    return {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": (
                    "Required. Action to dispatch. Send 'list_actions' to "
                    "discover the canonical enum at runtime. Interaction "
                    "actions (click, type, screenshot, ...) target the "
                    "browser or desktop via `target`; meta-actions "
                    "(trajectory, reset, metrics, ...) operate on the "
                    "session itself."
                ),
            },
            "target": {
                "type": "string",
                "enum": ["browser", "desktop", "auto"],
                "description": (
                    "Backend to route cross-target actions to. 'auto' "
                    "(default) lets the dispatcher pick based on the "
                    "action; browser-only / desktop-only actions ignore "
                    "this field. Optional."
                ),
            },
            "x": {
                "type": "integer",
                "description": (
                    "X coordinate. For desktop this is physical pixels "
                    "by default (see coord_space); for browser it is "
                    "viewport CSS pixels. Required for click, "
                    "double_click, right_click, move_mouse, drag start, "
                    "scroll anchor."
                ),
            },
            "y": {
                "type": "integer",
                "description": (
                    "Y coordinate, same coordinate space as `x`. "
                    "Required alongside `x` for click / move / drag "
                    "start / scroll anchor."
                ),
            },
            "x2": {
                "type": "integer",
                "description": (
                    "End X coordinate for drag (drop target) or line "
                    "draw. Required for `drag` alongside `y2`."
                ),
            },
            "y2": {
                "type": "integer",
                "description": (
                    "End Y coordinate for drag (drop target) or line "
                    "draw. Required for `drag` alongside `x2`."
                ),
            },
            "text": {
                "type": "string",
                "description": (
                    "String payload. For `type` it is the literal text "
                    "to type; for `navigate` it is the URL; for "
                    "clipboard_set it is the clipboard content."
                ),
            },
            "query": {
                "type": "string",
                "description": (
                    "Text to find for click_text / find_text / "
                    "find_element_by_name. Also used as the free-text "
                    "substring match on name, description, and tags for "
                    "library_search (case-insensitive)."
                ),
            },
            "tag": {
                "type": "string",
                "description": (
                    "library_search: filter to macros that include this "
                    "tag. Optional."
                ),
            },
            "key": {
                "type": "string",
                "description": (
                    "Single key name for press_key (e.g. 'Enter', 'Tab', "
                    "'Escape', 'F1'). Use `keys` for combinations."
                ),
            },
            "keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Ordered list of key names for hotkey, pressed "
                    "sequentially then released in reverse (e.g. "
                    "[\"Control\", \"c\"] for copy)."
                ),
            },
            "scroll_amount": {
                "type": "integer",
                "description": (
                    "Scroll direction and magnitude. Positive scrolls "
                    "down, negative scrolls up. Magnitude unit is "
                    "backend-defined (typically wheel clicks)."
                ),
            },
            "selector": {
                "type": "string",
                "description": (
                    "CSS or ARIA selector for browser-only actions "
                    "(fill_form field key, wait_for_selector, "
                    "click_by_role target, etc.)."
                ),
            },
            "fields": {
                "type": "object",
                "description": (
                    "fill_form: map of {selector: value} entries to "
                    "populate in one batch. Each value is typed into the "
                    "matching input."
                ),
            },
            "tab_index": {
                "type": "integer",
                "description": (
                    "0-based tab index for switch_tab / close_tab. "
                    "Out-of-range values return an error."
                ),
            },
            "option_value": {
                "type": "string",
                "description": (
                    "select_option: value to match against the option. "
                    "Interpreted according to `option_by` (default "
                    "matches the option's `value` attribute)."
                ),
            },
            "option_by": {
                "type": "string",
                "enum": ["value", "label", "index"],
                "description": (
                    "select_option: how option_value is matched. "
                    "'value' (default) matches the value attribute, "
                    "'label' matches visible text, 'index' treats "
                    "option_value as a 0-based position."
                ),
            },
            "attr_name": {
                "type": "string",
                "description": (
                    "get_attribute / get_property: name of the DOM "
                    "attribute or element property to read."
                ),
            },
            "js_code": {
                "type": "string",
                "description": (
                    "execute_js: JavaScript source to evaluate in the "
                    "active page context. Return value is serialised "
                    "back to the caller."
                ),
            },
            "fuzzy": {
                "type": "boolean",
                "description": (
                    "click_text / find_text: when True, treat `query` as "
                    "ordered whitespace-separated tokens that must all "
                    "appear in the matched text. Default False."
                ),
            },
            "exact": {
                "type": "boolean",
                "description": (
                    "click_text / find_text / click_by_role: when True, "
                    "require the match to equal `query` exactly rather "
                    "than as a substring. Default False."
                ),
            },
            "occurrence": {
                "type": "integer",
                "description": (
                    "click_text / find_text: 1-based index of the match "
                    "to use when the same text appears multiple times. "
                    "Default 1."
                ),
            },
            "ms": {
                "type": "integer",
                "description": (
                    "wait: milliseconds to sleep before returning. "
                    "Use short values for animation settle, longer for "
                    "network waits."
                ),
            },
            "button": {
                "type": "string",
                "enum": ["left", "middle", "right"],
                "description": (
                    "Mouse button for click / click_text. Default "
                    "'left'."
                ),
            },
            "coord_space": {
                "type": "string",
                "enum": ["auto", "physical", "logical"],
                "description": (
                    "Desktop coordinate system. 'physical' = raw "
                    "screenshot pixels, 'logical' = OS-scaled pixels, "
                    "'auto' (default) infers from magnitude. Ignored "
                    "for browser actions."
                ),
            },
            "accept": {
                "type": "boolean",
                "description": (
                    "set_dialog_handler: True to auto-accept alert / "
                    "confirm dialogs, False to dismiss them."
                ),
            },
            "prompt_text": {
                "type": "string",
                "description": (
                    "set_dialog_handler: text to inject into a prompt() "
                    "dialog before accepting. Optional."
                ),
            },
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "set_file_chooser_handler / file_drop: list of "
                    "absolute file paths to upload or drop."
                ),
            },
            "timeout": {
                "type": "integer",
                "description": (
                    "wait_for_selector timeout in milliseconds. The "
                    "action fails if the selector does not appear "
                    "within this window."
                ),
            },
            "dry_run": {
                "type": "boolean",
                "description": (
                    "When True, dispatch returns a preview report "
                    "(selector_present / text_match_count / would_send) "
                    "without mutating the UI. Use to sanity-check a "
                    "click target before committing. Default False."
                ),
            },
            "keep_screenshots": {
                "type": "integer",
                "description": (
                    "compress_trajectory: number of most recent steps "
                    "to keep screenshots for; older screenshots are "
                    "dropped (text action logs are retained). Defaults "
                    "to 5."
                ),
            },
            "n": {
                "type": "integer",
                "description": (
                    "recent_screenshots: how many recent steps to "
                    "return with their base64 screenshots for VLM "
                    "context. Defaults to 5. Clamped to max_steps."
                ),
            },
            "expect_change": {
                "type": "boolean",
                "description": (
                    "When True, the dispatcher verifies the DOM / "
                    "screen state hash changed after the action and "
                    "returns page_changed: bool plus a warning if not. "
                    "Use to catch no-op clicks on dead elements. "
                    "Default False."
                ),
            },
            "timeout_ms": {
                "type": "integer",
                "description": (
                    "Per-action timeout in milliseconds. Overrides the "
                    "session default. Omit / null to use the session "
                    "default."
                ),
            },
            "state": {
                "type": "object",
                "description": (
                    "load_state: dict returned from a prior save_state "
                    "call. Restores cookies, URL, and localStorage."
                ),
            },
            "name": {
                "type": "string",
                "description": (
                    "register_macro / execute_macro / library_register / "
                    "library_remove: name of the macro to register, "
                    "execute, or remove."
                ),
            },
            "actions": {
                "type": "array",
                "items": {"type": "object"},
                "description": (
                    "register_macro / library_register: list of action "
                    "dicts (each with at least an 'action' key) to "
                    "register as a named sequence."
                ),
            },
            "stop_on_failure": {
                "type": "boolean",
                "description": (
                    "execute_macro / replay_trajectory / replay_bundle: "
                    "if True (default), stop at the first failed step "
                    "and skip the remainder; if False, continue "
                    "dispatching remaining steps."
                ),
            },
            "steps": {
                "type": "array",
                "items": {"type": "object"},
                "description": (
                    "replay_trajectory: list of step dicts (each with "
                    "an 'action' field) to re-execute in order."
                ),
            },
            "start": {
                "type": "integer",
                "description": (
                    "replay_trajectory / replay_bundle: 0-based index "
                    "to start from; earlier steps are skipped. Defaults "
                    "to 0."
                ),
            },
            "category": {
                "type": "string",
                "description": (
                    "library_register / library_search: category to tag "
                    "the macro with (e.g. 'login', 'search') or to "
                    "filter by. Defaults to 'general'."
                ),
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "library_register: list of free-form tags for "
                    "later search."
                ),
            },
            "overwrite": {
                "type": "boolean",
                "description": (
                    "library_register: when True, replace an existing "
                    "macro with the same name (still bumps version). "
                    "Defaults to False."
                ),
            },
            "bundle": {
                "type": "object",
                "description": (
                    "replay_bundle: bundle dict produced by a prior "
                    "export_bundle call. Contains recorded actions and "
                    "optional state checkpoint."
                ),
            },
            "variables": {
                "type": "object",
                "description": (
                    "replay_bundle: mapping used to substitute "
                    "'{{key}}' placeholders inside the recorded action "
                    "payloads (e.g. {'username': 'alice'}). Missing "
                    "keys are left in place rather than raising."
                ),
            },
            "restore_state": {
                "type": "boolean",
                "description": (
                    "replay_bundle: when True (default), load the "
                    "bundle's saved browser state (cookies, URL, "
                    "localStorage) before the first replay step."
                ),
            },
            "include_state": {
                "type": "boolean",
                "description": (
                    "export_bundle: when True (default), include the "
                    "browser state checkpoint in the bundle. Set False "
                    "to keep the bundle tiny (replay then uses a fresh "
                    "session)."
                ),
            },
            "include_screenshot_b64": {
                "type": "boolean",
                "description": (
                    "Computer-use envelope: by default the base64 PNG "
                    "screenshot is replaced with a one-line placeholder "
                    "so the LLM context isn't flooded. Set True to opt "
                    "back into the full base64 (debugging / VLM only). "
                    "Default False."
                ),
            },
            "include_full_result": {
                "type": "boolean",
                "description": (
                    "Computer-use envelope: by default bulky string "
                    "fields under result (text, html, value, output, "
                    "data, ...) are truncated to max_text_chars. Set "
                    "True to return the raw result untouched. Default "
                    "False."
                ),
            },
            "max_text_chars": {
                "type": "integer",
                "description": (
                    "Computer-use envelope: override the per-string "
                    "truncation cap (default 8000). Use 0 to disable "
                    "truncation entirely (equivalent to "
                    "include_full_result=true)."
                ),
            },
            "source": {
                "type": "string",
                "description": (
                    "export_bundle: free-form label for the producer "
                    "(e.g. an agent identifier). Informational only."
                ),
            },
            "enabled": {
                "type": "boolean",
                "description": (
                    "set_no_op_as_failure: when True (default), an "
                    "action that returns success but produces an "
                    "unchanged DOM / screen hash is converted to a "
                    "NO_CHANGE failure so the retry policy can fire. "
                    "Set False to revert to success-with-warning."
                ),
            },
            "author": {
                "type": "string",
                "description": (
                    "library_register: free-form author or origin tag. "
                    "Informational."
                ),
            },
            "description": {
                "type": "string",
                "description": (
                    "library_register: human-readable summary of what "
                    "the macro does. Surfaced to the VLM so it knows "
                    "when to invoke the macro by name."
                ),
            },
        },
        "required": ["action"],
    }


EncreComputerUseTool = build_tool(
    name="computer_use",
    description=(
        "WHAT: Unified computer-use tool exposing one curated action "
        "schema that routes each action to the browser or desktop backend "
        "behind the scenes, with a trajectory buffer and step budget. "
        "WHEN: Use for visual / interactive automation that benefits from "
        "a single model-friendly API across both browser and desktop; "
        "ideal for multi-step loops that benefit from trajectory memory, "
        "macros, and page-change verification. "
        "WHEN NOT: Call `browser` or `desktop` directly when you know "
        "exactly which backend you need; use `vlm_computer_use` when the "
        "model should delegate pixel-level decisions to a vision model. "
        "TIPS: Set `dry_run: true` to preview an action without mutating "
        "the UI; set `expect_change: true` to flag dead-element clicks; "
        "call `compress_trajectory` periodically to bound context size; "
        "call `list_actions` to re-discover the canonical action enum. "
        "PITFALLS: The session enforces a step budget (default 200) -- "
        "beyond it the tool refuses to dispatch and returns an explicit "
        "error, so call `reset` once a task is complete. Base64 "
        "screenshots are stripped from the LLM envelope by default to "
        "avoid flooding context -- opt back in with "
        "`include_screenshot_b64: true` (debugging / VLM only). "
        "Interaction actions: click, double_click, right_click, "
        "triple_click, type, press_key / key, hotkey, scroll, drag, "
        "move_mouse, hover, screenshot, click_text, find_text, wait, "
        "navigate, fill_form, select_option, get_attribute, get_property, "
        "get_html, get_text, get_all_text, execute_js, list_tabs, "
        "switch_tab, new_tab, close_tab, set_dialog_handler, "
        "set_file_chooser_handler, a11y_snapshot, click_by_role, "
        "get_by_text_count, get_page_structure, clipboard_get, "
        "clipboard_set, file_drop, get_screen_size, get_cursor_position, "
        "accessibility_tree, find_element_by_name, get_elements, "
        "take_screenshot_png, locate_on_screen, done. "
        "Meta-actions: 'trajectory' (return past actions), 'reset' "
        "(forget history), 'list_actions' (return the action enum), "
        "'cancel' (abort further dispatches), 'recent_screenshots' "
        "(return the last N steps with their base64 screenshots for VLM "
        "context), 'compress_trajectory' (drop screenshots older than "
        "keep_screenshots to free context), 'save_state' / 'load_state' "
        "(browser cookie/storage checkpoint), 'register_macro' / "
        "'execute_macro' (in-session named action sequences), "
        "'replay_trajectory' (re-execute a recorded sequence), 'metrics' "
        "(success rate, latency, failure breakdown, page-change "
        "verification, no-op count), 'set_no_op_as_failure' (toggle the "
        "expect_change no-op to NO_CHANGE failure conversion), "
        "'library_register' / 'library_search' / 'library_list' / "
        "'library_save' / 'library_remove' (persistent macro library on "
        "disk, versioned and searchable by category / tag / free-text), "
        "'export_bundle' / 'replay_bundle' (cross-session export with "
        "optional state restore and variable substitution via {{key}} "
        "placeholders). Browser-only actions (navigate, fill_form, ...) "
        "auto-route to the browser backend; desktop-only actions "
        "(triple_click, clipboard_*, ...) route to the desktop. "
        "Cross-target actions (click, type, screenshot, ...) honour the "
        "`target` field -- default 'browser'."
    ),
    input_schema=_build_schema(),
    execute=_computer_use_execute,
    intents=["coding", "system"],
    category="system",
    semantic_type="exec",
    is_destructive=lambda args: args.get("action", "") in ("click", "type", "press_key", "clipboard_set", "file_drop"),
)
