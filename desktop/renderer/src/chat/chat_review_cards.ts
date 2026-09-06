// @ts-nocheck -- methods relocated from the Chat class in chat.ts; private
// members are reached through the instance (`self`). Runtime semantics are
// byte-identical to the original in-class implementations.
import type { Chat } from "./chat.js";
import type { TimelineItem } from "./timeline.js";
import { getState } from "../core/state.js";
import { t } from "../features/i18n.js";
import { escapeHtml } from "./chat_markdown.js";

export function renderSpecCardImpl(self: Chat, item: Extract<TimelineItem, { kind: "spec_card" }>): string {
  const spec = item.spec;
  const status = spec.status;
  const isApproved = status === "approved";
  const isRejected = status === "rejected";
  const isReview = status === "review" || status === "draft";
  const sessionId = getState().sessionId;
  const cardId = `spec-card-${sessionId}`;

  // Section list as expandable file rows
  const sectionsHtml = spec.sections.map((s, i) => {
    const sid = `spec-sec-${i}`;
    const open = self.expandedItems.has(sid);
    return `<div class="review-file${open ? " expanded" : ""}" data-review-toggle="${sid}">
      <div class="review-file-row">
        <span class="review-file-icon"><i data-lucide="file-text"></i></span>
        <span class="review-file-name">${escapeHtml(s.title)}</span>
        <i data-lucide="chevron-down" class="review-file-arrow"></i>
      </div>
      <div class="review-file-body">${escapeHtml(s.content)}</div>
    </div>`;
  }).join("");

  const feedbackHtml = spec.feedback ? `<div class="review-feedback"><strong>Feedback:</strong> ${escapeHtml(spec.feedback)}</div>` : "";

  let bodyHtml: string;
  if (isReview) {
    bodyHtml = `<div class="question-card-body">
      <div class="q-step">${escapeHtml(t("chat.reviewSpecSub") || "If it does not match your intent, review and edit the files, or enter guidance in the input box.")}</div>
      <div class="q-field">
        <div class="q-field-label">${t("chat.reviewArtifact") || "Files"}</div>
        <div class="q-field-text">${sectionsHtml}</div>
      </div>
      ${feedbackHtml}
      <div class="q-actions" style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end">
        <button class="q-action-btn" data-spec-reject="${sessionId}" style="background:var(--bg-tertiary);color:var(--tool-text);border:1px solid var(--border)">${t("chat.reviewCancel") || "Cancel"}</button>
        <button class="q-action-btn" data-spec-approve="${sessionId}" style="background:var(--accent);color:#fff;border:1px solid var(--accent)">${t("chat.reviewExecute") || "Execute"}</button>
      </div>
    </div>`;
  } else if (isApproved) {
    bodyHtml = `<div class="question-card-body">
      <div class="q-step">${escapeHtml(t("chat.reviewSpecMain") || "The specification has been generated.")}</div>
      <div class="q-field">
        <div class="q-field-label">${t("chat.specDocument")}</div>
        <div class="q-field-text">${sectionsHtml}</div>
      </div>
      ${feedbackHtml}
      <div class="q-step" style="color:var(--success-color);margin-top:8px"><i data-lucide="check-circle"></i> ${t("chat.reviewExecuted") || "Executed"}</div>
    </div>`;
  } else if (isRejected) {
    bodyHtml = `<div class="question-card-body">
      <div class="q-step">${escapeHtml(t("chat.reviewSpecMain") || "The specification has been generated.")}</div>
      <div class="q-field">
        <div class="q-field-label">${t("chat.specDocument")}</div>
        <div class="q-field-text">${sectionsHtml}</div>
      </div>
      ${feedbackHtml}
      <div class="q-step" style="color:var(--danger-color);margin-top:8px"><i data-lucide="x-circle"></i> ${t("chat.reviewCancelled") || "Cancelled"}</div>
    </div>`;
  } else {
    bodyHtml = `<div class="question-card-body">${sectionsHtml}</div>`;
  }

  return `<div class="question-card" id="${cardId}">
    <div class="question-card-header">
      <i data-lucide="file-text" class="question-card-icon"></i>
      <span class="question-card-title">${escapeHtml(t("chat.reviewSpecMain") || "Specification Review")}</span>
      <span class="question-card-badge">${isReview ? (t("chat.waitingForAnswer") || "Pending") : (isApproved ? (t("chat.reviewExecuted") || "Executed") : (t("chat.reviewCancelled") || "Cancelled"))}</span>
    </div>
    ${bodyHtml}
  </div>`;
}

