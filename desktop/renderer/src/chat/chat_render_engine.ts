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

/**
 * Render pipeline for the Chat view (full / parallel / incremental).
 *
 * Each pipeline stage was extracted from the `Chat` class and is invoked
 * with `impl.call(this, ...)` from a thin class delegate, so `this` still
 * refers to the owning `Chat` instance and every private member stays
 * reachable.
 */

// @ts-nocheck -- pipeline stages relocated from the Chat class; called via
// `XImpl.call(this, ...)` so the instance context is preserved.

import type { Chat } from "./chat.js";
import type { Message } from "../core/types.js";
import type { TimelineItem } from "./timeline.js";
import { getState, setSubAgentView, isEnabled, toolCallMatchesId } from "../core/state.js";
import { t } from "../features/i18n.js";
import { EALoader } from "../features/ealoader.js";
import { renderMarkdown, escapeHtml } from "./chat_markdown.js";
import { getToolSummary, getToolInlineSummary, getToolBodyText, _toolStatusHtml, createLucideIcons, saveVideoPlayback, restoreVideoPlayback } from "./chat_tool_display.js";
import { buildTimeline, buildRenderKey, buildSubAgentTimeline, selectSubAgentTaskMessages } from "./timeline.js";

  export function requestRenderImpl(this: Chat): void {
    if (this.rafPending) return;
    this.rafPending = true;
    requestAnimationFrame(() => {
      this.rafPending = false;
      this.render();
    });
  }

  export function renderForceImpl(this: Chat): void {
    this.renderedKey = "";
    this._inRenderForce = true;
    try {
      const st = getState();
      const subTc = st.subAgentView;
      const isSubAgentStreaming = !!subTc &&
        (subTc.status === "running" || subTc.status === "pending");
      if (!isSubAgentStreaming) {
        this.render();
        return;
      }
      // Throttle sub-agent streaming renders (single AND parallel) so the
      // main thread stays responsive enough for scrolling and window
      // dragging.  Without this, every tool_progress frame triggers a full
      // transcript re-render, which freezes the UI while a sub-agent runs.
      this._pendingParallelRender = true;
      if (this._parallelRenderTimer === null) {
        this.render();
        this._parallelRenderTimer = window.setTimeout(() => {
          this._parallelRenderTimer = null;
          if (this._pendingParallelRender) {
            this._pendingParallelRender = false;
            this.render();
          }
        }, 100);
      }
    } finally {
      this._inRenderForce = false;
    }
  }

  /** Re-renders the message list from current state (RAF-throttled). */
  export function renderImpl(this: Chat): void {
    if (this.liveLoader) {
      this.liveLoader.destroy();
      this.liveLoader = null;
    }
    const state = getState();
    // Breadcrumb restoration: if the user navigated back to an ancestor
    // session via the breadcrumb, the sub-agent view may have been cleared
    // while waiting for the parent session to load. Once the parent session
    // arrives, automatically reopen the sub-agent view that corresponds to
    // the last breadcrumb entry so the UI lands on the right level.
    if (!state.subAgentView && state.subAgentBreadcrumb.length > 0) {
      const crumb = state.subAgentBreadcrumb[state.subAgentBreadcrumb.length - 1];
      if (crumb.sessionId === state.sessionId) {
        for (const msg of state.messages) {
          for (const tc of msg.toolCalls) {
            if (toolCallMatchesId(tc, crumb.toolCallId)) {
              setSubAgentView(tc);
              break;
            }
          }
          if (state.subAgentView) break;
        }
      }
    }
    if (state.subAgentView) {
      this.toggleWelcome(false);
      const subTc = state.subAgentView;
      // A session-backed sub-agent streams directly into the active session
      // snapshot after its transcript has been resumed. Inline sub-agents use
      // the tool-call snapshot instead.
      const sessionBacked = (window as any).__activeSubAgentSessionId === state.sessionId;
      // Prefer the live session snapshot while session-backed — the sub-agent
      // session streams every text/thinking/tool delta into `state.messages`,
      // so rendering from it makes the sub-agent view update incrementally
      // instead of showing one frozen tool-call snapshot and then the whole
      // transcript at once. Fall back to the inline snapshot when no session
      // has been resumed (e.g. plain inline sub-agent, automation detail).
      let subMsgs: Message[];
      if (sessionBacked) {
        subMsgs = state.messages.length > 0
          ? state.messages
          : (subTc.subAgentMessages ?? []);
      } else {
        subMsgs = subTc.subAgentMessages?.length
          ? subTc.subAgentMessages
          : [];
      }

      // When the user clicked one card of a parallel agent run, show only
      // that single task's transcript instead of the combined run.
      const selectedMsgs = selectSubAgentTaskMessages(subMsgs, subTc.taskIndex);
      const hasInlineData = selectedMsgs.length > 0;
      const isStreaming = sessionBacked
        ? state.running
        : (subTc.status === "running" || subTc.status === "pending");
      this.renderedKey = "__subagent__";
      if (hasInlineData) {
        // Sub-agent snapshot arrived: render the real user + assistant
        // bubbles together.  The loader was already torn down at the
        // top of render(), so the message area is clean by now.
        const timeline = buildSubAgentTimeline(selectedMsgs, isStreaming);
        this.fullRender(timeline, selectedMsgs);
      } else if (isStreaming) {
        // Still waiting for the first snapshot: hide every message bubble
        // (no user box, no assistant box) and show only the centered EA
        // loader.  Both bubbles will appear together once data lands.
        this.ml.innerHTML = "";
        this.liveLoader = new EALoader(this.ml, { maxWidth: "50px" });
      } else if (subTc.isError) {
        // Map the raw tool result into something the user can act on:
        // bare sandbox exit codes (-1 timeout / -2 Docker missing) get a
        // readable label, "Error: …" text is shown verbatim instead of
        // being used as a cryptic error code.
        const rawResult = typeof subTc.result === "string" ? subTc.result.trim() : "";
        let errorCode = String(rawResult || "AUTOMATION_EXECUTION_FAILED");
        if (rawResult === "-1") {
          errorCode = t("automation.errorBashTimeout") || "Command timed out (-1)";
        } else if (rawResult === "-2") {
          errorCode = t("automation.errorDockerMissing") || "Sandbox unavailable: Docker not installed (-2)";
        } else if (rawResult.startsWith("Error:") && rawResult.length > 6) {
          errorCode = rawResult.length > 500 ? rawResult.slice(0, 500) + "…" : rawResult;
        }
        this.ml.innerHTML = `<div class="si-panel-empty" style="flex:1;gap:14px;">
          <i data-lucide="ban" class="lucide"></i>
          <div class="si-panel-empty-title">${t("automation.executionFailed") || "Automation execution error"}</div>
          <div class="si-panel-empty-sub" style="word-break:break-word;">${escapeHtml(errorCode)}</div>
        </div>`;
      } else {
        // No inline transcript survived (e.g. reopened after switching
        // sessions before the snapshot was persisted). Fall back to the
        // aggregated tool result text so the user still sees the real
        // output instead of a bare "no output" placeholder.
        const resultText = typeof subTc.result === "string" ? subTc.result.trim() : "";
        if (resultText) {
          this.ml.innerHTML = `<div class="sub-agent-result-fallback">${renderMarkdown(resultText)}</div>`;
        } else {
          // Finished (or never started) without producing any output.
          this.ml.innerHTML = `<div class="si-empty-center"><i data-lucide="bot" class="lucide"></i><span class="si-empty-title">${t("chat.noSubAgentOutput")}</span></div>`;
        }
      }
      createLucideIcons();
      this._updateStatusBar(false);
      this.autoScroll();
      return;
    }
    this.toggleWelcome(state.messages.length === 0);
    const msgs = state.messages;
    if (msgs.length === 0) {
      this.ml.innerHTML = "";
      this.renderedKey = "";
      this.syncScrollButton();
      return;
    }
    const timeline = buildTimeline(msgs);
    const key = buildRenderKey(timeline);
    const wasRunning = this._lastRunning;
    this._lastRunning = state.running;
    // Force full render when streaming completes so auto-expand/collapse
    // logic in fullRender is applied correctly (the render key may not
    // change when running transitions from true to false).
    if (key !== this.renderedKey || (wasRunning && !state.running)) {
      console.log("[chat.render] fullRender", { msgCount: msgs.length, roles: msgs.map(m => m.role), serverIds: msgs.map(m => m.serverId?.slice(-12)) });
      this.fullRender(timeline, msgs);
      this.renderedKey = key;
    } else {
      this.incrementalTextUpdate(timeline);
    }
    this._updateStatusBar(state.running);
    // Auto-open HTML info cards only when the model just finished
    if (wasRunning && !state.running) {
      // Scoped to the main chat container so the pass never reaches into the
      // automation detail (which can hold the same tc-* card ids).
      window.__openInfoHtmlCards?.(this.ml);
    }

  }

  /**
   * Build the timeline HTML for sub-agent messages and render it into
   * an arbitrary container element. Reuses the same rendering pipeline
   * as the main chat's fullRender, so the result looks identical to the
   * chat sub-agent view.
   *
   * Used by the automation panel to render execution results inside
   * #automation-detail-content without switching to chat mode.
   */
  export function renderSubAgentIntoImpl(this: Chat, container: HTMLElement, messages: Message[], isRunning: boolean): void {
    const timeline = buildSubAgentTimeline(messages, isRunning);
    const st = getState();
    const autoExpand = isEnabled(st.settings.auto_expand);
    this.applyAutoExpand(timeline, autoExpand, isRunning);
    // Treat the automation detail exactly like the tape's sub-agent view:
    // user bubbles belong to the current turn (in-turn), not standalone
    // blocks. Pass treatAsSubAgent=true so buildTimelineHTML matches what
    // chat.render() produces when state.subAgentView is set.
    this._subAgentRender = true;
    let html: string;
    try {
      html = this.buildTimelineHTML(timeline, messages, true);
    } finally {
      this._subAgentRender = false;
    }
    const _vs = saveVideoPlayback(container);
    window.__stopAllMedia?.();
    container.innerHTML = html;
    createLucideIcons();
    window.__initMediaCards?.(container);
    restoreVideoPlayback(_vs, container);
    if (!container.dataset.subAgentClickBound) {
      container.addEventListener("click", (e) => this.handleDelegateClick(e));
      container.dataset.subAgentClickBound = "true";
    }
  }

  /**
   * Single source of truth for whether a timeline item should be expanded.
   * Honors explicit user overrides, then the special "thinking" rule, then
   * the auto-expand setting.
   *
   * Rules:
   *  - Thinking, while the model is still actively reasoning
   *    (thinkingActive): ALWAYS expanded so the user can watch the reasoning
   *    stream, regardless of the auto-expand setting (a user may still
   *    explicitly collapse it).
   *  - Otherwise: a manual collapse/expand wins; when the user hasn't touched
   *    it, follow the auto-expand setting. This applies uniformly to thinking
   *    (after it finishes) and to every expandable tool card, so the automation
   *    detail behaves exactly like the main chat.
   */
  export function computeExpandedImpl(this: Chat, kind: string, id: string, autoExpand: boolean, thinkingActive: boolean): boolean {
    const userCollapsed = this.userCollapsedItems.has(id);
    if (kind === "thinking" && thinkingActive) {
      return !userCollapsed;
    }
    if (userCollapsed) return false;
    if (this.userExpandedItems.has(id)) return true;
    return autoExpand;
  }

  /**
   * Identify the thinking segment the model is *actively* generating.
   *
   * "Still thinking" means the reasoning is the last content the model has
   * produced so far — the moment any text or tool segment appears after it,
   * the thinking is finished even though the overall turn keeps running (e.g.
   * while a tool executes). Only the actively-streaming thinking strip is
   * force-expanded; finished ones fall back to the auto-expand setting.
   */
  export function activeThinkingIdImpl(this: Chat, timeline: TimelineItem[], isRunning: boolean): string | null {
    if (!isRunning) return null;
    for (let i = timeline.length - 1; i >= 0; i--) {
      const it = timeline[i];
      if (it.kind === "thinking") return it.id;
      if (it.kind === "tool" || it.kind === "assistant_text") return null;
    }
    return null;
  }

  /**
   * Shared auto-expand pass used by both fullRender and renderSubAgentInto
   * so the two never drift. Auto-expands thinking strips and every expandable
   * tool card unless the user manually collapsed them.
   */
  export function applyAutoExpandImpl(this: Chat, timeline: TimelineItem[], autoExpand: boolean, isRunning = false): void {
    const activeThinkingId = this.activeThinkingId(timeline, isRunning);
    for (const item of timeline) {
      if (item.kind !== "thinking" && item.kind !== "tool") continue;
      const id = item.id;
      const thinkingActive = item.kind === "thinking" && id === activeThinkingId;
      if (this.computeExpanded(item.kind, id, autoExpand, thinkingActive)) {
        this.expandedItems.add(id);
      } else {
        this.expandedItems.delete(id);
      }
    }
  }

  /**
   * Build the timeline's inner HTML (turns + standalone cards) - the shared
   * body of fullRender. Extracted so renderSubAgentInto produces byte-identical
   * markup to the main chat's sub-agent view instead of a parallel copy.
   *
   * @param treatAsSubAgent When true, user bubbles are folded into the
   *   current turn (matching chat.render()'s sub-agent path). When false,
   *   the live subAgentView/__parentSessionId flags decide - the normal
   *   chat behaviour.
   */
  export function buildTimelineHTMLImpl(this: Chat, timeline: TimelineItem[], allMsgs?: Message[], treatAsSubAgent = false): string {
    let html = "";
    let turnMid = ""; // buffered items inside current turn
    let turnActions = false;
    let turnRetry = false;
    let turnBranchSwitcher = false;
    const _this = this;

    function closeTurn() {
      if (!turnMid) return;
      html += `<div class="turn">${turnMid}`;
      if (turnActions) {
        html += `<div class="assistant-actions turn-actions">`;
        html += `<button class="btn-icon btn-icon--msg assistant-copy-btn" data-tooltip="${t("chat.copy")}">
          <span class="icon-wrap">
            <i data-lucide="copy" class="semantic"></i>
            <i data-lucide="chevron-down" class="arrow"></i>
          </span>
        </button>`;
        if (turnRetry) {
          html += `<button class="btn-icon btn-icon--msg assistant-retry-btn" data-tooltip="${t("chat.retry")}">
            <span class="icon-wrap">
              <i data-lucide="refresh-cw" class="semantic"></i>
              <i data-lucide="chevron-down" class="arrow"></i>
            </span>
          </button>`;
        }
        if (turnBranchSwitcher) {
          html += _this.renderBranchSwitcher();
        }
        html += `</div>`;
      }
      html += `</div>`;
      turnMid = "";
      turnActions = false;
      turnRetry = false;
      turnBranchSwitcher = false;
    }

    const inSubAgent = treatAsSubAgent || !!getState().subAgentView || !!(window as any).__parentSessionId;
    for (let i = 0; i < timeline.length; i++) {
      const item = timeline[i];

      if (item.kind === "compact" || item.kind === "workflow" || (item.kind === "user" && !inSubAgent)) {
        closeTurn.call(_this);
        html += this.renderItemHTML(item);
      } else if (item.kind === "ai_header") {
        closeTurn.call(_this);
        turnMid += this.renderItemHTML(item);
      } else {
        // thinking / assistant_text / tool / status cards all belong to the current turn
        if ((item as any).showBranchSwitcher) turnBranchSwitcher = true;
        if ((item as any).showActions) {
          // Every completed turn gets a copy button
          turnActions = true;
          // No retry button in sub-agent view
          if (!inSubAgent) {
            // Only show retry on the very last assistant message in the conversation
            if (allMsgs) {
              for (let mi = allMsgs.length - 1; mi >= 0; mi--) {
                if (allMsgs[mi].role === "assistant") {
                  if ((item as any).messageId === allMsgs[mi].id) turnRetry = true;
                  break;
                }
              }
            } else {
              turnRetry = true;
            }
          }
        }
        turnMid += this.renderItemHTML(item);
      }
    }
    closeTurn.call(_this);
    return html;
  }

  /**
   * Render a parallel sub-agent run: one ``agent`` tool that executed several
   * tasks concurrently. The transcript is a flat list delimited by structured
   * ``task_divider`` markers (``mode === "task_divider"``); we split it back
   * into per-task groups and tile them into split regions -- like a window
   * snap layout -- so "one agent, many jobs" reads as distinct panes:
   *   1 task  -> fills the whole tape
   *   2 tasks -> left / right
   *   3 tasks -> one across the top, two side-by-side below
   *   4 tasks -> 2x2 grid
   * Regions are separated by faint dashed lines (CSS). At most 4 tiles are
   * drawn -- more would deform and can't be laid out cleanly.
   */
  export function fullRenderParallelImpl(this: Chat, subMsgs: Message[], isStreaming: boolean): void {
    // Split the flat transcript by its stable backend task index. A reconnect
    // may replay dividers out of order, so array position is not task identity.
    const groupsByIndex = new Map<number, { divider: Message; body: Message[] }>();
    let fallbackIndex = 0;
    let current: { divider: Message; body: Message[] } | null = null;
    for (const m of subMsgs) {
      if (m.mode === "task_divider") {
        const index = Number.isInteger(m.taskIndex) ? m.taskIndex! : fallbackIndex;
        fallbackIndex = Math.max(fallbackIndex, index + 1);
        current = { divider: m, body: [] };
        groupsByIndex.set(index, current);
      } else if (current) {
        current.body.push(m);
      }
    }
    const groups = [...groupsByIndex.entries()]
      .sort(([left], [right]) => left - right)
      .map(([, group]) => group);

    const statusMeta = (s: string | undefined): { icon: string; label: string; cls: string } => {
      if (s === "done") return { icon: "check", label: t("chat.taskDone") || "Done", cls: "is-done" };
      if (s === "error") return { icon: "x", label: t("chat.taskError") || "Failed", cls: "is-error" };
      if (s === "queued") return { icon: "clock", label: t("chat.taskQueued") || "Queued", cls: "is-queued" };
      return { icon: "loader", label: t("chat.taskRunning") || "Running", cls: "is-running" };
    };

    // Only the first 4 tasks get a region; the split grid can't draw more.
    const shown = groups.slice(0, 4);
    const count = shown.length;

    // Build each tile body HTML up-front so we can diff against the
    // existing DOM and only replace the tiles that actually changed.
    const tileBodies: string[] = [];
    for (const g of shown) {
      const isRunning = statusMeta(g.divider.taskStatus).cls === "is-running";
      const bodyTimeline = buildSubAgentTimeline(g.body, isRunning);
      this._subAgentRender = true;
      let bodyHtml: string;
      try {
        bodyHtml = g.body.length > 0
          ? this.buildTimelineHTML(bodyTimeline, g.body, true)
          : `<div class="parallel-task-pending">${t("chat.taskWaiting") || "Waiting for output…"}</div>`;
      } finally {
        this._subAgentRender = false;
      }
      tileBodies.push(bodyHtml);
    }

    // Windows-style snap layout: panes tile edge-to-edge with no outer frame.
    // 1 task fills the tape; 2 tasks split left/right; 3 tasks put one large
    // pane on the left and two stacked panes on the right; 4 tasks form a 2x2
    // grid. Split ratios are fixed (no drag resize).
    const wrapTile = (idx: number): string =>
      `<section class="parallel-tile"><div class="parallel-tile-body">${tileBodies[idx]}</div></section>`;
    let html = `<div class="parallel-sub-agent" data-count="${count}">`;
    if (count === 3) {
      html += wrapTile(0);
      html += `<div class="parallel-sub-agent-stack">`;
      html += wrapTile(1);
      html += wrapTile(2);
      html += `</div>`;
    } else {
      for (let i = 0; i < count; i++) {
        html += wrapTile(i);
      }
    }
    html += `</div>`;

    this.ml.classList.add("parallel-active");
    const existing = this.ml.querySelector(":scope > .parallel-sub-agent") as HTMLElement | null;
    const _vs = saveVideoPlayback(this.ml);
    window.__stopAllMedia?.();
    if (existing && existing.dataset.count === String(count)) {
      // Diff update: only swap tile bodies whose content changed. This keeps
      // scroll position, cursor selection, and expansion state intact for the
      // tiles that are not currently streaming.
      const bodies = existing.querySelectorAll(".parallel-tile-body");
      let idx = 0;
      for (const body of Array.from(bodies)) {
        if (idx < tileBodies.length && body.innerHTML !== tileBodies[idx]) {
          body.innerHTML = tileBodies[idx];
        }
        idx++;
      }
      window.__initMediaCards?.(this.ml);
      restoreVideoPlayback(_vs, this.ml);
    } else {
      this.ml.innerHTML = html;
      window.__initMediaCards?.(this.ml);
      restoreVideoPlayback(_vs, this.ml);
      
    }
  }

  export function fullRenderImpl(this: Chat, timeline: TimelineItem[], allMsgs?: Message[]): void {
    this.ml.classList.remove("parallel-active");
    const st = getState();
    const autoExpand = isEnabled(st.settings.auto_expand);

    // Auto-expand based on setting (unless user manually collapsed).
    // During streaming, thinking is always expanded so the user sees the
    // reasoning process in real time. After streaming, follow the setting.
    // Delegated to the shared applyAutoExpand pass so fullRender, the
    // streaming incremental path and the automation detail never drift.
    const isRunning = st.running;
    this.applyAutoExpand(timeline, autoExpand, isRunning);

    // Reuse the shared turn-builder so fullRender and renderSubAgentInto
    // (and the automation detail) produce byte-identical markup.
    const html = buildTimelineHTMLImpl.call(this, timeline, allMsgs, false);

    // Capture the scroll snapshot BEFORE innerHTML resets, then restore
    // the visual anchor AFTER. Without this, a full re-render during
    // streaming collapses the user's scroll position and makes the
    // chat feel like it is "always rendering", preventing them from
    // scrolling up to inspect earlier turns.
    const container = this.container;
    const wasScrolledUp = this.userScrolledUp;
    const prevScrollTop = container.scrollTop;
    const prevScrollHeight = container.scrollHeight;
    const _vs = saveVideoPlayback(this.ml);
    window.__stopAllMedia?.();
    this.ml.innerHTML = html;
    createLucideIcons();
    window.__initMediaCards?.(this.ml);
    restoreVideoPlayback(_vs, this.ml);
    
    if (wasScrolledUp) {
      // Preserve the user's visual position: when new content is appended
      // below, the previous bottom offset should still point at the same
      // pixel anchor in the re-rendered DOM.
      const newScrollHeight = container.scrollHeight;
      const delta = newScrollHeight - prevScrollHeight;
      container.scrollTop = prevScrollTop + delta;
      // Refresh the "scrolled up" flag — if the delta restored the user
      // to the bottom, treat them as pinned again.
      const dist = newScrollHeight - container.scrollTop - container.clientHeight;
      this.userScrolledUp = dist > 8;
    } else {
      // New render: always pin to the bottom so the latest message is
      // visible. This covers both streaming and static sessions -- when
      // the user opens a session, we want to land on the last turn,
      // not the middle of the history.
      this.scrollToBottomAfterMedia();
    }
    const userMsgs = getState().messages.filter(m => m.role === "user");
    this.scrollIndicator.update(userMsgs.length, userMsgs.map(m => m.content));
    this.syncScrollButton();
  }

  export function incrementalTextUpdateImpl(this: Chat, timeline: TimelineItem[]): void {
    // Find the last assistant message block in timeline.  This anchor is
    // only needed for the assistant-text delta updates below; the thinking,
    // tool, and workflow updates must still run during the pre-text thinking
    // phase (i.e. when only `thinking_delta` events have arrived so far) so
    // the user sees the reasoning stream in real time instead of having the
    // card freeze on the first delta and then jump to the full text when
    // the first text_delta triggers a fullRender.
    let lastAssistantIndex = -1;
    for (let i = timeline.length - 1; i >= 0; i--) {
      if (timeline[i].kind === "assistant_text") {
        lastAssistantIndex = i;
        break;
      }
    }

    if (lastAssistantIndex >= 0) {
      const assistantItem = timeline[lastAssistantIndex] as Extract<TimelineItem, { kind: "assistant_text" }>;

      // Detect new assistant message round — reset userCollapsedItems
      const currentAssistantMsgId = assistantItem.id;
      if (currentAssistantMsgId !== this.lastAssistantMsgId) {
        this.lastAssistantMsgId = currentAssistantMsgId;
      }
    }

    // Update thinking text if present.  This runs on every render frame
    // (including frames where only a thinking_delta arrived) so the thought
    // card streams in real time just like the assistant text card.
    const activeThinkingId = this.activeThinkingId(timeline, getState().running);
    for (let i = 0; i < timeline.length; i++) {
      const item = timeline[i];
      if (item.kind === "thinking") {
        const el = this.ml.querySelector(`[data-id="${item.id}"]`) as HTMLElement | null;
        if (el) {
          const bodyEl = el.querySelector(".thought-body") as HTMLElement | null;
          if (bodyEl && bodyEl.textContent !== item.text) {
            bodyEl.textContent = item.text;
          }
          // Auto-expand thinking: while the model is ACTIVELY thinking (this is
          // the last content it has produced) always expand unless the user
          // manually collapsed it. Once thinking finishes, follow the
          // auto-expand setting. User manual toggle is respected via
          // userCollapsedItems/userExpandedItems.
          const shouldExpand = isEnabled(getState().settings.auto_expand);
          const thinkingActive = item.id === activeThinkingId;
          const wantExpanded = this.computeExpanded("thinking", item.id, shouldExpand, thinkingActive);
          const isExpanded = el.classList.contains("expanded");
          if (wantExpanded && !isExpanded) {
            el.classList.add("expanded");
            this.expandedItems.add(item.id);
          } else if (!wantExpanded && isExpanded) {
            el.classList.remove("expanded");
            this.expandedItems.delete(item.id);
          }
        }
      }
    }

    // Update tool items incrementally. Covers: streaming params (summary
    // text), status transitions (spinner show/hide), result body, file
    // card diff badge / view button, and agent card preview.
    for (let i = 0; i < timeline.length; i++) {
      const toolItem = timeline[i];
      if (toolItem.kind !== "tool") continue;
      // timeline item id is already `tc-${tc.id}`; do NOT prefix again
      // (the old selector emitted `data-id="tc-tc-..."` and never matched).
      const el = this.ml.querySelector(`[data-id="${toolItem.id}"]`) as HTMLElement | null;
      if (!el) continue;

      // 1) Status slot — toggle spinner on pending<->running<->done.
      const statusSlot = el.querySelector(".strip-status, .tool-item-status") as HTMLElement | null;
      if (statusSlot) {
        const curStatus = statusSlot.getAttribute("data-status") || "";
        if (curStatus !== toolItem.tc.status) {
          statusSlot.setAttribute("data-status", toolItem.tc.status);
          statusSlot.innerHTML = _toolStatusHtml(toolItem.tc.status);
        }
      }

      // 2) Summary text (strip-summary) — pick the right summary function
      //    per layout (inline vs expandable).
      const summaryEl = el.querySelector(".strip-summary") as HTMLElement | null;
      if (summaryEl) {
        const isExpandable = el.classList.contains("strip-item") || el.classList.contains("terminal-card");
        const newSummary = isExpandable ? getToolSummary(toolItem.tc) : getToolInlineSummary(toolItem.tc);
        if (summaryEl.textContent !== newSummary) {
          summaryEl.textContent = newSummary;
        }
      }

      // 3) Result body slot (expandable strip + terminal card). Filled
      //    lazily when tc.result arrives; key flips structurally so the
      //    first time it is rendered through fullRender too.
      const bodySlot = el.querySelector(".strip-body-slot, .terminal-body-slot") as HTMLElement | null;
      if (bodySlot) {
        const hasBody = !!toolItem.tc.result;
        const cur = bodySlot.getAttribute("data-has-body") === "1";
        if (hasBody !== cur) {
          bodySlot.setAttribute("data-has-body", hasBody ? "1" : "0");
          if (hasBody) {
            bodySlot.innerHTML = `<div class="${el.classList.contains("terminal-card") ? "terminal-body" : "strip-body"}">${getToolBodyText(toolItem.tc)}</div>`;
          } else {
            bodySlot.innerHTML = "";
          }
        }
      }

      // 4) Auto-expand based on setting (unless user manually collapsed).
      //    Applies to all expandable tool cards. Mirrors the thinking-strip
      //    handling above so toggling auto_expand takes effect on already-
      //    rendered tool cards without a full re-render.
      const shouldExpandTool = isEnabled(getState().settings.auto_expand);
      const wantExpandedTool = this.computeExpanded("tool", toolItem.id, shouldExpandTool, false);
      const isExpandedTool = el.classList.contains("expanded");
      if (wantExpandedTool && !isExpandedTool) {
        el.classList.add("expanded");
        this.expandedItems.add(toolItem.id);
      } else if (!wantExpandedTool && isExpandedTool) {
        el.classList.remove("expanded");
        this.expandedItems.delete(toolItem.id);
      }
      
    }

    // Update workflow card progress bar and task list
    for (let i = 0; i < timeline.length; i++) {
      if (timeline[i].kind !== "workflow") continue;
      const wf = getState().workflowState;
      if (!wf) continue;
      const card = this.ml.querySelector(`#wf-${wf.workflowId}`) as HTMLElement | null;
      if (!card) continue;
      // Update progress bar
      const bar = card.querySelector(".workflow-progress-fill") as HTMLElement | null;
      if (bar) {
        const pct = wf.totalTasks > 0 ? Math.round((wf.completedCount + wf.failedCount + wf.skippedCount) / wf.totalTasks * 100) : 0;
        bar.style.width = pct + "%";
      }
      // Update progress text
      const textEl = card.querySelector(".workflow-progress-text") as HTMLElement | null;
      if (textEl) {
        const newText = `${wf.completedCount + wf.failedCount + wf.skippedCount}/${wf.totalTasks} tasks — ${wf.completedCount} done, ${wf.failedCount} failed, ${wf.skippedCount} skipped`;
        if (textEl.textContent !== newText) textEl.textContent = newText;
      }
      // Update header badge
      const badge = card.querySelector(".workflow-card-badge") as HTMLElement | null;
      if (badge && !wf.active) {
        const statusColor = wf.success ? "#22c55e" : "#ef4444";
        badge.textContent = wf.success ? (t("chat.workflowDone") || "Completed") : (t("chat.workflowFailed") || "Failed");
        badge.style.background = statusColor + "20";
        badge.style.color = statusColor;
      }
      // Update task status dots
      const taskEls = card.querySelectorAll(".wf-task") as NodeListOf<HTMLElement>;
      taskEls.forEach((taskEl, idx) => {
        if (idx >= wf.tasks.length) return;
        const task = wf.tasks[idx];
        const dot = taskEl.querySelector(".wf-dot") as HTMLElement | null;
        const statusEl = taskEl.querySelector(".wf-task-status") as HTMLElement | null;
        if (dot && dot.getAttribute("data-status") !== task.status) {
          dot.setAttribute("data-status", task.status);
          dot.className = `wf-dot wf-dot--${task.status}`;
        }
        if (statusEl && statusEl.textContent !== task.status) {
          statusEl.textContent = task.status;
        }
      });
    }

    // Update assistant text content
    // During streaming we use textContent (instant, no parsing) to avoid
    // O(n^2) markdown re-parsing on every delta. Full markdown rendering
    // happens once when the stream ends.
    if (lastAssistantIndex >= 0) {
      const assistantItem = timeline[lastAssistantIndex] as Extract<TimelineItem, { kind: "assistant_text" }>;
      const newText = assistantItem.content;
      const el = this.ml.querySelector(`[data-id="${assistantItem.id}"]`) as HTMLElement | null;
      if (!el) {
        // DOM and state are out of sync (e.g. the assistant message was
        // created for a tool call before any text segment existed). Force a
        // full render so the produced content actually appears.
        // Guard against re-entrancy: if we're already inside a renderForce
        // (which is what got us here), don't recurse infinitely.
        if (!this._inRenderForce) {
          this.renderForce();
        }
        return;
      }
      if (newText.trim().length > 0) {
        const contentEl = el.querySelector(".msg-text") as HTMLElement | null;
        if (contentEl) {
          const newHtml = renderMarkdown(newText);
          if (contentEl.innerHTML !== newHtml) {
            contentEl.innerHTML = newHtml;
          }
        }
      }
    }

    this.autoScroll();
    const userMsgs = getState().messages.filter(m => m.role === "user");
    this.scrollIndicator.update(userMsgs.length, userMsgs.map(m => m.content));
    this.syncScrollButton();
  }

