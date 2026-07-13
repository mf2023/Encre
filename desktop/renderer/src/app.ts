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

import { connect, send, sendRetry, sendSwitchBranch, sendRollback } from "./ws.js";
import { handleEvent, init as streamInit, setOnTranscription, onAutomationShowResult, setRequestedSessionId, onAutomationStreamEvent } from "./stream.js";
import {
  addUserMessage,
  addMessage,
  startAssistantMessage,
  setRunning,
  setTheme,
  setThemePreference,
  setActiveToolId,
  setSettings,
  getState,
  subscribe,
  resetChat,
  initNotificationPersistence,
  showToast,
  clearAttachments,
  setInputMode,
  clearMessages,
  setSessionId,
  addAttachments,
  pushQueuedPrompt,
  setPendingQueueCount,
  removeQueuedPromptAt,
  clearQueuedPrompts,
  removeLastMessage,
  setTempChat,
  setSubAgentView,
  clearSubAgentBreadcrumb,
  restoreMessages,
  getTraySessions,
  removeBranchMessages,
  clearAllNotifications,
} from "./state.js";
import { Chat, formatAgentLabel } from "./chat.js";
import { SplashScreen } from "./splash.js";
import { Tools } from "./tools.js";
import { Settings, type PanelId } from "./settings.js";
import { Files } from "./files.js";
import { Session, showRenameDialogForSession } from "./session.js";
import { ViewManager } from "./viewmanager.js";
import { Search, commandActions } from "./search.js";
import { Agents } from "./agents.js";
import { Notifications } from "./notifications.js";
import { Workspace } from "./workspace.js";
import { Permissions } from "./permissions.js";
import { AutomationPanel } from "./iclaw.js";
import { Automation } from "./automation.js";
import { TransitionHelper } from "./transition-helper.js";
import { SessionInner, TabDef } from "./session_inner.js";
import { renderMarkdown } from "./chat.js";
import { t, onLocaleChange, applyI18n, setLocale } from "./i18n.js";
import { Dialog } from "./dialog.js";
import { lookupShortcut, augmentTitle, formatShortcut, platformLabel } from "./shortcutDisplay.js";
import type { Message } from "./types.js";
import { SLASH_COMMANDS, parseSlashInput, type SlashCommand } from "./slash_commands.js";
import { mountNebula } from "./easter-egg.js";

type ChildTab = {
  view: string;
  label: string;
  title?: string;
  webview?: any;
  _nebulaCleanup?: () => void;
};

(window as any).__state_setActiveToolId = setActiveToolId;
(window as any).sendRetry = sendRetry;
(window as any).sendSwitchBranch = sendSwitchBranch;
(window as any).sendRollback = sendRollback;

class App {
  private chat: Chat;
  private splash: SplashScreen;
  private tools: Tools;
  private settings: Settings;
  private files: Files;
  private session: Session;
  private viewManager: ViewManager;
  private notifications: Notifications;
  private permissions: Permissions;
  private workspace: Workspace;
  private automationPanel: AutomationPanel;
  private automation: Automation;
  private sessionInner: SessionInner;
  private search: Search;
  private input: HTMLTextAreaElement;
  private btnSend: HTMLButtonElement;
  private btnStop: HTMLButtonElement;
  private btnVoice: HTMLButtonElement;
  private tokenCountEl: HTMLElement;
  private welcomeScreen: HTMLElement;
  private messageList: HTMLElement;
  private summaryPanel: HTMLElement;
  private userToggledSidebar = false;
  private skipNextInput = false;
  private _slashActive = false;
  private _currentChipMode = "";
  private _welcomeTitleAnimating = false;
  private _mediaRecorder: MediaRecorder | null = null;
  private _audioChunks: Blob[] = [];
  private _mediaStream: MediaStream | null = null;
  private _isRecording = false;
  private _isChild = false;
  private _childView = "";
  private _tabs: ChildTab[] = [];
  private _activeTabIndex = -1;
  private _region = "intl";
  private _activeAutomationJobId = "";
  private _keybindActions: Record<string, () => void> = {};
  private _inputHistory: string[] = [];
  private _inputHistoryIdx: number = -1;
  private _shortcutsApplied: boolean = false;
  private _shortcutSub: (() => void) | undefined;

  constructor() {
    this.input = document.getElementById("prompt-input") as HTMLTextAreaElement;
    this.btnSend = document.getElementById("btn-send") as HTMLButtonElement;
    this.btnStop = document.getElementById("btn-stop") as HTMLButtonElement;
    this.btnVoice = document.getElementById("btn-voice") as HTMLButtonElement;
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
    this.files = new Files(this.input);

    this.session = new Session();
    this.viewManager = new ViewManager();
    this.search = new Search();
    this.registerCommandActions();
    new Agents();
    this.notifications = new Notifications();
    initNotificationPersistence(() => this.notifications.syncSeenIds());
    this.permissions = new Permissions();
    this.workspace = new Workspace();
    this.automationPanel = new AutomationPanel();
    this.automation = new Automation();

    // Refresh automation data each time the panel opens
    this.automationPanel.onShow = () => this.automation.render();

    // Show automation job results in the chat area when they complete
    const showAutomationResult = (data: any): void => {
      // If a live streaming view for this job already exists, skip creating a new one
      const curView = getState().subAgentView;
      if (curView && curView.id === data.id && (curView.status as string) === "completed") {
        send({ type: "automation_list_jobs" });
        return;
      }
      this.automationPanel.hide();
      clearMessages();
      setSessionId("");
      addUserMessage(data.prompt || data.name || "");
      // Running/in-progress automation entry — show live sub-agent view
      // connected to the real-time stream events. Check this BEFORE the
      // messages check so a running job with partial messages still gets
      // the correct running sub-agent view (with stream event wiring).
      if (data.job_id && data.state !== "COMPLETED") {
        this._activeAutomationJobId = data.job_id;
        const tc: any = {
          id: data.job_id,
          name: "agent",
          params: { agent_name: data.name || t("app.automationDefaultName") },
          status: "running",
          subAgentMessages: restoreMessages(data.messages || []),
          content: data.result || "",
        };
        const origClose = (window as any).__closeSubAgentView;
        (window as any).__closeSubAgentView = () => {
          setSubAgentView(null);
          clearMessages();
          this._activeAutomationJobId = "";
          (window as any).__isAutomationView = false;
          (window as any).__closeSubAgentView = origClose;
          this.automationPanel.toggleAutomationView();
        };
        (window as any).__isAutomationView = true;
        setSubAgentView(tc);
        return;
      }
      // If we have full messages from the sub-agent execution, use sub-agent view
      if (data.messages && data.messages.length > 0) {
        const tc: any = {
          id: crypto.randomUUID(),
          name: "agent",
          params: { agent_name: data.name || t("app.automationDefaultName") },
          status: "completed",
          subAgentMessages: restoreMessages(data.messages),
          content: data.result || "",
        };
        const origClose = (window as any).__closeSubAgentView;
        (window as any).__closeSubAgentView = () => {
          setSubAgentView(null);
          clearMessages();
          (window as any).__isAutomationView = false;
          (window as any).__closeSubAgentView = origClose;
          this.automationPanel.toggleAutomationView();
        };
        setSubAgentView(tc);
        (window as any).__isAutomationView = true;
        return;
      }
      // Fallback: show as plain text assistant message
      const msg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: data.result || "",
        thinking: "",
        thinkingElapsed: 0,
        segments: [],
        isStreaming: false,
        toolCalls: [],
        timestamp: Date.now(),
      };
      addMessage(msg);
    };
    onAutomationShowResult((result: any) => showAutomationResult(result));
    this.automation.onViewResult = (data) => showAutomationResult(data);

    // ── Real-time automation execution streaming ─────────────────────
    onAutomationStreamEvent((event) => {
      const { job_id, event_type, event_data } = event;

      if (event_type === "start") {
        // New automation job started. The ``automation_auto_open_view``
        // setting (default OFF) decides whether we jump to the live
        // sub-agent view immediately or just track it silently in
        // ``_activeAutomationJobId`` and let the user open it later
        // from the history.
        const data = event_data as any;
        this._activeAutomationJobId = job_id;
        const raw = getState().settings?.automation_auto_open_view;
        const autoOpen = raw === true || raw === "true";
        if (!autoOpen) {
          // Silent tracking: the automation panel badge / history will
          // be updated via the automation_job_update event. The user
          // can still click an execution row to open the sub-agent
          // view manually (that path is not gated).
          return;
        }
        this.automationPanel.hide();
        clearMessages();
        setSessionId("");
        addUserMessage(data.prompt || data.name || "");
        const tc: any = {
          id: job_id,
          name: "agent",
          params: { agent_name: data.name || t("app.automationDefaultName") },
          status: "running",
          subAgentMessages: [],
          content: "",
        };
        const origClose = (window as any).__closeSubAgentView;
        (window as any).__closeSubAgentView = () => {
          setSubAgentView(null);
          clearMessages();
          this._activeAutomationJobId = "";
          (window as any).__isAutomationView = false;
          (window as any).__closeSubAgentView = origClose;
          this.automationPanel.toggleAutomationView();
        };
        (window as any).__isAutomationView = true;
        setSubAgentView(tc);
        return;
      }

      // Ignore events for jobs we're not currently viewing
      if (this._activeAutomationJobId !== job_id) return;
      const view = getState().subAgentView;
      if (!view || view.id !== job_id) return;

      if (event_type === "text_delta") {
        (view as any).content = ((view as any).content || "") + ((event_data as any).text || "");
        setSubAgentView({ ...view });
      } else if (event_type === "thinking_delta") {
        // Ignore thinking deltas in the automation view
      } else if (event_type === "tool_progress" || event_type === "tool_result") {
        const ed = event_data as any;
        if (ed.sub_agent_messages && ed.sub_agent_messages.length > 0) {
          view.subAgentMessages = restoreMessages(ed.sub_agent_messages);
          setSubAgentView({ ...view });
        }
      } else if (event_type === "finish") {
        (view as any).status = "completed";
        (view as any).content = (view as any).content || ((event_data as any).result || "");
        setSubAgentView({ ...view });
      }
    });

    // Mode change callbacks — refresh content, close session sidebar, animate welcome
    const onAnyModeChange = (): void => {
      // Hide automation view when switching modes
      this.automationPanel.hide();
      this.exitTempChat();
      // Do NOT call resetChat() here — it destroys the running session's
      // UI state (sessionId, running flag, messages).  The backend sends
      // session_ready after open_workspace / close_workspace completes,
      // which correctly loads the new session's state.  The old session's
      // snapshot stays intact in the session store so the user can switch
      // back without losing context.
      this.closeSessionInnerSidebar();
      // Nuke EVERY content-area artifact so widgets from the previous mode
      // do not bleed into the new one (sub-agent view, tool detail panel,
      // mention dropdown, search overlay, automation flags, etc.).
      this.cleanupContentArea({ keepAutomationFlag: false });
      this.chat.render();
      // 在 updatePlaceholder 之前标记动画进行中，防止 updateWelcomeTitle 预置文字
      this._welcomeTitleAnimating = true;
      this.updatePlaceholder();
      this.animateWelcomeTitle(getState().workspaceMode);
    };
    this.workspace.onModeChange = onAnyModeChange;
    this.sessionInner = new SessionInner();
    this.chat.onViewChanges = (path: string) => {
      const st = getState();
      const artifact = st.artifacts.find(a => a.path === path);
      this.sessionInner.showReviewTab(path, artifact || undefined);
    };

    (window as any).__sessionInner = this.sessionInner;
    streamInit(this.chat, this.tools, this.permissions, this.settings);
    this.bindGlobalLinkInterceptor();
    this.bindInput();
    this.updatePlaceholder();
    this.bindToolbarButtons();
    this.bindSummaryPanel();
    this.bindWindowControls();
    this.bindSearchOverlay();
    this.initKeybindActions();
    this.bindKeyboardShortcuts();
    this.applyShortcutHints();
    this.initTheme();
    this.bindResponsiveSidebar();

    // Mirror sidebar collapse state to body so sibling elements can style
    const appEl = document.getElementById("app");
    if (appEl) {
      const observer = new MutationObserver(() => {
        document.body.classList.toggle("sidebar-collapsed", appEl.classList.contains("sidebar-collapsed"));
      });
      observer.observe(appEl, { attributes: true, attributeFilter: ["class"] });
      // Sync initial state
      document.body.classList.toggle("sidebar-collapsed", appEl.classList.contains("sidebar-collapsed"));
    }

    // Forward locale to tray
    let lastTrayLocale = "";
    onLocaleChange(() => {
      if (!this.summaryPanel.classList.contains("hidden")) this.renderSummaryPanel();
    });

    subscribe(() => {
      const locale = getState().settings.language as string;
      if (locale && locale !== lastTrayLocale) {
        lastTrayLocale = locale;
        if (window.electronAPI) {
          window.electronAPI.trayLocaleUpdate(locale);
        }
      }
    });

    // Forward resolved theme to tray popup
    let lastTrayThemePref = "";
    onLocaleChange(() => {
      if (!this.summaryPanel.classList.contains("hidden")) this.renderSummaryPanel();
    });

