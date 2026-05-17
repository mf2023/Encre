import { connect, send } from "./ws.js";
import { handleEvent, init as streamInit } from "./stream.js";
import {
  addUserMessage,
  startAssistantMessage,
  setRunning,
  setTheme,
  setActiveToolId,
  setSettings,
  getState,
  subscribe,
  resetChat,
} from "./state.js";
import { Chat } from "./chat.js";
import { Tools } from "./tools.js";
import { Permissions } from "./permissions.js";
import { Settings } from "./settings.js";
import { Files } from "./files.js";
import { Session } from "./session.js";
import { ViewManager } from "./viewmanager.js";
import { Search } from "./search.js";
import { Agents } from "./agents.js";
import { Plan } from "./plan.js";
import { Notifications } from "./notifications.js";

(window as any).__state_setActiveToolId = setActiveToolId;

class App {
  private chat: Chat;
  private tools: Tools;
  private permissions: Permissions;
  private settings: Settings;
  private files: Files;
  private session: Session;
  private viewManager: ViewManager;
  private plan: Plan;
  private notifications: Notifications;
  private search: Search;
  private input: HTMLTextAreaElement;
  private btnSend: HTMLButtonElement;
  private btnStop: HTMLButtonElement;
  private tokenCountEl: HTMLElement;
  private welcomeScreen: HTMLElement;
  private messageList: HTMLElement;
  private userToggledSidebar = false;

  constructor() {
    this.input = document.getElementById("prompt-input") as HTMLTextAreaElement;
    this.btnSend = document.getElementById("btn-send") as HTMLButtonElement;
    this.btnStop = document.getElementById("btn-stop") as HTMLButtonElement;
    this.tokenCountEl = document.getElementById("token-count")!;
    this.welcomeScreen = document.getElementById("welcome-screen")!;
    this.messageList = document.getElementById("message-list")!;

    this.chat = new Chat();
    this.tools = new Tools();
    this.permissions = new Permissions();
    this.settings = new Settings();
    this.files = new Files(this.input);
    this.session = new Session();
    this.viewManager = new ViewManager();
    this.search = new Search();
    new Agents();
    this.plan = new Plan();
    this.notifications = new Notifications();

    streamInit(this.chat, this.tools, this.permissions);
    this.bindInput();
    this.bindToolbarButtons();
    this.bindWindowControls();
    this.bindSearchOverlay();
    this.bindKeyboardShortcuts();
    this.initTheme();
    this.bindResponsiveSidebar();

    // Update stats display when telemetry changes
    subscribe(() => this.updateStats());

    // Auto-update send/stop button visibility when running state changes
    subscribe(() => {
      const running = getState().running;
      if (running) {
        this.btnSend.style.display = "none";
        this.btnStop.style.display = "flex";
        this.btnStop.classList.remove("cancelling");
        this.btnStop.style.pointerEvents = "";
      } else {
        this.btnSend.style.display = "flex";
        this.btnStop.style.display = "none";
        this.btnStop.classList.remove("cancelling");
        this.btnStop.style.pointerEvents = "";
      }
      this.btnSend.disabled = this.input.value.trim().length === 0;
    });

    // Show quick-chips only on welcome screen (no messages), hide in conversation
    subscribe(() => {
      const chips = document.getElementById("quick-chips");
      if (chips) {
        const hasMessages = getState().messages.length > 0;
        chips.classList.toggle("hidden", hasMessages);
      }
    });

    // Re-fetch models when backend or base_url changes
    let lastBackend = getState().settings.backend;
    let lastBaseUrl = getState().settings.base_url;
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
  }

