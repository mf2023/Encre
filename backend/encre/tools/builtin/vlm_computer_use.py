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

"""
``vlm_computer_use`` tool -- vision-guided desktop automation.

Wires :class:`encre.computer.computer_use.EncreComputerUseSession`
into the tool system so the agent can delegate a high-level goal
(e.g. "open Chrome and log in to gmail") to a VLM that handles the
pixel-level decisions (screenshot -> plan -> click/type -> verify -> repeat).

The dispatch and trajectory are owned by the unified computer-use
session; this tool is just the model-facing entry point that owns the
VLM backend lifecycle and a few prompt-engineering concerns (system
prompt, history injection, action validation).
"""

import asyncio
import json
import logging
import os
import time
from typing import Any

from encre.tools.base import build_tool

logger = logging.getLogger("encre.tools.vlm_computer_use")

#: Default system prompt used when no task template is specified.
#: Mirrors the generic VLM prompt in :mod:`encre.computer.vlm` so the
#: behaviour matches whether you go through the session or the tool.
_DEFAULT_SYSTEM_PROMPT = (
    "You are a vision-guided computer-use agent.  Look at the screenshot "
    "and the user's goal, then respond with **exactly one** JSON object "
    "(optionally inside a ```json``` fence) describing the next action. "
    "Schema:\n"
    "{\n"
    '  "action": "click" | "double_click" | "right_click" | "type" | '
    '"press" | "key" | "hotkey" | "scroll" | "drag" | "move" | "hover" | '
    '"wait" | "screenshot" | "triple_click" | "done",\n'
    '  "x": <int pixel coordinate>,\n'
    '  "y": <int pixel coordinate>,\n'
    '  "x2": <int pixel coordinate, for drag>,\n'
    '  "y2": <int pixel coordinate, for drag>,\n'
    '  "text": "<for type action: the literal text to type>",\n'
    '  "key": "<for press / key: the key name, e.g. \\"Enter\\">",\n'
    '  "keys": ["<for hotkey: ordered list of key names, e.g. [\\"Control\\", \\"c\\"]>"],\n'
    '  "scroll_amount": <for scroll: positive=down, negative=up>,\n'
    '  "ms": <for wait: milliseconds to sleep>,\n'
    '  "reasoning": "<one sentence on why this action advances the goal>",\n'
    '  "confidence": <float 0-1>\n'
    "}\n"
    "Set action to \"done\" once the goal is achieved."
)

# ---------------------------------------------------------------------------
# VLM backend cache (backends are stateless; session is per-call)
# ---------------------------------------------------------------------------

_vlm_backend: Any = None


def _resolve_vlm_backend() -> Any:
    """Return a cached VLM backend, resolving it from environment variables
    on first call.

    Priority: OpenAI-compatible (``OPENAI_API_KEY``) -> Anthropic
    (``ANTHROPIC_API_KEY``).  The model, base URL, and timeout are
    customisable via ``VLM_*`` environment variables.
    """
    global _vlm_backend
    if _vlm_backend is not None:
        return _vlm_backend

    from encre.computer.vlm import AnthropicVLM, OpenAICompatibleVLM

    errors: list[str] = []

    # ── OpenAI-compatible ──
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key:
        try:
            _vlm_backend = OpenAICompatibleVLM(
                api_key=api_key,
                base_url=os.environ.get("VLM_OPENAI_BASE_URL",
                                        os.environ.get("OPENAI_BASE_URL",
                                                       "https://api.openai.com/v1")),
                model=os.environ.get("VLM_MODEL", "gpt-4o-mini"),
                timeout=float(os.environ.get("VLM_TIMEOUT", "60")),
            )
            return _vlm_backend
        except Exception as exc:
            errors.append(f"OpenAI: {exc}")

    # ── Anthropic ──
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        try:
            _vlm_backend = AnthropicVLM(
                api_key=api_key,
                base_url=os.environ.get("VLM_ANTHROPIC_BASE_URL",
                                        os.environ.get("ANTHROPIC_BASE_URL",
                                                       "https://api.anthropic.com")),
                model=os.environ.get("VLM_MODEL", "claude-3-5-sonnet-20241022"),
                timeout=float(os.environ.get("VLM_TIMEOUT", "60")),
            )
            return _vlm_backend
        except Exception as exc:
            errors.append(f"Anthropic: {exc}")

    raise RuntimeError(
        "No VLM backend configured.  Set OPENAI_API_KEY or "
        "ANTHROPIC_API_KEY environment variable."
        + (f"  Errors: {'; '.join(errors)}" if errors else "")
    )


