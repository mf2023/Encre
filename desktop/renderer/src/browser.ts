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
import { getState } from "./state.js";
import { sendSetCdpUrl } from "./ws.js";
import { t, onLocaleChange, applyI18n } from "./i18n.js";

interface BookmarkEntry {
  date_added: string;
  date_modified?: string;
  guid: string;
  id: string;
  name: string;
  type: "url" | "folder";
  url?: string;
  children?: BookmarkEntry[];
}

interface BookmarkRoot {
  children: BookmarkEntry[];
  date_added: string;
  date_modified: string;
  guid: string;
  id: string;
  name: string;
  type: "folder";
}

interface BookmarksData {
  checksum: string;
  roots: {
    bookmark_bar: BookmarkRoot;
    other: BookmarkRoot;
  };
  version: number;
}

const LOAD_TIMEOUT_MS = 30000;

export interface SearchEngine {
  id: string;
  name: string;
  homepage: string;
  searchUrl: string;
}

export const SEARCH_ENGINES: SearchEngine[] = [
  { id: "bing", name: "Bing", homepage: "https://www.bing.com", searchUrl: "https://www.bing.com/search?q={query}" },
  { id: "google", name: "Google", homepage: "https://www.google.com", searchUrl: "https://www.google.com/search?q={query}" },
  { id: "duckduckgo", name: "DuckDuckGo", homepage: "https://duckduckgo.com", searchUrl: "https://duckduckgo.com/?q={query}" },
  { id: "baidu", name: "\u767E\u5EA6", homepage: "https://www.baidu.com", searchUrl: "https://www.baidu.com/s?wd={query}" },
  { id: "sogou", name: "\u641C\u72D7", homepage: "https://www.sogou.com", searchUrl: "https://www.sogou.com/web?query={query}" },
  { id: "yahoo", name: "Yahoo", homepage: "https://search.yahoo.com", searchUrl: "https://search.yahoo.com/search?p={query}" },
  { id: "brave", name: "Brave", homepage: "https://search.brave.com", searchUrl: "https://search.brave.com/search?q={query}" },
  { id: "qwant", name: "Qwant", homepage: "https://www.qwant.com", searchUrl: "https://www.qwant.com/?q={query}" },
];

export function getDefaultSearchEngine(): SearchEngine {
  const st = getState();
  const id = (st.settings.default_search_engine as string) || "bing";
  return SEARCH_ENGINES.find(e => e.id === id) || SEARCH_ENGINES[0];
}

export function getDefaultHomepage(): string {
  return getDefaultSearchEngine().homepage;
}

