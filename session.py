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

import base64
import copy
import json
import os
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from yim.config import YmiConfig
from yim.utils.tokens import count_message_tokens, estimate_tokens


@dataclass
class SessionCheckpoint:
    checkpoint_id: str
    label: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_call_count: int = 0
    turn_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0


class YmiSession:
    SYSTEM_BUDGET_RATIO = 0.15
    HISTORY_BUDGET_RATIO = 0.50
    RESPONSE_BUDGET_RATIO = 0.35

    def __init__(self, config: YmiConfig) -> None:
        self.id: str = str(uuid.uuid4())
        self.config: YmiConfig = config
        self.messages: list[dict[str, Any]] = []
        self.created_at: float = time.time()
        self.updated_at: float = time.time()
        self.tool_call_count: int = 0
        self.turn_count: int = 0
        self.metadata: dict[str, Any] = {}
        self._checkpoints: OrderedDict[str, SessionCheckpoint] = OrderedDict()
        self._max_checkpoints: int = config.checkpoint_max_count

    def add_message(self, role: str, content: str | list[dict[str, Any]], **kwargs: Any) -> None:
        message: dict[str, Any] = {"role": role, "content": content}
        message.update(kwargs)
        self.messages.append(message)
        self.updated_at = time.time()

    def add_user_message_with_image(self, text: str, image_path: str) -> None:
        """Add a user message containing both text and an image."""
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        if image_path.startswith(("http://", "https://")):
            content.append({
                "type": "image_url",
                "image_url": {"url": image_path},
            })
        else:
            mime = _guess_image_mime(image_path)
            try:
                with open(image_path, "rb") as f:
                    data = base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                return
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{data}"},
            })
        self.add_message("user", content)

    def add_user_message_with_file(self, text: str, file_path: str) -> None:
        """Add a user message with an attached file's content."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                file_content = f.read()
        except Exception:
            return
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        filename = os.path.basename(file_path)
        content.append({
            "type": "text",
            "text": f"\n<attached_file filename=\"{filename}\">\n{file_content}\n</attached_file>",
        })
        self.add_message("user", content)

    def add_message_content(self, role: str, blocks: list[dict[str, Any]]) -> None:
        """Add a message with raw content blocks (for advanced multimodal use)."""
        self.add_message(role, blocks)

    def add_tool_result(self, tool_call_id: str, content: str, is_error: bool = False) -> None:
        self.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        })
        self.tool_call_count += 1
        self.updated_at = time.time()

    def checkpoint(self, label: str = "") -> str:
        cid = str(uuid.uuid4())[:12]
        cp = SessionCheckpoint(
            checkpoint_id=cid,
            label=label,
            messages=copy.deepcopy(self.messages),
            tool_call_count=self.tool_call_count,
            turn_count=self.turn_count,
            metadata=copy.deepcopy(self.metadata),
            created_at=time.time(),
        )
        self._checkpoints[cid] = cp
        while len(self._checkpoints) > self._max_checkpoints:
            self._checkpoints.popitem(last=False)
        return cid

    def rollback(self, checkpoint_id: str) -> bool:
        cp = self._checkpoints.get(checkpoint_id)
        if cp is None:
            return False
        self.messages = copy.deepcopy(cp.messages)
        self.tool_call_count = cp.tool_call_count
        self.turn_count = cp.turn_count
        self.metadata = copy.deepcopy(cp.metadata)
        self.updated_at = time.time()
        return True

    def list_checkpoints(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for cp in self._checkpoints.values():
            result.append({
                "checkpoint_id": cp.checkpoint_id,
                "label": cp.label,
                "message_count": len(cp.messages),
                "tool_call_count": cp.tool_call_count,
                "turn_count": cp.turn_count,
                "created_at": cp.created_at,
            })
        return result

    def clear_checkpoints(self) -> None:
        self._checkpoints.clear()

    def is_expired(self) -> bool:
        age = time.time() - self.created_at
        max_age_seconds = self.config.session_max_age_hours * 3600
        return age > max_age_seconds

    def is_max_turns_reached(self) -> bool:
        return self.turn_count >= self.config.max_turns

    def get_context_messages(self) -> list[dict[str, Any]]:
        return list(self.messages)

    def clear_history(self) -> None:
        self.messages.clear()
        self.tool_call_count = 0
        self.turn_count = 0
        self.updated_at = time.time()

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return estimate_tokens(text)

    @staticmethod
    def count_messages_tokens(messages: list[dict[str, Any]]) -> int:
        return count_message_tokens(messages)

    def truncate_messages(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int,
    ) -> list[dict[str, Any]]:
        system_budget = int(max_tokens * self.SYSTEM_BUDGET_RATIO)
        history_budget = int(max_tokens * self.HISTORY_BUDGET_RATIO)

        system_msgs: list[dict[str, Any]] = []
        history_msgs: list[dict[str, Any]] = []

        for msg in messages:
            if msg.get("role") == "system":
                system_msgs.append(msg)
            else:
                history_msgs.append(msg)

        system_truncated = self._truncate_to_budget(system_msgs, system_budget)
        history_truncated = self._smart_truncate_history(history_msgs, history_budget)

        return system_truncated + history_truncated

    def _truncate_to_budget(
        self,
        messages: list[dict[str, Any]],
        budget: int,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        used = 0
        for msg in messages:
            tokens = self.count_messages_tokens([msg])
            if used + tokens > budget:
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 200:
                    truncated = content[:200] + "\n...[truncated]"
                    truncated_msg = dict(msg)
                    truncated_msg["content"] = truncated
                    result.append(truncated_msg)
                break
            result.append(msg)
            used += tokens
        return result

    def _smart_truncate_history(
        self,
        messages: list[dict[str, Any]],
        budget: int,
    ) -> list[dict[str, Any]]:
        total = self.count_messages_tokens(messages)
        if total <= budget:
            return messages

        preserved_pairs: list[int] = []
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "tool":
                for j in range(i - 1, -1, -1):
                    msg = messages[j]
                    role = msg.get("role")
                    content = msg.get("content", "")
                    if role == "assistant" and isinstance(content, str) and content:
                        preserved_pairs = [j, i]
                        break
                    elif role == "assistant" and msg.get("tool_calls"):
                        preserved_pairs = [j, i]
                        break
                if preserved_pairs:
                    continue

        preserved = 0
        for i in preserved_pairs:
            if i < len(messages):
                preserved += self.count_messages_tokens([messages[i]])

        preserved_indices: set[int] = set(preserved_pairs)
        compressed: list[dict[str, Any]] = []
        compressed.append({
            "role": "user",
            "content": "[Previous conversation context has been compressed to save tokens]",
        })

        used = self.count_messages_tokens(compressed)
        for i in range(len(messages) - 1, -1, -1):
            if i in preserved_indices:
                compressed.append(messages[i])
                used += self.count_messages_tokens([messages[i]])
                continue
            tokens = self.count_messages_tokens([messages[i]])
            if used + tokens <= budget:
                compressed.append(messages[i])
                used += tokens
            else:
                break

        compressed.reverse()
        return compressed

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "messages": self.messages,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tool_call_count": self.tool_call_count,
            "turn_count": self.turn_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], config: YmiConfig) -> YmiSession:
        session = cls(config)
        session.id = data.get("id", session.id)
        session.messages = data.get("messages", [])
        session.created_at = data.get("created_at", session.created_at)
        session.updated_at = data.get("updated_at", session.updated_at)
        session.tool_call_count = data.get("tool_call_count", 0)
        session.turn_count = data.get("turn_count", 0)
        session.metadata = data.get("metadata", {})
        return session

    def save_to_json(self, filepath: str) -> None:
        import json
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load_from_json(cls, filepath: str, config: YmiConfig) -> YmiSession:
        import json
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data, config)


def _guess_image_mime(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }.get(ext, "image/png")