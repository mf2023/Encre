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



import json
from dataclasses import dataclass, field
from typing import Any, Literal, Union

from encre.crypto import decrypt, encrypt

# ── Transport‑layer encryption wrappers ────────────────────────────

def _parse_client_encrypted(raw: str | bytes) -> str | bytes | None:
    """Decrypt an encrypted client message, returning the raw JSON string.

    If the payload is valid base64 ciphertext, decrypt it.  Otherwise
    treat the message as legacy plaintext (backwards‑compatible).
    """
    if not raw:
        return raw
    decoded = raw.decode("utf-8") if isinstance(raw, bytes) else raw

    # A valid base64 ciphertext from AES‑GCM is always at least
    # 12 (nonce) + 1 (min ciphertext) + 16 (tag) ≈ 30 bytes ≈ 40 base64 chars.
    # Messages starting with "{" are almost certainly plain JSON.
    stripped = decoded.strip()
    if not stripped:
        return decoded
    if stripped.startswith("{"):
        return decoded  # legacy plaintext

    try:
        return decrypt(stripped)
    except Exception:
        # Decryption failed -- return the raw payload so the upper
        # layer can still attempt to parse it as plaintext (or fail gracefully).
        return decoded


def encode_server_encrypted(msg_type: str, **kwargs: Any) -> str:
    """Encode and encrypt a server‑to‑client message.

    The message is serialized as JSON, encrypted via AES‑256‑GCM, and
    returned as a base64 ciphertext string.
    """
    payload = json.dumps({"type": msg_type, **kwargs}, ensure_ascii=False)
    return encrypt(payload)


def encode_server_plaintext(msg_type: str, **kwargs: Any) -> str:
    """Encode a server‑to‑client message as plain JSON (no encryption).

    Use this when the client does not have crypto capability or when
    transport encryption is not required (e.g. localhost-only deployments).
    """
    return json.dumps({"type": msg_type, **kwargs}, ensure_ascii=False)


# ── Client -> Server message types ──────────────────────────────────

ClientMessageType = Literal[
    "run", "respond_permission", "cancel", "resume", "configure", "ping",
    "list_models", "list_sessions", "new_session",
    "get_config", "update_models", "set_active_model", "delete_model",
    "fetch_models",
    "update_skills", "install_skill", "uninstall_skill", "update_skill", "update_mcp", "update_agent",  # noqa: E501
    "search",
    "rollback_log", "rollback_checkout",
    "validate_model",
    "edit_message", "delete_message",
    "delete_session", "export_session", "rename_session",
    "agent_create", "agent_delete", "agent_update", "agent_list", "agent_set_active",
    "update_sub_agents",
    "get_memory_list",
    "get_memory_detail",
    "get_global_rules",
    "get_global_rule_content",
    "save_global_rule",
    "delete_global_rule",
    "get_profile",
    "reindex_workspace",
    "get_gitignore",
    "delete_index",
    "set_gitignore",
    "terminal_spawn",
    "terminal_write",
    "terminal_resize",
    "terminal_kill",
    "terminal_list_shells",
    "retry",
    "switch_branch",
    "rollback",
    "transcribe_audio",
    "get_usage_stats",
    "automation_list_jobs",
    "automation_create_job",
    "automation_cancel_job",
    "automation_get_history",
]


@dataclass
class ClientRun:
    type: str = "run"
    prompt: str = ""
    system_prompt: str | None = None
    session_id: str | None = None
    specialty: str = "general"
    attachments: list[dict[str, Any]] | None = None
    mode: str | None = None
    mode_prompt: str | None = None
    channel: str | None = None  # "iclaw" when in iClaw mode
    temp_chat: bool = False  # True = ephemeral, never persist to disk

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientRun:
        return cls(
            type="run",
            prompt=d.get("prompt", ""),
            system_prompt=d.get("system_prompt"),
            session_id=d.get("session_id"),
            specialty=d.get("specialty", "general"),
            attachments=d.get("attachments"),
            mode=d.get("mode"),
            mode_prompt=d.get("mode_prompt"),
            channel=d.get("channel"),
            temp_chat=bool(d.get("temp_chat", False)),
        )


@dataclass
class ClientRespondPermission:
    type: str = "respond_permission"
    tool_name: str = ""
    decision: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientRespondPermission:
        return cls(
            type="respond_permission",
            tool_name=d.get("tool_name", ""),
            decision=d.get("decision", False),
        )


@dataclass
class ClientRespondPlan:
    type: str = "respond_plan"
    proposal_id: str = ""
    approved: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientRespondPlan:
        return cls(
            type="respond_plan",
            proposal_id=str(d.get("proposal_id", "")),
            approved=bool(d.get("approved", False)),
        )


@dataclass
class ClientSetPlanMode:
    type: str = "set_plan_mode"
    active: bool = False
    reason: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientSetPlanMode:
        return cls(
            type="set_plan_mode",
            active=bool(d.get("active", False)),
            reason=str(d.get("reason", "")),
        )