function isSearchQuery(input: string): boolean {
  if (/^https?:\/\//i.test(input)) return false;
  if (/^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+\.?/i.test(input) && !input.includes(" ")) return false;
  if (/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/.test(input)) return false;
  if (input.includes("/") && !input.includes(" ")) return false;
  return true;
}

export function buildSearchUrl(input: string, engine?: SearchEngine): string {
  const se = engine || getDefaultSearchEngine();
  return se.searchUrl.replace("{query}", encodeURIComponent(input));
}

export interface BrowserViewOptions {
  startUrl?: string;
  partition?: string;
  onTitleChange?: (title: string) => void;
  onUrlChange?: (url: string) => void;
  onFaviconChange?: (favicon: string) => void;
  onNewWindow?: (url: string) => void;
  cdpPort?: number;
  compact?: boolean;
}

export class BrowserView {
  readonly container: HTMLElement;
  readonly webview: any;
  private urlInput: HTMLInputElement;
  private statusEl: HTMLElement | null;
  private loadingEl: HTMLElement | null;
  private errorEl: HTMLElement | null;
  private overlayTitle: HTMLElement | null;
  private overlayDesc: HTMLElement | null;
  private retryBtn: HTMLButtonElement | null;
  private loader: EALoader | null = null;
  private loadTimer: number | null = null;
  private _showedError = false;
  private explicitNav = true;
  private _destroyed = false;
  private _cdpPort: number;
  private _webContentsId: number = -1;
  private _onTitleChange?: (title: string) => void;
  private _onUrlChange?: (url: string) => void;
  private _onFaviconChange?: (favicon: string) => void;
  private _onNewWindow?: (url: string) => void;
  private _settingsBtn: HTMLButtonElement;
  private _mainLoaded = false;
  private _bookmarks: BookmarksData | null = null;
  private _starBtn: HTMLButtonElement;
  private _unsubLocale: (() => void) | null = null;

  constructor(container: HTMLElement, options: BrowserViewOptions = {}) {
    this.container = container;
    this._onTitleChange = options.onTitleChange;
    this._onUrlChange = options.onUrlChange;
    this._onFaviconChange = options.onFaviconChange;
    this._onNewWindow = options.onNewWindow;
    this._cdpPort = options.cdpPort || 0;
    container.style.cssText = "display:flex;flex-direction:column;flex:1;min-height:0;";

    const startUrl = options.startUrl && options.startUrl !== "about:blank" ? options.startUrl : "";
    const partition = options.partition || "persist:encre-browser";
    const compact = options.compact ? " browser-compact" : "";

    const localePlaceholder = t("browserNav.searchOrEnter");
    container.innerHTML = `
      <div class="browser-nav-bar${compact}">
        <button class="browser-nav-btn" data-nav="back" data-i18n-title="browserNav.back">
          <svg viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/></svg>
        </button>
        <button class="browser-nav-btn" data-nav="forward" data-i18n-title="browserNav.forward">
          <svg viewBox="0 0 24 24"><path d="M9 18l6-6-6-6" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/></svg>
        </button>
        <button class="browser-nav-btn" data-nav="reload" data-i18n-title="browserNav.reload">
          <svg viewBox="0 0 24 24"><path d="M23 4v6h-6M1 20v-6h6" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/></svg>
        </button>
        <input type="text" class="browser-url-input" value="${startUrl}" placeholder="${localePlaceholder}" data-i18n-placeholder="browserNav.searchOrEnter" spellcheck="false" />
        <button class="browser-star-btn" data-i18n-title="browserNav.bookmark">☆</button>
        <button class="browser-settings-btn" data-i18n-title="browserNav.settings">
          <svg viewBox="0 0 24 24"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="2" fill="none"/></svg>
        </button>
      </div>
      <div class="browser-webview-wrap">
        <webview class="browser-webview" src="${startUrl || "about:blank"}" partition="${partition}" allowpopups></webview>
        <div class="browser-webview-status hidden">
          <div class="browser-status-loading"></div>
          <div class="browser-status-error hidden">
            <div class="browser-overlay-content">
              <div class="browser-overlay-icon">
                <svg viewBox="0 0 24 24" width="56" height="56" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="12" r="10"/>
                  <line x1="12" y1="8" x2="12" y2="12"/>
                  <line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
              </div>
              <div class="browser-overlay-title" data-i18n="browserNav.failedToLoad">Failed to load</div>
              <div class="browser-overlay-desc" data-i18n="browserNav.checkConnection">The page could not be loaded. Please check your connection and try again.</div>
              <button class="browser-overlay-retry" type="button" data-i18n="browserNav.retry">Retry</button>
            </div>
          </div>
        </div>
      </div>`;

    this.urlInput = container.querySelector(".browser-url-input") as HTMLInputElement;
    this.statusEl = container.querySelector(".browser-webview-status");
    this.loadingEl = container.querySelector(".browser-status-loading");
    this.errorEl = container.querySelector(".browser-status-error");
    this.overlayTitle = container.querySelector(".browser-overlay-title");
    this.overlayDesc = container.querySelector(".browser-overlay-desc");
    this.retryBtn = container.querySelector(".browser-overlay-retry");
    this._settingsBtn = container.querySelector(".browser-settings-btn") as HTMLButtonElement;

    this._starBtn = container.querySelector(".browser-star-btn") as HTMLButtonElement;

    applyI18n();
    this._bindSettings();
    this._bindStarButton();
    this.loadBookmarks();
    this._unsubLocale = onLocaleChange(() => applyI18n());

    const wv = container.querySelector("webview") as any;
    this.webview = wv;

    this.bindEvents();
    this.bindNavButtons();
    this.bindUrlInput();
    const ro = new ResizeObserver(() => {
      if (!this._destroyed) {
        const wv = this.webview;
        try {
          const cw = this.container.clientWidth;
          const factor = Math.max(0.3, Math.min(1.0, cw / 1280));
          wv.setZoomFactor(factor);
        } catch {}
      }
    });
    ro.observe(this.container);
    const api = (window as any).electronAPI;
    if (api?.onNewWindow) {
      api.onNewWindow((url: string, wcId: number) => {
        let myId = -1;
        try { myId = this.webview.getWebContentsId(); } catch {}
        if (myId === wcId) {
          if (url && /^https?:\/\//i.test(url)) {
            this.hideStatus();
            this._onNewWindow?.(url);
          }
        }
      });
    }
    // Register CDP relay for the internal webview and send URL to the backend
    wv.addEventListener("dom-ready", () => {
      try {
        const wcId = wv.getWebContentsId();
        this._webContentsId = wcId;
        const api = (window as any).electronAPI;
        if (api?.registerCdpWebview) {
          api.registerCdpWebview(wcId).then((port: number) => {
            this._cdpPort = port;
            const url = `ws://127.0.0.1:${port}`;
            sendSetCdpUrl(url);
          }).catch((err: any) => {
            console.warn("[browser] CDP relay registration failed:", err);
          });
        }
      } catch (err) {
        console.warn("[browser] CDP setup failed:", err);
      }
    }, { once: true });
  }

  get cdpPort(): number {
    return this._cdpPort;
  }

  set cdpPort(port: number) {
    this._cdpPort = port;
  }

  navigate(url: string): void {
    if (!url || this._destroyed) return;
    if (isSearchQuery(url)) {
      url = buildSearchUrl(url, getDefaultSearchEngine());
    } else if (!/^https?:\/\//i.test(url)) {
      url = "https://" + url;
    }
    this._showedError = false;
    this._mainLoaded = false;
    this.hideStatus();
    this.explicitNav = true;
    this.webview.src = url;
  }

  goBack(): void {
    if (this._destroyed) return;
    this.explicitNav = true;
    this.hideStatus();
    this.webview.goBack();
  }

  goForward(): void {
    if (this._destroyed) return;
    this.explicitNav = true;
    this.hideStatus();
    this.webview.goForward();
  }

  reload(): void {
    if (this._destroyed) return;
    this._mainLoaded = false;
    this.webview.reload();
  }

  getUrl(): string {
    try { return this.webview.getURL(); } catch { return ""; }
  }

  getTitle(): string {
    try { return this.webview.getTitle(); } catch { return ""; }
  }

  canGoBack(): boolean {
    try { return this.webview.canGoBack(); } catch { return false; }
  }

  canGoForward(): boolean {
    try { return this.webview.canGoForward(); } catch { return false; }
  }

  isLoading(): boolean {
    try { return this.webview.isLoading(); } catch { return false; }
  }

  executeJavaScript(code: string): Promise<any> {
    try { return this.webview.executeJavaScript(code); } catch { return Promise.resolve(null); }
  }

  destroy(): void {
    this._destroyed = true;
    this.clearLoadTimer();
    if (this._unsubLocale) {
      this._unsubLocale();
      this._unsubLocale = null;
    }
    if (this.loader) {
      this.loader.destroy();
      this.loader = null;
    }
    // Clean up CDP relay
    if (this._webContentsId > 0) {
      const api = (window as any).electronAPI;
      if (api?.unregisterCdpWebview) {
        api.unregisterCdpWebview(this._webContentsId).catch(() => {});
      }
    }
    try { this.webview.remove(); } catch {}
    this.container.innerHTML = "";
  }

  private _bindSettings(): void {
    this._settingsBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const isChild = document.body.classList.contains("child-mode");
      if (isChild) {
        const api = (window as any).electronAPI;
        if (api?.openSettings) {
          api.openSettings("browser");
        }
      } else {
        window.dispatchEvent(new CustomEvent("open-settings-panel", { detail: { panel: "browser" } }));
      }
    });
  }

  private _bindStarButton(): void {
    this._starBtn.addEventListener("click", () => {
      const raw = this.getUrl();
      if (!raw || raw === "about:blank" || raw.startsWith("chrome-error://")) return;
      const url = raw.replace(/\/+$/, "");
      const api = (window as any).electronAPI;
      if (!api) return;
      if (this._isBookmarked(url)) {
        api.removeBookmark(url).then(() => this.loadBookmarks());
      } else {
        const title = this.getTitle();
        api.addBookmark({ url, title }).then(() => this.loadBookmarks());
      }
    });
  }

  private _isBookmarked(url: string): boolean {
    if (!this._bookmarks) return false;
    const target = url.replace(/\/+$/, "");
    function search(children: BookmarkEntry[]): boolean {
      for (const c of children) {
        if (c.type === "url" && c.url && c.url.replace(/\/+$/, "") === target) return true;
        if (c.type === "folder" && c.children && search(c.children)) return true;
      }
      return false;
    }
    return search(this._bookmarks!.roots.bookmark_bar.children) || search(this._bookmarks!.roots.other.children);
  }

  private loadBookmarks(): void {
    const api = (window as any).electronAPI;
    if (!api?.getBookmarks) return;
    api.getBookmarks().then((data: BookmarksData) => {
      this._bookmarks = data;
      this._updateStarButton();
    }).catch(() => {});
  }

  private _updateStarButton(): void {
    const url = this.getUrl();
    if (url && this._isBookmarked(url)) {
      this._starBtn.textContent = "★";
      this._starBtn.classList.add("starred");
    } else {
      this._starBtn.textContent = "☆";
      this._starBtn.classList.remove("starred");
    }
  }

  private _addHistoryEntry(): void {
    const url = this.getUrl();
    if (!url || url === "about:blank" || url.startsWith("chrome-error://")) return;
    const api = (window as any).electronAPI;
    if (api?.addHistoryEntry) {
      api.addHistoryEntry({ url, title: this.getTitle() });
    }
  }

  private esc(str: string): string {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  private bindEvents(): void {
    const wv = this.webview;

    wv.addEventListener("page-title-updated", (e: any) => {
      this._onTitleChange?.(e.title || "");
    });

    wv.addEventListener("page-favicon-updated", (e: any) => {
      if (e.favicons && e.favicons.length > 0) {
        this._onFaviconChange?.(e.favicons[0]);
      }
    });

    wv.addEventListener("dom-ready", () => {
    });

    wv.addEventListener("will-navigate", (e: any) => {
      this.hideStatus();
      this.explicitNav = false;
      this._mainLoaded = false;
    });

    const applyZoom = () => {
      try {
        const cw = this.container.clientWidth;
        const factor = Math.max(0.3, Math.min(1.0, cw / 1280));
        wv.setZoomFactor(factor);
      } catch {}
    };
    wv.addEventListener("did-finish-load", applyZoom);
    wv.addEventListener("did-navigate", applyZoom);
    applyZoom();

    wv.addEventListener("did-start-loading", () => {
      if (!this._showedError && !this._mainLoaded) {
        this.showLoading();
      }
      this.clearLoadTimer();
      this.loadTimer = window.setTimeout(() => {
        this.showError(t("browserNav.loadTimedOut"), t("browserNav.timeoutDesc"));
      }, LOAD_TIMEOUT_MS);
    });

    wv.addEventListener("did-stop-loading", () => {
      this.clearLoadTimer();
    });

    wv.addEventListener("did-finish-load", () => {
      this._mainLoaded = true;
      this.clearLoadTimer();
      const url = this.webview.getURL();
      // Only show error overlay for real chrome-error pages, not for
      // the initial about:blank state that happens before CDP navigation
      if (url && url.startsWith("chrome-error://")) {
        this.showError(t("browserNav.failedToLoad"), t("browserNav.checkConnection"));
      } else {
        this.hideStatus();
      }
      this._addHistoryEntry();
      this._updateStarButton();
    });

    wv.addEventListener("did-fail-load", (e: any) => {
      if (e && e.isMainFrame === false) return;
      // ERR_ABORTED (-3) fires on redirects and cancelled navigations —
      // the page will retry or the final navigation will fire did-finish-load.
      if (e && e.errorCode === -3) return;
      this.clearLoadTimer();
      const desc = (e && (e.errorDescription || e.message)) || t("browserNav.checkConnection");
      this.showError(t("browserNav.failedToLoad"), String(desc));
    });

    wv.addEventListener("did-navigate", (e: any) => {
      try {
        const url = e.url || wv.getURL() || "";
        if (url.startsWith("chrome-error://")) {
          this.showError(t("browserNav.failedToLoad"), t("browserNav.checkConnection"));
        }
        this._onUrlChange?.(url);
        this._addHistoryEntry();
        this._updateStarButton();
      } catch {}
    });

    wv.addEventListener("did-navigate-in-page", (e: any) => {
      this._onUrlChange?.(e.url);
      this._updateStarButton();
    });
  }

  private bindNavButtons(): void {
    this.container.querySelectorAll("[data-nav]").forEach(btn => {
      btn.addEventListener("click", () => {
        const action = btn.getAttribute("data-nav");
        this.hideStatus();
        if (action === "back") { this.explicitNav = true; this.webview.goBack(); }
        else if (action === "forward") { this.explicitNav = true; this.webview.goForward(); }
        else if (action === "reload") { this._mainLoaded = false; this.webview.reload(); }
      });
    });
  }

  private bindUrlInput(): void {
    this.urlInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        let url = this.urlInput.value.trim();
        if (!url) return;
        this.navigate(url);
      }
    });

    this.webview.addEventListener("did-navigate", (e: any) => {
      try { this.urlInput.value = decodeURI(e.url); } catch { this.urlInput.value = e.url; }
    });
    this.webview.addEventListener("did-navigate-in-page", (e: any) => {
      try { this.urlInput.value = decodeURI(e.url); } catch { this.urlInput.value = e.url; }
    });
  }

  private showLoading(): void {
    this.statusEl?.classList.remove("hidden");
    this.loadingEl?.classList.remove("hidden");
    this.errorEl?.classList.add("hidden");
    if (!this.loader && this.loadingEl) {
      this.loader = new EALoader(this.loadingEl);
    }
  }

  private showError(title: string, desc: string): void {
    this._showedError = true;
    if (this.loader) { this.loader.destroy(); this.loader = null; }
    this.statusEl?.classList.remove("hidden");
    this.loadingEl?.classList.add("hidden");
    if (this.overlayTitle) this.overlayTitle.textContent = title;
    if (this.overlayDesc) this.overlayDesc.textContent = desc;
    this.errorEl?.classList.remove("hidden");
  }

  private hideStatus(): void {
    this._showedError = false;
    if (this.loader) { this.loader.destroy(); this.loader = null; }
    this.statusEl?.classList.add("hidden");
    this.loadingEl?.classList.add("hidden");
    this.errorEl?.classList.add("hidden");
  }

  private clearLoadTimer(): void {
    if (this.loadTimer !== null) {
      clearTimeout(this.loadTimer);
      this.loadTimer = null;
    }
  }

  private isErrorPage(): boolean {
    try {
      const url = this.webview.getURL();
      return !!(url && (url.startsWith("chrome-error://") || url === "about:blank"));
    } catch { return false; }
  }

  }