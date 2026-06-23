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

import { getState, subscribe, setActiveWorkspace, setSessionId, clearMessages, setWorkspaceMode } from "./state.js";
import { send } from "./ws.js";
import { setRequestedSessionId } from "./stream.js";
import { t, onLocaleChange } from "./i18n.js";
import { Dialog } from "./dialog.js";
import { TransitionHelper } from "./transition-helper.js";
import type { WorkspaceEntry, SessionEntryData } from "./types.js";

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
      this.treeSectionEl.classList.add("hidden");
    }
    if (this._sessionSectionEl) {
      this._sessionSectionEl.style.transition = "";
      this._sessionSectionEl.style.transform = "";
      this._sessionSectionEl.style.opacity = "";
      this._sessionSectionEl.classList.remove("hidden");
    }
    const oldWs = getState().activeWorkspace;
    setActiveWorkspace("");
    setWorkspaceMode("normal");
    if (oldWs) {
      const requestId = crypto.randomUUID();
      setRequestedSessionId("", requestId);
      send({ type: "close_workspace", path: oldWs, request_id: requestId });
    }
    send({ type: "list_sessions" });
    this.syncFirstNavActive();
    setTimeout(() => { this._exiting = false; }, 100);
  }

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

  private toggleWorkspaceMode(): void {
    if (this._transitioning) return;
    if (this.isInWorkspaceMode) {
      this.exitWorkspaceMode();
    } else {
      this.enterWorkspaceMode();
    }
  }

  enter(): void {
    if (!this.isInWorkspaceMode && !this._transitioning) {
      this.enterWorkspaceMode();
    }
  }

  /** Public exit — used by the header mode switch to leave workspace mode
   *  with the same animation pipeline as the internal toggle button. */
  exit(): void {
    if (this.isInWorkspaceMode && !this._transitioning) {
      this.exitWorkspaceMode();
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
    if (this._exiting || this._transitioning) return;
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
    this.renderTree();

    // Unified slide transition:
    //   - 退出: session 分段向左滑出
    //   - 进入: workspace tree 从右侧滑入
    await TransitionHelper.slide({
      exit: [this._sessionSectionEl!].filter(Boolean) as HTMLElement[],
      enter: [this.treeSectionEl!].filter(Boolean) as HTMLElement[],
      setup: () => {
        if (this.treeSectionEl) {
          this.treeSectionEl.classList.add("active");
          this.treeSectionEl.style.maxHeight = "1000px";
        }
      },
    });

    // Activate the first workspace if none active
    const workspaces = getState().workspaces;
    const activeWs = getState().activeWorkspace;
    if ((window as any).__pendingTrayResume) {
      // Do nothing — onSwitchSession already handles opening the correct workspace.
      // Avoid overwriting _requestedSessionRequestId set by that handler.
    } else if (!activeWs && workspaces.length > 0 && workspaces[0].path) {
      setActiveWorkspace(workspaces[0].path);
      const requestId = crypto.randomUUID();
      setRequestedSessionId("", requestId);
      send({ type: "open_workspace", path: workspaces[0].path, request_id: requestId });
    } else if (activeWs) {
      this.expandedWsPaths.add(activeWs);
    }

    // Hide automation button in workspace mode
    const autoBtn = document.getElementById("btn-automation");
    if (autoBtn) autoBtn.classList.add("hidden");
    // Hide temp chat button in workspace mode
    const tempBtn = document.getElementById("btn-temp-chat");
    if (tempBtn) tempBtn.classList.add("hidden");

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
    await TransitionHelper.slide({
      exit: [this.treeSectionEl!].filter(Boolean) as HTMLElement[],
      enter: [this._sessionSectionEl!].filter(Boolean) as HTMLElement[],
      setup: () => {
        if (this.treeSectionEl) {
          this.treeSectionEl.classList.remove("active");
        }
      },
    });

    this._exiting = true;
    this.isInWorkspaceMode = false;
    this.batchMode = false;
    this.selectedPaths.clear();
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

    // Show automation button when exiting workspace mode
    const autoBtn = document.getElementById("btn-automation");
    if (autoBtn) autoBtn.classList.remove("hidden");
    // Show temp chat button when exiting workspace mode
    const tempBtn = document.getElementById("btn-temp-chat");
    if (tempBtn) tempBtn.classList.remove("hidden");

    setTimeout(() => { this._exiting = false; }, 100);
  }

  private syncFirstNavActive(): void {
    syncFirstNavActive();
  }

  private ensureTreeSection(): void {
    if (this.treeSectionEl) return;
    const sessionSection = document.getElementById("session-section");
    if (!sessionSection) return;

    const section = document.createElement("div");
    section.id = "workspace-tree-section";

    const header = document.createElement("div");
    header.className = "workspace-tree-header";
    header.innerHTML = `
      <div class="workspace-tree-actions">
        <button class="btn-icon btn-sm" id="btn-open-workspace" title="${t("workspace.openFolder")}">
          <i data-lucide="folder-plus" class="lucide"></i>
        </button>
        <button class="btn-icon btn-sm" id="btn-ws-manage" title="${t("general.manage")}">
          <i data-lucide="sliders-horizontal" class="lucide"></i>
        </button>
        <button class="btn-icon btn-sm hidden" id="btn-ws-select-all" title="${t("session.batchSelectAll")}">
          <i data-lucide="check-square" class="lucide"></i>
        </button>
        <button class="btn-icon btn-sm hidden batch-color-accent" id="btn-ws-export" title="${t("session.batchExport")}">
          <i data-lucide="download" class="lucide"></i>
        </button>
        <button class="btn-icon btn-sm hidden" id="btn-ws-delete" title="${t("general.delete")}">
          <i data-lucide="trash-2" class="lucide"></i>
        </button>
      </div>`;

    const list = document.createElement("div");
    list.id = "workspace-tree-list";
    list.className = "workspace-tree-list";

    section.appendChild(header);
    section.appendChild(list);

    // Insert workspace tree BEFORE session-section
    sessionSection.parentNode?.insertBefore(section, sessionSection);

    this.treeSectionEl = section;
    this.treeListEl = list;

    // Initially hidden
    section.classList.add("hidden");

    document.getElementById("btn-open-workspace")?.addEventListener("click", () => this.openFolder());
    document.getElementById("btn-ws-manage")?.addEventListener("click", () => this.toggleBatchMode());
    document.getElementById("btn-ws-select-all")?.addEventListener("click", () => this.batchSelectAll());
    document.getElementById("btn-ws-export")?.addEventListener("click", () => this.batchExport());
    document.getElementById("btn-ws-delete")?.addEventListener("click", () => this.batchDelete());

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: section });
    }
  }

  private removeTreeSection(): void {
    // Keep in DOM, just visually hide via CSS transition
    if (this.treeSectionEl) {
      this.treeSectionEl.style.opacity = "0";
      this.treeSectionEl.style.maxHeight = "0";
    }
  }

  private renderTree(): void {
    if (!this.isInWorkspaceMode || !this.treeListEl || this._exiting) return;

    const s = getState();
    const workspaces = s.workspaces.filter((w) => w.path && w.name);
    const activeWs = s.activeWorkspace;

    if (workspaces.length === 0) {
      this.treeListEl.innerHTML = `<div class="workspace-tree-empty">${t("workspace.empty")}</div>`;
      return;
    }

    let html = "";
    for (const ws of workspaces) {
      const isExpanded = this.expandedWsPaths.has(ws.path);
      const isActive = ws.path === activeWs ? " active" : "";
      const expandIcon = isExpanded ? "chevron-down" : "chevron-right";

      // Count sessions for this workspace from the full sessions list
      const wsSessions = s.sessionsList.filter(sess => {
        const wsPath = sess.metadata?.workspace || sess.metadata?.workspace_path || "";
        return wsPath === ws.path;
      });

      html += `<div class="ws-tree-node" data-ws-path="${this.esc(ws.path)}">
        <div class="ws-tree-node-header${isActive}" data-ws-path="${this.esc(ws.path)}">
          ${this.batchMode ? `<input type="checkbox" class="ws-checkbox" data-path="${this.esc(ws.path)}" ${this.selectedPaths.has(ws.path) ? "checked" : ""} />` : ""}
          <i data-lucide="${expandIcon}" class="lucide lucide-xs ws-chevron"></i>
          <i data-lucide="folder" class="lucide lucide-sm ws-folder-icon${isActive ? " ws-folder-active" : ""}"></i>
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
      const ts = (sess.last_active || sess.created_at || 0) * 1000;
      const date = new Date(ts);
      const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      const dateStr = date.toLocaleDateString([], { month: "short", day: "numeric" });
      // Full timestamp for the hover tooltip; empty when invalid.
      const fullTs = ts > 0 ? date.toLocaleString() : "";
      const displayName = sess.name || sess.preview || t("general.emptySessionName");
      const msgCount = sess.message_count ?? 0;
      const runningBadge = sess.is_running ? '<span class="session-running"></span>' : "";
      const badge = this.channelBadge(sess.channel);

      html += `<div class="ws-tree-session-item${active}" data-sid="${sess.session_id}" title="${this.esc(fullTs)}">
        <div class="session-item-top">
          ${this.batchMode ? `<input type="checkbox" class="session-checkbox" data-sid="${sess.session_id}" ${this.selectedPaths.has(sess.session_id) ? "checked" : ""} />` : ""}
          <span class="session-preview">${this.esc(displayName)}</span>
          ${runningBadge}
        </div>
        <span class="ws-session-meta">${dateStr} ${time} · ${msgCount} ${t("session.messages")} ${badge}</span>
      </div>`;
    }
    return html;
  }

  private bindTreeEvents(): void {
    if (!this.treeListEl) return;

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

        if (this.expandedWsPaths.has(path)) {
          this.expandedWsPaths.delete(path);
        } else {
          this.expandedWsPaths.add(path);
        }
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
    // Toggle visibility of batch-mode buttons
    const manageBtn = document.getElementById("btn-ws-manage");
    const selectAllBtn = document.getElementById("btn-ws-select-all");
    const exportBtn = document.getElementById("btn-ws-export");
    const deleteBtn = document.getElementById("btn-ws-delete");
    if (manageBtn) manageBtn.classList.toggle("hidden", this.batchMode);
    if (selectAllBtn) selectAllBtn.classList.toggle("hidden", !this.batchMode);
    if (exportBtn) exportBtn.classList.toggle("hidden", !this.batchMode);
    if (deleteBtn) deleteBtn.classList.toggle("hidden", !this.batchMode);
    this.renderTree();
  }

  private batchSelectAll(): void {
    const workspaces = getState().workspaces;
    if (this.selectedPaths.size === workspaces.length) {
      this.selectedPaths.clear();
    } else {
      for (const ws of workspaces) {
        this.selectedPaths.add(ws.path);
      }
    }
    this.renderTree();
  }

  private async batchExport(): Promise<void> {
    const paths = Array.from(this.selectedPaths);
    if (paths.length === 0) return;
    const wsPaths = new Set(getState().workspaces.map(w => w.path));
    for (const p of paths) {
      if (!wsPaths.has(p)) {
        send({ type: "export_session", session_id: p });
      }
    }
    this.selectedPaths.clear();
    this.toggleBatchMode();
  }

  private toggleSelect(path: string): void {
    if (this.selectedPaths.has(path)) {
      this.selectedPaths.delete(path);
    } else {
      this.selectedPaths.add(path);
    }
  }

  private async batchDelete(): Promise<void> {
    const paths = Array.from(this.selectedPaths);
    if (paths.length === 0) return;
    const count = paths.length;
    if (!await Dialog.confirm(t("workspace.confirmDeleteTitle", { count }), t("workspace.confirmDelete", { count }))) return;
    const wsPaths = new Set(getState().workspaces.map(w => w.path));
    for (const p of paths) {
      if (wsPaths.has(p)) {
        send({ type: "remove_workspace", path: p });
      } else {
        send({ type: "delete_session", session_id: p });
      }
    }
    this.selectedPaths.clear();
    this.toggleBatchMode();
  }

  async openFolder(): Promise<void> {
    const folderPath = await window.electronAPI?.pickDirectory();
    if (!folderPath) return;
    const requestId = crypto.randomUUID();
    setRequestedSessionId("", requestId);
    send({ type: "open_workspace", path: folderPath, request_id: requestId });
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
    menuEl.style.left = `${x}px`;
    menuEl.style.top = `${y}px`;
    menuEl.classList.remove("hidden");

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

export function syncFirstNavActive(): void {
  const nav = document.getElementById("sidebar-main-nav");
  if (!nav) return;
  nav.querySelectorAll(".nav-item").forEach((el) => el.classList.remove("active"));
  const first = nav.querySelector<HTMLElement>(".nav-item:not(.hidden)");
  first?.classList.add("active");
}
