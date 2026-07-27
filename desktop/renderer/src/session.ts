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
 * Session sidebar & management.
 *
 * Renders the conversation session list in the sidebar and provides
 * rename/export/delete via a context menu and a rename dialog. Also supports a
 * batch-selection mode for bulk export/delete. The standalone helpers
 * `showSessionContextMenu` / `showRenameDialogForSession` reuse the same DOM
 * overlays for sessions shown inside the workspace tree.
 */

import { getState, subscribe, setSessionId, clearMessages, setRunning, setSubAgentView, clearSubAgentBreadcrumb, setTempChat, removeSessionById } from "./state.js";
import { send } from "./ws.js";
import { setRequestedSessionId } from "./stream.js";
import { t, onLocaleChange } from "./i18n.js";
import { Dialog } from "./dialog.js";
import { showContextMenu } from "./context-menu.js";
import type { SessionEntryData, SessionSource } from "./types.js";

/**
 * Renders and manages the sidebar session list.
 */
export class Session {
  private el: HTMLElement;
  private lastListJson: string = "";
  private contextMenuEl: HTMLElement;
  private renameOverlayEl: HTMLElement;
  private contextTargetSid: string = "";
  private batchMode: boolean = false;
  private selectedIds: Set<string> = new Set();
  private batchBar: HTMLElement;
  /**
   * Constructor: grabs sidebar DOM nodes and subscribes to state/locale changes.
   */
  constructor() {
    this.el = document.getElementById("session-list")!;
    this.contextMenuEl = document.getElementById("session-context-menu")!;
    this.renameOverlayEl = document.getElementById("rename-dialog-overlay")!;
    this.batchBar = document.getElementById("batch-action-bar")!;
    let lastSid = "";
    subscribe(() => {
      const st = getState();
      const currentJson = JSON.stringify(st.sessionsList);
      const sidChanged = st.sessionId !== lastSid;
      if (currentJson !== this.lastListJson || sidChanged) {
        this.lastListJson = currentJson;
        lastSid = st.sessionId;
        this.render();
      }
    });
    onLocaleChange(() => {
      this.render();
      this.updateBatchBarLabels();
    });
    document.addEventListener("click", () => this.hideContextMenu());
    this.bindBatchBar();
  }

  private bindBatchBar(): void {
    document.getElementById("btn-batch-manage")?.addEventListener("click", () => this.toggleBatchMode());
    document.getElementById("btn-batch-select-all")?.addEventListener("click", () => this.batchSelectAll());
    document.getElementById("btn-batch-export")?.addEventListener("click", () => this.batchExport());
    document.getElementById("btn-batch-delete")?.addEventListener("click", () => this.batchDelete());
    document.getElementById("btn-batch-cancel")?.addEventListener("click", () => this.exitBatchMode());
  }

  private updateBatchBarLabels(): void {
    const selAll = document.getElementById("btn-batch-select-all");
    const exp = document.getElementById("btn-batch-export");
    const del = document.getElementById("btn-batch-delete");
    const cancel = document.getElementById("btn-batch-cancel");
    if (selAll) selAll.dataset.tooltip = t("session.batchSelectAll");
    if (exp) exp.dataset.tooltip = t("session.batchExport");
    if (del) del.dataset.tooltip = t("session.batchDelete");
    if (cancel) cancel.dataset.tooltip = t("session.cancel");
  }

  private toggleBatchMode(): void {
    if (this.batchMode) {
      this.exitBatchMode();
    } else {
      this.enterBatchMode();
    }
  }

