---
name: tool-codebase_context
description: "Return indexed context for a workspace file: full source, imports, dependents, and exports. Use this to understand how a file fits into the codebase before editing it, instead of opening each related file individually. Requires the workspace code index to be ready. TIP: Call this once before a multi-file refactor to see upstream callers and downstream dependencies in one shot. AVOID: Calling this on files outside the indexed workspace -- it returns an error if the index is not ready."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# codebase_context

Return indexed context for a workspace file: full source, imports, dependents, and exports. Use this to understand how a file fits into the codebase before editing it, instead of opening each related file individually. Requires the workspace code index to be ready. TIP: Call this once before a multi-file refactor to see upstream callers and downstream dependencies in one shot. AVOID: Calling this on files outside the indexed workspace -- it returns an error if the index is not ready.