# ---------------------------------------------------------------------------
# VLM-driven session wrapper
# ---------------------------------------------------------------------------


def _resolve_prompt_bundle(template_name: str) -> dict[str, Any]:
    """Return the prompt bundle for the given template name.

    Falls back to the generic defaults when ``template_name`` is empty
    or unknown -- callers can use whatever the model returns without
    having to handle the error themselves.
    """
    bundle: dict[str, Any] = {
        "system": _DEFAULT_SYSTEM_PROMPT,
        "step_preamble": "",
        "done_criteria": "",
        "action_hints": {},
        "template": "",
    }
    if not template_name:
        return bundle
    try:
        from encre.computer.vlm import get_task_template
        template = get_task_template(template_name)
    except (ImportError, KeyError) as exc:
        logger.warning(
            "[vlm_computer_use] template %r unavailable (%s); "
            "falling back to generic prompt",
            template_name, exc,
        )
        return bundle
    bundle["system"] = template.get("system", _DEFAULT_SYSTEM_PROMPT)
    bundle["step_preamble"] = template.get("step_preamble", "")
    bundle["done_criteria"] = template.get("done_criteria", "")
    bundle["action_hints"] = dict(template.get("action_hints") or {})
    bundle["template"] = template_name
    return bundle


def _decision_to_action_dict(d: Any) -> dict[str, Any]:
    """Convert a VLM decision to the unified computer-use schema."""
    act = str(getattr(d, "action", "") or "").strip().lower()
    payload: dict[str, Any] = {}
    if act in ("press", "key", "press_key"):
        payload = {"action": "press_key", "key": str(getattr(d, "key", "") or "Return")}
    elif act == "type":
        payload = {"action": "type", "text": str(getattr(d, "text", "") or "")}
    elif act == "hotkey":
        keys_attr = getattr(d, "keys", None) or []
        if isinstance(keys_attr, str):
            keys_attr = [k for k in keys_attr.split("+") if k]
        payload = {"action": "hotkey", "keys": [str(k) for k in keys_attr]}
    elif act == "scroll":
        payload = {
            "action": "scroll",
            "scroll_amount": int(getattr(d, "scroll_amount", 0) or 0),
        }
    elif act == "drag":
        payload = {
            "action": "drag",
            "x": int(getattr(d, "x", 0) or 0),
            "y": int(getattr(d, "y", 0) or 0),
            "x2": int(getattr(d, "x2", 0) or 0),
            "y2": int(getattr(d, "y2", 0) or 0),
        }
    elif act in ("move", "move_mouse", "hover"):
        payload = {
            "action": "move_mouse" if act != "hover" else "hover",
            "x": int(getattr(d, "x", 0) or 0),
            "y": int(getattr(d, "y", 0) or 0),
        }
    elif act in ("double_click", "right_click"):
        payload = {
            "action": act,
            "x": int(getattr(d, "x", 0) or 0),
            "y": int(getattr(d, "y", 0) or 0),
        }
    elif act == "triple_click":
        payload = {
            "action": "triple_click",
            "x": int(getattr(d, "x", 0) or 0),
            "y": int(getattr(d, "y", 0) or 0),
        }
    elif act == "wait":
        ms_attr = getattr(d, "ms", None)
        if ms_attr is None:
            # Older models used `text` to encode wait seconds.
            try:
                ms = int(float(getattr(d, "text", 0.5) or 0.5) * 1000)
            except (TypeError, ValueError):
                ms = 500
        else:
            try:
                ms = int(ms_attr)
            except (TypeError, ValueError):
                ms = 500
        payload = {"action": "wait", "ms": max(0, ms)}
    elif act == "screenshot":
        payload = {"action": "screenshot"}
    elif act == "done":
        payload = {"action": "done"}
    else:
        # Default to a click -- the most common action.
        payload = {
            "action": "click",
            "x": int(getattr(d, "x", 0) or 0),
            "y": int(getattr(d, "y", 0) or 0),
        }
    return payload


