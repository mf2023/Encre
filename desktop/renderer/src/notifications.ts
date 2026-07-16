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
 * Notification center (bell, panel & toasts).
 *
 * Manages the in-app notifications surfaced through the bell button: an
 * unread-count badge, a slide-out panel grouping unread/read items, and
 * transient toasts for newly-arrived notifications. Reactive to global state
 * via a subscription.
 */

import {
  getState,
  subscribe,
  markNotificationsRead,
  markOneNotificationRead,
  dismissNotification,
  clearAllNotifications,
  getUnreadCount,
  addNotification,
} from "./state.js";
import { MediaViewer } from "./media-viewer.js";
import { t } from "./i18n.js";
import type { NotificationItem } from "./types.js";

let toastTimer: ReturnType<typeof setTimeout> | null = null;

/** Formats a timestamp as a localized relative time ("just now", "3m ago", …). */
function relativeTime(ts: number): string {
  const diff = Date.now() - ts;
  const secs = Math.floor(diff / 1000);
  if (secs < 60) return t("notifications.justNow");
  const mins = Math.floor(secs / 60);
  if (mins < 60) return t("notifications.minutesAgo", { n: mins });
  const hours = Math.floor(mins / 60);
  if (hours < 24) return t("notifications.hoursAgo", { n: hours });
  const days = Math.floor(hours / 24);
  return t("notifications.daysAgo", { n: days });
}

/** Returns the lucide icon name for a notification type. */
function typeIcon(type: string): string {
  switch (type) {
    case "error": return "alert-circle";
    case "warning": return "alert-triangle";
    case "success": return "check-circle";
    default: return "info";
  }
}

/**
 * The notifications controller: badge, panel and toast lifecycle.
 */
export class Notifications {
  private bell: HTMLElement | null;
  private panel: HTMLElement | null = null;
  private toastContainer: HTMLElement | null = null;
  private lastNotificationIds: Set<string> = new Set();
  private _mediaViewer: MediaViewer | null = null;
  private _detailId: string | null = null;
  private _listClickHandler: ((e: MouseEvent) => void) | null = null;

  /**
   * Constructor: wires the bell button, outside-click dismissal and state subscription.
   */
  constructor() {
    this.bell = document.getElementById("btn-bell");
    if (this.bell) {
      this.bell.addEventListener("click", (e) => {
        e.stopPropagation();
        this.togglePanel();
      });
    }
    document.addEventListener("click", (e) => {
      if (this.panel && !this.panel.contains(e.target as Node) && e.target !== this.bell) {
        this.closePanel();
      }
    });

    this.ensureToastContainer();
    subscribe(() => this.render());

    for (const n of getState().notifications) {
      this.lastNotificationIds.add(n.id);
    }
  }

  /** Snapshots the current notification ids as "already seen". */
  syncSeenIds(): void {
    this.lastNotificationIds = new Set(getState().notifications.map((n) => n.id));
  }

  /** Re-renders the badge/panel and pops toasts for any new notifications. */
  render(): void {
    const notifications = getState().notifications;

    for (const n of notifications) {
      if (!this.lastNotificationIds.has(n.id)) {
        this.lastNotificationIds.add(n.id);
        this.showToast(n);
      }
    }

    const currentIds = new Set(notifications.map((n) => n.id));
    for (const id of this.lastNotificationIds) {
      if (!currentIds.has(id)) this.lastNotificationIds.delete(id);
    }

    const count = getUnreadCount();
    if (this.bell) {
      let badge = this.bell.querySelector(".notification-badge") as HTMLElement | null;
      if (count > 0) {
        if (!badge) {
          badge = document.createElement("span");
          badge.className = "notification-badge";
          this.bell.style.position = "relative";
          this.bell.appendChild(badge);
        }
        badge.textContent = "";
      } else {
        badge?.remove();
      }
    }
    if (this.panel) this.renderPanel();
  }

