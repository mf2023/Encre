/**
 * Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
 *
 * This file is part of Encre.
 * The Encre project belongs to the Dunimd Team.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * You may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * DISCLAIMER: Users must comply with applicable AI regulations.
 * Non-compliance may result in service termination or legal liability.
 */

import type { ToolCallState } from "../core/types.js";
import { t } from "../features/i18n.js";
import { renderDiffHtml } from "./diff_render.js";
import { escapeHtml } from "./chat_markdown.js";
import { TransitionHelper } from "../ui/transition-helper.js";

// === Tool helpers ===================================================================

// === Tool category helpers (match ALL backend tools) ================================

export function isTerminalTool(name: string): boolean {
  return name === "bash" || name === "bash_output" || name === "bash_kill" || name === "bash_list" ||
         name === "shell" || name === "terminal" || name === "run_command" || name === "chat.terminal";
}

export function isFileMutationTool(name: string): boolean {
  if (
    name === "write" || name === "file_write" || name === "write_file" ||
    name === "edit" || name === "file_edit" || name === "edit_file" ||
    name === "delete_file"
  ) {
    return true;
  }
  // Fallback for provider/tool-alias variants
  return /(write|edit|delete)/i.test(name) && /file/i.test(name);
}

export function isFileReadTool(name: string): boolean {
  return name === "read" || name === "file_read";
}

const TERMINAL_TOOLS = new Set([
  "bash", "bash_output", "bash_kill", "bash_list",
  "shell", "terminal", "run_command", "chat.terminal",
]);

const FILE_MUTATION_TOOLS = new Set([
  "write", "file_write", "edit", "file_edit",
  "delete_file", "apply_patch",
]);

const FILE_READ_TOOLS = new Set(["read", "file_read"]);

export function isExpandableStripTool(name: string): boolean {
  return name === "search" || name === "grep" || name === "glob" || name === "codebase" ||
         name === "web_search";
}

export function isToolItemTool(name: string): boolean {
  return name === "skill" || name === "mcp" || name.startsWith("mcp__") ||
         name === "memory" || name.startsWith("memory_") ||
         name === "task" || name.startsWith("task_") ||
         name === "image" || name === "spreadsheet" || name.startsWith("cron_") || name === "todo" ||
         name === "find_tool" ||
         name === "web_fetch" || name === "git" || name === "lsp" || name === "notebook" ||
         name === "rest_client" || name === "browser" || name === "database" || name === "docker" ||
         name === "pdf" || name === "deploy" || name === "apply_patch" ||
         name === "computer" || name === "desktop";
}

export function isHiddenTool(name: string): boolean {
  if (name === "task" || name.startsWith("task_")) return true;
  if (name === "memory" || name.startsWith("memory_")) return true;
  if (name.startsWith("cron_")) return true;
  return name === "todo" || name === "find_tool" || name === "lsp";
}

export function compactText(value: unknown, max = 88): string {
  if (value === undefined || value === null) return "";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  const oneLine = text.replace(/\s+/g, " ").trim();
  return oneLine.length > max ? `${oneLine.slice(0, max - 3)}...` : oneLine;
}

/**
 * Resolves the target file path of a file tool call.
 *
 * `tool_call_end` normally replaces `params` with the parsed argument object,
 * but every render between the first result and that event still sees the raw
 * `arguments` string — and history replay never re-sends `tool_call_end` at
 * all. In both cases `params.path` is missing, so the strip summary fell back
 * to dumping the tool result (i.e. the file's first lines). Parse defensively
 * here so the path is available regardless of how far the stream got.
 */
export function toolFilePath(tc: ToolCallState): string {
  const PATH_KEYS = ["file_path", "path", "filename", "filepath", "file", "target"];
  const direct = firstParam(tc, PATH_KEYS);
  if (direct) return direct;
  const raw = tc.params?.arguments;
  if (typeof raw === "string" && raw.trim().startsWith("{")) {
    try {
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      for (const key of PATH_KEYS) {
        const v = parsed[key];
        if (typeof v === "string" && v.trim()) return v;
      }
    } catch {
      // Partial JSON while the arguments are still streaming — ignore.
    }
  }
  return "";
}

/**
 * Trims a path to fit a strip summary without ever cutting off the file name,
 * which is the part that identifies what the tool actually touched.
 * Keeps `…/<parent>/<name>` when it fits, otherwise degrades to `…/<name>`.
 */
