/**
 * Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
 *
 * This file is part of Encre.
 * The Encre project belongs to the Dunimd Team.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
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
 * Global command palette / search.
 *
 * Implements the ⌘K-style search overlay. It merges server-side search results
 * with locally-indexed entities (skills, workspaces, models, settings nav, app
 * actions, slash commands, memory, rules, sessions, tools, automation, workflow,
 * and — for every *registered* workspace — its files) via MiniSearch — a
 * production-grade, zero-dependency, offline full-text search engine — using the
 * browser/Electron built-in `Intl.Segmenter` for CJK (Chinese) word segmentation,
 * so Chinese queries actually match. Results are grouped into labeled sections
 * and the appropriate action is dispatched when a result is activated.
 *
 * Both the ⌘K palette and the in-settings sidebar search share the same match
 * logic (`runLocalSearch` / `searchSettingsNavItems`) and the same user
 * configurable search filter (`AppState.searchFilter`).
 */

import MiniSearch from "minisearch";
import { getState, subscribe, setSearchResults, addAttachments } from "./state.js";
import { send } from "./ws.js";
import { setRequestedSessionId } from "./stream.js";
import type { SearchResultEntry, SearchFilter, SearchFilterKey } from "./types.js";
import { t, onLocaleChange } from "./i18n.js";
import { matchingSlashCommands, SLASH_COMMANDS } from "./slash_commands.js";

/**
 * Registry of app-action callbacks invokable from search results.
 * Populated by `app.ts` (registerCommandActions); search reads it at runtime
 * so any newly registered action becomes searchable automatically.
 */
export const commandActions: Record<string, () => void> = {};

/** A locally-indexed item fed into the MiniSearch full-text index. */
interface LocalItem {
  id?: number;
  kind: string;
  name: string;
  snippet: string;
  preview?: string;
  path?: string;
  icon?: string;
  session_id?: string;
  workspace_id?: string;
}

/** Convenience alias for the reactive app-state shape. */
type AppStateT = ReturnType<typeof getState>;

/** Template describing how a search section is labeled/iconed. */
interface SectionTemplate {
  getLabel: () => string;
  icon: string;
  kindLabel: (r: SearchResultEntry) => string;
}

/** A concrete search section: template plus its matched items. */
interface SectionDef extends SectionTemplate {
  items: SearchResultEntry[];
}

