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



import asyncio
import base64
import contextlib
import json
import logging
import os
import re
import shutil
import tempfile
import time
import traceback
import zipfile

import websockets
from dataclasses import replace
from typing import Any

logger = logging.getLogger("encre.server.ws")

from encre.backend import create_backend  # noqa: E402
from encre.backends.catalog import catalog_payload  # noqa: E402
from encre.backends.mcp_catalog import mcp_catalog_payload  # noqa: E402
from encre.channels.slash_commands import get_slash_command_defs  # noqa: E402
from encre.config import (  # noqa: E402
    AgentConfig,
    EncreConfig,
    ModelConfig,
    SubAgentConfig,
)
from encre.server.protocol import (  # noqa: E402
    ClientAddDocument,
    ClientAgentCreate,
    ClientAgentDelete,
    ClientAgentList,
    ClientAgentSetActive,
    ClientAgentUpdate,
    ClientAutomationCancelJob,
    ClientAutomationCreateJob,
    ClientAutomationDeleteJob,
    ClientAutomationGetHistory,
    ClientAutomationListJobs,
    ClientAutomationToggleJob,
    ClientAutomationUpdateJob,
    ClientCancel,
    ClientCloseWorkspace,
    ClientEngineInstallResponse,
    ClientConfigure,
    ClientDeleteGlobalRule,
    ClientDeleteIndex,
    ClientDeleteMessage,
    ClientDeleteModel,
    ClientDeleteSession,
    ClientEditMessage,
    ClientExportSession,
    ClientFetchModels,
    ClientGetConfig,
    ClientGetGitignore,
    ClientGetGlobalRuleContent,
    ClientGetMemoryDetail,
    ClientGetMemoryList,
    ClientGetProfile,
    ClientIclawResume,
    ClientInstallSkill,
    ClientListDocuments,
    ClientListGlobalRules,
    ClientListModels,
    ClientListProjectRules,
    ClientListProjectHooks,
    ClientListSessions,
    ClientListAllSessions,
    ClientListWorkspaces,
    ClientNewSession,
    ClientOpenWorkspace,
    ClientPing,
    ClientReindexWorkspace,
    ClientRemoveDocument,
    ClientRemoveWorkspace,
    ClientRenameSession,
    ClientRespondPermission,
    ClientRespondPlan,
    ClientRespondQuestion,
    ClientResume,
    ClientRetry,
    ClientRollbackBranch,
    ClientRollbackCheckout,
    ClientRollbackLog,
    ClientRun,
    ClientSaveGlobalRule,
    ClientSearch,
    ClientSetActiveModel,
    ClientSetGitignore,
    ClientSetPlanMode,
    ClientSwitchBranch,
    ClientTerminalKill,
    ClientTerminalListShells,
    ClientTerminalResize,
    ClientTerminalSpawn,
    ClientTerminalWrite,
    ClientTestAdapter,
    ClientUninstallSkill,
    ClientUpdateAgent,
    ClientUpdateMCP,
    ClientUpdateModels,
    ClientUpdateSkill,
    ClientUpdateSkills,
    ClientUpdateSubAgents,
    ClientGetUsageStats,
    ClientValidateModel,
    encode_server_message,
    parse_client_message,
)
from encre.server.session_manager import SessionManager  # noqa: E402
from encre.spec import EncreSpecEngine  # noqa: E402
from encre.utils.tokens import count_message_tokens  # noqa: E402