export function compactPath(p: string, max = 88): string {
  const path = (p || "").trim();
  if (!path) return "";
  if (path.length <= max) return path;
  const parts = path.split(/[\\/]+/).filter(Boolean);
  const name = parts[parts.length - 1] || path;
  if (parts.length >= 2) {
    const tail2 = `…/${parts[parts.length - 2]}/${name}`;
    if (tail2.length <= max) return tail2;
  }
  const tail1 = `…/${name}`;
  return tail1.length <= max ? tail1 : compactText(name, max);
}

/**
 * Try to extract a short human-readable summary from a JSON result string.
 * Returns null if the input is not valid JSON or no usable field is found.
 */
export function extractJsonSummary(result: string): string | null {
  const trimmed = result.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return null;
  try {
    const parsed = JSON.parse(trimmed);
    if (Array.isArray(parsed)) {
      return `${parsed.length} item${parsed.length === 1 ? "" : "s"}`;
    }
    if (typeof parsed === "object" && parsed !== null) {
      // Prefer common human-readable fields.
      const preferred = [
        "summary", "message", "content", "result", "output",
        "stdout", "stderr", "error", "status", "data",
        "results", "matches", "items", "files", "count", "total",
      ];
      for (const key of preferred) {
        if (!(key in parsed)) continue;
        const v = parsed[key];
        if (v === undefined || v === null) continue;
        if (typeof v === "string") return compactText(v, 88);
        if (typeof v === "number" || typeof v === "boolean") return String(v);
        if (Array.isArray(v)) {
          const label = key === "results" ? "result" : key === "matches" ? "match" : key === "files" ? "file" : "item";
          return `${v.length} ${label}${v.length === 1 ? "" : "s"}`;
        }
      }
      const keys = Object.keys(parsed);
      if (keys.length > 0) return `${keys.length} field${keys.length === 1 ? "" : "s"}`;
    }
  } catch {
    // Not JSON -- fall through.
  }
  return null;
}