export function renderPlanCardImpl(self: Chat, item: Extract<TimelineItem, { kind: "plan_card" }>): string {
  const review = item.review;
  const status = review.status;
  const isApproved = status === "approved";
  const isRejected = status === "rejected";
  const isReview = status === "review" || status === "draft";
  const sessionId = getState().sessionId;
  const cardId = `plan-card-${review.review_id}`;

  // Parse sections from the full content using ## Plan/## Steps/## Checklist headers
  const sections = self.parsePlanSections(review.content);

  // File rows that open in the sidebar markdown tab on click
  const fileRows = [
    { name: "plan.md", content: sections.plan, icon: "file-text" },
    { name: "steps.md", content: sections.steps, icon: "list-ordered" },
    { name: "checklist.md", content: sections.checklist, icon: "check-square" },
  ];

  const fileRowsHtml = fileRows.map((f, i) => {
    const fileKey = `plan-${review.review_id}-${i}`;
    self._planFileLookup.set(fileKey, f.content);
    return `<div class="review-file" data-open-md="${fileKey}" data-md-title="${escapeHtml(f.name)}">
      <div class="review-file-row">
        <span class="review-file-icon"><i data-lucide="${f.icon}"></i></span>
        <span class="review-file-name">${escapeHtml(f.name)}</span>
      </div>
    </div>`;
  }).join("");

  let bodyHtml: string;
  if (isReview) {
    bodyHtml = `<div class="question-card-body">
      <div class="q-step">${escapeHtml(t("chat.reviewPlanSub") || "If it does not match your intent, review and edit the files, or enter guidance in the input box.")}</div>
      <div class="q-field">
        <div class="q-field-label">${t("chat.reviewArtifact") || "Files"}</div>
        <div class="q-field-text">${fileRowsHtml}</div>
      </div>
      <div class="q-actions" style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end">
        <button class="q-action-btn" data-plan-reject="${sessionId}" style="background:var(--bg-tertiary);color:var(--tool-text);border:1px solid var(--border)">${t("chat.reviewCancel") || "Cancel"}</button>
        <button class="q-action-btn" data-plan-approve="${sessionId}" style="background:var(--accent);color:#fff;border:1px solid var(--accent)">${t("chat.reviewExecute") || "Execute"}</button>
      </div>
    </div>`;
  } else if (isApproved) {
    bodyHtml = `<div class="question-card-body">
      <div class="q-step">${escapeHtml(t("chat.reviewPlanMain") || "The plan has been generated.")}</div>
      <div class="q-field">
        <div class="q-field-label">${t("chat.planContent")}</div>
        <div class="q-field-text">${fileRowsHtml}</div>
      </div>
      <div class="q-step" style="color:var(--success-color);margin-top:8px"><i data-lucide="check-circle"></i> ${t("chat.reviewExecuted") || "Executed"}</div>
    </div>`;
  } else if (isRejected) {
    bodyHtml = `<div class="question-card-body">
      <div class="q-step">${escapeHtml(t("chat.reviewPlanMain") || "The plan has been generated.")}</div>
      <div class="q-field">
        <div class="q-field-label">${t("chat.planContent")}</div>
        <div class="q-field-text">${fileRowsHtml}</div>
      </div>
      <div class="q-step" style="color:var(--danger-color);margin-top:8px"><i data-lucide="x-circle"></i> ${t("chat.reviewCancelled") || "Cancelled"}</div>
    </div>`;
  } else {
    bodyHtml = `<div class="question-card-body">${fileRowsHtml}</div>`;
  }

  return `<div class="question-card" id="${cardId}">
    <div class="question-card-header">
      <i data-lucide="list-checks" class="question-card-icon"></i>
      <span class="question-card-title">${escapeHtml(t("chat.reviewPlanMain") || "Plan Review")}</span>
      <span class="question-card-badge">${isReview ? (t("chat.waitingForAnswer") || "Pending") : (isApproved ? (t("chat.reviewExecuted") || "Executed") : (t("chat.reviewCancelled") || "Cancelled"))}</span>
    </div>
    ${bodyHtml}
  </div>`;
}

