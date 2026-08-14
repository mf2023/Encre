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

import { EALoader } from "./ealoader.js";
import { t } from "./i18n.js";

export class SplashScreen {
  private loader: EALoader | null = null;
  private errorEl: HTMLElement | null = null;

  show(): void {
    document.body.classList.add("splash-mode");
    const el = document.getElementById("splash-screen")!;
    el.classList.remove("hidden");

    if (!this.loader) {
      this.loader = new EALoader(el, {
        maxWidth: "140px",
        staticSrc: "assets/Encre-lm.svg",
        staticDarkSrc: "assets/Encre-dm.svg",
      });
    }

    this.createErrorArea(el);
  }

  hide(): void {
    document.body.classList.remove("splash-mode");
    const el = document.getElementById("splash-screen");
    if (el) el.classList.add("hidden");
    if (this.loader) {
      this.loader.destroy();
      this.loader = null;
    }
    this.errorEl = null;
  }

  showError(title: string, detail: string, onRestart: () => void): void {
    if (this.errorEl) {
      document.getElementById("splash-screen")?.classList.add("splash-error-active");
      const titleEl = this.errorEl.querySelector(".splash-error-title") as HTMLElement;
      if (titleEl) titleEl.textContent = title;
      const detailEl = this.errorEl.querySelector(".splash-error-detail") as HTMLElement;
      if (detailEl) {
        detailEl.textContent = detail;
        detailEl.classList.toggle("hidden", !detail);
      }
      this.errorEl.classList.remove("hidden");
      const btn = this.errorEl.querySelector(".splash-restart-btn") as HTMLButtonElement;
      if (btn) {
        btn.disabled = false;
        btn.textContent = t("app.splashRestart");
        btn.onclick = () => {
          btn.textContent = t("app.splashRestarting");
          btn.disabled = true;
          onRestart();
        };
      }
    }
  }

  private createErrorArea(parent: HTMLElement): void {
    if (this.errorEl) return;
    const el = document.createElement("div");
    el.className = "splash-error hidden";
    el.innerHTML = `
      <div class="splash-error-icon-wrap">
        <i data-lucide="triangle-alert" class="lucide"></i>
      </div>
      <div class="splash-error-title"></div>
      <div class="splash-error-detail hidden"></div>
      <button class="splash-restart-btn btn btn-sm"></button>
    `;
    parent.appendChild(el);
    if (typeof (window as any).lucide !== "undefined") (window as any).lucide.createIcons({ root: el });
    this.errorEl = el;
  }
}