  private enterBatchMode(): void {
    const sessions = getState().sessionsList;
    if (sessions.length === 0) return;
    this.batchMode = true;
    this.selectedIds.clear();
    const manageBtn = document.getElementById("btn-batch-manage");
    if (manageBtn) manageBtn.style.display = "none";
    this.batchBar.classList.remove("hidden");
    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.batchBar });
    }
    this.render();
  }

  private exitBatchMode(): void {
    this.batchMode = false;
    this.selectedIds.clear();
    const manageBtn = document.getElementById("btn-batch-manage");
    if (manageBtn) manageBtn.style.display = "";
    this.batchBar.classList.add("hidden");
    this.render();
  }

  private batchSelectAll(): void {
    const sessions = getState().sessionsList;
    if (this.selectedIds.size === sessions.length) {
      this.selectedIds.clear();
    } else {
      for (const s of sessions) {
        this.selectedIds.add(s.session_id);
      }
    }
    this.render();
  }

  private async batchExport(): Promise<void> {
    const ids = Array.from(this.selectedIds);
    if (ids.length === 0) return;
    if (ids.length === 1) {
      send({ type: "export_session", session_id: ids[0] });
    } else {
      send({ type: "export_sessions_batch", session_ids: ids });
    }
    this.exitBatchMode();
  }

  private batchDelete(): void {
    const ids = Array.from(this.selectedIds);
    if (ids.length === 0) return;
    for (const sid of ids) {
      send({ type: "delete_session", session_id: sid });
    }
    this.exitBatchMode();
  }

  /** Renders the session list (or empty state) and (re)binds all interactions. */
  render(): void {
    const st = getState();
    const sessions = st.sessionsList;
    const currentSid = st.sessionId;
    const isTempChat = st.tempChat;

    // Filter out the temp session from the sidebar list
    const filteredSessions = isTempChat
      ? sessions.filter(s => s.session_id !== currentSid)
      : sessions;

    if (filteredSessions.length === 0) {
      this.el.innerHTML = `<div class="session-empty">${t("session.noHistory")}</div>`;
      if (this.batchMode) this.exitBatchMode();
      return;
    }

    let html = "";
    for (const s of filteredSessions) {
      const active = s.session_id === currentSid ? " active" : "";
      const preview = s.preview || t("general.emptySessionName");
      const displayName = s.name || preview;
      const runningBadge = s.is_running ? '<span class="session-running"></span>' : "";
      if (this.batchMode) {
        html += `<div class="ws-tree-session-item" data-sid="${s.session_id}">
          <div class="session-item-top">
            <input type="checkbox" class="session-checkbox" data-sid="${s.session_id}" ${this.selectedIds.has(s.session_id) ? "checked" : ""} />
            <span class="session-preview">${this.esc(displayName)}</span>
            ${runningBadge}${this.sourceBadge(s.source)}
          </div>
        </div>`;
      } else {
        html += `<div class="ws-tree-session-item${active}" data-sid="${s.session_id}">
          <div class="session-item-top">
            <span class="session-preview">${this.esc(displayName)}</span>
            ${runningBadge}${this.sourceBadge(s.source)}
          </div>
        </div>`;
      }
    }

    this.el.innerHTML = html;
    this.bindClicks();
    this.bindContextMenus();
    this.bindCheckboxes();
    this.updateBatchBarLabels();
  }

  /** Platform-origin badge for adapter-sourced sessions (Phase 5).
   *
   *  Renders a small pill showing the originating platform (and chat type)
   *  when the session carries a structured {@link SessionSource}.  Returns an
   *  empty string for desktop/normal sessions (no source) -- preserving the
   *  prior badgeless appearance.  Aligns with Hermes' platform_hint projection
   *  so a user can see at a glance which IM platform a conversation came from.
   */
  private sourceBadge(source?: SessionSource): string {
    if (!source || !source.platform) return "";
    const platformLabels: Record<string, string> = {
      qqbot: "QQ", telegram: "Telegram", webhook: "Webhook", discord: "Discord",
      slack: "Slack", feishu: "Feishu", dingtalk: "DingTalk", wecom: "WeCom",
      weixin: "WeChat", whatsapp: "WhatsApp", signal: "Signal", matrix: "Matrix",
      email: "Email", sms: "SMS", yuanbao: "Yuanbao",
      bluebubbles: "iMessage", homeassistant: "HomeAssistant",
      google_chat: "GoogleChat", irc: "IRC", line: "LINE",
      mattermost: "Mattermost", ntfy: "ntfy", photon: "Photon",
      raft: "Raft", simplex: "SimpleX", teams: "Teams",
    };
    const chatTypeLabels: Record<string, string> = {
      dm: "DM", group: "Group", channel: "Channel", thread: "Thread", forum: "Forum",
    };
    const plat = platformLabels[source.platform] || source.platform;
    const ct = source.chat_type ? (chatTypeLabels[source.chat_type] || source.chat_type) : "";
    const label = ct ? `${plat} · ${ct}` : plat;
    return `<span class="session-source-badge" data-platform="${this.esc(source.platform)}">${this.esc(label)}</span>`;
  }

  private bindClicks(): void {
    const items = this.el.querySelectorAll(".ws-tree-session-item");
    items.forEach((item) => {
      item.addEventListener("click", (e) => {
        if ((e.target as HTMLElement).tagName === "INPUT") return;
        if (this.batchMode) return;
        const sid = (item as HTMLElement).dataset.sid;
        if (sid && sid !== getState().sessionId) {
          // Wipe the entire content area BEFORE flipping the session id so
          // every residual widget from the previous session is gone.  The
          // (window as any).__appCleanupContentArea() bridge is set by app.ts
          // at construction time; it nukes sub-agent view, tool detail
          // panel, mention dropdown, queue card, mode chip, attachments,
          // session-inner sidebar (and its terminal/editor tabs),
          // automation view, child view, and forces the welcome screen
          // back to its initial state.
          const cleanup = (window as any).__appCleanupContentArea as
            | ((opts?: { keepAutomationFlag?: boolean }) => void)
            | undefined;
          cleanup?.({ keepAutomationFlag: false });

          // Clear any active sub-agent view overlay (including automation
          // sub-agent views) when explicitly switching to a different session.
          setSubAgentView(null);
          clearSubAgentBreadcrumb();
          (window as any).__isAutomationView = false;
          (window as any).__activeAutomationJobId = "";
          const requestId = crypto.randomUUID();
          // Clean up temp chat before switching to another session
          if (getState().tempChat && getState().sessionId) {
            const oldSid = getState().sessionId;
            setTempChat(false);
            send({ type: "delete_session", session_id: oldSid });
          }
          setSessionId(sid);
          setRequestedSessionId(sid, requestId);
          send({ type: "resume", session_id: sid, request_id: requestId });
        }
      });
    });
  }

  private bindCheckboxes(): void {
    if (!this.batchMode) return;
    const cbs = this.el.querySelectorAll<HTMLInputElement>(".session-checkbox");
    cbs.forEach((cb) => {
      cb.addEventListener("change", () => {
        const sid = cb.dataset.sid;
        if (!sid) return;
        if (cb.checked) {
          this.selectedIds.add(sid);
        } else {
          this.selectedIds.delete(sid);
        }
      });
    });
  }

  private bindContextMenus(): void {
    if (this.batchMode) return;
    const items = this.el.querySelectorAll(".ws-tree-session-item");
    items.forEach((item: Element) => {
      (item as HTMLElement).addEventListener("contextmenu", (e: MouseEvent) => {
        e.preventDefault();
        const sid = (item as HTMLElement).dataset.sid;
        if (!sid) return;
        this.contextTargetSid = sid;
        this.showContextMenu(e.clientX, e.clientY);
      });
    });
  }

  private showContextMenu(x: number, y: number): void {
    this.contextMenuEl.innerHTML = `
      <div class="context-menu-item" id="ctx-rename">
        <i data-lucide="pencil" class="lucide lucide-sm"></i>
        <span>${this.esc(t("session.rename"))}</span>
      </div>
      <div class="context-menu-item" id="ctx-export">
        <i data-lucide="arrow-up-right" class="lucide lucide-sm"></i>
        <span>${this.esc(t("session.exportMd"))}</span>
      </div>
      <div class="context-menu-divider"></div>
      <div class="context-menu-item context-menu-item-danger" id="ctx-delete">
        <i data-lucide="trash-2" class="lucide lucide-sm"></i>
        <span>${this.esc(t("session.delete"))}</span>
      </div>`;
    showContextMenu(this.contextMenuEl, x, y);

    document.getElementById("ctx-rename")?.addEventListener("click", () => this.handleRename());
    document.getElementById("ctx-export")?.addEventListener("click", () => this.handleExport());
    document.getElementById("ctx-delete")?.addEventListener("click", () => this.handleDelete());

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.contextMenuEl });
    }
  }

  private hideContextMenu(): void {
    this.contextMenuEl.classList.add("hidden");
  }

  private hideRenameDialog(): void {
    this.renameOverlayEl.classList.add("hidden");
    this.renameOverlayEl.innerHTML = "";
  }

  private handleRename(): void {
    this.hideContextMenu();
    const sid = this.contextTargetSid;
    if (!sid) return;
    const sessions = getState().sessionsList;
    const s = sessions.find((x) => x.session_id === sid);
    const currentName = s?.name || s?.preview || "";

    this.renameOverlayEl.innerHTML = `
      <div id="rename-dialog">
        <div class="rename-dialog-header">
          <h3>${this.esc(t("session.renameDialogTitle"))}</h3>
        </div>
        <input type="text" id="rename-dialog-input" placeholder="${this.esc(t("session.renamePlaceholder"))}" value="${this.esc(currentName)}" />
        <div class="rename-dialog-actions">
          <button id="rename-dialog-cancel" class="btn">${this.esc(t("session.cancel"))}</button>
          <button id="rename-dialog-confirm" class="btn btn--primary">${this.esc(t("session.rename"))}</button>
        </div>
      </div>`;
    this.renameOverlayEl.classList.remove("hidden");

    const input = document.getElementById("rename-dialog-input") as HTMLInputElement;
    if (input) input.dataset.sessionId = sid;

    document.getElementById("rename-dialog-cancel")?.addEventListener("click", () => this.hideRenameDialog());
    document.getElementById("rename-dialog-confirm")?.addEventListener("click", () => this.confirmRename());
    input?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") this.confirmRename();
      if (e.key === "Escape") this.hideRenameDialog();
    });
    setTimeout(() => input?.focus(), 50);
  }

  private handleExport(): void {
    this.hideContextMenu();
    const sid = this.contextTargetSid;
    if (!sid) return;
    send({ type: "export_session", session_id: sid });
  }

  private async handleDelete(): Promise<void> {
    this.hideContextMenu();
    const sid = this.contextTargetSid;
    if (!sid) return;
    const sessions = getState().sessionsList;
    const s = sessions.find((x) => x.session_id === sid);
    const name = s?.name || s?.preview || sid.slice(0, 8);
    if (await Dialog.confirm(t("session.confirmDeleteTitle"), t("session.confirmDelete", { name }))) {
      removeSessionById(sid);
      if (getState().sessionId === sid) {
        clearMessages();
        setSessionId("");
        setRunning(false, "");
      }
      send({ type: "delete_session", session_id: sid });
    }
  }

  private confirmRename(): void {
    const input = document.getElementById("rename-dialog-input") as HTMLInputElement;
    const newName = input?.value.trim();
    const sid = input?.dataset.sessionId;
    if (sid && newName) {
      send({ type: "rename_session", session_id: sid, new_name: newName });
    }
    this.hideRenameDialog();
  }

  private esc(s: string): string {
    const el = document.createElement("span");
    el.textContent = s;
    return el.innerHTML;
  }
}

