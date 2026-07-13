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
 * code editor, file review, agent, …), each with its own embedded xterm
 * terminal instances. Width is persisted to `localStorage`.
 */

import { getState, subscribe, addAttachments } from "./state.js";
import type { ArtifactItem, AttachmentMeta, ReferenceItem } from "./types.js";
import { t, onLocaleChange } from "./i18n.js";
import { send } from "./ws.js";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebglAddon } from "@xterm/addon-webgl";

/** Definition of a sidebar tab (id + whether it can be closed). */
export interface TabDef {
  id: string;
  closable: boolean;
}

interface NewTabOption {
  id: string;
  icon: string;
}

const NEW_TAB_OPTIONS: NewTabOption[] = [
  { id: "terminal", icon: "terminal" },
  { id: "editor", icon: "code-2" },
  { id: "review", icon: "eye" },
  { id: "files", icon: "folder-open" },
];

function tabLabel(id: string): string {
  switch (id) {
    case "terminal": return t("sessionInner.tabTerminal");
    case "files": return t("sessionInner.tabFiles");
    case "editor": return t("sessionInner.tabEditor");
    case "review": return t("sessionInner.tabReview");
    default: return id;
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
  private tabs: TabDef[] = [
    { id: "info", closable: true },
  ];
  private activeTab: string = "info";

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

  /* terminals �?each panel can have multiple sub-terminals */
  private panelTerminals = new Map<string, Array<{ label: string; ptyId: number; term: any; cleanup: () => void; resizeObs: ResizeObserver }>>();
  private panelActiveTermIdx = new Map<string, number>();
  private panelShellPath = new Map<string, string>();
  private panelShellArgs = new Map<string, string[]>();

  /**
   * Constructor: resolves DOM nodes, restores width and wires tabs/resize.
   */
  constructor() {
    this.el = document.getElementById("session-inner-sidebar")!;
    this.tabBar = this.el.querySelector(".tab-bar")!;
    this.tabList = document.createElement("div");
    this.tabList.className = "tab-list";
    this.tabBody = this.el.querySelector(".tab-body")!;

    // Default tabs �?only summary by default, others via +
    this.tabs = [];
    this.activeTab = "";

    try {
      const saved = localStorage.getItem("session-sidebar-width");
      if (saved) this.sidebarWidth = parseInt(saved, 10) || 280;
    } catch {}
    this.el.style.setProperty("--sidebar-w", this.sidebarWidth + "px");
    document.getElementById("main-body")?.style.setProperty("--sidebar-w", this.sidebarWidth + "px");

    subscribe(() => this.render());
    onLocaleChange(() => this.render());
    this.renderTabs();
    this.bindAddButton();
    this.bindResize();
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
    if (this.tabs.length === 0) {
      this.renderHomePage();
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
        ? `<button class="tab-close" data-close="${tab.id}" title="${t("sessionInner.closeTab")}"><i data-lucide="x" class="lucide lucide-sm"></i></button>`
        : "";
      return `<div class="tab${activeCls} tab--fill" data-tab="${tab.id}" draggable="false">
        <span class="tab-label">${this.esc(tabLabel(tab.id))}</span>${closeBtn}
      </div>`;
    }).join("");

    if (!this.tabBar.contains(this.tabList)) {
      this.tabBar.prepend(this.tabList);
    }

    this.bindTabEvents();
    if (this.tabs.length === 0) {
      this.renderHomePage();
    } else {
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
    btn.title = t("sessionInner.newTab");
    btn.innerHTML = `<i data-lucide="plus" class="lucide lucide-sm"></i>`;
    this.tabBar.appendChild(btn);
    this.tabAddBtn = btn;

    const dropdown = document.createElement("div");
    dropdown.className = "tab-add-dropdown hidden";
    document.body.appendChild(dropdown);
    this.tabAddDropdown = dropdown;

    const rebuildDropdown = () => {
      const openIds = new Set(this.tabs.map((t) => t.id));
      const available = NEW_TAB_OPTIONS.filter((opt) => !openIds.has(opt.id));
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
            const id = (item as HTMLElement).dataset.add!;
            await this.createTab(id);
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
    // Dispose all open terminal PTYs and the xterm instances bound to
    // them.  Skipping this leaks WebGL contexts and zombie rAF loops.
    const api = (window as any).electronAPI;
    for (const [, terms] of this.panelTerminals) {
      for (const t of terms) {
        try { t.cleanup(); } catch { /* noop */ }
        try { t.resizeObs.disconnect(); } catch { /* noop */ }
        try { t.term.dispose(); } catch { /* noop */ }
        try { api?.terminalKill?.(t.ptyId); } catch { /* noop */ }
      }
    }
    this.panelTerminals.clear();
    this.panelActiveTermIdx.clear();
    this.panelShellPath.clear();
    this.panelShellArgs.clear();

    // Remove the per-panel shell dropdown that setupTerminalPanel()
    // appended to document.body — it is not a child of #session-inner-sidebar
    // so querySelector'ing inside that container would not find it.
    document.querySelectorAll(".si-term-shell-dropdown").forEach((el) => el.remove());

    // Rebuild the "+" tab affordance after reset. Its dropdown lives on
    // document.body, so removing it without rebinding leaves the button inert.
    this.tabAddBtn?.remove();
    this.tabAddBtn = null;
    this.tabAddDropdown?.remove();
    this.tabAddDropdown = null;
    if (this.tabAddDocClickHandler) {
      document.removeEventListener("click", this.tabAddDocClickHandler);
      this.tabAddDocClickHandler = null;
    }

    // Remove every panel DOM node; renderTabs() will recreate the default
    // "info" tab from scratch on the next render cycle.
    this.tabBody.querySelectorAll(".tab-panel").forEach((p) => p.remove());

    // Reset the in-memory tab list to default (empty).
    this.tabs = [];
    this.activeTab = "";
    await this.renderTabs();
    this.bindAddButton();
  }

  private renderHomePage(): void {
    // Remove any leftover panels
    this.tabBody.querySelectorAll(".tab-panel").forEach((p) => p.remove());

    const cards = [
      { id: "terminal", icon: "terminal", label: t("sessionInner.tabTerminal"), desc: t("sessionInner.tabTerminalDesc") },
      { id: "files", icon: "folder-open", label: t("sessionInner.tabFiles"), desc: t("sessionInner.tabFilesDesc") },
      { id: "editor", icon: "code-2", label: t("sessionInner.tabEditor"), desc: t("sessionInner.tabEditorDesc") },
      { id: "review", icon: "eye", label: t("sessionInner.tabReview"), desc: t("sessionInner.tabReviewDesc") },
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
        const id = (el as HTMLElement).dataset.tab!;
        this.createTab(id);
      });
    });

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.tabBody });
    }
  }

  public async createTab(id: string): Promise<void> {
    if (!this.tabs.some((tab) => tab.id === id)) {
      this.tabs.push({ id, closable: true });
    }
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

      if (t.id === "terminal") {
        await this.setupTerminalPanel(panel);
      } else if (t.id === "files") {
        this.setupFilesPanel(panel);
      } else if (t.id === "editor") {
        this.setupEditorPanel(panel);
      } else if (t.id === "review") {
        this.setupReviewPanel(panel);
      }

      this.tabBody.appendChild(panel);
    }

    this.tabBody.querySelectorAll(".tab-panel").forEach((p) => {
      const pid = (p as HTMLElement).dataset.panel || "";
      const exists = this.tabs.some((t) => t.id === pid);
      if (!exists) {
        if (pid === "terminal") {
          const terms = this.panelTerminals.get(pid);
          if (terms) {
            for (const t of terms) {
              t.cleanup();
              t.resizeObs.disconnect();
              t.term.dispose();
              const api = (window as any).electronAPI;
              if (api) api.terminalKill(t.ptyId);
            }
            this.panelTerminals.delete(pid);
            this.panelActiveTermIdx.delete(pid);
          }
          /* Remove the shell dropdown from document.body */
          const dd = document.querySelector(".si-term-shell-dropdown");
          if (dd) dd.remove();
        }
        p.remove();
      } else {
        p.classList.toggle("active", pid === this.activeTab);
      }
    });
  }

  /* ── Terminal ───────────────────────────────────────────────────── */

  private async setupTerminalPanel(panel: HTMLElement): Promise<void> {
    panel.innerHTML = `<div class="si-terminal-wrap">
      <div class="tab-bar tab-bar--term">
        <div class="tab-list"></div>
        <button class="tab-action-btn" title="${t("sessionInner.termNew")}"><i data-lucide="plus" class="lucide lucide-sm"></i></button>
        <button class="tab-action-btn danger" title="${t("sessionInner.termKillAll")}"><i data-lucide="trash-2" class="lucide lucide-sm"></i></button>
      </div>
      <div class="si-term-empty"><i data-lucide="terminal" class="lucide" style="width:32px;height:32px;opacity:0.4"></i><span>${t("sessionInner.termEmpty")}</span></div>
      <div class="si-terminal-body" style="display:none"></div>
    </div>`;

    const body = panel.querySelector(".si-terminal-body") as HTMLElement;
    const emptyEl = panel.querySelector(".si-term-empty") as HTMLElement;
    const tabList = panel.querySelector(".tab-bar--term .tab-list") as HTMLElement;
    const addBtn = panel.querySelector(".tab-bar--term .tab-action-btn") as HTMLElement;
    const killAllBtn = panel.querySelector(".tab-bar--term .tab-action-btn.danger") as HTMLElement;

    /* Create shell dropdown on document.body to avoid parent overflow clipping */
    const shellDropdown = document.createElement("div");
    shellDropdown.className = "si-term-shell-dropdown hidden";
    document.body.appendChild(shellDropdown);

    const panelId = panel.dataset.panel || "terminal";
    this.panelTerminals.set(panelId, []);
    this.panelActiveTermIdx.set(panelId, 0);

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

    const getShellPath = () => this.panelShellPath.get(panelId) || shells[0]?.path || "";
    const getShellArgs = () => this.panelShellArgs.get(panelId) || shells[0]?.args || [];

    const buildTheme = () => {
      const st = getState();
      const isLight = st.theme === "light";
      return isLight ? {
        background: "#f3f3f3", foreground: "#1e1e1e", cursor: "#000000",
        selectionBackground: "rgba(0,0,0,0.10)",
        black: "#000000", red: "#cd3131", green: "#00bc00",
        yellow: "#949800", blue: "#0451a5", magenta: "#bc05bc",
        cyan: "#0598bc", white: "#555555",
        brightBlack: "#666666", brightRed: "#cd3131", brightGreen: "#14ce14",
        brightYellow: "#b5ba00", brightBlue: "#0451a5", brightMagenta: "#bc05bc",
        brightCyan: "#0598bc", brightWhite: "#a5a5a5",
      } : {
        background: "#252526", foreground: "#cccccc", cursor: "#ffffff",
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

    const showTermEmpty = (show: boolean) => {
      emptyEl.style.display = show ? "flex" : "none";
      body.style.display = show ? "none" : "flex";
      tabList.style.display = show ? "none" : "";
      killAllBtn.style.display = show ? "none" : "";
    };

    const spawnAndAttach = async () => {
      const sh = getShellPath();
      const args = getShellArgs();
      let ptyId: number;
      try {
        const result = await api.terminalSpawn(sh || undefined, args.length ? args : undefined);
        if (result.error) {
          body.innerHTML = `<div class="si-empty">${t("sessionInner.termError")}: ${this.esc(result.error)}</div>`;
          return null;
        }
        ptyId = result.id as number;
      } catch (e: any) {
        body.innerHTML = `<div class="si-empty">${t("sessionInner.termError")}: ${this.esc(e?.message || String(e))}</div>`;
        return null;
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

      term.element?.addEventListener("contextmenu", (ev: MouseEvent) => {
        ev.preventDefault();
        ctxTermTarget = term;
        ctxMenu.style.top = ev.clientY + "px";
        ctxMenu.style.left = ev.clientX + "px";
        ctxMenu.classList.remove("hidden");
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

      const obs = new ResizeObserver(() => {
        try {
          fitAddon.fit();
          const dims = (term as any)._core?._renderService?.dimensions;
          if (dims && dims.cols > 0 && dims.rows > 0) {
            api.terminalResize(ptyId, dims.cols, dims.rows);
          }
        } catch {}
      });
      obs.observe(body);
      setTimeout(() => { try { fitAddon.fit(); } catch {} }, 50);

      term.focus();

      const cleanup = () => { dataCleanup(); exitCleanup(); };
      return { term, ptyId, cleanup, resizeObs: obs };
    };

    const switchTerminal = (pid: string, idx: number, _termBody: HTMLElement) => {
      const terms = this.panelTerminals.get(pid) || [];
      if (idx < 0 || idx >= terms.length) return;
      this.panelActiveTermIdx.set(pid, idx);
      terms.forEach((ti, i) => {
        (ti.term as any).element.style.display = i === idx ? "" : "none";
      });
      if (terms[idx]) terms[idx].term.focus();
    };

    const killLocal = (pid: string, idx: number, _termBody: HTMLElement) => {
      const terms = this.panelTerminals.get(pid);
      if (!terms || idx < 0 || idx >= terms.length) return;
      const tobj = terms[idx];
      tobj.cleanup();
      tobj.resizeObs.disconnect();
      tobj.term.dispose();
      if (api) api.terminalKill(tobj.ptyId);
      terms.splice(idx, 1);

      if (terms.length === 0) {
        this.panelActiveTermIdx.set(pid, -1);
        showTermEmpty(true);
        renderTermTabs();
      } else {
        const cur = this.panelActiveTermIdx.get(pid) || 0;
        const newIdx = Math.min(cur, terms.length - 1);
        switchTerminal(pid, newIdx, body);
        renderTermTabs();
      }
    };
    this.killSubTerminal = killLocal;

    /* merged shell selector + add button */
    const openShellDropdown = (anchor: HTMLElement, spawnAfter: boolean) => {
      const isHidden = shellDropdown.classList.contains("hidden");
      if (!isHidden) return;
      const rect = anchor.getBoundingClientRect();
      const dw = Math.max(200, rect.width);
      shellDropdown.style.top = (rect.bottom + 4) + "px";
      const rightEdge = rect.left + dw;
      const fitsRight = rightEdge <= window.innerWidth - 8;
      shellDropdown.style.left = fitsRight ? rect.left + "px" : "auto";
      shellDropdown.style.right = fitsRight ? "auto" : (window.innerWidth - rect.right + "px");
      shellDropdown.style.minWidth = dw + "px";
      shellDropdown.style.maxHeight = Math.min(240, window.innerHeight - rect.bottom - 40) + "px";
      const cur = getShellPath();
      shellDropdown.innerHTML = shells.map((s) => {
        const active = (s.path === cur) ? " active" : "";
        return `<div class="si-term-shell-item${active}" data-path="${this.esc(s.path)}" data-args="${this.esc(JSON.stringify(s.args || []))}">
          <span>${this.esc(s.name)}</span>
          <span class="si-term-shell-path">${this.esc(s.path)}</span>
        </div>`;
      }).join("");
      shellDropdown.querySelectorAll(".si-term-shell-item").forEach((item) => {
        item.addEventListener("click", () => {
          const el = item as HTMLElement;
          this.panelShellPath.set(panelId, el.dataset.path || "");
          try { this.panelShellArgs.set(panelId, JSON.parse(el.dataset.args || "[]")); } catch { this.panelShellArgs.set(panelId, []); }
          shellDropdown.classList.add("hidden");
          if (spawnAfter) {
            spawnAndAttach().then((inst) => {
              if (!inst) return;
              const tms = this.panelTerminals.get(panelId) || [];
              const idx = tms.length;
              tms.push({ label: `${idx + 1}. ${t("sessionInner.termLabel")}`, ...inst });
              showTermEmpty(false);
              switchTerminal(panelId, idx, body);
              renderTermTabs();
            });
          }
        });
      });
      shellDropdown.classList.remove("hidden");
    };

    addBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      openShellDropdown(addBtn, true);
    });

    /* Click on the empty state also creates a terminal */
    emptyEl.addEventListener("click", (e) => {
      if (shellDropdown.classList.contains("hidden")) {
        openShellDropdown(addBtn, true);
      }
    });

    document.addEventListener("click", (e) => {
      if (!addBtn.contains(e.target as Node) && !shellDropdown.contains(e.target as Node) && !emptyEl.contains(e.target as Node)) {
        shellDropdown.classList.add("hidden");
      }
    });

    /* context menu */
    const ctxMenu = document.createElement("div");
    ctxMenu.className = "context-menu hidden";
    ctxMenu.setAttribute("id", "term-ctx-menu");
    ctxMenu.innerHTML = `
      <div class="context-menu-item" data-action="copy">${t("sessionInner.termCopy")}</div>
      <div class="context-menu-item" data-action="paste">${t("sessionInner.termPaste")}</div>
      <div class="context-menu-divider"></div>
      <div class="context-menu-item" data-action="send">${t("sessionInner.termSendToChat")}</div>`;
    document.body.appendChild(ctxMenu);
    let ctxTermTarget: any = null;

    const getShellName = (): string => {
      const shellPath = this.panelShellPath.get(panelId) || "";
      const match = shells.find(s => s.path === shellPath);
      return match ? match.name : shellPath.split(/[/\\]/).pop()?.replace(/\.(exe|cmd|bat)$/i, "") || "Terminal";
    };

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
            const shellName = getShellName();
            const lineCount = content.split("\n").length;
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
    const renderTermTabs = () => {
      const terms = this.panelTerminals.get(panelId) || [];
      const activeIdx = this.panelActiveTermIdx.get(panelId) || 0;
      if (terms.length === 0) {
        tabList.innerHTML = "";
        return;
      }
      tabList.innerHTML = terms.map((ti, i) => {
        const cls = i === activeIdx ? " active" : "";
        return `<div class="tab tab--term${cls}" data-idx="${i}">
          <span class="tab-label">${this.esc(ti.label)}</span>
          <button class="tab-close" data-idx="${i}" title="${t("sessionInner.termKill")}">×</button>
        </div>`;
      }).join("");

      tabList.querySelectorAll(".tab.tab--term").forEach((el) => {
        el.addEventListener("click", (e) => {
          if ((e.target as HTMLElement).closest(".tab-close")) return;
          const idx = parseInt((el as HTMLElement).dataset.idx || "0");
          switchTerminal(panelId, idx, body);
          renderTermTabs();
        });
      });
      tabList.querySelectorAll(".tab-close").forEach((el) => {
        el.addEventListener("click", (e) => {
          e.stopPropagation();
          const idx = parseInt((el as HTMLElement).dataset.idx || "0");
          killLocal(panelId, idx, body);
          renderTermTabs();
        });
      });
    };

    killAllBtn.addEventListener("click", () => {
      const terms = this.panelTerminals.get(panelId);
      if (!terms) return;
      for (const t of [...terms]) {
        t.cleanup();
        t.resizeObs.disconnect();
        t.term.dispose();
        if (api) api.terminalKill(t.ptyId);
      }
      terms.length = 0;
      this.panelActiveTermIdx.set(panelId, -1);
      showTermEmpty(true);
      renderTermTabs();
    });

    showTermEmpty(true);
    renderTermTabs();

    const themeUnsub = subscribe(() => {
      const terms = this.panelTerminals.get(panelId);
      if (terms) {
        for (const tt of terms) applyTheme(tt.term);
      }
    });

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: panel });
    }
  }

  private killSubTerminal: ((pid: string, idx: number, body: HTMLElement) => void) | undefined;

  /* ── Files ───────────────────────────────────────────────────────── */

  private async setupFilesPanel(panel: HTMLElement): Promise<void> {
    panel.innerHTML = `<div class="si-panel-empty"><!-- show when no workspace --></div>
<div class="si-files-wrap" style="display:none">
      <div class="si-files-toolbar">
        <button class="btn-icon btn-icon--xs btn-icon--fade si-files-up" title="${t("sessionInner.filesUp")}"><i data-lucide="arrow-up" class="lucide lucide-sm"></i></button>
        <input type="text" class="si-files-path" spellcheck="false" />
        <button class="btn-icon btn-icon--xs btn-icon--fade si-files-refresh" title="${t("sessionInner.filesRefresh")}"><i data-lucide="refresh-cw" class="lucide lucide-sm"></i></button>
      </div>
      <div class="si-files-tree"></div>
    </div>`;

    const api = (window as any).electronAPI;
    if (!api) return;

    const treeEl = panel.querySelector(".si-files-tree")! as HTMLElement;
    const pathInput = panel.querySelector(".si-files-path")! as HTMLInputElement;
    const upBtn = panel.querySelector(".si-files-up")!;
    const refreshBtn = panel.querySelector(".si-files-refresh")!;
    const emptyEl = panel.querySelector(".si-panel-empty") as HTMLElement;
    const wrapEl = panel.querySelector(".si-files-wrap") as HTMLElement;

    let rootPath = "";
    const expandedDirs = new Set<string>();
    const dirCache = new Map<string, DirEntry[]>();

    const joinPath = (base: string, name: string) => {
      const sep = base.includes("\\") ? "\\" : "/";
      return base.replace(/[/\\]+$/, "") + sep + name;
    };

    const fetchDir = async (dirPath: string): Promise<DirEntry[]> => {
      if (dirCache.has(dirPath)) return dirCache.get(dirPath)!;
      try {
        const entries: DirEntry[] = await api.listDirectory(dirPath);
        dirCache.set(dirPath, entries);
        return entries;
      } catch {
        return [];
      }
    };

    const fileIcon = (name: string): string => {
      const ext = name.split(".").pop()?.toLowerCase();
      if (!ext) return "file";
      const map: Record<string, string> = {
        py: "file-code-2", ts: "file-code-2", tsx: "file-code-2",
        js: "file-code-2", jsx: "file-code-2", rs: "file-code-2",
        go: "file-code-2", java: "file-code-2",
        md: "file-text", txt: "file-text",
        json: "file-json-2", yaml: "file-json-2", yml: "file-json-2",
        toml: "file-json-2",
        html: "file-text", css: "file-text",
        svg: "file-image", png: "file-image", jpg: "file-image",
      };
      return map[ext] || "file";
    };

    const renderRecursive = async (dirPath: string, depth: number, out: string[]) => {
      const entries = await fetchDir(dirPath);
      const sorted = [...entries].sort((a, b) => {
        if (a.isDirectory && !b.isDirectory) return -1;
        if (!a.isDirectory && b.isDirectory) return 1;
        return a.name.localeCompare(b.name);
      });

      const indent = 12 + depth * 16;

      for (const entry of sorted) {
        const fullPath = joinPath(dirPath, entry.name);

        if (entry.isDirectory) {
          const isExp = expandedDirs.has(fullPath);
          out.push(`<div class="si-tree-entry" data-path="${this.esc(fullPath)}" data-dir="true" style="padding-left:${indent}px">
            <span class="si-tree-chevron${isExp ? " expanded" : ""}"><i data-lucide="chevron-right" class="lucide lucide-xs"></i></span>
            <i data-lucide="folder" class="lucide lucide-sm si-tree-icon"></i>
            <span class="si-tree-name">${this.esc(entry.name)}</span>
          </div>`);
          if (isExp) {
            await renderRecursive(fullPath, depth + 1, out);
          }
        } else {
          out.push(`<div class="si-tree-entry" data-path="${this.esc(fullPath)}" data-file="true" style="padding-left:${indent}px">
            <span class="si-tree-chevron" style="visibility:hidden"><i data-lucide="chevron-right" class="lucide lucide-xs"></i></span>
            <i data-lucide="${fileIcon(entry.name)}" class="lucide lucide-sm si-tree-icon"></i>
            <span class="si-tree-name">${this.esc(entry.name)}</span>
          </div>`);
        }
      }
    };

    const renderTree = async () => {
      const out: string[] = [];
      await renderRecursive(rootPath, 0, out);
      treeEl.innerHTML = out.length ? out.join("") : `<div class="si-empty">${t("sessionInner.filesEmpty")}</div>`;

      treeEl.querySelectorAll(".si-tree-entry[data-dir]").forEach((el) => {
        el.addEventListener("click", async () => {
          const path = (el as HTMLElement).dataset.path!;
          treeEl.querySelectorAll(".si-tree-entry.selected").forEach((s) => s.classList.remove("selected"));
          (el as HTMLElement).classList.add("selected");
          await toggleDir(path);
        });
      });

      treeEl.querySelectorAll(".si-tree-entry[data-file]").forEach((el) => {
        el.addEventListener("click", () => {
          treeEl.querySelectorAll(".si-tree-entry.selected").forEach((s) => s.classList.remove("selected"));
          (el as HTMLElement).classList.add("selected");
          const path = (el as HTMLElement).dataset.path!;
          this.openFileInEditor(path);
        });
      });

      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: treeEl });
      }
    };

    const toggleDir = async (path: string) => {
      if (expandedDirs.has(path)) {
        expandedDirs.delete(path);
      } else {
        await fetchDir(path);
        expandedDirs.add(path);
      }
      await renderTree();
    };

    const goUp = () => {
      const p = rootPath.replace(/[/\\]+$/, "").replace(/[/\\][^/\\]+$/, "");
      if (p) {
        rootPath = p;
        pathInput.value = rootPath;
        expandedDirs.clear();
        dirCache.clear();
        renderTree();
      }
    };

    upBtn.addEventListener("click", goUp);
    refreshBtn.addEventListener("click", () => {
      dirCache.clear();
      renderTree();
    });
    pathInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        rootPath = pathInput.value.trim() || "/";
        expandedDirs.clear();
        dirCache.clear();
        renderTree();
      }
    });

    const renderEmpty = () => {
      wrapEl.style.display = "none";
      emptyEl.style.display = "flex";
      emptyEl.innerHTML = `<i data-lucide="folder-open" class="lucide"></i>
        <div class="si-panel-empty-title">${t("sessionInner.filesEmpty")}</div>
        <div class="si-panel-empty-sub">${t("workspace.empty")}</div>`;
      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: emptyEl });
      }
    };

    const renderFiles = () => {
      emptyEl.style.display = "none";
      wrapEl.style.display = "flex";
      renderTree();
    };

    const home = (window as any).electronAPI?.getAppPath
      ? (await api.getAppPath()).replace(/[/\\][^/\\]+$/, "")
      : ".";

    const workspace = getState().activeWorkspace;
    if (workspace) {
      rootPath = workspace;
      renderFiles();
    } else {
      rootPath = home;
      renderEmpty();
    }

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: panel });
    }
  }

  /* ── Review (Git Diff) ─────────────────────────────────────────── */

  private async setupReviewPanel(panel: HTMLElement): Promise<void> {
    panel.innerHTML = `<div class="si-review-toolbar">
      <div class="settings-dropdown-wrap">
        <button class="settings-dropdown-trigger" type="button" style="width:130px">
          <span>${this.esc(t("sessionInner.reviewGitChange"))}</span>
          <i data-lucide="chevron-down" class="lucide settings-dropdown-chevron"></i>
        </button>
        <div class="settings-dropdown">
          <div class="settings-dropdown-item selected" data-value="git">${this.esc(t("sessionInner.reviewGitChange"))}</div>
          <div class="settings-dropdown-item" data-value="artifact">${this.esc(t("sessionInner.reviewArtifactChange"))}</div>
        </div>
      </div>
      <span class="si-review-stats"></span>
      <button class="btn-icon btn-icon--xs btn-icon--fade si-review-refresh" title="${t("sessionInner.reviewRefresh")}">
        <i data-lucide="refresh-cw" class="lucide lucide-sm"></i>
      </button>
</div>
<div class="si-review-empty" style="display:none"></div>
<div class="si-review-wrap" style="display:none">
      <div class="si-review-body">
        <div class="si-review-diff"></div>
        <div class="si-review-tree"></div>
      </div>
      <div class="si-review-commit-bar hidden">
        <input class="si-review-commit-input" type="text" placeholder="${this.esc(t("sessionInner.reviewCommitPlaceholder"))}" />
        <button class="si-review-commit-btn">${this.esc(t("sessionInner.reviewCommitBtn"))}</button>
      </div>
</div>`;

    const diffEl = panel.querySelector(".si-review-diff") as HTMLElement;
    const treeEl = panel.querySelector(".si-review-tree") as HTMLElement;
    const modeWrap = panel.querySelector(".settings-dropdown-wrap") as HTMLElement;
    const modeTrigger = modeWrap.querySelector(".settings-dropdown-trigger") as HTMLElement;
    const modeLabel = modeTrigger.querySelector("span") as HTMLElement;
    const modeDropdown = modeWrap.querySelector(".settings-dropdown") as HTMLElement;
    const statsEl = panel.querySelector(".si-review-stats") as HTMLElement;
    const refreshBtn = panel.querySelector(".si-review-refresh") as HTMLElement;
    const emptyEl = panel.querySelector(".si-review-empty") as HTMLElement;
    const wrapEl = panel.querySelector(".si-review-wrap") as HTMLElement;
    const commitBar = panel.querySelector(".si-review-commit-bar") as HTMLElement;
    const commitInput = panel.querySelector(".si-review-commit-input") as HTMLInputElement;
    const commitBtn = panel.querySelector(".si-review-commit-btn") as HTMLElement;

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
          if (path) entries.push({ path, staged, unstaged });
        }
      }
      return { branch, entries };
    };

    const fileIcon = (name: string): string => {
      const ext = name.split(".").pop()?.toLowerCase();
      if (!ext) return "file";
      const map: Record<string, string> = {
        py: "file-code-2", ts: "file-code-2", tsx: "file-code-2",
        js: "file-code-2", jsx: "file-code-2", rs: "file-code-2",
        go: "file-code-2", java: "file-code-2",
        md: "file-text", txt: "file-text",
        json: "file-json-2", yaml: "file-json-2", yml: "file-json-2",
        toml: "file-json-2",
        html: "file-text", css: "file-text",
        svg: "file-image", png: "file-image", jpg: "file-image",
      };
      return map[ext] || "file";
    };

    const buildTree = (entries: StatusEntry[], activePath?: string): string => {
      const treeCacheKey = `${activePath || ""}\n` + entries.map((e) => `${e.staged}${e.unstaged}:${e.path}`).join("\n");
      const cachedTree = this._reviewTreeCache.get(treeCacheKey);
      if (cachedTree) return cachedTree;
      if (entries.length === 0) return `<div class="si-review-empty">
        <i data-lucide="check-circle-2" class="lucide"></i>
        <div class="si-review-empty-title">${t("sessionInner.reviewNoChanges")}</div>
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
          const statusClass = item.staged !== " " && item.staged !== "?"
            ? "si-review-staged"
            : item.unstaged !== " " && item.unstaged !== "?"
              ? "si-review-unstaged"
              : "si-review-untracked";
          const statusLabel = item.staged !== " " && item.staged !== "?"
            ? t("sessionInner.reviewStaged")
            : item.unstaged !== " " && item.unstaged !== "?"
              ? t("sessionInner.reviewUnstaged")
              : t("sessionInner.reviewUntracked");
          const active = item.path === activePath ? " si-review-tree-file--active" : "";
          html += `<div class="si-review-tree-file${active}" data-path="${this.esc(item.path)}">
            <i data-lucide="${fileIcon(item.path)}" class="lucide lucide-xs"></i>
            <span class="si-review-tree-name">${this.esc(item.path.split("/").pop() || item.path)}</span>
            <span class="si-review-tree-status ${statusClass}">${statusLabel}</span>
          </div>`;
        }
        html += `</div>`;
      }
      this._reviewTreeCache.set(treeCacheKey, html);
      return html;
    };

    const parseDiffFn = (cacheKey: string, output: string): string => {
      this._reviewDiffCache ??= new Map<string, string>();
      const cached = this._reviewDiffCache.get(cacheKey);
      if (cached) return cached;
      const parsed = this.parseDiff(output);
      this._reviewDiffCache.set(cacheKey, parsed);
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
      const unstaged = entries.filter((e) => e.unstaged !== " " && e.unstaged !== "?").length;
      const untracked = entries.filter((e) => e.staged === "?" || e.unstaged === "?").length;
      return {
        adds: staged,
        dels: unstaged,
        label: `${t("sessionInner.reviewStaged")}: ${staged}  ${t("sessionInner.reviewUnstaged")}: ${unstaged}  ${t("sessionInner.reviewUntracked")}: ${untracked}`,
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
        if (typeof (window as any).lucide !== "undefined") {
          (window as any).lucide.createIcons({ root: emptyEl });
        }
      };

      // Show/hide commit bar based on mode
      if (commitBar) commitBar.classList.toggle("hidden", this._reviewMode !== "git");
      modeLabel.textContent = this._reviewMode === "git"
        ? t("sessionInner.reviewGitChange")
        : t("sessionInner.reviewArtifactChange");
      modeDropdown.querySelectorAll(".settings-dropdown-item").forEach((el) => {
        el.classList.toggle("selected", el.getAttribute("data-value") === this._reviewMode);
      });

      // Artifact mode: show stored diff from tool result (non-git).
      // Build a multi-file tree from all session artifacts; clicking a
      // tree item loads its diff — just like the git file tree works.
      if (this._reviewMode === "artifact") {
        const arts = getState().artifacts;
        // Fall through to git if no artifacts remain (e.g. after session switch)
        if (arts.length === 0) {
          this._reviewMode = "git";
        } else {
          if (requestSeq !== this._reviewRequestSeq) return;
          wrapEl.style.display = "flex";
          emptyEl.style.display = "none";
          const targetPath = filePath || this._reviewArtifact?.path || arts[0].path;
          const currentArtifact = arts.find(a => a.path === targetPath) || null;
          diffEl.innerHTML = currentArtifact
            ? this.parseArtifactDiff(currentArtifact, targetPath)
            : `<div class="si-empty">${this.esc(t("sessionInner.reviewNoChanges"))}</div>`;
          treeEl.innerHTML = this.buildArtifactTree(arts, targetPath);
          const adds = currentArtifact?.diff_text ? (currentArtifact.diff_text.match(/^\+/gm) || []).length : 0;
          const dels = currentArtifact?.diff_text ? (currentArtifact.diff_text.match(/^-/gm) || []).length : 0;
          statsEl.innerHTML = `<span class="si-review-stat-add">+${adds}</span> <span class="si-review-stat-del">-${dels}</span>`;
          // Wire tree-item clicks to load the clicked file's diff
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
      }

      if (!ws) {
        showEmptyState(`<i data-lucide="git-pull-request" class="lucide"></i>
          <div class="si-review-empty-title">${t("sessionInner.reviewNoChanges")}</div>
          <div class="si-review-empty-sub">${t("workspace.empty")}</div>`);
        return;
      }
      if (!api) {
        showEmptyState(`<i data-lucide="alert-circle" class="lucide"></i>
          <div class="si-review-empty-title">${t("sessionInner.apiNotAvailable")}</div>`);
        return;
      }

      // Show loading state before potentially slow git operations
      wrapEl.style.display = "flex";
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
            <div class="si-review-empty-title">${this.esc(statusRes.error)}</div>`);
          return;
        }

        const { branch, entries } = parseStatus(statusRes.output);
        if (!branch && entries.length === 0) {
          showEmptyState(`<i data-lucide="folder-git-2" class="lucide"></i>
            <div class="si-review-empty-title">${t("sessionInner.reviewNoGit")}</div>`);
          return;
        }
        cachedBranch = branch;
        cachedEntries = entries;
      }
      const entries = cachedEntries || [];
      const branch = cachedBranch;

      // Show file tree
      treeEl.innerHTML = buildTree(entries, filePath);
      let adds = 0;
      let dels = 0;
      let statsLabel = "";

      if (filePath) {
        currentReviewPath = filePath;
        // Show loading in diff area before potentially slow git diff
        diffEl.innerHTML = `<div class="si-review-diff-loading">${t("sessionInner.reviewLoading")}</div>`;
        const diffRes = await api.gitDiff(ws, filePath);
        if (requestSeq !== this._reviewRequestSeq) return;
        if (diffRes.error) {
          diffEl.innerHTML = `<div class="si-empty">${this.esc(diffRes.error)}</div>`;
        } else {
          diffEl.innerHTML = parseDiffFn(`${ws}:${filePath}`, diffRes.output);
          ({ adds, dels } = computeStats(entries, diffRes.output));
        }
      } else {
        currentReviewPath = undefined;
        ({ adds, dels, label: statsLabel } = computeStats(entries));
        diffEl.innerHTML = `<div class="si-empty">${this.esc(t("sessionInner.reviewNoChanges"))}<br><span style="color:var(--text-muted)">${this.esc(t("sessionInner.reviewRefresh"))}</span></div>`;
      }

      if (requestSeq !== this._reviewRequestSeq) return;
      statsEl.innerHTML = statsLabel
        ? `<span class="si-review-loading">${this.esc(statsLabel)}</span>`
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

    refreshBtn.addEventListener("click", () => load(currentReviewPath, true));
    this._reviewLoad = load;

    // Mode switcher dropdown
    const onModeChange = (val: string) => {
      const mode = val as "git" | "artifact";
      if (mode === this._reviewMode) return;
      this._reviewMode = mode;
      if (mode === "git") {
        currentReviewPath = undefined;
        cachedEntries = null;
        cachedBranch = "";
      }
      load(mode === "artifact" ? (getState().artifacts?.[0]?.path || "") : undefined, true);
    };
    modeTrigger.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpen = modeDropdown.classList.contains("open");
      document.querySelectorAll(".settings-dropdown.open").forEach((dd) => dd.classList.remove("open"));
      if (!isOpen) modeDropdown.classList.add("open");
    });
    modeDropdown.querySelectorAll(".settings-dropdown-item").forEach((item) => {
      item.addEventListener("click", (e) => {
        e.stopPropagation();
        const val = (item as HTMLElement).getAttribute("data-value") || "";
        modeLabel.textContent = (item as HTMLElement).textContent || "";
        modeDropdown.classList.remove("open");
        modeDropdown.querySelectorAll(".settings-dropdown-item").forEach((el) => el.classList.remove("selected"));
        (item as HTMLElement).classList.add("selected");
        onModeChange(val);
      });
    });
    document.addEventListener("click", (e) => {
      if (!modeWrap.contains(e.target as Node)) {
        modeDropdown.classList.remove("open");
      }
    });

    // Commit
    const doCommit = async () => {
      const msg = commitInput.value.trim();
      if (!msg) return;
      commitBtn.disabled = true;
      commitBtn.textContent = t("sessionInner.reviewCommitting");
      try {
        const ws = getState().activeWorkspace;
        if (!ws || !api) return;
        const res = await api.gitCommit(ws, msg);
        if (res.error) {
          showToast?.(t("sessionInner.commitFailed"), res.error, "error");
        } else {
          commitInput.value = "";
          cachedEntries = null;
          cachedBranch = "";
          await load(undefined, true);
        }
      } finally {
        commitBtn.disabled = false;
        commitBtn.textContent = t("sessionInner.reviewCommitBtn");
      }
    };
    commitBtn.addEventListener("click", doCommit);
    commitInput.addEventListener("keydown", (e) => { if (e.key === "Enter") doCommit(); });

    // Always load the review panel state when opened, even without a pending file
    if (this._reviewFilePending !== undefined) {
      await load(this._reviewFilePending, false);
      this._reviewFilePending = undefined;
    } else {
      await load(undefined, false);
    }
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
    if (!output.trim()) return `<div class="si-empty">${t("sessionInner.reviewNoChanges")}</div>`;
    const MAX_RENDER_LINES = 4000;
    const rawLines = output.split("\n");
    const lines = rawLines.length > MAX_RENDER_LINES
      ? rawLines.slice(0, MAX_RENDER_LINES).concat(["... [diff truncated in viewer]"])
      : rawLines;

    let fileName = "";
    let adds = 0;
    let dels = 0;
    let inHunk = false;
    let newLn = 0;
    let bodyRows = "";

    for (const rawLine of lines) {
      const line = rawLine.replace(/\t/g, "    ");
      if (line.startsWith("diff --git")) {
        inHunk = false;
        const m = line.match(/diff --git a\/(.+?) b\/(.+?)$/);
        if (m) fileName = m[2];
      } else if (line.startsWith("+++ ")) {
        // b/path or just path
        const m = line.match(/^\+\+\+ (?:b\/)?(.+)$/);
        if (m) fileName = m[1];
      } else if (line.startsWith("@@")) {
        inHunk = true;
        const m = line.match(/@@ \-\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
        newLn = m ? parseInt(m[1], 10) - 1 : 0;
      } else if (inHunk && line.startsWith("+")) {
        newLn++;
        adds++;
        const content = line.slice(1);
        bodyRows += `<div class="diff-row diff-row-add"><span class="diff-ln">${newLn}</span><span class="diff-content">${this.esc(content) || " "}</span></div>`;
      } else if (inHunk && line.startsWith("-")) {
        dels++;
        const content = line.slice(1);
        bodyRows += `<div class="diff-row diff-row-del"><span class="diff-ln">&nbsp;</span><span class="diff-content">${this.esc(content) || " "}</span></div>`;
      } else if (inHunk) {
        newLn++;
        const content = line.startsWith(" ") ? line.slice(1) : line;
        bodyRows += `<div class="diff-row"><span class="diff-ln">${newLn}</span><span class="diff-content">${this.esc(content) || " "}</span></div>`;
      }
    }

    fileName = fileName || t("sessionInner.reviewUnknownFile");
    return `<div class="diff-container">
      <div class="diff-header">
        <span class="diff-file-icon"><svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0 1 13.25 16h-9.5A1.75 1.75 0 0 1 2 14.25Zm1.75-.25a.25.25 0 0 0-.25.25v12.5c0 .138.112.25.25.25h9.5a.25.25 0 0 0 .25-.25V6h-2.75A1.75 1.75 0 0 1 9 4.25V1.5Zm6.75.062V4.25c0 .138.112.25.25.25h2.688l-.011-.013-2.914-2.914-.013-.011Z"/></svg></span>
        <span class="diff-file-name">${this.esc(fileName)}</span>
        <span class="diff-stats"><span class="diff-add-stat">+${adds}</span><span class="diff-del-stat">-${dels}</span></span>
      </div>
      <div class="diff-body">${bodyRows}</div>
    </div>`;
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
    const MAX_RENDER_LINES = 4000;
    const rawLines = diffText.split("\n");
    const lines = rawLines.length > MAX_RENDER_LINES
      ? rawLines.slice(0, MAX_RENDER_LINES).concat(["... [diff truncated in viewer]"])
      : rawLines;

    let adds = 0, dels = 0, ln = 0;
    let inHunk = false;
    let bodyRows = "";

    for (const rawLine of lines) {
      const line = rawLine.replace(/\t/g, "    ");
      if (line.startsWith("@@")) {
        inHunk = true;
        const m = line.match(/@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
        if (m) ln = parseInt(m[1], 10) - 1;
        bodyRows += `<div class="diff-row"><span class="diff-ln">&nbsp;</span><span class="diff-content"><span style="color:var(--text-tertiary)">${this.esc(line)}</span></span></div>`;
      } else if (line.startsWith("+") && !line.startsWith("+++")) {
        inHunk = true;
        ln++;
        adds++;
        bodyRows += `<div class="diff-row diff-row-add"><span class="diff-ln">${ln}</span><span class="diff-content">${this.esc(line.slice(1)) || " "}</span></div>`;
      } else if (line.startsWith("-") && !line.startsWith("---")) {
        inHunk = true;
        dels++;
        bodyRows += `<div class="diff-row diff-row-del"><span class="diff-ln">&nbsp;</span><span class="diff-content">${this.esc(line.slice(1)) || " "}</span></div>`;
      } else if (line.startsWith("diff --git") || line.startsWith("index ")) {
        continue;
      } else if (line.startsWith("---") || line.startsWith("+++")) {
        continue;
      } else if (!inHunk && !line.trim()) {
        continue;
      } else {
        inHunk = true;
        ln++;
        bodyRows += `<div class="diff-row"><span class="diff-ln">${ln}</span><span class="diff-content">${this.esc(line) || " "}</span></div>`;
      }
    }

    return `<div class="diff-container">
      <div class="diff-header">
        <span class="diff-file-icon"><svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0 1 13.25 16h-9.5A1.75 1.75 0 0 1 2 14.25Zm1.75-.25a.25.25 0 0 0-.25.25v12.5c0 .138.112.25.25.25h9.5a.25.25 0 0 0 .25-.25V6h-2.75A1.75 1.75 0 0 1 9 4.25V1.5Zm6.75.062V4.25c0 .138.112.25.25.25h2.688l-.011-.013-2.914-2.914-.013-.011Z"/></svg></span>
        <span class="diff-file-name">${this.esc(filePath)}</span>
        <span class="diff-stats"><span class="diff-add-stat">+${adds}</span><span class="diff-del-stat">-${dels}</span></span>
      </div>
      <div class="diff-body">${bodyRows}</div>
    </div>`;
  }

  private buildArtifactTree(artifacts: ArtifactItem[], activePath: string): string {
    if (artifacts.length === 0) return `<div class="si-review-empty">
      <i data-lucide="check-circle-2" class="lucide"></i>
      <div class="si-review-empty-title">${t("sessionInner.reviewNoChanges")}</div>
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
        const extIcon = a.ext === "py" ? "file-code-2"
          : a.ext === "ts" || a.ext === "tsx" || a.ext === "js" ? "file-json-2"
          : a.ext === "html" || a.ext === "css" || a.ext === "md" ? "file-text"
          : a.ext === "json" ? "file-json-2"
          : "file";
        const active = a.path === activePath ? " si-review-tree-file--active" : "";
        const toolLabel = a.tool === "file_write" || a.tool === "write_file" || a.tool === "writeFile"
          ? "created" : "modified";
        html += `<div class="si-review-tree-file${active}" data-path="${this.esc(a.path)}">
          <i data-lucide="${extIcon}" class="lucide lucide-xs"></i>
          <span class="si-review-tree-name">${this.esc(a.name)}</span>
          <span class="si-review-tree-status si-review-${toolLabel === "created" ? "untracked" : "unstaged"}">${toolLabel}</span>
        </div>`;
      }
      html += `</div>`;
    }
    return html;
  }

  /* ── Editor (File Tree + Code Editor) ──────────────────────────── */

  private _monaco: any = null;
  private _editor: any = null;
  private _editorReady = false;
  private _editorQueue: string[] = [];
  private _themeObserver: MutationObserver | null = null;
  private _openTabs: Array<{ path: string; name: string; model: any }> = [];
  private _activeTabPath = "";
  private _tabBar: HTMLElement | null = null;

  private async setupEditorPanel(panel: HTMLElement): Promise<void> {
    const api = (window as any).electronAPI;

    /* In normal mode (no workspace), editor is completely useless �?show only the default interface */
    if (!getState().activeWorkspace) {
      panel.innerHTML = `<div class="si-editor-empty" style="display:flex;flex:1;height:100%">
        <i data-lucide="file-code-2" class="lucide" style="width:28px;height:28px;opacity:0.35"></i>
        <span class="si-panel-empty-title">${t("sessionInner.editorEmpty")}</span>
        <span class="si-panel-empty-sub">${t("workspace.empty")}</span>
      </div>`;
      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: panel });
      }
      return;
    }

    panel.innerHTML = `<div class="si-editor-wrap" style="display:flex">
      <div class="si-editor-code" style="flex:1;display:flex;overflow:hidden">
        <div class="si-editor-empty" style="display:flex;flex-direction:column;align-items:center;justify-content:center;flex:1;gap:4px;padding:20px;color:var(--editor-empty,#888);font-size:13px;text-align:center">
          <i data-lucide="file-code-2" class="lucide" style="width:24px;height:24px;opacity:0.35"></i>
          <span class="si-panel-empty-title">${t("sessionInner.editorEmpty")}</span>
          <span class="si-panel-empty-sub">${t("workspace.empty")}</span>
        </div>
        <div class="tab-bar tab-bar--editor" style="display:none"></div>
        <div class="si-code-container" style="display:none;flex:1;overflow:hidden"></div>
      </div>
      <div class="si-editor-divider"></div>
      <div class="si-editor-tree">
        <div class="si-editor-tree-body"></div>
      </div>
    </div>`;

    const container = panel.querySelector(".si-code-container")! as HTMLElement;
    const treeBody = panel.querySelector(".si-editor-tree-body")! as HTMLElement;
    const divider = panel.querySelector(".si-editor-divider")! as HTMLElement;
    this._tabBar = panel.querySelector(".tab-bar--editor") as HTMLElement;

    let rootPath = "";
    const expandedDirs = new Set<string>();
    const dirCache = new Map<string, DirEntry[]>();

    interface DirEntry {
      name: string;
      isDirectory: boolean;
    }

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

    const fileIcon = (name: string): string => {
      const ext = name.split(".").pop()?.toLowerCase();
      if (!ext) return "file";
      const map: Record<string, string> = {
        py: "file-code-2", ts: "file-code-2", tsx: "file-code-2",
        js: "file-code-2", jsx: "file-code-2", rs: "file-code-2",
        go: "file-code-2", java: "file-code-2",
        md: "file-text", txt: "file-text",
        json: "file-json-2", yaml: "file-json-2", yml: "file-json-2",
        toml: "file-json-2",
        html: "file-text", css: "file-text",
        svg: "file-image", png: "file-image", jpg: "file-image",
      };
      return map[ext] || "file";
    };

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
            <span class="si-tree-icon"><i data-lucide="${fileIcon(entry.name)}" class="lucide lucide-sm"></i></span>
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
      });

      treeBody.querySelectorAll(".si-tree-entry[data-file]").forEach((el) => {
        el.addEventListener("click", () => {
          treeBody.querySelectorAll(".si-tree-entry.selected").forEach((s) => s.classList.remove("selected"));
          (el as HTMLElement).classList.add("selected");
          const filePath = (el as HTMLElement).dataset.path!;
          this.openFileInEditor(filePath);
        });
      });

      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: treeBody });
      }
    };

    /* tree resizer */
    let resizing = false;
    let startX = 0;
    let startW = 0;
    divider.addEventListener("mousedown", (e) => {
      resizing = true;
      startX = e.clientX;
      const treeWrap = panel.querySelector(".si-editor-tree") as HTMLElement;
      startW = treeWrap.offsetWidth;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      e.preventDefault();
    });
    document.addEventListener("mousemove", (e) => {
      if (!resizing) return;
      const newW = Math.max(120, Math.min(400, startW + e.clientX - startX));
      const treeWrap = panel.querySelector(".si-editor-tree") as HTMLElement;
      treeWrap.style.width = newW + "px";
    });
    document.addEventListener("mouseup", () => {
      if (!resizing) return;
      resizing = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    });

    /* Monaco editor */
    const amdRequire = (window as any).require;
    if (amdRequire && !this._editorReady) {
      amdRequire(["vs/editor/editor.main"], () => {
        const monaco = (window as any).monaco;
        this._monaco = monaco;

        monaco.editor.defineTheme("vscode-dark-plus", {
          base: "vs-dark",
          inherit: true,
          rules: [
            { token: "comment", foreground: "6A9955", fontStyle: "italic" },
            { token: "keyword", foreground: "569CD6" },
            { token: "string", foreground: "CE9178" },
            { token: "number", foreground: "B5CEA8" },
            { token: "type", foreground: "4EC9B0" },
            { token: "tag", foreground: "569CD6" },
            { token: "attribute.name", foreground: "9CDCFE" },
            { token: "attribute.value", foreground: "CE9178" },
            { token: "delimiter", foreground: "808080" },
            { token: "variable", foreground: "9CDCFE" },
            { token: "function", foreground: "DCDCAA" },
            { token: "class", foreground: "4EC9B0" },
            { token: "interface", foreground: "4EC9B0" },
            { token: "parameter", foreground: "9CDCFE" },
            { token: "property", foreground: "9CDCFE" },
            { token: "constant", foreground: "4FC1FF" },
            { token: "regexp", foreground: "D16969" },
            { token: "string.key.json", foreground: "CE9178" },
            { token: "string.value.json", foreground: "B5CEA8" },
          ],
          colors: {
            "editor.background": "#252526",
            "editor.foreground": "#d4d4d4",
            "editor.lineHighlightBackground": "#252526",
            "editor.selectionBackground": "#252526",
            "editor.inactiveSelectionBackground": "#252526",
            "editorCursor.foreground": "#aeafad",
            "editorLineNumber.foreground": "#6e6e6e",
            "editorLineNumber.activeForeground": "#c6c6c6",
            "editor.selectionHighlightBackground": "#252526",
            "editor.wordHighlightBackground": "#252526",
            "editor.wordHighlightStrongBackground": "#252526",
            "editorBracketMatch.background": "#252526",
            "editorBracketMatch.border": "#888888",
            "editorGutter.background": "#252526",
            "editorIndentGuide.background": "#3b3b3b",
            "editorIndentGuide.activeBackground": "#606060",
            "editorRuler.foreground": "#5a5a5a",
            "editorCodeLens.foreground": "#999999",
            "editorOverviewRuler.border": "#7f7f7f4d",
            "editorWidget.background": "#252526",
            "editorWidget.border": "#454545",
            "editorSuggestWidget.background": "#252526",
            "editorSuggestWidget.border": "#454545",
            "editorSuggestWidget.selectedBackground": "#252526",
            "editorSuggestWidget.foreground": "#d4d4d4",
            "editorHoverWidget.background": "#252526",
            "editorHoverWidget.border": "#454545",
            "editorLink.activeForeground": "#4e94ce",
            "diffEditor.insertedTextBackground": "#252526",
            "diffEditor.removedTextBackground": "#252526",
            "scrollbar.shadow": "#00000000",
            "scrollbarSlider.background": "#42424266",
            "scrollbarSlider.hoverBackground": "#515151cc",
            "scrollbarSlider.activeBackground": "#616161b3",
            "tab.activeBackground": "#252526",
            "tab.inactiveBackground": "#252526",
            "tab.activeForeground": "#ffffff",
            "tab.inactiveForeground": "#969696",
            "tab.border": "#252526",
            "tab.activeBorderTop": "#5188e6",
          },
        });

        monaco.editor.defineTheme("vscode-light-plus", {
          base: "vs",
          inherit: true,
          rules: [
            { token: "comment", foreground: "008000", fontStyle: "italic" },
            { token: "keyword", foreground: "0000FF" },
            { token: "string", foreground: "A31515" },
            { token: "number", foreground: "098658" },
            { token: "type", foreground: "267F99" },
            { token: "tag", foreground: "800000" },
            { token: "attribute.name", foreground: "FF0000" },
            { token: "attribute.value", foreground: "0000FF" },
            { token: "delimiter", foreground: "808080" },
            { token: "variable", foreground: "001188" },
            { token: "function", foreground: "795E26" },
            { token: "class", foreground: "267F99" },
            { token: "interface", foreground: "267F99" },
            { token: "parameter", foreground: "001188" },
            { token: "property", foreground: "001188" },
            { token: "constant", foreground: "0070C1" },
            { token: "regexp", foreground: "800000" },
            { token: "string.key.json", foreground: "A31515" },
            { token: "string.value.json", foreground: "098658" },
          ],
          colors: {
            "editor.background": "#f3f3f3",
            "editor.foreground": "#333333",
            "editor.lineHighlightBackground": "#f3f3f3",
            "editor.selectionBackground": "#f3f3f3",
            "editor.inactiveSelectionBackground": "#f3f3f3",
            "editorCursor.foreground": "#333333",
            "editorLineNumber.foreground": "#9ca3af",
            "editorLineNumber.activeForeground": "#237893",
            "editor.selectionHighlightBackground": "#f3f3f3",
            "editor.wordHighlightBackground": "#f3f3f3",
            "editor.wordHighlightStrongBackground": "#f3f3f3",
            "editorBracketMatch.background": "#f3f3f3",
            "editorBracketMatch.border": "#b8b8b8",
            "editorGutter.background": "#f3f3f3",
            "editorIndentGuide.background": "#e0e0e0",
            "editorIndentGuide.activeBackground": "#c0c0c0",
            "editorRuler.foreground": "#e0e0e0",
            "editorCodeLens.foreground": "#999999",
            "editorOverviewRuler.border": "#e0e0e0",
            "editorWidget.background": "#f3f3f3",
            "editorWidget.border": "#c4c4c4",
            "editorSuggestWidget.background": "#f3f3f3",
            "editorSuggestWidget.border": "#c4c4c4",
            "editorSuggestWidget.selectedBackground": "#f3f3f3",
            "editorSuggestWidget.foreground": "#333333",
            "editorHoverWidget.background": "#f3f3f3",
            "editorHoverWidget.border": "#c4c4c4",
            "editorLink.activeForeground": "#006ab1",
            "diffEditor.insertedTextBackground": "#f3f3f3",
            "diffEditor.removedTextBackground": "#f3f3f3",
            "scrollbar.shadow": "#00000000",
            "scrollbarSlider.background": "#c1c1c166",
            "scrollbarSlider.hoverBackground": "#a0a0a0b3",
            "scrollbarSlider.activeBackground": "#90909099",
          },
        });

        const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
        const themeName = currentTheme === "light" ? "vscode-light-plus" : "vscode-dark-plus";
        this._editor = monaco.editor.create(container, {
          value: "",
          language: "plaintext",
          theme: themeName,
          fontSize: 13,
          fontFamily: "'Cascadia Code', 'JetBrains Mono', 'Fira Code', Consolas, monospace",
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          automaticLayout: true,
          tabSize: 2,
          wordWrap: "on",
          bracketPairColorization: { enabled: true },
          smoothScrolling: true,
          cursorBlinking: "smooth",
          cursorSmoothCaretAnimation: "on",
          padding: { top: 8 },
          renderLineHighlight: "all",
          overviewRulerBorder: false,
          hideCursorInOverviewRuler: true,
          readOnly: true,
          lineNumbersMinChars: 2,
          lineDecorationsWidth: 4,
          folding: false,
          glyphMargin: false,
        });

        this._editorReady = true;

        if (!this._themeObserver) {
          this._themeObserver = new MutationObserver(() => {
            const t = document.documentElement.getAttribute("data-theme");
            if (this._editor && this._monaco) {
              this._monaco.editor.setTheme(t === "light" ? "vscode-light-plus" : "vscode-dark-plus");
            }
          });
          this._themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
        }

        for (const p of this._editorQueue) {
          this.doOpenFile(p);
        }
        this._editorQueue = [];
      });
    } else if (this._editorReady) {
      this._editor.layout();
    }

    /* start in workspace root */
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

  private openFileInEditor(filePath: string): void {
    if (!this.tabs.some((t) => t.id === "editor")) {
      this.createTab("editor");
      requestAnimationFrame(() => this.openFileInEditor(filePath));
      return;
    }
    if (!this._editorReady) {
      this._editorQueue.push(filePath);
      return;
    }
    this.doOpenFile(filePath);
  }

  private async doOpenFile(filePath: string): Promise<void> {
    const api = (window as any).electronAPI;
    if (!api) return;
    const content = await api.readFile(filePath);
    if (content === undefined) return;

    const ext = filePath.split(".").pop()?.toLowerCase() || "";
    const langMap: Record<string, string> = {
      py: "python", ts: "typescript", tsx: "typescript",
      js: "javascript", jsx: "javascript", rs: "rust",
      go: "go", md: "markdown", json: "json",
      html: "html", css: "css", yaml: "yaml", yml: "yaml",
      toml: "plaintext", java: "java", cpp: "cpp", c: "c",
      h: "c", hpp: "cpp", cs: "csharp", swift: "swift",
      kt: "kotlin", scala: "scala", rb: "ruby", php: "php",
      sh: "shell", bash: "shell", zsh: "shell",
      sql: "sql", r: "r", lua: "lua", dart: "dart",
    };
    const lang = langMap[ext] || "plaintext";

    const monaco = this._monaco;
    const name = filePath.split(/[/\\]/).pop() || filePath;
    /* Use 'inmemory' scheme instead of 'file' because standalone Monaco
       (loaded via vs/editor/editor.main.js) does not register a model
       factory for the 'file' scheme, which would cause
       "t.create is not a function" in the instantiation service. */
    const uri = monaco.Uri.parse(
      "inmemory://model" + (filePath.startsWith("/") ? filePath : "/" + filePath).replace(/\\/g, "/")
    );

    let model = monaco.editor.getModel(uri);
    if (model) {
      model.setValue(content);
    } else {
      model = monaco.editor.createModel(content, lang, uri);
    }

    /* check if tab already exists */
    const existing = this._openTabs.find((t) => t.path === filePath);
    if (!existing) {
      this._openTabs.push({ path: filePath, name, model });
    }
    this._activeTabPath = filePath;
    this._editor.setModel(model);
    this.renderEditorTabs();
    this.showEditorEmpty(false);

    if (!this.tabs.some((t) => t.id === "editor")) {
      this.createTab("editor");
    } else {
      this.activateTab("editor");
    }
  }

  private _dragSrcIdx = -1;
  private _reviewLoad: ((filePath?: string) => Promise<void>) | null = null;
  private _reviewMode: "git" | "artifact" = "git";
  private _reviewArtifact: ArtifactItem | null = null;
  private _reviewRequestSeq = 0;
  private _reviewDiffCache: Map<string, string> | null = null;
  private _reviewTreeCache = new Map<string, string>();

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
    }
    if (artifact) {
      this._reviewMode = "artifact";
      this._reviewArtifact = artifact;
    } else {
      this._reviewMode = "git";
      this._reviewArtifact = null;
    }
    this.openReviewTab(path);
  }

  private openReviewTab(filePath?: string): void {
    const createNew = !this.tabs.some((t) => t.id === "review");
    if (createNew) {
      this.tabs.push({ id: "review", closable: true });
      this._reviewFilePending = filePath;
    }
    this.activeTab = "review";
    this.renderTabs();
    if (!createNew) {
      if (this._reviewLoad) this._reviewLoad(filePath);
    }
  }
  private _reviewFilePending: string | undefined;

  private renderEditorTabs(): void {
    if (!this._tabBar) return;
    this._tabBar.innerHTML = this._openTabs.map((t) => {
      const active = t.path === this._activeTabPath ? " active" : "";
      return `<div class="tab tab--editor${active}" data-path="${this.esc(t.path)}" draggable="true">
        <span class="tab-label">${this.esc(t.name)}</span>
        <span class="tab-close" data-path="${this.esc(t.path)}">&times;</span>
      </div>`;
    }).join("");

    const tabs = this._tabBar.querySelectorAll<HTMLElement>(".tab.tab--editor");
    tabs.forEach((el, idx) => {
      el.addEventListener("click", (e) => {
        if ((e.target as HTMLElement).classList.contains("tab-close")) return;
        const path = (el as HTMLElement).dataset.path!;
        this.switchEditorTab(path);
      });

      /* drag & drop */
      el.addEventListener("dragstart", (e: DragEvent) => {
        this._dragSrcIdx = idx;
        (el as HTMLElement).classList.add("dragging");
        if (e.dataTransfer) {
          e.dataTransfer.effectAllowed = "move";
        }
      });

      el.addEventListener("dragend", () => {
        (el as HTMLElement).classList.remove("dragging");
        tabs.forEach((t) => (t as HTMLElement).classList.remove("drag-over"));
        this._dragSrcIdx = -1;
      });

      el.addEventListener("dragover", (e: DragEvent) => {
        e.preventDefault();
        if (e.dataTransfer) {
          e.dataTransfer.dropEffect = "move";
        }
        if (idx !== this._dragSrcIdx) {
          (el as HTMLElement).classList.add("drag-over");
        }
      });

      el.addEventListener("dragleave", () => {
        (el as HTMLElement).classList.remove("drag-over");
      });

      el.addEventListener("drop", (e) => {
        e.preventDefault();
        (el as HTMLElement).classList.remove("drag-over");
        if (this._dragSrcIdx === -1 || this._dragSrcIdx === idx) return;
        const item = this._openTabs.splice(this._dragSrcIdx, 1)[0];
        this._openTabs.splice(idx, 0, item);
        this.renderEditorTabs();
      });
    });

    this._tabBar.querySelectorAll(".tab-close").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        const path = (el as HTMLElement).dataset.path!;
        this.closeEditorTab(path);
      });
    });
  }

  private switchEditorTab(filePath: string): void {
    if (filePath === this._activeTabPath) return;
    const tab = this._openTabs.find((t) => t.path === filePath);
    if (!tab) return;
    this._activeTabPath = filePath;
    this._editor.setModel(tab.model);
    this.showEditorEmpty(false);
    this.renderEditorTabs();
  }

  private closeEditorTab(filePath: string): void {
    const idx = this._openTabs.findIndex((t) => t.path === filePath);
    if (idx === -1) return;
    const tab = this._openTabs[idx];

    tab.model.dispose();

    /* determine next tab to show */
    const wasActive = filePath === this._activeTabPath;
    this._openTabs.splice(idx, 1);

    if (this._openTabs.length === 0) {
      this._activeTabPath = "";
      this._editor.setModel(this._monaco.editor.createModel("", "plaintext"));
      this.showEditorEmpty(true);
    } else if (wasActive) {
      const next = this._openTabs[Math.min(idx, this._openTabs.length - 1)];
      this._activeTabPath = next.path;
      this._editor.setModel(next.model);
      this.showEditorEmpty(false);
    }
    this.renderEditorTabs();
  }

  private showEditorEmpty(show: boolean): void {
    const panel = this.tabBody.querySelector('[data-panel="editor"]') as HTMLElement;
    if (!panel) return;
    const empty = panel.querySelector(".si-editor-empty") as HTMLElement;
    const tabBar = panel.querySelector(".si-editor-code .tab-bar") as HTMLElement;
    const container = panel.querySelector(".si-code-container") as HTMLElement;
    if (empty) empty.style.display = show ? "flex" : "none";
    if (tabBar) tabBar.style.display = show ? "none" : "";
    if (container) container.style.display = show ? "none" : "flex";
  }

  /* ── Tab Events ──────────────────────────────────────────────────── */

  private bindTabEvents(): void {
    this.tabList.querySelectorAll(".tab-close").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const id = (btn as HTMLElement).dataset.close!;
        this.closeTab(id);
      });
    });

    const tabs = this.tabList.querySelectorAll(".tab.tab--fill");
    tabs.forEach((tab, idx) => {
      const el = tab as HTMLElement;

      /* Activate on click (unless dragged) */
      el.addEventListener("click", () => {
        if (this.wasDragged) { this.wasDragged = false; return; }
        const id = el.dataset.tab!;
        if (id !== this.activeTab) this.activateTab(id);
      });

      /* Middle-click to close */
      el.addEventListener("auxclick", (e) => {
        if (e.button === 1) {
          e.preventDefault();
          const id = el.dataset.tab!;
          const tabDef = this.tabs.find((t) => t.id === id);
          if (tabDef?.closable) this.closeTab(id);
        }
      });

      /* Drag start (left button only) */
      el.addEventListener("mousedown", (e) => {
        if (e.button !== 0) return;
        if ((e.target as HTMLElement).closest(".tab-close")) return;
        this.wasDragged = false;
        this.dragEl = el;
        this.dragIdx = idx;
        this.dragStartX = e.clientX;
        this.dragOverIdx = idx;
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
    this.tabList.querySelectorAll(".tab.tab--fill").forEach((t) => {
      t.classList.toggle("active", (t as HTMLElement).dataset.tab === id);
    });
    this.tabBody.querySelectorAll(".tab-panel").forEach((p) => {
      p.classList.toggle("active", (p as HTMLElement).dataset.panel === id);
    });
    if (id === "info") this.renderContent();
  }

  private closeTab(id: string): void {
    const idx = this.tabs.findIndex((tab) => tab.id === id);
    if (idx < 0) return;
    if (id === "terminal") {
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
      const dd = document.querySelector(".si-term-shell-dropdown");
      if (dd) dd.remove();
    }
    if (id === "editor" && this._editor) {
      this._editor.dispose();
      this._editor = null;
      this._editorReady = false;
      this._monaco = null;
      if (this._themeObserver) {
        this._themeObserver.disconnect();
        this._themeObserver = null;
      }
    }
    this.tabs.splice(idx, 1);
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
    const items = st.planItems;
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
        const extIcon = a.ext === "py" ? "file-code-2"
          : a.ext === "ts" || a.ext === "tsx" || a.ext === "js" ? "file-json-2"
          : a.ext === "html" || a.ext === "css" || a.ext === "md" ? "file-text"
          : a.ext === "json" ? "file-json-2"
          : "file";
        return `<div class="si-diff-file" data-path="${this.esc(a.path)}">
          <i data-lucide="${extIcon}" class="lucide lucide-sm si-diff-icon"></i>
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
    let bodyHTML: string;
    if (refs.length === 0) {
      bodyHTML = `<div class="si-panel-empty">${t("sessionInner.noRefs")}</div>`;
    } else {
      // Show most recent references first, limit to 50
      const shown = refs.slice(-50).reverse();
      bodyHTML = `<div class="si-ref-list">${shown.map((r: ReferenceItem) => {
        const icon = r.icon || "zap";
        const toolLabel = r.tool.startsWith("mcp__") ? r.tool.split("__").slice(0, 2).join(":") : r.tool;
        return `<div class="si-ref-item" title="${this.esc(r.tool)}">
          <i data-lucide="${icon}" class="lucide si-ref-icon"></i>
          <div class="si-ref-content">
            <span class="si-ref-tool">${this.esc(toolLabel)}</span>
            <span class="si-ref-summary">${this.esc(r.summary)}</span>
          </div>
        </div>`;
      }).join("")}</div>`;
    }

    return `<div class="si-panel">
      ${this.panelHeader("references", t("sessionInner.references"), "link-2", refs.length > 0 ? String(refs.length) : undefined)}
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
    const lastCompact = st.compactEvents.length > 0 ? st.compactEvents[st.compactEvents.length - 1] : null;
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
        <button id="${btnId}" class="si-panel-action-btn" style="flex-shrink:0;background:none;border:none;cursor:pointer;padding:2px;color:var(--text-secondary)" title="${t("settings.indexActions")}">
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
        return `<div class="si-hook-row" title="${src}">
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