  private ensureToastContainer(): void {
    if (this.toastContainer) return;
    this.toastContainer = document.createElement("div");
    this.toastContainer.className = "notification-toast-container";
    document.body.appendChild(this.toastContainer);
  }

  /** Renders and shows a transient toast for a single notification. */
  showToast(item: NotificationItem): void {
    this.ensureToastContainer();
    const toast = document.createElement("div");
    toast.className = `notification-toast ${item.type}`;
    toast.setAttribute("data-id", item.id);

    const sourceHtml = item.source
      ? `<div class="notification-toast-source">${t("notifications.source")}: ${this.esc(item.source)}</div>`
      : "";

    toast.innerHTML = `
      <div class="notification-toast-message">${this.esc(item.message || item.title)}</div>
      ${sourceHtml}
      <button class="notification-toast-collapse" data-tooltip="${t("notifications.dismiss")}">
        <i data-lucide="chevron-down" class="lucide lucide-sm"></i>
      </button>
    `;

    const collapseBtn = toast.querySelector(".notification-toast-collapse");
    collapseBtn?.addEventListener("click", (e) => {
      e.stopPropagation();
      markOneNotificationRead(item.id);
      dismissNotification(item.id);
      toast.classList.add("removing");
      setTimeout(() => toast.remove(), 300);
    });

    toast.addEventListener("click", () => {
      markOneNotificationRead(item.id);
    });

    this.toastContainer!.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add("visible"));

