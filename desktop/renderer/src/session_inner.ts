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
 * Session-inner sidebar.
 *
 * The resizable right-hand sidebar shown inside a session: a draggable tab bar
 * hosting an info/summary panel plus dynamically-opened panels (terminal,
 * code editor, file review, agent, �?, each with its own embedded xterm
 * terminal instances. Width is persisted to `localStorage`.
 */

import { getState, subscribe, addAttachments, showToast } from "./state.js";
import type { ArtifactItem, AttachmentMeta, ReferenceItem } from "./types.js";
import { getFileIcon } from "./files.js";
import { t, onLocaleChange } from "./i18n.js";
import { send } from "./ws.js";
import { getMonaco, monacoLang, registerEditor, unregisterEditor } from "./monaco.js";

import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebglAddon } from "@xterm/addon-webgl";
import { renderDiffHtml, setupSplitViewScrollSync } from "./diff_render.js";
import { showContextMenu } from "./context-menu.js";
import { BrowserView } from "./browser.js";
import { getDefaultHomepage } from "./browser.js";
import { MarkdownPreviewView } from "./markdown_preview.js";
import { MediaViewer } from "./media-viewer.js";

/** Definition of a sidebar tab. */
export interface TabDef {
  id: string;            /** unique instance ID: "terminal-1", "browser-1", "editor", "review" */
  type: string;          /** panel type: "terminal" | "editor" | "review" | "browser" | "markdown" */
  label: string;         /** display label shown in the tab bar */
  closable: boolean;
  shellPath?: string;    /** for terminal tabs */
  shellArgs?: string[];  /** for terminal tabs */
  startUrl?: string;     /** for browser tabs */
  favicon?: string;      /** for browser tabs: favicon URL from the page */
  content?: string;      /** for markdown tabs: initial markdown content */
  title?: string;        /** for markdown tabs: preview title */
   filePath?: string;     /** for editor/markdown tabs: file path */
}

const TABS_STORAGE_KEY = "session-sidebar-tabs";