    subscribe(() => {
      const pref = getState().themePreference;
      if (pref && pref !== lastTrayThemePref) {
        lastTrayThemePref = pref;
        if (window.electronAPI) {
          window.electronAPI.trayThemeUpdate(pref);
        }
      }
    });

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
        send({ type: "list_all_sessions" });
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
    this.btnSend.disabled = !hasText && !this.hasModeChip() && getState().attachments.length === 0;
    });

    // Re-fetch models when backend or base_url changes
    let lastBackend = getState().settings.backend;
    let lastBaseUrl = getState().settings.base_url;
    onLocaleChange(() => {
      if (!this.summaryPanel.classList.contains("hidden")) this.renderSummaryPanel();
    });

    subscribe(() => {
      const s = getState();
      if (s.settings.backend !== lastBackend || s.settings.base_url !== lastBaseUrl) {
        lastBackend = s.settings.backend;
        lastBaseUrl = s.settings.base_url;
        if (s.connected) {
          this.fetchModels();
        }
      }
    });

    // Listen for session switch from tray popup
    if (window.electronAPI) {
      window.electronAPI.onSwitchSession((sessionId: string) => {
        const st = getState();
        if (!sessionId || sessionId === st.sessionId) return;
        // The tray popup maintains a dual cache (normal + iwork); search both.
        const tray = getTraySessions();
        const entry =
          tray.iwork.find((s: any) => s.session_id === sessionId) ||
          tray.normal.find((s: any) => s.session_id === sessionId);
        const isIworkSession = tray.iwork.some((s: any) => s.session_id === sessionId);
        const wsPath: string =
          (entry && (entry.metadata?.workspace || (entry.metadata as any)?.workspace_path)) || "";
        const requestId = crypto.randomUUID();

        // Stash pending resume BEFORE enter() so enterWorkspaceMode()
        // can detect it and skip its auto-activation of first workspace.
        if (isIworkSession && wsPath) {
          (window as any).__pendingTrayResume = { sessionId, requestId };
        }

        if (isIworkSession && st.workspaceMode !== "iwork") {
          // Temporarily replace onModeChange to avoid resetChat() clearing the session being loaded
          const orig = this.workspace.onModeChange;
          this.workspace.onModeChange = () => {
            this.closeSessionInnerSidebar();
            this.cleanupContentArea({ keepAutomationFlag: false });
            this.chat.render();
            this.workspace.onModeChange = orig;
          };
          this.workspace.enter();
          // Pre-expand the target workspace so the tree shows its sessions
          // as soon as workspace_opened renders it.
          if (wsPath) this.workspace.ensureExpanded(wsPath);
        } else if (!isIworkSession && st.workspaceMode === "iwork") {
          this.workspace.forceExit();
        } else {
          // Same mode: clear residual widgets from the previous session
          // (sub-agent view, tool detail panel, mention dropdown, etc.) so
          // the user does not see stale content flash as the new session loads.
          this.cleanupContentArea({ keepAutomationFlag: false });
        }
        setRequestedSessionId(sessionId, requestId);
        if (wsPath && wsPath !== st.activeWorkspace) {
          setSessionId("");
          send({ type: "open_workspace", path: wsPath, request_id: requestId });
        } else {
          setSessionId(sessionId);
          send({ type: "resume", session_id: sessionId, request_id: requestId });
        }
      });
    }

    // Sync inputMode state to DOM attribute for CSS selector
    let prevInputMode = "";
    onLocaleChange(() => {
      if (!this.summaryPanel.classList.contains("hidden")) this.renderSummaryPanel();
    });

    subscribe(() => {
      const s = getState();
      if (s.inputMode !== prevInputMode) {
        prevInputMode = s.inputMode;
        const el = document.getElementById("input-area");
        if (el) {
          if (s.inputMode) {
            el.setAttribute("data-input-mode", s.inputMode);
          } else {
            el.removeAttribute("data-input-mode");
          }
        }
      }
    });

    // Re-render everything when locale changes
    onLocaleChange(() => {
      applyI18n();
      this.chat.render();
      this.session.render();
      this.tools.render();
      this.notifications.render();
      this.sessionInner.renderForce();
      this.settings.renderAll();
      this.automation.render();
      this.updateStats();
      this.bindInputModelSelector();
    });

    // Apply startup mode only on initial connection + config_data received.
    // Wait until startup_session_mode appears in settings (set by config_data
    // handler in stream.ts) — checking Object.keys won't work because
    // initTheme() populates settings.theme before the server responds.
    let _startupModeApplied = false;
    onLocaleChange(() => {
      if (!this.summaryPanel.classList.contains("hidden")) this.renderSummaryPanel();
    });

    subscribe(() => {
      const st = getState();
      if (!st.connected) return;
      if (_startupModeApplied) return;
      if (!("startup_session_mode" in st.settings)) return;
      _startupModeApplied = true;
      const mode = st.settings.startup_session_mode as string;
      if (mode === "iwork") {
        this.workspace.enter();
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

    // Session menu toggle — collapse main sidebar when session sidebar opens
    document.getElementById("btn-session-menu")?.addEventListener("click", () => {
      const panel = document.getElementById("session-inner-sidebar");
      const app = document.getElementById("app");
      const mainBody = document.getElementById("main-body");
      if (!panel || !app || !mainBody) return;
      if (panel.classList.contains("hidden")) {
        this.sessionInner.restoreWidth();
        panel.classList.remove("hidden");
        mainBody.classList.remove("sidebar-hidden");
        app.classList.add("sidebar-collapsed");
        this.sessionInner.renderForce();
      } else {
        // Closing: hide the panel AND tear down the dynamic tabs so the
        // next open starts from the default "info" tab.  Without this,
        // re-opening the sidebar would resurrect terminals/editors from
        // the previous session — they keep running in the background
        // burning CPU and the user sees stale output.
        this.sessionInner.saveWidth();
        panel.classList.add("hidden");
        mainBody.classList.add("sidebar-hidden");
        this.sessionInner.resetToDefaultTabs();
      }
    });

    this.renderSlashDropdown();
    applyI18n();

    // Re-render slash dropdown when backend commands arrive
    window.addEventListener("slash-commands-updated", () => {
      this.renderSlashDropdown();
    });

    // Child window mode — detect ?child=VIEW_NAME from URL
    const params = new URLSearchParams(window.location.search);
    const childView = params.get("child");
    if (childView) {
      this._isChild = true;
      this._childView = childView;
      this.initChildMode(childView, params.get("label") || childView);
    }
  }

  private initChildMode(view: string, label: string): void {
    document.title = "ESD";
    document.body.classList.add("child-mode");

    const inputArea = document.getElementById("input-area");
    if (inputArea) inputArea.style.display = "none";
    const chatView = document.getElementById("chat-view");
    if (chatView) chatView.style.display = "none";
    const searchView = document.getElementById("search-view");
    if (searchView) searchView.style.display = "none";
    const agentsView = document.getElementById("agents-view");
    if (agentsView) agentsView.style.display = "none";

    // Add brand label and tabs container into header bar
    const header = document.getElementById("header-bar");
    if (header) {
      const brand = document.createElement("span");
      brand.id = "child-header-brand";
      brand.className = "header-brand";
      brand.textContent = "ESD";

      const tabsEl = document.createElement("div");
      tabsEl.id = "child-header-tabs";
      tabsEl.className = "header-tabs";

      const headerLeft = header.querySelector(".header-left");
      if (headerLeft) {
        headerLeft.after(brand);
        brand.after(tabsEl);
      } else {
        header.appendChild(brand);
        header.appendChild(tabsEl);
      }
    }

    this._tabs = [];
    this._activeTabIndex = -1;
    this.addTab(view, label);

    if (window.electronAPI) {
      window.electronAPI.onChildAddTab((v: string, l: string) => {
        this.addTab(v, l);
      });
    }
  }

  private addTab(view: string, label: string): void {
    const existing = this._tabs.findIndex(t => t.view === view);
    if (existing >= 0) {
      this.switchTab(existing);
      return;
    }
    this._tabs.push({ view, label });
    this.switchTab(this._tabs.length - 1);
  }

  private switchTab(index: number): void {
    if (index < 0 || index >= this._tabs.length) return;
    this._activeTabIndex = index;
    this.renderTabBar();
    this.renderTabContent(this._tabs[index]);
  }

  private closeTab(index: number): void {
    const removed = this._tabs[index];
    if (removed?._nebulaCleanup) {
      removed._nebulaCleanup();
    }
    this._tabs.splice(index, 1);
    if (this._tabs.length === 0) {
      window.electronAPI?.windowClose();
      return;
    }
    if (this._activeTabIndex >= this._tabs.length) {
      this._activeTabIndex = this._tabs.length - 1;
    } else if (index < this._activeTabIndex) {
      this._activeTabIndex--;
    }
    this.renderTabBar();
    this.renderTabContent(this._tabs[this._activeTabIndex]);
  }

  private renderTabBar(): void {
    const tabsEl = document.getElementById("child-header-tabs");
    if (!tabsEl) return;
    tabsEl.innerHTML = this._tabs.map((t, i) => {
      const displayLabel = t.title || t.label;
      return `<button class="tab${i === this._activeTabIndex ? " active" : ""}" data-index="${i}" draggable="true">
        <span class="tab-label">${this.esc(displayLabel)}</span>
        <span class="tab-close"><svg viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none"/></svg></span>
      </button>`;
    }).join("");

    let dragSrcIdx: number | null = null;
    tabsEl.querySelectorAll("button[data-index]").forEach(btn => {
      const idx = parseInt(btn.getAttribute("data-index")!, 10);

      // Click to switch
      btn.addEventListener("click", (e) => {
        if ((e.target as HTMLElement).closest(".tab-close")) return;
        this.switchTab(idx);
      });

      // Middle-click to close
      btn.addEventListener("auxclick", (e) => {
        const ev = e as MouseEvent;
        if (ev.button === 1) {
          ev.preventDefault();
          this.closeTab(idx);
        }
      });

      // Close button
      const closeBtn = btn.querySelector(".tab-close");
      if (closeBtn) {
        closeBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          this.closeTab(idx);
        });
      }

      // Drag-and-drop reorder
      btn.addEventListener("dragstart", (e) => {
        const ev = e as DragEvent;
        dragSrcIdx = idx;
        ev.dataTransfer?.setData("text/plain", String(idx));
        btn.classList.add("dragging");
      });
      btn.addEventListener("dragend", () => {
        btn.classList.remove("dragging");
        dragSrcIdx = null;
        tabsEl.querySelectorAll(".tab.drop-target").forEach(el => el.classList.remove("drop-target"));
      });
      btn.addEventListener("dragover", (e) => {
        e.preventDefault();
        if (dragSrcIdx !== null && dragSrcIdx !== idx) {
          tabsEl.querySelectorAll(".tab.drop-target").forEach(el => el.classList.remove("drop-target"));
          btn.classList.add("drop-target");
        }
      });
      btn.addEventListener("dragleave", () => {
        btn.classList.remove("drop-target");
      });
      btn.addEventListener("drop", (e) => {
        e.preventDefault();
        btn.classList.remove("drop-target");
        if (dragSrcIdx !== null && dragSrcIdx !== idx) {
          const [moved] = this._tabs.splice(dragSrcIdx, 1);
          this._tabs.splice(idx, 0, moved);
          if (this._activeTabIndex === dragSrcIdx) {
            this._activeTabIndex = idx;
          } else if (dragSrcIdx < idx && this._activeTabIndex > dragSrcIdx && this._activeTabIndex <= idx) {
            this._activeTabIndex--;
          } else if (dragSrcIdx > idx && this._activeTabIndex >= idx && this._activeTabIndex < dragSrcIdx) {
            this._activeTabIndex++;
          }
          this.renderTabBar();
          this.renderTabContent(this._tabs[this._activeTabIndex]);
        }
        dragSrcIdx = null;
      });
    });
  }

  private renderTabContent(tab: ChildTab): void {
    const childViewEl = document.getElementById("child-view");
    if (!childViewEl) return;
    childViewEl.classList.remove("hidden");

    if (tab.view.startsWith("http://") || tab.view.startsWith("https://") || tab.view === "about:blank") {
      const startUrl = tab.view === "about:blank" ? "" : tab.view;
      childViewEl.innerHTML = `
        <div class="child-nav-bar">
          <button class="child-nav-btn" data-nav="back"><svg viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/></svg></button>
          <button class="child-nav-btn" data-nav="forward"><svg viewBox="0 0 24 24"><path d="M9 18l6-6-6-6" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/></svg></button>
          <button class="child-nav-btn" data-nav="reload"><svg viewBox="0 0 24 24"><path d="M23 4v6h-6M1 20v-6h6" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/></svg></button>
          <input type="text" class="child-url-input" value="${startUrl}" placeholder="https://..." spellcheck="false" />
        </div>
        <webview class="child-webview" src="${startUrl || "about:blank"}" partition="encre-browser"></webview>`;
      const wv = childViewEl.querySelector("webview") as any;
      if (wv) {
        tab.webview = wv;
        // Track page title
        wv.addEventListener("page-title-updated", (e: any) => {
          tab.title = e.title;
          this.renderTabBar();
        });
        // Intercept new windows (popups, target=_blank) — open as new tab
        wv.addEventListener("new-window", (e: any) => {
          e.preventDefault();
          const newUrl = e.url || "";
          console.log("[webview] new-window:", newUrl);
          if (!newUrl || !/^https?:\/\//i.test(newUrl)) return;
          const behavior = (getState().settings.default_link_behavior as string) || "system";
          if (behavior === "in_app") {
            this.addTab(newUrl, newUrl);
          } else {
            const api = (window as any).electronAPI;
            if (api?.openExternal) {
              api.openExternal(newUrl);
            } else {
              window.open(newUrl, "_blank");
            }
          }
        });
        // will-navigate: user-initiated (URL bar/back/forward) = same tab; link click = new tab
        let explicitNav = true;
        wv.addEventListener("will-navigate", (e: any) => {
          console.log("[webview] will-navigate:", e.url, "explicitNav:", explicitNav, "isMainFrame:", e.isMainFrame);
          if (e.isMainFrame !== false) {
            if (!explicitNav && e.url && /^https?:\/\//i.test(e.url)) {
              console.log("[webview] → intercept, open new tab:", e.url);
              e.preventDefault();
              const behavior = (getState().settings.default_link_behavior as string) || "system";
              if (behavior === "in_app") {
                this.addTab(e.url, e.url);
              } else {
                const api = (window as any).electronAPI;
                if (api?.openExternal) {
                  api.openExternal(e.url);
                } else {
                  window.open(e.url, "_blank");
                }
              }
              return;
            }
            explicitNav = false;
          }
        });
        // Force 80% zoom on each navigation
        const applyZoom = () => {
          try { wv.setZoomFactor(1); } catch {}
        };
        wv.addEventListener("did-finish-load", applyZoom);
        wv.addEventListener("did-navigate", applyZoom);
        // Also set zoom immediately if already loaded
        applyZoom();
        // Nav buttons
        childViewEl.querySelectorAll("[data-nav]").forEach(btn => {
          btn.addEventListener("click", () => {
            if (!wv) return;
            const action = btn.getAttribute("data-nav");
            if (action === "back") { explicitNav = true; wv.goBack(); }
            else if (action === "forward") { explicitNav = true; wv.goForward(); }
            else if (action === "reload") wv.reload();
          });
        });
        // URL input in nav bar
        const urlInput = childViewEl.querySelector(".child-url-input") as HTMLInputElement;
        if (urlInput) {
          const navigate = () => {
            let url = urlInput.value.trim();
            if (!url) return;
            if (!/^https?:\/\//i.test(url)) {
              url = "https://" + url;
            }
            explicitNav = true;
            wv.src = url;
          };
          urlInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") navigate();
          });
          // Sync URL input with webview navigation
          if (wv) {
            wv.addEventListener("did-navigate", (e: any) => {
              urlInput.value = e.url;
            });
            wv.addEventListener("did-navigate-in-page", (e: any) => {
              urlInput.value = e.url;
            });
          }
        }
      }
    } else if (tab.view === "license") {
      childViewEl.innerHTML = `<div class="child-view-content"><pre class="child-raw-text">Loading...</pre></div>`;
      if (window.electronAPI) {
        window.electronAPI.getLicenseContent().then((content: string) => {
          const pre = childViewEl.querySelector(".child-raw-text");
          if (pre) pre.textContent = content;
        });
      }
    } else if (tab.view === "privacy" || tab.view === "terms" || tab.view === "thanks" || tab.view === "data-rules" || tab.view === "minors") {
      childViewEl.innerHTML = `
        <div class="child-doc-container">
          <div class="child-doc-toolbar">
            <div class="settings-dropdown-wrap" id="child-region-wrap">
              <button class="settings-dropdown-trigger" id="child-region-trigger" type="button">
                <span>${t("settings.aboutRegionIntl")}</span>
                <i data-lucide="chevron-down" class="lucide settings-dropdown-chevron"></i>
              </button>
              <div class="settings-dropdown" id="child-region-dropdown">
                <div class="settings-dropdown-item selected" data-value="intl">${t("settings.aboutRegionIntl")}</div>
                <div class="settings-dropdown-item" data-value="cn">${t("settings.aboutRegionCn")}</div>
              </div>
            </div>
          </div>
          <div class="child-view-content"><div class="child-view-body msg-text"><p>Loading...</p></div></div>
        </div>`;

      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: childViewEl });
      }

      const loadDoc = (region: string) => {
        const body = childViewEl.querySelector(".child-view-body");
        if (body) body.innerHTML = "<p>Loading...</p>";
        if (window.electronAPI) {
          window.electronAPI.getDocumentContent(tab.view, region).then((content: string) => {
            const bodyEl = childViewEl.querySelector(".child-view-body");
            if (bodyEl) bodyEl.innerHTML = renderMarkdown(content);
          });
        }
      };

      this.bindChildRegionDropdown("child-region", (val) => {
        this._region = val;
        loadDoc(val);
      });

      loadDoc(this._region);
    } else if (tab.view === "easter-egg") {
      childViewEl.innerHTML = `<div class="easter-egg-container" style="position:absolute;inset:0;overflow:hidden;background:#000"></div>`;
      const container = childViewEl.querySelector(".easter-egg-container") as HTMLElement;
      if (container) {
        tab._nebulaCleanup = mountNebula(container);
      }
    } else if (tab.view === "logs") {
      childViewEl.innerHTML = `
        <div id="settings-content-wrap">
          <div class="settings-card" style="padding:0">
            <div class="model-table" id="logger-table">
              <div class="model-table-header">
                <div class="model-table-cell model-cell-provider" style="flex:1">${t("settings.aboutLogContent") || "Content"}</div>
                <div class="model-table-cell model-cell-actions" style="width:96px;justify-content:flex-end;gap:4px">
                  <button class="btn-icon" id="logger-copy-btn" title="Copy all"><i data-lucide="clipboard-copy" class="lucide"></i></button>
                  <button class="btn-icon" id="logger-open-btn" title="Open folder"><i data-lucide="folder-open" class="lucide"></i></button>
                </div>
              </div>
              <div class="logger-scroll" id="logger-scroll">
                <div id="logger-rows"></div>
              </div>
            </div>
          </div>
        </div>`;
      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: childViewEl });
      }
      const api = window.electronAPI;
      if (api) {
        api.getDiagnostics().then(diag => {
          const rowsEl = document.getElementById("logger-rows");
          const copyBtn = document.getElementById("logger-copy-btn");
          const openBtn = document.getElementById("logger-open-btn");
          if (!rowsEl) return;
          // Render log lines as plain model-table rows, exactly like the
          // model list: one row per log line, content fills the cell.
          rowsEl.innerHTML = diag.recentLogs.length === 0
            ? `<div class="model-table-row"><div class="model-table-cell model-cell-provider" style="flex:1;color:var(--text-muted)">(no logs)</div><div class="model-table-cell model-cell-actions" style="width:96px"></div></div>`
            : diag.recentLogs.map(line =>
                `<div class="model-table-row">
                  <div class="model-table-cell model-cell-provider" style="flex:1;font-family:var(--font-mono);font-size:12px;white-space:pre-wrap;word-break:break-all;color:var(--text-secondary)">${this.esc(line)}</div>
                  <div class="model-table-cell model-cell-actions" style="width:96px"></div>
                </div>`
              ).join("");
          if (copyBtn) {
            copyBtn.addEventListener("click", () => {
              navigator.clipboard.writeText(diag.recentLogs.join("\n")).catch(() => {});
            });
          }
          if (openBtn) {
            openBtn.addEventListener("click", () => {
              api?.openLogs();
            });
          }
        });
      }
    } else if (tab.view.startsWith("mailto:")) {
      window.location.href = tab.view;
    } else {
      childViewEl.innerHTML = `<div class="si-panel-empty" style="flex:1;gap:14px">
        <i data-lucide="file-question" class="lucide" style="width:32px;height:32px;color:var(--text-muted)"></i>
        <div class="si-panel-empty-title">${this.esc(tab.label)}</div>
        <div class="si-panel-empty-sub" style="font-size:12px;color:var(--text-muted)">Coming soon</div>
      </div>`;
      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: childViewEl });
      }
    }
  }

  private bindChildRegionDropdown(id: string, onChange: (val: string) => void): void {
    const wrap = document.getElementById(`${id}-wrap`);
    const trigger = document.getElementById(`${id}-trigger`);
    const dropdown = document.getElementById(`${id}-dropdown`);
    if (!wrap || !trigger || !dropdown) return;

    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpen = dropdown.classList.contains("open");
      document.querySelectorAll(".settings-dropdown.open").forEach((dd) => dd.classList.remove("open"));
      if (!isOpen) dropdown.classList.add("open");
    });

    dropdown.querySelectorAll(".settings-dropdown-item").forEach((item) => {
      item.addEventListener("click", (e) => {
        e.stopPropagation();
        const val = (item as HTMLElement).getAttribute("data-value") || "";
        const label = (item as HTMLElement).textContent || "";
        trigger.querySelector("span")!.textContent = label;
        dropdown.classList.remove("open");
        dropdown.querySelectorAll(".settings-dropdown-item").forEach((el) => el.classList.remove("selected"));
        (item as HTMLElement).classList.add("selected");
        onChange(val);
      });
    });

    document.addEventListener("click", (e) => {
      if (!wrap.contains(e.target as Node)) {
        dropdown.classList.remove("open");
      }
    });
  }

  private updateStats(): void {
    if (!this.tokenCountEl) return;
    const s = getState();
    let totalIn = 0;
    let totalOut = 0;
    for (const msg of s.messages) {
      if (msg.role === "assistant" && msg.tokenUsage) {
        totalIn += msg.tokenUsage.input_tokens;
        totalOut += msg.tokenUsage.output_tokens;
      }
    }
    const totalAll = totalIn + totalOut;
    if (s.telemetry) {
      this.tokenCountEl.textContent = t("app.toolsTokens", { count: s.telemetry.total_tool_calls, tokens: this.fmtTokens(totalAll) });
      this.tokenCountEl.title =
        t("app.inputOutput", { input: this.fmtTokens(totalIn), output: this.fmtTokens(totalOut) }) +
        ` | ${t("app.turns")}: ${s.telemetry.total_turns} | ` +
        `${t("app.duration")}: ${s.telemetry.session_duration_s.toFixed(0)}s`;
    } else if (totalAll > 0) {
      this.tokenCountEl.textContent = `${this.fmtTokens(totalAll)} ${t("app.tokens")}`;
      this.tokenCountEl.title = t("app.inputOutput", { input: this.fmtTokens(totalIn), output: this.fmtTokens(totalOut) });
    } else {
      this.tokenCountEl.textContent = "";
      this.tokenCountEl.title = "";
    }
  }

  private fmtTokens(n: number): string {
    if (n >= 1000) return (n / 1000).toFixed(1) + "k";
    return String(n);
  }

  private updateSessionBarName(): void {
    const s = getState();
    const bar = document.getElementById("session-bar");
    const nameEl = document.getElementById("session-bar-name") as HTMLElement | null;

    if (!bar) return;

    const hasMessages = s.messages.length > 0;
    bar.style.display = hasMessages ? "" : "none";

    if (!nameEl) return;
    const isAutomationView = !!(window as any).__isAutomationView;
    const rootLabel = isAutomationView
      ? t("automation.title")
      : s.tempChat
      ? t("session.tempChatActive")
      : (() => {
          const entry = s.sessionsList.find((x) => x.session_id === s.sessionId);
          return s.sessionId
            ? (entry?.name || entry?.preview || s.sessionId.slice(0, 8))
            : t("session.newSession");
        })();
    const inputArea = document.getElementById("input-area");
    const sessionMenu = document.getElementById("btn-session-menu");
    const mainContent = document.getElementById("main-content");
    const breadcrumb = s.subAgentBreadcrumb;
    const _truncate = (s: string, max = 18) => s.length > max ? s.slice(0, max) + "…" : s;
    const isSubAgentView = !!(s.subAgentView || breadcrumb.length > 0);
    if (isSubAgentView) {
      // Build breadcrumb HTML: root / sub1 / sub2 / ... / current
      let crumbsHtml = `<button class="session-crumb session-crumb-root" data-crumb-index="-1" type="button" title="${this.esc(rootLabel)}">${this.esc(_truncate(rootLabel))}</button>`;
      for (let i = 0; i < breadcrumb.length; i++) {
        const entry = breadcrumb[i];
        const isLast = i === breadcrumb.length - 1;
        const label = formatAgentLabel(entry.name);
        crumbsHtml += `<span class="session-crumb-sep">/</span>`;
        if (isLast && !s.subAgentView) {
          // Last crumb and no active sub-agent view = currently viewing this level
          crumbsHtml += `<span class="session-crumb-current" title="${this.esc(label)}">${this.esc(_truncate(label))}</span>`;
        } else {
          crumbsHtml += `<button class="session-crumb" data-crumb-index="${i}" type="button" title="${this.esc(label)}">${this.esc(_truncate(label))}</button>`;
        }
      }
      // If a sub-agent view is active, show the current agent name
      if (s.subAgentView) {
        const rawName = String(
          s.subAgentView.params.agent_name || s.subAgentView.params.name || s.subAgentView.params.mode || "agent"
        );
        crumbsHtml += `<span class="session-crumb-sep">/</span>`;
        const curLabel = formatAgentLabel(rawName);
        crumbsHtml += `<span class="session-crumb-current" title="${this.esc(curLabel)}">${this.esc(_truncate(curLabel))}</span>`;
      }
      nameEl.innerHTML = crumbsHtml;
      // Bind click handlers for each breadcrumb level
      nameEl.querySelectorAll("[data-crumb-index]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const idx = parseInt((btn as HTMLElement).dataset.crumbIndex || "-1", 10);
          if (idx < 0) {
            (window as any).__closeSubAgentView?.();
          } else {
            (window as any).__navigateToBreadcrumb?.(idx);
          }
        });
      });
      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: nameEl });
      }
      // Hide input area and session menu in sub-agent view
      if (inputArea) inputArea.style.display = "none";
      if (sessionMenu) sessionMenu.style.display = "none";
      if (mainContent) mainContent.classList.add("sub-agent-active");
      return;
    }
    // Restore input area and session menu when leaving sub-agent view
    // Skip in child mode (ESD): child window has its own tabs and no chat input.
    const isChildMode = document.body.classList.contains("child-mode");
    if (!isChildMode) {
      if (inputArea) inputArea.style.display = "";
      if (sessionMenu) sessionMenu.style.display = "";
    }
    if (mainContent) mainContent.classList.remove("sub-agent-active");
    nameEl.textContent = rootLabel;
  }

  private _renderQueueCard(): void {
    const s = getState();
    const card = document.getElementById("queue-card");
    const body = document.getElementById("queue-card-body");
    const statusBar = document.getElementById("chat-status-bar");
    if (!card || !body) return;
    if (s.pendingQueueCount === 0 || s.queuedPrompts.length === 0) {
      card.classList.add("hidden");
      if (statusBar) statusBar.style.maxWidth = "";
      return;
    }
    card.classList.remove("hidden");
    if (statusBar) statusBar.style.maxWidth = "calc(var(--input-max-w) - 100px)";
    body.innerHTML = s.queuedPrompts.map((p, i) =>
      `<div class="queue-item">
        <span class="queue-item-text">${this.esc(p.text)}</span>
        <button class="queue-item-remove" data-queue-index="${i}" title="${t("dialog.cancel")}">
          <i data-lucide="x" class="lucide"></i>
        </button>
      </div>`
    ).join("");
    if ((window as any).lucide) {
      (window as any).lucide.createIcons(body);
    }
    body.querySelectorAll(".queue-item-remove").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const idx = parseInt((btn as HTMLElement).dataset.queueIndex || "0", 10);
        removeQueuedPromptAt(idx);
      });
    });
  }

  async start(): Promise<void> {
    this.splash.show();
    const _splashStart = performance.now();

    // Yield to browser so the splash actually paints before we block on I/O
    await new Promise<void>(r => requestAnimationFrame(() => r()));

    await connect(handleEvent);
    setOnTranscription((text) => {
      if (!text) return;
      this.input.focus();
      const start = this.input.selectionStart ?? this.input.value.length;
      const end = this.input.selectionEnd ?? start;
      this.input.value =
        this.input.value.substring(0, start) + text + this.input.value.substring(end);
      const newPos = start + text.length;
      this.input.selectionStart = this.input.selectionEnd = newPos;
      this.resizeInput();
      this.updateSendButton();
    });
    if (getState().connected) {
      // Fetch available models from the provider and server config
      this.fetchModels();
      send({ type: "get_config" });
      send({ type: "list_workspaces" });
    }

    // Let data responses arrive, then ensure splash is visible ≥ 1 s
    await new Promise<void>(r => requestAnimationFrame(() => r()));
    const _elapsed = performance.now() - _splashStart;
    if (_elapsed < 1000) {
      await new Promise(r => setTimeout(r, 1000 - _elapsed));
    }
    this.splash.hide();
  }

  private bindInput(): void {
    this.btnSend.addEventListener("click", () => this.submit());
    this.btnStop.addEventListener("click", () => this.cancel());
    this.btnVoice.addEventListener("click", () => this.toggleVoice());

    this.input.addEventListener("keydown", (e) => {
      const sendMode = (getState().settings.shortcut_send_mode as string) || "enter";
      const isCtrlEnter = sendMode === "ctrl_enter";
      const isSendKey = isCtrlEnter
        ? e.key === "Enter" && (e.ctrlKey || e.metaKey)
        : e.key === "Enter" && !e.shiftKey;

      if (isSendKey) {
        e.preventDefault();
        const text = this.getPlainText();

        // Don't re-activate slash command when a mode chip is already present
        if (!this.hasModeChip()) {
          // Check exact slash command match first (e.g. /plan → activate mode)
          const parsed = parseSlashInput(text);
          if (parsed && parsed.exact) {
            this.activateSlashCommand(parsed.command);
            return;
          }
        }

        // If slash menu is active, check for matched command first
        if (this._slashActive) {
          const dd = document.getElementById("mention-dropdown");
          const bm = document.getElementById("btn-mention");
          const matched = dd?.querySelector(".mention-match") as HTMLElement | null;
          if (matched) {
            const action = matched.getAttribute("data-action");
            const cmd = SLASH_COMMANDS.find(c => c.id === action || c.name === action);
            if (cmd) {
              this.activateSlashCommand(cmd);
              return;
            }
          }
          dd?.classList.add("hidden");
          bm?.classList.remove("active");
          this._slashActive = false;
          this.input.innerHTML = "";
          this.updatePlaceholder();
          this.resizeInput();
          this.updateSendButton();
          return;
        }

        this.submit();
      }
      if (e.key === "Escape") {
        if (this._slashActive) {
          this._slashActive = false;
          this.input.innerHTML = "";
          const dd = document.getElementById("mention-dropdown");
          const bm = document.getElementById("btn-mention");
          dd?.classList.add("hidden");
          bm?.classList.remove("active");
          this.updatePlaceholder();
          this.resizeInput();
          this.updateSendButton();
          return;
        }
        this.cancel();
      }
    });

    this.input.addEventListener("focus", () => {
      const chip = this.input.querySelector('.mode-chip[data-mode]');
      if (!chip) return;
      const sel = window.getSelection();
      if (!sel || !sel.rangeCount) return;
      const range = sel.getRangeAt(0);
      const fakeEls = this.input.querySelectorAll('[contenteditable="false"]');
      const lastFake = fakeEls[fakeEls.length - 1];
      if (!lastFake) return;
      const afterLast = new Range();
      afterLast.setStartAfter(lastFake);
      afterLast.collapse(true);
      if (range.compareBoundaryPoints(Range.END_TO_END, afterLast) < 0) {
        sel.removeAllRanges();
        sel.addRange(afterLast);
      }
    });

    this.input.addEventListener("input", () => {
      if (this.skipNextInput) {
        this.skipNextInput = false;
        return;
      }
      this.detectSlashCommand();
      this.handleManualSlashCommand();
      this.updateChipState();
      this.resizeInput();
      this.updatePlaceholder();
      this.updateSendButton();
    });

    // Watch for mode-chip removal so we can clean up state when user deletes it
    const chipObserver = new MutationObserver(() => {
      const mode = this.getCurrentMode();
      if (this._currentChipMode && !mode) {
        this._currentChipMode = "";
        this.updateChipState();
        this.updatePlaceholder();
        this.updateSendButton();
      } else if (mode) {
        this._currentChipMode = mode;
      }
    });
    chipObserver.observe(this.input, { childList: true, subtree: true });
  }

  private detectSlashCommand(): void {
    const text = this.getPlainText();
    const mentionDropdown = document.getElementById("mention-dropdown");
    const btnMention = document.getElementById("btn-mention");
    if (!mentionDropdown || !btnMention) return;

    const mainPage = mentionDropdown.querySelector('[data-page="main"]');
    const slashPage = mentionDropdown.querySelector('[data-page="slash"]');

    // Clear all match highlights
    mentionDropdown.querySelectorAll(".mention-match").forEach(el => el.classList.remove("mention-match"));

    if (text.startsWith("/") && !this.hasModeChip()) {
      if (mentionDropdown.classList.contains("hidden")) {
        mentionDropdown.classList.remove("hidden");
        btnMention.classList.add("active");
      }
      this._slashActive = true;

      // Slash mode → always show only slash sub-page, never Files/Folder
      mainPage?.classList.add("hidden");
      slashPage?.classList.remove("hidden");

      // Highlight matching slash commands
      const query = text.slice(1).toLowerCase();
      if (query) {
        mentionDropdown.querySelectorAll('[data-slash]').forEach(el => {
          const cmd = el.getAttribute("data-slash") || "";
          if (cmd.startsWith(query)) {
            el.classList.add("mention-match");
          }
        });
      }
    } else if (this._slashActive) {
      mentionDropdown.classList.add("hidden");
      btnMention.classList.remove("active");
      this._slashActive = false;
    }
  }

  private handleManualSlashCommand(): void {
    const text = this.getPlainText();

    if (this.hasModeChip()) return;
    const parsed = parseSlashInput(text);
    if (!parsed) return;
    this.activateSlashCommand(parsed.command, parsed.rest);
  }

  private registerCommandActions(): void {
    commandActions["settings"] = () => { this.automationPanel.hide(); this.settings.open(); };
    commandActions["model-management"] = () => { this.automationPanel.hide(); this.settings.open(); this.settings.switchPanel("model"); };
    commandActions["skills-management"] = () => { this.automationPanel.hide(); this.settings.open(); this.settings.switchPanel("skills"); };
    commandActions["mcp-servers"] = () => { this.automationPanel.hide(); this.settings.open(); this.settings.switchPanel("mcp"); };
    commandActions["agent-config"] = () => { this.automationPanel.hide(); this.settings.open(); this.settings.switchPanel("agent"); };
    commandActions["about"] = () => { this.automationPanel.hide(); this.settings.open(); this.settings.switchPanel("about"); };
    commandActions["theme-dark"] = () => {
      setThemePreference("dark");
      setTheme("dark");
      localStorage.setItem("encre-theme", "dark");
    };
    commandActions["theme-light"] = () => {
      setThemePreference("light");
      setTheme("light");
      localStorage.setItem("encre-theme", "light");
    };
    commandActions["theme-system"] = () => {
      setThemePreference("system");
      const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      setTheme(isDark ? "dark" : "light");
      localStorage.setItem("encre-theme", "system");
    };
    commandActions["language-zh"] = () => {
      const current = { ...getState().settings, language: "zh" };
      setSettings(current);
      setLocale("zh");
      send({ type: "configure", config: { language: "zh" } });
    };
    commandActions["language-en"] = () => {
      const current = { ...getState().settings, language: "en" };
      setSettings(current);
      setLocale("en");
      send({ type: "configure", config: { language: "en" } });
    };
    commandActions["new-session"] = () => {
      this.automationPanel.hide();
      this.exitTempChat();
      this.cleanupContentArea({ keepAutomationFlag: false });
      resetChat();
      const requestId = crypto.randomUUID();
      setRequestedSessionId("", requestId);
      send({ type: "new_session", request_id: requestId });
    };
    commandActions["keyboard-shortcuts"] = () => {
      showToast(t("general.keyboardShortcuts"), t("general.shortcutsDesc"), "info");
    };
  }

  private bindGlobalLinkInterceptor(): void {
    document.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;
      if (!target || !target.closest) return;
      const link = target.closest("a") as HTMLAnchorElement | null;
      if (!link || !link.href) return;
      const behavior = (getState().settings.default_link_behavior as string) || "system";
      if (behavior !== "in_app") return;
      let url = link.href;
      if (!url) return;
      const isWeb = /^(https?:\/\/|www\.)/i.test(url);
      if (!isWeb) return;
      if (/^www\./i.test(url)) url = "https://" + url;
      e.preventDefault();
      e.stopPropagation();
      const api = (window as any).electronAPI;
      if (api?.openChildWindow) {
        api.openChildWindow(url, url);
      } else {
        window.open(url, "_blank");
      }
    }, true);
  }

  private bindToolbarButtons(): void {
    const toggleSidebar = document.getElementById("btn-toggle-sidebar");
    toggleSidebar?.addEventListener("click", () => {
      this.userToggledSidebar = true;
      document.getElementById("app")?.classList.toggle("sidebar-collapsed");
    });

    // ── Header mode switch (shared .seg component with the tray popup) ──
    // The switch lives in the top tab bar; clicking it toggles between the
    // normal (chats) and iwork (workspace) modes by reusing the existing
    // workspace enter / exit flows so all animation, persistence and IPC
    // behavior stays in one place.
    const modeSeg = document.getElementById("mode-seg");
    if (modeSeg) {
      const items = modeSeg.querySelectorAll<HTMLElement>(".seg-item");
      items.forEach((item) => {
        item.addEventListener("click", () => {
          const mode = item.getAttribute("data-mode");
          if (mode === "iwork") {
            this.workspace?.enter();
          } else if (mode === "normal") {
            this.workspace?.exit();
          }
        });
      });
      // Keep the seg in sync with the canonical workspaceMode state. This
      // handles the case where the mode is changed by another path (e.g. a
      // workspace session being auto-resumed) or by the tray popup.
      const syncSegFromState = () => {
        const active = getState().workspaceMode === "iwork" ? "iwork" : "normal";
        items.forEach((el) => {
          const isActive = el.getAttribute("data-mode") === active;
          el.classList.toggle("active", isActive);
          el.setAttribute("aria-selected", isActive ? "true" : "false");
        });
      };
      syncSegFromState();
      // Re-sync whenever the workspace mode changes from anywhere in the
      // app (workspace enter/exit, IPC, tray popup, etc.).
      subscribe(syncSegFromState);
    }

    const newTaskBtn = document.querySelector('.nav-item[data-view="chat"]');
    newTaskBtn?.addEventListener("click", () => {
      // Hide automation view if active
      if (this.automationPanel.isActive) {
        this.automationPanel.toggleAutomationView();
      }
      this.exitTempChat();
      this.cleanupContentArea({ keepAutomationFlag: false });
      resetChat();
      const requestId = crypto.randomUUID();
      setRequestedSessionId("", requestId);
      send({ type: "new_session", request_id: requestId });
    });

    const tempChatBtn = document.getElementById("btn-temp-chat");
    tempChatBtn?.addEventListener("click", () => {
      if (getState().tempChat) return;
      this.automationPanel.hide();
      this.exitTempChat();
      this.cleanupContentArea({ keepAutomationFlag: false });
      resetChat();
      setTempChat(true);
      tempChatBtn?.classList.add("active");
      const requestId = crypto.randomUUID();
      setRequestedSessionId("", requestId);
      send({ type: "new_session", request_id: requestId });
    });

    const btnSettingsTrigger = document.getElementById("btn-settings-trigger");
    btnSettingsTrigger?.addEventListener("click", () => {
      this.automationPanel.hide();
      this.settings.open();
    });

    // @ button: upward dropdown
    const btnMention = document.getElementById("btn-mention");
    const mentionDropdown = document.getElementById("mention-dropdown");
    btnMention?.addEventListener("click", (e) => {
      e.stopPropagation();
      const wasHidden = mentionDropdown?.classList.contains("hidden");
      mentionDropdown?.classList.toggle("hidden");
      btnMention?.classList.toggle("active");
      this._slashActive = false;
      if (wasHidden) {
        const mainPage = mentionDropdown?.querySelector('[data-page="main"]');
        const slashPage = mentionDropdown?.querySelector('[data-page="slash"]');
        if (mainPage) mainPage.classList.remove("hidden");
        if (slashPage) slashPage.classList.add("hidden");
      }
    });

    // Close dropdown on outside click
    document.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;
      if (target.closest("#prompt-input") && this._slashActive) return;
      if (!target.closest("#btn-mention") && !target.closest("#mention-dropdown")) {
        mentionDropdown?.classList.add("hidden");
        btnMention?.classList.remove("active");
        this._slashActive = false;
      }
    });

    // Dropdown item actions
    mentionDropdown?.addEventListener("click", async (e) => {
      const item = (e.target as HTMLElement).closest(".mention-dropdown-item") as HTMLElement | null;
      if (!item) return;
      const action = item.getAttribute("data-action");

      // Sub-navigation: Slash Commands (enter sub-page)
      if (action === "sub-slash") {
        const mainPage = mentionDropdown.querySelector('[data-page="main"]');
        const slashPage = mentionDropdown.querySelector('[data-page="slash"]');
        mainPage?.classList.add("hidden");
        slashPage?.classList.remove("hidden");
        return;
      }

      // Sub-navigation: back to main
      if (action === "back-main") {
        const mainPage = mentionDropdown.querySelector('[data-page="main"]');
        const slashPage = mentionDropdown.querySelector('[data-page="slash"]');
        slashPage?.classList.add("hidden");
        mainPage?.classList.remove("hidden");
        return;
      }

      mentionDropdown.classList.add("hidden");
      btnMention?.classList.remove("active");

      // Don't re-activate if a mode chip already exists
      if (this.hasModeChip()) return;

      const cmd = SLASH_COMMANDS.find(c => c.id === action || c.name === action);
      if (cmd) {
        this.activateSlashCommand(cmd);
        if (cmd.kind === "mode") {
          this.input.focus();
        }
        return;
      }

      switch (action) {
        case "upload-file":
          this._slashActive = false;
          await this.files.promptForFiles();
          break;
        case "select-folder":
          this._slashActive = false;
          await this.files.promptForFolder();
          break;
      }
    });

    this.bindInputModelSelector();
  }

  private bindSummaryPanel(): void {
    const btn = document.getElementById("btn-summary-panel");
    const panel = document.getElementById("summary-panel");
    if (!btn || !panel) return;

    const toggle = () => {
      const isHidden = panel!.classList.toggle("hidden");
      btn!.classList.toggle("active", !isHidden);
      if (!isHidden) this.renderSummaryPanel();
    };

    btn.addEventListener("click", (e) => { e.stopPropagation(); toggle(); });

    // Close panel on outside click
    document.addEventListener("click", (e) => {
      if (panel!.classList.contains("hidden")) return;
      if (!panel!.contains(e.target as Node) && !btn!.contains(e.target as Node)) {
        panel!.classList.add("hidden");
        btn!.classList.remove("active");
      }
    });

    // "View all" link → open review tab in sidebar
    const viewAll = document.getElementById("summary-view-all");
    if (viewAll) {
      viewAll.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        panel!.classList.add("hidden");
        btn!.classList.remove("active");
        const st = getState();
        const first = st.artifacts?.[0];
        if (st.workspaceMode === "iwork") {
          this.sessionInner.showReviewTab("", undefined);
        } else {
          this.sessionInner.showReviewTab(first?.path || "", first || undefined);
        }
      });
    }

    // Re-render when state changes
    onLocaleChange(() => {
      if (!this.summaryPanel.classList.contains("hidden")) this.renderSummaryPanel();
    });

    subscribe(() => {
      if (!this.summaryPanel.classList.contains("hidden")) this.renderSummaryPanel();
    });
  }

  private renderSummaryPanel(): void {
    const st = getState();
    this.renderSummaryProgress(st);
    this.renderSummaryArtifacts(st);
    this.renderSummaryReferences(st);
    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons();
    }
  }

  private renderSummaryProgress(st: ReturnType<typeof getState>): void {
    const el = document.getElementById("summary-progress-items");
    if (!el) return;
    const items = st.planItems;
    if (!items || items.length === 0) {
      el.innerHTML = `<div style="padding:6px 0;font-size:12px;color:var(--text-muted)">${t("sessionInner.noProgress")}</div>`;
      return;
    }
    const active = items.filter((i: any) => i.status !== "done");
    const done = items.filter((i: any) => i.status === "done");
    const parts: string[] = [];
    const renderItem = (item: any) => {
      let cls = "sp-todo-item";
      let icon = "circle";
      if (item.status === "done") { cls += " sp-todo-done"; icon = "check-circle-2"; }
      else if (item.status === "active") { cls += " sp-todo-active"; icon = "loader"; }
      else { cls += " sp-todo-pending"; }
      return `<div class="${cls}">
        <i data-lucide="${icon}" class="lucide lucide-sm sp-todo-icon"></i>
        <span class="sp-todo-text">${this.esc(item.text)}</span>
      </div>`;
    };
    active.slice(0, 8).forEach((i: any) => parts.push(renderItem(i)));
    if (done.length > 0) {
      const collapsed = done.length > 2;
      const displayCount = collapsed ? 0 : done.length;
      parts.push(`<div class="sp-todo-done-section${collapsed ? " collapsed" : ""}">
        <div class="sp-todo-done-header" onclick="this.parentElement.classList.toggle('collapsed')">
          <i data-lucide="check-circle-2" class="lucide lucide-sm sp-todo-done-icon"></i>
          <span class="sp-todo-done-label">${t("sessionInner.doneItems", { count: done.length })}</span>
          <i data-lucide="chevron-down" class="lucide lucide-sm sp-todo-chevron"></i>
        </div>
        <div class="sp-todo-done-body">${done.slice(0, 8).map(renderItem).join("")}</div>
      </div>`);
    }
    el.innerHTML = parts.join("");
    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: el });
    }
  }

  private renderSummaryArtifacts(st: ReturnType<typeof getState>): void {
    const el = document.getElementById("summary-artifacts-items");
    if (!el) return;
    const artifacts = st.artifacts;
    if (!artifacts || artifacts.length === 0) {
      el.innerHTML = `<div style="padding:6px 0;font-size:12px;color:var(--text-muted)">${t("sessionInner.noArtifacts")}</div>`;
      return;
    }
    el.innerHTML = artifacts.slice(0, 6).map((a: any) => {
      const iconSrc = a.ext === "py" ? "file-code-2" : a.ext === "ts" || a.ext === "tsx" || a.ext === "js" ? "file-code-2" : "file-plus-2";
      const adds = a.diff_text ? (a.diff_text.match(/^\+/gm) || []).length : 0;
      const dels = a.diff_text ? (a.diff_text.match(/^-/gm) || []).length : 0;
      return `<div class="sp-artifact-item">
        <i data-lucide="${iconSrc}" class="lucide lucide-sm sp-artifact-icon"></i>
        <span class="sp-artifact-name">${this.esc(a.name)}</span>
        <span class="sp-artifact-stats">
          <span class="si-diff-add">+${adds}</span>
          <span class="si-diff-remove">-${dels}</span>
        </span>
        <a class="sp-artifact-review" href="#" data-path="${this.esc(a.path)}">
          <i data-lucide="eye" class="lucide lucide-xs"></i>
        </a>
      </div>`;
    }).join("");
    el.querySelectorAll(".sp-artifact-review").forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const path = (link as HTMLElement).dataset.path!;
        this.summaryPanel.classList.add("hidden");
        const sbBtn = document.getElementById("btn-summary-panel");
        if (sbBtn) sbBtn.classList.remove("active");
        if (this.chat.onViewChanges) this.chat.onViewChanges(path);
      });
    });
  }

  private renderSummaryReferences(st: ReturnType<typeof getState>): void {
    const el = document.getElementById("summary-references-items");
    if (!el) return;
    const refs = st.references || [];
    if (refs.length === 0) {
      el.innerHTML = `<div style="padding:6px 0;font-size:12px;color:var(--text-muted)">${t("sessionInner.noRefs")}</div>`;
      return;
    }
    const shown = refs.slice(-8).reverse();
    el.innerHTML = shown.map((r: any) => {
      const iconSrc = r.icon || "link-2";
      return `<div style="display:flex;align-items:center;gap:6px;padding:3px 0;font-size:12px;color:var(--text-secondary)">
        <i data-lucide="${iconSrc}" class="lucide lucide-sm" style="flex-shrink:0;width:12px;height:12px;opacity:0.6"></i>
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${this.esc(r.summary)}</span>
      </div>`;
    }).join("");
  }

  private esc(s: string): string {
    const el = document.createElement("span");
    el.textContent = s;
    return el.innerHTML;
  }

  private bindInputModelSelector(): void {
    const selector = document.getElementById("input-model-selector");
    const dropdown = document.getElementById("input-model-dropdown");
    if (!selector || !dropdown) return;

    const render = () => {
      const st = getState();
      const allModels = st.modelConfigs || [];
      const activeIdx = st.activeModelIndex;
      const active = allModels[activeIdx];
      // Show only enabled models (fallback: show active model even if disabled)
      const models = allModels.filter((m, i) => m.enabled !== false || i === activeIdx);
      selector.textContent = active?.name || active?.model_id || t("app.model");

      if (models.length === 0) {
        dropdown.innerHTML = `<div class="settings-dropdown-item muted">${t("app.noModelsConfigured")}</div>`;
        return;
      }

      dropdown.innerHTML = models
        .map((m, i) => {
            const origIdx = allModels.indexOf(m);
            const sel = origIdx === activeIdx ? " selected" : "";
            const disabled = m.enabled === false ? " muted" : "";
            return `<div class="settings-dropdown-item${sel}${disabled}" data-idx="${origIdx}">${this.esc(m.name || m.model_id)}</div>`;
          })
          .join("");
      dropdown.querySelectorAll(".settings-dropdown-item[data-idx]").forEach((item) => {
        item.addEventListener("click", (e) => {
          e.stopPropagation();
          const idx = parseInt((item as HTMLElement).dataset.idx || "0");
          send({ type: "set_active_model", model_index: idx });
          selector.textContent = allModels[idx]?.name || allModels[idx]?.model_id || t("app.model");
          dropdown.classList.add("hidden");
        });
      });
    };

    selector.addEventListener("click", (e) => {
      e.stopPropagation();
      console.log("[model-selector] clicked, hidden=", dropdown.classList.contains("hidden"));
      if (dropdown.classList.contains("hidden")) {
        render();
        dropdown.classList.remove("hidden");
        console.log("[model-selector] opened, items=", dropdown.querySelectorAll("[data-idx]").length);
      } else {
        dropdown.classList.add("hidden");
      }
    });

    document.addEventListener("click", (e) => {
      if (!selector.contains(e.target as Node) && !dropdown.contains(e.target as Node)) {
        dropdown.classList.add("hidden");
      }
    });

    onLocaleChange(() => {
      if (!this.summaryPanel.classList.contains("hidden")) this.renderSummaryPanel();
    });

    subscribe(() => {
      try {
        render();
        if (!dropdown.classList.contains("hidden")) {
          render();
        }
      } catch (e) {
        console.error("[model-selector] subscribe render failed:", e);
      }
    });

    render();
  }

  private activateSlashCommand(cmd: SlashCommand, restText?: string): void {
    this.skipNextInput = true;
    const dd = document.getElementById("mention-dropdown");
    const bm = document.getElementById("btn-mention");
    dd?.classList.add("hidden");
    bm?.classList.remove("active");
    this._slashActive = false;
    this.input.innerHTML = "";

    if (cmd.kind === "mode") {
      this.insertModeChip(cmd.id, restText);
      this._currentChipMode = cmd.id;
      setInputMode(cmd.id);
      this.updateChipState();
      this.updatePlaceholder();
      this.resizeInput();
      this.updateSendButton();
    } else if (cmd.kind === "action") {
      this.executeSlashAction(cmd, restText);
      this.updatePlaceholder();
      this.resizeInput();
      this.updateSendButton();
    }
  }

  private executeSlashAction(cmd: SlashCommand, restText?: string): void {
    switch (cmd.id) {
      case "new-session":
      case "clear-session":
        this.automationPanel.hide();
        this.exitTempChat();
        this.cleanupContentArea({ keepAutomationFlag: false });
        resetChat();
        {
          const requestId = crypto.randomUUID();
          setRequestedSessionId("", requestId);
          send({ type: "new_session", request_id: requestId });
        }
        return;
      case "steer":
        this.insertModeChip(cmd.id, restText);
        this._currentChipMode = "steer";
        this.updateChipState();
        this.input.focus();
        return;
      default:
        break;
    }
    // Custom action commands: insert a chip so the user can type after it,
    // then submit sends only the text (no mode parameter)
    this.insertModeChip(cmd.id, restText);
    this._currentChipMode = cmd.id;
    this.updateChipState();
    this.input.focus();
  }

  private deactivateModeChip(): void {
    if (!this.hasModeChip()) return;
    this.removeModeChip();
    this._currentChipMode = "";
    this.updateChipState();
    this.updatePlaceholder();
    this.resizeInput();
    this.updateSendButton();
  }

  /* ── Contenteditable helpers ─────────────────────────────────── */

  private getPlainText(): string {
    const clone = this.input.cloneNode(true) as HTMLElement;
    clone.querySelectorAll('[contenteditable="false"]').forEach(el => el.remove());
    return clone.textContent?.trim() || "";
  }

  private hasModeChip(): boolean {
    return !!this.input.querySelector('.mode-chip[data-mode]');
  }

  private getCurrentMode(): string {
    const chip = this.input.querySelector('.mode-chip[data-mode]');
    if (!chip) return "";
    return chip.getAttribute("data-mode") || "";
  }

  private insertModeChip(mode: string, restText?: string): void {
    this.removeModeChip();
    const chip = document.createElement("span");
    chip.contentEditable = "false";
    chip.className = "mode-chip";
    chip.setAttribute("data-mode", mode);
    const cmd = SLASH_COMMANDS.find(c => c.id === mode);
    const label = cmd ? cmd.title : mode;
    const icon = cmd ? cmd.icon : "list-checks";
    chip.innerHTML = `<i data-lucide="${icon}" class="chip-icon" style="width:12px;height:12px;"></i><span>${label}</span>`;
    this.input.appendChild(chip);

    if (restText) {
      this.input.appendChild(document.createTextNode(restText));
    }

    // Cursor after chip — typing inserts text after the chip
    const sel = window.getSelection();
    if (sel) {
      const range = document.createRange();
      range.setStartAfter(chip);
      range.collapse(true);
      sel.removeAllRanges();
      sel.addRange(range);
    }

    if ((window as any).lucide) {
      (window as any).lucide.createIcons();
    }
  }

  private removeModeChip(): void {
    const chip = this.input.querySelector('.mode-chip[data-mode]');
    if (chip) chip.remove();
  }

  private handleModeEnd(): void {
    this.removeModeChip();
    this._currentChipMode = "";
    setInputMode("");
    this.updateChipState();
    this.updatePlaceholder();
  }

  private updateChipState(): void {
    const mode = this.getCurrentMode();
    const el = document.getElementById("input-area");
    if (!el) return;
    if (mode) {
      el.setAttribute("data-input-mode", mode);
    } else {
      el.removeAttribute("data-input-mode");
    }
  }

  private updatePlaceholder(): void {
    const ph = document.getElementById("prompt-placeholder");
    if (!ph) return;
    const mode = this.getCurrentMode();
    const wsMode = getState().workspaceMode;

    if (mode) {
      ph.textContent = t("input.placeholderMode");
    } else if (wsMode === "iwork") {
      ph.textContent = t("input.placeholderIwork");
    } else {
      ph.textContent = t("input.placeholder");
    }

    // Hide overlay when user typed text, or when any chip present (chip is the visual indicator)
    const hasText = this.getPlainText().length > 0;
    const hasChip = this.hasModeChip();
    const hasAttach = !!this.input.querySelector('[data-attach]');
    ph.classList.toggle("hidden", hasText || hasChip || hasAttach);

    // Update welcome screen title based on current mode
    this.updateWelcomeTitle(wsMode);
  }

  private updateWelcomeTitle(mode: string): void {
    const title = document.querySelector(".welcome-title");
    if (!title) return;

    const st = getState();
    const newText = st.tempChat ? t("session.tempChatActive") :
                    mode === "iwork" ? t("welcome.iwork") :
                    t("welcome.title");

    // If an animation is in progress, skip setting text here
    if (this._welcomeTitleAnimating) return;
    title.textContent = newText;
  }

  /** Animate welcome title text change with a slide transition */
  private animateWelcomeTitle(mode: string): void {
    const title = document.querySelector(".welcome-title") as HTMLElement | null;
    if (!title) return;

    const newText = mode === "iwork" ? t("welcome.iwork") :
                    t("welcome.title");

    if (title.textContent === newText) {
      this._welcomeTitleAnimating = false;
      return;
    }

    const d = TransitionHelper.DEFAULT_DURATION;
    const easing = "cubic-bezier(0.4, 0, 0.2, 1)";

    // 滑出（向左 100%）
    title.style.transition = `transform ${d}ms ${easing}, opacity ${d}ms ${easing}`;
    title.style.transform = "translateX(-100%)";
    title.style.opacity = "0";

    setTimeout(() => {
      // 切换文字，定位到右侧起始位置
      title.textContent = newText;
      title.style.transition = "none";
      title.style.transform = "translateX(100%)";
      title.style.opacity = "0";

      requestAnimationFrame(() => {
        // 滑入（从右到左）
        title.style.transition = `transform ${d}ms ${easing}, opacity ${d}ms ${easing}`;
        title.style.transform = "translateX(0)";
        title.style.opacity = "1";

        setTimeout(() => {
          title.style.transition = "";
          title.style.transform = "";
          title.style.opacity = "";
          this._welcomeTitleAnimating = false;
        }, d + 50);
      });
    }, d + 30);
  }

  /** Programmatically close the session inner sidebar if it's open */
  private closeSessionInnerSidebar(): void {
    const panel = document.getElementById("session-inner-sidebar");
    const mainBody = document.getElementById("main-body");
    if (!panel || !mainBody) return;
    if (!panel.classList.contains("hidden")) {
      this.sessionInner.saveWidth();
      panel.classList.add("hidden");
      mainBody.classList.add("sidebar-hidden");
    }
  }

  /**
   * Re-initialize the main content area to its default "fresh chat" state.
   * Called AFTER cleanupContentArea() on session/mode switches so the user
   * sees a clean welcome screen with empty input, no sub-agent header, no
   * queue card, no status bar, and no leftover dropdowns — exactly like
   * the app's first launch.
   */
  private enterChatMode(): void {
    // Show welcome screen, hide message list (chat.render() will
    // override this once state.messages lands).
    if (this.welcomeScreen) {
      this.welcomeScreen.classList.remove("hidden");
    }
    if (this.messageList) {
      this.messageList.classList.add("hidden");
      this.messageList.innerHTML = "";
    }
    // Reset welcome title to default.  animateWelcomeTitle() will replace
    // this with the right "iWork" / "default" text in a moment.
    const title = document.querySelector(".welcome-title") as HTMLElement | null;
    if (title) {
      title.textContent = t("welcome.title");
      title.style.transition = "";
      title.style.transform = "";
      title.style.opacity = "";
    }
    // Show placeholder, hide mode chip.
    const placeholder = document.getElementById("prompt-placeholder");
    if (placeholder) placeholder.classList.remove("hidden");
    // Force chat.render() to redraw the message list with the new state.
    // It will set welcome vs message-list visibility based on state.messages
    // and re-bind handlers on the freshly-built DOM.
    this.chat.renderForce?.();
    this.chat.render();
    // Re-bind the input model selector in case the model selector's
    // event listener was lost during a heavy innerHTML replacement.
    this.bindInputModelSelector();
    // Re-apply shortcut hints (e.g. when the input area was just rebuilt).
    this.applyShortcutHints();
    // Update placeholder text + welcome title for the new mode.
    this.updatePlaceholder();
    this.updateSessionBarName();
  }

  /**
   * Tear down all transient UI artifacts from the content area so the next
   * render starts from a clean slate.  Called BEFORE enterChatMode() on
   * session/mode switches.
   * @param opts - Optional flags controlling cleanup behaviour.
   */
  private cleanupContentArea(opts?: { keepAutomationFlag?: boolean }): void {
    // ── 1. Sub-agent view + breadcrumb ──────────────────────────────
    // These gate the inline "sub-agent" overlay in #message-list and the
    // breadcrumb chips in the session bar.  Without clearing them, switching
    // sessions leaves a phantom sub-agent header and a stale "X / Y / Z" trail
    // pointing at the previous session's nested agent.
    setSubAgentView(null);
    clearSubAgentBreadcrumb();
    (window as any).__closeSubAgentView = undefined;
    (window as any).__navigateToBreadcrumb = undefined;

    // ── 2. Automation panel state ──────────────────────────────────
    if (!opts?.keepAutomationFlag) {
      (window as any).__isAutomationView = false;
      (window as any).__activeAutomationJobId = "";
      // Restore automation sub-agent close-handler to the no-op default.
      (window as any).__closeSubAgentView = undefined;
    }

    // ── 3. Tool detail panel (right-side aside) ─────────────────────
    // The aside is a sibling of #main-content; it is hidden when no active
    // tool id is set, but the id itself sticks around.  Wipe both.
    setActiveToolId(null);
    const detailPanel = document.getElementById("detail-panel");
    if (detailPanel) {
      detailPanel.classList.add("hidden");
      const detailContent = document.getElementById("detail-content");
      if (detailContent) detailContent.innerHTML = "";
    }

    // ── 4. Mention / @ dropdown (above the prompt input) ───────────
    const mentionDropdown = document.getElementById("mention-dropdown");
    if (mentionDropdown) {
      mentionDropdown.classList.add("hidden");
      // Also reset to the main page so the next open shows Files/Folder,
      // not a stale "back" state from the slash-commands sub-page.
      const mainPage = mentionDropdown.querySelector('[data-page="main"]');
      const slashPage = mentionDropdown.querySelector('[data-page="slash"]');
      if (mainPage) mainPage.classList.remove("hidden");
      if (slashPage) slashPage.classList.add("hidden");
    }
    const btnMention = document.getElementById("btn-mention");
    if (btnMention) btnMention.classList.remove("active");
    this._slashActive = false;

    // ── 5. Model selector dropdown (in input toolbar) ──────────────
    const modelDropdown = document.getElementById("input-model-dropdown");
    if (modelDropdown) modelDropdown.classList.add("hidden");

    // ── 6. Chat status bar + queue card ────────────────────────────
    const statusBar = document.getElementById("chat-status-bar");
    if (statusBar) {
      statusBar.classList.add("hidden");
      statusBar.innerHTML = "";
      statusBar.style.maxWidth = "";
    }
    const queueCard = document.getElementById("queue-card");
    if (queueCard) {
      queueCard.classList.add("hidden");
      const qBody = document.getElementById("queue-card-body");
      if (qBody) qBody.innerHTML = "";
    }

    // ── 7. Input area — clear leftover text/chip/attachments ───────
    if (this.input) {
      this.input.innerHTML = "";
      this.input.style.height = "56px";
    }
    this._currentChipMode = "";
    setInputMode("");
    clearAttachments();
    clearQueuedPrompts();
    setPendingQueueCount(0);

    // ── 8. Mode-chip CSS hook + restore input area visibility ─────
    const inputArea = document.getElementById("input-area");
    if (inputArea) {
      inputArea.removeAttribute("data-input-mode");
      // Always restore input-area visibility — sub-agent view hides it via
      // updateSessionBarName(); we want to undo that on cleanup.
      inputArea.style.display = "";
    }
    const sessionMenuBtn = document.getElementById("btn-session-menu");
    if (sessionMenuBtn) sessionMenuBtn.style.display = "";
    const mainContent = document.getElementById("main-content");
    if (mainContent) mainContent.classList.remove("sub-agent-active");

    // ── 9. Search overlay (Ctrl/Cmd+K) ─────────────────────────────
    if (this.search) this.search.close();

    // ── 10. Floating dropdowns that may be left open ───────────────
    // The settings-search overlay, the input-area "model" dropdown, any
    // inline tab-add dropdowns in #session-inner-sidebar, etc.  Anything
    // with `.open` or `.visible` is a transient popup — close it.
    document.querySelectorAll(".settings-dropdown.open").forEach((dd) => dd.classList.remove("open"));
    document.querySelectorAll(".tab-add-dropdown:not(.hidden)").forEach((dd) => dd.classList.add("hidden"));
    document.querySelectorAll(".context-menu:not(.hidden)").forEach((m) => m.classList.add("hidden"));
    document.querySelectorAll(".tooltip:not(.hidden), [data-tooltip-visible]").forEach((t) => {
      t.classList.add("hidden");
      t.removeAttribute("data-tooltip-visible");
    });

    // ── 11. Rename dialog ──────────────────────────────────────────
    const renameOverlay = document.getElementById("rename-dialog-overlay");
    if (renameOverlay) {
      renameOverlay.classList.add("hidden");
      renameOverlay.innerHTML = "";
    }

    // ── 12. Session inner sidebar — hide the container AND drop tabs ─
    // The user might have opened the right-side #session-inner-sidebar
    // in the previous view (e.g. opened a terminal tab in normal mode and
    // then switched to iWork).  If we only tear down the dynamic tabs and
    // leave the container visible, the user sees an empty blank panel
    // sitting on top of the workspace tree — which is wrong.  Force-hide
    // the container here so the content area is fully reset, regardless
    // of whatever state the previous view left it in.
    const sessionInnerSidebar = document.getElementById("session-inner-sidebar");
    if (sessionInnerSidebar) {
      // Persist the (probably user-set) width before we hide it so we can
      // restore it when the user re-opens the sidebar.
      this.sessionInner?.saveWidth?.();
      sessionInnerSidebar.classList.add("hidden");
    }
    if (this.sessionInner) this.sessionInner.resetToDefaultTabs();
    const mainBody = document.getElementById("main-body");
    if (mainBody) mainBody.classList.add("sidebar-hidden");

    // ── 13. Welcome screen transition guard ────────────────────────
    // Force-reset the animation latch so the next mode switch re-animates
    // the title.  Without this the second switch can land on a stale
    // ``_welcomeTitleAnimating=true`` and the title text never updates.
    this._welcomeTitleAnimating = false;

    // ── 14. Force-reset #message-list + welcome screen ─────────────
    // chat.render() will repaint #message-list, but it does not always
    // run synchronously with this cleanup.  Clear it eagerly so we never
    // show a stale message bubble for one frame after switching modes.
    if (this.messageList) {
      this.messageList.innerHTML = "";
      this.messageList.classList.add("hidden");
    }
    if (this.welcomeScreen) {
      this.welcomeScreen.classList.remove("hidden");
      // Reset the welcome title text so animateWelcomeTitle() can drive
      // it from scratch on the next paint.  Without this the second
      // mode-switch can land on a stale (already-animated) string and
      // the slide-in transition is skipped.
      const title = this.welcomeScreen.querySelector(".welcome-title") as HTMLElement | null;
      if (title) {
        title.textContent = t("welcome.title");
        title.style.transition = "";
        title.style.transform = "";
        title.style.opacity = "";
      }
    }

    // ── 15. Force-reset #placeholder visibility ────────────────────
    // The placeholder is hidden while the user types or has a chip; the
    // chat render pipeline restores it.  Show it eagerly so the next
    // frame does not flash a blank input.
    const placeholder = document.getElementById("prompt-placeholder");
    if (placeholder) placeholder.classList.remove("hidden");

    // ── 16. Force-hide #automation-view + clear its children ───────
    // AutomationPanel.hide() also does this, but doing it here makes
    // the cleanup robust to races where the user's mode change happens
    // before the panel has time to slide away.
    const automationView = document.getElementById("automation-view");
    if (automationView) {
      automationView.classList.add("hidden");
      // Clear any inline-positioning styles set by TransitionHelper.slide.
      automationView.style.position = "";
      automationView.style.width = "";
      automationView.style.height = "";
      automationView.style.top = "";
      automationView.style.left = "";
    }
    const automationBack = document.getElementById("btn-automation-back");
    if (automationBack) automationBack.classList.add("hidden");
    const sidebarToggle = document.getElementById("btn-toggle-sidebar");
    if (sidebarToggle) sidebarToggle.classList.remove("hidden");

    // ── 17. Clear #child-view content ──────────────────────────────
    // The child view hosts sub-windows (license, easter-egg, logs, etc.).
    // Switching modes or sessions must not leave those webviews/canvases
    // running in the background — that wastes GPU and is a security smell.
    const childView = document.getElementById("child-view");
    if (childView) {
      childView.classList.add("hidden");
      childView.innerHTML = "";
    }

    // ── 18. Reset session-bar text + btn-session-menu state ───────
    // When sub-agent view is active the session-bar shows a breadcrumb
    // trail; after cleanup we want the plain "New Session" label back.
    const sessionBarName = document.getElementById("session-bar-name");
    if (sessionBarName) {
      sessionBarName.textContent = t("session.newSession");
      sessionBarName.removeAttribute("title");
    }

    // ── 19. Reset #session-bar visibility ─────────────────────────
    // Automation hides #session-bar; if the user was in automation and
    // switched modes, the bar must come back.
    const sessionBar = document.getElementById("session-bar");
    if (sessionBar) {
      sessionBar.classList.remove("hidden");
      sessionBar.style.display = "";
    }

    // ── 20. Reset main-area inline styles set by TransitionHelper ─
    // The slide transitions on automation / workspace swap can leave
    // absolute-positioning styles behind if the animation is interrupted
    // (e.g. the user clicks again mid-transition).  Clear them here.
    if (mainBody) {
      mainBody.style.position = "";
    }
    if (mainContent) {
      mainContent.style.position = "";
      mainContent.style.width = "";
      mainContent.style.height = "";
      mainContent.style.top = "";
      mainContent.style.left = "";
    }

    // ── 21. Scroll position reset for chat-container ───────────────
    // The chat container keeps its scrollTop across renders.  If the user
    // was scrolled deep in a long previous session, switching to a new
    // short session keeps the scroll position at a "blank" area.  Reset
    // to the bottom so the welcome screen / first message is visible.
    const chatContainer = document.getElementById("chat-container");
    if (chatContainer) chatContainer.scrollTop = chatContainer.scrollHeight;

    // ── 22. Scroll-track / scroll-thumb reset ─────────────────────
    // The right-side scroll progress indicator is built by ChatScrollIndicator.
    // Reset its DOM so it does not show a stale position for one frame.
    const scrollTrack = document.getElementById("chat-scroll-track");
    if (scrollTrack) scrollTrack.innerHTML = "";
    const scrollThumb = document.getElementById("chat-scroll-thumb");
    if (scrollThumb) {
      scrollThumb.classList.add("hidden");
      scrollThumb.style.top = "";
    }
    const scrollIndicator = document.getElementById("chat-scroll-indicator");
    if (scrollIndicator) scrollIndicator.classList.add("hidden");

    // ── 23. Reset temp-chat button + clear any temp flags ─────────
    const tempBtn = document.getElementById("btn-temp-chat");
    if (tempBtn) tempBtn.classList.remove("active");
    const btnNewTask = document.querySelector('.nav-item[data-view="chat"]');
    if (btnNewTask) btnNewTask.classList.add("active");

    // ── 24. Clear pending rollout animation classes on #app ────────
    // The body sometimes gets a "sidebar-collapsed" class from the
    // responsive collapse code; if the previous view left it stale
    // and we are NOT in a small viewport, the layout breaks.  Let the
    // responsive observer re-evaluate, but force-clear transient mode
    // classes here.
    const appEl = document.getElementById("app");
    if (appEl) {
      appEl.classList.remove("sub-agent-active");
    }
  }

  /** Exit temp chat: delete the temporary session from server. */
  private exitTempChat(): void {
    if (!getState().tempChat) return;
    const sid = getState().sessionId;
    setTempChat(false);
    if (sid) {
      send({ type: "delete_session", session_id: sid });
    }
  }

  private resizeInput(): void {
    this.input.style.height = "auto";
    const h = Math.min(Math.max(this.input.scrollHeight, 56), 320);
    this.input.style.height = `${h}px`;
  }

  private updateSendButton(): void {
    const hasText = this.getPlainText().length > 0;
    const running = getState().running;
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
    this.btnSend.disabled = !hasText && !this.hasModeChip();
  }

  private placeCursorAtEnd(): void {
    const sel = window.getSelection();
    if (!sel) return;
    const range = document.createRange();
    range.selectNodeContents(this.input);
    range.collapse(false);
    sel.removeAllRanges();
    sel.addRange(range);
  }

  private renderSlashDropdown(): void {
    const slashPage = document.querySelector('[data-page="slash"]');
    if (!slashPage) return;

    const backBtn = `<button class="mention-dropdown-item" data-action="back-main">
      <i data-lucide="arrow-left" class="lucide"></i>
      <span>${t("general.slashCommands")}</span>
    </button>`;

    const items = SLASH_COMMANDS.map(cmd => `
      <button class="mention-dropdown-item" data-action="${cmd.id}" data-slash="${cmd.name}" data-kind="${cmd.kind}">
        <i data-lucide="${cmd.icon}" class="lucide mention-icon-${cmd.id}"></i>
        <span>${cmd.title}  <span class="mention-hint">/${cmd.name}</span></span>
      </button>
    `).join("");

    slashPage.innerHTML = backBtn + items;

    if ((window as any).lucide) {
      (window as any).lucide.createIcons();
    }
  }

  private fetchModels(): void {
    send({ type: "list_models" });
  }

  private bindWindowControls(): void {
    const btnMinimize = document.getElementById("btn-minimize");
    const btnMaximize = document.getElementById("btn-maximize");
    const btnClose = document.getElementById("btn-close");

    btnMinimize?.addEventListener("click", async () => {
      await window.electronAPI?.windowMinimize();
    });

    btnMaximize?.addEventListener("click", async () => {
      await window.electronAPI?.windowMaximize();
    });

    btnClose?.addEventListener("click", async () => {
      await window.electronAPI?.windowClose();
    });
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

  private submit(): void {
    let text = this.getPlainText();
    const st = getState();
    const hasAttachments = st.attachments.length > 0;

    if (!text.trim() && !this.hasModeChip() && !hasAttachments) return;

    const isQueued = st.running;

    // Send mode for all commands that have a chip in the input
    const sendMode = this.getCurrentMode() || undefined;

    // If user submitted with no text, generate default text
    if (!text.trim()) {
      if (sendMode) {
        text = `<mode>${sendMode}</mode>`;
      } else if (hasAttachments) {
        const first = st.attachments[0];
        if (first.mime_type === "text/x-terminal") {
          text = `<terminal>\n${first.content}\n</terminal>`;
        } else {
          text = `<attach n="${first.name}"${st.attachments.length > 1 ? ` c="${st.attachments.length}"` : ""} />`;
        }
      }
    }

    const fileRefs = st.attachments.length > 0 ? st.attachments.map(a => ({ name: a.name, size: a.size, icon: a.mime_type === "text/x-terminal" ? "terminal" : a.mime_type === "text/x-directory" ? "folder" : this.files.fileIcon(a.name), path: a.path, mime_type: a.mime_type })) : undefined;

    if (isQueued) {
      pushQueuedPrompt(text, sendMode);
      clearAttachments();
      this.input.innerHTML = "";
      this.input.style.height = "56px";
      this._currentChipMode = "";
      setInputMode("");
      return;
    }

    // /steer: mid-run injection - don't add a user message or start a new turn
    if (this._currentChipMode === "steer") {
      if (!text.trim()) return;
      send({ type: "steer", session_id: st.sessionId || undefined, prompt: text } as any);
      this.input.innerHTML = "";
      this.input.style.height = "56px";
      this._currentChipMode = "";
      setInputMode("");
      this.updateChipState();
      this.updatePlaceholder();
      this.updateSendButton();
      return;
    }

    addUserMessage(text, sendMode, fileRefs);
    startAssistantMessage();
    setRunning(true);
    this.updateUIState(true);

    const attachments = st.attachments.length > 0 ? st.attachments.map(a => a.mime_type === "text/x-terminal" ? { ...a, content: `<terminal>\n${a.content}\n</terminal>` } : { ...a, content: "", is_binary: false }) : undefined;
    const payload: Record<string, any> = {
      type: "run",
      prompt: text,
      session_id: st.sessionId || undefined,
      attachments: attachments as any,
      temp_chat: st.tempChat || undefined,
    };
    if (sendMode) {
      payload.mode = sendMode;
      setInputMode(sendMode);
      // Include the command's custom prompt if defined
      const cmd = SLASH_COMMANDS.find(c => c.id === sendMode);
      if (cmd?.prompt) {
        payload.mode_prompt = cmd.prompt;
      }
    }
    send(payload as import("./types.js").ClientMessage);
    clearAttachments();
    this._inputHistory.push(text);
    this._inputHistoryIdx = this._inputHistory.length;
    // Force scroll to bottom so the user immediately sees the message they sent
    const _chatContainer = document.getElementById("chat-container");
    if (_chatContainer) _chatContainer.scrollTop = _chatContainer.scrollHeight;

    // Clear input — mode chip is hidden during agent execution.
    this.input.innerHTML = "";
    this.input.style.height = "56px";
    this._currentChipMode = "";
    setInputMode("");
    this.updateChipState();
    this.updatePlaceholder();
    this.updateSendButton();
    this.chat.render();
  }

  private cancel(): void {
    // Close @ dropdown if open
    const dd = document.getElementById("mention-dropdown");
    const bm = document.getElementById("btn-mention");
    if (dd && !dd.classList.contains("hidden")) {
      dd.classList.add("hidden");
      bm?.classList.remove("active");
      this._slashActive = false;
    }

    const s = getState();
    if (s.running) {
      this.btnStop.classList.add("cancelling");
      this.btnStop.style.pointerEvents = "none";
      send({ type: "cancel", session_id: s.sessionId });
    }
    // Clear pending queue and remove orphan user message if queue was partially consumed
    if (s.queuedPrompts.length > 0) {
      const msgs = getState().messages;
      clearQueuedPrompts();
      const lastMsg = msgs[msgs.length - 1];
      if (lastMsg && lastMsg.role === "user" && !lastMsg.isStreaming && !msgs.some(m => m.parentId === lastMsg.id || m.serverId === lastMsg.serverId)) {
        removeLastMessage();
      }
    }

    // Always remove mode chip regardless of running state
    this.deactivateModeChip();
  }

  /* ── Voice Input ──────────────────────────────────────────── */

  private toggleVoice(): void {
    if (this._isRecording) {
      this.stopVoice();
    } else {
      this.startVoice();
    }
  }

  private startVoice(): void {
    if (!navigator.mediaDevices?.getUserMedia) {
      showToast(t("app.voiceNotSupported"), "error");
      return;
    }

    this._audioChunks = [];

    navigator.mediaDevices.getUserMedia({ audio: true })
      .then((stream) => {
        this._mediaStream = stream;
        const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus"
          : "";
        this._mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);

        this._mediaRecorder.ondataavailable = (e) => {
          if (e.data.size > 0) this._audioChunks.push(e.data);
        };

        this._mediaRecorder.onstop = () => {
          const rec = this._mediaRecorder!;
          const mt = rec.mimeType || "audio/webm";
          const ext = mt.includes("mp4") ? "mp4" : "webm";
          const blob = new Blob(this._audioChunks, { type: mt });
          this._audioChunks = [];

          const reader = new FileReader();
          reader.onload = () => {
            const base64 = (reader.result as string).split(",")[1];
            send({ type: "transcribe_audio", audio_data: base64, format: ext });
          };
          reader.onerror = () => showToast(t("app.audioEncodeFailed"), "error");
          reader.readAsDataURL(blob);

          this.cleanupVoice();
        };

        this._mediaRecorder.onerror = () => {
          showToast(t("app.recordingError"), "error");
          this.cleanupVoice();
        };

        this._mediaRecorder.start();
        this._isRecording = true;
        this.btnVoice.classList.add("recording");
        this.btnVoice.title = t("input.voiceStop");
      })
      .catch(() => showToast(t("app.micAccessDenied"), "error"));
  }

  private stopVoice(): void {
    if (this._mediaRecorder && this._mediaRecorder.state !== "inactive") {
      this._mediaRecorder.stop();
    }
    if (this._mediaStream) {
      this._mediaStream.getTracks().forEach((t) => t.stop());
      this._mediaStream = null;
    }
  }

  private cleanupVoice(): void {
    this._mediaRecorder = null;
    this._mediaStream = null;
    this._audioChunks = [];
    this._isRecording = false;
    this.btnVoice.classList.remove("recording");
    this.btnVoice.title = t("input.voiceStart");
  }

  private updateUIState(running: boolean): void {
    if (running) {
      this.welcomeScreen.classList.add("hidden");
      this.messageList.classList.remove("hidden");
    }
  }

  private initKeybindActions(): void {
    const a = this._keybindActions;

    // ── Application ──────────────────────────────────────────────────
    a["quit"] = () => (window as any).electronAPI?.windowClose?.();
    a["devtools"] = () => {
      const devMode = (typeof localStorage !== "undefined") && localStorage.getItem("encre-dev-mode") === "1";
      if (!devMode) return;
      (window as any).electronAPI?.toggleDevTools?.();
    };
    a["reload"] = () => {
      send({ type: "list_sessions" });
      send({ type: "list_workspaces" });
      send({ type: "get_config" } as any);
      this.chat.render();
    };
    a["fullscreen"] = () => {
      if (document.fullscreenElement) {
        document.exitFullscreen();
      } else {
        document.documentElement.requestFullscreen();
      }
    };

    // ── Session Management ───────────────────────────────────────────
    const resumeSession = (sid: string) => {
      const requestId = crypto.randomUUID();
      setRequestedSessionId(sid, requestId);
      send({ type: "resume", session_id: sid, request_id: requestId });
    };
    a["new_session"] = () => {
      this.automationPanel.hide();
      this.exitTempChat();
      // Clear all residual content-area widgets (sub-agent view, tool
      // detail panel, queue card, model dropdown, …) before requesting
      // a brand-new session.  resetChat() below wipes the state slice
      // but does not touch the DOM directly.
      this.cleanupContentArea({ keepAutomationFlag: false });
      resetChat();
      const requestId = crypto.randomUUID();
      setRequestedSessionId("", requestId);
      send({ type: "new_session", request_id: requestId });
    };
    a["new_temp_chat"] = () => {
      if (getState().tempChat) return;
      this.automationPanel.hide();
      this.exitTempChat();
      this.cleanupContentArea({ keepAutomationFlag: false });
      resetChat();
      setTempChat(true);
      document.getElementById("btn-temp-chat")?.classList.add("active");
      const requestId = crypto.randomUUID();
      setRequestedSessionId("", requestId);
      send({ type: "new_session", request_id: requestId });
    };
    a["close_tab"] = () => {
      const app = document.getElementById("app");
      if (app?.classList.contains("settings-mode")) {
        this.settings.close();
      } else if (getState().sessionId) {
        const requestId = crypto.randomUUID();
        setRequestedSessionId("", requestId);
        send({ type: "new_session", request_id: requestId });
      }
    };
    a["next_session"] = () => {
      const sessions = getState().sessionsList;
      if (!sessions || sessions.length === 0) return;
      const currentId = getState().sessionId;
      const idx = sessions.findIndex(s => s.session_id === currentId);
      const next = sessions[(idx + 1) % sessions.length];
      if (next) resumeSession(next.session_id);
    };
    a["prev_session"] = () => {
      const sessions = getState().sessionsList;
      if (!sessions || sessions.length === 0) return;
      const currentId = getState().sessionId;
      const idx = sessions.findIndex(s => s.session_id === currentId);
      const prev = sessions[(idx - 1 + sessions.length) % sessions.length];
      if (prev) resumeSession(prev.session_id);
    };
    a["delete_session"] = async () => {
      const sid = getState().sessionId;
      if (!sid) return;
      const sessions = getState().sessionsList;
      const s = sessions?.find(x => x.session_id === sid);
      const name = s?.name || s?.preview || sid.slice(0, 8);
      const ok = await Dialog.confirm(t("session.confirmDeleteTitle"), t("session.confirmDelete", { name }));
      if (ok) {
        send({ type: "delete_session", session_id: sid });
        resetChat();
      }
    };
    a["rename_session"] = () => {
      const sid = getState().sessionId;
      if (sid) showRenameDialogForSession(sid);
    };
    a["export_session"] = () => {
      const sid = getState().sessionId;
      if (sid) send({ type: "export_session", session_id: sid });
    };

    // ── Message Operations ──────────────────────────────────────────
    a["edit_last_message"] = () => {
      const btns = document.querySelectorAll<HTMLElement>(".msg-rollback-btn");
      if (btns.length > 0) btns[btns.length - 1].click();
    };
    a["copy_last_response"] = () => {
      const msgs = getState().messages;
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === "assistant" && msgs[i].content) {
          navigator.clipboard.writeText(msgs[i].content).catch(() => {});
          break;
        }
      }
    };
    a["undo_message"] = () => {
      const btns = document.querySelectorAll<HTMLElement>(".msg-rollback-btn");
      if (btns.length > 0) btns[btns.length - 1].click();
    };
    a["delete_message"] = () => {
      const btns = document.querySelectorAll<HTMLElement>(".msg-delete-btn");
      if (btns.length > 0) btns[btns.length - 1].click();
    };
    const doRetry = (mode: "normal" | "detailed" | "concise") => {
      const msgs = getState().messages;
      const lastAssistantIdx = msgs.length - 1;
      if (lastAssistantIdx < 0 || msgs[lastAssistantIdx].role !== "assistant") return;
      let userMsgIdx = -1;
      for (let i = 0; i < lastAssistantIdx; i++) {
        if (msgs[i].role === "user") userMsgIdx++;
      }
      if (userMsgIdx < 0) return;
      const removed = new Set<string>();
      for (let i = lastAssistantIdx; i < msgs.length; i++) removed.add(msgs[i].id);
      removeBranchMessages(removed);
      startAssistantMessage();
      setRunning(true);
      const branchId = getState().activeBranchId;
      sendRetry(branchId, userMsgIdx, mode);
    };
    a["retry"] = () => doRetry("normal");
    a["retry_detailed"] = () => doRetry("detailed");
    a["retry_concise"] = () => doRetry("concise");

    // ── Search ──────────────────────────────────────────────────────
    a["search_global"] = () => this.search.open();
    a["search_settings"] = () => {
      const app = document.getElementById("app");
      if (app?.classList.contains("settings-mode")) {
        this.settings.focusSearch();
      }
    };

    // ── Settings ─────────────────────────────────────────────────────
    const openSetting = (panel: PanelId) => {
      this.automationPanel.hide();
      this.settings.open();
      this.settings.switchPanel(panel);
    };
    a["open_settings"] = () => openSetting("general");
    a["settings_general"] = () => openSetting("general");
    a["settings_models"] = () => openSetting("model");
    a["settings_skills"] = () => openSetting("skills");
    a["settings_mcp"] = () => openSetting("mcp");
    a["settings_agent"] = () => openSetting("agent");
    a["settings_index"] = () => openSetting("index");
    a["settings_rules"] = () => openSetting("rules");
    a["settings_memory"] = () => openSetting("memory");
    a["settings_usage"] = () => openSetting("usage");
    a["settings_about"] = () => openSetting("about");

    // ── Navigation / Sidebar ─────────────────────────────────────────
    a["toggle_sidebar"] = () => {
      this.userToggledSidebar = true;
      document.getElementById("app")?.classList.toggle("sidebar-collapsed");
    };
    a["view_chat"] = () => this.viewManager.switchTo("chat");
    a["view_automation"] = () => this.automationPanel.toggleAutomationView();

    // ── Input Area ───────────────────────────────────────────────────
    a["attach_file"] = () => { this.files.promptForFiles(); };
    a["upload_file"] = () => { this.files.promptForFiles(); };
    a["history_prev"] = () => {
      if (this._inputHistory.length === 0) return;
      if (this._inputHistoryIdx > 0) {
        this._inputHistoryIdx--;
        const mode = this.getCurrentMode();
        this.input.innerHTML = "";
        if (mode) this.insertModeChip(mode);
        document.execCommand("insertText", false, this._inputHistory[this._inputHistoryIdx]);
      }
    };
    a["history_next"] = () => {
      const mode = this.getCurrentMode();
      if (this._inputHistoryIdx < this._inputHistory.length - 1) {
        this._inputHistoryIdx++;
        this.input.innerHTML = "";
        if (mode) this.insertModeChip(mode);
        document.execCommand("insertText", false, this._inputHistory[this._inputHistoryIdx]);
      } else {
        this._inputHistoryIdx = this._inputHistory.length;
        this.input.innerHTML = "";
        if (mode) this.insertModeChip(mode);
      }
    };

    // ── Modes ────────────────────────────────────────────────────────
    a["toggle_plan_mode"] = () => {
      this.input.focus();
      document.execCommand("insertText", false, "/plan ");
    };
    a["toggle_spec_mode"] = () => {
      this.input.focus();
      document.execCommand("insertText", false, "/spec ");
    };
    a["cancel"] = () => this.cancel();

    // ── Panel Tabs (session inner sidebar) ───────────────────────────
    const ensureTab = (id: string) => {
      const tabs = this.sessionInner.getTabs();
      if (tabs.some((t: TabDef) => t.id === id)) {
        this.sessionInner.activateTab(id);
      } else {
        this.sessionInner.createTab(id);
      }
    };
    a["toggle_terminal"] = () => ensureTab("terminal");
    a["toggle_editor"] = () => ensureTab("editor");
    a["toggle_review"] = () => ensureTab("review");
    a["toggle_info"] = () => ensureTab("info");
    a["toggle_files"] = () => ensureTab("files");
    a["prev_tab"] = () => {
      const tabs = this.sessionInner.getTabs();
      if (tabs.length < 2) return;
      const active = this.sessionInner.getActiveTab();
      const idx = tabs.findIndex((t: TabDef) => t.id === active);
      const prev = tabs[(idx - 1 + tabs.length) % tabs.length];
      this.sessionInner.activateTab(prev.id);
    };
    a["next_tab"] = () => {
      const tabs = this.sessionInner.getTabs();
      if (tabs.length < 2) return;
      const active = this.sessionInner.getActiveTab();
      const idx = tabs.findIndex((t: TabDef) => t.id === active);
      const next = tabs[(idx + 1) % tabs.length];
      this.sessionInner.activateTab(next.id);
    };

    // ── Theme / Language / Voice ─────────────────────────────────────
    a["toggle_theme"] = () => {
      const current = getState().themePreference || "system";
      const next = current === "dark" ? "light" : current === "light" ? "system" : "dark";
      const label = next === "dark" ? "深色" : next === "light" ? "浅色" : "跟随系统";
      Dialog.confirm("切换主题", `确定切换到「${label}」主题？`).then(ok => {
        if (!ok) return;
        setThemePreference(next);
        if (next === "system") {
          const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
          setTheme(isDark ? "dark" : "light");
        } else {
          setTheme(next as "dark" | "light");
        }
        localStorage.setItem("encre-theme", next);
      });
    };
    a["toggle_language"] = () => {
      const current = (getState().settings.language as string) || "zh";
      const next = current === "zh" ? "en" : "zh";
      const label = next === "zh" ? "中文" : "English";
      Dialog.confirm("切换语言", `确定切换到「${label}」？`).then(ok => {
        if (!ok) return;
        const settings = { ...getState().settings, language: next };
        setSettings(settings);
        setLocale(next);
        send({ type: "configure", config: { language: next } });
      });
    };
    // ── Automation ───────────────────────────────────────────────────
    a["automation_open"] = () => this.automationPanel.toggleAutomationView();
    a["automation_new"] = () => {
      document.getElementById("automation-create-btn")?.click();
    };
    a["automation_run"] = () => {
      const firstEdit = document.querySelector<HTMLElement>('[data-action="edit"]');
      firstEdit?.click();
    };
    a["automation_toggle"] = () => {
      const firstToggle = document.querySelector<HTMLElement>(".auto-toggle");
      if (firstToggle) {
        firstToggle.click();
      }
    };
    a["automation_history"] = () => {
      const btn = document.querySelector<HTMLElement>("[data-automation-tab=\"history\"]");
      btn?.click();
    };

    // ── Workspace ────────────────────────────────────────────────────
    a["workspace_open"] = () => this.workspace.openFolder();
    a["workspace_close"] = () => this.workspace.forceExit();
    a["workspace_reindex"] = () => {
      send({ type: "reindex_workspace" } as any);
    };

    // ── Notifications ────────────────────────────────────────────────
    a["notifications_open"] = () => this.notifications.openPanel();
    a["notifications_clear"] = () => clearAllNotifications();
    a["show_shortcuts"] = () => this.toggleShortcutsCard();

  }

  private applyShortcutHints(): void {
    if (this._shortcutsApplied) return;
    const cfg = (getState().settings.keybinds as any);
    const binds: any[] = cfg?.keybinds || [];
    if (binds.length === 0) {
      if (!this._shortcutSub) this._shortcutSub = subscribe(() => this.applyShortcutHints());
      return;
    }
    this._shortcutsApplied = true;
    if (this._shortcutSub) { this._shortcutSub(); this._shortcutSub = undefined; }
    const els = document.querySelectorAll<HTMLElement>("[data-shortcut]");
    for (const el of els) {
      const id = el.getAttribute("data-shortcut");
      if (!id) continue;
      const shortcut = lookupShortcut(id);
      if (!shortcut) continue;
      const existingTitle = el.getAttribute("title") || el.getAttribute("data-i18n-title") || "";
      if (existingTitle) {
        el.setAttribute("title", augmentTitle(existingTitle, shortcut));
      }
    }
  }

  private toggleShortcutsCard(): void {
    const cfg = (getState().settings.keybinds as any);
    const binds: any[] = cfg?.keybinds || [];
    if (binds.length === 0) return;

    const scroll = document.createElement("div");
    scroll.className = "shortcuts-scroll";

    const grid = document.createElement("div");
    grid.className = "shortcuts-grid";

    const colDesc = document.createElement("div");
    colDesc.className = "sc-col sc-col-desc";
    colDesc.textContent = "Description";
    grid.appendChild(colDesc);

    const colKey = document.createElement("div");
    colKey.className = "sc-col sc-col-key";
    colKey.textContent = "Shortcut";
    grid.appendChild(colKey);

    const divider = document.createElement("div");
    divider.className = "sc-divider";
    grid.appendChild(divider);

    const categories = new Map<string, Array<{ id: string; keys: string[]; desc: string }>>();
    for (const b of binds) {
      const cat = b.category || "general";
      if (!categories.has(cat)) categories.set(cat, []);
      categories.get(cat)!.push({ id: b.id, keys: b.keys, desc: b.description || b.id });
    }

    const CAT_LABELS: Record<string, string> = {
      application: "Application",
      session: "Session",
      messages: "Messages",
      input: "Input",
      modes: "Modes",
      navigation: "Navigation",
      search: "Search",
      settings: "Settings",
      panels: "Panels",
      automation: "Automation",
      workspace: "Workspace",
      notifications: "Notifications",
      appearance: "Appearance",
      general: "General",
    };

    for (const [cat, items] of categories) {
      const cell = document.createElement("div");
      cell.className = "sc-category";
      cell.textContent = CAT_LABELS[cat] || cat.charAt(0).toUpperCase() + cat.slice(1);
      grid.appendChild(cell);

      for (const item of items) {
        const cellDesc = document.createElement("div");
        cellDesc.className = "sc-cell sc-cell-desc";
        cellDesc.textContent = t("shortcuts." + item.id);
        grid.appendChild(cellDesc);

        const keyText = item.keys && item.keys.length > 0
          ? formatShortcut(item.keys[0])
          : "—";
        const cellKey = document.createElement("div");
        cellKey.className = "sc-cell sc-cell-key";
        cellKey.textContent = keyText;
        grid.appendChild(cellKey);
      }
    }

    scroll.appendChild(grid);
    Dialog.showHtmlDialog("Keyboard Shortcuts", scroll);
  }

  private bindKeyboardShortcuts(): void {
    document.addEventListener("keydown", (e) => {
      const key = e.key;
      const mod = e.ctrlKey || e.metaKey;
      const alt = e.altKey;
      const shift = e.shiftKey;

      let parts: string[] = [];
      if (mod) parts.push("ctrlcmd");
      if (alt) parts.push("alt");
      if (shift) parts.push("shift");

      const mappedKey = key === "Escape" ? "escape"
        : key === " " ? "space"
        : key === "," ? ","
        : key === "." ? "."
        : key === "`" ? "`"
        : key === "=" ? "="
        : key === "-" ? "-"
        : key === "[" ? "["
        : key === "]" ? "]"
        : key === ";" ? ";"
        : key === "'" ? "'"
        : key === "\\" ? "\\"
        : key === "/" ? "/"
        : key.toLowerCase();
      parts.push(mappedKey);
      const pattern = parts.join("+");

      if (pattern === "escape") {
        this.settings.close();
        setActiveToolId(null);
        this.search.close();
        return;
      }

      const keybindsCfg = (getState().settings.keybinds as any);
      const binds: any[] = keybindsCfg?.keybinds || [];
      for (const kb of binds) {
        if (kb.keys && kb.keys.includes(pattern)) {
          if (kb.id === "search_settings") {
            const app = document.getElementById("app");
            if (!app?.classList.contains("settings-mode")) return;
          }
          const action = this._keybindActions[kb.id];
          if (action) {
            e.preventDefault();
            action();
            return;
          }
        }
      }
    });
  }

  private async initTheme(): Promise<void> {
    const stored = localStorage.getItem("encre-theme");
    if (stored === "dark" || stored === "light" || stored === "system") {
      setThemePreference(stored);
      setSettings({ ...getState().settings, theme: stored });
    }
    const pref = getState().themePreference;
    const applySystemTheme = () => {
      const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      setTheme(isDark ? "dark" : "light");
      this.applyThemeIcons(isDark);
    };

    if (pref === "dark") {
      setTheme("dark");
      this.applyThemeIcons(true);
    } else if (pref === "light") {
      setTheme("light");
      this.applyThemeIcons(false);
    } else {
      applySystemTheme();
    }

    window
      .matchMedia("(prefers-color-scheme: dark)")
      .addEventListener("change", (e) => {
        if (getState().themePreference === "system") {
          setTheme(e.matches ? "dark" : "light");
          this.applyThemeIcons(e.matches);
        }
      });
  }

  private applyThemeIcons(dark: boolean): void {
    const welcomeLogo = document.getElementById(
      "welcome-logo"
    ) as HTMLImageElement | null;
    if (welcomeLogo) {
      const iconOnly = dark ? "assets/yimiw.svg" : "assets/yimib.svg";
      welcomeLogo.src = iconOnly;
    }
  }
}

const app = new App();
app.start();

export function updateRunningUI(running: boolean): void {
  const btnSend = document.getElementById("btn-send") as HTMLButtonElement;
  const btnStop = document.getElementById("btn-stop") as HTMLButtonElement;
  const welcomeScreen = document.getElementById("welcome-screen");
  const messageList = document.getElementById("message-list");

  if (btnSend) btnSend.style.display = running ? "none" : "flex";
  if (btnStop) btnStop.style.display = running ? "flex" : "none";
  if (running && welcomeScreen) welcomeScreen.classList.add("hidden");
  if (running && messageList) messageList.classList.remove("hidden");
}
