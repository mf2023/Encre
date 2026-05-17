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
import type { PlanItem } from "./types.js";

export class Plan {
  private bar: HTMLElement;
  private barLabel: HTMLElement;
  private barProgress: HTMLElement;
  private barItems: HTMLElement;
  private barToggle: HTMLElement;
  private card: HTMLElement;
  private cardBody: HTMLElement;

  constructor() {
    this.bar = document.getElementById("plan-bar")!;
    this.barLabel = document.getElementById("plan-bar-label")!;
    this.barProgress = document.getElementById("plan-bar-progress")!;
    this.barItems = this.bar.querySelector(".plan-bar-items")!;
    this.barToggle = document.getElementById("plan-bar-toggle")! as HTMLElement;
    this.card = document.querySelector(".plan-card") as HTMLElement;
    this.cardBody = this.card?.querySelector(".plan-card-body")!;

    this.barToggle.addEventListener("click", () => {
      this.bar.classList.toggle("expanded");
      this.card?.classList.toggle("expanded");
    });

    subscribe(() => this.render());
  }

  render(): void {
    const items = getState().planItems;

    if (items.length === 0) {
      this.bar.classList.add("hidden");
      if (this.card) this.card.classList.add("hidden");
      return;
    }

    this.bar.classList.remove("hidden");
    if (this.card) this.card.classList.remove("hidden");

    // Update progress
    const done = items.filter((i) => i.status === "done").length;
    const total = items.length;
    this.barProgress.textContent = `${done}/${total}`;

    // Update bar items (compact icons)
    this.barItems.innerHTML = items
      .map((item) => {
        const cls = item.status;
        const icon =
          item.status === "done"
            ? "check-circle-2"
            : item.status === "active"
              ? "loader-2 plan-spinning"
              : "circle";
        return `<span class="plan-bar-item ${cls}"><i data-lucide="${icon}" class="lucide"></i></span>`;
      })
      .join("");

    // Update card body (detailed list)
    if (this.cardBody) {
      this.cardBody.innerHTML = items
        .map((item) => {
          const cls = `plan-item plan-item-${item.status}`;
          const icon =
            item.status === "done"
              ? "check-circle-2"
              : item.status === "active"
                ? "loader-2 plan-spinning"
                : "circle";
          return `<div class="${cls}">
              <i data-lucide="${icon}" class="lucide plan-item-icon"></i>
              <span>${this.escapeHtml(item.text)}</span>
              <i data-lucide="chevron-right" class="lucide plan-item-detail"></i>
            </div>`;
        })
        .join("");
    }

    // Update card count
    const countEl = this.card?.querySelector(".plan-card-count");
    if (countEl) countEl.textContent = `${done}/${total}`;

    // Refresh icons
    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons();
    }
  }

  private escapeHtml(s: string): string {
    const el = document.createElement("span");
    el.textContent = s;
    return el.innerHTML;
  }
}
