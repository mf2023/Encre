---
name: fast-io
description: Workspaces for agentic teams.
metadata:
  source: encre
  tags: 
user_invocable: true
hidden: true
context: inline
---

## Fast Io
# Fast.io MCP Server -- AI Agent Guide

**Version:** 1.223
**Last Updated:** 2026-05-22

The definitive guide for AI agents using the Fast.io MCP server. Covers why and how to use the platform: product capabilities, the free agent plan, authentication, core concepts (workspaces, shares, intelligence, previews, comments, URL import, metadata, workflow, ownership transfer), 12 end-to-end workflows, interactive MCP App widgets, and all 19 consolidated tools with action-based routing.

> **Versioned guide.** This guide is versioned and updated with each server release. The version number at the top of this document tracks tool parameters, ID formats, and API behavior changes. If you encounter unexpected errors, the guide version may have changed since you last read it.

> **Recent parameter changes (v2026.05.22 → v2026.05.23):**
> - **`event` tool:** the `created-min` / `created-max` filter names were renamed to `created_min` / `created_max` (snake_case). The old hyphenated names are silently migrated to the new names by the server — existing agents continue to work. New agents should use snake_case directly.
> - **`apps.extra_params`, `approval.properties`, `execute.body`, `execute.params`:** these free-form JSON parameters are now published as `{type: "string"}` in the tool schema (to satisfy strict-mode validators in OpenAI Apps SDK / Gemini API). The server still accepts either a native JSON object/array (auto-stringified) OR a pre-stringified JSON string at runtime — you can keep sending native objects from Claude Desktop and they will be auto-converted.
> - **`/file/workspace|share` pass-through:** now accepts either `Mcp-Session-Id` (existing path) OR `Authorization: Bearer` (new — unblocks OAuth-only clients streaming large files without first establishing an MCP tool-auth session). Fresh Bearer tokens are used even when the DO session has a stale or expired session-stored token.
> - **New `resource://status` MCP resource (v2026.05.24):** lightweight server-status resource alongside the existing `session://status` and `skill://guide` resources. Returns `{name, version, environment, transports, mcp_protocol_versions_supported, time, documentation}` — no auth, no session state. Added so MCP host UIs (ChatGPT Apps SDK in particular) that probe a well-known status URI can display server health without spending a tool call. For session-bound state continue using `session://status` (the resource) or `auth action=status` (the tool).

> **Platform reference.** For a comprehensive overview of Fast.io's capabilities, the agent plan, key workflows, and upgrade paths, see [documentation](external documentation).

> **ID parameter taxonomy.** Four canonical ID parameter names appear across tools — they are intentionally distinct, not interchangeable. Pick the one that matches the operation's domain:
>
> - **`workspace_id`** — workspace opaque ID. Use when only workspaces are valid (not shares or other contexts). Example: `events action workspace-stream workspace_id="..."`.
> - **`profile_id`** — polymorphic context ID. Pair with `profile_type` = `workspace` | `share` | `org`. Use instead of `workspace_id` when the operation also accepts shares. Example: `storage action list profile_type="share" profile_id="..." node_id="root"`.
> - **`entity_id`** — opaque ID of a specific object (file, comment, worklog entry, etc.). Pair with `entity_type` to disambiguate. Example: `worklog action list entity_type="task" entity_id="..."`.
> - **`node_id`** — storage tree node opaque ID. Both files and folders are nodes — use this name regardless of which. Example: `storage action details profile_type="workspace" profile_id="..." node_id="..."`.

---

## 1. Overview

**Workspaces for Agentic Teams. Collaborate, share, and query with AI -- all through one API, free.**

Fast.io provides workspaces for agentic teams -- where agents collaborate with other agents and with humans. Upload outputs, create branded shares, ask questions about documents using built-in AI, and hand everything off to a human when the job is done. No infrastructure to manage, no subscriptions to set up, no credit card required.

### The Problem Fast.io Solves

Agentic teams -- groups of agents working together and with humans -- need a shared place to work. Today, agents cobble together S3 buckets, presigned URLs, email attachments, and custom download pages. Every agent reinvents collaboration, and there is no shared workspace where agents and humans can see the same files, track activity, and hand off work.

When agents need to *understand* documents -- not just store them -- they have to download files, parse dozens of formats, build search indexes, and manage their own RAG pipeline. That is a lot of infrastructure for what should be a simple question: "What does this document say?"

| Problem | Fast.io Solution |
|---------|-----------------|
| No shared workspace for agentic teams | Workspaces where agents and humans collaborate with file preview, versioning, and AI |
| Agent-to-agent coordination lacks structure | Shared workspaces with activity feeds, comments, and real-time sync across team members |
| Sharing outputs with humans is awkward | Purpose-built shares (Send, Receive, Exchange) with link sharing, passwords, expiration |
| Collecting files from humans is harder | Receive shares let humans upload directly to your workspace -- no email attachments |
| Understanding document contents | Built-in AI reads, summarizes, and answers questions about your files |
| Building a RAG pipeline from scratch | Enable intelligence on a workspace and documents are automatically indexed, summarized, and queryable |
| Finding the right file in a large collection | Storage search finds documents by keyword or meaning (semantic search when intelligence is enabled) |
| Handing a project off to a human | One-click ownership transfer -- human gets the org, agent keeps admin access |
| Tracking what happened | Full audit trail with AI-powered activity summaries |
| Cost | Free. 50 GB storage, 5,000 monthly credits, no credit card |

### MCP Server

This MCP server exposes 19 consolidated tools that cover the full Fast.io REST API surface. Every authenticated API endpoint has a corresponding tool action, and the server handles session management automatically.

**All API access goes through the MCP tools.** Do not make direct HTTP calls to `api.fast.io` or the MCP server -- the tools handle authentication, session management, error recovery, and response formatting automatically. The only exceptions are binary transfers: `POST /blob` on the MCP server for uploads (the tool provides the curl command), download URLs returned by tools (which are pre-authenticated), and `GET /file/` pass-through endpoints on the MCP server for large file streaming. Everything else must use the tools.

Once a user authenticates, the auth token is stored in the server session and automatically attached to all subsequent API calls. There is no need to pass tokens between tool invocations.

### Server Endpoints

- **Production:** `mcp.fast.io`
- **Development:** `mcp.fastdev1.com`

Two transports are available on each:

- **Streamable HTTP at `/mcp`** -- the preferred transport for new integrations.
- **SSE at `/sse`** -- a legacy transport maintained for backward compatibility.

### MCP Resources

The server exposes static MCP resources, widget resources, and file download resource templates. Clients can read them via `resources/list` and `resources/read`:

| URI | Name | Description | MIME Type |
|-----|------|-------------|-----------|
| `skill://guide` | skill-guide | Full agent guide (this document) with all 19 tools, workflows, and platform documentation | `text/markdown` |
| `session://status` | session-status | Current authentication state: `authenticated` boolean, `user_id`, `user_email`, `auth_method` (`"api_key"`, `"jwt"`, or `"oauth"` -- how the session was authenticated), `token_expires_at` (Unix epoch)

> *This skill was truncated from its original 277306 chars. For the full version, use `web_search`/`web_fetch` to find the latest documentation.*
