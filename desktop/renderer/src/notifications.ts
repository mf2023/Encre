/**
 * Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
 *
 * This file is part of Yim.
 * The Yim project belongs to the Dunimd Team.
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

import { getState, subscribe, markNotificationsRead, getUnreadCount } from "./state.js";
import type { NotificationItem } from "./types.js";

export class Notifications {
  private bell: HTMLElement;
  private dropdown: HTMLElement | null;

  constructor() {
    this.bell = document.getElementById("btn-bell")!;
    this.dropdown = null;

    this.bell.addEventListener("click", (e) => {
      e.stopPropagation();
      this.toggle();
    });

    document.addEventListener("click", () => this.close());

    subscribe(() => this.render());
  }

  private toggle(): void {
    if (this.dropdown) {
      this.close();
    } else {
      this.open();
    }
  }

  private open(): void {
    markNotificationsRead();
    this.dropdown = document.createElement("div");
    this.dropdown.className = "notification-dropdown";
    this.renderDropdown();
    document.body.appendChild(this.dropdown);

    // Position below bell
    const rect = this.bell.getBoundingClientRect();
    this.dropdown.style.top = `${rect.bottom + 4}px`;
    this.dropdown.style.right = `${window.innerWidth - rect.right}px`;
  }

  close(): void {
    if (this.dropdown) {
      this.dropdown.remove();
      this.dropdown = null;
    }
    this.render();
  }

  private renderDropdown(): void {
    if (!this.dropdown) return;
    const notifications = getState().notifications;

    if (notifications.length === 0) {
      this.dropdown.innerHTML = `<div class="notification-empty">No notifications</div>`;
      return;
    }

    this.dropdown.innerHTML = notifications
      .slice(-20)
      .reverse()
      .map((n) => {
        const icon =
          n.type === "error"
            ? "alert-circle"
            : n.type === "success"
              ? "check-circle"
              : n.type === "warning"
                ? "alert-triangle"
                : "info";
        const time = new Date(n.timestamp).toLocaleTimeString();
        return `<div class="notification-item ${n.type}">
              <i data-lucide="${icon}" class="lucide notification-item-icon"></i>
              <div class="notification-item-body">
                <div class="notification-item-title">${this.escapeHtml(n.title)}</div>
                <div class="notification-item-message">${this.escapeHtml(n.message)}</div>
                <div class="notification-item-time">${time}</div>
              </div>
            </div>`;
      })
      .join("");

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons();
    }
  }

  render(): void {
    const count = getUnreadCount();
    // Update bell badge
    let badge = this.bell.querySelector(".notification-badge") as HTMLElement | null;
    if (count > 0) {
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "notification-badge";
        this.bell.style.position = "relative";
        this.bell.appendChild(badge);
      }
      badge.textContent = count > 99 ? "99+" : String(count);
    } else {
      badge?.remove();
    }

    // Refresh dropdown if open
    if (this.dropdown) {
      this.renderDropdown();
    }
  }

  private escapeHtml(s: string): string {
    const el = document.createElement("span");
    el.textContent = s;
    return el.innerHTML;
  }
}
