#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Yim.
# The Yim project belongs to the Dunimd Team.
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

import asyncio
import logging
import traceback
from typing import Any

logger = logging.getLogger("yim.server.ws")

from yim.config import YmiConfig
from yim.server.protocol import (
    ClientCancel,
    ClientConfigure,
    ClientDeleteModel,
    ClientGetConfig,
    ClientListModels,
    ClientListSessions,
    ClientNewSession,
    ClientRollbackLog,
    ClientRollbackCheckout,
    ClientSearch,
    ClientSetActiveModel,
    ClientPing,
    ClientRespondPermission,
    ClientResume,
    ClientRun,
    ClientUpdateAgent,
    ClientUpdateMCP,
    ClientUpdateModels,
    ClientUpdateSkills,
    ClientMessage,
    parse_client_message,
    encode_agent_updated,
    encode_config_data,
    encode_configured,
    encode_error,
    encode_finish,
    encode_mcp_updated,
    encode_models_list,
    encode_models_updated,
    encode_permission_request,
    encode_pong,
    encode_rollback_checkout,
    encode_rollback_log,
    encode_search_results,
    encode_session_ready,
    encode_sessions_list,
    encode_skills_list,
    encode_skills_updated,
    encode_telemetry,
    encode_text_delta,
    encode_thinking_delta,
    encode_tool_call_start,
    encode_tool_call_delta,
    encode_tool_call_end,
    encode_tool_progress,
    encode_tool_result,
)
from yim.server.session_manager import SessionManager
from yim.utils.types import (
    TextDelta,
    ThinkingDelta,
    ToolCallStart,
    ToolCallDelta,
    ToolCallEnd,
    ToolProgress,
    ToolResult,
    PermissionRequest,
    Finish,
)