@dataclass
class ClientRespondQuestion:
    type: str = "respond_question"
    tool_call_id: str = ""
    answers: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientRespondQuestion:
        return cls(
            type="respond_question",
            tool_call_id=str(d.get("tool_call_id", "")),
            answers=str(d.get("answers", "")),
        )


@dataclass
class ClientEngineInstallResponse:
    type: str = "engine_install_response"
    request_id: str = ""
    choice: str = "cancelled"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientEngineInstallResponse:
        return cls(
            type="engine_install_response",
            request_id=d.get("request_id", ""),
            choice=d.get("choice", "cancelled"),
        )


@dataclass
class ClientCancel:
    type: str = "cancel"
    session_id: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientCancel:
        return cls(
            type="cancel",
            session_id=d.get("session_id", ""),
        )


@dataclass
class ClientResume:
    type: str = "resume"
    session_id: str = ""
    request_id: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientResume:
        return cls(
            type="resume",
            session_id=d.get("session_id", ""),
            request_id=d.get("request_id", ""),
        )


@dataclass
class ClientConfigure:
    type: str = "configure"
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientConfigure:
        return cls(
            type="configure",
            config=d.get("config", {}),
        )


@dataclass
class ClientTestAdapter:
    type: str = "test_adapter"
    adapter_id: str = ""
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientTestAdapter:
        return cls(
            type="test_adapter",
            adapter_id=d.get("adapter_id", ""),
            config=d.get("config", {}),
        )


@dataclass
class ClientPing:
    type: str = "ping"

    @classmethod
    def from_dict(cls, _d: dict[str, Any]) -> ClientPing:
        return cls(type="ping")


@dataclass
class ClientListModels:
    type: str = "list_models"

    @classmethod
    def from_dict(cls, _d: dict[str, Any]) -> ClientListModels:
        return cls(type="list_models")


@dataclass
class ClientListSessions:
    type: str = "list_sessions"

    @classmethod
    def from_dict(cls, _d: dict[str, Any]) -> ClientListSessions:
        return cls(type="list_sessions")


@dataclass
class ClientListAllSessions:
    """List sessions across ALL channels (normal + iwork), unfiltered.

    Used by the tray popup which needs both mode's sessions at once.
    Returns a ``sessions_all`` event with ``{normal: [...], iwork: [...]}``.
    """

    type: str = "list_all_sessions"

    @classmethod
    def from_dict(cls, _d: dict[str, Any]) -> ClientListAllSessions:
        return cls(type="list_all_sessions")


@dataclass
class ClientNewSession:
    type: str = "new_session"
    request_id: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientNewSession":
        return cls(type="new_session", request_id=d.get("request_id", ""))


@dataclass
class ClientGetConfig:
    type: str = "get_config"

    @classmethod
    def from_dict(cls, _d: dict[str, Any]) -> "ClientGetConfig":
        return cls(type="get_config")


@dataclass
class ClientUpdateModels:
    type: str = "update_models"
    models: list[dict[str, Any]] = field(default_factory=list)
    active_model_index: int = 0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientUpdateModels":
        return cls(
            type="update_models",
            models=d.get("models", []),
            active_model_index=d.get("active_model_index", 0),
        )


@dataclass
class ClientSetActiveModel:
    type: str = "set_active_model"
    model_index: int = 0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientSetActiveModel":
        return cls(
            type="set_active_model",
            model_index=d.get("model_index", 0),
        )


@dataclass
class ClientDeleteModel:
    type: str = "delete_model"
    model_index: int = 0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientDeleteModel":
        return cls(
            type="delete_model",
            model_index=d.get("model_index", 0),
        )


@dataclass
class ClientFetchModels:
    type: str = "fetch_models"
    backend_type: str = ""
    api_key: str = ""
    base_url: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientFetchModels":
        return cls(
            type="fetch_models",
            backend_type=d.get("backend_type", ""),
            api_key=d.get("api_key", ""),
            base_url=d.get("base_url", ""),
        )


@dataclass
class ClientUninstallSkill:
    type: str = "uninstall_skill"
    name: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientUninstallSkill":
        return cls(
            type="uninstall_skill",
            name=d.get("name", ""),
        )


@dataclass
class ClientUpdateSkill:
    type: str = "update_skill"
    name: str = ""
    content: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientUpdateSkill":
        return cls(
            type="update_skill",
            name=d.get("name", ""),
            content=d.get("content", ""),
        )


@dataclass
class ClientUpdateSkills:
    type: str = "update_skills"
    enabled_skills: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientUpdateSkills":
        return cls(
            type="update_skills",
            enabled_skills=d.get("enabled_skills", []),
        )


@dataclass
class ClientInstallSkill:
    type: str = "install_skill"
    name: str = ""
    content: str = ""
    file_path: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientInstallSkill":
        return cls(
            type="install_skill",
            name=d.get("name", ""),
            content=d.get("content", ""),
            file_path=d.get("file_path", ""),
        )


