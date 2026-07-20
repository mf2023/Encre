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
 * Workspace (iWork) sidebar & mode management.
 *
 * Implements the "workspace mode" experience: a slide-in tree of workspace
 * folders and their sessions alongside the normal session list. Handles
 * entering/exiting workspace mode (with the shared slide transition), folder
 * open/remove, per-folder expansion state, and batch selection for bulk
 * export/delete. Also exposes `syncFirstNavActive` for sidebar nav state.
 */

import { getState, subscribe, setActiveWorkspace, setSessionId, setWorkspaceMode } from "./state.js";
import { send } from "./ws.js";
import { setRequestedSessionId } from "./stream.js";
import { t, onLocaleChange, applyI18n } from "./i18n.js";
import { Dialog } from "./dialog.js";
import { TransitionHelper } from "./transition-helper.js";
import type { WorkspaceEntry, SessionEntryData } from "./types.js";
import { showContextMenu } from "./context-menu.js";
import { getWorkspaceSessionGroups, normalizeWorkspacePath } from "./session-projection.js";

/**
 * Manages the workspace tree and iWork mode transitions.
 */
export class Workspace {
  private treeSectionEl: HTMLElement | null = null;
  private treeListEl: HTMLElement | null = null;
  private isInWorkspaceMode = false;
  private expandedWsPaths: Set<string> = new Set();
  private batchMode = false;
  private selectedPaths: Set<string> = new Set();
  private _exiting = false;
  private _sessionSectionEl: HTMLElement | null = null;
  private _lastWsTreeJson: string = "";
  private _lastSid: string = "";
  private _transitioning = false;
  private pendingWorkspacePath = "";
  /** Public read-only access to the workspace mode flag. */
  public get isInWorkspaceModePublic(): boolean {
    return this.isInWorkspaceMode;
  }

  /** Callback fired after entering/exiting iWork mode so the app can refresh the content area. */
  public onModeChange: (() => void) | null = null;

  /**
   * Force-exit workspace mode without any visual transitions.
   */
  public forceExit(): void {
    if (!this.isInWorkspaceMode) return;
    this._exiting = true;
    this.isInWorkspaceMode = false;
    this.batchMode = false;
    this.selectedPaths.clear();
    // Persist expanded state so re-entering workspace mode restores it
    this._saveExpandedState();
    this.expandedWsPaths.clear();
    // Restore sidebar visual state: hide tree, show session section
    if (this.treeSectionEl) {
      this.treeSectionEl.classList.remove("active");
      this.treeSectionEl.style.transition = "";
      this.treeSectionEl.style.transform = "";
      this.treeSectionEl.style.opacity = "";
      this.treeSectionEl.style.position = "";
      this.treeSectionEl.style.top = "";
      this.treeSectionEl.style.left = "";
      this.treeSectionEl.style.width = "";
      this.treeSectionEl.style.height = "";
      this.treeSectionEl.style.maxHeight = "";
      this.treeSectionEl.classList.add("hidden");
    }
    if (this._sessionSectionEl) {
      this._sessionSectionEl.style.transition = "";
      this._sessionSectionEl.style.transform = "";
      this._sessionSectionEl.style.opacity = "";
      this._sessionSectionEl.style.position = "";
      this._sessionSectionEl.style.top = "";
      this._sessionSectionEl.style.left = "";
      this._sessionSectionEl.style.width = "";
      this._sessionSectionEl.style.height = "";
      this._sessionSectionEl.classList.remove("hidden");
    }
    const parentForce = this._sessionSectionEl?.parentElement;
    if (parentForce) parentForce.style.position = "";
    const oldWs = getState().activeWorkspace;
    setActiveWorkspace("");
    setWorkspaceMode("normal");
    if (oldWs) {
      const requestId = crypto.randomUUID();
      setRequestedSessionId("", requestId);
      send({ type: "close_workspace", path: oldWs, request_id: requestId });
    }
    send({ type: "list_sessions" });
    // Reset temp chat button inline styles
    const tempBtnForce = document.getElementById("btn-temp-chat");
    if (tempBtnForce) {
      tempBtnForce.style.transition = "";
      tempBtnForce.style.opacity = "";
      tempBtnForce.style.transform = "";
      tempBtnForce.style.pointerEvents = "";
    }
    this.syncFirstNavActive();
    setTimeout(() => { this._exiting = false; }, 100);
  }