/**
 * Shows the session context menu (rename/export/delete) at the given coordinates.
 *
 * @param sid     - The session id the menu acts on.
 * @param x       - Screen X for menu placement.
 * @param y       - Screen Y for menu placement.
 * @param noRename - When `true`, hide the rename item (e.g. for workspace sessions).
 */
export interface RenameConfirmCallback {
  (newName: string): void;
}

/**
 * Shows a generic rename dialog and calls `onConfirm` with the trimmed new name.
 * The dialog is the same visual component used for session renaming.
 *
 * @param currentName - The initial value in the input field.
 * @param onConfirm   - Called when the user confirms a non-empty name.
 */
export function showRenameDialog(currentName: string, onConfirm: RenameConfirmCallback): void {
  const overlayEl = document.getElementById("rename-dialog-overlay")!;
  overlayEl.innerHTML = `
    <div id="rename-dialog">
      <div class="rename-dialog-header">
        <h3>${escHtml(t("session.renameDialogTitle"))}</h3>
      </div>
      <input type="text" id="rename-dialog-input" placeholder="${escHtml(t("session.renamePlaceholder"))}" value="${escHtml(currentName)}" />
      <div class="rename-dialog-actions">
        <button id="rename-dialog-cancel" class="btn">${escHtml(t("session.cancel"))}</button>
        <button id="rename-dialog-confirm" class="btn btn--primary">${escHtml(t("session.rename"))}</button>
      </div>
    </div>`;
  overlayEl.classList.remove("hidden");

  const input = document.getElementById("rename-dialog-input") as HTMLInputElement;

  const hideRename = () => {
    overlayEl.classList.add("hidden");
    overlayEl.innerHTML = "";
  };
  const confirmRename = () => {
    const newName = input?.value.trim();
    if (newName) {
      onConfirm(newName);
    }
    hideRename();
  };

  document.getElementById("rename-dialog-cancel")?.addEventListener("click", hideRename);
  document.getElementById("rename-dialog-confirm")?.addEventListener("click", confirmRename);
  input?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") confirmRename();
    if (e.key === "Escape") hideRename();
  });
  setTimeout(() => input?.focus(), 50);
}