@dataclass
class ClientUpdateMCP:
    type: str = "update_mcp"
    # Accept either list[dict] (old format) or dict[str, dict] (standard map format)
    mcp_servers: Any = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientUpdateMCP":
        return cls(
            type="update_mcp",
            mcp_servers=d.get("mcp_servers", []),
        )


@dataclass
class ClientUpdateAgent:
    type: str = "update_agent"
    system_prompt: str = ""
    specialty: str = "general"
    permission_mode: str = ""
    max_turns: int = 0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientUpdateAgent":
        return cls(
            type="update_agent",
            system_prompt=d.get("system_prompt", ""),
            specialty=d.get("specialty", "general"),
            permission_mode=d.get("permission_mode", ""),
            max_turns=d.get("max_turns", 0),
        )


@dataclass
class ClientSearch:
    type: str = "search"
    query: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientSearch":
        return cls(
            type="search",
            query=d.get("query", ""),
        )


@dataclass
class ClientRollbackLog:
    type: str = "rollback_log"
    session_id: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientRollbackLog:
        return cls(
            type="rollback_log",
            session_id=d.get("session_id", ""),
        )


@dataclass
class ClientRollbackCheckout:
    type: str = "rollback_checkout"
    session_id: str = ""
    commit_hash: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientRollbackCheckout:
        return cls(
            type="rollback_checkout",
            session_id=d.get("session_id", ""),
            commit_hash=d.get("commit_hash", ""),
        )


@dataclass
class ClientValidateModel:
    type: str = "validate_model"
    backend_type: str = ""
    api_key: str = ""
    base_url: str = ""
    model_id: str = ""
    max_tokens: int = 4096

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientValidateModel":
        return cls(
            type="validate_model",
            backend_type=d.get("backend_type", ""),
            api_key=d.get("api_key", ""),
            base_url=d.get("base_url", ""),
            model_id=d.get("model_id", ""),
            max_tokens=d.get("max_tokens", 4096),
        )


@dataclass
class ClientEditMessage:
    type: str = "edit_message"
    message_index: int = 0
    new_content: str = ""
    session_id: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientEditMessage":
        return cls(
            type="edit_message",
            message_index=d.get("message_index", 0),
            new_content=d.get("new_content", ""),
            session_id=d.get("session_id", ""),
        )


@dataclass
class ClientDeleteMessage:
    type: str = "delete_message"
    message_index: int = 0
    session_id: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientDeleteMessage":
        return cls(
            type="delete_message",
            message_index=d.get("message_index", 0),
            session_id=d.get("session_id", ""),
        )


@dataclass
class ClientDeleteSession:
    type: str = "delete_session"
    session_id: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientDeleteSession":
        return cls(
            type="delete_session",
            session_id=d.get("session_id", ""),
        )


@dataclass
class ClientExportSession:
    type: str = "export_session"
    session_id: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientExportSession":
        return cls(
            type="export_session",
            session_id=d.get("session_id", ""),
        )


@dataclass
class ClientRenameSession:
    type: str = "rename_session"
    session_id: str = ""
    new_name: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientRenameSession":
        return cls(
            type="rename_session",
            session_id=d.get("session_id", ""),
            new_name=d.get("new_name", ""),
        )


@dataclass
class ClientIclawResume:
    type: str = "iclaw_resume"

    @classmethod
    def from_dict(cls, _d: dict[str, Any]) -> "ClientIclawResume":
        return cls(type="iclaw_resume")


@dataclass
class ClientAgentCreate:
    type: str = "agent_create"
    agent: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientAgentCreate":
        return cls(type="agent_create", agent=d.get("agent", {}))


@dataclass
class ClientAgentDelete:
    type: str = "agent_delete"
    index: int = 0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientAgentDelete":
        return cls(type="agent_delete", index=d.get("index", 0))


@dataclass
class ClientAgentUpdate:
    type: str = "agent_update"
    index: int = 0
    agent: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientAgentUpdate":
        return cls(type="agent_update", index=d.get("index", 0), agent=d.get("agent", {}))


@dataclass
class ClientAgentList:
    type: str = "agent_list"

    @classmethod
    def from_dict(cls, _d: dict[str, Any]) -> "ClientAgentList":
        return cls(type="agent_list")


@dataclass
class ClientAgentSetActive:
    type: str = "agent_set_active"
    index: int = -1

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientAgentSetActive":
        return cls(type="agent_set_active", index=d.get("index", -1))


@dataclass
class ClientUpdateSubAgents:
    type: str = "update_sub_agents"
    sub_agents: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientUpdateSubAgents":
        return cls(
            type="update_sub_agents",
            sub_agents=d.get("agents", d.get("sub_agents", [])),
        )


@dataclass
class ClientOpenWorkspace:
    type: str = "open_workspace"
    path: str = ""
    request_id: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientOpenWorkspace":
        return cls(
            type="open_workspace",
            path=d.get("path", ""),
            request_id=d.get("request_id", ""),
        )