  /**
   * Constructor: resolves DOM nodes, wires buttons and subscribes to state.
   */
  constructor() {
    this._sessionSectionEl = document.getElementById("session-section");
    // The top-bar #mode-seg switch (wired in app.ts) is now the single
    // mode entry point. The sidebar iWork button has been removed.

    document.getElementById("btn-open-workspace")?.addEventListener("click", () => this.openFolder());
    document.getElementById("btn-ws-manage")?.addEventListener("click", () => this.toggleBatchMode());
    document.getElementById("btn-ws-delete")?.addEventListener("click", () => this.batchDelete());

    subscribe(() => this.onStateChange());
    onLocaleChange(() => {
      if (this.isInWorkspaceMode) this.renderTree();
    });
    if (getState().connected) {
      send({ type: "list_workspaces" });
    }
    this.syncFirstNavActive();
  }

  private async toggleWorkspaceMode(): Promise<void> {
    if (this._transitioning) return;
    if (this.isInWorkspaceMode) {
      await this.exitWorkspaceMode();
    } else {
      await this.enterWorkspaceMode();
    }
  }

  async enter(): Promise<void> {
    if (!this.isInWorkspaceMode && !this._transitioning) {
      await this.enterWorkspaceMode();
    }
  }

  /** Opens a workspace from an external entry point, such as the tray. */
  public async open(path: string): Promise<void> {
    if (!path || this._transitioning) return;
    this.ensureExpanded(path);
    if (!this.isInWorkspaceMode) {
      this.pendingWorkspacePath = path;
      await this.enterWorkspaceMode();
      return;
    }
    this.activate(path);
  }

  /** Public exit — used by the header mode switch to leave workspace mode
   *  with the same animation pipeline as the internal toggle button. */
  async exit(): Promise<void> {
    if (this.isInWorkspaceMode && !this._transitioning) {
      await this.exitWorkspaceMode();
    }
  }

  /** Ensure a workspace path is expanded in the tree so its sessions are visible. */
  public ensureExpanded(path: string): void {
    this.expandedWsPaths.add(path);
  }

  private _saveExpandedState(): void {
    try {
      sessionStorage.setItem("ws_expanded", JSON.stringify([...this.expandedWsPaths]));
    } catch { /* noop */ }
  }

  private _restoreExpandedState(): void {
    try {
      const raw = sessionStorage.getItem("ws_expanded");
      if (raw) {
        const paths: string[] = JSON.parse(raw);
        for (const p of paths) this.expandedWsPaths.add(p);
      }
    } catch { /* noop */ }
  }

  private onStateChange(): void {
    if (this._exiting) return;
    if (!this.isInWorkspaceMode) return;
    const st = getState();
    const currentJson = JSON.stringify({ workspaces: st.workspaces, activeWorkspace: st.activeWorkspace, sessions: st.sessionsList });
    const sidChanged = st.sessionId !== this._lastSid;
    if (currentJson !== this._lastWsTreeJson || sidChanged) {
      this._lastWsTreeJson = currentJson;
      this._lastSid = st.sessionId;
      this.renderTree();
    }
  }

