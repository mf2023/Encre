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

import { Workspace } from "../session/workspace.js";
import { AutomationPanel } from "../session/iclaw.js";
import { getState, setActiveWorkspace } from "../core/state.js";
import { send } from "../core/ws.js";
import { setRequestedSessionId } from "../core/stream.js";

export type AppMode = "normal" | "iwork" | "automation";

/**
 * ModeTransitionManager — single orchestrator for all three-mode switching.
 *
 * Core principle: when entering automation from iWork, the workspace is
 * **exited immediately** (state released) rather than preserved. This means:
 *   - Automation → Normal: only the automation hide animation plays.
 *   - Automation → iWork:  automation hide + workspace enter play in parallel.
 *
 * The workspace's internal `onModeChange` callback is suppressed during
 * transitions; this manager calls it manually at the right moment so the
 * welcome title animation always fires exactly once.
 *
 * Animating is not this class's job. Each branch below only changes *state* —
 * releasing a workspace, opening the automation panel — by toggling the
 * classes the stylesheet listens for. The moves themselves are declared in
 * CSS (see "Unified Motion" in styles.css), which means:
 *
 *   - Switching no longer waits on an animation. `refreshAllData`,
 *     `cleanupContentArea`, `chat.render()` and the backend round-trips all
 *     run immediately; the view slides under them.
 *   - Nothing here writes inline positioning, so nothing can be left behind
 *     by an interrupted switch. Rapid switching simply re-targets the CSS
 *     transition from wherever it had reached.
 */
export class ModeTransitionManager {
  private _workspace: Workspace;
  private _automationPanel: AutomationPanel;
  private _onModeChange: () => void;
  /** Invoked when leaving the automation view, before it slides away, so the
   *  in-panel sub-agent detail (breadcrumb, activeExecution, header buttons)
   *  can be torn down first and not leak into the target mode. */
  private _onLeaveAutomation: () => void;
  /** Invoked when leaving workspace (iwork) mode — used by the app to close
   *  the task-overview view before the automation view covers the area. */
  private _onLeaveWorkspace: () => void;
  private _transitioning = false;
  /** Mode the panel was opened from — used by the keyboard/tray toggle so
   *  closing automation returns there. The header seg does NOT use this: its
   *  tabs switch straight to the selected mode. */
  private _preAutomationMode: AppMode = "normal";
  /** Saved active workspace path so re-entering iWork restores it. */
  private _savedActiveWorkspace = "";

  constructor(opts: {
    workspace: Workspace;
    automationPanel: AutomationPanel;
    onModeChange: () => void;
    onLeaveAutomation?: () => void;
    onLeaveWorkspace?: () => void;
  }) {
    this._workspace = opts.workspace;
    this._automationPanel = opts.automationPanel;
    this._onModeChange = opts.onModeChange;
    this._onLeaveAutomation = opts.onLeaveAutomation ?? (() => {});
    this._onLeaveWorkspace = opts.onLeaveWorkspace ?? (() => {});
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

    // When leaving automation, close the in-panel sub-agent detail
    // (breadcrumb, activeExecution, header buttons) first, so no detail
    // state leaks into the target mode.
    if (current === "automation") {
      this._onLeaveAutomation();
    }

    // Suppress workspace's internal onModeChange — we call it ourselves
    // at the right moment to avoid double-cleanup and to make sure the
    // welcome animation fires exactly once per transition.
    const origOnModeChange = this._workspace.onModeChange;
    this._workspace.onModeChange = null;

    try {
      if (target === "automation") {
        this._preAutomationMode = current;
        if (current === "iwork") {
          // Remember the active workspace so returning to iWork restores it.
          this._savedActiveWorkspace = getState().activeWorkspace;
          this._onLeaveWorkspace();
          // Exit workspace and show automation *together*: both are class
          // toggles, so the tree slides out while the panel slides in.
          await Promise.all([
            this._workspace.exit(),
            Promise.resolve(this._automationPanel.show()),
          ]);
        } else {
          // Entered from normal: there is no workspace to restore, so clear
          // any path saved by an earlier iWork visit — otherwise a later
          // automation → iWork switch would resurrect a stale workspace.
          this._savedActiveWorkspace = "";
          this._automationPanel.show();
        }
        // No onModeChange here — we are in the automation view, not chat.
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
          // Both are class toggles, so the automation panel slides away while
          // the workspace comes back and the sidebar re-expands — one move.
          this._automationPanel.hide();
          await this._workspace.enter();
        } else {
          // normal -> iwork (direct)
          await this._workspace.enter();
        }
        origOnModeChange?.();
      } else if (target === "normal") {
        if (current === "automation") {
          // The workspace was already exited when entering automation, so
          // there is nothing to slide out besides the panel itself.
          this._automationPanel.hide();
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
      // Keyboard shortcut / tray toggle: return to the mode automation was
      // opened from. The header seg never calls this — it switches straight
      // to whichever tab was clicked (no intermediate hop).
      await this.switchMode(this._preAutomationMode);
    } else {
      await this.switchMode("automation");
    }
  }
}
