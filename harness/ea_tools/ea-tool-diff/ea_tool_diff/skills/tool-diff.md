---
name: tool-diff
description: "Compare text, files, or directories and return a structured diff. Supports unified/context/JSON/HTML output formats for text and file comparisons, SHA-256 binary diff for non-text files, directory tree diff (files only-in-left/right/differing/identical), and statistics (added/removed lines, similarity ratio). Use this instead of bash `diff` for richer structured output and for binary/directory modes. TIP: Use action='statistics' when you only need a similarity ratio and change counts, not the full diff. AVOID: Comparing huge directories with action='directory' when you only care about a few files -- scope the paths first."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# diff

Compare text, files, or directories and return a structured diff. Supports unified/context/JSON/HTML output formats for text and file comparisons, SHA-256 binary diff for non-text files, directory tree diff (files only-in-left/right/differing/identical), and statistics (added/removed lines, similarity ratio). Use this instead of bash `diff` for richer structured output and for binary/directory modes. TIP: Use action='statistics' when you only need a similarity ratio and change counts, not the full diff. AVOID: Comparing huge directories with action='directory' when you only care about a few files -- scope the paths first.