@dataclass
class ClientListWorkspaces:
    type: str = "list_workspaces"

    @classmethod
    def from_dict(cls, _d: dict[str, Any]) -> "ClientListWorkspaces":
        return cls(type="list_workspaces")


@dataclass
class ClientRemoveWorkspace:
    type: str = "remove_workspace"
    path: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientRemoveWorkspace":
        return cls(
            type="remove_workspace",
            path=d.get("path", ""),
        )


@dataclass
class ClientCloseWorkspace:
    type: str = "close_workspace"
    request_id: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientCloseWorkspace":
        return cls(type="close_workspace", request_id=d.get("request_id", ""))


@dataclass
class ClientReindexWorkspace:
    type: str = "reindex_workspace"

    @classmethod
    def from_dict(cls, _d: dict[str, Any]) -> "ClientReindexWorkspace":
        return cls(type="reindex_workspace")


@dataclass
class ClientGetGitignore:
    type: str = "get_gitignore"

    @classmethod
    def from_dict(cls, _d: dict[str, Any]) -> "ClientGetGitignore":
        return cls(type="get_gitignore")


@dataclass
class ClientDeleteIndex:
    type: str = "delete_index"

    @classmethod
    def from_dict(cls, _d: dict[str, Any]) -> "ClientDeleteIndex":
        return cls(type="delete_index")


@dataclass
class ClientSetGitignore:
    type: str = "set_gitignore"
    content: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientSetGitignore":
        return cls(
            type="set_gitignore",
            content=d.get("content", ""),
        )


@dataclass
class ClientAddDocument:
    type: str = "add_document"
    name: str = ""
    file_path: str = ""
    url: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientAddDocument":
        return cls(
            type="add_document",
            name=d.get("name", ""),
            file_path=d.get("file_path", ""),
            url=d.get("url", ""),
        )


@dataclass
class ClientRemoveDocument:
    type: str = "remove_document"
    id: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientRemoveDocument":
        return cls(
            type="remove_document",
            id=d.get("id", ""),
        )


@dataclass
class ClientListDocuments:
    type: str = "list_documents"

    @classmethod
    def from_dict(cls, _d: dict[str, Any]) -> "ClientListDocuments":
        return cls(type="list_documents")


@dataclass
class ClientGetMemoryList:
    type: str = "get_memory_list"

    @classmethod
    def from_dict(cls, _d: dict[str, Any]) -> "ClientGetMemoryList":
        return cls(type="get_memory_list")


@dataclass
class ClientGetProfile:
    type: str = "get_profile"

    @classmethod
    def from_dict(cls, _d: dict[str, Any]) -> "ClientGetProfile":
        return cls(type="get_profile")


@dataclass
class ClientGetMemoryDetail:
    type: str = "get_memory_detail"
    path: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientGetMemoryDetail":
        return cls(type="get_memory_detail", path=d.get("path", ""))


@dataclass
class ClientListGlobalRules:
    type: str = "list_global_rules"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientListGlobalRules":
        return cls(type="list_global_rules")


@dataclass
class ClientListProjectRules:
    type: str = "list_project_rules"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientListProjectRules":
        return cls(type="list_project_rules")


@dataclass
class ClientListProjectHooks:
    type: str = "list_project_hooks"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientListProjectHooks":
        return cls(type="list_project_hooks")


@dataclass
class ClientSaveGlobalRule:
    type: str = "save_global_rule"
    name: str = ""
    content: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientSaveGlobalRule":
        return cls(
            type="save_global_rule",
            name=d.get("name", ""),
            content=d.get("content", ""),
        )


@dataclass
class ClientDeleteGlobalRule:
    type: str = "delete_global_rule"
    name: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientDeleteGlobalRule":
        return cls(
            type="delete_global_rule",
            name=d.get("name", ""),
        )


@dataclass
class ClientGetGlobalRuleContent:
    type: str = "get_global_rule_content"
    name: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientGetGlobalRuleContent":
        return cls(
            type="get_global_rule_content",
            name=d.get("name", ""),
        )


@dataclass
class ClientTerminalSpawn:
    type: str = "terminal_spawn"
    shell: str = ""
    shell_args: list[str] | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientTerminalSpawn":
        return cls(
            type="terminal_spawn",
            shell=d.get("shell", ""),
            shell_args=d.get("shell_args"),
        )


@dataclass
class ClientTerminalWrite:
    type: str = "terminal_write"
    id: int = 0
    data: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientTerminalWrite":
        return cls(type="terminal_write", id=d.get("id", 0), data=d.get("data", ""))


@dataclass
class ClientTerminalResize:
    type: str = "terminal_resize"
    id: int = 0
    cols: int = 80
    rows: int = 24

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientTerminalResize":
        return cls(type="terminal_resize", id=d.get("id", 0), cols=d.get("cols", 80), rows=d.get("rows", 24))  # noqa: E501


@dataclass
class ClientTerminalKill:
    type: str = "terminal_kill"
    id: int = 0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientTerminalKill":
        return cls(type="terminal_kill", id=d.get("id", 0))