export function showSessionContextMenu(
  sid: string,
  x: number,
  y: number,
  noRename?: boolean,
  noExport?: boolean,
  deleteOverride?: () => void,
  renameOverride?: () => void,
): void {
  const menuEl = document.getElementById("session-context-menu")!;
  const currentSid = sid;
  let items = "";
  if (!noRename) {
    items += `
    <div class="context-menu-item" id="ctx-rename-ws">
      <i data-lucide="pencil" class="lucide lucide-sm"></i>
      <span>${escHtml(t("session.rename"))}</span>
    </div>`;
  }
  if (!noExport) {
    items += `
    <div class="context-menu-item" id="ctx-export-ws">
      <i data-lucide="arrow-up-right" class="lucide lucide-sm"></i>
      <span>${escHtml(t("session.exportMd"))}</span>
    </div>`;
  }
  if (!noRename || !noExport) {
    items += `<div class="context-menu-divider"></div>`;
  }
  items += `
    <div class="context-menu-item context-menu-item-danger" id="ctx-delete-ws">
      <i data-lucide="trash-2" class="lucide lucide-sm"></i>
      <span>${escHtml(t("session.delete"))}</span>
    </div>`;
  menuEl.innerHTML = items;
  showContextMenu(menuEl, x, y);

  if (!noRename) {
    document.getElementById("ctx-rename-ws")?.addEventListener("click", () => {
      menuEl.classList.add("hidden");
      if (renameOverride) {
        renameOverride();
        return;
      }
      const sessions = getState().sessionsList;
      const s = sessions.find((x) => x.session_id === currentSid);
      const currentName = s?.name || s?.preview || "";
      showRenameDialog(currentName, (newName) => {
        send({ type: "rename_session", session_id: currentSid, new_name: newName });
      });
    });
  }
  if (!noExport) {
    document.getElementById("ctx-export-ws")?.addEventListener("click", () => {
      send({ type: "export_session", session_id: currentSid });
      menuEl.classList.add("hidden");
    });
  }
  document.getElementById("ctx-delete-ws")?.addEventListener("click", async () => {
    menuEl.classList.add("hidden");
    if (deleteOverride) {
      deleteOverride();
      return;
    }
    const sessions = getState().sessionsList;
    const s = sessions.find((x) => x.session_id === currentSid);
    const name = s?.name || s?.preview || currentSid.slice(0, 8);
    if (await Dialog.confirm(t("session.confirmDeleteTitle"), t("session.confirmDelete", { name }))) {
      // Optimistically remove the session from the local state immediately,
      // so the UI updates even if the server response is delayed or fails.
      removeSessionById(currentSid);
      // If the deleted session is the one currently being viewed, clear the
      // chat area to show the "new task" welcome screen immediately.
      if (getState().sessionId === currentSid) {
        clearMessages();
        setSessionId("");
        setRunning(false, "");
      }
      send({ type: "delete_session", session_id: currentSid });
    }
  });

  if (typeof (window as any).lucide !== "undefined") {
    (window as any).lucide.createIcons({ root: menuEl });
  }
}

