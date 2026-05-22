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

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Union

from yim.crypto import encrypt, decrypt

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
        # Decryption failed — return the raw payload so the upper
        # layer can still attempt to parse it as plaintext (or fail gracefully).
        return decoded


def encode_server_encrypted(msg_type: str, **kwargs: Any) -> str:
    """Encode and encrypt a server‑to‑client message.

    The message is serialized as JSON, encrypted via AES‑256‑GCM, and
    returned as a base64 ciphertext string.
    """
    payload = json.dumps({"type": msg_type, **kwargs}, ensure_ascii=False)
    return encrypt(payload)


# ── Client → Server message types ──────────────────────────────────

ClientMessageType = Literal[
    "run", "respond_permission", "cancel", "resume", "configure", "ping",
    "list_models", "list_sessions", "new_session",
    "get_config", "update_models", "set_active_model", "delete_model",
    "update_skills", "update_mcp", "update_agent",
    "search",
    "rollback_log", "rollback_checkout",
]


@dataclass
class ClientRun:
    type: str = "run"
    prompt: str = ""
    system_prompt: str | None = None
    session_id: str | None = None
    specialty: str = "general"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientRun:
        return cls(
            type="run",
            prompt=d.get("prompt", ""),
            system_prompt=d.get("system_prompt"),
            session_id=d.get("session_id"),
            specialty=d.get("specialty", "general"),
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

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ClientResume:
        return cls(
            type="resume",
            session_id=d.get("session_id", ""),
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
class ClientNewSession:
    type: str = "new_session"

    @classmethod
    def from_dict(cls, _d: dict[str, Any]) -> "ClientNewSession":
        return cls(type="new_session")


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
class ClientUpdateMCP:
    type: str = "update_mcp"
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)

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


ClientMessage = Union[
    ClientRun,
    ClientRespondPermission,
    ClientCancel,
    ClientResume,
    ClientConfigure,
    ClientPing,
    ClientListModels,
    ClientListSessions,
    ClientNewSession,
    ClientGetConfig,
    ClientUpdateModels,
    ClientSetActiveModel,
    ClientDeleteModel,
    ClientUpdateSkills,
    ClientUpdateMCP,
    ClientUpdateAgent,
    ClientSearch,
    ClientRollbackLog,
    ClientRollbackCheckout,
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
        "cancel": ClientCancel,
        "resume": ClientResume,
        "configure": ClientConfigure,
        "ping": ClientPing,
        "list_models": ClientListModels,
        "list_sessions": ClientListSessions,
        "new_session": ClientNewSession,
        "get_config": ClientGetConfig,
        "update_models": ClientUpdateModels,
        "set_active_model": ClientSetActiveModel,
        "delete_model": ClientDeleteModel,
        "update_skills": ClientUpdateSkills,
        "update_mcp": ClientUpdateMCP,
        "update_agent": ClientUpdateAgent,
        "search": ClientSearch,
        "rollback_log": ClientRollbackLog,
        "rollback_checkout": ClientRollbackCheckout,
    }
    cls = parsers.get(msg_type)
    if cls is None:
        return None
    return cls.from_dict(data)


# ── Server → Client message types ──────────────────────────────────

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
    "models_list",
    "sessions_list",
    "config_data",
    "models_updated",
    "skills_updated",
    "skills_list",
    "mcp_updated",
    "agent_updated",
    "search_results",
    "rollback_log",
    "rollback_checkout",
]


def _make_message(msg_type: ServerMessageType, **kwargs: Any) -> dict[str, Any]:
    msg: dict[str, Any] = {"type": msg_type}
    msg.update(kwargs)
    return msg


def encode_server_message(
    msg_type: ServerMessageType,
    **kwargs: Any,
) -> str:
    return encode_server_encrypted(msg_type, **kwargs)


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


def encode_tool_result(call_id: str, content: str, is_error: bool = False) -> str:
    return encode_server_message("tool_result", id=call_id, content=content, is_error=is_error)


def encode_permission_request(tool_name: str, reason: str) -> str:
    return encode_server_message("permission_request", tool_name=tool_name, reason=reason)


def encode_finish(reason: str, usage: dict[str, Any] | None = None, error: str | None = None) -> str:
    return encode_server_message("finish", reason=reason, usage=usage, error=error)


def encode_pong() -> str:
    return encode_server_message("pong")


def encode_error(message: str, code: str = "internal") -> str:
    return encode_server_message("error", message=message, code=code)


def encode_session_ready(session_id: str, messages: list[dict[str, Any]] | None = None) -> str:
    payload: dict[str, Any] = {"session_id": session_id}
    if messages is not None:
        payload["messages"] = messages
    return encode_server_message("session_ready", **payload)


def encode_configured(config: dict[str, Any]) -> str:
    return encode_server_message("configured", config=config)


def encode_telemetry(data: dict[str, Any]) -> str:
    return encode_server_message("telemetry", data=data)


def encode_plan_update(plan_items: list[dict[str, Any]]) -> str:
    return encode_server_message("plan_update", plan_items=plan_items)


def encode_models_list(models: list[str]) -> str:
    return encode_server_message("models_list", models=models)


def encode_sessions_list(sessions: list[dict[str, Any]]) -> str:
    return encode_server_message("sessions_list", sessions=sessions)


def encode_config_data(config: dict[str, Any]) -> str:
    return encode_server_message("config_data", config=config)


def encode_models_updated(models: list[dict[str, Any]], active_model_index: int) -> str:
    return encode_server_message("models_updated", models=models, active_model_index=active_model_index)


def encode_skills_updated(enabled_skills: list[str], available_skills: list[dict[str, Any]]) -> str:
    return encode_server_message("skills_updated", enabled_skills=enabled_skills, available_skills=available_skills)


def encode_skills_list(skills: list[dict[str, Any]]) -> str:
    return encode_server_message("skills_list", skills=skills)


def encode_mcp_updated(mcp_servers: list[dict[str, Any]]) -> str:
    return encode_server_message("mcp_updated", mcp_servers=mcp_servers)


def encode_agent_updated(config: dict[str, Any]) -> str:
    return encode_server_message("agent_updated", config=config)


def encode_search_results(results: list[dict[str, Any]]) -> str:
    return encode_server_message("search_results", results=results)


def encode_rollback_log(session_id: str, commits: list[dict[str, Any]]) -> str:
    return encode_server_message("rollback_log", session_id=session_id, commits=commits)


def encode_rollback_checkout(session_id: str, commit_hash: str, messages: list[dict[str, Any]], turn_count: int) -> str:
    return encode_server_message("rollback_checkout", session_id=session_id, commit_hash=commit_hash, messages=messages, turn_count=turn_count)
