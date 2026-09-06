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

"""Automation domain handlers: scheduled-job CRUD, history, broadcast.

Owns the automation job snapshot builders, execution-history serialiser
and the update/progress broadcast paths used by the scheduler callbacks.
Extracted verbatim from ``encre.transport.ws`` (architecture refactor
Stage 3 / Task 5.2); behaviour is unchanged, only the layout moved.
Outer-loop ``continue`` statements of the original dispatch chain became
``return`` inside the extracted methods.
"""

import asyncio
import json
import logging
import shutil
from typing import Any

from encre.config import ModelConfig
from encre.server.protocol import (
    ClientAutomationCancelJob,
    ClientAutomationCreateJob,
    ClientAutomationDeleteExecution,
    ClientAutomationDeleteJob,
    ClientAutomationGetHistory,
    ClientAutomationListJobs,
    ClientAutomationRenameExecution,
    ClientAutomationToggleJob,
    ClientAutomationUpdateJob,
)

logger = logging.getLogger("encre.transport.ws")


class AutomationHandlers:
    """Automation job CRUD, execution history and broadcast handlers."""

    # 鈹€鈹€ Snapshot builders 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    def _build_automation_jobs(self) -> list[dict[str, Any]]:
        """Snapshot of all automation jobs (responses and snapshots share it)."""
        if self._scheduler is None:
            return []
        jobs = self._scheduler.list_jobs()
        job_list: list[dict[str, Any]] = []
        for j in jobs:
            job_list.append({
                "id": j.id,
                "name": j.name,
                "prompt": j.prompt,
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
        return job_list

    def _build_automation_agent_config(self, mc: ModelConfig) -> dict[str, Any]:
        """Build the per-job agent snapshot for an automation model."""
        agent_config = {
            "backend_type": mc.backend_type,
            "api_key": mc.api_key,
            "base_url": mc.base_url,
            "model_id": mc.model_id,
            "max_tokens": mc.max_tokens,
        }
        # Store current workspace path so the automation
        # agent runs in the correct workspace context.
        if self._workspace_path:
            agent_config["workspace"] = self._workspace_path
        return agent_config

    def _resolve_automation_model(self, model_index: int) -> tuple[int, dict[str, Any] | None]:
        """Resolve an automation job's model to an *enabled* model.

        Returns ``(effective_index, agent_config)``. If the requested index is
        disabled or out of range, the first enabled model is used so a job never
        snapshots a disabled model. If no model is enabled at all, returns
        ``(model_index, None)`` and execution falls back to the active model.
        """
        models = getattr(self._default_config, "models", None)
        if models:
            if 0 <= model_index < len(models) and getattr(models[model_index], "enabled", True):
                return model_index, self._build_automation_agent_config(models[model_index])
            for i, mc in enumerate(models):
                if getattr(mc, "enabled", True):
                    logger.info(
                        "[automation] requested model_index=%d disabled/unavailable, "
                        "falling back to enabled model index=%d", model_index, i,
                    )
                    return i, self._build_automation_agent_config(mc)
        return model_index, None

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
                "prompt": job.prompt if job else "",
                "tag": job.metadata.get("tag", "") if job else "",
                "time": execution.time,
                "state": execution.state,
                "last_result": execution.result[:500] if execution.result else "",
                "fail_count": execution.fail_count,
                "messages": [],
            }
            if execution.state == "FAILED":
                try:
                    from encre.errors import classify_error_code
                    entry["error_code"] = classify_error_code(execution.result or "").value
                except Exception:
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

    # 鈹€鈹€ Broadcasts (scheduler callbacks) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

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
                # a stable, classified code (rate_limit / network_timeout / 鈥?
                # instead of a bare placeholder that hides the real cause.
                try:
                    from encre.errors import classify_error_code
                    result_data["error_code"] = classify_error_code(job.last_result or "").value
                except Exception:
                    result_data["error_code"] = "AUTOMATION_EXECUTION_FAILED"
            if getattr(job, "session_id", None):
                result_data["session_id"] = job.session_id

        # 鈹€鈹€ Push result through configured gateways 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
        if job and job.last_result and hasattr(job, "push_gateways") and job.push_gateways and self._adapter_manager:
            # Route through the DeliveryRouter for unified truncation + audit
            # (aligns with Hermes delivery.py).  Each entry in push_gateways is
            # either "platform:chat_id" (explicit chat) or a bare adapter id
            # (resolved to the adapter's default push target).
            push_text = f"馃 {job.name}\n\n{job.last_result}"
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

    # 鈹€鈹€ Client message handlers 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

    async def _h_automation_list_jobs(self, ws: Any, msg: ClientAutomationListJobs) -> None:
        info = self._get_or_create_session()
        self._manager.touch(info.session_id)
        await self._send(ws, "automation_jobs_list", jobs=self._build_automation_jobs())

    async def _h_automation_create_job(self, ws: Any, msg: ClientAutomationCreateJob) -> None:
        info = self._get_or_create_session()
        self._manager.touch(info.session_id)
        if self._scheduler is None:
            await self._send(ws, "error", message="Scheduler not available", code="no_scheduler")
            return
        try:
            effective_index, agent_config = self._resolve_automation_model(msg.model_index)
            job_id = self._scheduler.schedule(
                name=msg.name,
                prompt=msg.prompt,
                cron=msg.cron if msg.cron else "",
                metadata={"tag": msg.tag} if msg.tag else {},
                agent_config=agent_config,
                model_index=effective_index,
                push_gateways=list(msg.push_gateways),
            )
            await self._send(ws, "automation_job_created",
                job_id=job_id, name=msg.name)
        except Exception as e:
            await self._send(ws, "error",
                message=f"Failed to create job: {e}", code="create_job_error")

    async def _h_automation_cancel_job(self, ws: Any, msg: ClientAutomationCancelJob) -> None:
        info = self._get_or_create_session()
        self._manager.touch(info.session_id)
        if self._scheduler is None:
            await self._send(ws, "error", message="Scheduler not available", code="no_scheduler")
            return
        ok = self._scheduler.cancel(msg.job_id)
        if ok:
            await self._send(ws, "automation_job_cancelled", job_id=msg.job_id)
        else:
            await self._send(ws, "error",
                message="Job not found", code="job_not_found")

    async def _h_automation_toggle_job(self, ws: Any, msg: ClientAutomationToggleJob) -> None:
        info = self._get_or_create_session()
        self._manager.touch(info.session_id)
        if self._scheduler is None:
            await self._send(ws, "error", message="Scheduler not available", code="no_scheduler")
            return
        running = self._scheduler.toggle_job(msg.job_id)
        if running is not None:
            await self._send(ws, "automation_job_toggled", job_id=msg.job_id, running=running)
        else:
            await self._send(ws, "error",
                message="Job not found", code="job_not_found")

    async def _h_automation_update_job(self, ws: Any, msg: ClientAutomationUpdateJob) -> None:
        info = self._get_or_create_session()
        self._manager.touch(info.session_id)
        if self._scheduler is None:
            await self._send(ws, "error", message="Scheduler not available", code="no_scheduler")
            return
        effective_index, agent_config = self._resolve_automation_model(msg.model_index)
        ok = self._scheduler.update_job(
            msg.job_id,
            name=msg.name,
            prompt=msg.prompt,
            cron=msg.cron,
            tag=msg.tag,
            model_index=effective_index,
            agent_config=agent_config,
            push_gateways=list(msg.push_gateways),
        )
        if ok:
            await self._send(ws, "automation_job_updated", job_id=msg.job_id)
        else:
            await self._send(ws, "error",
                message="Job not found", code="job_not_found")

    async def _h_automation_delete_job(self, ws: Any, msg: ClientAutomationDeleteJob) -> None:
        info = self._get_or_create_session()
        self._manager.touch(info.session_id)
        if self._scheduler is None:
            await self._send(ws, "error", message="Scheduler not available", code="no_scheduler")
            return
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

    async def _h_automation_delete_execution(self, ws: Any, msg: ClientAutomationDeleteExecution) -> None:
        info = self._get_or_create_session()
        self._manager.touch(info.session_id)
        if self._scheduler is None:
            await self._send(ws, "error", message="Scheduler not available", code="no_scheduler")
            return
        sid = self._scheduler.delete_job_execution(msg.entry_id)
        if sid:
            # Clean up sub-agent session directory if it exists
            from encre.config import get_data_dir as _get_data_dir
            sub_agent_dir = _get_data_dir() / "sub_agents" / sid
            if sub_agent_dir.is_dir():
                shutil.rmtree(str(sub_agent_dir))
            self.broadcast_automation_update()
            await self._send(ws, "automation_execution_deleted", entry_id=msg.entry_id)
        else:
            await self._send(ws, "error",
                message="Execution not found", code="execution_not_found")

    async def _h_automation_rename_execution(self, ws: Any, msg: ClientAutomationRenameExecution) -> None:
        info = self._get_or_create_session()
        self._manager.touch(info.session_id)
        if self._scheduler is None:
            await self._send(ws, "error", message="Scheduler not available", code="no_scheduler")
            return
        new_name = (msg.new_name or "").strip()
        if not new_name:
            await self._send(ws, "error", message="Name cannot be empty", code="invalid_request")
            return
        ok = self._scheduler.rename_job_execution(msg.entry_id, new_name)
        if ok:
            self.broadcast_automation_update()
            await self._send(ws, "automation_execution_renamed", entry_id=msg.entry_id, new_name=new_name)
        else:
            await self._send(ws, "error",
                message="Execution not found", code="execution_not_found")

    async def _h_automation_get_history(self, ws: Any, msg: ClientAutomationGetHistory) -> None:
        info = self._get_or_create_session()
        self._manager.touch(info.session_id)
        if self._scheduler is None:
            await self._send(ws, "automation_job_history", history=[])
            return
        await self._send(
            ws,
            "automation_job_history",
            history=self._build_automation_history(),
        )