class YmiWSHandler:
    def __init__(self, session_manager: SessionManager, config: YmiConfig | None = None) -> None:
        self._manager = session_manager
        self._default_config = config
        self._current_session_id: str | None = None
        self._info = None  # lazily created session

    def _get_or_create_session(self):
        """Lazily create a session only when needed (first run or new_session)."""
        if self._info is None:
            self._info = self._manager.create_session(config=self._default_config)
            self._current_session_id = self._info.session_id
        return self._info

    async def handle(self, ws) -> None:
        existing = self._manager.try_resume_most_recent(config=self._default_config)
        if existing is not None:
            self._info = existing
            self._current_session_id = existing.session_id
            msgs = [m for m in existing.agent.session.messages if m.get("role") != "system"]
            await ws.send(encode_session_ready(existing.session_id, messages=msgs))
        else:
            self._info = None
            self._current_session_id = None
            await ws.send(encode_session_ready(""))

        async for raw in ws:
            try:
                msg = parse_client_message(raw)
            except Exception:
                await ws.send(encode_error("Failed to parse message", "parse_error"))
                continue

            if msg is None:
                await ws.send(encode_error("Unknown message type", "parse_error"))
                continue

            if isinstance(msg, ClientPing):
                if self._info:
                    self._manager.touch(self._info.session_id)
                await ws.send(encode_pong())

            elif isinstance(msg, ClientListModels):
                info = self._get_or_create_session()
                self._manager.touch(info.session_id)
                models = await info.agent.loop.backend.list_models()
                await ws.send(encode_models_list(models))

            elif isinstance(msg, ClientListSessions):
                sessions = self._list_all_sessions()
                await ws.send(encode_sessions_list(sessions))

            elif isinstance(msg, ClientNewSession):
                # Remove old session if it was empty (no real messages)
                if self._info:
                    real_msgs = [m for m in self._info.agent.session.messages if m.get("role") != "system"]
                    if not real_msgs:
                        self._manager.remove_session(self._info.session_id)
                self._info = self._manager.create_session(config=self._default_config)
                self._current_session_id = self._info.session_id
                await ws.send(encode_session_ready(self._info.session_id))

            elif isinstance(msg, ClientConfigure):
                # Use the current session (may have been switched via resume)
                session = self._manager.get_session(self._current_session_id) if self._current_session_id else None
                if session is None:
                    session = self._get_or_create_session()
                self._manager.touch(session.session_id)
                # Keys that require rebuilding the backend instance
                _backend_keys = {"backend_type", "api_key", "base_url", "model"}
                _rebuild = _backend_keys & set(msg.config.keys())
                for key, value in msg.config.items():
                    # Don't overwrite non-empty values with empty ones
                    if value == "" or value is None:
                        continue
                    if hasattr(session.agent.config, key):
                        setattr(session.agent.config, key, value)
                if _rebuild:
                    session.agent.rebuild_backend()
                # Persist config to ~/.dunimd/yim/model/config.toml
                try:
                    from yim.config import _get_config_path
                    config_path = _get_config_path()
                    session.agent.config.save(str(config_path))
                except Exception as exc:
                    logger.warning("Failed to save config: %s", exc)
                await ws.send(encode_configured(msg.config))

            elif isinstance(msg, ClientRun):
                # Support session-aware runs: use the specified session or the connection's default
                if msg.session_id:
                    session = self._manager.load_or_create_session(msg.session_id, config=self._default_config)
                    self._info = session
                    self._current_session_id = session.session_id
                else:
                    session = self._get_or_create_session()

                self._manager.touch(session.session_id)

                if session.is_running:
                    await ws.send(encode_error("Session already running", "busy"))
                    continue

                acquired = await self._manager.acquire_slot()
                if not acquired:
                    await ws.send(encode_error("Server at capacity, try later", "capacity"))
                    continue

                session.is_running = True
                prompt = msg.prompt
                system_prompt = msg.system_prompt

                if msg.specialty and msg.specialty != "general":
                    session.agent.loop.prompt_builder._specialty = msg.specialty

                # Persist immediately so session appears in history when user clicks send
                session.agent.add_message("user", prompt)
                self._manager._save_session(session)

                try:
                    async for event in session.agent.run(prompt=prompt, system_prompt=system_prompt):
                        await self._dispatch_event(ws, session, event)
                except Exception as e:
                    logger.error(f"Agent run failed: {e}\n{traceback.format_exc()}")
                    try:
                        await ws.send(encode_error(str(e), "execution_error"))
                    except Exception:
                        pass

                # Send telemetry summary after run completes
                if session.agent.telemetry.enabled:
                    summary = session.agent.telemetry.get_summary()
                    await ws.send(encode_telemetry(summary))

                session.is_running = False
                self._manager.release_slot()
                # Persist session after each run
                self._manager._save_session(session)

            elif isinstance(msg, ClientRespondPermission):
                session = self._manager.get_session(self._current_session_id) if self._current_session_id else None
                if session is None:
                    session = self._get_or_create_session()
                self._manager.touch(session.session_id)
                session.agent.respond_permission(msg.decision)

            elif isinstance(msg, ClientCancel):
                if msg.session_id:
                    session = self._manager.get_session(msg.session_id)
                    if session is None:
                        session = self._get_or_create_session()
                else:
                    session = self._get_or_create_session()
                self._manager.touch(session.session_id)
                if session.agent_task and not session.agent_task.done():
                    session.agent_task.cancel()
                session.is_running = False
                self._manager.release_slot()
                await ws.send(encode_finish("cancelled"))

            elif isinstance(msg, ClientGetConfig):
                info = self._get_or_create_session()
                self._manager.touch(info.session_id)
                config_data = info.agent.config.to_dict()
                if "models" in config_data:
                    config_data["models"] = [
                        m.to_dict() if hasattr(m, "to_dict") else m
                        for m in config_data["models"]
                    ]
                available = self._build_skills_list(info)
                config_data["available_skills"] = available
                await ws.send(encode_config_data(config_data))

            elif isinstance(msg, ClientUpdateModels):
                info = self._get_or_create_session()
                self._manager.touch(info.session_id)
                from yim.config import ModelConfig
                models = [
                    ModelConfig.from_dict(m) if isinstance(m, dict) else m
                    for m in msg.models
                ]
                info.agent.config.models = models
                info.agent.config.active_model_index = msg.active_model_index
                info.agent.config.apply_active_model()
                info.agent.rebuild_backend()
                self._persist_config(info)
                await ws.send(encode_models_updated(
                    [m.to_dict() if hasattr(m, "to_dict") else m for m in models],
                    msg.active_model_index,
                ))

            elif isinstance(msg, ClientSetActiveModel):
                info = self._get_or_create_session()
                self._manager.touch(info.session_id)
                if 0 <= msg.model_index < len(info.agent.config.models):
                    info.agent.config.active_model_index = msg.model_index
                    info.agent.config.apply_active_model()
                    info.agent.rebuild_backend()
                    self._persist_config(info)
                    await ws.send(encode_models_updated(
                        [m.to_dict() if hasattr(m, "to_dict") else m for m in info.agent.config.models],
                        msg.model_index,
                    ))
                else:
                    await ws.send(encode_error("Invalid model index", "invalid_index"))

            elif isinstance(msg, ClientDeleteModel):
                info = self._get_or_create_session()
                self._manager.touch(info.session_id)
                if 0 <= msg.model_index < len(info.agent.config.models):
                    del info.agent.config.models[msg.model_index]
                    if info.agent.config.active_model_index >= len(info.agent.config.models):
                        info.agent.config.active_model_index = max(0, len(info.agent.config.models) - 1)
                    if info.agent.config.models:
                        info.agent.config.apply_active_model()
                        info.agent.rebuild_backend()
                    self._persist_config(info)
                    await ws.send(encode_models_updated(
                        [m.to_dict() if hasattr(m, "to_dict") else m for m in info.agent.config.models],
                        info.agent.config.active_model_index,
                    ))
                else:
                    await ws.send(encode_error("Invalid model index", "invalid_index"))

            elif isinstance(msg, ClientUpdateSkills):
                info = self._get_or_create_session()
                self._manager.touch(info.session_id)
                info.agent.config.enabled_skills = list(msg.enabled_skills)
                self._persist_config(info)
                available = self._build_skills_list(info)
                await ws.send(encode_skills_updated(msg.enabled_skills, available))

            elif isinstance(msg, ClientUpdateMCP):
                info = self._get_or_create_session()
                self._manager.touch(info.session_id)
                info.agent.config.mcp_servers = list(msg.mcp_servers)
                self._persist_config(info)
                await ws.send(encode_mcp_updated(msg.mcp_servers))

            elif isinstance(msg, ClientUpdateAgent):
                info = self._get_or_create_session()
                self._manager.touch(info.session_id)
                if msg.system_prompt:
                    info.agent.config.system_prompt = msg.system_prompt
                if msg.specialty:
                    info.agent.config.default_specialty = msg.specialty
                if msg.permission_mode:
                    info.agent.config.permission_mode = msg.permission_mode  # type: ignore[assignment]
                if msg.max_turns > 0:
                    info.agent.config.max_turns = msg.max_turns
                self._persist_config(info)
                await ws.send(encode_agent_updated({
                    "system_prompt": info.agent.config.system_prompt,
                    "specialty": info.agent.config.default_specialty,
                    "permission_mode": info.agent.config.permission_mode,
                    "max_turns": info.agent.config.max_turns,
                }))

            elif isinstance(msg, ClientSearch):
                results = self._do_search(msg.query)
                await ws.send(encode_search_results(results))

            elif isinstance(msg, ClientRollbackLog):
                sid = msg.session_id or self._current_session_id
                if not sid:
                    await ws.send(encode_error("No active session", "no_session"))
                    continue
                from yim.rollback import YmiRollbackGit
                rb = YmiRollbackGit()
                commits = rb.tree(sid)
                await ws.send(encode_rollback_log(sid, commits))

            elif isinstance(msg, ClientRollbackCheckout):
                sid = msg.session_id or self._current_session_id
                if not sid or not msg.commit_hash:
                    await ws.send(encode_error("Missing session_id or commit_hash", "invalid_request"))
                    continue
                session = self._manager.load_or_create_session(sid, config=self._default_config)
                from yim.rollback import YmiRollbackGit
                rb = YmiRollbackGit()
                ok = rb.checkout(session.agent.loop.session, msg.commit_hash)
                if not ok:
                    await ws.send(encode_error(f"Commit not found: {msg.commit_hash[:8]}...", "not_found"))
                    continue
                self._current_session_id = sid
                self._info = session
                self._manager._save_session(session)
                msgs = [m for m in session.agent.loop.session.messages if m.get("role") != "system"]
                await ws.send(encode_rollback_checkout(
                    sid, msg.commit_hash, msgs, session.agent.loop.session.turn_count,
                ))

            elif isinstance(msg, ClientResume):
                if msg.session_id:
                    session = self._manager.load_or_create_session(msg.session_id, config=self._default_config)
                else:
                    session = self._get_or_create_session()
                self._current_session_id = session.session_id
                # Send messages without resetting — reset() would wipe history
                msgs = [m for m in session.agent.session.messages if m.get("role") != "system"]
                await ws.send(encode_session_ready(session.session_id, messages=msgs))

    def _list_all_sessions(self) -> list[dict[str, Any]]:
        """List sessions — combines in‑memory sessions with on‑disk index."""
        result = self._manager.list_sessions()
        index_entries = self._manager.query_index()
        active_ids = {s["session_id"] for s in result}
        for entry in index_entries:
            if entry["session_id"] not in active_ids:
                result.append(entry)
        result.sort(key=lambda s: s.get("last_active", s.get("created_at", 0)), reverse=True)
        result = [s for s in result if (s.get("message_count") or 0) > 0]
        return result

    @staticmethod
    def _extract_preview(data: dict[str, Any]) -> str:
        messages = data.get("messages", [])
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str) and content.strip():
                    return content.strip()[:80]
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "").strip()
                            if text:
                                return text[:80]
        return "Empty session"

    def _do_search(self, query: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        q = query.strip().lower()
        if not q:
            return results
        import os

        sessions_dir = self._manager._get_sessions_dir()
        from yim.session import YmiSession
        try:
            for entry in os.scandir(sessions_dir):
                if len(results) >= 80:
                    break
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                sid = entry.name
                preview = YmiSession.load_preview(entry.path) or ""
                turn_matches = YmiSession.search_turns(entry.path, q)
                for tm in turn_matches:
                    results.append({
                        "kind": "conversation",
                        "session_id": sid,
                        "role": tm["role"],
                        "snippet": tm["snippet"],
                        "preview": preview or "Empty session",
                    })
                    if len(results) >= 80:
                        break
        except Exception:
            pass

        workspace = os.getcwd()
        if os.path.isdir(workspace):
            excluded = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "target", ".yim", ".pytest_cache", ".mypy_cache", "__pypackages__"}
            for root, dirs, files in os.walk(workspace):
                dirs[:] = [d for d in dirs if d not in excluded and not d.startswith(".")]
                if len(results) >= 100:
                    break
                for fname in files:
                    if len(results) >= 100:
                        break
                    if fname.startswith("."):
                        continue
                    fpath = os.path.join(root, fname)
                    rel = os.path.relpath(fpath, workspace).replace("\\", "/")
                    name_match = q in fname.lower()
                    if name_match:
                        results.append({"kind": "file", "path": rel, "snippet": rel})
                        continue
                    try:
                        size = os.path.getsize(fpath)
                        if size > 300_000 or size == 0:
                            continue
                        ext = os.path.splitext(fname)[1].lower()
                        if ext in (".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".mp3", ".mp4", ".wav", ".zip", ".tar", ".gz", ".7z", ".exe", ".dll", ".so", ".dylib", ".wasm", ".bin", ".pyc", ".pyo"):
                            continue
                        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                            for li, line in enumerate(f):
                                if q in line.lower():
                                    results.append({
                                        "kind": "file",
                                        "path": rel,
                                        "line": li + 1,
                                        "snippet": line.strip()[:120],
                                    })
                                    break
                    except Exception:
                        continue

        results.sort(key=lambda r: 0 if r["kind"] == "conversation" else 1)
        return results[:60]

    def _persist_config(self, info: Any) -> None:
        try:
            from yim.config import _get_config_path
            config_path = _get_config_path()
            info.agent.config.save(str(config_path))
        except Exception as exc:
            logger.warning("Failed to persist config: %s", exc)

    @staticmethod
    def _build_skills_list(info: Any) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            registry = info.agent.skill_registry
            for name, skill in registry._skills.items():
                results.append({
                    "name": name,
                    "description": skill.description,
                    "aliases": skill.aliases,
                    "source": str(skill.source) if hasattr(skill, "source") else "bundled",
                })
        except Exception:
            pass
        return results

    async def _dispatch_event(self, ws, info, event: Any) -> None:
        if isinstance(event, TextDelta) and event.text:
            await ws.send(encode_text_delta(event.text))

        elif isinstance(event, ThinkingDelta) and event.text:
            await ws.send(encode_thinking_delta(event.text))

        elif isinstance(event, ToolCallStart):
            await ws.send(encode_tool_call_start(event.name, event.id))

        elif isinstance(event, ToolCallDelta):
            await ws.send(encode_tool_call_delta(event.id, event.key, event.value))

        elif isinstance(event, ToolCallEnd):
            await ws.send(encode_tool_call_end(event.id))

        elif isinstance(event, ToolProgress):
            await ws.send(encode_tool_progress(event.id, event.tool_name, event.status))

        elif isinstance(event, ToolResult):
            content = event.content
            if len(content) > 100000:
                content = content[:100000] + "\n... (truncated)"
            await ws.send(encode_tool_result(event.id, content, event.is_error))

        elif isinstance(event, PermissionRequest):
            await ws.send(encode_permission_request(event.tool_name, event.reason))

        elif isinstance(event, Finish):
            await ws.send(encode_finish(event.reason, event.usage, event.error))