const SECTION_DEFS: Record<string, SectionTemplate> = {
  session_header: {
    getLabel: () => t("search.sectionSessions"),
    icon: `<i data-lucide="message-square" class="lucide lucide-sm"></i>`,
    kindLabel: () => t("search.resultSession"),
  },
  conversation: {
    getLabel: () => t("search.sectionConversations"),
    icon: `<i data-lucide="message-square" class="lucide lucide-sm"></i>`,
    kindLabel: () => t("general.resultConversation"),
  },
  memory: {
    getLabel: () => t("search.sectionMemory"),
    icon: `<i data-lucide="brain" class="lucide lucide-sm"></i>`,
    kindLabel: (r) => r.path || t("search.resultMemory"),
  },
  global_rule: {
    getLabel: () => t("search.sectionGlobalRules"),
    icon: `<i data-lucide="file-check" class="lucide lucide-sm"></i>`,
    kindLabel: (r) => r.path || t("search.resultGlobalRule"),
  },
  project_rule: {
    getLabel: () => t("search.sectionProjectRules"),
    icon: `<i data-lucide="file-check" class="lucide lucide-sm"></i>`,
    kindLabel: (r) => r.path || t("search.resultProjectRule"),
  },
  skill: {
    getLabel: () => t("search.sectionSkills"),
    icon: `<i data-lucide="wand-2" class="lucide lucide-sm"></i>`,
    kindLabel: (r) => r.name || t("search.resultSkill"),
  },
  workspace: {
    getLabel: () => t("search.sectionWorkspaces"),
    icon: `<i data-lucide="compass" class="lucide lucide-sm"></i>`,
    kindLabel: () => t("search.resultWorkspace"),
  },
  model: {
    getLabel: () => t("search.sectionModels"),
    icon: `<i data-lucide="cpu" class="lucide lucide-sm"></i>`,
    kindLabel: (r) => r.name || t("search.resultModel"),
  },
  mcp_server: {
    getLabel: () => t("search.sectionMcpServers"),
    icon: `<i data-lucide="server" class="lucide lucide-sm"></i>`,
    kindLabel: (r) => r.name || t("search.resultMcpServer"),
  },
  sub_agent: {
    getLabel: () => t("search.sectionSubAgents"),
    icon: `<i data-lucide="bot" class="lucide lucide-sm"></i>`,
    kindLabel: (r) => r.name || t("search.resultSubAgent"),
  },
  document: {
    getLabel: () => t("search.sectionDocuments"),
    icon: `<i data-lucide="book" class="lucide lucide-sm"></i>`,
    kindLabel: (r) => r.name || t("search.resultDocument"),
  },
  notification: {
    getLabel: () => t("search.sectionNotifications"),
    icon: `<i data-lucide="bell" class="lucide lucide-sm"></i>`,
    kindLabel: () => t("search.resultNotification"),
  },
  custom_command: {
    getLabel: () => t("search.sectionCommands"),
    icon: `<i data-lucide="terminal" class="lucide lucide-sm"></i>`,
    kindLabel: (r) => `/${r.name}` || t("search.resultCommand"),
  },
  settings_nav: {
    getLabel: () => t("search.sectionSettings"),
    icon: `<i data-lucide="settings" class="lucide lucide-sm"></i>`,
    kindLabel: (r) => r.preview || "",
  },
  app_action: {
    getLabel: () => t("search.sectionActions"),
    icon: `<i data-lucide="zap" class="lucide lucide-sm"></i>`,
    kindLabel: (r) => r.preview || "",
  },
  slash_command: {
    getLabel: () => t("search.sectionSlashCommands"),
    icon: `<i data-lucide="command" class="lucide lucide-sm"></i>`,
    kindLabel: () => t("search.resultSlashCommand"),
  },
  tool: {
    getLabel: () => t("search.sectionTools"),
    icon: `<i data-lucide="wrench" class="lucide lucide-sm"></i>`,
    kindLabel: () => t("search.resultTool"),
  },
  automation: {
    getLabel: () => t("search.sectionAutomation"),
    icon: `<i data-lucide="list-checks" class="lucide lucide-sm"></i>`,
    kindLabel: () => t("search.resultAutomation"),
  },
  workflow: {
    getLabel: () => t("search.sectionWorkflow"),
    icon: `<i data-lucide="git-branch" class="lucide lucide-sm"></i>`,
    kindLabel: () => t("search.resultWorkflow"),
  },
  file: {
    getLabel: () => t("search.sectionFiles"),
    icon: `<i data-lucide="file" class="lucide lucide-sm"></i>`,
    kindLabel: (r) => {
      const p = r.path || "";
      return r.preview ? `${r.preview}: ${p}` : (r.line ? `${p}:${r.line}` : p || r.kind);
    },
  },
};

/** Every settings panel the app can navigate to (must match `PanelId`). */
export const SETTINGS_NAV_ITEMS: { panel: string; nameEn: string; nameZh: string }[] = [
  { panel: "general", nameEn: "General", nameZh: "基本设置" },
  { panel: "model", nameEn: "Model", nameZh: "模型管理" },
  { panel: "mcp", nameEn: "MCP", nameZh: "MCP 服务器" },
  { panel: "skills", nameEn: "Skills", nameZh: "技能管理" },
  { panel: "agent", nameEn: "Agent", nameZh: "子代理管理" },
  { panel: "index", nameEn: "Index", nameZh: "文档管理" },
  { panel: "rules", nameEn: "Rules", nameZh: "规则管理" },
  { panel: "memory", nameEn: "Memory", nameZh: "记忆" },
  { panel: "usage", nameEn: "Usage", nameZh: "使用统计" },
  { panel: "about", nameEn: "About", nameZh: "关于" },
  { panel: "shortcuts", nameEn: "Shortcuts", nameZh: "快捷键" },
  { panel: "storage", nameEn: "Storage", nameZh: "存储" },
  { panel: "browser", nameEn: "Browser", nameZh: "浏览器" },
  { panel: "gateway", nameEn: "Gateway", nameZh: "网关" },
  { panel: "permissions", nameEn: "Permissions", nameZh: "权限" },
  { panel: "developer", nameEn: "Developer", nameZh: "开发者" },
];