@dataclass
class ClientTerminalListShells:
    type: str = "terminal_list_shells"

    @classmethod
    def from_dict(cls, _d: dict[str, Any]) -> ClientTerminalListShells:
        return cls(type="terminal_list_shells")


@dataclass
class ClientRetry:
    type: str = "retry"
    user_message_index: int = 0
    session_id: str = ""
    mode: str = "normal"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientRetry:
        return cls(
            type="retry",
            user_message_index=d.get("user_message_index", 0),
            session_id=d.get("session_id", ""),
            mode=d.get("mode", "normal"),
        )


@dataclass
class ClientSwitchBranch:
    type: str = "switch_branch"
    branch_id: str = ""
    session_id: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientSwitchBranch:
        return cls(
            type="switch_branch",
            branch_id=d.get("branch_id", ""),
            session_id=d.get("session_id", ""),
        )


@dataclass
class ClientRollbackBranch:
    type: str = "rollback"
    branch_id: str = ""
    message_id: str = ""
    session_id: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientRollbackBranch:
        return cls(
            type="rollback",
            branch_id=d.get("branch_id", ""),
            message_id=d.get("message_id", ""),
            session_id=d.get("session_id", ""),
        )


@dataclass
class ClientGetUsageStats:
    type: str = "get_usage_stats"

    @classmethod
    def from_dict(cls, _d: dict[str, Any]) -> "ClientGetUsageStats":
        return cls(type="get_usage_stats")


@dataclass
class ClientTranscribeAudio:
    type: str = "transcribe_audio"
    audio_data: str = ""
    format: str = "webm"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientTranscribeAudio":
        return cls(
            type="transcribe_audio",
            audio_data=d.get("audio_data", ""),
            format=d.get("format", "webm"),
        )


@dataclass
class ClientAutomationListJobs:
    type: str = "automation_list_jobs"

    @classmethod
    def from_dict(cls, _d: dict[str, Any]) -> "ClientAutomationListJobs":
        return cls(type="automation_list_jobs")


@dataclass
class ClientAutomationCreateJob:
    type: str = "automation_create_job"
    name: str = ""
    prompt: str = ""
    cron: str = ""
    tag: str = ""
    model_index: int = -1
    push_gateways: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientAutomationCreateJob":
        return cls(
            type="automation_create_job",
            name=d.get("name", ""),
            prompt=d.get("prompt", ""),
            cron=d.get("cron", ""),
            tag=d.get("tag", ""),
            model_index=d.get("model_index", -1),
            push_gateways=d.get("push_gateways", []),
        )


@dataclass
class ClientAutomationCancelJob:
    type: str = "automation_cancel_job"
    job_id: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientAutomationCancelJob":
        return cls(
            type="automation_cancel_job",
            job_id=d.get("job_id", ""),
        )


@dataclass
class ClientAutomationGetHistory:
    type: str = "automation_get_history"

    @classmethod
    def from_dict(cls, _d: dict[str, Any]) -> "ClientAutomationGetHistory":
        return cls(type="automation_get_history")


@dataclass
class ClientAutomationToggleJob:
    type: str = "automation_toggle_job"
    job_id: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientAutomationToggleJob":
        return cls(
            type="automation_toggle_job",
            job_id=d.get("job_id", ""),
        )


@dataclass
class ClientAutomationUpdateJob:
    type: str = "automation_update_job"
    job_id: str = ""
    name: str = ""
    prompt: str = ""
    cron: str = ""
    tag: str = ""
    model_index: int = -1
    push_gateways: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientAutomationUpdateJob":
        return cls(
            type="automation_update_job",
            job_id=d.get("job_id", ""),
            name=d.get("name", ""),
            prompt=d.get("prompt", ""),
            cron=d.get("cron", ""),
            tag=d.get("tag", ""),
            model_index=d.get("model_index", -1),
            push_gateways=d.get("push_gateways", []),
        )


@dataclass
class ClientAutomationDeleteJob:
    type: str = "automation_delete_job"
    job_id: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClientAutomationDeleteJob":
        return cls(
            type="automation_delete_job",
            job_id=d.get("job_id", ""),
        )


