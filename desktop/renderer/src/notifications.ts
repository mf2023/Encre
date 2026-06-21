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

import {
  getState,
  subscribe,
  markNotificationsRead,
  markOneNotificationRead,
  dismissNotification,
  clearAllNotifications,
  getUnreadCount,
} from "./state.js";
import { t } from "./i18n.js";
import type { NotificationItem } from "./types.js";

let toastTimer: ReturnType<typeof setTimeout> | null = null;

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

function typeIcon(type: string): string {
  switch (type) {
    case "error": return "alert-circle";
    case "warning": return "alert-triangle";
    case "success": return "check-circle";
    default: return "info";
  }
}

export class Notifications {
  private bell: HTMLElement | null;
  private panel: HTMLElement | null = null;
  private toastContainer: HTMLElement | null = null;
  private lastNotificationIds: Set<string> = new Set();

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

  syncSeenIds(): void {
    this.lastNotificationIds = new Set(getState().notifications.map((n) => n.id));
  }

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
      <button class="notification-toast-collapse" title="${t("notifications.dismiss")}">
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

  openPanel(): void {
    if (!this.bell) return;
    this.panel = document.createElement("div");
    this.panel.className = "notification-panel";
    this.renderPanel();
    document.body.appendChild(this.panel);

    const rect = this.bell.getBoundingClientRect();
    this.panel.style.top = `${rect.bottom + 6}px`;
    this.panel.style.right = `${window.innerWidth - rect.right}px`;
  }

  private closePanel(): void {
    if (this.panel) {
      this.panel.remove();
      this.panel = null;
      this.render();
    }
  }

  private renderPanel(): void {
    if (!this.panel) return;
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

    this.panel.querySelector(".notification-panel-clear")?.addEventListener("click", () => {
      clearAllNotifications();
      this.closePanel();
    });

    this.panel.querySelectorAll(".notification-panel-item").forEach((el) => {
      const id = el.getAttribute("data-id");
      if (!id) return;
      el.addEventListener("click", () => markOneNotificationRead(id));
      el.querySelector(".notification-panel-dismiss")?.addEventListener("click", (e) => {
        e.stopPropagation();
        dismissNotification(id);
      });
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
          ${n.source ? `<div class="notification-panel-item-source">${this.esc(n.source)}</div>` : ""}
          <div class="notification-panel-item-time">${relativeTime(n.timestamp)}</div>
        </div>
        <div class="notification-panel-actions">
          ${n.read ? "" : `<span class="notification-panel-dot"></span>`}
          <button class="notification-panel-dismiss" title="${t("notifications.dismiss")}">
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
