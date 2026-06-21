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

export class ViewManager {
  private currentView: string;
  private navItems: NodeListOf<HTMLElement>;
  private containers: Map<string, HTMLElement>;

  constructor() {
    this.currentView = "chat";
    this.navItems = document.querySelectorAll(".nav-item[data-view]");
    this.containers = new Map();

    // Map data-view values to container elements
    const views = ["chat"];
    for (const view of views) {
      const el = document.getElementById(`${view}-view`);
      if (el) this.containers.set(view, el);
    }

    // Bind nav item clicks
    this.navItems.forEach((item) => {
      item.addEventListener("click", () => {
        const view = item.getAttribute("data-view");
        if (view && this.containers.has(view)) {
          this.switchTo(view);
        }
      });
    });

    // Start with chat view active
    this.showView("chat");
  }

  switchTo(view: string): void {
    if (!this.containers.has(view)) return;
    this.currentView = view;
    this.showView(view);
  }

  private showView(view: string): void {
    // Update nav items active state
    this.navItems.forEach((item) => {
      const v = item.getAttribute("data-view");
      if (v === view) {
        item.classList.add("active");
      } else {
        item.classList.remove("active");
      }
    });

    // Show/hide containers
    this.containers.forEach((el, key) => {
      if (key === view) {
        el.classList.remove("hidden");
      } else {
        el.classList.add("hidden");
      }
    });
  }

  getCurrentView(): string {
    return this.currentView;
  }
}