  private async enterWorkspaceMode(): Promise<void> {
    if (this.isInWorkspaceMode || this._transitioning) return;
    this._transitioning = true;
    this.isInWorkspaceMode = true;
    this._exiting = false;

    // Restore previously expanded workspace folders
    this._restoreExpandedState();
    // Pre-create tree section & render content (hidden)
    this.ensureTreeSection();
    // Reset any stale batch-mode state left over from a previous session.
    this.batchMode = false;
    this.selectedPaths.clear();
    this.renderTree();
    this.updateBatchBarVisibility();

    // Unified slide transition:
    //   - 退出: session 分段向左滑出
    //   - 进入: workspace tree 从右侧滑入
    try {
      await TransitionHelper.slide({
        exit: [this._sessionSectionEl!].filter(Boolean) as HTMLElement[],
        enter: [this.treeSectionEl!].filter(Boolean) as HTMLElement[],
        setup: () => {
          const parent = this._sessionSectionEl?.parentElement;
          if (parent) parent.style.position = "relative";
          [this._sessionSectionEl!, this.treeSectionEl!].forEach(el => {
            if (!el) return;
            el.style.position = "absolute";
            el.style.top = "0";
            el.style.left = "0";
            el.style.width = "100%";
            el.style.height = "100%";
          });
          if (this.treeSectionEl) {
            this.treeSectionEl.classList.add("active");
            this.treeSectionEl.style.maxHeight = "1000px";
          }
        },
      });
    } catch (e) {
      console.error("[workspace] slide transition failed:", e);
    }

    // Cleanup absolute positioning
    const parentEnter = this._sessionSectionEl?.parentElement;
    [this._sessionSectionEl!, this.treeSectionEl!].forEach(el => {
      if (!el) return;
      el.style.position = "";
      el.style.top = "";
      el.style.left = "";
      el.style.width = "";
      el.style.height = "";
    });
    if (parentEnter) parentEnter.style.position = "";

    const workspaces = getState().workspaces;
    const activeWs = getState().activeWorkspace;
    const pendingWorkspacePath = this.pendingWorkspacePath;
    this.pendingWorkspacePath = "";
    if (pendingWorkspacePath) {
      setActiveWorkspace(pendingWorkspacePath);
      const requestId = crypto.randomUUID();
      setRequestedSessionId("", requestId);
      send({ type: "open_workspace", path: pendingWorkspacePath, request_id: requestId });
    } else if ((window as any).__pendingTrayResume) {
      // Do nothing — onSwitchSession already handles opening the correct workspace.
      // Avoid overwriting _requestedSessionRequestId set by that handler.
    } else if (!activeWs && workspaces.length > 0 && workspaces[0].path) {
      setActiveWorkspace(workspaces[0].path);
      const requestId = crypto.randomUUID();
      setRequestedSessionId("", requestId);
      send({ type: "open_workspace", path: workspaces[0].path, request_id: requestId });
      // open_workspace triggers session_ready → list_all_sessions, so the tree
      // will be populated with sessions for all workspaces.
    } else {
      // Already have an active workspace (or empty); send list_all_sessions
      // explicitly so the tree picks up any new sessions from other workspaces.
      send({ type: "list_all_sessions" });
      if (activeWs) this.expandedWsPaths.add(activeWs);
    }

    // Slide-hide temp chat button in workspace mode (exit left, consistent with all other transitions)
    const tempBtn = document.getElementById("btn-temp-chat");
    if (tempBtn) {
      tempBtn.style.transition = "opacity 0.12s cubic-bezier(0.4, 0, 0.2, 1), transform 0.12s cubic-bezier(0.4, 0, 0.2, 1)";
      tempBtn.style.opacity = "0";
      tempBtn.style.transform = "translateX(-20px)";
      tempBtn.style.pointerEvents = "none";
    }

    this.syncFirstNavActive();
    this._transitioning = false;
    setWorkspaceMode("iwork");
    this.onModeChange?.();
  }

