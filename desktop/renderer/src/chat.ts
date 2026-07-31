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

/**
 * Chat view & markdown rendering.
 *
 * Renders the conversation message list (markdown + syntax-highlighted code
 * blocks, tool calls, artifacts and sub-agent views) and owns the composer
 * send flow. Also exports the shared `renderMarkdown` and `formatAgentLabel`
 * helpers used across the renderer.
 */

import { getState, subscribe, showToast, addUserMessage, addAttachments, startAssistantMessage, setRunning, removeBranchMessages, restoreInputModeChip, truncateToUserMessage, setSubAgentView, pushSubAgentBreadcrumb, popSubAgentBreadcrumb, clearSubAgentBreadcrumb, resetToSubAgentBreadcrumbIndex, rememberRollbackEditTarget, isEnabled, toolCallMatchesId } from "./state.js";
import { send } from "./ws.js";
import { setRequestedSessionId } from "./stream.js";
import type { Message, ToolCallState, BranchMeta, AttachmentMeta } from "./types.js";
import MarkdownIt from "markdown-it";
import hljs from "highlight.js";
import { t, onLocaleChange, getLocale } from "./i18n.js";
import { Dialog } from "./dialog.js";
import { findSlashCommand } from "./slash_commands.js";
import { EALoader } from "./ealoader.js";
import { renderDiffHtml } from "./diff_render.js";
import { MediaViewer } from "./media-viewer.js";

const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  breaks: true,
});

md.renderer.rules.fence = (tokens: any[], idx: number) => {
  const token = tokens[idx];
  const lang = token.info ? token.info.trim().split(/\s+/)[0] : "";
  let content = token.content;
  let highlighted = "";

  if (lang && hljs.getLanguage(lang)) {
    try {
      highlighted = hljs.highlight(content, { language: lang }).value;
    } catch {
      highlighted = escapeHtml(content);
    }
  } else {
    highlighted = escapeHtml(content);
  }

  const attr = lang ? ` class="hljs language-${lang}"` : ' class="hljs"';
  const langLabel = lang ? escapeHtml(lang) : t("general.code");
  const codeAttr = `data-code="${escapeHtml(content)}"`;

  return `<div class="code-block-wrapper">
    <div class="code-block-header">
      <span class="code-lang">${langLabel}</span>
      <button class="code-copy" ${codeAttr}>${t("chat.copy")}</button>
    </div>
    <pre><code${attr}>${highlighted}</code></pre>
  </div>\n`;
};

md.renderer.rules.code_inline = (tokens: any[], idx: number) => {
  const content = tokens[idx].content;
  return `<code class="inline-code">${escapeHtml(content)}</code>`;
};

