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
 * Automation panel controller.
 *
 * Manages the full-screen "Automation" view that covers the main chat area.
 * (This module originated from the now-removed "iClaw" mode.)
 *
 * Visibility is expressed as a single class on the panel (`hidden`), and the
 * slide itself lives in CSS — see the "Unified Motion" block near the end of
 * styles.css. The sidebar collapse is likewise a class on #app, whose width
 * transition is also declared in CSS.
 *
 * This controller therefore animates nothing itself. It flips state, fires
 * its callbacks and lets the stylesheet move things. That is deliberate: the
 * old implementation drove the slide with inline transform/transition plus a
 * timer, and any interruption (a second click mid-flight, a minimised window
 * pausing rAF) could strand inline positioning on the shared main-area
 * elements — the layout residue this rewrite removes.
 */

export class AutomationPanel {
  private _toggleBtn: HTMLElement | null = null;
  private _automationView: HTMLElement | null = null;
  private readonly _appEl: HTMLElement | null = null;
  /** Whether the sidebar was already collapsed before automation opened. */
  private _sidebarWasCollapsed = false;

  /** Called each time the automation panel opens */
  public onShow: (() => void) | null = null;
  /** Called each time the automation panel hides */
  public onHide: (() => void) | null = null;

  constructor() {
    this._toggleBtn = document.getElementById("btn-toggle-sidebar");
    this._automationView = document.getElementById("automation-view");
    this._appEl = document.getElementById("app");
  }

  /** Whether the automation view is currently visible. */
  get isActive(): boolean {
    return (
      !!this._automationView &&
      !this._automationView.classList.contains("hidden")
    );
  }

  /** Shows the automation view. No-op when already open. */
  show(): void {
    if (!this._automationView || this.isActive) return;

    // Collapse the sidebar for the duration of the automation view. The
    // width transition is CSS, so adding the class is the whole job.
    if (this._appEl) {
      this._sidebarWasCollapsed =
        this._appEl.classList.contains("sidebar-collapsed");
      this._appEl.classList.add("sidebar-collapsed");
    }

    // The sidebar is force-collapsed here, so its toggle must not look
    // clickable. The search button is deliberately left untouched.
    if (this._toggleBtn) {
      (this._toggleBtn as HTMLButtonElement).disabled = true;
    }

    this._automationView.classList.remove("hidden");
    this.onShow?.();
  }

  /** Hides the automation view. No-op when not open. */
  hide(): void {
    if (!this._automationView || !this.isActive) return;

    // Restore the sidebar, unless it was already collapsed on entry.
    if (this._appEl && !this._sidebarWasCollapsed) {
      this._appEl.classList.remove("sidebar-collapsed");
    }
    if (this._toggleBtn) {
      (this._toggleBtn as HTMLButtonElement).disabled = false;
    }

    this._automationView.classList.add("hidden");
    this.onHide?.();
  }

  /** Toggles automation panel visibility (show when hidden, hide when shown). */
  toggle(): void {
    if (this.isActive) {
      this.hide();
    } else {
      this.show();
    }
  }
}
