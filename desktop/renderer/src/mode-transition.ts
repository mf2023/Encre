/**
 * Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
 *
 * This file is part of Encre.
 * The Encre project belongs to the Dunimd Team.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
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

import { Workspace } from "./workspace.js";
import { AutomationPanel } from "./iclaw.js";
import { getState, setActiveWorkspace } from "./state.js";
import { send } from "./ws.js";
import { setRequestedSessionId } from "./stream.js";

export type AppMode = "normal" | "iwork" | "automation";

/**
 * ModeTransitionManager — single orchestrator for all three-mode switching.
 *
 * Core principle: when entering automation from iWork, the workspace is
 * **exited immediately** (state released) rather than preserved. This
 * means:
 *   - Automation → Normal: only the automation hide animation plays.
 *   - Automation → iWork:  automation hide + workspace enter play in parallel.
 *
 * The workspace's internal `onModeChange` callback is suppressed during
 * transitions; this manager calls it manually at the right moment so the
 * welcome title animation always fires exactly once.
 */
export class ModeTransitionManager {
  private _workspace: Workspace;
  private _automationPanel: AutomationPanel;
  private _onModeChange: () => void;
  private _transitioning = false;
  private _preAutomationMode: AppMode = "normal";
  /** Saved active workspace path so re-entering iWork restores it. */
  private _savedActiveWorkspace = "";

  constructor(opts: {
    workspace: Workspace;
    automationPanel: AutomationPanel;
    onModeChange: () => void;
  }) {
    this._workspace = opts.workspace;
    this._automationPanel = opts.automationPanel;
    this._onModeChange = opts.onModeChange;
  }

  get isTransitioning(): boolean {
    return this._transitioning;
  }

  getCurrentMode(): AppMode {
    if (this._automationPanel.isActive) return "automation";
    return getState().workspaceMode === "iwork" ? "iwork" : "normal";
  }

  async switchMode(target: AppMode): Promise<void> {
    const current = this.getCurrentMode();
    if (target === current || this._transitioning) return;
    this._transitioning = true;

    // Suppress workspace's internal onModeChange — we call it ourselves
    // at the right time to avoid double-cleanup and ensure the welcome
    // animation always fires exactly once per transition.
    const origOnModeChange = this._workspace.onModeChange;
    this._workspace.onModeChange = null;

    try {
      if (target === "automation") {
        this._preAutomationMode = current;
        if (current === "iwork") {
          // Save the active workspace so we can restore it when returning.
          this._savedActiveWorkspace = getState().activeWorkspace;
          // Exit workspace AND show automation in parallel.
          // This "releases" the workspace state immediately so that
          // returning to normal mode doesn't replay the workspace
          // exit animation, and returning to iWork replays the enter
          // animation fresh.
          await Promise.all([
            this._workspace.exit(),
            this._automationPanel.show(),
          ]);
        } else {
          await this._automationPanel.show();
        }
        // Don't call onModeChange — we're in automation view, not chat.
      } else if (target === "iwork") {
        if (current === "automation") {
          // Restore the saved active workspace and send open_workspace
          // BEFORE entering, so enterWorkspaceMode() sees it set and
          // doesn't auto-activate the first workspace.
          if (this._savedActiveWorkspace) {
            setActiveWorkspace(this._savedActiveWorkspace);
            const requestId = crypto.randomUUID();
            setRequestedSessionId("", requestId);
            send({ type: "open_workspace", path: this._savedActiveWorkspace, request_id: requestId });
            this._savedActiveWorkspace = "";
          }
          // Sequential: hide automation first, then enter workspace.
          // The CSS rule `#app:has(#automation-view:not(.hidden)) #sidebar { width: 0; transition: none; }`
          // keeps the sidebar at width:0 for the entire duration of hideAutomationView().
          // Running workspace.enter() in parallel would make the tree slide invisible.
          // After hide() completes, we force the sidebar to its final width instantly
          // (it would otherwise CSS-transition from 0 → 280px over another 280ms).
          await this._automationPanel.hide();
          const sidebar = document.getElementById("sidebar");
          if (sidebar) {
            sidebar.style.transition = "none";
            void document.body.offsetHeight;
            sidebar.style.transition = "";
          }
          await this._workspace.enter();
        } else {
          // normal -> iwork (direct)
          await this._workspace.enter();
        }
        origOnModeChange?.();
      } else if (target === "normal") {
        if (current === "automation") {
          // Workspace was already exited when entering automation.
          // Just hide automation — no workspace animation needed.
          await this._automationPanel.hide();
        } else {
          // iwork -> normal (direct)
          await this._workspace.exit();
        }
        origOnModeChange?.();
      }
    } finally {
      this._workspace.onModeChange = origOnModeChange;
      this._transitioning = false;
    }
  }

  async toggleAutomation(): Promise<void> {
    if (this.getCurrentMode() === "automation") {
      await this.switchMode(this._preAutomationMode);
    } else {
      await this.switchMode("automation");
    }
  }
}
