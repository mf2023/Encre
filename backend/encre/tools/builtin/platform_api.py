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
    description=(
        "WHAT: Upload, list, retrieve, or delete files via the OpenAI-compatible "
        "Files API on the configured backend. Returns file IDs that other endpoints "
        "(batch, fine-tuning, assistants) accept. "
        "WHEN: Use to stage a JSONL input file for Batch API jobs, attach training "
        "data for fine-tuning, or manage previously uploaded files. "
        "WHEN NOT: Not for reading local files (use file_read) or for general HTTP "
        "uploads (use rest_client). The backend must implement upload_file / "
        "list_files / retrieve_file / delete_file or the call returns an error. "
        "TIPS: For 'upload' pass an absolute local path in 'file'; 'purpose' "
        "defaults to 'assistants' -- use 'batch' or 'fine-tune' when staging for "
        "those APIs. "
        "PITFALLS: Each action requires its own parameters (file for upload, file_id "
        "for retrieve/delete); mixing them silently no-ops. Large uploads may be "
        "subject to the backend's per-file size limits."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["upload", "list", "retrieve", "delete"], "description": "File operation: 'upload' a local file, 'list' all uploaded files, 'retrieve' metadata for one file_id, or 'delete' a file_id."},
            "file": {"type": "string", "description": "Absolute local path (or base64 data) of the file to upload. Required for action='upload'."},
            "file_id": {"type": "string", "description": "ID of the file to retrieve or delete (as returned by 'upload' or 'list'). Required for action='retrieve' and action='delete'."},
            "purpose": {"type": "string", "description": "Intended use of the uploaded file -- one of 'assistants' (default), 'batch', 'fine-tune', or 'vision'. Must match what the downstream endpoint expects.", "default": "assistants"},
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
    description=(
        "WHAT: Create, retrieve, or list asynchronous batch processing jobs against "
        "the OpenAI-compatible Batch API. Batches run large volumes of requests "
        "off-line at lower cost. "
        "WHEN: Use when you have a JSONL file of requests (already uploaded via "
        "file_api) and want to process thousands of completions asynchronously "
        "within a 24h window. "
        "WHEN NOT: Not for interactive single requests -- call the model directly. "
        "The backend must implement create_batch / retrieve_batch / list_batches or "
        "the call returns an error. "
        "TIPS: Set 'endpoint' to match the API version of your JSONL requests "
        "('/v1/chat/completions' by default); 'completion_window' is usually '24h'. "
        "PITFALLS: Polling retrieve too frequently is wasteful -- batches typically "
        "take minutes to hours; check status a few times per window."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create", "retrieve", "list"], "description": "Batch operation: 'create' submits a new batch from an input file, 'retrieve' fetches the status of one batch_id, 'list' enumerates all batches."},
            "input_file_id": {"type": "string", "description": "file_id of the JSONL input file (uploaded via file_api with purpose='batch'). Required for action='create'."},
            "endpoint": {"type": "string", "description": "Target API endpoint for each request in the batch -- typically '/v1/chat/completions' or '/v1/embeddings'. Required for action='create'.", "default": "/v1/chat/completions"},
            "completion_window": {"type": "string", "description": "Maximum time the backend has to complete the batch, e.g. '24h'. Most backends only support '24h'.", "default": "24h"},
            "batch_id": {"type": "string", "description": "ID of the batch to retrieve (as returned by 'create' or 'list'). Required for action='retrieve'."},
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
    description=(
        "WHAT: Create a fine-tuning job from an uploaded training file, or list "
        "existing fine-tuning jobs and their statuses, via the OpenAI-compatible "
        "Fine-tuning API. "
        "WHEN: Use after uploading a properly formatted JSONL training file via "
        "file_api, when you need a model specialised for your domain or task. "
        "WHEN NOT: Not for quick experimentation -- fine-tuning is slow, expensive, "
        "and irreversible; prefer prompt engineering or retrieval first. The backend "
        "must implement create_fine_tuning_job / list_fine_tuning_jobs or the call "
        "errors. "
        "TIPS: 'training_file' must be a file_id returned by file_api 'upload' with "
        "purpose='fine-tune'; 'model' must be a base model the backend allows "
        "fine-tuning. "
        "PITFALLS: Jobs can take hours and may fail mid-run -- poll list "
        "periodically and validate the training file format before submitting to "
        "avoid wasted quota."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create", "list"], "description": "Fine-tuning operation: 'create' starts a new job from a training file, 'list' enumerates all jobs and their statuses."},
            "training_file": {"type": "string", "description": "file_id of the JSONL training data (uploaded via file_api with purpose='fine-tune'). Required for action='create'."},
            "model": {"type": "string", "description": "Name of the base model to fine-tune (e.g. 'gpt-4o', 'gpt-3.5-turbo'). Must be a model the backend allows fine-tuning. Required for action='create'."},
        },
        "required": ["action"],
    },
    execute=lambda **kw: _finetune_create_execute(**kw) if kw.get("action") == "create" else _finetune_list_execute(**kw),
    intents=["general", "data"],
    category="data",
    is_concurrency_safe=True,
)

__all__ = ["EncreFileApiTool", "EncreBatchApiTool", "EncreFineTuneApiTool"]
