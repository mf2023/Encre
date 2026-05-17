/**
 * Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
 *
 * This file is part of Yim.
 * The Yim project belongs to the Dunimd Team.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
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

import { getState, subscribe, setSessionId } from "./state.js";
import { send } from "./ws.js";
import type { SessionEntryData } from "./types.js";

export class Session {
  private el: HTMLElement;
  private lastListJson: string = "";

  constructor() {
    this.el = document.getElementById("session-list")!;
    subscribe(() => {
      // Only re-render when sessionsList actually changes — avoids flicker
      const currentJson = JSON.stringify(getState().sessionsList);
      if (currentJson !== this.lastListJson) {
        this.lastListJson = currentJson;
        this.render();
      }
    });
  }

  private fetchSessions(): void {
    send({ type: "list_sessions" });
  }

  render(): void {
    const sessions = getState().sessionsList;
    const currentSid = getState().sessionId;

    if (sessions.length === 0) {
      this.el.innerHTML = '<div class="session-empty">No history yet</div>';
      return;
    }

    let html = "";
    for (const s of sessions) {
      const active = s.session_id === currentSid ? " active" : "";
      const ts = (s.last_active || s.created_at || 0) * 1000;
      const date = new Date(ts);
      const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      const dateStr = date.toLocaleDateString([], { month: "short", day: "numeric" });
      const preview = s.preview || "Empty session";
      const msgCount = s.message_count ?? 0;
      const runningBadge = s.is_running ? '<span class="session-running">●</span>' : "";
      html += `<div class="session-item${active}" data-sid="${s.session_id}">
        <div class="session-item-top">
          <span class="session-preview">${this.escapeHtml(preview)}</span>
          ${runningBadge}
        </div>
        <span class="session-meta">${dateStr} ${time} · ${msgCount} msgs</span>
      </div>`;
    }

    this.el.innerHTML = html;
    this.bindClicks();
  }

  private bindClicks(): void {
    const items = this.el.querySelectorAll(".session-item");
    items.forEach((item) => {
      item.addEventListener("click", () => {
        const sid = (item as HTMLElement).dataset.sid;
        if (sid && sid !== getState().sessionId) {
          setSessionId(sid);
          send({
            type: "resume",
            session_id: sid,
          });
        }
      });
    });
  }

  private escapeHtml(s: string): string {
    const el = document.createElement("span");
    el.textContent = s;
    return el.innerHTML;
  }
}
