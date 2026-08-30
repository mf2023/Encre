"use strict";
(() => {
  var __create = Object.create;
  var __defProp = Object.defineProperty;
  var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __getProtoOf = Object.getPrototypeOf;
  var __hasOwnProp = Object.prototype.hasOwnProperty;
  var __require = /* @__PURE__ */ ((x) => typeof require !== "undefined" ? require : typeof Proxy !== "undefined" ? new Proxy(x, {
    get: (a, b) => (typeof require !== "undefined" ? require : a)[b]
  }) : x)(function(x) {
    if (typeof require !== "undefined") return require.apply(this, arguments);
    throw Error('Dynamic require of "' + x + '" is not supported');
  });
  var __copyProps = (to, from, except, desc) => {
    if (from && typeof from === "object" || typeof from === "function") {
      for (let key of __getOwnPropNames(from))
        if (!__hasOwnProp.call(to, key) && key !== except)
          __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
    }
    return to;
  };
  var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
    // If the importer is in node compatibility mode or this is not an ESM
    // file that has been converted to a CommonJS file using a Babel-
    // compatible transform (i.e. "__esModule" has not been set), then set
    // "default" to the CommonJS "module.exports" for node compatibility.
    isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
    mod
  ));

  // src/chat.ts
  var import_state = __require("./state.js");
  var import_ws = __require("./ws.js");
  var import_stream = __require("./stream.js");
  var import_markdown_it = __toESM(__require("markdown-it"));
  var import_highlight = __toESM(__require("highlight.js"));
  var import_i18n = __require("./i18n.js");
  var import_dialog = __require("./dialog.js");
  var import_slash_commands = __require("./slash_commands.js");
  var import_ealoader = __require("./ealoader.js");
  var import_diff_render = __require("./diff_render.js");
  var import_media_viewer = __require("./media-viewer.js");
  var md = new import_markdown_it.default({
    html: true,
    linkify: true,
    typographer: true,
    breaks: true
  });
  md.renderer.rules.fence = (tokens, idx) => {
    const token = tokens[idx];
    const lang = token.info ? token.info.trim().split(/\s+/)[0] : "";
    let content = token.content;
    let highlighted = "";
    if (lang && import_highlight.default.getLanguage(lang)) {
      try {
        highlighted = import_highlight.default.highlight(content, { language: lang }).value;
      } catch {
        highlighted = escapeHtml(content);
      }
    } else {
      highlighted = escapeHtml(content);
    }
    const attr = lang ? ` class="hljs language-${lang}"` : ' class="hljs"';
    const langLabel = lang ? escapeHtml(lang) : (0, import_i18n.t)("general.code");
    const codeAttr = `data-code="${escapeHtml(content)}"`;
    return `<div class="code-block-wrapper">
    <div class="code-block-header">
      <span class="code-lang">${langLabel}</span>
      <button class="code-copy" ${codeAttr}>${(0, import_i18n.t)("chat.copy")}</button>
    </div>
    <pre><code${attr}>${highlighted}</code></pre>
  </div>
`;
  };
  md.renderer.rules.code_inline = (tokens, idx) => {
    const content = tokens[idx].content;
    return `<code class="inline-code">${escapeHtml(content)}</code>`;
  };
  function renderMarkdown(text) {
    if (!text) return "";
    const trimmed = text.replace(/\n+$/, "");
    const html = md.render(trimmed);
    return html.replace(/(?:<br\s*\/?>\s*)+$/, "").replace(/<p>\s*<\/p>\s*$/, "");
  }
  function escapeHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function isTerminalTool(name) {
    return name === "bash" || name === "bash_output" || name === "bash_kill" || name === "bash_list" || name === "shell" || name === "terminal" || name === "run_command" || name === "chat.terminal";
  }
  function isFileMutationTool(name) {
    if (name === "write" || name === "file_write" || name === "write_file" || name === "edit" || name === "file_edit" || name === "edit_file" || name === "delete_file") {
      return true;
    }
    return /(write|edit|delete)/i.test(name) && /file/i.test(name);
  }
  function isFileReadTool(name) {
    return name === "read" || name === "file_read";
  }
  var TERMINAL_TOOLS = /* @__PURE__ */ new Set([
    "bash",
    "bash_output",
    "bash_kill",
    "bash_list",
    "shell",
    "terminal",
    "run_command",
    "chat.terminal"
  ]);
  var FILE_MUTATION_TOOLS = /* @__PURE__ */ new Set([
    "write",
    "file_write",
    "edit",
    "file_edit",
    "delete_file",
    "apply_patch"
  ]);
  var FILE_READ_TOOLS = /* @__PURE__ */ new Set(["read", "file_read"]);
  function isToolItemTool(name) {
    return name === "skill" || name === "mcp" || name.startsWith("mcp__") || name === "memory" || name.startsWith("memory_") || name === "task" || name.startsWith("task_") || name === "image" || name === "spreadsheet" || name.startsWith("cron_") || name === "todo" || name === "find_tool" || name === "web_fetch" || name === "git" || name === "lsp" || name === "notebook" || name === "rest_client" || name === "browser" || name === "database" || name === "docker" || name === "pdf" || name === "deploy" || name === "apply_patch" || name === "computer" || name === "desktop";
  }
  function isHiddenTool(name) {
    if (name === "task" || name.startsWith("task_")) return true;
    if (name === "memory" || name.startsWith("memory_")) return true;
    if (name.startsWith("cron_")) return true;
    return name === "todo" || name === "find_tool" || name === "lsp";
  }
  function compactText(value, max = 88) {
    if (value === void 0 || value === null) return "";
    const text = typeof value === "string" ? value : JSON.stringify(value);
    const oneLine = text.replace(/\s+/g, " ").trim();
    return oneLine.length > max ? `${oneLine.slice(0, max - 3)}...` : oneLine;
  }
  function extractJsonSummary(result) {
    const trimmed = result.trim();
    if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return null;
    try {
      const parsed = JSON.parse(trimmed);
      if (Array.isArray(parsed)) {
        return `${parsed.length} item${parsed.length === 1 ? "" : "s"}`;
      }
      if (typeof parsed === "object" && parsed !== null) {
        const preferred = [
          "summary",
          "message",
          "content",
          "result",
          "output",
          "stdout",
          "stderr",
          "error",
          "status",
          "data",
          "results",
          "matches",
          "items",
          "files",
          "count",
          "total"
        ];
        for (const key of preferred) {
          if (!(key in parsed)) continue;
          const v = parsed[key];
          if (v === void 0 || v === null) continue;
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
    }
    return null;
  }
  function firstParam(tc, keys) {
    for (const key of keys) {
      const value = tc.params[key];
      if (typeof value === "string" && value.trim()) return value;
    }
    return "";
  }
  function getToolIcon(name, terminal) {
    if (isTerminalTool(name)) {
      return "terminal";
    }
    if (isFileMutationTool(name)) return "pencil-line";
    if (isFileReadTool(name)) return "eye";
    if (name === "web_search" || name === "web_fetch") return "globe";
    if (name === "search" || name === "grep") return "search";
    if (name === "codebase" || name.startsWith("codebase")) return "search";
    if (name === "find_tool") return "compass";
    if (name === "glob") return "folder-search";
    if (name === "memory_profile") return "user-circle";
    if (name === "memory" || name.startsWith("memory_")) return "database";
    if (name === "task" || name.startsWith("task_")) return "list-checks";
    if (name.startsWith("cron_")) return "clock-9";
    if (name === "skill") return "wand-2";
    if (name === "mcp" || name.startsWith("mcp__")) return "plug";
    if (name === "agent") return "zap";
    if (name === "swarm") return "users";
    if (name === "workflow") return "workflow";
    if (name === "browser") return "monitor";
    if (name === "computer" || name === "computer_use" || name === "vlm_computer_use" || name === "desktop") return "container";
    if (name === "docker") return "container";
    if (name === "ssh") return "terminal";
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
    if (name === "rest_client" || name === "cloud_storage") return "cloud";
    if (name === "deploy") return "rocket";
    if (name === "email") return "mail";
    if (name === "notify") return "bell";
    if (name === "file_api") return "file";
    if (name === "batch_api") return "layers";
    if (name === "fine_tuning_api") return "sliders-horizontal";
    if (name === "create_embeddings") return "boxes";
    if (name === "create_moderation") return "shield-check";
    if (name === "todo") return "check-circle-2";
    if (name === "plan") return "file-text";
    if (name === "question") return "help-circle";
    if (name === "compact") return "shrink";
    if (name === "info") return "layout-dashboard";
    return "wrench";
  }
  var TERMINAL_LABELS = {
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
    R: "R"
  };
  function formatToolName(name, terminal) {
    if (terminal && (name === "bash" || name === "shell" || name === "chat.terminal" || name === "run_command")) {
      return TERMINAL_LABELS[terminal] || terminal.charAt(0).toUpperCase() + terminal.slice(1);
    }
    const labels = {
      "chat.terminal": "Bash",
      bash: "Bash",
      bash_output: "Bash Output",
      bash_kill: "Bash",
      bash_list: "Bash",
      shell: "Shell",
      terminal: "Terminal",
      run_command: "Bash",
      web_search: "Web Search",
      web_fetch: "Web Fetch",
      find_tool: "Find Tool",
      read: "Read File",
      file_read: "Read File",
      write: "Write File",
      file_write: "Write File",
      edit: "Edit File",
      file_edit: "Edit File",
      apply_patch: "Apply Patch",
      mcp: "MCP",
      lsp: "LSP",
      git: "Git",
      memory_create: "Memory",
      memory_read: "Memory",
      memory_update: "Memory",
      memory_delete: "Memory",
      memory_search: "Memory",
      task_create: "Task",
      task_list: "Task",
      task_get: "Task",
      task_update: "Task",
      task_stop: "Task",
      task_output: "Task",
      cron_create: "Cron",
      cron_delete: "Cron",
      cron_list: "Cron",
      rest_client: "Rest Client",
      desktop: "Desktop",
      computer: "Computer",
      question: "Question",
      memory_profile: "Memory Profile",
      compact: "Compress",
      info: "Info Card"
    };
    if (labels[name]) return labels[name];
    if (name.startsWith("mcp__")) return "MCP";
    if (name === "agent") return "Agent";
    return name.replace(/_/g, " ").replace(/\b\w/g, (ch) => ch.toUpperCase());
  }
  function getToolSummary(tc) {
    if (tc.result) {
      if (TERMINAL_TOOLS.has(tc.name)) {
        const cmd = firstParam(tc, ["command", "cmd", "input", "shell_command", "script"]);
        return compactText(cmd, 88);
      }
      const jsonSummary = extractJsonSummary(tc.result);
      if (jsonSummary) return jsonSummary;
      if (tc.name === "web_search") return compactText(tc.result, 88);
      if (tc.name === "web_fetch") return compactText(tc.result, 88);
      if (tc.name === "search" || tc.name === "grep" || tc.name === "codebase") {
        const match = tc.result.match(/(\d+)\s*match/i);
        return match ? (0, import_i18n.t)("chat.toolMatches", { count: parseInt(match[1], 10) }) : compactText(tc.result, 88);
      }
      if (tc.name === "glob") {
        const count = tc.result.trim().split("\n").filter((l) => l.trim()).length;
        return (0, import_i18n.t)("chat.toolFiles", { count });
      }
      if (tc.name === "git") return compactText(tc.result, 88);
      if (tc.name === "find_tool") return (0, import_i18n.t)("chat.toolDiscoverTools");
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
      if (FILE_MUTATION_TOOLS.has(tc.name)) {
        return compactText(firstParam(tc, ["path", "file_path", "filename"]), 88);
      }
      return compactText(tc.result, 88);
    }
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
    if (tc.name === "find_tool") return (0, import_i18n.t)("chat.toolDiscoverTools");
    const keys = Object.keys(tc.params).filter((k) => k !== "id");
    if (keys.length > 0) {
      return compactText(tc.params[keys[0]], 88);
    }
    return "";
  }
  function getToolInlineSummary(tc) {
    if (tc.name === "find_tool") return (0, import_i18n.t)("chat.toolDiscoverTools");
    if (tc.name === "mcp" || tc.name.startsWith("mcp__")) {
      const mcpTool = firstParam(tc, ["tool", "name", "function"]);
      return compactText(mcpTool || (0, import_i18n.t)("general.selectToolCall"), 42);
    }
    if (tc.name === "memory" || tc.name.startsWith("memory_")) {
      const hint = firstParam(tc, ["query", "name", "path"]);
      return compactText(hint || (0, import_i18n.t)("general.memoryAction"), 42);
    }
    if (tc.name === "task" || tc.name.startsWith("task_")) {
      const hint = firstParam(tc, ["id", "title", "task_id"]);
      return compactText(hint || (0, import_i18n.t)("general.taskAction"), 42);
    }
    if (tc.name.startsWith("cron_")) {
      const hint = firstParam(tc, ["schedule", "expression", "name"]);
      return compactText(hint || (0, import_i18n.t)("general.cronAction"), 42);
    }
    const fromParams = firstParam(tc, ["query", "path", "file_path", "url", "name"]);
    return compactText(fromParams || getToolSummary(tc), 42);
  }
  function getAgentName(tc) {
    const configuredName = tc.params.agent_name || tc.params.name;
    return configuredName && configuredName.trim() || "Agent";
  }
  function formatAgentLabel(rawName) {
    const name = (rawName || "").trim();
    if (!name) return "Agent";
    return name.charAt(0).toUpperCase() + name.slice(1);
  }
  function selectSubAgentTaskMessages(msgs, taskIndex) {
    if (taskIndex === void 0) return msgs;
    const groups = /* @__PURE__ */ new Map();
    let fallbackIndex = 0;
    let current = null;
    for (const m of msgs) {
      if (m.mode === "task_divider") {
        const index = Number.isInteger(m.taskIndex) ? m.taskIndex : fallbackIndex;
        fallbackIndex = Math.max(fallbackIndex, index + 1);
        current = [];
        groups.set(index, current);
      } else if (current) {
        current.push(m);
      }
    }
    return groups.get(taskIndex) ?? [];
  }
  function buildSubAgentTimeline(msgs, isRunning) {
    const clean = msgs.filter((m) => m.mode !== "task_divider");
    const timeline = buildTimeline(clean);
    const subView = (0, import_state.getState)().subAgentView;
    const subRunning = isRunning ?? !!(subView && (subView.status === "running" || subView.status === "pending"));
    if (subRunning) {
      for (const item of timeline) {
        item.showActions = false;
      }
    }
    return timeline;
  }
  function getToolBodyText(tc) {
    if (!tc.result) return "";
    if (tc.name === "web_search") return renderWebResults(tc.result);
    if (tc.name === "web_fetch") return renderWebFetchedContent(tc.result);
    if (isFileMutationTool(tc.name) && tc.name !== "delete_file") {
      return renderDiff(tc.result);
    }
    if (TERMINAL_TOOLS.has(tc.name)) {
      try {
        const json = JSON.parse(tc.result);
        const parts = [];
        if (json.stdout) parts.push(json.stdout);
        if (json.stderr) parts.push(json.stderr);
        const text = parts.join("\n");
        if (!text.trim()) return `<pre style="font-size:11.5px;color:var(--text-muted);margin:0;padding:0">${escapeHtml("(no output)")}</pre>`;
        const lines2 = text.split("\n");
        const maxLines2 = 20;
        const shown2 = lines2.slice(0, maxLines2);
        const hasMore2 = lines2.length > maxLines2;
        let html2 = `<pre style="font-size:11.5px;color:var(--text-secondary);white-space:pre-wrap;margin:0;line-height:1.5">${escapeHtml(shown2.join("\n"))}`;
        if (hasMore2) {
          html2 += `
<span style="color:var(--text-muted)">${(0, import_i18n.t)("chat.moreLines", { count: lines2.length - maxLines2 })}</span>`;
        }
        html2 += "</pre>";
        return html2;
      } catch {
      }
    }
    const lines = tc.result.trim().split("\n").filter((l) => l.trim());
    const maxLines = 8;
    const shown = lines.slice(0, maxLines);
    const hasMore = lines.length > maxLines;
    let html = `<pre style="font-size:11.5px;color:var(--text-secondary);white-space:pre-wrap;margin:0;line-height:1.5">${escapeHtml(shown.join("\n"))}`;
    if (hasMore) {
      html += `
<span style="color:var(--text-muted)">${(0, import_i18n.t)("chat.moreLines", { count: lines.length - maxLines })}</span>`;
    }
    html += "</pre>";
    return html;
  }
  function renderDiff(result) {
    let fileName = "";
    const firstLine = result.split("\n")[0] || "";
    const pathMatch = firstLine.match(/(?:to|to:) (.+?)\.?\s*$/);
    if (pathMatch) fileName = pathMatch[1].trim();
    const diffMatch = result.match(/```diff\n([\s\S]*?)```/);
    if (!diffMatch) return "";
    return (0, import_diff_render.renderDiffHtml)(diffMatch[1].trim(), fileName);
  }
  function renderWebResults(result) {
    const lines = result.trim().split("\n");
    const hasMarkdownLinks = /\[.+?\]\(https?:\/\/.+?\)/.test(result);
    let html = '<div class="web-list">';
    let num = 1;
    if (hasMarkdownLinks) {
      const entries = splitMarkdownEntries(result);
      if (entries.length > 0) {
        for (const entry of entries) {
          html += renderWebEntry(num, entry.title, entry.url, entry.snippet);
          num++;
        }
      }
    } else {
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        const parts = trimmed.split(/\s{2,}-\s{2,}/);
        if (parts.length >= 2) {
          const title = parts[0].trim();
          const rest = parts.slice(1).join(" - ").trim();
          const urlMatch = rest.match(/^(https?:\/\/\S+)(?:\s+(.+))?$/);
          const url = urlMatch ? urlMatch[1] : "";
          const snip = urlMatch && urlMatch[2] ? urlMatch[2] : url ? "" : rest;
          html += renderWebEntry(num, title, url, snip);
          num++;
        } else {
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
      const cleaned = result.replace(/\n{3,}/g, "\n\n").trim();
      html += `<div class="web-item" style="white-space:pre-wrap;line-height:1.5;font-size:11.5px">${escapeHtml(cleaned)}</div>`;
    }
    html += "</div>";
    return html;
  }
  function splitMarkdownEntries(text) {
    const entries = [];
    const pattern = /(?:^\d+\.\s*)?\[(.+?)\]\((https?:\/\/[^)]+)\)\s*([\s\S]*?)(?=(?:^\d+\.\s*)?\[.+?\]\(https?:\/\/|$)/gm;
    let match;
    while ((match = pattern.exec(text)) !== null) {
      entries.push({
        title: match[1].trim(),
        url: match[2].trim(),
        snippet: match[3].trim().replace(/\n+/g, " ").slice(0, 300)
      });
    }
    return entries;
  }
  function renderWebEntry(num, title, url, snippet) {
    const displayTitle = title || url || "(untitled)";
    const titleHtml = url ? `<a class="web-title" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(displayTitle)}</a>` : `<span class="web-title">${escapeHtml(displayTitle)}</span>`;
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
  function renderWebFetchedContent(result) {
    const lines = result.split("\n").map((l) => l.trim()).filter((l) => l);
    const deduped = [];
    for (const line of lines) {
      const prev = deduped[deduped.length - 1];
      if (prev && _lineSimilarity(prev, line) > 0.85) continue;
      if (line.length < 3 && deduped.length > 0) continue;
      deduped.push(line);
    }
    const maxLines = 60;
    const shown = deduped.slice(0, maxLines);
    const more = deduped.length > maxLines ? `
<span style="color:var(--text-muted)">\u2026 ${deduped.length - maxLines} more lines</span>` : "";
    return `<pre class="web-fetched-content">${escapeHtml(shown.join("\n"))}${more}</pre>`;
  }
  function _lineSimilarity(a, b) {
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
  function _toolStatusHtml(status) {
    if (status === "running") return `<span class="tool-status-dot running"></span></span>`;
    return "";
  }
  function createLucideIcons(root) {
    if (typeof window.lucide !== "undefined") {
      window.lucide.createIcons(root ? { root } : void 0);
    }
  }
  var _openedHtmlCards = /* @__PURE__ */ new Set();
  function saveVideoPlayback() {
    const states = [];
    document.querySelectorAll(".info-card--media video").forEach((v) => {
      const card = v.closest(".info-card--media");
      if (card?.id) states.push({ id: card.id, t: v.currentTime, p: v.paused });
    });
    return states;
  }
  function restoreVideoPlayback(states) {
    if (states.length === 0) return;
    requestAnimationFrame(() => {
      states.forEach((s) => {
        const card = document.getElementById(s.id);
        if (!card) return;
        const video = card.querySelector("video");
        if (!video) return;
        video.currentTime = s.t;
        if (!s.p) {
          const play = () => video.play().catch(() => {
          });
          if (video.readyState >= 2) play();
          else video.addEventListener("canplay", play, { once: true });
        }
      });
    });
  }
  function flashCopyButton(btn) {
    const origIcon = btn.getAttribute("data-original-icon");
    const original = origIcon || "copy";
    if (!origIcon) btn.setAttribute("data-original-icon", original);
    btn.classList.add("copying");
    btn.style.transition = "opacity 0.12s ease";
    btn.style.opacity = "0";
    setTimeout(() => {
      const i = btn.querySelector("[data-lucide]");
      if (i) i.setAttribute("data-lucide", "check");
      createLucideIcons(btn);
      btn.style.opacity = "1";
    }, 120);
    setTimeout(() => {
      btn.style.opacity = "0";
      setTimeout(() => {
        const i = btn.querySelector("[data-lucide]");
        if (i) i.setAttribute("data-lucide", original);
        createLucideIcons(btn);
        btn.style.opacity = "1";
        setTimeout(() => {
          btn.style.transition = "";
          btn.classList.remove("copying");
        }, 120);
      }, 120);
    }, 2e3);
  }
  function buildStatusCards(msg) {
    const cards = [];
    if (msg.errorMessage) {
      cards.push({ kind: "error_card", id: `ec-${msg.id}`, messageId: msg.id, errorMessage: msg.errorMessage, errorCode: msg.errorCode || "", errorCategory: msg.errorCategory || "" });
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
  function buildTimeline(msgs) {
    const items = [];
    let userIndex = 0;
    let pendingStatusCards = [];
    const st = (0, import_state.getState)();
    if (st.branches.length > 1) {
      console.log("[buildTimeline] branches=%d active=%s msgs=%d", st.branches.length, st.activeBranchId?.slice(-8), msgs.length);
    }
    for (let ci = 0; ci < st.compactStartingEvents.length; ci++) {
      items.push({ kind: "compact_starting", id: `compact-starting-${ci}` });
    }
    for (let ci = 0; ci < st.compactEvents.length; ci++) {
      items.push({ kind: "compact", id: `compact-${ci}` });
    }
    for (let si = 0; si < (st.systemMessages || []).length; si++) {
      const sm = st.systemMessages[si];
      items.push({ kind: "system_message", id: `sysmsg-${si}`, content: sm.content, kindTag: sm.kind });
    }
    if (st.workflowState && st.workflowState.active) {
      items.push({ kind: "workflow", id: `wf-${st.workflowState.workflowId}` });
    }
    let forkMsgIdx = -1;
    if (st.branches.length > 1) {
      const cur = st.branches.find((b) => b.id === st.activeBranchId);
      const fpId = cur?.fork_point_message_id;
      if (fpId) {
        forkMsgIdx = msgs.findIndex((m) => m.serverId === fpId);
        if (forkMsgIdx < 0) {
          for (let i = msgs.length - 1; i >= 0; i--) {
            if (msgs[i].role === "user") {
              forkMsgIdx = i;
              break;
            }
          }
        }
      } else {
        for (const b of st.branches) {
          if (b.parent_branch_id === st.activeBranchId && b.fork_point_message_id) {
            const idx = msgs.findIndex((m) => m.serverId === b.fork_point_message_id);
            if (idx >= 0) {
              forkMsgIdx = idx;
              break;
            }
          }
        }
      }
    }
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
          fileRefs: msg.fileRefs
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
                  messageId: msg.id
                });
              }
              textSegIndex++;
            } else if (seg.kind === "tool") {
              const tc = seg.toolId ? msg.toolCalls.find((t2) => (0, import_state.toolCallMatchesId)(t2, seg.toolId)) : void 0;
              if (tc && tc.name && !isHiddenTool(tc.name)) {
                items.push({ kind: "tool", id: `tc-${tc.id}`, tc, messageId: msg.id });
              }
            }
          }
        } else {
          if (msg.thinking) {
            items.push({ kind: "thinking", id: `th-${msg.id}`, text: msg.thinking, elapsed: msg.thinkingElapsed, messageId: msg.id });
          }
          for (const tc of msg.toolCalls) {
            if (!tc.name || isHiddenTool(tc.name)) continue;
            items.push({ kind: "tool", id: `tc-${tc.id}`, tc, messageId: msg.id });
          }
          if (msg.content.trim().length > 0 || msg.isStreaming) {
            items.push({ kind: "assistant_text", id: `a-${msg.id}`, content: msg.content, isStreaming: msg.isStreaming, hasError: msg.hasError, messageId: msg.id });
          }
        }
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
        if (isLastAssistantInGroup && assistantStartIdx < items.length) {
          const lastItem = items[items.length - 1];
          if (!msg.isStreaming && !st.running) {
            lastItem.showActions = true;
          }
        }
        if (i === firstAssistantAfterForkIdx && assistantStartIdx < items.length) {
          const lastItem = items[items.length - 1];
          lastItem.showBranchSwitcher = true;
        }
        if (i === msgs.length - 1 || i + 1 < msgs.length && msgs[i + 1].role !== "assistant") {
          if (st.planReview) {
            items.push({ kind: "plan_card", id: `plan-card-${st.planReview.review_id}`, review: st.planReview });
          }
          if (st.spec) {
            items.push({ kind: "spec_card", id: `spec-card-${(0, import_state.getState)().sessionId}`, spec: st.spec });
          }
        }
      }
    }
    if (pendingStatusCards.length > 0) {
      items.push(...pendingStatusCards);
      pendingStatusCards = [];
    }
    if (items.every((it) => it.kind !== "assistant_text" && it.kind !== "ai_header" && it.kind !== "thinking" && it.kind !== "tool")) {
      if (st.planReview) {
        items.push({ kind: "plan_card", id: `plan-card-${st.planReview.review_id}`, review: st.planReview });
      }
      if (st.spec) {
        items.push({ kind: "spec_card", id: `spec-card-${(0, import_state.getState)().sessionId}`, spec: st.spec });
      }
    }
    return items;
  }
  function _fmtTokens(n) {
    if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
    return String(n);
  }
  function fmtSize(bytes) {
    if (!bytes || bytes < 0) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  function buildRenderKey(timeline) {
    return JSON.stringify(timeline.map((i) => {
      if (i.kind === "user") return { k: "u", c: i.content };
      if (i.kind === "ai_header") return { k: "ah", t: i.time };
      if (i.kind === "thinking") return { k: "th", id: i.id };
      if (i.kind === "tool") {
        const taskDividers = i.tc.subAgentMessages ? i.tc.subAgentMessages.filter((message) => message.mode === "task_divider").map((message, index) => ({
          index: message.taskIndex ?? index,
          name: message.taskName || "",
          status: message.taskStatus || ""
        })) : [];
        return { k: "tc", id: i.id, n: i.tc.name, r: i.tc.result ? 1 : 0, d: taskDividers, sa: i.showActions ? 1 : 0, sb: i.showBranchSwitcher ? 1 : 0 };
      }
      if (i.kind === "compact") return { k: "cp" };
      if (i.kind === "workflow") {
        const wf = (0, import_state.getState)().workflowState;
        if (wf) return { k: "wf", id: wf.workflowId, n: wf.tasks.length, a: wf.active ? 1 : 0 };
        return { k: "wf" };
      }
      if (i.kind === "assistant_text") {
        return { k: "a", id: i.id, st: i.isStreaming ? 1 : 0, sa: i.showActions ? 1 : 0, sb: i.showBranchSwitcher ? 1 : 0 };
      }
      if (i.kind === "error_card") return { k: "ec", id: i.id, sa: i.showActions ? 1 : 0, sb: i.showBranchSwitcher ? 1 : 0 };
      if (i.kind === "warning_card") return { k: "wc", id: i.id, sa: i.showActions ? 1 : 0, sb: i.showBranchSwitcher ? 1 : 0 };
      if (i.kind === "inline_success") return { k: "is", id: i.id, sa: i.showActions ? 1 : 0, sb: i.showBranchSwitcher ? 1 : 0 };
      if (i.kind === "inline_cancelled") return { k: "ic", id: i.id, sa: i.showActions ? 1 : 0, sb: i.showBranchSwitcher ? 1 : 0 };
      return { k: "" };
    }));
  }
  var STATUS_QUOTES = [
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
    { icon: "flask-conical", textKey: "statusQuoteFlask" }
  ];
  function pickRandomQuote() {
    return STATUS_QUOTES[Math.floor(Math.random() * STATUS_QUOTES.length)];
  }
  var Chat = class {
    /**
     * Constructor: resolves DOM nodes and wires the scroll indicator + bridges.
     */
    constructor() {
      this.userScrolledUp = false;
      this.renderedKey = "";
      this.expandedItems = /* @__PURE__ */ new Set();
      this.userCollapsedItems = /* @__PURE__ */ new Set();
      this.userExpandedItems = /* @__PURE__ */ new Set();
      this.lastAssistantMsgId = "";
      this._lastRunning = false;
      this._inRenderForce = false;
      this.rafPending = false;
      this.liveLoader = null;
      this._actionMenu = null;
      this._actionMenuBtn = null;
      this._actionMenuClose = null;
      this._actionMenuTurnLeave = null;
      this._actionMenuEnter = null;
      this._actionMenuLeave = null;
      this._actionMenuCloseTimer = null;
      /** Map of file keys to markdown content for plan file rows (avoids attribute length limits). */
      this._planFileLookup = /* @__PURE__ */ new Map();
      /** Callback invoked when the user clicks "View Changes" on an artifact file. */
      this.onViewChanges = null;
      this._parallelRenderTimer = null;
      this._pendingParallelRender = false;
      /** True while building marker-pipeline HTML for a sub-agent transcript
       *  (normal-chat sub-agent view, parallel tiles, or the automation detail
       *  panel).  renderUserItem reads this so user bubbles render their full
       *  content and hide rollback/delete actions even when the global
       *  `getState().subAgentView` is not set (the automation detail never sets
       *  it, because the automation panel is an independent view). */
      this._subAgentRender = false;
      this._currentQuote = null;
      this.ml = document.getElementById("message-list");
      this.welcomeScreen = document.getElementById("welcome-screen");
      this.container = document.getElementById("chat-container");
      this.statusBar = document.getElementById("chat-status-bar");
      this.scrollIndicator = new ChatScrollIndicator(this.container);
      const scrollBtn = document.createElement("button");
      scrollBtn.id = "chat-scroll-bottom-btn";
      scrollBtn.className = "chat-scroll-bottom-btn hidden";
      scrollBtn.setAttribute("aria-label", "Scroll to bottom");
      scrollBtn.innerHTML = '<i data-lucide="chevron-down" style="width:18px;height:18px"></i>';
      this.container.parentElement?.appendChild(scrollBtn);
      scrollBtn.addEventListener("click", () => {
        this.container.scrollTo({ top: this.container.scrollHeight, behavior: "smooth" });
      });
      const w = window;
      w.__openSubAgentView = (toolCallId, taskIndex) => {
        const st = (0, import_state.getState)();
        const MAX_DEPTH = 4;
        if (st.subAgentBreadcrumb.length >= MAX_DEPTH) {
          (0, import_state.showToast)?.("Sub-agent", `Max depth (${MAX_DEPTH}) reached`);
          return;
        }
        for (const msg of st.messages) {
          for (const tc of msg.toolCalls) {
            if ((0, import_state.toolCallMatchesId)(tc, toolCallId)) {
              w.__subAgentAutoOpenDismissed = false;
              const parentToolCallId = st.subAgentView ? st.subAgentView.id : null;
              const agentName = getAgentName(tc);
              const taskDividers = this._agentTaskDividers(tc);
              const selectedTask = taskIndex === void 0 ? void 0 : taskDividers.find((task) => task.index === taskIndex);
              const taskName = selectedTask ? selectedTask.name : "";
              const crumbName = taskName ? `${agentName} \xB7 ${taskName}` : agentName;
              const existingIdx = st.subAgentBreadcrumb.findIndex(
                (c) => c.toolCallId === toolCallId
              );
              if (existingIdx >= 0) {
                (0, import_state.resetToSubAgentBreadcrumbIndex)(existingIdx);
              } else {
                (0, import_state.pushSubAgentBreadcrumb)({
                  sessionId: st.sessionId,
                  name: crumbName,
                  toolCallId,
                  parentToolCallId
                });
              }
              if (tc.subAgentMessages && tc.subAgentMessages.length > 0) {
                const viewTc = { ...tc, taskIndex };
                w.__activeSubAgentSessionId = void 0;
                (0, import_state.setSubAgentView)(viewTc);
                this.render();
              } else if (tc.subAgentSessionId) {
                const requestId = crypto.randomUUID();
                w.__pendingSubAgentView = {
                  toolCall: tc,
                  sessionId: tc.subAgentSessionId,
                  requestId
                };
                (0, import_stream.setRequestedSessionId)(tc.subAgentSessionId, requestId);
                (0, import_ws.send)({ type: "resume", session_id: tc.subAgentSessionId, request_id: requestId });
              } else {
                (0, import_state.setSubAgentView)(tc);
                this.render();
              }
              return;
            }
          }
        }
      };
      w.__closeSubAgentView = () => {
        const crumb = (0, import_state.popSubAgentBreadcrumb)();
        w.__pendingSubAgentView = void 0;
        w.__activeSubAgentSessionId = void 0;
        if (!crumb) w.__subAgentAutoOpenDismissed = true;
        (0, import_state.setSubAgentView)(null);
        if (crumb) {
          const requestId = crypto.randomUUID();
          (0, import_stream.setRequestedSessionId)(crumb.sessionId, requestId);
          (0, import_ws.send)({ type: "resume", session_id: crumb.sessionId, request_id: requestId });
        } else {
          this.renderedKey = "";
          this.ml.innerHTML = "";
          requestAnimationFrame(() => this.render());
        }
      };
      w.__goToRootView = () => {
        const st = (0, import_state.getState)();
        w.__activeSubAgentSessionId = void 0;
        w.__pendingSubAgentView = void 0;
        w.__subAgentAutoOpenDismissed = true;
        if (st.subAgentBreadcrumb.length === 0) {
          (0, import_state.setSubAgentView)(null);
          this.render();
          return;
        }
        const rootSessionId = st.subAgentBreadcrumb[0].sessionId;
        (0, import_state.clearSubAgentBreadcrumb)();
        (0, import_state.setSubAgentView)(null);
        if (rootSessionId !== st.sessionId) {
          const requestId = crypto.randomUUID();
          (0, import_stream.setRequestedSessionId)(rootSessionId, requestId);
          (0, import_ws.send)({ type: "resume", session_id: rootSessionId, request_id: requestId });
        }
        this.renderedKey = "";
        this.ml.innerHTML = "";
        this.render();
      };
      w.__navigateToBreadcrumb = (index) => {
        const st = (0, import_state.getState)();
        const target = (0, import_state.resetToSubAgentBreadcrumbIndex)(index);
        if (!target) return;
        const stNow = (0, import_state.getState)();
        for (const msg of stNow.messages) {
          for (const tc of msg.toolCalls) {
            if ((0, import_state.toolCallMatchesId)(tc, target.toolCallId)) {
              (0, import_state.setSubAgentView)(tc);
              this.render();
              return;
            }
          }
        }
        (0, import_state.setSubAgentView)(null);
        const requestId = crypto.randomUUID();
        (0, import_stream.setRequestedSessionId)(target.sessionId, requestId);
        (0, import_ws.send)({ type: "resume", session_id: target.sessionId, request_id: requestId });
      };
      w.__answerQuestion = (event, btn, cardId) => {
        event.stopPropagation();
        const card = document.getElementById(cardId);
        if (!card) return;
        const input = card.querySelector(".q-input");
        let answer = input ? input.value.trim() : "";
        if (!answer) {
          const selected = card.querySelector(".q-option-card.selected");
          if (selected) answer = selected.getAttribute("data-value") || "";
        }
        if (answer) {
          (0, import_ws.send)({ type: "respond_question", tool_call_id: cardId.replace("tc-", ""), answers: answer });
        }
      };
      w.__hoverOn = (el) => {
        const wrap = el.querySelector(".icon-wrap");
        if (wrap) wrap.classList.add("hover");
      };
      w.__hoverOff = (el) => {
        const wrap = el.querySelector(".icon-wrap");
        if (wrap) wrap.classList.remove("hover");
      };
      w.__toggleStatusCard = (id) => {
        const el = document.getElementById(id);
        if (el) el.classList.toggle("expanded");
      };
      w.__viewChanges = (el) => {
        const card = el.closest(".file-card");
        if (card) {
          const path = card.getAttribute("data-path") || "";
          if (path && this.onViewChanges) this.onViewChanges(path);
        }
      };
      const resizeInfoFrame = (iframe) => {
        try {
          const doc = iframe.contentDocument;
          if (!doc) return;
          const height = Math.max(doc.body?.scrollHeight || 0, doc.documentElement?.scrollHeight || 0);
          if (height > 0) iframe.style.height = `${height}px`;
        } catch {
        }
      };
      window.addEventListener("message", (event) => {
        const data = event.data;
        if (!data || typeof data.__encreInfoHeight !== "number" || !data.__encreInfoId) return;
        const iframe = document.querySelector(`#${data.__encreInfoId} .info-card-frame`);
        if (iframe) iframe.style.height = `${data.__encreInfoHeight}px`;
      });
      w.__resizeInfoFrame = resizeInfoFrame;
      w.__toggleInfoView = (cardId) => {
        const card = document.getElementById(cardId);
        if (!card) return;
        const frame = card.querySelector(".info-card-frame");
        const codeBlock = card.querySelector(".info-card-code");
        const btn = card.querySelector(".info-card-actions .info-btn[data-action='toggle-view']");
        if (!frame || !codeBlock) return;
        const showingCode = !codeBlock.classList.contains("hidden");
        const nextMode = showingCode ? "render" : "code";
        frame.classList.toggle("hidden", nextMode !== "render");
        codeBlock.classList.toggle("hidden", nextMode !== "code");
        if (btn) {
          const nextIcon = nextMode === "code" ? "code" : "eye";
          btn.dataset.mode = nextMode;
          btn.dataset.tooltip = (0, import_i18n.t)(nextMode === "code" ? "chat.infoCode" : "chat.infoRender");
          btn.innerHTML = `<i data-lucide="${nextIcon}" class="info-btn-icon"></i>`;
          if (typeof window.lucide !== "undefined") {
            window.lucide.createIcons({ root: btn });
          }
        }
      };
      w.__copyInfoSource = async (cardId) => {
        const card = document.getElementById(cardId);
        if (!card) return;
        const source = card.getAttribute("data-source") || "";
        try {
          await navigator.clipboard.writeText(source);
        } catch {
          (0, import_state.showToast)((0, import_i18n.t)("chat.infoCopyFailed"), "", "error", "Chat");
        }
      };
      w.__initInfoCardMedia = (cardId) => {
        const card = document.getElementById(cardId);
        if (!card) return;
        card.querySelectorAll(":scope > [data-type]").forEach((el) => {
          const type = el.getAttribute("data-type") || "image";
          const src = el.getAttribute("data-src") || "";
          if (src) new import_media_viewer.MediaViewer(el, { type, src, controls: type === "video" });
        });
      };
      w.__initMediaCards = () => {
        document.querySelectorAll(".info-card--media").forEach((card) => {
          const id = card.id;
          if (id) w.__initInfoCardMedia(id);
        });
      };
      w.__openInfoHtmlCard = async (cardId) => {
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
        document.querySelectorAll(".strip-item[data-source]").forEach((card) => {
          const id = card.id;
          if (!id || _openedHtmlCards.has(id)) return;
          _openedHtmlCards.add(id);
          w.__openInfoHtmlCard(id);
        });
      };
      window.__initMediaCards = w.__initMediaCards;
      window.__initInfoCardMedia = w.__initInfoCardMedia;
      window.__openInfoHtmlCards = w.__openInfoHtmlCards;
      this.container.addEventListener("scroll", () => this.syncScrollButton());
      const ro = new ResizeObserver(() => this.syncScrollButton());
      ro.observe(this.container);
      this.ml.addEventListener("click", (e) => this.handleDelegateClick(e));
      let _lastSid = (0, import_state.getState)().sessionId;
      let _lastMsgLen = (0, import_state.getState)().messages.length;
      let _lastExpand = (0, import_state.isEnabled)((0, import_state.getState)().settings.auto_expand);
      (0, import_state.subscribe)(() => {
        const st = (0, import_state.getState)();
        const sid = st.sessionId;
        const msgs = st.messages;
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
          if (st.subAgentView || st.subAgentBreadcrumb.length > 0) {
            (0, import_state.setSubAgentView)(null);
            (0, import_state.clearSubAgentBreadcrumb)();
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
            (0, import_state.setSubAgentView)(null);
            (0, import_state.clearSubAgentBreadcrumb)();
          }
          this.ml.innerHTML = "";
          this.syncScrollButton();
          return;
        }
        if (msgs.length > 0 && _lastMsgLen === 0) {
          _lastMsgLen = msgs.length;
          this.renderedKey = "";
          this.render();
          return;
        }
        const curExpand = (0, import_state.isEnabled)(st.settings.auto_expand);
        if (curExpand !== _lastExpand) {
          _lastExpand = curExpand;
          this.requestRender();
          return;
        }
        _lastMsgLen = msgs.length;
        this.requestRender();
      });
      (0, import_i18n.onLocaleChange)(() => this.render());
    }
    requestRender() {
      if (this.rafPending) return;
      this.rafPending = true;
      requestAnimationFrame(() => {
        this.rafPending = false;
        this.render();
      });
    }
    renderForce() {
      this.renderedKey = "";
      this._inRenderForce = true;
      try {
        const st = (0, import_state.getState)();
        const subTc = st.subAgentView;
        const isSubAgentStreaming = !!subTc && (subTc.status === "running" || subTc.status === "pending");
        if (!isSubAgentStreaming) {
          this.render();
          return;
        }
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
    render() {
      if (this.liveLoader) {
        this.liveLoader.destroy();
        this.liveLoader = null;
      }
      const state = (0, import_state.getState)();
      if (!state.subAgentView && state.subAgentBreadcrumb.length > 0) {
        const crumb = state.subAgentBreadcrumb[state.subAgentBreadcrumb.length - 1];
        if (crumb.sessionId === state.sessionId) {
          for (const msg of state.messages) {
            for (const tc of msg.toolCalls) {
              if ((0, import_state.toolCallMatchesId)(tc, crumb.toolCallId)) {
                (0, import_state.setSubAgentView)(tc);
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
        const sessionBacked = window.__activeSubAgentSessionId === state.sessionId;
        let subMsgs;
        if (sessionBacked) {
          subMsgs = state.messages.length > 0 ? state.messages : subTc.subAgentMessages ?? [];
        } else {
          subMsgs = subTc.subAgentMessages?.length ? subTc.subAgentMessages : [];
        }
        const selectedMsgs = selectSubAgentTaskMessages(subMsgs, subTc.taskIndex);
        const hasInlineData = selectedMsgs.length > 0;
        const isStreaming = sessionBacked ? state.running : subTc.status === "running" || subTc.status === "pending";
        this.renderedKey = "__subagent__";
        if (hasInlineData) {
          const timeline2 = buildSubAgentTimeline(selectedMsgs, isStreaming);
          this.fullRender(timeline2, selectedMsgs);
        } else if (isStreaming) {
          this.ml.innerHTML = "";
          this.liveLoader = new import_ealoader.EALoader(this.ml, { maxWidth: "50px" });
        } else if (subTc.isError) {
          const rawResult = typeof subTc.result === "string" ? subTc.result.trim() : "";
          let errorCode = String(rawResult || "AUTOMATION_EXECUTION_FAILED");
          if (rawResult === "-1") {
            errorCode = (0, import_i18n.t)("automation.errorBashTimeout") || "Command timed out (-1)";
          } else if (rawResult === "-2") {
            errorCode = (0, import_i18n.t)("automation.errorDockerMissing") || "Sandbox unavailable: Docker not installed (-2)";
          } else if (rawResult.startsWith("Error:") && rawResult.length > 6) {
            errorCode = rawResult.length > 500 ? rawResult.slice(0, 500) + "\u2026" : rawResult;
          }
          this.ml.innerHTML = `<div class="si-panel-empty" style="flex:1;gap:14px;">
          <i data-lucide="ban" class="lucide"></i>
          <div class="si-panel-empty-title">${(0, import_i18n.t)("automation.executionFailed") || "Automation execution error"}</div>
          <div class="si-panel-empty-sub" style="word-break:break-word;">${escapeHtml(errorCode)}</div>
        </div>`;
        } else {
          const resultText = typeof subTc.result === "string" ? subTc.result.trim() : "";
          if (resultText) {
            this.ml.innerHTML = `<div class="sub-agent-result-fallback">${renderMarkdown(resultText)}</div>`;
          } else {
            this.ml.innerHTML = `<div class="si-empty-center"><i data-lucide="bot" class="lucide"></i><span class="si-empty-title">${(0, import_i18n.t)("chat.noSubAgentOutput")}</span></div>`;
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
        this.syncScrollButton();
        return;
      }
      const timeline = buildTimeline(msgs);
      const key = buildRenderKey(timeline);
      const wasRunning = this._lastRunning;
      this._lastRunning = state.running;
      if (key !== this.renderedKey || wasRunning && !state.running) {
        console.log("[chat.render] fullRender", { msgCount: msgs.length, roles: msgs.map((m) => m.role), serverIds: msgs.map((m) => m.serverId?.slice(-12)) });
        this.fullRender(timeline, msgs);
        this.renderedKey = key;
      } else {
        this.incrementalTextUpdate(timeline);
      }
      this._updateStatusBar(state.running);
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
    renderSubAgentInto(container, messages, isRunning) {
      const timeline = buildSubAgentTimeline(messages, isRunning);
      const st = (0, import_state.getState)();
      const autoExpand = (0, import_state.isEnabled)(st.settings.auto_expand);
      this.applyAutoExpand(timeline, autoExpand, isRunning);
      this._subAgentRender = true;
      let html;
      try {
        html = this.buildTimelineHTML(timeline, messages, true);
      } finally {
        this._subAgentRender = false;
      }
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
    computeExpanded(kind, id, autoExpand, thinkingActive) {
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
    activeThinkingId(timeline, isRunning) {
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
    applyAutoExpand(timeline, autoExpand, isRunning = false) {
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
    buildTimelineHTML(timeline, allMsgs, treatAsSubAgent = false) {
      let html = "";
      let turnMid = "";
      let turnActions = false;
      let turnRetry = false;
      let turnBranchSwitcher = false;
      const _this = this;
      function closeTurn() {
        if (!turnMid) return;
        html += `<div class="turn">${turnMid}`;
        if (turnActions) {
          html += `<div class="assistant-actions turn-actions">`;
          html += `<button class="btn-icon btn-icon--msg assistant-copy-btn" data-tooltip="${(0, import_i18n.t)("chat.copy")}">
          <span class="icon-wrap">
            <i data-lucide="copy" class="semantic"></i>
            <i data-lucide="chevron-down" class="arrow"></i>
          </span>
        </button>`;
          if (turnRetry) {
            html += `<button class="btn-icon btn-icon--msg assistant-retry-btn" data-tooltip="${(0, import_i18n.t)("chat.retry")}">
            <span class="icon-wrap">
              <i data-lucide="refresh-cw" class="semantic"></i>
              <i data-lucide="chevron-down" class="arrow"></i>
            </span>
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
      const inSubAgent = treatAsSubAgent || !!(0, import_state.getState)().subAgentView || !!window.__parentSessionId;
      for (let i = 0; i < timeline.length; i++) {
        const item = timeline[i];
        if (item.kind === "compact" || item.kind === "workflow" || item.kind === "user" && !inSubAgent) {
          closeTurn.call(_this);
          html += this.renderItemHTML(item);
        } else if (item.kind === "ai_header") {
          closeTurn.call(_this);
          turnMid += this.renderItemHTML(item);
        } else {
          if (item.showBranchSwitcher) turnBranchSwitcher = true;
          if (item.showActions) {
            turnActions = true;
            if (!inSubAgent) {
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
    fullRenderParallel(subMsgs, isStreaming) {
      const groupsByIndex = /* @__PURE__ */ new Map();
      let fallbackIndex = 0;
      let current = null;
      for (const m of subMsgs) {
        if (m.mode === "task_divider") {
          const index = Number.isInteger(m.taskIndex) ? m.taskIndex : fallbackIndex;
          fallbackIndex = Math.max(fallbackIndex, index + 1);
          current = { divider: m, body: [] };
          groupsByIndex.set(index, current);
        } else if (current) {
          current.body.push(m);
        }
      }
      const groups = [...groupsByIndex.entries()].sort(([left], [right]) => left - right).map(([, group]) => group);
      const statusMeta = (s) => {
        if (s === "done") return { icon: "check", label: (0, import_i18n.t)("chat.taskDone") || "Done", cls: "is-done" };
        if (s === "error") return { icon: "x", label: (0, import_i18n.t)("chat.taskError") || "Failed", cls: "is-error" };
        if (s === "queued") return { icon: "clock", label: (0, import_i18n.t)("chat.taskQueued") || "Queued", cls: "is-queued" };
        return { icon: "loader", label: (0, import_i18n.t)("chat.taskRunning") || "Running", cls: "is-running" };
      };
      const shown = groups.slice(0, 4);
      const count = shown.length;
      const tileBodies = [];
      for (const g of shown) {
        const isRunning = statusMeta(g.divider.taskStatus).cls === "is-running";
        const bodyTimeline = buildSubAgentTimeline(g.body, isRunning);
        this._subAgentRender = true;
        let bodyHtml;
        try {
          bodyHtml = g.body.length > 0 ? this.buildTimelineHTML(bodyTimeline, g.body, true) : `<div class="parallel-task-pending">${(0, import_i18n.t)("chat.taskWaiting") || "Waiting for output\u2026"}</div>`;
        } finally {
          this._subAgentRender = false;
        }
        tileBodies.push(bodyHtml);
      }
      const wrapTile = (idx) => `<section class="parallel-tile"><div class="parallel-tile-body">${tileBodies[idx]}</div></section>`;
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
      const existing = this.ml.querySelector(":scope > .parallel-sub-agent");
      const _vs = saveVideoPlayback();
      window.__stopAllMedia?.();
      if (existing && existing.dataset.count === String(count)) {
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
    fullRender(timeline, allMsgs) {
      this.ml.classList.remove("parallel-active");
      const st = (0, import_state.getState)();
      const autoExpand = (0, import_state.isEnabled)(st.settings.auto_expand);
      const isRunning = st.running;
      this.applyAutoExpand(timeline, autoExpand, isRunning);
      let html = "";
      let turnMid = "";
      let turnActions = false;
      let turnRetry = false;
      let turnBranchSwitcher = false;
      const _this = this;
      function closeTurn() {
        if (!turnMid) return;
        html += `<div class="turn">${turnMid}`;
        if (turnActions) {
          html += `<div class="assistant-actions turn-actions">`;
          html += `<button class="btn-icon btn-icon--msg assistant-copy-btn" data-tooltip="${(0, import_i18n.t)("chat.copy")}">
          <span class="icon-wrap">
            <i data-lucide="copy" class="semantic"></i>
            <i data-lucide="chevron-down" class="arrow"></i>
          </span>
        </button>`;
          if (turnRetry) {
            html += `<button class="btn-icon btn-icon--msg assistant-retry-btn" data-tooltip="${(0, import_i18n.t)("chat.retry")}">
            <span class="icon-wrap">
              <i data-lucide="refresh-cw" class="semantic"></i>
              <i data-lucide="chevron-down" class="arrow"></i>
            </span>
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
        if (item.kind === "compact" || item.kind === "workflow" || item.kind === "user" && !(0, import_state.getState)().subAgentView && !window.__parentSessionId) {
          closeTurn.call(_this);
          html += this.renderItemHTML(item);
        } else if (item.kind === "ai_header") {
          closeTurn.call(_this);
          turnMid += this.renderItemHTML(item);
        } else {
          if (item.showBranchSwitcher) turnBranchSwitcher = true;
          if (item.showActions) {
            turnActions = true;
            if (!(0, import_state.getState)().subAgentView) {
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
          turnMid += this.renderItemHTML(item);
        }
      }
      closeTurn.call(_this);
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
        const newScrollHeight = container.scrollHeight;
        const delta = newScrollHeight - prevScrollHeight;
        container.scrollTop = prevScrollTop + delta;
        const dist = newScrollHeight - container.scrollTop - container.clientHeight;
        this.userScrolledUp = dist > 8;
      } else {
        this.scrollToBottomAfterMedia();
      }
      const userMsgs = (0, import_state.getState)().messages.filter((m) => m.role === "user");
      this.scrollIndicator.update(userMsgs.length, userMsgs.map((m) => m.content));
      this.syncScrollButton();
    }
    incrementalTextUpdate(timeline) {
      let lastAssistantIndex = -1;
      for (let i = timeline.length - 1; i >= 0; i--) {
        if (timeline[i].kind === "assistant_text") {
          lastAssistantIndex = i;
          break;
        }
      }
      if (lastAssistantIndex >= 0) {
        const assistantItem = timeline[lastAssistantIndex];
        const currentAssistantMsgId = assistantItem.id;
        if (currentAssistantMsgId !== this.lastAssistantMsgId) {
          this.lastAssistantMsgId = currentAssistantMsgId;
        }
      }
      const activeThinkingId = this.activeThinkingId(timeline, (0, import_state.getState)().running);
      for (let i = 0; i < timeline.length; i++) {
        const item = timeline[i];
        if (item.kind === "thinking") {
          const el = this.ml.querySelector(`[data-id="${item.id}"]`);
          if (el) {
            const bodyEl = el.querySelector(".thought-body");
            if (bodyEl && bodyEl.textContent !== item.text) {
              bodyEl.textContent = item.text;
            }
            const shouldExpand = (0, import_state.isEnabled)((0, import_state.getState)().settings.auto_expand);
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
      for (let i = 0; i < timeline.length; i++) {
        const toolItem = timeline[i];
        if (toolItem.kind !== "tool") continue;
        const el = this.ml.querySelector(`[data-id="${toolItem.id}"]`);
        if (!el) continue;
        const statusSlot = el.querySelector(".strip-status, .tool-item-status");
        if (statusSlot) {
          const curStatus = statusSlot.getAttribute("data-status") || "";
          if (curStatus !== toolItem.tc.status) {
            statusSlot.setAttribute("data-status", toolItem.tc.status);
            statusSlot.innerHTML = _toolStatusHtml(toolItem.tc.status);
          }
        }
        const summaryEl = el.querySelector(".strip-summary");
        if (summaryEl) {
          const isExpandable = el.classList.contains("strip-item") || el.classList.contains("terminal-card");
          const newSummary = isExpandable ? getToolSummary(toolItem.tc) : getToolInlineSummary(toolItem.tc);
          if (summaryEl.textContent !== newSummary) {
            summaryEl.textContent = newSummary;
          }
        }
        const bodySlot = el.querySelector(".strip-body-slot, .terminal-body-slot");
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
        const shouldExpandTool = (0, import_state.isEnabled)((0, import_state.getState)().settings.auto_expand);
        const wantExpandedTool = this.computeExpanded("tool", toolItem.id, shouldExpandTool, false);
        const isExpandedTool = el.classList.contains("expanded");
        if (wantExpandedTool && !isExpandedTool) {
          el.classList.add("expanded");
          this.expandedItems.add(toolItem.id);
        } else if (!wantExpandedTool && isExpandedTool) {
          el.classList.remove("expanded");
          this.expandedItems.delete(toolItem.id);
        }
      }
      for (let i = 0; i < timeline.length; i++) {
        if (timeline[i].kind !== "workflow") continue;
        const wf = (0, import_state.getState)().workflowState;
        if (!wf) continue;
        const card = this.ml.querySelector(`#wf-${wf.workflowId}`);
        if (!card) continue;
        const bar = card.querySelector(".workflow-progress-fill");
        if (bar) {
          const pct = wf.totalTasks > 0 ? Math.round((wf.completedCount + wf.failedCount + wf.skippedCount) / wf.totalTasks * 100) : 0;
          bar.style.width = pct + "%";
        }
        const textEl = card.querySelector(".workflow-progress-text");
        if (textEl) {
          const newText = `${wf.completedCount + wf.failedCount + wf.skippedCount}/${wf.totalTasks} tasks \u2014 ${wf.completedCount} done, ${wf.failedCount} failed, ${wf.skippedCount} skipped`;
          if (textEl.textContent !== newText) textEl.textContent = newText;
        }
        const badge = card.querySelector(".workflow-card-badge");
        if (badge && !wf.active) {
          const statusColor = wf.success ? "#22c55e" : "#ef4444";
          badge.textContent = wf.success ? (0, import_i18n.t)("chat.workflowDone") || "Completed" : (0, import_i18n.t)("chat.workflowFailed") || "Failed";
          badge.style.background = statusColor + "20";
          badge.style.color = statusColor;
        }
        const taskEls = card.querySelectorAll(".wf-task");
        taskEls.forEach((taskEl, idx) => {
          if (idx >= wf.tasks.length) return;
          const t2 = wf.tasks[idx];
          const dot = taskEl.querySelector(".wf-dot");
          const statusEl = taskEl.querySelector(".wf-task-status");
          if (dot && dot.getAttribute("data-status") !== t2.status) {
            dot.setAttribute("data-status", t2.status);
            dot.className = `wf-dot wf-dot--${t2.status}`;
          }
          if (statusEl && statusEl.textContent !== t2.status) {
            statusEl.textContent = t2.status;
          }
        });
      }
      if (lastAssistantIndex >= 0) {
        const assistantItem = timeline[lastAssistantIndex];
        const newText = assistantItem.content;
        const el = this.ml.querySelector(`[data-id="${assistantItem.id}"]`);
        if (!el) {
          if (!this._inRenderForce) {
            this.renderForce();
          }
          return;
        }
        if (newText.trim().length > 0) {
          const contentEl = el.querySelector(".msg-text");
          if (contentEl) {
            const newHtml = renderMarkdown(newText);
            if (contentEl.innerHTML !== newHtml) {
              contentEl.innerHTML = newHtml;
            }
          }
        }
      }
      this.autoScroll();
      const userMsgs = (0, import_state.getState)().messages.filter((m) => m.role === "user");
      this.scrollIndicator.update(userMsgs.length, userMsgs.map((m) => m.content));
      this.syncScrollButton();
    }
    renderItemHTML(item) {
      switch (item.kind) {
        case "user":
          return this.renderUserItem(item);
        case "ai_header":
          return this.renderAIHeader(item);
        case "thinking":
          return this.renderThinkingStrip(item);
        case "tool":
          return this.renderToolCall(item);
        case "assistant_text":
          return this.renderAssistantText(item);
        case "error_card":
          return this.renderErrorCard(item);
        case "warning_card":
          return this.renderWarningCard(item);
        case "compact_starting":
          return this.renderCompactStartingCard(item);
        case "compact":
          return this.renderCompactCard(item);
        case "system_message":
          return this.renderSystemMessage(item);
        case "spec_card":
          return this.renderSpecCard(item);
        case "plan_card":
          return this.renderPlanCard(item);
        case "workflow":
          return this.renderWorkflowCard(item);
      }
      return "";
    }
    renderAIHeader(item) {
      return `<div class="ai-header">
      <span class="ai-name">${(0, import_i18n.t)("chat.yimAgent")}</span>
      <span class="ai-time">${item.time}</span>
    </div>`;
    }
    renderModeCard(icon, label, summary) {
      const iconHtml = icon.startsWith("data:") ? `<img src="${icon}" class="mode-card-icon" style="width:16px;height:16px">` : `<i data-lucide="${icon}" class="lucide mode-card-icon"></i>`;
      return `<span class="mode-chip mode-card">${iconHtml}<span class="mode-card-label">${escapeHtml(label)}</span>${summary ? `<span class="mode-card-summary">\xB7 ${escapeHtml(summary)}</span>` : ""}</span>`;
    }
    renderUserItem(item) {
      const isSubAgent = !!(0, import_state.getState)().subAgentView || this._subAgentRender;
      const cmdMatch = item.content.match(/^\/(\w[\w-]*)(?:\s+(.*))?$/s);
      const cmdTagMatch = !cmdMatch ? item.content.match(/^<command>(\w[\w-]*)<\/command>$/s) : null;
      const effectiveCmdMatch = cmdMatch || cmdTagMatch;
      const isTerminal = item.mode?.startsWith("terminal:");
      const modeBadge = item.mode && !isTerminal ? (() => {
        const c = (0, import_slash_commands.findSlashCommand)(item.mode);
        const icon = c ? c.icon : "list-checks";
        return `<span class="mode-chip" data-mode="${item.mode}"><i data-lucide="${icon}" class="chip-icon" style="width:12px;height:12px;"></i><span>${c ? c.title : item.mode}</span></span>`;
      })() : "";
      const fileCards = item.fileRefs?.map((f) => {
        if (f.icon === "folder") return this.renderModeCard(f.icon, f.name, "folder");
        if (f.icon === "terminal") return this.renderModeCard(f.icon, f.name, `${f.size} line${f.size !== 1 ? "s" : ""}`);
        return this.renderModeCard(f.icon, f.name, fmtSize(f.size));
      }).join("") || "";
      const termCard = isTerminal ? this.renderModeCard("terminal", item.mode.split(":")[1] || "Terminal", `${item.content.split("\n").length} lines`) : "";
      if (effectiveCmdMatch) {
        const cmdName = effectiveCmdMatch[1];
        const rest = cmdTagMatch ? "" : effectiveCmdMatch[2] || "";
        const displayContent = rest ? escapeHtml(rest) : "";
        const cmd = (0, import_slash_commands.findSlashCommand)(cmdName);
        const cmdBadge = cmd ? `<span class="mode-chip" data-mode="${cmdName}"><i data-lucide="${cmd.icon}" class="chip-icon" style="width:12px;height:12px;"></i><span>${cmd.title}</span></span>` : `<span class="mode-chip" data-mode="${cmdName}"><i data-lucide="wand-2" class="chip-icon" style="width:12px;height:12px;"></i><span>${escapeHtml(cmdName)}</span></span>`;
        return `<div class="user-item" data-user-idx="${item.index}">
        <div class="user-bubble">${cmdBadge}${modeBadge}${displayContent}</div>
        <div class="user-actions">
          <button class="btn-icon btn-icon--msg msg-copy-btn" data-tooltip="${(0, import_i18n.t)("chat.copy")}">
            <i data-lucide="copy" class="lucide lucide-sm"></i>
          </button>
          ${isSubAgent ? "" : `<button class="btn-icon btn-icon--msg msg-rollback-btn" data-tooltip="${(0, import_i18n.t)("chat.rollbackEdit")}">
            <i data-lucide="history" class="lucide lucide-sm"></i>
          </button>
          <button class="btn-icon btn-icon--msg msg-delete-btn btn-icon--danger" data-tooltip="${(0, import_i18n.t)("chat.delete")}">
            <i data-lucide="trash-2" class="lucide lucide-sm"></i>
          </button>`}
        </div>
      </div>`;
      }
      const contentHtml = isSubAgent ? escapeHtml(item.content) : item.content.includes("<attach ") || item.content.includes("<terminal>") || item.content.includes("<mode>") ? "" : escapeHtml(item.content);
      return `<div class="user-item" data-user-idx="${item.index}">
      <div class="user-bubble">${modeBadge}${termCard}${fileCards}${contentHtml}</div>
      <div class="user-actions">
        <button class="btn-icon btn-icon--msg msg-copy-btn" data-tooltip="${(0, import_i18n.t)("chat.copy")}">
          <i data-lucide="copy" class="lucide lucide-sm"></i>
        </button>
        ${isSubAgent ? "" : `<button class="btn-icon btn-icon--msg msg-rollback-btn" data-tooltip="${(0, import_i18n.t)("chat.rollbackEdit")}">
          <i data-lucide="history" class="lucide lucide-sm"></i>
        </button>
        <button class="btn-icon btn-icon--msg msg-delete-btn btn-icon--danger" data-tooltip="${(0, import_i18n.t)("chat.delete")}">
          <i data-lucide="trash-2" class="lucide lucide-sm"></i>
        </button>`}
      </div>
    </div>`;
    }
    renderThinkingStrip(item) {
      const id = item.id;
      const expanded = this.expandedItems.has(id);
      return `<div class="strip-item${expanded ? " expanded" : ""}" data-id="${id}">
      <div class="strip" onmouseenter="window.__hoverOn(this)" onmouseleave="window.__hoverOff(this)">
        <span class="icon-wrap">
          <i data-lucide="brain" class="semantic"></i>
          <i data-lucide="chevron-down" class="arrow"></i>
        </span>
        <span class="strip-name">${(0, import_i18n.t)("chat.thought")}</span>
      </div>
      <div class="strip-body thought-body">${escapeHtml(item.text)}</div>
    </div>`;
    }
    renderToolCall(item) {
      const tc = item.tc;
      const name = tc.name;
      if (isHiddenTool(name)) return "";
      if (name === "agent") return this.renderAgent(tc, item.id);
      if (name === "question") return this.renderQuestionCard(tc, item.id);
      if (name === "info") return this.renderInfoCard(tc, item.id);
      if (isFileMutationTool(name)) {
        if (name === "delete_file") return this.renderFileCard(tc);
        return this.renderExpandableStrip(tc, item.id);
      }
      if (isFileReadTool(name)) return this.renderToolItemSimple(tc);
      if (isToolItemTool(name)) return this.renderToolItemSimple(tc);
      return this.renderExpandableStrip(tc, item.id);
    }
    renderQuestionCard(tc, itemId) {
      let params = tc.params;
      const rawArgs = params["arguments"];
      if (typeof rawArgs === "string" && rawArgs) {
        try {
          params = JSON.parse(rawArgs);
        } catch {
        }
      }
      const input = params["input"];
      if (input && typeof input === "object") params = input;
      let question = params.question || "";
      let details = params.details || "";
      let options = [];
      if (Array.isArray(params.options)) options = params.options.map(String);
      if (!question) {
        let qs = params.questions;
        if (typeof qs === "string") {
          try {
            qs = JSON.parse(qs);
          } catch {
          }
        }
        if (Array.isArray(qs) && qs.length > 0) {
          const first = qs[0];
          question = first.question || "";
          details = first.details || "";
          if (Array.isArray(first.options)) options = first.options.map(String);
        }
      }
      if (!question) {
        const debug = JSON.stringify(tc.params).substring(0, 200);
        return `<div class="question-card" id="tc-${tc.id}">
        <div class="question-card-header">
          <i data-lucide="help-circle" class="question-card-icon"></i>
          <span class="question-card-title">${(0, import_i18n.t)("chat.toolQuestion")}</span>
          <span class="question-card-badge">${(0, import_i18n.t)("chat.waitingForAnswer")}</span>
        </div>
        <div class="question-card-body">
          <div class="q-step" style="color:var(--text-muted);font-size:10px">${escapeHtml(debug)}</div>
        </div>
      </div>`;
      }
      if (tc.status === "done" && tc.result) {
        return `<div class="tool-item">
        <i data-lucide="help-circle" class="tool-item-icon"></i>
        <span class="strip-name">${(0, import_i18n.t)("chat.toolQuestion")}</span>
        <span class="strip-summary">${escapeHtml(question.substring(0, 80))}</span>
      </div>`;
      }
      const id = `tc-${tc.id}`;
      const optsHtml = options.length ? `<div class="q-options">${options.map((o) => {
        const s = o.indexOf("\u2014") > 0 ? o.substring(0, o.indexOf("\u2014")).trim() : o;
        const d = o.indexOf("\u2014") > 0 ? o.substring(o.indexOf("\u2014") + 1).trim() : "";
        return `<button class="q-option-card" data-value="${escapeHtml(s)}" onclick="event.stopPropagation();var inp=this.closest('.question-card-body,.agent-content').querySelector('.q-input');if(inp)inp.value=this.dataset.value;this.closest('.q-options').querySelectorAll('.q-option-card.selected').forEach(function(b){b.classList.remove('selected')});this.classList.add('selected')">
            <div class="q-option-title">${escapeHtml(s)}</div>
            ${d ? `<div class="q-option-desc">${escapeHtml(d)}</div>` : ""}
          </button>`;
      }).join("")}</div>` : "";
      return `<div class="question-card" id="${id}">
      <div class="question-card-header">
        <i data-lucide="help-circle" class="question-card-icon"></i>
        <span class="question-card-title">${(0, import_i18n.t)("chat.toolQuestion")}</span>
        <span class="question-card-badge">${(0, import_i18n.t)("chat.waitingForAnswer")}</span>
      </div>
      <div class="question-card-body">
        ${details ? `<div class="q-step">${escapeHtml(details)}</div>` : ""}
        <div class="q-field">
          <div class="q-field-label">${(0, import_i18n.t)("chat.questionField")}</div>
          <div class="q-field-text">${escapeHtml(question)}</div>
        </div>
        ${optsHtml}
        <div class="q-input-row">
          <input class="q-input" type="text" placeholder="${options.length ? (0, import_i18n.t)("chat.inputOtherRequirements") : (0, import_i18n.t)("chat.typeAnswer")}" onkeydown="if(event.key==='Enter'){event.preventDefault();window.__answerQuestion(event,this,'${id}')}" />
          <button class="q-submit" onclick="event.stopPropagation();window.__answerQuestion(event,this,'${id}')">${(0, import_i18n.t)("chat.submit")}</button>
        </div>
      </div>
    </div>`;
    }
    renderInfoCard(tc, itemId) {
      let payload = {};
      if (tc.result) {
        try {
          const parsed = JSON.parse(tc.result);
          if (parsed && typeof parsed === "object") payload = parsed;
        } catch {
          payload = { content: tc.result };
        }
      }
      const display = payload.display || tc.params.display || "base";
      const title = payload.title || tc.params.title || "";
      const content = payload.content || tc.params.content || "";
      const media = payload.media || [];
      const cardId = `tc-${tc.id}`;
      if (media.length > 0) {
        const itemsHtml = media.map(
          (m, i) => `<div data-type="${escapeHtml(m.type)}" data-src="${escapeHtml(m.src)}"></div>`
        ).join("");
        return `<div class="info-card info-card--media" id="${cardId}">${itemsHtml}</div>`;
      }
      if (!content) {
        return `<div class="info-card info-card--empty" id="${cardId}">
        <div class="info-card-header">
          <i data-lucide="layout-dashboard" class="info-card-icon"></i>
          <span class="info-card-title">${(0, import_i18n.t)("chat.toolInfo")}</span>
        </div>
        <div class="info-card-body">${(0, import_i18n.t)("chat.infoWaiting")}</div>
      </div>`;
      }
      const label = escapeHtml(title || (0, import_i18n.t)("chat.toolInfo"));
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
    renderFileCard(tc) {
      const id = `tc-${tc.id}`;
      const path = tc.params.path || tc.params.file_path || "";
      const hasResult = !!tc.result;
      const isError = hasResult && (tc.isError || /^error:/i.test(tc.result || ""));
      const iconName = isError ? "alert-triangle" : "trash-2";
      const iconColor = isError ? "#f59e0b" : "#71717a";
      const errorText = isError ? (0, import_i18n.t)("chat.toolFailed") : "";
      return `<div class="file-card${isError ? " file-card--error" : ""}" data-id="${id}" data-path="${escapeHtml(path)}">
      <i data-lucide="${iconName}" class="file-card-icon" style="color:${iconColor}"></i>
      <span class="file-card-name">${escapeHtml(path || formatToolName(tc.name))}</span>
      ${errorText ? `<span class="file-card-error-text">${errorText}</span>` : ""}
    </div>`;
    }
    renderTerminalCard(tc, itemId) {
      const id = `tc-${tc.id}`;
      const expanded = this.expandedItems.has(id);
      const term = tc.params.terminal;
      const termIcon = "terminal";
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
    renderExpandableStrip(tc, itemId) {
      const id = `tc-${tc.id}`;
      const expanded = this.expandedItems.has(id);
      const term = tc.params.terminal;
      const icon = getToolIcon(tc.name, term);
      const name = formatToolName(tc.name, term);
      const summary = getToolSummary(tc);
      const statusHtml = _toolStatusHtml(tc.status);
      const hasResult = !!tc.result;
      const bodyHtml = hasResult ? getToolBodyText(tc) : "";
      const iconHtml = icon ? `<span class="icon-wrap"><i data-lucide="${icon}" class="semantic"></i><i data-lucide="chevron-down" class="arrow"></i></span>` : "";
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
    renderToolItemSimple(tc) {
      const id = `tc-${tc.id}`;
      const term = tc.params.terminal;
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
    renderAgent(tc, itemId) {
      const rawAgentName = getAgentName(tc);
      const agentName = formatAgentLabel(rawAgentName);
      const isPlanSpec = tc.params.mode === "plan" || tc.params.mode === "spec";
      const agentIcon = isPlanSpec ? "list-checks" : "sparkles";
      const id = `tc-${tc.id}`;
      const tasks = this._agentTaskDividers(tc);
      if (tasks.length > 1) {
        return tasks.map((task, idx) => {
          const taskName = task.name || `${agentName} ${idx + 1}`;
          return `<div class="strip-item" id="${id}" data-task-index="${task.index}">
          <div class="strip" onclick="window.__openSubAgentView('${tc.id}', ${task.index})" onmouseenter="window.__hoverOn(this)" onmouseleave="window.__hoverOff(this)">
            <span class="icon-wrap">
              <i data-lucide="${agentIcon}" class="semantic"></i>
              <i data-lucide="chevron-right" class="arrow"></i>
            </span>
            <span class="strip-name">${escapeHtml(taskName)}</span>
          </div>
        </div>`;
        }).join("");
      }
      return `<div class="strip-item" id="${id}">
      <div class="strip" onclick="window.__openSubAgentView('${tc.id}')" onmouseenter="window.__hoverOn(this)" onmouseleave="window.__hoverOff(this)">
        <span class="icon-wrap">
          <i data-lucide="${agentIcon}" class="semantic"></i>
          <i data-lucide="chevron-right" class="arrow"></i>
        </span>
        <span class="strip-name">${escapeHtml(agentName)}</span>
      </div>
    </div>`;
    }
    _agentTaskDividers(tc) {
      const msgs = tc.subAgentMessages;
      if (!msgs || msgs.length === 0) return [];
      const dividers = /* @__PURE__ */ new Map();
      let fallbackIndex = 0;
      for (const message of msgs) {
        if (message.mode !== "task_divider") continue;
        const index = Number.isInteger(message.taskIndex) ? message.taskIndex : fallbackIndex;
        fallbackIndex = Math.max(fallbackIndex, index + 1);
        dividers.set(index, {
          index,
          name: message.taskName || "",
          status: message.taskStatus
        });
      }
      return [...dividers.values()].sort((a, b) => a.index - b.index);
    }
    renderAssistantText(item) {
      const errorClass = item.hasError ? " has-error" : "";
      const msgId = item.messageId || item.id.replace("a-", "").replace(/-seg-\d+$/, "");
      return `<div class="assistant-text${errorClass}" data-id="${item.id}" data-message-id="${msgId}">
      <div class="msg-text">${renderMarkdown(item.content)}</div>
    </div>`;
    }
    renderErrorCard(item) {
      const id = `ec-${item.messageId}`;
      const cat = item.errorCategory || "";
      let iconSvg;
      let label;
      let extraClass = "";
      if (cat === "auth") {
        iconSvg = `<svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>`;
        label = (0, import_i18n.t)("chat.abortedError");
        extraClass = " status-error-auth";
      } else if (cat === "rate_limit") {
        iconSvg = `<svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`;
        label = (0, import_i18n.t)("chat.errorRateLimited");
        extraClass = " status-error-rate";
      } else if (cat === "context") {
        iconSvg = `<svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>`;
        label = (0, import_i18n.t)("chat.errorContext");
        extraClass = " status-error-context";
      } else if (cat === "network") {
        iconSvg = `<svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="1" y1="1" x2="23" y2="23"/><path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55"/><path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39"/><path d="M10.71 5.05A16 16 0 0 1 22.56 9"/><path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/></svg>`;
        label = (0, import_i18n.t)("chat.errorNetwork");
        extraClass = " status-error-network";
      } else if (cat === "server") {
        iconSvg = `<svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>`;
        label = (0, import_i18n.t)("chat.errorServer");
        extraClass = " status-error-server";
      } else if (cat === "tool") {
        iconSvg = `<svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>`;
        label = (0, import_i18n.t)("chat.errorTool");
        extraClass = " status-error-tool";
      } else {
        iconSvg = `<svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;
        label = (0, import_i18n.t)("chat.abortedError");
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
    renderWarningCard(item) {
      return `<div class="turn-status-card status-warning">
      <svg class="status-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
      <span class="status-label">${(0, import_i18n.t)("chat.interrupted")}</span>
      <span class="status-detail">${escapeHtml(item.interruptedReason)}</span>
    </div>`;
    }
    renderBranchSwitcher() {
      const st = (0, import_state.getState)();
      if (st.branches.length <= 1) return "";
      const sorted = [...st.branches].sort((a, b) => (a.created_at || 0) - (b.created_at || 0));
      const activeIdx = sorted.findIndex((b) => b.id === st.activeBranchId);
      if (activeIdx < 0) return "";
      const ids = sorted.map((b) => b.id).join(",");
      return `<span class="branch-switcher" data-branch-ids="${ids}" data-active-idx="${activeIdx}">
      <button class="branch-prev">\u2039</button>
      <span class="branch-indicator">${activeIdx + 1} / ${sorted.length}</span>
      <button class="branch-next">\u203A</button>
    </span>`;
    }
    renderCompactStartingCard(item) {
      return `<div class="strip-item compact-starting-item" data-id="${item.id}">
      <div class="strip" style="cursor:default">
        <span class="icon-wrap">
          <i data-lucide="file-archive" class="semantic" style="width:14px;height:14px"></i>
        </span>
        <span class="strip-name">${(0, import_i18n.t)("chat.compressingContext")}</span>
      </div>
    </div>`;
    }
    renderCompactCard(item) {
      const st = (0, import_state.getState)();
      const idx = parseInt(item.id.replace("compact-", ""));
      const evt = st.compactEvents[idx];
      if (!evt) return "";
      const id = item.id;
      const expanded = this.expandedItems.has(id);
      const reductionPct = evt.old_tokens > 0 ? Math.round((1 - evt.new_tokens / evt.old_tokens) * 100) : 0;
      const summary = `${evt.old_count} \u2192 ${evt.new_count} messages \xB7 ${_fmtTokens(evt.old_tokens)} \u2192 ${_fmtTokens(evt.new_tokens)} tokens (${reductionPct}% reduced)`;
      const bodyLines = [
        `Old messages: ${evt.old_count}  New messages: ${evt.new_count}`,
        `Old tokens:   ${_fmtTokens(evt.old_tokens)}  New tokens:   ${_fmtTokens(evt.new_tokens)}`,
        `Reduction:    ${reductionPct}%`
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
    renderSystemMessage(item) {
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
    renderSpecCard(item) {
      const spec = item.spec;
      const status = spec.status;
      const isApproved = status === "approved";
      const isRejected = status === "rejected";
      const isReview = status === "review" || status === "draft";
      const sessionId = (0, import_state.getState)().sessionId;
      const cardId = `spec-card-${sessionId}`;
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
      let bodyHtml;
      if (isReview) {
        bodyHtml = `<div class="question-card-body">
        <div class="q-step">${escapeHtml((0, import_i18n.t)("chat.reviewSpecSub") || "If it does not match your intent, review and edit the files, or enter guidance in the input box.")}</div>
        <div class="q-field">
          <div class="q-field-label">${(0, import_i18n.t)("chat.reviewArtifact") || "Files"}</div>
          <div class="q-field-text">${sectionsHtml}</div>
        </div>
        ${feedbackHtml}
        <div class="q-actions" style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end">
          <button class="q-action-btn" data-spec-reject="${sessionId}" style="background:var(--bg-tertiary);color:var(--tool-text);border:1px solid var(--border)">${(0, import_i18n.t)("chat.reviewCancel") || "Cancel"}</button>
          <button class="q-action-btn" data-spec-approve="${sessionId}" style="background:var(--accent);color:#fff;border:1px solid var(--accent)">${(0, import_i18n.t)("chat.reviewExecute") || "Execute"}</button>
        </div>
      </div>`;
      } else if (isApproved) {
        bodyHtml = `<div class="question-card-body">
        <div class="q-step">${escapeHtml((0, import_i18n.t)("chat.reviewSpecMain") || "The specification has been generated.")}</div>
        <div class="q-field">
          <div class="q-field-label">\u89C4\u683C\u6587\u6863</div>
          <div class="q-field-text">${sectionsHtml}</div>
        </div>
        ${feedbackHtml}
        <div class="q-step" style="color:var(--success-color);margin-top:8px"><i data-lucide="check-circle"></i> ${(0, import_i18n.t)("chat.reviewExecuted") || "Executed"}</div>
      </div>`;
      } else if (isRejected) {
        bodyHtml = `<div class="question-card-body">
        <div class="q-step">${escapeHtml((0, import_i18n.t)("chat.reviewSpecMain") || "The specification has been generated.")}</div>
        <div class="q-field">
          <div class="q-field-label">\u89C4\u683C\u6587\u6863</div>
          <div class="q-field-text">${sectionsHtml}</div>
        </div>
        ${feedbackHtml}
        <div class="q-step" style="color:var(--danger-color);margin-top:8px"><i data-lucide="x-circle"></i> ${(0, import_i18n.t)("chat.reviewCancelled") || "Cancelled"}</div>
      </div>`;
      } else {
        bodyHtml = `<div class="question-card-body">${sectionsHtml}</div>`;
      }
      return `<div class="question-card" id="${cardId}">
      <div class="question-card-header">
        <i data-lucide="file-text" class="question-card-icon"></i>
        <span class="question-card-title">${escapeHtml((0, import_i18n.t)("chat.reviewSpecMain") || "Specification Review")}</span>
        <span class="question-card-badge">${isReview ? (0, import_i18n.t)("chat.waitingForAnswer") || "Pending" : isApproved ? (0, import_i18n.t)("chat.reviewExecuted") || "Executed" : (0, import_i18n.t)("chat.reviewCancelled") || "Cancelled"}</span>
      </div>
      ${bodyHtml}
    </div>`;
    }
    renderPlanCard(item) {
      const review = item.review;
      const status = review.status;
      const isApproved = status === "approved";
      const isRejected = status === "rejected";
      const isReview = status === "review" || status === "draft";
      const sessionId = (0, import_state.getState)().sessionId;
      const cardId = `plan-card-${review.review_id}`;
      const sections = this.parsePlanSections(review.content);
      const fileRows = [
        { name: "plan.md", content: sections.plan, icon: "file-text" },
        { name: "steps.md", content: sections.steps, icon: "list-ordered" },
        { name: "checklist.md", content: sections.checklist, icon: "check-square" }
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
      let bodyHtml;
      if (isReview) {
        bodyHtml = `<div class="question-card-body">
        <div class="q-step">${escapeHtml((0, import_i18n.t)("chat.reviewPlanSub") || "If it does not match your intent, review and edit the files, or enter guidance in the input box.")}</div>
        <div class="q-field">
          <div class="q-field-label">${(0, import_i18n.t)("chat.reviewArtifact") || "Files"}</div>
          <div class="q-field-text">${fileRowsHtml}</div>
        </div>
        <div class="q-actions" style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end">
          <button class="q-action-btn" data-plan-reject="${sessionId}" style="background:var(--bg-tertiary);color:var(--tool-text);border:1px solid var(--border)">${(0, import_i18n.t)("chat.reviewCancel") || "Cancel"}</button>
          <button class="q-action-btn" data-plan-approve="${sessionId}" style="background:var(--accent);color:#fff;border:1px solid var(--accent)">${(0, import_i18n.t)("chat.reviewExecute") || "Execute"}</button>
        </div>
      </div>`;
      } else if (isApproved) {
        bodyHtml = `<div class="question-card-body">
        <div class="q-step">${escapeHtml((0, import_i18n.t)("chat.reviewPlanMain") || "The plan has been generated.")}</div>
        <div class="q-field">
          <div class="q-field-label">\u8BA1\u5212\u5185\u5BB9</div>
          <div class="q-field-text">${fileRowsHtml}</div>
        </div>
        <div class="q-step" style="color:var(--success-color);margin-top:8px"><i data-lucide="check-circle"></i> ${(0, import_i18n.t)("chat.reviewExecuted") || "Executed"}</div>
      </div>`;
      } else if (isRejected) {
        bodyHtml = `<div class="question-card-body">
        <div class="q-step">${escapeHtml((0, import_i18n.t)("chat.reviewPlanMain") || "The plan has been generated.")}</div>
        <div class="q-field">
          <div class="q-field-label">\u8BA1\u5212\u5185\u5BB9</div>
          <div class="q-field-text">${fileRowsHtml}</div>
        </div>
        <div class="q-step" style="color:var(--danger-color);margin-top:8px"><i data-lucide="x-circle"></i> ${(0, import_i18n.t)("chat.reviewCancelled") || "Cancelled"}</div>
      </div>`;
      } else {
        bodyHtml = `<div class="question-card-body">${fileRowsHtml}</div>`;
      }
      return `<div class="question-card" id="${cardId}">
      <div class="question-card-header">
        <i data-lucide="list-checks" class="question-card-icon"></i>
        <span class="question-card-title">${escapeHtml((0, import_i18n.t)("chat.reviewPlanMain") || "Plan Review")}</span>
        <span class="question-card-badge">${isReview ? (0, import_i18n.t)("chat.waitingForAnswer") || "Pending" : isApproved ? (0, import_i18n.t)("chat.reviewExecuted") || "Executed" : (0, import_i18n.t)("chat.reviewCancelled") || "Cancelled"}</span>
      </div>
      ${bodyHtml}
    </div>`;
    }
    parsePlanSections(text) {
      const result = { plan: "", steps: "", checklist: "" };
      const re = /^##\s+(Plan|Steps|Checklist)\s*$/gmi;
      const parts = text.split(re);
      if (parts.length < 3) {
        result.plan = text;
        return result;
      }
      let key = "";
      for (let i = 1; i < parts.length; i++) {
        const trimmed = parts[i].trim();
        if (trimmed === "Plan" || trimmed === "Steps" || trimmed === "Checklist") {
          key = trimmed.toLowerCase();
        } else if (key) {
          result[key] = (result[key] + "\n\n" + parts[i]).trim();
        }
      }
      return result;
    }
    renderWorkflowCard(_item) {
      const wf = (0, import_state.getState)().workflowState;
      if (!wf) return "";
      const pct = wf.totalTasks > 0 ? Math.round((wf.completedCount + wf.failedCount + wf.skippedCount) / wf.totalTasks * 100) : 0;
      const doneCount = wf.completedCount + wf.failedCount + wf.skippedCount;
      const status = wf.active ? "running" : wf.success ? "completed" : "failed";
      const statusIcon = status === "running" ? "loader-circle" : status === "completed" ? "check-circle" : "x-circle";
      const statusColor = status === "running" ? "#3b82f6" : status === "completed" ? "#22c55e" : "#ef4444";
      const statusLabel = status === "running" ? (0, import_i18n.t)("chat.workflowRunning") || "Running" : status === "completed" ? (0, import_i18n.t)("chat.workflowDone") || "Completed" : (0, import_i18n.t)("chat.workflowFailed") || "Failed";
      const taskList = wf.tasks.map((t2) => {
        const dotCls = t2.status === "completed" ? "wf-dot--done" : t2.status === "running" ? "wf-dot--running" : t2.status === "failed" ? "wf-dot--failed" : t2.status === "skipped" ? "wf-dot--skipped" : "wf-dot--pending";
        const dot = `<span class="wf-dot ${dotCls}" data-tooltip="${escapeHtml(t2.taskName)}: ${t2.status}"></span>`;
        return `<div class="wf-task">
        ${dot}
        <span class="wf-task-name">${escapeHtml(t2.taskName || t2.taskId)}</span>
        <span class="wf-task-status">${t2.status}</span>
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
      <div class="workflow-progress-text">${doneCount}/${wf.totalTasks} tasks \u2014 ${wf.completedCount} done, ${wf.failedCount} failed, ${wf.skippedCount} skipped</div>
      <div class="workflow-task-list">${taskList}</div>
    </div>`;
    }
    handleDelegateClick(e) {
      const target = e.target;
      const strip = target.closest(".strip, .terminal-card-header");
      if (strip) {
        const item = strip.closest("[data-id]");
        if (item) {
          const id = item.getAttribute("data-id");
          if (id) {
            this.toggleItem(id, item);
            return;
          }
        }
      }
      const reviewToggle = target.closest("[data-review-toggle]");
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
          if (typeof window.lucide !== "undefined") {
            window.lucide.createIcons();
          }
          e.stopPropagation();
          return;
        }
      }
      const link = target.closest("a");
      if (link && link.href) {
        const behavior = (0, import_state.getState)().settings.default_link_behavior || "system";
        let url = link.href;
        if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("www.")) {
          e.preventDefault();
          e.stopPropagation();
          if (url.startsWith("www.")) url = "https://" + url;
          if (behavior === "in_app") {
            const api = window.electronAPI;
            if (api?.openChildWindow) {
              api.openChildWindow(url, url);
            } else {
              window.open(url, "_blank");
            }
          } else {
            const api = window.electronAPI;
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
        navigator.clipboard.writeText(code).then(() => {
          codeCopyBtn.textContent = (0, import_i18n.t)("chat.copied");
          setTimeout(() => {
            codeCopyBtn.textContent = (0, import_i18n.t)("chat.copy");
          }, 2e3);
        }).catch(() => (0, import_state.showToast)((0, import_i18n.t)("chat.copyFailed"), "", "error", "Chat"));
        return;
      }
      const copyBtn = target.closest(".msg-copy-btn");
      if (copyBtn) {
        e.stopPropagation();
        const userItem = copyBtn.closest(".user-item");
        const idx = userItem ? parseInt(userItem.getAttribute("data-user-idx") ?? "") : NaN;
        const st = (0, import_state.getState)();
        const userMsgs = st.messages.filter((m) => m.role === "user");
        if (!isNaN(idx) && userMsgs[idx]) {
          navigator.clipboard.writeText(userMsgs[idx].content).then(() => flashCopyButton(copyBtn)).catch(() => (0, import_state.showToast)((0, import_i18n.t)("chat.copyFailed"), "", "error", "Chat"));
        }
        return;
      }
      const editBtn = target.closest(".msg-rollback-btn");
      if (editBtn) {
        e.stopPropagation();
        const userItem = editBtn.closest(".user-item");
        const idx = userItem ? parseInt(userItem.getAttribute("data-user-idx") ?? "") : NaN;
        const st = (0, import_state.getState)();
        const userMsgs = st.messages.filter((m) => m.role === "user");
        if (isNaN(idx) || !userMsgs[idx]) return;
        const targetMsg = userMsgs[idx];
        let origContent = targetMsg.content;
        if (origContent.includes("<terminal>") || origContent.includes("<attach ") || origContent.includes("<mode>")) origContent = "";
        import_dialog.Dialog.confirm((0, import_i18n.t)("chat.rollbackEdit"), (0, import_i18n.t)("chat.rollbackEditDesc")).then((confirmed) => {
          if (confirmed) {
            const sid = targetMsg.serverId;
            (0, import_state.rememberRollbackEditTarget)(targetMsg, idx);
            if (sid && st.activeBranchId) {
              (0, import_ws.send)({ type: "rollback", branch_id: st.activeBranchId, message_id: sid });
            } else {
              (0, import_ws.send)({ type: "delete_message", message_index: idx, session_id: st.sessionId });
            }
            (0, import_state.truncateToUserMessage)(idx);
            this.renderForce();
            const input = document.getElementById("prompt-input");
            if (input) {
              input.textContent = origContent;
              input.focus();
            }
            const msgMode = targetMsg.mode;
            if (msgMode) {
              (0, import_state.restoreInputModeChip)(msgMode);
            }
            const refs = targetMsg.fileRefs;
            if (refs && refs.length > 0) {
              const atts = [];
              for (const r of refs) {
                if (r.mime_type === "text/x-terminal") continue;
                if (r.path) {
                  atts.push({ name: r.name, path: r.path, content: "", mime_type: r.mime_type || "", size: r.size, is_binary: false });
                }
              }
              if (atts.length > 0) (0, import_state.addAttachments)(atts);
            }
          }
        });
        return;
      }
      const deleteBtn = target.closest(".msg-delete-btn");
      if (deleteBtn) {
        e.stopPropagation();
        const userItem = deleteBtn.closest(".user-item");
        const idx = userItem ? parseInt(userItem.getAttribute("data-user-idx") ?? "") : NaN;
        const st = (0, import_state.getState)();
        const userMsgs = st.messages.filter((m) => m.role === "user");
        if (isNaN(idx) || !userMsgs[idx]) return;
        import_dialog.Dialog.confirm((0, import_i18n.t)("chat.deleteMessage"), (0, import_i18n.t)("chat.deleteMessageDesc")).then((confirmed) => {
          if (confirmed) (0, import_ws.send)({ type: "delete_message", message_index: idx });
        });
        return;
      }
      const assistantCopyBtn = target.closest(".assistant-copy-btn");
      if (assistantCopyBtn) {
        e.stopPropagation();
        const turn = assistantCopyBtn.closest(".turn");
        const assistantItem = turn?.querySelector(".assistant-text");
        const msgId = assistantItem?.dataset.messageId;
        if (!msgId) return;
        const st = (0, import_state.getState)();
        const msg = st.messages.find((m) => m.id === msgId);
        const btn = assistantCopyBtn;
        this.openActionMenu(btn, [
          {
            icon: "copy",
            label: (0, import_i18n.t)("chat.copy"),
            onClick: () => {
              const text = assistantItem?.innerText ?? msg?.content ?? "";
              navigator.clipboard.writeText(text).then(() => flashCopyButton(btn)).catch(() => (0, import_state.showToast)((0, import_i18n.t)("chat.copyFailed"), "", "error", "Chat"));
            }
          },
          {
            icon: "code",
            label: (0, import_i18n.t)("chat.copyMarkdown"),
            onClick: () => {
              if (!msg) return;
              navigator.clipboard.writeText(msg.content).then(() => flashCopyButton(btn)).catch(() => (0, import_state.showToast)((0, import_i18n.t)("chat.copyFailed"), "", "error", "Chat"));
            }
          }
        ]);
        return;
      }
      const assistantRetryBtn = target.closest(".assistant-retry-btn");
      if (assistantRetryBtn) {
        e.stopPropagation();
        const turn = assistantRetryBtn.closest(".turn");
        const assistantItem = turn?.querySelector(".assistant-text");
        const msgId = assistantItem?.dataset.messageId;
        if (!msgId) return;
        const btn = assistantRetryBtn;
        this.openActionMenu(btn, [
          { icon: "refresh-cw", label: (0, import_i18n.t)("chat.retryNormal"), onClick: () => this.performRetry(msgId, "normal") },
          { icon: "stretch-horizontal", label: (0, import_i18n.t)("chat.retryDetailed"), onClick: () => this.performRetry(msgId, "detailed") },
          { icon: "minimize-2", label: (0, import_i18n.t)("chat.retryConcise"), onClick: () => this.performRetry(msgId, "concise") }
        ]);
        return;
      }
      const branchPrev = target.closest(".branch-prev");
      if (branchPrev) {
        e.stopPropagation();
        const switcher = branchPrev.closest(".branch-switcher");
        if (!switcher) return;
        const ids = switcher.dataset.branchIds?.split(",") || [];
        const idx = parseInt(switcher.dataset.activeIdx || "0");
        const newIdx = idx > 0 ? idx - 1 : ids.length - 1;
        const branchId = ids[newIdx];
        if (branchId && branchId !== (0, import_state.getState)().activeBranchId) {
          if (typeof window.sendSwitchBranch === "function") {
            window.sendSwitchBranch(branchId);
          }
        }
        return;
      }
      const branchNext = target.closest(".branch-next");
      if (branchNext) {
        e.stopPropagation();
        const switcher = branchNext.closest(".branch-switcher");
        if (!switcher) return;
        const ids = switcher.dataset.branchIds?.split(",") || [];
        const idx = parseInt(switcher.dataset.activeIdx || "0");
        const newIdx = idx < ids.length - 1 ? idx + 1 : 0;
        const branchId = ids[newIdx];
        if (branchId && branchId !== (0, import_state.getState)().activeBranchId) {
          if (typeof window.sendSwitchBranch === "function") {
            window.sendSwitchBranch(branchId);
          }
        }
        return;
      }
      const approveBtn = target.closest("[data-spec-approve]");
      if (approveBtn) {
        e.stopPropagation();
        const sessionId = approveBtn.getAttribute("data-spec-approve") || "";
        (0, import_ws.send)({ type: "spec_approve", session_id: sessionId });
        return;
      }
      const rejectBtn = target.closest("[data-spec-reject]");
      if (rejectBtn) {
        e.stopPropagation();
        const sessionId = rejectBtn.getAttribute("data-spec-reject") || "";
        const feedback = prompt("Feedback (optional):") || "";
        (0, import_ws.send)({ type: "spec_reject", session_id: sessionId, feedback });
        return;
      }
      const openMdBtn = target.closest("[data-open-md]");
      if (openMdBtn) {
        e.stopPropagation();
        const fileKey = openMdBtn.getAttribute("data-open-md") || "";
        const title = openMdBtn.getAttribute("data-md-title") || "";
        const content = this._planFileLookup.get(fileKey) || "";
        window.__sessionInner?.openMarkdownPreview(content, title);
        return;
      }
      const planApproveBtn = target.closest("[data-plan-approve]");
      if (planApproveBtn) {
        e.stopPropagation();
        const sessionId = planApproveBtn.getAttribute("data-plan-approve") || "";
        (0, import_ws.send)({ type: "plan_approve", session_id: sessionId });
        return;
      }
      const planRejectBtn = target.closest("[data-plan-reject]");
      if (planRejectBtn) {
        e.stopPropagation();
        const sessionId = planRejectBtn.getAttribute("data-plan-reject") || "";
        (0, import_ws.send)({ type: "plan_reject", session_id: sessionId });
        return;
      }
    }
    toggleItem(id, el) {
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
    /** Opens a unified dropdown menu anchored to the given action button.
     *  Reuses the same visual language as the model selector / @-command
     *  menus (`.mention-dropdown` / `.mention-dropdown-item`). */
    openActionMenu(btn, items) {
      if (btn.classList.contains("action-menu-open")) {
        this.closeActionMenu();
        return;
      }
      this.closeActionMenu();
      const rect = btn.getBoundingClientRect();
      const menu = document.createElement("div");
      menu.className = "mention-dropdown action-menu";
      menu.style.position = "fixed";
      menu.style.top = `${rect.bottom + 4}px`;
      menu.style.left = `${rect.left}px`;
      menu.style.marginBottom = "0";
      menu.style.bottom = "auto";
      menu.style.minWidth = "160px";
      for (const item of items) {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "mention-dropdown-item";
        row.innerHTML = `<i data-lucide="${item.icon}" class="lucide"></i><span>${item.label}</span>`;
        row.addEventListener("click", (ev) => {
          ev.stopPropagation();
          this.closeActionMenu();
          item.onClick();
        });
        menu.appendChild(row);
      }
      document.body.appendChild(menu);
      createLucideIcons(menu);
      btn.classList.add("action-menu-open");
      this._actionMenu = menu;
      this._actionMenuBtn = btn;
      const closeOnOutside = (ev) => {
        if (this._actionMenu && !this._actionMenu.contains(ev.target)) {
          this.closeActionMenu();
        }
      };
      this._actionMenuClose = closeOnOutside;
      setTimeout(() => document.addEventListener("click", closeOnOutside), 0);
      const turn = btn.closest(".turn");
      const scheduleClose = () => {
        if (this._actionMenuCloseTimer !== null) return;
        this._actionMenuCloseTimer = window.setTimeout(() => {
          this._actionMenuCloseTimer = null;
          this.closeActionMenu();
        }, 180);
      };
      const cancelClose = () => {
        if (this._actionMenuCloseTimer !== null) {
          window.clearTimeout(this._actionMenuCloseTimer);
          this._actionMenuCloseTimer = null;
        }
      };
      if (turn) {
        const onTurnLeave = (ev) => {
          if (!this._actionMenu) return;
          const rel = ev.relatedTarget;
          if (rel && this._actionMenu.contains(rel)) return;
          scheduleClose();
        };
        turn.addEventListener("mouseleave", onTurnLeave);
        this._actionMenuTurnLeave = { el: turn, fn: onTurnLeave };
      }
      menu.addEventListener("mouseenter", cancelClose);
      menu.addEventListener("mouseleave", scheduleClose);
      this._actionMenuEnter = { el: menu, fn: cancelClose };
      this._actionMenuLeave = { el: menu, fn: scheduleClose };
    }
    closeActionMenu() {
      if (this._actionMenu) {
        this._actionMenu.remove();
        this._actionMenu = null;
      }
      if (this._actionMenuBtn) {
        this._actionMenuBtn.classList.remove("action-menu-open");
        this._actionMenuBtn = null;
      }
      if (this._actionMenuClose) {
        document.removeEventListener("click", this._actionMenuClose);
        this._actionMenuClose = null;
      }
      if (this._actionMenuTurnLeave) {
        this._actionMenuTurnLeave.el.removeEventListener(
          "mouseleave",
          this._actionMenuTurnLeave.fn
        );
        this._actionMenuTurnLeave = null;
      }
      if (this._actionMenuEnter) {
        this._actionMenuEnter.el.removeEventListener(
          "mouseenter",
          this._actionMenuEnter.fn
        );
        this._actionMenuEnter = null;
      }
      if (this._actionMenuLeave) {
        this._actionMenuLeave.el.removeEventListener(
          "mouseleave",
          this._actionMenuLeave.fn
        );
        this._actionMenuLeave = null;
      }
      if (this._actionMenuCloseTimer !== null) {
        window.clearTimeout(this._actionMenuCloseTimer);
        this._actionMenuCloseTimer = null;
      }
    }
    /** Re-generates the assistant reply starting from the preceding user
     *  message, forking the branch with the given retry mode. */
    performRetry(msgId, mode) {
      const st = (0, import_state.getState)();
      const assistantIdx = st.messages.findIndex((m) => m.id === msgId);
      if (assistantIdx < 0) return;
      let userContent = "";
      for (let i = assistantIdx - 1; i >= 0; i--) {
        if (st.messages[i].role === "user") {
          userContent = st.messages[i].content;
          break;
        }
      }
      if (!userContent) return;
      let userMsgIdx = -1;
      for (let i = 0; i < assistantIdx; i++) {
        if (st.messages[i].role === "user") userMsgIdx++;
      }
      const removedIds = /* @__PURE__ */ new Set();
      for (let i = assistantIdx; i < st.messages.length; i++) {
        removedIds.add(st.messages[i].id);
      }
      (0, import_state.removeBranchMessages)(removedIds);
      (0, import_state.startAssistantMessage)();
      (0, import_state.setSessionState)("running");
      const branchId = st.activeBranchId;
      if (typeof window.sendRetry === "function") {
        window.sendRetry(branchId, userMsgIdx, mode);
      }
    }
    autoScroll() {
      const st = (0, import_state.getState)();
      if (st.messages.length === 0) return;
      if (st.messages[st.messages.length - 1].role === "user") {
        this.scrollToBottom();
        return;
      }
      if (!st.running) return;
      if (!this.userScrolledUp) this.scrollToBottom();
    }
    toggleWelcome(show) {
      if (show) {
        this.welcomeScreen.classList.remove("hidden");
        this.ml.classList.add("hidden");
      } else {
        this.welcomeScreen.classList.add("hidden");
        this.ml.classList.remove("hidden");
      }
    }
    /** Scrolls the message list to the bottom (unless the user scrolled up). */
    scrollToBottom() {
      const c = document.getElementById("chat-container");
      if (c) c.scrollTop = c.scrollHeight;
    }
    /** Scrolls to the bottom and keeps re-pinning until any async media
     *  (images / videos inside the message list) has finished loading.
     *  A plain scrollToBottom() on session entry runs before images resolve,
     *  so the container grows afterwards and leaves unread content below the
     *  fold.  This variant waits for those elements to settle. */
    scrollToBottomAfterMedia() {
      const c = document.getElementById("chat-container");
      if (!c) return;
      const pin = () => {
        if (this.userScrolledUp) return;
        c.scrollTop = c.scrollHeight;
      };
      pin();
      requestAnimationFrame(pin);
      const media = Array.from(this.ml.querySelectorAll("img, video")).filter(
        (el) => el instanceof HTMLImageElement && !el.complete || el instanceof HTMLVideoElement && el.readyState < 2
      );
      if (media.length === 0) return;
      const done = () => {
        pin();
        media.forEach((el) => {
          el.removeEventListener("load", done);
          el.removeEventListener("loadeddata", done);
          el.removeEventListener("error", done);
        });
      };
      media.forEach((el) => {
        el.addEventListener("load", done, { once: true });
        el.addEventListener("loadeddata", done, { once: true });
        el.addEventListener("error", done, { once: true });
      });
      window.setTimeout(() => {
        media.forEach((el) => {
          el.removeEventListener("load", done);
          el.removeEventListener("loadeddata", done);
          el.removeEventListener("error", done);
        });
        pin();
      }, 800);
    }
    /** Keeps the floating scroll-to-bottom button in sync with the real state
     *  of the chat container. The button may only appear when the content
     *  actually overflows the viewport AND the user has scrolled away from
     *  the bottom; when a session is cleared or switched this re-evaluates
     *  the metrics instead of trusting a stale scroll event. */
    syncScrollButton() {
      const btn = document.getElementById("chat-scroll-bottom-btn");
      if (!btn) return;
      const { scrollTop, scrollHeight, clientHeight } = this.container;
      const scrollable = scrollHeight - clientHeight > 8;
      this.userScrolledUp = scrollable && scrollHeight - scrollTop - clientHeight > 100;
      btn.classList.toggle("hidden", !this.userScrolledUp);
    }
    /** Public reset so the view-switch cleanup can hide the button eagerly. */
    resetScrollButton() {
      this.userScrolledUp = false;
      const btn = document.getElementById("chat-scroll-bottom-btn");
      if (btn) btn.classList.add("hidden");
    }
    _updateStatusBar(running) {
      if (running) {
        if (!this._currentQuote) {
          this._currentQuote = pickRandomQuote();
        }
        const q = this._currentQuote;
        this.statusBar.innerHTML = `<span class="status-shimmer">${(0, import_i18n.t)(`chat.${q.textKey}`)}</span>`;
        this.statusBar.classList.remove("hidden");
      } else {
        this.statusBar.classList.add("hidden");
        this._currentQuote = null;
      }
    }
  };
  var ChatScrollIndicator = class _ChatScrollIndicator {
    constructor(container) {
      this.ticks = [];
      this.tickCount = 0;
      this.lastKey = "";
      this.spacing = 0;
      this.lastCurrent = -1;
      this.dragging = false;
      this.rafScheduled = false;
      this.container = container;
      this.root = document.getElementById("chat-scroll-indicator");
      this.track = document.getElementById("chat-scroll-track");
      this.thumb = document.getElementById("chat-scroll-thumb");
      this.bind();
    }
    static {
      this.MAX_VISIBLE = 5;
    }
    bind() {
      this.container.addEventListener("scroll", () => this.schedule(), { passive: true });
      this.root.addEventListener("mousedown", (e) => this.onPointerDown(e));
      window.addEventListener("mousemove", (e) => this.onPointerMove(e));
      window.addEventListener("mouseup", () => this.onPointerUp());
      if (typeof ResizeObserver !== "undefined") {
        const ro = new ResizeObserver(() => this.schedule());
        ro.observe(this.container);
      }
    }
    schedule() {
      if (this.rafScheduled) return;
      this.rafScheduled = true;
      requestAnimationFrame(() => {
        this.rafScheduled = false;
        this.update();
      });
    }
    rebuildTicks(count, texts) {
      this.tickCount = count;
      this.spacing = 0;
      this.lastCurrent = -1;
      this.track.innerHTML = "";
      this.ticks = [];
      for (let i = 0; i < count; i++) {
        const tick = document.createElement("div");
        tick.className = "chat-scroll-tick";
        const text = (texts[i] || "").trim().slice(0, 200);
        if (text) tick.setAttribute("data-tooltip", text);
        this.track.appendChild(tick);
        this.ticks.push(tick);
      }
    }
    update(turns, userTexts) {
      const key = `${turns}|${(userTexts || []).join("\0")}`;
      if (turns !== void 0 && key !== this.lastKey) {
        this.rebuildTicks(turns, userTexts || []);
        this.lastKey = key;
      }
      if (this.tickCount < 1) {
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
      const windowH = this.root.offsetHeight || 70;
      const spacing = windowH / _ChatScrollIndicator.MAX_VISIBLE;
      if (spacing !== this.spacing) {
        this.spacing = spacing;
        for (let i = 0; i < this.tickCount; i++) {
          this.ticks[i].style.top = `${i * spacing}px`;
          this.ticks[i].style.height = `${spacing}px`;
        }
      }
      const trackH = this.tickCount * spacing;
      let offset;
      if (trackH <= windowH) {
        offset = (windowH - trackH) / 2;
      } else {
        offset = -ratio * (trackH - windowH);
      }
      this.track.style.top = `${offset}px`;
      this.track.style.height = `${trackH}px`;
      const current = Math.round(ratio * (this.tickCount - 1));
      if (current !== this.lastCurrent) {
        if (this.lastCurrent >= 0 && this.lastCurrent < this.tickCount) {
          this.ticks[this.lastCurrent].classList.remove("current");
        }
        this.ticks[current].classList.add("current");
        this.lastCurrent = current;
      }
      this.thumb.style.top = `${current * spacing + offset + spacing / 2}px`;
    }
    onPointerDown(e) {
      e.preventDefault();
      this.dragging = true;
      this.root.classList.add("dragging");
      this.jumpTo(e.clientY);
    }
    onPointerMove(e) {
      if (!this.dragging) return;
      this.jumpTo(e.clientY);
    }
    onPointerUp() {
      if (!this.dragging) return;
      this.dragging = false;
      this.root.classList.remove("dragging");
    }
    jumpTo(clientY) {
      const rect = this.root.getBoundingClientRect();
      if (rect.height <= 0 || this.tickCount < 1) return;
      const windowH = rect.height;
      const spacing = windowH / _ChatScrollIndicator.MAX_VISIBLE;
      if (spacing !== this.spacing) this.spacing = spacing;
      const trackH = this.tickCount * spacing;
      const { scrollTop, scrollHeight, clientHeight } = this.container;
      const scrollable = scrollHeight - clientHeight;
      const ratio = scrollable > 0 ? Math.min(1, Math.max(0, scrollTop / scrollable)) : 0;
      let offset;
      if (trackH <= windowH) {
        offset = (windowH - trackH) / 2;
      } else {
        offset = -ratio * (trackH - windowH);
      }
      const y = Math.min(rect.bottom, Math.max(rect.top, clientY)) - rect.top;
      const idx = Math.round((y - offset) / spacing);
      const clamped = Math.max(0, Math.min(this.tickCount - 1, idx));
      this.scrollToTurn(clamped);
    }
    scrollToTurn(idx) {
      const el = this.container.querySelector(`[data-user-idx="${idx}"]`);
      if (el) {
        const cRect = this.container.getBoundingClientRect();
        const eRect = el.getBoundingClientRect();
        this.container.scrollTop += eRect.top - cRect.top;
      } else {
        const { scrollHeight, clientHeight } = this.container;
        const max = Math.max(0, scrollHeight - clientHeight);
        this.container.scrollTop = idx / Math.max(1, this.tickCount - 1) * max;
      }
    }
  };
})();
