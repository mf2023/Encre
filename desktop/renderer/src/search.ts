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
 */

import { getState, subscribe, setSearchResults } from "./state.js";
import { send } from "./ws.js";
import type { SearchResultEntry } from "./types.js";

export class Search {
  private input: HTMLInputElement;
  private resultsEl: HTMLElement;
  private selectedIdx = -1;
  private timer = 0;

  constructor() {
    this.input = document.getElementById("search-input") as HTMLInputElement;
    this.resultsEl = document.getElementById("search-results")!;

    this.input.addEventListener("input", () => this.onInput());
    this.input.addEventListener("keydown", (e) => this.onKey(e));
    subscribe(() => this.renderResults());
  }

  open(): void {
    const overlay = document.getElementById("search-overlay")!;
    overlay.classList.remove("hidden");
    this.input.value = "";
    this.selectedIdx = -1;
    setSearchResults([]);
    this.resultsEl.innerHTML = "";
    setTimeout(() => this.input.focus(), 10);
  }

  close(): void {
    document.getElementById("search-overlay")?.classList.add("hidden");
    this.input.value = "";
    this.selectedIdx = -1;
    setSearchResults([]);
  }

  private onInput(): void {
    const q = this.input.value.trim();
    this.selectedIdx = -1;
    clearTimeout(this.timer);
    if (!q) {
      setSearchResults([]);
      this.resultsEl.innerHTML = "";
      return;
    }
    this.timer = window.setTimeout(() => {
      send({ type: "search", query: q });
    }, 150);
  }

  private onKey(e: KeyboardEvent): void {
    const results = getState().searchResults;
    if (e.key === "Escape") {
      e.preventDefault();
      this.close();
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      this.selectedIdx = Math.min(this.selectedIdx + 1, results.length - 1);
      this.renderResults();
      this.scrollToSelected();
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      this.selectedIdx = Math.max(this.selectedIdx - 1, -1);
      this.renderResults();
      this.scrollToSelected();
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      if (this.selectedIdx >= 0 && this.selectedIdx < results.length) {
        this.activateResult(results[this.selectedIdx]);
      }
      return;
    }
  }

  private activateResult(r: SearchResultEntry): void {
    this.close();
    if (r.kind === "conversation" && r.session_id) {
      send({ type: "resume", session_id: r.session_id });
    } else if (r.kind === "file" && r.path) {
      const input = document.getElementById("prompt-input") as HTMLTextAreaElement;
      if (input) {
        input.value = `Read ${r.path}`;
        input.focus();
      }
    }
  }

  private renderResults(): void {
    const results = getState().searchResults;
    if (results.length === 0) {
      const q = this.input.value.trim();
      if (q) {
        this.resultsEl.innerHTML = `<div class="search-empty">No results for "${this.esc(q)}"</div>`;
      } else {
        this.resultsEl.innerHTML = "";
      }
      return;
    }

    const convIcon = `<i data-lucide="message-square" class="lucide lucide-sm"></i>`;
    const fileIcon = `<i data-lucide="file" class="lucide lucide-sm"></i>`;

    let html = "";
    for (let i = 0; i < results.length; i++) {
      const r = results[i];
      const sel = i === this.selectedIdx ? " selected" : "";
      if (r.kind === "conversation") {
        html += `<div class="search-result-item${sel}" data-kind="conv" data-sid="${this.esc(r.session_id || "")}" data-idx="${i}">
          ${convIcon}
          <div class="search-result-body">
            <span class="search-result-kind">Conversation</span>
            <span class="search-result-snippet">${this.esc(r.snippet)}</span>
          </div>
        </div>`;
      } else {
        const lineInfo = r.line ? `:${r.line}` : "";
        html += `<div class="search-result-item${sel}" data-kind="file" data-path="${this.esc(r.path || "")}" data-idx="${i}">
          ${fileIcon}
          <div class="search-result-body">
            <span class="search-result-kind">${this.esc(r.path || "")}${lineInfo}</span>
            <span class="search-result-snippet">${this.esc(r.snippet)}</span>
          </div>
        </div>`;
      }
    }

    this.resultsEl.innerHTML = html;
    this.bindClicks();

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.resultsEl });
    }
  }

  private bindClicks(): void {
    const items = this.resultsEl.querySelectorAll(".search-result-item");
    items.forEach((item) => {
      item.addEventListener("click", () => {
        const idx = parseInt((item as HTMLElement).dataset.idx || "-1");
        const results = getState().searchResults;
        if (idx >= 0 && idx < results.length) {
          this.activateResult(results[idx]);
        }
      });
    });
  }

  private scrollToSelected(): void {
    const sel = this.resultsEl.querySelector(".search-result-item.selected");
    if (sel) {
      sel.scrollIntoView({ block: "nearest" });
    }
  }

  private esc(s: string): string {
    const el = document.createElement("span");
    el.textContent = s;
    return el.innerHTML;
  }
}