def _inject_context_windows(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure every model dict has a real ``context_window`` value.

    ``ModelConfig.to_dict()`` returns 0 for legacy configs.  This function
    creates a temporary backend to resolve the actual window size so the
    frontend canvas panel shows the correct token budget.
    """
    for m in models:
        if m.get("context_window", 0) > 0:
            continue
        bt = m.get("backend_type", "")
        mid = m.get("model_id", "")
        if bt and mid:
            try:
                be = create_backend(bt, model=mid, base_url=m.get("base_url", ""))
                if be:
                    m["context_window"] = be.context_window_size()
            except Exception:
                pass
    return models




from encre.keybinds import (  # noqa: E402
    load_keybinds,
    save_keybinds,
)
from encre.settings_manager import (  # noqa: E402  # noqa: E501
    load_custom_slash_commands,
    save_custom_slash_commands,
)
from encre.utils.types import (  # noqa: E402
    Artifact,
    AssistantBoundary,
    CompactNotification,
    EngineInstallProgress,
    EngineInstallRequest,
    Finish,
    PermissionRequest,
    PlanUpdate,
    QuestionRequest,
    Reference,
    TextDelta,
    ThinkingDelta,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallStart,
    ToolProgress,
    ToolResult,
    WorkflowCompletedEvent,
    WorkflowStartedEvent,
    WorkflowTaskEvent,
)


class EncreWSHandler:
    def __init__(self, session_manager: SessionManager, config: EncreConfig | None = None,
                 index_manager=None, adapter_manager=None, scheduler=None) -> None:
        self._manager = session_manager
        self._default_config = config
        self._index_manager = index_manager
        self._adapter_manager = adapter_manager
        self._scheduler = scheduler  # EncreScheduler from iClawEngine, if available
        self._current_session_id: str | None = None
        self._info = None  # lazily created session
        self._workspace_path: str = ""  # current workspace path (empty = normal mode)
        self._current_ws_id: str = ""
        self._index_progress_callback = None
        self._client_encrypted: bool | None = None  # detected from first client message
        self._spec_engine = EncreSpecEngine()
        self._term_sessions: dict[int, dict] = {}  # terminal_id -> {proc, reader_task}
        self._term_seq = 0
        self._connections: list[Any] = []
        self._iclaw_task: asyncio.Task[None] | None = None
        self._manager.on_sessions_changed(self._broadcast_sessions)

    async def _send(self, ws, msg_type: str, **kwargs) -> None:
        encrypt = self._client_encrypted if self._client_encrypted is not None else False
        try:
            payload = encode_server_message(msg_type, encrypt=encrypt, **kwargs)
        except Exception as exc:
            logger.error("[_send] Failed to encode %s: %s\n%s", msg_type, exc, traceback.format_exc())  # noqa: E501
            return
        try:
            await ws.send(payload)
        except Exception as exc:
            logger.warning("[_send] Failed to send %s: %s", msg_type, exc)
            # WebSocket disconnected -- cancel any running agent
            self._cancel_current_task()

    def _resolve_startup_mode(self) -> str:
        """Resolve startup_session_mode: settings.json takes priority (runtime changes),
        fall back to config default."""
        try:
            from encre.settings_manager import load_settings
            stored = load_settings()
            mode = stored.get("startup_session_mode")
            if mode in ("normal", "iwork", "iclaw"):
                return mode
        except Exception:
            pass
        if self._default_config is not None:
            return getattr(self._default_config, 'startup_session_mode', 'normal')
        return "normal"

    def _resolve_startup_behavior(self) -> str:
        """Resolve startup_session_behavior: settings.json priority, fall back to config."""
        try:
            from encre.settings_manager import load_settings
            stored = load_settings()
            behavior = stored.get("startup_session_behavior")
            if behavior in ("new", "last"):
                return behavior
        except Exception:
            pass
        if self._default_config is not None:
            return getattr(self._default_config, 'startup_session_behavior', 'new')
        return "new"

    def _get_or_create_session(self):
        """Lazily create a session only when needed (first run or new_session)."""
        if self._info is None:
            self._info = self._manager.create_session(config=self._default_config)
            self._current_session_id = self._info.session_id
            # Tag with current channel so _list_all_sessions groups it correctly
            self._info.agent.session.metadata["channel"] = "iwork" if self._workspace_path else "normal"  # noqa: E501
            # Load MCP servers from the canonical mcp.json
            try:
                from encre.tools.mcp_manager import default_mcp_config_path
                mcp_path = default_mcp_config_path()
                servers = self._load_mcp_servers(mcp_path)
                if servers:
                    self._info.agent.config.mcp_servers = servers
            except Exception:
                pass
        return self._info

    async def handle(self, ws) -> None:
        self._info = None
        self._current_session_id = None
        self._current_ws_id = ""
        self._index_progress_callback = None

        # Respect startup_session_behavior setting: "last" resumes the most recent session
        startup_behavior = self._resolve_startup_behavior()
        startup_mode = self._resolve_startup_mode()
        if startup_behavior == "last":
            try:
                resumed = self._manager.try_resume_most_recent(config=self._default_config)
                if resumed is not None:
                    self._info = resumed
                    self._current_session_id = resumed.session_id
                    sess = resumed.agent.session
                    sess.rebuild_artifacts_from_messages()
                    context = sess.get_context_messages()
                    msgs = [m for m in context if m.get("role") != "system"]
                    plan = sess.plan_items
                    arts = sess.artifacts
                    branches_list = [b.__dict__ for b in sess.branches.values()]
                    await self._send(ws, "session_ready", session_id=resumed.session_id,
                                     messages=msgs, plan_items=plan, artifacts=arts,
                                     branches=branches_list, active_branch_id=sess.active_branch_id)
                else:
                    placeholder = self._get_or_create_session()
                    await self._send(ws, "session_ready", session_id=placeholder.session_id, plan_items=[])
            except Exception:
                placeholder = self._get_or_create_session()
                await self._send(ws, "session_ready", session_id=placeholder.session_id, plan_items=[])
        else:
            # Normal mode: start fresh
            placeholder = self._get_or_create_session()
            await self._send(ws, "session_ready", session_id=placeholder.session_id, plan_items=[])

        # Track connection for gateway status broadcasting
        self._connections.append(ws)
        if self._adapter_manager:
            try:
                status = self._adapter_manager.get_status()
                await self._send(ws, "gateway_status", status=status)
            except Exception as e:
                logger.warning("[gateway_status] send error: %s", e)

        try:
            async for raw in ws:
                if self._client_encrypted is None:
                    text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                    self._client_encrypted = not text.strip().startswith("{")

                try:
                    msg = parse_client_message(raw)
                except Exception:
                    await self._send(ws, "error", message="Failed to parse message", code="parse_error")  # noqa: E501
                    continue

                if msg is None:
                    await self._send(ws, "error", message="Unknown message type", code="parse_error")  # noqa: E501
                    continue

                if isinstance(msg, ClientPing):
                    if self._info:
                        self._manager.touch(self._info.session_id)
                    await self._send(ws, "pong")

                elif isinstance(msg, ClientListModels):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    models = await info.agent.loop.backend.list_models()
                    await self._send(ws, "models_list", models=models)

                elif isinstance(msg, ClientListSessions):
                    sessions = self._list_all_sessions()
                    await self._send(ws, "sessions_list", sessions=sessions)

                elif isinstance(msg, ClientListAllSessions):
                    # Tray popup needs both modes' sessions at once.
                    normal = self._list_all_sessions(channel_filter="normal")
                    iwork = self._list_all_sessions(channel_filter="iwork")
                    await self._send(ws, "sessions_all", normal=normal, iwork=iwork)

                elif isinstance(msg, ClientNewSession):
                    if self._info:
                        real_msgs = [m for m in self._info.agent.session.messages if m.get("role") != "system"]  # noqa: E501
                        if not real_msgs:
                            await self._manager.remove_session(self._info.session_id)
                    # Use workspace config if currently in workspace mode
                    if self._workspace_path and os.path.isdir(self._workspace_path):
                        ws_config = replace(self._default_config, workspace=self._workspace_path)
                        _apply_workspace_config(ws_config, self._workspace_path)
                    else:
                        ws_config = replace(self._default_config, workspace="")
                    self._info = self._manager.create_session(config=ws_config)
                    self._current_session_id = self._info.session_id
                    # Tag the session with its channel immediately so
                    # _list_all_sessions filters it into the correct sidebar
                    self._info.agent.session.metadata["channel"] = "iwork" if self._workspace_path else "normal"  # noqa: E501
                    await self._send(ws, "session_ready", session_id=self._info.session_id, plan_items=[], request_id=msg.request_id)  # noqa: E501

                elif isinstance(msg, ClientConfigure):
                    session = (
                        self._manager.get_session(self._current_session_id)
                        if self._current_session_id else None
                    )
                    if session is None:
                        session = self._get_or_create_session()
                    self._manager.touch(session.session_id)
                    _backend_keys = {"backend_type", "api_key", "base_url", "model"}
                    _rebuild = _backend_keys & set(msg.config.keys())
                    logger.info("[configure] keys=%s, rebuild=%s", list(msg.config.keys()), _rebuild)  # noqa: E501
                    for key, value in msg.config.items():
                        if value == "" or value is None:
                            logger.info("[configure] skip key=%s (empty/null)", key)
                            continue
                        if hasattr(session.agent.config, key):
                            old_val = getattr(session.agent.config, key)
                            setattr(session.agent.config, key, value)
                            logger.info("[configure] set %s: %r -> %r", key, old_val, value)
                        else:
                            logger.warning("[configure] key=%s NOT found on EncreConfig, skipping", key)  # noqa: E501
                    if _rebuild:
                        session.agent.rebuild_backend()
                        logger.info("[configure] backend rebuilt due to key change")
                        #   Sync backend config to _default_config so EventRouter/adapter sessions
                        # get it too
                        for key in _backend_keys:
                            if key in msg.config and msg.config.get(key):
                                setattr(self._default_config, key, msg.config[key])
                        if "models" in msg.config and isinstance(msg.config["models"], list):
                            self._default_config.models = [
                                ModelConfig.from_dict(m) if isinstance(m, dict) else m
                                for m in msg.config["models"]
                            ]
                            self._default_config.apply_active_model()
                            logger.info("[configure] synced models to _default_config")
                    if self._adapter_manager:
                        adapter_keys = {k: v for k, v in msg.config.items() if k.startswith("adapter_")}  # noqa: E501
                        if adapter_keys:
                            await self._adapter_manager.apply_config(adapter_keys)
                            # Persist adapter configs on EncreConfig so they survive restart
                            parsed: dict[str, dict[str, Any]] = {}
                            for ak, av in adapter_keys.items():
                                parts = ak.split("_", 2)
                                if len(parts) >= 3:
                                    parsed.setdefault(parts[1], {})[parts[2]] = av
                            # Merge into adapter_configs so existing fields (e.g. push_chat_id)
                            # are not lost when only a subset of keys is sent.
                            for aid, fields in parsed.items():
                                if aid in session.agent.config.adapter_configs:
                                    session.agent.config.adapter_configs[aid].update(fields)
                                else:
                                    session.agent.config.adapter_configs[aid] = fields
                                if aid in self._default_config.adapter_configs:
                                    self._default_config.adapter_configs[aid].update(fields)
                                else:
                                    self._default_config.adapter_configs[aid] = fields
                            logger.info("[configure] applied %d adapter config keys and persisted", len(adapter_keys))  # noqa: E501
                    self._persist_config(session)
                    self._persist_settings(session)
                    if "custom_slash_commands" in msg.config:
                        custom_cmds = msg.config["custom_slash_commands"]
                        if isinstance(custom_cmds, list):
                            save_custom_slash_commands(custom_cmds)
                            logger.info("[configure] saved %d custom slash commands", len(custom_cmds))  # noqa: E501
                    if "keybinds" in msg.config:
                        raw = msg.config["keybinds"]
                        if isinstance(raw, dict):
                            save_keybinds(raw)
                            logger.info("[configure] saved keybinds (%d entries)", len(raw.get("keybinds", [])))  # noqa: E501
                    await self._send(ws, "configured", config=msg.config)

                elif isinstance(msg, ClientTestAdapter):
                    if not self._adapter_manager:
                        await self._send(ws, "adapter_test_result",
                            adapter_id=msg.adapter_id, success=False,
                            message="Adapter manager not available")
                        continue
                    from encre.adapters.manager import _ADAPTER_CLASSES
                    cls = _ADAPTER_CLASSES.get(msg.adapter_id)
                    if cls is None:
                        await self._send(ws, "adapter_test_result",
                            adapter_id=msg.adapter_id, success=False,
                            message=f"Unknown adapter: {msg.adapter_id}")
                        continue
                    try:
                        if hasattr(cls, 'validate_config'):
                            success, message = await cls.validate_config(msg.config)
                        else:
                            success, message = True, "No validation available"
                    except Exception as e:
                        success, message = False, str(e)

                    # On successful validation, auto-save the config so new credentials
                    # take effect immediately -- matches user expectation that Test + OK = applied.
                    if success and self._adapter_manager:
                        adapter_id = msg.adapter_id
                        adapter_keys: dict[str, Any] = {}
                        for k, v in msg.config.items():
                            if k != "enabled":
                                adapter_keys[f"adapter_{adapter_id}_{k}"] = v
                        adapter_keys[f"adapter_{adapter_id}_enabled"] = msg.config.get("enabled", True)  # noqa: E501
                        logger.info("[test_adapter] auto-saving config for %s: %s", adapter_id, list(adapter_keys.keys()))  # noqa: E501
                        await self._adapter_manager.apply_config(adapter_keys)
                        # Persist to configs so it survives restart
                        parsed: dict[str, dict[str, Any]] = {}
                        for ak, av in adapter_keys.items():
                            parts = ak.split("_", 2)
                            if len(parts) >= 3:
                                parsed.setdefault(parts[1], {})[parts[2]] = av
                        # Merge into adapter_configs so existing fields (push_chat_id)
                        # are not lost when the partial test config is saved.
                        for aid, fields in parsed.items():
                            if aid in self._default_config.adapter_configs:
                                self._default_config.adapter_configs[aid].update(fields)
                            else:
                                self._default_config.adapter_configs[aid] = fields
                        # Persist settings to disk
                        session = (
                            self._manager.get_session(self._current_session_id)
                            if self._current_session_id else None
                        )
                        if session is None:
                            session = self._get_or_create_session()
                        for aid, fields in parsed.items():
                            if aid in session.agent.config.adapter_configs:
                                session.agent.config.adapter_configs[aid].update(fields)
                            else:
                                session.agent.config.adapter_configs[aid] = fields
                        self._persist_settings(session)
                        # Notify frontend so its settings state reflects the new values
                        await self._send(ws, "configured", config=adapter_keys)
                        # Verify the adapter actually started -- validate_config only checks
                        #   the token endpoint, but connect() does more (gateway URL, WS,
                        # connectivity).
                        # If start_adapter failed, override the test result with the real error.
                        if adapter_id not in self._adapter_manager._instances:
                            err = self._adapter_manager._last_errors.get(adapter_id, "Adapter failed to start")  # noqa: E501
                            success = False
                            message = err
                            logger.warning("[test_adapter] %s validate OK but connect failed: %s", adapter_id, err)  # noqa: E501

                    await self._send(ws, "adapter_test_result",
                        adapter_id=msg.adapter_id, success=success, message=message)

                elif isinstance(msg, ClientRun):
                    #   iClaw mode: route through EventRouter in a task (same session space as
                    # adapters)
                    if msg.channel == "iclaw" and self._adapter_manager and self._adapter_manager.router:  # noqa: E501
                        router = self._adapter_manager.router
                        logger.info("[iclaw] received run: prompt=%.60s session_id=%s adapter_router=%s",  # noqa: E501
                                    msg.prompt, msg.session_id, bool(router))
                        # 在闭包外部提取所有需要捕获的值，避免闭包变量覆盖问题
                        iclaw_requested_sid = msg.session_id  # raw frontend value, resolved inside the task  # noqa: E501
                        iclaw_prompt = msg.prompt
                        iclaw_system_prompt = msg.system_prompt
                        iclaw_default_config = replace(self._default_config, workspace="")

                        async def _run_iclaw():
                            logger.info("[iclaw] task started, acquiring iclaw context")
                            async with router.iclaw_context():
                                sid = iclaw_requested_sid
                                if not sid:
                                    existing = router.session_manager.try_resume_most_recent(
                                        config=iclaw_default_config)
                                    if existing is not None:
                                        sid = existing.session_id
                                        logger.info("[iclaw] resumed most recent session: %s", sid)
                                    else:
                                        logger.info("[iclaw] no existing session, will create new one")  # noqa: E501
                                logger.info("[iclaw] calling router.submit_stream sid=%s", sid)

                                try:
                                    stream = router.submit_stream(
                                        channel_name="iclaw",
                                        prompt=iclaw_prompt,
                                        session_id=sid,
                                        system_prompt=iclaw_system_prompt,
                                    )
                                    try:
                                        async for event in stream:
                                            await self._dispatch_event(ws, None, event)
                                    except asyncio.CancelledError:
                                        logger.info("[iclaw] task cancelled")
                                        with contextlib.suppress(Exception):
                                            await stream.aclose()
                                        with contextlib.suppress(Exception):
                                            await self._send(ws, "finish", reason="cancelled")
                                    except Exception as e:
                                        logger.error("[iclaw] run error: %s", e, exc_info=True)
                                        with contextlib.suppress(Exception):
                                            await self._send(ws, "finish", reason="error", error=str(e))  # noqa: E501
                                except Exception as e:
                                    logger.error("[iclaw] setup error: %s", e, exc_info=True)
                                    with contextlib.suppress(Exception):
                                        await self._send(ws, "finish", reason="error", error=str(e))

                        self._iclaw_task = asyncio.create_task(_run_iclaw())
                        continue

                    if self._workspace_path and os.path.isdir(self._workspace_path):
                        run_config = replace(self._default_config, workspace=self._workspace_path)
                        _apply_workspace_config(run_config, self._workspace_path)
                    else:
                        run_config = replace(self._default_config, workspace="")
                    if msg.session_id:
                        session = self._manager.load_or_create_session(
                            msg.session_id, config=run_config)
                        self._info = session
                        self._current_session_id = session.session_id
                    else:
                        session = self._get_or_create_session()

                    self._manager.touch(session.session_id)

                    session.agent.session.metadata["channel"] = "iwork" if self._workspace_path else "normal"  # noqa: E501

                    # Temp chat: never persist, never list in sidebar
                    if msg.temp_chat:
                        session.agent.session.metadata["temp_chat"] = True
                        # Don't save this session -- it's ephemeral

                    # Log backend identity for debugging
                    _bk = session.agent.loop.backend
                    if _bk:
                        logger.info("[run] backend type=%s model=%s api_key=%s...",
                                    type(_bk).__name__, getattr(_bk, "model", "?"),
                                    (getattr(_bk, "api_key", "") or "")[:8])

                    if session.is_running:
                        await self._send(ws, "error", message="Session already running", code="busy",
                                         session_id=session.session_id)
                        continue

                    acquired = await self._manager.acquire_slot()
                    if not acquired:
                        await self._send(ws, "error",
                            message="Server at capacity, try later", code="capacity",
                            session_id=session.session_id)
                        continue

                    session.is_running = True
                    # If the backend was force-closed during a previous cancel
                    # (to abort an in-flight API request), rebuild it now.
                    with contextlib.suppress(Exception):
                        session.agent.rebuild_backend()
                    prompt = msg.prompt
                    system_prompt = msg.system_prompt
                    mode_prompt = msg.mode_prompt or ""

                    if msg.attachments:
                        attachment_block = _format_attachments(msg.attachments)
                        if attachment_block:
                            prompt = attachment_block + "\n\n" + prompt

                    if msg.specialty and msg.specialty != "general":
                        session.agent.loop.prompt_builder._specialty = msg.specialty

                    active_agent = session.agent.config.get_active_agent()
                    if active_agent is not None:
                        if not msg.system_prompt:
                            system_prompt = active_agent.system_prompt
                        if not msg.specialty:
                            session.agent.loop.prompt_builder._specialty = "general"
                        if active_agent.max_turns > 0:
                            session.agent.config.max_turns = active_agent.max_turns
                        if active_agent.permission_mode:
                            session.agent.config.permission_mode = active_agent.permission_mode

                    session.agent.config.slash_command_mode = msg.mode or ""

                    session.agent.add_message("user", prompt)
                    if not session.agent.session.metadata.get("temp_chat"):
                        await self._manager._save_session_async(session)
                    logger.info("[run] session=%s workspace=%s", session.session_id[:8], self._workspace_path or "(none)")  # noqa: E501

                    # Auto-name: fire-and-forget so conversation is not delayed.
                    sess = session.agent.session
                    if not sess.metadata.get("name") and sess.turn_count <= 1:
                        _sid = session.session_id
                        _p = prompt
                        asyncio.ensure_future(self._auto_name_and_rename(session, _p))

                    # Don't block on background code index -- let the agent run
                    # immediately. The code index becomes available asynchronously.
                    if self._index_manager and self._current_ws_id:
                        task = self._index_manager.get_task(self._current_ws_id)
                        if task and not task.done():
                            logger.info("[run] index still building, running agent without full index")  # noqa: E501

                    # Wire the engine-install requester's immediate emit
                    # hook so the desktop dialog pops up the moment a
                    # browser / desktop action needs the engine, without
                    # waiting for the agent's event loop to tick.
                    async def _emit_engine(evt: Any) -> None:
                        try:
                            await self._dispatch_event(ws, session, evt)
                        except Exception as exc:
                            logger.warning("engine emit failed: %s", exc)
                    try:
                        session.agent.set_engine_emit(_emit_engine)
                    except Exception:
                        logger.debug("agent has no set_engine_emit", exc_info=True)

                    async def _run_agent():
                        try:
                            async for event in session.agent.run(
                                prompt=prompt, system_prompt=system_prompt,
                                custom_instructions=mode_prompt):
                                await self._dispatch_event(ws, session, event)
                                # Mid-turn checkpoint & real-time canvas update
                                if isinstance(event, (ToolResult, AssistantBoundary)):
                                    # Push context usage to canvas panel so the
                                    # progress bar updates in real time
                                    ctx_msgs = session.agent.session.get_context_messages()
                                    ctx_tokens = count_message_tokens(ctx_msgs)
                                    window = session.agent.loop.backend.context_window_size() if session.agent.loop.backend else 0  # noqa: E501
                                    await self._send(ws, "context_usage",
                                        context_tokens=ctx_tokens,
                                        context_window=window,
                                        session_id=session.session_id)
                                    # Stream telemetry summary so the canvas panel
                                    # (Compactions / Tool Calls) updates in real
                                    # time, not only on agent-finish.
                                    if session.agent.telemetry.enabled:
                                        with contextlib.suppress(Exception):
                                            await self._send(ws, "telemetry",
                                                data=session.agent.telemetry.get_summary(),
                                                session_id=session.session_id)
                                    if not session.agent.session.metadata.get("temp_chat"):
                                        try:
                                            await self._manager._save_session_async(session)
                                        except Exception:
                                            pass  # non-blocking
                        except asyncio.CancelledError:
                            await self._send(ws, "finish", reason="cancelled", session_id=session.session_id)  # noqa: E501
                        except Exception as e:
                            logger.error(f"Agent run failed: {e}\n{traceback.format_exc()}")
                            with contextlib.suppress(Exception):
                                await self._send(ws, "error", message=str(e), code="execution_error", session_id=session.session_id)  # noqa: E501
                            with contextlib.suppress(Exception):
                                await self._send(ws, "finish", reason="error", session_id=session.session_id)  # noqa: E501
                        finally:
                            if session.agent.telemetry.enabled:
                                with contextlib.suppress(Exception):
                                    summary = session.agent.telemetry.get_summary()
                                    await self._send(ws, "telemetry", data=summary)
                            # Only release state when this task is still the
                            # current owner -- a new run may have already taken
                            # over, and we must NOT clear its is_running flag
                            # or release its semaphore slot.
                            if session.agent_task is asyncio.current_task():
                                session.is_running = False
                                self._manager.release_slot()
                                if not session.agent.session.metadata.get("temp_chat"):
                                    await self._manager._save_session_async(session)
                                self._manager.notify_session_completed()
                                session.agent_task = None

                    # Ensure any previous agent task is fully finished before
                    # starting a new one -- otherwise two _run_impl generators
                    # run on the same EncreLoop instance, corrupting shared
                    # state (session.messages, _cancel_event, caches, etc.).
                    if session.agent_task and not session.agent_task.done():
                        session.agent.loop.cancel()
                        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                            await asyncio.wait_for(session.agent_task, timeout=0.5)
                    session.agent_task = asyncio.create_task(_run_agent())

                elif isinstance(msg, ClientRespondPermission):
                    session = (
                        self._manager.get_session(self._current_session_id)
                        if self._current_session_id else None
                    )
                    if session is None:
                        session = self._get_or_create_session()
                    self._manager.touch(session.session_id)
                    session.agent.respond_permission(msg.decision)

                elif isinstance(msg, ClientRespondPlan):
                    session = (
                        self._manager.get_session(self._current_session_id)
                        if self._current_session_id else None
                    )
                    if session is None:
                        session = self._get_or_create_session()
                    self._manager.touch(session.session_id)
                    session.agent.loop.approve_plan(msg.proposal_id) if msg.approved else session.agent.loop.reject_plan(msg.proposal_id)  # noqa: E501

                elif isinstance(msg, ClientSetPlanMode):
                    session = (
                        self._manager.get_session(self._current_session_id)
                        if self._current_session_id else None
                    )
                    if session is None:
                        session = self._get_or_create_session()
                    self._manager.touch(session.session_id)
                    if msg.active:
                        session.agent.loop.enter_plan_mode(reason=msg.reason)
                    else:
                        session.agent.loop.exit_plan_mode(reason=msg.reason)

                elif isinstance(msg, ClientRespondQuestion):
                    session = (
                        self._manager.get_session(self._current_session_id)
                        if self._current_session_id else None
                    )
                    if session is None:
                        session = self._get_or_create_session()
                    self._manager.touch(session.session_id)
                    session.agent.loop.resolve_question(msg.answers)

                elif isinstance(msg, ClientEngineInstallResponse):
                    session = (
                        self._manager.get_session(self._current_session_id)
                        if self._current_session_id else None
                    )
                    agent = getattr(session, "agent", None) if session is not None else None
                    if agent is not None and hasattr(agent, "resolve_engine_install"):
                        agent.resolve_engine_install(msg.request_id, msg.choice)
                    await self._send(ws, "engine_install_response_ack",
                        request_id=msg.request_id, choice=msg.choice)

                elif isinstance(msg, ClientCancel):
                    # iClaw task cancel (runs concurrently in its own task)
                    if self._iclaw_task and not self._iclaw_task.done():
                        # Also cancel the agent loop so the EventRouter stops promptly
                        sid = msg.session_id or self._current_session_id or ""
                        if sid and self._adapter_manager and self._adapter_manager.router:
                            info = self._adapter_manager.router.session_manager.get_session(sid)
                            if info and info.agent.loop:
                                info.agent.loop.cancel()
                        self._iclaw_task.cancel()
                        await self._send(ws, "finish", reason="cancelled", session_id=sid)
                        continue

                    # Try EventRouter cancel_session as fallback (for adapter/gateway flows)
                    if self._adapter_manager and self._adapter_manager.router:
                        sid = msg.session_id or self._current_session_id or ""
                        if sid and self._adapter_manager.router.cancel_session(sid):
                            await self._send(ws, "finish", reason="cancelled", session_id=sid)
                            continue

                    session = None
                    if msg.session_id:
                        session = self._manager.get_session(msg.session_id)
                    if session is None and self._current_session_id:
                        session = self._manager.get_session(self._current_session_id)
                    if session is None:
                        continue
                    self._manager.touch(session.session_id)
                    if session.agent_task and not session.agent_task.done():
                        session.is_running = False
                        session.agent.loop.cancel()
                        session.agent_task.cancel()
                        # Force-close the backend HTTP client so any in-flight
                        # API request is aborted immediately instead of blocking
                        # until the 120s timeout.  This lets the old task unwind
                        # promptly.  The backend will be rebuilt on the next run.
                        with contextlib.suppress(Exception):
                            await session.agent.loop.backend.aclose()
                        self._manager.release_slot()
                        await self._send(ws, "finish", reason="cancelled", session_id=session.session_id)  # noqa: E501
                    else:
                        session.is_running = False
                        self._manager.release_slot()
                        await self._send(ws, "finish", reason="cancelled", session_id=session.session_id)  # noqa: E501

                elif isinstance(msg, ClientGetConfig):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    config_data = info.agent.config.to_dict(encrypt_api_keys=False)
                    if "models" in config_data:
                        config_data["models"] = _inject_context_windows(list(config_data["models"]))
                    available = await self._build_skills_list(info)
                    config_data["available_skills"] = available
                    config_data["tools_info"] = self._build_tools_info(info)
                    config_data["workspace_mode"] = "iwork" if self._workspace_path else "normal"
                    config_data["workspace_path"] = self._workspace_path
                    config_data["model_catalog"] = catalog_payload()
                    config_data["mcp_catalog"] = mcp_catalog_payload()
                    if "sub_agents" in config_data:
                        config_data["sub_agents"] = [
                            sa for sa in config_data["sub_agents"] if not sa.get("hidden", False)
                        ]
                    current_spec = self._spec_engine.current_spec
                    config_data["spec"] = current_spec.to_dict() if current_spec else None
                    config_data["slash_commands"] = get_slash_command_defs(
                        info.agent.command_registry
                    )
                    config_data["custom_slash_commands"] = load_custom_slash_commands()
                    config_data["keybinds"] = load_keybinds()
                    await self._send(ws, "config_data", config=config_data)

                elif isinstance(msg, ClientUpdateModels):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    models = [
                        ModelConfig.from_dict(m) if isinstance(m, dict) else m
                        for m in msg.models
                    ]
                    info.agent.config.models = models
                    info.agent.config.active_model_index = msg.active_model_index
                    info.agent.config.apply_active_model()
                    info.agent.rebuild_backend()
                    # Sync to _default_config so new sessions pick up the models
                    self._default_config.models = models
                    self._default_config.active_model_index = msg.active_model_index
                    self._default_config.apply_active_model()
                    logger.info("[update_models] models=%d, calling _persist_config", len(models))
                    self._persist_config(info)
                    models_dict = _inject_context_windows([
                        m.to_dict(encrypt_api_keys=False) if isinstance(m, ModelConfig) else m
                        for m in models
                    ])
                    await self._send(ws, "models_updated",
                        models=models_dict, active_model_index=msg.active_model_index)

                elif isinstance(msg, ClientSetActiveModel):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    if 0 <= msg.model_index < len(info.agent.config.models):
                        # Refuse to activate a disabled model
                        target = info.agent.config.models[msg.model_index]
                        if not target.enabled:
                            await self._send(ws, "error",
                                message=f"Model '{target.name}' is disabled", code="model_disabled")
                            return
                        info.agent.config.active_model_index = msg.model_index
                        info.agent.config.apply_active_model()
                        info.agent.rebuild_backend()
                        # Sync to _default_config
                        self._default_config.active_model_index = msg.model_index
                        self._default_config.apply_active_model()
                        self._persist_config(info)
                        cfg_models = info.agent.config.models
                        models_dict = _inject_context_windows([
                            m.to_dict(encrypt_api_keys=False) if isinstance(m, ModelConfig) else m
                            for m in cfg_models
                        ])
                        await self._send(ws, "models_updated",
                            models=models_dict, active_model_index=msg.model_index)
                    else:
                        await self._send(ws, "error",
                            message="Invalid model index", code="invalid_index")

                elif isinstance(msg, ClientDeleteModel):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    try:
                        if 0 <= msg.model_index < len(info.agent.config.models):
                            logger.info("[delete_model] deleting index=%d, total_models=%d",
                                        msg.model_index, len(info.agent.config.models))
                            del info.agent.config.models[msg.model_index]
                            if info.agent.config.active_model_index >= len(info.agent.config.models):  # noqa: E501
                                info.agent.config.active_model_index = max(0, len(info.agent.config.models) - 1)  # noqa: E501
                            if info.agent.config.models:
                                info.agent.config.apply_active_model()
                                info.agent.rebuild_backend()
                            # Sync to _default_config
                            self._default_config.models = info.agent.config.models
                            self._default_config.active_model_index = info.agent.config.active_model_index  # noqa: E501
                            if info.agent.config.models:
                                self._default_config.apply_active_model()
                            self._persist_config(info)
                            cfg_models = info.agent.config.models
                            models_dict = _inject_context_windows([
                                m.to_dict(encrypt_api_keys=False) if isinstance(m, ModelConfig) else m  # noqa: E501
                                for m in cfg_models
                            ])
                            await self._send(ws, "models_updated",
                                models=models_dict, active_model_index=info.agent.config.active_model_index)  # noqa: E501
                            logger.info("[delete_model] done, remaining=%d", len(cfg_models))
                        else:
                            logger.warning("[delete_model] invalid index %d (max %d)",
                                           msg.model_index, len(info.agent.config.models))
                            await self._send(ws, "error",
                                message="Invalid model index", code="invalid_index")
                    except Exception as exc:
                        logger.error("[delete_model] failed: %s\n%s", exc, traceback.format_exc())
                        await self._send(ws, "error", message=f"Delete model failed: {exc}", code="handler_error")  # noqa: E501

                elif isinstance(msg, ClientFetchModels):
                    from encre.backend import create_backend
                    backend = create_backend(
                        msg.backend_type,
                        api_key=msg.api_key,
                        base_url=msg.base_url,
                        model="",
                    )
                    if backend is None:
                        await self._send(ws, "error",
                            message=f"Unknown backend type: {msg.backend_type}", code="api_error")
                    else:
                        model_ids: list[str] = []
                        try:
                            model_ids = await backend.list_models()
                        except Exception as e:
                            await self._send(ws, "error",
                                message=f"Failed to fetch models: {e!s}", code="api_error")
                        finally:
                            await backend.aclose()
                        if model_ids:
                            await self._send(ws, "models_fetched", models=model_ids)

                elif isinstance(msg, ClientValidateModel):
                    from encre.backend import create_backend
                    backend = create_backend(
                        msg.backend_type,
                        api_key=msg.api_key,
                        base_url=msg.base_url,
                        model=msg.model_id,
                    )
                    if backend is None:
                        await self._send(ws, "model_validation_error",
                            message=f"Unknown backend type: {msg.backend_type}")
                    else:
                        try:
                            async for _ in backend.chat(
                                messages=[{"role": "user", "content": "hi"}],
                                max_tokens=msg.max_tokens,
                                stream=False,
                            ):
                                pass
                            await self._send(ws, "model_validated")
                        except Exception as e:
                            await self._send(ws, "model_validation_error",
                                message=f"Validation failed: {e!s}")
                        finally:
                            await backend.aclose()

                elif isinstance(msg, ClientUpdateSkills):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    info.agent.config.enabled_skills = list(msg.enabled_skills)
                    self._persist_config(info)
                    available = await self._build_skills_list(info)
                    await self._send(ws, "skills_updated",
                            enabled_skills=msg.enabled_skills, available_skills=available)

                elif isinstance(msg, ClientInstallSkill):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    from encre.config import get_data_dir
                    from encre.skills.types import SkillSource
                    skills_dir = get_data_dir() / "skills"
                    skills_dir.mkdir(parents=True, exist_ok=True)
                    try:
                        content = msg.content
                        file_path = msg.file_path
                        # Always install into a subdirectory named after the skill
                        skill_dir = skills_dir / msg.name
                        if skill_dir.exists():
                            shutil.rmtree(str(skill_dir), ignore_errors=True)
                        skill_dir.mkdir(parents=True, exist_ok=True)

                        if file_path and file_path.lower().endswith(".zip") and os.path.isfile(file_path):  # noqa: E501
                            self._install_skill_from_zip_file(file_path, skill_dir)
                            self._add_skill_to_index(skills_dir, msg.name, "zip")
                        elif self._looks_like_base64_zip(content):
                            self._install_skill_from_zip_data(content, skill_dir)
                            self._add_skill_to_index(skills_dir, msg.name, "zip")
                        else:
                            skill_md = skill_dir / "SKILL.md"
                            skill_md.write_text(content, encoding="utf-8")
                            self._add_skill_to_index(skills_dir, msg.name, "md")

                        info.agent.skill_registry.load_from_dir(str(skills_dir), source=SkillSource.USER)  # noqa: E501
                        available = await self._build_skills_list(info)
                        await self._send(ws, "skill_installed", name=msg.name, available_skills=available)  # noqa: E501
                    except Exception as e:
                        logger.error(f"Skill install failed: {e}")
                        await self._send(ws, "skill_install_error", name=msg.name, message=str(e))

                elif isinstance(msg, ClientUninstallSkill):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    from encre.config import get_data_dir
                    from encre.skills.types import SkillSource
                    skills_dir = get_data_dir() / "skills"
                    try:
                        skill_name = msg.name
                        # Find the actual skill directory -- the dir name may differ
                        # from the frontmatter name (e.g. zip file "github-1.0.0.zip"
                        # creates a dir named "github-1.0.0" but SKILL.md has "name: github").
                        found_dir = None
                        if (skills_dir / skill_name).exists():
                            found_dir = skills_dir / skill_name
                        else:
                            for entry in os.listdir(str(skills_dir)):
                                entry_path = skills_dir / entry
                                if entry_path.is_dir():
                                    skill_md = entry_path / "SKILL.md"
                                    if skill_md.exists():
                                        try:
                                            text = skill_md.read_text(encoding="utf-8")
                                            import re as _re
                                            m = _re.search(r"^name\s*:\s*(.+)$", text, _re.MULTILINE)  # noqa: E501
                                            if m and m.group(1).strip() == skill_name:
                                                found_dir = entry_path
                                                break
                                        except Exception:
                                            pass
                        if found_dir:
                            shutil.rmtree(str(found_dir), ignore_errors=True)
                            logger.info("[uninstall_skill] removed directory %s", found_dir)
                        # Remove from index -- find the correct key
                        index = EncreWSHandler._load_skills_index(skills_dir)
                        index_key = skill_name
                        if index_key not in index.get("skills", {}):
                            for k in list(index.get("skills", {})):
                                if k.startswith(skill_name):
                                    index_key = k
                                    break
                        index["skills"].pop(index_key, None)
                        EncreWSHandler._save_skills_index(skills_dir, index)
                        # Clear from registry and reload
                        info.agent.skill_registry._skills.pop(skill_name, None)
                        info.agent.skill_registry.load_from_dir(str(skills_dir), source=SkillSource.USER)  # noqa: E501
                        available = await self._build_skills_list(info)
                        await self._send(ws, "skill_uninstalled", name=skill_name, available_skills=available)  # noqa: E501
                    except Exception as e:
                        logger.error(f"Skill uninstall failed: {e}")
                        await self._send(ws, "error", message=f"Failed to uninstall skill: {e}")

                elif isinstance(msg, ClientUpdateSkill):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    from encre.config import get_data_dir
                    from encre.skills.types import SkillSource
                    skills_dir = get_data_dir() / "skills"
                    skills_dir.mkdir(parents=True, exist_ok=True)
                    try:
                        skill_dir = skills_dir / msg.name
                        skill_dir.mkdir(parents=True, exist_ok=True)
                        skill_md = skill_dir / "SKILL.md"
                        skill_md.write_text(msg.content, encoding="utf-8")
                        info.agent.skill_registry.load_from_dir(str(skills_dir), source=SkillSource.USER)  # noqa: E501
                        available = await self._build_skills_list(info)
                        await self._send(ws, "skill_installed", name=msg.name, available_skills=available)  # noqa: E501
                    except Exception as e:
                        await self._send(ws, "skill_install_error", name=msg.name, message=str(e))

                elif isinstance(msg, ClientUpdateMCP):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    try:
                        # Normalize: accept both list and dict (map) formats
                        raw = msg.mcp_servers
                        if isinstance(raw, dict):
                            # Standard mcpServers map format: {name: {config}, ...}
                            servers = []
                            for name, cfg in raw.items():
                                entry: dict[str, Any] = {"name": name, **cfg}
                                # Normalize transport field name
                                if "type" not in entry and "transport" in entry:
                                    entry["type"] = entry.pop("transport")
                                if "type" not in entry:
                                    entry["type"] = "stdio"
                                servers.append(entry)
                        elif isinstance(raw, list):
                            servers = list(raw)
                        else:
                            servers = []

                        logger.info("[update_mcp] updating %d servers", len(servers))
                        info.agent.config.mcp_servers = servers
                        self._persist_mcp_json(info, servers)
                        self._persist_config(info)
                        await info.agent.reconnect_mcp()
                        await self._send(ws, "mcp_updated", mcp_servers=servers)
                        logger.info("[update_mcp] done")
                    except Exception as exc:
                        logger.error("[update_mcp] failed: %s\n%s", exc, traceback.format_exc())
                        await self._send(ws, "error", message=f"MCP update failed: {exc}", code="handler_error")  # noqa: E501

                elif isinstance(msg, ClientUpdateAgent):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    if msg.system_prompt:
                        info.agent.config.system_prompt = msg.system_prompt
                    if msg.specialty:
                        info.agent.config.default_specialty = msg.specialty
                    if msg.permission_mode:
                        info.agent.config.permission_mode = msg.permission_mode
                    if msg.max_turns > 0:
                        info.agent.config.max_turns = msg.max_turns
                    self._persist_config(info)
                    await self._send(ws, "agent_updated", config={
                        "system_prompt": info.agent.config.system_prompt,
                        "specialty": info.agent.config.default_specialty,
                        "permission_mode": info.agent.config.permission_mode,
                        "max_turns": info.agent.config.max_turns,
                    })

                elif isinstance(msg, ClientSearch):
                    results = self._do_search(msg.query)
                    await self._send(ws, "search_results", results=results)

                elif isinstance(msg, ClientRollbackLog):
                    sid = msg.session_id or self._current_session_id
                    if not sid:
                        await self._send(ws, "error", message="No active session", code="no_session")  # noqa: E501
                        continue
                    from encre.rollback import EncreRollbackGit
                    rb = EncreRollbackGit()
                    commits = rb.tree(sid)
                    await self._send(ws, "rollback_log", session_id=sid, commits=commits)

                elif isinstance(msg, ClientRollbackCheckout):
                    sid = msg.session_id or self._current_session_id
                    if not sid or not msg.commit_hash:
                        await self._send(ws, "error",
                            message="Missing session_id or commit_hash",
                            code="invalid_request", session_id=sid or "")
                        continue
                    session = self._manager.load_or_create_session(sid, config=self._default_config)
                    from encre.rollback import EncreRollbackGit
                    rb = EncreRollbackGit()
                    ok = rb.checkout(session.agent.loop.session, msg.commit_hash)
                    if not ok:
                        await self._send(ws, "error",
                            message=f"Commit not found: {msg.commit_hash[:8]}...",
                            code="not_found", session_id=sid)
                        continue
                    self._current_session_id = sid
                    self._info = session
                    await self._manager._save_session_async(session)
                    s = session.agent.loop.session
                    msgs = [m for m in s.messages if m.get("role") != "system"]
                    # Find last user message text for input restoration
                    user_input = ""
                    for m in reversed(s.messages):
                        if m.get("role") == "user":
                            c = m.get("content", "")
                            user_input = c if isinstance(c, str) else ""
                            break
                    await self._send(ws, "rollback_checkout",
                        session_id=sid, commit_hash=msg.commit_hash, messages=msgs,
                        turn_count=s.turn_count,
                        plan_items=s.plan_items,
                        artifacts=s.artifacts,
                        user_input=user_input)

                elif isinstance(msg, ClientEditMessage):
                    session = self._get_or_create_session()
                    self._manager.touch(session.session_id)
                    try:
                        await self._edit_message(session, msg.message_index, msg.new_content)
                        msgs = [m for m in session.agent.session.messages if m.get("role") != "system"]  # noqa: E501
                        head = session.agent.loop.rollback.head(session.agent.session.id) or ""
                        await self._send(ws, "messages_updated", messages=msgs,
                                         session_id=session.session_id, commit_hash=head,
                                         plan_items=session.agent.session.plan_items,
                                         artifacts=session.agent.session.artifacts,
                                         references=session.agent.session.references)
                    except Exception as e:
                        logger.error(f"Edit message failed: {e}")
                        await self._send(ws, "error", message=str(e), code="edit_error",
                                         session_id=session.session_id)

                elif isinstance(msg, ClientDeleteMessage):
                    session = self._get_or_create_session()
                    self._manager.touch(session.session_id)
                    if session.is_running:
                        await self._send(ws, "error", message="Session is running, cannot delete messages", code="busy",  # noqa: E501
                                         session_id=session.session_id)
                        continue
                    try:
                        await self._delete_message(session, msg.message_index)
                        msgs = [m for m in session.agent.session.messages if m.get("role") != "system"]  # noqa: E501
                        head = session.agent.loop.rollback.head(session.agent.session.id) or ""
                        await self._send(ws, "messages_updated", messages=msgs,
                                         session_id=session.session_id, commit_hash=head,
                                         plan_items=session.agent.session.plan_items,
                                         artifacts=session.agent.session.artifacts,
                                         references=session.agent.session.references)
                    except Exception as e:
                        logger.error(f"Delete message failed: {e}")
                        await self._send(ws, "error", message=str(e), code="delete_error",
                                         session_id=session.session_id)

                elif isinstance(msg, ClientDeleteSession):
                    if not msg.session_id:
                        await self._send(ws, "error", message="No session_id provided", code="invalid_request")  # noqa: E501
                        continue
                    if self._current_session_id == msg.session_id:
                        self._current_session_id = None
                        self._info = None
                    from encre.config import get_data_dir as _get_data_dir
                    ok = self._manager.delete_session_from_disk(msg.session_id)
                    # Also clean up from EventRouter's session manager so the
                    # session doesn't reappear when list_sessions is called.
                    if self._adapter_manager and self._adapter_manager.router:
                        self._adapter_manager.router.session_manager.delete_session_from_disk(msg.session_id)
                    # Also clean up workspace session indices so the session
                    # doesn't reappear when list_sessions reloads from workspace dirs.
                    _remove_session_from_workspace_indices(msg.session_id)
                    # Also clean up sub-agent session directory (automation history entries)
                    sub_agent_dir = _get_data_dir() / "sub_agents" / msg.session_id
                    had_sub_agent = sub_agent_dir.is_dir()
                    if had_sub_agent:
                        shutil.rmtree(str(sub_agent_dir))
                        ok = True
                    # Remove automation history entry if scheduler exists
                    if self._scheduler:
                        self._scheduler.delete_job_execution_by_session_id(msg.session_id)
                    # Always broadcast automation update when a sub-agent session
                    # is deleted so the history list refreshes immediately,
                    # regardless of whether the scheduler found a matching entry.
                    if self._scheduler and had_sub_agent:
                        self.broadcast_automation_update()
                    if ok:
                        await self._send(ws, "session_deleted", session_id=msg.session_id)
                    else:
                        await self._send(ws, "error", message="Session not found", code="not_found")

                elif isinstance(msg, ClientExportSession):
                    if not msg.session_id:
                        await self._send(ws, "error", message="No session_id provided", code="invalid_request")  # noqa: E501
                        continue
                    from encre.session import EncreSession
                    dir_path = self._manager._session_dir_path(msg.session_id)
                    if not dir_path.is_dir():
                        await self._send(ws, "error", message="Session not found", code="not_found")
                        continue
                    try:
                        md = EncreSession.export_to_markdown(str(dir_path))
                        name = self._manager._index.get(msg.session_id, {}).get("name", msg.session_id[:8])  # noqa: E501
                        filename = f"{name or msg.session_id[:8]}.md"
                        await self._send(ws, "session_exported", session_id=msg.session_id, markdown=md, filename=filename)  # noqa: E501
                    except Exception as e:
                        logger.error(f"Export session failed: {e}")
                        await self._send(ws, "error", message=str(e), code="export_error")

                elif isinstance(msg, ClientRenameSession):
                    if not msg.session_id or not msg.new_name.strip():
                        await self._send(ws, "error", message="Missing session_id or new_name", code="invalid_request")  # noqa: E501
                        continue
                    ok = self._manager.rename_session(msg.session_id, msg.new_name.strip())
                    if ok:
                        await self._send(ws, "session_renamed", session_id=msg.session_id, new_name=msg.new_name.strip())  # noqa: E501
                    else:
                        await self._send(ws, "error", message="Session not found", code="not_found")

                elif isinstance(msg, ClientAgentList):
                    info = self._get_or_create_session()
                    agents = [a.to_dict() for a in info.agent.config.agents]
                    await self._send(ws, "agents_list", agents=agents, active_index=info.agent.config.active_agent_index)  # noqa: E501

                elif isinstance(msg, ClientAgentCreate):
                    info = self._get_or_create_session()
                    agent_data = dict(msg.agent)
                    agent = AgentConfig.from_dict(agent_data)
                    info.agent.config.agents.append(agent)
                    self._persist_config(info)
                    agents = [a.to_dict() for a in info.agent.config.agents]
                    await self._send(ws, "agents_updated", agents=agents, active_index=info.agent.config.active_agent_index)  # noqa: E501

                elif isinstance(msg, ClientAgentDelete):
                    info = self._get_or_create_session()
                    idx = msg.index
                    total_before = len(info.agent.config.agents)
                    logger.info("[agent_delete] index=%d, total_before=%d", idx, total_before)
                    if 0 <= idx < total_before:
                        deleted_name = info.agent.config.agents[idx].name
                        del info.agent.config.agents[idx]
                        logger.info("[agent_delete] deleted agent '%s' at index %d", deleted_name, idx)  # noqa: E501
                        if info.agent.config.active_agent_index >= len(info.agent.config.agents):
                            info.agent.config.active_agent_index = len(info.agent.config.agents) - 1
                            logger.info("[agent_delete] adjusted active_agent_index to %d", info.agent.config.active_agent_index)  # noqa: E501
                        self._persist_config(info)
                    else:
                        logger.warning("[agent_delete] invalid index %d (total=%d)", idx, total_before)  # noqa: E501
                    agents = [a.to_dict() for a in info.agent.config.agents]
                    await self._send(ws, "agents_updated", agents=agents, active_index=info.agent.config.active_agent_index)  # noqa: E501
                    logger.info("[agent_delete] done, remaining=%d", len(agents))

                elif isinstance(msg, ClientAgentUpdate):
                    info = self._get_or_create_session()
                    idx = msg.index
                    if 0 <= idx < len(info.agent.config.agents):
                        agent_data = dict(msg.agent)
                        updated = AgentConfig.from_dict(agent_data)
                        info.agent.config.agents[idx] = updated
                        self._persist_config(info)
                    agents = [a.to_dict() for a in info.agent.config.agents]
                    await self._send(ws, "agents_updated", agents=agents, active_index=info.agent.config.active_agent_index)  # noqa: E501

                elif isinstance(msg, ClientAgentSetActive):
                    info = self._get_or_create_session()
                    idx = msg.index
                    if -1 <= idx < len(info.agent.config.agents):
                        info.agent.config.active_agent_index = idx
                        self._persist_config(info)
                    agents = [a.to_dict() for a in info.agent.config.agents]
                    await self._send(ws, "agents_updated", agents=agents, active_index=info.agent.config.active_agent_index)  # noqa: E501

                elif isinstance(msg, ClientUpdateSubAgents):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    try:
                        logger.info("[update_sub_agents] updating, count=%d", len(msg.sub_agents))
                        sub_agents = [
                            SubAgentConfig.from_dict(s) if isinstance(s, dict) else s
                            for s in msg.sub_agents
                        ]
                        info.agent.config.sub_agents = sub_agents
                        self._persist_config(info)
                        sub_agents_dict = [
                            s.to_dict() if isinstance(s, SubAgentConfig) else s
                            for s in sub_agents if not getattr(s, "hidden", False)
                        ]
                        await self._send(ws, "sub_agents_updated", sub_agents=sub_agents_dict)
                        logger.info("[update_sub_agents] done")
                    except Exception as exc:
                        logger.error("[update_sub_agents] failed: %s\n%s", exc, traceback.format_exc())  # noqa: E501
                        await self._send(ws, "error", message=f"Sub agents update failed: {exc}", code="handler_error")  # noqa: E501

                elif isinstance(msg, ClientOpenWorkspace):
                    folder_path = os.path.abspath(os.path.expanduser(msg.path))
                    if not os.path.isdir(folder_path):
                        await self._send(ws, "error", message="Folder not found", code="invalid_path")  # noqa: E501
                        continue

                    _t_open = time.time()

                    # Create .encre directory in the project folder
                    yim_dir = os.path.join(folder_path, ".encre")
                    os.makedirs(yim_dir, exist_ok=True)

                    # Generate stable ID and create workspace data dir under ~/.dunimd/encre
                    ws_id = _make_workspace_id(folder_path)
                    _ensure_workspace_dirs(ws_id)

                    # Save to encrypted workspace records
                    workspaces = _load_workspaces()
                    existing = next((w for w in workspaces if w["path"] == folder_path), None)
                    if existing:
                        existing["opened_at"] = time.time()
                        existing["id"] = ws_id
                    else:
                        workspaces.append({
                            "id": ws_id,
                            "path": folder_path,
                            "name": os.path.basename(folder_path),
                            "opened_at": time.time(),
                        })
                    # Keep last 20
                    workspaces = workspaces[-20:]
                    _save_workspaces(workspaces)

                    # Change working directory
                    os.chdir(folder_path)

                    # Switch session storage to workspace context
                    await self._manager.set_workspace(ws_id)
                    self._info = None  # invalidate stale session ref after workspace switch
                    self._workspace_path = folder_path
                    self._current_ws_id = ws_id
                    # Start background index via IndexManager (survives WS disconnects)
                    if self._index_manager:
                        self._index_progress_callback = self._make_index_callback(ws)
                        self._index_manager.subscribe(ws_id, self._index_progress_callback)

                        # Register a callback that injects the built index into
                        # the running agent so the conversation never blocks on
                        # codebase queries.  The callback is re-registered for
                        # every workspace open to capture the latest session ref.
                        self._index_manager.set_on_index_ready(
                            lambda _ws_id, idx: self._inject_index_to_session(_ws_id, idx)
                        )

                        self._index_manager.start_index(ws_id, folder_path)

                    # Clone config to avoid mutating the shared _default_config
                    ws_config = replace(
                        self._default_config,
                        workspace=folder_path,
                    )
                    _apply_workspace_config(ws_config, folder_path)

                    #   If startup session mode is "resume", try to resume most recent workspace
                    # session
                    startup_mode = self._resolve_startup_mode()
                    if startup_mode == "resume":
                        existing = self._manager.try_resume_most_recent(config=ws_config)
                        if existing is not None:
                            info = existing
                        else:
                            info = self._manager.create_session(config=ws_config)
                    else:
                        info = self._manager.create_session(config=ws_config)

                    self._info = info
                    self._current_session_id = info.session_id
                    self._manager.touch(info.session_id)
                    info.metadata["workspace"] = folder_path
                    info.agent.session.metadata["workspace"] = folder_path
                    info.agent.session.metadata["channel"] = "iwork"
                    self._persist_config(info)

                    logger.info("[workspace] open_workspace session=%s setup=%.2fs",
                                info.session_id[:8], time.time() - _t_open)

                    # Get index state for immediate display in sidebar tree
                    idx_status = "idle"
                    idx_files = 0
                    if self._index_manager:
                        # Check if index is already cached (ready)
                        cached_status = self._index_manager.get_status(ws_id) if hasattr(self._index_manager, "get_status") else {}  # noqa: E501
                        if cached_status.get("status") == "ready":
                            idx_status = "ready"
                            idx_files = cached_status.get("files", 0)
                        else:
                            task = self._index_manager.get_task(ws_id) if hasattr(self._index_manager, "get_task") else None  # noqa: E501
                            if task is not None and not task.done():
                                idx_status = "indexing"
                    await self._send(ws, "workspace_opened",
                        path=folder_path, name=os.path.basename(folder_path),
                        id=ws_id, workspaces=workspaces,
                        index_status=idx_status, index_files=idx_files)

                    sess = info.agent.session
                    sess.rebuild_artifacts_from_messages()
                    context = sess.get_context_messages()
                    msgs = [m for m in context if m.get("role") != "system"]
                    branches_list = [b.__dict__ for b in sess.branches.values()]
                    await self._send(ws, "session_ready", session_id=info.session_id, messages=msgs,
                                     plan_items=sess.plan_items, artifacts=sess.artifacts, references=sess.references,  # noqa: E501
                                     branches=branches_list, active_branch_id=sess.active_branch_id,
                                     request_id=msg.request_id)
                    _t1 = time.time()
                    logger.info("[workspace] open_workspace done session=%s total=%.2fs",
                                info.session_id[:8], _t1 - _t_open)

                elif isinstance(msg, ClientListWorkspaces):
                    workspaces = _load_workspaces()
                    await self._send(ws, "workspaces_list", workspaces=workspaces)

                elif isinstance(msg, ClientRemoveWorkspace):
                    workspaces = _load_workspaces()
                    removed_ws = None
                    for w in workspaces:
                        if w["path"] == msg.path:
                            removed_ws = w
                            break
                    workspaces = [w for w in workspaces if w["path"] != msg.path]
                    _save_workspaces(workspaces)
                    # Clean up workspace session data on disk
                    if removed_ws and removed_ws.get("id"):
                        ws_id = removed_ws["id"]
                    else:
                        ws_id = _make_workspace_id(msg.path)
                    ws_dir = _get_workspace_dir(ws_id)
                    if os.path.isdir(ws_dir):
                        shutil.rmtree(ws_dir, ignore_errors=True)
                    await self._send(ws, "workspace_removed", path=msg.path, workspaces=workspaces)

                elif isinstance(msg, ClientCloseWorkspace):
                    # Unsubscribe from index progress but do NOT cancel -- indexing
                    # continues in the background service even without a WS connection.
                    if self._index_manager and self._current_ws_id and self._index_progress_callback:  # noqa: E501
                        self._index_manager.unsubscribe(self._current_ws_id, self._index_progress_callback)  # noqa: E501
                        self._index_progress_callback = None
                        self._current_ws_id = ""
                    # Switch back to global session storage
                    await self._manager.set_workspace(None)
                    self._info = None  # invalidate stale session ref after workspace switch
                    self._workspace_path = ""
                    self._default_config = replace(self._default_config, workspace="")
                    # Reset working directory
                    os.chdir(os.path.join(os.path.expanduser("~"), ".dunimd", "encre"))
                    clean_config = replace(self._default_config, workspace="")
                    # Try to resume most recent normal mode session if startup mode is "resume"
                    startup_mode = self._resolve_startup_mode()
                    if startup_mode == "resume":
                        existing = self._manager.try_resume_most_recent(config=clean_config)
                        if existing is not None:
                            info = existing
                        else:
                            info = self._manager.create_session(config=clean_config)
                    else:
                        info = self._manager.create_session(config=clean_config)
                    self._info = info
                    self._current_session_id = info.session_id
                    self._manager.touch(info.session_id)
                    self._persist_config(info)
                    await self._send(ws, "workspace_closed")
                    sess = info.agent.session
                    sess.rebuild_artifacts_from_messages()
                    context = sess.get_context_messages()
                    msgs = [m for m in context if m.get("role") != "system"]
                    branches_list = [b.__dict__ for b in sess.branches.values()]
                    await self._send(ws, "session_ready", session_id=info.session_id, messages=msgs,
                                     plan_items=sess.plan_items, artifacts=sess.artifacts, references=sess.references,  # noqa: E501
                                     branches=branches_list, active_branch_id=sess.active_branch_id,
                                     request_id=msg.request_id)

                elif isinstance(msg, ClientGetMemoryList):
                    from encre.config import get_data_dir
                    from encre.crypto import decrypt as _decrypt
                    mem_dir = get_data_dir() / "memory"
                    entries: list[dict[str, Any]] = []
                    if mem_dir.is_dir():
                        for fpath in sorted(mem_dir.glob("*.md"), key=lambda p:
                            p.stat().st_mtime, reverse=True):
                            try:
                                raw = fpath.read_text("utf-8")
                                # Decrypt memory files (all encrypted by default)
                                content = raw
                                if raw.strip() and not raw.strip().startswith("---") and not raw.strip().startswith("#"):  # noqa: E501
                                    with contextlib.suppress(Exception):
                                        content = _decrypt(raw)
                                meta = self._parse_memory_frontmatter(raw) if "---" in raw else None
                                if not meta:
                                    meta = self._parse_memory_frontmatter(content) if "---" in content else None  # noqa: E501
                                entry: dict[str, Any] = {
                                    "name": fpath.stem,
                                    "path": str(fpath.relative_to(mem_dir)),
                                    "size": fpath.stat().st_size,
                                    "modified": fpath.stat().st_mtime,
                                    "preview": content[:200].replace("\n", " ").strip(),
                                }
                                if meta:
                                    entry["title"] = meta.get("title", "")
                                    entry["tags"] = list(meta.get("tags", [])) if isinstance(meta.get("tags"), (list, tuple)) else []  # noqa: E501
                                    entry["type"] = str(meta.get("type", ""))
                                entries.append(entry)
                            except Exception:
                                continue
                    await self._send(ws, "memory_list", entries=entries)

                elif isinstance(msg, ClientGetMemoryDetail):
                    from encre.config import get_data_dir
                    mem_dir = get_data_dir() / "memory"
                    file_path = mem_dir / msg.path
                    file_path = file_path.resolve()
                    if not str(file_path).startswith(str(mem_dir.resolve())) or not file_path.is_file():  # noqa: E501
                        await self._send(ws, "memory_detail", path=msg.path, content="", error="File not found or access denied")  # noqa: E501
                    else:
                        try:
                            raw = file_path.read_text("utf-8")
                            content = raw
                            from encre.crypto import decrypt
                            if not raw.startswith("---"):
                                with contextlib.suppress(Exception):
                                    content = decrypt(raw)
                        except Exception:
                            content = ""
                        await self._send(ws, "memory_detail", path=msg.path, content=content)

                elif isinstance(msg, ClientListGlobalRules):
                    from encre.config import get_data_dir
                    rules_dir = get_data_dir() / "rules"
                    rules_list: list[dict[str, Any]] = []
                    if rules_dir.is_dir():
                        for fpath in sorted(rules_dir.glob("*.md"), key=lambda p:
                            p.stat().st_mtime, reverse=True):
                            try:
                                rules_list.append({
                                    "name": fpath.stem,
                                    "path": str(fpath.relative_to(rules_dir)),
                                    "size": fpath.stat().st_size,
                                    "modified": fpath.stat().st_mtime,
                                })
                            except Exception:
                                continue
                    await self._send(ws, "global_rules_list", rules=rules_list)

                elif isinstance(msg, ClientListProjectRules):
                    ws_path = self._workspace_path or self._default_config.workspace if self._default_config else ""  # noqa: E501
                    rules_list: list[dict[str, Any]] = []
                    if ws_path and os.path.isdir(ws_path):
                        for rel_path, priority, name in [
                            (".encre/rules.md", 100, "encre"),
                            (".cursorrules", 90, "cursor"),
                            (".windsurfrules", 85, "windsurf"),
                            (".clinerules", 80, "cline"),
                            ("CLAUDE.md", 75, "claude"),
                            (".github/copilot-instructions.md", 60, "copilot"),
                        ]:
                            full_path = os.path.join(ws_path, rel_path)
                            if os.path.isfile(full_path):
                                try:
                                    st = os.stat(full_path)
                                    rules_list.append({
                                        "name": name,
                                        "path": rel_path,
                                        "priority": priority,
                                        "modified": st.st_mtime,
                                    })
                                except Exception:
                                    continue
                        # Codex instructions: AGENTS.md chain, .codex/config.toml
                        # developer_instructions, and model_instructions_file.
                        try:
                            from encre.codex_compat import build_codex_context
                            ctx = build_codex_context(ws_path)
                            seen_codex: set[str] = set()
                            for path, _ in ctx.instructions:
                                if path in seen_codex:
                                    continue
                                seen_codex.add(path)
                                rel = path
                                if rel.startswith(ws_path + os.sep):
                                    rel = rel[len(ws_path) + len(os.sep):]
                                try:
                                    mtime = os.path.getmtime(path)
                                except OSError:
                                    mtime = 0.0
                                rules_list.append({
                                    "name": "codex",
                                    "path": rel,
                                    "priority": 65,
                                    "modified": mtime,
                                })
                        except Exception:
                            pass
                        rules_list.sort(key=lambda r: -r["priority"])
                    await self._send(ws, "project_rules_list", rules=rules_list)

                elif isinstance(msg, ClientListProjectHooks):
                    from encre.hooks import EncreHookSystem
                    info = self._info
                    hook_system: EncreHookSystem | None = (
                        getattr(getattr(info, "agent", None), "hook_system", None)
                    )
                    hooks_list: list[dict[str, Any]] = []
                    if hook_system is not None:
                        for h in hook_system.list_handlers():
                            hooks_list.append({
                                "handler_id": h.get("handler_id", ""),
                                "event_type": h.get("event_type", ""),
                                "source_path": h.get("source_path", ""),
                                "matcher": h.get("matcher", ""),
                                "command": h.get("command", ""),
                                "hook_type": h.get("hook_type", "command"),
                                "timeout_ms": int(h.get("timeout_ms", 0) or 0),
                            })
                    await self._send(ws, "project_hooks_list", hooks=hooks_list)

                elif isinstance(msg, ClientSaveGlobalRule):
                    from encre.config import get_data_dir
                    rules_dir = get_data_dir() / "rules"
                    rules_dir.mkdir(parents=True, exist_ok=True)
                    rule_path = rules_dir / f"{msg.name}.md"
                    try:
                        rule_path.write_text(msg.content, encoding="utf-8")
                        await self._send(ws, "global_rule_saved", name=msg.name)
                        # Immediately push the full list so frontend doesn't need to request it
                        rules_list: list[dict[str, Any]] = []
                        if rules_dir.is_dir():
                            for fpath in sorted(rules_dir.glob("*.md"), key=lambda p:
                                p.stat().st_mtime, reverse=True):
                                try:
                                    rules_list.append({
                                        "name": fpath.stem,
                                        "path": str(fpath.relative_to(rules_dir)),
                                        "size": fpath.stat().st_size,
                                        "modified": fpath.stat().st_mtime,
                                    })
                                except Exception:
                                    continue
                        await self._send(ws, "global_rules_list", rules=rules_list)
                    except Exception as e:
                        await self._send(ws, "error", message=f"Failed to save global rule: {e}")

                elif isinstance(msg, ClientDeleteGlobalRule):
                    from encre.config import get_data_dir
                    rules_dir = get_data_dir() / "rules"
                    rule_path = rules_dir / f"{msg.name}.md"
                    try:
                        if rule_path.is_file():
                            rule_path.unlink()
                        await self._send(ws, "global_rule_deleted", name=msg.name)
                    except Exception as e:
                        await self._send(ws, "error", message=f"Failed to delete global rule: {e}")

                elif isinstance(msg, ClientGetGlobalRuleContent):
                    from encre.config import get_data_dir
                    rules_dir = get_data_dir() / "rules"
                    rule_path = (rules_dir / f"{msg.name}.md").resolve()
                    if not str(rule_path).startswith(str(rules_dir.resolve())) or not rule_path.is_file():  # noqa: E501
                        await self._send(ws, "global_rule_content", name=msg.name, content="", error="File not found")  # noqa: E501
                    else:
                        try:
                            content = rule_path.read_text("utf-8")
                            await self._send(ws, "global_rule_content", name=msg.name, content=content)  # noqa: E501
                        except Exception as e:
                            await self._send(ws, "global_rule_content", name=msg.name, content="", error=str(e))  # noqa: E501

                elif isinstance(msg, ClientGetProfile):
                    from encre.config import get_data_dir
                    from encre.profile.system import EncreProfileSystem
                    mem_dir = str(get_data_dir() / "memory")
                    ps = EncreProfileSystem(mem_dir)
                    ps.load()
                    data = ps.get_data()
                    await self._send(ws, "profile_data", profile=data)

                elif isinstance(msg, ClientReindexWorkspace):
                    if not self._workspace_path or not self._index_manager:
                        await self._send(ws, "index_status", files=0, status="no_workspace")
                    else:
                        try:
                            logger.info("[index] reindex_workspace ws=%s path=%s",
                                        self._current_ws_id[:8], self._workspace_path)
                            # Subscribe for progress updates during reindex
                            if self._index_progress_callback:
                                self._index_manager.unsubscribe(self._current_ws_id, self._index_progress_callback)  # noqa: E501
                            self._index_progress_callback = self._make_index_callback(ws)
                            self._index_manager.subscribe(self._current_ws_id, self._index_progress_callback)  # noqa: E501
                            self._index_manager.reindex(self._current_ws_id, self._workspace_path)
                            asyncio.get_running_loop().call_soon(
                                lambda: logger.info("[index] reindex triggered")
                            )
                        except Exception as e:
                            logger.error("[index] reindex failed: %s", e, exc_info=True)
                            await self._send(ws, "index_status", files=0, status=f"error: {e}")

                elif isinstance(msg, dict) and msg.get("type") == "delete_index":
                    if self._current_ws_id and self._workspace_path and self._index_manager:
                        self._index_manager.delete_index(self._current_ws_id, self._workspace_path)
                        await self._send(ws, "index_status", files=0, status="idle")
                        logger.info("[index] deleted index ws=%s", self._current_ws_id[:8])

                elif isinstance(msg, ClientGetGitignore):
                    if not self._workspace_path:
                        await self._send(ws, "gitignore_content", path="", content="")
                    else:
                        yim_dir = os.path.join(self._workspace_path, ".encre")
                        gitignore_path = os.path.join(yim_dir, ".gitignore")
                        os.makedirs(yim_dir, exist_ok=True)
                        if os.path.isfile(gitignore_path):
                            try:
                                with open(gitignore_path, encoding="utf-8", errors="replace") as f:
                                    content = f.read()
                                await self._send(ws, "gitignore_content", path=gitignore_path, content=content)  # noqa: E501
                            except Exception as e:
                                await self._send(ws, "gitignore_content", path=gitignore_path, content=f"# Error reading .gitignore: {e}")  # noqa: E501
                        else:
                            await self._send(ws, "gitignore_content", path=gitignore_path, content="")  # noqa: E501

                elif isinstance(msg, ClientSetGitignore):
                    if self._workspace_path:
                        yim_dir = os.path.join(self._workspace_path, ".encre")
                        gitignore_path = os.path.join(yim_dir, ".gitignore")
                        os.makedirs(yim_dir, exist_ok=True)
                        try:
                            with open(gitignore_path, "w", encoding="utf-8") as f:
                                f.write(msg.content)
                            await self._send(ws, "gitignore_content", path=gitignore_path, content=msg.content)  # noqa: E501
                        except Exception as e:
                            await self._send(ws, "error", message=f"Failed to save .gitignore: {e}")

                elif isinstance(msg, ClientDeleteIndex):
                    if not self._workspace_path or not self._index_manager:
                        await self._send(ws, "index_status", files=0, status="no_workspace")
                    else:
                        try:
                            self._index_manager.delete_index(self._current_ws_id, self._workspace_path)  # noqa: E501
                            await self._send(ws, "index_status", files=0, status="idle")
                        except Exception as e:
                            await self._send(ws, "index_status", files=0, status=f"error: {e}")

                elif isinstance(msg, ClientAddDocument):
                    from codebase.document_manager import EncreDocumentManager

                    from encre.config import get_data_dir
                    try:
                        mgr = EncreDocumentManager(str(get_data_dir()))
                        if msg.file_path:
                            doc = mgr.add_from_local(msg.name, msg.file_path)
                            await self._send(ws, "document_added", document=doc.to_dict())
                        elif msg.url:
                            doc = mgr.add_pending_url(msg.name, msg.url)
                            await self._send(ws, "document_added", document=doc.to_dict())
                            asyncio.ensure_future(self._crawl_and_update(ws, mgr, doc, msg.url))
                        else:
                            await self._send(ws, "document_error", message="Either file_path or url is required")  # noqa: E501
                    except Exception as e:
                        await self._send(ws, "document_error", message=str(e))

                elif isinstance(msg, ClientRemoveDocument):
                    from codebase.document_manager import EncreDocumentManager

                    from encre.config import get_data_dir
                    try:
                        mgr = EncreDocumentManager(str(get_data_dir()))
                        removed = mgr.remove(msg.id)
                        if removed:
                            await self._send(ws, "document_removed", id=msg.id)
                        else:
                            await self._send(ws, "document_error", message="Document not found")
                    except Exception as e:
                        await self._send(ws, "document_error", message=str(e))

                elif isinstance(msg, ClientListDocuments):
                    from codebase.document_manager import EncreDocumentManager

                    from encre.config import get_data_dir
                    try:
                        mgr = EncreDocumentManager(str(get_data_dir()))
                        docs = mgr.list_all()
                        await self._send(ws, "documents_list", documents=docs)
                    except Exception as e:
                        await self._send(ws, "document_error", message=str(e))

                elif isinstance(msg, ClientResume):
                    # Use workspace config if currently in workspace mode
                    if self._workspace_path and os.path.isdir(self._workspace_path):
                        resume_config = replace(self._default_config, workspace=self._workspace_path)  # noqa: E501
                        _apply_workspace_config(resume_config, self._workspace_path)
                    else:
                        resume_config = replace(self._default_config, workspace="")
                    if msg.session_id:
                        session = self._manager.load_or_create_session(
                            msg.session_id, config=resume_config)
                        self._info = session
                    else:
                        session = self._get_or_create_session()
                    self._current_session_id = session.session_id
                    # Tag the resumed session with the correct channel for the current mode
                    session.agent.session.metadata["channel"] = "iwork" if self._workspace_path else "normal"  # noqa: E501
                    # Reconcile is_running from the actual task state -- if the
                    # task is still alive, the session is definitely running even
                    # if the finally block has not fired yet.
                    if session.agent_task is not None and not session.agent_task.done():
                        session.is_running = True
                    sess = session.agent.session
                    sess.rebuild_artifacts_from_messages()
                    context = sess.get_context_messages()
                    msgs = [m for m in context if m.get("role") != "system"]
                    branches_list = [b.__dict__ for b in sess.branches.values()]
                    await self._send(ws, "session_ready", session_id=session.session_id, messages=msgs,  # noqa: E501
                                     plan_items=sess.plan_items, artifacts=sess.artifacts, references=sess.references,  # noqa: E501
                                     branches=branches_list, active_branch_id=sess.active_branch_id,
                                     is_running=session.is_running, request_id=msg.request_id)

                elif isinstance(msg, ClientIclawResume):
                    logger.info("[iclaw] resume requested")
                    router = self._adapter_manager.router if self._adapter_manager else None
                    if router:
                        async with router.iclaw_context():
                            existing = router.session_manager.try_resume_most_recent(
                                config=replace(self._default_config, workspace=""))
                            if existing is not None:
                                ctx = existing.agent.session.get_context_messages()
                                msgs = [m for m in ctx if m.get("role") != "system"]
                                self._current_session_id = existing.session_id
                                await self._send(ws, "session_ready",
                                    session_id=existing.session_id, messages=msgs)
                                logger.info("[iclaw] resume sent session_ready with %d messages sid=%s",  # noqa: E501
                                            len(msgs), existing.session_id)
                            else:
                                logger.info("[iclaw] no session to resume")
                    else:
                        logger.warning("[iclaw] no router available for resume")

                elif isinstance(msg, ClientTerminalListShells):
                    is_windows = os.name == "nt"
                    shells = []
                    if is_windows:
                        shells.append({"name": "PowerShell", "path": "powershell.exe", "args": []})
                        shells.append({"name": "cmd", "path": "cmd.exe", "args": []})
                        if os.path.isfile("C:/Windows/System32/wsl.exe"):
                            shells.append({"name": "WSL", "path": "wsl.exe", "args": []})
                    else:
                        for sp in ["/bin/bash", "/bin/zsh", "/bin/sh"]:
                            if os.path.isfile(sp):
                                shells.append({"name": os.path.basename(sp), "path": sp, "args": []})  # noqa: E501
                    await self._send(ws, "terminal_shells", shells=shells)

                elif isinstance(msg, ClientTerminalSpawn):
                    shell = msg.shell or ("powershell.exe" if os.name == "nt" else "/bin/bash")
                    shell_args = msg.shell_args or []
                    try:
                        from encre.tools.builtin._suppress_window import (
                            hidden_subprocess_kwargs,
                        )
                        term_kwargs = hidden_subprocess_kwargs()
                        proc = await asyncio.create_subprocess_exec(
                            shell, *shell_args,
                            stdin=asyncio.subprocess.PIPE,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.STDOUT,
                            **term_kwargs,
                        )
                    except Exception as e:
                        await self._send(ws, "error", message=f"Terminal spawn failed: {e}", code="terminal_error")  # noqa: E501
                        continue
                    tid = self._term_seq
                    self._term_seq += 1
                    term_info: dict[str, Any] = {"proc": proc, "buf": b""}
                    self._term_sessions[tid] = term_info
                    await self._send(ws, "terminal_spawned", id=tid)

                    async def _read_stdout():
                        try:
                            while True:
                                data = await proc.stdout.read(4096)
                                if not data:
                                    break
                                term_info["buf"] += data
                                try:
                                    decoded = data.decode("utf-8", errors="replace")
                                except Exception:
                                    decoded = data.decode("latin-1", errors="replace")
                                await self._send(ws, "terminal_data", id=tid, data=decoded)
                        except Exception:
                            pass
                        finally:
                            self._term_sessions.pop(tid, None)
                            await self._send(ws, "terminal_data", id=tid, data="")

                    asyncio.ensure_future(_read_stdout())

                elif isinstance(msg, ClientTerminalWrite):
                    tinfo = self._term_sessions.get(msg.id)
                    if tinfo is None:
                        await self._send(ws, "error", message="Terminal not found", code="terminal_not_found")  # noqa: E501
                        continue
                    proc = tinfo["proc"]
                    if proc.stdin and not proc.stdin.is_closed():
                        try:
                            proc.stdin.write(msg.data.encode("utf-8", errors="replace"))
                            await proc.stdin.drain()
                        except Exception:
                            pass

                elif isinstance(msg, ClientTerminalResize):
                    pass

                elif isinstance(msg, ClientTerminalKill):
                    tinfo = self._term_sessions.get(msg.id)
                    if tinfo is None:
                        continue
                    proc = tinfo["proc"]
                    if proc.returncode is None:
                        try:
                            proc.terminate()
                            try:
                                await asyncio.wait_for(proc.wait(), timeout=3)
                            except TimeoutError:
                                proc.kill()
                                await proc.wait()
                        except Exception:
                            pass
                    self._term_sessions.pop(msg.id, None)

                elif isinstance(msg, ClientRetry):
                    sid = msg.session_id or self._current_session_id
                    if not sid:
                        await self._send(ws, "error", message="No active session", code="no_session")  # noqa: E501
                        continue
                    info = self._manager.get_session(sid)
                    if info is None:
                        info = self._manager.load_or_create_session(sid, config=self._default_config)  # noqa: E501
                    self._manager.touch(sid)
                    sess = info.agent.session
                    try:
                        user_msg, _new_branch = sess.retry_at_user_index(msg.user_message_index)
                    except ValueError as e:
                        await self._send(ws, "error", message=str(e), code="retry_error",
                                         session_id=sid)
                        continue
                    # Notify frontend about the new branch so the branch switcher updates.
                    branches_list = [b.__dict__ for b in sess.branches.values()]
                    await self._send(ws, "branch_updated",
                        session_id=sid,
                        active_branch_id=sess.active_branch_id,
                        branches=branches_list)
                    if user_msg:
                        mode = getattr(msg, "mode", "normal")
                        if mode == "detailed":
                            user_msg += "\n\n(Please provide a more detailed response with thorough explanations and comprehensive coverage.)"  # noqa: E501
                        elif mode == "concise":
                            user_msg += "\n\n(Please provide a concise response, keeping it brief and to the point.)"  # noqa: E501
                        self._current_session_id = sid
                        self._info = info
                        info.is_running = True
                        acquired = await self._manager.acquire_slot()
                        if not acquired:
                            await self._send(ws, "error",
                                message="Server at capacity, try later", code="capacity",
                                session_id=sid)
                            info.is_running = False
                            continue

                        async def _run_retry(session_id: str, prompt: str):
                            try:
                                async for event in info.agent.run(prompt=prompt):
                                    await self._dispatch_event(ws, info, event)
                                    if isinstance(event, (ToolResult, AssistantBoundary)):
                                        with contextlib.suppress(Exception):
                                            await self._manager._save_session_async(info)
                            except asyncio.CancelledError:
                                await self._send(ws, "finish", reason="cancelled", session_id=session_id)  # noqa: E501
                            except Exception as e:
                                logger.error(f"Retry run failed: {e}\n{traceback.format_exc()}")
                                with contextlib.suppress(Exception):
                                    await self._send(ws, "error", message=str(e), code="execution_error", session_id=session_id)  # noqa: E501
                                with contextlib.suppress(Exception):
                                    await self._send(ws, "finish", reason="error", session_id=session_id)  # noqa: E501
                            finally:
                                if info.agent_task is asyncio.current_task():
                                    info.is_running = False
                                    self._manager.release_slot()
                                    await self._manager._save_session_async(info)
                                    info.agent_task = None

                        # Ensure previous task is done before starting retry
                        if info.agent_task and not info.agent_task.done():
                            info.agent.loop.cancel()
                            with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                                await asyncio.wait_for(info.agent_task, timeout=0.5)
                        info.agent_task = asyncio.create_task(_run_retry(sid, user_msg))
                    else:
                        await self._send(ws, "error", message="Original user message not found", code="retry_error",
                                         session_id=sid)  # noqa: E501

                elif isinstance(msg, ClientSwitchBranch):
                    sid = msg.session_id or self._current_session_id
                    if not sid:
                        await self._send(ws, "error", message="No active session", code="no_session")  # noqa: E501
                        continue
                    info = self._manager.get_session(sid)
                    if info is None:
                        info = self._manager.load_or_create_session(sid, config=self._default_config)  # noqa: E501
                    self._manager.touch(sid)
                    sess = info.agent.session
                    if msg.branch_id not in sess.branches:
                        await self._send(ws, "error", message=f"Branch not found: {msg.branch_id}", code="branch_not_found",
                                         session_id=sid)  # noqa: E501
                        continue
                    sess.switch_branch(msg.branch_id)
                    context_msgs = sess.get_context_messages()
                    msgs = [m for m in context_msgs if m.get("role") != "system"]
                    branches_list = [b.__dict__ for b in sess.branches.values()]
                    await self._send(ws, "branch_switched",
                        session_id=sid,
                        branch_id=sess.active_branch_id,
                        messages=msgs,
                        branches=branches_list,
                        artifacts=sess.artifacts,
                        references=sess.references,
                        tokens={"input": 0, "output": 0, "total": 0},
                    )

                elif isinstance(msg, ClientRollbackBranch):
                    sid = msg.session_id or self._current_session_id
                    if not sid:
                        await self._send(ws, "error", message="No active session", code="no_session")  # noqa: E501
                        continue
                    info = self._manager.get_session(sid)
                    if info is None:
                        info = self._manager.load_or_create_session(sid, config=self._default_config)  # noqa: E501
                    self._manager.touch(sid)
                    self._info = info
                    self._current_session_id = sid
                    sess = info.agent.session
                    removed = sess.rollback_to(msg.branch_id, msg.message_id)
                    # rollback_to keeps the target message but the frontend
                    # removes it locally (its content goes into the input box
                    # for re-editing).  Remove it here too so that a page
                    # refresh does NOT resurrect the rolled-back message.
                    sess.messages = [
                        m for m in sess.messages
                        if not (
                            m.get("branch_id") == msg.branch_id
                            and (
                                m.get("id", "").endswith(":M:" + msg.message_id)
                                or m.get("id") == msg.message_id
                            )
                        )
                    ]
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(self._manager._save_session_async(info))
                    except Exception:
                        pass
                    context_msgs = sess.get_context_messages()
                    msgs = [m for m in context_msgs if m.get("role") != "system"]
                    branches_list = [b.__dict__ for b in sess.branches.values()]
                    await self._send(ws, "branch_switched",
                        session_id=sid,
                        branch_id=sess.active_branch_id,
                        messages=msgs,
                        branches=branches_list,
                        artifacts=sess.artifacts,
                        references=sess.references,
                        tokens={"input": 0, "output": 0, "total": 0},
                    )

                # ── Automation / scheduled tasks ─────────────────────────────────

                elif isinstance(msg, ClientAutomationListJobs):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    if self._scheduler is None:
                        await self._send(ws, "automation_jobs_list", jobs=[])
                        continue
                    jobs = self._scheduler.list_jobs()
                    job_list = []
                    for j in jobs:
                        job_list.append({
                            "id": j.id,
                            "name": j.name,
                            "prompt": j.prompt[:200],
                            "cron": j.cron.to_expression() if j.cron else "",
                            "schedule_type": j.schedule_type.name,
                            "state": j.state.name,
                            "suspended": j.suspended,
                            "created_at": j.created_at,
                            "last_fired": j.last_fired,
                            "last_result": j.last_result,
                            "fail_count": j.fail_count,
                            "max_failures": j.max_failures,
                            "tag": j.metadata.get("tag", ""),
                            "model_index": j.model_index,
                            "push_gateways": list(j.push_gateways),
                        })
                    await self._send(ws, "automation_jobs_list", jobs=job_list)

                elif isinstance(msg, ClientAutomationCreateJob):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    if self._scheduler is None:
                        await self._send(ws, "error", message="Scheduler not available", code="no_scheduler")  # noqa: E501
                        continue
                    try:
                        agent_config = None
                        if self._default_config and 0 <= msg.model_index < len(self._default_config.models):  # noqa: E501
                            mc = self._default_config.models[msg.model_index]
                            agent_config = {
                                "backend_type": mc.backend_type,
                                "api_key": mc.api_key,
                                "base_url": mc.base_url,
                                "model_id": mc.model_id,
                                "max_tokens": mc.max_tokens,
                            }
                        # Store current workspace path so the automation
                        # agent runs in the correct workspace context.
                        if agent_config is not None and self._workspace_path:
                            agent_config["workspace"] = self._workspace_path
                        job_id = self._scheduler.schedule(
                            name=msg.name,
                            prompt=msg.prompt,
                            cron=msg.cron if msg.cron else "",
                            metadata={"tag": msg.tag} if msg.tag else {},
                            agent_config=agent_config,
                            model_index=msg.model_index,
                            push_gateways=list(msg.push_gateways),
                        )
                        await self._send(ws, "automation_job_created",
                            job_id=job_id, name=msg.name)
                    except Exception as e:
                        await self._send(ws, "error",
                            message=f"Failed to create job: {e}", code="create_job_error")

                elif isinstance(msg, ClientAutomationCancelJob):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    if self._scheduler is None:
                        await self._send(ws, "error", message="Scheduler not available", code="no_scheduler")  # noqa: E501
                        continue
                    ok = self._scheduler.cancel(msg.job_id)
                    if ok:
                        await self._send(ws, "automation_job_cancelled", job_id=msg.job_id)
                    else:
                        await self._send(ws, "error",
                            message="Job not found", code="job_not_found")

                elif isinstance(msg, ClientAutomationToggleJob):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    if self._scheduler is None:
                        await self._send(ws, "error", message="Scheduler not available", code="no_scheduler")  # noqa: E501
                        continue
                    running = self._scheduler.toggle_job(msg.job_id)
                    if running is not None:
                        await self._send(ws, "automation_job_toggled", job_id=msg.job_id, running=running)  # noqa: E501
                    else:
                        await self._send(ws, "error",
                            message="Job not found", code="job_not_found")

                elif isinstance(msg, ClientAutomationUpdateJob):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    if self._scheduler is None:
                        await self._send(ws, "error", message="Scheduler not available", code="no_scheduler")  # noqa: E501
                        continue
                    agent_config = None
                    if self._default_config and 0 <= msg.model_index < len(self._default_config.models):  # noqa: E501
                        mc = self._default_config.models[msg.model_index]
                        agent_config = {
                            "backend_type": mc.backend_type,
                            "api_key": mc.api_key,
                            "base_url": mc.base_url,
                            "model_id": mc.model_id,
                            "max_tokens": mc.max_tokens,
                        }
                    if agent_config is not None and self._workspace_path:
                        agent_config["workspace"] = self._workspace_path
                    ok = self._scheduler.update_job(
                        msg.job_id,
                        name=msg.name,
                        prompt=msg.prompt,
                        cron=msg.cron,
                        tag=msg.tag,
                        model_index=msg.model_index,
                        agent_config=agent_config,
                        push_gateways=list(msg.push_gateways),
                    )
                    if ok:
                        await self._send(ws, "automation_job_updated", job_id=msg.job_id)
                    else:
                        await self._send(ws, "error",
                            message="Job not found", code="job_not_found")

                elif isinstance(msg, ClientAutomationDeleteJob):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    if self._scheduler is None:
                        await self._send(ws, "error", message="Scheduler not available", code="no_scheduler")  # noqa: E501
                        continue
                    ok = self._scheduler.delete_job(msg.job_id)
                    if ok:
                        await self._send(ws, "automation_job_deleted", job_id=msg.job_id)
                    else:
                        await self._send(ws, "error",
                            message="Job not found", code="job_not_found")


                elif isinstance(msg, ClientAutomationGetHistory):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    if self._scheduler is None:
                        await self._send(ws, "automation_job_history", history=[])
                        continue
                    jobs = self._scheduler.list_jobs()
                    history = []
                    for j in jobs:
                        for exec_entry in j.executions:
                            entry: dict[str, Any] = {
                                "id": f"{j.id}_{exec_entry.time}",
                                "job_id": j.id,
                                "name": j.name,
                                "tag": j.metadata.get("tag", ""),
                                "time": exec_entry.time,
                                "state": exec_entry.state,
                                "last_result": exec_entry.result[:500] if exec_entry.result else "",
                                "fail_count": exec_entry.fail_count,
                            }
                            if exec_entry.session_id:
                                entry["session_id"] = exec_entry.session_id
                                # The sub-agent session is the canonical
                                # source of truth. Load its messages so
                                # the frontend history view can show the
                                # full transcript without re-running the
                                # job.
                                messages = self._load_sub_agent_messages(exec_entry.session_id)
                                if messages:
                                    entry["messages"] = messages
                            history.append(entry)
                    history.sort(key=lambda h: h["time"], reverse=True)
                    await self._send(ws, "automation_job_history", history=history)

                elif isinstance(msg, ClientGetUsageStats):
                    try:
                        from encre.telemetry import EncreTelemetry
                        stats = EncreTelemetry.get_all_sessions_usage()
                        # Build model_id → display_name mapping from config
                        model_names: dict[str, str] = {}
                        if self._default_config:
                            for mc in self._default_config.models:
                                mid = mc.model_id or ""
                                if mid and mc.name:
                                    model_names[mid] = mc.name
                        # Apply display names & strip empty/unknown
                        if stats.get("sessions"):
                            cleaned: list[dict[str, Any]] = []
                            for s in stats["sessions"]:
                                raw = s.get("model", "") or ""
                                if not raw or raw == "unknown":
                                    continue  # skip sessions with no model
                                if raw in model_names:
                                    s["model"] = model_names[raw]
                                cleaned.append(s)
                            stats["sessions"] = cleaned
                        if stats.get("model_breakdown"):
                            mb = {}
                            for raw, data in stats["model_breakdown"].items():
                                if not raw or raw == "unknown":
                                    continue
                                key = model_names.get(raw, raw)
                                if key in mb:
                                    # merge if same display name from different ids
                                    for k in ("input_tokens", "output_tokens", "total_tokens", "turns"):
                                        mb[key][k] = mb[key].get(k, 0) + data.get(k, 0)
                                else:
                                    mb[key] = dict(data)
                            stats["model_breakdown"] = mb
                        await self._send(ws, "usage_stats", stats=stats)
                    except Exception:
                        await self._send(ws, "usage_stats", stats={
                            "total_sessions": 0, "total_tokens": 0,
                            "total_input_tokens": 0, "total_output_tokens": 0,
                            "total_tool_calls": 0,
                            "tool_call_breakdown": {},
                            "model_breakdown": {},
                            "sessions": [],
                        })

        except (ConnectionResetError, OSError) as _conn_err:
            logger.debug("[ws] connection reset: %s", _conn_err)
        except websockets.exceptions.ConnectionClosed:
            logger.debug("[ws] connection closed")
        finally:
            if self._iclaw_task and not self._iclaw_task.done():
                self._iclaw_task.cancel()
            self._connections = [c for c in self._connections if c is not ws]

    def _list_all_sessions(self, channel_filter: str | None = None) -> list[dict[str, Any]]:
        """List sessions -- combines in‑memory sessions with on‑disk index.

        When ``channel_filter`` is None, the workspace-channel filter applies
        automatically (``iwork`` in workspace mode, ``normal`` otherwise).
        Pass an explicit channel string to override (used by the tray popup to
        fetch both groups at once).
        """
        result = self._manager.list_sessions()
        index_entries = self._manager.query_index()
        active_ids = {s["session_id"] for s in result}

        # Include sessions managed by the EventRouter (iClaw desktop + QQ/Telegram etc. adapters)
        if self._adapter_manager and self._adapter_manager.router:
            router = self._adapter_manager.router
            for s in router.session_manager.list_sessions():
                if s["session_id"] not in active_ids:
                    result.append(s)
                    active_ids.add(s["session_id"])
            for entry in router.session_manager.query_index():
                if entry["session_id"] not in active_ids:
                    result.append(entry)
                    active_ids.add(entry["session_id"])

        # include workspace sessions from ALL workspace directories
        if channel_filter is None or channel_filter == "iwork":
            workspaces = _load_workspaces()
            for ws in workspaces:
                ws_id = ws.get("id") or _make_workspace_id(ws["path"])
                ws_dir = _get_workspace_dir(ws_id)
                sess_dir = os.path.join(ws_dir, "sessions")
                idx_file = os.path.join(sess_dir, "index.json")
                if not os.path.isfile(idx_file):
                    continue
                try:
                    raw = open(idx_file, encoding="utf-8").read().strip()
                    if raw and not raw.startswith("{"):
                        from encre.crypto import decrypt as _decrypt
                        with contextlib.suppress(Exception):
                            raw = _decrypt(raw)
                    ws_index = json.loads(raw)
                    if not isinstance(ws_index, dict):
                        continue
                except Exception:
                    continue
                for sid, entry in ws_index.items():
                    if sid in active_ids:
                        continue
                    ech = entry.get("channel", "iwork") or "iwork"
                    if ech in ("automation", "sub_agent"):
                        continue
                    active_ids.add(sid)
                    ws_path = ws.get("path", "")
                    # Use meta.json's last_message_at (the canonical "when was
                    # the last conversation") instead of the index entry so
                    # clicking a session in the sidebar never resets the
                    # displayed time.
                    from encre.session import EncreSession as _EncreSession
                    fallback_active = entry.get("last_active", 0)
                    last_active = _EncreSession.read_meta_last_active(
                        os.path.join(sess_dir, sid),
                        fallback_active,
                    )
                    result.append({
                        "session_id": sid,
                        "created_at": entry.get("created_at", 0),
                        "last_active": last_active,
                        "is_running": self._manager.is_session_running(sid),
                        "metadata": {"workspace": ws_path, "workspace_path": ws_path},
                        "preview": entry.get("preview", ""),
                        "name": entry.get("name", ""),
                        "channel": ech,
                        "message_count": entry.get("message_count", 0),
                    })

        # When in workspace mode, normal sessions live in the GLOBAL session
        # directory (not the workspace one).  We must read it directly since
        # self._manager only points to the workspace directory.
        if self._workspace_path:
            global_idx = os.path.join(_get_yim_data_dir(), "sessions", "index.json")
            if os.path.isfile(global_idx):
                try:
                    raw = open(global_idx, encoding="utf-8").read().strip()
                    if raw and not raw.startswith("{"):
                        from encre.crypto import decrypt as _decrypt
                        with contextlib.suppress(Exception):
                            raw = _decrypt(raw)
                    g_index = json.loads(raw)
                    if isinstance(g_index, dict):
                        global_sess_dir = os.path.join(_get_yim_data_dir(), "sessions")
                        for sid, entry in g_index.items():
                            if sid in active_ids:
                                continue
                            ech = entry.get("channel", "normal") or "normal"
                            if ech in ("automation", "sub_agent"):
                                continue
                            active_ids.add(sid)
                            # Same reasoning as the workspace branch above:
                            # always read the canonical last_message_at from
                            # meta.json so clicking a sidebar entry cannot
                            # rewrite the timestamp to "now".
                            from encre.session import EncreSession as _EncreSession
                            fallback_active = entry.get("last_active", 0)
                            last_active = _EncreSession.read_meta_last_active(
                                os.path.join(global_sess_dir, sid),
                                fallback_active,
                            )
                            result.append({
                                "session_id": sid,
                                "created_at": entry.get("created_at", 0),
                                "last_active": last_active,
                                "is_running": self._manager.is_session_running(sid),
                                "metadata": {},
                                "preview": entry.get("preview", ""),
                                "name": entry.get("name", ""),
                                "channel": ech,
                                "message_count": entry.get("message_count", 0),
                            })
                except Exception:
                    pass

        result.sort(key=lambda s: s.get("last_active", s.get("created_at", 0)), reverse=True)
        result = [s for s in result if (s.get("message_count") or 0) > 0 and s.get("channel", "normal") not in ("automation", "sub_agent")]  # noqa: E501

        # ── Workspace-channel filter ───────────────────────────────────
        if channel_filter is None:
            expected_channel = "iwork" if self._workspace_path else "normal"
        else:
            expected_channel = channel_filter
        result = [s for s in result if s.get("channel", "normal") == expected_channel]

        # ── Exclude temp chats from the sidebar ───────────────────────
        result = [s for s in result if not s.get("temp_chat")]

        return result

    @staticmethod
    def _parse_memory_frontmatter(content: str) -> dict[str, Any] | None:
        import re
        pattern = r"^---\s*\n(.*?)\n---"
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            return None
        yaml_block = match.group(1)
        result: dict[str, Any] = {}
        current_key: str | None = None
        current_list: list[str] = []
        for line in yaml_block.split("\n"):
            stripped = line.rstrip()
            if not stripped or stripped.startswith("#"):
                continue
            list_match = re.match(r"^\s+-\s+(.+)$", stripped)
            if list_match and current_key:
                current_list.append(list_match.group(1).strip().strip("\"'"))
                continue
            if current_key is not None and current_list:
                result[current_key] = current_list
                current_list = []
                current_key = None
            kv_match = re.match(r"^(\w[\w_-]*)\s*:\s*(.*)$", stripped)
            if kv_match:
                key = kv_match.group(1)
                value = kv_match.group(2).strip()
                if not value:
                    current_key = key
                    current_list = []
                else:
                    val = value.strip("\"'")
                    result[key] = val
        if current_key is not None and current_list:
            result[current_key] = current_list
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
        from encre.session import EncreSession
        try:
            for entry in os.scandir(sessions_dir):
                if len(results) >= 80:
                    break
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                sid = entry.name
                preview = EncreSession.load_preview(entry.path) or ""
                turn_matches = EncreSession.search_turns(entry.path, q)
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
            excluded = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "target", ".encre", ".pytest_cache", ".mypy_cache", "__pypackages__"}  # noqa: E501
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
                        if ext in (".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".mp3", ".mp4", ".wav", ".zip", ".tar", ".gz", ".7z", ".exe", ".dll", ".so", ".dylib", ".wasm", ".bin", ".pyc", ".pyo"):  # noqa: E501
                            continue
                        with open(fpath, encoding="utf-8", errors="replace") as f:
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

    def _inject_index_to_session(self, ws_id: str, idx: Any) -> None:
        """Inject a fully-built code index into the current session's agent.

        Called by ``IndexManager._fire_index_ready`` (via the
        ``_on_index_ready`` callback registered in
        ``ClientOpenWorkspace``).  If the current session belongs to the
        same workspace the index was built for, the code index is injected
        into ``agent.loop`` so that future ``_build_codebase_context()``
        calls receive real data instead of an empty string.
        """
        if ws_id != self._current_ws_id:
            return
        if not self._info or not self._info.agent:
            return
        self._info.agent.loop.inject_code_index(idx)
        logger.info("[index] injected ready index into agent session=%s ws=%s",
                     self._info.session_id[:8], ws_id)

    def _cancel_current_task(self) -> None:
        """Cancel the running agent task for the current session (on disconnect)."""
        if self._iclaw_task and not self._iclaw_task.done():
            self._iclaw_task.cancel()
        if self._current_session_id:
            sess = self._manager.get_session(self._current_session_id)
            if sess and sess.agent_task and not sess.agent_task.done():
                sess.agent.loop.cancel()
                sess.agent_task.cancel()

    def broadcast_gateway_status(self, status: dict) -> None:
        """Called by AdapterManager when adapter status changes."""
        closed = []
        for ws in self._connections:
            try:
                asyncio.ensure_future(self._send(ws, "gateway_status", status=status))
            except Exception:
                closed.append(ws)
        for ws in closed:
            self._connections.remove(ws)

    def _load_sub_agent_messages(self, session_id: str) -> list[dict[str, Any]] | None:
        """Load messages from a sub-agent session directory.

        Sub-agent sessions created by :meth:`EncreLoop._run_sub_agent`
        are persisted under ``<data_dir>/sub_agents/<sid>/`` as a
        directory of turn files. This method reads them back in order
        and returns the flat message list for the automation history
        view.
        """
        if not session_id:
            return None
        try:
            from encre.config import EncreConfig, get_data_dir
            from encre.session import EncreSession
            sess_dir = get_data_dir() / "sub_agents" / session_id
            if not sess_dir.is_dir():
                return None
            cfg = EncreConfig()
            session = EncreSession.load_from_dir(str(sess_dir), config=cfg)
            return [dict(m) for m in session.messages]
        except Exception:
            logger.warning("[automation] failed to load sub-agent session %s", session_id, exc_info=True)  # noqa: E501
            return None

    def broadcast_automation_update(self, job: Any = None) -> None:
        """Notify all connected clients that an automation job state changed.

        The automation run is itself a sub-agent session under
        ``<data_dir>/sub_agents/<sid>/``; we do NOT spawn a parallel
        session in the regular session store anymore. The history
        payload still includes the lightweight ``JobExecution`` record
        plus a messages snapshot loaded from the sub-agent session
        directory so the frontend's "view result" feature keeps
        working.
        """
        closed: list[Any] = []

        # Build history list with session_ids and per-execution messages
        history: list[dict[str, Any]] = []
        if self._scheduler:
            for j in self._scheduler.list_jobs():
                for exec_entry in j.executions:
                    entry: dict[str, Any] = {
                        "id": f"{j.id}_{exec_entry.time}",
                        "job_id": j.id,
                        "name": j.name,
                        "tag": j.metadata.get("tag", ""),
                        "time": exec_entry.time,
                        "state": exec_entry.state,
                        "last_result": exec_entry.result[:500] if exec_entry.result else "",
                        "fail_count": exec_entry.fail_count,
                    }
                    if exec_entry.session_id:
                        entry["session_id"] = exec_entry.session_id
                        messages = self._load_sub_agent_messages(exec_entry.session_id)
                        if messages:
                            entry["messages"] = messages
                    history.append(entry)
            history.sort(key=lambda h: h["time"], reverse=True)

        # Result data for frontend display -- pull messages from the
        # sub-agent session, not from JobExecution.
        result_data: dict[str, Any] | None = None
        if job and job.last_result:
            messages: list[dict[str, Any]] | None = None
            if getattr(job, "session_id", None):
                messages = self._load_sub_agent_messages(job.session_id)
            result_data = {
                "action": "completed" if job.state.name == "COMPLETED" else "failed",
                "id": job.id,
                "name": job.name,
                "prompt": job.prompt,
                "result": job.last_result[:2000],
                "messages": messages,
            }
            if getattr(job, "session_id", None):
                result_data["session_id"] = job.session_id

        # ── Push result through configured gateways ─────────────────
        if job and job.last_result and hasattr(job, "push_gateways") and job.push_gateways and self._adapter_manager:  # noqa: E501
            push_text = f"🤖 {job.name}\n\n{job.last_result[:1500]}"
            for gw_id in job.push_gateways:
                try:
                    instances = getattr(self._adapter_manager, "_instances", {})
                    adapter = instances.get(gw_id)
                    if adapter is None:
                        logger.warning("[automation] push gateway %s not running", gw_id)
                        continue
                    # Use the adapter's auto-detected default push target (e.g. the
                    # most recently active chat).  No manual configuration needed.
                    push_chat_id = getattr(adapter, "default_push_chat_id", None)
                    logger.info("[automation] push gateway %s adapter=%s default_push=%s", gw_id, type(adapter).__name__, push_chat_id)  # noqa: E501
                    if not push_chat_id:
                        logger.warning("[automation] push gateway %s has no push target, skipping", gw_id)  # noqa: E501
                        continue
                    _ = asyncio.create_task(adapter.send(push_chat_id, push_text))  # noqa: RUF006
                    logger.info("[automation] pushed result to gateway %s (chat=%s)", gw_id, push_chat_id)  # noqa: E501
                except Exception as exc:
                    logger.warning("[automation] failed to push to gateway %s: %s", gw_id, exc)

        for ws in self._connections:
            try:
                asyncio.ensure_future(self._send(ws, "automation_job_update", history=history, result=result_data))  # noqa: E501
            except Exception:
                closed.append(ws)
        for ws in closed:
            self._connections.remove(ws)

    async def broadcast_automation_progress(self, job: Any = None, event_type: str = "", event_data: dict[str, Any] | None = None) -> None:  # noqa: E501
        """Broadcast a real-time streaming event from an automation job execution.

        Called (and awaited) by the scheduler's progress callback during
        ``agent.run()`` so that events are sent in order.  Sends
        ``automation_stream_event`` to all connected clients so the frontend
        can display the automation's execution process in real-time, matching
        the main chat's sub-agent streaming pattern.
        """
        if not event_data:
            event_data = {}
        closed: list[Any] = []
        for ws in self._connections:
            try:
                await self._send(ws, "automation_stream_event",
                    job_id=job.id if job else "",
                    event_type=event_type,
                    event_data=event_data,
                )
            except Exception:
                closed.append(ws)
        for ws in closed:
            self._connections.remove(ws)

    def _broadcast_sessions(self) -> None:
        """Broadcast updated session list to all connected desktop clients.

        Registered as a callback on SessionManager so it fires whenever
        a session is created, updated, or deleted -- including from adapter
        (QQ/Telegram) and iClaw flows.
        """
        if not self._connections:
            logger.info("[broadcast] skipping -- no connections")
            return
        sessions = self._list_all_sessions()
        logger.info("[broadcast] %d sessions to %d connection(s)",
                    len(sessions), len(self._connections))

        async def _try_send(ws_conn: Any, payload_sessions: list) -> None:
            """Send sessions_list to one connection without cascading to _cancel_current_task."""
            encrypt = self._client_encrypted if self._client_encrypted is not None else False
            try:
                payload = encode_server_message("sessions_list", encrypt=encrypt, sessions=payload_sessions)  # noqa: E501
                await ws_conn.send(payload)
            except Exception as exc:
                logger.warning("[broadcast] send failed (will remove connection): %s", exc)

        closed: list[Any] = []
        for ws in self._connections:
            try:
                asyncio.ensure_future(_try_send(ws, sessions))
            except Exception as exc:
                logger.warning("[broadcast] schedule send failed: %s", exc)
                closed.append(ws)
        for ws in closed:
            with contextlib.suppress(ValueError):
                self._connections.remove(ws)

    def _persist_config(self, info: Any) -> None:
        try:
            from encre.config import _get_config_path
            config_path = _get_config_path()
            config_to_save = replace(info.agent.config, workspace="")
            config_to_save.save(str(config_path))
            logger.info("[persist_config] saved to %s", config_path)
        except Exception as exc:
            logger.error("[persist_config] Failed to persist config: %s\n%s", exc, traceback.format_exc())  # noqa: E501

    @staticmethod
    def _persist_settings(info: Any) -> None:
        try:
            from encre.settings_manager import (
                _GENERAL_SETTINGS_KEYS,
                load_settings,
                save_settings,
            )
            cfg = info.agent.config
            # Merge: load existing settings, update general keys, keep everything else
            existing = load_settings()
            for key in _GENERAL_SETTINGS_KEYS:
                val = getattr(cfg, key, None)
                if val is not None and val != "":
                    existing[key] = str(val)
            # Also persist adapter configs from EncreConfig for auto-start on restart
            if cfg.adapter_configs:
                for adapter_id, fields in cfg.adapter_configs.items():
                    for fk, fv in fields.items():
                        existing[f"adapter_{adapter_id}_{fk}"] = fv
            logger.info("[persist_settings] saving keys: %s", list(existing.keys()))
            if existing:
                save_settings(existing)
                logger.info("[persist_settings] saved successfully")
        except Exception as exc:
            logger.warning("Failed to persist settings: %s", exc)

    @staticmethod
    def _persist_mcp_json(info: Any, servers: list[dict[str, Any]]) -> None:
        """Persist MCP servers to canonical encre mcp.json + ~/.claude/mcp.json."""
        try:
            mcp_data: dict[str, dict[str, Any]] = {}
            for srv in servers:
                name = srv.get("name", "")
                if not name:
                    continue
                entry: dict[str, Any] = {
                    "type": srv.get("type", "stdio"),
                }
                if srv.get("type") == "http":
                    if srv.get("url"):
                        entry["url"] = srv["url"]
                    if srv.get("timeout"):
                        entry["timeout"] = srv["timeout"]
                    if srv.get("headers"):
                        entry["headers"] = srv["headers"]
                else:
                    if srv.get("command"):
                        entry["command"] = srv["command"]
                    if srv.get("args"):
                        entry["args"] = srv["args"]
                if srv.get("cwd"):
                    entry["cwd"] = srv["cwd"]
                if srv.get("env"):
                    entry["env"] = srv["env"]
                if srv.get("disabled"):
                    entry["disabled"] = True
                mcp_data[name] = entry

            import json as _json

            payload: dict[str, Any] = {"mcpServers": mcp_data}

            # Canonical encre location (used by mcp_manager.py)
            from encre.tools.mcp_manager import default_mcp_config_path
            yim_path = default_mcp_config_path()
            os.makedirs(os.path.dirname(yim_path), exist_ok=True)
            with open(yim_path, "w", encoding="utf-8") as f:
                _json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.info("[persist_mcp_json] saved %d servers to %s", len(mcp_data), yim_path)

            # Claude Code compat location
            claude_dir = os.path.expanduser("~/.claude")
            os.makedirs(claude_dir, exist_ok=True)
            claude_path = os.path.join(claude_dir, "mcp.json")
            with open(claude_path, "w", encoding="utf-8") as f:
                _json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.info("[persist_mcp_json] saved %d servers to %s", len(mcp_data), claude_path)
        except Exception as exc:
            logger.warning("[persist_mcp_json] failed: %s", exc)

    @staticmethod
    def _load_mcp_servers(path: str) -> list[dict[str, Any]]:
        """Load MCP servers from a mcp.json file.

        Returns a list of server dicts compatible with EncreConfig.mcp_servers.
        """
        import json as _json
        try:
            if not os.path.exists(path):
                return []
            with open(path, encoding="utf-8") as f:
                data = _json.load(f)
            raw = data.get("mcpServers") or data
            if isinstance(raw, dict):
                servers = []
                for name, cfg in raw.items():
                    entry: dict[str, Any] = {"name": name, **cfg}
                    if "type" not in entry and "transport" in entry:
                        entry["type"] = entry.pop("transport")
                    if "type" not in entry:
                        entry["type"] = "stdio"
                    servers.append(entry)
                return servers
            if isinstance(raw, list):
                return raw
            return []
        except Exception:
            return []

    async def _crawl_and_update(self, ws: Any, mgr: Any, doc: Any, url: str) -> None:
        from codebase.document_manager import crawl_url_to_text
        try:
            loop = asyncio.get_event_loop()
            full_text = await loop.run_in_executor(None, crawl_url_to_text, doc.name, url)
            updated = mgr.finish_url_crawl(doc.id, full_text)
            if updated:
                await self._send(ws, "document_updated", document=updated.to_dict())
        except Exception as e:
            mgr._documents.pop(doc.id, None)
            mgr._save()
            await self._send(ws, "document_error", message=f"Crawl failed: {e}")

    def _make_index_callback(self, ws):
        """Return a progress callback for IndexManager that sends WS messages."""
        def callback(data: dict) -> None:
            try:
                status = data.get("status", "indexing")
                files = data.get("files", 0)
                progress = data.get("progress", 0)
                current_file = data.get("current_file", "")
                if status in ("indexing", "ready", "error") and progress >= 0:
                    logger.info("[index] progress: %d%% status=%s files=%d ws=%s",
                                progress, status, files,
                                self._current_ws_id[:8] if self._current_ws_id else "?")
                # Fire-and-forget the send coroutine (ignore connection errors)
                asyncio.ensure_future(
                    self._safe_send_index_status(ws, status, files, progress, current_file)
                )
            except Exception:
                pass
        return callback

    async def _safe_send_index_status(self, ws, status, files, progress, current_file):
        """Send index_status, ignoring any connection errors."""
        try:
            await self._send(ws, "index_status", files=files, status=status,
                             progress=progress, current_file=current_file,
                             workspace_id=self._current_ws_id if self._current_ws_id else "")
        except ConnectionResetError:
            logger.debug("[index] connection reset while sending progress")
        except Exception:
            logger.debug("[index] failed to send progress", exc_info=True)

    async def _auto_name_session(self, session: Any, first_user_msg: str) -> str:
        """Generate a concise session name (≤10 chars) from the user's first message.
        Uses the same backend as the session's agent with a minimal prompt.
        If the call fails or times out, returns empty string (no name set)."""
        try:
            backend = session.agent.loop.backend
            if backend is None:
                return ""
            prompt_text = first_user_msg.strip()[:200]
            if not prompt_text:
                return ""
            sys_prompt = "You are a naming assistant. Summarize the user's request in 10 characters or less. Return ONLY the name, no quotes, no explanation."
            gen = backend.chat(
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": prompt_text},
                ],
                max_tokens=30,
                stream=True,
            )
            full_text = ""
            async for event in gen:
                from encre.utils.types import BackendText
                if isinstance(event, BackendText):
                    full_text += event.text
                elif isinstance(event, (BackendFinish,)):
                    break
            name = full_text.strip().strip('"').strip("'").strip("「").strip("」").strip("『").strip("』")[:15]
            if len(name) < 2:
                return ""
            return name
        except Exception:
            return ""

    async def _auto_name_and_rename(self, session: Any, prompt: str) -> None:
        """Generate a session name in the background (fire-and-forget)."""
        try:
            name = await asyncio.wait_for(
                self._auto_name_session(session, prompt), timeout=5.0)
            if name:
                self._manager.rename_session(session.session_id, name)
                logger.info("[session] auto-named %s -> %s", session.session_id[:8], name)
        except asyncio.TimeoutError:
            logger.debug("[session] auto-name timed out")
        except Exception:
            logger.debug("[session] auto-name failed", exc_info=True)

    @staticmethod
    async def _build_skills_list(info: Any) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            registry = info.agent.skill_registry
            for name, skill in registry._skills.items():
                if getattr(skill, "hidden", False):
                    continue
                entry: dict[str, Any] = {
                    "name": name,
                    "description": skill.description,
                    "aliases": skill.aliases,
                    "source": str(skill.source) if hasattr(skill, "source") else "bundled",
                    "argument_hint": skill.argument_hint,
                    "allowed_tools": skill.allowed_tools,
                    "when_to_use": skill.when_to_use,
                    "context": str(skill.context) if hasattr(skill, "context") else "inline",
                    "model": skill.model,
                    "disable_model_invocation": skill.disable_model_invocation,
                    "user_invocable": skill.user_invocable,
                    "license": getattr(skill, "license", ""),
                    "compatibility": getattr(skill, "compatibility", ""),
                    "metadata": getattr(skill, "metadata", {}),
                }
                if skill.body:
                    entry["body"] = skill.body
                else:
                    try:
                        entry["body"] = await skill.get_prompt_for_command(None, {})
                    except Exception:
                        entry["body"] = ""
                results.append(entry)
        except Exception as e:
            logger.error(f"_build_skills_list failed: {e}")
        return results

    @staticmethod
    def _build_tools_info(info: Any) -> dict[str, Any]:
        """Snapshot of tool catalog for the client UI.

        Exposes the base always-on tools, the per-session unlocked set,
        the full active payload the model sees this turn, and a category
        breakdown so the UI can render a discovery panel.
        """
        try:
            from encre.tools.discovery import BASE_TOOLS
            discovery = info.agent.loop.discovery
            session_id = info.agent.session.id
            tools_map = info.agent.tool_registry.list_tools()
            return {
                "base": sorted(BASE_TOOLS),
                "unlocked": discovery.get_unlocked(session_id),
                "active": discovery.get_active_tool_names(session_id),
                "by_category": discovery.list_by_category(),
                "total_available": len(tools_map),
            }
        except Exception as exc:
            logger.warning("Failed to build tools_info: %s", exc)
            return {
                "base": [],
                "unlocked": [],
                "active": [],
                "by_category": {},
                "total_available": 0,
            }

    # ── Skills index management ──────────────────────────────────────────

    @staticmethod
    def _skills_index_path(skills_dir: Any) -> str:
        return os.path.join(str(skills_dir), "index.json")

    @staticmethod
    def _load_skills_index(skills_dir: Any) -> dict[str, Any]:
        idx_path = EncreWSHandler._skills_index_path(skills_dir)
        if not os.path.isfile(idx_path):
            return {"skills": {}}
        try:
            from encre.crypto import decrypt
            with open(idx_path, encoding="utf-8") as f:
                raw = decrypt(f.read())
            return json.loads(raw)
        except Exception:
            return {"skills": {}}

    @staticmethod
    def _save_skills_index(skills_dir: Any, index: dict[str, Any]) -> None:
        from encre.crypto import encrypt
        idx_path = EncreWSHandler._skills_index_path(skills_dir)
        raw = json.dumps(index, ensure_ascii=False, indent=2)
        with open(idx_path, "w", encoding="utf-8") as f:
            f.write(encrypt(raw))

    @staticmethod
    def _add_skill_to_index(skills_dir: Any, name: str, source_type: str = "md") -> None:
        index = EncreWSHandler._load_skills_index(skills_dir)
        index["skills"][name] = {
            "name": name,
            "installed_at": int(time.time()),
            "type": source_type,
        }
        EncreWSHandler._save_skills_index(skills_dir, index)

    @staticmethod
    def _remove_skill_from_index(skills_dir: Any, name: str) -> None:
        index = EncreWSHandler._load_skills_index(skills_dir)
        index["skills"].pop(name, None)
        EncreWSHandler._save_skills_index(skills_dir, index)

    # ── Zip helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _looks_like_base64_zip(content: str) -> bool:
        """Heuristic: base64 zip payloads are single-line, no markdown frontmatter."""
        stripped = content.strip()
        if not stripped:
            return False
        if "\n" in stripped:
            return False
        if stripped.startswith("---"):
            return False
        # Must be valid base64-ish (no unicode, only base64 chars)
        if not re.match(r"^[A-Za-z0-9+/=]+$", stripped):
            return False
        try:
            decoded = base64.b64decode(stripped)
            # Check for zip magic bytes
            return decoded[:4] == b"PK\x03\x04"
        except Exception:
            return False

    @staticmethod
    def _install_skill_from_zip_data(content: str, skill_dir: Any) -> None:
        """Extract base64-encoded zip directly into skill_dir."""
        decoded = base64.b64decode(content.strip())
        tmpdir = tempfile.mkdtemp(prefix="yim_skill_")
        try:
            with zipfile.ZipFile(zipfile.BytesIO(decoded), "r") as zf:
                zf.extractall(tmpdir)

            src = _find_skill_root(tmpdir)
            if src is None:
                raise ValueError("No SKILL.md found in zip package")
            _copy_skill_tree(src, str(skill_dir))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    @staticmethod
    def _install_skill_from_zip_file(zip_path: str, skill_dir: Any) -> None:
        """Extract zip from disk directly into skill_dir."""
        tmpdir = tempfile.mkdtemp(prefix="yim_skill_")
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmpdir)

            src = _find_skill_root(tmpdir)
            if src is None:
                raise ValueError("No SKILL.md found in zip package")
            _copy_skill_tree(src, str(skill_dir))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    async def _edit_message(self, session: Any, index: int, new_content: str) -> None:
        """Edit a user message -- commit current state, modify, truncate subsequent.

        ``index`` is the user-role-only index (0 = first user message),
        matching the frontend's ``data-user-idx``.
        """
        sess = session.agent.session
        msgs = list(sess.messages)
        user_idx = -1
        for i, m in enumerate(msgs):
            if m.get("role") == "user":
                user_idx += 1
                if user_idx == index:
                    session.agent.loop.rollback.commit(
                        sess, f"before_edit_msg_{index}")
                    # Restore file snapshots from the truncated turns
                    restored = sess.restore_file_snapshots()
                    if restored:
                        logger.info("[edit_msg] restored %d file(s) from snapshots", restored)
                    m["content"] = new_content
                    sess.messages = msgs[:i + 1]
                    sess.turn_count = max(1, index + 1)
                    sess.updated_at = time.time()
                    sess.rebuild_runtime_caches()
                    session.agent.loop.rollback.commit(
                        sess, f"edit_msg_{index}")
                    if not sess.metadata.get("temp_chat"):
                        await self._manager._save_session_async(session)
                    return
        raise ValueError(f"Message index {index} not found")

    async def _delete_message(self, session: Any, index: int) -> None:
        """Delete a user message and all subsequent -- commit current state first.

        ``index`` is the user-role-only index (0 = first user message),
        matching the frontend's ``data-user-idx``.
        """
        sess = session.agent.session
        msgs = list(sess.messages)
        user_idx = -1
        for i, m in enumerate(msgs):
            if m.get("role") == "user":
                user_idx += 1
                if user_idx == index:
                    session.agent.loop.rollback.commit(
                        sess, f"before_delete_msg_{index}")
                    # Restore file snapshots from the deleted turns
                    restored = sess.restore_file_snapshots()
                    if restored:
                        logger.info("[delete_msg] restored %d file(s) from snapshots", restored)
                    sess.messages = msgs[:i]
                    sess.turn_count = max(1, index)
                    sess.updated_at = time.time()
                    sess.rebuild_runtime_caches()
                    session.agent.loop.rollback.commit(
                        sess, f"delete_msg_{index}")
                    if not sess.metadata.get("temp_chat"):
                        await self._manager._save_session_async(session)
                    return
        raise ValueError(f"Message index {index} not found")

    async def _dispatch_event(self, ws, _info, event: Any) -> None:
        sid = _info.session_id if _info else None
        if isinstance(event, TextDelta) and event.text:
            await self._send(ws, "text_delta", text=event.text, session_id=sid)

        elif isinstance(event, ThinkingDelta) and event.text:
            await self._send(ws, "thinking_delta", text=event.text, session_id=sid)

        elif isinstance(event, ToolCallStart):
            await self._send(ws, "tool_call_start", name=event.name, id=event.id, session_id=sid)

        elif isinstance(event, ToolCallDelta):
            await self._send(ws, "tool_call_delta", id=event.id, key=event.key, value=event.value, session_id=sid)  # noqa: E501

        elif isinstance(event, ToolCallEnd):
            await self._send(ws, "tool_call_end", id=event.id, session_id=sid)

        elif isinstance(event, ToolProgress):
            await self._send(
                ws,
                "tool_progress",
                id=event.id,
                tool_name=event.tool_name,
                status=event.status,
                sub_agent_messages=event.sub_agent_messages,
                session_id=sid,
            )

        elif isinstance(event, ToolResult):
            content = event.content
            if len(content) > 100000:
                content = content[:100000] + "\n... (truncated)"
            await self._send(
                ws,
                "tool_result",
                id=event.id,
                content=content,
                is_error=event.is_error,
                sub_agent_messages=event.sub_agent_messages,
                sub_agent_session_id=event.sub_agent_session_id,
                session_id=sid,
            )

        elif isinstance(event, PermissionRequest):
            await self._send(ws, "permission_request", tool_name=event.tool_name, reason=event.reason, session_id=sid)  # noqa: E501

        elif isinstance(event, QuestionRequest):
            await self._send(ws, "question_request", tool_call_id=event.tool_call_id, questions=event.questions, session_id=sid)  # noqa: E501

        elif isinstance(event, Artifact):
            await self._send(ws, "artifacts_update", artifacts=[event.artifact], session_id=sid)

        elif isinstance(event, Reference):
            await self._send(ws, "references_update", references=[event.reference], session_id=sid)

        elif isinstance(event, PlanUpdate):
            await self._send(ws, "plan_update", plan_items=event.plan_items, session_id=sid)
            # Persist plan items asynchronously (debounced) so they survive app
            # refresh without blocking the event dispatch / subsequent WS sends.
            if _info is not None:
                _info.agent.session.plan_items = event.plan_items
                self._manager._schedule_save(_info)

        elif isinstance(event, AssistantBoundary):
            await self._send(ws, "assistant_boundary", session_id=sid)

        elif isinstance(event, CompactNotification):
            await self._send(ws, "compact",
                old_count=event.old_count,
                new_count=event.new_count,
                old_tokens=event.old_tokens,
                new_tokens=event.new_tokens,
                session_id=sid)
            # Also push updated context usage to the canvas panel
            if _info is not None:
                ctx_msgs = _info.agent.session.get_context_messages()
                ctx_tokens = count_message_tokens(ctx_msgs)
                window = _info.agent.loop.backend.context_window_size() if _info.agent.loop.backend else 0  # noqa: E501
                await self._send(ws, "context_usage",
                    context_tokens=ctx_tokens,
                    context_window=window,
                    session_id=sid)

        elif isinstance(event, WorkflowStartedEvent):
            await self._send(ws, "workflow_started",
                workflow_id=event.workflow_id,
                goal=event.goal,
                total_tasks=event.total_tasks,
                task_ids=event.task_ids,
                session_id=sid)

        elif isinstance(event, WorkflowTaskEvent):
            await self._send(ws, "workflow_task",
                workflow_id=event.workflow_id,
                task_id=event.task_id,
                task_name=event.task_name,
                status=event.status,
                session_id=sid)

        elif isinstance(event, WorkflowCompletedEvent):
            await self._send(ws, "workflow_completed",
                workflow_id=event.workflow_id,
                goal=event.goal,
                success=event.success,
                completed_count=event.completed_count,
                failed_count=event.failed_count,
                skipped_count=event.skipped_count,
                total_duration=event.total_duration,
                session_id=sid)

        elif isinstance(event, EngineInstallRequest):
            kwargs: dict[str, Any] = dict(
                request_id=event.request_id,
                engine=event.engine,
                title=event.title,
                body=event.body,
                hint=event.hint,
                options=list(event.options),
                session_id=sid,
            )
            if event.title_code:
                kwargs["title_code"] = event.title_code
                kwargs["title_args"] = dict(event.title_args)
            if event.body_code:
                kwargs["body_code"] = event.body_code
                kwargs["body_args"] = dict(event.body_args)
            if event.hint_code:
                kwargs["hint_code"] = event.hint_code
                kwargs["hint_args"] = dict(event.hint_args)
            await self._send(ws, "engine_install_request", **kwargs)

        elif isinstance(event, EngineInstallProgress):
            await self._send(ws, "engine_install_progress",
                request_id=event.request_id,
                pct=event.pct,
                message=event.message,
                sub_message=event.sub_message,
                indeterminate=event.indeterminate,
                status=event.status,
                session_id=sid)

        elif isinstance(event, Finish):
            # Send the last assistant message ID so the frontend can store it for retry matching
            last_msg_id = None
            if _info and _info.agent.session.messages:
                last = _info.agent.session.messages[-1]
                if last.get("role") == "assistant":
                    last_msg_id = last.get("id")
            await self._send(ws, "finish", reason=event.reason, usage=event.usage,
                             error=event.error, assistant_message_id=last_msg_id,
                             session_id=sid)
            # Push updated context usage so the canvas panel stays in sync
            if _info is not None:
                ctx_msgs = _info.agent.session.get_context_messages()
                ctx_tokens = count_message_tokens(ctx_msgs)
                window = _info.agent.loop.backend.context_window_size() if _info.agent.loop.backend else 0  # noqa: E501
                await self._send(ws, "context_usage",
                    context_tokens=ctx_tokens,
                    context_window=window,
                    session_id=sid)


# ── Module-level helpers ──────────────────────────────────────────────────

def _format_attachments(attachments: list[dict]) -> str:
    """Format attachment list into a structured markdown block for the agent.

    Text files (is_binary=False) include their content in a fenced code block.
    Binary files are listed by name and size only.
    """
    if not attachments:
        return ""

    parts: list[str] = []
    for att in attachments:
        name = att.get("name", "unnamed")
        size = att.get("size", 0)
        is_binary = att.get("is_binary", True)
        content = att.get("content", "")

        size_str = _fmt_size(size)
        if is_binary or not content.strip():
            parts.append(f"- **{name}** (binary, {size_str})")
        else:
            ext = os.path.splitext(name)[1].lower()
            lang = _ext_to_lang(ext)
            parts.append(f"- **{name}** ({size_str}):\n```{lang}\n{content.rstrip()}\n```")

    if not parts:
        return ""

    return "--- Attached Files ---\n" + "\n".join(parts) + "\n---"


def _fmt_size(bytes: int) -> str:
    if bytes < 1024:
        return f"{bytes} B"
    elif bytes < 1024 * 1024:
        return f"{bytes / 1024:.1f} KB"
    return f"{bytes / (1024 * 1024):.1f} MB"


_LANG_MAP = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "tsx",
    ".jsx": "jsx", ".html": "html", ".css": "css", ".scss": "scss",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".md": "markdown", ".rs": "rust", ".go": "go", ".java": "java",
    ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
    ".sh": "bash", ".bash": "bash", ".ps1": "powershell",
    ".sql": "sql", ".rb": "ruby", ".php": "php", ".swift": "swift",
    ".kt": "kotlin", ".dart": "dart", ".vue": "vue", ".svelte": "svelte",
    ".xml": "xml", ".svg": "xml", ".tex": "latex",
    ".gradle": "groovy", ".cmake": "cmake",
    ".dockerfile": "dockerfile", ".makefile": "makefile",
}


def _ext_to_lang(ext: str) -> str:
    return _LANG_MAP.get(ext, "")


def _find_skill_root(extracted_dir: str) -> str | None:
    """Find the directory containing SKILL.md in an extracted zip tree.

    Returns the path to the directory that directly contains SKILL.md.
    """
    for root, dirs, files in os.walk(extracted_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.upper() == "SKILL.MD":
                return root
    return None


def _copy_skill_tree(src_dir: str, dest_dir: str) -> None:
    """Copy all files from src_dir into dest_dir, overwriting dest."""
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir, ignore_errors=True)
    os.makedirs(dest_dir, exist_ok=True)
    for item in os.listdir(src_dir):
        s = os.path.join(src_dir, item)
        d = os.path.join(dest_dir, item)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)


# ── Workspace persistence ──────────────────────────────────────────────

def _apply_workspace_config(config: Any, workspace_path: str) -> None:
    """Load .encre/config.json from the workspace and apply overrides to config."""
    ws_config_path = os.path.join(workspace_path, ".encre", "config.json")
    if not os.path.isfile(ws_config_path):
        return
    try:
        with open(ws_config_path, encoding="utf-8") as f:
            ws_config = json.load(f)

        if "system_prompt" in ws_config:
            config.system_prompt = ws_config["system_prompt"]
        if "permission_mode" in ws_config:
            config.permission_mode = ws_config["permission_mode"]
        if "specialty" in ws_config:
            config.default_specialty = ws_config["specialty"]
        if "max_turns" in ws_config:
            config.max_turns = ws_config["max_turns"]
        if "language" in ws_config:
            config.language = ws_config["language"]

        logger.info(f"Applied workspace config from {ws_config_path}")
    except Exception:
        logger.warning("Failed to load workspace config", exc_info=True)


def _get_yim_data_dir() -> str:
    return os.environ.get("ENCRE_DATA_DIR", os.path.join(os.path.expanduser("~"), ".dunimd", "encre"))  # noqa: E501


def _build_workspace_tree(ws_path: str, max_depth: int = 4, max_entries: int = 200) -> str:
    """Quickly walk the workspace directory tree without reading file contents.
    Returns a compact tree representation for immediate injection into the
    session's system prompt, so the model sees the project structure on the
    very first turn (before the full code index is built)."""
    skip_dirs = {"node_modules", "__pycache__", ".git", ".venv", "venv",
                 "target", "build", "dist", ".tox", ".eggs",
                 ".mypy_cache", ".pytest_cache", ".ruff_cache",
                 ".svn", ".hg", ".idea", ".vscode"}
    skip_ext = {".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe"}
    lines: list[str] = []
    total_files = 0
    try:
        for root, dirs, files in os.walk(ws_path):
            dirs[:] = [d for d in dirs
                       if not d.startswith(".") and d not in skip_dirs]
            rel = os.path.relpath(root, ws_path)
            if rel == ".":
                rel = ""
            depth = rel.count(os.sep) + 1 if rel else 0
            if depth > max_depth:
                continue
            indent = "  " * depth
            if depth == 0:
                lines.append("📁 workspace/")
            else:
                basename = os.path.basename(root)
                lines.append(f"{indent}📁 {basename}/")
            for fname in sorted(files):
                if fname.startswith("."):
                    continue
                ext = os.path.splitext(fname)[1].lower()
                if ext in skip_ext:
                    continue
                if len(lines) >= max_entries:
                    break
                lines.append(f"{indent}  📄 {fname}")
                total_files += 1
            if len(lines) >= max_entries:
                lines.append(f"  ... (truncated at {max_entries} entries)")
                break
    except (OSError, PermissionError):
        pass
    if not lines:
        return ""
    return (
        f"## Workspace Structure\n"
        f"{total_files} files (tree depth ≤{max_depth}). "
        f"Full code index is building in the background.\n"
        f"```\n" + "\n".join(lines) + "\n```"
    )


def _get_workspaces_path() -> str:
    return os.path.join(_get_yim_data_dir(), "iwork", "index.json")


def _make_workspace_id(folder_path: str) -> str:
    """Generate a stable ID from the workspace path."""
    import hashlib
    return hashlib.sha256(folder_path.encode()).hexdigest()[:12]


def _get_workspace_dir(ws_id: str) -> str:
    return os.path.join(_get_yim_data_dir(), "iwork", ws_id)


def _remove_session_from_workspace_indices(session_id: str) -> None:
    """Remove a session_id from ALL workspace index files.

    Workspace ``index.json`` files are separate from the main session
    manager's index. ``list_sessions`` loads them independently, so a
    deleted session would reappear on page refresh if we don't clean
    them up here.
    """
    for ws in _load_workspaces():
        ws_id = ws.get("id") or _make_workspace_id(ws["path"])
        ws_dir = _get_workspace_dir(ws_id)
        idx_file = os.path.join(ws_dir, "sessions", "index.json")
        if not os.path.isfile(idx_file):
            continue
        try:
            raw = open(idx_file, encoding="utf-8").read().strip()
            if raw and not raw.startswith("{"):
                from encre.crypto import decrypt
                with contextlib.suppress(Exception):
                    raw = decrypt(raw)
            idx = json.loads(raw)
            if not isinstance(idx, dict):
                continue
            if session_id in idx:
                del idx[session_id]
                new_raw = json.dumps(idx, ensure_ascii=False, separators=(",", ":"))
                try:
                    from encre.crypto import encrypt
                    new_raw = encrypt(new_raw)
                except Exception:
                    pass
                open(idx_file, "w", encoding="utf-8").write(new_raw)
        except Exception:
            continue


def _index_metadata_path(ws_id: str) -> str:
    """Path to the index metadata marker for a workspace."""
    return os.path.join(_get_workspace_dir(ws_id), "index_metadata.json")


def _load_index_metadata(ws_id: str) -> dict[str, Any] | None:
    """Load index metadata for a workspace. Returns None if never indexed."""
    path = _index_metadata_path(ws_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_index_metadata(ws_id: str, file_count: int) -> None:
    """Write index metadata marker to persist that indexing was done."""
    path = _index_metadata_path(ws_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"files": file_count, "indexed_at": time.time()}, f)
    except Exception:
        logger.warning("[codebase] failed to save index metadata for ws=%s", ws_id)


def _ensure_workspace_dirs(ws_id: str) -> str:
    """Create workspace data directories and return the workspace dir path."""
    ws_dir = _get_workspace_dir(ws_id)
    os.makedirs(os.path.join(ws_dir, "sessions"), exist_ok=True)
    return ws_dir


def _load_workspaces() -> list[dict[str, Any]]:
    path = _get_workspaces_path()
    if not os.path.exists(path):
        return []
    try:
        from encre.crypto import decrypt
        with open(path, encoding="utf-8") as f:
            encrypted = f.read()
        if not encrypted.strip():
            return []
        raw = decrypt(encrypted)
        workspaces: list[dict[str, Any]] = json.loads(raw)
        # Migrate old records that lack an id field
        migrated = False
        for w in workspaces:
            if "id" not in w:
                w["id"] = _make_workspace_id(w["path"])
                migrated = True
        if migrated:
            _save_workspaces(workspaces)
        # Filter out invalid entries (empty path or name)
        workspaces = [w for w in workspaces if w.get("path") and w.get("name")]
        return workspaces
    except Exception:
        logger.warning("Failed to load workspaces", exc_info=True)
        return []


def _save_workspaces(workspaces: list[dict[str, Any]]) -> None:
    path = _get_workspaces_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        from encre.crypto import encrypt
        raw = json.dumps(workspaces, ensure_ascii=False)
        encrypted = encrypt(raw)
        with open(path, "w", encoding="utf-8") as f:
            f.write(encrypted)
    except Exception:
        logger.warning("Failed to save workspaces", exc_info=True)