export function parsePlanSectionsImpl(text: string): { plan: string; steps: string; checklist: string } {
  const result = { plan: "", steps: "", checklist: "" };
  const re = /^##\s+(Plan|Steps|Checklist)\s*$/gmi;
  const parts = text.split(re);
  if (parts.length < 3) {
    result.plan = text;
    return result;
  }
  let key: "plan" | "steps" | "checklist" | "" = "";
  for (let i = 1; i < parts.length; i++) {
    const trimmed = parts[i].trim();
    if (trimmed === "Plan" || trimmed === "Steps" || trimmed === "Checklist") {
      key = trimmed.toLowerCase() as any;
    } else if (key) {
      result[key] = (result[key] + "\n\n" + parts[i]).trim();
    }
  }
  return result;
}

export function renderWorkflowCardImpl(_self: Chat, _item: Extract<TimelineItem, { kind: "workflow" }>): string {
  const wf = getState().workflowState;
  if (!wf) return "";
  const pct = wf.totalTasks > 0 ? Math.round((wf.completedCount + wf.failedCount + wf.skippedCount) / wf.totalTasks * 100) : 0;
  const doneCount = wf.completedCount + wf.failedCount + wf.skippedCount;
  const status = wf.active ? "running" : (wf.success ? "completed" : "failed");
  const statusIcon = status === "running" ? "loader-circle" : status === "completed" ? "check-circle" : "x-circle";
  const statusColor = status === "running" ? "#3b82f6" : status === "completed" ? "#22c55e" : "#ef4444";
  const statusLabel = status === "running" ? t("chat.workflowRunning") || "Running" : status === "completed" ? t("chat.workflowDone") || "Completed" : t("chat.workflowFailed") || "Failed";
  const taskList = wf.tasks.map(task => {
    const dotCls = task.status === "completed" ? "wf-dot--done"
      : task.status === "running" ? "wf-dot--running"
      : task.status === "failed" ? "wf-dot--failed"
      : task.status === "skipped" ? "wf-dot--skipped"
      : "wf-dot--pending";
    const dot = `<span class="wf-dot ${dotCls}" data-tooltip="${escapeHtml(task.taskName)}: ${task.status}"></span>`;
    return `<div class="wf-task">
      ${dot}
      <span class="wf-task-name">${escapeHtml(task.taskName || task.taskId)}</span>
      <span class="wf-task-status">${task.status}</span>
    </div>`;
  }).join("");
  return `<div class="workflow-card" id="wf-${wf.workflowId}">
    <div class="workflow-card-header">
      <i data-lucide="${statusIcon}" class="workflow-card-icon" style="color:${statusColor}"></i>
      <span class="workflow-card-goal">${escapeHtml(wf.goal)}</span>
      <span class="workflow-card-badge" style="background:${statusColor}20;color:${statusColor}">${statusLabel}</span>
    </div>
    <div class="workflow-progress-bar">
      <div class="workflow-progress-fill" style="width:${pct}%;background:${statusColor}"></div>
    </div>
    <div class="workflow-progress-text">${doneCount}/${wf.totalTasks} tasks — ${wf.completedCount} done, ${wf.failedCount} failed, ${wf.skippedCount} skipped</div>
    <div class="workflow-task-list">${taskList}</div>
  </div>`;
}