export function firstParam(tc: ToolCallState, keys: string[]): string {
  for (const key of keys) {
    const value = tc.params[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return "";
}

export function getToolIcon(name: string, terminal?: string): string {
  if (isTerminalTool(name)) {
    // All terminal tools share one glyph (the `>_` prompt, matching the
    // PowerShell icon). No per-shell differentiation.
    return "terminal";
  }
  if (isFileMutationTool(name)) return "pencil-line";
  if (isFileReadTool(name)) return "eye";
  // Web / search / discovery
  if (name === "web_search" || name === "web_fetch") return "globe";
  if (name === "search" || name === "grep") return "search";
  if (name === "codebase" || name.startsWith("codebase")) return "search";
  if (name === "find_tool") return "compass";
  if (name === "glob") return "folder-search";
  // Memory / task / cron (specific match before the prefix fallbacks)
  if (name === "memory_profile") return "user-circle";
  if (name === "memory" || name.startsWith("memory_")) return "database";
  if (name === "task" || name.startsWith("task_")) return "list-checks";
  if (name.startsWith("cron_")) return "clock-9";
  // Skills / MCP / agents / orchestration
  if (name === "skill") return "wand-2";
  if (name === "mcp" || name.startsWith("mcp__")) return "plug";
  if (name === "agent") return "zap";
  if (name === "swarm") return "users";
  if (name === "workflow") return "workflow";
  // Compute / automation environments
  if (name === "browser") return "monitor";
  if (name === "computer" || name === "computer_use" || name === "vlm_computer_use" || name === "desktop") return "container";
  if (name === "docker") return "container";
  if (name === "ssh") return "terminal";
  // Dev tooling
  if (name === "notebook") return "notebook-pen";
  if (name === "git") return "git-branch";
  if (name === "github") return "github";
  if (name === "lsp") return "code-2";
  if (name === "database") return "database";
  if (name === "diff") return "git-compare";
  if (name === "json_tool") return "braces";
  if (name === "lint_format") return "check-check";
  if (name === "test_run") return "flask-conical";
  if (name === "env_manager") return "settings-2";
  if (name === "apply_patch") return "git-pull-request";
  if (name === "manage") return "settings";
  // Content / media generation
  if (name === "pdf" || name === "document") return "file-text";
  if (name === "presentation") return "presentation";
  if (name === "spreadsheet") return "table";
  if (name === "chart") return "bar-chart-3";
  if (name === "diagram") return "workflow";
  if (name === "image" || name === "generate_image" || name === "edit_image" || name === "image_variation") return "image";
  if (name === "qr_code") return "qr-code";
  if (name === "media") return "film";
  if (name === "transcribe_audio" || name === "translate_audio") return "mic";
  if (name === "translation") return "languages";
  if (name === "archive") return "archive";
  if (name === "hash_crypto") return "hash";
  // Cloud / network / provider APIs
  if (name === "rest_client" || name === "cloud_storage") return "cloud";
  if (name === "deploy") return "rocket";
  if (name === "email") return "mail";
  if (name === "notify") return "bell";
  if (name === "file_api") return "file";
  if (name === "batch_api") return "layers";
  if (name === "fine_tuning_api") return "sliders-horizontal";
  if (name === "create_embeddings") return "boxes";
  if (name === "create_moderation") return "shield-check";
  // Misc known cards
  if (name === "todo") return "check-circle-2";
  if (name === "plan") return "file-text";
  if (name === "question") return "help-circle";
  if (name === "compact") return "shrink";
  if (name === "info") return "layout-dashboard";
  // Fallback: never leave a tool with a blank icon gap — show a neutral
  // "tool" glyph so unmapped/MCP/provider tools still read as tool calls.
  return "wrench";
}

const TERMINAL_LABELS: Record<string, string> = {
  auto: "Shell",
  bash: "Bash",
  cmd: "CMD",
  powershell: "PowerShell",
  pwsh: "pwsh",
  python: "Python",
  node: "Node.js",
  irb: "Ruby",
  julia: "Julia",
  lua: "Lua",
  php: "PHP",
  R: "R",
};

export function formatToolName(name: string, terminal?: string): string {
  if (terminal && (name === "bash" || name === "shell" || name === "chat.terminal" || name === "run_command")) {
    return TERMINAL_LABELS[terminal] || terminal.charAt(0).toUpperCase() + terminal.slice(1);
  }
  const labels: Record<string, string> = {
    "chat.terminal": "Bash",
    bash: "Bash", bash_output: "Bash Output", bash_kill: "Bash", bash_list: "Bash",
    shell: "Shell", terminal: "Terminal", run_command: "Bash",
    web_search: "Web Search", web_fetch: "Web Fetch", find_tool: "Find Tool",
    read: "Read File", file_read: "Read File", write: "Write File", file_write: "Write File",
    edit: "Edit File", file_edit: "Edit File", apply_patch: "Apply Patch",
    mcp: "MCP", lsp: "LSP", git: "Git",
    memory_create: "Memory", memory_read: "Memory", memory_update: "Memory", memory_delete: "Memory", memory_search: "Memory",
    task_create: "Task", task_list: "Task", task_get: "Task", task_update: "Task", task_stop: "Task", task_output: "Task",
    cron_create: "Cron", cron_delete: "Cron", cron_list: "Cron",
    rest_client: "Rest Client", desktop: "Desktop", computer: "Computer",
    question: "Question", memory_profile: "Memory Profile",
    compact: "Compress",
    info: "Info Card",
  };
  if (labels[name]) return labels[name];
  if (name.startsWith("mcp__")) return "MCP";
  if (name === "agent") return "Agent";
  return name.replace(/_/g, " ").replace(/\b\w/g, (ch) => ch.toUpperCase());
}

export function getToolSummary(tc: ToolCallState): string {
  // For tools with result, show result summary instead of params
  if (tc.result) {
    // Terminal tools: strip-summary shows the command, body shows result
    if (TERMINAL_TOOLS.has(tc.name)) {
      const cmd = firstParam(tc, ["command", "cmd", "input", "shell_command", "script"]);
      return compactText(cmd, 88);
    }
    // If the backend returned JSON, extract a readable field instead of
    // dumping the raw serialized object into the strip summary.
    const jsonSummary = extractJsonSummary(tc.result);
    if (jsonSummary) return jsonSummary;
    if (tc.name === "web_search") return compactText(tc.result, 88);
    if (tc.name === "web_fetch") return compactText(tc.result, 88);
    if (tc.name === "search" || tc.name === "grep" || tc.name === "codebase") {
      const match = tc.result.match(/(\d+)\s*match/i);
      return match ? t("chat.toolMatches", { count: parseInt(match[1], 10) }) : compactText(tc.result, 88);
    }
    if (tc.name === "glob") {
      const count = tc.result.trim().split("\n").filter((l) => l.trim()).length;
      return t("chat.toolFiles", { count });
    }
    if (tc.name === "git") return compactText(tc.result, 88);
    if (tc.name === "find_tool") return t("chat.toolDiscoverTools");
    if (tc.name === "skill") return compactText(tc.result, 88);
    if (tc.name === "mcp") return compactText(tc.result, 88);
    if (tc.name === "memory") return compactText(tc.result, 88);
    if (tc.name === "task") return compactText(tc.result, 88);
    if (tc.name === "lsp") return compactText(tc.result, 88);
    if (tc.name === "notebook") return compactText(tc.result, 88);
    if (tc.name === "browser") return compactText(tc.result, 88);
    if (tc.name === "database") return compactText(tc.result, 88);
    if (tc.name === "docker") return compactText(tc.result, 88);
    if (tc.name === "pdf") return compactText(tc.result, 88);
    if (tc.name === "deploy") return compactText(tc.result, 88);
    // File read/write tools always show WHICH file was targeted, never the
    // tool result: file_read returns the file's raw content, so falling back
    // to `compactText(tc.result)` turned the summary into a dump of its first
    // lines and hid the file name entirely.
    if (FILE_READ_TOOLS.has(tc.name) || FILE_MUTATION_TOOLS.has(tc.name)) {
      return compactPath(toolFilePath(tc), 88);
    }
    return compactText(tc.result, 88);
  }
  // No result yet — show minimal param hint (not full params)
  if (isTerminalTool(tc.name)) {
    return compactText(firstParam(tc, ["command", "cmd", "input", "shell_command", "script"]), 96);
  }
  if (tc.name === "web_search") return compactText(firstParam(tc, ["query", "q"]), 88);
  if (tc.name === "web_fetch") return compactText(firstParam(tc, ["url", "uri"]), 88);
  if (FILE_READ_TOOLS.has(tc.name) || FILE_MUTATION_TOOLS.has(tc.name)) {
    return compactPath(toolFilePath(tc), 88);
  }
  if (tc.name === "search" || tc.name === "grep" || tc.name === "glob" || tc.name === "codebase") {
    return compactText(firstParam(tc, ["query", "pattern", "glob", "path"]), 88);
  }
  if (tc.name === "skill") return compactText(firstParam(tc, ["name", "skill"]), 88);
  if (tc.name === "agent") return compactText(firstParam(tc, ["prompt", "description", "agent_name"]), 88);
  if (tc.name === "mcp" || tc.name.startsWith("mcp__")) return compactText(firstParam(tc, ["tool", "name"]), 88);
  if (tc.name === "find_tool") return t("chat.toolDiscoverTools");
  const keys = Object.keys(tc.params).filter(k => k !== "id");
  if (keys.length > 0) {
    return compactText(tc.params[keys[0]], 88);
  }
  return "";
}

export function getToolInlineSummary(tc: ToolCallState): string {
  if (tc.name === "find_tool") return t("chat.toolDiscoverTools");
  if (tc.name === "mcp" || tc.name.startsWith("mcp__")) {
    const mcpTool = firstParam(tc, ["tool", "name", "function"]);
    return compactText(mcpTool || t("general.selectToolCall"), 42);
  }
  if (tc.name === "memory" || tc.name.startsWith("memory_")) {
    const hint = firstParam(tc, ["query", "name", "path"]);
    return compactText(hint || t("general.memoryAction"), 42);
  }
  if (tc.name === "task" || tc.name.startsWith("task_")) {
    const hint = firstParam(tc, ["id", "title", "task_id"]);
    return compactText(hint || t("general.taskAction"), 42);
  }
  if (tc.name.startsWith("cron_")) {
    const hint = firstParam(tc, ["schedule", "expression", "name"]);
    return compactText(hint || t("general.cronAction"), 42);
  }
  // File tools lead with the target file name — same rule as getToolSummary,
  // just narrower, and never shortened in a way that hides the name.
  if (isFileReadTool(tc.name) || isFileMutationTool(tc.name)) {
    return compactPath(toolFilePath(tc), 42) || getToolSummary(tc);
  }
  const fromParams = firstParam(tc, ["query", "path", "file_path", "url", "name"]);
  return compactText(fromParams || getToolSummary(tc), 42);
}

export function getAgentName(tc: ToolCallState): string {
  // Backend must pass an English agent name via agent_name / name.
  // Fall back to the literal "Agent" (English) so the label never
  // degenerates into a localized string like "智能体".
  const configuredName = (tc.params.agent_name as string) || (tc.params.name as string);
  return (configuredName && configuredName.trim()) || "Agent";
}

/** Normalizes an agent/tool name into a human-friendly display label. */
export function formatAgentLabel(rawName: string): string {
  // The backend supplies the agent name in English; preserve it as-is and
  // only capitalize the first character. Do NOT append "Agent" or lowercase
  // the rest, so names like "Code Reviewer" stay intact.
  const name = (rawName || "").trim();
  if (!name) return "Agent";
  return name.charAt(0).toUpperCase() + name.slice(1);
}

export function parseOption(raw: string): { label: string; desc: string } {
  const trimmed = (raw || "").trim();
  if (!trimmed) return { label: "", desc: "" };
  // Try common separators between title and description.
  const separators = [" / ", " — ", " – ", " - ", ": ", "：", "\n"];
  for (const sep of separators) {
    const idx = trimmed.indexOf(sep);
    if (idx > 0 && idx < trimmed.length - sep.length) {
      return { label: trimmed.slice(0, idx).trim(), desc: trimmed.slice(idx + sep.length).trim() };
    }
  }
  return { label: trimmed, desc: "" };
}

export function getToolBodyText(tc: ToolCallState): string {
  if (!tc.result) return "";
  if (tc.name === "web_search") return renderWebResults(tc.result);
  if (tc.name === "web_fetch") return renderWebFetchedContent(tc.result);
  if (isFileMutationTool(tc.name) && tc.name !== "delete_file") {
    return renderDiff(tc.result);
  }
  // Terminal tools: result is JSON, extract stdout/stderr for display
  if (TERMINAL_TOOLS.has(tc.name)) {
    try {
      const json = JSON.parse(tc.result);
      const parts: string[] = [];
      if (json.stdout) parts.push(json.stdout);
      if (json.stderr) parts.push(json.stderr);
      const text = parts.join("\n");
      if (!text.trim()) return `<pre style="font-size:11.5px;color:var(--text-muted);margin:0;padding:0">${escapeHtml("(no output)")}</pre>`;
      const lines = text.split("\n");
      const maxLines = 20;
      const shown = lines.slice(0, maxLines);
      const hasMore = lines.length > maxLines;
      let html = `<pre style="font-size:11.5px;color:var(--text-secondary);white-space:pre-wrap;margin:0;line-height:1.5">${escapeHtml(shown.join("\n"))}`;
      if (hasMore) {
        html += `\n<span style="color:var(--text-muted)">${t("chat.moreLines", { count: lines.length - maxLines })}</span>`;
      }
      html += "</pre>";
      return html;
    } catch {
      // Fallback: not JSON, treat as plain text
    }
  }
  // For most tools, show first few lines as summary, not full raw output
  const lines = tc.result.trim().split("\n").filter((l) => l.trim());
  const maxLines = 8;
  const shown = lines.slice(0, maxLines);
  const hasMore = lines.length > maxLines;
  let html = `<pre style="font-size:11.5px;color:var(--text-secondary);white-space:pre-wrap;margin:0;line-height:1.5">${escapeHtml(shown.join("\n"))}`;
  if (hasMore) {
    html += `\n<span style="color:var(--text-muted)">${t("chat.moreLines", { count: lines.length - maxLines })}</span>`;
  }
  html += "</pre>";
  return html;
}

export function renderDiff(result: string): string {
  // Extract filename from the first line produced by the file tools:
  // "Successfully wrote N chars to <path>" or "Applied N edit(s) to <path>."
  let fileName = "";
  const firstLine = result.split("\n")[0] || "";
  const pathMatch = firstLine.match(/(?:to|to:) (.+?)\.?\s*$/);
  if (pathMatch) fileName = pathMatch[1].trim();

  // Extract the diff body from the ```diff ... ``` fence, then render via the
  // shared renderer so the chat card and the review panel stay identical.
  const diffMatch = result.match(/```diff\n([\s\S]*?)```/);
  if (!diffMatch) return "";
  return renderDiffHtml(diffMatch[1].trim(), fileName);
}

export function renderWebResults(result: string): string {
  const lines = result.trim().split("\n");
  // Detect format: markdown links "1. [title](url)" or raw text
  const hasMarkdownLinks = /\[.+?\]\(https?:\/\/.+?\)/.test(result);

  let html = '<div class="web-list">';
  let num = 1;

  if (hasMarkdownLinks) {
    // Parse markdown format: "1. [title](url)\n   snippet"
    const entries = splitMarkdownEntries(result);
    if (entries.length > 0) {
      for (const entry of entries) {
        html += renderWebEntry(num, entry.title, entry.url, entry.snippet);
        num++;
      }
    }
  } else {
    // Fallback: try key-value line parsing, or show as clean text
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      // Try "title - url - snippet" pattern
      const parts = trimmed.split(/\s{2,}-\s{2,}/);
      if (parts.length >= 2) {
        const title = parts[0].trim();
        const rest = parts.slice(1).join(" - ").trim();
        const urlMatch = rest.match(/^(https?:\/\/\S+)(?:\s+(.+))?$/);
        const url = urlMatch ? urlMatch[1] : "";
        const snip = urlMatch && urlMatch[2] ? urlMatch[2] : (url ? "" : rest);
        html += renderWebEntry(num, title, url, snip);
        num++;
      } else {
        // Catch inline URLs
        const urlMatch = trimmed.match(/^(.*?)\s*(https?:\/\/\S+)\s*(.*)$/);
        if (urlMatch) {
          html += renderWebEntry(num, urlMatch[1] || trimmed, urlMatch[2], urlMatch[3]);
          num++;
        } else {
          html += `<div class="web-item"><span class="web-num">${num}</span><span class="web-snip">${escapeHtml(trimmed)}</span></div>`;
          num++;
        }
      }
    }
  }

  if (num === 1) {
    // No structured entries found, show cleaned text
    const cleaned = result.replace(/\n{3,}/g, "\n\n").trim();
    html += `<div class="web-item" style="white-space:pre-wrap;line-height:1.5;font-size:11.5px">${escapeHtml(cleaned)}</div>`;
  }
  html += "</div>";
  return html;
}

/** Split web_search markdown output into title/url/snippet entries. */
export function splitMarkdownEntries(text: string): { title: string; url: string; snippet: string }[] {
  const entries: { title: string; url: string; snippet: string }[] = [];
  // Match: optional number. [title](url) followed by optional snippet on next line(s)
  const pattern = /(?:^\d+\.\s*)?\[(.+?)\]\((https?:\/\/[^)]+)\)\s*([\s\S]*?)(?=(?:^\d+\.\s*)?\[.+?\]\(https?:\/\/|$)/gm;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    entries.push({
      title: match[1].trim(),
      url: match[2].trim(),
      snippet: match[3].trim().replace(/\n+/g, " ").slice(0, 300),
    });
  }
  return entries;
}

