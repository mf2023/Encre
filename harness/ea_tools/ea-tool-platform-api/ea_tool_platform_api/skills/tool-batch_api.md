---
name: tool-batch_api
description: "WHAT: Create, retrieve, or list asynchronous batch processing jobs against the OpenAI-compatible Batch API. Batches run large volumes of requests off-line at lower cost. WHEN: Use when you have a JSONL file of requests (already uploaded via file_api) and want to process thousands of completions asynchronously within a 24h window. WHEN NOT: Not for interactive single requests -- call the model directly. The backend must implement create_batch / retrieve_batch / list_batches or the call returns an error. TIPS: Set 'endpoint' to match the API version of your JSONL requests ('/v1/chat/completions' by default); 'completion_window' is usually '24h'. PITFALLS: Polling retrieve too frequently is wasteful -- batches typically take minutes to hours; check status a few times per window."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# batch_api

WHAT: Create, retrieve, or list asynchronous batch processing jobs against the OpenAI-compatible Batch API. Batches run large volumes of requests off-line at lower cost. WHEN: Use when you have a JSONL file of requests (already uploaded via file_api) and want to process thousands of completions asynchronously within a 24h window. WHEN NOT: Not for interactive single requests -- call the model directly. The backend must implement create_batch / retrieve_batch / list_batches or the call returns an error. TIPS: Set 'endpoint' to match the API version of your JSONL requests ('/v1/chat/completions' by default); 'completion_window' is usually '24h'. PITFALLS: Polling retrieve too frequently is wasteful -- batches typically take minutes to hours; check status a few times per window.
