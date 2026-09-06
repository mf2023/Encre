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

import { send } from "../core/ws.js";
import { init as streamInit } from "../core/stream.js";
import { getState, subscribe } from "../core/state.js";
import { Chat } from "../chat/chat.js";
import { initTooltip } from "../ui/tooltip.js";
import { SplashScreen } from "../ui/splash.js";
import { Tools } from "../features/tools.js";
import { Settings } from "../settings/settings.js";
import { Files } from "../features/files.js";
import { Session } from "../session/session.js";
import { ViewManager } from "../ui/viewmanager.js";
import { Search } from "../features/search.js";
import { Notifications } from "../ui/notifications.js";
import { Workspace, WorkspaceManager } from "../session/workspace.js";
import { Permissions } from "../features/permissions.js";
import { AutomationPanel } from "../session/iclaw.js";
import { Automation } from "../session/automation.js";
import { ModeTransitionManager } from "../chat/mode-transition.js";
import { SessionInner } from "../session/session_inner.js";
import { getLocale, onLocaleChange } from "../features/i18n.js";
import { BrowserView } from "../features/browser.js";

export type ChildTab = {
  view: string;
  label: string;
  title?: string;
  favicon?: string;
  browserView?: BrowserView;
  _contentEl?: HTMLElement;
  _nebulaCleanup?: () => void;
};

/** Default legal-doc region for a UI locale (used before the user picks one). */
function defaultDocRegion(locale: string): string {
  switch (locale) {
    case "zh": return "cn";
    case "zh-Hant": return "tw";
    case "ja": return "jp";
    case "ko": return "kr";
    case "de": return "ch";
    case "tr": return "tr";
    case "es": return "mx";
    case "pt": return "br";
    case "ar": return "ae";
    case "he": return "il";
    default: return "us";
  }
}

// The constructor below calls methods contributed by the feature mixins in
// this directory. The index signature keeps those calls type-safe without an
// extends clause (which would turn the constructor into a derived one and
// require a super() call).
export class AppCore {
  [key: string]: any;
  private chat: Chat;
  private splash: SplashScreen;
  private tools: Tools;
  private settings: Settings;
  private files!: Files;
  private session!: Session;
  private viewManager!: ViewManager;
  private notifications!: Notifications;
  private permissions: Permissions;
  private workspace!: Workspace;
  private workspaceManager!: WorkspaceManager;
  private automationPanel!: AutomationPanel;
  private automation!: Automation;
  private modeTransition!: ModeTransitionManager;
  private sessionInner!: SessionInner;
  private search!: Search;
  private input: HTMLTextAreaElement;
  private btnSend: HTMLButtonElement;
  private btnStop: HTMLButtonElement;
  private tokenCountEl: HTMLElement;
  private welcomeScreen: HTMLElement;
  private messageList: HTMLElement;
  private summaryPanel: HTMLElement;
  private userToggledSidebar = false;
  private skipNextInput = false;
  private _slashActive = false;
  private _currentChipMode = "";
  private _persistentMode = "";
  private _summaryDoneCollapsed: boolean | null = null;
  /** Per-group collapsed state for summary reference groups. */
  private _refCollapsedState: Map<string, boolean> = new Map();
  /** Active slash *command* (distinct from a mode).  Mirrors the backend
   *  ``session.metadata["active_command"]`` slot: a sticky prompt injection
   *  that stays across turns until cleared.  ``null`` = no command active. */
  private _activeCommand: { name: string; prompt?: string; icon?: string; title?: string } | null = null;
  private _welcomeTitleAnimating = false;
  private _isChild = false;
  private _childView = "";
  private _tabs: ChildTab[] = [];
  private _activeTabIndex = -1;
  private _region = defaultDocRegion(getLocale());
  private _activeAutomationJobId = "";
  private _keybindActions: Record<string, () => void> = {};
  private _inputHistory: string[] = [];
  private _inputHistoryIdx: number = -1;
  /** Per-session unsent input drafts, keyed by session id.  Saved while the
   *  user types and restored when the session becomes active again so that
   *  switching away and back does not lose what was being composed. */
  private _drafts = new Map<string, string>();
  private _shortcutsApplied: boolean = false;
  private _shortcutSub: (() => void) | undefined;
  /** Pending auto-resize animation frame for the composer */
  private _inputResizeRaf = 0;
  /** True while the composer is in its expanded (taller) mode. */
  private _inputExpanded = false;
  /** Timer clearing the temporary height-animation class after a toggle. */
  private _inputAnimTimer = 0;
  /**
   * Cached height of `#input-area` measured while it sits in the normal
   * flex flow (i.e. NOT `position: absolute`).  When the composer switches
   * to its expanded "floating overlay" mode, `#input-area` exits the
   * document flow and the chat container would suddenly grow to fill the
   * empty slot, pushing the timeline down to the bottom of the visible
   * area.  We avoid that jump by mirroring this cached height into
   * `#main-content-clip`'s `padding-bottom` for the duration of the
   * overlay so the chat container's geometry stays put.  Updated whenever
   * `#input-area` resizes (textarea auto-grow, viewport changes, etc.).
   */
  private _inputNaturalHeight = 0;
  /** ResizeObserver used to keep `_inputNaturalHeight` in sync. */
  private _inputAreaResizeObs: ResizeObserver | null = null;
  private inputExpandBtn: HTMLButtonElement;
  private inputArea: HTMLElement;
  /** Cache key of the last queue-card render; skips DOM rebuilds when unchanged. */
  private _queueRenderKey = "";

