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
 * The iWork mode reuses the normal session sidebar (#session-section) and
 * only toggles the backend session context: entering iWork mode opens a
 * workspace (and lists its sessions via `list_sessions`, channel "iwork"),
 * exiting restores the normal session list. This module owns the mode state
 * transitions and the external entry points (tray, mode switch, keyboard
 * shortcuts). Also exposes `syncFirstNavActive` for sidebar nav state.
 */

import { getState, setActiveWorkspace, setWorkspaceMode, subscribe, removeArchivedSessionById, clearMessages, setSessionId, setSessionState } from "./state.js";
import { send } from "./ws.js";
import { setRequestedSessionId, refreshAllData } from "./stream.js";
import { t } from "./i18n.js";
import { Dialog } from "./dialog.js";
import { showContextMenu } from "./context-menu.js";
import { workspaceIconHtml } from "./session-projection.js";
import type { WorkspaceEntry, WorkspaceConfig, SessionEntryData } from "./types.js";

/**
 * Manages iWork mode transitions (enter / exit / force-exit).
 */
export class Workspace {
  private isInWorkspaceMode = false;
  private _exiting = false;
  private _transitioning = false;
  private pendingWorkspacePath = "";

  /** Public read-only access to the workspace mode flag. */
  public get isInWorkspaceModePublic(): boolean {
    return this.isInWorkspaceMode;
  }

  /** Callback fired after entering/exiting iWork mode so the app can refresh the content area. */
  public onModeChange: (() => void) | null = null;

  constructor() {
    this.syncFirstNavActive();
    // The sidebar workspace section keeps only its header + ">" nav button;
    // the actual workspace list lives in the WorkspaceManager popup.
  }

  private esc(s: string): string {
    const el = document.createElement("span");
    el.textContent = s;
    return el.innerHTML;
  }

  /** Toggle between normal and iWork mode. */
  private async toggleWorkspaceMode(): Promise<void> {
    if (this._transitioning) return;
    if (this.isInWorkspaceMode) {
      await this.exitWorkspaceMode();
    } else {
      await this.enterWorkspaceMode();
    }
  }

  /** Enter iWork mode (no-op if already in it or mid-transition). */
  async enter(): Promise<void> {
    if (!this.isInWorkspaceMode && !this._transitioning) {
      await this.enterWorkspaceMode();
    }
  }

  /** Opens a workspace from an external entry point, such as the tray. */
  public async open(path: string): Promise<void> {
    if (!path || this._transitioning) return;
    if (!this.isInWorkspaceMode) {
      this.pendingWorkspacePath = path;
      await this.enterWorkspaceMode();
      return;
    }
    this.activate(path);
  }

  /** Public exit — used by the header mode switch to leave workspace mode. */
  async exit(): Promise<void> {
    if (this.isInWorkspaceMode && !this._transitioning) {
      await this.exitWorkspaceMode();
    }
  }

  /**
   * Force-exit workspace mode without any visual transitions.
   */
  public forceExit(): void {
    if (!this.isInWorkspaceMode) return;
    this._exiting = true;
    this.isInWorkspaceMode = false;

    const oldWs = getState().activeWorkspace;
    setActiveWorkspace("");
    setWorkspaceMode("normal");
    if (oldWs) {
      const requestId = crypto.randomUUID();
      setRequestedSessionId("", requestId);
      send({ type: "close_workspace", path: oldWs, request_id: requestId });
    }
    // Unified refresh — workspace_closed also triggers it server-side, this
    // call covers the case where no workspace was open to close.
    refreshAllData();
    this.syncFirstNavActive();
    setTimeout(() => { this._exiting = false; }, 100);
  }

  private async enterWorkspaceMode(): Promise<void> {
    if (this.isInWorkspaceMode || this._transitioning) return;
    this._transitioning = true;
    this.isInWorkspaceMode = true;
    this._exiting = false;

    // Set workspace mode BEFORE sending requests so the sessions_list
    // handler's channel check (workspaceMode === "iwork") passes when the
    // response arrives.
    setWorkspaceMode("iwork");

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
    } else {
      // Already have an active workspace (or empty): refresh the sidebar
      // session list and the tray cache for the current workspace context.
      // Full unified pull so the model selector / settings also refresh.
      refreshAllData();
    }

    this.syncFirstNavActive();
    this._transitioning = false;
    this.onModeChange?.();
  }

  private async exitWorkspaceMode(): Promise<void> {
    if (this._transitioning) return;
    this._transitioning = true;
    this._exiting = true;
    this.isInWorkspaceMode = false;

    const oldWs = getState().activeWorkspace;
    setActiveWorkspace("");
    if (oldWs) {
      const requestId = crypto.randomUUID();
      setRequestedSessionId("", requestId);
      send({ type: "close_workspace", path: oldWs, request_id: requestId });
    }
    // Unified refresh — the close_workspace round-trip triggers workspace_closed
    // (which also runs refreshAllData); this direct call covers edge cases.
    refreshAllData();
    this.syncFirstNavActive();
    this._transitioning = false;
    setWorkspaceMode("normal");
    this.onModeChange?.();
    setTimeout(() => { this._exiting = false; }, 100);
  }

  private syncFirstNavActive(): void {
    syncFirstNavActive();
  }

  /** Switch the active workspace (used when already in iWork mode). */
  private activate(path: string): void {
    if (this._exiting || this._transitioning || !this.isInWorkspaceMode) return;
    setActiveWorkspace(path);
    const requestId = crypto.randomUUID();
    setRequestedSessionId("", requestId);
    send({ type: "open_workspace", path, request_id: requestId });
  }

  /** Opens a folder picker and requests the backend to open it as a workspace. */
  async openFolder(): Promise<void> {
    const folderPath = await window.electronAPI?.pickDirectory();
    if (!folderPath) return;
    const requestId = crypto.randomUUID();
    setRequestedSessionId("", requestId);
    send({ type: "open_workspace", path: folderPath, request_id: requestId });
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

/** Deterministic hue from the workspace name (mirrors the backend generator). */
export function nameHue(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) {
    h = (((h * 31) + name.charCodeAt(i)) | 0) >>> 0;
  }
  return h % 360;
}

/**
 * Workspace management overlay.
 *
 * A toast-overlay dialog listing all registered workspaces (real data from
 * `state.workspaces`). The header carries the "New workspace" and "Archive"
 * actions; each list item opens a right-click context menu with Settings /
 * Delete. Settings and Archive render as internal sub-views with a back
 * button, mirroring the notification panel's drill-down navigation.
 */
export class WorkspaceManager {
  private workspace: Workspace;
  private overlay: HTMLElement | null = null;
  private contextMenu: HTMLElement | null = null;
  private view: "list" | "details" | "settings" | "archive" = "list";
  private editingPath = "";
  private unsub: (() => void) | null = null;

  constructor(workspace: Workspace) {
    this.workspace = workspace;
    this.contextMenu = document.getElementById("workspace-mgr-context-menu");
    document.addEventListener("click", () => this.hideContextMenu());
    // Refresh the overlay whenever workspace state changes so the list
    // stays in sync with the backend in real time.
    this.unsub = subscribe(() => {
      if (!this.overlay) return;
      try {
        this.renderBody();
      } catch (err) {
        console.error("[workspace-manager] render failed:", err);
      }
    });
  }

  open(): void {
    this.view = "list";
    this.editingPath = "";
    if (!this.overlay) this.buildOverlay();
    this.overlay!.classList.remove("hidden");
    this.renderBody();
    window.addEventListener("keydown", this.onKeyDown);
  }

  close(): void {
    this.hideContextMenu();
    window.removeEventListener("keydown", this.onKeyDown);
    this.overlay?.classList.add("hidden");
  }

  /** Re-render the open overlay (used when async config responses arrive). */
  refresh(): void {
    if (!this.overlay || this.overlay.classList.contains("hidden")) return;
    this.renderBody();
  }

  private onKeyDown = (e: KeyboardEvent): void => {
    if (e.key === "Escape") this.close();
  };

  private buildOverlay(): void {
    const overlay = document.createElement("div");
    overlay.className = "toast-overlay";
    overlay.id = "workspace-mgr-overlay";
    overlay.innerHTML = `<div class="toast-dialog workspace-mgr-dialog">
      <div class="workspace-mgr-header">
        <button class="btn-icon btn-sm" id="wsmgr-back" title="${t("workspace.back")}"><i data-lucide="arrow-left" class="lucide"></i></button>
        <span class="workspace-mgr-title" id="wsmgr-title"></span>
        <div class="workspace-mgr-actions">
          <button class="btn-icon btn-sm" id="wsmgr-archive" title="${t("workspace.archive")}"><i data-lucide="archive" class="lucide"></i></button>
          <button class="btn-icon btn-sm" id="wsmgr-new" title="${t("workspace.newWorkspace")}"><i data-lucide="plus" class="lucide"></i></button>
        </div>
      </div>
      <div class="workspace-mgr-body" id="wsmgr-body"></div>
    </div>`;
    document.body.appendChild(overlay);
    this.overlay = overlay;
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) this.close();
    });
    overlay.querySelector("#wsmgr-back")?.addEventListener("click", (e) => {
      e.stopPropagation();
      this.handleBack();
    });
    overlay.querySelector("#wsmgr-new")?.addEventListener("click", (e) => {
      e.stopPropagation();
      this.handleNewWorkspace();
    });
    overlay.querySelector("#wsmgr-archive")?.addEventListener("click", (e) => {
      e.stopPropagation();
      this.view = "archive";
      this.renderBody();
      // Pull the latest archived sessions from the backend; the response
      // (archived_sessions_list) fills state.archivedSessions and the state
      // subscription re-renders this view.
      send({ type: "list_archived_sessions" });
    });
    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: overlay });
    }
  }

  private handleBack(): void {
    if (this.view === "list") {
      this.close();
    } else {
      this.view = "list";
      this.editingPath = "";
      this.renderBody();
    }
  }

  private renderBody(): void {
    if (!this.overlay) return;
    const body = this.overlay.querySelector<HTMLElement>("#wsmgr-body");
    const titleEl = this.overlay.querySelector<HTMLElement>("#wsmgr-title");
    if (!body || !titleEl) return;
    // New-workspace / archive actions only belong to the workspace list; hide
    // them while drilling into a workspace's details/settings view.
    const showActions = this.view === "list";
    const archiveBtn = this.overlay.querySelector<HTMLElement>("#wsmgr-archive");
    const newBtn = this.overlay.querySelector<HTMLElement>("#wsmgr-new");
    if (archiveBtn) archiveBtn.style.display = showActions ? "" : "none";
    if (newBtn) newBtn.style.display = showActions ? "" : "none";
    if (this.view === "details") {
      const ws = getState().workspaces.find((w) => w.path === this.editingPath);
      if (!ws) {
        this.view = "list";
        this.editingPath = "";
        this.renderBody();
        return;
      }
      titleEl.textContent = ws.name;
      body.innerHTML = this.renderDetails(ws);
    } else if (this.view === "settings") {
      const ws = getState().workspaces.find((w) => w.path === this.editingPath);
      if (!ws) {
        this.view = "list";
        this.editingPath = "";
        this.renderBody();
        return;
      }
      titleEl.textContent = t("workspace.settingsTitle");
      body.innerHTML = this.renderSettings(ws);
      this.bindSettings(body);
    } else if (this.view === "archive") {
      titleEl.textContent = t("workspace.archive");
      body.innerHTML = this.renderArchive();
      this.bindArchive(body);
    } else {
      titleEl.textContent = t("workspace.manageTitle");
      body.innerHTML = this.renderList();
      this.bindList(body);
    }
    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: body });
    }
  }

  private renderList(): string {
    const workspaces = getState().workspaces;
    if (workspaces.length === 0) {
      return `<div class="si-empty-center"><i data-lucide="folder-open" class="lucide"></i>
        <span class="si-empty-title">${t("workspace.noWorkspaces")}</span>
        <span class="si-empty-sub">${t("workspace.empty")}</span></div>`;
    }
    return `<div class="workspace-mgr-list">${workspaces.map((w) => this.renderListItem(w)).join("")}</div>`;
  }

  private renderListItem(w: WorkspaceEntry): string {
    const active = w.path === getState().activeWorkspace;
    const initial = (w.name.trim()[0] || "?").toUpperCase();
    const iconInner = w.icon_data
      ? `<img class="workspace-mgr-icon-img" src="${w.icon_data}" alt="" draggable="false">`
      : `<span class="workspace-mgr-icon-letter">${this.esc(initial)}</span>`;
    const bgAttr = w.icon_data ? "" : ` style="background:hsl(${nameHue(w.name)}, 62%, 46%)"`;
    return `<div class="workspace-mgr-item${active ? " active" : ""}" data-path="${this.esc(w.path)}">
      <div class="workspace-mgr-item-icon"${bgAttr}>${iconInner}</div>
      <span class="workspace-mgr-item-name">${this.esc(w.name)}</span>
      <span class="workspace-mgr-item-count">${t("workspace.sessions", { count: w.session_count ?? 0 })}</span>
    </div>`;
  }

  private bindList(container: HTMLElement): void {
    container.querySelectorAll(".workspace-mgr-item").forEach((el) => {
      const item = el as HTMLElement;
      const path = item.dataset.path || "";
      item.addEventListener("click", (e) => {
        e.stopPropagation();
        if (!path) return;
        // Left-click drills into the workspace's details view.
        this.view = "details";
        this.editingPath = path;
        this.renderBody();
      });
      item.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.showItemMenu(path, e.clientX, e.clientY);
      });
    });
  }

  private showItemMenu(path: string, x: number, y: number): void {
    if (!this.contextMenu) return;
    this.contextMenu.innerHTML = `<div class="context-menu-item" id="wsmgr-ctx-settings"><i data-lucide="settings" class="lucide lucide-sm"></i><span>${t("workspace.settingsTitle")}</span></div>
      <div class="context-menu-item context-menu-item-danger" id="wsmgr-ctx-delete"><i data-lucide="trash-2" class="lucide lucide-sm"></i><span>${t("workspace.delete")}</span></div>`;
    showContextMenu(this.contextMenu, x, y);
    this.contextMenu.querySelector("#wsmgr-ctx-settings")?.addEventListener("click", () => {
      this.hideContextMenu();
      this.view = "settings";
      this.editingPath = path;
      this.renderBody();
    });
    this.contextMenu.querySelector("#wsmgr-ctx-delete")?.addEventListener("click", () => {
      this.hideContextMenu();
      void this.handleDelete(path);
    });
    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.contextMenu });
    }
  }

  private hideContextMenu(): void {
    this.contextMenu?.classList.add("hidden");
  }

  private renderDetails(w: WorkspaceEntry): string {
    const createdAt = w.created_at ? new Date(w.created_at * 1000).toLocaleString() : "";
    return `<div class="workspace-mgr-settings">
      <div class="workspace-mgr-form-row"><span class="workspace-mgr-form-label">${t("workspace.workspaceName")}</span><span class="workspace-mgr-form-value">${this.esc(w.name)}</span></div>
      <div class="workspace-mgr-form-row"><span class="workspace-mgr-form-label">${t("workspace.path")}</span><span class="workspace-mgr-form-value workspace-mgr-form-value-path">${this.esc(w.path)}</span></div>
      <div class="workspace-mgr-form-row"><span class="workspace-mgr-form-label">${t("workspace.sessionCount")}</span><span class="workspace-mgr-form-value">${w.session_count ?? 0}</span></div>
      <div class="workspace-mgr-form-row"><span class="workspace-mgr-form-label">${t("workspace.workspaceId")}</span><span class="workspace-mgr-form-value">${this.esc(w.id)}</span></div>
      ${createdAt ? `<div class="workspace-mgr-form-row"><span class="workspace-mgr-form-label">${t("workspace.createdAt")}</span><span class="workspace-mgr-form-value">${this.esc(createdAt)}</span></div>` : ""}
    </div>`;
  }

  private renderSettings(w: WorkspaceEntry): string {
    const initial = (w.name.trim()[0] || "?").toUpperCase();
    const iconInner = w.icon_data
      ? `<img class="workspace-mgr-icon-img" src="${w.icon_data}" alt="" draggable="false">`
      : `<span class="workspace-mgr-icon-letter">${this.esc(initial)}</span>`;
    const bgAttr = w.icon_data ? "" : ` style="background:hsl(${nameHue(w.name)}, 62%, 46%)"`;
    // NOTE: workspace-scoped model configuration has been REMOVED — workspaces
    // always use the same model set as general mode (every enabled model).
    return `<div class="workspace-mgr-settings">
      <div class="workspace-mgr-icon-row">
        <div class="workspace-mgr-icon-wrap">
          <div class="workspace-mgr-icon"${bgAttr}>${iconInner}</div>
          <button class="workspace-mgr-icon-upload" id="wsmgr-icon-upload" title="${t("workspace.uploadIcon")}"><i data-lucide="image-plus" class="lucide"></i></button>
        </div>
      </div>
      <div class="model-form-row">
        <label class="model-form-label">${t("workspace.workspaceName")}</label>
        <input type="text" class="model-form-input" id="wsmgr-name-input" value="${this.esc(w.name)}" />
      </div>
    </div>`;
  }

  private bindSettings(container: HTMLElement): void {
    const nameInput = container.querySelector("#wsmgr-name-input") as HTMLInputElement | null;
    nameInput?.addEventListener("change", () => {
      const v = nameInput.value.trim();
      if (!v || !this.editingPath) return;
      send({ type: "rename_workspace", path: this.editingPath, name: v });
    });

    container.querySelector("#wsmgr-icon-upload")?.addEventListener("click", (e) => {
      e.stopPropagation();
      if (!this.editingPath) return;
      const input = document.createElement("input");
      input.type = "file";
      input.accept = "image/*";
      input.addEventListener("change", () => {
        const file = input.files?.[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => {
          if (typeof reader.result === "string" && reader.result.startsWith("data:image/")) {
            send({ type: "upload_workspace_icon", path: this.editingPath, icon_data: reader.result });
          }
        };
        reader.readAsDataURL(file);
      });
      input.click();
    });
  }

  /**
   * Archive manager view.
   *
   * Lists every archived conversation (not workspaces) using the exact same
   * row UI as the sidebar session list ("全部任务" rows): the same
   * `ws-tree-session-item` / `session-item-top` / `session-preview` markup
   * and styles. Each row carries two trailing actions — restore (移出归档)
   * and delete (identical to deleting a normal conversation) — plus a
   * right-click context menu offering the same two actions.
   */
  private renderArchive(): string {
    const archived = getState().archivedSessions;
    if (archived.length === 0) {
      return `<div class="si-empty-center"><i data-lucide="archive" class="lucide"></i>
        <span class="si-empty-title">${t("workspace.archiveEmpty")}</span></div>`;
    }
    return `<div class="workspace-mgr-list">${archived.map((s) => this.renderArchiveItem(s)).join("")}</div>`;
  }

  private renderArchiveItem(s: SessionEntryData): string {
    const preview = s.preview || t("general.emptySessionName");
    const displayName = s.name || preview;
    // Archived conversations are workspace sessions — always show the owning
    // workspace icon (forced, like the sidebar history rows).
    const wsPath = (s.metadata as any)?.workspace_path || (s.metadata as any)?.workspace || "";
    const wsIcon = workspaceIconHtml(wsPath, getState().workspaces, true);
    return `<div class="ws-tree-session-item" data-sid="${this.esc(s.session_id)}">
      <div class="session-item-top">
        ${wsIcon}
        <span class="session-preview">${this.esc(displayName)}</span>
        <span class="archive-item-actions">
          <button class="btn-icon btn-sm archive-action-restore" title="${t("workspace.unarchive")}"><i data-lucide="archive-restore" class="lucide"></i></button>
          <button class="btn-icon btn-sm archive-action-delete" title="${t("workspace.delete")}"><i data-lucide="trash-2" class="lucide"></i></button>
        </span>
      </div>
    </div>`;
  }

  private bindArchive(container: HTMLElement): void {
    container.querySelectorAll(".ws-tree-session-item").forEach((el) => {
      const item = el as HTMLElement;
      const sid = item.dataset.sid || "";
      if (!sid) return;
      item.querySelector(".archive-action-restore")?.addEventListener("click", (e) => {
        e.stopPropagation();
        void this.handleUnarchive(sid);
      });
      item.querySelector(".archive-action-delete")?.addEventListener("click", (e) => {
        e.stopPropagation();
        void this.handleArchiveDelete(sid);
      });
      item.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.showArchiveMenu(sid, e.clientX, e.clientY);
      });
    });
  }

  /** Context menu for an archived conversation: restore + delete. */
  private showArchiveMenu(sid: string, x: number, y: number): void {
    if (!this.contextMenu) return;
    this.contextMenu.innerHTML = `<div class="context-menu-item" id="wsmgr-ctx-unarchive"><i data-lucide="archive-restore" class="lucide lucide-sm"></i><span>${t("workspace.unarchive")}</span></div>
      <div class="context-menu-divider"></div>
      <div class="context-menu-item context-menu-item-danger" id="wsmgr-ctx-delete-archived"><i data-lucide="trash-2" class="lucide lucide-sm"></i><span>${t("workspace.delete")}</span></div>`;
    showContextMenu(this.contextMenu, x, y);
    this.contextMenu.querySelector("#wsmgr-ctx-unarchive")?.addEventListener("click", () => {
      this.hideContextMenu();
      void this.handleUnarchive(sid);
    });
    this.contextMenu.querySelector("#wsmgr-ctx-delete-archived")?.addEventListener("click", () => {
      this.hideContextMenu();
      void this.handleArchiveDelete(sid);
    });
    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.contextMenu });
    }
  }

  /** Restore an archived conversation back into the workspace history —
   *  with the same confirmation UX as archiving/deleting. */
  private async handleUnarchive(sid: string): Promise<void> {
    const s = getState().archivedSessions.find((x) => x.session_id === sid);
    const name = s?.name || s?.preview || sid.slice(0, 8);
    if (!(await Dialog.confirm(t("workspace.confirmUnarchiveTitle"), t("workspace.confirmUnarchive", { name })))) return;
    // Optimistically drop the row from the archive view; the backend
    // broadcast re-inserts the session into the workspace history list.
    removeArchivedSessionById(sid);
    send({ type: "unarchive_session", session_id: sid });
  }

  /** Delete an archived conversation — identical to deleting a normal one:
   *  same confirmation copy, same delete_session message, optimistic removal. */
  private async handleArchiveDelete(sid: string): Promise<void> {
    const s = getState().archivedSessions.find((x) => x.session_id === sid);
    const name = s?.name || s?.preview || sid.slice(0, 8);
    if (!(await Dialog.confirm(t("session.confirmDeleteTitle"), t("session.confirmDelete", { name })))) return;
    // Optimistically drop the row from the archive view.
    removeArchivedSessionById(sid);
    // If the deleted session is the one currently being viewed, clear the
    // chat area to show the "new task" welcome screen immediately.
    if (getState().sessionId === sid) {
      clearMessages();
      setSessionId("");
      setSessionState("idle", "");
    }
    send({ type: "delete_session", session_id: sid });
  }

  private async handleDelete(path: string): Promise<void> {
    const ws = getState().workspaces.find((w) => w.path === path);
    const name = ws?.name || path;
    const ok = await Dialog.confirm(t("workspace.confirmDeleteOneTitle"), t("workspace.confirmDeleteOne", { name }));
    if (!ok) return;
    send({ type: "remove_workspace", path });
    // Backend replies workspace_removed; the state subscription refreshes the list.
  }

  private handleNewWorkspace(): void {
    void this.workspace.openFolder();
  }

  private esc(s: string): string {
    const el = document.createElement("span");
    el.textContent = s;
    return el.innerHTML;
  }
}
