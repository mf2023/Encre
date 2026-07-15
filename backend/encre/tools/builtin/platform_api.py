#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from typing import Any

from encre.tools.base import build_tool


def _get_backend():
    from encre.tools.builtin.agent import _resolve_loop
    loop = _resolve_loop()
    if loop and loop.backend and hasattr(loop.backend, "upload_file"):
        return loop.backend
    return None


async def _file_upload_execute(**kwargs: Any) -> str:
    backend = _get_backend()
    if backend is None or not hasattr(backend, "upload_file"):
        return "Error: Backend does not support Files API"
    try:
        file = kwargs.get("file", "")
        purpose = kwargs.get("purpose", "assistants")
        result = await backend.upload_file(file=file, purpose=purpose)
        return json.dumps({"id": result.id, "filename": result.filename, "bytes": result.bytes, "purpose": result.purpose} if hasattr(result, "id") else result, indent=2, default=str)
    except Exception as e:
        return f"Error uploading file: {e}"


async def _file_list_execute(**kwargs: Any) -> str:
    backend = _get_backend()
    if backend is None or not hasattr(backend, "list_files"):
        return "Error: Backend does not support Files API"
    try:
        result = await backend.list_files()
        files = [{"id": f.id, "filename": f.filename, "bytes": f.bytes} for f in result.data]
        return json.dumps(files, indent=2, default=str)
    except Exception as e:
        return f"Error listing files: {e}"


async def _file_retrieve_execute(**kwargs: Any) -> str:
    backend = _get_backend()
    if backend is None or not hasattr(backend, "retrieve_file"):
        return "Error: Backend does not support Files API"
    try:
        file_id = kwargs.get("file_id", "")
        result = await backend.retrieve_file(file_id=file_id)
        return json.dumps({"id": result.id, "filename": result.filename} if hasattr(result, "id") else result, indent=2, default=str)
    except Exception as e:
        return f"Error retrieving file: {e}"


async def _file_delete_execute(**kwargs: Any) -> str:
    backend = _get_backend()
    if backend is None or not hasattr(backend, "delete_file"):
        return "Error: Backend does not support Files API"
    try:
        file_id = kwargs.get("file_id", "")
        result = await backend.delete_file(file_id=file_id)
        return json.dumps({"deleted": result.deleted} if hasattr(result, "deleted") else result, indent=2, default=str)
    except Exception as e:
        return f"Error deleting file: {e}"


async def _batch_create_execute(**kwargs: Any) -> str:
    backend = _get_backend()
    if backend is None or not hasattr(backend, "create_batch"):
        return "Error: Backend does not support Batch API"
    try:
        input_file_id = kwargs.get("input_file_id", "")
        endpoint = kwargs.get("endpoint", "/v1/chat/completions")
        completion_window = kwargs.get("completion_window", "24h")
        result = await backend.create_batch(input_file_id=input_file_id, endpoint=endpoint, completion_window=completion_window)
        return json.dumps({"id": result.id, "status": result.status} if hasattr(result, "id") else result, indent=2, default=str)
    except Exception as e:
        return f"Error creating batch: {e}"


async def _batch_retrieve_execute(**kwargs: Any) -> str:
    backend = _get_backend()
    if backend is None or not hasattr(backend, "retrieve_batch"):
        return "Error: Backend does not support Batch API"
    try:
        batch_id = kwargs.get("batch_id", "")
        result = await backend.retrieve_batch(batch_id=batch_id)
        return json.dumps({"id": result.id, "status": result.status} if hasattr(result, "id") else result, indent=2, default=str)
    except Exception as e:
        return f"Error retrieving batch: {e}"


async def _batch_list_execute(**kwargs: Any) -> str:
    backend = _get_backend()
    if backend is None or not hasattr(backend, "list_batches"):
        return "Error: Backend does not support Batch API"
    try:
        result = await backend.list_batches()
        batches = [{"id": b.id, "status": b.status} for b in result.data]
        return json.dumps(batches, indent=2, default=str)
    except Exception as e:
        return f"Error listing batches: {e}"


async def _finetune_create_execute(**kwargs: Any) -> str:
    backend = _get_backend()
    if backend is None or not hasattr(backend, "create_fine_tuning_job"):
        return "Error: Backend does not support Fine-tuning API"
    try:
        training_file = kwargs.get("training_file", "")
        model = kwargs.get("model", "")
        result = await backend.create_fine_tuning_job(training_file=training_file, model=model)
        return json.dumps({"id": result.id, "status": result.status} if hasattr(result, "id") else result, indent=2, default=str)
    except Exception as e:
        return f"Error creating fine-tuning job: {e}"


async def _finetune_list_execute(**kwargs: Any) -> str:
    backend = _get_backend()
    if backend is None or not hasattr(backend, "list_fine_tuning_jobs"):
        return "Error: Backend does not support Fine-tuning API"
    try:
        result = await backend.list_fine_tuning_jobs()
        jobs = [{"id": j.id, "status": j.status} for j in result.data]
        return json.dumps(jobs, indent=2, default=str)
    except Exception as e:
        return f"Error listing fine-tuning jobs: {e}"


EncreFileApiTool = build_tool(
    name="file_api",
    description="Upload, list, retrieve, or delete files via the OpenAI Files API",
    input_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["upload", "list", "retrieve", "delete"], "description": "File operation"},
            "file": {"type": "string", "description": "File path or base64 data (for upload)"},
            "file_id": {"type": "string", "description": "File ID (for retrieve/delete)"},
            "purpose": {"type": "string", "description": "File purpose (for upload)", "default": "assistants"},
        },
        "required": ["action"],
    },
    execute=lambda **kw: _file_upload_execute(**kw) if kw.get("action") == "upload" else (_file_list_execute(**kw) if kw.get("action") == "list" else (_file_retrieve_execute(**kw) if kw.get("action") == "retrieve" else _file_delete_execute(**kw))),
    intents=["general", "data"],
    category="data",
    is_concurrency_safe=True,
)

EncreBatchApiTool = build_tool(
    name="batch_api",
    description="Create, retrieve, or list batch processing jobs",
    input_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create", "retrieve", "list"], "description": "Batch operation"},
            "input_file_id": {"type": "string", "description": "Input file ID (for create)"},
            "endpoint": {"type": "string", "description": "API endpoint (for create)", "default": "/v1/chat/completions"},
            "completion_window": {"type": "string", "description": "Completion window", "default": "24h"},
            "batch_id": {"type": "string", "description": "Batch ID (for retrieve)"},
        },
        "required": ["action"],
    },
    execute=lambda **kw: _batch_create_execute(**kw) if kw.get("action") == "create" else (_batch_retrieve_execute(**kw) if kw.get("action") == "retrieve" else _batch_list_execute(**kw)),
    intents=["general", "data"],
    category="data",
    is_concurrency_safe=True,
)

EncreFineTuneApiTool = build_tool(
    name="fine_tuning_api",
    description="Create or list fine-tuning jobs",
    input_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create", "list"], "description": "Fine-tuning operation"},
            "training_file": {"type": "string", "description": "Training file ID (for create)"},
            "model": {"type": "string", "description": "Base model to fine-tune (for create)"},
        },
        "required": ["action"],
    },
    execute=lambda **kw: _finetune_create_execute(**kw) if kw.get("action") == "create" else _finetune_list_execute(**kw),
    intents=["general", "data"],
    category="data",
    is_concurrency_safe=True,
)

__all__ = ["EncreFileApiTool", "EncreBatchApiTool", "EncreFineTuneApiTool"]