  constructor() {
    this.input = document.getElementById("prompt-input") as HTMLTextAreaElement;
    this.inputExpandBtn = document.getElementById("btn-input-expand") as HTMLButtonElement;
    this.inputArea = document.getElementById("input-area")!;
    this.btnSend = document.getElementById("btn-send") as HTMLButtonElement;
    this.btnStop = document.getElementById("btn-stop") as HTMLButtonElement;
    this.tokenCountEl = document.getElementById("token-count")!;
    this.welcomeScreen = document.getElementById("welcome-screen")!;
    this.messageList = document.getElementById("message-list")!;
    this.summaryPanel = document.getElementById("summary-panel")!;

    // Expose the cleanup function on window so other modules (settings,
    // search, etc.) can request a content-area reset without needing a
    // direct import.  Use a getter that re-binds to ``this`` so callers
    // always invoke the bound method even after hot-reloads.
    (window as any).__appCleanupContentArea = (opts?: { keepAutomationFlag?: boolean }) =>
      this.cleanupContentArea(opts);
    // Expose the app instance on window so stream.ts can update the mode chip
    (window as any).__app = this;

    this.splash = new SplashScreen();
    this.chat = new Chat();
    // Expose chat render so settings can refresh the message list after
    // the settings overlay tears down the chat DOM.
    (window as any).__chatRender = () => this.chat.render();
    // Force a full re-render (resets the render-key cache) -- needed after
    // cleanupContentArea() empties #message-list, because a plain render()
    // would see the unchanged render key and skip fullRender, leaving the
    // chat blank when returning from settings.
    (window as any).__chatForceRender = () => this.chat.renderForce();
    this.tools = new Tools();
this.settings = new Settings();
    this.permissions = new Permissions();
    streamInit(this.chat, this.tools, this.permissions, this.settings);
    this.bindGlobalLinkInterceptor();
    this.bindInput();
    this.updatePlaceholder();
    this.bindSummaryPanel();
    this.bindSearchOverlay();
    this.initKeybindActions();
    this.bindKeyboardShortcuts();
    this.applyShortcutHints();
    this.initTheme();
    initTooltip();
    this.bindResponsiveSidebar();

    // Forward workspace mode to tray + refresh dual session list on mode change
    let lastTrayMode = "";
    ;
    onLocaleChange(() => {
      if (!this.summaryPanel.classList.contains("hidden")) this.renderSummaryPanel();
    });

    subscribe(() => {
      const mode = getState().workspaceMode;
      if (mode && mode !== lastTrayMode) {
        lastTrayMode = mode;
        if (window.electronAPI) {
          window.electronAPI.trayModeUpdate(mode);
        }
        // Tray sessions (normal+iwork) come from the unified sessions_all
        // push — nothing new to fetch on a tray view switch.
      }
    });

    // Update stats display when telemetry changes
    subscribe(() => this.updateStats());

    // Auto-update send/stop button: show send when input has text,
    // show stop only when running AND input is empty.
    onLocaleChange(() => {
      if (!this.summaryPanel.classList.contains("hidden")) this.renderSummaryPanel();
    });

    subscribe(() => {
      const running = getState().running;
      const hasText = this.getPlainText().length > 0;
      if (hasText) {
        this.btnSend.style.display = "flex";
        this.btnStop.style.display = "none";
      } else if (running) {
        this.btnSend.style.display = "none";
        this.btnStop.style.display = "flex";
      } else {
        this.btnSend.style.display = "flex";
        this.btnStop.style.display = "none";
      }
      this.btnStop.classList.remove("cancelling");
      this.btnStop.style.pointerEvents = "";
    this.btnSend.disabled = !hasText && !this.effectiveMode() && !this.hasCommandChip() && getState().attachments.length === 0;
    });

    // Sync inputMode state changes to the input border / chip via the
    // single updateChipState() path.  Previously this wrote data-input-mode
    // directly from state.inputMode while updateChipState() wrote it from
    // _persistentMode -- two sources fighting over one attribute.  Now both
    // funnel through effectiveMode() (chip OR persistent), so the border
    // always reflects the mode that will actually be sent.
    let prevInputMode = "";
    onLocaleChange(() => {
      if (!this.summaryPanel.classList.contains("hidden")) this.renderSummaryPanel();
    });

    let prevTheme = "";
    subscribe(() => {
      const s = getState();
      if (s.inputMode !== prevInputMode) {
        prevInputMode = s.inputMode;
        this.updateChipState();
      }
      const curTheme = s.themePreference;
      if (curTheme !== prevTheme) {
        prevTheme = curTheme;
        this.applyThemeIcons(document.documentElement.getAttribute("data-theme") === "dark");
      }
    });

    // Update session bar name when session changes
    subscribe(() => this.updateSessionBarName());
    subscribe(() => this.updatePlaceholder());
    subscribe(() => this._renderQueueCard());

    // Sync temp chat button active state
    onLocaleChange(() => {
      if (!this.summaryPanel.classList.contains("hidden")) this.renderSummaryPanel();
    });

    subscribe(() => {
      const btn = document.getElementById("btn-temp-chat");
      if (btn) {
        btn.classList.toggle("active", getState().tempChat);
      }
    });

    // Child window mode — detect ?child=VIEW_NAME from URL
    const params = new URLSearchParams(window.location.search);
    const childView = params.get("child");
    if (childView) {
      this._isChild = true;
      this._childView = childView;
      this.initChildMode(childView, params.get("label") || childView);
    }

    // Defer non-critical module initialization (Files, Session, Workspace,
    // Automation, etc.) so the constructor returns quickly and the splash
    // can hide earlier.  Use a double-rAF (NOT a microtask) so the heavy
    // init runs AFTER the first paint — the splash is visible immediately
    // and the deferred work happens in the gap while the renderer waits for
    // the backend WS handshake.
    requestAnimationFrame(() => {
      requestAnimationFrame(() => this.initDeferred());
    });
  }

