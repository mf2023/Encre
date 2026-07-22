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
 * Global command palette / search.
 *
 * Implements the ⌘K-style search overlay. It merges server-side search results
 * with locally-indexed entities (skills, workspaces, models, settings nav, app
 * actions, slash commands, …) via Fuse.js fuzzy matching, groups them into
 * labeled sections, and dispatches the appropriate action when a result is
 * activated.
 */

import Fuse from "fuse.js";
import { getState, subscribe, setSearchResults, addAttachments } from "./state.js";
import { send } from "./ws.js";
import { setRequestedSessionId } from "./stream.js";
import type { SearchResultEntry } from "./types.js";
import { t, onLocaleChange } from "./i18n.js";
import { matchingSlashCommands, SLASH_COMMANDS } from "./slash_commands.js";

/**
 * Registry of app-action callbacks invokable from search results.
 */
export const commandActions: Record<string, () => void> = {};

/** A locally-indexed item fed into the Fuse fuzzy index. */
interface LocalItem {
  kind: string;
  name: string;
  snippet: string;
  preview?: string;
  path?: string;
  icon?: string;
}

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
  file: {
    getLabel: () => t("search.sectionFiles"),
    icon: `<i data-lucide="file" class="lucide lucide-sm"></i>`,
    kindLabel: (r) => {
      const p = r.path || "";
      return r.line ? `${p}:${r.line}` : p || r.kind;
    },
  },
};

const SETTINGS_NAV_ITEMS: { panel: string; nameEn: string; nameZh: string }[] = [
  { panel: "general", nameEn: "General", nameZh: "基本设置" },
  { panel: "model", nameEn: "Model", nameZh: "模型管理" },
  { panel: "mcp", nameEn: "MCP", nameZh: "MCP 服务器" },
  { panel: "skills", nameEn: "Skills", nameZh: "技能管理" },
  { panel: "agent", nameEn: "Agent", nameZh: "子代理管理" },
  { panel: "index", nameEn: "Index", nameZh: "文档管理" },
  { panel: "rules", nameEn: "Rules", nameZh: "规则管理" },
  { panel: "memory", nameEn: "Memory", nameZh: "内存" },
  { panel: "usage", nameEn: "Usage", nameZh: "使用统计" },
  { panel: "about", nameEn: "About", nameZh: "关于" },
];

/** Definition of an application action exposed in search (id + i18n labels). */
interface AppActionDef {
  id: string;
  nameEn: string;
  nameZh: string;
}

const APP_ACTIONS: AppActionDef[] = [
  { id: "new_session", nameEn: "New Session", nameZh: "新建对话" },
  { id: "normal_mode", nameEn: "Normal Mode", nameZh: "普通模式" },
  { id: "iwork_mode", nameEn: "iWork Mode", nameZh: "工作区模式" },
  { id: "tools_panel", nameEn: "Tools Panel", nameZh: "工具面板" },
];

const SECTION_ORDER = [
  "session_header", "conversation", "memory", "global_rule", "project_rule",
  "app_action", "settings_nav", "slash_command",
  "skill", "workspace", "model", "mcp_server", "sub_agent", "document",
  "notification", "custom_command", "file",
];

/**
 * The search command palette controller.
 */
export class Search {
  private input: HTMLInputElement;
  private resultsEl: HTMLElement;
  private selectedIdx = -1;
  private timer = 0;
  private fuse: Fuse<LocalItem>;
  private currentResults: SearchResultEntry[] = [];