  private updateStats(): void {
    const s = getState();
    // Accumulate total tokens across all assistant messages
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
      this.tokenCountEl.textContent = `${s.telemetry.total_tool_calls} tools · ${this.fmtTokens(totalAll)} tokens`;
      this.tokenCountEl.title =
        `Input: ${this.fmtTokens(totalIn)} | Output: ${this.fmtTokens(totalOut)} | ` +
        `Turns: ${s.telemetry.total_turns} | ` +
        `Duration: ${s.telemetry.session_duration_s.toFixed(0)}s`;
    } else if (totalAll > 0) {
      this.tokenCountEl.textContent = `${this.fmtTokens(totalAll)} tokens`;
      this.tokenCountEl.title = `Input: ${this.fmtTokens(totalIn)} | Output: ${this.fmtTokens(totalOut)}`;
    } else {
      this.tokenCountEl.textContent = "";
      this.tokenCountEl.title = "";
    }
  }

  private fmtTokens(n: number): string {
    if (n >= 1000) return (n / 1000).toFixed(1) + "k";
    return String(n);
  }

  async start(): Promise<void> {
    await connect(handleEvent);
    if (getState().connected) {
      // Fetch available models from the provider and server config
      this.fetchModels();
      send({ type: "get_config" });
    }
  }

  private bindInput(): void {
    this.btnSend.addEventListener("click", () => this.submit());
    this.btnStop.addEventListener("click", () => this.cancel());
    this.input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.submit();
      }
      if (e.key === "Escape") {
        this.cancel();
      }
    });

    this.input.addEventListener("input", () => {
      this.input.style.height = "auto";
      const h = Math.min(Math.max(this.input.scrollHeight, 56), 320);
      this.input.style.height = `${h}px`;
      // Disable send when input is empty
      this.btnSend.disabled = this.input.value.trim().length === 0;
    });
  }

  private bindToolbarButtons(): void {
    const toggleSidebar = document.getElementById("btn-toggle-sidebar");
    toggleSidebar?.addEventListener("click", () => {
      this.userToggledSidebar = true;
      document.getElementById("app")?.classList.toggle("sidebar-collapsed");
    });

    const newTaskBtn = document.querySelector('.nav-item[data-view="chat"]');
    newTaskBtn?.addEventListener("click", () => {
      resetChat();
      send({ type: "new_session" });
    });

    const btnSettingsTrigger = document.getElementById("btn-settings-trigger");
    btnSettingsTrigger?.addEventListener("click", () => {
      this.settings.open();
    });

    const btnFilePicker = document.getElementById("btn-file-picker");
    btnFilePicker?.addEventListener("click", async () => {
      await this.files.promptForFiles();
    });

    const btnAttach = document.getElementById("btn-attach");
    btnAttach?.addEventListener("click", async () => {
      await this.files.promptForFiles();
    });

    // Mention (@) toggle
    const btnMention = document.getElementById("btn-mention");
    const mentionBar = document.getElementById("mention-bar");
    btnMention?.addEventListener("click", () => {
      const hidden = mentionBar?.classList.toggle("hidden");
      if (!hidden) {
        btnMention.classList.add("active");
      } else {
        btnMention.classList.remove("active");
      }
    });

    document.getElementById("mention-close")?.addEventListener("click", () => {
      document.getElementById("mention-bar")?.classList.add("hidden");
      document.getElementById("btn-mention")?.classList.remove("active");
    });

    // Enhance / Voice placeholders
    const showComingSoon = () => {
      const toast = document.createElement("div");
      toast.className = "error-toast";
      toast.textContent = "Coming soon";
      toast.style.background = "var(--accent)";
      document.body.appendChild(toast);
      setTimeout(() => toast.remove(), 2000);
    };
    document.getElementById("btn-enhance")?.addEventListener("click", showComingSoon);
    document.getElementById("btn-voice")?.addEventListener("click", showComingSoon);

    this.bindInputModelSelector();
  }

  private bindInputModelSelector(): void {
    const selector = document.getElementById("input-model-selector");
    const nameEl = document.getElementById("input-model-name");
    const dropdown = document.getElementById("input-model-dropdown");
    if (!selector || !dropdown || !nameEl) return;

    const render = () => {
      const st = getState();
      const models = st.modelConfigs;
      const activeIdx = st.activeModelIndex;
      const active = models[activeIdx];
      nameEl.textContent = active?.name || active?.model_id || "Model";

      if (models.length === 0) {
        dropdown.innerHTML = `<div class="model-dropdown-item muted">No models configured</div>`;
        return;
      }

      dropdown.innerHTML = models
        .map((m, i) => {
          const sel = i === activeIdx ? " selected" : "";
          return `<div class="model-dropdown-item${sel}" data-idx="${i}">${this.esc(m.name || m.model_id)}<span class="model-dropdown-sub">${this.esc(m.backend_type)} / ${this.esc(m.model_id)}</span></div>`;
        })
        .join("");
      dropdown.querySelectorAll(".model-dropdown-item[data-idx]").forEach((item) => {
        item.addEventListener("click", (e) => {
          e.stopPropagation();
          const idx = parseInt((item as HTMLElement).dataset.idx || "0");
          send({ type: "set_active_model", model_index: idx });
          nameEl.textContent = models[idx]?.name || models[idx]?.model_id || "Model";
          dropdown.classList.add("hidden");
        });
      });
    };

    selector.addEventListener("click", (e) => {
      e.stopPropagation();
      if (dropdown.classList.contains("hidden")) {
        render();
        dropdown.classList.remove("hidden");
      } else {
        dropdown.classList.add("hidden");
      }
    });

    document.addEventListener("click", (e) => {
      if (!selector.contains(e.target as Node) && !dropdown.contains(e.target as Node)) {
        dropdown.classList.add("hidden");
      }
    });

    subscribe(() => {
      render();
      if (!dropdown.classList.contains("hidden")) {
        render();
      }
    });

    render();
  }

  private esc(s: string): string {
    const el = document.createElement("span");
    el.textContent = s;
    return el.innerHTML;
  }

  private fetchModels(): void {
    send({ type: "list_models" });
  }

  private bindWindowControls(): void {
    const btnMinimize = document.getElementById("btn-minimize");
    const btnMaximize = document.getElementById("btn-maximize");
    const btnClose = document.getElementById("btn-close");
    const btnDevMode = document.getElementById("btn-dev-mode");

    btnMinimize?.addEventListener("click", async () => {
      await window.electronAPI?.windowMinimize();
    });

    btnMaximize?.addEventListener("click", async () => {
      await window.electronAPI?.windowMaximize();
    });

    btnClose?.addEventListener("click", async () => {
      await window.electronAPI?.windowClose();
    });

    btnDevMode?.addEventListener("click", async () => {
      await window.electronAPI?.toggleDevTools();
    });
  }

  private bindSearchOverlay(): void {
    const btn = document.getElementById("btn-sidebar-search");
    btn?.addEventListener("click", () => this.search.open());

    const overlay = document.getElementById("search-overlay");
    overlay?.addEventListener("click", (e) => {
      if (e.target === overlay) this.search.close();
    });
  }

  private bindResponsiveSidebar(): void {
    const app = document.getElementById("app");
    const mainArea = document.getElementById("main-area");
    if (!app) return;
    const NARROW = 920;
    let wasNarrow = window.innerWidth < NARROW;

    const isNarrow = () => window.innerWidth < NARROW;

    const check = () => {
      const narrow = isNarrow();
      if (narrow && !wasNarrow && !this.userToggledSidebar) {
        app.classList.add("sidebar-collapsed");
      } else if (!narrow && wasNarrow) {
        app.classList.remove("sidebar-collapsed");
        this.userToggledSidebar = false;
      }
      wasNarrow = narrow;
    };

    new ResizeObserver(check).observe(document.documentElement);
    check();

    mainArea?.addEventListener("click", () => {
      if (isNarrow() && !app.classList.contains("sidebar-collapsed")) {
        app.classList.add("sidebar-collapsed");
      }
    });
  }

  private submit(): void {
    const text = this.input.value.trim();
    if (!text) return;

    const state = getState();
    if (state.running) return;

    addUserMessage(text);
    startAssistantMessage();
    setRunning(true);
    this.updateUIState(true);

    send({
      type: "run",
      prompt: text,
      session_id: state.sessionId || undefined,
    });

    this.input.value = "";
    this.input.style.height = "56px";
    this.chat.render();
  }

  private cancel(): void {
    const s = getState();
    if (!s.running) return;
    // Show cancelling visual state — server will send finish event
    this.btnStop.classList.add("cancelling");
    this.btnStop.style.pointerEvents = "none";
    send({
      type: "cancel",
      session_id: s.sessionId,
    });
  }

  private updateUIState(running: boolean): void {
    if (running) {
      this.welcomeScreen.classList.add("hidden");
      this.messageList.classList.remove("hidden");
    }
  }

  private bindKeyboardShortcuts(): void {
    document.addEventListener("keydown", (e) => {
      const mod = e.ctrlKey || e.metaKey;

      if (mod && e.key === "k") {
        e.preventDefault();
        this.search.open();
      } else if (mod && e.key === ",") {
        e.preventDefault();
        this.settings.open();
      } else if (mod && e.key === "l") {
        e.preventDefault();
        resetChat();
        send({ type: "new_session" });
      } else if (e.key === "Escape") {
        this.settings.close();
        this.permissions.hide();
        setActiveToolId(null);
        this.search.close();
      }
    });
  }

  private showSavedToast(key: string): void {
    const existing = document.querySelector(".settings-toast");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.className = "settings-toast";
    toast.textContent = `✓ ${key} saved`;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 1800);
  }

  private async initTheme(): Promise<void> {
    const stored = localStorage.getItem("yim-theme");
    if (stored === "dark" || stored === "light" || stored === "system") {
      setThemePreference(stored);
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