# ---------------------------------------------------------------------------
# Tool execute
# ---------------------------------------------------------------------------


async def _vlm_execute(**kwargs: Any) -> str:
    """Execute a VLM-driven computer-use session for the given ``goal``."""
    goal = kwargs.get("goal", "")
    if not goal:
        return json.dumps({"success": False, "error": "goal parameter is required"})

    max_steps = int(kwargs.get("max_steps", 20))
    template_name = str(kwargs.get("template_name", "") or "").strip()
    prompt_bundle = _resolve_prompt_bundle(template_name)
    system_prompt = str(prompt_bundle.get("system", _DEFAULT_SYSTEM_PROMPT))
    step_preamble = str(prompt_bundle.get("step_preamble", "") or "")
    done_criteria = str(prompt_bundle.get("done_criteria", "") or "")
    action_hints: dict[str, str] = dict(prompt_bundle.get("action_hints") or {})

    try:
        vlm = _resolve_vlm_backend()
    except RuntimeError as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)

    from encre.computer.computer_use import EncreComputerUseSession
    from encre.computer.vlm import parse_decision

    session = EncreComputerUseSession(
        default_target="desktop",
        max_steps=max_steps + 5,
        auto_screenshot=True,
        retry_on_failure=1,
        fallback_enabled=True,
    )

    decisions: list[Any] = []
    last_error = ""
    last_action_verb = ""
    for step in range(max_steps):
        # Take a fresh screenshot via the unified session.
        shot = await session.dispatch({"action": "screenshot"})
        if not shot.get("success") or not shot.get("result"):
            last_error = shot.get("error") or "screenshot failed"
            break
        png_b64 = shot["result"].get("screenshot_b64", "")
        if not png_b64:
            last_error = "screenshot returned no image"
            break
        try:
            png_bytes = __import__("base64").b64decode(png_b64)
        except Exception as exc:
            last_error = f"screenshot b64 decode failed: {exc}"
            break

        # Build the action-history block.  We feed both a textual
        # summary (so the model sees what was tried) and the last
        # 2 step screenshots (so the model can correlate the
        # current frame with what just happened).  This is the
        # same shape Codex/Manus use.
        recent_steps = session.trajectory.recent_with_screenshots(10)
        history_lines: list[str] = []
        attached_screenshots: list[str] = []
        for i, entry in enumerate(recent_steps[:-1]):  # exclude the
            # screenshot we just took -- it's already the model input
            history_lines.append(f"  {i + 1}. {entry['summary']}")
            if entry.get("screenshot_b64"):
                attached_screenshots.append(
                    f"[past-frame-{i + 1} attached below]"
                )
        history_text = (
            "\n".join(history_lines) if history_lines
            else "  (no prior actions)"
        )

        # Bound the in-memory trajectory before it grows unbounded.
        # 5 recent screenshots ~= 5 * 1 MB base64 = 5 MB; plenty of
        # room for hundreds of action descriptions in between.
        if session.trajectory.total_screenshot_bytes() > 8 * 1024 * 1024:
            session.trajectory.compress(strategy="window", keep_screenshots=3)

        # Per-action hint: surface the hint for the *most recent*
        # action so the VLM gets a soft "you did X, be aware of Y"
        # nudge on the next step.
        hint_text = ""
        if last_action_verb and last_action_verb in action_hints:
            hint_text = (
                f"\nHint for the previous action ({last_action_verb}): "
                f"{action_hints[last_action_verb]}"
            )
        preamble = step_preamble or (
            "The attached image is the current desktop.  Past frames "
            "from earlier in this session are attached below in "
            "chronological order.  Respond with a single JSON object "
            "describing the next action."
        )
        user_prompt = (
            f"Goal: {goal}\n"
            f"{preamble}\n"
            f"Step {step + 1}/{max_steps}.  "
            f"{done_criteria}\n"
            f"Recent actions (most recent last):\n{history_text}\n"
            f"Past frames: {'; '.join(attached_screenshots) or '(none)'}"
            f"{hint_text}"
        )
        try:
            raw = await asyncio.to_thread(vlm, png_bytes, system_prompt, user_prompt)
        except Exception as exc:
            last_error = f"VLM call failed: {exc}"
            break
        try:
            decision = parse_decision(raw)
        except ValueError as exc:
            last_error = str(exc)
            break
        decisions.append(decision)
        last_action_verb = decision.action

        if decision.action == "done":
            return json.dumps({
                "success": True,
                "steps_taken": step + 1,
                "decisions": [d.to_dict() for d in decisions],
                "last_screenshot_b64": png_b64,
                "final_message": decision.reasoning or "done",
                "trajectory": session.trajectory_dict(),
                "template": prompt_bundle.get("template", ""),
            }, ensure_ascii=False)

        # Translate decision -> unified action and dispatch.
        action_payload = _decision_to_action_dict(decision)
        try:
            dispatch_result = await session.dispatch(action_payload)
        except Exception as exc:
            logger.warning("[vlm_computer_use] dispatch raised: %s", exc, exc_info=True)
            last_error = f"dispatch failed: {exc}"
            continue
        if not dispatch_result.get("success"):
            last_error = (
                f"{dispatch_result.get('error') or 'dispatch failed'} "
                f"(retries={dispatch_result.get('retries_used', 0)}, "
                f"fallback={dispatch_result.get('fallback_used', False)})"
            )
        # Brief settle pause so animations / network calls have time.
        await asyncio.to_thread(time.sleep, 0.3)

    return json.dumps({
        "success": False,
        "steps_taken": len(decisions),
        "decisions": [d.to_dict() for d in decisions],
        "error": last_error or f"max_steps={max_steps} reached without a 'done' action",
        "trajectory": session.trajectory_dict(),
        "template": prompt_bundle.get("template", ""),
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------


EncreVLMComputerUseTool = build_tool(
    name="vlm_computer_use",
    description=(
        "Vision-Language-Model-driven computer use.  Give it a high-level "
        "goal (e.g. 'open Chrome, navigate to gmail, and log in') and it "
        "will take screenshots, reason about what to click/type, execute "
        "the action, re-screenshot, and repeat until the goal is achieved "
        "or max_steps is reached.  Requires a VLM backend configured via "
        "the OPENAI_API_KEY (or ANTHROPIC_API_KEY) environment variable.  "
        "Returns a JSON object with success, steps_taken, decisions, the "
        "last screenshot (base64 PNG), the full action trajectory, and "
        "the task template that was used.  Use the 'computer_use' tool "
        "for individual low-level actions across both browser and "
        "desktop; use this tool when you need vision-guided multi-step "
        "automation.  Pass template_name to specialise the system "
        "prompt and per-step guidance for a particular task category "
        "(navigate / fill_form / extract_data / login / search).  "
        "Unknown names fall back to the generic prompt automatically."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "High-level goal for the computer-use session, "
                               "e.g. 'open Notepad and type hello world'",
            },
            "max_steps": {
                "type": "integer",
                "description": "Maximum VLM decision steps before giving up "
                               "(default 20, each step is screenshot+reason+act)",
                "default": 20,
            },
            "template_name": {
                "type": "string",
                "description": (
                    "Optional VLM task template to specialise the prompt "
                    "for.  One of: 'navigate', 'fill_form', 'extract_data', "
                    "'login', 'search'.  Empty / unknown names fall back "
                    "to the generic computer-use prompt."
                ),
                "enum": [
                    "",
                    "navigate",
                    "fill_form",
                    "extract_data",
                    "login",
                    "search",
                ],
                "default": "",
            },
        },
        "required": ["goal"],
    },
    execute=_vlm_execute,
    intents=["coding", "system"],
    category="system",
    semantic_type="exec",
)
