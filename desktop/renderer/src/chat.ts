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

import { getState, subscribe, showToast, addUserMessage, addAttachments, startAssistantMessage, setRunning, removeBranchMessages, restoreInputModeChip, truncateToUserMessage, setSubAgentView, pushSubAgentBreadcrumb, popSubAgentBreadcrumb, clearSubAgentBreadcrumb, resetToSubAgentBreadcrumbIndex, rememberRollbackEditTarget, isEnabled } from "./state.js";
import { send } from "./ws.js";
import { setRequestedSessionId } from "./stream.js";
import type { Message, ToolCallState, BranchMeta, AttachmentMeta } from "./types.js";
import MarkdownIt from "markdown-it";
import hljs from "highlight.js";
import { t, onLocaleChange, getLocale } from "./i18n.js";
import { Dialog } from "./dialog.js";
import { findSlashCommand } from "./slash_commands.js";
import { EALoader } from "./ealoader.js";
import { renderFlightWidget, renderTrainWidget, renderShipWidget } from "./info-widgets.js";
import { renderDiffHtml } from "./diff_render.js";

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
         name === "web_search" || name === "computer" || name === "desktop";
}

function isToolItemTool(name: string): boolean {
  return name === "skill" || name === "mcp" || name.startsWith("mcp__") ||
         name === "memory" || name.startsWith("memory_") ||
         name === "task" || name.startsWith("task_") ||
         name === "image" || name === "spreadsheet" || name.startsWith("cron_") || name === "todo" ||
         name === "find_tool" ||
         name === "web_fetch" || name === "git" || name === "lsp" || name === "notebook" ||
         name === "rest_client" || name === "browser" || name === "database" || name === "docker" ||
         name === "pdf" || name === "deploy" || name === "apply_patch";
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
    // Map terminal type to Lucide icon name
    const terminalIcons: Record<string, string> = {
      powershell: "terminal",
      cmd: "command",
      bash: "terminal",
      python: "code-2",
      node: "code",
      auto: "command",
    };
    return terminal ? (terminalIcons[terminal] || "command") : "command";
  }
  if (isFileMutationTool(name)) return "pencil-line";
  if (isFileReadTool(name)) return "eye";
  if (name === "web_search" || name === "web_fetch") return "globe";
  if (name === "search" || name === "grep" || name === "codebase") return "search";
  if (name === "find_tool") return "compass";
  if (name === "glob") return "folder-search";
  if (name === "skill") return "wand-2";
  if (name === "mcp" || name.startsWith("mcp__")) return "plug";
  if (name.startsWith("memory_")) return "database";
  if (name.startsWith("task_")) return "list-checks";
  if (name === "agent") return "zap";
  if (name === "browser") return "monitor";
  if (name === "computer" || name === "desktop") return "container";
  if (name === "notebook") return "notebook-pen";
  if (name === "git") return "git-branch";
  if (name === "lsp") return "code-2";
  if (name === "database") return "database";
  if (name === "docker") return "container";
  if (name === "pdf") return "file-text";
  if (name === "deploy") return "rocket";
  if (name === "rest_client") return "cloud";
  if (name === "apply_patch") return "git-pull-request";
  if (name === "image") return "image";
  if (name === "spreadsheet") return "table";
  if (name.startsWith("cron_")) return "clock-9";
    if (name === "todo") return "check-circle-2";
    if (name === "plan") return "file-text";
    if (name === "question") return "help-circle";
    if (name === "memory_profile") return "user-circle";
    if (name === "compact") return "shrink";
    if (name === "info") return "layout-dashboard";
    return "";
}

