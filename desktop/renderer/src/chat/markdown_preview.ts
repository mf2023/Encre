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

import { renderMarkdown } from "./chat.js";

export interface MarkdownPreviewOptions {
  onOpenLink?: (url: string) => void;
}

export class MarkdownPreviewView {
  readonly container: HTMLElement;
  private _body: HTMLElement;
  private _raw = "";
  private _basePath = "";
  private _destroyed = false;
  private _onOpenLink?: (url: string) => void;

  constructor(container: HTMLElement, _title?: string, opts?: MarkdownPreviewOptions) {
    this.container = container;
    this._onOpenLink = opts?.onOpenLink;
    container.style.cssText = "display:flex;flex-direction:column;flex:1;min-height:0;height:100%;";
    container.innerHTML = `<div class="markdown-preview-body"></div>`;
    this._body = container.querySelector(".markdown-preview-body")!;
    this._body.addEventListener("click", (e) => this._onClick(e));
  }

  setContent(markdown: string, basePath?: string): void {
    this._raw = markdown;
    if (basePath !== undefined) this._basePath = basePath;
    this._render();
  }

  setTitle(_title: string): void {
    // title is shown in the tab bar
  }

  private _resolveImages(html: string): string {
    if (!this._basePath) return html;
    const dir = this._basePath.replace(/\\/g, "/").replace(/\/?$/, "/");
    return html.replace(/<img\s+[^>]*src="([^"]+)"[^>]*>/gi, (match, src: string) => {
      if (/^(https?:|data:|local:\/\/\/|file:\/\/|\/)/.test(src)) return match;
      const parts = dir.split("/").filter(Boolean);
      const rel = src.replace(/\\/g, "/");
      for (const seg of rel.split("/")) {
        if (seg === "..") { if (parts.length > 1) parts.pop(); }
        else if (seg !== "." && seg) parts.push(seg);
      }
      return match.replace(`src="${src}"`, `src="local:///${parts.join("/")}"`);
    });
  }

  private _onClick(e: MouseEvent): void {
    const a = (e.target as HTMLElement).closest("a");
    if (!a || !a.href) return;
    const href = a.getAttribute("href") || "";
    if (href.startsWith("#")) return;
    e.preventDefault();
    if (this._onOpenLink) {
      this._onOpenLink(href);
    }
  }

  private _render(): void {
    if (this._destroyed) return;
    this._body.innerHTML = renderMarkdown(this._raw);
    this._body.innerHTML = this._resolveImages(this._body.innerHTML);
  }

  destroy(): void {
    this._destroyed = true;
    this.container.innerHTML = "";
  }
}
