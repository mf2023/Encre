---
name: tool-file_api
description: "WHAT: Upload, list, retrieve, or delete files via the OpenAI-compatible Files API on the configured backend. Returns file IDs that other endpoints (batch, fine-tuning, assistants) accept. WHEN: Use to stage a JSONL input file for Batch API jobs, attach training data for fine-tuning, or manage previously uploaded files. WHEN NOT: Not for reading local files (use file_read) or for general HTTP uploads (use rest_client). The backend must implement upload_file / list_files / retrieve_file / delete_file or the call returns an error. TIPS: For 'upload' pass an absolute local path in 'file'; 'purpose' defaults to 'assistants' -- use 'batch' or 'fine-tune' when staging for those APIs. PITFALLS: Each action requires its own parameters (file for upload, file_id for retrieve/delete); mixing them silently no-ops. Large uploads may be subject to the backend's per-file size limits."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# file_api

WHAT: Upload, list, retrieve, or delete files via the OpenAI-compatible Files API on the configured backend. Returns file IDs that other endpoints (batch, fine-tuning, assistants) accept. WHEN: Use to stage a JSONL input file for Batch API jobs, attach training data for fine-tuning, or manage previously uploaded files. WHEN NOT: Not for reading local files (use file_read) or for general HTTP uploads (use rest_client). The backend must implement upload_file / list_files / retrieve_file / delete_file or the call returns an error. TIPS: For 'upload' pass an absolute local path in 'file'; 'purpose' defaults to 'assistants' -- use 'batch' or 'fine-tune' when staging for those APIs. PITFALLS: Each action requires its own parameters (file for upload, file_id for retrieve/delete); mixing them silently no-ops. Large uploads may be subject to the backend's per-file size limits.