  private async exitWorkspaceMode(): Promise<void> {
    if (this._transitioning) return;
    this._transitioning = true;

    // Unified slide transition:
    //   - 退出: workspace tree 向左滑出
    //   - 进入: session 分段从右侧滑入
    try {
      await TransitionHelper.slide({
        exit: [this.treeSectionEl!].filter(Boolean) as HTMLElement[],
        enter: [this._sessionSectionEl!].filter(Boolean) as HTMLElement[],
        setup: () => {
          const parent = this._sessionSectionEl?.parentElement;
          if (parent) parent.style.position = "relative";
          [this._sessionSectionEl!, this.treeSectionEl!].forEach(el => {
            if (!el) return;
            el.style.position = "absolute";
            el.style.top = "0";
            el.style.left = "0";
            el.style.width = "100%";
            el.style.height = "100%";
          });
          if (this.treeSectionEl) {
            this.treeSectionEl.classList.remove("active");
          }
        },
      });
    } catch (e) {
      console.error("[workspace] exit slide transition failed:", e);
    }

    // Cleanup absolute positioning
    const parentExit = this._sessionSectionEl?.parentElement;
    [this._sessionSectionEl!, this.treeSectionEl!].forEach(el => {
      if (!el) return;
      el.style.position = "";
      el.style.top = "";
      el.style.left = "";
      el.style.width = "";
      el.style.height = "";
    });
    if (parentExit) parentExit.style.position = "";

    this._exiting = true;
    this.isInWorkspaceMode = false;
    this.batchMode = false;
    this.selectedPaths.clear();
    this._saveExpandedState();
    this.expandedWsPaths.clear();

    const oldWs = getState().activeWorkspace;
    setActiveWorkspace("");
    if (oldWs) {
      const requestId = crypto.randomUUID();
      setRequestedSessionId("", requestId);
      send({ type: "close_workspace", path: oldWs, request_id: requestId });
    }
    send({ type: "list_sessions" });
    this.syncFirstNavActive();
    this._transitioning = false;
    setWorkspaceMode("normal");
    this.onModeChange?.();

    // Slide-show temp chat button when exiting workspace mode (enter from right)
    const tempBtn = document.getElementById("btn-temp-chat");
    if (tempBtn) {
      tempBtn.style.transition = "none";
      tempBtn.style.transform = "translateX(100%)";
      tempBtn.style.opacity = "0";
      requestAnimationFrame(() => {
        tempBtn.style.transition = "opacity 0.28s cubic-bezier(0.4, 0, 0.2, 1), transform 0.28s cubic-bezier(0.4, 0, 0.2, 1)";
        tempBtn.style.transform = "translateX(0)";
        tempBtn.style.opacity = "";
        tempBtn.style.pointerEvents = "";
        setTimeout(() => { if (tempBtn) tempBtn.style.transition = ""; }, 330);
      });
    }

    setTimeout(() => { this._exiting = false; }, 100);
  }

  private syncFirstNavActive(): void {
    syncFirstNavActive();
  }