/**
 * Shows the rename dialog for a session and wires confirm/cancel handlers.
 *
 * @param sid - The session id to rename.
 */
export function showRenameDialogForSession(sid: string): void {
  const overlayEl = document.getElementById("rename-dialog-overlay")!;
  const sessions = getState().sessionsList;
  const s = sessions.find((x) => x.session_id === sid);
  const currentName = s?.name || s?.preview || "";

  overlayEl.innerHTML = `
    <div id="rename-dialog">
      <div class="rename-dialog-header">
        <h3>${escHtml(t("session.renameDialogTitle"))}</h3>
      </div>
      <input type="text" id="rename-dialog-input" placeholder="${escHtml(t("session.renamePlaceholder"))}" value="${escHtml(currentName)}" />
      <div class="rename-dialog-actions">
        <button id="rename-dialog-cancel" class="btn">${escHtml(t("session.cancel"))}</button>
        <button id="rename-dialog-confirm" class="btn btn--primary">${escHtml(t("session.rename"))}</button>
      </div>
    </div>`;
  overlayEl.classList.remove("hidden");

  const input = document.getElementById("rename-dialog-input") as HTMLInputElement;
  if (input) input.dataset.sessionId = sid;

  const hideRename = () => {
    overlayEl.classList.add("hidden");
    overlayEl.innerHTML = "";
  };
  const confirmRename = () => {
    const newName = input?.value.trim();
    const sid2 = input?.dataset.sessionId;
    if (sid2 && newName) {
      send({ type: "rename_session", session_id: sid2, new_name: newName });
    }
    hideRename();
  };

  document.getElementById("rename-dialog-cancel")?.addEventListener("click", hideRename);
  document.getElementById("rename-dialog-confirm")?.addEventListener("click", confirmRename);
  input?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") confirmRename();
    if (e.key === "Escape") hideRename();
  });
  setTimeout(() => input?.focus(), 50);
}

function escHtml(s: string): string {
  const el = document.createElement("span");
  el.textContent = s;
  return el.innerHTML;
}
