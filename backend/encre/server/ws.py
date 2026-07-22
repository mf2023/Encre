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

"""Encre WebSocket message handler.

:class:`EncreWSHandler` is the per-connection handler bound to
:class:`~encre.server.app.EncreServer`.  It receives typed client messages
(parsed by :mod:`encre.server.protocol`), drives the agent runtime, and
streams :class:`~encre.utils.types.AgentEvent` results back to the desktop
client as JSON frames.

The handler owns a great deal of the product surface: session lifecycle,
model / skill / agent configuration, workspaces & code indexing, memory &
rules, terminal control, branch/rollback editing, and the automation
scheduler bridge.  iClaw (``channel == "iclaw"``) runs are dispatched
through the adapter :class:`~encre.gateway.server.GatewayServer`'s
EventRouter in a background task.
"""

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
from dataclasses import replace
from typing import Any

import websockets

from encre.backend import create_backend
from encre.backends.catalog import catalog_payload
from encre.backends.mcp_catalog import mcp_catalog_payload
from encre.channels.slash_commands import get_slash_command_defs
from encre.config import (
    AgentConfig,
    EncreConfig,
    ModelConfig,
    SubAgentConfig,
    _thinking_config_from_dict,
)
from encre.server.protocol import (
    ClientAddDocument,
    ClientAgentCreate,
    ClientAgentDelete,
    ClientAgentList,
    ClientAgentSetActive,
    ClientAgentUpdate,
    ClientAutomationCancelJob,
    ClientAutomationCreateJob,
    ClientAutomationDeleteJob,
    ClientAutomationDeleteExecution,
    ClientAutomationGetHistory,
    ClientAutomationListJobs,
    ClientAutomationRenameExecution,
    ClientAutomationToggleJob,
    ClientAutomationUpdateJob,
    ClientCancel,
    ClientCloseWorkspace,
    ClientConfigure,
    ClientDeleteGlobalRule,
    ClientDeleteIndex,
    ClientDeleteMessage,
    ClientDeleteModel,
    ClientDeleteSession,
    ClientEditMessage,
    ClientEngineInstallResponse,
    ClientExportSession,
    ClientFetchModels,
    ClientGetConfig,
    ClientGetGitignore,
    ClientGetGlobalRuleContent,
    ClientGetMemoryDetail,
    ClientGetMemoryList,
    ClientGetProfile,
    ClientGetUsageStats,
    ClientIclawResume,
    ClientInstallSkill,
    ClientListAllSessions,
    ClientListDocuments,
    ClientListGlobalRules,
    ClientListModels,
    ClientListProjectHooks,
    ClientListProjectRules,
    ClientListSessions,
    ClientListWorkspaces,
    ClientNewSession,
    ClientOpenWorkspace,
    ClientPing,
    ClientReindexWorkspace,
    ClientReplayGetSession,
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
    ClientSetMode,
    ClientSetPlanMode,
    ClientSetCommand,
    ClientSpecApprove,
    ClientSpecReject,
    ClientSteer,
    ClientSwitchBranch,
    ClientTerminalKill,
    ClientTerminalListShells,
    ClientTerminalResize,
    ClientTerminalSpawn,
    ClientTerminalWrite,
    ClientTestAdapter,
    ClientWechatScan,
    ClientUninstallSkill,
    ClientUpdateAgent,
    ClientUpdateMCP,
    ClientUpdateModels,
    ClientUpdateSkill,
    ClientUpdateSkills,
    ClientUpdateSubAgents,
    ClientValidateModel,
    encode_server_message,
    parse_client_message,
)
from encre.server.session_manager import SessionManager
from encre.spec import EncreSpecEngine
from encre.utils.tokens import count_message_tokens


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
from encre.settings_manager import (  # noqa: E402
    load_custom_slash_commands,
    save_custom_slash_commands,
)
from encre.utils.types import (  # noqa: E402
    Artifact,
    AssistantBoundary,
    BackendError,
    BackendFinish,
    CompactNotification,
    EngineInstallProgress,
    EngineInstallRequest,
    Finish,
    PermissionRequest,
    PlanUpdate,
    QuestionRequest,
    Reference,
    SystemMessage,
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

logger = logging.getLogger("encre.server.ws")

# Bridge standard logging to loguru so ws.py logs appear in desktop output
try:
    from loguru import logger as _loguru_logger
    import sys
    class _LoguruHandler(logging.Handler):
        def emit(self, record):
            try:
                _loguru_logger.opt(depth=6, exception=record.exc_info).log(record.levelname, record.getMessage())
            except Exception:
                pass
    _loguru_handler = _LoguruHandler()
    _loguru_handler.setLevel(logging.DEBUG)
    logging.getLogger("encre.server.ws").addHandler(_loguru_handler)
    logging.getLogger("encre.server.ws").setLevel(logging.DEBUG)
except Exception:
    pass


class EncreWSHandler:
    """Per-connection handler for the Encre WebSocket protocol.

    One instance is created per :class:`~encre.server.app.EncreServer` and is
    reused across connections.  It owns the session manager, optional index
    manager, adapter manager and automation scheduler, and implements the big
    ``handle`` dispatch loop that turns client protocol messages into agent
    runs and server protocol frames.
    """

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
        self._tasks: set[asyncio.Task[Any]] = set()

    async def _send(self, ws, msg_type: str, **kwargs) -> None:
        """Encode and send a server message, then deliver it over the WebSocket.

        Honours the per-connection ``_client_encrypted`` flag so legacy
        plaintext clients keep receiving plain JSON while encrypted clients
        get AES-GCM frames.  On send failure (disconnect) the running
        agent task is cancelled.
        """
        encrypt = self._client_encrypted if self._client_encrypted is not None else False
        try:
            payload = encode_server_message(msg_type, encrypt=encrypt, **kwargs)
        except Exception as exc:
            logger.error("[_send] Failed to encode %s: %s\n%s", msg_type, exc, traceback.format_exc())
            return
        try:
            await ws.send(payload)
        except Exception as exc:
            logger.warning("[_send] Failed to send %s: %s", msg_type, exc)
            # WebSocket disconnected -- cancel any running agent
            self._cancel_current_task()

    async def _send_session_mode(self, ws, session) -> None:
        """Send mode_changed for the session's persisted mode (if any)."""
        try:
            mode = (session.metadata.get("slash_command_mode") if hasattr(session, 'metadata') else None) or ""
            if mode:
                await self._send(ws, "mode_changed", mode=mode, session_id=session.session_id)
        except Exception:
            pass

    async def _apply_mode(self, ws, session, mode: str) -> str:
        """Apply a slash-command mode transition through the single entry point.

        Normalises ``mode`` (only ``""``/``"plan"``/``"spec"`` survive) and
        drives it through ``loop.set_mode`` so ``config.slash_command_mode``,
        the ``session.metadata`` mirror, and the derived ``plan_mode_active``
        flag never disagree.  Then broadcasts ``mode_changed`` so the desktop
        toolbar chip / exit button reflect the new mode, and -- only when the
        plan-active state actually changed -- ``plan_mode_changed`` so the plan
        proposals panel stays in sync.  Returns the normalised mode.
        """
        valid = ("", "plan", "spec")
        mode = mode if mode in valid else ""
        was_plan = session.agent.loop.plan_mode_active
        session.agent.loop.set_mode(mode)
        now_plan = session.agent.loop.plan_mode_active
        logger.info("[set_mode] mode applied: '%s' session=%s plan_mode_active=%s->%s",
                    mode, session.session_id[:8], was_plan, now_plan)
        await self._send(ws, "mode_changed", mode=mode, session_id=session.session_id)
        if was_plan != now_plan:
            await self._send(ws, "plan_mode_changed",
                             active=now_plan, session_id=session.session_id)
        return mode

    def _restore_persisted_mode(self, session) -> None:
        """Re-apply a session's persisted slash-command mode after (re)load.

        A resumed or freshly-created session carries its mode in metadata but
        the agent's ``config.slash_command_mode`` starts at the default.  Drive
        it through ``loop.set_mode`` so the string, metadata mirror, and
        derived ``plan_mode_active`` flag all agree before the next run.
        """
        try:
            mode = session.metadata.get("slash_command_mode", "") or ""
            session.agent.loop.set_mode(mode)
        except Exception:
            logger.debug("failed to restore persisted mode", exc_info=True)

    async def _send_session_command(self, ws, session) -> None:
        """Send command_changed for the session's persisted command (if any)."""
        try:
            cmd = (session.metadata.get("active_command") if hasattr(session, 'metadata') else None)
            if cmd and cmd.get("name"):
                await self._send(ws, "command_changed", command=cmd,
                                 session_id=session.session_id)
        except Exception:
            pass

    async def _apply_command(self, ws, session, name: str, prompt: str = "",
                             icon: str = "", title: str = "") -> None:
        """Apply a slash-command activation/clear through the single entry point.

        Stores the command (``{name, prompt, icon, title}``) via
        ``loop.set_command`` so ``config.active_command`` and the
        ``session.metadata`` mirror stay consistent, then broadcasts
        ``command_changed`` so the desktop command chip reflects the new
        state.  An empty ``name`` clears the active command.  A command is
        independent of the mode (plan/spec) -- both may be active at once.
        """
        name = (name or "").strip()
        if name:
            session.agent.loop.set_command(name, prompt, icon=icon, title=title)
        else:
            session.agent.loop.clear_command()
        cmd = session.agent.config.active_command
        logger.info("[set_command] command applied: '%s' session=%s",
                    name or "(cleared)", session.session_id[:8])
        await self._send(ws, "command_changed", command=cmd,
                         session_id=session.session_id)

    def _restore_persisted_command(self, session) -> None:
        """Re-apply a session's persisted slash command after (re)load.

        Mirrors :meth:`_restore_persisted_mode`: the persisted command lives
        in ``session.metadata["active_command"]`` but ``config.active_command``
        starts at ``None``.  Drive it through ``loop.set_command`` so the
        in-memory mirror agrees before the next run re-injects the block.
        """
        try:
            cmd = session.metadata.get("active_command") or {}
            if cmd.get("name"):
                session.agent.loop.set_command(
                    cmd.get("name", ""),
                    cmd.get("prompt", ""),
                    icon=cmd.get("icon", ""),
                    title=cmd.get("title", ""),
                )
        except Exception:
            logger.debug("failed to restore persisted command", exc_info=True)

    @staticmethod
    def _renderer_session_messages(session: Any) -> list[dict[str, Any]]:
        """Return visible history without dropping renderer-only tool IDs."""
        return [
            message
            for message in session.get_renderer_messages()
            if message.get("role") != "system"
        ]

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
            self._info.agent.session.metadata["channel"] = "iwork" if self._workspace_path else "normal"
            # Restore permission_settings from persisted settings
            try:
                from encre.settings_manager import load_settings
                stored = load_settings()
                pset = stored.get("permission_settings")
                if pset and hasattr(self._info.agent.config, "permission_settings"):
                    self._info.agent.config.permission_settings = pset
                    if hasattr(self._info.agent, "safety"):
                        from encre.utils.types import PermissionAllow
                        tools_dict = {}
                        caps_dict = {}
                        for k, v in pset.items():
                            if v not in ("default", "allow", "deny", "ask"):
                                continue
                            if k in ("network", "file", "bash_io", "docker", "browser", "workflow", "git", "deploy", "desktop", "database", "misc", "mcp"):
                                caps_dict[k] = v
                            else:
                                tools_dict[k] = v
                        self._info.agent.safety.set_policies(tools_dict, caps_dict)
            except Exception:
                pass
            # Load MCP servers from the canonical mcp.json
            try:
                from encre.tools.mcp_manager import default_mcp_config_path
                mcp_path = default_mcp_config_path()
                servers = self._load_mcp_servers(mcp_path)
                if servers:
                    self._info.agent.config.mcp_servers = servers
            except Exception:
                pass
            # Re-apply any persisted slash-command mode so config and the
            # derived ``plan_mode_active`` flag are correct before the first run.
            self._restore_persisted_mode(self._info)
            # Re-apply any persisted slash *command* (sticky prompt injection)
            # so its ``command_instructions`` block is re-injected next run.
            self._restore_persisted_command(self._info)
        return self._info

    async def handle(self, ws) -> None:
        """Main per-connection message loop.

        Reads raw WebSocket frames, parses them into typed client messages,
        dispatches on their type (the large ``elif isinstance(msg, ...)``
        chain below), drives the agent, and streams events back.  Also
        handles startup-mode session restore and connection lifecycle.
        """
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
                    # Re-apply the resumed session's persisted slash-command
                    # mode so config + derived plan_mode_active agree with
                    # metadata before the first run (and before _send_session_mode
                    # broadcasts the chip to the frontend).
                    self._restore_persisted_mode(self._info)
                    # Re-apply the persisted slash command (sticky injection)
                    # alongside the mode, then broadcast its chip too.
                    self._restore_persisted_command(self._info)
                    msgs = self._renderer_session_messages(sess)
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
            # Main dispatch loop: read each WebSocket frame, parse it into a
            # typed ClientMessage, then route on its type through the
            # elif isinstance(msg, ...) chain below.
            async for raw in ws:
                if self._client_encrypted is None:
                    text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                    self._client_encrypted = not text.strip().startswith("{")

                try:
                    msg = parse_client_message(raw)
                except Exception:
                    await self._send(ws, "error", message="Failed to parse message", code="parse_error")
                    continue

                if msg is None:
                    await self._send(ws, "error", message="Unknown message type", code="parse_error")
                    continue

                if isinstance(msg, ClientPing):
                    if self._info:
                        self._manager.touch(self._info.session_id)
                    await self._send(ws, "pong")

                elif isinstance(msg, ClientListModels):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    backend = info.agent.loop.backend
                    if backend is None:
                        # No backend configured yet - return empty model list
                        # instead of crashing with AttributeError.
                        models = []
                    else:
                        models = await backend.list_models()
                    await self._send(ws, "models_list", models=models)

                elif isinstance(msg, ClientListSessions):
                    sessions = self._list_all_sessions()
                    channel = "iwork" if self._workspace_path else "normal"
                    await self._send(ws, "sessions_list", sessions=sessions, channel=channel)

                elif isinstance(msg, ClientListAllSessions):
                    # Tray popup needs both modes' sessions at once.
                    normal = self._list_all_sessions(channel_filter="normal")
                    iwork = self._list_all_sessions(channel_filter="iwork")
                    await self._send(ws, "sessions_all", normal=normal, iwork=iwork)

                elif isinstance(msg, ClientNewSession):
                    if self._info:
                        real_msgs = [m for m in self._info.agent.session.messages if m.get("role") != "system"]
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
                    self._info.agent.session.metadata["channel"] = "iwork" if self._workspace_path else "normal"
                    await self._send(ws, "session_ready", session_id=self._info.session_id, plan_items=[], request_id=msg.request_id)

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
                    logger.info("[configure] keys=%s, rebuild=%s", list(msg.config.keys()), _rebuild)
                    for key, value in msg.config.items():
                        if value == "" or value is None:
                            logger.info("[configure] skip key=%s (empty/null)", key)
                            continue
                        if hasattr(session.agent.config, key):
                            old_val = getattr(session.agent.config, key)
                            setattr(session.agent.config, key, value)
                            logger.info("[configure] set %s: %r -> %r", key, old_val, value)
                        else:
                            logger.warning("[configure] key=%s NOT found on EncreConfig, skipping", key)
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
                        adapter_keys = {k: v for k, v in msg.config.items() if k.startswith("adapter_")}
                        if adapter_keys:
                            await self._adapter_manager.apply_config(adapter_keys)
                            # Persist adapter configs on EncreConfig so they survive restart
                            parsed: dict[str, dict[str, Any]] = {}
                            for ak, av in adapter_keys.items():
                                parts = ak.split("_", 2)
                                if len(parts) >= 3:
                                    parsed.setdefault(parts[1], {})[parts[2]] = av
                            # Handle unbind: if all weixin credential fields are empty, remove config
                            for aid, fields in list(parsed.items()):
                                if aid == "weixin" and "app_id" in fields and "token" in fields and not fields.get("app_id") and not fields.get("token"):
                                    session.agent.config.adapter_configs.pop(aid, None)
                                    self._default_config.adapter_configs.pop(aid, None)
                                    parsed.pop(aid, None)
                                    continue
                                # Merge into adapter_configs so existing fields (e.g. push_chat_id)
                                # are not lost when only a subset of keys is sent.
                                if aid in session.agent.config.adapter_configs:
                                    session.agent.config.adapter_configs[aid].update(fields)
                                else:
                                    session.agent.config.adapter_configs[aid] = fields
                                if aid in self._default_config.adapter_configs:
                                    self._default_config.adapter_configs[aid].update(fields)
                                else:
                                    self._default_config.adapter_configs[aid] = fields
                            logger.info("[configure] applied %d adapter config keys and persisted", len(adapter_keys))
                    self._persist_config(session)
                    self._persist_settings(session)
                    if "custom_slash_commands" in msg.config:
                        custom_cmds = msg.config["custom_slash_commands"]
                        if isinstance(custom_cmds, list):
                            save_custom_slash_commands(custom_cmds)
                            logger.info("[configure] saved %d custom slash commands", len(custom_cmds))
                    if "keybinds" in msg.config:
                        raw = msg.config["keybinds"]
                        if isinstance(raw, dict):
                            save_keybinds(raw)
                            logger.info("[configure] saved keybinds (%d entries)", len(raw.get("keybinds", [])))
                    if "permission_settings" in msg.config:
                        raw = msg.config["permission_settings"]
                        if isinstance(raw, dict):
                            capability_keys = {
                                "network", "file", "bash_io", "docker", "browser",
                                "workflow", "git", "deploy", "desktop", "database", "misc", "mcp",
                            }
                            # Empty dict is a read request: return the persisted settings.
                            if not raw:
                                msg.config["permission_settings"] = dict(session.agent.config.permission_settings)
                            else:
                                tools: dict[str, str] = {}
                                capabilities: dict[str, str] = {}
                                for key, value in raw.items():
                                    if not isinstance(value, str):
                                        continue
                                    if key in capability_keys:
                                        capabilities[key] = value
                                    else:
                                        tools[key] = value
                                session.agent.safety.set_policies(tools, capabilities)
                                session.agent.config.permission_settings = {**session.agent.config.permission_settings, **raw}
                                logger.info("[configure] applied permission_settings (%d tools, %d capabilities)", len(tools), len(capabilities))
                    self._persist_settings(session)
                    await self._send(ws, "configured", config=msg.config)

                elif isinstance(msg, ClientWechatScan):
                    if not self._adapter_manager:
                        await self._send(ws, "wechat_scan_result",
                            qrcode_url="", success=False,
                            message="Server not ready")
                        continue
                    try:
                        # Prefer a running adapter instance; otherwise build a
                        # temporary one so get_qrcode_url() uses the correct
                        # api_base derived from the gateway_url.
                        instances = getattr(self._adapter_manager, "_instances", {}) or {}
                        adapter = instances.get("weixin")
                        if adapter is None:
                            from encre.adapters.manager import _ADAPTER_CLASSES
                            cls = _ADAPTER_CLASSES.get("weixin")
                            if cls is None:
                                await self._send(ws, "wechat_scan_result",
                                    qrcode_url="", success=False,
                                    message="WeChat adapter class not found")
                                continue
                            adapter = cls()
                        if not hasattr(adapter, "get_qrcode_url"):
                            await self._send(ws, "wechat_scan_result",
                                qrcode_url="", success=False,
                                message="WeChat adapter does not support QR login")
                            continue
                        url, qrcode_token = await adapter.get_qrcode_url()
                        await self._send(ws, "wechat_scan_result",
                            qrcode_url=url, success=True, message="")
                        # Start background polling for scan confirmation
                        if qrcode_token:
                            _t = asyncio.ensure_future(self._poll_wechat_scan(ws, adapter, qrcode_token))
                            self._tasks.add(_t)
                    except Exception as e:
                        await self._send(ws, "wechat_scan_result",
                            qrcode_url="", success=False,
                            message=str(e))

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
                        adapter_keys[f"adapter_{adapter_id}_enabled"] = msg.config.get("enabled", True)
                        logger.info("[test_adapter] auto-saving config for %s: %s", adapter_id, list(adapter_keys.keys()))
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
                            err = self._adapter_manager._last_errors.get(adapter_id, "Adapter failed to start")
                            success = False
                            message = err
                            logger.warning("[test_adapter] %s validate OK but connect failed: %s", adapter_id, err)

                    await self._send(ws, "adapter_test_result",
                        adapter_id=msg.adapter_id, success=success, message=message)

                elif isinstance(msg, ClientRun):
                    #   iClaw mode: route through EventRouter in a task (same session space as
                    # adapters)
                    if msg.channel == "iclaw" and self._adapter_manager and self._adapter_manager.router:
                        router = self._adapter_manager.router
                        logger.info("[iclaw] received run: prompt=%.60s session_id=%s adapter_router=%s",
                                    msg.prompt, msg.session_id, bool(router))
                        # 在闭包外部提取所有需要捕获的值，避免闭包变量覆盖问题
                        iclaw_requested_sid = msg.session_id  # raw frontend value, resolved inside the task
                        iclaw_prompt = msg.prompt
                        iclaw_system_prompt = msg.system_prompt
                        iclaw_default_config = replace(self._default_config, workspace="")

                        async def _run_iclaw(*, router=router, iclaw_requested_sid=iclaw_requested_sid, iclaw_default_config=iclaw_default_config, iclaw_prompt=iclaw_prompt, iclaw_system_prompt=iclaw_system_prompt):
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
                                        logger.info("[iclaw] no existing session, will create new one")
                                logger.info("[iclaw] calling router.submit_stream sid=%s", sid)

                                try:
                                    stream = router.submit_stream(
                                        channel_name="iclaw",
                                        prompt=iclaw_prompt,
                                        session_id=sid,
                                        system_prompt=iclaw_system_prompt,
                                    )
                                    # Resolve the session info once so every event
                                    # dispatched downstream carries a concrete
                                    # session_id, allowing the desktop UI to
                                    # filter by session and prevent one session's
                                    # tokens from leaking into another session.
                                    iclaw_info = (
                                        router.session_manager.get_session(sid)
                                        if sid else None
                                    )
                                    try:
                                        async for event in stream:
                                            await self._dispatch_event(ws, iclaw_info, event)
                                    except asyncio.CancelledError:
                                        logger.info("[iclaw] task cancelled")
                                        with contextlib.suppress(Exception):
                                            await stream.aclose()
                                        with contextlib.suppress(Exception):
                                            await self._send(ws, "finish", reason="cancelled", session_id=sid)
                                    except Exception as e:
                                        logger.error("[iclaw] run error: %s", e, exc_info=True)
                                        from encre.backends.base import format_backend_error
                                        with contextlib.suppress(Exception):
                                            await self._send(ws, "finish", reason="error", error=format_backend_error(e), session_id=sid)
                                    else:
                                        _iclaw_session = router.session_manager.get_session(sid) if sid else None
                                        if _iclaw_session and _iclaw_session.agent.telemetry.enabled:
                                            with contextlib.suppress(Exception):
                                                await self._send(ws, "telemetry",
                                                    data=_iclaw_session.agent.telemetry.get_summary(),
                                                    session_id=sid)
                                except Exception as e:
                                    logger.error("[iclaw] setup error: %s", e, exc_info=True)
                                    from encre.backends.base import format_backend_error
                                    with contextlib.suppress(Exception):
                                        await self._send(ws, "finish", reason="error", error=format_backend_error(e), session_id=sid)

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
                        # Temp chat: mark ephemeral sessions immediately so
                        # nothing is persisted even if a save is triggered
                        # before the run loop starts.
                        if msg.temp_chat:
                            session.agent.session.metadata["temp_chat"] = True

                    self._manager.touch(session.session_id)

                    session.agent.session.metadata["channel"] = "iwork" if self._workspace_path else "normal"

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
                        # Check if the active model supports multimodal.
                        active_model = session.agent.config.get_active_model()
                        is_multimodal = active_model and (active_model.multimodal or False)

                        if is_multimodal and any(
                            a.get("mime_type", "").startswith("image/") for a in msg.attachments
                        ):
                            # Build a multimodal content block: text + image_url items.
                            content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
                            for att in msg.attachments:
                                mime = att.get("mime_type", "")
                                if mime.startswith("image/"):
                                    data = att.get("content", "")
                                    if data:
                                        content.append({
                                            "type": "image_url",
                                            "image_url": {"url": f"data:{mime};base64,{data}"},
                                        })
                                else:
                                    name = att.get("name", "file")
                                    content.append({"type": "text", "text": f"[Attached: {name}]"})
                            session.session.add_message("user", content)
                            # Set prompt empty since we already built the combined content
                            prompt = ""
                        else:
                            attachment_block = _format_attachments(msg.attachments)
                            if attachment_block:
                                prompt = attachment_block + "\n\n" + prompt

                    if msg.specialty and msg.specialty != "general":
                        session.agent.loop.prompt_builder._specialty = msg.specialty

                    # Wire the spec engine into the loop so spec mode can
                    # parse specs and enforce the approval gate.
                    session.agent.loop.spec_engine = self._spec_engine

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

                    # Mode transitions.  The desktop frontend echoes the
                    # active mode on every ``run`` message (inline chip or the
                    # persisted mode).  Treat an explicit ``mode`` that differs
                    # from the session's persisted mode as a real transition
                    # (the user typed /plan or /spec, or switched modes) and
                    # drive it through the single entry point so the string,
                    # metadata mirror and derived ``plan_mode_active`` flag
                    # stay consistent, then broadcast ``mode_changed`` so the
                    # toolbar chip / exit button appear.  When there is no
                    # explicit mode, just echo the persisted mode into config
                    # for this run WITHOUT touching the persistent slot --
                    # this avoids the old "sticky restore" bug where a one-off
                    # /plan kept replaying across every later normal message.
                    _persisted = session.metadata.get("slash_command_mode", "") or ""
                    if msg.mode and msg.mode != _persisted:
                        await self._apply_mode(ws, session, msg.mode)
                    else:
                        session.agent.config.slash_command_mode = msg.mode or _persisted
                    logger.info("[run] slash_command_mode resolved to: '%s' (msg.mode='%s', persisted='%s')",
                                session.agent.config.slash_command_mode, msg.mode, _persisted)

                    # Echo the persisted slash *command* into config for this
                    # run so its ``command_instructions`` block is re-injected.
                    # Activation/clearing is handled by the dedicated
                    # ``set_command`` message; here we only keep the in-memory
                    # mirror in sync with the persisted slot (e.g. after a
                    # session switch where config was not yet restored).
                    if not getattr(session.agent.config, "active_command", None):
                        session.agent.config.active_command = (
                            session.metadata.get("active_command") or None
                        )

                    session.agent.add_message("user", prompt, mode=session.agent.config.slash_command_mode)
                    # Immediately update the in-memory index and broadcast so
                    # the sidebar shows the new entry before the model responds.
                    if not session.agent.session.metadata.get("temp_chat"):
                        self._manager._index_add(session)
                        self._broadcast_sessions()
                        # Persist to disk in the background (non-blocking).
                        self._manager._schedule_save(session)
                    logger.info("[run] session=%s workspace=%s", session.session_id[:8], self._workspace_path or "(none)")

                    # Auto-name: fire-and-forget so conversation is not delayed.
                    sess = session.agent.session
                    current_name = session.metadata.get("name", "") or sess.metadata.get("name", "")
                    if current_name.startswith("未命名") and sess.turn_count <= 1:
                        _sid = session.session_id
                        _p = prompt
                        _t = asyncio.ensure_future(self._auto_name_and_rename(session, _p))
                        self._tasks.add(_t)

                    # Don't block on background code index -- let the agent run
                    # immediately. The code index becomes available asynchronously.
                    if self._index_manager and self._current_ws_id:
                        task = self._index_manager.get_task(self._current_ws_id)
                        if task and not task.done():
                            logger.info("[run] index still building, running agent without full index")

                    # Wire the engine-install requester's immediate emit
                    # hook so the desktop dialog pops up the moment a
                    # browser / desktop action needs the engine, without
                    # waiting for the agent's event loop to tick.
                    async def _emit_engine(evt: Any, session=session) -> None:
                        try:
                            await self._dispatch_event(ws, session, evt)
                        except Exception as exc:
                            logger.warning("engine emit failed: %s", exc)
                    try:
                        session.agent.set_engine_emit(_emit_engine)
                    except Exception:
                        logger.debug("agent has no set_engine_emit", exc_info=True)

                    # Snapshot the active_command before the task is created
                    # so the _run_agent closure captures it by value, not by
                    # reference, avoiding the race with the frontend's
                    # set_command clear message.
                    _active_command = getattr(session.agent.config, "active_command", None)

                    async def _run_agent(*, session=session, prompt=prompt, system_prompt=system_prompt, mode_prompt=mode_prompt, _saved_command=_active_command):
                        try:
                            # Restore active_command that may have been cleared
                            # by the frontend's set_command clear message (sent
                            # right after the run message, creating a race).
                            if _saved_command and not getattr(session.agent.config, "active_command", None):
                                session.agent.config.active_command = _saved_command
                            async for event in session.agent.run(
                                prompt=prompt, system_prompt=system_prompt,
                                custom_instructions=mode_prompt):
                                await self._dispatch_event(ws, session, event)
                                # Mid-turn checkpoint & real-time canvas update
                                if isinstance(event, ToolResult | AssistantBoundary):
                                    # Push context usage to canvas panel so the
                                    # progress bar updates in real time
                                    ctx_msgs = session.agent.session.get_context_messages()
                                    ctx_tokens = count_message_tokens(ctx_msgs)
                                    window = session.agent.loop.backend.context_window_size() if session.agent.loop.backend else 0
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
                                        with contextlib.suppress(Exception):
                                            await self._manager._save_session_async(session)
                        except asyncio.CancelledError:
                            await self._send(ws, "finish", reason="cancelled", session_id=session.session_id)
                        except Exception as e:
                            logger.error(f"Agent run failed: {e}\n{traceback.format_exc()}")
                            from encre.backends.base import format_backend_error
                            from encre.errors import classify_error_code
                            err_msg = format_backend_error(e)
                            err_code = classify_error_code(err_msg).value
                            with contextlib.suppress(Exception):
                                await self._send(ws, "error", message=err_msg, code=err_code, category="unknown", retryable=False, details={}, session_id=session.session_id)
                            with contextlib.suppress(Exception):
                                await self._send(ws, "finish", reason="error", error_code=err_code, session_id=session.session_id)
                        finally:
                            # One-shot commands: clear the active command after
                            # the run completes so it is not re-injected on the
                            # next turn.  The frontend also sends a set_command
                            # clear message, but this inline clear is the
                            # authoritative one-shot guarantee.
                            if _saved_command and _saved_command.get("name"):
                                try:
                                    session.agent.loop.clear_command()
                                except Exception:
                                    pass
                            if session.agent.telemetry.enabled:
                                with contextlib.suppress(Exception):
                                    summary = session.agent.telemetry.get_summary()
                                    await self._send(ws, "telemetry", data=summary, session_id=session.session_id)
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
                    session.agent.loop.approve_plan(msg.proposal_id) if msg.approved else session.agent.loop.reject_plan(msg.proposal_id)

                elif isinstance(msg, ClientSetPlanMode):
                    session = (
                        self._manager.get_session(self._current_session_id)
                        if self._current_session_id else None
                    )
                    if session is None:
                        session = self._get_or_create_session()
                    self._manager.touch(session.session_id)
                    # Legacy ``set_plan_mode``: map the boolean onto the
                    # unified mode state via the single entry point and
                    # broadcast ``mode_changed``/``plan_mode_changed`` so the
                    # frontend toolbar chip and plan panel stay in sync (this
                    # path previously mutated the bool without notifying).
                    await self._apply_mode(ws, session, "plan" if msg.active else "")

                elif isinstance(msg, ClientSetMode):
                    sid = msg.session_id or self._current_session_id
                    session = (
                        self._manager.get_session(sid)
                        if sid else None
                    )
                    if session is None:
                        session = self._get_or_create_session()
                    self._manager.touch(session.session_id)
                    logger.info("[set_mode] received mode='%s' session=%s",
                                msg.mode, session.session_id[:8])
                    # Drive every persistent-mode change through the single
                    # entry point.  ``_apply_mode`` normalises the value,
                    # updates config + metadata mirror + derived flag, and
                    # broadcasts ``mode_changed`` / ``plan_mode_changed`` so
                    # the desktop toolbar chip and plan panel reflect it.
                    _mode = await self._apply_mode(ws, session, msg.mode)
                    if not _mode:
                        logger.info("[set_mode] mode cleared for session=%s", session.session_id[:8])

                elif isinstance(msg, ClientSetCommand):
                    sid = msg.session_id or self._current_session_id
                    session = (
                        self._manager.get_session(sid)
                        if sid else None
                    )
                    if session is None:
                        session = self._get_or_create_session()
                    self._manager.touch(session.session_id)
                    # Activate / clear the sticky slash command through the
                    # single entry point.  Stores the command in config +
                    # session.metadata so it survives restart, re-injects its
                    # ``command_instructions`` block every turn, and broadcasts
                    # ``command_changed`` so the command chip stays in sync.
                    await self._apply_command(
                        ws, session, msg.name, msg.prompt, msg.icon, msg.title,
                    )

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
                        await self._send(ws, "finish", reason="cancelled", session_id=session.session_id)
                    else:
                        session.is_running = False
                        self._manager.release_slot()
                        await self._send(ws, "finish", reason="cancelled", session_id=session.session_id)

                elif isinstance(msg, ClientSteer):
                    sid = msg.session_id or self._current_session_id or ""
                    if sid:
                        info = self._manager.get_session(sid)
                    else:
                        info = self._get_or_create_session()
                    if info and info.agent and info.agent.loop:
                        info.agent.loop._steer_queue.push(msg.prompt or "")
                        logger.info("[steer] queued instruction for session=%s", info.session_id)
                        await self._send(ws, "steer_queued", session_id=info.session_id)
                    else:
                        await self._send(ws, "steer_queued", session_id=sid, error="no_active_session")

                elif isinstance(msg, ClientSpecApprove):
                    self._spec_engine.approve()
                    spec = self._spec_engine.current_spec
                    if spec:
                        logger.info("[spec] approved by user")
                        await self._send(ws, "spec_update",
                                         spec=spec.to_dict() if spec else None,
                                         status="approved",
                                         session_id=msg.session_id or self._current_session_id or "")

                elif isinstance(msg, ClientSpecReject):
                    self._spec_engine.reject(feedback=msg.feedback or "")
                    spec = self._spec_engine.current_spec
                    if spec:
                        logger.info("[spec] rejected by user: %s", msg.feedback[:80] if msg.feedback else "(no feedback)")
                        await self._send(ws, "spec_update",
                                         spec=spec.to_dict() if spec else None,
                                         status="rejected",
                                         feedback=msg.feedback or "",
                                         session_id=msg.session_id or self._current_session_id or "")

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
                    # Ship the session's active command (if any) so the
                    # frontend can render the command chip on connect /
                    # config refresh.
                    config_data["active_command"] = (
                        getattr(info.agent.config, "active_command", None)
                        or info.agent.session.metadata.get("active_command")
                    )
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
                            if info.agent.config.active_model_index >= len(info.agent.config.models):
                                info.agent.config.active_model_index = max(0, len(info.agent.config.models) - 1)
                            if info.agent.config.models:
                                info.agent.config.apply_active_model()
                                info.agent.rebuild_backend()
                            # Sync to _default_config
                            self._default_config.models = info.agent.config.models
                            self._default_config.active_model_index = info.agent.config.active_model_index
                            if info.agent.config.models:
                                self._default_config.apply_active_model()
                            self._persist_config(info)
                            cfg_models = info.agent.config.models
                            models_dict = _inject_context_windows([
                                m.to_dict(encrypt_api_keys=False) if isinstance(m, ModelConfig) else m
                                for m in cfg_models
                            ])
                            await self._send(ws, "models_updated",
                                models=models_dict, active_model_index=info.agent.config.active_model_index)
                            logger.info("[delete_model] done, remaining=%d", len(cfg_models))
                        else:
                            logger.warning("[delete_model] invalid index %d (max %d)",
                                           msg.model_index, len(info.agent.config.models))
                            await self._send(ws, "error",
                                message="Invalid model index", code="invalid_index")
                    except Exception as exc:
                        logger.error("[delete_model] failed: %s\n%s", exc, traceback.format_exc())
                        await self._send(ws, "error", message=f"Delete model failed: {exc}", code="handler_error")

                elif isinstance(msg, ClientFetchModels):
                    from encre.backend import create_backend
                    from encre.backends.base import format_backend_error
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
                                message=format_backend_error(e, "Failed to fetch models:"),
                                code="api_error")
                        finally:
                            await backend.aclose()
                        if model_ids:
                            await self._send(ws, "models_fetched", models=model_ids)

                elif isinstance(msg, ClientValidateModel):
                    from encre.backend import create_backend
                    from encre.backends.base import format_backend_error
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
                        validated = False
                        try:
                            async for _ in backend.chat(
                                messages=[{"role": "user", "content": "hi"}],
                                max_tokens=msg.max_tokens,
                                stream=False,
                            ):
                                pass
                            validated = True
                        except Exception as e:
                            # Validation failed — report it and keep the
                            # connection alive (do NOT return, which would tear
                            # down the whole WebSocket and lose this message).
                            await self._send(ws, "model_validation_error",
                                message=format_backend_error(e, "Validation failed:"))
                        finally:
                            await backend.aclose()

                        if validated:
                          try:
                            # Validation passed — persist the model authoritatively
                            # in THIS single round-trip and echo the full list via
                            # models_updated.  The frontend syncs its state from that
                            # echo, so there is no fragile second update_models
                            # message that can be lost if the WebSocket goes away.
                            info = self._get_or_create_session()
                            self._manager.touch(info.session_id)
                            cfg = info.agent.config
                            new_model = ModelConfig(
                                name=msg.name or msg.model_id,
                                model_id=msg.model_id,
                                backend_type=msg.backend_type,
                                api_key=msg.api_key,
                                base_url=msg.base_url,
                                max_tokens=msg.max_tokens or 4096,
                                context_window=0,
                                enabled=True,
                                multimodal=msg.multimodal,
                                thinking_config=_thinking_config_from_dict(msg.thinking_config) if msg.thinking_config else None,
                            )
                            if 0 <= msg.model_index < len(cfg.models):
                                # Edit: replace the exact entry the user opened and
                                # keep the current active selection.
                                cfg.models[msg.model_index] = new_model
                                active_idx = cfg.active_model_index
                            else:
                                # Add: collapse onto an existing identical model
                                # (same backend + model_id + base_url) rather than
                                # appending a duplicate when re-validated.
                                existing_idx = next(
                                    (i for i, m in enumerate(cfg.models)
                                     if m.backend_type == msg.backend_type
                                     and m.model_id == msg.model_id
                                     and (m.base_url or "") == (msg.base_url or "")),
                                    None,
                                )
                                if existing_idx is not None:
                                    cfg.models[existing_idx] = new_model
                                    active_idx = existing_idx
                                else:
                                    cfg.models.append(new_model)
                                    active_idx = len(cfg.models) - 1
                            cfg.active_model_index = active_idx
                            cfg.apply_active_model()
                            # Sync to _default_config so new sessions pick it up.
                            self._default_config.models = list(cfg.models)
                            self._default_config.active_model_index = active_idx
                            self._default_config.apply_active_model()
                            try:
                                info.agent.rebuild_backend()
                            except Exception as exc:
                                logger.error("[validate_model] rebuild_backend failed: %s\n%s",
                                    exc, traceback.format_exc())
                                await self._send(ws, "model_validation_error",
                                    message=f"Validation passed but backend rebuild failed: {exc}")
                                return
                            # Verify backend actually got created - if not, surface error.
                            if info.agent.loop.backend is None:
                                logger.error("[validate_model] backend is None after rebuild - config: type=%s api_key=%s base_url=%s",
                                    cfg.backend_type, bool(cfg.api_key), cfg.base_url)
                                await self._send(ws, "model_validation_error",
                                    message="Backend failed to initialize. Check backend_type/api_key/base_url.")
                                return
                            self._persist_config(info)

                            models_dict = _inject_context_windows([
                                m.to_dict(encrypt_api_keys=False) for m in cfg.models
                            ])
                            await self._send(ws, "models_updated",
                                models=models_dict, active_model_index=active_idx)
                            await self._send(ws, "model_validated",
                                backend_type=msg.backend_type,
                                model_id=msg.model_id,
                                model_index=active_idx)
                          except Exception as exc:
                            # The connection test passed but persisting failed.
                            # Surface a real error instead of letting the
                            # frontend hang until its 30s timeout.
                            logger.error("[validate_model] save failed: %s\n%s",
                                exc, traceback.format_exc())
                            await self._send(ws, "model_validation_error",
                                message=f"Validation passed but saving failed: {exc}")

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

                        if file_path and file_path.lower().endswith(".zip") and os.path.isfile(file_path):
                            self._install_skill_from_zip_file(file_path, skill_dir)
                            self._add_skill_to_index(skills_dir, msg.name, "zip")
                        elif self._looks_like_base64_zip(content):
                            self._install_skill_from_zip_data(content, skill_dir)
                            self._add_skill_to_index(skills_dir, msg.name, "zip")
                        else:
                            skill_md = skill_dir / "SKILL.md"
                            skill_md.write_text(content, encoding="utf-8")
                            self._add_skill_to_index(skills_dir, msg.name, "md")

                        info.agent.skill_registry.load_from_dir(str(skills_dir), source=SkillSource.USER)
                        available = await self._build_skills_list(info)
                        await self._send(ws, "skill_installed", name=msg.name, available_skills=available)
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
                                            m = _re.search(r"^name\s*:\s*(.+)$", text, _re.MULTILINE)
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
                        info.agent.skill_registry.load_from_dir(str(skills_dir), source=SkillSource.USER)
                        available = await self._build_skills_list(info)
                        await self._send(ws, "skill_uninstalled", name=skill_name, available_skills=available)
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
                        info.agent.skill_registry.load_from_dir(str(skills_dir), source=SkillSource.USER)
                        available = await self._build_skills_list(info)
                        await self._send(ws, "skill_installed", name=msg.name, available_skills=available)
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
                        await self._send(ws, "error", message=f"MCP update failed: {exc}", code="handler_error")

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
                        await self._send(ws, "error", message="No active session", code="no_session")
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
                    # Cancel any running agent task before rollback to prevent
                    # session state corruption (the running task's finally block
                    # could overwrite the rollback's restored state).
                    if session.agent_task and not session.agent_task.done():
                        session.is_running = False
                        session.agent.loop.cancel()
                        session.agent_task.cancel()
                        with contextlib.suppress(Exception):
                            await session.agent.loop.backend.aclose()
                        self._manager.release_slot()
                        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                            await asyncio.wait_for(session.agent_task, timeout=0.5)
                        session.agent_task = None
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
                        references=s.references,
                        user_input=user_input)

                elif isinstance(msg, ClientEditMessage):
                    session = self._get_or_create_session()
                    self._manager.touch(session.session_id)
                    try:
                        await self._edit_message(session, msg.message_index, msg.new_content)
                        msgs = [m for m in session.agent.session.messages if m.get("role") != "system"]
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
                        await self._send(ws, "error", message="Session is running, cannot delete messages", code="busy",
                                         session_id=session.session_id)
                        continue
                    try:
                        await self._delete_message(session, msg.message_index)
                        msgs = [m for m in session.agent.session.messages if m.get("role") != "system"]
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
                        await self._send(ws, "error", message="No session_id provided", code="invalid_request")
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
                        await self._send(ws, "error", message="No session_id provided", code="invalid_request")
                        continue
                    from encre.session import EncreSession
                    dir_path = self._manager._session_dir_path(msg.session_id)
                    if not dir_path.is_dir():
                        await self._send(ws, "error", message="Session not found", code="not_found")
                        continue
                    try:
                        md = EncreSession.export_to_markdown(str(dir_path))
                        name = self._manager._index.get(msg.session_id, {}).get("name", msg.session_id[:8])
                        filename = f"{name or msg.session_id[:8]}.md"
                        await self._send(ws, "session_exported", session_id=msg.session_id, markdown=md, filename=filename)
                    except Exception as e:
                        logger.error(f"Export session failed: {e}")
                        await self._send(ws, "error", message=str(e), code="export_error")

                elif isinstance(msg, ClientRenameSession):
                    if not msg.session_id or not msg.new_name.strip():
                        await self._send(ws, "error", message="Missing session_id or new_name", code="invalid_request")
                        continue
                    new_name = msg.new_name.strip()[:8]
                    ok = self._manager.rename_session(msg.session_id, new_name)
                    if ok:
                        await self._send(ws, "session_renamed", session_id=msg.session_id, new_name=new_name)
                    else:
                        await self._send(ws, "error", message="Session not found", code="not_found")

                elif isinstance(msg, ClientAgentList):
                    info = self._get_or_create_session()
                    agents = [a.to_dict() for a in info.agent.config.agents]
                    await self._send(ws, "agents_list", agents=agents, active_index=info.agent.config.active_agent_index)

                elif isinstance(msg, ClientAgentCreate):
                    info = self._get_or_create_session()
                    agent_data = dict(msg.agent)
                    agent = AgentConfig.from_dict(agent_data)
                    info.agent.config.agents.append(agent)
                    self._persist_config(info)
                    agents = [a.to_dict() for a in info.agent.config.agents]
                    await self._send(ws, "agents_updated", agents=agents, active_index=info.agent.config.active_agent_index)

                elif isinstance(msg, ClientAgentDelete):
                    info = self._get_or_create_session()
                    idx = msg.index
                    total_before = len(info.agent.config.agents)
                    logger.info("[agent_delete] index=%d, total_before=%d", idx, total_before)
                    if 0 <= idx < total_before:
                        deleted_name = info.agent.config.agents[idx].name
                        del info.agent.config.agents[idx]
                        logger.info("[agent_delete] deleted agent '%s' at index %d", deleted_name, idx)
                        if info.agent.config.active_agent_index >= len(info.agent.config.agents):
                            info.agent.config.active_agent_index = len(info.agent.config.agents) - 1
                            logger.info("[agent_delete] adjusted active_agent_index to %d", info.agent.config.active_agent_index)
                        self._persist_config(info)
                    else:
                        logger.warning("[agent_delete] invalid index %d (total=%d)", idx, total_before)
                    agents = [a.to_dict() for a in info.agent.config.agents]
                    await self._send(ws, "agents_updated", agents=agents, active_index=info.agent.config.active_agent_index)
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
                    await self._send(ws, "agents_updated", agents=agents, active_index=info.agent.config.active_agent_index)

                elif isinstance(msg, ClientAgentSetActive):
                    info = self._get_or_create_session()
                    idx = msg.index
                    if -1 <= idx < len(info.agent.config.agents):
                        info.agent.config.active_agent_index = idx
                        self._persist_config(info)
                    agents = [a.to_dict() for a in info.agent.config.agents]
                    await self._send(ws, "agents_updated", agents=agents, active_index=info.agent.config.active_agent_index)

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
                        logger.error("[update_sub_agents] failed: %s\n%s", exc, traceback.format_exc())
                        await self._send(ws, "error", message=f"Sub agents update failed: {exc}", code="handler_error")

                elif isinstance(msg, ClientOpenWorkspace):
                    folder_path = os.path.abspath(os.path.expanduser(msg.path))
                    if not os.path.isdir(folder_path):
                        await self._send(ws, "error", message="Folder not found", code="invalid_path")
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
                        info = existing if existing is not None else self._manager.create_session(config=ws_config)
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
                        cached_status = self._index_manager.get_status(ws_id) if hasattr(self._index_manager, "get_status") else {}
                        if cached_status.get("status") == "ready":
                            idx_status = "ready"
                            idx_files = cached_status.get("files", 0)
                        else:
                            task = self._index_manager.get_task(ws_id) if hasattr(self._index_manager, "get_task") else None
                            if task is not None and not task.done():
                                idx_status = "indexing"
                    await self._send(ws, "workspace_opened",
                        path=folder_path, name=os.path.basename(folder_path),
                        id=ws_id, workspaces=workspaces,
                        index_status=idx_status, index_files=idx_files)

                    sess = info.agent.session
                    sess.rebuild_artifacts_from_messages()
                    msgs = self._renderer_session_messages(sess)
                    branches_list = [b.__dict__ for b in sess.branches.values()]
                    await self._send(ws, "session_ready", session_id=info.session_id, messages=msgs,
                                     plan_items=sess.plan_items, artifacts=sess.artifacts, references=sess.references,
                                     branches=branches_list, active_branch_id=sess.active_branch_id,
                                     request_id=msg.request_id)
                    await self._send_session_mode(ws, info)
                    await self._send_session_command(ws, info)
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
                    ws_id = removed_ws["id"] if removed_ws and removed_ws.get("id") else _make_workspace_id(msg.path)
                    ws_dir = _get_workspace_dir(ws_id)
                    if os.path.isdir(ws_dir):
                        shutil.rmtree(ws_dir, ignore_errors=True)
                    await self._send(ws, "workspace_removed", path=msg.path, workspaces=workspaces)

                elif isinstance(msg, ClientCloseWorkspace):
                    # Unsubscribe from index progress but do NOT cancel -- indexing
                    # continues in the background service even without a WS connection.
                    if self._index_manager and self._current_ws_id and self._index_progress_callback:
                        self._index_manager.unsubscribe(self._current_ws_id, self._index_progress_callback)
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
                        info = existing if existing is not None else self._manager.create_session(config=clean_config)
                    else:
                        info = self._manager.create_session(config=clean_config)
                    self._info = info
                    self._current_session_id = info.session_id
                    self._manager.touch(info.session_id)
                    self._persist_config(info)
                    await self._send(ws, "workspace_closed")
                    sess = info.agent.session
                    sess.rebuild_artifacts_from_messages()
                    msgs = self._renderer_session_messages(sess)
                    branches_list = [b.__dict__ for b in sess.branches.values()]
                    await self._send(ws, "session_ready", session_id=info.session_id, messages=msgs,
                                     plan_items=sess.plan_items, artifacts=sess.artifacts, references=sess.references,
                                     branches=branches_list, active_branch_id=sess.active_branch_id,
                                     request_id=msg.request_id)
                    await self._send_session_mode(ws, info)
                    await self._send_session_command(ws, info)

                elif isinstance(msg, ClientGetMemoryList):
                    from encre.config import get_data_dir
                    from encre.crypto import decrypt as _decrypt
                    mem_dir = get_data_dir() / "memory"
                    entries: list[dict[str, Any]] = []
                    if mem_dir.is_dir():
                        for fpath in sorted(mem_dir.glob("*.md"), key=lambda p:
                            p.stat().st_mtime, reverse=True):
                            # Hide the internal profile file (_profile.md) from
                            # the settings UI. It is still loaded by the system;
                            # just not shown. Match by the fixed filename so
                            # other files starting with "_" or "." are unaffected.
                            if fpath.name == "_profile.md":
                                continue
                            try:
                                raw = fpath.read_text("utf-8")
                                # Decrypt memory files (all encrypted by default)
                                content = raw
                                if raw.strip() and not raw.strip().startswith("---") and not raw.strip().startswith("#"):
                                    with contextlib.suppress(Exception):
                                        content = _decrypt(raw)
                                meta = self._parse_memory_frontmatter(raw) if "---" in raw else None
                                if not meta:
                                    meta = self._parse_memory_frontmatter(content) if "---" in content else None
                                entry: dict[str, Any] = {
                                    "name": fpath.stem,
                                    "path": str(fpath.relative_to(mem_dir)),
                                    "size": fpath.stat().st_size,
                                    "modified": fpath.stat().st_mtime,
                                    "preview": content[:200].replace("\n", " ").strip(),
                                }
                                if meta:
                                    entry["title"] = meta.get("title", "")
                                    entry["tags"] = list(meta.get("tags", [])) if isinstance(meta.get("tags"), list | tuple) else []
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
                    if not str(file_path).startswith(str(mem_dir.resolve())) or not file_path.is_file():
                        await self._send(ws, "memory_detail", path=msg.path, content="", error="File not found or access denied")
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
                    ws_path = self._workspace_path or self._default_config.workspace if self._default_config else ""
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
                    if not str(rule_path).startswith(str(rules_dir.resolve())) or not rule_path.is_file():
                        await self._send(ws, "global_rule_content", name=msg.name, content="", error="File not found")
                    else:
                        try:
                            content = rule_path.read_text("utf-8")
                            await self._send(ws, "global_rule_content", name=msg.name, content=content)
                        except Exception as e:
                            await self._send(ws, "global_rule_content", name=msg.name, content="", error=str(e))

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
                                self._index_manager.unsubscribe(self._current_ws_id, self._index_progress_callback)
                            self._index_progress_callback = self._make_index_callback(ws)
                            self._index_manager.subscribe(self._current_ws_id, self._index_progress_callback)
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
                                await self._send(ws, "gitignore_content", path=gitignore_path, content=content)
                            except Exception as e:
                                await self._send(ws, "gitignore_content", path=gitignore_path, content=f"# Error reading .gitignore: {e}")
                        else:
                            await self._send(ws, "gitignore_content", path=gitignore_path, content="")

                elif isinstance(msg, ClientSetGitignore):
                    if self._workspace_path:
                        yim_dir = os.path.join(self._workspace_path, ".encre")
                        gitignore_path = os.path.join(yim_dir, ".gitignore")
                        os.makedirs(yim_dir, exist_ok=True)
                        try:
                            with open(gitignore_path, "w", encoding="utf-8") as f:
                                f.write(msg.content)
                            await self._send(ws, "gitignore_content", path=gitignore_path, content=msg.content)
                        except Exception as e:
                            await self._send(ws, "error", message=f"Failed to save .gitignore: {e}")

                elif isinstance(msg, ClientDeleteIndex):
                    if not self._workspace_path or not self._index_manager:
                        await self._send(ws, "index_status", files=0, status="no_workspace")
                    else:
                        try:
                            self._index_manager.delete_index(self._current_ws_id, self._workspace_path)
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
                            _t = asyncio.ensure_future(self._crawl_and_update(ws, mgr, doc, msg.url))
                            self._tasks.add(_t)
                        else:
                            await self._send(ws, "document_error", message="Either file_path or url is required")
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
                        resume_config = replace(self._default_config, workspace=self._workspace_path)
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
                    session.agent.session.metadata["channel"] = "iwork" if self._workspace_path else "normal"
                    # Reconcile is_running from the actual task state -- if the
                    # task is still alive, the session is definitely running even
                    # if the finally block has not fired yet.
                    if session.agent_task is not None and not session.agent_task.done():
                        session.is_running = True
                    sess = session.agent.session
                    sess.mark_messages_dirty()
                    sess.rebuild_artifacts_from_messages()
                    msgs = self._renderer_session_messages(sess)
                    branches_list = [b.__dict__ for b in sess.branches.values()]
                    await self._send(ws, "session_ready", session_id=session.session_id, messages=msgs,
                                     plan_items=sess.plan_items, artifacts=sess.artifacts, references=sess.references,
                                     branches=branches_list, active_branch_id=sess.active_branch_id,
                                     is_running=session.is_running, request_id=msg.request_id)
                    await self._send_session_mode(ws, session)
                    await self._send_session_command(ws, session)

                elif isinstance(msg, ClientIclawResume):
                    logger.info("[iclaw] resume requested")
                    router = self._adapter_manager.router if self._adapter_manager else None
                    if router:
                        async with router.iclaw_context():
                            existing = router.session_manager.try_resume_most_recent(
                                config=replace(self._default_config, workspace=""))
                            if existing is not None:
                                msgs = self._renderer_session_messages(existing.agent.session)
                                self._current_session_id = existing.session_id
                                await self._send(ws, "session_ready",
                                    session_id=existing.session_id, messages=msgs)
                                logger.info("[iclaw] resume sent session_ready with %d messages sid=%s",
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
                                shells.append({"name": os.path.basename(sp), "path": sp, "args": []})
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
                        await self._send(ws, "error", message=f"Terminal spawn failed: {e}", code="terminal_error")
                        continue
                    tid = self._term_seq
                    self._term_seq += 1
                    term_info: dict[str, Any] = {"proc": proc, "buf": b""}
                    self._term_sessions[tid] = term_info
                    await self._send(ws, "terminal_spawned", id=tid)

                    async def _read_stdout(*, proc=proc, term_info=term_info, tid=tid):
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

                    _t = asyncio.ensure_future(_read_stdout())
                    self._tasks.add(_t)

                elif isinstance(msg, ClientTerminalWrite):
                    tinfo = self._term_sessions.get(msg.id)
                    if tinfo is None:
                        await self._send(ws, "error", message="Terminal not found", code="terminal_not_found")
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
                        await self._send(ws, "error", message="No active session", code="no_session")
                        continue
                    info = self._manager.get_session(sid)
                    if info is None:
                        info = self._manager.load_or_create_session(sid, config=self._default_config)
                    self._manager.touch(sid)
                    sess = info.agent.session
                    mode = getattr(msg, "mode", "normal")
                    # Save the old assistant content BEFORE branching, so we can
                    # pass it as context for detailed/concise retry.
                    old_assistant_content = None
                    if mode in ("detailed", "concise"):
                        branch_msgs = sess.get_branch_messages(sess.active_branch_id)
                        user_count = 0
                        for i, m in enumerate(branch_msgs):
                            if m.get("role") == "user":
                                if user_count == msg.user_message_index:
                                    for j in range(i + 1, len(branch_msgs)):
                                        if branch_msgs[j].get("role") == "assistant":
                                            old_raw = branch_msgs[j].get("content", "")
                                            if isinstance(old_raw, list):
                                                texts = [
                                                    b.get("text", "")
                                                    for b in old_raw
                                                    if isinstance(b, dict) and b.get("type") == "text"
                                                ]
                                                old_assistant_content = " ".join(texts)
                                            else:
                                                old_assistant_content = str(old_raw)
                                            break
                                    break
                                user_count += 1
                    try:
                        user_msg, _new_branch = sess.retry_at_user_index(msg.user_message_index)
                    except ValueError as e:
                        await self._send(ws, "error", message=str(e), code="retry_error",
                                         session_id=sid)
                        continue
                    # Retry invalidates the compact summary: the conversation
                    # diverges at this point, so the old summary (which
                    # summarised the previous branch's "future") is now
                    # misleading.  Clear it so the next compact regenerates
                    # from the new branch's state.
                    sess.metadata.pop("user_requirements_summary", None)
                    # Notify frontend about the new branch so the branch switcher updates.
                    branches_list = [b.__dict__ for b in sess.branches.values()]
                    # Send the correct messages for the new branch so the frontend
                    # can render only the active branch's messages.
                    msgs = self._renderer_session_messages(sess)
                    await self._send(ws, "branch_updated",
                        session_id=sid,
                        active_branch_id=sess.active_branch_id,
                        branches=branches_list,
                        messages=msgs)
                    if user_msg:
                        if mode == "detailed" and old_assistant_content:
                            user_msg += f"\n\nBelow is my previous response — please rewrite it to be more detailed and thorough, expanding on all points with deeper explanations:\n\n{old_assistant_content}"
                        elif mode == "concise" and old_assistant_content:
                            user_msg += f"\n\nBelow is my previous response — please rewrite it to be more concise, keeping only the essential information:\n\n{old_assistant_content}"
                        elif mode == "detailed":
                            user_msg += "\n\n(Please provide a more detailed response with thorough explanations and comprehensive coverage.)"
                        elif mode == "concise":
                            user_msg += "\n\n(Please provide a concise response, keeping it brief and to the point.)"
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

                        async def _run_retry(session_id: str, prompt: str, info=info):
                            try:
                                async for event in info.agent.run(prompt=prompt):
                                    await self._dispatch_event(ws, info, event)
                                    if isinstance(event, ToolResult | AssistantBoundary):
                                        with contextlib.suppress(Exception):
                                            await self._manager._save_session_async(info)
                            except asyncio.CancelledError:
                                await self._send(ws, "finish", reason="cancelled", session_id=session_id)
                            except Exception as e:
                                logger.error(f"Retry run failed: {e}\n{traceback.format_exc()}")
                                with contextlib.suppress(Exception):
                                    await self._send(ws, "error", message=str(e), code="execution_error", session_id=session_id)
                                with contextlib.suppress(Exception):
                                    await self._send(ws, "finish", reason="error", session_id=session_id)
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
                                         session_id=sid)

                elif isinstance(msg, ClientSwitchBranch):
                    sid = msg.session_id or self._current_session_id
                    if not sid:
                        await self._send(ws, "error", message="No active session", code="no_session")
                        continue
                    info = self._manager.get_session(sid)
                    if info is None:
                        info = self._manager.load_or_create_session(sid, config=self._default_config)
                    self._manager.touch(sid)
                    sess = info.agent.session
                    if msg.branch_id not in sess.branches:
                        await self._send(ws, "error", message=f"Branch not found: {msg.branch_id}", code="branch_not_found",
                                         session_id=sid)
                        continue
                    sess.switch_branch(msg.branch_id)
                    msgs = self._renderer_session_messages(sess)
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
                        await self._send(ws, "error", message="No active session", code="no_session")
                        continue
                    info = self._manager.get_session(sid)
                    if info is None:
                        info = self._manager.load_or_create_session(sid, config=self._default_config)
                    self._manager.touch(sid)
                    # Cancel any running agent task before rollback to prevent
                    # session state corruption.
                    if info.agent_task and not info.agent_task.done():
                        info.is_running = False
                        info.agent.loop.cancel()
                        info.agent_task.cancel()
                        with contextlib.suppress(Exception):
                            await info.agent.loop.backend.aclose()
                        self._manager.release_slot()
                        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
                            await asyncio.wait_for(info.agent_task, timeout=0.5)
                        info.agent_task = None
                    self._info = info
                    self._current_session_id = sid
                    sess = info.agent.session
                    removed, target_branch_id = sess.rollback_to(msg.branch_id, msg.message_id)
                    if not removed and target_branch_id == msg.branch_id:
                        await self._send(ws, "error", message="Message not found", code="rollback_error",
                                         session_id=sid)
                        continue
                    # Rollback restores the conversation to a previous state.
                    # The compact summary (which summarised "future" work) is
                    # now misleading — clear it so the next compact regenerates.
                    sess.metadata.pop("user_requirements_summary", None)
                    # rollback_to keeps the target message but the frontend
                    # removes it locally (its content goes into the input box
                    # for re-editing).  Remove it here too so that a page
                    # refresh does NOT resurrect the rolled-back message.
                    sess.messages = [
                        m for m in sess.messages
                        if not (
                            m.get("branch_id") == target_branch_id
                            and (
                                m.get("id", "").endswith(":M:" + msg.message_id)
                                or m.get("id") == msg.message_id
                            )
                        )
                    ]
                    try:
                        _t = asyncio.ensure_future(self._manager._save_session_async(info))
                        self._tasks.add(_t)
                    except Exception:
                        pass
                    msgs = self._renderer_session_messages(sess)
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
                        await self._send(ws, "error", message="Scheduler not available", code="no_scheduler")
                        continue
                    try:
                        agent_config = None
                        if self._default_config and 0 <= msg.model_index < len(self._default_config.models):
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
                        await self._send(ws, "error", message="Scheduler not available", code="no_scheduler")
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
                        await self._send(ws, "error", message="Scheduler not available", code="no_scheduler")
                        continue
                    running = self._scheduler.toggle_job(msg.job_id)
                    if running is not None:
                        await self._send(ws, "automation_job_toggled", job_id=msg.job_id, running=running)
                    else:
                        await self._send(ws, "error",
                            message="Job not found", code="job_not_found")

                elif isinstance(msg, ClientAutomationUpdateJob):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    if self._scheduler is None:
                        await self._send(ws, "error", message="Scheduler not available", code="no_scheduler")
                        continue
                    agent_config = None
                    if self._default_config and 0 <= msg.model_index < len(self._default_config.models):
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
                        await self._send(ws, "error", message="Scheduler not available", code="no_scheduler")
                        continue
                    ok = self._scheduler.delete_job(msg.job_id)
                    if ok:
                        # The scheduler keeps execution history separately from
                        # job definitions. Broadcast the new job list together
                        # with that retained history immediately.
                        self.broadcast_automation_update()
                        await self._send(ws, "automation_job_deleted", job_id=msg.job_id)
                    else:
                        await self._send(ws, "error",
                            message="Job not found", code="job_not_found")

                elif isinstance(msg, ClientAutomationDeleteExecution):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    if self._scheduler is None:
                        await self._send(ws, "error", message="Scheduler not available", code="no_scheduler")
                        continue
                    sid = self._scheduler.delete_job_execution(msg.entry_id)
                    if sid:
                        # Clean up sub-agent session directory if it exists
                        sub_agent_dir = _get_data_dir() / "sub_agents" / sid
                        if sub_agent_dir.is_dir():
                            shutil.rmtree(str(sub_agent_dir))
                        self.broadcast_automation_update()
                        await self._send(ws, "automation_execution_deleted", entry_id=msg.entry_id)
                    else:
                        await self._send(ws, "error",
                            message="Execution not found", code="execution_not_found")

                elif isinstance(msg, ClientAutomationRenameExecution):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    if self._scheduler is None:
                        await self._send(ws, "error", message="Scheduler not available", code="no_scheduler")
                        continue
                    new_name = (msg.new_name or "").strip()
                    if not new_name:
                        await self._send(ws, "error", message="Name cannot be empty", code="invalid_request")
                        continue
                    ok = self._scheduler.rename_job_execution(msg.entry_id, new_name)
                    if ok:
                        self.broadcast_automation_update()
                        await self._send(ws, "automation_execution_renamed", entry_id=msg.entry_id, new_name=new_name)
                    else:
                        await self._send(ws, "error",
                            message="Execution not found", code="execution_not_found")

                elif isinstance(msg, ClientAutomationGetHistory):
                    info = self._get_or_create_session()
                    self._manager.touch(info.session_id)
                    if self._scheduler is None:
                        await self._send(ws, "automation_job_history", history=[])
                        continue
                    await self._send(
                        ws,
                        "automation_job_history",
                        history=self._build_automation_history(),
                    )

                elif isinstance(msg, ClientGetUsageStats):
                    try:
                        from encre.telemetry import EncreTelemetry
                        stats = EncreTelemetry.get_all_sessions_usage()
                        # Build model_id → display_name mapping from the CURRENT
                        # config.  Sessions whose model is no longer configured
                        # keep their raw model_id so historical data is never
                        # lost -- the frontend can show a "(deleted)" tag.
                        model_names: dict[str, str] = {}
                        current_model_ids: set[str] = set()
                        if self._default_config:
                            for mc in self._default_config.models:
                                mid = (mc.model_id or "").strip()
                                if mid:
                                    current_model_ids.add(mid)
                                    if mc.name:
                                        model_names[mid] = mc.name
                        # Apply display names & label sessions whose model is no
                        # longer in the config, so the user can see the model
                        # was deleted/renamed.  No session is dropped -- every
                        # historical record is preserved.
                        if stats.get("sessions"):
                            for s in stats["sessions"]:
                                raw = (s.get("model", "") or "").strip()
                                if not raw or raw == "unknown":
                                    s["model"] = "(unknown model)"
                                    s["model_status"] = "unknown"
                                elif raw in model_names:
                                    s["model"] = model_names[raw]
                                    s["model_status"] = "active"
                                else:
                                    # Model is no longer in the user's config.
                                    # Keep the raw id so the historical record
                                    # is preserved and the user knows which
                                    # model it was.
                                    s["model"] = raw
                                    s["model_status"] = "deleted"
                        if stats.get("model_breakdown"):
                            mb: dict[str, dict[str, Any]] = {}
                            for raw, data in stats["model_breakdown"].items():
                                if not raw or raw == "unknown":
                                    display = "(unknown model)"
                                elif raw in model_names:
                                    display = model_names[raw]
                                else:
                                    display = raw
                                if display in mb:
                                    for k in ("input_tokens", "output_tokens", "total_tokens", "turns"):
                                        mb[display][k] = mb[display].get(k, 0) + data.get(k, 0)
                                else:
                                    mb[display] = dict(data)
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

                elif isinstance(msg, ClientReplayGetSession):
                    # Session replay: load the recorded telemetry JSONL and
                    # return the full event stream + summary + turn boundaries
                    # so the frontend can scrub through what the agent did.
                    try:
                        from encre.replay import ReplayPlayer
                        _player = ReplayPlayer(msg.session_id)
                        await self._send(ws, "replay_session",
                            session_id=msg.session_id,
                            summary=_player.summary(),
                            events=[ev.to_dict() for ev in _player.event_stream()],
                            turn_boundaries=_player.turn_boundaries(),
                        )
                    except Exception as _replay_exc:
                        logger.warning("[ws] replay failed: %s", _replay_exc, exc_info=True)
                        await self._send(ws, "replay_session",
                            session_id=getattr(msg, "session_id", ""),
                            summary={},
                            events=[],
                            turn_boundaries=[],
                            error=str(_replay_exc),
                        )

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
        active_ids = {s["session_id"] for s in result}
        for entry in self._manager.query_index():
            if entry["session_id"] in active_ids:
                continue
            if entry.get("channel", "normal") == "iwork":
                continue
            result.append(entry)
            active_ids.add(entry["session_id"])

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
                    with open(idx_file, encoding="utf-8") as f:
                        raw = f.read().strip()
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
                    with open(global_idx, encoding="utf-8") as f:
                        raw = f.read().strip()
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
        result = [s for s in result if (s.get("message_count") or 0) > 0 and s.get("channel", "normal") not in ("automation", "sub_agent")]

        # ── Workspace-channel filter ───────────────────────────────────
        expected_channel = ("iwork" if self._workspace_path else "normal") if channel_filter is None else channel_filter
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
        """Search sessions (by message content) and the workspace (by file name / content).

        Returns at most ~60 results tagged ``conversation`` or ``file`` so
        the desktop search box can jump to a past turn or a source file.
        """
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
            excluded = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "target", ".encre", ".pytest_cache", ".mypy_cache", "__pypackages__"}
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
                _t = asyncio.ensure_future(self._send(ws, "gateway_status", status=status))
                self._tasks.add(_t)
            except Exception:
                closed.append(ws)
        for ws in closed:
            self._connections.remove(ws)

    async def _poll_wechat_scan(self, ws, adapter, qrcode_token: str) -> None:
        """Poll iLink Bot QR code status in background and notify frontend."""
        try:
            result = await adapter.poll_qrcode_status(qrcode_token)
            if result:
                ilink_bot_id = result.get("ilink_bot_id", "")
                bot_token = result.get("bot_token", "")
                baseurl = result.get("baseurl", "")
                ilink_user_id = result.get("ilink_user_id", "")
                await self._send(ws, "wechat_scan_result",
                    qrcode_url="", success=True, message="",
                    scan_confirmed=True,
                    credentials={
                        "ilink_bot_id": ilink_bot_id,
                        "bot_token": bot_token,
                        "baseurl": baseurl,
                        "ilink_user_id": ilink_user_id,
                    })
                # Save credentials and start the adapter
                if self._adapter_manager and ilink_bot_id and bot_token:
                    # Clear any stale stored config for weixin
                    if hasattr(self._adapter_manager, "_stored_configs"):
                        self._adapter_manager._stored_configs.pop("weixin", None)
                    cfg = {
                        "app_id": ilink_bot_id,
                        "token": bot_token,
                        "api_url": baseurl,
                        "enabled": True,
                    }
                    await self._adapter_manager.start_adapter("weixin", cfg)
                    # Persist to adapter_configs
                    info = self._info
                    if info and hasattr(info, "agent") and hasattr(info.agent, "config"):
                        info.agent.config.adapter_configs["weixin"] = {
                            "app_id": ilink_bot_id,
                            "token": bot_token,
                            "api_url": baseurl,
                            "enabled": True,
                        }
                        if hasattr(self, "_default_config"):
                            self._default_config.adapter_configs["weixin"] = {
                                "app_id": ilink_bot_id,
                                "token": bot_token,
                                "api_url": baseurl,
                                "enabled": True,
                            }
                        self._persist_settings(info)
        except Exception as e:
            logger.warning("[wechat_scan] poll error: %s", e)
        finally:
            task = asyncio.current_task()
            if task:
                self._tasks.discard(task)

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
            logger.warning("[automation] failed to load sub-agent session %s", session_id, exc_info=True)
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

        history = self._build_automation_history()

        # Result data for frontend display -- pull messages from the
        # sub-agent session, not from JobExecution.
        result_data: dict[str, Any] | None = None
        if job and job.last_result:
            messages: list[dict[str, Any]] | None = None
            if getattr(job, "session_id", None):
                messages = self._load_sub_agent_messages(job.session_id)
                if messages:
                    try:
                        json.dumps(messages, ensure_ascii=False)
                    except (TypeError, ValueError) as e:
                        logger.warning("[automation] result messages not serializable for session %s: %s", job.session_id, e)
                        messages = None
            execution_failed = job.last_result.startswith("Error:")
            result_data = {
                "action": "failed" if execution_failed else "completed",
                "id": job.id,
                "job_id": job.id,
                "name": job.name,
                "prompt": job.prompt,
                "result": job.last_result[:2000],
                "messages": messages or [],
                "state": "FAILED" if execution_failed else job.state.name,
            }
            if execution_failed:
                # Keep raw exception text out of the UI while still providing
                # a stable code that identifies the failed automation state.
                result_data["error_code"] = "AUTOMATION_EXECUTION_FAILED"
            if getattr(job, "session_id", None):
                result_data["session_id"] = job.session_id

        # ── Push result through configured gateways ─────────────────
        if job and job.last_result and hasattr(job, "push_gateways") and job.push_gateways and self._adapter_manager:
            # Route through the DeliveryRouter for unified truncation + audit
            # (aligns with Hermes delivery.py).  Each entry in push_gateways is
            # either "platform:chat_id" (explicit chat) or a bare adapter id
            # (resolved to the adapter's default push target).
            push_text = f"🤖 {job.name}\n\n{job.last_result}"
            try:
                router = self._adapter_manager.delivery
                self._tasks.add(asyncio.create_task(
                    router.deliver(push_text, list(job.push_gateways))
                ))
                logger.debug("[automation] routed push to %s via DeliveryRouter", job.push_gateways)
            except Exception as exc:
                logger.warning("[automation] DeliveryRouter push failed: %s", exc)

        logger.debug("[broadcast_automation_update] job=%s state=%s connections=%s history_len=%s",
                    getattr(job, 'id', None) if job else None,
                    getattr(job, 'state', None) if job else None,
                    len(self._connections), len(history))
        for ws in self._connections:
            try:
                _t = asyncio.ensure_future(self._send(ws, "automation_job_update", history=history, result=result_data))
                self._tasks.add(_t)
            except Exception as exc:
                logger.warning("[broadcast_automation_update] failed to schedule send: %s", exc)
                closed.append(ws)
        for ws in closed:
            self._connections.remove(ws)

    def _build_automation_history(self) -> list[dict[str, Any]]:
        """Serialize global execution history without requiring a live job."""
        if self._scheduler is None:
            return []

        jobs = self._scheduler.list_jobs(include_finished=True)
        job_map = {job.id: job for job in jobs}
        history: list[dict[str, Any]] = []
        for execution in self._scheduler.get_execution_history():
            job = job_map.get(execution.job_id)
            entry: dict[str, Any] = {
                "id": f"{execution.job_id}_{execution.time}",
                "job_id": execution.job_id,
                "name": execution.name or (job.name if job else "Deleted automation"),
                "tag": job.metadata.get("tag", "") if job else "",
                "time": execution.time,
                "state": execution.state,
                "last_result": execution.result[:500] if execution.result else "",
                "fail_count": execution.fail_count,
                "messages": [],
            }
            if execution.state == "FAILED":
                entry["error_code"] = "AUTOMATION_EXECUTION_FAILED"
            if execution.session_id:
                entry["session_id"] = execution.session_id
                messages = self._load_sub_agent_messages(execution.session_id)
                if messages:
                    try:
                        json.dumps(messages, ensure_ascii=False)
                    except (TypeError, ValueError) as exc:
                        logger.warning(
                            "[automation] messages not serializable for session %s: %s",
                            execution.session_id,
                            exc,
                        )
                    else:
                        entry["messages"] = messages
            history.append(entry)
        history.sort(key=lambda entry: entry["time"] or 0, reverse=True)
        return history

    async def broadcast_automation_progress(self, job: Any = None, event_type: str = "", event_data: dict[str, Any] | None = None) -> None:
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
        channel = "iwork" if self._workspace_path else "normal"
        sessions = self._list_all_sessions(channel_filter=channel)
        logger.info("[broadcast] %d sessions to %d connection(s)",
                    len(sessions), len(self._connections))

        async def _try_send(ws_conn: Any, payload_sessions: list, payload_channel: str) -> None:
            """Send sessions_list to one connection without cascading to _cancel_current_task."""
            encrypt = self._client_encrypted if self._client_encrypted is not None else False
            try:
                payload = encode_server_message(
                    "sessions_list",
                    encrypt=encrypt,
                    sessions=payload_sessions,
                    channel=payload_channel,
                )
                await ws_conn.send(payload)
            except Exception as exc:
                logger.warning("[broadcast] send failed (will remove connection): %s", exc)

        closed: list[Any] = []
        for ws in self._connections:
            try:
                _t = asyncio.ensure_future(_try_send(ws, sessions, channel))
                self._tasks.add(_t)
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
            logger.error("[persist_config] Failed to persist config: %s\n%s", exc, traceback.format_exc())

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
            # First, remove stale adapter keys that are no longer in config
            adapter_ids_in_config = set()
            if cfg.adapter_configs:
                adapter_ids_in_config = set(cfg.adapter_configs.keys())
                for adapter_id, fields in cfg.adapter_configs.items():
                    for fk, fv in fields.items():
                        existing[f"adapter_{adapter_id}_{fk}"] = fv
            # Remove keys for adapters no longer in config (e.g. unbound weixin)
            stale_keys = [k for k in existing if k.startswith("adapter_") and k.split("_", 2)[1] not in adapter_ids_in_config]
            for k in stale_keys:
                existing.pop(k, None)
            if hasattr(cfg, "permission_settings") and cfg.permission_settings:
                existing["permission_settings"] = dict(cfg.permission_settings)
            logger.info("[persist_settings] saving keys: %s", list(existing.keys()))
            if existing:
                save_settings(existing)
                logger.info("[persist_settings] saved successfully")
        except Exception as exc:
            logger.warning("Failed to persist settings: %s", exc)

    @staticmethod
    def _persist_mcp_json(_info: Any, servers: list[dict[str, Any]]) -> None:
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
                _t = asyncio.ensure_future(
                    self._safe_send_index_status(ws, status, files, progress, current_file)
                )
                self._tasks.add(_t)
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

    @staticmethod
    def _truncate_name(text: str) -> str:
        """Truncate text: CJK -> first 10 chars, English -> first 5 words."""
        import re
        text = text.strip().strip('"').strip("'").strip("「").strip("」").strip("『").strip("』")
        if re.search(r'[\u4e00-\u9fff]', text):
            return text[:10]
        return ' '.join(text.split()[:5])

    async def _auto_name_session(self, session: Any, first_user_msg: str) -> str:
        """Generate a concise session name from the user's first message.
        Uses the same backend as the session's agent with a minimal prompt.
        If the call fails or times out, returns empty string (no name set)."""
        try:
            backend = session.agent.loop.backend
            if backend is None:
                logger.debug("[session] auto-name: backend is None")
                return ""
            prompt_text = first_user_msg.strip()[:500]
            if not prompt_text:
                return ""
            sys_prompt = (
                "You are a title naming assistant. Based on the user's message, "
                "generate a concise title. For Chinese: no more than 10 characters. "
                "For English: no more than 5 words. "
                "Return ONLY the title text, no quotes, no explanation, no punctuation."
            )
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
                elif isinstance(event, BackendFinish):
                    break
                elif isinstance(event, BackendError):
                    logger.debug("[session] auto-name: backend error: %s", event.error)
                    return ""
            name = self._truncate_name(full_text)
            if len(name) < 2:
                logger.debug("[session] auto-name: generated name too short: '%s'", full_text[:50])
                return ""
            return name
        except Exception as e:
            logger.warning("[session] auto-name failed: %s", e, exc_info=True)
            return ""

    async def _auto_name_and_rename(self, session: Any, prompt: str) -> None:
        """Generate a session name in the background (fire-and-forget)."""
        try:
            name = await asyncio.wait_for(
                self._auto_name_session(session, prompt), timeout=15.0)
            if name:
                # A user may rename the session while title generation is still
                # running. Never let this late background result replace it.
                live_session = self._manager.get_session(session.session_id)
                if live_session and live_session.metadata.get("name_manually_renamed"):
                    return
                self._manager.rename_session(session.session_id, name, manual=False)
                logger.info("[session] auto-named %s -> %s", session.session_id[:8], name)
                # Notify the frontend so it can update the session bar immediately.
                await self._broadcast_session_renamed(session.session_id, name)
            else:
                # Fallback: use truncated first user message as name
                fallback = self._truncate_name(prompt)
                if fallback:
                    self._manager.rename_session(session.session_id, fallback, manual=False)
                    logger.info("[session] auto-name fallback %s -> %s", session.session_id[:8], fallback)
                    await self._broadcast_session_renamed(session.session_id, fallback)
        except TimeoutError:
            logger.debug("[session] auto-name timed out (15s)")
        except Exception as e:
            logger.debug("[session] auto-name failed: %s", e, exc_info=True)

    async def _broadcast_session_renamed(self, session_id: str, new_name: str) -> None:
        """Send session_renamed to all connected clients."""
        for ws in list(self._connections):
            try:
                await self._send(ws, "session_renamed", session_id=session_id, new_name=new_name)
            except Exception:
                pass

    @staticmethod
    async def _build_skills_list(info: Any) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            registry = info.agent.skill_registry
            for name, skill in registry._skills.items():
                if getattr(skill, "hidden", False):
                    continue
                if skill.source in ("bundled", "managed"):
                    continue
                entry: dict[str, Any] = {
                    "name": name,
                    "description": skill.description,
                    "aliases": skill.aliases,
                    "source": skill.source,
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
                    from encre.session import _extract_file_paths_from_messages
                    session.agent.loop.rollback.commit(
                        sess, f"before_edit_msg_{index}")
                    # Restore only file snapshots from the truncated turns;
                    # leave files touched by kept messages untouched.
                    removed_files = _extract_file_paths_from_messages(msgs[i + 1:])
                    kept_files = _extract_file_paths_from_messages(msgs[:i + 1])
                    files_to_restore = removed_files - kept_files
                    restored = sess.restore_file_snapshots_for_paths(files_to_restore)
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
                    from encre.session import _extract_file_paths_from_messages
                    session.agent.loop.rollback.commit(
                        sess, f"before_delete_msg_{index}")
                    # Restore only file snapshots from the deleted turns;
                    # leave files touched by kept messages untouched.
                    removed_files = _extract_file_paths_from_messages(msgs[i:])
                    kept_files = _extract_file_paths_from_messages(msgs[:i])
                    files_to_restore = removed_files - kept_files
                    restored = sess.restore_file_snapshots_for_paths(files_to_restore)
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
        """Translate one agent :class:`~encre.utils.types.AgentEvent` to WS frames.

        Each branch matches an event type and emits the corresponding server
        protocol message (``text_delta``, ``tool_call_start``, ``finish``,
        ``plan_update``, ``compact``, workflow events, engine-install dialogs,
        ...).  Keeps the canvas/usage panel in sync where relevant.
        """
        sid = _info.session_id if _info else None

        async def _send_agent_state() -> None:
            if _info is None:
                return
            sess = _info.agent.session
            meta = sess.metadata or {}
            await self._send(
                ws,
                "agent_state",
                state={
                    "task_stage": meta.get("task_stage", "discover"),
                    "task_stage_history": meta.get("task_stage_history", []),
                    "working_set": meta.get("working_set", {}),
                    "turn_summaries": meta.get("turn_summaries", []),
                    "delegate_history": meta.get("delegate_history", []),
                    "stuck_events": meta.get("stuck_events", []),
                    "tool_semantics": meta.get("tool_semantics", {}),
                },
                session_id=sid,
            )

        if isinstance(event, TextDelta) and event.text:
            await self._send(ws, "text_delta", text=event.text, session_id=sid)

        elif isinstance(event, ThinkingDelta) and event.text:
            await self._send(ws, "thinking_delta", text=event.text, session_id=sid)

        elif isinstance(event, ToolCallStart):
            await self._send(ws, "tool_call_start", name=event.name, id=event.id, session_id=sid)

        elif isinstance(event, ToolCallDelta):
            await self._send(ws, "tool_call_delta", id=event.id, key=event.key, value=event.value, session_id=sid)

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
            await self._send(ws, "permission_request", tool_name=event.tool_name, reason=event.reason, session_id=sid)

        elif isinstance(event, QuestionRequest):
            await self._send(ws, "question_request", tool_call_id=event.tool_call_id, questions=event.questions, session_id=sid)

        elif isinstance(event, Artifact):
            await self._send(ws, "artifacts_update", artifacts=[event.artifact], session_id=sid)

        elif isinstance(event, BackendError):
            # A backend yielded a structured error event (e.g. provider returned
            # a non-retryable 400 mid-stream).  Surface it to the UI immediately
            # so the user sees the provider's actual error message instead of a
            # generic "Error 400" once the agent loop finally unwinds.
            # Includes code/category/retryable for structured frontend rendering.
            await self._send(ws, "error",
                message=event.error,
                code=event.code or "backend_error",
                category=event.category or "unknown",
                retryable=event.retryable,
                retry_after=event.retry_after,
                details=event.details or {},
                session_id=sid)

        elif isinstance(event, Reference):
            await self._send(ws, "references_update", references=[event.reference], session_id=sid)

        elif isinstance(event, PlanUpdate):
            await self._send(ws, "plan_update", plan_items=event.plan_items, session_id=sid)
            await _send_agent_state()
            # Persist plan items asynchronously (debounced) so they survive app
            # refresh without blocking the event dispatch / subsequent WS sends.
            if _info is not None:
                _info.agent.session.plan_items = event.plan_items
                self._manager._schedule_save(_info)

        elif isinstance(event, AssistantBoundary):
            await self._send(ws, "assistant_boundary", session_id=sid)

        elif isinstance(event, CompactNotification):
            # Send the compacted message list so the frontend's state
            # matches the backend. Without this, the frontend still shows
            # compacted-away messages, leading to "Message not found"
            # errors when the user tries to rollback to them.
            compact_msgs = self._renderer_session_messages(_info.agent.session) if _info else []
            await self._send(ws, "compact",
                old_count=event.old_count,
                new_count=event.new_count,
                old_tokens=event.old_tokens,
                new_tokens=event.new_tokens,
                messages=compact_msgs,
                session_id=sid)
            await _send_agent_state()
        elif isinstance(event, SystemMessage):
            content = event.content or ""
            # Spec data rides on a SystemMessage with an ``__spec_data__:``
            # prefix (loop.py emits it after parsing a generated spec).
            # The raw JSON must NEVER reach the frontend as a visible
            # "System message" bubble -- it would render as a leaked
            # prompt-like strip at the top of the conversation.  Re-route
            # it as a proper ``spec_update`` event so the frontend renders
            # the spec card (with Approve/Reject) instead.
            if content.startswith("__spec_data__:"):
                try:
                    import json as _json
                    spec_data = _json.loads(content[len("__spec_data__:"):])
                    await self._send(ws, "spec_update",
                                     spec=spec_data,
                                     status="review",
                                     session_id=sid)
                except Exception:
                    logger.warning("[spec] failed to relay spec_update from system message", exc_info=True)
            else:
                await self._send(ws, "system_message",
                                content=content,
                                kind=event.kind,
                                session_id=sid)
            # Also push updated context usage to the canvas panel
            if _info is not None:
                ctx_msgs = _info.agent.session.get_context_messages()
                ctx_tokens = count_message_tokens(ctx_msgs)
                window = _info.agent.loop.backend.context_window_size() if _info.agent.loop.backend else 0
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
            # If compaction occurred during this turn, send the updated
            # message list so the frontend's state matches the backend.
            # Without this, compacted-away messages stay in the frontend
            # and cause "Message not found" errors on rollback.
            finish_msgs = []
            if event.compacted and _info:
                finish_msgs = self._renderer_session_messages(_info.agent.session)
            await self._send(ws, "finish", reason=event.reason, usage=event.usage,
                             error=event.error,
                             error_code=event.error_code or "",
                             error_category=event.error_category or "",
                             assistant_message_id=last_msg_id,
                             compacted=event.compacted,
                             messages=finish_msgs if finish_msgs else None,
                             session_id=sid)
            await _send_agent_state()
            # Push updated context usage so the canvas panel stays in sync
            if _info is not None:
                ctx_msgs = _info.agent.session.get_context_messages()
                ctx_tokens = count_message_tokens(ctx_msgs)
                window = _info.agent.loop.backend.context_window_size() if _info.agent.loop.backend else 0
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
    return os.environ.get("ENCRE_DATA_DIR", os.path.join(os.path.expanduser("~"), ".dunimd", "encre"))


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
            with open(idx_file, encoding="utf-8") as f:
                raw = f.read().strip()
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
                with open(idx_file, "w", encoding="utf-8") as f:
                    f.write(new_raw)
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