  /**
   * Constructor: resolves DOM elements, builds the Fuse index and wires input/keys.
   */
  constructor() {
    this.input = document.getElementById("search-input") as HTMLInputElement;
    this.resultsEl = document.getElementById("search-results")!;

    this.fuse = new Fuse<LocalItem>([], {
      keys: [
        { name: "name", weight: 2 },
        { name: "snippet", weight: 1.5 },
        { name: "preview", weight: 1 },
      ],
      threshold: 0.4,
      includeScore: true,
      minMatchCharLength: 1,
    });

    this.input.addEventListener("input", () => this.onInput());
    this.input.addEventListener("keydown", (e) => this.onKey(e));
    subscribe(() => this.renderResults());
    onLocaleChange(() => this.renderResults());
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
        if (r.path) this.activateFileResult(r.path);
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
        // The top-bar .seg switch is now the single mode entry point.
        // Clicking its iwork segment goes through the same code path as a
        // user click, so animation, IPC and state stay in one place.
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

  private async activateFileResult(path: string): Promise<void> {
    const wsPath = getState().activeWorkspace;
    const fullPath = wsPath ? `${wsPath}/${path}` : path;
    if (window.electronAPI) {
      try {
        const result = await window.electronAPI.readFile(fullPath);
        if (result?.content && result.size > 0) {
          addAttachments([{
            name: path.split("/").pop() ?? path,
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
    this.insertPromptText(t("search.readFile", { path }));
  }

  /** Renders the merged backend + local results grouped into sections. */
  private renderResults(): void {
    const q = this.input.value.trim();
    const backendResults = getState().searchResults;
    const localResults = this.searchLocal(q);
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

  /** Builds the local Fuse-indexed items from current app state. */
  private searchLocal(q: string): SearchResultEntry[] {
    if (!q || q.length < 2) return [];
    const st = getState();
    const items: LocalItem[] = [];

    for (const sk of st.skillsList) {
      items.push({ kind: "skill", name: sk.name, snippet: sk.name, preview: sk.description });
    }
    for (const ws of st.workspaces) {
      items.push({ kind: "workspace", name: ws.name, snippet: ws.name, preview: ws.path, path: ws.path });
    }
    for (const mc of st.modelConfigs) {
      items.push({ kind: "model", name: mc.name, snippet: mc.name, preview: mc.model_id });
    }
    for (const sv of st.mcpServers) {
      items.push({ kind: "mcp_server", name: sv.name, snippet: sv.name });
    }
    for (const sa of st.subAgents) {
      items.push({ kind: "sub_agent", name: sa.name, snippet: sa.name, preview: sa.description });
    }
    for (const doc of st.docsList) {
      items.push({ kind: "document", name: doc.name, snippet: doc.name });
    }
    for (const notif of st.notifications) {
      items.push({ kind: "notification", name: notif.title, snippet: notif.title, preview: notif.message });
    }
    for (const cc of st.customCommands) {
      items.push({ kind: "custom_command", name: cc.name, snippet: cc.title, preview: cc.description });
    }

    for (const nav of SETTINGS_NAV_ITEMS) {
      items.push({ kind: "settings_nav", name: nav.nameEn, snippet: nav.nameZh, preview: nav.panel });
    }

    for (const act of APP_ACTIONS) {
      items.push({ kind: "app_action", name: act.nameEn, snippet: act.nameZh, preview: act.id, path: act.id });
    }

    const cmds = matchingSlashCommands(q, st.workspaceMode);
    for (const cmd of cmds) {
      items.push({ kind: "slash_command", name: `/${cmd.name}`, snippet: cmd.title, preview: cmd.description, icon: cmd.icon });
    }

    this.fuse.setCollection(items);
    const fuseResults = this.fuse.search(q);
    return fuseResults.map(fr => ({
      kind: fr.item.kind,
      name: fr.item.name,
      snippet: fr.item.snippet,
      preview: fr.item.preview,
      path: fr.item.path,
      icon: fr.item.icon,
    } as SearchResultEntry));
  }

  /** Merges backend and local results, de-duplicated by kind+identity. */
  private mergeResults(backend: SearchResultEntry[], local: SearchResultEntry[]): SearchResultEntry[] {
    const seen = new Set<string>();
    const merged = [...backend];
    for (const item of backend) {
      seen.add(`${item.kind}:${item.session_id || item.path || item.name || item.snippet}`);
    }
    for (const item of local) {
      const key = `${item.kind}:${item.path || item.name || item.snippet}`;
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
      const items = results.filter(r => r.kind === kind);
      if (items.length === 0) continue;
      const def = SECTION_DEFS[kind] || SECTION_DEFS["file"];
      sections.push({
        ...def,
        items,
      });
      seenKinds.add(kind);
    }
    const other = results.filter(r => !seenKinds.has(r.kind));
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