ClientMessage = Union[
    ClientRun,
    ClientRespondPermission,
    ClientCancel,
    ClientResume,
    ClientConfigure,
    ClientPing,
    ClientListModels,
    ClientListSessions,
    ClientListAllSessions,
    ClientNewSession,
    ClientGetConfig,
    ClientUpdateModels,
    ClientSetActiveModel,
    ClientDeleteModel,
    ClientFetchModels,
    ClientUpdateSkills,
    ClientInstallSkill,
    ClientUninstallSkill,
    ClientUpdateSkill,
    ClientUpdateMCP,
    ClientUpdateAgent,
    ClientSearch,
    ClientRollbackLog,
    ClientRollbackCheckout,
    ClientValidateModel,
    ClientEditMessage,
    ClientDeleteMessage,
    ClientDeleteSession,
    ClientExportSession,
    ClientRenameSession,
    ClientAgentCreate,
    ClientAgentDelete,
    ClientAgentUpdate,
    ClientAgentList,
    ClientAgentSetActive,
    ClientUpdateSubAgents,
    ClientOpenWorkspace,
    ClientListWorkspaces,
    ClientRemoveWorkspace,
    ClientCloseWorkspace,
    ClientReindexWorkspace,
    ClientGetGitignore,
    ClientDeleteIndex,
    ClientSetGitignore,
    ClientGetMemoryList,
    ClientGetMemoryDetail,
    ClientListGlobalRules,
    ClientListProjectRules,
    ClientListProjectHooks,
    ClientSaveGlobalRule,
    ClientDeleteGlobalRule,
    ClientGetGlobalRuleContent,
    ClientGetProfile,
    ClientTerminalSpawn,
    ClientTerminalWrite,
    ClientTerminalResize,
    ClientTerminalKill,
    ClientTerminalListShells,
    ClientRetry,
    ClientSwitchBranch,
    ClientRollbackBranch,
    ClientTranscribeAudio,
    ClientGetUsageStats,
    ClientTestAdapter,
    ClientIclawResume,
    ClientAutomationListJobs,
    ClientAutomationCreateJob,
    ClientAutomationCancelJob,
    ClientAutomationGetHistory,
    ClientAutomationToggleJob,
    ClientAutomationUpdateJob,
    ClientAutomationDeleteJob,
]


def parse_client_message(raw: str | bytes) -> ClientMessage | None:
    decrypted = _parse_client_encrypted(raw)
    try:
        if isinstance(decrypted, bytes):
            decrypted = decrypted.decode("utf-8")
        data = json.loads(decrypted)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    msg_type = data.get("type", "")
    parsers: dict[str, type] = {
        "run": ClientRun,
        "respond_permission": ClientRespondPermission,
        "respond_plan": ClientRespondPlan,
        "set_plan_mode": ClientSetPlanMode,
        "respond_question": ClientRespondQuestion,
        "cancel": ClientCancel,
        "resume": ClientResume,
        "configure": ClientConfigure,
        "ping": ClientPing,
        "list_models": ClientListModels,
        "list_sessions": ClientListSessions,
        "list_all_sessions": ClientListAllSessions,
        "new_session": ClientNewSession,
        "get_config": ClientGetConfig,
        "test_adapter": ClientTestAdapter,
        "iclaw_resume": ClientIclawResume,
        "update_models": ClientUpdateModels,
        "set_active_model": ClientSetActiveModel,
        "delete_model": ClientDeleteModel,
        "fetch_models": ClientFetchModels,
        "update_skills": ClientUpdateSkills,
        "install_skill": ClientInstallSkill,
        "uninstall_skill": ClientUninstallSkill,
        "update_skill": ClientUpdateSkill,
        "update_mcp": ClientUpdateMCP,
        "update_agent": ClientUpdateAgent,
        "search": ClientSearch,
        "rollback_log": ClientRollbackLog,
        "rollback_checkout": ClientRollbackCheckout,
        "validate_model": ClientValidateModel,
        "edit_message": ClientEditMessage,
        "delete_message": ClientDeleteMessage,
        "delete_session": ClientDeleteSession,
        "export_session": ClientExportSession,
        "rename_session": ClientRenameSession,
        "agent_create": ClientAgentCreate,
        "agent_delete": ClientAgentDelete,
        "agent_update": ClientAgentUpdate,
        "agent_list": ClientAgentList,
        "agent_set_active": ClientAgentSetActive,
        "update_sub_agents": ClientUpdateSubAgents,
        "open_workspace": ClientOpenWorkspace,
        "list_workspaces": ClientListWorkspaces,
        "remove_workspace": ClientRemoveWorkspace,
        "close_workspace": ClientCloseWorkspace,
        "reindex_workspace": ClientReindexWorkspace,
        "get_gitignore": ClientGetGitignore,
        "delete_index": ClientDeleteIndex,
        "set_gitignore": ClientSetGitignore,
        "add_document": ClientAddDocument,
        "remove_document": ClientRemoveDocument,
        "list_documents": ClientListDocuments,
        "get_memory_list": ClientGetMemoryList,
        "get_memory_detail": ClientGetMemoryDetail,
        "list_global_rules": ClientListGlobalRules,
        "list_project_rules": ClientListProjectRules,
        "list_project_hooks": ClientListProjectHooks,
        "save_global_rule": ClientSaveGlobalRule,
        "delete_global_rule": ClientDeleteGlobalRule,
        "get_global_rule_content": ClientGetGlobalRuleContent,
        "get_profile": ClientGetProfile,
        "terminal_spawn": ClientTerminalSpawn,
        "terminal_write": ClientTerminalWrite,
        "terminal_resize": ClientTerminalResize,
        "terminal_kill": ClientTerminalKill,
        "terminal_list_shells": ClientTerminalListShells,
        "retry": ClientRetry,
        "switch_branch": ClientSwitchBranch,
        "rollback": ClientRollbackBranch,
        "transcribe_audio": ClientTranscribeAudio,
        "get_usage_stats": ClientGetUsageStats,
        "automation_list_jobs": ClientAutomationListJobs,
        "automation_create_job": ClientAutomationCreateJob,
        "automation_cancel_job": ClientAutomationCancelJob,
        "automation_get_history": ClientAutomationGetHistory,
        "automation_toggle_job": ClientAutomationToggleJob,
        "automation_update_job": ClientAutomationUpdateJob,
        "automation_delete_job": ClientAutomationDeleteJob,
        "engine_install_response": ClientEngineInstallResponse,
    }
    cls = parsers.get(msg_type)
    if cls is None:
        return None
    return cls.from_dict(data)


