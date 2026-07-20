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

import { getState, setSettings, setCustomCommands, setTheme, setThemePreference, setPermissionPolicies, subscribe, showToast, isEnabled } from "./state.js";
import { send } from "./ws.js";
import { waitForModelValidation, onAdapterTestResult, onWechatScanResult } from "./stream.js";
import { setModelConfigs, setMcpServers, setSkillsList, setSubAgents } from "./state.js";
import type { ModelConfigMeta, MCPServerConfig, SkillInfo, ModelCatalog, McpCatalog, McpProviderEntry, ProviderEntry, ProfileData, CustomCommand, UsageStatsSessionEntry } from "./types.js";
import { Dialog } from "./dialog.js";
import { t, initLocale, setLocale, getLocale, clearLocaleCache, onLocaleChange, type Locale } from "./i18n.js";
import { applyServerCommands } from "./slash_commands.js";
import { renderMarkdown } from "./chat.js";
import { PLATFORM_ICONS } from "./icons.js";
import { formatShortcut } from "./shortcutDisplay.js";
import { Chart, registerables } from "chart.js";
Chart.register(...registerables);
import { showTooltipAt, hideTooltip } from "./tooltip.js";

/** Wraps an async operation with a loading spinner on the button. */
export async function withLoading<T>(btn: HTMLButtonElement, fn: () => Promise<T>): Promise<T> {
  const origText = btn.textContent || "";
  const origDisabled = btn.disabled;
  btn.innerHTML = `<span class="btn-loading-icon"><i data-lucide="loader" style="width:14px;height:14px"></i></span> ${origText}`;
  btn.classList.add("btn-loading");
  btn.disabled = true;
  if (typeof (window as any).lucide !== "undefined") {
    (window as any).lucide.createIcons({ root: btn });
  }
  try {
    return await fn();
  } finally {
    btn.innerHTML = origText;
    btn.classList.remove("btn-loading");
    btn.disabled = origDisabled;
  }
}

initLocale();

const APP_VERSION = "0.2.0-pre.1";

export type PanelId = "general" | "usage" | "shortcuts" | "storage" | "model" | "gateway" | "index" | "skills" | "rules" | "permissions" | "mcp" | "agent" | "about" | "developer" | "memory";

const DEV_MODE_STORAGE_KEY = "encre-dev-mode";
const DEV_TAP_THRESHOLD = 7;
const DEV_TAP_RESET_MS = 2500;
let _devTapCount = 0;
let _devTapTimer: number = 0;

const EE_TAP_THRESHOLD = 5;
const EE_TAP_RESET_MS = 3000;
let _eeTapCount = 0;
let _eeTapTimer: number = 0;

