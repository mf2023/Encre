---
name: tool-fine_tuning_api
description: "WHAT: Create a fine-tuning job from an uploaded training file, or list existing fine-tuning jobs and their statuses, via the OpenAI-compatible Fine-tuning API. WHEN: Use after uploading a properly formatted JSONL training file via file_api, when you need a model specialised for your domain or task. WHEN NOT: Not for quick experimentation -- fine-tuning is slow, expensive, and irreversible; prefer prompt engineering or retrieval first. The backend must implement create_fine_tuning_job / list_fine_tuning_jobs or the call errors. TIPS: 'training_file' must be a file_id returned by file_api 'upload' with purpose='fine-tune'; 'model' must be a base model the backend allows fine-tuning. PITFALLS: Jobs can take hours and may fail mid-run -- poll list periodically and validate the training file format before submitting to avoid wasted quota."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# fine_tuning_api

WHAT: Create a fine-tuning job from an uploaded training file, or list existing fine-tuning jobs and their statuses, via the OpenAI-compatible Fine-tuning API. WHEN: Use after uploading a properly formatted JSONL training file via file_api, when you need a model specialised for your domain or task. WHEN NOT: Not for quick experimentation -- fine-tuning is slow, expensive, and irreversible; prefer prompt engineering or retrieval first. The backend must implement create_fine_tuning_job / list_fine_tuning_jobs or the call errors. TIPS: 'training_file' must be a file_id returned by file_api 'upload' with purpose='fine-tune'; 'model' must be a base model the backend allows fine-tuning. PITFALLS: Jobs can take hours and may fail mid-run -- poll list periodically and validate the training file format before submitting to avoid wasted quota.