  private fetchModels(): void {
    send({ type: "list_models" });
  }

  private bindSearchOverlay(): void {
    const btn = document.getElementById("btn-sidebar-search");
    btn?.addEventListener("click", () => {
      this.search.open();
    });

    const overlay = document.getElementById("search-overlay");
    overlay?.addEventListener("click", (e) => {
      if (e.target === overlay) this.search.close();
    });
  }

  private bindResponsiveSidebar(): void {
    const app = document.getElementById("app");
    if (!app) return;
    // Hysteresis: collapse below COLLAPSE_BP, expand above EXPAND_BP.
    // Inside the dead band, keep current state to avoid flicker.
    // COLLAPSE_BP matches the CSS `@media (max-width: 920px)` breakpoint so
    // the sidebar auto-collapses at the EXACT width where it would otherwise
    // flip into absolute/overlay mode — no gray zone where the sidebar covers
    // the main area but refuses to hide.
    const COLLAPSE_BP = 920;
    const EXPAND_BP = 1280;

    const collapsed = () => app.classList.contains("sidebar-collapsed");

    const check = () => {
      // When the window grows well past EXPAND_BP, clear the user-toggle
      // latch so future shrinks can auto-collapse again. Without this, a
      // single explicit click could permanently freeze the sidebar state.
      if (this.userToggledSidebar && window.innerWidth >= EXPAND_BP) {
        this.userToggledSidebar = false;
      }
      if (this.userToggledSidebar) return; // respect explicit user choice
      const w = window.innerWidth;
      // Use <= so the auto-collapse fires at the exact pixel where the CSS
      // overlay breakpoint kicks in (max-width: 920px). w < COLLAPSE_BP would
      // leave a 1px gray zone where the sidebar flips to absolute but is
      // still considered "expanded".
      if (w <= COLLAPSE_BP && !collapsed()) {
        app.classList.add("sidebar-collapsed");
      } else if (w >= EXPAND_BP && collapsed()) {
        app.classList.remove("sidebar-collapsed");
      }
      // Inside the dead band (COLLAPSE_BP, EXPAND_BP), keep current state.
    };

    // Triple-redundant trigger so the auto-collapse / auto-expand can never
    // silently miss a viewport change:
    //   1. matchMedia change listeners — fire EXACTLY when the viewport
    //      crosses the breakpoint; this is the most reliable signal.
    //   2. window resize event — fires on every viewport tick during drag.
    //   3. ResizeObserver on the documentElement — kept as belt-and-braces;
    //      known to be flaky for the root element but costs nothing.
    const collapseMql = window.matchMedia(`(max-width: ${COLLAPSE_BP}px)`);
    const expandMql = window.matchMedia(`(min-width: ${EXPAND_BP}px)`);
    const onCollapseMq = (ev: MediaQueryListEvent) => { if (ev.matches) check(); };
    const onExpandMq = (ev: MediaQueryListEvent) => { if (ev.matches) check(); };
    if (typeof collapseMql.addEventListener === "function") {
      collapseMql.addEventListener("change", onCollapseMq);
      expandMql.addEventListener("change", onExpandMq);
    } else {
      // Safari < 14 fallback (Electron's Chromium supports the new API).
      collapseMql.addListener(onCollapseMq);
      expandMql.addListener(onExpandMq);
    }
    window.addEventListener("resize", check, { passive: true });
    new ResizeObserver(check).observe(document.documentElement);

    // Initial state: align with viewport size, override persisted state.
    if (window.innerWidth <= COLLAPSE_BP) {
      app.classList.add("sidebar-collapsed");
    } else if (window.innerWidth >= EXPAND_BP) {
      app.classList.remove("sidebar-collapsed");
    }
    check();
    // Intentionally NO click handler on main-area: clicking the content
    // must not collapse the sidebar. Users can dismiss it via the toggle
    // button or by resizing past EXPAND_BP.
  }
}