function isDevModeEnabled(): boolean {
  try {
    return localStorage.getItem(DEV_MODE_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function setDevModeEnabled(enabled: boolean): void {
  try {
    if (enabled) localStorage.setItem(DEV_MODE_STORAGE_KEY, "1");
    else localStorage.removeItem(DEV_MODE_STORAGE_KEY);
  } catch {
    // localStorage unavailable — fail silently
  }
}

const PERMISSION_OPTIONS = ["default", "accept_edits", "plan", "auto", "dont_ask", "bypass"];

interface DropdownOption { id: string; label: string }

export class Settings {
  private nav: HTMLElement;
  private currentPanel: PanelId = "general";
  private _expandedAdapterId: string | null = null;
  private _adapterTestResults: Record<string, {success: boolean, message: string}> = {};
  private panels: Record<PanelId, HTMLElement>;
  private searchInput: HTMLInputElement;
  private searchTimer: number = 0;
  private _versions: { desktop: string; agent: string } | null = null;
  private _usageBarChart: Chart | null = null;
  private _usageBarChartData: {
    labels: string[];
    datasets: any[];
  } | null = null;
  private _usageGroupBy: "model" | "channel" = "model";
  private _recordingShortcutId: string | null = null;
  private _captureHandler: ((ev: KeyboardEvent) => void) | null = null;

  constructor() {
    this.nav = document.querySelector(".sidebar-settings-items")!;
    this.panels = {
      general: document.getElementById("panel-general")!,
      usage: document.getElementById("panel-usage")!,
      shortcuts: document.getElementById("panel-shortcuts")!,
      storage: document.getElementById("panel-storage")!,
      model: document.getElementById("panel-model")!,
      gateway: document.getElementById("panel-gateway")!,
      index: document.getElementById("panel-index")!,
      skills: document.getElementById("panel-skills")!,
      rules: document.getElementById("panel-rules")!,
      permissions: document.getElementById("panel-permissions")!,
      mcp: document.getElementById("panel-mcp")!,
      agent: document.getElementById("panel-agent")!,
      about: document.getElementById("panel-about")!,
      developer: document.getElementById("panel-developer")!,
      memory: document.getElementById("panel-memory")!,
    };

    this.searchInput = document.querySelector(".sidebar-settings-search-input") as HTMLInputElement;
    this.searchInput?.addEventListener("input", () => this.onSearchInput());

    document.getElementById("btn-settings-back")?.addEventListener("click", () => this.close());

    this.bindVersionTapUnlock();
    this.loadVersions();

    this.nav.addEventListener("click", (e) => {
      const target = (e.target as HTMLElement).closest(".settings-nav-item") as HTMLElement | null;
      if (!target) return;
      const panel = target.getAttribute("data-panel") as PanelId;
      if (panel) this.switchPanel(panel);
    });

    // Close any open dropdowns when clicking outside
    document.addEventListener("click", (e) => {
      const target = e.target as Node;
      document.querySelectorAll(".settings-dropdown.open").forEach((dd) => {
        const wrap = dd.closest(".settings-dropdown-wrap");
        if (wrap && !wrap.contains(target)) {
          dd.classList.remove("open");
        }
      });
    });

    // ── Event delegation on panel containers ─────────────────────────
    // These survive innerHTML replacement — no need to re-bind after render.

    // Index panel: document add/remove
    this.panels.index.addEventListener("click", (e) => {
      console.log("[DEBUG index] click fired, target:", (e.target as HTMLElement).className, "tag:", (e.target as HTMLElement).tagName);
      const target = e.target as HTMLElement;

      // Add document dropdown trigger
      const trigger = target.closest("#doc-add-trigger");
      if (trigger) {
        e.stopPropagation();
        const dd = document.getElementById("doc-add-dropdown");
        if (dd) {
          const isOpen = dd.classList.contains("open");
          document.querySelectorAll(".settings-dropdown.open").forEach((d) => d.classList.remove("open"));
          if (!isOpen) dd.classList.add("open");
        }
        return;
      }

      // Dropdown items (local file / URL)
      const item = target.closest(".settings-dropdown-item");
      if (item && document.getElementById("doc-add-dropdown")?.contains(item)) {
        document.getElementById("doc-add-dropdown")?.classList.remove("open");
        const action = item.getAttribute("data-action");
        if (action === "local") {
          (async () => {
            const api = (window as any).electronAPI;
            if (api?.pickFiles) {
              const paths = await api.pickFiles();
              if (!paths?.length) return;
              const filePath = paths[0];
              const fileName = filePath.split(/[/\\]/).pop() || filePath;
              this._showDocNameDialog(fileName, (name) => {
                send({ type: "add_document", name: name || fileName, file_path: filePath } as any);
              }, t);
            }
          })();
        } else if (action === "url") {
          this._showDocUrlDialog(t);
        }
        return;
      }

      // Remove document button
      const removeBtn = target.closest(".btn-doc-remove");
      if (removeBtn) {
        const id = removeBtn.getAttribute("data-doc-id");
        const name = removeBtn.getAttribute("data-doc-name");
        if (id && name) this._showDocDeleteConfirm(id, name, t);
      }
    });

    // Skills panel: skill view/edit/delete, command add/edit/delete
    this.panels.skills.addEventListener("click", (e) => {
      console.log("[DEBUG skills] click fired, target:", (e.target as HTMLElement).className, "tag:", (e.target as HTMLElement).tagName);
      const target = e.target as HTMLElement;

      // View skill
      const viewBtn = target.closest("[data-action='view-skill']");
      if (viewBtn) {
        console.log("[DEBUG skills] view-slick matched, name:", viewBtn.getAttribute("data-name"));
        const name = viewBtn.getAttribute("data-name") || "";
        if (name) this.showSkillDetail(name);
        return;
      }

      // Edit skill
      const editBtn = target.closest("[data-action='edit-skill']");
      if (editBtn) {
        console.log("[DEBUG skills] edit-skill matched, name:", editBtn.getAttribute("data-name"));
        const name = editBtn.getAttribute("data-name") || "";
        if (name) this.showSkillDetail(name, true);
        return;
      }

      // Delete skill
      const deleteBtn = target.closest("[data-action='delete-skill']");
      if (deleteBtn) {
        const name = deleteBtn.getAttribute("data-name") || "";
        if (name) {
          Dialog.confirm(t("settings.delete"), t("settings.skillDeleteConfirm", { name })).then(async (ok) => {
            if (ok) {
              const filtered = getState().skillsList.filter(s => s.name !== name);
              setSkillsList(filtered);
              send({ type: "uninstall_skill", name });
              this.renderSkills();
            }
          });
        }
        return;
      }

      // Edit command
      const editCmd = target.closest("[data-action='edit-command']");
      if (editCmd) {
        const name = editCmd.getAttribute("data-name") || "";
        if (name) this.showCommandCreate(name);
        return;
      }

      // Delete command
      const deleteCmd = target.closest("[data-action='delete-command']");
      if (deleteCmd) {
        const name = deleteCmd.getAttribute("data-name") || "";
        if (name) {
          Dialog.confirm(t("settings.delete"), t("settings.commandRemoveConfirm", { name })).then(async (ok) => {
            if (ok) {
              this.removeCustomCommand(name);
            }
          });
        }
        return;
      }

      // Install skill button
      const installBtn = target.closest("#btn-install-skill");
      if (installBtn) {
        this.installSkill();
        return;
      }

      // Add command button
      const addCmd = target.closest("#btn-add-command");
      if (addCmd) {
        this.showCommandCreate();
        return;
      }
    });

    // Skills panel: toggle switches (change event)
    this.panels.skills.addEventListener("change", (e) => {
      const cb = (e.target as HTMLElement).closest(".skill-toggle") as HTMLInputElement | null;
      if (cb) {
        const checked = new Set<string>();
        this.panels.skills.querySelectorAll(".skill-toggle").forEach((el) => {
          if ((el as HTMLInputElement).checked) {
            checked.add((el as HTMLInputElement).getAttribute("data-skill") || "");
          }
        });
        send({ type: "update_skills", enabled_skills: Array.from(checked) });
      }

    });

    // ── Model panel: edit, delete, enable/disable ───────────────────
    this.panels.model.addEventListener("change", (e) => {
      const cb = (e.target as HTMLInputElement).closest(".model-enable-toggle") as HTMLInputElement | null;
      if (!cb) return;
      const idx = parseInt(cb.getAttribute("data-idx") || "0");
      const currentModels = [...getState().modelConfigs];
      if (idx < 0 || idx >= currentModels.length) return;

      const isMultimodal = cb.classList.contains("model-multimodal-toggle");
      if (isMultimodal) {
        currentModels[idx] = { ...currentModels[idx], multimodal: cb.checked };
      } else {
        const newEnabled = cb.checked;
        currentModels[idx] = { ...currentModels[idx], enabled: newEnabled };
        let activeIdx = getState().activeModelIndex;
        if (!newEnabled && idx === activeIdx) {
          const nextIdx = currentModels.findIndex((m, i) => i !== idx && m.enabled !== false);
          if (nextIdx >= 0) activeIdx = nextIdx;
        }
        setModelConfigs(currentModels, activeIdx);
      }
      send({ type: "update_models", models: currentModels, active_model_index: getState().activeModelIndex });
    });

    this.panels.model.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;

      const deleteBtn = target.closest("[data-action='delete']");
      if (deleteBtn) {
        const idx = parseInt(deleteBtn.getAttribute("data-idx") || "0");
        const m = getState().modelConfigs[idx];
        Dialog.confirm(t("common.confirmDeleteTitle"), t("common.confirmDelete", { name: m?.name || t("common.unnamed") })).then((ok) => {
          if (ok) {
            const currentModels = [...getState().modelConfigs];
            currentModels.splice(idx, 1);
            let activeIdx = getState().activeModelIndex;
            if (activeIdx >= currentModels.length) activeIdx = Math.max(0, currentModels.length - 1);
            setModelConfigs(currentModels, activeIdx);
            send({ type: "delete_model", model_index: idx });
          }
        });
        return;
      }

      const editBtn = target.closest("[data-action='edit']");
      if (editBtn) {
        const idx = parseInt(editBtn.getAttribute("data-idx") || "0");
        this.showModelEdit(idx);
        return;
      }

      const createBtn = target.closest("#btn-goto-create-model");
      if (createBtn) {
        this.showModelCreate();
        return;
      }
    });

    // ── MCP panel: create, edit, delete, toggle ─────────────────────
    this.panels.mcp.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;

      const deleteBtn = target.closest("[data-action='delete-mcp']");
      if (deleteBtn) {
        const idx = parseInt(deleteBtn.getAttribute("data-idx") || "0");
        const current = [...(getState().mcpServers || [])];
        const srv = current[idx];
        const name = srv?.name || t("settings.mcpServer");
        Dialog.confirm(t("settings.confirmDeleteMcpTitle"), t("settings.confirmDeleteMcp", { name })).then((ok) => {
          if (ok) {
            current.splice(idx, 1);
            setMcpServers(current);
            send({ type: "update_mcp", mcp_servers: current });
          }
        });
        return;
      }

      const editBtn = target.closest("[data-action='edit-mcp']");
      if (editBtn) {
        const idx = parseInt(editBtn.getAttribute("data-idx") || "0");
        this._renderMcpImportDialog(idx);
        return;
      }

      const createBtn = target.closest("#btn-goto-create-mcp");
      if (createBtn) {
        this._renderMcpImportDialog();
        return;
      }
    });

    this.panels.mcp.addEventListener("change", (e) => {
      const cb = (e.target as HTMLInputElement).closest(".mcp-enable-toggle") as HTMLInputElement | null;
      if (cb) {
        const idx = parseInt(cb.getAttribute("data-idx") || "0");
        const current = [...(getState().mcpServers || [])];
        if (idx >= 0 && idx < current.length) {
          current[idx] = { ...current[idx], disabled: !cb.checked };
          send({ type: "update_mcp", mcp_servers: current });
        }
      }
    });

    // ── Agent panel: create, edit, delete ────────────────────────────
    this.panels.agent.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;

      const createBtn = target.closest("#btn-create-agent");
      if (createBtn) {
        this.showAgentCreate();
        return;
      }

      const editBtn = target.closest("[data-action='edit']");
      if (editBtn && this.panels.agent.contains(editBtn)) {
        const idx = parseInt(editBtn.getAttribute("data-index") || "0");
        const agents = getState().subAgents || [];
        if (idx >= 0 && idx < agents.length) {
          this.showAgentCreate(agents[idx]);
        }
        return;
      }

      const deleteBtn = target.closest("[data-action='delete']");
      if (deleteBtn && this.panels.agent.contains(deleteBtn)) {
        const idx = parseInt(deleteBtn.getAttribute("data-index") || "0");
        const agents = getState().subAgents || [];
        if (idx < 0 || idx >= agents.length) return;
        const name = agents[idx].name;
        Dialog.confirm(t("settings.confirmDeleteSubAgent", { name }), t("settings.confirmDeleteSubAgentTitle")).then((confirmed) => {
          if (!confirmed) return;
          const updated = agents.filter((_, i) => i !== idx);
          setSubAgents(updated);
          send({ type: "update_sub_agents", agents: updated });
        });
        return;
      }
    });

    // ── Memory panel: refresh, view ──────────────────────────────────
    this.panels.memory.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;

      const refreshBtn = target.closest("#btn-refresh-memory");
      if (refreshBtn) {
        send({ type: "get_memory_list" });
        return;
      }

      const viewBtn = target.closest("[data-action='view-memory']");
      if (viewBtn) {
        const path = viewBtn.getAttribute("data-path") || "";
        if (path) this._showMemoryDetailDialog(path);
        return;
      }
    });

    onLocaleChange(() => {
      const app = document.getElementById("app");
      if (!app?.classList.contains("settings-mode")) return;
      this.refreshCurrentPanel();
    });

    // Auto-refresh skills panel when skillsList changes (install/uninstall)
    let lastSkillsLen = getState().skillsList.length;
    subscribe(() => {
      const app = document.getElementById("app");
      if (!app?.classList.contains("settings-mode")) return;
      const currentLen = getState().skillsList.length;
      if (currentLen !== lastSkillsLen) {
        lastSkillsLen = currentLen;
        // Always re-render skills list in case user navigates there
        if (this.panels.skills) this.renderSkills();
      }
    });

    // Auto-refresh model panel when modelConfigs change (count or enabled status)
    subscribe(() => {
      const app = document.getElementById("app");
      if (!app?.classList.contains("settings-mode")) return;
      if (this.currentPanel === "model" && this.panels.model) this.renderModel();
    });

    // Auto-refresh MCP panel when mcpServers change
    let lastMcpLen = getState().mcpServers.length;
    subscribe(() => {
      const app = document.getElementById("app");
      if (!app?.classList.contains("settings-mode")) return;
      const cur = getState().mcpServers.length;
      if (cur !== lastMcpLen) {
        lastMcpLen = cur;
        if (this.currentPanel === "mcp" && this.panels.mcp) this.renderMcpList();
      }
    });

    // Auto-refresh agent panel when subAgents change
    let lastAgentLen = getState().subAgents.length;
    subscribe(() => {
      const app = document.getElementById("app");
      if (!app?.classList.contains("settings-mode")) return;
      const cur = getState().subAgents.length;
      if (cur !== lastAgentLen) {
        lastAgentLen = cur;
        if (this.currentPanel === "agent" && this.panels.agent) this.renderAgent();
      }
    });

    // Auto-refresh memory panel when memoryList or profile changes
    let lastMemoryLen = getState().memoryList.length;
    subscribe(() => {
      const app = document.getElementById("app");
      if (!app?.classList.contains("settings-mode")) return;
      if (getState().memoryList.length !== lastMemoryLen) {
        lastMemoryLen = getState().memoryList.length;
        if (this.currentPanel === "memory" && this.panels.memory) this.renderMemory();
      }
    });
    let lastProfileUpd = getState().profile?.update_count ?? -1;
    subscribe(() => {
      const app = document.getElementById("app");
      if (!app?.classList.contains("settings-mode")) return;
      const currUpd = getState().profile?.update_count ?? -1;
      if (currUpd !== lastProfileUpd) {
        lastProfileUpd = currUpd;
        if (this.currentPanel === "memory" && this.panels.memory) this.renderMemory();
      }
    });

    // Auto-refresh index panel when docsList changes
    let lastDocsLen = getState().docsList.length;
    subscribe(() => {
      const app = document.getElementById("app");
      if (!app?.classList.contains("settings-mode")) return;
      if (getState().docsList.length !== lastDocsLen) {
        lastDocsLen = getState().docsList.length;
        if (this.panels.index) this.renderIndex();
      }
    });

    // Auto-refresh rules panel when globalRules / projectRules changes
    let lastRulesLen = getState().globalRules.length;
    let lastProjectRulesLen = getState().projectRules.length;
    let lastViewingRule = getState().viewingGlobalRule;
    subscribe(() => {
      const app = document.getElementById("app");
      if (!app?.classList.contains("settings-mode")) return;
      const st = getState();
      if (st.globalRules.length !== lastRulesLen) {
        lastRulesLen = st.globalRules.length;
        if (this.currentPanel === "rules" && this.panels.rules) {
          this.renderRules();
        }
      }
      if (st.projectRules.length !== lastProjectRulesLen) {
        lastProjectRulesLen = st.projectRules.length;
        if (this.currentPanel === "rules" && this.panels.rules) {
          this.renderRules();
        }
      }
      if (st.viewingGlobalRule !== lastViewingRule && st.viewingGlobalRule) {
        const prev = lastViewingRule;
        lastViewingRule = st.viewingGlobalRule;
        if (this.currentPanel === "rules" && !st.viewingGlobalRule.error) {
          this._showRuleFormDialog(
            st.viewingGlobalRule.name,
            st.viewingGlobalRule.content,
            true
          );
        }
      }
    });

    // Auto-refresh permissions panel when policies change
    let lastPermissionPolicies = JSON.stringify(getState().permissionPolicies);
    subscribe(() => {
      const app = document.getElementById("app");
      if (!app?.classList.contains("settings-mode")) return;
      const current = JSON.stringify(getState().permissionPolicies);
      if (current !== lastPermissionPolicies) {
        lastPermissionPolicies = current;
        if (this.currentPanel === "permissions" && this.panels.permissions) {
          this.renderPermissions();
        }
      }
    });

    // Auto-refresh usage panel when usageStats changes
    let lastUsageStats = getState().usageStats;
    subscribe(() => {
      const app = document.getElementById("app");
      if (!app?.classList.contains("settings-mode")) return;
      const cur = getState().usageStats;
      if (cur !== lastUsageStats) {
        lastUsageStats = cur;
        if (this.currentPanel === "usage") this._renderUsageSection();
      }
    });

    // Auto-refresh gateway panel when gatewayStatus changes
    let lastGatewayStatus = getState().gatewayStatus;
    subscribe(() => {
      const app = document.getElementById("app");
      if (!app?.classList.contains("settings-mode")) return;
      const cur = getState().gatewayStatus;
      if (cur !== lastGatewayStatus) {
        lastGatewayStatus = cur;
        if (this.currentPanel === "gateway" && this.panels.gateway) this.renderGateway();
      }
    });

    // Fill memory detail dialog when content arrives
    let lastMemoryDetail = getState().memoryDetail;
    subscribe(() => {
      const curr = getState().memoryDetail;
      if (curr !== lastMemoryDetail) {
        lastMemoryDetail = curr;
        const contentEl = document.getElementById("memory-detail-content");
        if (contentEl) {
          if (curr?.error) {
            contentEl.innerHTML = `<span class="error-text">Error: ${this.esc(curr.error)}</span>`;
          } else if (curr?.content) {
            contentEl.innerHTML = renderMarkdown(curr.content);
          } else {
            contentEl.textContent = t("settings.loading");
          }
        }
      }
    });

    // Handle adapter test results
    onAdapterTestResult((event) => {
      this._adapterTestResults[event.adapter_id] = { success: event.success, message: event.message };
      if (this.currentPanel === "gateway") {
        this.renderGateway();
      }
    });

    // Handle WeChat QR code scan results
    onWechatScanResult((event) => {
      if (!(this as any)._wechatDialogOpen) return;
      const img = document.getElementById("wechat-qr-img") as HTMLImageElement | null;
      const statusEl = document.getElementById("wechat-qr-status");
      const countdownEl = document.getElementById("wechat-qr-countdown");
      const scanBtn = document.getElementById("wechat-scan-btn");
      if (scanBtn) scanBtn.removeAttribute("disabled");
      if (event.scan_confirmed) {
        if ((this as any)._qrCountdown) clearInterval((this as any)._qrCountdown);
        if (countdownEl) { countdownEl.style.display = "none"; countdownEl.textContent = ""; }
        if (statusEl) {
          statusEl.textContent = t("settings.wechatScanSuccess");
          statusEl.style.padding = "12px 0 0";
          statusEl.style.display = "block";
        }
        const successOverlay = document.getElementById("wechat-qr-success-overlay");
        if (successOverlay) {
          successOverlay.style.display = "flex";
          successOverlay.style.animation = "fade-in 0.3s ease";
        }
        return;
      }
      if (event.success && event.qrcode_url) {
        if ((this as any)._qrResultReceived) return;
        (this as any)._qrResultReceived = true;
        if (statusEl) { statusEl.style.display = "none"; statusEl.style.padding = "60px 0 0"; }
        if (img) {
          img.src = event.qrcode_url;
          img.style.display = "block";
        }
        if (countdownEl) {
          countdownEl.style.display = "block";
          countdownEl.textContent = t("settings.wechatRemainingTime").replace("{seconds}", "120");
          let remain = 120;
          if ((this as any)._qrCountdown) clearInterval((this as any)._qrCountdown);
          (this as any)._qrCountdown = setInterval(() => {
            remain -= 1;
            const el = document.getElementById("wechat-qr-countdown");
            if (!el) {
              clearInterval((this as any)._qrCountdown);
              return;
            }
            if (remain <= 0) {
              el.textContent = "";
              el.style.display = "none";
              const statusEl = document.getElementById("wechat-qr-status");
              if (statusEl) {
                statusEl.textContent = t("settings.wechatQrExpired");
                statusEl.style.padding = "12px 0 0";
                statusEl.style.display = "block";
              }
              const refreshOverlay = document.getElementById("wechat-qr-refresh-overlay");
              if (refreshOverlay) refreshOverlay.style.display = "flex";
              clearInterval((this as any)._qrCountdown);
              return;
            }
            el.textContent = t("settings.wechatRemainingTime").replace("{seconds}", String(remain));
          }, 1000);
        }
      } else {
        if (img) img.style.display = "none";
        if (countdownEl) { countdownEl.style.display = "none"; countdownEl.textContent = ""; }
        if (statusEl) {
          statusEl.style.display = "block";
          statusEl.textContent = `❌ ${event.message}`;
        }
      }
    });
  }

  /** Show a standalone QR code popup window for WeChat login. */
  private _showWechatQrDialog(): void {
    document.getElementById("wechat-qr-overlay")?.remove();
    (this as any)._wechatDialogOpen = true;
    (this as any)._qrResultReceived = false;
    const overlay = document.createElement("div");
    overlay.id = "wechat-qr-overlay";
    overlay.className = "toast-overlay";
    overlay.innerHTML = `
      <div class="toast-dialog" style="width:320px;text-align:center;padding:24px">
        <div class="toast-title" style="text-align:center;font-size:15px;font-weight:600;border-bottom:none;padding-bottom:0;margin-bottom:0">${t("settings.wechatScanDialogTitle")}</div>
        <hr style="border:none;border-top:1px solid var(--border);margin:16px 0" />
        <div style="position:relative;display:inline-block;margin:0 auto">
          <img id="wechat-qr-img" style="display:none;width:240px;height:240px;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.12)" />
          <div id="wechat-qr-success-overlay" style="display:none;position:absolute;inset:0;background:rgba(0,0,0,0.35);border-radius:12px;align-items:center;justify-content:center">
            <div style="width:56px;height:56px;border-radius:50%;background:#07C160;display:flex;align-items:center;justify-content:center">
              <svg viewBox="0 0 24 24" width="32" height="32" style="color:#fff;display:block">
                <path fill="currentColor" d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
              </svg>
            </div>
          </div>
          <div id="wechat-qr-refresh-overlay" style="display:none;position:absolute;inset:0;background:rgba(0,0,0,0.35);border-radius:12px;align-items:center;justify-content:center;cursor:pointer">
            <div style="width:56px;height:56px;border-radius:50%;background:#9aa0a6;display:flex;align-items:center;justify-content:center">
              <svg viewBox="0 0 24 24" width="32" height="32" style="color:#fff;display:block">
                <path fill="currentColor" d="M17.65 6.35A7.96 7.96 0 0012 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0112 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/>
              </svg>
            </div>
          </div>
        </div>
        <div id="wechat-qr-status" style="padding:60px 0 0;font-size:14px;color:var(--text-muted)">${t("settings.wechatScanning")}</div>
        <div id="wechat-qr-countdown" style="display:none;font-size:12px;color:var(--text-muted);margin-top:4px"></div>
        <div style="margin-top:16px">
          <button class="btn" id="wechat-qr-close" style="padding:6px 24px;font-size:13px">${t("header.close")}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    overlay.querySelector("#wechat-qr-close")?.addEventListener("click", () => {
      if ((this as any)._qrCountdown) clearInterval((this as any)._qrCountdown);
      (this as any)._wechatDialogOpen = false;
      overlay.remove();
    });
    const refreshOverlay = overlay.querySelector("#wechat-qr-refresh-overlay") as HTMLElement | null;
    if (refreshOverlay) {
      refreshOverlay.addEventListener("click", () => {
        refreshOverlay.style.display = "none";
        const statusEl = document.getElementById("wechat-qr-status");
        if (statusEl) {
          statusEl.textContent = t("settings.wechatScanning");
          statusEl.style.display = "block";
        }
        const img = document.getElementById("wechat-qr-img") as HTMLImageElement | null;
        if (img) { img.style.display = "none"; img.src = ""; }
        (this as any)._qrResultReceived = false;
        send({ type: "wechat_scan", adapter_id: "weixin" });
      });
    }
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) {
        e.stopPropagation();
      }
    });
  }

  private bindVersionTapUnlock(): void {
    this.panels.about.addEventListener("click", (e) => {
      const target = e.target as HTMLElement;
      const row = target.closest('.about-info-row[data-key="version"]') as HTMLElement | null;
      if (!row) return;
      const ver = row.getAttribute("data-version");
      if (ver === "agent") {
        this.handleAgentTap();
      } else if (ver === "desktop") {
        this.handleDesktopTap();
      }
    });
  }

  private async loadVersions(): Promise<void> {
    const api = (window as any).electronAPI;
    if (api?.getAppVersions) {
      try {
        this._versions = await api.getAppVersions();
      } catch {}
    }
  }

  private handleAgentTap(): void {
    if (isDevModeEnabled()) return;

    _devTapCount += 1;
    if (_devTapTimer) {
      clearTimeout(_devTapTimer);
    }
    _devTapTimer = window.setTimeout(() => {
      _devTapCount = 0;
    }, DEV_TAP_RESET_MS);

    if (_devTapCount >= DEV_TAP_THRESHOLD) {
      _devTapCount = 0;
      if (_devTapTimer) {
        clearTimeout(_devTapTimer);
        _devTapTimer = 0;
      }
      setDevModeEnabled(true);
      const devNav = document.getElementById("settings-nav-developer");
      if (devNav) devNav.classList.remove("hidden");
      this.updateSidebarNav();
      if (devNav && typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: devNav });
      }
    }
  }

  private handleDesktopTap(): void {
    _eeTapCount += 1;
    if (_eeTapTimer) {
      clearTimeout(_eeTapTimer);
    }
    _eeTapTimer = window.setTimeout(() => {
      _eeTapCount = 0;
    }, EE_TAP_RESET_MS);

    if (_eeTapCount >= EE_TAP_THRESHOLD) {
      _eeTapCount = 0;
      if (_eeTapTimer) {
        clearTimeout(_eeTapTimer);
        _eeTapTimer = 0;
      }
      window.electronAPI?.openChildWindow("easter-egg", "✦ Nebula");
    }
  }

  open(): void {
    this.modelCreateActive = false;
    if (this.searchInput) this.searchInput.value = "";
    this.filterNavItems("");
    send({ type: "get_config" } as any);
    this.renderAll();
    this.updateSidebarNav();
    this.switchPanel(this.currentPanel);
    // Don't highlight any nav item on initial open — only when user clicks one
    this.nav.querySelectorAll(".settings-nav-item").forEach(item => item.classList.remove("active"));
    document.getElementById("app")?.classList.add("settings-mode");
    const sidebarNav = document.querySelector(".sidebar-settings-nav");
    if (sidebarNav && typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: sidebarNav });
    }
  }

  public openModelCreate(): void {
    this.open();
    this.switchPanel("model");
    this.showModelCreate();
  }

  private updateSidebarNav(): void {
    const labelMap: Record<string, string> = {
      general: t("sidebar.general"),
      usage: t("sidebar.usage"),
      shortcuts: t("sidebar.shortcuts"),
      storage: t("sidebar.storage"),
      model: t("sidebar.models"),
      gateway: t("sidebar.gateway"),
      agent: t("sidebar.agent"),
      mcp: t("sidebar.mcp"),
      index: t("sidebar.document"),
      skills: t("sidebar.skills"),
      rules: t("sidebar.rules"),
      memory: t("sidebar.memory"),
      developer: t("sidebar.developer"),
      about: t("sidebar.about"),
    };
    this.nav.querySelectorAll<HTMLElement>(".settings-nav-item").forEach((item) => {
      const panel = item.getAttribute("data-panel");
      if (panel && labelMap[panel]) {
        const span = item.querySelector("span");
        if (span) span.textContent = labelMap[panel];
      }
    });
    const devBtn = document.getElementById("settings-nav-developer");
    if (devBtn) {
      devBtn.style.display = isDevModeEnabled() ? "" : "none";
    }
  }

  close(): void {
    document.getElementById("app")?.classList.remove("settings-mode");
    delete document.documentElement.dataset.shortcutPanelActive;
    delete document.documentElement.dataset.shortcutRecording;
    (window as any).electronAPI?.setWinKeyCapture?.(false);
    this._recordingShortcutId = null;
    this._cleanupTransientOverlays();
    if (typeof (window as any).__appCleanupContentArea === "function") {
      (window as any).__appCleanupContentArea();
    }
    // Force a full chat re-render after cleanup emptied the DOM.  A plain
    // render() would hit the render-key cache, see "messages unchanged", and
    // skip fullRender -- leaving the chat blank. renderForce() resets the
    // key so the message list is repainted from current state.
    if (typeof (window as any).__chatForceRender === "function") {
      (window as any).__chatForceRender();
    } else if (typeof (window as any).__chatRender === "function") {
      (window as any).__chatRender();
    }
  }

  /**
   * Best-effort teardown of every transient overlay a settings panel may
   * have created.  We only target overlays that are unconditionally safe
   * to remove (the settings view is already hidden at this point).
   */
  private _cleanupTransientOverlays(): void {
    // Floating dialogs/overlays created by settings panels:
    //   - skill-detail overlay
    //   - command-create overlay
    //   - doc-name / doc-url dialog
    //   - rule-edit overlay
    //   - agent-edit overlay
    //   - memory-edit overlay
    // Each is appended to document.body with a unique class.
    const transientClasses = [
      "skill-detail-overlay",
      "command-create-overlay",
      "doc-name-dialog",
      "doc-url-dialog",
      "rule-edit-overlay",
      "agent-edit-overlay",
      "memory-edit-overlay",
    ];
    for (const cls of transientClasses) {
      document.querySelectorAll(`.${cls}`).forEach((el) => el.remove());
    }
    // Close any still-open dropdown menus so they don't pop up the
    // moment the user moves the mouse.
    document.querySelectorAll(".settings-dropdown.open").forEach((dd) => dd.classList.remove("open"));
    // Drop inline form nodes that were inserted into #settings-content-wrap
    // by a settings panel's edit-mode flow (rare but possible).
    document.querySelectorAll("#settings-content-wrap .inline-form, #settings-content-wrap .edit-form").forEach((el) => el.remove());
  }

  focusSearch(): void {
    if (!document.getElementById("app")?.classList.contains("settings-mode")) {
      this.open();
    }
    setTimeout(() => this.searchInput?.focus(), 50);
  }

  private onSearchInput(): void {
    if (!this.searchInput) return;
    clearTimeout(this.searchTimer);
    const q = this.searchInput.value.trim().toLowerCase();
    this.searchTimer = window.setTimeout(() => {
      this.filterNavItems(q);
    }, 100);
  }

  private filterNavItems(q: string): void {
    const items = this.nav.querySelectorAll<HTMLElement>(".settings-nav-item");
    const lower = q.toLowerCase();
    let firstMatch: HTMLElement | null = null;
    let firstPanelId: string | null = null;

    items.forEach((item) => {
      const panel = item.getAttribute("data-panel") as string;
      const span = item.querySelector("span");
      const label = span?.textContent?.toLowerCase() || "";

      let panelText = "";
      if (panel && this.panels[panel as PanelId]) {
        panelText = this.panels[panel as PanelId].textContent?.toLowerCase() || "";
      }

      const matches = !lower || label.includes(lower) || panelText.includes(lower);
      (item as HTMLElement).style.display = matches ? "" : "none";

      if (matches && !firstMatch) {
        firstMatch = item as HTMLElement;
        firstPanelId = panel;
      }
    });

    if (lower && firstMatch && firstPanelId) {
      if (firstPanelId !== this.currentPanel) {
        this.switchPanel(firstPanelId as PanelId);
      }
      setTimeout(() => this.highlightInPanel(firstPanelId as PanelId, lower), 150);
    }

    this._updateDividerVisibility();
  }

  /** Hide dividers that separate groups where all items are hidden by search. */
  private _updateDividerVisibility(): void {
    const children = this.nav.children;
    let lastVisibleIdx = -1;
    for (let i = 0; i < children.length; i++) {
      const child = children[i] as HTMLElement;
      if (child.classList.contains("settings-nav-item")) {
        if (child.style.display !== "none") {
          lastVisibleIdx = i;
        }
      } else if (child.classList.contains("settings-nav-divider")) {
        let hasVisibleAfter = false;
        for (let j = i + 1; j < children.length; j++) {
          const next = children[j] as HTMLElement;
          if (next.classList.contains("settings-nav-divider")) break;
          if (next.classList.contains("settings-nav-item") && next.style.display !== "none") {
            hasVisibleAfter = true;
            break;
          }
        }
        const hasVisibleBefore = lastVisibleIdx >= 0;
        child.style.display = hasVisibleBefore && hasVisibleAfter ? "" : "none";
      }
    }
  }

  private highlightInPanel(panelId: PanelId, query: string): void {
    const panel = this.panels[panelId];
    if (!panel) return;

    this.clearHighlights();

    const walker = document.createTreeWalker(panel, NodeFilter.SHOW_TEXT, {
      acceptNode: (node) => {
        if (!node.textContent || !node.textContent.toLowerCase().includes(query)) {
          return NodeFilter.FILTER_REJECT;
        }
        let parent = node.parentElement;
        while (parent && parent !== panel) {
          const style = window.getComputedStyle(parent);
          if (style.display === "none" || style.visibility === "hidden") return NodeFilter.FILTER_REJECT;
          parent = parent.parentElement;
        }
        return NodeFilter.FILTER_ACCEPT;
      },
    });

    const firstNode = walker.nextNode();
    if (!firstNode) return;

    let target: HTMLElement | null = firstNode.parentElement;
    while (target && !this.isHighlightable(target, panel)) {
      target = target.parentElement;
    }
    if (!target) return;

    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.classList.add("settings-search-flash");
    setTimeout(() => target?.classList.remove("settings-search-flash"), 1600);
  }

  private isHighlightable(el: HTMLElement, panel: HTMLElement): boolean {
    if (el === panel) return false;
    const tag = el.tagName.toLowerCase();
    if (tag === "span" || tag === "p" || tag === "div" || tag === "h3" || tag === "h4" ||
        tag === "label" || tag === "button" || tag === "pre" || tag === "code" ||
        tag === "td" || tag === "th") {
      return true;
    }
    return false;
  }

  private clearHighlights(): void {
    document.querySelectorAll(".settings-search-flash").forEach((el) => {
      el.classList.remove("settings-search-flash");
    });
  }

  private modelCreateActive = false;

  private refreshCurrentPanel(): void {
    this.switchPanel(this.currentPanel);
  }

  switchPanel(id: PanelId): void {
    this.currentPanel = id;
    this.modelCreateActive = false;
    delete document.documentElement.dataset.shortcutPanelActive;
    (window as any).electronAPI?.setWinKeyCapture?.(false);

    this.nav.querySelectorAll(".settings-nav-item").forEach((item) => {
      item.classList.toggle("active", item.getAttribute("data-panel") === id);
    });

    Object.entries(this.panels).forEach(([key, el]) => {
      el.classList.toggle("active", false);
    });

    if (id === "skills") {
      console.log("[DEBUG switchPanel] skills panel, skillsList:", getState().skillsList.length, "items");
      this.panels.skills.classList.add("active");
      this.renderSkills();
    } else if (id === "model") {
      this.panels.model.classList.add("active");
      this.renderModel();
    } else if (id === "gateway") {
      this.panels.gateway.classList.add("active");
      this.renderGateway();
    } else if (id === "mcp") {
      this.panels.mcp.classList.add("active");
      this.renderMcpList();
    } else if (id === "agent") {
      this.panels.agent.classList.add("active");
      this.renderAgent();
    } else if (id === "memory") {
      this.panels.memory.classList.add("active");
      this.renderMemory();
      send({ type: "get_memory_list" });
    } else if (id === "usage") {
      this.panels.usage.classList.add("active");
      this._renderUsageSection();
      send({ type: "get_usage_stats" });
    } else if (id === "shortcuts") {
      this.panels.shortcuts.classList.add("active");
      this.renderShortcuts();
      document.documentElement.dataset.shortcutPanelActive = "true";
      (window as any).electronAPI?.setWinKeyCapture?.(true);
    } else if (id === "storage") {
      this.panels.storage.classList.add("active");
      this.renderStorage();
    } else if (id === "index") {
      console.log("[DEBUG switchPanel] index panel, docsList:", getState().docsList.length, "items");
      this.panels.index.classList.add("active");
      this.renderIndex();
      send({ type: "list_documents" } as any);
    } else if (id === "rules") {
      this.panels.rules.classList.add("active");
      this.renderRules();
    } else if (id === "permissions") {
      this.panels.permissions.classList.add("active");
      this.renderPermissions();
    } else if (id === "developer") {
      this.panels.developer.classList.add("active");
      this.renderDeveloper();
    } else {
      this.panels[id].classList.add("active");
    }
  }

  private showSkillDetail(skillName: string, isEdit = false): void {
    console.log("[DEBUG showSkillDetail] called with:", skillName, "isEdit:", isEdit);
    this._renderSkillDetailDialog(skillName, isEdit);
  }

  private showSkillList(): void {
    this.panels.skills.classList.add("active");
    this.renderSkills();
  }

  private showMcpCreate(editIdx?: number): void {
    this._renderMcpImportDialog(editIdx);
  }

  private showMcpList(): void {
    this.panels.mcp.classList.add("active");
    this.renderMcpList();
  }

  private showAgentCreate(existing?: import("./types.js").SubAgentConfig): void {
    this._renderAgentCreateDialog(existing);
  }

  private showAgentList(): void {
    this.panels.agent.classList.add("active");
    this.renderAgent();
  }

  private showModelCreate(): void {
    this.modelCreateActive = true;
    this._renderModelCreateDialog();
  }

  private showModelEdit(idx: number): void {
    this.modelCreateActive = true;
    this._renderModelCreateDialog(idx);
  }

  renderAll(): void {
    this.renderGeneral();
    this._renderUsageSection();
    this.renderShortcuts();
    this.renderModel();
    this.renderGateway();
    this.renderIndex();
    this.renderSkills();
    this.renderRules();
    this.renderPermissions();
    this.renderMcp();
    this.renderAgent();
    this.renderAbout();
    if (isDevModeEnabled()) this.renderDeveloper();
  }

  private renderDropdown(id: string, options: DropdownOption[], currentId: string, onChange: (val: string) => void): string {
    const current = options.find(o => o.id === currentId) || options[0];
    const items = options.map(o =>
      `<div class="settings-dropdown-item${o.id === currentId ? " selected" : ""}" data-value="${o.id}">${o.label}</div>`
    ).join("");
    return `
      <div class="settings-dropdown-wrap" id="${id}-wrap">
        <button class="settings-dropdown-trigger" id="${id}-trigger" type="button">
          <span>${current.label}</span>
          <i data-lucide="chevron-down" class="lucide settings-dropdown-chevron"></i>
        </button>
        <div class="settings-dropdown" id="${id}-dropdown">${items}</div>
      </div>`;
  }

  private modeHint(modeKey: string): string {
    return `<span class="mode-hint-icon" data-tooltip="${this.esc(t(modeKey))}">
      <i data-lucide="circle-alert" class="lucide"></i>
    </span>`;
  }

  private bindDropdown(id: string, onChange: (val: string) => void): void {
    const wrap = document.getElementById(`${id}-wrap`);
    const trigger = document.getElementById(`${id}-trigger`);
    const dropdown = document.getElementById(`${id}-dropdown`);
    if (!wrap || !trigger || !dropdown) return;

    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpen = dropdown.classList.contains("open");
      // Close all other dropdowns
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
  }

  private renderGeneral(): void {
    const st = getState();
    const currentTheme = st.themePreference;
    const s = st.settings;

    const currentLang = getLocale();
    this.updateSidebarNav();
    const currentLinkBehavior = (s.default_link_behavior as string) || "system";
    const currentSendMode = (s.shortcut_send_mode as string) || "enter";
    const currentStartupMode = (s.startup_session_mode as string) || "normal";
    const currentStartupBehavior = (s.startup_session_behavior as string) || "new";
    const currentLangPref = (s.language_preference as string) || "auto";

    const themeOptions: DropdownOption[] = [
      { id: "system", label: t("theme.system") },
      { id: "light", label: t("theme.light") },
      { id: "dark", label: t("theme.dark") },
    ];

    const langOptions: DropdownOption[] = [
      { id: "zh", label: t("language.zh") },
      { id: "en", label: t("language.en") },
    ];

    const behaviorOptions: DropdownOption[] = [
      { id: "system", label: t("settings.systemBrowser") },
      { id: "in_app", label: t("settings.inApp") },
    ];

    const sendModes: DropdownOption[] = [
      { id: "enter", label: t("settings.enterSend") },
      { id: "ctrl_enter", label: t("settings.ctrlEnterSend") },
    ];

    const startupModes: DropdownOption[] = [
      { id: "normal", label: t("settings.normalMode") },
      { id: "iwork", label: t("settings.iworkMode") },
    ];

    const startupBehaviors: DropdownOption[] = [
      { id: "new", label: t("settings.startupNew") },
      { id: "last", label: t("settings.startupLast") },
    ];

    const langPrefOptions: DropdownOption[] = [
      { id: "auto", label: t("language.autoFollow") },
      { id: "zh", label: t("language.zh") },
      { id: "en", label: t("language.en") },
    ];

    this.panels.general.innerHTML = `
      <div class="settings-section-title"><i data-lucide="settings" class="lucide section-title-icon"></i> ${t("settings.basicSettings")}</div>
      <div class="settings-card">
        <div class="settings-item-row">
          <div class="settings-item-info">
            <div class="settings-item-title">${t("settings.theme")}</div>
            <div class="settings-item-desc">${t("settings.themeDesc")}</div>
          </div>
          <div class="settings-item-control">
            ${this.renderDropdown("dd-theme", themeOptions, currentTheme, (v) => this.saveTheme(v))}
          </div>
        </div>
        <div class="settings-item-divider"></div>
        <div class="settings-item-row">
          <div class="settings-item-info">
            <div class="settings-item-title">${t("settings.language")}</div>
            <div class="settings-item-desc">${t("settings.languageDesc")}</div>
          </div>
          <div class="settings-item-control">
            ${this.renderDropdown("dd-lang", langOptions, currentLang, (v) => { this.saveSetting("language", v); this.renderGeneral(); })}
          </div>
        </div>
      </div>

      <div class="settings-section-title"><i data-lucide="pencil" class="lucide section-title-icon"></i> ${t("settings.preferences")}</div>
      <div class="settings-card">
        <div class="settings-item-row">
          <div class="settings-item-info">
            <div class="settings-item-title">${t("settings.shortcutSendMode")}</div>
            <div class="settings-item-desc">${t("settings.shortcutSendModeDesc")}</div>
          </div>
          <div class="settings-item-control">
            ${this.renderDropdown("dd-send", sendModes, currentSendMode, (v) => { this.saveSetting("shortcut_send_mode", v); this.renderGeneral(); })}
          </div>
        </div>
        <div class="settings-item-divider"></div>
        <div class="settings-item-row">
          <div class="settings-item-info">
            <div class="settings-item-title">${t("settings.startupSessionMode")}</div>
            <div class="settings-item-desc">${t("settings.startupSessionModeDesc")}</div>
          </div>
          <div class="settings-item-control">
            ${this.renderDropdown("dd-startup", startupModes, currentStartupMode, (v) => { this.saveSetting("startup_session_mode", v); this.renderGeneral(); })}
          </div>
        </div>
        <div class="settings-item-divider"></div>
        <div class="settings-item-row">
          <div class="settings-item-info">
            <div class="settings-item-title">${t("settings.startupSessionBehavior")}</div>
            <div class="settings-item-desc">${t("settings.startupSessionBehaviorDesc")}</div>
          </div>
          <div class="settings-item-control">
            ${this.renderDropdown("dd-startup-behavior", startupBehaviors, currentStartupBehavior, (v) => { this.saveSetting("startup_session_behavior", v); this.renderGeneral(); })}
          </div>
        </div>
        <div class="settings-item-divider"></div>
        <div class="settings-item-row">
          <div class="settings-item-info">
            <div class="settings-item-title">${t("settings.localLinkBehavior")}</div>
            <div class="settings-item-desc">${t("settings.localLinkBehaviorDesc")}</div>
          </div>
          <div class="settings-item-control">
            ${this.renderDropdown("dd-link", behaviorOptions, currentLinkBehavior, (v) => { this.saveSetting("default_link_behavior", v); this.renderGeneral(); })}
          </div>
        </div>
          <div class="settings-item-divider"></div>
        <div class="settings-item-row">
          <div class="settings-item-info">
            <div class="settings-item-title">${t("settings.languagePreference")}</div>
            <div class="settings-item-desc">${t("settings.languagePreferenceDesc")}</div>
          </div>
          <div class="settings-item-control">
            ${this.renderDropdown("dd-lang-pref", langPrefOptions, currentLangPref, (v) => { this.saveSetting("language_preference", v); this.renderGeneral(); })}
          </div>
        </div>
        <div class="settings-item-divider"></div>
        <div class="settings-item-row">
          <div class="settings-item-info">
            <div class="settings-item-title">${t("settings.autoExpandTitle")}</div>
            <div class="settings-item-desc">${t("settings.autoExpandDesc")}</div>
          </div>
          <div class="settings-item-control">
            <label class="toggle-switch">
              <input type="checkbox" id="auto-expand-toggle" ${isEnabled(s.auto_expand) ? "checked" : ""} />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>
        <div class="settings-item-divider"></div>
        <div class="settings-item-row">
          <div class="settings-item-info">
            <div class="settings-item-title">${t("settings.subAgentAutoOpenTitle")}</div>
            <div class="settings-item-desc">${t("settings.subAgentAutoOpenDesc")}</div>
          </div>
          <div class="settings-item-control">
            <label class="toggle-switch">
              <input type="checkbox" id="sub-agent-auto-open-toggle" ${s.sub_agent_auto_open_view === undefined || isEnabled(s.sub_agent_auto_open_view) ? "checked" : ""} />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>
        <div class="settings-item-divider"></div>
        <div class="settings-item-row">
          <div class="settings-item-info">
            <div class="settings-item-title">${t("settings.automationAutoOpenTitle")}</div>
            <div class="settings-item-desc">${t("settings.automationAutoOpenDesc")}</div>
          </div>
          <div class="settings-item-control">
            <label class="toggle-switch">
              <input type="checkbox" id="automation-auto-open-toggle" ${isEnabled(s.automation_auto_open_view) ? "checked" : ""} />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>
      </div>

      <!-- Service section -->
      <div class="settings-section-title"><i data-lucide="server" class="lucide section-title-icon"></i> ${t("settings.service")}</div>
      <div class="settings-card" id="service-settings-card">
        <div class="settings-item-row">
          <div class="settings-item-info">
            <div class="settings-item-title">${t("settings.autoStart")}</div>
            <div class="settings-item-desc">${t("settings.autoStartDesc")}</div>
          </div>
          <div class="settings-item-control">
            <label class="toggle-switch">
              <input type="checkbox" id="auto-start-checkbox" />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>
      </div>`;

    // Bind dropdowns
    this.bindDropdown("dd-theme", (v) => this.saveTheme(v));
    this.bindDropdown("dd-lang", (v) => { this.saveSetting("language", v); this.renderGeneral(); });
    this.bindDropdown("dd-send", (v) => { this.saveSetting("shortcut_send_mode", v); this.renderGeneral(); });
    this.bindDropdown("dd-startup", (v) => { this.saveSetting("startup_session_mode", v); this.renderGeneral(); });
    this.bindDropdown("dd-startup-behavior", (v) => { this.saveSetting("startup_session_behavior", v); this.renderGeneral(); });
    this.bindDropdown("dd-link", (v) => { this.saveSetting("default_link_behavior", v); this.renderGeneral(); });
    this.bindDropdown("dd-lang-pref", (v) => { this.saveSetting("language_preference", v); this.renderGeneral(); });

    // Auto-expand toggle
    document.getElementById("auto-expand-toggle")?.addEventListener("change", (e) => {
      const checked = (e.target as HTMLInputElement).checked;
      this.saveSetting("auto_expand", checked ? "true" : "false");
    });

    // Sub-agent auto-open toggle (default ON)
    document.getElementById("sub-agent-auto-open-toggle")?.addEventListener("change", (e) => {
      const checked = (e.target as HTMLInputElement).checked;
      this.saveSetting("sub_agent_auto_open_view", checked ? "true" : "false");
    });

    // Automation auto-open toggle (default OFF)
    document.getElementById("automation-auto-open-toggle")?.addEventListener("change", (e) => {
      const checked = (e.target as HTMLInputElement).checked;
      this.saveSetting("automation_auto_open_view", checked ? "true" : "false");
    });

    // Auto-start toggle
    const electronAPI = window.electronAPI;
    if (electronAPI) {
      (async () => {
        try {
          const autoStart = await electronAPI.getAutoStart();
          const checkbox = document.getElementById("auto-start-checkbox") as HTMLInputElement;
          if (checkbox) {
            checkbox.checked = autoStart;
            checkbox.addEventListener("change", async () => {
              const enabled = checkbox.checked;
              const result = await window.electronAPI!.setAutoStart(enabled);
              if (!result.success) {
                if (typeof showToast === "function") {
                  showToast("Error", result.error || "", "error", "Settings");
                }
                checkbox.checked = !enabled;
              }
            });
          }
        } catch (err) {
          console.error("Failed to get auto-start setting:", err);
        }
      })();
    }

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panels.general });
    }
  }

  private renderShortcuts(): void {
    const keybindsCfg = (getState().settings.keybinds as any);
    const binds: any[] = keybindsCfg?.keybinds || [];

    const categories = new Map<string, Array<{ id: string; keys: string[]; desc: string }>>();
    for (const b of binds) {
      const cat = b.category || "general";
      if (!categories.has(cat)) categories.set(cat, []);
      categories.get(cat)!.push({ id: b.id, keys: b.keys, desc: b.description || b.id });
    }

    const CAT_LABELS: Record<string, string> = {
      application: t("settings.shortcutCategoryApplication"),
      session: t("settings.shortcutCategorySession"),
      messages: t("settings.shortcutCategoryMessages"),
      input: t("settings.shortcutCategoryInput"),
      modes: t("settings.shortcutCategoryModes"),
      navigation: t("settings.shortcutCategoryNavigation"),
      search: t("settings.shortcutCategorySearch"),
      settings: t("settings.shortcutCategorySettings"),
      panels: t("settings.shortcutCategoryPanels"),
      automation: t("settings.shortcutCategoryAutomation"),
      workspace: t("settings.shortcutCategoryWorkspace"),
      notifications: t("settings.shortcutCategoryNotifications"),
      appearance: t("settings.shortcutCategoryAppearance"),
      general: t("settings.shortcutCategoryGeneral"),
    };

    let rowsHtml = "";
    for (const [cat, items] of categories) {
      rowsHtml += `<div class="shortcut-category-label">${this.esc(CAT_LABELS[cat] || cat)}</div>`;
      for (const item of items) {
        const displayKeys = item.keys && item.keys.length > 0 ? formatShortcut(item.keys[0]) : "—";
        const desc = t("shortcuts." + item.id) || item.desc;
        const isRecording = this._recordingShortcutId === item.id;
        rowsHtml += `
        <div class="settings-item-row shortcut-row" data-id="${item.id}">
          <div class="settings-item-info">
            <div class="settings-item-title">${this.esc(desc)}</div>
          </div>
          <div class="settings-item-control">
            <button class="shortcut-key-btn${isRecording ? " recording" : ""}" data-id="${item.id}">${isRecording ? "..." : this.esc(displayKeys)}</button>
          </div>
        </div>`;
      }
    }

    this.panels.shortcuts.innerHTML = `
      <div class="settings-section-title"><i data-lucide="keyboard" class="lucide section-title-icon"></i> ${t("settings.keyboardShortcuts")}</div>
      <div class="settings-item-desc" style="margin: -8px 0 16px; padding: 0 2px;">${t("settings.shortcutsDisabledDesc")}</div>
      <div class="settings-card" id="shortcuts-card">${rowsHtml}</div>`;

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panels.shortcuts });
    }

    // Bind key capture
    const card = document.getElementById("shortcuts-card");
    if (!card) return;

    card.querySelectorAll<HTMLButtonElement>(".shortcut-key-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const id = btn.getAttribute("data-id");
        if (!id) return;

        // Cancel current recording and start new one
        if (this._recordingShortcutId) {
          document.removeEventListener("keydown", this._captureHandler as any, true);
        }

        this._recordingShortcutId = id;
        document.documentElement.dataset.shortcutRecording = "true";
        const allBtns = card.querySelectorAll<HTMLButtonElement>(".shortcut-key-btn");
        allBtns.forEach((b) => b.classList.remove("recording"));
        btn.classList.add("recording");
        btn.textContent = "...";

        const stopRecording = () => {
          this._recordingShortcutId = null;
          delete document.documentElement.dataset.shortcutRecording;
        };

        this._captureHandler = async (ev: KeyboardEvent) => {
          ev.preventDefault();
          ev.stopPropagation();

          if (ev.repeat) return;

          // Ignore modifier-only key presses
          if (ev.key === "Control" || ev.key === "Meta" || ev.key === "Alt" || ev.key === "Shift") {
            return;
          }

          const parts: string[] = [];
          if (ev.ctrlKey || ev.metaKey) parts.push("ctrlcmd");
          if (ev.altKey) parts.push("alt");
          if (ev.shiftKey) parts.push("shift");

          const key = ev.key;
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

          stopRecording();

          const cfg = (getState().settings.keybinds as any);
          const allBinds: any[] = cfg?.keybinds ? [...cfg.keybinds] : [];
          const target = allBinds.find((b: any) => b.id === id);

          // Conflict detection — check if another shortcut already uses this key combo
          if (target) {
            const conflict = allBinds.find((b: any) => b.id !== id && b.keys && b.keys.includes(pattern));
            if (conflict) {
              const conflictName = t(`shortcuts.${conflict.id}` as any) || conflict.description || conflict.id;
              const msg = t("settings.shortcutConflict").replace("{0}", conflictName);
              const ok = await Dialog.confirm(t("settings.shortcutConflictTitle"), msg);
              if (!ok) {
this.renderShortcuts();
    this.renderStorage();
                document.removeEventListener("keydown", this._captureHandler!, true);
                return;
              }
              // Remove the conflicting key from the other shortcut
              conflict.keys = conflict.keys.filter((k: string) => k !== pattern);
            }

            const existingIdx = target.keys.indexOf(pattern);
            if (existingIdx >= 0) target.keys.splice(existingIdx, 1);
            if (target.keys.length === 0) target.keys = [pattern];
            else target.keys[0] = pattern;
          }

          const updated = { ...cfg, keybinds: allBinds };
          setSettings({ ...getState().settings, keybinds: updated });
          send({ type: "configure", config: { keybinds: updated } });
          // localStorage fallback — survive backend crypto failure across restarts
          try { localStorage.setItem("encre_keybinds", JSON.stringify(updated)); } catch { /* ignore */ }
          this.renderShortcuts();

          document.removeEventListener("keydown", this._captureHandler!, true);
        };

        document.addEventListener("keydown", this._captureHandler, true);
      });
    });
  }

  private saveSetting(key: string, value: string): void {
    const current = { ...getState().settings, [key]: value };
    setSettings(current);
    if (key === "language") {
      const locale = value as Locale;
      if (locale === "en" || locale === "zh") {
        setLocale(locale);
        this.updateSidebarNav();
      }
    }
    send({ type: "configure", config: { [key]: value } });
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
    localStorage.setItem("encre-theme", value);
    send({ type: "configure", config: { theme: value } });
    this.renderGeneral();
  }

  private esc(s: string): string {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  private _maxTokensDefault(backendType: string, context?: number): number {
    const catalog = getState().modelCatalog;
    const defOutput = catalog.default_output_tokens[backendType] || 8192;
    if (context && context > 0) {
      return Math.min(context, defOutput);
    }
    return defOutput;
  }

  private renderModel(): void {
    const st = getState();
    const models = st.modelConfigs;
    const activeIdx = st.activeModelIndex;

    let rowsHtml = "";
    for (let i = 0; i < models.length; i++) {
      const m = models[i];
      const isActive = i === activeIdx && m.enabled !== false;
      rowsHtml += `
        <div class="model-table-row" data-model-idx="${i}">
          <div class="model-table-cell model-cell-name">
            <span class="model-name-text">${this.esc(m.name || t("common.unnamed"))}</span>
            ${isActive ? `<span class="model-active-tag">${t("settings.inUse")}</span>` : ''}
          </div>
          <div class="model-table-cell model-cell-provider">${this.esc(m.backend_type)}</div>
          <div class="model-table-cell model-cell-actions">
            <button class="btn-icon" data-action="edit" data-idx="${i}" data-tooltip="${t("settings.edit")}">
              <i data-lucide="pencil" class="lucide"></i>
            </button>
            <button class="btn-icon" data-action="delete" data-idx="${i}" data-tooltip="${t("settings.delete")}">
              <i data-lucide="trash-2" class="lucide"></i>
            </button>
            <label class="toggle-switch toggle-sm">
              <input type="checkbox" class="model-enable-toggle" data-idx="${i}" ${m.enabled !== false ? "checked" : ""} />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>`;
    }

    const tableHtml = models.length === 0
      ? `<div class="model-empty">${t("settings.noModelsYet")}</div>`
      : `
        <div class="model-table">
          <div class="model-table-header">
            <div class="model-table-cell model-cell-name">${t("settings.model")}</div>
            <div class="model-table-cell model-cell-provider">${t("settings.provider")}</div>
            <div class="model-table-cell model-cell-actions">${t("settings.actions")}</div>
          </div>
          ${rowsHtml}
        </div>`;

    this.panels.model.innerHTML = `
      <div class="settings-section-title"><i data-lucide="cpu" class="lucide section-title-icon"></i> ${t("settings.modelManagement")}</div>
      <div class="settings-card">
        <div class="model-manage-header">
          <div class="model-manage-desc">${t("settings.modelManagementDesc")}</div>
          <button class="btn-add-model-top" id="btn-goto-create-model">
            <i data-lucide="plus" class="lucide"></i>
            <span>${t("settings.addModel")}</span>
          </button>
        </div>
        ${tableHtml}
      </div>`;

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panels.model });
    }
  }

  private renderGateway(): void {
    const st = getState();
    const s = st.settings;
    const gs = st.gatewayStatus;
    const adapters = gs?.adapters ?? [];

    interface AdapterFieldDef {
      key: string;
      labelKey: string;
      type: "text" | "password" | "number";
    }

    interface AdapterDef {
      id: string;
      name: string;
      desc: string;
      fields: AdapterFieldDef[];
      docs?: string;
    }

    const adapterDefs: AdapterDef[] = [
      { id: "qqbot", name: "QQ Bot", desc: "接入 QQ 机器人平台，实时接收与回复群聊及私聊消息", fields: [
        { key: "app_id", labelKey: "fieldAppId", type: "text" },
        { key: "client_secret", labelKey: "fieldClientSecret", type: "password" },
      ], docs: "https://bot.q.qq.com/wiki/" },
      { id: "telegram", name: "Telegram", desc: "连接 Telegram Bot API，自动处理频道与私信中的指令和对话", fields: [
        { key: "bot_token", labelKey: "fieldBotToken", type: "password" },
      ], docs: "https://core.telegram.org/bots#how-do-i-create-a-bot" },
      { id: "discord", name: "Discord", desc: "集成 Discord 机器人，管理服务器频道消息与交互", fields: [
        { key: "bot_token", labelKey: "fieldBotToken", type: "password" },
      ], docs: "https://discord.com/developers/applications" },
      { id: "weixin", name: "微信", desc: "通过 iLink Bot 扫码绑定微信个人号，自动收发消息", fields: [], docs: "https://www.wechatbot.dev/zh/protocol" },
      { id: "wecom", name: "企业微信", desc: "对接企业微信自建应用回调，接收成员消息并自动回复", fields: [
        { key: "token", labelKey: "fieldWecomToken", type: "text" },
        { key: "encoding_aes_key", labelKey: "fieldEncodingAesKey", type: "password" },
        { key: "receive_id", labelKey: "fieldWecomReceiveId", type: "text" },
      ], docs: "https://developer.work.weixin.qq.com/document/" },
      { id: "feishu", name: "飞书", desc: "连接飞书开放平台机器人，接收机器人事件并回复消息", fields: [
        { key: "app_id", labelKey: "fieldAppId", type: "text" },
        { key: "app_secret", labelKey: "fieldAppSecret", type: "password" },
        { key: "verify_token", labelKey: "fieldVerifyToken", type: "password" },
      ], docs: "https://open.feishu.cn/document/home/develop-a-bot-in-5-minutes" },
      { id: "dingtalk", name: "钉钉", desc: "接入钉钉开放平台机器人，通过 WebSocket 接收事件并通过 OpenAPI 回复消息", fields: [
        { key: "client_id", labelKey: "fieldDingtalkClientId", type: "text" },
        { key: "client_secret", labelKey: "fieldDingtalkClientSecret", type: "password" },
      ], docs: "https://open.dingtalk.com/document/orgapp/create-and-configure-a-robot" },
      { id: "slack", name: "Slack", desc: "集成 Slack 工作空间，通过 Bot Token 监听和发送频道消息", fields: [
        { key: "bot_token", labelKey: "fieldBotToken", type: "password" },
        { key: "signing_secret", labelKey: "fieldSigningSecret", type: "password" },
      ], docs: "https://api.slack.com/apps" },
      { id: "whatsapp", name: "WhatsApp", desc: "连接 WhatsApp Business API，处理客户消息与对话", fields: [
        { key: "phone_number_id", labelKey: "fieldPhoneNumberId", type: "text" },
        { key: "access_token", labelKey: "fieldAccessToken", type: "password" },
      ], docs: "https://developers.facebook.com/docs/whatsapp/" },
      { id: "signal", name: "Signal", desc: "对接 Signal 消息服务，通过 REST API 收发加密消息", fields: [
        { key: "phone_number", labelKey: "fieldPhoneNumber", type: "text" },
        { key: "api_url", labelKey: "fieldApiUrl", type: "text" },
      ]},
      { id: "matrix", name: "Matrix", desc: "接入 Matrix 去中心化通信网络，加入房间并自动响应消息", fields: [
        { key: "homeserver_url", labelKey: "fieldHomeserverUrl", type: "text" },
        { key: "access_token", labelKey: "fieldAccessToken", type: "password" },
      ], docs: "https://matrix.org/docs/guides/" },
      { id: "email", name: "Email", desc: "通过 SMTP/IMAP 协议收发电子邮件，支持自动回复与处理", fields: [
        { key: "smtp_host", labelKey: "fieldSmtpHost", type: "text" },
        { key: "smtp_port", labelKey: "fieldSmtpPort", type: "number" },
        { key: "smtp_user", labelKey: "fieldSmtpUser", type: "text" },
        { key: "smtp_pass", labelKey: "fieldSmtpPass", type: "password" },
        { key: "imap_host", labelKey: "fieldImapHost", type: "text" },
        { key: "imap_port", labelKey: "fieldImapPort", type: "number" },
      ]},
      { id: "sms", name: "SMS", desc: "对接短信服务商 API，发送和接收短信通知", fields: [
        { key: "provider", labelKey: "fieldProvider", type: "text" },
        { key: "account_sid", labelKey: "fieldAccountSid", type: "text" },
        { key: "auth_token", labelKey: "fieldAuthToken", type: "password" },
      ]},
      { id: "yuanbao", name: "元宝", desc: "接入元宝开放平台，通过 API 实现消息交互", fields: [
        { key: "app_key", labelKey: "fieldAppKey", type: "text" },
        { key: "app_secret", labelKey: "fieldAppSecret", type: "password" },
      ]},
      { id: "bluebubbles", name: "BlueBubbles", desc: "连接 BlueBubbles 服务器，实现 iMessage 消息收发", fields: [
        { key: "server_url", labelKey: "fieldServerUrl", type: "text" },
        { key: "api_key", labelKey: "fieldApiKey", type: "password" },
      ], docs: "https://bluebubbles.app/" },
      { id: "webhook", name: "Webhook", desc: "启动 Webhook 监听服务，接收外部系统的 HTTP 回调请求", fields: [
        { key: "listen_path", labelKey: "fieldListenPath", type: "text" },
        { key: "secret", labelKey: "fieldSecret", type: "password" },
      ]},
      { id: "homeassistant", name: "Home Assistant", desc: "连接 Home Assistant 智能家居平台，执行设备控制与状态查询", fields: [
        { key: "server_url", labelKey: "fieldServerUrl", type: "text" },
        { key: "access_token", labelKey: "fieldLongLivedToken", type: "password" },
      ], docs: "https://www.home-assistant.io/docs/authentication/" },
      { id: "msgraph", name: "Microsoft Graph", desc: "通过 Microsoft Graph API 接入 Office 365，管理邮件日历和用户", fields: [
        { key: "tenant_id", labelKey: "fieldTenantId", type: "text" },
        { key: "client_id", labelKey: "fieldClientId", type: "text" },
        { key: "client_secret", labelKey: "fieldClientSecret", type: "password" },
      ], docs: "https://learn.microsoft.com/en-us/graph/auth/" },
    ];

    const expandedAdapter = this._expandedAdapterId;

    let cardsHtml = "";
    for (const def of adapterDefs) {
      const adapterNameKey = `settings.adapterName${def.id.charAt(0).toUpperCase() + def.id.slice(1)}`;
      const displayName = t(adapterNameKey);
      const enabled = !!(s[`adapter_${def.id}_enabled` as keyof typeof s]);
      const statusInfo = adapters.find(a => a.name === def.id);
      const connected = statusInfo?.connected ?? false;
      const isExpanded = expandedAdapter === def.id;

      const fieldCount = def.fields.length;
      const allConfigured = def.fields.every(f => {
        const val = s[`adapter_${def.id}_${f.key}` as keyof typeof s];
        return val && String(val).length > 0;
      });
      const testResult = this._adapterTestResults[def.id];

      // Unified status: only ONE state shown at a time
      let statusLabel: string;
      let statusStyle: string;
      if (!enabled) {
        statusLabel = `○ ${t("settings.adapterDisabled")}`;
        statusStyle = "color:var(--text-muted)";
      } else if (!allConfigured) {
        statusLabel = `○ ${t("settings.adapterNotConfigured")}`;
        statusStyle = "color:var(--text-muted)";
      } else if (connected) {
        statusLabel = `● ${t("settings.adapterStatusConnected")}`;
        statusStyle = "color:var(--text-success)";
      } else if (testResult && !testResult.success) {
        statusLabel = `● ${t("settings.adapterStatusError")}`;
        statusStyle = "color:var(--text-danger)";
      } else {
        statusLabel = `● ${t("settings.adapterStatusDisconnected")}`;
        statusStyle = "color:var(--text-warning)";
      }

      // Description shows test result, connection error, adapter description, or config hint
      const connErr = statusInfo?.error || null;
      let descHtml: string;
      if (testResult) {
        const icon = testResult.success ? "check-circle" : "x-circle";
        const color = testResult.success ? "var(--text-success)" : "var(--text-danger)";
        descHtml = `<span style="color:${color};font-size:11px"><i data-lucide="${icon}" style="width:11px;height:11px;display:inline-block;vertical-align:middle;margin-right:3px"></i> ${this.esc(testResult.message)}</span>`;
      } else if (connErr && enabled && allConfigured) {
        descHtml = `<span style="color:var(--text-danger);font-size:11px"><i data-lucide="alert-circle" style="width:11px;height:11px;display:inline-block;vertical-align:middle;margin-right:3px"></i> ${this.esc(connErr)}</span>`;
      } else if (!enabled) {
        descHtml = `<span style="color:var(--text-muted);font-size:11px">${t("settings.adapterDisabled")} · ${this.esc(t(`settings.adapterDesc${def.id.charAt(0).toUpperCase() + def.id.slice(1)}`))}</span>`;
      } else if (!allConfigured) {
        descHtml = `<span style="color:var(--text-muted);font-size:11px">${this.esc(t(`settings.adapterDesc${def.id.charAt(0).toUpperCase() + def.id.slice(1)}`))}</span>`;
      } else {
        descHtml = `<span style="color:var(--text-muted);font-size:11px">${this.esc(t(`settings.adapterDesc${def.id.charAt(0).toUpperCase() + def.id.slice(1)}`))}</span>`;
      }

      let configBodyHtml = "";
      if (isExpanded) {
        let fieldsHtml = "";
        for (const f of def.fields) {
          const val = (s[`adapter_${def.id}_${f.key}` as keyof typeof s] as string) ?? "";
          fieldsHtml += `
            <div style="display:flex;align-items:center;justify-content:center;padding:8px 0;gap:12px">
              <div style="font-size:13px;color:var(--text-primary);white-space:nowrap;width:140px;flex-shrink:0;margin:0;text-align:right">${t("settings." + f.labelKey)}</div>
              <input type="${f.type}" id="adapter-${def.id}-${f.key}" class="model-form-input" style="width:380px;flex:0 0 auto" value="${this.esc(val)}" spellcheck="false" />
            </div>`;
        }
        configBodyHtml = `
	          <div style="padding:12px 16px 8px">
	            ${fieldsHtml}
${def.id === "weixin" ? connected ? `
            <div style="display:flex;align-items:center;justify-content:center;min-height:60px">
              <button class="btn btn-sm" id="wechat-unbind-btn" style="padding:6px 16px;font-size:12px;color:var(--text-danger)">
                <i data-lucide="unlink" style="width:14px;height:14px;margin-right:4px"></i>
                ${t("settings.wechatUnbind")}
              </button>
            </div>
            ` : `
            <div style="display:flex;align-items:center;justify-content:center;min-height:60px">
              <button class="btn btn-primary" id="wechat-scan-btn" style="padding:8px 28px;font-size:14px">
                <i data-lucide="scan-qr-code" style="width:16px;height:16px;margin-right:6px"></i>
                ${t("settings.wechatScan")}
              </button>
            </div>
            ` : `
	            <div id="adapter-test-status-${def.id}" style="font-size:12px;padding:4px 0;min-height:20px"></div>
	            <div style="padding-top:12px;display:flex;justify-content:flex-end;gap:8px">
	              <button class="btn btn-sm" id="adapter-test-${def.id}" style="padding:6px 20px;font-size:13px">
	                <i data-lucide="plug" style="width:14px;height:14px;margin-right:4px"></i>
	                ${t("settings.adapterTest")}
	              </button>
	              <button class="btn btn-primary btn-sm" id="adapter-save-${def.id}" style="padding:6px 20px;font-size:13px">
	                <i data-lucide="check" style="width:14px;height:14px;margin-right:4px"></i>
	                ${t("settings.adapterSave")}
	              </button>
	            </div>
	            `}
	          </div>`;
      }

      const iconData = PLATFORM_ICONS[def.id];
      const isMonoIcon = def.id === "matrix" || def.id === "sms" || def.id === "webhook";
      let iconHtml: string;
      if (iconData) {
        const vb = iconData.viewBox || "0 0 24 24";
        iconHtml = `<svg viewBox="${vb}" width="22" height="22" class="adapter-platform-icon${isMonoIcon ? " pi-mono" : ""}" style="margin-right:10px;flex-shrink:0">${iconData.inner}</svg>`;
      } else {
        const fbColors: Record<string, string> = {
          feishu: "#3370FF", dingtalk: "#0089FF", slack: "#4A154B", msgraph: "#0078D4",
          yuanbao: "#FF6A00", bluebubbles: "#007AFF", webhook: "#6B7280", sms: "#34A853",
        };
        const fbText: Record<string, string> = {
          feishu: t("settings.abbrFeishu"),
          dingtalk: t("settings.abbrDingtalk"),
          slack: "Sl",
          msgraph: "MS",
          yuanbao: t("settings.abbrYuanbao"),
          bluebubbles: "BB",
          webhook: "WH",
          sms: "SMS",
        };
        const c = fbColors[def.id] || "#888";
        const fbLabel = fbText[def.id] || displayName.substring(0, 2);
        iconHtml = `<div style="width:22px;height:22px;border-radius:5px;background:${c};color:#fff;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;margin-right:10px;flex-shrink:0">${fbLabel}</div>`;
      }

      cardsHtml += `
        <div class="settings-card" style="margin-bottom:12px">
          <div class="settings-item-row" style="cursor:pointer" data-adapter-toggle="${def.id}">
            <div class="settings-item-info">
              <div class="settings-item-title" style="display:flex;align-items:center">
                ${iconHtml}
                 ${this.esc(displayName)}
                <span style="margin-left:8px;font-size:11px;font-weight:400">${statusLabel}</span>
              </div>
              <div class="settings-item-desc">${descHtml}</div>
            </div>
            <div class="settings-item-control" style="gap:8px">
              ${isExpanded && def.docs && def.id !== "weixin" ? `<a href="#" class="model-get-apikey-link" data-adapter-docs="${def.id}" style="font-size:12px">${t("settings.viewDocs")}</a>` : ""}
              <label class="toggle-switch" onclick="event.stopPropagation()">
                <input type="checkbox" id="adapter-enable-${def.id}" ${enabled ? "checked" : ""} />
                <span class="toggle-slider"></span>
              </label>
              <button class="btn-icon" id="adapter-expand-${def.id}" data-adapter-expand="${def.id}" style="transition:transform 0.2s${isExpanded ? ";transform:rotate(180deg)" : ""}">
                <i data-lucide="chevron-down" style="width:16px;height:16px"></i>
              </button>
            </div>
          </div>
          ${configBodyHtml}
        </div>`;
    }

    this.panels.gateway.innerHTML = `
      <div class="settings-section-title"><i data-lucide="network" class="lucide section-title-icon"></i> ${t("settings.gatewayManagement")}</div>
      ${cardsHtml}`;

    // Bind event listeners
    for (const def of adapterDefs) {
      const enableToggle = document.getElementById(`adapter-enable-${def.id}`) as HTMLInputElement;
      if (enableToggle) {
        enableToggle.addEventListener("change", () => {
          const enabled = enableToggle.checked;
          const current = { ...getState().settings, [`adapter_${def.id}_enabled`]: enabled };
          setSettings(current as any);
          send({ type: "configure", config: { [`adapter_${def.id}_enabled`]: enabled } });
          delete this._adapterTestResults[def.id];
          this.renderGateway();
        });
      }

      const expandBtn = document.getElementById(`adapter-expand-${def.id}`);
      if (expandBtn) {
        expandBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          this._expandedAdapterId = this._expandedAdapterId === def.id ? null : def.id;
          this.renderGateway();
        });
      }

      const toggleRow = document.querySelector(`[data-adapter-toggle="${def.id}"]`);
      if (toggleRow) {
        toggleRow.addEventListener("click", () => {
          this._expandedAdapterId = this._expandedAdapterId === def.id ? null : def.id;
          this.renderGateway();
        });
      }

      const saveBtn = document.getElementById(`adapter-save-${def.id}`);
      if (saveBtn) {
        saveBtn.addEventListener("click", () => {
          const current = { ...getState().settings };
          for (const f of def.fields) {
            const input = document.getElementById(`adapter-${def.id}-${f.key}`) as HTMLInputElement;
            if (input) {
              (current as any)[`adapter_${def.id}_${f.key}`] = input.value;
            }
          }
          const config: Record<string, any> = {};
          for (const f of def.fields) {
            const input = document.getElementById(`adapter-${def.id}-${f.key}`) as HTMLInputElement;
            if (input) {
              config[`adapter_${def.id}_${f.key}`] = input.value;
            }
          }
          setSettings(current as any);
          // Include enable state so adapter starts immediately after save
          const enableInput = document.getElementById(`adapter-enable-${def.id}`) as HTMLInputElement;
          if (enableInput) {
            config[`adapter_${def.id}_enabled`] = enableInput.checked;
          }
          send({ type: "configure", config });
          delete this._adapterTestResults[def.id];
          this.renderGateway();
        });
      }

      // WeChat scan button (QR code login) - opens a standalone popup window
      const scanBtn = document.getElementById("wechat-scan-btn");
      if (scanBtn) {
        scanBtn.addEventListener("click", () => {
          scanBtn.setAttribute("disabled", "disabled");
          (this as any)._lastQrUrl = "";
          this._showWechatQrDialog();
          send({ type: "wechat_scan", adapter_id: "weixin" });
          // Re-enable after the result arrives (or after 30s timeout).
          setTimeout(() => scanBtn.removeAttribute("disabled"), 30000);
        });
      }
      // WeChat unbind button
      const unbindBtn = document.getElementById("wechat-unbind-btn");
      if (unbindBtn) {
        unbindBtn.addEventListener("click", () => {
          Dialog.confirm(t("settings.wechatUnbind"), t("settings.wechatUnbindConfirm")).then((confirmed) => {
            if (confirmed) {
              send({ type: "configure", config: { adapter_weixin_app_id: "", adapter_weixin_token: "", adapter_weixin_api_url: "" } });
            }
          });
        });
      }

      const testBtn = document.getElementById(`adapter-test-${def.id}`) as HTMLButtonElement | null;
      if (testBtn) {
        testBtn.addEventListener("click", () => {
          const config: Record<string, any> = {};
          for (const f of def.fields) {
            const input = document.getElementById(`adapter-${def.id}-${f.key}`) as HTMLInputElement;
            if (input) {
              config[f.key] = input.value;
            }
          }
          const enableInput = document.getElementById(`adapter-enable-${def.id}`) as HTMLInputElement;
          config.enabled = enableInput ? enableInput.checked : false;

          delete this._adapterTestResults[def.id];
          withLoading(testBtn, () => new Promise<void>((resolve) => {
            const poll = () => {
              if (this._adapterTestResults[def.id] !== undefined) {
                resolve();
              } else {
                setTimeout(poll, 100);
              }
            };
            setTimeout(poll, 100);
            send({ type: "test_adapter", adapter_id: def.id, config });
          }));
        });
      }

      const docsLink = document.querySelector(`[data-adapter-docs="${def.id}"]`) as HTMLAnchorElement;
      if (docsLink) {
        docsLink.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          const behavior = (getState().settings.default_link_behavior as string) || "system";
          const url = def.docs || "";
          if (behavior === "in_app") {
            const api = (window as any).electronAPI;
            if (api?.openChildWindow) { api.openChildWindow(url, url); return; }
          } else {
            const api = (window as any).electronAPI;
            if (api?.openExternal) { api.openExternal(url); return; }
          }
          window.open(url, "_blank");
        });
      }
    }

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panels.gateway });
    }
  }

  private _getCatalog(): ModelCatalog {
    return getState().modelCatalog;
  }

  private _findProvider(providerId: string): ProviderEntry | undefined {
    return this._getCatalog().providers.find(p => p.id === providerId);
  }

  private _buildModelOptions(providerId: string): DropdownOption[] {
    const p = this._findProvider(providerId);
    const opts: DropdownOption[] = (p?.models || []).map(m => ({
      id: m.id,
      label: `${m.label} (${m.context.toLocaleString()} ctx)`,
    }));
    if (p && p.allow_custom) {
      opts.push({ id: "__custom__", label: t("common.custom") || "Custom" });
    }
    return opts;
  }

private _bindModelSelect(): void {
    this.bindDropdown("new-model-select", (val) => {
      const backend = (document.getElementById("new-model-backend-hidden") as HTMLInputElement)?.value || "";
      const provider = this._findProvider(backend);
      const modelIdRow = document.getElementById("model-id-row");
      const modelIdInput = document.getElementById("new-model-id") as HTMLInputElement;
      const nameInput = document.getElementById("new-model-name") as HTMLInputElement;
      const tokensInput = document.getElementById("new-model-tokens") as HTMLInputElement;
      const urlInput = document.getElementById("new-model-url") as HTMLInputElement;

      if (val === "__custom__") {
        if (modelIdRow) modelIdRow.style.display = "";
        if (modelIdInput) {
          modelIdInput.value = "";
          modelIdInput.dataset.userModified = "true";
        }
        if (urlInput) urlInput.readOnly = false;
        if (tokensInput) tokensInput.readOnly = false;
      } else {
        if (modelIdRow) modelIdRow.style.display = "none";
        const model = provider?.models.find(m => m.id === val);
        if (modelIdInput) {
          modelIdInput.value = model?.id || val;
        }
        if (nameInput && model && !nameInput.dataset.userModified) {
          nameInput.value = model.label;
        }
        if (tokensInput && model) {
          tokensInput.value = String(this._maxTokensDefault(backend, model.context));
          tokensInput.readOnly = true;
        }
        if (urlInput && provider) {
          urlInput.value = provider.base_url;
          urlInput.readOnly = true;
        }
      }
    });
  }

  private _renderModelCreateDialog(editIdx?: number): void {
    const isEdit = editIdx !== undefined;
    const existing = isEdit ? getState().modelConfigs[editIdx!] : null;
    const title = isEdit ? t("settings.editModel") : t("settings.addEditModel");
    const btnLabel = isEdit ? t("settings.saveChanges") : t("settings.addModel");
    const catalog = this._getCatalog();

    const providers = [...catalog.providers].sort((a, b) => a.label.localeCompare(b.label));
    const providerOptions: DropdownOption[] = providers.map(p => ({ id: p.id, label: p.label }));
    const initialProviderId = existing ? existing.backend_type : (providers.length > 0 ? providers[0].id : "deepseek");
    const provider = this._findProvider(initialProviderId);
    const firstModelId = provider && provider.models.length > 0 ? provider.models[0].id : null;

    let initialModelSelectValue: string;
    if (existing) {
      const matched = provider?.models.find(m => m.id === existing.model_id);
      initialModelSelectValue = matched ? matched.id : "__custom__";
    } else {
      initialModelSelectValue = firstModelId || "__custom__";
    }
    const isCurated = initialModelSelectValue !== "__custom__";
    const modelOptions = this._buildModelOptions(initialProviderId);

    let initialTokens = 4096;
    if (existing) {
      initialTokens = existing.max_tokens;
    } else if (isCurated && provider) {
      const model = provider.models.find(m => m.id === initialModelSelectValue);
      initialTokens = this._maxTokensDefault(initialProviderId, model?.context);
    } else {
      initialTokens = this._maxTokensDefault(initialProviderId);
    }

    const initialThinkingConfig = existing?.thinking_config;
    const initialThinkingEnabled = initialThinkingConfig ? initialThinkingConfig.selectable !== false : true;

    const bodyHtml = `
      <div class="model-form-row">
        <label class="model-form-label" for="model-create-backend">
          <span class="model-form-required">*</span>${t("settings.providerSelect")}
        </label>
        <div class="model-form-dropdown-row">
          ${this.renderDropdown("model-create-backend", providerOptions, initialProviderId, () => {})}
          <input type="hidden" id="new-model-backend-hidden" value="${this.esc(initialProviderId)}" />
        </div>
      </div>
      <div class="model-form-row" id="model-select-row">
        <label class="model-form-label" for="new-model-select">
          <span class="model-form-required">*</span>${t("settings.model")}
        </label>
        <div class="model-form-dropdown-row" style="display:flex;align-items:center;gap:10px">
          ${modelOptions.length > 0 ? this.renderDropdown("new-model-select", modelOptions, initialModelSelectValue, () => {}) : `<div class="model-form-hint">${t("settings.customModelIdHint")}</div>`}
          <label class="toggle-switch">
            <input type="checkbox" id="new-model-multimodal" ${existing?.multimodal ? "checked" : ""} />
            <span class="toggle-slider"></span>
          </label>
        </div>
      </div>
      <div class="model-form-row" id="model-id-row"${isCurated ? ` style="display:none"` : ""}>
        <label class="model-form-label" for="new-model-id">
          <span class="model-form-required">*</span>${t("settings.modelId")}
        </label>
        <input type="text" id="new-model-id" class="model-form-input" placeholder="${t("settings.deepseekChatExample")}" value="${existing ? this.esc(existing.model_id) : (isCurated ? this.esc(initialModelSelectValue) : '')}" />
      </div>
      <div class="model-form-row">
        <label class="model-form-label" for="new-model-name">
          <span class="model-form-required">*</span>${t("settings.displayName")}
        </label>
        <input type="text" id="new-model-name" class="model-form-input" placeholder="${t("settings.modelNamePlaceholder")}" value="${existing ? this.esc(existing.name) : ""}" />
      </div>
      <div class="model-form-row">
        <label class="model-form-label" for="new-model-apikey">
          <span class="model-form-required">*</span>${t("settings.apiKey")}
          ${provider && provider.docs ? `<a href="${this.esc(provider.docs)}" class="model-get-apikey-link">${t("settings.getApiKey")}</a>` : ""}
        </label>
        <input type="password" id="new-model-apikey" class="model-form-input" placeholder="${t("settings.enterApiKey")}" value="${existing ? this.esc(existing.api_key) : ""}" />
      </div>
      <div class="model-form-row">
        <label class="model-form-label" for="new-model-url">${t("settings.baseUrl")}</label>
        <input type="text" id="new-model-url" class="model-form-input" placeholder="${t("settings.baseUrlPlaceholder")}" value="${existing ? this.esc(existing.base_url) : (provider ? this.esc(provider.base_url) : "")}" ${isCurated ? "readonly" : ""} />
      </div>
      <div class="model-form-row">
        <label class="model-form-label" for="new-model-tokens">${t("settings.maxTokens")}</label>
        <input type="number" id="new-model-tokens" class="model-form-input" min="1" value="${initialTokens}" ${isCurated ? "readonly" : ""} />
      </div>
      <div class="model-form-row model-form-row-inline">
        <label class="model-form-label" for="new-model-thinking-enabled">${t("settings.enableThinkingLevel")}</label>
        <label class="toggle-switch">
          <input type="checkbox" id="new-model-thinking-enabled" ${initialThinkingEnabled ? "checked" : ""} />
          <span class="toggle-slider"></span>
        </label>
      </div>`;

    const { overlay, close } = this._showFormDialog(title, bodyHtml, true);
    const okBtn = overlay.querySelector("#dialog-form-ok") as HTMLButtonElement;
    okBtn.textContent = btnLabel;

    const _wireApiKeyLink = () => {
      const apiKeyLink = document.querySelector(".model-get-apikey-link") as HTMLAnchorElement;
      if (!apiKeyLink) return;
      const p = this._findProvider((document.getElementById("new-model-backend-hidden") as HTMLInputElement)?.value);
      apiKeyLink.href = p?.docs || "#";
      apiKeyLink.style.display = p?.docs ? "" : "none";
      apiKeyLink.onclick = (e) => {
        e.preventDefault();
        const url = apiKeyLink.href;
        if (!url || url === "#") return;
        const behavior = (getState().settings.default_link_behavior as string) || "system";
        if (behavior === "in_app") {
          window.electronAPI?.openChildWindow(url, url);
        } else {
          window.electronAPI?.openExternal(url);
        }
      };
    };
    _wireApiKeyLink();

    this.bindDropdown("model-create-backend", (v) => {
      const hidden = document.getElementById("new-model-backend-hidden") as HTMLInputElement;
      if (hidden) hidden.value = v;
      _wireApiKeyLink();

      const selectRow = document.getElementById("model-select-row");
      if (!selectRow) return;
      const newOpts = this._buildModelOptions(v);
      const providerForBackend = this._findProvider(v);
      const firstModelId = providerForBackend && providerForBackend.models.length > 0 ? providerForBackend.models[0].id : null;
      const defaultVal = firstModelId || "__custom__";

      // Switching providers is an explicit user action -- always reset the
      // base URL to the new provider's default, and clear the manual-edit
      // flag so the user can still type their own URL afterwards.  Without
      // this, switching to a provider that has no curated models (or
      // picking "Custom") would leave the previous provider's URL in the
      // field, which is wrong.
      const urlInput2 = document.getElementById("new-model-url") as HTMLInputElement;
      if (urlInput2) {
        urlInput2.value = providerForBackend?.base_url || "";
        delete urlInput2.dataset.userModified;
      }

      if (newOpts.length === 0) {
        selectRow.innerHTML = `
          <label class="model-form-label" for="new-model-select">
            <span class="model-form-required">*</span>${t("settings.model")}
          </label>
          <div class="model-form-hint">${t("common.customModelIdHint")}</div>`;
        const modelIdRow2 = document.getElementById("model-id-row");
        if (modelIdRow2) modelIdRow2.style.display = "";
        const modelIdInput = document.getElementById("new-model-id") as HTMLInputElement;
        if (modelIdInput) { modelIdInput.value = ""; modelIdInput.dataset.userModified = "true"; }
        if (urlInput2) urlInput2.readOnly = false;
        const tokensInput2 = document.getElementById("new-model-tokens") as HTMLInputElement;
        if (tokensInput2) tokensInput2.readOnly = false;
      } else {
        const isCustom = defaultVal === "__custom__";
        selectRow.innerHTML = `
          <label class="model-form-label" for="new-model-select">
            <span class="model-form-required">*</span>${t("settings.model")}
          </label>
          <div class="model-form-dropdown-row">
            ${this.renderDropdown("new-model-select", newOpts, defaultVal, () => {})}
          </div>`;
        this._bindModelSelect();
        const modelIdRow2 = document.getElementById("model-id-row");
        const mid = document.getElementById("new-model-id") as HTMLInputElement;
        const tokensInput2 = document.getElementById("new-model-tokens") as HTMLInputElement;
        if (isCustom) {
          if (modelIdRow2) modelIdRow2.style.display = "";
          if (mid) { mid.value = ""; mid.dataset.userModified = "true"; }
          if (urlInput2) urlInput2.readOnly = false;
          if (tokensInput2) tokensInput2.readOnly = false;
        } else {
          if (modelIdRow2) modelIdRow2.style.display = "none";
          const model = providerForBackend?.models.find((m) => m.id === defaultVal);
          if (mid) mid.value = model?.id || defaultVal;
          if (urlInput2 && providerForBackend) { urlInput2.readOnly = true; }
          if (tokensInput2 && model) { tokensInput2.value = String(this._maxTokensDefault(v, model.context)); tokensInput2.readOnly = true; }
        }
        const nameInput2 = document.getElementById("new-model-name") as HTMLInputElement;
        const model = providerForBackend?.models.find((m) => m.id === defaultVal);
        if (nameInput2 && model && !nameInput2.dataset.userModified) {
          nameInput2.value = model.label;
        }
        if (typeof (window as any).lucide !== "undefined") {
          (window as any).lucide.createIcons({ root: selectRow });
        }
      }
    });

    if (modelOptions.length > 0) {
      this._bindModelSelect();
    }

    document.getElementById("new-model-url")?.addEventListener("input", () => {
      const el = document.getElementById("new-model-url") as HTMLInputElement;
      if (el) el.dataset.userModified = "true";
    });
    document.getElementById("new-model-id")?.addEventListener("input", () => {
      const el = document.getElementById("new-model-id") as HTMLInputElement;
      if (el) el.dataset.userModified = "true";
    });
    document.getElementById("new-model-name")?.addEventListener("input", () => {
      const el = document.getElementById("new-model-name") as HTMLInputElement;
      if (el) el.dataset.userModified = "true";
    });

    okBtn.addEventListener("click", async () => {
      const name = (document.getElementById("new-model-name") as HTMLInputElement)?.value.trim();
      const modelIdEl = document.getElementById("new-model-id") as HTMLInputElement;
      const modelId = modelIdEl?.value?.trim() || "";
      const backend = (document.getElementById("new-model-backend-hidden") as HTMLInputElement)?.value || initialProviderId;
      const apiKey = (document.getElementById("new-model-apikey") as HTMLInputElement)?.value.trim();
      const baseUrl = (document.getElementById("new-model-url") as HTMLInputElement)?.value.trim();
      const maxTokens = Math.max(1, parseInt((document.getElementById("new-model-tokens") as HTMLInputElement)?.value || "4096")) || 4096;
      console.log("[model-create] name=%j modelId=%j apiKey=%s backend=%j baseUrl=%j maxTokens=%d", name, modelId, apiKey ? "***" : "", backend, baseUrl, maxTokens);
      console.log("[model-create] modelIdEl exists=", !!modelIdEl, "value=", modelIdEl?.value, "display=", modelIdEl?.style?.display);
      if (!name || !modelId || !apiKey) {
        console.warn("[model-create] validation failed — name=%s modelId=%s apiKey=%s", name ? "ok" : "MISSING", modelId ? "ok" : "MISSING", apiKey ? "ok" : "MISSING");
        showToast(t("common.pleaseFillRequired"), "", "error", "Settings");
        return;
      }

      const multimodalInput = document.getElementById("new-model-multimodal") as HTMLInputElement;
      const thinkingEnabledInput = document.getElementById("new-model-thinking-enabled") as HTMLInputElement;
      const thinkingLevelEnabled = thinkingEnabledInput?.checked ?? true;
      const previousLevel = initialThinkingConfig?.level || "medium";
      const thinkingConfig = thinkingLevelEnabled
        ? { type: "enabled" as const, enabled: true, level: previousLevel, selectable: true }
        : { type: "enabled" as const, enabled: true, level: "", selectable: false };
      send({
        type: "validate_model", backend_type: backend, api_key: apiKey,
        base_url: baseUrl, model_id: modelId, max_tokens: maxTokens,
        name, model_index: isEdit && editIdx !== undefined ? editIdx : -1,
        multimodal: multimodalInput?.checked ?? false,
        thinking_config: thinkingConfig,
      });

      let validated = false;
      await withLoading(okBtn, async () => {
        try {
          await waitForModelValidation();
          validated = true;
        } catch (e: any) {
          showToast(t("common.connectionFailed") + (e ? `: ${e}` : ""), "", "error", "Settings");
        }
      });

      if (!validated) return;

      // Validation succeeded: the backend has already persisted the model and
      // pushed the authoritative list via models_updated (which updated state
      // before model_validated resolved).  No second round-trip to lose — just
      // refresh from the synced state and close.
      this.renderModel();
      close();
    });

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: overlay });
    }
  }

  private renderIndex(): void {
    const st = getState();
    const tFn = t;

    const docsHtml = this._renderDocList(st.docsList, tFn);

    const html = `
      <div class="settings-section-title"><i data-lucide="file-text" class="lucide section-title-icon"></i> ${tFn("settings.documentManage")}</div>
      <div class="settings-card">
        <div class="model-manage-header">
          <div class="model-manage-desc">${tFn("settings.docManagementDesc")}</div>
          <div class="settings-dropdown-wrap doc-add-dropdown" id="doc-add-dropdown-wrap">
            <button class="btn-add-model-top" id="doc-add-trigger" type="button">
              <i data-lucide="plus" class="lucide" style="width:14px;height:14px"></i>
              <span>${tFn("settings.addDocument")}</span>
              <i data-lucide="chevron-down" class="lucide" style="width:12px;height:12px;margin-left:2px"></i>
            </button>
            <div class="settings-dropdown" id="doc-add-dropdown">
              <div class="settings-dropdown-item" data-action="local">
                <i data-lucide="file-plus" class="lucide" style="width:14px;height:14px"></i>
                <span>${tFn("settings.addDocFromFile")}</span>
              </div>
              <div class="settings-dropdown-item" data-action="url">
                <i data-lucide="link" class="lucide" style="width:14px;height:14px"></i>
                <span>${tFn("settings.addDocFromUrl")}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="docs-list-flat" id="doc-list-items">
          ${docsHtml}
        </div>
      </div>`;

    this.panels.index.innerHTML = html;

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panels.index });
    }
  }

  private _renderDocList(docs: import("./types.js").DocumentEntry[], tFn: any): string {
    if (docs.length === 0) {
      return `<div class="model-empty">${tFn("settings.noDocuments")}</div>`;
    }
    const header = `
      <div class="model-table-header">
        <div class="model-table-cell model-cell-name">${tFn("settings.docName")}</div>
        <div class="model-table-cell model-cell-provider">${tFn("settings.docSourceLocal")} / ${tFn("settings.docSize")}</div>
        <div class="model-table-cell model-cell-actions">${tFn("settings.actions")}</div>
      </div>`;
    let rows = "";
    for (const d of docs) {
      const isLoading = d.status === "loading";
      const sizeStr = isLoading
        ? `<span class="doc-loading-spinner"></span>`
        : d.size > 1024 * 1024
          ? (d.size / 1024 / 1024).toFixed(1) + " MB"
          : d.size > 1024
            ? (d.size / 1024).toFixed(1) + " KB"
            : d.size + " B";
      const sourceLabel = isLoading ? tFn("common.loading") : (d.source === "url" ? tFn("common.url") : tFn("common.local"));
      rows += `
        <div class="model-table-row${isLoading ? " doc-row-loading" : ""}" data-doc-id="${d.id}">
          <div class="model-table-cell model-cell-name">
            <i data-lucide="${d.source === "url" ? "link" : "file"}" class="lucide" style="width:14px;height:14px;margin-right:6px;vertical-align:middle"></i>
            ${this._escapeHtml(d.name)}<span class="doc-ext">${d.file_type}</span>
          </div>
          <div class="model-table-cell model-cell-provider">
            <span class="skill-desc-text">${sourceLabel}</span>
            <div class="skill-aliases-sub">${sizeStr}</div>
          </div>
          <div class="model-table-cell model-cell-actions">
            <button class="btn-icon btn-doc-remove" data-doc-id="${d.id}" data-doc-name="${this._escapeHtml(d.name)}" data-tooltip="${tFn("settings.delete")}">
              <i data-lucide="trash-2" class="lucide"></i>
            </button>
          </div>
        </div>`;
    }
    return `<div class="model-table">${header}${rows}</div>`;
  }

  private _showDocNameDialog(defaultName: string, onConfirm: (name: string) => void, tFn: any): void {
    const overlay = document.createElement("div");
    overlay.className = "toast-overlay";
    overlay.innerHTML = `
      <div class="toast-dialog">
        <div class="toast-title">${tFn("settings.docName")}</div>
        <input class="toast-input" id="dialog-doc-name" value="${this._escapeHtml(defaultName)}" placeholder="${tFn("settings.docNamePlaceholder")}">
        <div class="toast-actions">
          <button class="btn" id="dialog-doc-cancel">${tFn("common.cancel")}</button>
          <button class="btn btn--primary" id="dialog-doc-ok">${tFn("common.confirm")}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);

    const input = overlay.querySelector("#dialog-doc-name") as HTMLInputElement;
    input?.focus();
    input?.select();

    overlay.querySelector("#dialog-doc-ok")?.addEventListener("click", () => {
      const name = input?.value?.trim() || defaultName;
      onConfirm(name);
      overlay.remove();
    });
    overlay.querySelector("#dialog-doc-cancel")?.addEventListener("click", () => overlay.remove());
    overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
  }

  private _showDocUrlDialog(tFn: any): void {
    const overlay = document.createElement("div");
    overlay.className = "toast-overlay";
    overlay.innerHTML = `
      <div class="toast-dialog">
        <div class="toast-title">${tFn("settings.addDocFromUrl")}</div>
        <input class="toast-input" id="dialog-doc-name-input" placeholder="${tFn("settings.docNamePlaceholder")}">
        <input class="toast-input" id="dialog-doc-url-input" placeholder="${tFn("settings.docUrlPlaceholder")}" style="margin-top:8px">
        <div class="toast-actions">
          <button class="btn" id="dialog-url-cancel">${tFn("common.cancel")}</button>
          <button class="btn btn--primary" id="dialog-url-ok">${tFn("common.confirm")}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);

    const nameInput = overlay.querySelector("#dialog-doc-name-input") as HTMLInputElement;
    const urlInput = overlay.querySelector("#dialog-doc-url-input") as HTMLInputElement;
    urlInput?.focus();

    overlay.querySelector("#dialog-url-ok")?.addEventListener("click", () => {
      const name = nameInput?.value?.trim() || "";
      const url = urlInput?.value?.trim() || "";
      if (!url) return;
      send({ type: "add_document", name, url } as any);
      overlay.remove();
    });
    overlay.querySelector("#dialog-url-cancel")?.addEventListener("click", () => overlay.remove());
    overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
  }

  private _showDocDeleteConfirm(id: string, name: string, tFn: any): void {
    const overlay = document.createElement("div");
    overlay.className = "toast-overlay";
    overlay.innerHTML = `
      <div class="toast-dialog">
        <div class="toast-title">${tFn("settings.confirmDeleteDoc").replace("{name}", this._escapeHtml(name))}</div>
        <div class="toast-actions">
          <button class="btn" id="dialog-del-cancel">${tFn("common.cancel")}</button>
          <button class="btn btn--danger" id="dialog-del-ok">${tFn("common.delete")}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);

    overlay.querySelector("#dialog-del-ok")?.addEventListener("click", () => {
      send({ type: "remove_document", id } as any);
      overlay.remove();
    });
    overlay.querySelector("#dialog-del-cancel")?.addEventListener("click", () => overlay.remove());
    overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
  }

  private _escapeHtml(str: string): string {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  private _showFormDialog(title: string, bodyHtml: string, wide: boolean = false): {
    overlay: HTMLElement;
    close: () => void;
  } {
    const overlay = document.createElement("div");
    overlay.className = "toast-overlay";
    overlay.innerHTML = `
      <div class="toast-dialog ${wide ? 'dialog-wide' : ''}">
        <div class="toast-title">${this._escapeHtml(title)}</div>
        <div class="dialog-body">${bodyHtml}</div>
        <div class="dialog-footer">
          <button class="btn" id="dialog-form-cancel">${t("common.cancel")}</button>
          <button class="btn btn--primary" id="dialog-form-ok">${t("common.confirm")}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);

    overlay.querySelectorAll("textarea").forEach((ta) => {
      const autoResize = () => {
        ta.style.height = "auto";
        ta.style.height = Math.min(ta.scrollHeight, 300) + "px";
      };
      ta.addEventListener("input", autoResize);
      autoResize();
    });

    // Auto-resize contenteditable prompt-inputs in dialogs
    overlay.querySelectorAll(".prompt-input[contenteditable]").forEach((el) => {
      const ph = el.parentElement?.querySelector(".prompt-placeholder") as HTMLElement;
      const update = () => {
        (el as HTMLElement).style.height = "auto";
        (el as HTMLElement).style.height = Math.min((el as HTMLElement).scrollHeight, 300) + "px";
        if (ph) {
          ph.classList.toggle("hidden", (el.textContent || "").trim().length > 0);
        }
      };
      el.addEventListener("input", update);
      update();
    });

    const close = () => overlay.remove();
    overlay.querySelector("#dialog-form-cancel")?.addEventListener("click", close);
    // No "click outside to dismiss" -- the form has unsaved edits and the
    // user has to deliberately press Cancel to discard them.  Also avoids
    // accidental dismissal when the user clicks on dropdown menus that
    // temporarily extend beyond the dialog bounds.

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: overlay });
    }

    return { overlay, close };
  }

  private renderSkills(): void {
    const st = getState();
    const skills: SkillInfo[] = st.skillsList;
    console.log("[DEBUG renderSkills] skills count:", skills.length, "skillsList:", skills.map(s=>s.name).join(","));
    const enabled = new Set(st.enabledSkills);

    let rowsHtml = "";
    for (const sk of skills) {
      const isOn = enabled.has(sk.name);
      const isUser = sk.source === "user" || sk.source === "project";
      const canDelete = sk.source !== "bundled" && sk.source !== "managed";
      const aliases = sk.aliases && sk.aliases.length > 0
        ? sk.aliases.join(", ") : "";
      rowsHtml += `
        <div class="model-table-row" data-skill="${this.esc(sk.name)}">
          <div class="model-table-cell model-cell-name">
            <span class="model-name-text">${this.esc(sk.name)}</span>
          </div>
          <div class="model-table-cell model-cell-provider">
            <span class="skill-desc-text">${this.esc(sk.description)}</span>
            ${aliases ? `<div class="skill-aliases-sub">${t("settings.aliases")}: ${this.esc(aliases)}</div>` : ""}
          </div>
          <div class="model-table-cell model-cell-actions">
            <button class="btn-icon" data-action="view-skill" data-name="${this.esc(sk.name)}" data-tooltip="${t("settings.view")}">
              <i data-lucide="eye" class="lucide"></i>
            </button>
            ${isUser ? `<button class="btn-icon" data-action="edit-skill" data-name="${this.esc(sk.name)}" data-tooltip="${t("settings.edit")}">
              <i data-lucide="pencil" class="lucide"></i>
            </button>` : ""}
            ${canDelete ? `<button class="btn-icon" data-action="delete-skill" data-name="${this.esc(sk.name)}" data-tooltip="${t("settings.delete")}">
              <i data-lucide="trash-2" class="lucide"></i>
            </button>` : ""}
            <label class="toggle-switch toggle-sm">
              <input type="checkbox" class="skill-toggle" data-skill="${this.esc(sk.name)}" ${isOn ? "checked" : ""} />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>`;
    }

    const skillsCardHtml = skills.length === 0
      ? `<div class="model-empty">${t("settings.noSkills")}</div>`
      : `
        <div class="model-table">
          <div class="model-table-header">
            <div class="model-table-cell model-cell-name">${t("settings.skillName")}</div>
            <div class="model-table-cell model-cell-provider">${t("settings.skillDescription")}</div>
            <div class="model-table-cell model-cell-actions">${t("settings.actions")}</div>
          </div>
          ${rowsHtml}
        </div>`;

    const commandsHtml = this.renderCommandsHTML();

    this.panels.skills.innerHTML = `
      <div class="settings-section-title"><i data-lucide="wand-2" class="lucide section-title-icon"></i> ${t("settings.skillsManagement")}</div>
      <div class="settings-card">
        <div class="model-manage-header">
          <div class="model-manage-desc">${t("settings.skillsInstructions")}</div>
          <button class="btn-add-model-top" id="btn-install-skill">
            <i data-lucide="plus" class="lucide"></i>
            <span>${t("settings.addSkill")}</span>
          </button>
        </div>
        ${skillsCardHtml}
      </div>
      <div class="settings-section-title"><i data-lucide="terminal" class="lucide section-title-icon"></i> ${t("settings.slashCommands")}</div>
      <div class="settings-card">
        <div class="model-manage-header">
          <div class="model-manage-desc">${t("settings.commandsDesc")}</div>
          <button class="btn-add-model-top" id="btn-add-command">
            <i data-lucide="plus" class="lucide"></i>
            <span>${t("settings.addCommand")}</span>
          </button>
        </div>
        ${commandsHtml}
      </div>`;

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panels.skills });
    }
  }

  private renderCommandsHTML(): string {
    const st = getState();
    const cmds = st.customCommands;

    if (cmds.length === 0) {
      return `<div class="model-empty">${t("settings.noCommands")}</div>`;
    }

    let rowsHtml = "";
    for (const cmd of cmds) {
      rowsHtml += `
        <div class="model-table-row" data-command="${this.esc(cmd.name)}">
          <div class="model-table-cell model-cell-name">
            <span class="model-name-text">/${this.esc(cmd.name)}</span>
          </div>
          <div class="model-table-cell model-cell-provider">
            <span class="skill-desc-text">${this.esc(cmd.title)}</span>
            <div class="skill-aliases-sub">${this.esc(cmd.description)}</div>
          </div>
          <div class="model-table-cell model-cell-actions">
            <button class="btn-icon" data-action="edit-command" data-name="${this.esc(cmd.name)}" data-tooltip="${t("settings.edit")}">
              <i data-lucide="pencil" class="lucide"></i>
            </button>
            <button class="btn-icon" data-action="delete-command" data-name="${this.esc(cmd.name)}" data-tooltip="${t("settings.delete")}">
              <i data-lucide="trash-2" class="lucide"></i>
            </button>
          </div>
        </div>`;
    }

    return `
      <div class="model-table">
        <div class="model-table-header">
          <div class="model-table-cell model-cell-name">${t("settings.commandName")}</div>
          <div class="model-table-cell model-cell-provider">${t("settings.commandTitle")}</div>
          <div class="model-table-cell model-cell-actions">${t("settings.actions")}</div>
        </div>
        ${rowsHtml}
      </div>`;
  }

  private showCommandCreate(editName?: string): void {
    this._renderCommandCreateDialog(editName);
  }

  private _renderCommandCreateDialog(editName?: string): void {
    const st = getState();
    const existing = editName ? st.customCommands.find(c => c.name === editName) : null;
    const isEdit = !!existing;

    const bodyHtml = `
      <div class="model-form-row">
        <label class="model-form-label">${t("settings.commandName")} <span class="required-star">*</span></label>
        <input type="text" id="cmd-name" class="model-form-input" value="${this.esc(existing?.name || "")}" placeholder="${t("settings.commandNamePlaceholder")}" ${isEdit ? "readonly" : ""} />
      </div>
      <div class="model-form-row">
        <label class="model-form-label">${t("settings.commandTitle")} <span class="required-star">*</span></label>
        <input type="text" id="cmd-title" class="model-form-input" value="${this.esc(existing?.title || "")}" placeholder="${t("settings.commandTitlePlaceholder")}" />
      </div>
      <div class="model-form-row">
        <label class="model-form-label">${t("settings.commandDescription")}</label>
        <input type="text" id="cmd-description" class="model-form-input" value="${this.esc(existing?.description || "")}" placeholder="${t("settings.commandDescriptionPlaceholder")}" />
      </div>
      <div class="model-form-row">
        <label class="model-form-label">${t("settings.commandIcon")}</label>
        <input type="text" id="cmd-icon" class="model-form-input" value="${this.esc(existing?.icon || "command")}" placeholder="${t("settings.commandIconPlaceholder")}" />
      </div>
      <div class="model-form-row">
        <label class="model-form-label">${t("settings.commandPrompt")}</label>
        <textarea id="cmd-prompt" class="model-form-input" placeholder="${t("settings.commandPromptPlaceholder")}" rows="4">${this.esc(existing?.prompt || "")}</textarea>
      </div>`;

    const title = isEdit ? t("settings.editCommand") : t("settings.createCommand");
    const { overlay, close } = this._showFormDialog(title, bodyHtml);

    const okBtn = overlay.querySelector("#dialog-form-ok") as HTMLButtonElement;
    okBtn.textContent = isEdit ? t("settings.saveChanges") : t("settings.createCommand");
    okBtn.addEventListener("click", () => {
      const name = (document.getElementById("cmd-name") as HTMLInputElement)?.value?.trim();
      if (!name) {
        Dialog.alert(t("settings.error"), t("settings.commandNamePlaceholder"));
        return;
      }
      if (!/^[a-zA-Z0-9][a-zA-Z0-9-]*$/.test(name)) {
        Dialog.alert(t("settings.error"), t("settings.invalidCommandName"));
        return;
      }

      const newCmd: CustomCommand = {
        name,
        title: (document.getElementById("cmd-title") as HTMLInputElement)?.value?.trim() || name,
        description: (document.getElementById("cmd-description") as HTMLInputElement)?.value?.trim() || "",
        icon: (document.getElementById("cmd-icon") as HTMLInputElement)?.value?.trim() || "command",
        prompt: (document.getElementById("cmd-prompt") as HTMLTextAreaElement)?.value?.trim() || undefined,
      };

      if (isEdit) {
        const updated = st.customCommands.map(c => c.name === editName ? newCmd : c);
        this.saveCustomCommands(updated);
      } else {
        if (st.customCommands.some(c => c.name === name)) {
          Dialog.alert(t("settings.error"), t("settings.invalidCommandName"));
          return;
        }
        const updated = [...st.customCommands, newCmd];
        this.saveCustomCommands(updated);
      }
      close();
      this.renderSkills();
    });
  }

  private saveCustomCommands(commands: CustomCommand[]): void {
    setCustomCommands(commands);
    send({
      type: "configure",
      config: { custom_slash_commands: commands },
    } as any);
    applyServerCommands(commands);
    window.dispatchEvent(new CustomEvent("slash-commands-updated"));
  }

  private removeCustomCommand(name: string): void {
    const st = getState();
    const updated = st.customCommands.filter(c => c.name !== name);
    this.saveCustomCommands(updated);
    this.renderSkills();
  }

  private _renderSkillDetailDialog(skillName: string, isEdit = false): void {
    const st = getState();
    const sk = st.skillsList.find((s) => s.name === skillName);
    if (!sk) return;
    const isUser = sk.source === "user";
    const canEdit = isUser && isEdit;
    const content = sk.body || "";

    let frontmatter = `---\nname: ${sk.name}\ndescription: ${sk.description}`;
    if (sk.aliases && sk.aliases.length > 0) frontmatter += `\naliases: ${sk.aliases.join(", ")}`;
    if (sk.license) frontmatter += `\nlicense: ${sk.license}`;
    if (sk.compatibility) frontmatter += `\ncompatibility: ${sk.compatibility}`;
    if (sk.argument_hint) frontmatter += `\nargument_hint: ${sk.argument_hint}`;
    if (sk.allowed_tools && sk.allowed_tools.length > 0) frontmatter += `\nallowed_tools: ${sk.allowed_tools.join(", ")}`;
    if (sk.when_to_use) frontmatter += `\nwhen_to_use: ${sk.when_to_use}`;
    if (sk.context) frontmatter += `\ncontext: ${sk.context}`;
    if (sk.model) frontmatter += `\nmodel: ${sk.model}`;
    frontmatter += `\nuser_invocable: ${sk.user_invocable ? "true" : "false"}`;
    frontmatter += `\ndisable_model_invocation: ${sk.disable_model_invocation ? "true" : "false"}`;
    frontmatter += `\nsource: ${sk.source}`;
    if (sk.metadata && Object.keys(sk.metadata).length > 0) {
      frontmatter += `\nmetadata:`;
      for (const [k, v] of Object.entries(sk.metadata)) {
        frontmatter += `\n  ${k}: ${v}`;
      }
    }
    frontmatter += `\n---`;

    const fullContent = `${frontmatter}\n\n${content}`;

    let extraFields = "";
    if (sk.license) extraFields += `<div class="model-form-row"><label class="model-form-label">${t("settings.license")}</label><input type="text" class="model-form-input" value="${this.esc(sk.license)}" readonly /></div>`;
    if (sk.compatibility) extraFields += `<div class="model-form-row"><label class="model-form-label">${t("settings.compatibility")}</label><input type="text" class="model-form-input" value="${this.esc(sk.compatibility)}" readonly /></div>`;
    if (sk.argument_hint) extraFields += `<div class="model-form-row"><label class="model-form-label">${t("settings.argumentHint")}</label><input type="text" class="model-form-input" value="${this.esc(sk.argument_hint)}" readonly /></div>`;
    if (sk.when_to_use) extraFields += `<div class="model-form-row"><label class="model-form-label">${t("settings.whenToUse")}</label><input type="text" class="model-form-input" value="${this.esc(sk.when_to_use)}" readonly /></div>`;

    const bodyHtml = `
      <div class="model-form-row">
        <label class="model-form-label">${t("settings.skillName")}</label>
        <input type="text" class="model-form-input" value="${this.esc(sk.name)}" readonly />
      </div>
      <div class="model-form-row">
        <label class="model-form-label">${t("settings.source")}</label>
        <input type="text" class="model-form-input" value="${sk.source}" readonly />
      </div>
      <div class="model-form-row">
        <label class="model-form-label">${t("settings.description")}</label>
        <input type="text" class="model-form-input" value="${this.esc(sk.description)}" readonly />
      </div>
      ${extraFields}
      <div class="model-form-row">
        <label class="model-form-label">${t("settings.skillContent")}</label>
        ${canEdit
          ? `<textarea id="skill-content-editor" class="code-textarea" rows="16" style="min-height:300px">${this.esc(fullContent)}</textarea>`
           : `<div class="msg-text" style="max-height:60vh;overflow-y:auto;padding:12px 16px;background:var(--surface);border:1px solid var(--border);border-radius:8px">${renderMarkdown(content)}</div>`}
      </div>`;

    const title = canEdit ? `${t("settings.edit")}: ${sk.name}` : sk.name;
    const { overlay, close } = this._showFormDialog(title, bodyHtml, true);

    if (canEdit) {
      const okBtn = overlay.querySelector("#dialog-form-ok") as HTMLButtonElement;
      okBtn.textContent = t("settings.saveChanges");
      okBtn.addEventListener("click", () => {
        const newContent = (overlay.querySelector("#skill-content-editor") as HTMLTextAreaElement)?.value || "";
        send({ type: "update_skill", name: sk.name, content: newContent });
        close();
      });
    } else {
      const okBtn = overlay.querySelector("#dialog-form-ok") as HTMLButtonElement;
      okBtn.remove();
    }

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: overlay });
    }
  }

  private async installSkill(): Promise<void> {
    if (!window.electronAPI) return;
    try {
      const paths = await window.electronAPI.pickFiles();
      if (paths.length === 0) return;
      for (const fp of paths) {
        const name = fp.split(/[/\\]/).pop() ?? fp;
        const isZip = name.toLowerCase().endsWith(".zip");
        const isMd = name.toLowerCase().endsWith(".md");
        if (!isMd && !isZip) {
          showToast(t("settings.skillFileError"), "", "error", "Settings");
          continue;
        }
        if (isZip) {
          // For zip files, send the file path so the backend reads the binary zip
          const skillName = name.replace(/\.zip$/i, "");
          send({ type: "install_skill", name: skillName, content: "", file_path: fp });
        } else {
          const fileResult = await window.electronAPI.readFile(fp);
          const skillName = name.replace(/\.md$/i, "");
          send({ type: "install_skill", name: skillName, content: fileResult.content, file_path: "" });
        }
      }
    } catch (e: any) {
      showToast(t("settings.failedInstallSkill"), e.message || String(e), "error", "Settings");
    }
  }

  private renderMcpList(): void {
    const st = getState();
    const servers: MCPServerConfig[] = st.mcpServers || [];

    let rowsHtml = "";
    for (let i = 0; i < servers.length; i++) {
      const srv = servers[i];
      const isHttp = srv.type === "http";
      const transportTag = isHttp ? t("settings.transportTagHttp") : t("settings.transportTagStdio");
      const isDisabled = srv.disabled === true;
      const sourceLabel = srv.source === "model" ? "model" : "user";
      rowsHtml += `
        <div class="model-table-row" data-mcp-idx="${i}">
          <div class="model-table-cell model-cell-name">
            <span class="model-name-text">${this.esc(srv.name)}</span>
            <span class="model-active-tag" style="margin-left:8px">${sourceLabel}</span>
            <span class="model-active-tag">${isDisabled ? t("settings.disabled") : t("settings.enabled")}</span>
          </div>
          <div class="model-table-cell model-cell-provider">
            <span class="mcp-transport-tag">${transportTag}</span>
          </div>
          <div class="model-table-cell model-cell-actions">
            <button class="btn-icon" data-action="edit-mcp" data-idx="${i}" data-tooltip="${t("settings.edit")}">
              <i data-lucide="pencil" class="lucide"></i>
            </button>
            <button class="btn-icon" data-action="delete-mcp" data-idx="${i}" data-tooltip="${t("settings.removeServer")}">
              <i data-lucide="trash-2" class="lucide"></i>
            </button>
            <label class="toggle-switch toggle-sm">
              <input type="checkbox" class="mcp-enable-toggle" data-idx="${i}" ${isDisabled ? "" : "checked"} />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>`;
    }

    const tableHtml = servers.length === 0
      ? `<div class="model-empty">${t("settings.noMcpServers")}</div>`
      : `
        <div class="model-table">
          <div class="model-table-header">
            <div class="model-table-cell model-cell-name">${t("settings.serverName")}</div>
            <div class="model-table-cell model-cell-provider">${t("settings.type")}</div>
            <div class="model-table-cell model-cell-actions">${t("settings.actions")}</div>
          </div>
          ${rowsHtml}
        </div>`;

    this.panels.mcp.innerHTML = `
      <div class="settings-section-title"><i data-lucide="server" class="lucide section-title-icon"></i> ${t("settings.mcpServers")}</div>
      <div class="settings-card">
        <div class="model-manage-header">
          <div class="model-manage-desc">${t("settings.mcpInstructions")}</div>
          <button class="btn-add-model-top" id="btn-goto-create-mcp">
            <i data-lucide="plus" class="lucide"></i>
            <span>${t("settings.addMcpServer")}</span>
          </button>
        </div>
        ${tableHtml}
      </div>`;

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panels.mcp });
    }
  }

  // ── MCP JSON import helpers ───────────────────────────────────────────

  /** Serialize a single ``MCPServerConfig`` back to standard JSON string. */
  private _serverConfigToJson(srv: MCPServerConfig): string {
    const obj: Record<string, any> = {};
    if (srv.type === "http") {
      obj.url = srv.url || "";
      obj.timeout = srv.timeout ?? 60;
      if (srv.headers && Object.keys(srv.headers).length > 0) obj.headers = srv.headers;
    } else {
      obj.command = srv.command || "";
      if (srv.args && srv.args.length > 0) obj.args = srv.args;
      if (srv.cwd) obj.cwd = srv.cwd;
    }
    obj.type = srv.type;
    if (srv.env && Object.keys(srv.env).length > 0) obj.env = srv.env;
    if (srv.disabled) obj.disabled = true;
    const wrapper: Record<string, any> = {};
    wrapper[srv.name] = obj;
    return JSON.stringify(wrapper, null, 2);
  }

  /** Try to detect whether *obj* is a map of MCP server configs (as opposed to some arbitrary object). */
  private _isMcpServerMap(obj: Record<string, unknown>): boolean {
    return Object.values(obj).some((v) =>
      v && typeof v === "object" && !Array.isArray(v) &&
      (typeof (v as any).command === "string" || typeof (v as any).url === "string")
    );
  }

  /** Normalize a single raw config entry into an ``MCPServerConfig``. */
  private _normalizeMcpServerConfig(name: string, cfg: any): MCPServerConfig {
    const type: "stdio" | "http" = (cfg.type === "http" || cfg.transport === "http") ? "http" : "stdio";
    const result: MCPServerConfig = { name, type };
    if (type === "http") {
      result.url = cfg.url || "";
      result.timeout = cfg.timeout ?? cfg.http_timeout ?? 60;
      result.headers = cfg.headers || {};
    } else {
      result.command = cfg.command || "";
      result.args = Array.isArray(cfg.args) ? cfg.args : [];
      result.cwd = cfg.cwd || "";
    }
    if (cfg.env && typeof cfg.env === "object" && !Array.isArray(cfg.env)) {
      result.env = cfg.env;
    }
    if (cfg.disabled) result.disabled = true;
    return result;
  }

  /** Parse standard MCP JSON into ``MCPServerConfig[]``. */
  private _parseMcpJsonToServers(parsed: any): MCPServerConfig[] {
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return [];

    let map: Record<string, unknown> | null = null;

    // Format 1: { mcpServers: { name: { ... } } } — the official Claude Code format
    if (parsed.mcpServers && typeof parsed.mcpServers === "object" && !Array.isArray(parsed.mcpServers)) {
      map = parsed.mcpServers;
    }
    // Format 2: { name: { command: "...", ... } } — a single server config object
    else if (parsed.command || parsed.url) {
      return [this._normalizeMcpServerConfig("mcp-server", parsed)];
    }
    // Format 3: { name: { ... }, name2: { ... } } — bare server map
    else if (this._isMcpServerMap(parsed)) {
      map = parsed;
    }

    if (!map) return [];
    return Object.entries(map).map(([name, cfg]) =>
      this._normalizeMcpServerConfig(name, cfg)
    );
  }

  // ── MCP JSON Import Dialog ────────────────────────────────────────────

  private _renderMcpImportDialog(editIdx?: number): void {
    const isEdit = editIdx !== undefined;
    const title = isEdit ? t("settings.editMcpServer") : t("settings.addMcpServer");

    // Pre-fill textarea for edit mode
    let initialJson = "";
    if (isEdit) {
      const existing = (getState().mcpServers || [])[editIdx!];
      if (existing) initialJson = this._serverConfigToJson(existing);
    }

    const bodyHtml = `
      <div class="model-form-row" style="flex-direction:column;align-items:stretch">
        <label class="model-form-label">${t("settings.importMcpJsonDesc")}</label>
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:8px;line-height:1.6">
          ${t("settings.importMcpJsonFmt1")}<br>
          ${t("settings.importMcpJsonFmt2")}
        </div>
        <textarea id="mcp-import-textarea" class="code-textarea"
          placeholder="${this.esc(t("settings.importMcpJsonPlaceholder"))}">${this.esc(initialJson)}</textarea>
        <div id="mcp-import-preview" style="margin-top:10px"></div>
        <div id="mcp-import-options" class="hidden" style="margin-top:10px">
          ${isEdit ? "" : `
          <div style="font-size:12px;font-weight:500;color:var(--text-primary);margin-bottom:6px">${t("settings.importMode")}</div>
          <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-primary);cursor:pointer">
            <input type="radio" name="mcp-import-mode" value="merge" checked />
            ${t("settings.importMcpJsonMerge")}
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-primary);cursor:pointer;margin-top:4px">
            <input type="radio" name="mcp-import-mode" value="replace" />
            ${t("settings.importMcpJsonReplace")}
          </label>
          `}
        </div>
      </div>`;

    const { overlay, close } = this._showFormDialog(title, bodyHtml, true);
    const okBtn = overlay.querySelector("#dialog-form-ok") as HTMLButtonElement;
    okBtn.textContent = t("settings.importMcpJsonParse");

    let parsedServers: MCPServerConfig[] | null = null;

    okBtn.addEventListener("click", () => {
      if (parsedServers) {
        // ── Import / Save mode (second click) ──
        if (isEdit) {
          const current = [...(getState().mcpServers || [])];
          if (editIdx! < current.length) current.splice(editIdx!, 1);
          current.push(...parsedServers);
          send({ type: "update_mcp", mcp_servers: current });
        } else {
          const isMerge = (overlay.querySelector('input[name="mcp-import-mode"]:checked') as HTMLInputElement)?.value === "merge";
          const current = [...(getState().mcpServers || [])];
          if (isMerge) {
            const existingNames = new Set(current.map((s) => s.name));
            for (const srv of parsedServers) {
              if (!existingNames.has(srv.name)) current.push(srv);
            }
          } else {
            current.length = 0;
            current.push(...parsedServers);
          }
          send({ type: "update_mcp", mcp_servers: current });
        }
        close();
        return;
      }

      // ── Parse mode (first click) ──
      const textarea = overlay.querySelector("#mcp-import-textarea") as HTMLTextAreaElement;
      const raw = textarea?.value.trim();
      if (!raw) {
        showToast(t("common.pleaseFillRequired"), "", "error", "Settings");
        return;
      }

      let parsed: any;
      try {
        parsed = JSON.parse(raw);
      } catch (e) {
        showToast(t("settings.importMcpJsonParseError"), String(e), "error", "Settings");
        return;
      }

      const servers = this._parseMcpJsonToServers(parsed);
      if (servers.length === 0) {
        showToast(t("settings.importMcpJsonParseError"), t("settings.noMcpServers"), "error", "Settings");
        return;
      }

      // Show parsed preview
      parsedServers = servers;
      const preview = overlay.querySelector("#mcp-import-preview") as HTMLElement;
      let html = `<div style="font-size:12px;color:var(--text-success);margin-bottom:8px">${t("settings.importMcpJsonParsed", { count: servers.length })}</div>`;
      html += `<div style="border:1px solid var(--border);border-radius:6px;overflow:hidden">`;
      html += `<div style="display:grid;grid-template-columns:1fr 2fr 1fr;font-size:11px;font-weight:600;background:var(--bg-secondary);padding:6px 10px;border-bottom:1px solid var(--border)">`;
      html += `<div>Name</div><div>Command / URL</div><div>Type</div></div>`;
      for (const srv of servers) {
        const detail = srv.type === "http"
          ? (srv.url || "")
          : `${srv.command || ""} ${(srv.args || []).join(" ")}`.trim();
        const typeLabel = srv.type === "http" ? "HTTP" : "STDIO";
        html += `<div style="display:grid;grid-template-columns:1fr 2fr 1fr;padding:5px 10px;font-size:11px;border-bottom:1px solid var(--border);align-items:center">`;
        html += `<div style="font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${this.esc(srv.name)}</div>`;
        html += `<div style="color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:0 6px">${this.esc(detail)}</div>`;
        html += `<div><span class="mcp-transport-tag" style="font-size:10px">${typeLabel}</span></div>`;
        html += `</div>`;
      }
      html += `</div>`;
      preview.innerHTML = html;

      // Reveal options and switch button text
      overlay.querySelector("#mcp-import-options")?.classList.remove("hidden");
      okBtn.textContent = isEdit
        ? t("common.save")
        : t("settings.importMcpJsonConfirm", { count: servers.length });
    });

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: overlay });
    }
  }

  private renderRules(): void {
    const st = getState();
    const rules = st.globalRules;

    let rowsHtml = "";
    for (const r of rules) {
      rowsHtml += `
        <div class="model-table-row" data-rule="${this._escapeHtml(r.name)}">
          <div class="model-table-cell model-cell-name">
            <span class="model-name-text">${this._escapeHtml(r.name)}.md</span>
          </div>
          <div class="model-table-cell model-cell-provider">
            ${new Date(r.modified * 1000).toLocaleString()}
          </div>
          <div class="model-table-cell model-cell-actions">
            <button class="btn-icon" data-action="edit-rule" data-name="${this._escapeHtml(r.name)}" data-tooltip="${t("settings.edit")}">
              <i data-lucide="pencil" class="lucide"></i>
            </button>
            <button class="btn-icon" data-action="delete-rule" data-name="${this._escapeHtml(r.name)}" data-tooltip="${t("settings.delete")}">
              <i data-lucide="trash-2" class="lucide"></i>
            </button>
          </div>
        </div>`;
    }

    const tableHtml = rules.length === 0
      ? `<div class="model-empty">${t("settings.noGlobalRules")}</div>`
      : `
        <div class="model-table">
          <div class="model-table-header">
            <div class="model-table-cell model-cell-name">${t("settings.ruleSource")}</div>
            <div class="model-table-cell model-cell-provider">${t("settings.memoryTime")}</div>
            <div class="model-table-cell model-cell-actions">${t("settings.actions")}</div>
          </div>
          ${rowsHtml}
        </div>`;

    this.panels.rules.innerHTML = `
      <div class="settings-section-title"><i data-lucide="file-check" class="lucide section-title-icon"></i> ${t("settings.globalRules")}</div>
      <div class="settings-card">
        <div class="model-manage-header">
          <div class="model-manage-desc">${t("settings.globalRulesDesc")}</div>
          <button class="btn-add-model-top" id="btn-add-global-rule">
            <i data-lucide="plus" class="lucide"></i>
            <span>${t("settings.addGlobalRule")}</span>
          </button>
        </div>
        ${tableHtml}
      </div>`;

    // Bind edit
    this.panels.rules.querySelectorAll("[data-action='edit-rule']").forEach((btn) => {
      btn.addEventListener("click", () => {
        const name = (btn as HTMLElement).getAttribute("data-name") || "";
        send({ type: "get_global_rule_content", name });
      });
    });

    // Bind delete
    this.panels.rules.querySelectorAll("[data-action='delete-rule']").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const name = (btn as HTMLElement).getAttribute("data-name") || "";
        if (await Dialog.confirm(t("common.confirmDeleteTitle"), t("common.confirmDelete", { name: `${name}.md` }))) {
          send({ type: "delete_global_rule", name });
        }
      });
    });

    document.getElementById("btn-add-global-rule")?.addEventListener("click", () => {
      this._showRuleFormDialog("", "", false);
    });

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panels.rules });
    }

    if (!rules.length) {
      send({ type: "list_global_rules" });
    }
  }

  private _showRuleFormDialog(name: string, content: string, isEdit: boolean): void {
    const title = isEdit ? t("settings.edit") : t("settings.addGlobalRule");
    const bodyHtml = `
      <div class="model-form-row">
        <label class="model-form-label" for="rule-form-name">
          <span class="model-form-required">*</span>${t("settings.ruleSource")}
        </label>
        <input type="text" id="rule-form-name" class="model-form-input" placeholder="rule-name" value="${this._escapeHtml(name)}" ${isEdit ? "readonly" : ""} />
      </div>
      <div class="model-form-row">
        <label class="model-form-label" for="rule-form-content">${t("settings.ruleContent")}</label>
        <textarea id="rule-form-content" class="model-form-input" placeholder="${t("settings.ruleContent")}..." style="min-height:300px;resize:vertical">${this._escapeHtml(content)}</textarea>
      </div>`;

    const { overlay, close } = this._showFormDialog(title, bodyHtml, true);
    const okBtn = overlay.querySelector("#dialog-form-ok") as HTMLButtonElement;
    okBtn.textContent = isEdit ? t("settings.saveChanges") : t("settings.addGlobalRule");

    okBtn.addEventListener("click", () => {
      const inputName = (overlay.querySelector("#rule-form-name") as HTMLInputElement).value.trim();
      const inputContent = (overlay.querySelector("#rule-form-content") as HTMLTextAreaElement).value.trim();
      if (!inputName) return;
      send({ type: "save_global_rule", name: inputName, content: inputContent });
      close();
    });
  }

  private renderPermissions(): void {
    const st = getState();
    const policies = st.permissionPolicies || { tools: {}, capabilities: {} };

    // Request persisted policies on first open.
    if (Object.keys(policies.tools).length === 0 && Object.keys(policies.capabilities).length === 0) {
      send({ type: "configure", config: { permission_settings: {} } });
    }

    const options: DropdownOption[] = [
      { id: "default", label: t("permissions.settings.default") },
      { id: "allow", label: t("permissions.settings.allow") },
      { id: "deny", label: t("permissions.settings.deny") },
      { id: "ask", label: t("permissions.settings.ask") },
    ];

    const capabilityKeys = new Set([
      "network", "file", "bash_io", "docker", "browser",
      "workflow", "git", "deploy", "desktop", "database", "misc", "mcp",
    ]);

    const knownTools = [
      "bash", "file_write", "file_edit", "apply_patch",
      "docker", "deploy", "database", "browser", "desktop",
    ];
    const knownCapabilities = Array.from(capabilityKeys);

    const ensureEntries = (keys: string[], existing: Record<string, import("./types.js").PermissionPolicy>) => {
      const entries: Array<[string, import("./types.js").PermissionPolicy]> = [];
      for (const key of keys) {
        entries.push([key, existing[key] || { value: "default", source: "default" }]);
      }
      for (const [key, policy] of Object.entries(existing)) {
        if (!keys.includes(key)) entries.push([key, policy]);
      }
      return entries;
    };

    const toolEntries = ensureEntries(knownTools, policies.tools);
    const capEntries = ensureEntries(knownCapabilities, policies.capabilities);

    const renderRows = (group: "tools" | "capabilities", entries: Array<[string, import("./types.js").PermissionPolicy]>) => {
      if (entries.length === 0) {
        return `<div class="empty-state">${t("permissions.settings.noItems")}</div>`;
      }
      return entries.map(([name, policy], idx) => {
        const divider = idx < entries.length - 1 ? '<div class="settings-item-divider"></div>' : "";
        const descKey = `permissions.settings.desc.${name}`;
        const desc = t(descKey as any) === descKey ? "" : t(descKey as any);
        return `
          <div class="settings-item-row" data-perm-group="${group}" data-perm-name="${this.esc(name)}">
            <div class="settings-item-info">
              <div class="settings-item-title">
                ${this.esc(name)}
                <span class="model-active-tag perm-source-${policy.source || "default"}">${policy.source || "default"}</span>
              </div>
              ${desc ? `<div class="settings-item-desc">${this.esc(desc)}</div>` : ""}
            </div>
            <div class="settings-item-control">
              ${this.renderDropdown(`perm-dd-${group}-${name}`, options, policy.value || "default", () => {})}
            </div>
          </div>
          ${divider}
        `;
      }).join("");
    };

    const toolsHtml = renderRows("tools", toolEntries);
    const capsHtml = renderRows("capabilities", capEntries);

    this.panels.permissions.innerHTML = `
      <div class="settings-section-title"><i data-lucide="wrench" class="lucide section-title-icon"></i> ${t("permissions.settings.tools")}</div>
      <div class="settings-card">${toolsHtml}</div>

      <div class="settings-section-title"><i data-lucide="zap" class="lucide section-title-icon"></i> ${t("permissions.settings.capabilities")}</div>
      <div class="settings-card">${capsHtml}</div>
    `;

    // Auto-save on every dropdown change.
    for (const group of ["tools", "capabilities"] as const) {
      const entries = group === "tools" ? toolEntries : capEntries;
      for (const [name, policy] of entries) {
        this.bindDropdown(`perm-dd-${group}-${name}`, (val) => {
          const payload: Record<string, string> = {};
          for (const g of ["tools", "capabilities"] as const) {
            const es = g === "tools" ? toolEntries : capEntries;
            for (const [n, p] of es) {
              const key = `perm-dd-${g}-${n}`;
              const wrap = document.getElementById(`${key}-wrap`);
              const trigger = wrap?.querySelector(".settings-dropdown-trigger span");
              const selectedOption = options.find(o => o.label === trigger?.textContent);
              payload[n] = selectedOption?.id ?? p.value ?? "default";
            }
          }
          // Update the changed value
          payload[name] = val;
          send({ type: "configure", config: { permission_settings: payload } });
          const next: import("./types.js").PermissionPolicies = { tools: {}, capabilities: {} };
          for (const [n, p] of toolEntries) {
            next.tools[n] = { value: (payload[n] as any) || p.value || "default", source: "user" };
          }
          for (const [n, p] of capEntries) {
            if (capabilityKeys.has(n)) {
              next.capabilities[n] = { value: (payload[n] as any) || p.value || "default", source: "user" };
            }
          }
          setPermissionPolicies(next);
        });
      }
    }

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panels.permissions });
    }
  }

  private renderMcp(): void {
    this.renderMcpList();
  }

  private renderAgent(): void {
    const agents = getState().subAgents || [];

    const tableContent = agents.length === 0
      ? `<div class="model-empty">${t("settings.noSubAgentsYet")}</div>`
      : `
        <div class="model-table">
          <div class="model-table-header">
            <div class="model-table-cell model-cell-name">${t("settings.subAgent")}</div>
            <div class="model-table-cell model-cell-provider">${t("settings.description")}</div>
            <div class="model-table-cell model-cell-actions">${t("settings.actions")}</div>
          </div>
          ${agents.map((a, i) => {
              const sourceLabel = a.source === "model" ? "model" : "user";
              return `
            <div class="model-table-row">
              <div class="model-table-cell model-cell-name">
                <span class="model-name-text">${this.esc(a.name)}</span>
                <span class="model-active-tag" style="margin-left:8px">${sourceLabel}</span>
              </div>
              <div class="model-table-cell model-cell-provider">
                <span class="skill-desc-text">${this.esc(a.description || "-")}</span>
              </div>
              <div class="model-table-cell model-cell-actions">
                <button class="btn-icon" data-action="edit" data-index="${i}">
                  <i data-lucide="pencil" class="lucide icon-sm"></i>
                </button>
                <button class="btn-icon" data-action="delete" data-index="${i}">
                  <i data-lucide="trash-2" class="lucide icon-sm"></i>
                </button>
              </div>
            </div>`}).join("")}
        </div>`;

    this.panels.agent.innerHTML = `
      <div class="settings-section-title"><i data-lucide="sparkles" class="lucide section-title-icon"></i> ${t("settings.agentManagement")}</div>
      <div class="settings-card">
        <div class="model-manage-header">
          <div class="model-manage-desc">${t("settings.agentInstructions")}</div>
          <button class="btn-add-model-top" id="btn-create-agent">
            <i data-lucide="plus" class="lucide"></i>
            <span>${t("settings.addSubAgent")}</span>
          </button>
        </div>
        ${tableContent}
      </div>`;

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panels.agent });
    }
  }

  private _renderAgentCreateDialog(existing?: import("./types.js").SubAgentConfig): void {
    const isEdit = !!existing;

    const bodyHtml = `
      <div class="model-form-row">
        <label class="model-form-label">${t("settings.subAgentName")} <span class="required-star">*</span></label>
        <input type="text" id="agent-name" class="model-form-input" value="${this.esc(existing?.name || "")}" placeholder="${t("settings.subAgentNamePlaceholder")}" />
      </div>
      <div class="model-form-row">
        <label class="model-form-label">${t("settings.description")}</label>
        <input type="text" id="agent-description" class="model-form-input" value="${this.esc(existing?.description || "")}" placeholder="${t("settings.subAgentDescPlaceholder")}" />
      </div>
      <div class="model-form-row">
        <label class="model-form-label">${t("settings.systemPrompt")}</label>
        <textarea id="agent-system-prompt" class="code-textarea" placeholder="${t("settings.subAgentSystemPromptPlaceholder")}" style="min-height:120px">${this.esc(existing?.system_prompt || "")}</textarea>
      </div>`;

    const title = isEdit ? t("settings.editSubAgent") : t("settings.addSubAgent");
    const { overlay, close } = this._showFormDialog(title, bodyHtml, true);

    const okBtn = overlay.querySelector("#dialog-form-ok") as HTMLButtonElement;
    okBtn.textContent = isEdit ? t("settings.saveChanges") : t("settings.addSubAgent");
    okBtn.addEventListener("click", () => {
      const name = (document.getElementById("agent-name") as HTMLInputElement)?.value?.trim();
      if (!name) {
        Dialog.alert(t("settings.subAgentNameRequired"), "");
        return;
      }

      const agents = getState().subAgents || [];
      const description = (document.getElementById("agent-description") as HTMLInputElement)?.value?.trim() || "";
      const systemPrompt = (document.getElementById("agent-system-prompt") as HTMLTextAreaElement)?.value || "";

      const newAgent = { name, description, system_prompt: systemPrompt };

      if (isEdit && existing) {
        const idx = agents.findIndex(a => a.name === existing.name);
        if (idx >= 0) {
          agents[idx] = newAgent;
        }
      } else {
        agents.push(newAgent);
      }

      send({ type: "update_sub_agents", agents: agents });
      close();
    });

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: overlay });
    }
  }

  private renderMemory(): void {
    const entries = getState().memoryList;
    const tFn = t;

    let rowsHtml = "";
    for (const entry of entries) {
      const title = entry.title || entry.name.replace(/\.md$/i, "");
      const memType = entry.type
        ? `<span class="model-active-tag" style="margin-left:8px">${this.esc(entry.type)}</span>`
        : "";
      rowsHtml += `
        <div class="model-table-row">
          <div class="model-table-cell model-cell-name">
            <span class="model-name-text">${this.esc(title)}</span>
            ${memType}
          </div>
          <div class="model-table-cell model-cell-actions">
            <button class="btn-icon" data-action="view-memory" data-path="${this.esc(entry.path)}" data-tooltip="${tFn("settings.view")}">
              <i data-lucide="eye" class="lucide"></i>
            </button>
          </div>
        </div>`;
    }

    const tableHtml = entries.length === 0
      ? `<div class="model-empty">${tFn("settings.noMemoryEntries")}</div>`
      : `
        <div class="model-table">
          <div class="model-table-header">
            <div class="model-table-cell model-cell-name">${tFn("settings.name")}</div>
            <div class="model-table-cell model-cell-actions">${tFn("settings.actions")}</div>
          </div>
          ${rowsHtml}
        </div>`;

    this.panels.memory.innerHTML = `
      <div class="settings-section-title"><i data-lucide="brain" class="lucide section-title-icon"></i> ${tFn("settings.memory")}</div>
      <div class="settings-card">
        <div class="model-manage-header">
          <div class="model-manage-desc">${tFn("settings.memoryDesc")}</div>
          <button class="btn-add-model-top" id="btn-refresh-memory">
            <i data-lucide="refresh-cw" class="lucide"></i>
            <span>${tFn("settings.refresh")}</span>
          </button>
        </div>
        ${tableHtml}
      </div>`;

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panels.memory });
    }
  }

  private _showMemoryDetailDialog(path: string): void {
    const tFn = t;
    const fileName = path.replace(/\.md$/i, "").split("/").pop() || path;
    const bodyHtml = `
      <div class="model-form-row">
        <label class="model-form-label">${tFn("settings.memoryFileName")}</label>
        <input type="text" class="model-form-input" value="${this.esc(fileName)}" readonly />
      </div>
      <div class="model-form-row">
        <label class="model-form-label">${tFn("settings.memoryContent")}</label>
        <div id="memory-detail-content" class="msg-text" style="max-height:60vh;overflow-y:auto;padding:12px 16px;background:var(--surface);border:1px solid var(--border);border-radius:8px">${tFn("settings.loading")}</div>
      </div>`;
    const { overlay, close } = this._showFormDialog(tFn("settings.view"), bodyHtml, true);
    const cancelBtn = overlay.querySelector("#dialog-form-cancel") as HTMLElement | null;
    if (cancelBtn) cancelBtn.style.display = "none";
    const okBtn = overlay.querySelector("#dialog-form-ok") as HTMLButtonElement;
    okBtn.textContent = tFn("header.close");
    okBtn.addEventListener("click", close);

    send({ type: "get_memory_detail", path });
  }

  private _renderUsageSection(): void {
    const el = this.panels.usage;
    if (!el) return;
    const stats = getState().usageStats;
    const accent = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#999";
    const muted = getComputedStyle(document.documentElement).getPropertyValue("--text-muted").trim() || "#666";

    if (!stats || stats.total_sessions === 0) {
      el.innerHTML = `
        <div class="settings-section-title"><i data-lucide="chart-column" class="lucide section-title-icon"></i> ${t("settings.usageStats")}</div>
        <div class="usage-empty">
          <div class="usage-empty-icon"><i data-lucide="chart-column" class="lucide"></i></div>
          <div class="usage-empty-text">${t("settings.noUsageData")}</div>
          <button class="btn" id="btn-refresh-usage-empty">${t("settings.refresh")}</button>
        </div>`;
      document.getElementById("btn-refresh-usage-empty")?.addEventListener("click", () => {
        send({ type: "get_usage_stats" });
      });
      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: el });
      }
      return;
    }

    // ── Group sessions by (day, model|channel) for a unified chart ──
    const sessions = stats.sessions || [];
    const groupBy = this._usageGroupBy;
    // Collect every day that has any session, sorted ascending.
    const daySet = new Set<string>();
    for (const s of sessions) {
      const dk = this._formatDayKey(s.first_active);
      if (dk) daySet.add(dk);
    }
    const allDays = Array.from(daySet).sort();
    // Cap the bar chart to the most recent 60 days so bars stay readable
    // with many models.  Older days are still counted in metrics and
    // shown in the heatmap; we just don't draw them in the daily chart.
    const BAR_CHART_DAY_LIMIT = 60;
    const days = allDays.slice(-BAR_CHART_DAY_LIMIT);

    // Collect every group (model or channel) that appears, sort by total tokens descending
    const groupTotals: Record<string, { tokens: number; status?: string }> = {};
    for (const s of sessions) {
      const g = groupBy === "model" ? (s.model || "(unknown model)") : this._channelDisplayName(s.channel || "normal");
      if (!groupTotals[g]) groupTotals[g] = { tokens: 0, status: s.model_status };
      groupTotals[g].tokens += s.total_tokens || 0;
    }
    const groupOrder = Object.keys(groupTotals).sort(
      (a, b) => (groupTotals[b].tokens - groupTotals[a].tokens) || a.localeCompare(b)
    );
    const groupColor: Record<string, string> = {};
    groupOrder.forEach((g, i) => {
      groupColor[g] = Settings.CHART_COLORS[i % Settings.CHART_COLORS.length];
    });

    // Build (day, group) → { tokens, count, turns, tools } matrix.
    const cellMap: Record<string, Record<string, { tokens: number; count: number; turns: number; tools: number }>> = {};
    for (const s of sessions) {
      const dk = this._formatDayKey(s.first_active);
      if (!dk) continue;
      const g = groupBy === "model" ? (s.model || "(unknown model)") : this._channelDisplayName(s.channel || "normal");
      if (!cellMap[dk]) cellMap[dk] = {};
      if (!cellMap[dk][g]) cellMap[dk][g] = { tokens: 0, count: 0, turns: 0, tools: 0 };
      const cell = cellMap[dk][g];
      cell.tokens += s.total_tokens || 0;
      cell.count += 1;
      cell.turns += s.turns || 0;
      cell.tools += s.tool_calls || 0;
    }

    const truncated = allDays.length > days.length;
    const unifiedChart = this._renderUnifiedDailyBarChart(days, groupOrder, cellMap, groupColor, muted, groupTotals, truncated, groupBy);
    const heatmap = this._renderUsageHeatmap(sessions, muted);

    el.innerHTML = `
      <div class="settings-section-title">
        <i data-lucide="chart-column" class="lucide section-title-icon"></i>
        ${t("settings.usageStats")}
        <button class="btn-icon" id="btn-refresh-usage" style="margin-left:auto" data-tooltip="${t("settings.refresh")}">
          <i data-lucide="refresh-cw" class="lucide"></i>
        </button>
      </div>

      <!-- Metrics row -->
      <div class="usage-metrics">
        <div class="usage-metric">
          <span class="usage-metric-value">${stats.total_sessions}</span>
          <span class="usage-metric-label">${t("settings.totalSessions")}</span>
        </div>
        <div class="usage-metric-vr"></div>
        <div class="usage-metric">
          <span class="usage-metric-value">${this._formatNumber(stats.total_tokens)}</span>
          <span class="usage-metric-label">${t("settings.totalTokens")}</span>
        </div>
        <div class="usage-metric-vr"></div>
        <div class="usage-metric">
          <span class="usage-metric-value">${this._formatNumber(stats.total_input_tokens)}</span>
          <span class="usage-metric-label">${t("settings.totalInputTokens")}</span>
        </div>
        <div class="usage-metric-vr"></div>
        <div class="usage-metric">
          <span class="usage-metric-value">${this._formatNumber(stats.total_output_tokens)}</span>
          <span class="usage-metric-label">${t("settings.totalOutputTokens")}</span>
        </div>
        <div class="usage-metric-vr"></div>
        <div class="usage-metric">
          <span class="usage-metric-value">${stats.total_tool_calls}</span>
          <span class="usage-metric-label">${t("settings.totalToolCalls")}</span>
        </div>
      </div>

      <!-- Activity heatmap (per-hour, all models combined) -->
      ${heatmap}

      <!-- Unified daily bar chart, grouped by model with legend -->
      ${unifiedChart}`;

    // Build / refresh the Chart.js instance on the canvas.  We stash the
    // data on the instance in _renderUnifiedDailyBarChart so we can
    // attach the Chart after innerHTML has placed the canvas in the DOM.
    if (this._usageBarChart) {
      this._usageBarChart.destroy();
      this._usageBarChart = null;
    }
    const canvas = el.querySelector("#usage-bar-chart") as HTMLCanvasElement | null;
    if (canvas && this._usageBarChartData) {
      const data = this._usageBarChartData;
      this._usageBarChart = new Chart(canvas, {
        type: "bar",
        data: { labels: data.labels, datasets: data.datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          animation: { duration: 250 },
          plugins: {
            legend: { display: false },
            // Native Chart.js tooltip disabled in favour of our global custom
            // tooltip (see tooltip.ts) which matches the app's design system.
            tooltip: { enabled: false },
          },
          onHover: (event: any, activeElements: any[]) => {
            if (!activeElements || activeElements.length === 0) {
              hideTooltip();
              return;
            }
            const idx = activeElements[0].index;
            const day = data.labels[idx];
            const lines = [`${day}`];
            let total = 0;
            for (const ds of data.datasets) {
              const v = (ds.data as any[])[idx] || 0;
              if (v > 0) {
                lines.push(`${ds.label}: ${this._formatNumber(v)}`);
                total += v;
              }
            }
            lines.push(`${t("settings.chartTotal")}: ${this._formatNumber(total)}`);
            const rect = canvas.getBoundingClientRect();
            const x = rect.left + (event?.x ?? rect.width / 2);
            const y = rect.top + (event?.y ?? 0);
            showTooltipAt(lines.join("\n"), x, y);
          },
          scales: {
            x: {
              stacked: true,
              grid: { color: "rgba(224,226,242,0.08)" },
              ticks: { color: muted, font: { size: 10 } },
            },
            y: {
              stacked: true,
              beginAtZero: true,
              grid: { color: "rgba(224,226,242,0.08)" },
              ticks: {
                color: muted,
                font: { size: 10 },
                callback: (v: any) => this._formatNumber(Number(v)),
              },
            },
          },
        },
      });
    }

    canvas?.addEventListener("mouseleave", () => hideTooltip());

    document.getElementById("btn-refresh-usage")?.addEventListener("click", () => {
      send({ type: "get_usage_stats" });
    });

    // Mode toggle for chart grouping
    el.querySelectorAll(".usage-groupby-seg .seg-item").forEach((btn) => {
      btn.addEventListener("click", () => {
        const mode = (btn as HTMLElement).getAttribute("data-groupby") as "model" | "channel";
        if (mode && mode !== this._usageGroupBy) {
          this._usageGroupBy = mode;
          this._renderUsageSection();
        }
      });
    });

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: el });
    }
  }

  /** Map channel identifier to a display label. */
  private _channelDisplayName(channel: string): string {
    const labels: Record<string, string> = {
      normal: t("settings.modeNormal"),
      iwork: "iWork",
      iclaw: "iClaw",
      sub_agent: t("settings.modeAutomation"),
    };
    return labels[channel] || channel;
  }

  /** YYYY-MM-DD key for grouping sessions by calendar day (local time). */
  private _formatDayKey(timestamp: number): string {
    if (!timestamp || timestamp <= 0) return "";
    const d = new Date(timestamp * 1000);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  /**
   * Render one unified bar chart covering all models.  X axis = days,
   * Y axis = tokens per day.  Each day's bar is a single stacked column
   * where every model contributes one colored segment (fixed color from
   * :data:`Settings.CHART_COLORS`).  Stacked layout means all models
   * share the same bar per day, distinguished only by color.  A legend
   * below the chart maps every model name to its color and shows a
   * "(deleted)" / "(unknown)" tag for historical-only models.
   */
  private _renderUnifiedDailyBarChart(
    days: string[],
    groupOrder: string[],
    cellMap: Record<string, Record<string, { tokens: number; count: number; turns: number; tools: number }>>,
    groupColor: Record<string, string>,
    muted: string,
    groupTotals: Record<string, { tokens: number; status?: string }>,
    truncated: boolean = false,
    groupBy: "model" | "channel" = "model",
  ): string {
    if (days.length === 0 || groupOrder.length === 0) return "";

    // Build Chart.js datasets: one stacked bar per group, all sharing
    // the same x-axis (one stack per day).
    const datasets = groupOrder.map((g) => ({
      label: g,
      data: days.map((d) => cellMap[d]?.[g]?.tokens || 0),
      backgroundColor: groupColor[g],
      borderColor: groupColor[g],
      borderWidth: 0,
      borderRadius: 2,
      maxBarThickness: 28,
      stack: "usage",
    }));
    const labels = days.map((d) => this._shortDay(d));
    this._usageBarChartData = { labels, datasets };

    // Legend: every group gets a swatch + name + total.
    const legendItems = groupOrder.map((g) => {
      const color = groupColor[g];
      const total = groupTotals[g]?.tokens || 0;
      const status = groupTotals[g]?.status;
      const tag = groupBy === "model" && status === "deleted" ? `<span class="usage-model-tag usage-model-tag--deleted">${t("settings.deletedModel")}</span>`
                 : groupBy === "model" && status === "unknown" ? `<span class="usage-model-tag usage-model-tag--unknown">${t("settings.unknownModel")}</span>`
                 : "";
      const display = g.length > 32 ? this.esc(g.slice(0, 32) + "...") : this.esc(g);
      return `
        <div class="usage-legend-item">
          <span class="usage-model-dot" style="background:${color}"></span>
          <span class="usage-legend-name">${display}</span>
          ${tag}
          <span class="usage-legend-tokens">${this._formatNumber(total)}</span>
        </div>`;
    }).join("");

    const titleKey = groupBy === "model" ? "settings.dailyUsageByModel" : "settings.dailyUsageByChannel";

    return `
      <div class="usage-chart-box">
        <div class="usage-chart-title">
          <i data-lucide="bar-chart-3" class="lucide"></i>
          ${t(titleKey)}
          <div class="seg usage-groupby-seg">
            <button class="seg-item${groupBy === "model" ? " active" : ""}" data-groupby="model" aria-selected="${groupBy === "model" ? "true" : "false"}">${t("settings.usageGroupByModel")}</button>
            <button class="seg-item${groupBy === "channel" ? " active" : ""}" data-groupby="channel" aria-selected="${groupBy === "channel" ? "true" : "false"}">${t("settings.usageGroupByMode")}</button>
          </div>
        </div>
        <div class="usage-heatmap-stats">
          ${truncated ? `<div class="usage-heatmap-stat"><span>${t("settings.olderDaysHidden")}</span></div>` : ""}
        </div>
        <div class="usage-chart-canvas-wrap">
          <canvas id="usage-bar-chart"></canvas>
        </div>
        <div class="usage-legend">${legendItems}</div>
      </div>`;
  }

  /** "2026-06-22" -> "Jun 22" for compact X-axis labels. */
  private _shortDay(iso: string): string {
    if (!iso) return "";
    const parts = iso.split("-");
    if (parts.length !== 3) return iso;
    const d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString(getLocale() === "zh" ? "zh-CN" : "en-US", { month: "short", day: "numeric" });
  }

  /**
    * Render a daily activity heatmap.  Each day is one column with 6
    * rows, one per 4-hour block of the day (00:00 at the top, 20:00 at
    * the bottom) × N day columns (one per calendar day, newest on the
    * right).  Cell color encodes total tokens consumed during that
    * 4-hour block of that day, summed across every model.
   *
   * Color scale: empty = light/neutral, more activity = deeper brand
   * green.  The user wanted "less = white, more = green", which means
   * an empty cell is NOT a dark block -- it's the panel background
   * with just a thin border, so the chart reads as mostly white with
   * green dots marking activity.
   *
   * Layout is intentionally compact: small cells, small fonts, and
   * the SVG total width grows with the day count so the container
   * scrolls horizontally for long histories.
   */
   private _renderUsageHeatmap(sessions: UsageStatsSessionEntry[], muted: string): string {
    if (!sessions || sessions.length === 0) return "";
    const loc = getLocale() === "zh" ? "zh-CN" : "en-US";

    // Aggregate sessions by (day, 4-hour block).  Each day is one column
    // with BLOCKS rows; every row spans 4 hours of the day so the chart
    // stays compact (6 rows instead of 24 tiny hourly boxes).
    const BLOCK_HOURS = 4;
    const BLOCKS = Math.floor(24 / BLOCK_HOURS); // 6 rows
    const cellTokens: Record<string, number> = {};
    for (const s of sessions) {
      if (!s.first_active) continue;
      const d = new Date(s.first_active * 1000);
      if (isNaN(d.getTime())) continue;
      const dayKey = this._formatDayKey(s.first_active);
      if (!dayKey) continue;
      const block = Math.floor(d.getHours() / BLOCK_HOURS);
      cellTokens[`${dayKey}|${block}`] = (cellTokens[`${dayKey}|${block}`] || 0) + (s.total_tokens || 0);
    }

    // Determine the date range.  Always show at least MIN_DAYS of
    // calendar so a user with one session doesn't see a single bar.
    const MIN_DAYS = 30;    // minimum visible days (~1 month)
    const MAX_DAYS = 92;    // cap at the recent 3 months (this month + previous 2)
    const latestMs = Math.max(...sessions.filter(s => s.first_active).map(s => s.first_active * 1000));
    const earliestMs = Math.min(...sessions.filter(s => s.first_active).map(s => s.first_active * 1000));
    const latestDate = new Date(latestMs);
    const earliestDate = new Date(earliestMs);
    let startDate = new Date(earliestDate);
    startDate.setHours(0, 0, 0, 0);
    const endDate = new Date(latestDate);
    endDate.setHours(0, 0, 0, 0);
    const totalDays = Math.round((endDate.getTime() - startDate.getTime()) / 86400000) + 1;
    let numDays = totalDays;
    if (numDays < MIN_DAYS) {
      // Pad backwards so we always show at least MIN_DAYS columns.
      const newStart = new Date(endDate);
      newStart.setDate(newStart.getDate() - (MIN_DAYS - 1));
      startDate = newStart;
      numDays = MIN_DAYS;
    } else if (numDays > MAX_DAYS) {
      // Crop to the most recent MAX_DAYS so the chart stays readable.
      const newStart = new Date(endDate);
      newStart.setDate(newStart.getDate() - (MAX_DAYS - 1));
      startDate = newStart;
      numDays = MAX_DAYS;
    }

    // Max value for color scaling.
    let maxCell = 0;
    for (const k of Object.keys(cellTokens)) {
      if (cellTokens[k] > maxCell) maxCell = cellTokens[k];
    }
    if (maxCell <= 0) {
      // No usage at all -- still render the grid so the user sees the shape.
      maxCell = 1;
    }

    // Layout -- square cells that fill the panel width.  With only
    // BLOCKS (6) rows the chart stays short; each cell spans 4 hours.
    // The chart is capped at the recent 3 months (this month + the
    // previous two) and scales to fit the panel (no horizontal scroll),
    // so the cells spread out to fill the available width.
    const cellW = 11, cellH = 11, cellGap = 3;
    const cellRadius = 1;
    const PL = 6, PR = 6, PT = 18, PB = 18;
    // Stretch the day columns to fill the panel: a wider per-day stride
    // for short histories (so it isn't a narrow strip) and a tighter one
    // for the full 3 months (so it still fits without scrolling).
    const MIN_DAY_STRIDE = 9; // min px per day column
    const TARGET_TOTAL_W = 1100; // preferred full width
    const naturalStride = cellW + cellGap;
    const idealStride = Math.max(MIN_DAY_STRIDE, Math.min(naturalStride * 2, TARGET_TOTAL_W / numDays));
    const stride = Math.max(MIN_DAY_STRIDE, Math.min(naturalStride * 2, idealStride));
    const W = PL + numDays * stride - cellGap + PR;
    const H = PT + BLOCKS * (cellH + cellGap) - cellGap + PB;

    // Today marker -- highlight the column for today.
    const todayKey = this._formatDayKey(Math.floor(Date.now() / 1000));

    // Color ramp: 5 stops.  Empty cell is the panel background
    // (almost transparent over the chart box), so empty reads as
    // "white" / "no color".  Activity is brand green at increasing
    // alpha over a near-white base, so the chart visually inverts to
    // "less = white, more = green" as the user asked.
    //
    // The brand color is var(--bg-bg-brand, #32f08c); the base is
    // var(--bg-bg-base-secondary, #222427) for dark and #ffffff for
    // light.  We pick the base from the active theme.
    const baseBg = "var(--usage-hm-base, #ffffff)";
    const emptyColor = "var(--usage-hm-empty, #f3f4f6)";
    const ramp = [
      emptyColor,
      `color-mix(in srgb, var(--bg-bg-brand, #32f08c) 22%, ${baseBg})`,
      `color-mix(in srgb, var(--bg-bg-brand, #32f08c) 45%, ${baseBg})`,
      `color-mix(in srgb, var(--bg-bg-brand, #32f08c) 70%, ${baseBg})`,
      `color-mix(in srgb, var(--bg-bg-brand, #32f08c) 92%, ${baseBg})`,
    ];
    const pickColor = (v: number): string => {
      if (v <= 0) return ramp[0];
      const t = v / maxCell;
      let idx = 1;
      if (t > 0.75) idx = 4;
      else if (t > 0.5) idx = 3;
      else if (t > 0.25) idx = 2;
      return ramp[idx];
    };

    // No left-axis hour labels (removed per user request); cells start
    // at the panel edge.

    // Day labels along the bottom: ONLY month names (e.g. "7月"),
    // shown once at the first column of each month.  No day numbers, no
    // weekly ticks -- the user explicitly wants month-only axis labels.
    const dayLabels: string[] = [];
    let lastMonth = -1;
    for (let d = 0; d < numDays; d++) {
      const colDate = new Date(startDate);
      colDate.setDate(colDate.getDate() + d);
      const m = colDate.getMonth();
      if (m !== lastMonth) {
        lastMonth = m;
        const x = PL + d * stride + cellW / 2;
        const label = colDate.toLocaleDateString(loc, { month: "short" });
        dayLabels.push(
           `<text x="${x.toFixed(1)}" y="${(PT + BLOCKS * (cellH + cellGap) + 13).toFixed(1)}" ` +
          `text-anchor="middle" ` +
          `fill="var(--text-text-secondary, #9599a6)" ` +
          `style="font-size:12px;font-weight:var(--font-weight-medium,500);font-family:var(--font-family-default);">` +
          `${label}</text>`
        );
      }
    }

    // Cells: one per (day, 4-hour block).  Only render cells inside the
    // data range; padding cells stay empty (drawn with the empty color).
    // The native SVG <title> is replaced by data-tooltip so our global
    // custom tooltip (tooltip.ts) renders the hover hint instead.
    const cells: string[] = [];
    for (let d = 0; d < numDays; d++) {
      const colDate = new Date(startDate);
      colDate.setDate(colDate.getDate() + d);
      const dayKey = this._formatDayKey(Math.floor(colDate.getTime() / 1000));
      const isToday = dayKey === todayKey;
      for (let b = 0; b < BLOCKS; b++) {
        const v = cellTokens[`${dayKey}|${b}`] || 0;
        const x = PL + d * stride;
        const y = PT + b * (cellH + cellGap);
        const fill = pickColor(v);
        const startH = b * BLOCK_HOURS;
        const endH = startH + BLOCK_HOURS;
        const tooltip = v > 0
          ? `${dayKey} ${String(startH).padStart(2, "0")}:00–${String(endH).padStart(2, "0")}:00\n${this._formatNumber(v)} tokens`
          : `${dayKey} ${String(startH).padStart(2, "0")}:00–${String(endH).padStart(2, "0")}:00\nNo activity`;
        // Empty cells get a hairline border so the grid is visible
        // even on a fully-empty day.  Today's column gets a slightly
        // thicker green ring on the topmost block (b=0) to anchor the
        // eye.
        const stroke = isToday && b === 0
          ? "var(--bg-bg-brand, #32f08c)"
          : "var(--border-border-neutral-l1, rgba(224,226,242,0.18))";
        const strokeW = isToday && b === 0 ? 1 : 0.4;
        cells.push(
          `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${cellW}" height="${cellH}" ` +
          `rx="${cellRadius}" ry="${cellRadius}" fill="${fill}" ` +
          `stroke="${stroke}" stroke-width="${strokeW}" class="usage-hm-cell" ` +
          `data-day="${this.esc(dayKey)}" data-block="${b}" ` +
          `data-tooltip="${this.esc(tooltip)}"></rect>`
        );
      }
    }

    // Legend row at the bottom -- "Less" ... ramp swatches ... "More".
    const legendCellSize = 11;
    const legendGap = 3;
    const legendW = ramp.length * legendCellSize + (ramp.length - 1) * legendGap;
    const legendRects = ramp.map((c, i) =>
      `<rect x="${i * (legendCellSize + legendGap)}" y="0" width="${legendCellSize}" height="${legendCellSize}" rx="0" ry="0" ` +
      `fill="${c}" stroke="var(--border-border-neutral-l1, rgba(224,226,242,0.18))" stroke-width="0.4"/>`
    ).join("");

    // Aggregate stats for the caption row.
    const daySet = new Set<string>();
    for (const s of sessions) {
      if (!s.first_active) continue;
      const k = this._formatDayKey(s.first_active);
      if (k) daySet.add(k);
    }
    const activeDays = daySet.size;
    const captionParts = [
      `<span class="usage-heatmap-num">${activeDays}</span> <span>${t("settings.activeDays") || "active days"}</span>`,
      `<span class="usage-heatmap-num">${numDays}</span> <span>${t("settings.days") || "days"}</span>`,
      `<span class="usage-heatmap-num">24</span> <span>${t("settings.hoursPerDay") || "hours"}</span>`,
    ];
    const captionHtml = captionParts
      .map(p => `<div class="usage-heatmap-stat">${p}</div>`)
      .join('<div class="usage-heatmap-stat-divider"></div>');

    return `
      <div class="usage-chart-box usage-chart-box--compact">
        <div class="usage-chart-title">
          <i data-lucide="calendar-days" class="lucide"></i>
          ${t("settings.activityHeatmap") || "Activity heatmap"}
        </div>
        <div class="usage-heatmap-stats usage-heatmap-stats--compact">${captionHtml}</div>
        <div class="usage-heatmap-scroll">
          <svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMinYMid meet" style="width:100%;height:auto;display:block">
            ${cells.join("")}
            ${dayLabels.join("")}
          </svg>
        </div>
        <div class="usage-heatmap-legend usage-heatmap-legend--compact">
          <span class="usage-heatmap-legend-label">${t("settings.less") || "Less"}</span>
          <svg width="${legendW}" height="${legendCellSize}" viewBox="0 0 ${legendW} ${legendCellSize}" xmlns="http://www.w3.org/2000/svg">${legendRects}</svg>
          <span class="usage-heatmap-legend-label">${t("settings.more") || "More"}</span>
        </div>
      </div>`;
  }

  /* ── SVG Chart Helpers ─────────────────────────────────────────── */

  private static readonly CHART_COLORS = [
    "#22c55e", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6",
    "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16",
    "#06b6d4", "#d946ef", "#0ea5e9", "#eab308", "#10b981",
  ];

  private _renderSvgLineChart(sessions: UsageStatsSessionEntry[], accent: string, muted: string): string {
    const W = 600, H = 200;
    const PT = 16, PR = 16, PB = 32, PL = 48;
    const cw = W - PL - PR, ch = H - PT - PB;
    const values = sessions.map(s => s.total_tokens);
    const maxVal = Math.max(...values, 1);
    const n = sessions.length;

    const points = values.map((v, i) => ({
      x: PL + (n > 1 ? (i / (n - 1)) * cw : cw / 2),
      y: PT + ch - (v / maxVal) * ch,
      v,
      s: sessions[i],
    }));

    // Y axis grid
    const gridY: { y: number; label: string }[] = [];
    for (let i = 0; i <= 4; i++) {
      const y = PT + (i / 4) * ch;
      gridY.push({ y, label: this._formatNumber(Math.round(maxVal * (1 - i / 4))) });
    }

    // X axis labels
    const xLabels: { x: number; label: string }[] = [];
    const labelCount = Math.min(n, 6);
    const step = Math.max(1, Math.floor((n - 1) / (labelCount - 1)));
    for (let i = 0; i < n; i += step) {
      xLabels.push({ x: points[i].x, label: this._formatSessionDate(sessions[i].first_active) });
    }
    if (xLabels.length === 0 || xLabels[xLabels.length - 1].x !== points[n - 1].x) {
      xLabels.push({ x: points[n - 1].x, label: this._formatSessionDate(sessions[n - 1].first_active) });
    }

    const polyPts = points.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
    const areaPath = n > 0
      ? `M${points[0].x.toFixed(1)},${PT + ch} L${polyPts} L${points[n - 1].x.toFixed(1)},${PT + ch} Z`
      : "";
    const gradId = "lg-" + Math.random().toString(36).slice(2, 8);

    return `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;display:block">
      <defs>
        <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${accent}" stop-opacity="0.25"/>
          <stop offset="100%" stop-color="${accent}" stop-opacity="0.02"/>
        </linearGradient>
      </defs>
      ${gridY.map(g => `
        <line x1="${PL}" y1="${g.y}" x2="${W - PR}" y2="${g.y}" stroke="var(--border-light, #222)" stroke-width="1"/>
        <text x="${PL - 6}" y="${g.y + 4}" text-anchor="end" fill="${muted}" font-size="10">${g.label}</text>`).join("")}
      <path d="${areaPath}" fill="url(#${gradId})"/>
      <polyline points="${polyPts}" fill="none" stroke="${accent}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
      ${points.map(p => {
        const dateStr = this._formatSessionDate(p.s.first_active);
        const modelName = p.s.model && p.s.model !== "unknown" ? p.s.model : "";
        const tooltipLines = [
          dateStr ? `Date: ${dateStr}` : "",
          `Tokens: ${p.v.toLocaleString()}`,
          modelName ? `Model: ${modelName}` : "",
          `Turns: ${p.s.turns}`,
          `Tool calls: ${p.s.tool_calls}`,
        ].filter(Boolean).join("  |  ");
        return `<g style="cursor:pointer">
          <circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="10" fill="transparent" stroke="transparent" stroke-width="10">
            <title>${this.esc(tooltipLines)}</title>
          </circle>
          <circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="3" fill="${accent}" stroke="var(--bg-primary, #000)" stroke-width="1.5" pointer-events="none"/>
        </g>`;
      }).join("")}
      ${xLabels.map(xl => `<text x="${xl.x}" y="${H - 4}" text-anchor="middle" fill="${muted}" font-size="9">${this.esc(xl.label)}</text>`).join("")}
    </svg>`;
  }

  private _renderSvgDonutChart(entries: [string, { total_tokens: number }][], accent: string): string {
    const total = entries.reduce((s, [, v]) => s + v.total_tokens, 0);
    const sorted = [...entries].sort((a, b) => b[1].total_tokens - a[1].total_tokens);
    const CX = 100, CY = 100, R = 68, SW = 26;
    const circ = 2 * Math.PI * R;

    let segments = "";
    let offset = 0;
    sorted.forEach(([name, data], i) => {
      const pct = data.total_tokens / total;
      const len = Math.max(circ * pct, 0.5);
      const color = Settings.CHART_COLORS[i % Settings.CHART_COLORS.length];
      const pctDisplay = (pct * 100).toFixed(1);
      const displayName = name === "unknown" ? "Unknown" : name;
      segments += `<g style="cursor:pointer">
        <circle cx="${CX}" cy="${CY}" r="${R}" fill="none" stroke="transparent" stroke-width="${SW + 8}" style="cursor:pointer">
          <title>${this.esc(displayName)}: ${this._formatNumber(data.total_tokens)} tokens (${pctDisplay}%)</title>
        </circle>
        <circle cx="${CX}" cy="${CY}" r="${R}" fill="none" stroke="${color}" stroke-width="${SW}"
        stroke-dasharray="${len.toFixed(1)} ${(circ - len).toFixed(1)}"
        stroke-dashoffset="${(-offset).toFixed(1)}"
        transform="rotate(-90, ${CX}, ${CY})" stroke-linecap="butt" pointer-events="none"/>
      </g>`;
      offset += len;
    });

    // Legend
    const maxLegend = 8;
    const legendItems = sorted.slice(0, maxLegend);
    const legend = legendItems.map(([name, data], i) => {
      const pct = ((data.total_tokens / total) * 100).toFixed(1);
      const displayName = name === "unknown" ? "Unknown" : name;
      return `<div class="donut-legend-item">
        <span class="donut-legend-dot" style="background:${Settings.CHART_COLORS[i % Settings.CHART_COLORS.length]}"></span>
        <span class="donut-legend-label" : displayName)}</span>
        <span class="donut-legend-value">${pct}%</span>
      </div>`;
    }).join("");
    const more = sorted.length > maxLegend ? `<div class="donut-legend-item"><span class="donut-legend-label" style="color:var(--text-muted)">+${sorted.length - maxLegend} more</span></div>` : "";

    return `<div class="donut-wrap">
      <div class="donut-svg">
        <svg viewBox="0 0 200 200" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;max-width:180px">
          ${segments}
          <text x="${CX}" y="${CY - 6}" text-anchor="middle" fill="var(--text-primary)" font-size="18" font-weight="700">${this._formatNumber(total)}</text>
          <text x="${CX}" y="${CY + 12}" text-anchor="middle" fill="${accent}" font-size="10">tokens</text>
        </svg>
      </div>
      <div class="donut-legend">${legend}${more}</div>
    </div>`;
  }

  private _renderSvgToolBar(entries: [string, number][], secondary: string): string {
    const sorted = [...entries].sort((a, b) => b[1] - a[1]).slice(0, 10);
    if (sorted.length === 0) return `<div class="chart-empty">${t("settings.noToolData")}</div>`;
    const maxVal = sorted[0][1] || 1;
    const BH = 26, H = sorted.length * BH + 8, W = 400, PL = 100, PR = 50, PT = 4;
    const bw = W - PL - PR;

    const bars = sorted.map(([name, count], i) => {
      const y = PT + i * BH;
      const w = (count / maxVal) * bw;
      const color = Settings.CHART_COLORS[(i + 3) % Settings.CHART_COLORS.length];
      return `
        <text x="${PL - 8}" y="${y + 16}" text-anchor="end" fill="var(--text-secondary, #999)" font-size="11">${this.esc(name.length > 16 ? name.slice(0, 16) + "..." : name)}</text>
        <rect x="${PL}" y="${y + 3}" width="${Math.max(w, 4)}" height="18" rx="4" fill="${color}" opacity="0.85"/>
        <text x="${PL + Math.max(w, 4) + 5}" y="${y + 16}" fill="var(--text-primary)" font-size="11" font-weight="600">${count}</text>`;
    }).join("");

    return `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;display:block">${bars}</svg>`;
  }

  private _formatSessionDate(timestamp: number): string {
    if (!timestamp || timestamp <= 0) return "";
    const d = new Date(timestamp * 1000);
    const loc = getLocale() === "zh" ? "zh-CN" : "en-US";
    const now = Date.now();
    if (now - timestamp * 1000 < 86400000) {
      return d.toLocaleTimeString(loc, { hour: "2-digit", minute: "2-digit" });
    }
    return d.toLocaleDateString(loc, { month: "short", day: "numeric" });
  }

  private _formatNumber(n: number): string {
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
    if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
    return n.toLocaleString();
  }

  private renderDeveloper(): void {
    this.panels.developer.innerHTML = `
      <div class="settings-section-title"><i data-lucide="code" class="lucide section-title-icon"></i> ${t("settings.devPanelTitle")}</div>
      <div class="settings-card">
        <div class="settings-item-row">
          <div class="settings-item-info">
            <div class="settings-item-title">${t("settings.devDevToolsTitle")}</div>
            <div class="settings-item-desc">${t("settings.devDevToolsDesc")}</div>
          </div>
          <div class="settings-item-control">
            <button class="btn btn-sm" id="dev-open-devtools">${t("settings.devDevToolsBtn")}</button>
          </div>
        </div>
        <div class="settings-item-divider"></div>
        <div class="settings-item-row">
          <div class="settings-item-info">
            <div class="settings-item-title">${t("settings.devCloseTitle")}</div>
            <div class="settings-item-desc">${t("settings.devCloseDesc")}</div>
          </div>
          <div class="settings-item-control">
            <button class="btn btn-sm" id="dev-close-mode" style="color:var(--error)">${t("settings.devCloseBtn")}</button>
          </div>
        </div>
      </div>
      <div class="settings-section-title" style="margin-top:24px"><i data-lucide="rotate-ccw" class="lucide section-title-icon"></i> ${t("settings.devRestartTitle")}</div>
      <div class="settings-card">
        <div class="settings-item-row">
          <div class="settings-item-info">
            <div class="settings-item-title">${t("settings.devRestartAppTitle")}</div>
            <div class="settings-item-desc">${t("settings.devRestartAppDesc")}</div>
          </div>
          <div class="settings-item-control">
            <button class="btn btn-sm" id="dev-reset-state" style="color:var(--error)">${t("settings.devRestartBtn")}</button>
          </div>
        </div>
        <div class="settings-item-divider"></div>
        <div class="settings-item-row">
          <div class="settings-item-info">
            <div class="settings-item-title">${t("settings.devRestartServerTitle")}</div>
            <div class="settings-item-desc">${t("settings.devRestartServerDesc")}</div>
          </div>
          <div class="settings-item-control">
            <button class="btn btn-sm" id="dev-restart-server" style="color:var(--error)">${t("settings.devRestartBtn")}</button>
          </div>
        </div>
      </div>`;

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panels.developer });
    }

    document.getElementById("dev-close-mode")?.addEventListener("click", () => {
      setDevModeEnabled(false);
      this.updateSidebarNav();
      this.switchPanel("general");
    });

    document.getElementById("dev-open-devtools")?.addEventListener("click", () => {
      window.electronAPI?.toggleDevTools();
    });

    document.getElementById("dev-reset-state")?.addEventListener("click", async () => {
      const confirmed = await Dialog.confirm(t("settings.devRestartAppTitle"), t("settings.devRestartAppDesc"));
      if (!confirmed) return;
      localStorage.clear();
      location.reload();
    });

    document.getElementById("dev-restart-server")?.addEventListener("click", async () => {
      const running = getState().running;
      if (running) {
        const ok = await Dialog.confirm(t("settings.devRestartRunningTitle"), t("settings.devRestartRunningDesc"));
        if (!ok) return;
      }
      const confirmed = await Dialog.confirm(t("settings.devRestartTitle"), t("settings.devRestartServerDesc"));
      if (!confirmed) return;
      const prog = Dialog.progress(t("settings.devRestartProgressTitle"), "");
      const cleanup = (window as any).electronAPI?.onRestartProgress?.((data: { progress: number }) => {
        const p = data.progress;
        let msg: string;
        if (p <= 20) msg = t("settings.devRestartPhaseKill");
        else if (p <= 50) msg = t("settings.devRestartPhasePort");
        else msg = t("settings.devRestartPhaseStart");
        prog.update(p, msg);
      });
      try {
        const result = await window.electronAPI?.restartService?.();
        if (result?.success) {
          prog.succeed(t("settings.devRestartSucceed"));
        } else {
          prog.fail(t("settings.devRestartFailed") + (result?.error ? ": " + result.error : ""));
        }
      } catch (err) {
        prog.fail(t("settings.devRestartFailed") + ": " + String(err));
      } finally {
        if (cleanup) cleanup();
      }
    });
  }

  private renderStorage(): void {
    this.panels.storage.innerHTML = `
      <div class="settings-section-title"><i data-lucide="hard-drive" class="lucide section-title-icon"></i> ${t("settings.storage")}</div>
      <div class="settings-card">
        <div class="settings-item-row">
          <div class="settings-item-info">
            <div class="settings-item-title">${t("settings.aboutLogs")}</div>
            <div class="settings-item-desc">${t("settings.aboutLogsDesc")}</div>
          </div>
          <div class="settings-item-control">
            <button class="btn btn-sm" id="storage-open-logs">${t("settings.aboutLogs")}</button>
          </div>
        </div>
        <div class="settings-item-divider"></div>
        <div class="settings-item-row">
          <div class="settings-item-info">
            <div class="settings-item-title">${t("settings.storageDataDir")}</div>
            <div class="settings-item-desc">${t("settings.aboutOpenDataDir")}</div>
          </div>
          <div class="settings-item-control">
            <button class="btn btn-sm" id="storage-open-data-dir">${t("settings.aboutOpenDataDir")}</button>
          </div>
        </div>
        <div class="settings-item-divider"></div>
        <div class="settings-item-row">
          <div class="settings-item-info">
            <div class="settings-item-title">${t("settings.storageSessions")}</div>
            <div class="settings-item-desc">${t("settings.storageSessionsDesc")}</div>
          </div>
          <div class="settings-item-control">
            <button class="btn btn-sm" id="storage-clear-sessions" style="color:var(--error)">${t("settings.storageClearSessions")}</button>
          </div>
        </div>
        <div class="settings-item-divider"></div>
        <div class="settings-item-row">
          <div class="settings-item-info">
            <div class="settings-item-title">${t("settings.browserData")}</div>
            <div class="settings-item-desc">${t("settings.browserDataDesc")}</div>
          </div>
          <div class="settings-item-control">
            <button class="btn btn-sm" id="storage-clear-browser" style="color:var(--error)">${t("settings.clear")}</button>
          </div>
        </div>
      </div>`;

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panels.storage });
    }

    // Open data directory
    document.getElementById("storage-open-data-dir")?.addEventListener("click", async () => {
      const appPath = await window.electronAPI?.getAppPath?.();
      if (appPath) {
        window.electronAPI?.openFolder?.(appPath);
      }
    });

    // Clear sessions
    document.getElementById("storage-clear-sessions")?.addEventListener("click", async () => {
      const ok = await Dialog.confirm(t("common.confirmClearSessionsTitle"), t("common.confirmClearSessions"));
      if (ok) {
        send({ type: "clear_all_sessions" } as any);
      }
    });

    // Clear browser data
    document.getElementById("storage-clear-browser")?.addEventListener("click", async () => {
      const ok = await Dialog.confirm(t("settings.confirmClearBrowserDataTitle"), t("settings.confirmClearBrowserData"));
      if (ok) {
        window.electronAPI?.browserClearData?.();
      }
    });

    // Open logs
    document.getElementById("storage-open-logs")?.addEventListener("click", async () => {
      await window.electronAPI?.openChildWindow("logs", t("settings.aboutLogs") || "Logs");
    });
  }

  private renderAbout(): void {
    const tFn = t;

    const legalLinks: Array<{ icon: string; label: string; key: string }> = [
      { icon: "file-text", label: tFn("settings.aboutLicense"), key: "license" },
      { icon: "shield", label: tFn("settings.aboutPrivacy"), key: "privacy" },
      { icon: "scroll", label: tFn("settings.aboutTerms"), key: "terms" },
      { icon: "heart", label: tFn("settings.aboutThanks"), key: "thanks" },
      { icon: "database", label: tFn("settings.aboutDataRules"), key: "data-rules" },
      { icon: "shield", label: tFn("settings.aboutMinors"), key: "minors" },
    ];

    const supportLinks: Array<{ icon: string; label: string; key: string }> = [
      { icon: "book-open", label: tFn("settings.aboutDocs"), key: "docs" },
      { icon: "bug", label: tFn("settings.aboutReportBug"), key: "report-bug" },
      { icon: "users", label: tFn("settings.aboutCommunity"), key: "community" },
      { icon: "mail", label: tFn("settings.aboutContact"), key: "contact" },
    ];

    const legalHtml = legalLinks.map(l => `
      <button class="about-link-row" type="button" data-link="${l.key}" data-label="${this.esc(l.label)}">
        <span class="about-link-icon"><i data-lucide="${l.icon}"></i></span>
        <span class="about-link-label">${l.label}</span>
        <span class="about-link-chevron"><i data-lucide="chevron-right"></i></span>
      </button>
    `).join("");

    const supportHtml = supportLinks.map(l => `
      <button class="about-link-row" type="button" data-link="${l.key}" data-label="${this.esc(l.label)}">
        <span class="about-link-icon"><i data-lucide="${l.icon}"></i></span>
        <span class="about-link-label">${l.label}</span>
        <span class="about-link-chevron"><i data-lucide="chevron-right"></i></span>
      </button>
    `).join("");

    const dv = this._versions?.desktop || APP_VERSION;
    const av = this._versions?.agent || APP_VERSION;

    this.panels.about.innerHTML = `
      <div class="about-banner">
        <div class="about-banner-glow"></div>
        <div class="about-banner-title">Encre Agent</div>
      </div>

      <div class="about-info-card">
        <div class="about-info-row" data-key="version" data-version="agent">
          <span class="about-info-label">Encre Agent</span>
          <span class="about-info-value">v${av}</span>
        </div>
        <div class="about-info-row" data-key="version" data-version="desktop">
          <span class="about-info-label">Encre Desktop</span>
          <span class="about-info-value">v${dv}</span>
        </div>

      </div>

      <div class="about-links-card">
        <div class="about-links-group-title">${tFn("settings.aboutLegalTitle")}</div>
        ${legalHtml}
        <div class="about-links-divider"></div>
        <div class="about-links-group-title">${tFn("settings.aboutSupportTitle")}</div>
        ${supportHtml}
        <div class="about-links-divider"></div>
        <button class="about-link-row" type="button" data-action="check-update">
          <span class="about-link-icon"><i data-lucide="refresh-cw"></i></span>
          <span class="about-link-label">${tFn("settings.aboutCheckUpdate")}</span>
          <span class="about-link-chevron"><i data-lucide="chevron-right"></i></span>
        </button>
      </div>

      <div class="about-copyright">${tFn("settings.copyright")}</div>`;

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.panels.about });
    }

    // Wire link row clicks
    this.panels.about.querySelectorAll<HTMLButtonElement>(".about-link-row[data-link]").forEach(btn => {
      btn.addEventListener("click", () => {
        const link = btn.getAttribute("data-link");
        if (link) {
          const label = btn.getAttribute("data-label") || link;
          const behavior = (getState().settings.default_link_behavior as string) || "system";
          const urlMap: Record<string, string> = {
            "report-bug": "https://github.com/mf2023/Encre/issues/new",
            "community": "https://github.com/mf2023/Encre/discussions",
            "contact": "mailto:dunimd@outlook.com",
          };
          const url = urlMap[link];
          if (url && url.startsWith("mailto:")) {
            window.electronAPI?.openExternal(url);
          } else if (behavior === "system") {
            if (url) {
              window.electronAPI?.openExternal(url);
            } else {
              window.electronAPI?.openChildWindow(link, label);
            }
          } else {
            if (url) {
              window.electronAPI?.openChildWindow(url, label);
            } else {
              window.electronAPI?.openChildWindow(link, label);
            }
          }
        }
      });
    });

    }
}
