---
name: tool-cloud_storage
description: "Cloud object-storage operations for AWS S3, Google Cloud Storage (GCS), and Azure Blob Storage behind one interface. Actions vary by provider: list (list objects, optionally prefix-filtered), upload (upload a local file), download (download an object to a local path), delete (delete an object), info (object metadata), list_buckets (list all buckets/containers, S3/GCS only), sync_up (sync a local directory to S3, S3 only). Use this instead of shelling out to aws/gsutil/az CLIs -- it parses responses into structured output and resolves credentials from the environment. TIP: Use 'prefix' with action='list' to scope large buckets and avoid huge responses. AVOID: Passing access_key/secret_key/connection_string inline in shared sessions -- prefer environment variables for credentials."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# cloud_storage

Cloud object-storage operations for AWS S3, Google Cloud Storage (GCS), and Azure Blob Storage behind one interface. Actions vary by provider: list (list objects, optionally prefix-filtered), upload (upload a local file), download (download an object to a local path), delete (delete an object), info (object metadata), list_buckets (list all buckets/containers, S3/GCS only), sync_up (sync a local directory to S3, S3 only). Use this instead of shelling out to aws/gsutil/az CLIs -- it parses responses into structured output and resolves credentials from the environment. TIP: Use 'prefix' with action='list' to scope large buckets and avoid huge responses. AVOID: Passing access_key/secret_key/connection_string inline in shared sessions -- prefer environment variables for credentials.