function _loadTabs(): TabDef[] {
  try {
    const raw = localStorage.getItem(TABS_STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}
  return [];
}
function _saveTabs(tabs: TabDef[]): void {
  try { localStorage.setItem(TABS_STORAGE_KEY, JSON.stringify(tabs.map(t => ({id: t.id, type: t.type, label: t.label, closable: t.closable})))); } catch {}
}

interface NewTabOption {
  id: string;
  icon: string;
}

const NEW_TAB_OPTIONS: NewTabOption[] = [
  { id: "terminal", icon: "terminal" },
  { id: "editor", icon: "code-2" },
  { id: "review", icon: "eye" },
  { id: "browser", icon: "globe" },
];

function tabLabel(id: string): string {
  switch (id) {
    case "terminal": return t("sessionInner.tabTerminal");
    case "editor": return t("sessionInner.tabEditor");
    case "review": return t("sessionInner.tabReview");
    case "browser": return t("sessionInner.tabBrowser");
    case "markdown": return t("sessionInner.tabMarkdown");
    case "code": return t("sessionInner.tabCode");
    case "media": return t("sessionInner.tabMedia");
    default: return id;
  }
}

function termIcon(shellPath?: string): string {
  if (!shellPath) return "terminal";
  const name = shellPath.split(/[/\\]/).pop()?.toLowerCase().replace(/\.(exe|cmd|bat)$/, "") || "";
  if (name.includes("powershell") || name === "pwsh") return "terminal";
  if (name === "cmd") return "monitor";
  if (name.includes("wsl")) return "linux";
  if (name === "bash" || name === "zsh" || name === "sh") return "terminal";
  return "terminal";
}

function tabIcon(type: string, shellPath?: string): string {
  if (type === "terminal") return termIcon(shellPath);
  switch (type) {
    case "editor": return "code-2";
    case "review": return "eye";
    case "browser": return "globe";
    case "markdown": return "file-text";
    case "code": return "file-text";
    case "media": return "image";
    default: return "square";
  }
}

function getTerminalAllText(term: any): string {
  try {
    const buffer = term.buffer?.active;
    if (!buffer || typeof buffer.length !== "number") return "";
    const lines: string[] = [];
    for (let y = 0; y < buffer.length; y++) {
      const line = buffer.getLine(y);
      if (line && typeof line.translateToString === "function") {
        lines.push(line.translateToString());
      }
    }
    return lines.join("\n");
  } catch { return ""; }
}

/**
 * Manages the session-inner sidebar tabs, panels and embedded terminals.
 */
export class SessionInner {
  private el: HTMLElement;
  private tabBar: HTMLElement;
  private tabList: HTMLElement;
  private tabBody: HTMLElement;
  private infoBody!: HTMLElement;
  private tabAddBtn: HTMLButtonElement | null = null;
  private tabAddDropdown: HTMLDivElement | null = null;
  private tabAddDocClickHandler: ((e: MouseEvent) => void) | null = null;
  private tabs: TabDef[] = [];
  private activeTab: string = "";
  private _sessionTabs = new Map<string, TabDef[]>();
  private _sessionTerminals = new Map<string, Map<string, Array<{ ptyId: number; term: any; cleanup: () => void; resizeObs: ResizeObserver }>>>();
  private _sessionTermActiveIdx = new Map<string, Map<string, number>>();
  private _sessionSidebarVisible = new Map<string, boolean>();
  private _sessionBrowsers = new Map<string, Map<string, BrowserView>>();

  private _sessionReviewState = new Map<string, { filter: string; mode: "git" | "artifact"; artifact: ArtifactItem | null; filePending: string | undefined }>();
  /** Key used for storing sidebar tabs: "session:<sid>" or "workspace:<path>". */
  private _tabKey = "";

  /** Build the storage key: session-level in normal mode, workspace-level in ws mode. */
  private _tabStorageKey(): string {
    const s = getState();
    if (s.activeWorkspace) return "ws:" + s.activeWorkspace;
    return "session:" + (s.sessionId || "");
  }

  /** React to state changes: swap tab + terminal state on session/workspace
   * switches, and refresh the live info panels when the same session mutates
   * (plan items, artifacts, references, etc.). */
  private _onStateChange(): void {
    const newKey = this._tabStorageKey();
    if (newKey === this._tabKey) {
      // Same session/workspace but state mutated (e.g. plan progress, new
      // artifacts, references). Keep the info panels live without rebuilding
      // the whole tab skeleton.
      if (this.activeTab === "info") {
        this.renderContent();
      }
      return;
    }

    // Save current state to old key.
    if (this._tabKey) {
      this._sessionTabs.set(this._tabKey, [...this.tabs]);
      // Only save visibility if sidebar is currently visible.
      // If hidden, the correct state was already saved by whoever hid it
      // (cleanupContentArea, closeSessionInnerSidebar, or session menu button).
      const _panel = document.getElementById("session-inner-sidebar");
      if (_panel && !_panel.classList.contains("hidden")) {
        this.saveSidebarVisibility();
      }
      // Deep-copy terminals map so each session gets its own Map instance.
      const termCopy = new Map<string, Array<{ ptyId: number; term: any; cleanup: () => void; resizeObs: ResizeObserver }>>();
      for (const [k, arr] of this.panelTerminals) {
        termCopy.set(k, [...arr]);
      }
      this._sessionTerminals.set(this._tabKey, termCopy);
      this._sessionTermActiveIdx.set(this._tabKey, new Map(this.panelActiveTermIdx));
      const browserCopy = new Map<string, BrowserView>();
      for (const [k, bv] of this.panelBrowsers) {
        browserCopy.set(k, bv);
      }
      this._sessionBrowsers.set(this._tabKey, browserCopy);

      this._sessionReviewState.set(this._tabKey, {
        filter: this._reviewFilter,
        mode: this._reviewMode,
        artifact: this._reviewArtifact,
        filePending: this._reviewFilePending,
      });
    }
    this._tabKey = newKey;

    // Restore terminals for the new key, or create fresh.
    const restoredTerminals = this._sessionTerminals.get(newKey);
    const restoredActiveIdx = this._sessionTermActiveIdx.get(newKey);
    this.panelTerminals = restoredTerminals ?? new Map();
    this.panelActiveTermIdx = restoredActiveIdx ?? new Map();
    const restoredBrowsers = this._sessionBrowsers.get(newKey);
    this.panelBrowsers = restoredBrowsers ?? new Map();

    const savedReview = this._sessionReviewState.get(newKey);
    if (savedReview) {
      this._reviewFilter = savedReview.filter;
      this._reviewMode = savedReview.mode;
      this._reviewArtifact = savedReview.artifact;
      this._reviewFilePending = savedReview.filePending;
    } else {
      const hasWs = !!getState().activeWorkspace;
      this._reviewFilter = hasWs ? "all" : "lastRound";
      this._reviewMode = hasWs ? "git" : "artifact";
      this._reviewArtifact = null;
      this._reviewFilePending = undefined;
    }

    const restored = this._sessionTabs.get(newKey);
    if (restored) {
      this.tabs = restored;
    } else {
      this.tabs = [];
    }
    this.activeTab = this.tabs.length > 0 ? this.tabs[0].id : "";
    // Force panels to re-render so terminal panel reflects restored state.
    this.tabBody.querySelectorAll(".tab-panel").forEach((p) => p.remove());
    this.renderTabs();
    this.render();
    this.restoreSidebarVisibility();
  }

  /* tab drag */
  private dragEl: HTMLElement | null = null;
  private dragIdx: number = -1;
  private dragStartX: number = 0;
  private dragOverIdx: number = -1;
  private dragBound = false;
  private wasDragged = false;

  /* width persistence */
  private sidebarWidth = 280;

  /* resize */
  private resizing = false;
  private resizeStartX = 0;
  private resizeStartW = 0;

  /* terminals �� each panel can have multiple sub-terminals */
  private panelTerminals = new Map<string, Array<{ ptyId: number; term: any; cleanup: () => void; resizeObs: ResizeObserver }>>();
  private panelActiveTermIdx = new Map<string, number>();
  private panelShellPath = new Map<string, string>();
  private panelShellArgs = new Map<string, string[]>();
  private panelBrowsers = new Map<string, BrowserView>();
  private panelMarkdownPreviews = new Map<string, MarkdownPreviewView>();
  private panelCodeEditors = new Map<string, any>();
  private panelMediaViewers = new Map<string, MediaViewer>();
  private _terminalCounter = 0;
  private _browserCounter = 0;
  private _markdownCounter = 0;
  private _codeCounter = 0;
  private _mediaCounter = 0;
  private _editorCounter = 0;
  private _availableShells: Array<{ name: string; path: string; args?: string[] }> = [];
  private _shellsLoaded = false;
/**
   * Constructor: resolves DOM nodes, restores width and wires tabs/resize.
   */
  constructor() {
    this.el = document.getElementById("session-inner-sidebar")!;
    this.tabBar = this.el.querySelector(".tab-bar")!;
    this.tabList = document.createElement("div");
    this.tabList.className = "header-tabs";
    this.tabBody = this.el.querySelector(".tab-body")!;

    // Start empty �?the home page (terminal/editor/review cards) shows.
    this.tabs = [];
    this.activeTab = "";

    try {
      const saved = localStorage.getItem("session-sidebar-width");
      if (saved) this.sidebarWidth = parseInt(saved, 10) || 280;
    } catch {}
    this.el.style.setProperty("--sidebar-w", this.sidebarWidth + "px");
    document.getElementById("main-body")?.style.setProperty("--sidebar-w", this.sidebarWidth + "px");

    subscribe(() => this._onStateChange());
    onLocaleChange(() => this.render());
    this.renderTabs();
    this.bindAddButton();
    this.bindResize();

    // Auto-open sidebar + browser tab when the model uses the browser tool
    window.addEventListener("browser-tool-call", () => {
      const panel = document.getElementById("session-inner-sidebar");
      const mainBody = document.getElementById("main-body");
      if (panel && mainBody && panel.classList.contains("hidden")) {
        panel.classList.remove("hidden");
        mainBody.classList.remove("sidebar-hidden");
        document.getElementById("app")?.classList.add("sidebar-collapsed");
        this.saveSidebarVisibility();
      }
      // Only create a browser tab if none exists yet, so the model
      // operates the same webview across multiple tool calls
      const existingBrowser = this.tabs.find(t => t.type === "browser");
      if (!existingBrowser) {
        this.createTab("browser");
      }
    });

    window.addEventListener("info-html-open", ((e: CustomEvent) => {
      const { url } = e.detail;
      if (!url) return;
      // Ensure sidebar is visible
      const panel = document.getElementById("session-inner-sidebar");
      const mainBody = document.getElementById("main-body");
      if (panel && mainBody && panel.classList.contains("hidden")) {
        panel.classList.remove("hidden");
        mainBody.classList.remove("sidebar-hidden");
        document.getElementById("app")?.classList.add("sidebar-collapsed");
        this.saveSidebarVisibility();
      }
      // Reuse existing browser tab or create one
      const existing = this.tabs.find(t => t.type === "browser");
      if (existing) {
        this.activateTab(existing.id);
        const bv = this.panelBrowsers.get(existing.id);
        if (bv) bv.navigate(url);
      } else {
        this.createTab("browser", { startUrl: url });
      }
    }) as EventListener);
  }

  /** Re-renders the active tab's content (reactive to state/locale). */
  render(): void {
    if (this.tabs.length === 0) {
      this.renderHomePage();
    }
    if (this.activeTab === "info") this.renderContent();
    const agentPanel = this.tabBody.querySelector('.tab-panel[data-panel="agent"]') as HTMLElement | null;
    if (agentPanel) {
      this.renderAgentPanel(agentPanel);
    }
  }

  renderForce(): void {
    // When re-opening the sidebar, the .tab-panel elements were removed from
    // DOM by resetToDefaultTabs. Re-render tab state so panels come back.
    if (this.tabs.length === 0) {
      this.renderHomePage();
    } else {
      // Re-bind events and let renderTabs recreate panels.
      this.renderTabs();
    }
    if (this.activeTab === "info") this.renderContent();
    const agentPanel = this.tabBody.querySelector('.tab-panel[data-panel="agent"]') as HTMLElement | null;
    if (agentPanel) {
      this.renderAgentPanel(agentPanel);
    }
  }

  /* ── Tab Management ─────────────────────────────────────────────── */

  private async renderTabs(): Promise<void> {
    this.tabList.innerHTML = this.tabs.map((tab) => {
      const activeCls = tab.id === this.activeTab ? " active" : "";
      const closeBtn = tab.closable
        ? `<span class="tab-close"><svg viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none"/></svg></span>`
        : "";
      let iconHtml: string;
      if (tab.type === "browser" && tab.favicon) {
        iconHtml = `<img class="tab-favicon" src="${this.esc(tab.favicon)}" alt="" onerror="this.style.display='none';this.nextElementSibling.style.display=''"/><i data-lucide="globe" class="lucide lucide-xs" style="margin-right:4px;flex-shrink:0;display:none"></i>`;
      } else if (tab.type === "code" || tab.type === "markdown") {
        iconHtml = `<img src="${getFileIcon(tab.label)}" class="icon" style="width:14px;height:14px;margin-right:4px;flex-shrink:0">`;
      } else {
        iconHtml = `<i data-lucide="${tabIcon(tab.type, tab.shellPath)}" class="lucide lucide-xs" style="margin-right:4px;flex-shrink:0"></i>`;
      }
      return `<button class="tab${activeCls}" data-tab="${tab.id}" draggable="true">
        ${iconHtml}
        <span class="tab-label">${this.esc(tab.label)}</span>${closeBtn}
      </button>`;
    }).join("");

    if (!this.tabBar.contains(this.tabList)) {
      this.tabBar.prepend(this.tabList);
    }

    this.bindTabEvents();
    if (this.tabs.length === 0) {
      this.renderHomePage();
    } else {
      const homeEl = this.tabBody.querySelector(".si-home");
      if (homeEl) homeEl.remove();
      await this.renderPanels();
    }
    this.refreshLucide();
  }

  private refreshLucide(): void {
    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.tabBar });
    }
  }

  private bindAddButton(): void {
    this.tabAddBtn?.remove();
    this.tabAddDropdown?.remove();
    if (this.tabAddDocClickHandler) {
      document.removeEventListener("click", this.tabAddDocClickHandler);
      this.tabAddDocClickHandler = null;
    }

    const btn = document.createElement("button");
    btn.className = "tab-add-btn";
    btn.dataset.tooltip = t("sessionInner.newTab");
    btn.innerHTML = `<i data-lucide="plus" class="lucide lucide-sm"></i>`;
    this.tabBar.appendChild(btn);
    this.tabAddBtn = btn;

    const dropdown = document.createElement("div");
    dropdown.className = "tab-add-dropdown hidden";
    document.body.appendChild(dropdown);
    this.tabAddDropdown = dropdown;

    const rebuildDropdown = () => {
      const openTypes = new Set(this.tabs.map((tab) => tab.type));
      const available = NEW_TAB_OPTIONS.filter((opt) => {
        if (opt.id === "terminal" || opt.id === "browser") return true;
        return !openTypes.has(opt.id);
      });
      if (available.length === 0) {
        dropdown.innerHTML = `<div class="tab-add-empty">${t("sessionInner.newTabEmpty")}</div>`;
      } else {
        dropdown.innerHTML = available.map((opt) => {
          return `<div class="tab-add-item" data-add="${opt.id}">
            <i data-lucide="${opt.icon}" class="lucide lucide-sm"></i>
            <span>${this.esc(tabLabel(opt.id))}</span>
          </div>`;
        }).join("");
        dropdown.querySelectorAll(".tab-add-item").forEach((item) => {
          item.addEventListener("click", async (e) => {
            e.stopPropagation();
            const type = (item as HTMLElement).dataset.add!;
            if (type === "terminal") {
              await this._showShellSelector(btn);
            } else {
              await this.createTab(type);
            }
            dropdown.classList.add("hidden");
          });
        });
      }
    };

    const toggle = () => {
      const isHidden = dropdown.classList.toggle("hidden");
      if (!isHidden) {
        rebuildDropdown();
        const rect = btn.getBoundingClientRect();
        dropdown.style.top = (rect.bottom + 4) + "px";
        dropdown.style.right = (window.innerWidth - rect.right + 4) + "px";
        if (typeof (window as any).lucide !== "undefined") {
          (window as any).lucide.createIcons({ root: dropdown });
        }
      }
    };

    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggle();
    });

    this.tabAddDocClickHandler = (e: MouseEvent) => {
      if (!btn.contains(e.target as Node) && !dropdown.contains(e.target as Node)) {
        dropdown.classList.add("hidden");
      }
    };
    document.addEventListener("click", this.tabAddDocClickHandler);
  }

  private async _showShellSelector(anchor: HTMLElement): Promise<void> {
    const api = (window as any).electronAPI;
    if (!api) {
      await this.createTab("terminal");
      return;
    }
    if (!this._shellsLoaded) {
      try {
        this._availableShells = await api.terminalListShells();
        this._shellsLoaded = true;
      } catch {
        this._availableShells = [];
      }
    }
    if (this._availableShells.length === 0) {
      this._availableShells.push({ name: "Default", path: "" });
    }
    if (this._availableShells.length === 1) {
      const s = this._availableShells[0];
      await this.createTab("terminal", { shellPath: s.path, shellArgs: s.args });
      return;
    }

    const shellDropdown = document.createElement("div");
    shellDropdown.className = "tab-add-dropdown hidden";
    document.body.appendChild(shellDropdown);

    const rect = anchor.getBoundingClientRect();
    shellDropdown.style.top = (rect.bottom + 4) + "px";
    shellDropdown.style.right = (window.innerWidth - rect.right + 4) + "px";
    shellDropdown.style.maxHeight = Math.min(240, window.innerHeight - rect.bottom - 40) + "px";
    shellDropdown.style.overflowY = "auto";
    shellDropdown.innerHTML = this._availableShells.map((s) => {
      return `<div class="tab-add-item" data-path="${this.esc(s.path)}" data-args="${this.esc(JSON.stringify(s.args || []))}" style="flex-direction:column;align-items:flex-start;gap:2px">
        <span>${this.esc(s.name)}</span>
        ${s.path ? `<span style="font-size:10px;color:var(--text-muted);font-family:var(--font-mono,monospace)">${this.esc(s.path)}</span>` : ""}
      </div>`;
    }).join("");
    shellDropdown.querySelectorAll(".tab-add-item").forEach((item) => {
      item.addEventListener("click", async () => {
        const el = item as HTMLElement;
        const sp = el.dataset.path || "";
        let sa: string[] = [];
        try { sa = JSON.parse(el.dataset.args || "[]"); } catch {}
        shellDropdown.remove();
        await this.createTab("terminal", { shellPath: sp, shellArgs: sa });
      });
    });
    shellDropdown.classList.remove("hidden");

    const closeHandler = (e: MouseEvent) => {
      if (!shellDropdown.contains(e.target as Node)) {
        shellDropdown.remove();
        document.removeEventListener("click", closeHandler);
      }
    };
    setTimeout(() => document.addEventListener("click", closeHandler), 0);
  }

  public getTabs(): TabDef[] {
    return this.tabs.slice();
  }

  public getActiveTab(): string {
    return this.activeTab;
  }

  /**
   * Tear down every dynamic tab/panel/terminal in the sidebar and restore
   * the default "info" tab.  Called from app.ts on session switch and
   * mode switch so terminals and editors from a previous session do not
   * leak into the next.
   */
  public async resetToDefaultTabs(): Promise<void> {
    // Hide panels from the DOM so the sidebar shows the home page.
    // Keep this.tabs intact so re-opening restores everything.
    this.tabBody.querySelectorAll(".tab-panel").forEach((p) => p.remove());
    this.tabBody.innerHTML = "";
    this.activeTab = "";
    await this.renderTabs();
    this.bindAddButton();
  }

  private renderHomePage(): void {
    // Remove any leftover panels
    this.tabBody.querySelectorAll(".tab-panel").forEach((p) => p.remove());

    const cards = [
      { id: "terminal", icon: "terminal", label: t("sessionInner.tabTerminal"), desc: t("sessionInner.tabTerminalDesc") },
      { id: "editor", icon: "code-2", label: t("sessionInner.tabEditor"), desc: t("sessionInner.tabEditorDesc") },
      { id: "review", icon: "eye", label: t("sessionInner.tabReview"), desc: t("sessionInner.tabReviewDesc") },
      { id: "browser", icon: "globe", label: t("sessionInner.tabBrowser"), desc: t("sessionInner.tabBrowserDesc") },
    ];

    this.tabBody.innerHTML = `<div class="si-home">${cards.map((c) => `
      <div class="si-home-card" data-tab="${c.id}">
        <i data-lucide="${c.icon}" class="lucide si-home-icon"></i>
        <div class="si-home-info">
          <div class="si-home-label">${this.esc(c.label)}</div>
          <div class="si-home-desc">${this.esc(c.desc)}</div>
        </div>
        <i data-lucide="chevron-right" class="lucide si-home-arrow"></i>
      </div>
    `).join("")}</div>`;

    this.tabBody.querySelectorAll(".si-home-card").forEach((el) => {
      el.addEventListener("click", () => {
        const type = (el as HTMLElement).dataset.tab!;
        if (type === "terminal") {
          this._showShellSelector(this.tabAddBtn || this.el);
        } else {
          this.createTab(type);
        }
      });
    });

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.tabBody });
    }
  }

  public async createTab(type: string, opts?: { shellPath?: string; shellArgs?: string[]; startUrl?: string; content?: string; title?: string; filePath?: string }): Promise<void> {
    let id: string;
    let label: string;
    if (type === "terminal") {
      this._terminalCounter++;
      id = `terminal-${this._terminalCounter}`;
      const shellName = opts?.shellPath ? opts.shellPath.split(/[/\\]/).pop()?.replace(/\.(exe|cmd|bat)$/i, "") || "Terminal" : "Terminal";
      label = `${shellName} ${this._terminalCounter}`;
    } else if (type === "browser") {
      this._browserCounter++;
      id = `browser-${this._browserCounter}`;
      label = t("sessionInner.tabBrowser");
    } else if (type === "markdown") {
      this._markdownCounter++;
      id = `markdown-${this._markdownCounter}`;
      label = opts?.title || t("sessionInner.tabMarkdown");
    } else if (type === "editor") {
      this._editorCounter = (this._editorCounter || 0) + 1;
      id = `editor-${this._editorCounter}`;
      const fileName = opts?.filePath ? opts.filePath.split(/[/\\]/).pop() || opts.filePath : "Editor";
      label = fileName;
    } else if (type === "code") {
      this._codeCounter++;
      id = `code-${this._codeCounter}`;
      label = opts?.title || t("sessionInner.tabCode");
    } else if (type === "media") {
      this._mediaCounter++;
      id = `media-${this._mediaCounter}`;
      label = opts?.title || t("sessionInner.tabMedia");
    } else {
      id = type;
      label = tabLabel(type);
    }
    const tab: TabDef = { id, type, label, closable: true };
    if (opts?.shellPath !== undefined) tab.shellPath = opts.shellPath;
    if (opts?.shellArgs !== undefined) tab.shellArgs = opts.shellArgs;
    if (opts?.startUrl !== undefined) tab.startUrl = opts.startUrl;
    if (opts?.content !== undefined) tab.content = opts.content;
    if (opts?.title !== undefined) tab.title = opts.title;
    if (opts?.filePath !== undefined) tab.filePath = opts.filePath;
    this.tabs.push(tab);
    _saveTabs(this.tabs);
    this.activeTab = id;
    await this.renderTabs();
  }

  private async renderPanels(): Promise<void> {
    const existingIds = new Set<string>();
    this.tabBody.querySelectorAll(".tab-panel").forEach((p) => {
      existingIds.add((p as HTMLElement).dataset.panel || "");
    });

    for (const t of this.tabs) {
      if (existingIds.has(t.id)) continue;
      const panel = document.createElement("div");
      panel.className = "tab-panel" + (t.id === this.activeTab ? " active" : "");
      panel.dataset.panel = t.id;
      panel.dataset.type = t.type;

      if (t.type === "terminal") {
        await this.setupTerminalPanel(panel, t.id, t.shellPath, t.shellArgs);
      } else if (t.type === "editor") {
        this.setupEditorPanel(panel);
      } else if (t.type === "review") {
        this.setupReviewPanel(panel);
      } else if (t.type === "browser") {
        this.setupBrowserPanel(panel, t.id, t.startUrl);
      } else if (t.type === "markdown") {
        this.setupMarkdownPanel(panel, t.id, t.content, t.title, t.filePath);
      } else if (t.type === "binary") {
        this.setupBinaryPanel(panel, t.filePath!);
      } else if (t.type === "code") {
        await this.setupCodePanel(panel, t.id, t.content || "", t.filePath || "");
      } else if (t.type === "media") {
        this.setupMediaPanel(panel, t.id, t.filePath || "");
      }

      this.tabBody.appendChild(panel);
    }

    this.tabBody.querySelectorAll(".tab-panel").forEach((p) => {
      const pid = (p as HTMLElement).dataset.panel || "";
      const ptype = (p as HTMLElement).dataset.type || "";
      const exists = this.tabs.some((t) => t.id === pid);
      if (!exists) {
        if (ptype === "terminal") {
          const terms = this.panelTerminals.get(pid);
          if (terms) {
            for (const trm of terms) {
              trm.cleanup();
              trm.resizeObs.disconnect();
              trm.term.dispose();
              const api = (window as any).electronAPI;
              if (api) api.terminalKill(trm.ptyId);
            }
            this.panelTerminals.delete(pid);
            this.panelActiveTermIdx.delete(pid);
          }
          const dd = document.querySelector(".si-term-shell-dropdown");
          if (dd) dd.remove();
        }
        if (ptype === "browser") {
          const bv = this.panelBrowsers.get(pid);
          if (bv) {
            bv.destroy();
            this.panelBrowsers.delete(pid);
          }
        }
        if (ptype === "markdown") {
          const mp = this.panelMarkdownPreviews.get(pid);
          if (mp) {
            mp.destroy();
            this.panelMarkdownPreviews.delete(pid);
          }
        }
        if (ptype === "code") {
          const editor = this.panelCodeEditors.get(pid);
          if (editor) {
            unregisterEditor(editor);
            editor.dispose();
            this.panelCodeEditors.delete(pid);
          }
        }
        if (ptype === "media") {
          const mv = this.panelMediaViewers.get(pid);
          if (mv) {
            mv.destroy();
            this.panelMediaViewers.delete(pid);
          }
        }
        p.remove();
      } else {
        p.classList.toggle("active", pid === this.activeTab);
      }
    });
  }

  /* ── Terminal ───────────────────────────────────────────────────── */

  private async setupTerminalPanel(panel: HTMLElement, tabId: string, shellPath?: string, shellArgs?: string[]): Promise<void> {
    panel.innerHTML = `<div class="si-terminal-wrap">
      <div class="si-terminal-body"></div>
    </div>`;

    const body = panel.querySelector(".si-terminal-body") as HTMLElement;
    const panelId = tabId;

    if (this.panelTerminals.has(panelId) && (this.panelTerminals.get(panelId)?.length || 0) > 0) {
      const terms = this.panelTerminals.get(panelId)!;
      for (const trm of terms) {
        if (trm.term?.element) {
          body.appendChild(trm.term.element);
        }
      }
      if (terms[0]) {
        try { terms[0].term.focus(); } catch {}
      }
      this._bindTerminalTheme(panelId, panel);
      return;
    }

    if (!this.panelTerminals.has(panelId)) {
      this.panelTerminals.set(panelId, []);
      this.panelActiveTermIdx.set(panelId, 0);
    }

    const api = (window as any).electronAPI;
    if (!api) {
      body.innerHTML = `<div class="si-empty">${t("sessionInner.termNotAvailable")}</div>`;
      return;
    }

    let shells: Array<{ name: string; path: string; args?: string[] }>;
    try {
      shells = await api.terminalListShells();
    } catch {
      shells = [];
    }
    if (shells.length === 0) {
      shells.push({ name: "Default", path: "" });
    }

    const getShellPath = () => shellPath || shells[0]?.path || "";
    const getShellArgs = () => shellArgs || shells[0]?.args || [];

    const buildTheme = () => {
      const st = getState();
      const isLight = st.theme === "light";
      return isLight ? {
        background: "#ffffff", foreground: "#1a1a1a", cursor: "#1a1a1a",
        selectionBackground: "rgba(0,0,0,0.10)",
        black: "#000000", red: "#cd3131", green: "#00bc00",
        yellow: "#949800", blue: "#0451a5", magenta: "#bc05bc",
        cyan: "#0598bc", white: "#555555",
        brightBlack: "#666666", brightRed: "#cd3131", brightGreen: "#14ce14",
        brightYellow: "#b5ba00", brightBlue: "#0451a5", brightMagenta: "#bc05bc",
        brightCyan: "#0598bc", brightWhite: "#a5a5a5",
      } : {
        background: "#000000", foreground: "#f5f5f7", cursor: "#f5f5f7",
        selectionBackground: "rgba(255,255,255,0.15)",
        black: "#000000", red: "#cd3131", green: "#0dbc79",
        yellow: "#e5e510", blue: "#2472c8", magenta: "#bc3fbc",
        cyan: "#11a8cd", white: "#e5e5e5",
        brightBlack: "#666666", brightRed: "#f14c4c", brightGreen: "#23d18b",
        brightYellow: "#f5f543", brightBlue: "#3b8eea", brightMagenta: "#d670d6",
        brightCyan: "#29b8db", brightWhite: "#ffffff",
      };
    };
    const applyTheme = (term: any) => { term.options.theme = buildTheme(); };

    const sh = getShellPath();
    const args = getShellArgs();
    let ptyId: number;
    try {
      const result = await api.terminalSpawn(sh || undefined, args.length ? args : undefined);
      if (result.error) {
        body.innerHTML = `<div class="si-empty">${t("sessionInner.termError")}: ${this.esc(result.error)}</div>`;
        return;
      }
      ptyId = result.id as number;
    } catch (e: any) {
      body.innerHTML = `<div class="si-empty">${t("sessionInner.termError")}: ${this.esc(e?.message || String(e))}</div>`;
      return;
    }

    const term = new Terminal({
      cursorBlink: true,
      cursorStyle: "bar",
      fontSize: 12.5,
      fontFamily: '"Cascadia Code", "JetBrains Mono", "Fira Code", "Cascadia Mono", Consolas, monospace',
      lineHeight: 1.3,
      theme: buildTheme(),
      cols: 60,
      rows: 16,
      allowProposedApi: true,
      allowTransparency: false,
      scrollback: 5000,
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);

    try {
      const webglAddon = new WebglAddon();
      term.loadAddon(webglAddon);
    } catch {}

    term.open(body);

    term.attachCustomKeyEventHandler((e) => {
      const mod = e.ctrlKey || e.metaKey;
      if (mod && (e.key === "c" || e.key === "C")) {
        if (term.hasSelection()) {
          e.preventDefault();
          navigator.clipboard.writeText(term.getSelection()).catch(() => {});
          return false;
        }
        return true;
      }
      if (mod && (e.key === "v" || e.key === "V")) {
        e.preventDefault();
        navigator.clipboard.readText().then((text) => term.paste(text)).catch(() => {});
        return false;
      }
      if (e.key === "Insert") {
        if (e.shiftKey) {
          e.preventDefault();
          navigator.clipboard.readText().then((text) => term.paste(text)).catch(() => {});
          return false;
        }
        if (e.ctrlKey && term.hasSelection()) {
          e.preventDefault();
          navigator.clipboard.writeText(term.getSelection()).catch(() => {});
          return false;
        }
      }
      return true;
    });

    /* context menu */
    const ctxMenu = document.createElement("div");
    ctxMenu.className = "context-menu hidden";
    ctxMenu.setAttribute("id", `term-ctx-menu-${tabId}`);
    ctxMenu.innerHTML = `
      <div class="context-menu-item" data-action="copy">${t("sessionInner.termCopy")}</div>
      <div class="context-menu-item" data-action="paste">${t("sessionInner.termPaste")}</div>
      <div class="context-menu-divider"></div>
      <div class="context-menu-item" data-action="send">${t("sessionInner.termSendToChat")}</div>`;
    document.body.appendChild(ctxMenu);
    let ctxTermTarget: any = null;

    term.element?.addEventListener("contextmenu", (ev: MouseEvent) => {
      ev.preventDefault();
      ctxTermTarget = term;
      showContextMenu(ctxMenu, ev.clientX, ev.clientY);
    });

    term.onData((data: string) => {
      api.terminalWrite(ptyId, data);
    });

    const dataCleanup = api.onTerminalData((d: { id: number; data: string }) => {
      if (d.id === ptyId) term.write(d.data);
    });
    const exitCleanup = api.onTerminalExit((d: { id: number }) => {
      if (d.id === ptyId) {
        term.write(`\r\n\x1b[33m${t("sessionInner.processExited")}\x1b[0m\r\n`);
      }
    });

    let resizeTimer: any = null;
    const obs = new ResizeObserver(() => {
      if (resizeTimer) return;
      resizeTimer = setTimeout(() => {
        resizeTimer = null;
        try {
          fitAddon.fit();
          const dims = (term as any)._core?._renderService?.dimensions;
          if (dims && dims.cols > 0 && dims.rows > 0) {
            api.terminalResize(ptyId, dims.cols, dims.rows);
          }
        } catch {}
      }, 50);
    });
    obs.observe(body);
    requestAnimationFrame(() => { try { fitAddon.fit(); } catch {} });

    term.focus();

    const cleanup = () => { dataCleanup(); exitCleanup(); ctxMenu.remove(); };
    const tms = this.panelTerminals.get(panelId) || [];
    tms.push({ ptyId, term, cleanup, resizeObs: obs });
    this.panelTerminals.set(panelId, tms);

    ctxMenu.querySelectorAll(".context-menu-item").forEach((item) => {
      item.addEventListener("click", () => {
        const action = (item as HTMLElement).dataset.action;
        if (action === "copy" && ctxTermTarget) {
          const sel = ctxTermTarget.getSelection();
          if (sel) navigator.clipboard.writeText(sel).catch(() => {});
        } else if (action === "paste" && ctxTermTarget) {
          navigator.clipboard.readText().then((text) => ctxTermTarget.paste(text)).catch(() => {});
        } else if (action === "send") {
          const content = getTerminalAllText(ctxTermTarget);
          if (content) {
            const shellName = sh.split(/[/\\]/).pop()?.replace(/\.(exe|cmd|bat)$/i, "") || "Terminal";
            const att: AttachmentMeta = {
              name: shellName,
              path: `terminal:${Date.now()}`,
              content,
              mime_type: "text/x-terminal",
              size: content.split("\n").length,
              is_binary: false,
            };
            addAttachments([att]);
          }
        }
        ctxMenu.classList.add("hidden");
        ctxTermTarget = null;
      });
    });
    document.addEventListener("click", (e) => {
      if (!ctxMenu.contains(e.target as Node)) {
        ctxMenu.classList.add("hidden");
      }
    });

    this._bindTerminalTheme(panelId, panel);

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: panel });
    }
  }

  private killSubTerminal: ((pid: string, idx: number, body: HTMLElement) => void) | undefined;

  private _bindTerminalTheme(panelId: string, panel: HTMLElement): void {
    const buildTheme = () => {
      const st = getState();
      const isLight = st.theme === "light";
      return isLight ? {
        background: "#ffffff", foreground: "#1a1a1a", cursor: "#1a1a1a",
        selectionBackground: "rgba(0,0,0,0.10)",
        black: "#000000", red: "#cd3131", green: "#00bc00",
        yellow: "#949800", blue: "#0451a5", magenta: "#bc05bc",
        cyan: "#0598bc", white: "#555555",
        brightBlack: "#666666", brightRed: "#cd3131", brightGreen: "#14ce14",
        brightYellow: "#b5ba00", brightBlue: "#0451a5", brightMagenta: "#bc05bc",
        brightCyan: "#0598bc", brightWhite: "#a5a5a5",
      } : {
        background: "#000000", foreground: "#f5f5f7", cursor: "#f5f5f7",
        selectionBackground: "rgba(255,255,255,0.15)",
        black: "#000000", red: "#cd3131", green: "#0dbc79",
        yellow: "#e5e510", blue: "#2472c8", magenta: "#bc3fbc",
        cyan: "#11a8cd", white: "#e5e5e5",
        brightBlack: "#666666", brightRed: "#f14c4c", brightGreen: "#23d18b",
        brightYellow: "#f5f543", brightBlue: "#3b8eea", brightMagenta: "#d670d6",
        brightCyan: "#29b8db", brightWhite: "#ffffff",
      };
    };
    const applyTheme = (term: any) => { term.options.theme = buildTheme(); };
    subscribe(() => {
      const terms = this.panelTerminals.get(panelId);
      if (terms) {
        for (const tt of terms) applyTheme(tt.term);
      }
    });
  }

  /* ── Review (Git Diff) ─────────────────────────────────────────── */

  private async setupReviewPanel(panel: HTMLElement): Promise<void> {
    panel.innerHTML = `<div class="si-review-toolbar">
      <div class="settings-dropdown-wrap">
        <button class="settings-dropdown-trigger" type="button">
          <span>${this.esc(t(getState().activeWorkspace ? "sessionInner.reviewAllChanges" : "sessionInner.reviewLastRound"))}</span>
          <i data-lucide="chevron-down" class="lucide settings-dropdown-chevron"></i>
        </button>
        <div class="settings-dropdown"></div>
      </div>
      <div class="settings-dropdown-wrap si-review-actions" style="margin-left:auto">
        <button class="settings-dropdown-trigger si-review-action-trigger" type="button">
          <i data-lucide="more-horizontal" class="lucide lucide-sm"></i>
        </button>
        <div class="settings-dropdown si-review-action-dropdown" style="right:0;left:auto;min-width:210px"></div>
      </div>
      <button class="settings-dropdown-trigger si-review-action-trigger si-review-collapse-btn" type="button" data-tooltip="${t("sessionInner.reviewCollapse")}">
        <i data-lucide="minus" class="lucide lucide-sm"></i>
      </button>
      <button class="settings-dropdown-trigger si-review-action-trigger si-review-split-btn" type="button" data-tooltip="${t("sessionInner.reviewSplitView")}">
        <i data-lucide="list" class="lucide lucide-sm"></i>
      </button>
      <div class="settings-dropdown-wrap si-review-actions si-review-git-wrap">
        <button class="settings-dropdown-trigger si-review-action-trigger si-review-git-trigger" type="button" data-tooltip="${t("sessionInner.reviewActionCommit")}">
          <i data-lucide="git-commit-horizontal" class="lucide lucide-sm si-review-git-icon"></i>
          <i data-lucide="chevron-down" class="lucide lucide-xs settings-dropdown-chevron"></i>
        </button>
        <div class="settings-dropdown si-review-git-dropdown" style="right:0;left:auto;min-width:170px"></div>
      </div>
</div>
<div class="si-review-commit-overlay hidden">
  <div class="search-palette">
    <div class="search-overlay-inner" style="align-items:flex-start">
      <i data-lucide="git-commit-horizontal" class="search-overlay-icon" style="margin-top:10px"></i>
      <textarea class="si-review-commit-input" placeholder="${this.esc(t("sessionInner.reviewCommitPrompt"))}" rows="2" style="flex:1;font-size:14px"></textarea>
      <kbd class="search-esc-hint" style="flex-shrink:0;margin-top:10px">${this.esc(t("sessionInner.reviewCommitBtn"))}</kbd>
    </div>
  </div>
</div>
<div class="si-panel-empty" style="display:none"></div>
<div class="si-review-wrap" style="display:none">
      <div class="si-review-body">
        <div class="si-review-diff"></div>
        <div class="si-review-divider"></div>
        <div class="si-review-tree"></div>
      </div>
    </div>`;

    // Initialize toolbar icons immediately (before load() completes)
    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: panel });
    }

    const diffEl = panel.querySelector(".si-review-diff") as HTMLElement;
    const treeEl = panel.querySelector(".si-review-tree") as HTMLElement;
    this._reviewDiffEl = diffEl;
    const modeWrap = panel.querySelector(".settings-dropdown-wrap") as HTMLElement;
    const toolbar = panel.querySelector(".si-review-toolbar") as HTMLElement;
    const modeTrigger = modeWrap.querySelector(".settings-dropdown-trigger") as HTMLElement;
    const modeLabel = modeTrigger.querySelector("span") as HTMLElement;
    const modeDropdown = modeWrap.querySelector(".settings-dropdown") as HTMLElement;
    const allDropdownWraps = panel.querySelectorAll(".settings-dropdown-wrap");
    const actionWrap = allDropdownWraps[1] as HTMLElement;
    const actionTrigger = actionWrap.querySelector(".settings-dropdown-trigger") as HTMLButtonElement;
    const actionDropdown = actionWrap.querySelector(".settings-dropdown") as HTMLElement;
    // Collapse / split / git-action buttons (added after the �?menu).
    const collapseBtn = panel.querySelector(".si-review-collapse-btn") as HTMLButtonElement;
    const splitBtn = panel.querySelector(".si-review-split-btn") as HTMLButtonElement;
    const gitWrap = panel.querySelector(".si-review-git-wrap") as HTMLElement;
    const gitTrigger = gitWrap.querySelector(".settings-dropdown-trigger") as HTMLButtonElement;
    const gitDropdown = gitWrap.querySelector(".settings-dropdown") as HTMLElement;
    const gitIcon = gitWrap.querySelector(".si-review-git-icon") as HTMLElement;
    // Inline commit input area.
    const commitWrap = document.getElementById("review-commit-overlay") as HTMLElement;
    const commitInput = document.getElementById("review-commit-input") as HTMLInputElement;
    // The toolbar stats element was removed (it duplicated the +/- counts
    // already shown in the diff header). Keep a no-op stub so the legacy
    // statsEl.innerHTML = ... assignments don't throw if re-added.
    const statsEl: { innerHTML: string } = (panel.querySelector(".si-review-stats") as HTMLElement | null)
      || { innerHTML: "" };
    const emptyEl = panel.querySelector(".si-panel-empty") as HTMLElement;
    const wrapEl = panel.querySelector(".si-review-wrap") as HTMLElement;

    const api = (window as any).electronAPI;
    const workspace = getState().activeWorkspace;

    interface StatusEntry {
      path: string;
      staged: string;
      unstaged: string;
    }

    let currentReviewPath: string | undefined;
    let cachedBranch = "";
    let cachedEntries: StatusEntry[] | null = null;

    const parseStatus = (output: string): { branch: string; entries: StatusEntry[] } => {
      const lines = output.split("\n").filter((l) => l.trim());
      let branch = "";
      const entries: StatusEntry[] = [];
      for (const line of lines) {
        if (line.startsWith("## ")) {
          branch = line.slice(3).split("...")[0].trim();
          continue;
        }
        if (line.length >= 3) {
          const staged = line[0];
          const unstaged = line[1];
          const path = line.slice(3).trim();
          // Skip directory entries (trailing / from git status)
          if (path && !path.endsWith("/")) entries.push({ path, staged, unstaged });
        }
      }
      return { branch, entries };
    };

    const fileIcon = (name: string): string => getFileIcon(name);

    const buildTree = (entries: StatusEntry[], activePath?: string): string => {
      const treeCacheKey = `${activePath || ""}\n` + entries.map((e) => `${e.staged}${e.unstaged}:${e.path}`).join("\n");
      const cachedTree = this._reviewTreeCache.get(treeCacheKey);
      if (cachedTree) return cachedTree;
      if (entries.length === 0) return `<div class="si-panel-empty">
        <i data-lucide="check-circle-2" class="lucide"></i>
        <div class="si-panel-empty-title">${t("sessionInner.reviewNoChanges")}</div>
        <div class="si-panel-empty-sub">${t("sessionInner.reviewNoChangesSub")}</div>
      </div>`;
      const groups = new Map<string, StatusEntry[]>();
      for (const e of entries) {
        const dir = e.path.includes("/") ? e.path.split("/")[0] : "(root)";
        if (!groups.has(dir)) groups.set(dir, []);
        groups.get(dir)!.push(e);
      }
      let html = "";
      for (const [dir, items] of groups) {
        html += `<div class="si-review-tree-group">
          <div class="si-review-tree-folder">
            <i data-lucide="folder" class="lucide lucide-xs"></i>
            <span>${this.esc(dir)}</span>
          </div>`;
        for (const item of items) {
          // Porcelain X column: "?" => untracked, non-space => staged, else unstaged.
          const isUntracked = item.staged === "?";
          const isStaged = !isUntracked && item.staged !== " ";
          const statusClass = isUntracked
            ? "si-review-untracked"
            : isStaged ? "si-review-staged" : "si-review-unstaged";
          // Single-letter badge (locale-independent): U/M/S.
          const statusLabel = isUntracked ? "U" : isStaged ? "S" : "M";
          const active = item.path === activePath ? " si-review-tree-file--active" : "";
          html += `<div class="si-review-tree-file${active}" data-path="${this.esc(item.path)}">
            <img src="${getFileIcon(item.path)}" class="icon" style="width:14px;height:14px">
            <span class="si-review-tree-name">${this.esc(item.path.split("/").pop() || item.path)}</span>
            <span class="si-review-tree-status ${statusClass}">${statusLabel}</span>
          </div>`;
        }
        html += `</div>`;
      }
      this._reviewTreeCache.set(treeCacheKey, html);
      return html;
    };

    const parseDiffFn = (cacheKey: string, output: string, cacheSalt = ""): string => {
      this._reviewDiffCache ??= new Map<string, string>();
      const saltedKey = cacheKey + cacheSalt;
      const cached = this._reviewDiffCache.get(saltedKey);
      if (cached) return cached;
      const parsed = this.parseDiff(output);
      this._reviewDiffCache.set(saltedKey, parsed);
      return parsed;
    };

    const computeStats = (entries: StatusEntry[], fileDiff?: string): { adds: number; dels: number; label: string } => {
      if (fileDiff) {
        let adds = 0;
        let dels = 0;
        for (const l of fileDiff.split("\n")) {
          if (l.startsWith("+") && !l.startsWith("+++")) adds++;
          if (l.startsWith("-") && !l.startsWith("---")) dels++;
        }
        return { adds, dels, label: "" };
      }
      const staged = entries.filter((e) => e.staged !== " " && e.staged !== "?").length;
      const untracked = entries.filter((e) => e.staged === "?").length;
      // Unstaged excludes untracked (X="?") so new files are not double-counted.
      const unstaged = entries.filter((e) => e.staged !== "?" && e.unstaged !== " ").length;
      const parts: string[] = [];
      if (staged) parts.push(`${t("sessionInner.reviewStaged")}: ${staged}`);
      if (unstaged) parts.push(`${t("sessionInner.reviewUnstaged")}: ${unstaged}`);
      if (untracked) parts.push(`${t("sessionInner.reviewUntracked")}: ${untracked}`);
      return {
        adds: staged,
        dels: unstaged,
        label: parts.join("  ") || t("sessionInner.reviewNoChanges"),
      };
    };

    const load = async (filePath?: string, forceRefresh = false) => {
      const requestSeq = ++this._reviewRequestSeq;
      const ws = getState().activeWorkspace;
      const showEmptyState = (html: string) => {
        if (requestSeq !== this._reviewRequestSeq) return;
        wrapEl.style.display = "none";
        emptyEl.style.display = "flex";
        emptyEl.innerHTML = html;
        toolbar.style.borderBottom = "none";
        statsEl.innerHTML = "";
        if (typeof (window as any).lucide !== "undefined") {
          (window as any).lucide.createIcons({ root: panel });
        }
      };

      // Update mode trigger label
      const labelMap: Record<string, string> = {
        all: t("sessionInner.reviewAllChanges"),
        unstaged: t("sessionInner.reviewUnstaged"),
        staged: t("sessionInner.reviewStaged"),
        branch: t("sessionInner.reviewBranch"),
        commit: t("sessionInner.reviewCommitChanges"),
        lastRound: t("sessionInner.reviewLastRound"),
      };
      modeLabel.textContent = labelMap[this._reviewFilter] || t("sessionInner.reviewLastRound");
      // Sync dropdown selections
      modeDropdown.querySelectorAll(".settings-dropdown-item").forEach((el) => {
        el.classList.toggle("selected", el.getAttribute("data-filter") === this._reviewFilter);
      });

      // lastRound filter: show artifacts from the most recent AI round
      if (this._reviewFilter === "lastRound") {
        const arts = getState().artifacts;
        if (arts.length === 0) {
          showEmptyState(`<i data-lucide="check-circle-2" class="lucide"></i>
            <div class="si-panel-empty-title">${t("sessionInner.reviewNoChanges")}</div>
            <div class="si-panel-empty-sub">${t("sessionInner.reviewNoChangesSub")}</div>`);
          return;
        }
        // Without a workspace the panel reviews every artifact the current
        // session produced (all changes); with one, "last round" stays scoped
        // to the most recent artifact group.
        let roundArts: ArtifactItem[];
        if (!ws) {
          roundArts = arts;
        } else {
          const groups = new Map<number, ArtifactItem[]>();
          for (const a of arts) {
            const key = a.created_at || 0;
            if (!groups.has(key)) groups.set(key, []);
            groups.get(key)!.push(a);
          }
          const sorted = [...groups.entries()].sort((a, b) => b[0] - a[0]);
          roundArts = sorted.length > 0 ? sorted[0][1] : arts;
        }
        if (requestSeq !== this._reviewRequestSeq) return;
        wrapEl.style.display = "flex";
        emptyEl.style.display = "none";
        toolbar.style.borderBottom = "";
        const targetPath = filePath || roundArts[0]?.path || "";
        const currentArtifact = roundArts.find((a: ArtifactItem) => a.path === targetPath) || null;
        diffEl.innerHTML = currentArtifact
          ? this.parseArtifactDiff(currentArtifact, targetPath)
          : `<div class="si-panel-empty"><i data-lucide="check-circle-2" class="lucide"></i><div class="si-panel-empty-title">${this.esc(t("sessionInner.reviewNoChanges"))}</div></div>`;
        treeEl.innerHTML = this.buildArtifactTree(roundArts, targetPath);
        const adds = currentArtifact?.diff_text ? (currentArtifact.diff_text.match(/^\+/gm) || []).length : 0;
        const dels = currentArtifact?.diff_text ? (currentArtifact.diff_text.match(/^-/gm) || []).length : 0;
        statsEl.innerHTML = `<span class="si-review-stat-add">+${adds}</span> <span class="si-review-stat-del">-${dels}</span>`;
        treeEl.querySelectorAll(".si-review-tree-file").forEach((el) => {
          el.addEventListener("click", () => {
            const path = (el as HTMLElement).dataset.path;
            if (path) load(path);
          });
        });
        if (typeof (window as any).lucide !== "undefined") {
          (window as any).lucide.createIcons({ root: panel });
        }
        return;
      }

      // (artifact/lastRound already handled above �?only git modes reach here)
      

      if (!ws) {
        showEmptyState(`<i data-lucide="git-pull-request" class="lucide"></i>
          <div class="si-panel-empty-title">${t("sessionInner.reviewNoChanges")}</div>
          <div class="si-panel-empty-sub">${t("workspace.empty")}</div>`);
        return;
      }
      if (!api) {
        showEmptyState(`<i data-lucide="alert-circle" class="lucide"></i>
          <div class="si-panel-empty-title">${t("sessionInner.apiNotAvailable")}</div>`);
        return;
      }

      // Show loading state before potentially slow git operations
      wrapEl.style.display = "flex";
      toolbar.style.borderBottom = "";
      emptyEl.style.display = "none";
      diffEl.innerHTML = `<div class="si-review-diff-loading">${t("sessionInner.reviewLoading")}</div>`;
      if (!cachedEntries || forceRefresh) {
        treeEl.innerHTML = "";
      }
      statsEl.innerHTML = `<span class="si-review-loading">${t("sessionInner.reviewLoading")}</span>`;

      if (!cachedEntries || forceRefresh) {
        const statusRes = await api.gitStatus(ws);
        if (requestSeq !== this._reviewRequestSeq) return;
        if (statusRes.error) {
            showEmptyState(`<i data-lucide="alert-triangle" class="lucide"></i>
              <div class="si-panel-empty-title">${this.esc(statusRes.error)}</div>`);
          return;
        }

        const { branch, entries } = parseStatus(statusRes.output);
        if (!branch && entries.length === 0) {
          showEmptyState(`<i data-lucide="folder-git-2" class="lucide"></i>
            <div class="si-panel-empty-title">${t("sessionInner.reviewNoGit")}</div>`);
          return;
        }
        cachedBranch = branch;
        cachedEntries = entries;
      }
      const entries = cachedEntries || [];
      const branch = cachedBranch;

      // Apply filter to entries
      let filteredEntries = entries;
      if (this._reviewFilter === "unstaged") {
        filteredEntries = entries.filter((e: StatusEntry) => e.unstaged !== " ");
      } else if (this._reviewFilter === "staged") {
        filteredEntries = entries.filter((e: StatusEntry) => e.staged !== " " && e.staged !== "?");
      }

      // When the current filter matches no entries, show an empty state
      // instead of closing the panel. Closing it (closeReviewTab) made the
      // panel "kick out" whenever the status cache lagged behind a fresh
      // `git add` (e.g. a newly staged file still read as unstaged), which
      // looked like staged files disappeared for no reason.
      if (filteredEntries.length === 0 && !filePath && this._reviewFilter !== "lastRound") {
        wrapEl.style.display = "none";
        emptyEl.style.display = "flex";
        emptyEl.innerHTML = `<i data-lucide="check-circle-2" class="lucide"></i>
          <div class="si-panel-empty-title">${t("sessionInner.reviewNoChanges")}</div>
          <div class="si-panel-empty-sub">${t("sessionInner.reviewNoChangesSub")}</div>`;
        statsEl.innerHTML = "";
        if (typeof (window as any).lucide !== "undefined") {
          (window as any).lucide.createIcons({ root: panel });
        }
        return;
      }

      // Show file tree
      treeEl.innerHTML = buildTree(filteredEntries, filePath);
      let adds = 0;
      let dels = 0;
      let statsLabel = "";

      if (filePath) {
        currentReviewPath = filePath;
        diffEl.innerHTML = `<div class="si-review-diff-loading">${t("sessionInner.reviewLoading")}</div>`;
        // Use gitDiffEx for staged/unstaged/branch/commit filters
        const isEx = this._reviewFilter === "all" || this._reviewFilter === "staged" || this._reviewFilter === "unstaged" || this._reviewFilter === "branch" || this._reviewFilter === "commit";
        const diffRes = isEx ? await api.gitDiffEx(ws, this._reviewFilter, filePath) : await api.gitDiff(ws, filePath);
        if (requestSeq !== this._reviewRequestSeq) return;
        if (diffRes.error) {
          diffEl.innerHTML = `<div class="si-empty">${this.esc(diffRes.error)}</div>`;
        } else {
          diffEl.innerHTML = parseDiffFn(`${ws}:${filePath}`, diffRes.output, String(this._reviewSplitView));
          setupSplitViewScrollSync(diffEl);
          ({ adds, dels } = computeStats(filteredEntries, diffRes.output));
        }
      } else {
        currentReviewPath = undefined;
        ({ adds, dels, label: statsLabel } = computeStats(filteredEntries));
        diffEl.innerHTML = `<div class="si-panel-empty"><i data-lucide="check-circle-2" class="lucide"></i><div class="si-panel-empty-title">${this.esc(t("sessionInner.reviewNoChanges"))}</div></div>`;
      }

      if (requestSeq !== this._reviewRequestSeq) return;
      // Summary view (no file selected) hides the staged/unstaged/untracked
      // counts - they were noisy and read like line stats. Per-file view still
      // shows +/- line counts.
      statsEl.innerHTML = statsLabel
        ? ""
        : `<span class="si-review-stat-add">+${adds}</span> <span class="si-review-stat-del">-${dels}</span>`;

      treeEl.querySelectorAll(".si-review-tree-file").forEach((el) => {
        el.addEventListener("click", () => {
          const path = (el as HTMLElement).dataset.path;
          if (path) load(path, false);
        });
      });

      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: panel });
      }
    };

    this._reviewLoad = load;

    // Build action dropdown items (right dropdown - functional actions).
    // refresh is a plain action; the rest are toggles with a checkmark.
    // Merged overflow buttons (collapse/split/git) are prepended at the top.
    const buildActionItems = () => {
      type Item = { action: string; icon: string; labelKey: string; toggle?: boolean; divider?: boolean };
      const items: Item[] = [];
      // Overflow: collapse(0), split(1), git(2) merged when _reviewOverflow > idx.
      const overflowDefs: Array<{ action: string; icon: string; labelKey: string }> = [
        { action: "_overflow_collapse", icon: "minus", labelKey: "reviewCollapse" },
        { action: "_overflow_split", icon: "list", labelKey: "reviewSplitView" },
        { action: "_overflow_git", icon: "git-commit-horizontal", labelKey: "reviewActionCommit" },
      ];
      for (let i = 0; i < this._reviewOverflow && i < overflowDefs.length; i++) {
        items.push(overflowDefs[i]);
      }
      if (this._reviewOverflow > 0) {
        items.push({ action: "_ov_div", icon: "", labelKey: "", divider: true });
      }
      items.push(
        { action: "refresh", icon: "refresh-cw", labelKey: "reviewRefresh" },
        { action: "wrap", icon: "wrap-text", labelKey: "reviewAutoWrap", toggle: true },
        { action: "_divider1", icon: "", labelKey: "", divider: true },
        { action: "fullFile", icon: "file-output", labelKey: "reviewNotFullFile", toggle: true },
        { action: "richText", icon: "layout-list", labelKey: "reviewRichText", toggle: true },
        { action: "wordDiff", icon: "diff", labelKey: "reviewWordDiff", toggle: true },
        { action: "hideWs", icon: "eraser", labelKey: "reviewHideWhitespace", toggle: true },
      );
      const isChecked = (a: string): boolean => {
        if (a === "wrap") return this._reviewWrap;
        if (a === "fullFile") return !this._reviewFullFile;
        if (a === "richText") return this._reviewRichText;
        if (a === "wordDiff") return this._reviewWordDiff;
        if (a === "hideWs") return this._reviewHideWs;
        return false;
      };
      actionDropdown.innerHTML = items.map((item) => {
        if (item.divider) {
          return `<div class="settings-dropdown-divider"></div>`;
        }
        const checked = item.toggle && isChecked(item.action) ? " checked" : "";
        return `<div class="settings-dropdown-item review-action-item${checked}" data-action="${item.action}">
          <i data-lucide="${item.icon}" class="lucide lucide-xs"></i>
          <span>${this.esc(t("sessionInner." + item.labelKey))}</span>
          <i data-lucide="check" class="lucide lucide-xs review-check"></i>
        </div>`;
      }).join("");
      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: actionDropdown });
      }
    };
    buildActionItems();

    // Responsive overflow: as the sidebar narrows, merge buttons into the �?
    // menu from left to right (collapse -> split -> git module). The �?menu
    // and the mode selector are always kept. Button sizes never change.
    const setOverflow = (count: number) => {
      const n = Math.max(0, Math.min(3, count));
      if (n === this._reviewOverflow) return;
      this._reviewOverflow = n;
      // In normal mode (no workspace) all buttons stay hidden.
      const hasWs = !!getState().activeWorkspace;
      collapseBtn.style.display = hasWs && n <= 0 ? "" : "none";
      splitBtn.style.display = hasWs && n <= 1 ? "" : "none";
      gitWrap.style.display = hasWs && n <= 2 ? "" : "none";
      buildActionItems();
    };
    // Measure by the sidebar panel width, which is the real constraint.
    // Sidebar default is 280px; mode selector + �?need ~170px.
    const measureOverflow = () => {
      // Normal mode (no workspace): no buttons to merge, all hidden.
      if (!getState().activeWorkspace) { setOverflow(0); return; }
      const w = panel.clientWidth;
      let need = 0;
      if (w < 230) need = 3;       // everything merged, only mode + �?left
      else if (w < 270) need = 2;  // git + split merged
      else if (w < 310) need = 1; // collapse merged
      else need = 0;
      setOverflow(need);
    };
    const ro = new ResizeObserver(() => measureOverflow());
    ro.observe(panel);
    measureOverflow();

    // Collapse the right-side file tree when the panel gets narrow so the
    // diff area can use the full width.
    const reviewBody = panel.querySelector(".si-review-body") as HTMLElement;
    const reviewTree = panel.querySelector(".si-review-tree") as HTMLElement;
    const reviewDivider = panel.querySelector(".si-review-divider") as HTMLElement;
    const measureTree = () => {
      if (!reviewBody) return;
      reviewBody.classList.toggle("tree-collapsed", panel.clientWidth < 340);
    };
    const treeRo = new ResizeObserver(() => measureTree());
    treeRo.observe(panel);
    measureTree();

    // Draggable divider between diff and tree (mirrors editor divider).
    if (reviewDivider && reviewTree) {
      let rResizing = false, rStartX = 0, rStartW = 0;
      reviewDivider.addEventListener("mousedown", (e) => {
        rResizing = true;
        rStartX = e.clientX;
        rStartW = reviewTree.offsetWidth;
        reviewDivider.classList.add("resizing");
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
        e.preventDefault();
      });
      document.addEventListener("mousemove", (e) => {
        if (!rResizing) return;
        const newW = Math.max(120, Math.min(480, rStartW - (e.clientX - rStartX)));
        reviewTree.style.flex = "0 0 " + newW + "px";
      });
      document.addEventListener("mouseup", () => {
        if (!rResizing) return;
        rResizing = false;
        reviewDivider.classList.remove("resizing");
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        // Persist tree width
        const w = reviewTree.offsetWidth;
        try { localStorage.setItem("review-tree-width", String(w)); } catch {}
      });

      // Restore saved width
      try {
        const saved = localStorage.getItem("review-tree-width");
        if (saved) {
          const w = parseInt(saved, 10);
          if (w >= 120 && w <= 480) reviewTree.style.flex = "0 0 " + w + "px";
        }
      } catch {}
    }

    // Apply CSS-class-driven toggles to the diff container.
    const applyContainerClasses = () => {
      if (!this._reviewDiffEl) return;
      this._reviewDiffEl.classList.toggle("review-wrap", this._reviewWrap);
      this._reviewDiffEl.classList.toggle("review-collapsed", this._reviewCollapsed);
      this._reviewDiffEl.classList.toggle("review-split", this._reviewSplitView);
    };
    applyContainerClasses();

    // Update the collapse/split button icons to reflect the current state.
    // Lucide's createIcons() replaces <i> with <svg>, so the icon element
    // no longer has data-lucide on the next call �?rebuild the inner HTML.
    const updateToolIcons = () => {
      collapseBtn.innerHTML = `<i data-lucide="${this._reviewCollapsed ? "plus" : "minus"}" class="lucide lucide-sm"></i>`;
      splitBtn.innerHTML = `<i data-lucide="${this._reviewSplitView ? "columns" : "list"}" class="lucide lucide-sm"></i>`;
      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: collapseBtn });
        (window as any).lucide.createIcons({ root: splitBtn });
      }
    };
    updateToolIcons();

    // Collapse / expand all diff bodies.
    collapseBtn.addEventListener("click", () => {
      this._reviewCollapsed = !this._reviewCollapsed;
      applyContainerClasses();
      updateToolIcons();
    });

    // Toggle split (two-column) view. Mutually exclusive with rich text + word diff.
    splitBtn.addEventListener("click", () => {
      this._reviewSplitView = !this._reviewSplitView;
      if (this._reviewSplitView) {
        this._reviewRichText = false;
        this._reviewWordDiff = false;
      }
      applyContainerClasses();
      updateToolIcons();
      buildActionItems();
      if (currentReviewPath) load(currentReviewPath, true);
      else load(undefined, true);
    });

    // Git action dropdown: commit / push / pull.
    const gitActionItems: Array<{ action: "commit" | "push" | "pull"; icon: string; labelKey: string }> = [
      { action: "commit", icon: "git-commit-horizontal", labelKey: "reviewActionCommit" },
      { action: "push", icon: "upload", labelKey: "reviewActionPush" },
      { action: "pull", icon: "download", labelKey: "reviewActionPull" },
    ];
    const buildGitActionItems = () => {
      gitDropdown.innerHTML = gitActionItems.map((item) =>
        `<div class="settings-dropdown-item review-action-item${item.action === this._reviewGitAction ? " checked" : ""}${item.action === "push" ? " si-review-git-disabled" : ""}" data-git-action="${item.action}">
          <i data-lucide="${item.icon}" class="lucide lucide-xs"></i>
          <span>${this.esc(t("sessionInner." + item.labelKey))}</span>
        </div>`
      ).join("");
      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: gitDropdown });
      }
      // Update the trigger icon to the currently-selected action.
      const sel = gitActionItems.find((i) => i.action === this._reviewGitAction);
      gitIcon.setAttribute("data-lucide", sel?.icon || "git-commit-horizontal");
      gitTrigger.dataset.tooltip = sel ? t("sessionInner." + sel.labelKey) : "";
      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: gitTrigger });
      }
    };
    buildGitActionItems();
    // Move dropdowns to document.body so they escape the sidebar's stacking
    // context (transform) and overflow:clip. Position with fixed coords.
    const moveToBody = (dd: HTMLElement) => {
      if (dd.parentElement !== document.body) document.body.appendChild(dd);
    };
    moveToBody(actionDropdown);
    moveToBody(gitDropdown);
    const positionDropdown = (dd: HTMLElement, trigger: HTMLElement) => {
      moveToBody(dd);
      const r = trigger.getBoundingClientRect();
      dd.style.position = "fixed";
      dd.style.top = `${r.bottom + 4}px`;
      dd.style.left = "auto";
      const right = window.innerWidth - r.right;
      dd.style.right = `${Math.max(8, right)}px`;
    };
    // Git trigger: click on the icon runs the action; click on the chevron
    // opens the dropdown. Both handlers merged into one to avoid conflicts.
    gitTrigger.addEventListener("click", (e) => {
      e.stopPropagation();
      // If the click landed on the chevron icon, open/close the dropdown.
      if ((e.target as HTMLElement).classList.contains("settings-dropdown-chevron") ||
          (e.target as HTMLElement).closest(".settings-dropdown-chevron")) {
        const isOpen = gitDropdown.classList.contains("open");
        document.querySelectorAll(".settings-dropdown.open").forEach((dd) => dd.classList.remove("open"));
        if (!isOpen) {
          buildGitActionItems();
          gitDropdown.classList.add("open");
          positionDropdown(gitDropdown, gitTrigger);
        }
        return;
      }
      // Click on the icon or button body �?run the selected git action.
      runGitAction();
    });
    gitDropdown.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;
      const item = target.closest(".settings-dropdown-item") as HTMLElement;
      if (!item) return;
      e.stopPropagation();
      const action = (item.getAttribute("data-git-action") || "commit") as "commit" | "push" | "pull";
      this._reviewGitAction = action;
      gitDropdown.classList.remove("open");
      buildGitActionItems();
    });

    // Trigger the selected git action when the trigger button is clicked directly
    // (not the chevron area). For commit, open the inline input; push/pr run directly.
    gitTrigger.addEventListener("dblclick", (e) => e.preventDefault());
    const runGitAction = async () => {
      const ws = getState().activeWorkspace;
      if (!ws) return;
      if (this._reviewGitAction === "commit") {
        commitWrap.classList.remove("hidden");
        commitInput.value = "";
        commitInput.focus();
        return;
      }
      const api = (window as any).electronAPI;
      if (!api) return;
      if (this._reviewGitAction === "push") {
        const res = await api.gitPush(ws);
        if (res.error) { showToast(res.error, "error", undefined, "Review"); }
      } else if (this._reviewGitAction === "pull") {
        const res = await api.gitPull(ws);
        if (res.error) { showToast(res.error, "error", undefined, "Review"); }
      }
      if (currentReviewPath) load(currentReviewPath, true);
      else load(undefined, true);
    };

    // Commit input area handlers.
    const commitCommit = () => {
      const ws = getState().activeWorkspace;
      const message = commitInput.value.trim();
      if (!ws || !message) return;
      const api = (window as any).electronAPI;
      if (!api) return;
      api.gitCommit(ws, message).then((res: any) => {
        if (res.error) { showToast(res.error, "error", undefined, "Review"); return; }
        commitWrap.classList.add("hidden");
        currentReviewPath = undefined;
        cachedEntries = null;
        cachedBranch = "";
        load(undefined, true);
      });
    };
    commitInput.addEventListener("keydown", (e: KeyboardEvent) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        commitCommit();
      } else if (e.key === "Escape") {
        commitWrap.classList.add("hidden");
        commitInput.value = "";
      }
    });
    // Click outside the palette (on the dimmed overlay) closes it, matching
    // the search overlay's behavior in bindSearchOverlay().
    commitWrap.addEventListener("click", (e: MouseEvent) => {
      if (e.target === commitWrap) {
        commitWrap.classList.add("hidden");
        commitInput.value = "";
      }
    });

    // Action menu dropdown - use delegation for dynamically built items.
    actionTrigger.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpen = actionDropdown.classList.contains("open");
      document.querySelectorAll(".settings-dropdown.open").forEach((dd) => dd.classList.remove("open"));
      if (!isOpen) {
        buildActionItems();
        actionDropdown.classList.add("open");
        positionDropdown(actionDropdown, actionTrigger);
      }
    });
    actionDropdown.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;
      const item = target.closest(".settings-dropdown-item") as HTMLElement;
      if (!item) return;
      e.stopPropagation();
      const action = item.getAttribute("data-action") || "";
      if (action === "refresh") {
        currentReviewPath = undefined;
        cachedEntries = null;
        cachedBranch = "";
        load(undefined, true);
        actionDropdown.classList.remove("open");
        return;
      }
      // Overflow buttons merged from the toolbar when narrow.
      if (action === "_overflow_collapse") { collapseBtn.click(); actionDropdown.classList.remove("open"); return; }
      if (action === "_overflow_split") { splitBtn.click(); actionDropdown.classList.remove("open"); return; }
      if (action === "_overflow_git") { gitTrigger.click(); actionDropdown.classList.remove("open"); return; }
      // Toggle handlers: flip state, re-render, refresh checkmarks.
      let changed = false;
      if (action === "wrap") { this._reviewWrap = !this._reviewWrap; changed = true; }
      else if (action === "fullFile") { this._reviewFullFile = !this._reviewFullFile; changed = true; }
      else if (action === "richText") {
        this._reviewRichText = !this._reviewRichText;
        if (this._reviewRichText) this._reviewSplitView = false;
        changed = true;
      }
      else if (action === "wordDiff") {
        this._reviewWordDiff = !this._reviewWordDiff;
        if (this._reviewWordDiff) this._reviewSplitView = false;
        changed = true;
      }
      else if (action === "hideWs") { this._reviewHideWs = !this._reviewHideWs; changed = true; }
      if (changed) {
        applyContainerClasses();
        updateToolIcons();
        if (currentReviewPath) {
          load(currentReviewPath, true);
        } else {
          load(undefined, true);
        }
        buildActionItems();
      }
      actionDropdown.classList.remove("open");
    });

    // Build filter dropdown items (left dropdown �?mode/filter selection)
    const buildFilterItems = () => {
      const ws = getState().activeWorkspace;
      const items: Array<{ filter: string; labelKey: string }> = [];
      if (ws) {
        items.push(
          { filter: "all", labelKey: "reviewAllChanges" },
          { filter: "unstaged", labelKey: "reviewUnstaged" },
          { filter: "staged", labelKey: "reviewStaged" },
          { filter: "branch", labelKey: "reviewBranch" },
          { filter: "commit", labelKey: "reviewCommitChanges" },
          { filter: "lastRound", labelKey: "reviewLastRound" },
        );
      } else {
        items.push({ filter: "lastRound", labelKey: "reviewLastRound" });
      }
      // Without a workspace there is no git to review: force the artifact
      // view and hide both dropdowns so the panel just shows all session changes.
      if (!ws && this._reviewFilter !== "lastRound") {
        this._reviewFilter = "lastRound";
        this._reviewMode = "artifact";
      }
      modeWrap.style.display = ws ? "" : "none";
      actionWrap.style.display = ws ? "" : "none";
      // In normal mode (no workspace) all review buttons are disabled -
      // only the modified-file artifact list is shown.
      collapseBtn.style.display = ws ? (this._reviewOverflow <= 0 ? "" : "none") : "none";
      splitBtn.style.display = ws ? (this._reviewOverflow <= 1 ? "" : "none") : "none";
      gitWrap.style.display = ws ? (this._reviewOverflow <= 2 ? "" : "none") : "none";
      modeDropdown.innerHTML = items.map((item) =>
        `<div class="settings-dropdown-item${item.filter === this._reviewFilter ? " selected" : ""}" data-filter="${item.filter}">${this.esc(t("sessionInner." + item.labelKey))}</div>`
      ).join("");
      // Update trigger label to match current filter
      const labelMap: Record<string, string> = {
        all: t("sessionInner.reviewAllChanges"),
        unstaged: t("sessionInner.reviewUnstaged"),
        staged: t("sessionInner.reviewStaged"),
        branch: t("sessionInner.reviewBranch"),
        commit: t("sessionInner.reviewCommitChanges"),
        lastRound: t("sessionInner.reviewLastRound"),
      };
      modeLabel.textContent = labelMap[this._reviewFilter] || t("sessionInner.reviewLastRound");
    };
    buildFilterItems();

    // Filter dropdown �?delegation
    modeTrigger.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpen = modeDropdown.classList.contains("open");
      document.querySelectorAll(".settings-dropdown.open").forEach((dd) => dd.classList.remove("open"));
      if (!isOpen) {
        buildFilterItems();
        modeDropdown.classList.add("open");
      }
    });
    modeDropdown.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;
      const item = target.closest(".settings-dropdown-item") as HTMLElement;
      if (!item) return;
      e.stopPropagation();
      const filter = item.getAttribute("data-filter") || "all";
      if (filter === this._reviewFilter) { modeDropdown.classList.remove("open"); return; }
      this._reviewFilter = filter;
      this._reviewMode = filter === "lastRound" ? "artifact" : "git";
      modeLabel.textContent = item.textContent || "";
      buildFilterItems();
      currentReviewPath = undefined;
      cachedEntries = null;
      cachedBranch = "";
      modeDropdown.classList.remove("open");
      load(undefined, true);
    });
    document.addEventListener("click", (e) => {
      if (!modeWrap.contains(e.target as Node)) {
        modeDropdown.classList.remove("open");
      }
    });

    // Always load the review panel state when opened, even without a pending file
    if (this._reviewFilePending !== undefined) {
      await load(this._reviewFilePending, false);
      this._reviewFilePending = undefined;
    } else {
      // Opening the review tab directly (not via "view changes" with an
      // artifact): default to "all changes" so the workspace's full diff is
      // shown, never a stale "last round".
      if (getState().activeWorkspace) {
        this._reviewFilter = "all";
        this._reviewMode = "git";
        this._reviewArtifact = null;
      }
      await load(undefined, false);
    }
  }

  private setupBrowserPanel(panel: HTMLElement, tabId: string, startUrl?: string): void {
    panel.style.overflow = "hidden";

    const existing = this.panelBrowsers.get(tabId);
    if (existing) {
      panel.appendChild(existing.container);
      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: panel });
      }
      return;
    }

    const container = document.createElement("div");
    container.style.cssText = "display:flex;flex-direction:column;flex:1;min-height:0;height:100%;";
    panel.appendChild(container);
    const url = startUrl || getDefaultHomepage();
    const bv = new BrowserView(container, {
      startUrl: url,
      compact: true,
      onTitleChange: (title: string) => {
        const tab = this.tabs.find(t => t.id === tabId);
        if (tab && title) {
          tab.label = title;
          this.renderTabLabels();
        }
      },
      onFaviconChange: (faviconUrl: string) => {
        const tab = this.tabs.find(t => t.id === tabId);
        if (tab) {
          tab.favicon = faviconUrl;
          this.renderTabIcons();
        }
      },
      onNewWindow: (newUrl: string) => {
        this.createTab("browser", { startUrl: newUrl });
      },
    });
    this.panelBrowsers.set(tabId, bv);
    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: panel });
    }
  }

  private setupMarkdownPanel(panel: HTMLElement, tabId: string, content?: string, title?: string, filePath?: string): void {
    panel.style.overflow = "hidden";

    const existing = this.panelMarkdownPreviews.get(tabId);
    if (existing) {
      panel.appendChild(existing.container);
      return;
    }

    const basePath = filePath ? filePath.replace(/[/\\][^/\\]+$/, "") : "";
    const container = document.createElement("div");
    container.style.cssText = "display:flex;flex-direction:column;flex:1;min-height:0;height:100%;";
    panel.appendChild(container);
    const mp = new MarkdownPreviewView(container, title || "", {
      onOpenLink: (href) => this._handleMarkdownLink(href, tabId),
    });
    if (content) mp.setContent(content, basePath || undefined);
    this.panelMarkdownPreviews.set(tabId, mp);
  }

  public async openMarkdownPreview(content: string, title?: string, filePath?: string): Promise<void> {
    const existing = filePath
      ? this.tabs.find(t => t.type === "markdown" && t.filePath === filePath)
      : this.tabs.find(t => t.type === "markdown");
    if (existing) {
      this.activeTab = existing.id;
      existing.content = content;
      if (title) existing.title = title;
      existing.filePath = filePath || existing.filePath;
      const mp = this.panelMarkdownPreviews.get(existing.id);
      const basePath = filePath ? filePath.replace(/[/\\][^/\\]+$/, "") : "";
      if (mp) mp.setContent(content, basePath || undefined);
      await this.renderTabs();
      return;
    }
    await this.createTab("markdown", { content, title, filePath });
  }

  private _handleMarkdownLink(href: string, tabId: string): void {
    if (/^https?:\/\//i.test(href)) {
      const api = (window as any).electronAPI;
      if (api?.openExternal) api.openExternal(href);
      return;
    }
    // Resolve relative paths against the markdown file's directory
    const tab = this.tabs.find(t => t.id === tabId);
    const filePath = tab?.filePath;
    if (!filePath) return;
    const basePath = filePath.replace(/[/\\][^/\\]+$/, "");

    let fullPath: string;
    if (href.startsWith("/")) {
      fullPath = href;
    } else {
      const dir = basePath.replace(/\\/g, "/").replace(/\/?$/, "/");
      const parts = dir.split("/").filter(Boolean);
      for (const seg of href.replace(/\\/g, "/").split("/")) {
        if (seg === "..") { if (parts.length > 1) parts.pop(); }
        else if (seg !== "." && seg) parts.push(seg);
      }
      fullPath = parts.join("/");
    }
    if (/\.md$/i.test(fullPath)) {
      this._openMdInPreview(fullPath);
    } else {
      this.openFileInEditor(fullPath);
    }
  }

  private async _openMdInPreview(filePath: string): Promise<void> {
    const api = (window as any).electronAPI;
    if (!api) return;
    const result = await api.readFile(filePath);
    if (!result) return;
    const name = filePath.split(/[/\\]/).pop() || "Markdown";
    this.openMarkdownPreview(result.content, name, filePath);
  }

  private renderTabLabels(): void {
    this.tabList.querySelectorAll(".tab").forEach((el) => {
      const id = (el as HTMLElement).dataset.tab;
      if (!id) return;
      const tab = this.tabs.find(t => t.id === id);
      if (!tab) return;
      const labelEl = el.querySelector(".tab-label");
      if (labelEl) labelEl.textContent = tab.label;
    });
  }

  private renderTabIcons(): void {
    this.tabList.querySelectorAll(".tab").forEach((el) => {
      const id = (el as HTMLElement).dataset.tab;
      if (!id) return;
      const tab = this.tabs.find(t => t.id === id);
      if (!tab || tab.type !== "browser") return;
      const existingImg = el.querySelector(".tab-favicon");
      const existingIcon = el.querySelector(".lucide");
      if (tab.favicon && !existingImg) {
        if (existingIcon) {
          const img = document.createElement("img");
          img.className = "tab-favicon";
          img.src = tab.favicon;
          img.alt = "";
          img.style.cssText = "width:14px;height:14px;flex-shrink:0;margin-right:4px;";
          img.onerror = () => { img.style.display = "none"; if (existingIcon) (existingIcon as HTMLElement).style.display = ""; };
          existingIcon.replaceWith(img);
          if (typeof (window as any).lucide !== "undefined") {
            (window as any).lucide.createIcons({ root: el });
          }
        }
      }
    });
  }

  private setupAgentPanel(panel: HTMLElement): void {
    panel.innerHTML = `<div class="session-inner-sidebar-body"><div class="si-agent-root"></div></div>`;
    this.renderAgentPanel(panel);
  }

  private renderAgentPanel(panel: HTMLElement): void {
    const root = panel.querySelector(".si-agent-root") as HTMLElement | null;
    if (!root) return;

    const agentState = getState().agentState;
    if (!agentState) {
      root.innerHTML = `<div class="si-panel-empty">${this.esc(t("sessionInner.agentNoState"))}</div>`;
      return;
    }

    const workingSet = (agentState.working_set || {}) as Record<string, unknown>;
    const tools = this.asStringList(workingSet.tools);
    const artifacts = this.asStringList(workingSet.artifacts);
    const references = this.asStringList(workingSet.references);
    const planItems = this.asStringList(workingSet.plan_items);
    const delegates = Array.isArray(agentState.delegate_history) ? agentState.delegate_history.slice(-6).reverse() : [];
    const stuckEvents = Array.isArray(agentState.stuck_events) ? agentState.stuck_events.slice(-6).reverse() : [];
    const stages = Array.isArray(agentState.task_stage_history) ? agentState.task_stage_history.slice(-8).reverse() : [];

    root.innerHTML = `<div class="si-panels">
      <div class="si-panel">
        ${this.panelHeader("agent-overview", t("sessionInner.agentOverview"), "bot")}
        <div class="si-panel-body${this.collapsedPanels.has("agent-overview") ? " hidden" : ""}">
          <div class="si-panel-inner">
            <div class="si-agent-stage-row">
              <span class="si-agent-label">${this.esc(t("sessionInner.agentCurrentStage"))}</span>
              <span class="si-agent-stage-badge">${this.esc(agentState.task_stage || t("sessionInner.agentUnknown"))}</span>
            </div>
            <div class="si-agent-kv-grid">
              <div class="si-agent-kv"><span class="si-agent-k">${this.esc(t("sessionInner.agentDelegations"))}</span><span class="si-agent-v">${delegates.length}</span></div>
              <div class="si-agent-kv"><span class="si-agent-k">${this.esc(t("sessionInner.agentStuckEvents"))}</span><span class="si-agent-v">${stuckEvents.length}</span></div>
              <div class="si-agent-kv"><span class="si-agent-k">${this.esc(t("sessionInner.tools"))}</span><span class="si-agent-v">${tools.length}</span></div>
              <div class="si-agent-kv"><span class="si-agent-k">${this.esc(t("sessionInner.agentPlanItems"))}</span><span class="si-agent-v">${planItems.length}</span></div>
            </div>
          </div>
        </div>
      </div>
      <div class="si-panel">
        ${this.panelHeader("agent-working-set", t("sessionInner.agentWorkingSet"), "layers")}
        <div class="si-panel-body${this.collapsedPanels.has("agent-working-set") ? " hidden" : ""}">
          <div class="si-panel-inner">
            ${this.renderAgentListSection(t("sessionInner.agentSectionTools"), tools)}
            ${this.renderAgentListSection(t("sessionInner.agentSectionArtifacts"), artifacts)}
            ${this.renderAgentListSection(t("sessionInner.agentSectionReferences"), references)}
            ${this.renderAgentListSection(t("sessionInner.agentSectionPlan"), planItems)}
          </div>
        </div>
      </div>
      <div class="si-panel">
        ${this.panelHeader("agent-delegates", t("sessionInner.agentDelegation"), "git-branch", delegates.length > 0 ? String(delegates.length) : undefined)}
        <div class="si-panel-body${this.collapsedPanels.has("agent-delegates") ? " hidden" : ""}">
          <div class="si-panel-inner">
            ${this.renderAgentEventList(delegates, t("sessionInner.agentNoDelegation"))}
          </div>
        </div>
      </div>
      <div class="si-panel">
        ${this.panelHeader("agent-stuck", t("sessionInner.agentRecovery"), "siren", stuckEvents.length > 0 ? String(stuckEvents.length) : undefined)}
        <div class="si-panel-body${this.collapsedPanels.has("agent-stuck") ? " hidden" : ""}">
          <div class="si-panel-inner">
            ${this.renderAgentEventList(stuckEvents, t("sessionInner.agentNoRecovery"))}
          </div>
        </div>
      </div>
      <div class="si-panel">
        ${this.panelHeader("agent-stages", t("sessionInner.agentStageHistory"), "route", stages.length > 0 ? String(stages.length) : undefined)}
        <div class="si-panel-body${this.collapsedPanels.has("agent-stages") ? " hidden" : ""}">
          <div class="si-panel-inner">
            ${this.renderAgentEventList(stages, t("sessionInner.agentNoStages"))}
          </div>
        </div>
      </div>
    </div>`;

    this.bindAgentPanel(panel);
    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: panel });
    }
  }

  private bindAgentPanel(panel: HTMLElement): void {
    panel.querySelectorAll(".si-panel-header").forEach((header) => {
      header.addEventListener("click", () => {
        const panelId = (header as HTMLElement).dataset.panel!;
        this.togglePanel(panelId);
        this.renderAgentPanel(panel);
      });
    });
  }

  private renderAgentListSection(label: string, items: string[]): string {
    return `<div class="si-agent-section">
      <div class="si-agent-section-title">${this.esc(label)}</div>
      ${items.length > 0
        ? `<div class="si-agent-chip-list">${items.map((item) => `<span class="si-agent-chip">${this.esc(item)}</span>`).join("")}</div>`
        : `<div class="si-agent-empty-inline">${this.esc(t("sessionInner.agentEmptyInline"))}</div>`}
    </div>`;
  }

  private renderAgentEventList(items: Array<Record<string, unknown>>, emptyText: string): string {
    if (!items.length) {
      return `<div class="si-agent-empty-inline">${this.esc(emptyText)}</div>`;
    }
    return `<div class="si-agent-event-list">${items.map((item) => {
      const entries = Object.entries(item)
        .filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== "")
        .slice(0, 4);
      const title = this.esc(this.getAgentEventTitle(item, entries));
      const meta = entries.slice(1).map(([key, value]) =>
        `<span class="si-agent-event-meta"><span class="si-agent-event-key">${this.esc(key)}</span>${this.esc(this.stringifyAgentValue(value))}</span>`
      ).join("");
      return `<div class="si-agent-event">
        <div class="si-agent-event-title">${title}</div>
        ${meta ? `<div class="si-agent-event-row">${meta}</div>` : ""}
      </div>`;
    }).join("")}</div>`;
  }

  private asStringList(value: unknown): string[] {
    if (!Array.isArray(value)) return [];
    return value
      .map((item) => this.stringifyAgentValue(item))
      .filter((item) => item.length > 0);
  }

  private getAgentEventTitle(
    item: Record<string, unknown>,
    entries: Array<[string, unknown]>,
  ): string {
    const preferredKeys = ["summary", "message", "stage", "agent", "name", "reason", "status", "tool"];
    for (const key of preferredKeys) {
      const text = this.stringifyAgentValue(item[key]);
      if (text) return text;
    }
    if (entries.length > 0) {
      return this.stringifyAgentValue(entries[0][1]);
    }
    return t("sessionInner.agentEvent");
  }

  private stringifyAgentValue(value: unknown): string {
    if (typeof value === "string") return value;
    if (typeof value === "number" || typeof value === "boolean") return String(value);
    if (Array.isArray(value)) return value.map((item) => this.stringifyAgentValue(item)).filter(Boolean).join(", ");
    if (value && typeof value === "object") {
      const pairs = Object.entries(value as Record<string, unknown>)
        .slice(0, 3)
        .map(([key, inner]) => `${key}: ${this.stringifyAgentValue(inner)}`);
      return pairs.join(" | ");
    }
    return "";
  }

  private parseDiff(output: string): string {
    if (!output.trim()) return `<div class="si-panel-empty"><i data-lucide="check-circle-2" class="lucide"></i><div class="si-panel-empty-title">${t("sessionInner.reviewNoChanges")}</div></div>`;

    // Check if this is a binary/media file — use same extension sets as editor
    const fnMatch = output.match(/diff --git a\/\S+ b\/(.+?)(?:\n|$)/) || output.match(/^--- (?:[ab]\/)?(.+)$/m);
    const diffFileName = fnMatch ? fnMatch[1] : "";
    const ext = diffFileName.split(".").pop()?.toLowerCase() || "";
    const isBinary = !!ext && (
      SessionInner._mediaExts.has(ext) || SessionInner._binaryExts.has(ext)
    );
    if (isBinary || /Binary files |GIT binary patch/.test(output)) {
      const name = diffFileName || t("sessionInner.reviewUnknownFile");
      return `<div class="si-panel-empty">
        <i data-lucide="file-x-2" class="lucide"></i>
        <span class="si-panel-empty-title">${this.esc(name)}</span>
        <span class="si-panel-empty-sub">${t("sessionInner.binaryFileNotShown")}</span>
      </div>`;
    }

    return renderDiffHtml(output, {
      fileNameFallback: t("sessionInner.reviewUnknownFile"),
      maxLines: this._reviewFullFile ? 4000 : 1000,
      richText: this._reviewRichText,
      wordDiff: this._reviewWordDiff,
      hideWhitespace: this._reviewHideWs,
      splitView: this._reviewSplitView,
      truncatedNotice: (n: number) => t("sessionInner.reviewTruncated", { n }),
    });
  }

  private parseArtifactDiff(artifact: ArtifactItem, filePath?: string): string {
    const diffText = artifact.diff_text;
    const targetPath = filePath || artifact.path;
    if (!diffText || !diffText.trim()) {
      // Show a rich file info card for artifacts without diff (e.g. new files)
      const isCreated = artifact.tool === "file_write" || artifact.tool === "write_file" || artifact.tool === "writeFile";
      const sizeStr = artifact.size > 0
        ? artifact.size >= 1024
          ? `${(artifact.size / 1024).toFixed(1)} KB`
          : `${artifact.size} B`
        : "";
      return `<div class="si-review-diff-content">
        <div class="si-review-diff-file-header">
          <i data-lucide="file-plus" class="lucide lucide-sm" style="margin-right:6px"></i>
          ${this.esc(targetPath)}
        </div>
        <div style="padding:16px 20px;color:var(--text-secondary);font-size:13px;line-height:1.6">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
            <span class="si-review-${isCreated ? "untracked" : "unstaged"}" style="padding:1px 8px;border-radius:3px;font-size:11px;font-weight:500">
              ${isCreated ? this.esc(t("sessionInner.reviewCreated")) : this.esc(t("sessionInner.reviewModified"))}
            </span>
            <span style="font-family:var(--mono);font-size:12px">${this.esc(targetPath)}</span>
          </div>
          ${sizeStr ? `<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
            <i data-lucide="hard-drive" class="lucide lucide-xs" style="opacity:0.6"></i>
            <span>${this.esc(sizeStr)}</span>
          </div>` : ""}
          <div style="display:flex;align-items:center;gap:6px">
            <i data-lucide="wrench" class="lucide lucide-xs" style="opacity:0.6"></i>
            <span>${this.esc(artifact.tool)}</span>
          </div>
          ${!isCreated ? `<div style="margin-top:8px;color:var(--text-muted);font-style:italic">(${this.esc(t("sessionInner.reviewNoChanges"))})</div>` : ""}
        </div>
      </div>`;
    }
    return this.renderArtifactDiffView(diffText, targetPath);
  }

  private renderArtifactDiffView(diffText: string, filePath: string): string {
    return renderDiffHtml(diffText, {
      fileNameFallback: filePath,
      maxLines: this._reviewFullFile ? 4000 : 1000,
      richText: this._reviewRichText,
      wordDiff: this._reviewWordDiff,
      hideWhitespace: this._reviewHideWs,
      splitView: this._reviewSplitView,
      truncatedNotice: (n: number) => t("sessionInner.reviewTruncated", { n }),
    });
  }

  private buildArtifactTree(artifacts: ArtifactItem[], activePath: string): string {
    if (artifacts.length === 0) return `<div class="si-panel-empty">
      <i data-lucide="check-circle-2" class="lucide"></i>
      <div class="si-panel-empty-title">${t("sessionInner.reviewNoChanges")}</div>
      <div class="si-panel-empty-sub">${t("sessionInner.reviewNoChangesSub")}</div>
    </div>`;
    // Group by top-level directory (same as git buildTree style)
    const groups = new Map<string, ArtifactItem[]>();
    for (const a of artifacts) {
      const dir = a.path.includes("/") ? a.path.split("/")[0] : "(root)";
      if (!groups.has(dir)) groups.set(dir, []);
      groups.get(dir)!.push(a);
    }
    let html = "";
    for (const [dir, items] of groups) {
      html += `<div class="si-review-tree-group">
        <div class="si-review-tree-folder">
          <i data-lucide="folder" class="lucide lucide-xs"></i>
          <span>${this.esc(dir)}</span>
        </div>`;
      for (const a of items) {
        const active = a.path === activePath ? " si-review-tree-file--active" : "";
        const toolLabel = a.tool === "file_write" || a.tool === "write_file" || a.tool === "writeFile"
          ? "created" : "modified";
        html += `<div class="si-review-tree-file${active}" data-path="${this.esc(a.path)}">
          <img src="${getFileIcon(a.name)}" class="icon" style="width:14px;height:14px">
          <span class="si-review-tree-name">${this.esc(a.name)}</span>
          <span class="si-review-tree-status si-review-${toolLabel === "created" ? "untracked" : "unstaged"}">${toolLabel === "created" ? "U" : "M"}</span>
        </div>`;
      }
      html += `</div>`;
    }
    return html;
  }





  private async setupEditorPanel(panel: HTMLElement): Promise<void> {
    const api = (window as any).electronAPI;

    if (!getState().activeWorkspace) {
      panel.innerHTML = `<div class="si-panel-empty si-editor-empty">
        <i data-lucide="file-code-2" class="lucide"></i>
        <span class="si-panel-empty-title">${t("sessionInner.editorEmpty")}</span>
        <span class="si-panel-empty-sub">${t("workspace.empty")}</span>
      </div>`;
      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: panel });
      }
      return;
    }

    panel.innerHTML = `<div class="si-editor-wrap" style="display:flex;height:100%">
      <div class="si-editor-tree" style="flex:1;overflow:auto;max-width:none;width:100%">
        <div class="si-editor-tree-body"></div>
      </div>
    </div>`;

    const treeBody = panel.querySelector(".si-editor-tree-body")! as HTMLElement;

    /* context menu for tree */
    const treeCtxMenu = document.createElement("div");
    treeCtxMenu.className = "context-menu hidden";
    treeCtxMenu.id = "editor-tree-ctx-menu";
    let treeCtxPath = "";
    let treeCtxIsDir = false;
    document.body.appendChild(treeCtxMenu);

    const showTreeCtx = (ev: MouseEvent, path: string, isDir: boolean) => {
      ev.preventDefault();
      treeCtxPath = path;
      treeCtxIsDir = isDir;
      const ext = path.split(".").pop()?.toLowerCase() || "";
      const isMd = !isDir && ext === "md";
      treeCtxMenu.innerHTML = isDir
        ? `<div class="context-menu-item" data-action="send-folder">${t("sessionInner.termSendToChat")}</div>`
        : `<div class="context-menu-item" data-action="send-file">${t("sessionInner.termSendToChat")}</div>`
        + (isMd ? `<div class="context-menu-divider"></div><div class="context-menu-item" data-action="preview">预览</div>` : "");
      showContextMenu(treeCtxMenu, ev.clientX, ev.clientY);
    };

    treeCtxMenu.addEventListener("click", async (ev) => {
      const item = (ev.target as HTMLElement).closest(".context-menu-item") as HTMLElement | null;
      if (!item) return;
      const action = item.dataset.action;
      const api = (window as any).electronAPI;
      if (action === "send-file" && api) {
        const result = await api.readFile(treeCtxPath);
        if (result) {
          const name = treeCtxPath.split(/[/\\]/).pop() || treeCtxPath;
          const att: AttachmentMeta = {
            name, path: treeCtxPath,
            content: result.content,
            mime_type: result.mime_type || "",
            size: result.size,
            is_binary: result.is_binary,
          };
          addAttachments([att]);
        }
      } else if (action === "send-folder" && api) {
        const name = treeCtxPath.split(/[/\\]/).pop() || treeCtxPath;
        const att: AttachmentMeta = {
          name, path: treeCtxPath,
          content: "",
          mime_type: "text/x-directory",
          size: 0, is_binary: false,
        };
        addAttachments([att]);
      } else if (action === "preview" && api) {
        const result = await api.readFile(treeCtxPath);
        if (result) {
          const name = treeCtxPath.split(/[/\\]/).pop() || treeCtxPath;
          this.openMarkdownPreview(result.content, name, treeCtxPath);
        }
      }
      treeCtxMenu.classList.add("hidden");
    });
    document.addEventListener("click", (e) => {
      if (!treeCtxMenu.contains(e.target as Node)) {
        treeCtxMenu.classList.add("hidden");
      }
    });

    let rootPath = "";
    const expandedDirs = new Set<string>();
    const dirCache = new Map<string, DirEntry[]>();

    const joinPath = (base: string, name: string) => {
      const sep = base.includes("\\") ? "\\" : "/";
      return base.replace(/[/\\]+$/, "") + sep + name;
    };

    const fetchDir = async (dirPath: string): Promise<DirEntry[]> => {
      if (dirCache.has(dirPath)) return dirCache.get(dirPath)!;
      if (!api) return [];
      try {
        const entries: DirEntry[] = await api.listDirectory(dirPath);
        dirCache.set(dirPath, entries);
        return entries;
      } catch {
        return [];
      }
    };

    const fileIcon = (name: string): string => getFileIcon(name);

    const renderRecursive = async (dirPath: string, depth: number, out: string[]) => {
      const entries = await fetchDir(dirPath);
      const sorted = [...entries].sort((a, b) => {
        if (a.isDirectory && !b.isDirectory) return -1;
        if (!a.isDirectory && b.isDirectory) return 1;
        return a.name.localeCompare(b.name);
      });
      const indent = depth * 8;
      for (const entry of sorted) {
        const fullPath = joinPath(dirPath, entry.name);
        if (entry.isDirectory) {
          const isExp = expandedDirs.has(fullPath);
          out.push(`<div class="si-tree-entry" data-path="${this.esc(fullPath)}" data-dir="true" style="padding-left:${indent}px">
            <span class="si-tree-chevron${isExp ? " expanded" : ""}"><i data-lucide="chevron-right" class="lucide lucide-xs"></i></span>
            <span class="si-tree-icon"><i data-lucide="folder" class="lucide lucide-sm"></i></span>
            <span class="si-tree-name">${this.esc(entry.name)}</span>
          </div>`);
          if (isExp) {
            await renderRecursive(fullPath, depth + 1, out);
          }
        } else {
          out.push(`<div class="si-tree-entry" data-path="${this.esc(fullPath)}" data-file="true" style="padding-left:${indent}px">
            <span class="si-tree-chevron" style="visibility:hidden"><i data-lucide="chevron-right" class="lucide lucide-xs"></i></span>
            <span class="si-tree-icon"><img src="${getFileIcon(entry.name)}" class="icon" style="width:14px;height:14px"></span>
            <span class="si-tree-name">${this.esc(entry.name)}</span>
          </div>`);
        }
      }
    };

    const renderTree = async () => {
      const out: string[] = [];
      await renderRecursive(rootPath, 0, out);
      treeBody.innerHTML = out.length ? out.join("") : `<div class="si-empty">${t("sessionInner.filesEmpty")}</div>`;

      treeBody.querySelectorAll(".si-tree-entry[data-dir]").forEach((el) => {
        el.addEventListener("click", async () => {
          const path = (el as HTMLElement).dataset.path!;
          treeBody.querySelectorAll(".si-tree-entry.selected").forEach((s) => s.classList.remove("selected"));
          (el as HTMLElement).classList.add("selected");
          if (expandedDirs.has(path)) {
            expandedDirs.delete(path);
          } else {
            await fetchDir(path);
            expandedDirs.add(path);
          }
          await renderTree();
        });
        (el as HTMLElement).addEventListener("contextmenu", (ev: MouseEvent) => {
          showTreeCtx(ev, (el as HTMLElement).dataset.path!, true);
        });
      });

      treeBody.querySelectorAll(".si-tree-entry[data-file]").forEach((el) => {
        el.addEventListener("click", () => {
          treeBody.querySelectorAll(".si-tree-entry.selected").forEach((s) => s.classList.remove("selected"));
          (el as HTMLElement).classList.add("selected");
          const filePath = (el as HTMLElement).dataset.path!;
          this.openFileInEditor(filePath);
        });
        (el as HTMLElement).addEventListener("contextmenu", (ev: MouseEvent) => {
          showTreeCtx(ev, (el as HTMLElement).dataset.path!, false);
        });
      });

      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: treeBody });
      }
    };

    /* workspace root */
    const home = api
      ? (await api.getAppPath()).replace(/[/\\][^/\\]+$/, "")
      : ".";
    const workspace = getState().activeWorkspace;
    rootPath = workspace || home;
    await renderTree();

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: panel });
    }
  }

  private static _imgExts = new Set(["png","jpg","jpeg","gif","webp","ico","bmp","svg"]);
  private static _videoExts = new Set(["mp4","avi","mov","wmv","flv","mkv","webm"]);
  private static _mediaExts = new Set([...SessionInner._imgExts, ...SessionInner._videoExts]);

  private static _binaryExts = new Set([
    "exe","dll","so","dylib","bin","dat","iso","img","dmg",
    "zip","rar","7z","gz","tar","bz2","xz","zst",
    "pdf","doc","docx","xls","xlsx","ppt","pptx",
    "mp3","wav","flac","ogg",
    "ttf","otf","woff","woff2","eot",
    "pyc","class","o","obj","lib","a","lo",
  ]);

  private _isBinaryContent(content: string): boolean {
    return /\0/.test(content);
  }

  private async openFileInEditor(filePath: string): Promise<void> {
    const api = (window as any).electronAPI;
    if (!api) return;
    const name = filePath.split(/[/\\]/).pop() || filePath;
    const ext = filePath.split(".").pop()?.toLowerCase() || "";

    if (SessionInner._mediaExts.has(ext)) {
      await this._openMediaPreview(name, filePath);
      return;
    }

    const result = await api.readFile(filePath);
    if (!result) return;

    if (result.is_binary || SessionInner._binaryExts.has(ext) || this._isBinaryContent(result.content)) {
      await this._openBinaryPreview(name, filePath);
      return;
    }

    // Re-use existing code tab for this file, or create a new one
    const existing = this.tabs.find(t => t.type === "code" && t.filePath === filePath);
    if (existing) {
      this.activeTab = existing.id;
      await this.renderTabs();
      return;
    }
    await this.createTab("code", { content: result.content, title: name, filePath });
  }

  private async _openBinaryPreview(name: string, filePath: string): Promise<void> {
    const existing = this.tabs.find(t => t.type === "binary" && t.filePath === filePath);
    if (existing) {
      this.activeTab = existing.id;
      await this.renderTabs();
      return;
    }
    const tabId = `binary-${Date.now()}`;
    this.tabs.push({
      id: tabId,
      type: "binary",
      label: name,
      closable: true,
      filePath,
    });
    this.activeTab = tabId;
    await this.renderTabs();
  }

  private async _openMediaPreview(name: string, filePath: string): Promise<void> {
    const existing = this.tabs.find(t => t.type === "media" && t.filePath === filePath);
    if (existing) {
      this.activeTab = existing.id;
      await this.renderTabs();
      return;
    }
    await this.createTab("media", { title: name, filePath });
  }

  private setupMediaPanel(panel: HTMLElement, tabId: string, filePath: string): void {
    panel.style.overflow = "hidden";
    panel.style.background = "var(--bg-primary)";

    const existing = this.panelMediaViewers.get(tabId);
    if (existing) {
      if (existing.el.parentElement !== panel) {
        panel.appendChild(existing.el);
      }
      return;
    }

    const container = document.createElement("div");
    container.style.cssText = "width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:var(--bg-primary);overflow:hidden;";
    panel.appendChild(container);

    const ext = filePath.split(".").pop()?.toLowerCase() || "";
    const isVideo = SessionInner._videoExts.has(ext);

    const mv = new MediaViewer(container, { type: isVideo ? "video" : "image", src: filePath });
    this.panelMediaViewers.set(tabId, mv);
  }

  private setupBinaryPanel(panel: HTMLElement, filePath: string): void {
    const name = filePath.split(/[/\\]/).pop() || filePath;
    panel.innerHTML = `<div class="si-panel-empty">
      <i data-lucide="file-x-2" class="lucide"></i>
      <span class="si-panel-empty-title">${this.esc(name)}</span>
      <span class="si-panel-empty-sub">${t("sessionInner.binaryFileNotShown")}</span>
    </div>`;
    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: panel });
    }
  }

  private async setupCodePanel(panel: HTMLElement, tabId: string, content: string, filePath: string): Promise<void> {
    panel.style.overflow = "hidden";
    panel.style.background = "var(--bg-primary)";

    const existing = this.panelCodeEditors.get(tabId);
    if (existing) {
      const container = existing._codeContainer;
      if (container && container.parentElement !== panel) {
        panel.appendChild(container);
      }
      return;
    }

    const container = document.createElement("div");
    container.style.cssText = "width:100%;height:100%;background:var(--bg-primary);";
    panel.appendChild(container);

    const ext = filePath.split(".").pop()?.toLowerCase() || "";
    const isDark = document.documentElement.getAttribute("data-theme") !== "light";

    const editor = await getMonaco();
    const view = editor.create(container, {
      value: content,
      language: monacoLang(ext),
      theme: isDark ? "vs-dark" : "vs",
      readOnly: true,
      minimap: { enabled: false },
      automaticLayout: true,
      scrollBeyondLastLine: false,
      fontSize: 13,
      lineNumbers: "on",
      renderLineHighlight: "line",
      contextmenu: false,
      bracketPairColorization: { enabled: true },
      padding: { top: 8 },
    });

    (view as any)._codeContainer = container;
    registerEditor(view);
    this.panelCodeEditors.set(tabId, view);
  }

  private _reviewLoad: ((filePath?: string) => Promise<void>) | null = null;
  private _reviewMode: "git" | "artifact" = "git";
  private _reviewFilter: string = "all";
  private _reviewArtifact: ArtifactItem | null = null;
  private _reviewRequestSeq = 0;
  private _reviewDiffCache: Map<string, string> | null = null;
  private _reviewTreeCache = new Map<string, string>();
  // Review display toggles (set by the action menu).
  private _reviewWrap = false;        // word wrap
  private _reviewFullFile = true;     // false => truncate large diffs
  private _reviewRichText = false;    // rich-text summary view
  private _reviewWordDiff = false;     // inline word diff
  private _reviewHideWs = false;       // dim whitespace-only lines
  private _reviewSplitView = false;    // two-column split diff
  private _reviewCollapsed = false;    // collapse all diff bodies
  // Selected git action for the commit/push/pr trigger.
  private _reviewGitAction: "commit" | "push" | "pull" = "commit";
  // How many side buttons are currently merged into the �?overflow menu.
  private _reviewOverflow = 0;
  private _reviewDiffEl: HTMLElement | null = null;  // ref for CSS class toggling

  /** Public entry point called from App when a "View Changes" button is clicked. */
  public showReviewTab(path: string, artifact?: ArtifactItem): void {
    // Ensure sidebar is visible when showing review
    const panel = document.getElementById("session-inner-sidebar");
    const mainBody = document.getElementById("main-body");
    if (panel && mainBody && panel.classList.contains("hidden")) {
      panel.classList.remove("hidden");
      mainBody.classList.remove("sidebar-hidden");
      document.getElementById("app")?.classList.add("sidebar-collapsed");
      // Re-render info panel content since it was skipped while hidden
      this.renderForce();
      this.saveSidebarVisibility();
    }
    if (artifact) {
      this._reviewFilter = "lastRound";
      this._reviewMode = "artifact";
      this._reviewArtifact = artifact;
    } else {
      // No artifact: review git changes when a workspace is open, otherwise
      // fall back to the session's artifacts (all changes).
      const hasWs = !!getState().activeWorkspace;
      this._reviewFilter = hasWs ? "all" : "lastRound";
      this._reviewMode = hasWs ? "git" : "artifact";
      this._reviewArtifact = null;
    }
    this.openReviewTab(path);
  }

  private closeReviewTab(): void {
    this.closeTab("review");
  }

  private openReviewTab(filePath?: string): void {
    const createNew = !this.tabs.some((t) => t.type === "review");
    if (createNew) {
      this.tabs.push({ id: "review", type: "review", label: tabLabel("review"), closable: true });
      this._reviewFilePending = filePath;
    }
    this.activeTab = "review";
    this.renderTabs();
    if (!createNew) {
      if (this._reviewLoad) this._reviewLoad(filePath);
    }
  }
  private _reviewFilePending: string | undefined;

  /* ── Tab Events ──────────────────────────────────────────────────── */

  private bindTabEvents(): void {
    // Close button (tab-close) for sidebar tabs uses data-tab from the
    // parent <button>. Also attach middle-click-to-close on the tab itself.
    const closeTab = (el: HTMLElement) => {
      const tabEl = el.closest(".tab") as HTMLElement;
      if (!tabEl) return;
      const id = tabEl.dataset.tab;
      if (id) this.closeTab(id);
    };
    this.tabList.addEventListener("wheel", (e) => {
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
        e.preventDefault();
        this.tabList.scrollLeft += e.deltaY;
      }
    }, { passive: false });
    this.tabList.querySelectorAll(".tab").forEach((tab, idx) => {
      const el = tab as HTMLElement;
      el.dataset.idx = String(idx);

      el.addEventListener("mousedown", (e) => {
        if (e.button === 1) e.preventDefault();
      });
      const xBtn = el.querySelector(".tab-close");
      if (xBtn) {
        xBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          closeTab(el);
        });
      }
      el.addEventListener("auxclick", (e) => {
        if ((e as MouseEvent).button === 1) {
          e.preventDefault();
          closeTab(el);
        }
      });

      /* Activate on click (unless dragged) */
      el.addEventListener("click", (e) => {
        if ((e.target as HTMLElement).closest(".tab-close")) return;
        if (this.wasDragged) { this.wasDragged = false; return; }
        const id = el.dataset.tab!;
        if (id !== this.activeTab) this.activateTab(id);
      });

      /* Drag start */
      el.addEventListener("mousedown", (e) => {
        if (e.button !== 0) return;
        if ((e.target as HTMLElement).closest(".tab-close")) return;
        this.wasDragged = false;
        this.dragEl = el;
        this.dragIdx = parseInt(el.dataset.idx ?? "-1");
        this.dragStartX = e.clientX;
        this.dragOverIdx = this.dragIdx;
        el.classList.add("dragging");
        e.preventDefault();
      });
    });

    if (!this.dragBound) {
      this.dragBound = true;
      document.addEventListener("mousemove", (e) => {
        if (!this.dragEl) return;
        /* Only consider it a drag if moved more than 5px */
        if (Math.abs(e.clientX - this.dragStartX) > 5) {
          this.wasDragged = true;
        }
        const dx = e.clientX - this.dragStartX;
        this.dragEl.style.transform = `translateX(${dx}px)`;

        const allTabs = [...this.tabList.querySelectorAll(".tab.tab--fill")];
        for (let i = 0; i < allTabs.length; i++) {
          const rect = allTabs[i].getBoundingClientRect();
          if (e.clientX > rect.left && e.clientX < rect.right) {
            if (i !== this.dragOverIdx) {
              if (this.dragOverIdx >= 0 && this.dragOverIdx < allTabs.length) {
                allTabs[this.dragOverIdx].classList.remove("drop-target");
              }
              this.dragOverIdx = i;
              allTabs[i].classList.add("drop-target");
            }
            break;
          }
        }
      });

      document.addEventListener("mouseup", () => {
        if (!this.dragEl) return;
        this.dragEl.style.transform = "";
        this.dragEl.classList.remove("dragging");
        this.tabList.querySelectorAll(".drop-target").forEach((t) => t.classList.remove("drop-target"));

        if (this.dragOverIdx >= 0 && this.dragOverIdx !== this.dragIdx) {
          const moved = this.tabs.splice(this.dragIdx, 1)[0];
          this.tabs.splice(this.dragOverIdx, 0, moved);
          this.renderTabs();
        }

        this.dragEl = null;
        this.dragIdx = -1;
        this.dragOverIdx = -1;
      });
    }
  }

  public activateTab(id: string): void {
    this.activeTab = id;
    this.tabList.querySelectorAll(".tab").forEach((t) => {
      t.classList.toggle("active", (t as HTMLElement).dataset.tab === id);
    });
    // Remove the .si-home placeholder when switching to a real tab so it
    // doesn't remain visible underneath the .tab-panel.
    const homeEl = this.tabBody.querySelector(".si-home");
    if (homeEl && id !== "home") homeEl.remove();
    this.tabBody.querySelectorAll(".tab-panel").forEach((p) => {
      p.classList.toggle("active", (p as HTMLElement).dataset.panel === id);
    });
    if (id === "info") this.renderContent();
    if (id === "review" && getState().activeWorkspace && this._reviewFilter !== "all") {
      this._reviewFilter = "all";
      this._reviewMode = "git";
      this._reviewArtifact = null;
      if (this._reviewLoad) this._reviewLoad(undefined);
    }
  }

  private closeTab(id: string): void {
    const idx = this.tabs.findIndex((tab) => tab.id === id);
    if (idx < 0) return;
    const tab = this.tabs[idx];
    if (tab.type === "terminal") {
      const terms = this.panelTerminals.get(id);
      if (terms) {
        for (const t of terms) {
          t.cleanup();
          t.resizeObs.disconnect();
          t.term.dispose();
          const api = (window as any).electronAPI;
          if (api) api.terminalKill(t.ptyId);
        }
        this.panelTerminals.delete(id);
        this.panelActiveTermIdx.delete(id);
      }
      const dd = document.querySelector(`#term-ctx-menu-${id}`);
      if (dd) dd.remove();
    }
    if (tab.type === "browser") {
      const bv = this.panelBrowsers.get(id);
      if (bv) {
        bv.destroy();
        this.panelBrowsers.delete(id);
      }
    }
    if (tab.type === "markdown") {
      const mp = this.panelMarkdownPreviews.get(id);
      if (mp) {
        mp.destroy();
        this.panelMarkdownPreviews.delete(id);
      }
    }
    if (tab.type === "code") {
      const editor = this.panelCodeEditors.get(id);
      if (editor) {
        unregisterEditor(editor);
        editor.dispose();
        this.panelCodeEditors.delete(id);
      }
    }
    if (tab.type === "media") {
      const mv = this.panelMediaViewers.get(id);
      if (mv) {
        mv.destroy();
        this.panelMediaViewers.delete(id);
      }
    }
    this.tabs.splice(idx, 1);
    _saveTabs(this.tabs);
    if (this.tabs.length === 0) {
      this.tabs = [];
      this.activeTab = "";
    } else if (this.activeTab === id) {
      this.activeTab = this.tabs[0].id;
    }
    this.renderTabs();
  }

  /* ── Resize ─────────────────────────────────────────────────────── */

  private bindResize(): void {
    const handle = this.el.querySelector(".si-resize-handle") as HTMLElement;
    if (!handle) return;

    handle.addEventListener("mousedown", (e) => {
      this.resizing = true;
      handle.classList.add("resizing");
      this.resizeStartX = e.clientX;
      this.resizeStartW = this.el.offsetWidth;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      e.preventDefault();
    });

    document.addEventListener("mousemove", (e) => {
      if (!this.resizing) return;
      const dx = this.resizeStartX - e.clientX;
      const newW = Math.min(800, Math.max(200, this.resizeStartW + dx));
      this.el.style.setProperty("--sidebar-w", newW + "px");
      document.getElementById("main-body")?.style.setProperty("--sidebar-w", newW + "px");
      this.el.style.transition = "none";
    });

    document.addEventListener("mouseup", () => {
      if (!this.resizing) return;
      this.resizing = false;
      const handle = this.el.querySelector(".si-resize-handle") as HTMLElement;
      if (handle) handle.classList.remove("resizing");
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      this.el.style.transition = "";
      this.sidebarWidth = this.el.offsetWidth;
      try { localStorage.setItem("session-sidebar-width", String(this.sidebarWidth)); } catch {}
    });
  }

  getSavedWidth(): number {
    return this.sidebarWidth;
  }

  saveWidth(): void {
    this.sidebarWidth = this.el.offsetWidth;
    try { localStorage.setItem("session-sidebar-width", String(this.sidebarWidth)); } catch {}
  }

  restoreWidth(): void {
    this.el.style.setProperty("--sidebar-w", this.sidebarWidth + "px");
    document.getElementById("main-body")?.style.setProperty("--sidebar-w", this.sidebarWidth + "px");
  }

  saveSidebarVisibility(): void {
    const panel = document.getElementById("session-inner-sidebar");
    if (!panel) return;
    this._sessionSidebarVisible.set(this._tabKey, !panel.classList.contains("hidden"));
  }

  restoreSidebarVisibility(): void {
    const panel = document.getElementById("session-inner-sidebar");
    const mainBody = document.getElementById("main-body");
    const appEl = document.getElementById("app");
    if (!panel || !mainBody) return;
    const visible = this._sessionSidebarVisible.get(this._tabKey) ?? false;
    if (visible) {
      this.restoreWidth();
      panel.classList.remove("hidden");
      mainBody.classList.remove("sidebar-hidden");
      appEl?.classList.add("sidebar-collapsed");
      this.renderForce();
    } else {
      panel.classList.add("hidden");
      mainBody.classList.add("sidebar-hidden");
    }
  }

  /* ── Collapsible Panel State ────────────────────────────────────── */
  private collapsedPanels = new Set<string>();

  private togglePanel(panelId: string): void {
    if (this.collapsedPanels.has(panelId)) {
      this.collapsedPanels.delete(panelId);
    } else {
      this.collapsedPanels.add(panelId);
    }
    this.renderContent();
  }

  /* ── Content Rendering ──────────────────────────────────────────── */

  private renderContent(): void {
    if (!this.infoBody) return;
    const st = getState();

    const panels: string[] = [];
    panels.push(this.renderIndexPanel(st));
    panels.push(this.renderProjectRulesPanel(st));
    panels.push(this.renderHooksPanel(st));
    panels.push(this.renderProgressPanel(st));
    panels.push(this.renderArtifactsPanel(st));
    panels.push(this.renderReferencesPanel(st));
    panels.push(this.renderCanvasPanel(st));

    this.infoBody.innerHTML = `<div class="si-panels">${panels.join("")}</div>`;
    this.bindPanelToggles();
    this.bindReviewLink();
    this.bindIndexManagement();
    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.infoBody });
    }
  }

  private bindPanelToggles(): void {
    this.infoBody.querySelectorAll(".si-panel-header").forEach((header) => {
      header.addEventListener("click", () => {
        const panelId = (header as HTMLElement).dataset.panel!;
        this.togglePanel(panelId);
      });
    });
  }

  private bindReviewLink(): void {
    const link = document.getElementById("si-view-all-changes");
    if (link) {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        this.showReviewTab("", undefined);
      });
    }
    this.infoBody.querySelectorAll(".si-diff-review").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const path = (el as HTMLElement).dataset.path!;
        const st = getState();
        const artifact = st.artifacts.find((a: ArtifactItem) => a.path === path);
        this.showReviewTab(path, artifact);
      });
    });
  }

  private bindIndexManagement(): void {
    const btn = document.getElementById("index-mgmt-btn");
    if (!btn) return;

    // Use a single-shot click handler (remove on first call to avoid stack-up)
    if ((btn as any)._bound) return;
    (btn as any)._bound = true;

    const st = getState();
    const hasIndex = st.indexStatus !== "idle" && st.indexStatus !== "no_workspace"
      && (st.indexStatus === "ready" || st.indexStatus === "error" || (st.indexProgress || 0) > 0);

    if (hasIndex) {
      // Show dropdown with reindex / delete-index
      let menu = document.getElementById("index-mgmt-menu") as HTMLElement | null;
      if (!menu) {
        menu = document.createElement("div");
        menu.id = "index-mgmt-menu";
        menu.className = "context-menu";
        menu.style.cssText = "display:none;position:fixed;z-index:10000";
        document.body.appendChild(menu);
      }
      menu.innerHTML = `
        <div class="context-menu-item" data-action="reindex">${t("settings.reindex")}</div>
        <div class="context-menu-item" data-action="delete-index">${t("settings.deleteIndex")}</div>`;

      btn.addEventListener("click", function _onSettingsClick(e: Event) {
        e.stopPropagation();
        document.querySelectorAll(".context-menu").forEach(m => (m as HTMLElement).style.display = "none");
        const shown = menu!.style.display !== "none";
        if (shown) {
          menu!.style.display = "none";
        } else {
          const rect = btn.getBoundingClientRect();
          menu!.style.left = Math.max(8, rect.right - 160) + "px";
          menu!.style.top = (rect.bottom + 4) + "px";
          menu!.style.display = "block";
          setTimeout(() => {
            document.addEventListener("click", function _closeMenu() {
              menu!.style.display = "none";
              document.removeEventListener("click", _closeMenu);
            });
          }, 0);
        }
      });

      menu.querySelectorAll(".context-menu-item").forEach((item) => {
        (item as HTMLElement).onclick = (e) => {
          e.stopPropagation();
          menu!.style.display = "none";
          const action = (item as HTMLElement).dataset.action!;
          send({ type: action === "reindex" ? "reindex_workspace" : "delete_index" });
        };
      });
    } else {
      // No index: clicking button directly starts indexing
      btn.innerHTML = `<i data-lucide="play" style="width:14px;height:14px;display:block;color:var(--text-secondary)"></i>`;
      btn.addEventListener("click", function _onStartClick(e: Event) {
        e.stopPropagation();
        console.log("[index] starting index...");
        send({ type: "reindex_workspace" });
      });
      if (typeof (window as any).lucide !== "undefined") {
        requestAnimationFrame(() => (window as any).lucide.createIcons());
      }
    }
  }

  private panelHeader(id: string, label: string, icon: string, badge?: string): string {
    const collapsed = this.collapsedPanels.has(id) ? " si-panel-collapsed" : "";
    const chevron = this.collapsedPanels.has(id) ? "chevron-right" : "chevron-down";
    const badgeHTML = badge ? `<span class="si-panel-badge">${this.esc(badge)}</span>` : "";
    return `<div class="si-panel-header${collapsed}" data-panel="${id}">
      <i data-lucide="${icon}" class="lucide si-panel-header-icon"></i>
      <span class="si-panel-title">${label}</span>
      ${badgeHTML}
      <i data-lucide="${chevron}" class="lucide si-panel-chevron"></i>
    </div>`;
  }

  /* ── Progress Panel (Todo / Plan Items) ─────────────────────────── */

  private renderProgressPanel(st: ReturnType<typeof getState>): string {
    const items = st.planItems || [];
    let bodyHTML = "";

    if (items.length === 0) {
      bodyHTML = `<div class="si-panel-empty">${t("sessionInner.noProgress")}</div>`;
    } else {
      bodyHTML = items.map((item) => {
        let iconClass = "si-todo-pending";
        let iconSvg = "circle";
        if (item.status === "done") { iconClass = "si-todo-done"; iconSvg = "check-circle-2"; }
        else if (item.status === "active") { iconClass = "si-todo-active"; iconSvg = "loader"; }
        return `<div class="si-todo-item ${iconClass}">
          <i data-lucide="${iconSvg}" class="lucide lucide-sm si-todo-icon"></i>
          <span class="si-todo-text">${this.esc(item.text)}</span>
        </div>`;
      }).join("");
    }

    return `<div class="si-panel">
      ${this.panelHeader("progress", t("sessionInner.progress"), "list-checks")}
      <div class="si-panel-body${this.collapsedPanels.has("progress") ? " hidden" : ""}"><div class="si-panel-inner">${bodyHTML}</div></div>
    </div>`;
  }

  /* ── Artifacts Panel (File Changes) ─────────────────────────────── */

  private renderArtifactsPanel(st: ReturnType<typeof getState>): string {
    const artifacts = st.artifacts;
    let bodyHTML = "";

    if (!artifacts || artifacts.length === 0) {
      bodyHTML = `<div class="si-panel-empty">${t("sessionInner.noArtifacts")}</div>`;
    } else {
      const countBadge = `${t("sessionInner.changedFiles")} ${artifacts.length}`;
      bodyHTML = `<div class="si-artifacts-header">
        <span>${countBadge}</span>
        <a class="si-artifacts-link" id="si-view-all-changes" href="#">${t("sessionInner.viewAllChanges")} <i data-lucide="arrow-up-right" class="lucide lucide-xs"></i></a>
      </div>
      <div class="si-diff-list">${artifacts.map((a) => {
        const extIcon = getFileIcon(a.name);
        return `<div class="si-diff-file" data-path="${this.esc(a.path)}">
          <img src="${extIcon}" class="si-diff-icon icon" style="width:14px;height:14px">
          <span class="si-diff-name">${this.esc(a.name)}</span>
          <span class="si-diff-stats">
            <span class="si-diff-add">+${a.diff_text ? (a.diff_text.match(/^\+/gm) || []).length : (a.size > 0 ? Math.min(a.size, 9999) : 0)}</span>
            <span class="si-diff-remove">-${a.diff_text ? (a.diff_text.match(/^-/gm) || []).length : 0}</span>
          </span>
          <a class="si-diff-review" href="#" data-path="${this.esc(a.path)}">${t("sessionInner.viewAllChanges")} <i data-lucide="eye" class="lucide lucide-xs"></i></a>
        </div>`;
      }).join("")}</div>`;
    }

    return `<div class="si-panel">
      ${this.panelHeader("artifacts", t("sessionInner.artifacts"), "file-code-2")}
      <div class="si-panel-body${this.collapsedPanels.has("artifacts") ? " hidden" : ""}"><div class="si-panel-inner">${bodyHTML}</div></div>
    </div>`;
  }

  /* ── References Panel ───────────────────────────────────────────── */

  private renderReferencesPanel(st: ReturnType<typeof getState>): string {
    const refs = st.references || [];
    const filteredRefs = refs.filter((r: ReferenceItem) => {
      const t = r.tool.toLowerCase();
      return t.startsWith("mcp__") || t.startsWith("memory_") || t.startsWith("web_") || t.includes("profile");
    });

    if (filteredRefs.length === 0) {
      const bodyHTML = `<div class="si-panel-empty">${t("sessionInner.noRefs")}</div>`;
      return `<div class="si-panel">
        ${this.panelHeader("references", t("sessionInner.references"), "link-2")}
        <div class="si-panel-body${this.collapsedPanels.has("references") ? " hidden" : ""}"><div class="si-panel-inner">${bodyHTML}</div></div>
      </div>`;
    }

    // Show most recent references first, limit to 50
    const shown = filteredRefs.slice(-50).reverse();

    // Group references by broad category so each class can be collapsed.
    const groups: { key: string; label: string; icon: string; refs: ReferenceItem[] }[] = [
      { key: "ref-group-web", label: t("sessionInner.referencesWeb") || "Web", icon: "globe", refs: [] },
      { key: "ref-group-memory", label: t("sessionInner.referencesMemory") || "Memory", icon: "brain", refs: [] },
      { key: "ref-group-mcp", label: t("sessionInner.referencesMcp") || "MCP", icon: "cable", refs: [] },
    ];
    for (const r of shown) {
      const t = r.tool.toLowerCase();
      if (t.startsWith("mcp__")) {
        groups[2].refs.push(r);
      } else if (t.includes("memory") || t.includes("profile")) {
        groups[1].refs.push(r);
      } else {
        groups[0].refs.push(r);
      }
    }

    const bodyHTML = groups
      .filter((g) => g.refs.length > 0)
      .map((g) => {
        const listHTML = g.refs.map((r: ReferenceItem) => {
          const icon = r.icon || "zap";
          const toolLabel = r.tool.startsWith("mcp__") ? r.tool.split("__").slice(0, 2).join(":") : r.tool;
          return `<div class="si-ref-item">
            <i data-lucide="${icon}" class="lucide si-ref-icon"></i>
            <div class="si-ref-content">
              <span class="si-ref-tool">${this.esc(toolLabel)}</span>
              <span class="si-ref-summary">${this.esc(r.summary)}</span>
            </div>
          </div>`;
        }).join("");
        return `<div class="si-ref-group">
          ${this.panelHeader(g.key, g.label, g.icon, String(g.refs.length))}
          <div class="si-panel-body${this.collapsedPanels.has(g.key) ? " hidden" : ""}"><div class="si-panel-inner si-ref-list">${listHTML}</div></div>
        </div>`;
      }).join("");

    return `<div class="si-panel">
      ${this.panelHeader("references", t("sessionInner.references"), "link-2", String(filteredRefs.length))}
      <div class="si-panel-body${this.collapsedPanels.has("references") ? " hidden" : ""}"><div class="si-panel-inner">${bodyHTML}</div></div>
    </div>`;
  }

  /* ── Canvas Panel (Context / Tokens / Info) ─────────────────────── */

  private renderCanvasPanel(st: ReturnType<typeof getState>): string {
    const models = st.modelConfigs;
    const active = models[st.activeModelIndex];
    const contextLimit = active ? (active.context_window || active.max_tokens || 0) : 0;
    const telemetry = st.telemetry;
    const tu = st.tokenUsage;

    // Context usage: use server-sent context_tokens (actual message count),
    // NOT output/usage tokens (which are minuscule vs context window).
    // Falls back to last compact event's new_tokens if not yet available.
    const lastCompact = (st.compactEvents || []).length > 0 ? st.compactEvents[st.compactEvents.length - 1] : null;
    const totalUsed = st.contextTokens || lastCompact?.new_tokens || 0;
    const usagePct = contextLimit > 0 ? ((totalUsed / contextLimit) * 100).toFixed(1) : null;
    const usageWarn = usagePct !== null && parseFloat(usagePct) > 80;
    const usageDanger = usagePct !== null && parseFloat(usagePct) > 95;

    let progressFillClass = "";
    if (usageDanger) progressFillClass = " danger";
    else if (usageWarn) progressFillClass = " warn";

    const rows: string[] = [];

    // Progress bar
    if (usagePct !== null) {
      rows.push(`<div class="si-canvas-progress-wrap">
        <div class="si-canvas-progress-track">
          <div class="si-canvas-progress-fill${progressFillClass}" style="width:${Math.min(parseFloat(usagePct), 100)}%"></div>
        </div>
      </div>`);
    }

    if (contextLimit > 0) {
      rows.push(`<div class="si-canvas-row">
        <span class="si-canvas-label">${t("sessionInner.contextWindow")}</span>
        <span class="si-canvas-value">${this.fmtNum(contextLimit)}</span>
      </div>`);
    }

    rows.push(`<div class="si-canvas-row">
      <span class="si-canvas-label">${t("sessionInner.contextUsed")}</span>
      <span class="si-canvas-value${usageWarn ? " si-canvas-warn" : ""}">${this.fmtNum(totalUsed)}${usagePct !== null ? ` <span class="si-canvas-pct">(${usagePct}%)</span>` : ""}</span>
    </div>`);

    if (tu) {
      rows.push(`<div class="si-canvas-row">
        <span class="si-canvas-label">${t("sessionInner.inputTokens")}</span>
        <span class="si-canvas-value">${this.fmtNum(tu.input_tokens)}</span>
      </div>`);
      rows.push(`<div class="si-canvas-row">
        <span class="si-canvas-label">${t("sessionInner.outputTokens")}</span>
        <span class="si-canvas-value">${this.fmtNum(tu.output_tokens)}</span>
      </div>`);
    }

    // Derive Compactions / Tool Calls from authoritative local state so the
    // canvas panel always shows real numbers, even if backend telemetry is
    // disabled or not yet streamed.
    const compactCount = st.compactEvents.length
      + (telemetry?.compactions ? Math.max(0, telemetry.compactions - st.compactEvents.length) : 0);
    const toolCallCount = st.messages.reduce(
      (sum, m) => sum + m.toolCalls.length, 0,
    );
    const hasCompactOrTools = compactCount > 0 || toolCallCount > 0 || telemetry;
    if (hasCompactOrTools) {
      rows.push(`<div class="si-canvas-divider"></div>`);
      rows.push(`<div class="si-canvas-row">
        <span class="si-canvas-label">${t("sessionInner.compactions")}</span>
        <span class="si-canvas-value">${compactCount}</span>
      </div>`);
      rows.push(`<div class="si-canvas-row">
        <span class="si-canvas-label">${t("sessionInner.toolCalls")}</span>
        <span class="si-canvas-value">${toolCallCount}</span>
      </div>`);
    }

    const turns = st.messages.filter((m) => m.role === "user").length;
    rows.push(`<div class="si-canvas-divider"></div>`);
    rows.push(`<div class="si-canvas-row">
      <span class="si-canvas-label">${t("sessionInner.turns")}</span>
      <span class="si-canvas-value">${turns}</span>
    </div>`);

    const bodyHTML = rows.length > 0
      ? `<div class="si-canvas-grid">${rows.join("")}</div>`
      : `<div class="si-panel-empty">${t("sessionInner.noData")}</div>`;

    return `<div class="si-panel">
      ${this.panelHeader("canvas", t("sessionInner.canvas"), "sliders")}
      <div class="si-panel-body${this.collapsedPanels.has("canvas") ? " hidden" : ""}"><div class="si-panel-inner">${bodyHTML}</div></div>
    </div>`;
  }

  private renderIndexPanel(st: ReturnType<typeof getState>): string {
    if (st.workspaceMode !== "iwork") return "";
    const status = st.indexStatus;
    const btnId = "index-mgmt-btn";
    const pct = status === "ready" ? 100 : Math.min(st.indexProgress || 0, 100);

    const html = `
      <div style="display:flex;align-items:center;gap:8px;margin:4px 0">
        <div class="si-canvas-progress-wrap" style="flex:1">
          <div class="si-canvas-progress-track">
            <div class="si-canvas-progress-fill" style="width:${pct}%"></div>
          </div>
        </div>
        <span style="font-size:11px;white-space:nowrap;min-width:32px;text-align:right;color:var(--text-secondary)">${pct}%</span>
        <button id="${btnId}" class="si-panel-action-btn" style="flex-shrink:0;background:none;border:none;cursor:pointer;padding:2px;color:var(--text-secondary)" data-tooltip="${t("settings.indexActions")}">
          <i data-lucide="settings-2" style="width:14px;height:14px;display:block;color:var(--text-secondary)"></i>
        </button>
      </div>`;

    return `<div class="si-panel">
      ${this.panelHeader("index", t("sidebar.index"), "file-search")}
      <div class="si-panel-body${this.collapsedPanels.has("index") ? " hidden" : ""}"><div class="si-panel-inner">${html}</div></div>
    </div>`;
  }

  private renderProjectRulesPanel(st: ReturnType<typeof getState>): string {
    if (st.workspaceMode !== "iwork") return "";
    const rules = st.projectRules || [];
    let bodyHTML: string;
    if (rules.length === 0) {
      bodyHTML = `<div class="si-panel-empty">${t("sessionInner.noProjectRules")}</div>`;
    } else {
      const rows = rules.map((r) => {
        const mod = new Date(r.modified * 1000).toLocaleString();
        return `<div class="si-rule-row">
          <i data-lucide="file-text" class="lucide lucide-sm si-rule-icon"></i>
          <div class="si-rule-body">
            <div class="si-rule-name">${this.esc(r.name)}</div>
            <div class="si-rule-path">${this.esc(r.path)}</div>
          </div>
          <span class="si-rule-priority">p${r.priority}</span>
          <span class="si-rule-time">${this.esc(mod)}</span>
        </div>`;
      }).join("");
      bodyHTML = `<div class="si-rule-list">${rows}</div>`;
    }
    return `<div class="si-panel">
      ${this.panelHeader("project-rules", t("sidebar.projectRules"), "book-open-check")}
      <div class="si-panel-body${this.collapsedPanels.has("project-rules") ? " hidden" : ""}"><div class="si-panel-inner">${bodyHTML}</div></div>
    </div>`;
  }

  private renderHooksPanel(st: ReturnType<typeof getState>): string {
    if (st.workspaceMode !== "iwork") return "";
    const hooks = st.projectHooks || [];
    let bodyHTML: string;
    if (hooks.length === 0) {
      bodyHTML = `<div class="si-panel-empty">${t("sessionInner.noProjectHooks")}</div>`;
    } else {
      const rows = hooks.map((h) => {
        const evt = this.esc(h.event_type);
        const matcher = this.esc(h.matcher || "*");
        const cmd = this.esc(h.command || "");
        const src = this.esc(h.source_path || "");
        return `<div class="si-hook-row" data-tooltip="${src}">
          <i data-lucide="zap" class="lucide lucide-sm si-hook-icon"></i>
          <div class="si-hook-body">
            <div class="si-hook-event">${evt} <span class="si-hook-matcher">${matcher}</span></div>
            <div class="si-hook-cmd">${cmd}</div>
          </div>
        </div>`;
      }).join("");
      bodyHTML = `<div class="si-hook-list">${rows}</div>`;
    }
    return `<div class="si-panel">
      ${this.panelHeader("hooks", t("sidebar.hooks"), "webhook")}
      <div class="si-panel-body${this.collapsedPanels.has("hooks") ? " hidden" : ""}"><div class="si-panel-inner">${bodyHTML}</div></div>
    </div>`;
  }

  private fmtNum(n: number): string {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
    if (n >= 1000) return (n / 1000).toFixed(1) + "k";
    return String(n);
  }

  private esc(s: string): string {
    const el = document.createElement("span");
    el.textContent = s;
    return el.innerHTML;
  }
}

