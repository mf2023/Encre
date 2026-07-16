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
  /** Called each time the automation panel hides */
  public onHide: (() => void) | null = null;

  constructor() {
    this._toggleBtn = document.getElementById("btn-toggle-sidebar");
    this._automationView = document.getElementById("automation-view");
    this._mainContent = document.getElementById("main-content");
    this._sessionBar = document.getElementById("session-bar");
    this._appEl = document.getElementById("app");
  }

  /**
   * Whether the automation view is currently visible.
   */
  get isActive(): boolean {
    return !!(this._automationView && !this._automationView.classList.contains("hidden"));
  }

  /** Hides the automation view if it is currently active. Returns a promise that
   *  resolves when the hide transition completes (or immediately if not active).
   *  If `instant` is true, skips the slide animation. */
  async hide(instant = false): Promise<void> {
    if (this.isActive) {
      if (instant) {
        this._instantHide();
      } else {
        await this.hideAutomationView();
      }
    }
  }

  /** Shows the automation view. Returns a promise that resolves when the show
   *  transition completes. */
  async show(): Promise<void> {
    await this.showAutomationView();
  }

  /** Toggles automation panel visibility (show when hidden, hide when shown). */
  async toggleAutomationView(): Promise<void> {
    if (this.isActive) {
      await this.hideAutomationView();
    } else {
      await this.showAutomationView();
    }
  }

  /** Instantly hides automation view without animation. Used when switching
   *  directly to another mode to avoid a double-transition flash. */
  private _instantHide(): void {
    if (this._automationView) {
      this._automationView.classList.add("hidden");
      this._automationView.style.position = "";
      this._automationView.style.width = "";
      this._automationView.style.height = "";
      this._automationView.style.top = "";
      this._automationView.style.left = "";
      this._automationView.style.transition = "";
      this._automationView.style.transform = "";
      this._automationView.style.opacity = "";
    }
    // main-content was hidden by TransitionHelper.slide (it was the exit element)
    if (this._mainContent) {
      this._mainContent.classList.remove("hidden");
      this._mainContent.style.position = "";
      this._mainContent.style.width = "";
      this._mainContent.style.height = "";
      this._mainContent.style.top = "";
      this._mainContent.style.left = "";
      this._mainContent.style.transition = "";
      this._mainContent.style.transform = "";
      this._mainContent.style.opacity = "";
    }
    const mainBody = document.getElementById("main-body");
    if (mainBody) mainBody.style.position = "";
    if (this._sessionBar) this._sessionBar.classList.remove("hidden");
    if (this._appEl && !this._sidebarWasCollapsed) {
      this._appEl.classList.remove("sidebar-collapsed");
    }
    if (this._toggleBtn) {
      this._toggleBtn.style.transition = "";
      this._toggleBtn.style.opacity = "";
      this._toggleBtn.style.transform = "";
      this._toggleBtn.style.pointerEvents = "";
    }
    this.onHide?.();
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

    // Smoothly fade+slide the sidebar toggle button instead of instant hide.
    // The toggle button becomes the "back" button in the detail view, so we
    // only fade it here for the list view; the search button is never touched
    // - it stays in place across the automation list and detail views.
    if (this._toggleBtn) {
      this._toggleBtn.style.transition = "opacity 0.12s cubic-bezier(0.4, 0, 0.2, 1), transform 0.12s cubic-bezier(0.4, 0, 0.2, 1)";
      this._toggleBtn.style.opacity = "0";
      this._toggleBtn.style.transform = "translateX(-8px)";
      this._toggleBtn.style.pointerEvents = "none";
    }

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

    // Clear button transition after animation
    if (this._toggleBtn) this._toggleBtn.style.transition = "";

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
        // Restore toggle button with slide-in from right
        if (this._toggleBtn) {
          this._toggleBtn.style.transition = "none";
          this._toggleBtn.style.transform = "translateX(100%)";
          this._toggleBtn.style.opacity = "0";
          requestAnimationFrame(() => {
            this._toggleBtn!.style.transition = "opacity 0.28s cubic-bezier(0.4, 0, 0.2, 1), transform 0.28s cubic-bezier(0.4, 0, 0.2, 1)";
            this._toggleBtn!.style.transform = "translateX(0)";
            this._toggleBtn!.style.opacity = "";
            this._toggleBtn!.style.pointerEvents = "";
          });
        }
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

    // Clear button transition after animation
    if (this._toggleBtn) this._toggleBtn.style.transition = "";

    this._transitioning = false;
    this.onHide?.();
  }
}