/** Renders markdown text to HTML (trimming trailing breaks/empty paragraphs). */
export function renderMarkdown(text: string): string {
  if (!text) return "";
  const trimmed = text.replace(/\n+$/, "");
  const html = md.render(trimmed);
  return html.replace(/(?:<br\s*\/?>\s*)+$/, "").replace(/<p>\s*<\/p>\s*$/, "");
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// === Tool helpers ===================================================================

// === Tool category helpers (match ALL backend tools) ================================

function isTerminalTool(name: string): boolean {
  return name === "bash" || name === "bash_output" || name === "bash_kill" || name === "bash_list" ||
         name === "shell" || name === "terminal" || name === "run_command" || name === "chat.terminal";
}

function isFileMutationTool(name: string): boolean {
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

function isFileReadTool(name: string): boolean {
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

function isExpandableStripTool(name: string): boolean {
  return name === "search" || name === "grep" || name === "glob" || name === "codebase" ||
         name === "web_search";
}

function isToolItemTool(name: string): boolean {
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

function isHiddenTool(name: string): boolean {
  if (name === "task" || name.startsWith("task_")) return true;
  if (name === "memory" || name.startsWith("memory_")) return true;
  if (name.startsWith("cron_")) return true;
  return name === "todo" || name === "find_tool" || name === "lsp";
}

function compactText(value: unknown, max = 88): string {
  if (value === undefined || value === null) return "";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  const oneLine = text.replace(/\s+/g, " ").trim();
  return oneLine.length > max ? `${oneLine.slice(0, max - 3)}...` : oneLine;
}

/**
 * Try to extract a short human-readable summary from a JSON result string.
 * Returns null if the input is not valid JSON or no usable field is found.
 */
function extractJsonSummary(result: string): string | null {
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

function firstParam(tc: ToolCallState, keys: string[]): string {
  for (const key of keys) {
    const value = tc.params[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return "";
}

function getToolIcon(name: string, terminal?: string): string {
  if (isTerminalTool(name)) {
    const terminalIcons: Record<string, string> = {
      auto: "command",
      bash: "terminal",
      cmd: "monitor",
      powershell: "terminal",
      pwsh: "terminal",
      python: "code-2",
      node: "code",
      irb: "gem",
      julia: "sigma",
      lua: "code",
      php: "file-type",
      R: "sigma",
    };
    return terminal ? (terminalIcons[terminal] || "command") : "command";
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

function formatToolName(name: string, terminal?: string): string {
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

function getToolSummary(tc: ToolCallState): string {
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
    // File mutation tools always show the file path, not the result
    if (FILE_MUTATION_TOOLS.has(tc.name)) {
      return compactText(firstParam(tc, ["path", "file_path", "filename"]), 88);
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
    return compactText(firstParam(tc, ["path", "file_path", "filename"]), 88);
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

function getToolInlineSummary(tc: ToolCallState): string {
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

/**
 * Select the messages that belong to a single parallel task.
 * When ``taskIndex`` is provided, the flat ``sub_agent_messages`` list is
 * split at ``task_divider`` markers and only the chosen task's body is
 * returned. Otherwise the full list is returned unchanged.
 */
function selectSubAgentTaskMessages(msgs: Message[], taskIndex?: number): Message[] {
  if (taskIndex === undefined) return msgs;
  const groups = new Map<number, Message[]>();
  let fallbackIndex = 0;
  let current: Message[] | null = null;
  for (const m of msgs) {
    if (m.mode === "task_divider") {
      const index = Number.isInteger(m.taskIndex) ? m.taskIndex! : fallbackIndex;
      fallbackIndex = Math.max(fallbackIndex, index + 1);
      current = [];
      groups.set(index, current);
    } else if (current) {
      current.push(m);
    }
  }
  return groups.get(taskIndex) ?? [];
}

export function buildSubAgentTimeline(msgs: Message[], isRunning?: boolean): TimelineItem[] {
  // task_divider markers are only structural metadata used to split parallel
  // runs in the parent transcript; they should never render inside a sub-agent
  // view.
  const clean = msgs.filter((m) => m.mode !== "task_divider");
  const timeline = buildTimeline(clean);
  // When the sub-agent view is running, suppress action buttons (copy, retry)
  // on all messages so they only appear after the turn is truly finished.
  const subView = getState().subAgentView;
  const subRunning = isRunning ?? !!(subView && (subView.status === "running" || subView.status === "pending"));
  if (subRunning) {
    for (const item of timeline) {
      (item as any).showActions = false;
    }
  }
  // Sub-agent views render a single focused turn inline. The ai_header
  // ("Encre Agent") shows at the top so the user knows which agent is
  // producing the output -- only one header exists per task.
  return timeline;
}


function parseOption(raw: string): { label: string; desc: string } {
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

function getToolBodyText(tc: ToolCallState): string {
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

function renderDiff(result: string): string {
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

function renderWebResults(result: string): string {
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
function splitMarkdownEntries(text: string): { title: string; url: string; snippet: string }[] {
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

function renderWebEntry(num: number, title: string, url: string, snippet: string): string {
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
function renderWebFetchedContent(result: string): string {
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

function _lineSimilarity(a: string, b: string): number {
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

function _toolStatusHtml(status: string): string {
  if (status === "running") return `<span class="tool-status-dot running"></span></span>`;
  return "";
}

function getThinkingSummary(text: string, elapsed?: number): string {
  const summary = compactText(text, 54);
  const duration = elapsed ? `${elapsed}s` : "";
  if (summary && duration) return `${summary} - ${duration}`;
  return summary || duration;
}

function createLucideIcons(root?: HTMLElement): void {
  if (typeof (window as any).lucide !== "undefined") {
    (window as any).lucide.createIcons(root ? { root } : undefined);
  }
}

const _openedHtmlCards = new Set<string>();

function saveVideoPlayback(): Array<{id: string; t: number; p: boolean}> {
  const states: Array<{id: string; t: number; p: boolean}> = [];
  document.querySelectorAll<HTMLVideoElement>(".info-card--media video").forEach(v => {
    const card = v.closest<HTMLElement>(".info-card--media");
    if (card?.id) states.push({ id: card.id, t: v.currentTime, p: v.paused });
  });
  return states;
}

function restoreVideoPlayback(states: Array<{id: string; t: number; p: boolean}>): void {
  if (states.length === 0) return;
  requestAnimationFrame(() => {
    states.forEach(s => {
      const card = document.getElementById(s.id);
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
function flashCopyButton(btn: HTMLElement): void {
  const origIcon = btn.getAttribute('data-original-icon');
  const original = origIcon || 'copy';
  if (!origIcon) btn.setAttribute('data-original-icon', original);

  // Use the button's opacity so the transition survives lucide DOM swaps
  btn.style.transition = 'opacity 0.12s ease';
  btn.style.opacity = '0';

  setTimeout(() => {
    const i = btn.querySelector('[data-lucide]');
    if (i) i.setAttribute('data-lucide', 'check');
    createLucideIcons(btn);
    btn.style.opacity = '1';
  }, 120);

  setTimeout(() => {
    btn.style.opacity = '0';
    setTimeout(() => {
      const i = btn.querySelector('[data-lucide]');
      if (i) i.setAttribute('data-lucide', original);
      createLucideIcons(btn);
      btn.style.opacity = '1';
      setTimeout(() => {
        btn.style.transition = '';
      }, 120);
    }, 120);
  }, 2000);
}

export type TimelineItem =
  | { kind: "user"; id: string; content: string; index: number; showBranchSwitcher?: boolean; mode?: string; fileRefs?: { name: string; size: number; icon: string }[] }
  | { kind: "ai_header"; id: string; time: string }
  | { kind: "thinking"; id: string; text: string; elapsed?: number; messageId?: string }
  | { kind: "tool"; id: string; tc: ToolCallState; messageId?: string; showActions?: boolean; showBranchSwitcher?: boolean }
  | { kind: "assistant_text"; id: string; content: string; isStreaming: boolean; hasError?: boolean; messageId?: string; showActions?: boolean; showBranchSwitcher?: boolean }
  | { kind: "error_card"; id: string; messageId: string; errorMessage: string; errorCode: string; errorCategory?: string; showActions?: boolean; showBranchSwitcher?: boolean }
  | { kind: "warning_card"; id: string; messageId: string; interruptedReason: string; showActions?: boolean; showBranchSwitcher?: boolean }
  | { kind: "inline_success"; id: string; messageId: string; turnStatusText: string; showActions?: boolean; showBranchSwitcher?: boolean }
  | { kind: "inline_cancelled"; id: string; messageId: string; text: string; showActions?: boolean; showBranchSwitcher?: boolean }
  | { kind: "compact"; id: string }
  | { kind: "system_message"; id: string; content: string; kindTag: string }
  | { kind: "spec_card"; id: string; spec: import("./types.js").SpecData }
  | { kind: "plan_card"; id: string; review: import("./types.js").PlanReviewData }
  | { kind: "workflow"; id: string };

function buildStatusCards(msg: Message): TimelineItem[] {
  const cards: TimelineItem[] = [];
  if (msg.errorMessage) {
    cards.push({ kind: "error_card", id: `ec-${msg.id}`, messageId: msg.id, errorMessage: msg.errorMessage, errorCode: msg.errorCode || "", errorCategory: (msg as any).errorCategory || "" });
  } else if (msg.interruptedReason) {
    cards.push({ kind: "warning_card", id: `wc-${msg.id}`, messageId: msg.id, interruptedReason: msg.interruptedReason });
  }
  if (msg.turnStatusText) {
    cards.push({ kind: "inline_success", id: `is-${msg.id}`, messageId: msg.id, turnStatusText: msg.turnStatusText });
  }
  if (msg.cancelledText) {
    cards.push({ kind: "inline_cancelled", id: `ic-${msg.id}`, messageId: msg.id, text: msg.cancelledText });
  }
  return cards;
}

function buildTimeline(msgs: Message[]): TimelineItem[] {
  const items: TimelineItem[] = [];
  let userIndex = 0;
  // Status cards from consecutive assistant messages are deferred and
  // flushed at the end of the group so the error/success banner always
  // sits below every text block, thinking strip, and tool card in the
  // visible turn — even when the backend split the turn into multiple
  // assistant messages.
  let pendingStatusCards: TimelineItem[] = [];

  const st = getState();
  if (st.branches.length > 1) {
    console.log("[buildTimeline] branches=%d active=%s msgs=%d", st.branches.length, st.activeBranchId?.slice(-8), msgs.length);
  }
  for (let ci = 0; ci < st.compactEvents.length; ci++) {
    items.push({ kind: "compact", id: `compact-${ci}` });
  }

  for (let si = 0; si < (st.systemMessages || []).length; si++) {
    const sm = st.systemMessages[si];
    items.push({ kind: "system_message", id: `sysmsg-${si}`, content: sm.content, kindTag: sm.kind });
  }

  // The spec/plan review cards are pushed at the bottom of the message
  // loop (see below) so they land right after the assistant that triggered
  // the review, instead of at the top of the timeline.

  // Insert workflow progress card when active
  if (st.workflowState && st.workflowState.active) {
    items.push({ kind: "workflow", id: `wf-${st.workflowState.workflowId}` });
  }

  // Find the fork-point user message (where branches diverge) so we can
  // render the branch switcher there instead of at the last assistant.
  // If serverId matching fails (e.g. locally-added messages), fall back
  // to the last user message position.
  let forkMsgIdx = -1;
  if (st.branches.length > 1) {
    const cur = st.branches.find(b => b.id === st.activeBranchId);
    const fpId = cur?.fork_point_message_id;
    if (fpId) {
      forkMsgIdx = msgs.findIndex(m => m.serverId === fpId);
      if (forkMsgIdx < 0) {
        // Fallback: last user message (no serverId — locally added)
        for (let i = msgs.length - 1; i >= 0; i--) {
          if (msgs[i].role === "user") { forkMsgIdx = i; break; }
        }
      }
    } else {
      // Root branch — find first child branch's fork point
      for (const b of st.branches) {
        if (b.parent_branch_id === st.activeBranchId && b.fork_point_message_id) {
          const idx = msgs.findIndex(m => m.serverId === b.fork_point_message_id);
          if (idx >= 0) { forkMsgIdx = idx; break; }
        }
      }
    }
  }

  // Find the first assistant message after the fork point — the branch
  // switcher renders below this message rather than below the user bubble.
  let firstAssistantAfterForkIdx = -1;
  if (forkMsgIdx >= 0 && st.branches.length > 1) {
    for (let i = forkMsgIdx + 1; i < msgs.length; i++) {
      if (msgs[i].role === "assistant") {
        firstAssistantAfterForkIdx = i;
        break;
      }
    }
  }

  for (let i = 0; i < msgs.length; i++) {
    const msg = msgs[i];
    if (msg.role === "user") {
      items.push({
        kind: "user",
        id: `u-${msg.id}`,
        content: msg.content,
        index: userIndex++,
        mode: msg.mode,
        fileRefs: msg.fileRefs,
      });
    } else if (msg.role === "assistant") {
      const prevIsAssistant = i > 0 && msgs[i - 1].role === "assistant";
      if (!prevIsAssistant) {
        const d = new Date(msg.timestamp || Date.now());
        const y = d.getFullYear();
        const mo = String(d.getMonth() + 1).padStart(2, "0");
        const day = String(d.getDate()).padStart(2, "0");
        const h = String(d.getHours()).padStart(2, "0");
        const mi = String(d.getMinutes()).padStart(2, "0");
        const msgTime = `${y}-${mo}-${day} ${h}:${mi}`;
        items.push({ kind: "ai_header", id: `ah-${msg.id}`, time: msgTime });
      }
      // Use segments ordering to preserve thinking/text/tool interleaving
      // as the model outputs them. Each kind is rendered at its segment
      // position in the exact order they were streamed.
      // Status cards (error/warning/success/cancelled) are intentionally
      // pushed AFTER all segments so they always sit at the bottom of the
      // turn, below any tool calls that arrived later in the stream.
      const assistantStartIdx = items.length;
      if (msg.segments && msg.segments.length > 0) {
        let lastTextSegIndex = -1;
        {
          let segCount = 0;
          for (let si = 0; si < msg.segments.length; si++) {
            if (msg.segments[si].kind === "text") {
              lastTextSegIndex = segCount;
              segCount++;
            }
          }
        }
        let textSegIndex = 0;
        let thinkingFallbackUsed = false;
        for (let si = 0; si < msg.segments.length; si++) {
          const seg = msg.segments[si];
          if (seg.kind === "thinking") {
            // Each thinking segment renders at its actual position with its own text.
            // When a segment has no per-segment text (legacy history), use msg.thinking
            // only on the first occurrence to avoid duplication.
            let thinkingText = seg.text || "";
            if (!thinkingText && !thinkingFallbackUsed && msg.thinking) {
              thinkingText = msg.thinking;
              thinkingFallbackUsed = true;
            }
            if (thinkingText) {
              items.push({ kind: "thinking", id: `th-${msg.id}-seg-${si}`, text: thinkingText, elapsed: msg.thinkingElapsed, messageId: msg.id });
            }
          } else if (seg.kind === "text") {
            const segText = (seg.text || "").trim();
            const isLast = textSegIndex === lastTextSegIndex;
            const isErrorOnly = msg.errorMessage && segText.startsWith("[Backend API Error]");
            if ((segText.length > 0 || msg.isStreaming) && !isErrorOnly) {
              items.push({
                kind: "assistant_text",
                id: `a-${msg.id}-seg-${textSegIndex}`,
                content: seg.text || "",
                isStreaming: msg.isStreaming,
                hasError: msg.hasError,
                messageId: msg.id,
              });
            }
            textSegIndex++;
          } else if (seg.kind === "tool") {
            const tc = seg.toolId ? msg.toolCalls.find(t => toolCallMatchesId(t, seg.toolId)) : undefined;
            // Skip tools that must never render (hidden), and tools whose
            // name has not streamed in yet (empty name). Rendering an
            // unnamed tool briefly shows a blank generic strip that then
            // vanishes once the name resolves (e.g. to a hidden tool),
            // which reads as a flicker. Keeping them out of the timeline
            // also keeps them out of the render key entirely.
            if (tc && tc.name && !isHiddenTool(tc.name)) {
              items.push({ kind: "tool", id: `tc-${tc.id}`, tc, messageId: msg.id });
            }
          }
        }
      } else {
        // Legacy fallback for messages without segments
        if (msg.thinking) {
          items.push({ kind: "thinking", id: `th-${msg.id}`, text: msg.thinking, elapsed: msg.thinkingElapsed, messageId: msg.id });
        }
        for (const tc of msg.toolCalls) {
          // Mirror the segment path: never surface hidden or not-yet-named
          // tools so they cannot flash in and out during streaming.
          if (!tc.name || isHiddenTool(tc.name)) continue;
          items.push({ kind: "tool", id: `tc-${tc.id}`, tc, messageId: msg.id });
        }
        if (msg.content.trim().length > 0 || msg.isStreaming) {
          items.push({ kind: "assistant_text", id: `a-${msg.id}`, content: msg.content, isStreaming: msg.isStreaming, hasError: msg.hasError, messageId: msg.id });
        }
      }
      // Status cards for this assistant message. If more assistant messages
      // follow consecutively, defer the cards so they all render at the end
      // of the combined turn.
      const statusCards = buildStatusCards(msg);
      const isLastAssistantInGroup = i === msgs.length - 1 || msgs[i + 1].role !== "assistant";
      if (isLastAssistantInGroup) {
        if (pendingStatusCards.length > 0) {
          items.push(...pendingStatusCards);
          pendingStatusCards = [];
        }
        items.push(...statusCards);
      } else {
        pendingStatusCards.push(...statusCards);
      }
      // Place copy/retry/branch-switcher actions on the very last rendered
      // item of the *last* assistant message in the current group. That
      // guarantees the action bar sits below every text block, thinking
      // strip, tool card, and status card in the visible turn.
      if (isLastAssistantInGroup && assistantStartIdx < items.length) {
        const lastItem = items[items.length - 1];
        if (!msg.isStreaming && !st.running) {
          (lastItem as any).showActions = true;
        }
      }
      // Branch switcher belongs to the first assistant after a fork; it is
      // rendered at the end of the turn, so attach the flag to this message's
      // last rendered item.
      if (i === firstAssistantAfterForkIdx && assistantStartIdx < items.length) {
        const lastItem = items[items.length - 1];
        (lastItem as any).showBranchSwitcher = true;
      }
      // After the LAST assistant message in the timeline, push the spec/plan
      // review card (if any) so it sits at the natural review position —
      // right after the assistant that triggered it, before the next user
      // message.
      if (i === msgs.length - 1 || (i + 1 < msgs.length && msgs[i + 1].role !== "assistant")) {
        if (st.planReview) {
          items.push({ kind: "plan_card", id: `plan-card-${st.planReview.review_id}`, review: st.planReview });
        }
        if (st.spec) {
          items.push({ kind: "spec_card", id: `spec-card-${getState().sessionId}`, spec: st.spec });
        }
      }
    }
  }

  // Safety flush: any deferred status cards that weren't flushed inside the
  // loop (should only happen in edge cases) are appended at the very end.
  if (pendingStatusCards.length > 0) {
    items.push(...pendingStatusCards);
    pendingStatusCards = [];
  }

  // Fallback: if there are no assistant messages but a review/spec is
  // available (e.g. session just loaded), still surface the card at the end.
  if (items.every(it => it.kind !== "assistant_text" && it.kind !== "ai_header" && it.kind !== "thinking" && it.kind !== "tool")) {
    if (st.planReview) {
      items.push({ kind: "plan_card", id: `plan-card-${st.planReview.review_id}`, review: st.planReview });
    }
    if (st.spec) {
      items.push({ kind: "spec_card", id: `spec-card-${getState().sessionId}`, spec: st.spec });
    }
  }

  return items;
}

function _fmtTokens(n: number): string {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
  if (n >= 1000) return (n / 1000).toFixed(1) + "K";
  return String(n);
}

function fmtSize(bytes: number): string {
  if (!bytes || bytes < 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function buildRenderKey(timeline: TimelineItem[]): string {
  // Key only encodes STRUCTURAL changes. Any per-item content (streaming
  // text, tool params, tool status, tool result body, workflow task
  // progress) is handled by incrementalTextUpdate. Including those here
  // forces a full innerHTML reset on every delta, which makes the chat
  // feel like it is "always rendering" and prevents the user from
  // scrolling up while the model is streaming.
  return JSON.stringify(timeline.map(i => {
    if (i.kind === "user") return { k: "u", c: i.content };
    if (i.kind === "ai_header") return { k: "ah", t: i.time };
    if (i.kind === "thinking") return { k: "th", id: i.id };
    if (i.kind === "tool") {
      // The result transition is structural (a body slot gets filled);
      // status/params/error changes are handled incrementally.  For
      // agent tool calls, the task-divider count is structural too:
      // when subAgentMessages arrive with new dividers (e.g. after a
      // session switch restores empty state) the agent card layout
      // must be rebuilt from scratch.
      const taskDividers = i.tc.subAgentMessages
        ? i.tc.subAgentMessages
          .filter((message) => message.mode === "task_divider")
          .map((message, index) => ({
            index: message.taskIndex ?? index,
            name: message.taskName || "",
            status: message.taskStatus || "",
          }))
        : [];
      return { k: "tc", id: i.id, n: i.tc.name, r: i.tc.result ? 1 : 0, d: taskDividers, sa: i.showActions ? 1 : 0, sb: i.showBranchSwitcher ? 1 : 0 };
    }
    if (i.kind === "compact") return { k: "cp" };
    if (i.kind === "workflow") {
      const wf = getState().workflowState;
      if (wf) return { k: "wf", id: wf.workflowId, n: wf.tasks.length, a: wf.active ? 1 : 0 };
      return { k: "wf" };
    }
    if (i.kind === "assistant_text") {
      // Streaming/finished transition is structural (turn actions appear,
      // streaming class toggles). Content stays incremental.
      return { k: "a", id: i.id, st: i.isStreaming ? 1 : 0, sa: i.showActions ? 1 : 0, sb: i.showBranchSwitcher ? 1 : 0 };
    }
    if (i.kind === "error_card") return { k: "ec", id: i.id, sa: i.showActions ? 1 : 0, sb: i.showBranchSwitcher ? 1 : 0 };
    if (i.kind === "warning_card") return { k: "wc", id: i.id, sa: i.showActions ? 1 : 0, sb: i.showBranchSwitcher ? 1 : 0 };
    if (i.kind === "inline_success") return { k: "is", id: i.id, sa: i.showActions ? 1 : 0, sb: i.showBranchSwitcher ? 1 : 0 };
    if (i.kind === "inline_cancelled") return { k: "ic", id: i.id, sa: i.showActions ? 1 : 0, sb: i.showBranchSwitcher ? 1 : 0 };
    // All TimelineItem kinds handled above — this fallback keeps TS happy.
    return { k: "" };
  }));
}

interface StatusQuote {
  icon: string;
  textKey: string;
}

const STATUS_QUOTES: StatusQuote[] = [
  { icon: "waves", textKey: "statusQuoteWaves" },
  { icon: "cpu", textKey: "statusQuoteCpu" },
  { icon: "brain", textKey: "statusQuoteBrain" },
  { icon: "zap", textKey: "statusQuoteZap" },
  { icon: "dices", textKey: "statusQuoteDices" },
  { icon: "network", textKey: "statusQuoteNetwork" },
  { icon: "rocket", textKey: "statusQuoteRocket" },
  { icon: "target", textKey: "statusQuoteTarget" },
  { icon: "puzzle", textKey: "statusQuotePuzzle" },
  { icon: "crystal-ball", textKey: "statusQuoteCrystalBall" },
  { icon: "palette", textKey: "statusQuotePalette" },
  { icon: "egg", textKey: "statusQuoteEgg" },
  { icon: "guitar", textKey: "statusQuoteGuitar" },
  { icon: "binary", textKey: "statusQuoteBinary" },
  { icon: "battery-charging", textKey: "statusQuoteBattery" },
  { icon: "brush", textKey: "statusQuoteBrush" },
  { icon: "flask-conical", textKey: "statusQuoteFlask" },
];

function pickRandomQuote(): StatusQuote {
  return STATUS_QUOTES[Math.floor(Math.random() * STATUS_QUOTES.length)];
}

/**
 * The chat view controller: message list rendering and composer send flow.
 */
export class Chat {
  private ml: HTMLElement;
  private welcomeScreen: HTMLElement;
  private container: HTMLElement;
  private statusBar: HTMLElement;
  private userScrolledUp = false;
  private renderedKey = "";
  private expandedItems = new Set<string>();
  private userCollapsedItems = new Set<string>();
  private userExpandedItems = new Set<string>();
  private lastAssistantMsgId = "";
  private _lastRunning = false;
  private _inRenderForce = false;
  private rafPending = false;
  private liveLoader: EALoader | null = null;
  private scrollIndicator: ChatScrollIndicator;
  /** Map of file keys to markdown content for plan file rows (avoids attribute length limits). */
  private _planFileLookup = new Map<string, string>();
  /** Callback invoked when the user clicks "View Changes" on an artifact file. */
  public onViewChanges: ((path: string) => void) | null = null;

  /**
   * Constructor: resolves DOM nodes and wires the scroll indicator + bridges.
   */
  constructor() {
    this.ml = document.getElementById("message-list")!;
    this.welcomeScreen = document.getElementById("welcome-screen")!;
    this.container = document.getElementById("chat-container")!;
    this.statusBar = document.getElementById("chat-status-bar")!;
    this.scrollIndicator = new ChatScrollIndicator(this.container);

    // Scroll-to-bottom floating button
    const scrollBtn = document.createElement("button");
    scrollBtn.id = "chat-scroll-bottom-btn";
    scrollBtn.className = "chat-scroll-bottom-btn hidden";
    scrollBtn.setAttribute("aria-label", "Scroll to bottom");
    scrollBtn.innerHTML = '<i data-lucide="chevron-down" style="width:18px;height:18px"></i>';
    this.container.parentElement?.appendChild(scrollBtn);
    scrollBtn.addEventListener("click", () => {
      this.container.scrollTo({ top: this.container.scrollHeight, behavior: "smooth" });
    });

    const w = window as any;
    w.__openSubAgentView = (toolCallId: string, taskIndex?: number) => {
      const st = getState();
      const MAX_DEPTH = 4;
      // Enforce max nesting depth using breadcrumb length
      if (st.subAgentBreadcrumb.length >= MAX_DEPTH) {
        showToast?.("Sub-agent", `Max depth (${MAX_DEPTH}) reached`);
        return;
      }
      for (const msg of st.messages) {
        for (const tc of msg.toolCalls) {
          if (toolCallMatchesId(tc, toolCallId)) {
            // Explicit user navigation INTO a sub-agent re-enables auto-open.
            w.__subAgentAutoOpenDismissed = false;
            // The parent tool call id is the currently-active sub-agent
            // view's tc id (when navigating from inside another sub-agent)
            // or null when navigating from the root main session.
            const parentToolCallId = st.subAgentView ? st.subAgentView.id : null;
            // Record current session as parent in the breadcrumb stack
            const agentName = getAgentName(tc);
            const taskDividers = this._agentTaskDividers(tc);
            const selectedTask = taskIndex === undefined
              ? undefined
              : taskDividers.find((task) => task.index === taskIndex);
            const taskName = selectedTask
              ? selectedTask.name
              : "";
            const crumbName = taskName ? `${agentName} · ${taskName}` : agentName;
            // If the user already has a deeper view open and clicks
            // an ancestor's card, truncate the stack back to that level
            // so the breadcrumb reflects their actual navigation, not
            // a stale "deeper view" branch.
            const existingIdx = st.subAgentBreadcrumb.findIndex(
              (c) => c.toolCallId === toolCallId,
            );
            if (existingIdx >= 0) {
              resetToSubAgentBreadcrumbIndex(existingIdx);
            } else {
              pushSubAgentBreadcrumb({
                sessionId: st.sessionId,
                name: crumbName,
                toolCallId,
                parentToolCallId,
              });
            }
            if (tc.subAgentMessages && tc.subAgentMessages.length > 0) {
              // Viewing a single parallel task keeps the parent tool-call
              // identity but narrows the transcript to that task.
              const viewTc: ToolCallState = { ...tc, taskIndex };
              // Inline sub-agents use the tool-call snapshot, not a resumed
              // session. Clear any stale session-backed flag so the fallback
              // path does not accidentally render the parent session messages.
              w.__activeSubAgentSessionId = undefined;
              setSubAgentView(viewTc);
              this.render();
            } else if (tc.subAgentSessionId) {
              const requestId = crypto.randomUUID();
              // The sub-agent transcript is loaded by a session_ready reply.
              // Keep the originating tool-call identity until that reply
              // arrives so the renderer can re-enter the sub-agent view.
              w.__pendingSubAgentView = {
                toolCall: tc,
                sessionId: tc.subAgentSessionId,
                requestId,
              };
              setRequestedSessionId(tc.subAgentSessionId, requestId);
              send({ type: "resume", session_id: tc.subAgentSessionId, request_id: requestId });
            } else {
              setSubAgentView(tc);
              this.render();
            }
            return;
          }
        }
      }
    };
    w.__closeSubAgentView = () => {
      const crumb = popSubAgentBreadcrumb();
      w.__pendingSubAgentView = undefined;
      w.__activeSubAgentSessionId = undefined;
      // User deliberately stepped back toward the main agent: stop
      // auto-opening freshly spawned sub-agents for the rest of this run.
      if (!crumb) w.__subAgentAutoOpenDismissed = true;
      setSubAgentView(null);
      if (crumb) {
        const requestId = crypto.randomUUID();
        setRequestedSessionId(crumb.sessionId, requestId);
        send({ type: "resume", session_id: crumb.sessionId, request_id: requestId });
      } else {
        this.renderedKey = "";
        this.ml.innerHTML = "";
        requestAnimationFrame(() => this.render());
      }
    };
    w.__goToRootView = () => {
      const st = getState();
      // Leaving every sub-agent level: drop the session-backed marker so the
      // parent view is never mistaken for a sub-agent snapshot.
      w.__activeSubAgentSessionId = undefined;
      w.__pendingSubAgentView = undefined;
      // User explicitly returned to the main agent: suppress auto-open of
      // subsequently spawned sub-agents until they opt back in or a new turn.
      w.__subAgentAutoOpenDismissed = true;
      if (st.subAgentBreadcrumb.length === 0) {
        setSubAgentView(null);
        this.render();
        return;
      }
      const rootSessionId = st.subAgentBreadcrumb[0].sessionId;
      clearSubAgentBreadcrumb();
      setSubAgentView(null);
      if (rootSessionId !== st.sessionId) {
        const requestId = crypto.randomUUID();
        setRequestedSessionId(rootSessionId, requestId);
        send({ type: "resume", session_id: rootSessionId, request_id: requestId });
      }
      this.renderedKey = "";
      this.ml.innerHTML = "";
      this.render();
    };
    w.__navigateToBreadcrumb = (index: number) => {
      const st = getState();
      const target = resetToSubAgentBreadcrumbIndex(index);
      if (!target) return;
      // Navigate to the sub-agent identified by this breadcrumb entry's
      // toolCallId.  toolCallId is the id of the agent tool call that
      // spawned this sub-agent — the same id used when clicking the
      // agent card (__openSubAgentView).  Previously the code searched
      // for target.parentToolCallId, which is the *parent* entry's id
      // and caused clicking a breadcrumb to navigate to the wrong view.
      const stNow = getState();
      for (const msg of stNow.messages) {
        for (const tc of msg.toolCalls) {
          if (toolCallMatchesId(tc, target.toolCallId)) {
            // Breadcrumb navigation always stays inside the parent session
            // and reopens the inline sub-agent view. Resuming the sub-agent
            // session itself would break the breadcrumb stack.
            setSubAgentView(tc);
            this.render();
            return;
          }
        }
      }
      // Fallback: tool call not found — clear the sub-agent view
      // and resume the breadcrumb's stored session.
      setSubAgentView(null);
      const requestId = crypto.randomUUID();
      setRequestedSessionId(target.sessionId, requestId);
      send({ type: "resume", session_id: target.sessionId, request_id: requestId });
    };
    w.__answerQuestion = (event: Event, btn: HTMLElement, cardId: string) => {
      event.stopPropagation();
      const card = document.getElementById(cardId);
      if (!card) return;
      const selected = card.querySelector(".q-option-card.selected");
      let answer = selected ? selected.getAttribute("data-value") || "" : "";
      if (!answer) {
        const input = card.querySelector(".q-input") as HTMLInputElement;
        if (input) answer = input.value.trim();
      }
      if (answer) {
        send({ type: "respond_question", tool_call_id: cardId.replace("tc-", ""), answers: answer });
      }
    };
    w.__hoverOn = (el: HTMLElement) => {
      const wrap = el.querySelector(".icon-wrap");
      if (wrap) wrap.classList.add("hover");
    };
    w.__hoverOff = (el: HTMLElement) => {
      const wrap = el.querySelector(".icon-wrap");
      if (wrap) wrap.classList.remove("hover");
    };
    w.__toggleStatusCard = (id: string) => {
      const el = document.getElementById(id);
      if (el) el.classList.toggle("expanded");
    };
    w.__viewChanges = (el: HTMLElement) => {
      const card = el.closest(".file-card") as HTMLElement | null;
      if (card) {
        const path = card.getAttribute("data-path") || "";
        if (path && this.onViewChanges) this.onViewChanges(path);
      }
    };

    // Resize info-card iframes when the sandboxed content reports its height.
    const resizeInfoFrame = (iframe: HTMLIFrameElement) => {
      try {
        const doc = iframe.contentDocument;
        if (!doc) return;
        const height = Math.max(doc.body?.scrollHeight || 0, doc.documentElement?.scrollHeight || 0);
        if (height > 0) iframe.style.height = `${height}px`;
      } catch {
        // Cross-origin or otherwise inaccessible iframe; ignore.
      }
    };
    window.addEventListener("message", (event) => {
      const data = event.data;
      if (!data || typeof data.__encreInfoHeight !== "number" || !data.__encreInfoId) return;
      const iframe = document.querySelector(`#${data.__encreInfoId} .info-card-frame`) as HTMLIFrameElement | null;
      if (iframe) iframe.style.height = `${data.__encreInfoHeight}px`;
    });
    w.__resizeInfoFrame = resizeInfoFrame;

    // Info-card toolbar actions: toggle render/code view and copy source.
    w.__toggleInfoView = (cardId: string) => {
      const card = document.getElementById(cardId);
      if (!card) return;
      const frame = card.querySelector(".info-card-frame") as HTMLElement | null;
      const codeBlock = card.querySelector(".info-card-code") as HTMLElement | null;
      const btn = card.querySelector(".info-card-actions .info-btn[data-action='toggle-view']") as HTMLElement | null;
      if (!frame || !codeBlock) return;
      const showingCode = !codeBlock.classList.contains("hidden");
      const nextMode = showingCode ? "render" : "code";
      frame.classList.toggle("hidden", nextMode !== "render");
      codeBlock.classList.toggle("hidden", nextMode !== "code");
      if (btn) {
        // The button icon always represents the action that will happen on click:
        // preview mode -> show code icon (click to view code)
        // code mode -> show eye icon (click to view preview)
        const nextIcon = nextMode === "code" ? "code" : "eye";
        btn.dataset.mode = nextMode;
        btn.dataset.tooltip = t(nextMode === "code" ? "chat.infoCode" : "chat.infoRender");
        // Re-create the <i> element because Lucide replaces it with an SVG.
        btn.innerHTML = `<i data-lucide="${nextIcon}" class="info-btn-icon"></i>`;
        if (typeof (window as any).lucide !== "undefined") {
          (window as any).lucide.createIcons({ root: btn });
        }
      }
    };
    w.__copyInfoSource = async (cardId: string) => {
      const card = document.getElementById(cardId);
      if (!card) return;
      const source = card.getAttribute("data-source") || "";
      try {
        await navigator.clipboard.writeText(source);
      } catch {
        showToast(t("chat.infoCopyFailed"), "", "error", "Chat");
      }
    };

    w.__initInfoCardMedia = (cardId: string) => {
      const card = document.getElementById(cardId);
      if (!card) return;
      card.querySelectorAll(":scope > [data-type]").forEach((el) => {
        const type = el.getAttribute("data-type") as "image" | "video" || "image";
        const src = el.getAttribute("data-src") || "";
        if (src) new MediaViewer(el as HTMLElement, { type, src, controls: type === "video" });
      });
    };
    w.__initMediaCards = () => {
      document.querySelectorAll(".info-card--media").forEach((card) => {
        const id = card.id;
        if (id) w.__initInfoCardMedia(id);
      });
    };
    w.__openInfoHtmlCard = async (cardId: string) => {
      const card = document.getElementById(cardId);
      if (!card) return;
      const src = card.getAttribute("data-source");
      if (!src) return;
      const fileUrl = await window.electronAPI?.openInfoHtml(src).catch(() => null);
      if (fileUrl) {
        window.dispatchEvent(new CustomEvent("info-html-open", { detail: { url: fileUrl } }));
      }
    };
    w.__openInfoHtmlCards = () => {
      document.querySelectorAll<HTMLElement>(".strip-item[data-source]").forEach((card) => {
        const id = card.id;
        if (!id || _openedHtmlCards.has(id)) return;
        _openedHtmlCards.add(id);
        w.__openInfoHtmlCard(id);
      });
    };
    window.__initMediaCards = w.__initMediaCards;
    window.__initInfoCardMedia = w.__initInfoCardMedia;
    window.__openInfoHtmlCards = w.__openInfoHtmlCards;
    this.container.addEventListener("scroll", () => {
      const { scrollTop, scrollHeight, clientHeight } = this.container;
      this.userScrolledUp = scrollHeight - scrollTop - clientHeight > 100;
      const btn = document.getElementById("chat-scroll-bottom-btn");
      if (btn) {
        btn.classList.toggle("hidden", !this.userScrolledUp);
      }
    });

    this.ml.addEventListener("click", (e) => this.handleDelegateClick(e));
    // Track session changes to prevent stale content bleeding
    let _lastSid = getState().sessionId;
    let _lastMsgLen = getState().messages.length;
    let _lastExpand = isEnabled(getState().settings.auto_expand);
    subscribe(() => {
      const st = getState();
      const sid = st.sessionId;
      const msgs = st.messages;
      // Session ID changed → force full reset and re-render
      if (sid && sid !== _lastSid) {
        _lastSid = sid;
        _lastMsgLen = msgs.length;
        this.renderedKey = "";
        this.expandedItems.clear();
        this.userCollapsedItems.clear();
        if (this.liveLoader) {
          this.liveLoader.destroy();
          this.liveLoader = null;
        }
        // Sub-agent views/breadcrumbs are scoped to a specific session.  When
        // the user switches sessions we must discard them so the new session
        // is not rendered with the previous session's nested agent content.
        if (st.subAgentView || st.subAgentBreadcrumb.length > 0) {
          setSubAgentView(null);
          clearSubAgentBreadcrumb();
        }
        this.ml.innerHTML = "";
        this.render();
        return;
      }
      if (msgs.length === 0 && _lastMsgLen > 0) {
        _lastMsgLen = 0;
        this.renderedKey = "";
        this.expandedItems.clear();
        this.userCollapsedItems.clear();
        if (this.liveLoader) {
          this.liveLoader.destroy();
          this.liveLoader = null;
        }
        if (st.subAgentView || st.subAgentBreadcrumb.length > 0) {
          setSubAgentView(null);
          clearSubAgentBreadcrumb();
        }
        this.ml.innerHTML = "";
        return;
      }
      if (msgs.length > 0 && _lastMsgLen === 0) {
        _lastMsgLen = msgs.length;
        this.renderedKey = "";
        this.render();
        return;
      }
      // Re-render when auto_expand setting changes (auto-expanded thinking
      // strips depend on it and they are not part of the render key).
      const curExpand = isEnabled(st.settings.auto_expand);
      if (curExpand !== _lastExpand) {
        _lastExpand = curExpand;
        this.requestRender();
        return;
      }
      _lastMsgLen = msgs.length;
      this.requestRender();
    });
    onLocaleChange(() => this.render());
  }

  private requestRender(): void {
    if (this.rafPending) return;
    this.rafPending = true;
    requestAnimationFrame(() => {
      this.rafPending = false;
      this.render();
    });
  }

  private _parallelRenderTimer: number | null = null;
  private _pendingParallelRender = false;

  renderForce(): void {
    this.renderedKey = "";
    this._inRenderForce = true;
    try {
      const st = getState();
      const subTc = st.subAgentView;
      const dividerCount = subTc?.subAgentMessages
        ? subTc.subAgentMessages.filter((m) => m.mode === "task_divider").length
        : 0;
      const isParallelRunning = subTc &&
        (subTc.status === "running" || subTc.status === "pending") &&
        dividerCount >= 2;
      if (!isParallelRunning) {
        this.render();
        return;
      }
      // Throttle parallel sub-agent streaming renders so the main thread
      // stays responsive enough for scrolling and window dragging.
      this._pendingParallelRender = true;
      if (this._parallelRenderTimer === null) {
        this.render();
        this._parallelRenderTimer = window.setTimeout(() => {
          this._parallelRenderTimer = null;
          if (this._pendingParallelRender) {
            this._pendingParallelRender = false;
            this.render();
          }
        }, 100);
      }
    } finally {
      this._inRenderForce = false;
    }
  }

  /** Re-renders the message list from current state (RAF-throttled). */
  render(): void {
    if (this.liveLoader) {
      this.liveLoader.destroy();
      this.liveLoader = null;
    }
    const state = getState();
    // Breadcrumb restoration: if the user navigated back to an ancestor
    // session via the breadcrumb, the sub-agent view may have been cleared
    // while waiting for the parent session to load. Once the parent session
    // arrives, automatically reopen the sub-agent view that corresponds to
    // the last breadcrumb entry so the UI lands on the right level.
    if (!state.subAgentView && state.subAgentBreadcrumb.length > 0) {
      const crumb = state.subAgentBreadcrumb[state.subAgentBreadcrumb.length - 1];
      if (crumb.sessionId === state.sessionId) {
        for (const msg of state.messages) {
          for (const tc of msg.toolCalls) {
            if (toolCallMatchesId(tc, crumb.toolCallId)) {
              setSubAgentView(tc);
              break;
            }
          }
          if (state.subAgentView) break;
        }
      }
    }
    if (state.subAgentView) {
      this.toggleWelcome(false);
      const subTc = state.subAgentView;
      // A session-backed sub-agent streams directly into the active session
      // snapshot after its transcript has been resumed. Inline sub-agents use
      // the tool-call snapshot instead.
      const sessionBacked = (window as any).__activeSubAgentSessionId === state.sessionId;
      // Prefer the inline snapshot when available; it survives navigation
      // back to the parent session and re-entry into the sub-agent view.
      let subMsgs = subTc.subAgentMessages?.length
        ? subTc.subAgentMessages
        : (sessionBacked ? state.messages : []);

      // When the user clicked one card of a parallel agent run, show only
      // that single task's transcript instead of the combined run.
      const selectedMsgs = selectSubAgentTaskMessages(subMsgs, subTc.taskIndex);
      const hasInlineData = selectedMsgs.length > 0;
      const isStreaming = sessionBacked
        ? state.running
        : (subTc.status === "running" || subTc.status === "pending");
      this.renderedKey = "__subagent__";
      if (hasInlineData) {
        // Sub-agent snapshot arrived: render the real user + assistant
        // bubbles together.  The loader was already torn down at the
        // top of render(), so the message area is clean by now.
        const timeline = buildSubAgentTimeline(selectedMsgs, isStreaming);
        this.fullRender(timeline, selectedMsgs);
      } else if (isStreaming) {
        // Still waiting for the first snapshot: hide every message bubble
        // (no user box, no assistant box) and show only the centered EA
        // loader.  Both bubbles will appear together once data lands.
        this.ml.innerHTML = "";
        this.liveLoader = new EALoader(this.ml);
      } else if (subTc.isError) {
        const errorCode = String(subTc.result || "AUTOMATION_EXECUTION_FAILED");
        this.ml.innerHTML = `<div class="si-panel-empty" style="flex:1;gap:14px;">
          <i data-lucide="ban" class="lucide"></i>
          <div class="si-panel-empty-title">${t("automation.executionFailed") || "Automation execution error"}</div>
          <div class="si-panel-empty-sub">${escapeHtml(errorCode)}</div>
        </div>`;
      } else {
        // No inline transcript survived (e.g. reopened after switching
        // sessions before the snapshot was persisted). Fall back to the
        // aggregated tool result text so the user still sees the real
        // output instead of a bare "no output" placeholder.
        const resultText = typeof subTc.result === "string" ? subTc.result.trim() : "";
        if (resultText) {
          this.ml.innerHTML = `<div class="sub-agent-result-fallback">${renderMarkdown(resultText)}</div>`;
        } else {
          // Finished (or never started) without producing any output.
          this.ml.innerHTML = `<div class="sub-agent-empty"><p>${t("chat.noSubAgentOutput")}</p></div>`;
        }
      }
      createLucideIcons();
      this._updateStatusBar(false);
      this.autoScroll();
      return;
    }
    this.toggleWelcome(state.messages.length === 0);
    const msgs = state.messages;
    if (msgs.length === 0) {
      this.ml.innerHTML = "";
      this.renderedKey = "";
      return;
    }
    const timeline = buildTimeline(msgs);
    const key = buildRenderKey(timeline);
    const wasRunning = this._lastRunning;
    this._lastRunning = state.running;
    // Force full render when streaming completes so auto-expand/collapse
    // logic in fullRender is applied correctly (the render key may not
    // change when running transitions from true to false).
    if (key !== this.renderedKey || (wasRunning && !state.running)) {
      console.log("[chat.render] fullRender", { msgCount: msgs.length, roles: msgs.map(m => m.role), serverIds: msgs.map(m => m.serverId?.slice(-12)) });
      this.fullRender(timeline, msgs);
      this.renderedKey = key;
    } else {
      this.incrementalTextUpdate(timeline);
    }
    this._updateStatusBar(state.running);
    // Auto-open HTML info cards only when the model just finished
    if (wasRunning && !state.running) {
      window.__openInfoHtmlCards?.();
    }

  }

  /**
   * Build the timeline HTML for sub-agent messages and render it into
   * an arbitrary container element. Reuses the same rendering pipeline
   * as the main chat's fullRender, so the result looks identical to the
   * chat sub-agent view.
   *
   * Used by the automation panel to render execution results inside
   * #automation-detail-content without switching to chat mode.
   */
  public renderSubAgentInto(container: HTMLElement, messages: Message[], isRunning: boolean): void {
    const timeline = buildSubAgentTimeline(messages, isRunning);
    const st = getState();
    const autoExpand = isEnabled(st.settings.auto_expand);
    this.applyAutoExpand(timeline, autoExpand, isRunning);
    // Treat the automation detail exactly like the tape's sub-agent view:
    // user bubbles belong to the current turn (in-turn), not standalone
    // blocks. Pass treatAsSubAgent=true so buildTimelineHTML matches what
    // chat.render() produces when state.subAgentView is set.
    const html = this.buildTimelineHTML(timeline, messages, true);
const _vs = saveVideoPlayback();
    window.__stopAllMedia?.();
    container.innerHTML = html;
    createLucideIcons();
    window.__initMediaCards();
    restoreVideoPlayback(_vs);
    if (!container.dataset.subAgentClickBound) {
      container.addEventListener("click", (e) => this.handleDelegateClick(e));
      container.dataset.subAgentClickBound = "true";
    }
  }

  /**
   * Single source of truth for whether a timeline item should be expanded.
   * Honors explicit user overrides, then the special "thinking" rule, then
   * the auto-expand setting.
   *
   * Rules:
   *  - Thinking, while the model is still actively reasoning
   *    (thinkingActive): ALWAYS expanded so the user can watch the reasoning
   *    stream, regardless of the auto-expand setting (a user may still
   *    explicitly collapse it).
   *  - Otherwise: a manual collapse/expand wins; when the user hasn't touched
   *    it, follow the auto-expand setting. This applies uniformly to thinking
   *    (after it finishes) and to every expandable tool card, so the automation
   *    detail behaves exactly like the main chat.
   */
  private computeExpanded(kind: string, id: string, autoExpand: boolean, thinkingActive: boolean): boolean {
    const userCollapsed = this.userCollapsedItems.has(id);
    if (kind === "thinking" && thinkingActive) {
      return !userCollapsed;
    }
    if (userCollapsed) return false;
    if (this.userExpandedItems.has(id)) return true;
    return autoExpand;
  }

  /**
   * Identify the thinking segment the model is *actively* generating.
   *
   * "Still thinking" means the reasoning is the last content the model has
   * produced so far — the moment any text or tool segment appears after it,
   * the thinking is finished even though the overall turn keeps running (e.g.
   * while a tool executes). Only the actively-streaming thinking strip is
   * force-expanded; finished ones fall back to the auto-expand setting.
   */
  private activeThinkingId(timeline: TimelineItem[], isRunning: boolean): string | null {
    if (!isRunning) return null;
    for (let i = timeline.length - 1; i >= 0; i--) {
      const it = timeline[i];
      if (it.kind === "thinking") return it.id;
      if (it.kind === "tool" || it.kind === "assistant_text") return null;
    }
    return null;
  }

  /**
   * Shared auto-expand pass used by both fullRender and renderSubAgentInto
   * so the two never drift. Auto-expands thinking strips and every expandable
   * tool card unless the user manually collapsed them.
   */
  private applyAutoExpand(timeline: TimelineItem[], autoExpand: boolean, isRunning = false): void {
    const activeThinkingId = this.activeThinkingId(timeline, isRunning);
    for (const item of timeline) {
      if (item.kind !== "thinking" && item.kind !== "tool") continue;
      const id = item.id;
      const thinkingActive = item.kind === "thinking" && id === activeThinkingId;
      if (this.computeExpanded(item.kind, id, autoExpand, thinkingActive)) {
        this.expandedItems.add(id);
      } else {
        this.expandedItems.delete(id);
      }
    }
  }

  /**
   * Build the timeline's inner HTML (turns + standalone cards) - the shared
   * body of fullRender. Extracted so renderSubAgentInto produces byte-identical
   * markup to the main chat's sub-agent view instead of a parallel copy.
   *
   * @param treatAsSubAgent When true, user bubbles are folded into the
   *   current turn (matching chat.render()'s sub-agent path). When false,
   *   the live subAgentView/__parentSessionId flags decide - the normal
   *   chat behaviour.
   */
  private buildTimelineHTML(timeline: TimelineItem[], allMsgs?: Message[], treatAsSubAgent = false): string {
    let html = "";
    let turnMid = ""; // buffered items inside current turn
    let turnActions = false;
    let turnRetry = false;
    let turnBranchSwitcher = false;
    const _this = this;

    function closeTurn() {
      if (!turnMid) return;
      html += `<div class="turn">${turnMid}`;
      if (turnActions) {
        html += `<div class="assistant-actions turn-actions">`;
        html += `<button class="btn-icon btn-icon--msg assistant-copy-btn" data-tooltip="${t("chat.copy")}">
          <i data-lucide="copy" class="lucide lucide-sm"></i>
        </button>`;
        if (turnRetry) {
          html += `<button class="btn-icon btn-icon--msg assistant-retry-btn" data-tooltip="${t("chat.retry")}">
            <i data-lucide="refresh-cw" class="lucide lucide-sm"></i>
          </button>`;
        }
        if (turnBranchSwitcher) {
          html += _this.renderBranchSwitcher();
        }
        html += `</div>`;
      }
      html += `</div>`;
      turnMid = "";
      turnActions = false;
      turnRetry = false;
      turnBranchSwitcher = false;
    }

    const inSubAgent = treatAsSubAgent || !!getState().subAgentView || !!(window as any).__parentSessionId;
    for (let i = 0; i < timeline.length; i++) {
      const item = timeline[i];

      if (item.kind === "compact" || item.kind === "workflow" || (item.kind === "user" && !inSubAgent)) {
        closeTurn.call(_this);
        html += this.renderItemHTML(item);
      } else if (item.kind === "ai_header") {
        closeTurn.call(_this);
        turnMid += this.renderItemHTML(item);
      } else {
        // thinking / assistant_text / tool / status cards all belong to the current turn
        if ((item as any).showBranchSwitcher) turnBranchSwitcher = true;
        if ((item as any).showActions) {
          // Every completed turn gets a copy button
          turnActions = true;
          // No retry button in sub-agent view
          if (!inSubAgent) {
            // Only show retry on the very last assistant message in the conversation
            if (allMsgs) {
              for (let mi = allMsgs.length - 1; mi >= 0; mi--) {
                if (allMsgs[mi].role === "assistant") {
                  if ((item as any).messageId === allMsgs[mi].id) turnRetry = true;
                  break;
                }
              }
            } else {
              turnRetry = true;
            }
          }
        }
        turnMid += this.renderItemHTML(item);
      }
    }
    closeTurn.call(_this);
    return html;
  }

  /**
   * Render a parallel sub-agent run: one ``agent`` tool that executed several
   * tasks concurrently. The transcript is a flat list delimited by structured
   * ``task_divider`` markers (``mode === "task_divider"``); we split it back
   * into per-task groups and tile them into split regions -- like a window
   * snap layout -- so "one agent, many jobs" reads as distinct panes:
   *   1 task  -> fills the whole tape
   *   2 tasks -> left / right
   *   3 tasks -> one across the top, two side-by-side below
   *   4 tasks -> 2x2 grid
   * Regions are separated by faint dashed lines (CSS). At most 4 tiles are
   * drawn -- more would deform and can't be laid out cleanly.
   */
  private fullRenderParallel(subMsgs: Message[], isStreaming: boolean): void {
    // Split the flat transcript by its stable backend task index. A reconnect
    // may replay dividers out of order, so array position is not task identity.
    const groupsByIndex = new Map<number, { divider: Message; body: Message[] }>();
    let fallbackIndex = 0;
    let current: { divider: Message; body: Message[] } | null = null;
    for (const m of subMsgs) {
      if (m.mode === "task_divider") {
        const index = Number.isInteger(m.taskIndex) ? m.taskIndex! : fallbackIndex;
        fallbackIndex = Math.max(fallbackIndex, index + 1);
        current = { divider: m, body: [] };
        groupsByIndex.set(index, current);
      } else if (current) {
        current.body.push(m);
      }
    }
    const groups = [...groupsByIndex.entries()]
      .sort(([left], [right]) => left - right)
      .map(([, group]) => group);

    const statusMeta = (s: string | undefined): { icon: string; label: string; cls: string } => {
      if (s === "done") return { icon: "check", label: t("chat.taskDone") || "Done", cls: "is-done" };
      if (s === "error") return { icon: "x", label: t("chat.taskError") || "Failed", cls: "is-error" };
      if (s === "queued") return { icon: "clock", label: t("chat.taskQueued") || "Queued", cls: "is-queued" };
      return { icon: "loader", label: t("chat.taskRunning") || "Running", cls: "is-running" };
    };

    // Only the first 4 tasks get a region; the split grid can't draw more.
    const shown = groups.slice(0, 4);
    const count = shown.length;

    // Build each tile body HTML up-front so we can diff against the
    // existing DOM and only replace the tiles that actually changed.
    const tileBodies: string[] = [];
    for (const g of shown) {
      const isRunning = statusMeta(g.divider.taskStatus).cls === "is-running";
      const bodyTimeline = buildSubAgentTimeline(g.body, isRunning);
      const bodyHtml = g.body.length > 0
        ? this.buildTimelineHTML(bodyTimeline, g.body, true)
        : `<div class="parallel-task-pending">${t("chat.taskWaiting") || "Waiting for output…"}</div>`;
      tileBodies.push(bodyHtml);
    }

    // Windows-style snap layout: panes tile edge-to-edge with no outer frame.
    // 1 task fills the tape; 2 tasks split left/right; 3 tasks put one large
    // pane on the left and two stacked panes on the right; 4 tasks form a 2x2
    // grid. Split ratios are fixed (no drag resize).
    const wrapTile = (idx: number): string =>
      `<section class="parallel-tile"><div class="parallel-tile-body">${tileBodies[idx]}</div></section>`;
    let html = `<div class="parallel-sub-agent" data-count="${count}">`;
    if (count === 3) {
      html += wrapTile(0);
      html += `<div class="parallel-sub-agent-stack">`;
      html += wrapTile(1);
      html += wrapTile(2);
      html += `</div>`;
    } else {
      for (let i = 0; i < count; i++) {
        html += wrapTile(i);
      }
    }
    html += `</div>`;

    this.ml.classList.add("parallel-active");
    const existing = this.ml.querySelector(":scope > .parallel-sub-agent") as HTMLElement | null;
    const _vs = saveVideoPlayback();
    window.__stopAllMedia?.();
    if (existing && existing.dataset.count === String(count)) {
      // Diff update: only swap tile bodies whose content changed. This keeps
      // scroll position, cursor selection, and expansion state intact for the
      // tiles that are not currently streaming.
      const bodies = existing.querySelectorAll(".parallel-tile-body");
      let idx = 0;
      for (const body of Array.from(bodies)) {
        if (idx < tileBodies.length && body.innerHTML !== tileBodies[idx]) {
          body.innerHTML = tileBodies[idx];
        }
        idx++;
      }
      window.__initMediaCards();
      restoreVideoPlayback(_vs);
    } else {
      this.ml.innerHTML = html;
      window.__initMediaCards();
      restoreVideoPlayback(_vs);
    }
  }

  private fullRender(timeline: TimelineItem[], allMsgs?: Message[]): void {
    this.ml.classList.remove("parallel-active");
    const st = getState();
    const autoExpand = isEnabled(st.settings.auto_expand);

    // Auto-expand based on setting (unless user manually collapsed).
    // During streaming, thinking is always expanded so the user sees the
    // reasoning process in real time. After streaming, follow the setting.
    // Delegated to the shared applyAutoExpand pass so fullRender, the
    // streaming incremental path and the automation detail never drift.
    const isRunning = st.running;
    this.applyAutoExpand(timeline, autoExpand, isRunning);

    let html = "";
    let turnMid = ""; // buffered items inside current turn
    let turnActions = false;
    let turnRetry = false;
    let turnBranchSwitcher = false;
    const _this = this;

    function closeTurn() {
      if (!turnMid) return;
      html += `<div class="turn">${turnMid}`;
      if (turnActions) {
        html += `<div class="assistant-actions turn-actions">`;
        html += `<button class="btn-icon btn-icon--msg assistant-copy-btn" data-tooltip="${t("chat.copy")}">
          <i data-lucide="copy" class="lucide lucide-sm"></i>
        </button>`;
        if (turnRetry) {
          html += `<button class="btn-icon btn-icon--msg assistant-retry-btn" data-tooltip="${t("chat.retry")}">
            <i data-lucide="refresh-cw" class="lucide lucide-sm"></i>
          </button>`;
        }
        if (turnBranchSwitcher) {
          html += _this.renderBranchSwitcher();
        }
        html += `</div>`;
      }
      html += `</div>`;
      turnMid = "";
      turnActions = false;
      turnRetry = false;
      turnBranchSwitcher = false;
    }

    for (let i = 0; i < timeline.length; i++) {
      const item = timeline[i];

      if (item.kind === "compact" || item.kind === "workflow" || (item.kind === "user" && !getState().subAgentView && !(window as any).__parentSessionId)) {
        closeTurn.call(_this);
        html += this.renderItemHTML(item);
      } else if (item.kind === "ai_header") {
        closeTurn.call(_this);
        turnMid += this.renderItemHTML(item);
      } else {
        // thinking / assistant_text / tool / status cards all belong to the current turn
        if ((item as any).showBranchSwitcher) turnBranchSwitcher = true;
        if ((item as any).showActions) {
          // Every completed turn gets a copy button
          turnActions = true;
          // No retry button in sub-agent view
          if (!getState().subAgentView) {
            // Only show retry on the very last assistant message in the conversation
            if (allMsgs) {
              for (let mi = allMsgs.length - 1; mi >= 0; mi--) {
                if (allMsgs[mi].role === "assistant") {
                  if ((item as any).messageId === allMsgs[mi].id) turnRetry = true;
                  break;
                }
              }
            } else {
              turnRetry = true;
            }
          }
        }
        turnMid += this.renderItemHTML(item);
      }
    }
    closeTurn.call(_this);
    // Capture the scroll snapshot BEFORE innerHTML resets, then restore
    // the visual anchor AFTER. Without this, a full re-render during
    // streaming collapses the user's scroll position and makes the
    // chat feel like it is "always rendering", preventing them from
    // scrolling up to inspect earlier turns.
    const container = this.container;
    const wasScrolledUp = this.userScrolledUp;
    const prevScrollTop = container.scrollTop;
    const prevScrollHeight = container.scrollHeight;
    const _vs = saveVideoPlayback();
    window.__stopAllMedia?.();
    this.ml.innerHTML = html;
    createLucideIcons();
    window.__initMediaCards();
    restoreVideoPlayback(_vs);
    if (wasScrolledUp) {
      // Preserve the user's visual position: when new content is appended
      // below, the previous bottom offset should still point at the same
      // pixel anchor in the re-rendered DOM.
      const newScrollHeight = container.scrollHeight;
      const delta = newScrollHeight - prevScrollHeight;
      container.scrollTop = prevScrollTop + delta;
      // Refresh the "scrolled up" flag — if the delta restored the user
      // to the bottom, treat them as pinned again.
      const dist = newScrollHeight - container.scrollTop - container.clientHeight;
      this.userScrolledUp = dist > 8;
    } else {
      // New render: always pin to the bottom so the latest message is
      // visible. This covers both streaming and static sessions -- when
      // the user opens a session, we want to land on the last turn,
      // not the middle of the history.
      this.scrollToBottom();
    }
    const turnCount = getState().messages.filter(m => m.role === "user").length;
    this.scrollIndicator.update(turnCount);
  }

  private incrementalTextUpdate(timeline: TimelineItem[]): void {
    // Find the last assistant message block in timeline.  This anchor is
    // only needed for the assistant-text delta updates below; the thinking,
    // tool, and workflow updates must still run during the pre-text thinking
    // phase (i.e. when only `thinking_delta` events have arrived so far) so
    // the user sees the reasoning stream in real time instead of having the
    // card freeze on the first delta and then jump to the full text when
    // the first text_delta triggers a fullRender.
    let lastAssistantIndex = -1;
    for (let i = timeline.length - 1; i >= 0; i--) {
      if (timeline[i].kind === "assistant_text") {
        lastAssistantIndex = i;
        break;
      }
    }

    if (lastAssistantIndex >= 0) {
      const assistantItem = timeline[lastAssistantIndex] as Extract<TimelineItem, { kind: "assistant_text" }>;

      // Detect new assistant message round — reset userCollapsedItems
      const currentAssistantMsgId = assistantItem.id;
      if (currentAssistantMsgId !== this.lastAssistantMsgId) {
        this.lastAssistantMsgId = currentAssistantMsgId;
      }
    }

    // Update thinking text if present.  This runs on every render frame
    // (including frames where only a thinking_delta arrived) so the thought
    // card streams in real time just like the assistant text card.
    const activeThinkingId = this.activeThinkingId(timeline, getState().running);
    for (let i = 0; i < timeline.length; i++) {
      const item = timeline[i];
      if (item.kind === "thinking") {
        const el = this.ml.querySelector(`[data-id="${item.id}"]`) as HTMLElement | null;
        if (el) {
          const bodyEl = el.querySelector(".thought-body") as HTMLElement | null;
          if (bodyEl && bodyEl.textContent !== item.text) {
            bodyEl.textContent = item.text;
          }
          // Auto-expand thinking: while the model is ACTIVELY thinking (this is
          // the last content it has produced) always expand unless the user
          // manually collapsed it. Once thinking finishes, follow the
          // auto-expand setting. User manual toggle is respected via
          // userCollapsedItems/userExpandedItems.
          const shouldExpand = isEnabled(getState().settings.auto_expand);
          const thinkingActive = item.id === activeThinkingId;
          const wantExpanded = this.computeExpanded("thinking", item.id, shouldExpand, thinkingActive);
          const isExpanded = el.classList.contains("expanded");
          if (wantExpanded && !isExpanded) {
            el.classList.add("expanded");
            this.expandedItems.add(item.id);
          } else if (!wantExpanded && isExpanded) {
            el.classList.remove("expanded");
            this.expandedItems.delete(item.id);
          }
        }
      }
    }

    // Update tool items incrementally. Covers: streaming params (summary
    // text), status transitions (spinner show/hide), result body, file
    // card diff badge / view button, and agent card preview.
    for (let i = 0; i < timeline.length; i++) {
      const toolItem = timeline[i];
      if (toolItem.kind !== "tool") continue;
      // timeline item id is already `tc-${tc.id}`; do NOT prefix again
      // (the old selector emitted `data-id="tc-tc-..."` and never matched).
      const el = this.ml.querySelector(`[data-id="${toolItem.id}"]`) as HTMLElement | null;
      if (!el) continue;

      // 1) Status slot — toggle spinner on pending<->running<->done.
      const statusSlot = el.querySelector(".strip-status, .tool-item-status, .agent-card-status") as HTMLElement | null;
      if (statusSlot) {
        const curStatus = statusSlot.getAttribute("data-status") || "";
        if (curStatus !== toolItem.tc.status) {
          statusSlot.setAttribute("data-status", toolItem.tc.status);
          statusSlot.innerHTML = _toolStatusHtml(toolItem.tc.status);
        }
      }

      // 2) Summary text (strip-summary) — pick the right summary function
      //    per layout (inline vs expandable).
      const summaryEl = el.querySelector(".strip-summary") as HTMLElement | null;
      if (summaryEl) {
        const isExpandable = el.classList.contains("strip-item") || el.classList.contains("terminal-card");
        const newSummary = isExpandable ? getToolSummary(toolItem.tc) : getToolInlineSummary(toolItem.tc);
        if (summaryEl.textContent !== newSummary) {
          summaryEl.textContent = newSummary;
        }
      }

      // 3) Result body slot (expandable strip + terminal card). Filled
      //    lazily when tc.result arrives; key flips structurally so the
      //    first time it is rendered through fullRender too.
      const bodySlot = el.querySelector(".strip-body-slot, .terminal-body-slot") as HTMLElement | null;
      if (bodySlot) {
        const hasBody = !!toolItem.tc.result;
        const cur = bodySlot.getAttribute("data-has-body") === "1";
        if (hasBody !== cur) {
          bodySlot.setAttribute("data-has-body", hasBody ? "1" : "0");
          if (hasBody) {
            bodySlot.innerHTML = `<div class="${el.classList.contains("terminal-card") ? "terminal-body" : "strip-body"}">${getToolBodyText(toolItem.tc)}</div>`;
          } else {
            bodySlot.innerHTML = "";
          }
        }
      }

      // 4) Auto-expand based on setting (unless user manually collapsed).
      //    Applies to all expandable tool cards. Mirrors the thinking-strip
      //    handling above so toggling auto_expand takes effect on already-
      //    rendered tool cards without a full re-render.
      const shouldExpandTool = isEnabled(getState().settings.auto_expand);
      const wantExpandedTool = this.computeExpanded("tool", toolItem.id, shouldExpandTool, false);
      const isExpandedTool = el.classList.contains("expanded");
      if (wantExpandedTool && !isExpandedTool) {
        el.classList.add("expanded");
        this.expandedItems.add(toolItem.id);
      } else if (!wantExpandedTool && isExpandedTool) {
        el.classList.remove("expanded");
        this.expandedItems.delete(toolItem.id);
      }
      // 5) Agent card icon: toggle spin class in-place so the CSS animation
      //    never restarts during streaming (the icon SVG survives through
      //    incremental updates because the render key is no longer cleared).
      if (toolItem.tc.name === "agent") {
        const iconEl = el.querySelector('.agent-card-icon') as HTMLElement | null;
        if (iconEl) {
          const st = getState();
          const isAgentRunning = st.running && (toolItem.tc.status === "running" || toolItem.tc.status === "pending");
          iconEl.classList.toggle('spinning', isAgentRunning);
        }
      }
    }

    // Update workflow card progress bar and task list
    for (let i = 0; i < timeline.length; i++) {
      if (timeline[i].kind !== "workflow") continue;
      const wf = getState().workflowState;
      if (!wf) continue;
      const card = this.ml.querySelector(`#wf-${wf.workflowId}`) as HTMLElement | null;
      if (!card) continue;
      // Update progress bar
      const bar = card.querySelector(".workflow-progress-fill") as HTMLElement | null;
      if (bar) {
        const pct = wf.totalTasks > 0 ? Math.round((wf.completedCount + wf.failedCount + wf.skippedCount) / wf.totalTasks * 100) : 0;
        bar.style.width = pct + "%";
      }
      // Update progress text
      const textEl = card.querySelector(".workflow-progress-text") as HTMLElement | null;
      if (textEl) {
        const newText = `${wf.completedCount + wf.failedCount + wf.skippedCount}/${wf.totalTasks} tasks — ${wf.completedCount} done, ${wf.failedCount} failed, ${wf.skippedCount} skipped`;
        if (textEl.textContent !== newText) textEl.textContent = newText;
      }
      // Update header badge
      const badge = card.querySelector(".workflow-card-badge") as HTMLElement | null;
      if (badge && !wf.active) {
        const statusColor = wf.success ? "#22c55e" : "#ef4444";
        badge.textContent = wf.success ? (t("chat.workflowDone") || "Completed") : (t("chat.workflowFailed") || "Failed");
        badge.style.background = statusColor + "20";
        badge.style.color = statusColor;
      }
      // Update task status dots
      const taskEls = card.querySelectorAll(".wf-task") as NodeListOf<HTMLElement>;
      taskEls.forEach((taskEl, idx) => {
        if (idx >= wf.tasks.length) return;
        const t = wf.tasks[idx];
        const dot = taskEl.querySelector(".wf-dot") as HTMLElement | null;
        const statusEl = taskEl.querySelector(".wf-task-status") as HTMLElement | null;
        if (dot && dot.getAttribute("data-status") !== t.status) {
          dot.setAttribute("data-status", t.status);
          dot.className = `wf-dot wf-dot--${t.status}`;
        }
        if (statusEl && statusEl.textContent !== t.status) {
          statusEl.textContent = t.status;
        }
      });
    }

    // Update assistant text content
    // During streaming we use textContent (instant, no parsing) to avoid
    // O(n^2) markdown re-parsing on every delta. Full markdown rendering
    // happens once when the stream ends.
    if (lastAssistantIndex >= 0) {
      const assistantItem = timeline[lastAssistantIndex] as Extract<TimelineItem, { kind: "assistant_text" }>;
      const newText = assistantItem.content;
      const el = this.ml.querySelector(`[data-id="${assistantItem.id}"]`) as HTMLElement | null;
      if (!el) {
        // DOM and state are out of sync (e.g. the assistant message was
        // created for a tool call before any text segment existed). Force a
        // full render so the produced content actually appears.
        // Guard against re-entrancy: if we're already inside a renderForce
        // (which is what got us here), don't recurse infinitely.
        if (!this._inRenderForce) {
          this.renderForce();
        }
        return;
      }
      if (newText.trim().length > 0) {
        const contentEl = el.querySelector(".msg-text") as HTMLElement | null;
        if (contentEl) {
          const newHtml = renderMarkdown(newText);
          if (contentEl.innerHTML !== newHtml) {
            contentEl.innerHTML = newHtml;
          }
        }
      }
    }

    this.autoScroll();
    const turnCount = getState().messages.filter(m => m.role === "user").length;
    this.scrollIndicator.update(turnCount);
  }

  private renderItemHTML(item: TimelineItem): string {
    switch (item.kind) {
      case "user": return this.renderUserItem(item);
      case "ai_header": return this.renderAIHeader(item);
      case "thinking": return this.renderThinkingStrip(item);
      case "tool": return this.renderToolCall(item);
      case "assistant_text": return this.renderAssistantText(item);
      case "error_card": return this.renderErrorCard(item);
      case "warning_card": return this.renderWarningCard(item);
      case "compact": return this.renderCompactCard(item);
      case "system_message": return this.renderSystemMessage(item);
      case "spec_card": return this.renderSpecCard(item);
      case "plan_card": return this.renderPlanCard(item);
      case "workflow": return this.renderWorkflowCard(item);
    }
    return "";
  }

  private renderAIHeader(item: Extract<TimelineItem, { kind: "ai_header" }>): string {
    return `<div class="ai-header">
      <span class="ai-name">${t("chat.yimAgent")}</span>
      <span class="ai-time">${item.time}</span>
    </div>`;
  }

  private renderModeCard(icon: string, label: string, summary?: string): string {
    const iconHtml = icon.startsWith("data:")
      ? `<img src="${icon}" class="mode-card-icon" style="width:16px;height:16px">`
      : `<i data-lucide="${icon}" class="lucide mode-card-icon"></i>`;
    return `<span class="mode-chip mode-card">${iconHtml}<span class="mode-card-label">${escapeHtml(label)}</span>${summary ? `<span class="mode-card-summary">· ${escapeHtml(summary)}</span>` : ""}</span>`;
  }

  private renderUserItem(item: Extract<TimelineItem, { kind: "user" }>): string {
    const isSubAgent = !!getState().subAgentView;
    const cmdMatch = item.content.match(/^\/(\w[\w-]*)(?:\s+(.*))?$/s);
    const cmdTagMatch = !cmdMatch ? item.content.match(/^<command>(\w[\w-]*)<\/command>$/s) : null;
    const effectiveCmdMatch = cmdMatch || cmdTagMatch;
    const isTerminal = item.mode?.startsWith("terminal:");
    const modeBadge = item.mode && !isTerminal ? (() => { const c = findSlashCommand(item.mode); const icon = c ? c.icon : "list-checks"; return `<span class="mode-chip" data-mode="${item.mode}"><i data-lucide="${icon}" class="chip-icon" style="width:12px;height:12px;"></i><span>${c ? c.title : item.mode}</span></span>`; })() : "";
    const fileCards = item.fileRefs?.map(f => {
      if (f.icon === "folder") return this.renderModeCard(f.icon, f.name, "folder");
      if (f.icon === "terminal") return this.renderModeCard(f.icon, f.name, `${f.size} line${f.size !== 1 ? "s" : ""}`);
      return this.renderModeCard(f.icon, f.name, fmtSize(f.size));
    }).join("") || "";
    const termCard = isTerminal ? this.renderModeCard("terminal", item.mode!.split(":")[1] || "Terminal", `${item.content.split("\n").length} lines`) : "";
    if (effectiveCmdMatch) {
      const cmdName = effectiveCmdMatch[1];
      const rest = cmdTagMatch ? "" : (effectiveCmdMatch[2] || "");
      const displayContent = rest ? escapeHtml(rest) : "";
      const cmd = findSlashCommand(cmdName);
      const cmdBadge = cmd
        ? `<span class="mode-chip" data-mode="${cmdName}"><i data-lucide="${cmd.icon}" class="chip-icon" style="width:12px;height:12px;"></i><span>${cmd.title}</span></span>`
        : `<span class="mode-chip" data-mode="${cmdName}"><i data-lucide="command" class="chip-icon" style="width:12px;height:12px;"></i><span>${escapeHtml(cmdName)}</span></span>`;
      return `<div class="user-item" data-user-idx="${item.index}">
        <div class="user-bubble">
          ${cmdBadge}
          ${modeBadge}
          ${displayContent}</div>
        <div class="user-actions">
          <button class="btn-icon btn-icon--msg msg-copy-btn" data-tooltip="${t("chat.copy")}">
            <i data-lucide="copy" class="lucide lucide-sm"></i>
          </button>
          ${isSubAgent ? "" : `<button class="btn-icon btn-icon--msg msg-rollback-btn" data-tooltip="${t("chat.rollbackEdit")}">
            <i data-lucide="history" class="lucide lucide-sm"></i>
          </button>
          <button class="btn-icon btn-icon--msg msg-delete-btn btn-icon--danger" data-tooltip="${t("chat.delete")}">
            <i data-lucide="trash-2" class="lucide lucide-sm"></i>
          </button>`}
        </div>
      </div>`;
    }
    const contentHtml = isSubAgent
      ? escapeHtml(item.content)
      : (item.content.includes("<attach ") || item.content.includes("<terminal>") || item.content.includes("<mode>")) ? "" : escapeHtml(item.content);
    return `<div class="user-item" data-user-idx="${item.index}">
      <div class="user-bubble">
        ${modeBadge}${termCard}${fileCards}${contentHtml}</div>
      <div class="user-actions">
        <button class="btn-icon btn-icon--msg msg-copy-btn" data-tooltip="${t("chat.copy")}">
          <i data-lucide="copy" class="lucide lucide-sm"></i>
        </button>
        ${isSubAgent ? "" : `<button class="btn-icon btn-icon--msg msg-rollback-btn" data-tooltip="${t("chat.rollbackEdit")}">
          <i data-lucide="history" class="lucide lucide-sm"></i>
        </button>
        <button class="btn-icon btn-icon--msg msg-delete-btn btn-icon--danger" data-tooltip="${t("chat.delete")}">
          <i data-lucide="trash-2" class="lucide lucide-sm"></i>
        </button>`}
      </div>
    </div>`;
  }

  private renderThinkingStrip(item: Extract<TimelineItem, { kind: "thinking" }>): string {
    const id = item.id;
    const expanded = this.expandedItems.has(id);
    return `<div class="strip-item${expanded ? " expanded" : ""}" data-id="${id}">
      <div class="strip" onmouseenter="window.__hoverOn(this)" onmouseleave="window.__hoverOff(this)">
        <span class="icon-wrap">
          <i data-lucide="brain" class="semantic"></i>
          <i data-lucide="chevron-down" class="arrow"></i>
        </span>
        <span class="strip-name">${t("chat.thought")}</span>
      </div>
      <div class="strip-body thought-body">${escapeHtml(item.text)}</div>
    </div>`;
  }

  private renderToolCall(item: Extract<TimelineItem, { kind: "tool" }>): string {
    const tc = item.tc;
    const name = tc.name;
    if (isHiddenTool(name)) return "";
    if (name === "agent") return this.renderAgent(tc, item.id);
    if (name === "question") return this.renderQuestionCard(tc, item.id);
    if (name === "info") return this.renderInfoCard(tc, item.id);
    if (isFileMutationTool(name)) {
      // edit / write / file_write / file_edit / apply_patch render as a
      // collapsible strip whose body shows a GitHub-style diff — same
      // primitive as web_search. delete_file keeps the compact file-card.
      if (name === "delete_file") return this.renderFileCard(tc);
      return this.renderExpandableStrip(tc, item.id);
    }
    if (isFileReadTool(name)) return this.renderToolItemSimple(tc);
    if (isToolItemTool(name)) return this.renderToolItemSimple(tc);
    return this.renderExpandableStrip(tc, item.id);
  }

  private renderQuestionCard(tc: ToolCallState, itemId: string): string {
    // Try to extract params — may be raw string or parsed object
    let params = tc.params;
    const rawArgs = params["arguments"];
    if (typeof rawArgs === "string" && rawArgs) {
      try { params = JSON.parse(rawArgs); } catch {}
    }
    const input = params["input"];
    if (input && typeof input === "object") params = input as Record<string, any>;

    let question = (params.question as string) || "";
    let details = (params.details as string) || "";
    let options: string[] = [];
    if (Array.isArray(params.options)) options = params.options.map(String);

    if (!question) {
      let qs = params.questions;
      // Handle double-encoded: questions might be a JSON string instead of array
      if (typeof qs === "string") {
        try { qs = JSON.parse(qs); } catch {}
      }
      if (Array.isArray(qs) && qs.length > 0) {
        const first = qs[0] as Record<string, any>;
        question = (first.question as string) || "";
        details = (first.details as string) || "";
        if (Array.isArray(first.options)) options = first.options.map(String);
      }
    }

    // Show placeholder when data hasn't arrived yet
    if (!question) {
      const debug = JSON.stringify(tc.params).substring(0, 200);
      return `<div class="question-card" id="tc-${tc.id}">
        <div class="question-card-header">
          <i data-lucide="help-circle" class="question-card-icon"></i>
          <span class="question-card-title">${t("chat.toolQuestion")}</span>
          <span class="question-card-badge">${t("chat.waitingForAnswer")}</span>
        </div>
        <div class="question-card-body">
          <div class="q-step" style="color:var(--text-muted);font-size:10px">${escapeHtml(debug)}</div>
        </div>
      </div>`;
    }

    // Done/error: show simple tool-item (like web_search completion)
    if (tc.status === "done" && tc.result) {
      return `<div class="tool-item">
        <i data-lucide="help-circle" class="tool-item-icon"></i>
        <span class="strip-name">${t("chat.toolQuestion")}</span>
        <span class="strip-summary">${escapeHtml(question.substring(0, 80))}</span>
      </div>`;
    }

    const id = `tc-${tc.id}`;
    const optsHtml = options.length
      ? `<div class="q-options">${options.map(o => {
          const s = o.indexOf("—") > 0 ? o.substring(0, o.indexOf("—")).trim() : o;
          const d = o.indexOf("—") > 0 ? o.substring(o.indexOf("—") + 1).trim() : "";
          return `<button class="q-option-card" data-value="${escapeHtml(s)}" onclick="event.stopPropagation();var inp=this.closest('.question-card-body,.agent-content').querySelector('.q-input');if(inp)inp.value=this.dataset.value;this.closest('.q-options').querySelectorAll('.q-option-card.selected').forEach(function(b){b.classList.remove('selected')});this.classList.add('selected')">
            <div class="q-option-title">${escapeHtml(s)}</div>
            ${d ? `<div class="q-option-desc">${escapeHtml(d)}</div>` : ""}
          </button>`;
        }).join("")}</div>`
      : "";

    return `<div class="question-card" id="${id}">
      <div class="question-card-header">
        <i data-lucide="help-circle" class="question-card-icon"></i>
        <span class="question-card-title">${t("chat.toolQuestion")}</span>
        <span class="question-card-badge">${t("chat.waitingForAnswer")}</span>
      </div>
      <div class="question-card-body">
        ${details ? `<div class="q-step">${escapeHtml(details)}</div>` : ""}
        <div class="q-field">
          <div class="q-field-label">${t("chat.questionField")}</div>
          <div class="q-field-text">${escapeHtml(question)}</div>
        </div>
        ${optsHtml}
        <div class="q-input-row">
          <input class="q-input" type="text" placeholder="${options.length ? t("chat.inputOtherRequirements") : t("chat.typeAnswer")}" />
          <button class="q-submit" onclick="event.stopPropagation();window.__answerQuestion(event,this,'${id}')">${t("chat.submit")}</button>
        </div>
      </div>
    </div>`;
  }

  private renderInfoCard(tc: ToolCallState, itemId: string): string {
    // Parse the info tool result. The backend returns a JSON payload with
    // display/title/content/media; fall back to treating the raw result as HTML.
    let payload: { display?: string; title?: string; content?: string; is_complete_html?: boolean; media?: Array<{type: string; src: string}> } = {};
    if (tc.result) {
      try {
        const parsed = JSON.parse(tc.result);
        if (parsed && typeof parsed === "object") payload = parsed;
      } catch {
        payload = { content: tc.result };
      }
    }

    const display = payload.display || (tc.params.display as string) || "base";
    const title = payload.title || (tc.params.title as string) || "";
    const content = payload.content || (tc.params.content as string) || "";
    const media = payload.media || [];
    const cardId = `tc-${tc.id}`;

    // Media card: render images/videos natively using MediaViewer.
    if (media.length > 0) {
      const itemsHtml = media.map((m, i) =>
        `<div data-type="${escapeHtml(m.type)}" data-src="${escapeHtml(m.src)}"></div>`
      ).join("");
      return `<div class="info-card info-card--media" id="${cardId}">${itemsHtml}</div>`;
    }

    if (!content) {
      return `<div class="info-card info-card--empty" id="${cardId}">
        <div class="info-card-header">
          <i data-lucide="layout-dashboard" class="info-card-icon"></i>
          <span class="info-card-title">${t("chat.toolInfo")}</span>
        </div>
        <div class="info-card-body">${t("chat.infoWaiting")}</div>
      </div>`;
    }

    // display='base' (default): strip card opens in child-window browser.
    const label = escapeHtml(title || t("chat.toolInfo"));
    return `<div class="strip-item" id="${cardId}" data-source="${escapeHtml(content)}">
      <div class="strip" onclick="window.__openInfoHtmlCard('${cardId}')" onmouseenter="window.__hoverOn(this)" onmouseleave="window.__hoverOff(this)">
        <span class="icon-wrap">
          <i data-lucide="layout-dashboard" class="semantic"></i>
          <i data-lucide="chevron-right" class="arrow"></i>
        </span>
        <span class="strip-name">${label}</span>
      </div>
    </div>`;
  }

  private renderFileCard(tc: ToolCallState): string {
    // Invoked only for delete_file (see renderToolCall routing). Kept as a
    // compact one-line card; no diff badge (delete has no diff) and no
    // "View Changes" button (the file is gone, nothing to review).
    const id = `tc-${tc.id}`;
    const path = (tc.params.path as string) || (tc.params.file_path as string) || "";
    const hasResult = !!tc.result;
    const isError = hasResult && (tc.isError || /^error:/i.test(tc.result || ""));
    const iconName = isError ? "alert-triangle" : "trash-2";
    const iconColor = isError ? "#f59e0b" : "#71717a";
    const errorText = isError ? t("chat.toolFailed") : "";
    return `<div class="file-card${isError ? " file-card--error" : ""}" data-id="${id}" data-path="${escapeHtml(path)}">
      <i data-lucide="${iconName}" class="file-card-icon" style="color:${iconColor}"></i>
      <span class="file-card-name">${escapeHtml(path || formatToolName(tc.name))}</span>
      ${errorText ? `<span class="file-card-error-text">${errorText}</span>` : ""}
    </div>`;
  }

  private renderTerminalCard(tc: ToolCallState, itemId: string): string {
    const id = `tc-${tc.id}`;
    const expanded = this.expandedItems.has(id);
    const term = tc.params.terminal as string | undefined;
    const termIcon = term ? getToolIcon("bash", term) : "command";
    const summary = getToolSummary(tc);
    const hasResult = !!tc.result;
    const bodyHtml = hasResult ? getToolBodyText(tc) : "";
    return `<div class="terminal-card${expanded ? " expanded" : ""}" data-id="${id}">
      <div class="terminal-card-header" onmouseenter="window.__hoverOn(this)" onmouseleave="window.__hoverOff(this)">
        <span class="icon-wrap">
          <i data-lucide="${termIcon}" class="semantic"></i>
          <i data-lucide="chevron-down" class="arrow"></i>
        </span>
        <span class="strip-name">${formatToolName(tc.name, term)}</span>
        <span class="strip-summary">${summary ? `<code>${escapeHtml(summary)}</code>` : ""}</span>
      </div>
      <div class="terminal-body-slot" data-has-body="${hasResult ? "1" : "0"}">${bodyHtml ? `<div class="terminal-body">${bodyHtml}</div>` : ""}</div>
    </div>`;
  }

  private renderExpandableStrip(tc: ToolCallState, itemId: string): string {
    const id = `tc-${tc.id}`;
    const expanded = this.expandedItems.has(id);
    const term = tc.params.terminal as string | undefined;
    const icon = getToolIcon(tc.name, term);
    const name = formatToolName(tc.name, term);
    const summary = getToolSummary(tc);
    const statusHtml = _toolStatusHtml(tc.status);
    const hasResult = !!tc.result;
    const bodyHtml = hasResult ? getToolBodyText(tc) : "";
    // Wrap the tool icon in an icon-wrap that swaps the semantic icon for
    // a chevron-down on hover, mirroring the thinking strip so the expand
    // affordance lives on the icon, not as a separate arrow on the right.
    const iconHtml = icon
      ? `<span class="icon-wrap"><i data-lucide="${icon}" class="semantic"></i><i data-lucide="chevron-down" class="arrow"></i></span>`
      : "";
    return `<div class="strip-item${expanded ? " expanded" : ""}" data-id="${id}">
      <div class="strip" onmouseenter="window.__hoverOn(this)" onmouseleave="window.__hoverOff(this)">
        ${iconHtml}
        <span class="strip-name">${name}</span>
        <span class="strip-status" data-status="${tc.status}">${statusHtml}</span>
        <span class="strip-summary">${summary ? escapeHtml(summary) : ""}</span>
      </div>
      <div class="strip-body-slot" data-has-body="${hasResult ? "1" : "0"}">${bodyHtml ? `<div class="strip-body">${bodyHtml}</div>` : ""}</div>
    </div>`;
  }

  private renderToolItemSimple(tc: ToolCallState): string {
    const id = `tc-${tc.id}`;
    const term = tc.params.terminal as string | undefined;
    const icon = getToolIcon(tc.name, term);
    const name = formatToolName(tc.name, term);
    const summary = getToolInlineSummary(tc);
    const statusHtml = _toolStatusHtml(tc.status);
    const iconHtml = icon ? `<i data-lucide="${icon}" class="tool-item-icon"></i>` : "";
    return `<div class="tool-item" data-id="${id}">
      ${iconHtml}
      <span class="strip-name">${name}</span>
      <span class="tool-item-status" data-status="${tc.status}">${statusHtml}</span>
      <span class="strip-summary">${summary ? escapeHtml(summary) : ""}</span>
    </div>`;
  }

  private renderAgent(tc: ToolCallState, itemId: string): string {
    const rawAgentName = getAgentName(tc);
    const agentName = formatAgentLabel(rawAgentName);
    const isPlanSpec = tc.params.mode === "plan" || tc.params.mode === "spec";
    const agentIcon = isPlanSpec ? "list-checks" : "sparkles";
    const statusHtml = _toolStatusHtml(tc.status);

    /** Pick the icon name and spinning class based on status and overall run state. */
    const _cardIcon = (status: string): { name: string; cls: string } => {
      const stillRunning = getState().running;
      if ((status === "running" || status === "pending") && stillRunning) {
        return { name: "loader", cls: "agent-card-icon spinning" };
      }
      return { name: agentIcon, cls: "agent-card-icon" };
    };

    // If this agent tool ran several parallel tasks, show one card per task
    // in the parent transcript instead of a single combined card.
    const tasks = this._agentTaskDividers(tc);
    if (tasks.length > 1) {
      return tasks.map((task, idx) => {
        const taskName = task.name || `${agentName} ${idx + 1}`;
        const taskStatus = task.status || tc.status;
        const { name: icon, cls: iconCls } = _cardIcon(taskStatus);
        return `<div class="agent-card" data-task-index="${task.index}" onclick="window.__openSubAgentView('${tc.id}', ${task.index})">
          <i data-lucide="${icon}" class="${iconCls}"></i>
          <span class="agent-card-name">${escapeHtml(taskName)}</span>
          <span class="agent-card-status" data-status="${taskStatus}">${_toolStatusHtml(taskStatus)}</span>
          <span class="agent-card-open">
            <i data-lucide="square-arrow-out-up-right" class="agent-card-open-icon"></i>
          </span>
        </div>`;
      }).join("");
    }

    const id = `tc-${tc.id}`;
    const { name: icon, cls: iconCls } = _cardIcon(tc.status);
    // Inline summary keeps ONLY the preview (last assistant text) so the
    // card stays compact. Thinking/tool counts are intentionally hidden in
    // the parent — they live in the sub-agent view.
    return `<div class="agent-card" data-id="${id}" onclick="window.__openSubAgentView('${tc.id}')">
      <i data-lucide="${icon}" class="${iconCls}"></i>
      <span class="agent-card-name">${escapeHtml(agentName)}</span>
      <span class="agent-card-status" data-status="${tc.status}">${statusHtml}</span>
      <span class="agent-card-open">
        <i data-lucide="square-arrow-out-up-right" class="agent-card-open-icon"></i>
      </span>
    </div>`;
  }

  private _agentTaskDividers(tc: ToolCallState): Array<{ index: number; name: string; status?: string }> {
    const msgs = tc.subAgentMessages;
    if (!msgs || msgs.length === 0) return [];
    const dividers = new Map<number, { index: number; name: string; status?: string }>();
    let fallbackIndex = 0;
    for (const message of msgs) {
      if (message.mode !== "task_divider") continue;
      const index = Number.isInteger(message.taskIndex) ? message.taskIndex! : fallbackIndex;
      fallbackIndex = Math.max(fallbackIndex, index + 1);
      dividers.set(index, {
        index,
        name: message.taskName || "",
        status: message.taskStatus,
      });
    }
    return [...dividers.values()].sort((a, b) => a.index - b.index);
  }

  private renderAssistantText(item: Extract<TimelineItem, { kind: "assistant_text" }>): string {
    const errorClass = item.hasError ? " has-error" : "";
    const msgId = item.messageId || item.id.replace("a-", "").replace(/-seg-\d+$/, "");
    return `<div class="assistant-text${errorClass}" data-id="${item.id}" data-message-id="${msgId}">
      <div class="msg-text">${renderMarkdown(item.content)}</div>
    </div>`;
  }

  private renderErrorCard(item: Extract<TimelineItem, { kind: "error_card" }>): string {
    const id = `ec-${item.messageId}`;
    const cat = item.errorCategory || "";
    // Category-based icon and label
    let iconSvg: string;
    let label: string;
    let extraClass = "";
    if (cat === "auth") {
      iconSvg = `<svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>`;
      label = t("chat.abortedError");
      extraClass = " status-error-auth";
    } else if (cat === "rate_limit") {
      iconSvg = `<svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`;
      label = t("chat.errorRateLimited");
      extraClass = " status-error-rate";
    } else if (cat === "context") {
      iconSvg = `<svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>`;
      label = t("chat.errorContext");
      extraClass = " status-error-context";
    } else if (cat === "network") {
      iconSvg = `<svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="1" y1="1" x2="23" y2="23"/><path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55"/><path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39"/><path d="M10.71 5.05A16 16 0 0 1 22.56 9"/><path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/></svg>`;
      label = t("chat.errorNetwork");
      extraClass = " status-error-network";
    } else if (cat === "server") {
      iconSvg = `<svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>`;
      label = t("chat.errorServer");
      extraClass = " status-error-server";
    } else if (cat === "tool") {
      iconSvg = `<svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>`;
      label = t("chat.errorTool");
      extraClass = " status-error-tool";
    } else {
      iconSvg = `<svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;
      label = t("chat.abortedError");
    }
    return `<div class="turn-status-card status-error${extraClass}" id="${id}">
      <div class="status-header" onclick="window.__toggleStatusCard('${id}')">
        ${iconSvg}
        <span class="status-label">${label}</span>
        <svg class="status-toggle" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
      </div>
      <div class="status-body">
        <div class="status-message">${escapeHtml(item.errorMessage)}</div>
      </div>
    </div>`;
  }

  private renderWarningCard(item: Extract<TimelineItem, { kind: "warning_card" }>): string {
    return `<div class="turn-status-card status-warning">
      <svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
      <span class="status-label">${t("chat.interrupted")}</span>
      <span class="status-detail">${escapeHtml(item.interruptedReason)}</span>
    </div>`;
  }

  private renderBranchSwitcher(): string {
    const st = getState();
    if (st.branches.length <= 1) return "";
    const sorted = [...st.branches].sort((a, b) => (a.created_at || 0) - (b.created_at || 0));
    const activeIdx = sorted.findIndex(b => b.id === st.activeBranchId);
    if (activeIdx < 0) return "";
    const ids = sorted.map(b => b.id).join(",");
    return `<span class="branch-switcher" data-branch-ids="${ids}" data-active-idx="${activeIdx}">
      <button class="branch-prev">‹</button>
      <span class="branch-indicator">${activeIdx + 1} / ${sorted.length}</span>
      <button class="branch-next">›</button>
    </span>`;
  }

  private renderCompactCard(item: Extract<TimelineItem, { kind: "compact" }>): string {
    const st = getState();
    const idx = parseInt(item.id.replace("compact-", ""));
    const evt = st.compactEvents[idx];
    if (!evt) return "";
    const id = item.id;
    const expanded = this.expandedItems.has(id);
    const reductionPct = evt.old_tokens > 0
      ? Math.round((1 - evt.new_tokens / evt.old_tokens) * 100)
      : 0;
    const summary = `${evt.old_count} → ${evt.new_count} messages · ${_fmtTokens(evt.old_tokens)} → ${_fmtTokens(evt.new_tokens)} tokens (${reductionPct}% reduced)`;
    const bodyLines = [
      `Old messages: ${evt.old_count}  New messages: ${evt.new_count}`,
      `Old tokens:   ${_fmtTokens(evt.old_tokens)}  New tokens:   ${_fmtTokens(evt.new_tokens)}`,
      `Reduction:    ${reductionPct}%`,
    ];
    return `<div class="strip-item${expanded ? " expanded" : ""}" data-id="${id}">
      <div class="strip" onmouseenter="window.__hoverOn(this)" onmouseleave="window.__hoverOff(this)">
        <span class="icon-wrap"><i data-lucide="shrink" class="semantic"></i><i data-lucide="chevron-down" class="arrow"></i></span>
        <span class="strip-name">Context compacted</span>
        <span class="strip-summary">${escapeHtml(summary)}</span>
      </div>
      <div class="strip-body">${escapeHtml(bodyLines.join("\n"))}</div>
    </div>`;
  }

  private renderSystemMessage(item: Extract<TimelineItem, { kind: "system_message" }>): string {
    const id = item.id;
    const expanded = this.expandedItems.has(id);
    const icon = item.kindTag === "error" ? "alert-circle" : "info";
    const label = item.kindTag === "error" ? "System notice" : "System message";
    return `<div class="strip-item system-message-strip${expanded ? " expanded" : ""}" data-id="${id}">
      <div class="strip" onmouseenter="window.__hoverOn(this)" onmouseleave="window.__hoverOff(this)">
        <span class="icon-wrap"><i data-lucide="${icon}" class="semantic"></i><i data-lucide="chevron-down" class="arrow"></i></span>
        <span class="strip-name">${escapeHtml(label)}</span>
        <span class="strip-summary">${escapeHtml(item.content.slice(0, 80))}</span>
      </div>
      <div class="strip-body">${escapeHtml(item.content)}</div>
    </div>`;
  }

  private renderSpecCard(item: Extract<TimelineItem, { kind: "spec_card" }>): string {
    const spec = item.spec;
    const status = spec.status;
    const isApproved = status === "approved";
    const isRejected = status === "rejected";
    const isReview = status === "review" || status === "draft";
    const sessionId = getState().sessionId;
    const cardId = `spec-card-${sessionId}`;

    // Section list as expandable file rows
    const sectionsHtml = spec.sections.map((s, i) => {
      const sid = `spec-sec-${i}`;
      const open = this.expandedItems.has(sid);
      return `<div class="review-file${open ? " expanded" : ""}" data-review-toggle="${sid}">
        <div class="review-file-row">
          <span class="review-file-icon"><i data-lucide="file-text"></i></span>
          <span class="review-file-name">${escapeHtml(s.title)}</span>
          <i data-lucide="chevron-down" class="review-file-arrow"></i>
        </div>
        <div class="review-file-body">${escapeHtml(s.content)}</div>
      </div>`;
    }).join("");

    const feedbackHtml = spec.feedback ? `<div class="review-feedback"><strong>Feedback:</strong> ${escapeHtml(spec.feedback)}</div>` : "";

    let bodyHtml: string;
    if (isReview) {
      bodyHtml = `<div class="question-card-body">
        <div class="q-step">${escapeHtml(t("chat.reviewSpecSub") || "If it does not match your intent, review and edit the files, or enter guidance in the input box.")}</div>
        <div class="q-field">
          <div class="q-field-label">${t("chat.reviewArtifact") || "Files"}</div>
          <div class="q-field-text">${sectionsHtml}</div>
        </div>
        ${feedbackHtml}
        <div class="q-actions" style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end">
          <button class="q-action-btn" data-spec-reject="${sessionId}" style="background:var(--bg-tertiary);color:var(--tool-text);border:1px solid var(--border)">${t("chat.reviewCancel") || "Cancel"}</button>
          <button class="q-action-btn" data-spec-approve="${sessionId}" style="background:var(--accent);color:#fff;border:1px solid var(--accent)">${t("chat.reviewExecute") || "Execute"}</button>
        </div>
      </div>`;
    } else if (isApproved) {
      bodyHtml = `<div class="question-card-body">
        <div class="q-step">${escapeHtml(t("chat.reviewSpecMain") || "The specification has been generated.")}</div>
        <div class="q-field">
          <div class="q-field-label">规格文档</div>
          <div class="q-field-text">${sectionsHtml}</div>
        </div>
        ${feedbackHtml}
        <div class="q-step" style="color:var(--success-color);margin-top:8px"><i data-lucide="check-circle"></i> ${t("chat.reviewExecuted") || "Executed"}</div>
      </div>`;
    } else if (isRejected) {
      bodyHtml = `<div class="question-card-body">
        <div class="q-step">${escapeHtml(t("chat.reviewSpecMain") || "The specification has been generated.")}</div>
        <div class="q-field">
          <div class="q-field-label">规格文档</div>
          <div class="q-field-text">${sectionsHtml}</div>
        </div>
        ${feedbackHtml}
        <div class="q-step" style="color:var(--danger-color);margin-top:8px"><i data-lucide="x-circle"></i> ${t("chat.reviewCancelled") || "Cancelled"}</div>
      </div>`;
    } else {
      bodyHtml = `<div class="question-card-body">${sectionsHtml}</div>`;
    }

    return `<div class="question-card" id="${cardId}">
      <div class="question-card-header">
        <i data-lucide="file-text" class="question-card-icon"></i>
        <span class="question-card-title">${escapeHtml(t("chat.reviewSpecMain") || "Specification Review")}</span>
        <span class="question-card-badge">${isReview ? (t("chat.waitingForAnswer") || "Pending") : (isApproved ? (t("chat.reviewExecuted") || "Executed") : (t("chat.reviewCancelled") || "Cancelled"))}</span>
      </div>
      ${bodyHtml}
    </div>`;
  }

  private renderPlanCard(item: Extract<TimelineItem, { kind: "plan_card" }>): string {
    const review = item.review;
    const status = review.status;
    const isApproved = status === "approved";
    const isRejected = status === "rejected";
    const isReview = status === "review" || status === "draft";
    const sessionId = getState().sessionId;
    const cardId = `plan-card-${review.review_id}`;

    // Parse sections from the full content using ## Plan/## Steps/## Checklist headers
    const sections = this.parsePlanSections(review.content);

    // File rows that open in the sidebar markdown tab on click
    const fileRows = [
      { name: "plan.md", content: sections.plan, icon: "file-text" },
      { name: "steps.md", content: sections.steps, icon: "list-ordered" },
      { name: "checklist.md", content: sections.checklist, icon: "check-square" },
    ];

    const fileRowsHtml = fileRows.map((f, i) => {
      const fileKey = `plan-${review.review_id}-${i}`;
      this._planFileLookup.set(fileKey, f.content);
      return `<div class="review-file" data-open-md="${fileKey}" data-md-title="${escapeHtml(f.name)}">
        <div class="review-file-row">
          <span class="review-file-icon"><i data-lucide="${f.icon}"></i></span>
          <span class="review-file-name">${escapeHtml(f.name)}</span>
        </div>
      </div>`;
    }).join("");

    let bodyHtml: string;
    if (isReview) {
      bodyHtml = `<div class="question-card-body">
        <div class="q-step">${escapeHtml(t("chat.reviewPlanSub") || "If it does not match your intent, review and edit the files, or enter guidance in the input box.")}</div>
        <div class="q-field">
          <div class="q-field-label">${t("chat.reviewArtifact") || "Files"}</div>
          <div class="q-field-text">${fileRowsHtml}</div>
        </div>
        <div class="q-actions" style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end">
          <button class="q-action-btn" data-plan-reject="${sessionId}" style="background:var(--bg-tertiary);color:var(--tool-text);border:1px solid var(--border)">${t("chat.reviewCancel") || "Cancel"}</button>
          <button class="q-action-btn" data-plan-approve="${sessionId}" style="background:var(--accent);color:#fff;border:1px solid var(--accent)">${t("chat.reviewExecute") || "Execute"}</button>
        </div>
      </div>`;
    } else if (isApproved) {
      bodyHtml = `<div class="question-card-body">
        <div class="q-step">${escapeHtml(t("chat.reviewPlanMain") || "The plan has been generated.")}</div>
        <div class="q-field">
          <div class="q-field-label">计划内容</div>
          <div class="q-field-text">${fileRowsHtml}</div>
        </div>
        <div class="q-step" style="color:var(--success-color);margin-top:8px"><i data-lucide="check-circle"></i> ${t("chat.reviewExecuted") || "Executed"}</div>
      </div>`;
    } else if (isRejected) {
      bodyHtml = `<div class="question-card-body">
        <div class="q-step">${escapeHtml(t("chat.reviewPlanMain") || "The plan has been generated.")}</div>
        <div class="q-field">
          <div class="q-field-label">计划内容</div>
          <div class="q-field-text">${fileRowsHtml}</div>
        </div>
        <div class="q-step" style="color:var(--danger-color);margin-top:8px"><i data-lucide="x-circle"></i> ${t("chat.reviewCancelled") || "Cancelled"}</div>
      </div>`;
    } else {
      bodyHtml = `<div class="question-card-body">${fileRowsHtml}</div>`;
    }

    return `<div class="question-card" id="${cardId}">
      <div class="question-card-header">
        <i data-lucide="list-checks" class="question-card-icon"></i>
        <span class="question-card-title">${escapeHtml(t("chat.reviewPlanMain") || "Plan Review")}</span>
        <span class="question-card-badge">${isReview ? (t("chat.waitingForAnswer") || "Pending") : (isApproved ? (t("chat.reviewExecuted") || "Executed") : (t("chat.reviewCancelled") || "Cancelled"))}</span>
      </div>
      ${bodyHtml}
    </div>`;
  }

  private parsePlanSections(text: string): { plan: string; steps: string; checklist: string } {
    const result = { plan: "", steps: "", checklist: "" };
    const re = /^##\s+(Plan|Steps|Checklist)\s*$/gmi;
    const parts = text.split(re);
    if (parts.length < 3) {
      result.plan = text;
      return result;
    }
    let key: "plan" | "steps" | "checklist" | "" = "";
    for (let i = 1; i < parts.length; i++) {
      const trimmed = parts[i].trim();
      if (trimmed === "Plan" || trimmed === "Steps" || trimmed === "Checklist") {
        key = trimmed.toLowerCase() as any;
      } else if (key) {
        result[key] = (result[key] + "\n\n" + parts[i]).trim();
      }
    }
    return result;
  }

  private renderWorkflowCard(_item: Extract<TimelineItem, { kind: "workflow" }>): string {
    const wf = getState().workflowState;
    if (!wf) return "";
    const pct = wf.totalTasks > 0 ? Math.round((wf.completedCount + wf.failedCount + wf.skippedCount) / wf.totalTasks * 100) : 0;
    const doneCount = wf.completedCount + wf.failedCount + wf.skippedCount;
    const status = wf.active ? "running" : (wf.success ? "completed" : "failed");
    const statusIcon = status === "running" ? "loader-circle" : status === "completed" ? "check-circle" : "x-circle";
    const statusColor = status === "running" ? "#3b82f6" : status === "completed" ? "#22c55e" : "#ef4444";
    const statusLabel = status === "running" ? t("chat.workflowRunning") || "Running" : status === "completed" ? t("chat.workflowDone") || "Completed" : t("chat.workflowFailed") || "Failed";
    const taskList = wf.tasks.map(t => {
      const dotCls = t.status === "completed" ? "wf-dot--done"
        : t.status === "running" ? "wf-dot--running"
        : t.status === "failed" ? "wf-dot--failed"
        : t.status === "skipped" ? "wf-dot--skipped"
        : "wf-dot--pending";
      const dot = `<span class="wf-dot ${dotCls}" data-tooltip="${escapeHtml(t.taskName)}: ${t.status}"></span>`;
      return `<div class="wf-task">
        ${dot}
        <span class="wf-task-name">${escapeHtml(t.taskName || t.taskId)}</span>
        <span class="wf-task-status">${t.status}</span>
      </div>`;
    }).join("");
    return `<div class="workflow-card" id="wf-${wf.workflowId}">
      <div class="workflow-card-header">
        <i data-lucide="${statusIcon}" class="workflow-card-icon" style="color:${statusColor}"></i>
        <span class="workflow-card-goal">${escapeHtml(wf.goal)}</span>
        <span class="workflow-card-badge" style="background:${statusColor}20;color:${statusColor}">${statusLabel}</span>
      </div>
      <div class="workflow-progress-bar">
        <div class="workflow-progress-fill" style="width:${pct}%;background:${statusColor}"></div>
      </div>
      <div class="workflow-progress-text">${doneCount}/${wf.totalTasks} tasks — ${wf.completedCount} done, ${wf.failedCount} failed, ${wf.skippedCount} skipped</div>
      <div class="workflow-task-list">${taskList}</div>
    </div>`;
  }

  private handleDelegateClick(e: MouseEvent): void {
    const target = e.target as HTMLElement;

    // Expandable strip / terminal card toggle (delegated).
    const strip = target.closest(".strip, .terminal-card-header") as HTMLElement | null;
    if (strip) {
      const item = strip.closest("[data-id]") as HTMLElement | null;
      if (item) {
        const id = item.getAttribute("data-id");
        if (id) {
          this.toggleItem(id, item);
          return;
        }
      }
    }

    // Review card section toggle: clicking a file row expands/collapses
    // that section's body. Uses data-review-toggle on the row.
    const reviewToggle = target.closest("[data-review-toggle]") as HTMLElement | null;
    if (reviewToggle) {
      const tid = reviewToggle.getAttribute("data-review-toggle");
      if (tid) {
        const expanded = this.expandedItems.has(tid);
        if (expanded) {
          this.expandedItems.delete(tid);
          reviewToggle.classList.remove("expanded");
        } else {
          this.expandedItems.add(tid);
          reviewToggle.classList.add("expanded");
        }
        if (typeof (window as any).lucide !== "undefined") {
          (window as any).lucide.createIcons();
        }
        e.stopPropagation();
        return;
      }
    }

    // Link click handling — route based on default_link_behavior setting
    const link = target.closest("a");
    if (link && link.href) {
      const behavior = (getState().settings.default_link_behavior as string) || "system";
      let url = link.href;
      // Only intercept http/https/www links
      if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("www.")) {
        e.preventDefault();
        e.stopPropagation();
        if (url.startsWith("www.")) url = "https://" + url;
        if (behavior === "in_app") {
          const api = (window as any).electronAPI;
          if (api?.openChildWindow) {
            api.openChildWindow(url, url);
          } else {
            window.open(url, "_blank");
          }
        } else {
          // Default: open in system browser
          const api = (window as any).electronAPI;
          if (api?.openExternal) {
            api.openExternal(url);
          } else {
            window.open(url, "_blank");
          }
        }
        return;
      }
    }

    const codeCopyBtn = target.closest(".code-copy");
    if (codeCopyBtn) {
      e.stopPropagation();
      const code = codeCopyBtn.getAttribute("data-code") || "";
      navigator.clipboard.writeText(code)
        .then(() => { codeCopyBtn.textContent = t("chat.copied"); setTimeout(() => { codeCopyBtn.textContent = t("chat.copy"); }, 2000); })
        .catch(() => showToast(t("chat.copyFailed"), "", "error", "Chat"));
      return;
    }

    const copyBtn = target.closest(".msg-copy-btn");
    if (copyBtn) {
      e.stopPropagation();
      const userItem = copyBtn.closest(".user-item") as HTMLElement | null;
      const idx = userItem ? parseInt(userItem.getAttribute("data-user-idx") ?? "") : NaN;
      const st = getState();
      const userMsgs = st.messages.filter(m => m.role === "user");
      if (!isNaN(idx) && userMsgs[idx]) {
        navigator.clipboard.writeText(userMsgs[idx].content)
          .then(() => flashCopyButton(copyBtn as HTMLElement))
          .catch(() => showToast(t("chat.copyFailed"), "", "error", "Chat"));
      }
      return;
    }

    const editBtn = target.closest(".msg-rollback-btn");
    if (editBtn) {
      e.stopPropagation();
      const userItem = editBtn.closest(".user-item") as HTMLElement | null;
      const idx = userItem ? parseInt(userItem.getAttribute("data-user-idx") ?? "") : NaN;
      const st = getState();
      const userMsgs = st.messages.filter(m => m.role === "user");
      if (isNaN(idx) || !userMsgs[idx]) return;
      const targetMsg = userMsgs[idx];
      let origContent = targetMsg.content;
      if (origContent.includes("<terminal>") || origContent.includes("<attach ") || origContent.includes("<mode>")) origContent = "";
      Dialog.confirm(t("chat.rollbackEdit"), t("chat.rollbackEditDesc")).then((confirmed) => {
        if (confirmed) {
          const sid = targetMsg.serverId;
          rememberRollbackEditTarget(targetMsg, idx);
          if (sid && st.activeBranchId) {
            send({ type: "rollback", branch_id: st.activeBranchId, message_id: sid });
          } else {
            send({ type: "delete_message", message_index: idx, session_id: st.sessionId });
          }
          // Immediately remove this message and all after from local state
          truncateToUserMessage(idx);
          this.renderForce();
          const input = document.getElementById("prompt-input") as HTMLElement | null;
          if (input) { input.textContent = origContent; input.focus(); }
          const msgMode = (targetMsg as any).mode;
          if (msgMode) {
            restoreInputModeChip(msgMode);
          }
          // Restore attachment chips from fileRefs
          const refs = targetMsg.fileRefs;
          if (refs && refs.length > 0) {
            const atts: AttachmentMeta[] = [];
            for (const r of refs) {
              if (r.mime_type === "text/x-terminal") continue;
              if (r.path) {
                atts.push({ name: r.name, path: r.path, content: "", mime_type: r.mime_type || "", size: r.size, is_binary: false });
              }
            }
            if (atts.length > 0) addAttachments(atts);
          }
        }
      });
      return;
    }

    const deleteBtn = target.closest(".msg-delete-btn");
    if (deleteBtn) {
      e.stopPropagation();
      const userItem = deleteBtn.closest(".user-item") as HTMLElement | null;
      const idx = userItem ? parseInt(userItem.getAttribute("data-user-idx") ?? "") : NaN;
      const st = getState();
      const userMsgs = st.messages.filter(m => m.role === "user");
      if (isNaN(idx) || !userMsgs[idx]) return;
      Dialog.confirm(t("chat.deleteMessage"), t("chat.deleteMessageDesc")).then((confirmed) => {
        if (confirmed) send({ type: "delete_message", message_index: idx });
      });
      return;
    }

    const assistantCopyBtn = target.closest(".assistant-copy-btn");
    if (assistantCopyBtn) {
      e.stopPropagation();
      const turn = assistantCopyBtn.closest(".turn") as HTMLElement | null;
      const assistantItem = turn?.querySelector(".assistant-text") as HTMLElement | null;
      const msgId = assistantItem?.dataset.messageId;
      if (!msgId) return;
      const st = getState();
      const msg = st.messages.find(m => m.id === msgId);
      if (msg) {
        navigator.clipboard.writeText(msg.content)
          .then(() => flashCopyButton(assistantCopyBtn as HTMLElement))
          .catch(() => showToast(t("chat.copyFailed"), "", "error", "Chat"));
      }
      return;
    }

    const assistantRetryBtn = target.closest(".assistant-retry-btn");
    if (assistantRetryBtn) {
      e.stopPropagation();
      const turn = assistantRetryBtn.closest(".turn") as HTMLElement | null;
      const assistantItem = turn?.querySelector(".assistant-text") as HTMLElement | null;
      if (!assistantItem) return;
      const existingPopup = assistantItem.querySelector(".retry-popup");
      if (existingPopup) {
        existingPopup.remove();
        return;
      }
      const msgId = assistantItem.dataset.messageId;
      if (!msgId) return;
      const rect = (assistantRetryBtn as HTMLElement).getBoundingClientRect();
      const popup = document.createElement("div");
      popup.className = "retry-popup";
      popup.style.position = "fixed";
      popup.style.top = `${rect.bottom + 2}px`;
      popup.style.left = `${rect.left}px`;
      popup.innerHTML = `
        <div class="retry-popup-item" data-mode="normal">${t("chat.retryNormal")}</div>
        <div class="retry-popup-item" data-mode="detailed">${t("chat.retryDetailed")}</div>
        <div class="retry-popup-item" data-mode="concise">${t("chat.retryConcise")}</div>
      `;
      assistantItem.appendChild(popup);
      const closePopup = (ev: MouseEvent) => {
        if (!popup.contains(ev.target as Node)) {
          popup.remove();
          document.removeEventListener("click", closePopup);
        }
      };
      setTimeout(() => document.addEventListener("click", closePopup), 0);
      return;
    }

    const retryPopupItem = target.closest(".retry-popup-item");
    if (retryPopupItem) {
      e.stopPropagation();
      const popup = retryPopupItem.closest(".retry-popup") as HTMLElement | null;
      const assistantItem = popup?.closest(".assistant-text") as HTMLElement | null;
      const msgId = assistantItem?.dataset.messageId;
      if (!msgId) return;
      const mode = (retryPopupItem as HTMLElement).dataset.mode || "normal";

      // Find the preceding user message and prepare the UI for retry
      const st = getState();
      const assistantIdx = st.messages.findIndex(m => m.id === msgId);
      if (assistantIdx < 0) return;
      let userContent = "";
      for (let i = assistantIdx - 1; i >= 0; i--) {
        if (st.messages[i].role === "user") {
          userContent = st.messages[i].content;
          break;
        }
      }
      if (!userContent) return;

      // Compute user message index (0-based among all user messages in the session)
      let userMsgIdx = -1;
      for (let i = 0; i < assistantIdx; i++) {
        if (st.messages[i].role === "user") userMsgIdx++;
      }

      // Remove old assistant messages after the fork point; the preceding
      // user message stays in place (no duplicate needed).
      const removedIds = new Set<string>();
      for (let i = assistantIdx; i < st.messages.length; i++) {
        removedIds.add(st.messages[i].id);
      }
      removeBranchMessages(removedIds);
      // Create assistant placeholder for new streaming output
      startAssistantMessage();
      setRunning(true);

      popup?.remove();
      const branchId = st.activeBranchId;
      if (typeof (window as any).sendRetry === "function") {
        (window as any).sendRetry(branchId, userMsgIdx, mode);
      }
      return;
    }

    const branchPrev = target.closest(".branch-prev");
    if (branchPrev) {
      e.stopPropagation();
      const switcher = branchPrev.closest(".branch-switcher") as HTMLElement;
      if (!switcher) return;
      const ids = switcher.dataset.branchIds?.split(",") || [];
      const idx = parseInt(switcher.dataset.activeIdx || "0");
      const newIdx = idx > 0 ? idx - 1 : ids.length - 1;
      const branchId = ids[newIdx];
      if (branchId && branchId !== getState().activeBranchId) {
        if (typeof (window as any).sendSwitchBranch === "function") {
          (window as any).sendSwitchBranch(branchId);
        }
      }
      return;
    }

    const branchNext = target.closest(".branch-next");
    if (branchNext) {
      e.stopPropagation();
      const switcher = branchNext.closest(".branch-switcher") as HTMLElement;
      if (!switcher) return;
      const ids = switcher.dataset.branchIds?.split(",") || [];
      const idx = parseInt(switcher.dataset.activeIdx || "0");
      const newIdx = idx < ids.length - 1 ? idx + 1 : 0;
      const branchId = ids[newIdx];
      if (branchId && branchId !== getState().activeBranchId) {
        if (typeof (window as any).sendSwitchBranch === "function") {
          (window as any).sendSwitchBranch(branchId);
        }
      }
      return;
    }

    // Spec approve/reject buttons
    const approveBtn = target.closest("[data-spec-approve]") as HTMLElement | null;
    if (approveBtn) {
      e.stopPropagation();
      const sessionId = approveBtn.getAttribute("data-spec-approve") || "";
      send({ type: "spec_approve", session_id: sessionId } as any);
      return;
    }
    const rejectBtn = target.closest("[data-spec-reject]") as HTMLElement | null;
    if (rejectBtn) {
      e.stopPropagation();
      const sessionId = rejectBtn.getAttribute("data-spec-reject") || "";
      const feedback = prompt("Feedback (optional):") || "";
      send({ type: "spec_reject", session_id: sessionId, feedback } as any);
      return;
    }

    // Plan file rows: open in sidebar markdown tab
    const openMdBtn = target.closest("[data-open-md]") as HTMLElement | null;
    if (openMdBtn) {
      e.stopPropagation();
      const fileKey = openMdBtn.getAttribute("data-open-md") || "";
      const title = openMdBtn.getAttribute("data-md-title") || "";
      const content = this._planFileLookup.get(fileKey) || "";
      (window as any).__sessionInner?.openMarkdownPreview(content, title);
      return;
    }

    // Plan approve/reject buttons
    const planApproveBtn = target.closest("[data-plan-approve]") as HTMLElement | null;
    if (planApproveBtn) {
      e.stopPropagation();
      const sessionId = planApproveBtn.getAttribute("data-plan-approve") || "";
      send({ type: "plan_approve", session_id: sessionId } as any);
      return;
    }
    const planRejectBtn = target.closest("[data-plan-reject]") as HTMLElement | null;
    if (planRejectBtn) {
      e.stopPropagation();
      const sessionId = planRejectBtn.getAttribute("data-plan-reject") || "";
      send({ type: "plan_reject", session_id: sessionId } as any);
      return;
    }
  }

  private toggleItem(id: string, el: HTMLElement): void {
    if (this.expandedItems.has(id)) {
      this.expandedItems.delete(id);
      el.classList.remove("expanded");
      this.userCollapsedItems.add(id);
      this.userExpandedItems.delete(id);
    } else {
      this.expandedItems.add(id);
      el.classList.add("expanded");
      this.userCollapsedItems.delete(id);
      this.userExpandedItems.add(id);
    }
  }

  private autoScroll(): void {
    const st = getState();
    if (st.messages.length === 0) return;
    if (st.messages[st.messages.length - 1].role === "user") { this.scrollToBottom(); return; }
    if (!st.running) return;
    if (!this.userScrolledUp) this.scrollToBottom();
  }

  private toggleWelcome(show: boolean): void {
    if (show) { this.welcomeScreen.classList.remove("hidden"); this.ml.classList.add("hidden"); }
    else { this.welcomeScreen.classList.add("hidden"); this.ml.classList.remove("hidden"); }
  }

  /** Scrolls the message list to the bottom (unless the user scrolled up). */
  scrollToBottom(): void {
    const c = document.getElementById("chat-container");
    if (c) c.scrollTop = c.scrollHeight;
  }

  private _currentQuote: StatusQuote | null = null;

  private _updateStatusBar(running: boolean): void {
    if (running) {
      if (!this._currentQuote) {
        this._currentQuote = pickRandomQuote();
      }
      const q = this._currentQuote;
      this.statusBar.innerHTML = `<span class="status-shimmer">${t(`chat.${q.textKey}`)}</span>`;
      this.statusBar.classList.remove("hidden");
    } else {
      this.statusBar.classList.add("hidden");
      this._currentQuote = null;
    }
  }
}

class ChatScrollIndicator {
  private container: HTMLElement;
  private root: HTMLElement;
  private track: HTMLElement;
  private thumb: HTMLElement;
  private ticks: HTMLElement[] = [];
  private tickCount = 0;
  private dragging = false;
  private rafScheduled = false;

  constructor(container: HTMLElement) {
    this.container = container;
    this.root = document.getElementById("chat-scroll-indicator") as HTMLElement;
    this.track = document.getElementById("chat-scroll-track") as HTMLElement;
    this.thumb = document.getElementById("chat-scroll-thumb") as HTMLElement;
    this.bind();
  }

  private bind(): void {
    this.container.addEventListener("scroll", () => this.schedule(), { passive: true });
    this.root.addEventListener("mousedown", (e) => this.onPointerDown(e));
    window.addEventListener("mousemove", (e) => this.onPointerMove(e));
    window.addEventListener("mouseup", () => this.onPointerUp());
    if (typeof ResizeObserver !== "undefined") {
      const ro = new ResizeObserver(() => this.schedule());
      ro.observe(this.container);
    }
  }

  private schedule(): void {
    if (this.rafScheduled) return;
    this.rafScheduled = true;
    requestAnimationFrame(() => {
      this.rafScheduled = false;
      this.update();
    });
  }

  private rebuildTicks(count: number): void {
    this.tickCount = count;
    this.track.innerHTML = "";
    this.ticks = [];
    for (let i = 0; i < count; i++) {
      const tick = document.createElement("div");
      tick.className = "chat-scroll-tick";
      this.track.appendChild(tick);
      this.ticks.push(tick);
    }
  }

  update(turns?: number): void {
    if (turns !== undefined && turns !== this.tickCount) {
      this.rebuildTicks(Math.min(turns, 5));
    }
    if (this.tickCount < 2) {
      this.root.classList.add("hidden");
      return;
    }
    this.root.classList.remove("hidden");
    const { scrollTop, scrollHeight, clientHeight } = this.container;
    const scrollable = scrollHeight - clientHeight;
    if (scrollable <= 4) {
      this.root.classList.add("hidden");
      return;
    }
    const ratio = Math.min(1, Math.max(0, scrollTop / scrollable));
    const trackRect = this.track.getBoundingClientRect();
    const rootRect = this.root.getBoundingClientRect();
    const thumbMax = trackRect.height;
    this.thumb.style.top = `${trackRect.top - rootRect.top + ratio * thumbMax}px`;
    const n = this.ticks.length;
    const exactPos = ratio * (n - 1);
    let closestIdx = 0;
    let minDist = Math.abs(0 - exactPos);
    for (let i = 1; i < n; i++) {
      const d = Math.abs(i - exactPos);
      if (d < minDist) { minDist = d; closestIdx = i; }
    }
    for (let i = 0; i < n; i++) {
      const dist = Math.abs(i - exactPos) / (n - 1);
      if (i === closestIdx) {
        this.ticks[i].style.background = "var(--accent-color, #1e6cff)";
      } else {
        const gray = Math.round(155 + dist * 70);
        this.ticks[i].style.background = `rgb(${gray}, ${gray}, ${gray})`;
      }
      this.ticks[i].style.opacity = "1";
    }
  }

  private onPointerDown(e: MouseEvent): void {
    e.preventDefault();
    this.dragging = true;
    this.root.classList.add("dragging");
    this.jumpTo(e.clientY);
  }

  private onPointerMove(e: MouseEvent): void {
    if (!this.dragging) return;
    this.jumpTo(e.clientY);
  }

  private onPointerUp(): void {
    if (!this.dragging) return;
    this.dragging = false;
    this.root.classList.remove("dragging");
  }

  private jumpTo(clientY: number): void {
    const rect = this.root.getBoundingClientRect();
    if (rect.height <= 0) return;
    const y = Math.min(rect.bottom, Math.max(rect.top, clientY));
    const ratio = (y - rect.top) / rect.height;
    const { scrollHeight, clientHeight } = this.container;
    const max = Math.max(0, scrollHeight - clientHeight);
    this.container.scrollTop = ratio * max;
  }
}



