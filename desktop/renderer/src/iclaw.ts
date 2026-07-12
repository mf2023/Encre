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

import { TransitionHelper } from "./transition-helper.js";

/**
 * Automation panel controller.
 *
 * Manages the full-screen "Automation" view that slides in over the main chat
 * area. (This module originated from the now-removed "iClaw" mode.) It handles
 * the sidebar collapse/expand choreography and the slide transition when
 * entering and leaving the automation view.
 */

/**
 * AutomationPanel — controls the automation panel visibility.
 * Previously part of the now-removed iClaw mode, this panel is directly
 * accessible from the sidebar "Automation" button.
 */

export class AutomationPanel {
  private _automationBtn: HTMLElement | null = null;
  private _backBtn: HTMLElement | null = null;
  private _toggleBtn: HTMLElement | null = null;
  private _automationView: HTMLElement | null = null;
  private _mainContent: HTMLElement | null = null;
  private _sessionBar: HTMLElement | null = null;
  private readonly _appEl: HTMLElement | null = null;
  /** Sidebar was collapsed before we entered automation */
  private _sidebarWasCollapsed = false;
  private _transitioning = false;

  /** Called each time the automation panel opens */
  public onShow: (() => void) | null = null;

  constructor() {
    this._automationBtn = document.getElementById("btn-automation");
    this._backBtn = document.getElementById("btn-automation-back");
    this._toggleBtn = document.getElementById("btn-toggle-sidebar");
    this._automationView = document.getElementById("automation-view");
    this._mainContent = document.getElementById("main-content");
    this._sessionBar = document.getElementById("session-bar");
    this._appEl = document.getElementById("app");

    this._automationBtn?.addEventListener("click", () => this.toggleAutomationView());
    this._backBtn?.addEventListener("click", () => this.hideAutomationView());
  }

  /**
   * Whether the automation view is currently visible.
   */
  get isActive(): boolean {
    return !!(this._automationView && !this._automationView.classList.contains("hidden"));
  }

  /** Public: hide automation view if active */
  /** Hides the automation view if it is currently active. */
  hide(): void {
    if (this.isActive) {
      this.hideAutomationView();
    }
  }

  /** Toggle automation panel visibility */
  /** Toggles automation panel visibility (show when hidden, hide when shown). */
  toggleAutomationView(): void {
    if (this.isActive) {
      this.hideAutomationView();
    } else {
      this.showAutomationView();
    }
  }

  /** Slides the automation view in over the main content (collapsing the sidebar). */
  private async showAutomationView(): Promise<void> {
    if (!this._mainContent || !this._automationView || this._transitioning) return;
    this._transitioning = true;

    // Save sidebar state and collapse it
    if (this._appEl) {
      this._sidebarWasCollapsed = this._appEl.classList.contains("sidebar-collapsed");
      if (!this._sidebarWasCollapsed) {
        this._appEl.classList.add("sidebar-collapsed");
      }
    }

    // Hide toggle button, show back button
    if (this._toggleBtn) this._toggleBtn.classList.add("hidden");
    if (this._backBtn) this._backBtn.classList.remove("hidden");

    if (this._sessionBar) this._sessionBar.classList.add("hidden");

    const mainBody = document.getElementById("main-body");

    await TransitionHelper.slide({
      exit: [this._mainContent],
      enter: [this._automationView],
      setup: () => {
        // Make both overlap during transition
        if (mainBody) mainBody.style.position = "relative";
        [this._mainContent!, this._automationView!].forEach(el => {
          el.style.position = "absolute";
          el.style.width = "100%";
          el.style.height = "100%";
          el.style.top = "0";
          el.style.left = "0";
        });
      },
    });

    // Cleanup absolute positioning
    [this._mainContent!, this._automationView!].forEach(el => {
      el.style.position = "";
      el.style.width = "";
      el.style.height = "";
      el.style.top = "";
      el.style.left = "";
    });
    if (mainBody) mainBody.style.position = "";

    // Refresh automation data when panel opens
    this.onShow?.();

    this._transitioning = false;
  }

  /** Slides the automation view out and restores the main content and sidebar. */
  private async hideAutomationView(): Promise<void> {
    if (!this._mainContent || !this._automationView || this._transitioning) return;
    this._transitioning = true;

    if (this._sessionBar) this._sessionBar.classList.remove("hidden");

    const mainBody = document.getElementById("main-body");

    await TransitionHelper.slide({
      exit: [this._automationView],
      enter: [this._mainContent],
      setup: () => {
        // Make both overlap during transition
        if (mainBody) mainBody.style.position = "relative";
        [this._mainContent!, this._automationView!].forEach(el => {
          el.style.position = "absolute";
          el.style.width = "100%";
          el.style.height = "100%";
          el.style.top = "0";
          el.style.left = "0";
        });
        // Restore sidebar state
        if (this._appEl && !this._sidebarWasCollapsed) {
          this._appEl.classList.remove("sidebar-collapsed");
        }
        // Show toggle button, hide back button
        if (this._toggleBtn) this._toggleBtn.classList.remove("hidden");
        if (this._backBtn) this._backBtn.classList.add("hidden");
      },
    });

    // Cleanup absolute positioning
    [this._mainContent!, this._automationView!].forEach(el => {
      el.style.position = "";
      el.style.width = "";
      el.style.height = "";
      el.style.top = "";
      el.style.left = "";
    });
    if (mainBody) mainBody.style.position = "";

    this._transitioning = false;
  }
}