# ── Server -> Client message types ──────────────────────────────────

ServerMessageType = Literal[
    "text_delta",
    "thinking_delta",
    "tool_call_start",
    "tool_call_delta",
    "tool_call_end",
    "tool_progress",
    "tool_result",
    "permission_request",
    "finish",
    "pong",
    "error",
    "session_ready",
    "configured",
    "telemetry",
    "plan_update",
    "spec_update",
    "models_list",
    "sessions_list",
    "config_data",
    "models_updated",
    "models_fetched",
    "skills_updated",
    "skills_list",
    "skill_installed",
    "skill_install_error",
    "skill_uninstalled",
    "mcp_updated",
    "agent_updated",
    "search_results",
    "compact",
    "rollback_log",
    "rollback_checkout",
    "model_validated",
    "model_validation_error",
    "messages_updated",
    "session_deleted",
    "session_exported",
    "session_renamed",
    "memory_list",
    "memory_detail",
    "global_rules_list",
    "project_rules_list",
    "global_rule_saved",
    "global_rule_deleted",
    "global_rule_content",
    "profile_data",
    "agents_list",
    "agents_updated",
    "sub_agents_updated",
    "index_status",
    "gitignore_content",
    "documents_list",
    "document_added",
    "document_removed",
    "document_error",
    "artifacts_update",
    "assistant_boundary",
    "slash_commands",
    "terminal_data",
    "terminal_shells",
    "terminal_spawned",
    "branch_switched",
    "branch_rolled_back",
    "branch_updated",
    "transcription_result",
    "usage_stats",
    "automation_jobs_list",
    "automation_job_created",
    "automation_job_cancelled",
    "automation_job_history",
    "automation_job_update",
    "automation_stream_event",
]


def _make_message(msg_type: ServerMessageType, **kwargs: Any) -> dict[str, Any]:
    msg: dict[str, Any] = {"type": msg_type}
    msg.update(kwargs)
    return msg


def encode_server_message(
    msg_type: ServerMessageType,
    encrypt: bool = True,
    **kwargs: Any,
) -> str:
    if encrypt:
        return encode_server_encrypted(msg_type, **kwargs)
    return json.dumps({"type": msg_type, **kwargs}, ensure_ascii=False)


# ── Convenience encoders ────────────────────────────────────────────


def encode_text_delta(text: str) -> str:
    return encode_server_message("text_delta", text=text)


def encode_thinking_delta(text: str) -> str:
    return encode_server_message("thinking_delta", text=text)


def encode_tool_call_start(name: str, call_id: str) -> str:
    return encode_server_message("tool_call_start", name=name, id=call_id)


def encode_tool_call_delta(call_id: str, key: str, value: str) -> str:
    return encode_server_message("tool_call_delta", id=call_id, key=key, value=value)


def encode_tool_call_end(call_id: str) -> str:
    return encode_server_message("tool_call_end", id=call_id)


def encode_tool_progress(call_id: str, tool_name: str, status: str) -> str:
    return encode_server_message("tool_progress", id=call_id, tool_name=tool_name, status=status)


def encode_tool_result(
    call_id: str,
    content: str,
    is_error: bool = False,
    sub_agent_messages: list[dict[str, Any]] | None = None,
    sub_agent_session_id: str | None = None,
) -> str:
    return encode_server_message(
        "tool_result",
        id=call_id,
        content=content,
        is_error=is_error,
        sub_agent_messages=sub_agent_messages,
        sub_agent_session_id=sub_agent_session_id,
    )


def encode_permission_request(tool_name: str, reason: str) -> str:
    return encode_server_message("permission_request", tool_name=tool_name, reason=reason)


def encode_finish(reason: str, usage: dict[str, Any] | None = None, error: str | None = None) -> str:  # noqa: E501
    return encode_server_message("finish", reason=reason, usage=usage, error=error)


def encode_pong() -> str:
    return encode_server_message("pong")


def encode_documents_list(documents: list[dict[str, Any]]) -> str:
    return encode_server_message("documents_list", documents=documents)


def encode_document_added(document: dict[str, Any]) -> str:
    return encode_server_message("document_added", document=document)


def encode_document_updated(document: dict[str, Any]) -> str:
    return encode_server_message("document_updated", document=document)


def encode_document_removed(id: str) -> str:
    return encode_server_message("document_removed", id=id)


def encode_document_error(message: str) -> str:
    return encode_server_message("document_error", message=message)


