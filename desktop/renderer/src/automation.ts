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

import { t, getLocale, onLocaleChange } from "./i18n.js";
import { send } from "./ws.js";
import { Dialog } from "./dialog.js";
import { getState, subscribe } from "./state.js";
import { showSessionContextMenu } from "./session.js";
import {
  onAutomationJobs,
  onAutomationJobCreated,
  onAutomationJobUpdated,
  onAutomationJobCancelled,
  downloadMarkdownFile,
} from "./stream.js";

interface TaskTemplate {
  id: string;
  icon: string;
  titleKey: string;
  descKey: string;
  defaultNameKey: string;
  defaultPrompt: string;
  defaultCron: string;
}

interface BackendJob {
  id: string;
  name: string;
  prompt: string;
  cron: string;
  schedule_type: string;
  state: string;
  suspended: boolean;
  created_at: number;
  last_fired: number | null;
  last_result: string | null;
  fail_count: number;
  max_failures: number;
  tag: string;
  model_index: number;
  push_gateways?: string[];
}

interface HistoryEntry {
  id: string;
  job_id: string;
  name: string;
  tag: string;
  time: number;
  state: string;
  last_result: string;
  fail_count: number;
  session_id?: string;
  messages?: any[];
}

const TEMPLATES: TaskTemplate[] = [
  {
    id: "ai-news",
    icon: "newspaper",
    titleKey: "automation.templateAiNewsTitle",
    descKey: "automation.templateAiNewsDesc",
    defaultNameKey: "defaultNameAiNews",
    defaultPrompt:
      "搜索今日 AI 行业的热点新闻，覆盖以下方面：\n1. 重要产品发布或功能更新（如 OpenAI、Google、Anthropic 等公司动态）\n2. 融资事件与行业并购\n3. 技术突破或重要论文发布\n4. 行业标准与规范动态（如 AI 安全框架、数据治理标准的进展）\n输出要求：\n- 按重要性排序，列出 5-8 条新闻",
    defaultCron: "0 9 * * 1-5",
  },
  {
    id: "brand-monitor",
    icon: "eye",
    titleKey: "automation.templateBrandMonitorTitle",
    descKey: "automation.templateBrandMonitorDesc",
    defaultNameKey: "defaultNameBrandMonitor",
    defaultPrompt:
      "监控品牌在社交媒体和社区中的提及与评价，生成舆情摘要。\n覆盖平台：微博、知乎、Twitter、Reddit\n输出要求：\n- 正面/负面/中性情绪占比\n- 重点提及汇总\n- 风险提示",
    defaultCron: "0 9 * * 1",
  },
  {
    id: "competitor-track",
    icon: "target",
    titleKey: "automation.templateCompetitorTitle",
    descKey: "automation.templateCompetitorDesc",
    defaultNameKey: "defaultNameCompetitorTrack",
    defaultPrompt:
      "追踪指定竞品的产品更新、社区反馈和重要新闻。\n输出要求：\n- 产品更新列表\n- 用户反馈摘要\n- 市场动态",
    defaultCron: "0 10 * * 1",
  },
  {
    id: "stock-monitor",
    icon: "trending-up",
    titleKey: "automation.templateStockTitle",
    descKey: "automation.templateStockDesc",
    defaultNameKey: "defaultNameStockMonitor",
    defaultPrompt:
      "监控关注股票的价格变动，异常波动时生成预警报告。\n输出要求：\n- 价格变动摘要\n- 异常波动分析\n- 相关新闻关联",
    defaultCron: "0 */1 * * 1-5",
  },
  {
    id: "security-scan",
    icon: "shield",
    titleKey: "automation.templateSecurityTitle",
    descKey: "automation.templateSecurityDesc",
    defaultNameKey: "defaultNameSecurityScan",
    defaultPrompt:
      "扫描代码仓库，发现经过验证的中高危安全漏洞。\n输出要求：\n- 漏洞列表（按严重程度排序）\n- 修复建议\n- 参考链接",
    defaultCron: "0 */3 * * *",
  },
  {
    id: "bug-scan",
    icon: "bug",
    titleKey: "automation.templateBugScanTitle",
    descKey: "automation.templateBugScanDesc",
    defaultNameKey: "defaultNameBugScan",
    defaultPrompt:
      "分析最近的代码提交，发现可能导致严重后果的高危 Bug。\n输出要求：\n- Bug 描述\n- 影响范围\n- 修复建议",
    defaultCron: "0 */2 * * *",
  },
  {
    id: "test-coverage",
    icon: "flask-conical",
    titleKey: "automation.templateTestCoverageTitle",
    descKey: "automation.templateTestCoverageDesc",
    defaultNameKey: "defaultNameTestCoverage",
    defaultPrompt:
      "识别最近变更中缺少测试的高风险代码，自动补充测试。\n输出要求：\n- 未覆盖代码片段\n- 建议测试用例\n- 测试框架适配代码",
    defaultCron: "0 9 * * 1",
  },
  {
    id: "daily-summary",
    icon: "git-commit",
    titleKey: "automation.templateDailySummaryTitle",
    descKey: "automation.templateDailySummaryDesc",
    defaultNameKey: "defaultNameDailySummary",
    defaultPrompt:
      "汇总代码仓库的变更情况，生成团队可读的工程日报。\n输出要求：\n- 提交统计\n- 重点变更说明\n- 风险提醒",
    defaultCron: "0 20 * * 1-5",
  },
];

function formatSchedule(cron: string): string {
  if (!cron) return t("automation.once");
  const parts = cron.split(" ");
  if (parts.length !== 5) return cron;
  const [min, hour, , , dow] = parts;
  if (hour === "*" && min === "*") return t("automation.everyMinute");
  if (hour !== "*" && min !== "*" && dow === "*")
    return `${hour.padStart(2, "0")}:${min.padStart(2, "0")} ${t("automation.daily")}`;
  if (dow !== "*")
    return `${hour.padStart(2, "0")}:${min.padStart(2, "0")} ${t("automation.onWeekdays")}`;
  return cron;
}