export function renderWebEntry(num: number, title: string, url: string, snippet: string): string {
  const displayTitle = title || url || "(untitled)";
  // Clickable title if URL present, otherwise plain text
  const titleHtml = url
    ? `<a class="web-title" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(displayTitle)}</a>`
    : `<span class="web-title">${escapeHtml(displayTitle)}</span>`;
  const shortUrl = url ? url.replace(/^https?:\/\//, "").replace(/\/$/, "").slice(0, 50) : "";
  const urlHtml = shortUrl ? `<span class="web-url">${escapeHtml(shortUrl)}</span>` : "";
  const snipHtml = snippet ? `<span class="web-snip">${escapeHtml(snippet)}</span>` : "";
  return `<div class="web-item">
    <span class="web-num">${num}</span>
    ${titleHtml}
    ${urlHtml}
    ${snipHtml}
  </div>`;
}

/** Render web_fetch results: clean scraped text into readable format. */
export function renderWebFetchedContent(result: string): string {
  const lines = result.split("\n").map(l => l.trim()).filter(l => l);
  // Deduplicate consecutive near-identical lines (common in scraped content)
  const deduped: string[] = [];
  for (const line of lines) {
    const prev = deduped[deduped.length - 1];
    if (prev && _lineSimilarity(prev, line) > 0.85) continue;
    if (line.length < 3 && deduped.length > 0) continue; // skip single-char noise
    deduped.push(line);
  }
  // Limit display
  const maxLines = 60;
  const shown = deduped.slice(0, maxLines);
  const more = deduped.length > maxLines
    ? `\n<span style="color:var(--text-muted)">… ${deduped.length - maxLines} more lines</span>`
    : "";
  return `<pre class="web-fetched-content">${escapeHtml(shown.join("\n"))}${more}</pre>`;
}

export function _lineSimilarity(a: string, b: string): number {
  if (a === b) return 1;
  const shorter = a.length < b.length ? a : b;
  const longer = a.length < b.length ? b : a;
  if (shorter.length === 0) return 0;
  let matches = 0;
  const words = new Set(shorter.split(/\s+/));
  for (const w of longer.split(/\s+/)) {
    if (words.has(w)) matches++;
  }
  return matches / Math.max(words.size, 1);
}

export function _toolStatusHtml(status: string): string {
  if (status === "running") return `<span class="tool-status-dot running"></span></span>`;
  return "";
}

export function getThinkingSummary(text: string, elapsed?: number): string {
  const summary = compactText(text, 54);
  const duration = elapsed ? `${elapsed}s` : "";
  if (summary && duration) return `${summary} - ${duration}`;
  return summary || duration;
}

export function createLucideIcons(root?: HTMLElement): void {
  if (typeof (window as any).lucide !== "undefined") {
    (window as any).lucide.createIcons(root ? { root } : undefined);
  }
}

const _openedHtmlCards = new Set<string>();

export function saveVideoPlayback(scope?: HTMLElement): Array<{id: string; t: number; p: boolean}> {
  const states: Array<{id: string; t: number; p: boolean}> = [];
  ((scope ?? document) as HTMLElement).querySelectorAll<HTMLVideoElement>(".info-card--media video").forEach(v => {
    const card = v.closest<HTMLElement>(".info-card--media");
    if (card?.id) states.push({ id: card.id, t: v.currentTime, p: v.paused });
  });
  return states;
}

export function restoreVideoPlayback(states: Array<{id: string; t: number; p: boolean}>, scope?: HTMLElement): void {
  if (states.length === 0) return;
  requestAnimationFrame(() => {
    states.forEach(s => {
      // Scoped lookup: the same tc-* id can exist in the main chat and the
      // automation detail; restore into the container being re-rendered, not
      // whichever card the global id resolves to first.
      const card = scope
        ? scope.querySelector<HTMLElement>(`#${CSS.escape(s.id)}`)
        : document.getElementById(s.id);
      if (!card) return;
      const video = card.querySelector<HTMLVideoElement>("video");
      if (!video) return;
      video.currentTime = s.t;
      if (!s.p) {
        const play = () => video.play().catch(() => {});
        if (video.readyState >= 2) play();
        else video.addEventListener("canplay", play, { once: true });
      }
    });
  });
}

/** Flash the copy icon to a checkmark with a fade transition, then revert after 2s. */
export function flashCopyButton(btn: HTMLElement): void {
  const origIcon = btn.getAttribute('data-original-icon');
  const original = origIcon || 'copy';
  if (!origIcon) btn.setAttribute('data-original-icon', original);

  // Keep the actions visible while the checkmark animation plays.
  btn.classList.add('copying', 'copy-flash');

  // The fade itself is CSS (`.copy-flash.is-fading`); these timings only
  // decide *when* the glyph swaps — while the button is fully faded out.
  const fade = TransitionHelper.step('--duration-fast', 120);
  const swapGlyph = (name: string): void => {
    const i = btn.querySelector('[data-lucide]');
    if (i) i.setAttribute('data-lucide', name);
    createLucideIcons(btn);
  };

  btn.classList.add('is-fading');
  setTimeout(() => {
    swapGlyph('check');
    btn.classList.remove('is-fading');
  }, fade);

  setTimeout(() => {
    btn.classList.add('is-fading');
    setTimeout(() => {
      swapGlyph(original);
      btn.classList.remove('is-fading', 'copying', 'copy-flash');
    }, fade);
  }, 2000);
}