/** i18n display names for registered command actions. */
const APP_ACTION_LABELS: Record<string, { en: string; zh: string }> = {
  "settings": { en: "Settings", zh: "设置" },
  "model-management": { en: "Model Management", zh: "模型管理" },
  "skills-management": { en: "Skills Management", zh: "技能管理" },
  "mcp-servers": { en: "MCP Servers", zh: "MCP 服务器" },
  "agent-config": { en: "Agent Config", zh: "子代理配置" },
  "about": { en: "About", zh: "关于" },
  "theme-dark": { en: "Dark Theme", zh: "深色主题" },
  "theme-light": { en: "Light Theme", zh: "浅色主题" },
  "theme-system": { en: "System Theme", zh: "跟随系统主题" },
  "language-zh": { en: "Language: Chinese", zh: "语言：中文" },
  "language-en": { en: "Language: English", zh: "语言：英文" },
  "new-session": { en: "New Session", zh: "新建对话" },
  "keyboard-shortcuts": { en: "Keyboard Shortcuts", zh: "键盘快捷键" },
};

/** Action ids exposed as dedicated search categories (not under "Actions"). */
const DEDICATED_ACTION_KINDS = new Set(["automation", "workflow"]);

// ── Mature full-text search engine (MiniSearch) + built-in CJK tokenizer ─────
// Replaces the previous Fuse.js fuzzy matcher, which is unreliable for Chinese
// (CJK) queries. MiniSearch is a production-grade, zero-dependency, offline
// in-memory search engine; Chinese word segmentation is provided by the
// browser/Electron built-in `Intl.Segmenter` (TC39 standard, no npm dep).
// Because both the index and the query use the same segmenter, Chinese
// substring and prefix queries match correctly.

const SegmenterCtor: any =
  typeof Intl !== "undefined" && (Intl as any).Segmenter ? (Intl as any).Segmenter : null;
const cjkSegmenter: any = SegmenterCtor
  ? new SegmenterCtor("zh", { granularity: "word" })
  : null;

/** Tokenizer: word-segments CJK and keeps latin/number runs; lower-cased. */
function cjkTokenize(text: string): string[] {
  if (!text) return [];
  if (!cjkSegmenter) {
    // Fallback for environments without Intl.Segmenter.
    return text.toLowerCase().split(/[^一-龥a-z0-9]+/i).filter(Boolean);
  }
  const out: string[] = [];
  for (const seg of cjkSegmenter.segment(text)) {
    if (seg.isWordLike) {
      const tok = (seg.segment as string).toLowerCase();
      if (tok) out.push(tok);
    }
  }
  return out;
}

let _searchIndex: MiniSearch<LocalItem> | null = null;
let _indexSignature = "";

/** Drop the cached local-search index (call when underlying data changes). */
export function invalidateSearchIndex(): void {
  _searchIndex = null;
}

/** Cheap signature of all data sources that feed the search index. */
function dataSourceSignature(st: AppStateT): string {
  const ti = st.toolsInfo;
  return [
    st.skillsList.length,
    st.workspaces.length,
    st.modelConfigs.length,
    st.mcpServers.length,
    st.subAgents.length,
    st.docsList.length,
    st.notifications.length,
    st.customCommands.length,
    st.memoryList.length,
    st.globalRules.length,
    st.projectRules.length,
    st.sessionsList.length,
    (ti?.base?.length || 0) + (ti?.unlocked?.length || 0) + (ti?.active?.length || 0),
    st.automationHistory.length,
    st.workflowState ? 1 : 0,
    cachedWorkspaceFiles.length,
    Object.keys(commandActions).length,
    st.workspaceMode,
  ].join(",");
}

/** Returns a cached MiniSearch index, rebuilding only when data changed. */
function getIndex(items: LocalItem[], st: AppStateT): MiniSearch<LocalItem> {
  const sig = dataSourceSignature(st);
  if (_searchIndex && _indexSignature === sig) return _searchIndex;
  const mini = new MiniSearch<LocalItem>({
    idField: "id",
    fields: ["name", "snippet", "preview", "path", "session_id", "icon"],
    storeFields: ["kind", "name", "snippet", "preview", "path", "session_id", "icon", "workspace_id"],
    tokenize: cjkTokenize,
    processTerm: (term: string) => term.toLowerCase(),
  });
  for (let i = 0; i < items.length; i++) items[i].id = i;
  mini.addAll(items);
  _searchIndex = mini;
  _indexSignature = sig;
  return mini;
}