function parseCronForUI(cron: string): { scheduleType: string; time: string } {
  const parts = cron.split(" ");
  if (parts.length !== 5) return { scheduleType: "daily", time: "09:00" };
  const [min, hour, , , dow] = parts;
  const time = `${hour.padStart(2, "0")}:${min.padStart(2, "0")}`;
  if (hour !== "*" && min !== "*" && dow === "*")
    return { scheduleType: "daily", time };
  if (hour === "*" && min === "*")
    return { scheduleType: "hourly", time: "09:00" };
  if (hour !== "*" && min !== "*" && (dow === "1" || dow === "0" || dow === "7"))
    return { scheduleType: "weekly", time };
  return { scheduleType: "daily", time };
}

function formatDateTime(unixTs: number): string {
  const d = new Date(unixTs * 1000);
  const locale = getLocale() === "en" ? "en-US" : "zh-CN";
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return locale === "en-US"
    ? `${mm}/${dd}/${yyyy} ${hh}:${mi}`
    : `${yyyy}年${Number(mm)}月${Number(dd)}号 ${hh}:${mi}`;
}

function formatDate(unixTs: number): string {
  const d = new Date(unixTs * 1000);
  const locale = getLocale() === "en" ? "en-US" : "zh-CN";
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return locale === "en-US"
    ? `${mm}/${dd}`
    : `${Number(mm)}月${Number(dd)}日`;
}

export class Automation {
  private el: HTMLElement;
  private tabsEl: HTMLElement;
  private panelsEl: HTMLElement;
  private configuredListEl: HTMLElement;
  private historyTimelineEl: HTMLElement;
  private createWrap: HTMLElement;
  private createBtn: HTMLElement;
  private createDropdown: HTMLElement;
  private activeTab = "history";

  public onViewResult?: (data: { id: string; name: string; prompt: string; result: string; tag: string; messages?: any[] }) => void;
  private jobs: BackendJob[] = [];
  // History filter state
  private historyStatus: string = "";   // "" = all, or "SUCCESS"/"FAILED"/"RUNNING"/"PENDING"
  private historyTaskId: string = "";   // "" = all, or a specific job id
  private historyDateFrom: string = ""; // YYYY-MM-DD or ""
  private historyDateTo: string = "";   // YYYY-MM-DD or ""
  private historyFiltersBound: boolean = false;
  private _lastHistoryRef: any = null;
  // Cached filtered history for export (set by renderHistory)
  private currentFilteredHistory: HistoryEntry[] = [];

  constructor() {
    this.el = document.getElementById("automation-view")!;
    this.tabsEl = this.el.querySelector(".automation-tabs")! as HTMLElement;
    this.panelsEl = this.el.querySelector(".automation-panels")! as HTMLElement;
    this.configuredListEl = document.getElementById("configured-list")!;
    this.historyTimelineEl = document.getElementById("history-timeline")!;
    this.createWrap = document.getElementById("automation-create-wrap")!;
    this.createBtn = document.getElementById("automation-create-btn")!;
    this.createDropdown = document.getElementById("automation-create-dropdown")!;

    this.bindTabs();
    this.bindCallbacks();
    this.bindCreateButton();
    this.bindHistoryFilters();

    // Close any open history dropdowns when clicking outside
    document.addEventListener("click", (e) => {
      const target = e.target as Node;
      const filtersEl = document.getElementById("history-filters");
      if (filtersEl && !filtersEl.contains(target)) {
        document.querySelectorAll("#history-filters .settings-dropdown.open").forEach((dd) => {
          dd.classList.remove("open");
        });
      }
    });
  }

  render(): void {
    this.requestJobsList();
    this.requestHistory();
  }

  private bindCallbacks(): void {
    onAutomationJobs((jobs: BackendJob[]) => {
      this.jobs = jobs;
      this.renderConfigured();
      this.onHistoryFiltersRebind?.();
      this.renderHistory();
    });
    // Automation history now flows through global state (automationHistory),
    // so the delete handler's removeSessionById filters it automatically.
    // React to state changes to re-render the timeline.
    subscribe(() => {
      const prev = this._lastHistoryRef;
      const cur = getState().automationHistory;
      if (cur !== prev) {
        this._lastHistoryRef = cur;
        this.onHistoryFiltersRebind?.();
        this.renderHistory();
      }
    });
    onAutomationJobCreated(() => {
      this.requestJobsList();
    });
    onAutomationJobUpdated(() => {
      this.requestJobsList();
    });
    onAutomationJobCancelled(() => {
      this.requestJobsList();
    });
  }

  private requestJobsList(): void {
    send({ type: "automation_list_jobs" });
  }

  private requestHistory(): void {
    send({ type: "automation_get_history" });
  }

  private bindTabs(): void {
    this.tabsEl.addEventListener("click", (e) => {
      const btn = (e.target as HTMLElement).closest(".automation-tab") as HTMLElement | null;
      if (!btn) return;
      const tab = btn.getAttribute("data-automation-tab");
      if (tab && tab !== this.activeTab) {
        this.switchTab(tab);
      }
    });
  }

