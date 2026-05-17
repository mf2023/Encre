import { getState, setSettings, setTheme, setThemePreference } from "./state.js";
import { send } from "./ws.js";
import { setModelConfigs } from "./state.js";
import type { ModelConfigMeta, MCPServerConfig, SkillInfo } from "./types.js";

type PanelId = "general" | "model" | "skills" | "mcp" | "agent" | "about";

const BACKEND_OPTIONS = ["deepseek", "anthropic", "openai", "google", "groq", "ollama"];
const PERMISSION_OPTIONS = ["default", "accept_edits", "plan", "auto", "dont_ask", "bypass"];

export class Settings {
  private overlay: HTMLElement;
  private nav: HTMLElement;
  private currentPanel: PanelId = "general";
  private panels: Record<PanelId | "modelCreate", HTMLElement>;
  private modelCreateActive = false;

  constructor() {
    this.overlay = document.getElementById("settings-overlay")!;
    this.nav = document.getElementById("settings-nav")!;
    this.panels = {
      general: document.getElementById("panel-general")!,
      model: document.getElementById("panel-model")!,
      modelCreate: document.getElementById("panel-model-create")!,
      skills: document.getElementById("panel-skills")!,
      mcp: document.getElementById("panel-mcp")!,
      agent: document.getElementById("panel-agent")!,
      about: document.getElementById("panel-about")!,
    };

    document.getElementById("btn-settings-trigger")?.addEventListener("click", () => this.open());
    document.getElementById("btn-settings-close")?.addEventListener("click", () => this.close());
    this.overlay.addEventListener("click", (e) => {
      if (e.target === this.overlay) this.close();
    });
    this.nav.addEventListener("click", (e) => {
      const target = (e.target as HTMLElement).closest(".settings-nav-item") as HTMLElement | null;
      if (!target) return;
      const panel = target.getAttribute("data-panel") as PanelId;
      if (panel) this.switchPanel(panel);
    });
  }

  open(): void {
    this.modelCreateActive = false;
    send({ type: "get_config" } as any);
    this.renderAll();
    this.switchPanel(this.currentPanel);
    this.overlay.classList.remove("hidden");
  }

  close(): void {
    this.overlay.classList.add("hidden");
  }

  switchPanel(id: PanelId): void {
    this.currentPanel = id;
    this.modelCreateActive = false;

    this.nav.querySelectorAll(".settings-nav-item").forEach((item) => {
      item.classList.toggle("active", item.getAttribute("data-panel") === id);
    });

    Object.entries(this.panels).forEach(([key, el]) => {
      el.classList.toggle("active", false);
    });

    if (id === "model") {
      this.panels.model.classList.add("active");
    } else {
      this.panels[id].classList.add("active");
    }
  }

  private showModelList(): void {
    this.modelCreateActive = false;
    this.panels.modelCreate.classList.remove("active");
    this.panels.model.classList.add("active");
  }

  private showModelCreate(): void {
    this.modelCreateActive = true;
    this.panels.model.classList.remove("active");
    this.panels.modelCreate.classList.add("active");
    this.renderModelCreate();
  }

  renderAll(): void {
    this.renderGeneral();
    this.renderModel();
    this.renderSkills();
    this.renderMcp();
    this.renderAgent();
    this.renderAbout();
  }