    const toasts = this.toastContainer!.querySelectorAll(".notification-toast");
    if (toasts.length > 3) {
      const oldest = toasts[0] as HTMLElement;
      oldest.classList.add("removing");
      setTimeout(() => oldest.remove(), 300);
    }

    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.classList.add("removing");
      setTimeout(() => toast.remove(), 300);
    }, 5000);

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: toast });
    }
  }

  private togglePanel(): void {
    if (this.panel) this.closePanel();
    else this.openPanel();
  }

  /** Opens the slide-out notification panel anchored to the bell. */
  openPanel(): void {
    if (!this.bell) return;

    this._detailId = null;
    this.panel = document.createElement("div");
    this.panel.className = "notification-panel";
    this.renderPanel();
    document.body.appendChild(this.panel);

    const rect = this.bell.getBoundingClientRect();
    this.panel.style.top = `${rect.bottom + 6}px`;
    this.panel.style.right = `${window.innerWidth - rect.right}px`;
  }

  /** Closes the slide-out notification panel. */
  private closePanel(): void {
    this._destroyMediaViewer();
    if (this.panel) {
      this.panel.remove();
      this.panel = null;
      this.render();
    }
  }

  /** Builds the panel's inner HTML from unread/read notification lists or detail view. */
  private renderPanel(): void {
    if (!this.panel) return;

    // Detail view
    if (this._detailId) {
      this._renderDetailView();
      return;
    }

    const all = getState().notifications;
    const unread = all.filter((n) => !n.read);
    const read = all.filter((n) => n.read);

    const empty = all.length === 0
      ? `<div class="notification-panel-empty">${t("notifications.empty")}</div>`
      : "";

    const header = all.length > 0
      ? `<div class="notification-panel-header">
           <span>${t("notifications.title")}</span>
           <button class="notification-panel-clear">${t("notifications.clearAll")}</button>
         </div>`
      : "";

    const unreadSection = unread.length > 0
      ? `<div class="notification-section-label">${t("notifications.new")} (${unread.length})</div>
         ${this.renderItems(unread)}`
      : "";

    const readSection = read.length > 0
      ? `<div class="notification-section-label">${t("notifications.read")}</div>
         ${this.renderItems(read.slice(0, 20))}`
      : "";

    this.panel.innerHTML = `${header}${empty}${unreadSection}${readSection}`;

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panel });
    }

    this._wireListEvents();
  }

  private _wireListEvents(): void {
    if (!this.panel) return;

    // Remove previous handler to avoid duplicates
    if (this._listClickHandler) {
      this.panel.removeEventListener("click", this._listClickHandler);
    }

    this.panel.querySelector(".notification-panel-clear")?.addEventListener("click", () => {
      clearAllNotifications();
      this.closePanel();
    });

    this._listClickHandler = (e: MouseEvent) => {
      const item = (e.target as HTMLElement).closest<HTMLElement>(".notification-panel-item");
      if (!item) return;
      const id = item.getAttribute("data-id");
      if (!id) return;

      if ((e.target as HTMLElement).closest(".notification-panel-dismiss")) {
        e.stopPropagation();
        dismissNotification(id);
        return;
      }

      e.stopPropagation();
      this._detailId = id;
      this.renderPanel();
    };

    this.panel.addEventListener("click", this._listClickHandler);
  }

  /** Destroys the current media viewer instance (stops video playback). */
  private _destroyMediaViewer(): void {
    if (this._mediaViewer) {
      this._mediaViewer.destroy();
      this._mediaViewer = null;
    }
  }

  /** Renders the detail view for the currently selected notification. */
  private _renderDetailView(): void {
    if (!this.panel) return;
    const n = getState().notifications.find((x) => x.id === this._detailId);
    if (!n) {
      this._detailId = null;
      this.renderPanel();
      return;
    }

    const absTime = new Date(n.timestamp).toLocaleString();

    this.panel.innerHTML = `
      <div class="notification-detail">
        <div class="notification-detail-header">
          <button class="notification-detail-back" id="notif-detail-back">
            <i data-lucide="arrow-left" class="lucide lucide-sm"></i>
            <span>${t("notifications.back")}</span>
          </button>
        </div>
        ${n.media
          ? `<div class="notification-detail-media" id="notif-detail-media"></div>`
          : `<div class="notification-detail-media notification-detail-media--empty"></div>`}
        <div class="notification-detail-body">
          <div class="notification-detail-title">${this.esc(n.title)}</div>
          ${n.message ? `<div class="notification-detail-msg">${this.esc(n.message)}</div>` : ""}
          <div class="notification-detail-meta">
            ${n.source ? `<span class="notification-detail-source">${this.esc(n.source)}</span>` : ""}
            <span class="notification-detail-time">${absTime}</span>
          </div>
        </div>
      </div>`;

    // Render media via shared MediaViewer component
    if (n.media) {
      const mediaEl = this.panel.querySelector<HTMLElement>("#notif-detail-media");
      if (mediaEl) {
        this._destroyMediaViewer();
        this._mediaViewer = new MediaViewer(mediaEl, n.media);
      }
    }

    this.panel.querySelector("#notif-detail-back")?.addEventListener("click", (e) => {
      e.stopPropagation();
      this._destroyMediaViewer();
      this._detailId = null;
      this.renderPanel();
    });

    this.panel.querySelector("#notif-detail-back")?.addEventListener("click", (e) => {
      e.stopPropagation();
      this._detailId = null;
      this.renderPanel();
    });

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panel });
    }
  }

  private renderItems(items: NotificationItem[]): string {
    return items.map((n) => `
      <div class="notification-panel-item ${n.type}${n.read ? "" : " unread"}" data-id="${n.id}">
        <i data-lucide="${typeIcon(n.type)}" class="lucide notification-panel-icon"></i>
        <div class="notification-panel-body">
          <div class="notification-panel-item-title">${this.esc(n.title)}</div>
          <div class="notification-panel-item-msg">${this.esc(n.message || "")}</div>
          <div class="notification-panel-meta">
            ${n.source ? `<span class="notification-panel-item-source">${this.esc(n.source)}</span>` : ""}
            <span class="notification-panel-item-time">${relativeTime(n.timestamp)}</span>
          </div>
        </div>
        <div class="notification-panel-actions">
          <button class="notification-panel-dismiss" data-tooltip="${t("notifications.dismiss")}">
            <i data-lucide="x" class="lucide lucide-sm"></i>
          </button>
        </div>
      </div>
    `).join("");
  }

  private esc(s: string): string {
    const el = document.createElement("span");
    el.textContent = s;
    return el.innerHTML;
  }
}