/** Builds the lower-cased haystack string for an item (substring recall). */
function haystackOf(it: LocalItem): string {
  return [it.name, it.snippet, it.preview, it.path, it.session_id, it.icon]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

/** Maps a LocalItem to the public SearchResultEntry shape. */
function toEntry(it: LocalItem): SearchResultEntry {
  return {
    kind: it.kind,
    name: it.name,
    snippet: it.snippet,
    preview: it.preview,
    path: it.path,
    session_id: it.session_id,
    icon: it.icon,
    workspace_id: it.workspace_id,
  } as SearchResultEntry;
}

/** User-facing labels for each search-filter toggle, shared by the settings UI. */
export const SEARCH_FILTER_META: { key: SearchFilterKey; zh: string; en: string }[] = [
  { key: "session", zh: "会话", en: "Sessions" },
  { key: "conversation", zh: "对话内容", en: "Conversations" },
  { key: "memory", zh: "记忆", en: "Memory" },
  { key: "global_rule", zh: "全局规则", en: "Global Rules" },
  { key: "project_rule", zh: "项目规则", en: "Project Rules" },
  { key: "skill", zh: "技能", en: "Skills" },
  { key: "workspace", zh: "工作区", en: "Workspaces" },
  { key: "workspace_file", zh: "工作区文件", en: "Workspace Files" },
  { key: "model", zh: "模型", en: "Models" },
  { key: "mcp_server", zh: "MCP 服务", en: "MCP Servers" },
  { key: "sub_agent", zh: "子代理", en: "Sub Agents" },
  { key: "document", zh: "文档", en: "Documents" },
  { key: "notification", zh: "通知", en: "Notifications" },
  { key: "settings", zh: "设置项", en: "Settings" },
  { key: "action", zh: "操作", en: "Actions" },
  { key: "slash_command", zh: "斜杠命令", en: "Slash Commands" },
  { key: "custom_command", zh: "命令", en: "Commands" },
  { key: "tool", zh: "工具", en: "Tools" },
  { key: "automation", zh: "自动化", en: "Automation" },
  { key: "workflow", zh: "工作流", en: "Workflow" },
];

const SECTION_ORDER = [
  "session_header", "conversation", "memory", "global_rule", "project_rule",
  "app_action", "settings_nav", "slash_command",
  "skill", "workspace", "model", "mcp_server", "sub_agent", "document",
  "notification", "custom_command", "tool", "automation", "workflow", "file",
];

// ── Workspace file index (frontend only, registered workspaces only) ─────────

/** Cache of file entries collected from every *registered* workspace. */
let cachedWorkspaceFiles: LocalItem[] = [];

const WS_FILE_EXCLUDED = new Set([
  ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "target",
  ".encre", ".pytest_cache", ".mypy_cache", "build", "out", ".idea", ".vscode",
]);

const MAX_WS_FILE_DEPTH = 5;
const MAX_WS_FILES_PER_WS = 400;

function norm(p: string): string {
  return p.replace(/\\/g, "/");
}

async function walkWorkspace(
  dir: string,
  wsName: string,
  wsPath: string,
  out: LocalItem[],
  depth: number,
): Promise<void> {
  if (depth > MAX_WS_FILE_DEPTH || out.length >= MAX_WS_FILES_PER_WS) return;
  const api = window.electronAPI;
  if (!api) return;
  let entries: { name: string; isDirectory: boolean; isFile: boolean }[] = [];
  try {
    entries = await api.listDirectory(dir);
  } catch {
    return;
  }
  for (const e of entries) {
    if (out.length >= MAX_WS_FILES_PER_WS) return;
    if (e.name.startsWith(".")) continue;
    const abs = norm(`${dir}/${e.name}`);
    if (e.isDirectory) {
      if (WS_FILE_EXCLUDED.has(e.name)) continue;
      await walkWorkspace(abs, wsName, wsPath, out, depth + 1);
    } else if (e.isFile) {
      const baseParts = norm(wsPath).split("/");
      const absParts = abs.split("/");
      const rel = absParts.slice(baseParts.length).join("/");
      out.push({
        kind: "file",
        name: e.name,
        snippet: rel,
        preview: wsName,
        path: abs,
        workspace_id: wsPath,
      });
    }
  }
}

/** Rebuilds `cachedWorkspaceFiles` from all registered workspaces. */
export async function buildWorkspaceFileIndex(): Promise<void> {
  const out: LocalItem[] = [];
  for (const ws of getState().workspaces) {
    if (out.length >= MAX_WS_FILES_PER_WS * 4) break;
    try {
      await walkWorkspace(norm(ws.path), ws.name, norm(ws.path), out, 0);
    } catch {
      /* ignore unreadable workspace */
    }
  }
  cachedWorkspaceFiles = out;
  invalidateSearchIndex();
}

/**
 * Core local search used by both the ⌘K palette and the settings sidebar.
 * Returns merged, de-duplicated results honoring the user's search filter.
 */
export function runLocalSearch(q: string, filter: SearchFilter): SearchResultEntry[] {
  const query = q.trim();
  if (!query) return [];
  const st = getState();
  const ql = query.toLowerCase();
  const items: LocalItem[] = [];

  // Build the FULL item set (filtering is applied to results, not the index,
  // so the cached MiniSearch index stays stable across filter toggles).
  for (const nav of SETTINGS_NAV_ITEMS) {
    items.push({ kind: "settings_nav", name: nav.nameEn, snippet: nav.nameZh, preview: nav.panel });
  }

  for (const id of Object.keys(commandActions)) {
    if (DEDICATED_ACTION_KINDS.has(id)) continue;
    const label = APP_ACTION_LABELS[id] || { en: id, zh: id };
    items.push({ kind: "app_action", name: label.en, snippet: label.zh, preview: id, path: id });
  }

  for (const sk of st.skillsList) items.push({ kind: "skill", name: sk.name, snippet: sk.name, preview: sk.description });
  for (const ws of st.workspaces) items.push({ kind: "workspace", name: ws.name, snippet: ws.name, preview: ws.path, path: ws.path });
  for (const mc of st.modelConfigs) items.push({ kind: "model", name: mc.name, snippet: mc.name, preview: mc.model_id });
  for (const sv of st.mcpServers) items.push({ kind: "mcp_server", name: sv.name, snippet: sv.name });
  for (const sa of st.subAgents) items.push({ kind: "sub_agent", name: sa.name, snippet: sa.name, preview: sa.description });
  for (const doc of st.docsList) items.push({ kind: "document", name: doc.name, snippet: doc.name });
  for (const n of st.notifications) items.push({ kind: "notification", name: n.title, snippet: n.title, preview: n.message });
  for (const cc of st.customCommands) items.push({ kind: "custom_command", name: cc.name, snippet: cc.title, preview: cc.description });
  for (const m of st.memoryList) items.push({ kind: "memory", name: m.name, snippet: m.path, preview: m.preview, path: m.path });
  for (const r of st.globalRules) items.push({ kind: "global_rule", name: r.name, snippet: r.path, preview: r.path, path: r.path });
  for (const r of st.projectRules) items.push({ kind: "project_rule", name: r.name, snippet: r.path, preview: `${r.priority}`, path: r.path });

  for (const s of st.sessionsList) {
    const name = s.name || s.session_id;
    items.push({
      kind: "session_header",
      name,
      snippet: s.name ? s.session_id : (s.preview || ""),
      preview: s.preview,
      session_id: s.session_id,
    });
  }

  const ti = st.toolsInfo;
  const seenTools = new Set<string>();
  for (const list of [ti.base, ti.unlocked, ti.active]) {
    for (const tool of list) {
      if (seenTools.has(tool)) continue;
      seenTools.add(tool);
      items.push({ kind: "tool", name: tool, snippet: tool, preview: t("search.resultTool") });
    }
  }

  for (const h of st.automationHistory) {
    const name = h.name || h.job_id || h.id || "automation";
    items.push({ kind: "automation", name, snippet: `${h.state || ""} ${h.name || ""}`.trim(), preview: h.job_id, path: h.id });
  }

  if (st.workflowState) {
    const wf = st.workflowState;
    items.push({
      kind: "workflow",
      name: wf.goal,
      snippet: wf.goal,
      preview: `${wf.completedCount}/${wf.totalTasks}`,
      path: wf.workflowId,
    });
  }

  for (const f of cachedWorkspaceFiles) items.push(f);

  const cmds = matchingSlashCommands(query, st.workspaceMode);
  for (const cmd of cmds) {
    items.push({ kind: "slash_command", name: `/${cmd.name}`, snippet: cmd.title, preview: cmd.description, icon: cmd.icon });
  }

  const mini = getIndex(items, st);

  // Primary pass: MiniSearch ranked results (CJK-aware via Intl.Segmenter).
  const ranked: SearchResultEntry[] = [];
  const seenId = new Set<number>();
  try {
    const hits = mini.search(query, {
      prefix: true,
      fuzzy: 0.2,
      combineWith: "AND",
      boost: { name: 2, snippet: 1.5 },
    });
    for (const h of hits) {
      const id = h.id as number;
      if (seenId.has(id)) continue;
      const item = h as unknown as LocalItem;
      if (!filter[item.kind as SearchFilterKey]) continue;
      seenId.add(id);
      ranked.push(toEntry(item));
    }
  } catch {
    /* ignore search errors */
  }

  // Recall fallback: case-insensitive substring. Guarantees CJK substring
  // matches (including a single mid-string character) that prefix/fuzzy may
  // miss. MiniSearch remains the primary ranked engine; this is just recall.
  for (const it of items) {
    if (seenId.has(it.id as number)) continue;
    if (!filter[it.kind as SearchFilterKey]) continue;
    if (haystackOf(it).includes(ql)) {
      seenId.add(it.id as number);
      ranked.push(toEntry(it));
    }
  }

  return ranked;
}

/**
 * Lightweight settings-nav matcher for the in-settings sidebar search.
 * Shares `SETTINGS_NAV_ITEMS` with the palette so both stay in sync.
 */
export function searchSettingsNavItems(q: string): { panel: string; nameEn: string; nameZh: string }[] {
  if (!q || !q.trim()) return SETTINGS_NAV_ITEMS;
  const lower = q.trim().toLowerCase();
  return SETTINGS_NAV_ITEMS.filter(
    (n) => n.nameEn.toLowerCase().includes(lower) || n.nameZh.toLowerCase().includes(lower),
  );
}

/**
 * The search command palette controller.
 */
export class Search {
  private input: HTMLInputElement;
  private resultsEl: HTMLElement;
  private selectedIdx = -1;
  private timer = 0;
  private currentResults: SearchResultEntry[] = [];
  private lastWsRef: unknown = null;

  /**
   * Constructor: resolves DOM elements, wires input/keys, and kicks off the
   * workspace-file index (refreshed whenever the registered workspaces change).
   */
  constructor() {
    this.input = document.getElementById("search-input") as HTMLInputElement;
    this.resultsEl = document.getElementById("search-results")!;

    this.input.addEventListener("input", () => this.onInput());
    this.input.addEventListener("keydown", (e) => this.onKey(e));
    subscribe(() => this.onStateChange());
    onLocaleChange(() => this.renderResults());

    this.refreshWorkspaceFiles();
  }

  /** Opens the search overlay and clears previous state/results. */
  open(): void {
    const overlay = document.getElementById("search-overlay")!;
    overlay.classList.remove("hidden");
    this.input.value = "";
    this.selectedIdx = -1;
    this.currentResults = [];
    setSearchResults([]);
    this.resultsEl.innerHTML = "";
    // Rebuild the registered-workspace file index so it's current.
    this.refreshWorkspaceFiles();
    setTimeout(() => this.input.focus(), 10);
  }

  /** Closes the search overlay and clears state/results. */
  close(): void {
    document.getElementById("search-overlay")?.classList.add("hidden");
    this.input.value = "";
    this.selectedIdx = -1;
    this.currentResults = [];
    setSearchResults([]);
  }

  private onInput(): void {
    const q = this.input.value.trim();
    this.selectedIdx = -1;
    clearTimeout(this.timer);
    if (!q) {
      setSearchResults([]);
      this.resultsEl.innerHTML = "";
      return;
    }
    this.timer = window.setTimeout(() => {
      send({ type: "search", query: q });
    }, 150);
  }

  private onKey(e: KeyboardEvent): void {
    if (e.key === "Escape") {
      e.preventDefault();
      this.close();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      this.selectedIdx = Math.min(this.selectedIdx + 1, this.currentResults.length - 1);
      this.renderResults();
      this.scrollToSelected();
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      this.selectedIdx = Math.max(this.selectedIdx - 1, -1);
      this.renderResults();
      this.scrollToSelected();
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      if (this.selectedIdx >= 0 && this.selectedIdx < this.currentResults.length) {
        this.activateResult(this.currentResults[this.selectedIdx]);
      }
      return;
    }
  }

  /** Re-indexes workspace files when the registered workspace set changes. */
  private refreshWorkspaceFiles(): void {
    buildWorkspaceFileIndex().catch((e) => console.warn("[search] workspace file index failed:", e));
  }

  private onStateChange(): void {
    const ws = getState().workspaces;
    if (ws !== this.lastWsRef) {
      this.lastWsRef = ws;
      this.refreshWorkspaceFiles();
    }
    this.renderResults();
  }

  /** Handles an activated result, dispatching by its `kind`. */
  private activateResult(r: SearchResultEntry): void {
    this.close();
    switch (r.kind) {
      case "conversation":
      case "session_header":
        if (r.session_id) {
          const requestId = crypto.randomUUID();
          setRequestedSessionId(r.session_id, requestId);
          send({ type: "resume", session_id: r.session_id, request_id: requestId });
        }
        break;
      case "file":
        if (r.path) this.activateFileResult(r.path, r.workspace_id);
        break;
      case "memory":
      case "global_rule":
      case "project_rule":
        this.insertPromptText(t("search.readEntry", { kind: r.kind, name: r.path || r.snippet }));
        break;
      case "skill":
        this.openSettingsPanel("skills");
        break;
      case "workspace":
        if (r.path) {
          const requestId = crypto.randomUUID();
          setRequestedSessionId("", requestId);
          send({ type: "open_workspace", path: r.path, request_id: requestId });
        }
        break;
      case "model":
        this.openSettingsPanel("model");
        break;
      case "mcp_server":
        this.openSettingsPanel("mcp");
        break;
      case "sub_agent":
        this.openSettingsPanel("agent");
        break;
      case "document":
        this.openSettingsPanel("index");
        break;
      case "settings_nav": {
        const panel = r.preview || "general";
        this.openSettingsPanel(panel);
        break;
      }
      case "tool":
        this.insertPromptText(r.name ?? "");
        break;
      case "automation":
        commandActions["automation"]?.();
        break;
      case "workflow":
        commandActions["workflow"]?.();
        break;
      case "app_action": {
        this.handleAppAction(r.path || r.name || "");
        break;
      }
      case "slash_command": {
        this.insertPromptText(r.name ?? "");
        break;
      }
      default:
        this.insertPromptText(r.snippet);
    }
  }

  private handleAppAction(actionId: string): void {
    if (commandActions[actionId]) {
      commandActions[actionId]();
      return;
    }
    switch (actionId) {
      case "new_session": {
        const newTaskBtn = document.querySelector('.nav-item[data-view="chat"]') as HTMLElement;
        newTaskBtn?.click();
        break;
      }
      case "iwork_mode": {
        const segItem = document.querySelector<HTMLElement>('#mode-seg .seg-item[data-mode="iwork"]');
        segItem?.click();
        break;
      }
      case "tools_panel": {
        const btn = document.getElementById("btn-tools-trigger") as HTMLElement;
        btn?.click();
        break;
      }
      case "normal_mode":
      default: {
        const segItem = document.querySelector<HTMLElement>('#mode-seg .seg-item[data-mode="normal"]');
        if (segItem?.classList.contains("active")) segItem.click();
        break;
      }
    }
  }

  private openSettingsPanel(panel: string): void {
    const btn = document.getElementById("btn-settings-trigger") as HTMLElement;
    btn?.click();
    setTimeout(() => {
      const navItem = document.querySelector(`.settings-nav-item[data-panel="${panel}"]`) as HTMLElement;
      navItem?.click();
    }, 50);
  }

  private insertPromptText(text: string): void {
    const input = document.getElementById("prompt-input") as HTMLElement;
    if (input) {
      input.textContent = text;
      input.focus();
    }
  }

  private async activateFileResult(fullPath: string, wsPath?: string): Promise<void> {
    if (wsPath) {
      const requestId = crypto.randomUUID();
      setRequestedSessionId("", requestId);
      send({ type: "open_workspace", path: wsPath, request_id: requestId });
    }
    if (window.electronAPI) {
      try {
        const result = await window.electronAPI.readFile(fullPath);
        if (result?.content && result.size > 0) {
          const name = fullPath.split("/").pop() ?? fullPath;
          addAttachments([{
            name,
            path: fullPath,
            content: result.content,
            mime_type: result.mime_type || "",
            size: result.size,
            is_binary: result.is_binary,
          }]);
        }
      } catch (e) {
        console.warn("[search] readFile failed:", e);
      }
    }
    this.insertPromptText(t("search.readFile", { path: fullPath }));
  }

  /** Renders the merged backend + local results grouped into sections. */
  private renderResults(): void {
    const q = this.input.value.trim();
    const filter = getState().searchFilter;
    let backendResults = getState().searchResults;
    backendResults = backendResults.filter((r) => {
      if (r.kind === "conversation") return filter.conversation;
      if (r.kind === "file") return filter.workspace_file;
      return true;
    });
    const localResults = runLocalSearch(q, filter);
    const results = this.mergeResults(backendResults, localResults);
    this.currentResults = results;

    if (results.length === 0) {
      this.resultsEl.innerHTML = q
        ? `<div class="search-empty">${t("search.noResultsFor", { query: this.esc(q) })}</div>`
        : "";
      return;
    }

    const sections = this.buildSections(results);

    let html = `<div class="search-result-count">${t("search.resultCount", { count: results.length })}</div>`;
    for (const sec of sections) {
      if (sec.items.length === 0) continue;
      html += `<div class="search-result-section-title">${sec.getLabel()}</div>`;
      for (const r of sec.items) {
        const idx = results.indexOf(r);
        const sel = idx === this.selectedIdx ? " selected" : "";
        const kindLabel = this.esc(sec.kindLabel(r));
        const snippet = this.esc(r.snippet);
        const preview = r.preview ? `<span class="search-result-preview">${this.esc(r.preview)}</span>` : "";
        const itemIcon = r.icon
          ? `<i data-lucide="${this.esc(r.icon)}" class="lucide lucide-sm"></i>`
          : sec.icon;
        html += `<div class="search-result-item${sel}" data-idx="${idx}">
          ${itemIcon}
          <div class="search-result-body">
            <span class="search-result-kind">${kindLabel}</span>
            <span class="search-result-snippet">${snippet}</span>
            ${preview}
          </div>
        </div>`;
      }
    }

    this.resultsEl.innerHTML = html;
    this.bindClicks();

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.resultsEl });
    }
  }

  /** Runs the shared local search (MiniSearch-backed) for the given query. */
  private searchLocal(q: string): SearchResultEntry[] {
    return runLocalSearch(q, getState().searchFilter);
  }

  /** Merges backend and local results, de-duplicated by kind+identity. */
  private mergeResults(backend: SearchResultEntry[], local: SearchResultEntry[]): SearchResultEntry[] {
    const seen = new Set<string>();
    const merged = [...backend];
    for (const item of backend) {
      seen.add(`${item.kind}:${item.session_id || item.path || item.name || item.snippet}`);
    }
    for (const item of local) {
      const key = `${item.kind}:${item.path || item.name || item.session_id || item.snippet}`;
      if (!seen.has(key)) {
        merged.push(item);
        seen.add(key);
      }
    }
    return merged;
  }

  /** Groups results into ordered, labeled sections for rendering. */
  private buildSections(results: SearchResultEntry[]): SectionDef[] {
    const sections: SectionDef[] = [];
    const seenKinds = new Set<string>();
    for (const kind of SECTION_ORDER) {
      const items = results.filter((r) => r.kind === kind);
      if (items.length === 0) continue;
      const def = SECTION_DEFS[kind] || SECTION_DEFS["file"];
      sections.push({
        ...def,
        items,
      });
      seenKinds.add(kind);
    }
    const other = results.filter((r) => !seenKinds.has(r.kind));
    if (other.length) {
      const fileDef = SECTION_DEFS["file"]!;
      sections.push({
        ...fileDef,
        items: other,
      });
    }
    return sections;
  }

  private bindClicks(): void {
    this.resultsEl.querySelectorAll(".search-result-item").forEach((item) => {
      item.addEventListener("click", () => {
        const idx = parseInt((item as HTMLElement).dataset.idx || "-1");
        if (idx >= 0 && idx < this.currentResults.length) {
          this.activateResult(this.currentResults[idx]);
        }
      });
    });
  }

  private scrollToSelected(): void {
    const sel = this.resultsEl.querySelector(".search-result-item.selected");
    sel?.scrollIntoView({ block: "nearest" });
  }

  private esc(s: string): string {
    const el = document.createElement("span");
    el.textContent = s;
    return el.innerHTML;
  }
}