  private renderGeneral(): void {
    const s = getState().settings;
    const currentTheme = (s.theme as string) || "system";
    const themes = [
      { id: "light", icon: "sun", label: "浅色" },
      { id: "dark", icon: "moon", label: "深色" },
      { id: "system", icon: "monitor", label: "跟随系统" },
    ];
    let html = "";
    for (const t of themes) {
      const active = t.id === currentTheme ? " active" : "";
      html += `<div class="theme-card${active}" data-theme-val="${t.id}">
        <i data-lucide="${t.icon}" class="lucide"></i>
        <span class="theme-card-label">${t.label}</span>
      </div>`;
    }
    this.panels.general.innerHTML = `
      <div class="settings-section">
        <div class="settings-section-title">主题</div>
        <div class="theme-cards">${html}</div>
      </div>`;
    this.panels.general.querySelectorAll(".theme-card").forEach((card) => {
      card.addEventListener("click", () => {
        const val = card.getAttribute("data-theme-val");
        if (val) this.saveTheme(val);
      });
    });
    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panels.general });
    }
  }

  private renderModel(): void {
    const st = getState();
    const models = st.modelConfigs;
    const activeIdx = st.activeModelIndex;

    let listHtml = "";
    for (let i = 0; i < models.length; i++) {
      const m = models[i];
      const isActive = i === activeIdx;
      listHtml += `<div class="model-card${isActive ? " model-active" : ""}" data-model-idx="${i}">
        <div class="model-card-header">
          <div class="model-card-info">
            <span class="model-card-name">${this.esc(m.name || "Unnamed")}</span>
            <span class="model-card-detail">${this.esc(m.backend_type)} / ${this.esc(m.model_id)}</span>
          </div>
          <div class="model-card-actions">
            ${!isActive ? `<button class="btn-model-set-active" data-action="activate" data-idx="${i}" title="Set as active">Set Active</button>` : `<span class="model-active-badge">Active</span>`}
            <button class="btn-model-delete" data-action="delete" data-idx="${i}" title="Delete model">&times;</button>
          </div>
        </div>
      </div>`;
    }

    if (models.length === 0) {
      listHtml = `<div class="model-empty">暂无已配置的模型。</div>`;
    }

    this.panels.model.innerHTML = `
      <div class="settings-section">
        <div class="settings-section-title">已配置的模型</div>
        <div class="model-list">${listHtml}</div>
      </div>
      <div class="settings-section" style="text-align:center;">
        <button class="btn-add-model-page" id="btn-goto-create-model">+ 创建模型配置</button>
      </div>`;

    this.panels.model.querySelectorAll("[data-action='activate']").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = parseInt((btn as HTMLElement).getAttribute("data-idx") || "0");
        send({ type: "set_active_model", model_index: idx });
        this.showToast("Model activated");
      });
    });

    this.panels.model.querySelectorAll("[data-action='delete']").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = parseInt((btn as HTMLElement).getAttribute("data-idx") || "0");
        send({ type: "delete_model", model_index: idx });
        this.showToast("Model deleted");
      });
    });

    document.getElementById("btn-goto-create-model")?.addEventListener("click", () => {
      this.showModelCreate();
    });
  }

  private renderModelCreate(): void {
    this.panels.modelCreate.innerHTML = `
      <div class="subpage-header">
        <button class="btn-subpage-back" id="btn-back-model-list">
          <i data-lucide="arrow-left" class="lucide"></i>
          <span>返回模型列表</span>
        </button>
        <span class="subpage-title">创建模型配置</span>
      </div>
      <div class="settings-section">
        <div class="setting-row">
          <label for="new-model-name">显示名称</label>
          <input type="text" id="new-model-name" placeholder="e.g. DeepSeek V4-Flash" />
        </div>
        <div class="setting-row">
          <label for="new-model-id">Model ID</label>
          <input type="text" id="new-model-id" placeholder="e.g. deepseek-chat" />
        </div>
        <div class="setting-row">
          <label for="new-model-backend">Backend</label>
          <select id="new-model-backend">${BACKEND_OPTIONS.map(o => `<option value="${o}">${o}</option>`).join("")}</select>
        </div>
        <div class="setting-row">
          <label for="new-model-apikey">API Key</label>
          <input type="password" id="new-model-apikey" placeholder="sk-..." />
        </div>
        <div class="setting-row">
          <label for="new-model-url">Base URL (optional)</label>
          <input type="text" id="new-model-url" placeholder="https://api.deepseek.com" />
        </div>
        <div class="setting-row">
          <label for="new-model-tokens">Max Tokens</label>
          <input type="number" id="new-model-tokens" value="4096" />
        </div>
        <button class="btn-add-model" id="btn-add-model">保存配置</button>
      </div>`;

    document.getElementById("btn-back-model-list")?.addEventListener("click", () => {
      this.renderModel();
      this.showModelList();
    });

    document.getElementById("btn-add-model")?.addEventListener("click", () => {
      const name = (document.getElementById("new-model-name") as HTMLInputElement)?.value.trim();
      const modelId = (document.getElementById("new-model-id") as HTMLInputElement)?.value.trim();
      const backend = (document.getElementById("new-model-backend") as HTMLSelectElement)?.value;
      const apiKey = (document.getElementById("new-model-apikey") as HTMLInputElement)?.value.trim();
      const baseUrl = (document.getElementById("new-model-url") as HTMLInputElement)?.value.trim();
      const maxTokens = parseInt((document.getElementById("new-model-tokens") as HTMLInputElement)?.value || "4096");
      if (!name || !modelId) {
        this.showToast("Name and Model ID are required");
        return;
      }
      const currentModels = [...getState().modelConfigs];
      currentModels.push({
        name, model_id: modelId, backend_type: backend,
        api_key: apiKey, base_url: baseUrl, max_tokens: maxTokens, enabled: true,
      });
      const activeIdx = currentModels.length - 1;
      setModelConfigs(currentModels, activeIdx);
      send({ type: "update_models", models: currentModels, active_model_index: activeIdx });
      this.showToast("Model created");
      this.renderModel();
      this.showModelList();
    });

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panels.modelCreate });
    }
  }

  private renderSkills(): void {
    const st = getState();
    const skills: SkillInfo[] = st.skillsList;
    const enabled = new Set(st.enabledSkills);

    let html = `<div class="settings-section">
      <div class="settings-section-title">Skills 管理</div>
      <div class="skills-instructions">启用或禁用内置 Skills。禁用后，该 Skill 不会出现在 Agent 的工作流中。</div>
      <div class="skill-list">`;

    if (skills.length === 0) {
      html += `<div class="model-empty">No skills loaded. Wait for server config or add bundled skills.</div>`;
    }

    for (const sk of skills) {
      const isOn = enabled.has(sk.name);
      html += `<div class="skill-card" data-skill="${this.esc(sk.name)}">
        <div class="skill-card-left">
          <span class="skill-name">${this.esc(sk.name)}</span>
          <span class="skill-desc">${this.esc(sk.description)}</span>
          ${sk.aliases && sk.aliases.length > 0 ? `<span class="skill-aliases">Aliases: ${sk.aliases.join(", ")}</span>` : ""}
        </div>
        <label class="toggle-switch">
          <input type="checkbox" class="skill-toggle" data-skill="${this.esc(sk.name)}" ${isOn ? "checked" : ""} />
          <span class="toggle-slider"></span>
        </label>
      </div>`;
    }

    html += `</div></div>`;
    this.panels.skills.innerHTML = html;

    this.panels.skills.querySelectorAll(".skill-toggle").forEach((cb) => {
      cb.addEventListener("change", () => {
        const checked = new Set<string>();
        this.panels.skills.querySelectorAll(".skill-toggle").forEach((el) => {
          if ((el as HTMLInputElement).checked) {
            checked.add((el as HTMLInputElement).getAttribute("data-skill") || "");
          }
        });
        send({ type: "update_skills", enabled_skills: Array.from(checked) });
        this.showToast("Skills updated");
      });
    });
  }

  private renderMcp(): void {
    const st = getState();
    const servers: MCPServerConfig[] = st.mcpServers || [];

    let listHtml = "";
    for (let i = 0; i < servers.length; i++) {
      const srv = servers[i];
      listHtml += `<div class="mcp-card">
        <div class="mcp-card-info">
          <span class="mcp-name">${this.esc(srv.name)}</span>
          <code class="mcp-cmd">${this.esc(srv.command)} ${this.esc((srv.args || []).join(" "))}</code>
        </div>
        <button class="btn-mcp-delete" data-action="delete-mcp" data-idx="${i}" title="Remove server">&times;</button>
      </div>`;
    }
    if (servers.length === 0) {
      listHtml = `<div class="model-empty">No MCP servers configured.</div>`;
    }

    this.panels.mcp.innerHTML = `
      <div class="settings-section">
        <div class="settings-section-title">MCP Servers</div>
        <div class="skills-instructions">MCP (Model Context Protocol) 服务器允许 Agent 扩展额外的工具能力。</div>
        <div class="mcp-list">${listHtml}</div>
      </div>
      <div class="settings-section">
        <div class="settings-section-title">添加 MCP Server</div>
        <div class="setting-row">
          <label for="new-mcp-name">Server Name</label>
          <input type="text" id="new-mcp-name" placeholder="e.g. filesystem-server" />
        </div>
        <div class="setting-row">
          <label for="new-mcp-cmd">Command</label>
          <input type="text" id="new-mcp-cmd" placeholder="e.g. npx -y @modelcontextprotocol/server-filesystem" />
        </div>
        <button class="btn-add-model" id="btn-add-mcp">+ 添加 MCP Server</button>
      </div>`;

    this.panels.mcp.querySelectorAll("[data-action='delete-mcp']").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = parseInt((btn as HTMLElement).getAttribute("data-idx") || "0");
        const current = [...(getState().mcpServers || [])];
        current.splice(idx, 1);
        send({ type: "update_mcp", mcp_servers: current });
        this.showToast("MCP server removed");
      });
    });

    document.getElementById("btn-add-mcp")?.addEventListener("click", () => {
      const name = (document.getElementById("new-mcp-name") as HTMLInputElement)?.value.trim();
      const cmd = (document.getElementById("new-mcp-cmd") as HTMLInputElement)?.value.trim();
      if (!name || !cmd) return;
      const parts = cmd.split(/\s+/);
      const command = parts[0];
      const args = parts.slice(1);
      const current = [...(getState().mcpServers || [])];
      current.push({ name, command, args, enabled: true });
      send({ type: "update_mcp", mcp_servers: current });
      this.showToast("MCP server added");
    });
  }

  private renderAgent(): void {
    const ag = getState().agentConfig;

    this.panels.agent.innerHTML = `
      <div class="settings-section">
        <div class="settings-section-title">Agent 行为配置</div>
        <div class="setting-row">
          <label for="agent-system-prompt">System Prompt</label>
          <textarea id="agent-system-prompt" class="setting-textarea" placeholder="Custom system prompt for the agent...">${this.esc(ag.system_prompt)}</textarea>
        </div>
        <div class="setting-row">
          <label for="agent-specialty">默认专长</label>
          <select id="agent-specialty">
            <option value="general"${ag.specialty === "general" ? " selected" : ""}>General</option>
            <option value="coding"${ag.specialty === "coding" ? " selected" : ""}>Coding</option>
            <option value="research"${ag.specialty === "research" ? " selected" : ""}>Research</option>
            <option value="data"${ag.specialty === "data" ? " selected" : ""}>Data Analysis</option>
          </select>
        </div>
        <div class="setting-row">
          <label for="agent-permission-mode">Permission Mode</label>
          <select id="agent-permission-mode">
            ${PERMISSION_OPTIONS.map(o => `<option value="${o}"${ag.permission_mode === o ? " selected" : ""}>${o}</option>`).join("")}
          </select>
        </div>
        <div class="setting-row">
          <label for="agent-max-turns">Max Turns</label>
          <input type="number" id="agent-max-turns" value="${ag.max_turns}" min="1" max="200" />
        </div>
        <button class="btn-add-model" id="btn-save-agent">保存 Agent 配置</button>
      </div>`;

    document.getElementById("btn-save-agent")?.addEventListener("click", () => {
      const systemPrompt = (document.getElementById("agent-system-prompt") as HTMLTextAreaElement)?.value || "";
      const specialty = (document.getElementById("agent-specialty") as HTMLSelectElement)?.value || "general";
      const permMode = (document.getElementById("agent-permission-mode") as HTMLSelectElement)?.value || "default";
      const maxTurns = parseInt((document.getElementById("agent-max-turns") as HTMLInputElement)?.value || "25");
      send({
        type: "update_agent",
        system_prompt: systemPrompt,
        specialty,
        permission_mode: permMode,
        max_turns: maxTurns,
      });
      this.showToast("Agent config saved");
    });
  }

  private renderAbout(): void {
    const isDark = getState().theme === "dark";
    const logoSrc = isDark ? "assets/yimw.svg" : "assets/yimb.svg";
    this.panels.about.innerHTML = `
      <div class="about-top">
        <div class="about-brand">
          <img class="about-logo" src="${logoSrc}" alt="Yim" />
        </div>
        <div class="about-desc">
          A general-purpose AI agent core library.<br>
          Backend-agnostic, multi-provider agent framework.
        </div>
      </div>
      <div class="about-copyright">
        Copyright &copy; 2024-2026 Dunimd. All Rights Reserved.
      </div>`;
  }

  private saveTheme(value: string): void {
    const current = { ...getState().settings, theme: value };
    setSettings(current);
    setThemePreference(value as "system" | "dark" | "light");
    if (value === "dark") setTheme("dark");
    else if (value === "light") setTheme("light");
    else {
      const isDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      setTheme(isDark ? "dark" : "light");
    }
    this.renderGeneral();
    this.showToast("Theme saved");
    localStorage.setItem("yim-theme", value);
    send({ type: "configure", config: { theme: value } });
  }

  private showToast(msg: string): void {
    const existing = document.querySelector(".settings-toast");
    if (existing) existing.remove();
    const toast = document.createElement("div");
    toast.className = "settings-toast";
    toast.textContent = `✓ ${msg}`;
    this.overlay.appendChild(toast);
    setTimeout(() => toast.remove(), 1800);
  }

  private esc(s: string): string {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
}