def encode_error(message: str, code: str = "internal") -> str:
    return encode_server_message("error", message=message, code=code)


def encode_session_ready(
    session_id: str,
    messages: list[dict[str, Any]] | None = None,
    request_id: str = "",
) -> str:
    payload: dict[str, Any] = {"session_id": session_id}
    if messages is not None:
        payload["messages"] = messages
    if request_id:
        payload["request_id"] = request_id
    return encode_server_message("session_ready", **payload)


def encode_configured(config: dict[str, Any]) -> str:
    return encode_server_message("configured", config=config)


def encode_telemetry(data: dict[str, Any]) -> str:
    return encode_server_message("telemetry", data=data)


def encode_plan_update(plan_items: list[dict[str, Any]]) -> str:
    return encode_server_message("plan_update", plan_items=plan_items)


def encode_spec_update(
    spec: dict[str, Any] | None,
    status: str = "",
    feedback: str = "",
) -> str:
    """Encode a spec update event for the frontend."""
    return encode_server_message("spec_update", spec=spec, status=status, feedback=feedback)


def encode_models_list(models: list[str]) -> str:
    return encode_server_message("models_list", models=models)


def encode_sessions_list(sessions: list[dict[str, Any]]) -> str:
    return encode_server_message("sessions_list", sessions=sessions)


def encode_config_data(config: dict[str, Any]) -> str:
    return encode_server_message("config_data", config=config)


def encode_models_updated(models: list[dict[str, Any]], active_model_index: int) -> str:
    return encode_server_message("models_updated", models=models, active_model_index=active_model_index)  # noqa: E501


def encode_models_fetched(models: list[str]) -> str:
    return encode_server_message("models_fetched", models=models)


def encode_skills_updated(enabled_skills: list[str], available_skills: list[dict[str, Any]]) -> str:
    return encode_server_message("skills_updated", enabled_skills=enabled_skills, available_skills=available_skills)  # noqa: E501


def encode_skills_list(skills: list[dict[str, Any]]) -> str:
    return encode_server_message("skills_list", skills=skills)


def encode_skill_installed(name: str, available_skills: list[dict[str, Any]]) -> str:
    return encode_server_message("skill_installed", name=name, available_skills=available_skills)


def encode_skill_install_error(name: str, message: str) -> str:
    return encode_server_message("skill_install_error", name=name, message=message)


def encode_skill_uninstalled(name: str, available_skills: list[dict[str, Any]]) -> str:
    return encode_server_message("skill_uninstalled", name=name, available_skills=available_skills)


def encode_mcp_updated(mcp_servers: list[dict[str, Any]]) -> str:
    return encode_server_message("mcp_updated", mcp_servers=mcp_servers)


def encode_agent_updated(config: dict[str, Any]) -> str:
    return encode_server_message("agent_updated", config=config)


def encode_search_results(results: list[dict[str, Any]]) -> str:
    return encode_server_message("search_results", results=results)


def encode_rollback_log(session_id: str, commits: list[dict[str, Any]]) -> str:
    return encode_server_message("rollback_log", session_id=session_id, commits=commits)


def encode_rollback_checkout(session_id: str, commit_hash: str, messages: list[dict[str, Any]], turn_count: int, plan_items: list[dict[str, Any]] | None = None, artifacts: list[dict[str, Any]] | None = None) -> str:  # noqa: E501
    return encode_server_message("rollback_checkout", session_id=session_id, commit_hash=commit_hash, messages=messages, turn_count=turn_count, plan_items=plan_items or [], artifacts=artifacts or [])  # noqa: E501


def encode_messages_updated(messages: list[dict[str, Any]], session_id: str, commit_hash: str = "") -> str:  # noqa: E501
    return encode_server_message("messages_updated", messages=messages, session_id=session_id, commit_hash=commit_hash)  # noqa: E501


def encode_session_deleted(session_id: str) -> str:
    return encode_server_message("session_deleted", session_id=session_id)


def encode_session_exported(session_id: str, markdown: str, filename: str) -> str:
    return encode_server_message("session_exported", session_id=session_id, markdown=markdown, filename=filename)  # noqa: E501


def encode_session_renamed(session_id: str, new_name: str) -> str:
    return encode_server_message("session_renamed", session_id=session_id, new_name=new_name)


def encode_agents_list(agents: list[dict[str, Any]], active_index: int) -> str:
    return encode_server_message("agents_list", agents=agents, active_index=active_index)


def encode_agents_updated(agents: list[dict[str, Any]], active_index: int) -> str:
    return encode_server_message("agents_updated", agents=agents, active_index=active_index)


def encode_sub_agents_updated(sub_agents: list[dict[str, Any]]) -> str:
    return encode_server_message("sub_agents_updated", sub_agents=sub_agents)


def encode_artifacts_update(artifacts: list[dict[str, Any]]) -> str:
    return encode_server_message("artifacts_update", artifacts=artifacts)


def encode_assistant_boundary() -> str:
    return encode_server_message("assistant_boundary")