function formatToolName(name: string, terminal?: string): string {
  // Append terminal type for bash tools
  if (terminal && (name === "bash" || name === "shell" || name === "chat.terminal" || name === "run_command")) {
    return terminal.charAt(0).toUpperCase() + terminal.slice(1);
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
    rest_client: "Rest Client", desktop: "Desktop",
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

function getAgentName(tc: ToolCallState): string {
  const configuredName = (tc.params.agent_name as string) || (tc.params.name as string);
  return configuredName || t("chat.agent");
}

/** Normalizes an agent/tool name into a human-friendly display label. */
export function formatAgentLabel(rawName: string): string {
  // Capitalize first letter, append AGENT label
  const name = rawName.charAt(0).toUpperCase() + rawName.slice(1).toLowerCase();
  return /\bagent\b/i.test(name) ? name : `${name} Agent`;
}

function buildSubAgentTimeline(msgs: Message[]): TimelineItem[] {
  const timeline = buildTimeline(msgs);
  // When the sub-agent view is running, suppress action buttons (copy, retry)
  // on all messages so they only appear after the turn is truly finished.
  const subView = getState().subAgentView;
  const subRunning = !!(subView && (subView.status === "running" || subView.status === "pending"));
  if (subRunning) {
    for (const item of timeline) {
      if (item.kind === "assistant_text") {
        (item as any).showActions = false;
      }
    }
  }
  // Keep only the first ai_header - sub-agent thinking/text/tool segments
  // belong to a single assistant turn, not individual turns per segment.
  let seenHeader = false;
  return timeline.filter(item => {
    if (item.kind === "ai_header") {
      if (seenHeader) return false;
      seenHeader = true;
    }
    return true;
  });
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

type TimelineItem =
  | { kind: "user"; id: string; content: string; index: number; showBranchSwitcher?: boolean; mode?: string; fileRefs?: { name: string; size: number; icon: string }[] }
  | { kind: "ai_header"; id: string; time: string }
  | { kind: "thinking"; id: string; text: string; elapsed?: number; messageId?: string }
  | { kind: "tool"; id: string; tc: ToolCallState; messageId?: string }
  | { kind: "assistant_text"; id: string; content: string; isStreaming: boolean; hasError?: boolean; messageId?: string; showActions?: boolean; showBranchSwitcher?: boolean }
  | { kind: "error_card"; id: string; messageId: string; errorMessage: string; errorCode: string }
  | { kind: "warning_card"; id: string; messageId: string; interruptedReason: string }
  | { kind: "inline_success"; id: string; messageId: string; turnStatusText: string }
  | { kind: "inline_cancelled"; id: string; messageId: string; text: string }
  | { kind: "compact"; id: string }
  | { kind: "system_message"; id: string; content: string; kindTag: string }
  | { kind: "spec_card"; id: string; spec: import("./types.js").SpecData }
  | { kind: "workflow"; id: string };

function buildTimeline(msgs: Message[]): TimelineItem[] {
  const items: TimelineItem[] = [];
  let userIndex = 0;

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

  // Insert spec card when spec data is available
  if (st.spec) {
    items.push({ kind: "spec_card", id: "spec-card", spec: st.spec });
  }

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
                showActions: !msg.isStreaming && isLast && !st.running,
                showBranchSwitcher: i === firstAssistantAfterForkIdx && isLast,
              });
            }
            // Insert status cards after the last text segment of each
            // assistant message.  Must be outside the isErrorOnly check
            // so the error card still renders when the text content is
            // purely the error message (avoiding double display).
            if (isLast) {
              if (msg.errorMessage) {
                items.push({ kind: "error_card", id: `ec-${msg.id}`, messageId: msg.id, errorMessage: msg.errorMessage, errorCode: msg.errorCode || "" });
              } else if (msg.interruptedReason) {
                items.push({ kind: "warning_card", id: `wc-${msg.id}`, messageId: msg.id, interruptedReason: msg.interruptedReason });
              }
              if (msg.turnStatusText) {
                items.push({ kind: "inline_success", id: `is-${msg.id}`, messageId: msg.id, turnStatusText: msg.turnStatusText });
              }
              if (msg.cancelledText) {
                items.push({ kind: "inline_cancelled", id: `ic-${msg.id}`, messageId: msg.id, text: msg.cancelledText });
              }
            }
            textSegIndex++;
          } else if (seg.kind === "tool") {
            const tc = seg.toolId ? msg.toolCalls.find(t => t.id === seg.toolId) : undefined;
            if (tc) {
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
          items.push({ kind: "tool", id: `tc-${tc.id}`, tc, messageId: msg.id });
        }
        if (msg.content.trim().length > 0 || msg.isStreaming) {
          items.push({ kind: "assistant_text", id: `a-${msg.id}`, content: msg.content, isStreaming: msg.isStreaming, hasError: msg.hasError, messageId: msg.id });
        }
        // Insert status cards for legacy messages
        if (msg.errorMessage) {
          items.push({ kind: "error_card", id: `ec-${msg.id}`, messageId: msg.id, errorMessage: msg.errorMessage, errorCode: msg.errorCode || "" });
        } else if (msg.interruptedReason) {
          items.push({ kind: "warning_card", id: `wc-${msg.id}`, messageId: msg.id, interruptedReason: msg.interruptedReason });
        }
        if (msg.turnStatusText) {
          items.push({ kind: "inline_success", id: `is-${msg.id}`, messageId: msg.id, turnStatusText: msg.turnStatusText });
        }
        if (msg.cancelledText) {
          items.push({ kind: "inline_cancelled", id: `ic-${msg.id}`, messageId: msg.id, text: msg.cancelledText });
        }
      }
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
      // status/params/error changes are handled incrementally.
      return { k: "tc", id: i.id, n: i.tc.name, r: i.tc.result ? 1 : 0 };
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
    if (i.kind === "error_card") return { k: "ec", id: i.id };
    if (i.kind === "warning_card") return { k: "wc", id: i.id };
    if (i.kind === "inline_success") return { k: "is", id: i.id };
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
  private lastAssistantMsgId = "";
  private rafPending = false;
  private liveLoader: EALoader | null = null;
  private scrollIndicator: ChatScrollIndicator;
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

    const w = window as any;
    w.__openSubAgentView = (toolCallId: string) => {
      const st = getState();
      const MAX_DEPTH = 4;
      // Enforce max nesting depth using breadcrumb length
      if (st.subAgentBreadcrumb.length >= MAX_DEPTH) {
        showToast?.("Sub-agent", `Max depth (${MAX_DEPTH}) reached`);
        return;
      }
      for (const msg of st.messages) {
        for (const tc of msg.toolCalls) {
          if (tc.id === toolCallId) {
            // The parent tool call id is the currently-active sub-agent
            // view's tc id (when navigating from inside another sub-agent)
            // or null when navigating from the root main session.
            const parentToolCallId = st.subAgentView ? st.subAgentView.id : null;
            // Record current session as parent in the breadcrumb stack
            const agentName = tc.name === "agent"
              ? String(tc.params.agent_name || tc.params.name || tc.params.mode || "agent")
              : tc.name;
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
                name: agentName,
                toolCallId,
                parentToolCallId,
              });
            }
            if (tc.subAgentMessages && tc.subAgentMessages.length > 0) {
              setSubAgentView(tc);
              this.render();
            } else if (tc.subAgentSessionId) {
              const requestId = crypto.randomUUID();
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
          if (tc.id === target.toolCallId) {
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

    this.container.addEventListener("scroll", () => {
      const { scrollTop, scrollHeight, clientHeight } = this.container;
      this.userScrolledUp = scrollHeight - scrollTop - clientHeight > 100;
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

  renderForce(): void {
    this.renderedKey = "";
    this.render();
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
            if (tc.id === crumb.toolCallId) {
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
      const subMsgs = subTc.subAgentMessages || [];
      const hasInlineData = subMsgs.length > 0;
      const isStreaming = subTc.status === "running" || subTc.status === "pending";
      this.renderedKey = "__subagent__";
      if (hasInlineData) {
        // Sub-agent snapshot arrived: render the real user + assistant
        // bubbles together.  The loader was already torn down at the
        // top of render(), so the message area is clean by now.
        const timeline = buildSubAgentTimeline(subMsgs);
        this.fullRender(timeline, subMsgs);
      } else if (isStreaming) {
        // Still waiting for the first snapshot: hide every message bubble
        // (no user box, no assistant box) and show only the centered EA
        // loader.  Both bubbles will appear together once data lands.
        this.ml.innerHTML = "";
        this.liveLoader = new EALoader(this.ml);
      } else {
        // Finished (or never started) without producing any output.
        this.ml.innerHTML = `<div class="sub-agent-empty"><p>${t("chat.noSubAgentOutput")}</p></div>`;
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
    if (key !== this.renderedKey) {
      console.log("[chat.render] fullRender", { msgCount: msgs.length, roles: msgs.map(m => m.role), serverIds: msgs.map(m => m.serverId?.slice(-12)) });
      this.fullRender(timeline, msgs);
      this.renderedKey = key;
    } else {
      this.incrementalTextUpdate(timeline);
    }
    this._updateStatusBar(state.running);

  }

  private fullRender(timeline: TimelineItem[], allMsgs?: Message[]): void {
    const st = getState();
    const autoExpand = isEnabled(st.settings.auto_expand);

    // Auto-expand based on setting (unless user manually collapsed)
    for (const item of timeline) {
      if (item.kind === "thinking") {
        const id = item.id;
        if (autoExpand && !this.userCollapsedItems.has(id)) {
          this.expandedItems.add(id);
        } else if (this.userCollapsedItems.has(id)) {
          this.expandedItems.delete(id);
        }
      } else if (item.kind === "tool" && item.tc.name === "agent") {
        const id = item.id;
        if (autoExpand && !this.userCollapsedItems.has(id)) {
          this.expandedItems.add(id);
        } else if (this.userCollapsedItems.has(id)) {
          this.expandedItems.delete(id);
        }
      }
    }

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
        // thinking / assistant_text / tool — belongs to current turn
        if (item.kind === "assistant_text") {
          if ((item as any).showBranchSwitcher) turnBranchSwitcher = true;
          const _sa = (item as any).showActions;
          const _shouldShowActions = _sa !== undefined ? _sa : !item.isStreaming;
          if (_shouldShowActions) {
            // Every completed turn gets a copy button
            turnActions = true;
            // No retry button in sub-agent view
            if (!getState().subAgentView) {
              // Only show retry on the very last assistant message in the conversation
              if (allMsgs) {
                for (let mi = allMsgs.length - 1; mi >= 0; mi--) {
                  if (allMsgs[mi].role === "assistant") {
                    if (item.messageId === allMsgs[mi].id) turnRetry = true;
                    break;
                  }
                }
              } else {
                turnRetry = true;
              }
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
    this.ml.innerHTML = html;
    createLucideIcons();
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
    for (let i = 0; i < timeline.length; i++) {
      const item = timeline[i];
      if (item.kind === "thinking") {
        const el = this.ml.querySelector(`[data-id="${item.id}"]`) as HTMLElement | null;
        if (el) {
          const bodyEl = el.querySelector(".thought-body") as HTMLElement | null;
          if (bodyEl && bodyEl.textContent !== item.text) {
            bodyEl.textContent = item.text;
          }
          // Auto-expand based on setting (unless user manually collapsed).
          // Toggling auto_expand OFF collapses expanded strips so the toggle
          // takes effect in both directions.
          const shouldExpand = isEnabled(getState().settings.auto_expand);
          const userCollapsed = this.userCollapsedItems.has(item.id);
          if (shouldExpand && !userCollapsed && !el.classList.contains("expanded")) {
            el.classList.add("expanded");
            this.expandedItems.add(item.id);
          } else if (!shouldExpand && !userCollapsed && el.classList.contains("expanded")) {
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
      //    Mirrors the thinking-strip handling above so toggling auto_expand
      //    takes effect on already-rendered tool/agent cards without a full
      //    re-render (the subscribe re-render uses the incremental path).
      const expandTool = toolItem.tc.name === "agent";
      if (expandTool) {
        const shouldExpandTool = isEnabled(getState().settings.auto_expand);
        const userCollapsedTool = this.userCollapsedItems.has(toolItem.id);
        if (shouldExpandTool && !userCollapsedTool && !el.classList.contains("expanded")) {
          el.classList.add("expanded");
          this.expandedItems.add(toolItem.id);
        } else if (!shouldExpandTool && userCollapsedTool && el.classList.contains("expanded")) {
          el.classList.remove("expanded");
          this.expandedItems.delete(toolItem.id);
        }
      }

      // 5) Agent card sub-agent preview text.
      if (toolItem.tc.name === "agent") {
        const previewEl = el.querySelector(".agent-card-preview") as HTMLElement | null;
        if (previewEl && toolItem.tc.subAgentMessages) {
          let lastText = "";
          for (const m of toolItem.tc.subAgentMessages) {
            if (m.role !== "assistant") continue;
            if (m.content && m.content.trim()) lastText = m.content;
          }
          const preview = lastText ? lastText.replace(/\s+/g, " ").slice(0, 80) : "";
          const newPreview = preview + (lastText.length > 80 ? "…" : "");
          if (previewEl.textContent !== newPreview) {
            previewEl.textContent = newPreview;
          }
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
        this.renderForce();
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
    return `<span class="mode-chip mode-card"><i data-lucide="${icon}" class="lucide mode-card-icon"></i><span class="mode-card-label">${escapeHtml(label)}</span>${summary ? `<span class="mode-card-summary">· ${escapeHtml(summary)}</span>` : ""}</span>`;
  }

  private renderUserItem(item: Extract<TimelineItem, { kind: "user" }>): string {
    const isSubAgent = !!getState().subAgentView;
    const cmdMatch = item.content.match(/^\/(\w[\w-]*)(?:\s+(.*))?$/s);
    const isTerminal = item.mode?.startsWith("terminal:");
    const modeBadge = item.mode && !isTerminal ? (() => { const c = findSlashCommand(item.mode); const icon = c ? c.icon : "list-checks"; return `<span class="mode-chip" data-mode="${item.mode}"><i data-lucide="${icon}" class="chip-icon" style="width:12px;height:12px;"></i><span>${c ? c.title : item.mode}</span></span>`; })() : "";
    const fileCards = item.fileRefs?.map(f => {
      if (f.icon === "folder") return this.renderModeCard(f.icon, f.name, "folder");
      if (f.icon === "terminal") return this.renderModeCard(f.icon, f.name, `${f.size} line${f.size !== 1 ? "s" : ""}`);
      return this.renderModeCard(f.icon, f.name, fmtSize(f.size));
    }).join("") || "";
    const termCard = isTerminal ? this.renderModeCard("terminal", item.mode!.split(":")[1] || "Terminal", `${item.content.split("\n").length} lines`) : "";
    if (cmdMatch) {
      const cmdName = cmdMatch[1];
      const rest = cmdMatch[2] || "";
      const displayContent = rest
        ? escapeHtml(rest)
        : `<span class="user-cmd-noargs">${t("app.slashActivated")}</span>`;
      return `<div class="user-item" data-user-idx="${item.index}">
        <div class="user-bubble">
          <span class="user-cmd-badge">${escapeHtml(cmdName)}</span>
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
    // display/type/title/content; fall back to treating the raw result as HTML.
    let payload: { display?: string; title?: string; content?: string; type?: string; widget?: string; is_complete_html?: boolean } = {};
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
    const widget = (payload.widget as string) || (tc.params.widget as string) || "";
    const cardType = (payload.type as string) || (tc.params.type as string) || "html";
    const cardId = `tc-${tc.id}`;

    // Structured travel widgets are rendered directly as cards in the chat
    // DOM. They do NOT live inside the sandboxed HTML iframe used by base.
    if (cardType === "widget" && ["flight", "train", "ship"].includes(widget)) {
      let widgetHtml = "";
      try {
        const data = JSON.parse(content || "{}");
        widgetHtml = widget === "flight"
          ? renderFlightWidget(data)
          : widget === "train"
          ? renderTrainWidget(data)
          : renderShipWidget(data);
      } catch {
        widgetHtml = `<div class="encre-widget-card encre-widget-error">
          <div class="encre-widget-title">Invalid ${widget} data</div>
          <div class="encre-widget-subtitle">The model must provide a JSON object with the required fields.</div>
        </div>`;
      }
      return `<div class="info-card info-card--widget" id="${cardId}" data-info-type="widget" data-widget="${escapeHtml(widget)}" data-source="${escapeHtml(content)}">
        <div class="info-card-header">
          <div class="info-card-title-wrap">
            <i data-lucide="layout-dashboard" class="info-card-icon"></i>
            <span class="info-card-title">${escapeHtml(title || t("chat.toolInfo"))}</span>
          </div>
          <div class="info-card-actions">
            <button class="info-btn" onclick="window.__copyInfoSource('${cardId}')" data-tooltip="${t("chat.infoCopy")}">
              <i data-lucide="copy" class="info-btn-icon"></i>
            </button>
          </div>
        </div>
        <div class="info-card-body info-card-body--widget">${widgetHtml}</div>
      </div>`;
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

    // display='base' (default): sandbox the model's HTML/CSS/JS in an iframe.
    const trimmed = content.trim().toLowerCase();
    const isFullDoc = trimmed.startsWith("<!doctype") || trimmed.startsWith("<html");
    const doc = isFullDoc
      ? content
      : `<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><style>html,body{margin:0;padding:0;overflow:auto !important;}</style></head><body>${content}<script>(function(){function s(){var h=Math.max(document.body.scrollHeight,document.documentElement.scrollHeight);if(window.parent!==window){window.parent.postMessage({__encreInfoHeight:h,__encreInfoId:"${cardId}"},'*');}}if(document.readyState==='complete')s();else window.onload=s;})();</script></body></html>`;
    const srcdoc = escapeHtml(doc);
    const isCode = display === "code";
    const escapedSource = escapeHtml(content);
    const isCompleteHtml = payload.is_complete_html ?? isFullDoc;
    const fragmentBadge = isCompleteHtml ? "" : `<span class="info-card-fragment-badge">fragment</span>`;

    return `<div class="info-card" id="${cardId}" data-info-type="html" data-source="${escapeHtml(content)}">
      <div class="info-card-header">
        <div class="info-card-title-wrap">
          <i data-lucide="layout-dashboard" class="info-card-icon"></i>
          <span class="info-card-title">${escapeHtml(title || t("chat.toolInfo"))}</span>
          ${fragmentBadge}
        </div>
        <div class="info-card-actions">
          <button class="info-btn" data-action="toggle-view" data-mode="${isCode ? "render" : "code"}" onclick="window.__toggleInfoView('${cardId}')" data-tooltip="${isCode ? t("chat.infoRender") : t("chat.infoCode")}">
            <i data-lucide="${isCode ? "eye" : "code"}" class="info-btn-icon"></i>
          </button>
          <button class="info-btn" onclick="window.__copyInfoSource('${cardId}')" data-tooltip="${t("chat.infoCopy")}">
            <i data-lucide="copy" class="info-btn-icon"></i>
          </button>
        </div>
      </div>
      <div class="info-card-body">
        <iframe class="info-card-frame${isCode ? " hidden" : ""}" sandbox="allow-scripts" srcdoc="${srcdoc}" loading="lazy" onload="window.__resizeInfoFrame(this)"></iframe>
        <pre class="info-card-code${isCode ? "" : " hidden"}"><code>${escapedSource}</code></pre>
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
    const id = `tc-${tc.id}`;
    const rawAgentName = getAgentName(tc);
    const agentName = formatAgentLabel(rawAgentName);
    const statusHtml = _toolStatusHtml(tc.status);
    const isPlanSpec = tc.params.mode === "plan" || tc.params.mode === "spec";
    const agentIcon = isPlanSpec ? "list-checks" : "zap";
    // Inline summary keeps ONLY the preview (last assistant text) so the
    // card stays compact. Thinking/tool counts are intentionally hidden in
    // the parent — they live in the sub-agent view.
    const subMsgs = tc.subAgentMessages;
    let summaryHtml = "";
    if (subMsgs && subMsgs.length > 0) {
      let lastText = "";
      for (const m of subMsgs) {
        if (m.role !== "assistant") continue;
        if (m.content && m.content.trim()) lastText = m.content;
      }
      const preview = lastText ? lastText.replace(/\s+/g, " ").slice(0, 80) : "";
      summaryHtml = preview
        ? `<div class="agent-card-summary"><span class="agent-card-preview">${escapeHtml(preview)}${lastText.length > 80 ? "…" : ""}</span></div>`
        : "";
    }
    return `<div class="agent-card" data-id="${id}" onclick="window.__openSubAgentView('${tc.id}')">
      <i data-lucide="${agentIcon}" class="agent-card-icon"></i>
      <span class="agent-card-name">${escapeHtml(agentName)}</span>
      <span class="agent-card-status" data-status="${tc.status}">${statusHtml}</span>
      ${summaryHtml}
      <span class="agent-card-open">
        <i data-lucide="square-arrow-out-up-right" class="agent-card-open-icon"></i>
      </span>
    </div>`;
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
    return `<div class="turn-status-card status-error" id="${id}">
      <div class="status-header" onclick="window.__toggleStatusCard('${id}')">
        <svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        <span class="status-label">${t("chat.abortedError")}</span>
        ${item.errorCode ? `<span class="status-code-tag">${escapeHtml(item.errorCode)}</span>` : ""}
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
    const id = "spec-card";
    const expanded = this.expandedItems.has(id);
    const sectionsHtml = spec.sections.map(s => `
      <div class="spec-section">
        <div class="spec-section-title">${escapeHtml(s.title)}</div>
        <div class="spec-section-content">${escapeHtml(s.content)}</div>
      </div>
    `).join("");
    const feedbackHtml = spec.feedback ? `<div class="spec-feedback"><strong>Feedback:</strong> ${escapeHtml(spec.feedback)}</div>` : "";
    const reviewActions = isReview ? `
      <div class="spec-footer">
        <button class="spec-btn spec-btn-approve" data-spec-approve="${sessionId}">Approve</button>
        <button class="spec-btn spec-btn-reject" data-spec-reject="${sessionId}">Reject</button>
      </div>
    ` : isApproved ? `<div class="spec-footer"><span class="spec-approved-label"><i data-lucide="check-circle"></i> Approved</span></div>`
    : isRejected ? `<div class="spec-footer"><span class="spec-rejected-label"><i data-lucide="x-circle"></i> Rejected</span></div>`
    : "";
    return `<div class="strip-item${expanded ? " expanded" : ""}" data-id="${id}">
      <div class="strip" onmouseenter="window.__hoverOn(this)" onmouseleave="window.__hoverOff(this)">
        <span class="icon-wrap"><i data-lucide="file-text" class="semantic" style="color:var(--chip-accent,#8b5cf6)"></i><i data-lucide="chevron-down" class="arrow"></i></span>
        <span class="strip-name">${escapeHtml(spec.title)}</span>
        <span class="strip-summary">${status}</span>
      </div>
      <div class="strip-body-slot" data-has-body="1">
        <div class="strip-body spec-body">${sectionsHtml}${feedbackHtml}${reviewActions}</div>
      </div>
    </div>`;
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
  }

  private toggleItem(id: string, el: HTMLElement): void {
    if (this.expandedItems.has(id)) {
      this.expandedItems.delete(id);
      el.classList.remove("expanded");
      this.userCollapsedItems.add(id);
    } else {
      this.expandedItems.add(id);
      el.classList.add("expanded");
      this.userCollapsedItems.delete(id);
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



