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

import { t } from "./i18n.js";

export class Agents {
  private el: HTMLElement;

  constructor() {
    this.el = document.getElementById("agents-view")!;
    this.render();
  }

  render(): void {
    this.el.innerHTML = `
      <div class="agents-container">
        <div class="agents-header">
          <h2>${t("agents.activeAgents")}</h2>
          <span class="agents-count">${t("agents.activeCount", { count: 0 })}</span>
        </div>
        <div class="agents-list">
          <div class="agents-placeholder">
            <i data-lucide="bot" class="lucide" style="width:32px;height:32px;color:var(--text-muted)"></i>
            <p>${t("agents.noActiveAgents")}</p>
            <span class="agents-placeholder-hint">${t("agents.agentsHint")}</span>
          </div>
        </div>
      </div>
    `;

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons();
    }
  }
}
