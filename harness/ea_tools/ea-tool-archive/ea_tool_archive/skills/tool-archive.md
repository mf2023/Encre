---
name: tool-archive
description: "Create, extract, list, or inspect archives in zip, tar, gz, bz2, or xz format. Use this instead of bash `tar`/`zip`/`unzip` -- it provides a single interface across formats, returns structured JSON for list/info actions, and handles directory recursion. Create from files or directories, extract to a destination, list entries, or get archive metadata (size, entry count, format). TIP: For 'create', set 'format' explicitly to avoid ambiguity from the file extension. AVOID: Extracting untrusted archives with action='extract' into sensitive directories -- inspect with action='list' first."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# archive

Create, extract, list, or inspect archives in zip, tar, gz, bz2, or xz format. Use this instead of bash `tar`/`zip`/`unzip` -- it provides a single interface across formats, returns structured JSON for list/info actions, and handles directory recursion. Create from files or directories, extract to a destination, list entries, or get archive metadata (size, entry count, format). TIP: For 'create', set 'format' explicitly to avoid ambiguity from the file extension. AVOID: Extracting untrusted archives with action='extract' into sensitive directories -- inspect with action='list' first.