  private ensureTreeSection(): void {
    if (this.treeSectionEl) return;
    const sessionSection = document.getElementById("session-section");
    if (!sessionSection) return;

    // Create a transition wrapper so slide animations position correctly
    // below the sidebar nav, not overlapping with the "New task" button.
    let wrapper = document.getElementById("sidebar-section-wrapper");
    if (!wrapper) {
      wrapper = document.createElement("div");
      wrapper.id = "sidebar-section-wrapper";
      wrapper.style.cssText = "position:relative;flex:1;overflow:hidden;display:flex;flex-direction:column;min-height:0";
      sessionSection.parentNode?.insertBefore(wrapper, sessionSection);
      wrapper.appendChild(sessionSection);
    }

    const section = document.createElement("div");
    section.id = "workspace-tree-section";

    const header = document.createElement("div");
    header.className = "workspace-tree-header";
    header.innerHTML = `
      <span class="sidebar-section-title" data-i18n="search.sectionWorkspaces">Workspaces</span>
      <div class="workspace-tree-actions">
        <button class="btn-icon btn-sm" id="btn-open-workspace" data-i18n-title="workspace.openFolder" data-tooltip="Open Folder">
          <i data-lucide="folder-plus" class="lucide"></i>
        </button>
        <button class="btn-icon btn-sm" id="btn-ws-manage" data-i18n-title="general.manage" data-tooltip="Manage">
          <i data-lucide="sliders-horizontal" class="lucide"></i>
        </button>
        <button class="btn-icon btn-sm hidden" id="btn-ws-cancel" data-i18n-title="session.cancel" data-tooltip="Cancel">
          <i data-lucide="x" class="lucide"></i>
        </button>
        <button class="btn-icon btn-sm hidden" id="btn-ws-select-all" data-i18n-title="session.batchSelectAll" data-tooltip="Select All">
          <i data-lucide="check-square" class="lucide"></i>
        </button>
        <button class="btn-icon btn-sm hidden batch-color-accent" id="btn-ws-export" data-i18n-title="session.batchExport" data-tooltip="Export Selected">
          <i data-lucide="download" class="lucide"></i>
        </button>
        <button class="btn-icon btn-sm hidden batch-color-danger" id="btn-ws-delete" data-i18n-title="session.batchDelete" data-tooltip="Delete Selected">
          <i data-lucide="trash-2" class="lucide"></i>
        </button>
      </div>`;

    const list = document.createElement("div");
    list.id = "workspace-tree-list";
    list.className = "workspace-tree-list";

    section.appendChild(header);
    section.appendChild(list);

    // Insert workspace tree INTO the wrapper, before session-section
    wrapper.insertBefore(section, sessionSection);

    this.treeSectionEl = section;
    this.treeListEl = list;

    // Initially hidden
    section.classList.add("hidden");

    document.getElementById("btn-open-workspace")?.addEventListener("click", () => this.openFolder());
    document.getElementById("btn-ws-manage")?.addEventListener("click", () => this.toggleBatchMode());
    document.getElementById("btn-ws-cancel")?.addEventListener("click", () => this.exitBatchMode());
    document.getElementById("btn-ws-select-all")?.addEventListener("click", () => this.batchSelectAll());
    document.getElementById("btn-ws-export")?.addEventListener("click", () => this.batchExport());
    document.getElementById("btn-ws-delete")?.addEventListener("click", () => this.batchDelete());

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: section });
    }
    // Translate the freshly-inserted data-i18n* nodes (the section is created
    // lazily, after the initial applyI18n() pass at startup).
    applyI18n();
  }

  private removeTreeSection(): void {
    // Keep in DOM, just visually hide via CSS transition
    if (this.treeSectionEl) {
      this.treeSectionEl.style.opacity = "0";
      this.treeSectionEl.style.maxHeight = "0";
    }
  }

  /** Renders the workspace tree (folders + sessions) for the active mode. */
  private renderTree(): void {
    if (!this.isInWorkspaceMode || !this.treeListEl || this._exiting) return;

    const s = getState();
    const workspaceGroups = getWorkspaceSessionGroups(s.workspaces, s.sessionsList);
    const activeWs = s.activeWorkspace;

    if (workspaceGroups.length === 0) {
      this.treeListEl.innerHTML = `<div class="workspace-tree-empty">${t("workspace.empty")}</div>`;
      return;
    }

    let html = "";
    for (const { workspace: ws, sessions: wsSessions } of workspaceGroups) {
      const isExpanded = this.expandedWsPaths.has(ws.path);
      const isActive = ws.path === activeWs ? " active" : "";
      html += `<div class="ws-tree-node" data-ws-path="${this.esc(ws.path)}">
        <div class="ws-tree-node-header${isActive}" data-ws-path="${this.esc(ws.path)}">
          ${this.batchMode ? `<input type="checkbox" class="ws-checkbox" data-path="${this.esc(ws.path)}" ${this.selectedPaths.has(ws.path) ? "checked" : ""} />` : ""}
          <button type="button" class="ws-expand-button"
            aria-label="${isExpanded ? "Collapse workspace sessions" : "Expand workspace sessions"}"
            aria-expanded="${isExpanded}">
            <i data-lucide="chevron-right" class="lucide lucide-xs ws-chevron${isExpanded ? " open" : ""}"></i>
          </button>
          <span class="ws-name">${this.esc(ws.name)}</span>
          <span class="ws-session-count">${wsSessions.length}</span>
        </div>
        <div class="ws-tree-children${isExpanded ? " expanded" : ""}">
          ${isExpanded ? this.renderWorkspaceSessions(wsSessions) : ""}
        </div>
      </div>`;
    }

    this.treeListEl.innerHTML = html;
    this.bindTreeEvents();

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.treeListEl });
    }
  }

  private renderWorkspaceSessions(sessions: SessionEntryData[]): string {
    if (sessions.length === 0) {
      return `<div class="ws-tree-empty-sessions">${t("workspace.noSessions")}</div>`;
    }
    const activeSid = getState().sessionId;
    let html = "";
    for (const sess of sessions) {
      const active = sess.session_id === activeSid ? " active" : "";
      const displayName = sess.name || sess.preview || t("general.emptySessionName");
      const runningBadge = sess.is_running ? '<span class="session-running"></span>' : "";

      html += `<div class="ws-tree-session-item${active}" data-sid="${sess.session_id}">
        <div class="session-item-top">
          ${this.batchMode ? `<input type="checkbox" class="session-checkbox" data-sid="${sess.session_id}" ${this.selectedPaths.has(sess.session_id) ? "checked" : ""} />` : ""}
          <span class="session-preview">${this.esc(displayName)}</span>
          ${runningBadge}
        </div>
      </div>`;
    }
    return html;
  }

  private bindTreeEvents(): void {
    if (!this.treeListEl) return;

    this.treeListEl.querySelectorAll(".ws-expand-button").forEach((button) => {
      button.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (this._exiting || this._transitioning) return;
        const path = button.closest<HTMLElement>(".ws-tree-node-header")?.dataset.wsPath;
        if (!path) return;
        this.toggleExpand(path);
        if (!this.batchMode && getState().activeWorkspace !== path) {
          this.activate(path);
        }
      });
    });

    this.treeListEl.querySelectorAll(".ws-tree-node-header").forEach((el) => {
      el.addEventListener("click", (e) => {
        if (this._exiting || this._transitioning) return;
        const path = (el as HTMLElement).getAttribute("data-ws-path");
        if (!path) return;

        if (this.batchMode) {
          const cb = (e.target as HTMLElement).closest<HTMLInputElement>(".ws-checkbox");
          if (!cb) {
            const checkbox = el.querySelector<HTMLInputElement>(".ws-checkbox");
            if (checkbox) {
              checkbox.checked = !checkbox.checked;
              this.toggleSelect(path);
            }
          }
          return;
        }
        if ((e.target as HTMLElement).closest("input")) return;

        this.activate(path);
      });
      el.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        if (this._exiting || this._transitioning || this.batchMode) return;
        const path = (el as HTMLElement).getAttribute("data-ws-path");
        if (!path) return;
        this.showWsContextMenu(path, (e as MouseEvent).clientX, (e as MouseEvent).clientY);
      });
    });

    this.treeListEl.querySelectorAll(".ws-tree-session-item").forEach((el) => {
      el.addEventListener("click", (e) => {
        if (this._exiting || this._transitioning) return;
        if ((e.target as HTMLElement).tagName === "INPUT") return;
        const sid = (el as HTMLElement).dataset.sid;
        if (this.batchMode) {
          if (sid) {
            const cb = el.querySelector<HTMLInputElement>(".session-checkbox");
            if (cb) {
              cb.checked = !cb.checked;
              this.toggleSelect(sid);
            }
          }
          return;
        }
        if (sid) {
          const requestId = crypto.randomUUID();
          setSessionId(sid);
          setRequestedSessionId(sid, requestId);
          send({ type: "resume", session_id: sid, request_id: requestId });
        }
      });
      el.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        if (this._exiting || this._transitioning) return;
        const sid = (el as HTMLElement).dataset.sid;
        if (!sid) return;
        import("./session.js").then(({ showSessionContextMenu }) => {
          showSessionContextMenu(sid, (e as MouseEvent).clientX, (e as MouseEvent).clientY);
        });
      });
    });

    this.treeListEl.querySelectorAll(".ws-checkbox").forEach((cb) => {
      cb.addEventListener("change", () => {
        const path = (cb as HTMLElement).getAttribute("data-path");
        if (path) this.toggleSelect(path);
      });
    });

    this.treeListEl.querySelectorAll(".session-checkbox").forEach((cb) => {
      cb.addEventListener("change", () => {
        const sid = (cb as HTMLElement).getAttribute("data-sid");
        if (sid) this.toggleSelect(sid);
      });
    });
  }

  private toggleBatchMode(): void {
    if (getState().workspaces.length === 0) return;
    this.batchMode = !this.batchMode;
    if (!this.batchMode) this.selectedPaths.clear();
    this.updateBatchBarVisibility();
    this.renderTree();
  }

  /** Exit batch mode without performing any bulk action (mirrors session cancel). */
  private exitBatchMode(): void {
    if (!this.batchMode) return;
    this.batchMode = false;
    this.selectedPaths.clear();
    this.updateBatchBarVisibility();
    this.renderTree();
  }

  /** Show/hide the batch-mode action buttons (mirrors the session batch bar). */
  private updateBatchBarVisibility(): void {
    const openBtn = document.getElementById("btn-open-workspace");
    const manageBtn = document.getElementById("btn-ws-manage");
    const cancelBtn = document.getElementById("btn-ws-cancel");
    const selectAllBtn = document.getElementById("btn-ws-select-all");
    const exportBtn = document.getElementById("btn-ws-export");
    const deleteBtn = document.getElementById("btn-ws-delete");
    // In batch mode the "add workspace" and "manage" toggles are replaced by
    // the cancel / select-all / export / delete actions.
    if (openBtn) openBtn.classList.toggle("hidden", this.batchMode);
    if (manageBtn) manageBtn.classList.toggle("hidden", this.batchMode);
    if (cancelBtn) cancelBtn.classList.toggle("hidden", !this.batchMode);
    if (selectAllBtn) selectAllBtn.classList.toggle("hidden", !this.batchMode);
    if (exportBtn) exportBtn.classList.toggle("hidden", !this.batchMode);
    if (deleteBtn) deleteBtn.classList.toggle("hidden", !this.batchMode);
  }

  private batchSelectAll(): void {
    const st = getState();
    const allPaths = [
      ...st.workspaces.map((w) => w.path),
      ...st.sessionsList.map((s) => s.session_id),
    ];
    const allSelected = allPaths.length > 0 && allPaths.every((p) => this.selectedPaths.has(p));
    if (allSelected) {
      this.selectedPaths.clear();
    } else {
      for (const p of allPaths) this.selectedPaths.add(p);
    }
    this.renderTree();
  }

  /**
   * Sessions whose parent workspace is also selected are covered by that
   * workspace selection, so they must not be processed a second time.
   */
  private coveredSessionIds(): Set<string> {
    const st = getState();
    const wsPaths = new Set(st.workspaces.map(w => w.path));
    const selectedWs = [...this.selectedPaths].filter(p => wsPaths.has(p));
    const covered = new Set<string>();
    if (selectedWs.length === 0) return covered;
    for (const wsPath of selectedWs) {
      for (const s of st.sessionsList) {
        if (this.belongsToWorkspace(s, wsPath)) covered.add(s.session_id);
      }
    }
    return covered;
  }

  private async batchExport(): Promise<void> {
    const st = getState();
    const wsPaths = new Set(st.workspaces.map(w => w.path));
    const covered = this.coveredSessionIds();
    const toExport: string[] = [];
    // Individual sessions that are not covered by a selected workspace.
    for (const p of this.selectedPaths) {
      if (wsPaths.has(p)) continue;        // a workspace is not a session export
      if (covered.has(p)) continue;        // already exported via its workspace
      toExport.push(p);
    }
    // Every session that belongs to a selected workspace.
    for (const sid of covered) toExport.push(sid);
    if (toExport.length === 0) return;
    for (const sid of toExport) {
      send({ type: "export_session", session_id: sid });
    }
    this.selectedPaths.clear();
    this.toggleBatchMode();
  }

  private toggleSelect(path: string): void {
    const st = getState();
    const ws = st.workspaces.find((w) => w.path === path);
    if (ws) {
      // Selecting a workspace cascades to every session under it (and
      // deselecting clears them), mirroring parent/child selection.
      const childSids = st.sessionsList
        .filter((s) => this.belongsToWorkspace(s, path))
        .map((s) => s.session_id);
      const willSelect = !this.selectedPaths.has(path);
      if (willSelect) {
        this.selectedPaths.add(path);
        for (const sid of childSids) this.selectedPaths.add(sid);
      } else {
        this.selectedPaths.delete(path);
        for (const sid of childSids) this.selectedPaths.delete(sid);
      }
      this.renderTree();
      return;
    }
    if (this.selectedPaths.has(path)) {
      this.selectedPaths.delete(path);
    } else {
      this.selectedPaths.add(path);
    }
  }

  private async batchDelete(): Promise<void> {
    const st = getState();
    const wsPaths = new Set(st.workspaces.map(w => w.path));
    const covered = this.coveredSessionIds();
    const selectedWs = [...this.selectedPaths].filter(p => wsPaths.has(p));
    const standaloneSessions = [...this.selectedPaths].filter(p => !wsPaths.has(p) && !covered.has(p));
    const count = selectedWs.length + standaloneSessions.length;
    if (count === 0) return;
    if (!await Dialog.confirm(t("workspace.confirmDeleteTitle", { count }), t("workspace.confirmDelete", { count }))) return;
    for (const p of this.selectedPaths) {
      if (wsPaths.has(p)) {
        send({ type: "remove_workspace", path: p });
      } else if (!covered.has(p)) {
        // Sessions under a selected workspace are removed with the workspace.
        send({ type: "delete_session", session_id: p });
      }
    }
    this.selectedPaths.clear();
    this.toggleBatchMode();
  }

  /** Opens a folder picker and requests the backend to open it as a workspace. */
  async openFolder(): Promise<void> {
    const folderPath = await window.electronAPI?.pickDirectory();
    if (!folderPath) return;
    const requestId = crypto.randomUUID();
    setRequestedSessionId("", requestId);
    send({ type: "open_workspace", path: folderPath, request_id: requestId });
  }

  /** Toggle a workspace's expansion in the tree (works in both normal and batch mode). */
  private toggleExpand(path: string): void {
    if (this.expandedWsPaths.has(path)) {
      this.expandedWsPaths.delete(path);
    } else {
      this.expandedWsPaths.add(path);
    }
    this._saveExpandedState();
    this.renderTree();
  }

  private activate(path: string): void {
    if (this._exiting || this._transitioning || !this.isInWorkspaceMode) return;
    setActiveWorkspace(path);
    const requestId = crypto.randomUUID();
    setRequestedSessionId("", requestId);
    send({ type: "open_workspace", path, request_id: requestId });
  }

  private esc(s: string): string {
    const el = document.createElement("span");
    el.textContent = s;
    return el.innerHTML;
  }

  /** Check whether a session belongs to a given workspace path. */
  private belongsToWorkspace(sess: SessionEntryData, wsPath: string): boolean {
    const owner = String(sess.metadata?.workspace || sess.metadata?.workspace_path || "");
    return normalizeWorkspacePath(owner) === normalizeWorkspacePath(wsPath);
  }

  /** Build a short badge label for the session's channel/mode. */
  private channelBadge(channel?: string): string {
    if (!channel || channel === "normal") return "";
    const labels: Record<string, string> = {
      iwork: "iWork",
      qqbot: "QQ",
      telegram: "Telegram",
      webhook: "Webhook",
      discord: "Discord",
      slack: "Slack",
    };
    const label = labels[channel] || channel;
    return `<span class="session-channel-badge" data-channel="${this.esc(channel)}">${this.esc(label)}</span>`;
  }

  private showWsContextMenu(path: string, x: number, y: number): void {
    const menuEl = document.getElementById("session-context-menu")!;
    const wsName = getState().workspaces.find(w => w.path === path)?.name || path;
    menuEl.innerHTML = `
      <div class="context-menu-item context-menu-item-danger" id="ctx-ws-delete">
        <i data-lucide="trash-2" class="lucide lucide-sm"></i>
        <span>${this.esc(t("workspace.remove"))}</span>
      </div>`;
    showContextMenu(menuEl, x, y);

    document.getElementById("ctx-ws-delete")?.addEventListener("click", async () => {
      menuEl.classList.add("hidden");
      if (await Dialog.confirm(
        t("workspace.confirmDeleteTitle", { count: 1 }),
        t("workspace.confirmDelete", { count: 1 })
      )) {
        send({ type: "remove_workspace", path });
      }
    });

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: menuEl });
    }
  }
}

/**
 * Marks the first visible sidebar nav item as active.
 */
export function syncFirstNavActive(): void {
  const nav = document.getElementById("sidebar-main-nav");
  if (!nav) return;
  nav.querySelectorAll(".nav-item").forEach((el) => el.classList.remove("active"));
  const first = nav.querySelector<HTMLElement>(".nav-item:not(.hidden)");
  first?.classList.add("active");
}
