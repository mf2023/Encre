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

import { getState, subscribe } from "./state.js";

export class Tools {
  private panel: HTMLElement;
  private content: HTMLElement;

  constructor() {
    this.panel = document.getElementById("detail-panel")!;
    this.content = document.getElementById("detail-content")!;
    subscribe(() => this.render());
  }

  render(): void {
    const state = getState();
    if (!state.activeToolId) {
      this.panel.classList.add("hidden");
      return;
    }

    const toolCall = this.findToolCall(state.activeToolId);
    if (!toolCall) {
      this.panel.classList.add("hidden");
      return;
    }

    this.panel.classList.remove("hidden");
    this.content.innerHTML = `
      <div class="detail-header">
        <h3>${toolCall.name}</h3>
        <button class="btn-close" id="btn-detail-close">&times;</button>
      </div>
      <div class="detail-section">
        <h4>Parameters</h4>
        <pre>${this.escapeHtml(JSON.stringify(toolCall.params, null, 2))}</pre>
      </div>
      ${
        toolCall.result
          ? `<div class="detail-section">
              <h4>Result</h4>
              <pre class="${toolCall.isError ? "error" : ""}">${this.escapeHtml(toolCall.result)}</pre>
            </div>`
          : '<div class="detail-section"><p>Running...</p></div>'
      }
    `;

    const btn = document.getElementById("btn-detail-close");
    btn?.addEventListener("click", () => {
      (window as any).__state_setActiveToolId?.(null);
    });
  }

  private findToolCall(id: string) {
    const state = getState();
    for (const msg of state.messages) {
      for (const tc of msg.toolCalls) {
        if (tc.id === id) return tc;
      }
    }
    return null;
  }

  private escapeHtml(s: string): string {
    const el = document.createElement("span");
    el.textContent = s;
    return el.innerHTML;
  }
}