  private openDialog(template: TaskTemplate, editJob?: BackendJob): void {
    const isEdit = !!editJob;
    const defaultCron = editJob?.cron || template.defaultCron;
    const parsed = parseCronForUI(defaultCron);
    const title = isEdit ? t("automation.editTask") : t("automation.createTaskTitle");
    const btnLabel = isEdit ? t("automation.save") : t("automation.create");

    const overlay = document.createElement("div");
    overlay.className = "toast-overlay";
    overlay.innerHTML = `
      <div class="toast-dialog dialog-wide">
        <div class="toast-title">${title}</div>
        <div class="dialog-body">
          <div class="model-form-row">
            <label class="model-form-label">${t("automation.taskName")}</label>
            <input type="text" id="auto-dlg-name" class="model-form-input" value="${escapeHtml(editJob?.name || (template.defaultNameKey ? t(`automation.${template.defaultNameKey}`) : ""))}" />
          </div>
          <div class="model-form-row">
            <label class="model-form-label">${t("automation.triggerTime")}</label>
            <div class="model-form-dropdown-row">
              <div class="settings-dropdown-wrap" id="auto-dlg-schedule-wrap">
                <button class="settings-dropdown-trigger" id="auto-dlg-schedule-trigger" type="button">
                  <span>${parsed.scheduleType === "daily" ? t("automation.everyDay") : parsed.scheduleType === "weekly" ? t("automation.everyWeek") : t("automation.everyHour")}</span>
                  <i data-lucide="chevron-down" class="lucide settings-dropdown-chevron"></i>
                </button>
                <div class="settings-dropdown" id="auto-dlg-schedule-dropdown">
                  <div class="settings-dropdown-item" data-value="daily"><i data-lucide="calendar" class="lucide" style="width:16px;height:16px;margin-right:6px"></i><span>${t("automation.everyDay")}</span></div>
                  <div class="settings-dropdown-item" data-value="weekly"><i data-lucide="calendar" class="lucide" style="width:16px;height:16px;margin-right:6px"></i><span>${t("automation.everyWeek")}</span></div>
                  <div class="settings-dropdown-item" data-value="hourly"><i data-lucide="clock" class="lucide" style="width:16px;height:16px;margin-right:6px"></i><span>${t("automation.everyHour")}</span></div>
                </div>
              </div>
            </div>
            <div class="model-form-dropdown-row" id="auto-dlg-time-row" style="margin-top:8px">
              <div class="settings-dropdown-wrap" id="auto-dlg-time-wrap">
                <button class="settings-dropdown-trigger" id="auto-dlg-time-trigger" type="button">
                  <i data-lucide="clock" class="lucide" style="width:16px;height:16px;margin-right:6px;opacity:0.5;flex-shrink:0"></i>
                  <span>${escapeHtml(parsed.time)}</span>
                  <i data-lucide="chevron-down" class="lucide settings-dropdown-chevron"></i>
                </button>
                <div class="settings-dropdown" id="auto-dlg-time-dropdown"></div>
              </div>
            </div>
          </div>
          <div class="model-form-row">
            <label class="model-form-label">${t("automation.modelLabel")}</label>
            <div class="model-form-dropdown-row">
              <div class="settings-dropdown-wrap" id="auto-dlg-model-wrap">
                <button class="settings-dropdown-trigger" id="auto-dlg-model-trigger" type="button">
                  <span>${(getState().modelConfigs[editJob?.model_index ?? getState().activeModelIndex]?.name) || "—"}</span>
                  <i data-lucide="chevron-down" class="lucide settings-dropdown-chevron"></i>
                </button>
                <div class="settings-dropdown" id="auto-dlg-model-dropdown"></div>
              </div>
            </div>
          </div>
          <div class="model-form-row" style="display:flex;align-items:center;border-top:1px solid var(--border);padding-top:12px;margin-top:4px">
            <label class="model-form-label" style="margin:0">${t("automation.enablePush")}</label>
            <label class="toggle-switch" style="margin-left:12px">
              <input type="checkbox" id="auto-dlg-push-toggle" ${editJob?.push_gateways?.length ? "checked" : ""} />
              <span class="toggle-slider"></span>
            </label>
          </div>
          <div class="model-form-row" id="auto-dlg-push-gateways-row" style="${editJob?.push_gateways?.length ? "" : "display:none"}">
            <label class="model-form-label">${t("automation.pushGateways")}</label>
            <div id="auto-dlg-push-gateways" style="margin-top:4px"></div>
          </div>
          <div class="model-form-row">
            <label class="model-form-label">${t("automation.whatToDo")}</label>
            <textarea id="auto-dlg-prompt" class="model-form-input" rows="8">${escapeHtml(editJob?.prompt || template.defaultPrompt)}</textarea>
          </div>
        </div>
        <div class="dialog-footer">
          <button class="btn" id="auto-dlg-cancel">${t("dialog.cancel")}</button>
          <button class="btn btn--primary" id="auto-dlg-ok">${btnLabel}</button>
        </div>
      </div>`;

    document.body.appendChild(overlay);
    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: overlay });
    }

    let scheduleValue = parsed.scheduleType;
    let timeValue = parsed.time;
    const timeRow = overlay.querySelector("#auto-dlg-time-row") as HTMLElement;
    const timeTrigger = overlay.querySelector("#auto-dlg-time-trigger") as HTMLElement;
    const timeDropdown = overlay.querySelector("#auto-dlg-time-dropdown") as HTMLElement;
    const scheduleTrigger = overlay.querySelector("#auto-dlg-schedule-trigger") as HTMLElement;
    const scheduleDropdown = overlay.querySelector("#auto-dlg-schedule-dropdown") as HTMLElement;

    const buildTimeOptions = () => {
      const times: string[] = [];
      for (let h = 0; h < 24; h++) {
        for (let m = 0; m < 60; m++) {
          times.push(`${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}`);
        }
      }
      timeDropdown.innerHTML = times.map(t =>
        `<div class="settings-dropdown-item${t === timeValue ? " selected" : ""}" data-value="${t}">
          <i data-lucide="clock" class="lucide" style="width:16px;height:16px;margin-right:6px;opacity:0.5"></i>
          <span>${t}</span>
        </div>`
      ).join("");
      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: timeDropdown });
      }
      timeDropdown.querySelectorAll(".settings-dropdown-item").forEach((item) => {
        item.addEventListener("click", (e) => {
          e.stopPropagation();
          timeValue = (item as HTMLElement).getAttribute("data-value") || "09:00";
          timeTrigger.querySelector("span")!.textContent = timeValue;
          timeDropdown.classList.remove("open");
        });
      });
    };

    const showTimePicker = (show: boolean) => {
      timeRow.style.display = show ? "" : "none";
    };

    scheduleTrigger.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpen = scheduleDropdown.classList.contains("open");
      if (isOpen) { scheduleDropdown.classList.remove("open"); return; }
      document.querySelectorAll(".settings-dropdown.open").forEach((dd) => dd.classList.remove("open"));
      scheduleDropdown.classList.add("open");
    });

    scheduleDropdown.querySelectorAll(".settings-dropdown-item").forEach((item) => {
      item.addEventListener("click", (e) => {
        e.stopPropagation();
        const val = (item as HTMLElement).getAttribute("data-value") || "daily";
        const label = (item as HTMLElement).querySelector("span")!.textContent || "";
        scheduleTrigger.querySelector("span")!.textContent = label;
        scheduleDropdown.classList.remove("open");
        scheduleValue = val;
        showTimePicker(val !== "hourly");
      });
    });

    timeTrigger.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpen = timeDropdown.classList.contains("open");
      if (isOpen) { timeDropdown.classList.remove("open"); return; }
      document.querySelectorAll(".settings-dropdown.open").forEach((dd) => dd.classList.remove("open"));
      buildTimeOptions();
      timeDropdown.classList.add("open");
    });

    let selectedModelIndex = editJob?.model_index ?? getState().activeModelIndex;
    const modelTrigger = overlay.querySelector("#auto-dlg-model-trigger") as HTMLElement;
    const modelDropdown = overlay.querySelector("#auto-dlg-model-dropdown") as HTMLElement;

    const buildModelOptions = () => {
      const models = getState().modelConfigs;
      if (!models || models.length === 0) {
        modelDropdown.innerHTML = `<div class="settings-dropdown-item" style="opacity:0.5;cursor:default">—</div>`;
        return;
      }
      modelDropdown.innerHTML = models.map((m, i) =>
        `<div class="settings-dropdown-item${i === selectedModelIndex ? " selected" : ""}" data-index="${i}">
          <span>${escapeHtml(m.name)}</span>
          <span style="opacity:0.5;margin-left:6px;font-size:11px">${escapeHtml(m.model_id)}</span>
        </div>`
      ).join("");
      modelDropdown.querySelectorAll(".settings-dropdown-item").forEach((item) => {
        item.addEventListener("click", (e) => {
          e.stopPropagation();
          const idx = parseInt((item as HTMLElement).getAttribute("data-index") || "-1");
          if (idx < 0) return;
          selectedModelIndex = idx;
          const models = getState().modelConfigs;
          modelTrigger.querySelector("span")!.textContent = models[idx]?.name || "—";
          modelDropdown.classList.remove("open");
        });
      });
    };

    modelTrigger.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpen = modelDropdown.classList.contains("open");
      if (isOpen) { modelDropdown.classList.remove("open"); return; }
      document.querySelectorAll(".settings-dropdown.open").forEach((dd) => dd.classList.remove("open"));
      buildModelOptions();
      modelDropdown.classList.add("open");
    });

    if (parsed.scheduleType === "hourly") showTimePicker(false);

    // ── Push gateway toggle ──
    const pushToggle = overlay.querySelector("#auto-dlg-push-toggle") as HTMLInputElement;
    const pushGatewaysRow = overlay.querySelector("#auto-dlg-push-gateways-row") as HTMLElement;
    const pushGatewaysContainer = overlay.querySelector("#auto-dlg-push-gateways") as HTMLElement;

    const buildPushGateways = () => {
      const gs = getState().gatewayStatus;
      const adapters = gs?.adapters || [];
      const available = adapters.filter(a => a.connected);
      if (available.length === 0) {
        pushGatewaysContainer.innerHTML = `<span style="color:var(--text-muted);font-size:13px">—</span>`;
        return;
      }
      const selected = new Set<string>(editJob?.push_gateways || []);
      pushGatewaysContainer.innerHTML = available.map(a => {
        const isSel = selected.has(a.name);
        return `<div class="settings-dropdown-item${isSel ? " selected" : ""}" data-gateway-id="${a.name}" style="display:flex;align-items:center;gap:8px">
          <i data-lucide="${isSel ? "check-circle" : "circle"}" class="lucide" style="width:16px;height:16px;flex-shrink:0;${isSel ? "color:var(--accent)" : "opacity:0.3"}"></i>
          <span>${a.name}</span>
        </div>`;
      }).join("");
      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: pushGatewaysContainer });
      }
      pushGatewaysContainer.querySelectorAll(".settings-dropdown-item").forEach(item => {
        item.addEventListener("click", (e) => {
          e.stopPropagation();
          const gwId = (item as HTMLElement).getAttribute("data-gateway-id");
          if (!gwId) return;
          const wasSel = selected.has(gwId);
          const icon = item.querySelector(".lucide");
          if (wasSel) {
            selected.delete(gwId);
            item.classList.remove("selected");
            if (icon) icon.setAttribute("data-lucide", "circle");
          } else {
            selected.add(gwId);
            item.classList.add("selected");
            if (icon) icon.setAttribute("data-lucide", "check-circle");
          }
          if (typeof (window as any).lucide !== "undefined") {
            (window as any).lucide.createIcons({ root: pushGatewaysContainer });
          }
        });
      });
    };

    pushToggle.addEventListener("change", () => {
      if (pushToggle.checked) {
        buildPushGateways();
        pushGatewaysRow.style.display = "";
      } else {
        pushGatewaysRow.style.display = "none";
      }
    });

    // In edit mode with push enabled, populate gateways immediately
    if (pushToggle.checked) {
      buildPushGateways();
    }

    const close = () => overlay.remove();
    overlay.querySelector("#auto-dlg-cancel")?.addEventListener("click", close);

    overlay.querySelector("#auto-dlg-ok")?.addEventListener("click", () => {
      const name = (document.getElementById("auto-dlg-name") as HTMLInputElement)?.value.trim();
      if (!name) return;

      const prompt = (document.getElementById("auto-dlg-prompt") as HTMLTextAreaElement)?.value.trim() || template.defaultPrompt;

      const time = timeValue || "09:00";
      const [h, m] = time.split(":").map(s => s.padStart(2, "0"));
      let cron: string;
      switch (scheduleValue) {
        case "daily": cron = `${m} ${h} * * *`; break;
        case "weekly": cron = `${m} ${h} * * 1`; break;
        default: cron = `${m} * * * *`; break;
      }

      // Read push gateway state before removing overlay (elements become detached)
      let selectedPushGateways: string[] = [];
      const pushToggleEl = document.getElementById("auto-dlg-push-toggle") as HTMLInputElement | null;
      if (pushToggleEl?.checked) {
        const container = document.getElementById("auto-dlg-push-gateways");
        if (container) {
          selectedPushGateways = Array.from(container.querySelectorAll(".settings-dropdown-item.selected"))
            .map(item => (item as HTMLElement).getAttribute("data-gateway-id")!)
            .filter(Boolean);
        }
      }

      overlay.remove();

      if (isEdit && editJob) {
        send({
          type: "automation_update_job",
          job_id: editJob.id,
          name,
          prompt,
          cron,
          tag: editJob.tag || "",
          model_index: selectedModelIndex,
          push_gateways: selectedPushGateways,
        } as any);
      } else {
        send({
          type: "automation_create_job",
          name,
          prompt,
          cron,
          tag: template.titleKey ? t(template.titleKey) : "",
          model_index: selectedModelIndex,
          push_gateways: selectedPushGateways,
        } as any);
      }
    });
  }

  private switchTab(tab: string): void {
    this.activeTab = tab;

    this.tabsEl.querySelectorAll(".automation-tab").forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-automation-tab") === tab);
    });

    this.panelsEl.querySelectorAll(".automation-panel").forEach((panel) => {
      panel.classList.toggle("active", panel.getAttribute("data-automation-panel") === tab);
    });

    if (tab === "configured") {
      this.requestJobsList();
    } else if (tab === "history") {
      this.requestHistory();
    }
  }

  private bindCreateButton(): void {
    const renderDropdown = () => {
      const blankHtml = `<div class="settings-dropdown-item" data-template-id="">
        <i data-lucide="plus" class="lucide" style="width:16px;height:16px;margin-right:6px"></i>
        <span>${t("automation.customCreate")}</span>
      </div>`;
      this.createDropdown.innerHTML = blankHtml + TEMPLATES.map(
        (tmpl) => `
        <div class="settings-dropdown-item" data-template-id="${tmpl.id}">
          <i data-lucide="${tmpl.icon}" class="lucide" style="width:16px;height:16px;margin-right:6px"></i>
          <span>${t(tmpl.titleKey)}</span>
        </div>
      `).join("");

      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: this.createDropdown });
      }

      this.createDropdown.querySelectorAll(".settings-dropdown-item").forEach((item) => {
        item.addEventListener("click", (e) => {
          e.stopPropagation();
          this.createDropdown.classList.remove("open");
          const id = (item as HTMLElement).getAttribute("data-template-id");
          if (!id) {
            const blank: TaskTemplate = { id: "custom", icon: "plus", titleKey: "", descKey: "", defaultNameKey: "", defaultPrompt: "", defaultCron: "" };
            this.openDialog(blank);
          } else {
            const template = TEMPLATES.find((t) => t.id === id);
            if (template) this.openDialog(template);
          }
        });
      });
    };

    this.createBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpen = this.createDropdown.classList.contains("open");
      if (isOpen) {
        this.createDropdown.classList.remove("open");
      } else {
        renderDropdown();
        this.createDropdown.classList.add("open");
      }
    });

    document.addEventListener("click", (e) => {
      if (!this.createWrap.contains(e.target as Node)) {
        this.createDropdown.classList.remove("open");
      }
    });
  }

  private renderConfigured(): void {
    const wrap = this.configuredListEl;

    if (this.jobs.length === 0) {
      wrap.innerHTML = `
        <div class="settings-card">
          <div class="model-manage-header">
            <div class="model-manage-desc">${t("automation.configuredDesc")}</div>
          </div>
          <div class="configured-empty">
            <i data-lucide="calendar" class="lucide"></i>
            <div class="empty-title">${t("automation.noTasks")}</div>
            <div class="empty-sub">${t("automation.noTasksHint")}</div>
          </div>
        </div>`;
      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: wrap });
      }
      return;
    }

    const stateTag = (state: string, suspended: boolean): string => {
      if (suspended) return `<span class="model-active-tag" style="color:var(--text-muted);background:rgba(156,163,175,0.12)">${t("automation.statePaused")}</span>`;
      switch (state) {
        case "RUNNING": return `<span class="model-active-tag" style="color:var(--success);background:rgba(34,197,94,0.12)">${t("automation.stateRunning")}</span>`;
        case "PENDING": return `<span class="model-active-tag" style="color:var(--warning);background:rgba(234,179,8,0.12)">${t("automation.statePending")}</span>`;
        default: return `<span class="model-active-tag" style="color:var(--text-muted);background:rgba(156,163,175,0.12)">${escapeHtml(state)}</span>`;
      }
    };

    let rowsHtml = "";
    for (const job of this.jobs) {
      const running = !job.suspended && (job.state === "RUNNING" || job.state === "PENDING");
      rowsHtml += `
        <div class="model-table-row" data-configured-id="${escapeHtml(job.id)}">
          <div class="model-table-cell model-cell-name">
            <span class="model-name-text">${escapeHtml(job.name)}</span>
            ${job.tag && job.tag !== job.name ? `<span class="model-active-tag">${escapeHtml(job.tag)}</span>` : ""}
          </div>
          <div class="model-table-cell model-cell-provider">${formatSchedule(job.cron)}</div>
          <div class="model-table-cell model-cell-actions">
            ${stateTag(job.state, job.suspended)}
            <button class="btn-icon" data-action="edit" title="${t("general.edit")}">
              <i data-lucide="pencil" class="lucide"></i>
            </button>
            <button class="btn-icon" data-action="delete" title="${t("general.delete")}">
              <i data-lucide="trash-2" class="lucide"></i>
            </button>
            <label class="toggle-switch toggle-sm">
              <input type="checkbox" class="auto-toggle" data-job-id="${escapeHtml(job.id)}" ${running ? "checked" : ""} />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>`;
    }

    this.configuredListEl.innerHTML = `
      <div class="settings-card">
        <div class="model-manage-header">
          <div class="model-manage-desc">${t("automation.configuredDesc")}</div>
        </div>
        <div class="model-table">
          <div class="model-table-header">
            <div class="model-table-cell model-cell-name">${t("automation.taskName")}</div>
            <div class="model-table-cell model-cell-provider">${t("automation.triggerTime")}</div>
            <div class="model-table-cell model-cell-actions">${t("automation.configured")}</div>
          </div>
          ${rowsHtml}
        </div>
      </div>`;

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.configuredListEl });
    }

    this.configuredListEl.querySelectorAll(".model-table-row").forEach((row) => {
      const id = (row as HTMLElement).getAttribute("data-configured-id")!;
      const job = this.jobs.find(j => j.id === id);

      row.querySelector('[data-action="edit"]')?.addEventListener("click", (e) => {
        e.stopPropagation();
        if (job) this.onConfiguredEdit(job);
      });

      row.querySelector('[data-action="delete"]')?.addEventListener("click", (e) => {
        e.stopPropagation();
        if (job) this.onConfiguredAction(id, "delete");
      });
    });

    // Bind toggle switches — matches settings model toggle pattern
    this.configuredListEl.querySelectorAll(".auto-toggle").forEach((cb) => {
      cb.addEventListener("change", () => {
        const jobId = (cb as HTMLElement).getAttribute("data-job-id") || "";
        this.onConfiguredToggle(jobId);
      });
    });
  }

  private bindHistoryFilters(): void {
    if (this.historyFiltersBound) return;
    const root = document.getElementById("history-filters");
    if (!root) return;
    this.historyFiltersBound = true;

    // ── Status dropdown ──
    const statusOptions: { id: string; label: string }[] = [
      { id: "", label: t("automation.filterAll") },
      { id: "SUCCESS", label: t("automation.filterSuccess") },
      { id: "FAILED", label: t("automation.filterFailed") },
      { id: "RUNNING", label: t("automation.stateRunning") },
      { id: "PENDING", label: t("automation.statePending") },
    ];
    this.renderHistoryDropdown("history-filter-status", statusOptions, this.historyStatus, (val) => {
      this.historyStatus = val;
      this.renderHistory();
    });

    // ── Task dropdown ──
    const renderTaskOptions = () => {
      const opts: { id: string; label: string }[] = [{ id: "", label: t("automation.filterAllTasks") }];
      const seen = new Set<string>();
      for (const h of getState().automationHistory) {
        if (seen.has(h.job_id)) continue;
        seen.add(h.job_id);
        opts.push({ id: h.job_id, label: h.name });
      }
      for (const j of this.jobs) {
        if (seen.has(j.id)) continue;
        seen.add(j.id);
        opts.push({ id: j.id, label: j.name });
      }
      return opts;
    };
    const rebindTask = () => {
      this.renderHistoryDropdown("history-filter-task", renderTaskOptions(), this.historyTaskId, (val) => {
        this.historyTaskId = val;
        this.renderHistory();
      });
    };
    rebindTask();
    // re-render task list when history/jobs change
    this.onHistoryFiltersRebind = rebindTask;

    // ── Date range ──
    const dateFrom = document.getElementById("history-date-from") as HTMLInputElement | null;
    const dateTo = document.getElementById("history-date-to") as HTMLInputElement | null;
    const applyDateLocale = () => {
      const lang = getLocale() === "en" ? "en" : "zh-CN";
      if (dateFrom) dateFrom.setAttribute("lang", lang);
      if (dateTo) dateTo.setAttribute("lang", lang);
    };
    applyDateLocale();
    onLocaleChange(() => applyDateLocale());
    if (dateFrom) {
      dateFrom.addEventListener("change", () => {
        this.historyDateFrom = dateFrom.value || "";
        this.renderHistory();
      });
    }
    if (dateTo) {
      dateTo.addEventListener("change", () => {
        this.historyDateTo = dateTo.value || "";
        this.renderHistory();
      });
    }
    const dateClear = document.getElementById("history-date-clear");
    if (dateClear) {
      dateClear.setAttribute("title", t("automation.clearDate"));
      dateClear.addEventListener("click", () => {
        this.historyDateFrom = "";
        this.historyDateTo = "";
        if (dateFrom) dateFrom.value = "";
        if (dateTo) dateTo.value = "";
        this.renderHistory();
      });
    }

    // Export button
    const exportBtn = document.getElementById("history-export-btn");
    if (exportBtn) {
      exportBtn.setAttribute("title", t("automation.exportHistory"));
      exportBtn.addEventListener("click", () => this.exportHistory());
    }
  }

  private exportHistory(): void {
    if (this.currentFilteredHistory.length === 0) {
      // No records to export — silent no-op (button is hidden in this case)
      return;
    }
    const lines: string[] = [];
    lines.push(`# ${t("automation.exportHistoryTitle")}`);
    lines.push("");
    const now = formatDateTime(Math.floor(Date.now() / 1000));
    lines.push(`*${now}*`);
    lines.push("");
    lines.push(`**${this.currentFilteredHistory.length}** ${t("automation.history")}`);
    lines.push("");

    // Build task → entries map
    const taskMap = new Map<string, HistoryEntry[]>();
    for (const h of this.currentFilteredHistory) {
      const key = h.name || h.job_id;
      if (!taskMap.has(key)) taskMap.set(key, []);
      taskMap.get(key)!.push(h);
    }

    for (const [taskName, entries] of taskMap) {
      lines.push(`## ${taskName}`);
      lines.push("");
      // sort newest first
      const sorted = [...entries].sort((a, b) => b.time - a.time);
      for (const e of sorted) {
        const ts = formatDateTime(e.time);
        const stateLabel = this.getStateLabel(e.state);
        const stateBadge = e.state === "SUCCESS" ? "✅"
          : e.state === "FAILED" ? "❌"
          : e.state === "RUNNING" ? "🔄"
          : "⏳";
        lines.push(`### ${stateBadge} ${ts} — ${stateLabel}`);
        if (e.tag && e.tag !== e.name) {
          lines.push("");
          lines.push(`- **${t("automation.modelLabel")}**: ${e.tag}`);
        }
        if (e.fail_count && e.fail_count > 0) {
          lines.push(`- **${t("automation.failedCount")}**: ${e.fail_count}`);
        }
        if (e.last_result) {
          lines.push("");
          lines.push("> " + e.last_result.replace(/\n/g, "\n> "));
        }
        if ((e as any).messages && Array.isArray((e as any).messages) && (e as any).messages.length > 0) {
          lines.push("");
          for (const m of (e as any).messages) {
            if (m.role === "user" || m.role === "human") {
              lines.push("**User:**");
              lines.push("");
              lines.push("```");
              lines.push(this.stripControlChars(String(m.content || "")));
              lines.push("```");
            } else if (m.role === "assistant" || m.role === "ai") {
              lines.push("**Assistant:**");
              lines.push("");
              lines.push(this.stripControlChars(String(m.content || "")));
            } else {
              lines.push(`**${m.role}:**`);
              lines.push("");
              lines.push("```");
              lines.push(this.stripControlChars(String(m.content || "")));
              lines.push("```");
            }
            lines.push("");
          }
        }
        lines.push("");
        lines.push("---");
        lines.push("");
      }
    }

    const md = lines.join("\n");
    const stamp = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    const filename = `automation-history-${stamp.getFullYear()}${pad(stamp.getMonth() + 1)}${pad(stamp.getDate())}-${pad(stamp.getHours())}${pad(stamp.getMinutes())}.md`;
    downloadMarkdownFile(md, filename);
  }

  private stripControlChars(s: string): string {
    return s.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "");
  }

  private getStateLabel(state: string): string {
    switch (state) {
      case "SUCCESS": return t("automation.stateSuccess");
      case "FAILED": return t("automation.stateFailed");
      case "RUNNING": return t("automation.stateRunning");
      case "PENDING": return t("automation.statePending");
      case "PAUSED": return t("automation.statePaused");
      default: return state;
    }
  }

  private onHistoryFiltersRebind?: () => void;

  private renderHistoryDropdown(
    id: string,
    options: { id: string; label: string }[],
    currentId: string,
    onChange: (val: string) => void,
  ): void {
    const trigger = document.getElementById(`${id}-trigger`);
    const labelEl = document.getElementById(`${id}-label`);
    const dropdown = document.getElementById(`${id}-dropdown`);
    if (!trigger || !dropdown || !labelEl) return;

    const current = options.find((o) => o.id === currentId) || options[0];
    labelEl.textContent = current.label;

    // Rebuild dropdown content
    dropdown.innerHTML = options.map((o) => `
      <div class="settings-dropdown-item${o.id === currentId ? " selected" : ""}" data-value="${escapeHtml(o.id)}">${escapeHtml(o.label)}</div>
    `).join("");

    // Re-bind trigger click (replace node to clear old listeners)
    const freshTrigger = trigger.cloneNode(true) as HTMLElement;
    trigger.parentNode!.replaceChild(freshTrigger, trigger);

    freshTrigger.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpen = dropdown.classList.contains("open");
      document.querySelectorAll(".settings-dropdown.open").forEach((dd) => dd.classList.remove("open"));
      if (!isOpen) dropdown.classList.add("open");
    });

    // Bind dropdown item clicks (delegated so it survives re-renders)
    dropdown.onclick = (e) => {
      const target = e.target as HTMLElement;
      const item = target.closest(".settings-dropdown-item") as HTMLElement | null;
      if (!item) return;
      e.stopPropagation();
      const val = item.getAttribute("data-value") || "";
      const label = item.textContent || "";
      labelEl.textContent = label;
      dropdown.classList.remove("open");
      dropdown.querySelectorAll(".settings-dropdown-item").forEach((el) => el.classList.remove("selected"));
      item.classList.add("selected");
      onChange(val);
    };
  }

  private renderHistory(): void {
    const filtersEl = document.getElementById("history-filters")!;

    // Show configured jobs that haven't run yet as pending entries
    let displayHistory = [...getState().automationHistory];
    if (this.jobs.length > 0) {
      const historyJobIds = new Set(displayHistory.map(h => h.job_id));
      for (const job of this.jobs) {
        if (!historyJobIds.has(job.id)) {
          displayHistory.push({
            id: `${job.id}_pending`,
            job_id: job.id,
            name: job.name,
            tag: job.tag || "",
            time: job.created_at,
            state: "PENDING",
            last_result: "",
            fail_count: 0,
          });
        }
      }
    }

    // ── Apply filters ──
    const fromTs = this.historyDateFrom ? new Date(this.historyDateFrom + "T00:00:00").getTime() / 1000 : null;
    const toTs = this.historyDateTo ? new Date(this.historyDateTo + "T23:59:59").getTime() / 1000 : null;
    displayHistory = displayHistory.filter((h) => {
      if (this.historyStatus && h.state !== this.historyStatus) return false;
      if (this.historyTaskId && h.job_id !== this.historyTaskId) return false;
      if (fromTs !== null && h.time < fromTs) return false;
      if (toTs !== null && h.time > toTs) return false;
      return true;
    });

    // Cache for export
    this.currentFilteredHistory = displayHistory;

    if (displayHistory.length === 0 && getState().automationHistory.length === 0) {
      filtersEl.style.display = "none";
      this.historyTimelineEl.innerHTML = `<div class="history-empty">
        <i data-lucide="history" class="lucide"></i>
        <div class="empty-title">${t("automation.noHistory")}</div>
        <div class="empty-sub">${t("automation.noHistoryHint")}</div>
      </div>`;
      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: this.historyTimelineEl });
      }
      return;
    }
    filtersEl.style.display = "";

    if (displayHistory.length === 0) {
      this.historyTimelineEl.innerHTML = `<div class="history-empty">
        <i data-lucide="search-x" class="lucide"></i>
        <div class="empty-title">${t("automation.noMatchingHistory")}</div>
      </div>`;
      if (typeof (window as any).lucide !== "undefined") {
        (window as any).lucide.createIcons({ root: this.historyTimelineEl });
      }
      return;
    }

    const groups: Record<string, HistoryEntry[]> = {};
    for (const h of displayHistory) {
      const dateKey = formatDate(h.time);
      if (!groups[dateKey]) groups[dateKey] = [];
      groups[dateKey].push(h);
    }

      this.historyTimelineEl.innerHTML = Object.entries(groups).map(
      ([date, records]) => `
      <div class="history-date-group">
        <div class="history-date-title">${date}</div>
        ${records.map((record) => {
          const state = record.state;
          const isRunning = state === "RUNNING";
          const isError = state === "FAILED";
          const iconName = isRunning ? "loader" : isError ? "x" : (state === "PENDING" ? "clock" : "check");
          const iconCls = isRunning ? "running" : isError ? "error" : (state === "PENDING" ? "pending" : "success");
          const metaText = `${formatDateTime(record.time)}`;
          return `
          <div class="history-timeline-item" data-entry-id="${escapeHtml(record.id)}"${record.session_id ? ` data-sid="${escapeHtml(record.session_id)}"` : ""}>
            <div class="history-timeline-icon history-timeline-icon--${iconCls}">
              <i data-lucide="${iconName}" class="lucide"></i>
            </div>
            <div class="history-timeline-content">
              <div class="history-timeline-header">
                <span class="history-timeline-name">${escapeHtml(record.name)}</span>
              </div>
              <div class="history-timeline-meta">
                ${metaText}
                ${record.fail_count > 0 ? `(${t("automation.failedCount")}: ${record.fail_count})` : ""}
              </div>
            </div>
          </div>
        `}).join("")}
      </div>
    `).join("");

    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons({ root: this.historyTimelineEl });
    }

    this.historyTimelineEl.querySelectorAll(".history-timeline-item").forEach((item) => {
      item.addEventListener("click", () => {
        const entryId = (item as HTMLElement).getAttribute("data-entry-id");
        const entry = getState().automationHistory.find(h => h.id === entryId);
        if (!entry) return;
        const job = this.jobs.find(j => j.id === entry.job_id);
        this.onViewResult?.({
          id: entry.id,
          name: entry.name,
          prompt: job?.prompt || entry.name,
          result: entry.last_result || "",
          tag: entry.tag,
          messages: (entry as any).messages,
          state: entry.state,
          job_id: entry.job_id,
          session_id: entry.session_id,
        } as any);
      });
    });

    this.historyTimelineEl.querySelectorAll(".history-timeline-item").forEach((item) => {
      (item as HTMLElement).addEventListener("contextmenu", (e: MouseEvent) => {
        e.preventDefault();
        const sid = (item as HTMLElement).getAttribute("data-sid");
        if (sid) {
          showSessionContextMenu(sid, e.clientX, e.clientY, true);
        }
      });
    });
  }

  private onConfiguredAction(id: string, action: string): void {
    if (action === "delete") {
      send({ type: "automation_delete_job", job_id: id });
      // Refresh list immediately instead of relying on event chain
      this.requestJobsList();
      this.requestHistory();
    }
  }

  private onConfiguredToggle(id: string): void {
    const job = this.jobs.find((j) => j.id === id);
    if (!job) return;
    send({ type: "automation_toggle_job", job_id: id });
  }

  private onConfiguredEdit(job: BackendJob): void {
    // Build a fake template to reuse openDialog in edit mode
    const fakeTemplate: TaskTemplate = {
      id: "edit",
      icon: "edit",
      titleKey: "automation.editTask",
      descKey: "",
      defaultNameKey: "",
      defaultPrompt: job.prompt,
      defaultCron: job.cron,
    };
    this.openDialog(fakeTemplate, job);
  }
}

function escapeHtml(str: string): string {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
