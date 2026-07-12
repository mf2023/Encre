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
 * Modal dialog system.
 *
 * A small, dependency-free modal framework used across the renderer for
 * confirm/prompt/alert prompts, engine-install confirmation, progress dialogs
 * and arbitrary HTML content. All dialogs share a single overlay/card visual
 * language and resolve via Promises; at most one overlay exists at a time.
 */

import { t } from "./i18n.js";

type Resolve<T> = (value: T) => void;

/**
 * Static collection of modal dialog builders.
 *
 * Every method returns a Promise that resolves when the user dismisses the
 * dialog. A single shared overlay element backs all instances.
 */
export class Dialog {
  private static overlay: HTMLElement | null = null;

  private static createOverlay(): HTMLElement {
    if (this.overlay) {
      this.overlay.remove();
    }
    const overlay = document.createElement("div");
    overlay.className = "encre-dialog-overlay";
    document.body.appendChild(overlay);
    this.overlay = overlay;
    return overlay;
  }

  private static card(overlay: HTMLElement): HTMLElement {
    const card = document.createElement("div");
    card.className = "encre-dialog-card";
    overlay.appendChild(card);
    return card;
  }

  private static titleEl(card: HTMLElement, text: string): void {
    const h = document.createElement("h3");
    h.className = "encre-dialog-title";
    h.textContent = text;
    card.appendChild(h);
  }

  private static bodyEl(card: HTMLElement, text: string): void {
    const p = document.createElement("p");
    p.className = "encre-dialog-body";
    p.textContent = text;
    card.appendChild(p);
  }

  private static buttons(card: HTMLElement, primary: string, secondary: string): {
    primaryBtn: HTMLButtonElement;
    secondaryBtn: HTMLButtonElement | null;
    footer: HTMLElement;
  } {
    const footer = document.createElement("div");
    footer.className = "encre-dialog-footer";
    card.appendChild(footer);

    let sec: HTMLButtonElement | null = null;
    if (secondary) {
      sec = document.createElement("button");
      sec.className = "btn";
      sec.textContent = secondary;
      footer.appendChild(sec);
    }

    const pri = document.createElement("button");
    pri.className = "btn btn--primary";
    pri.textContent = primary;
    footer.appendChild(pri);

    return { primaryBtn: pri, secondaryBtn: sec, footer };
  }

  /** Shows a confirm dialog; resolves `true` for the primary button, `false` otherwise. */
  static confirm(title: string, message: string): Promise<boolean> {
    return new Promise((resolve) => {
      const overlay = this.createOverlay();
      const card = this.card(overlay);
      this.titleEl(card, title);
      this.bodyEl(card, message);
      const { primaryBtn, secondaryBtn } = this.buttons(card, t("dialog.confirm"), t("dialog.cancel"));

      const done = (val: boolean) => {
        overlay.remove();
        this.overlay = null;
        resolve(val);
      };

      primaryBtn.addEventListener("click", () => done(true));
      if (secondaryBtn) secondaryBtn.addEventListener("click", () => done(false));
      primaryBtn.focus();

      overlay.addEventListener("keydown", (e) => {
        if (e.key === "Escape") done(false);
      });
    });
  }

  /** Shows a text-input prompt; resolves the entered value, or `null` on cancel. */
  static prompt(title: string, message: string, defaultValue = ""): Promise<string | null> {
    return new Promise((resolve) => {
      const overlay = this.createOverlay();
      const card = this.card(overlay);
      this.titleEl(card, title);
      this.bodyEl(card, message);

      const input = document.createElement("input");
      input.type = "text";
      input.className = "encre-dialog-input";
      input.value = defaultValue;
      card.appendChild(input);

      const { primaryBtn, secondaryBtn } = this.buttons(card, t("dialog.save"), t("dialog.cancel"));

      const done = (val: string | null) => {
        overlay.remove();
        this.overlay = null;
        resolve(val);
      };

      primaryBtn.addEventListener("click", () => done(input.value));
      if (secondaryBtn) secondaryBtn.addEventListener("click", () => done(null));
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") done(input.value);
        if (e.key === "Escape") done(null);
      });
      setTimeout(() => {
        input.focus();
        input.setSelectionRange(0, input.value.length);
      }, 100);
    });
  }

  /** Shows an informational alert with a single OK button. */
  static alert(title: string, message: string): Promise<void> {
    return new Promise((resolve) => {
      const overlay = this.createOverlay();
      const card = this.card(overlay);
      this.titleEl(card, title);
      this.bodyEl(card, message);
      const { primaryBtn } = this.buttons(card, t("dialog.ok"), "");

      const done = () => {
        overlay.remove();
        this.overlay = null;
        resolve();
      };

      primaryBtn.addEventListener("click", done);
      primaryBtn.focus();
      overlay.addEventListener("keydown", (e) => {
        if (e.key === "Escape" || e.key === "Enter") done();
      });
    });
  }

  // ------------------------------------------------------------------
  // Engine / driver install prompt
  // ------------------------------------------------------------------
  // Reuses the same visual shell as confirm() so the user sees a
  // dialog they already know (same as the right-click → "Delete"
  // prompt in the session sidebar).  Only the primary / secondary
  // button labels are customised so the ask is unambiguous
  // ("下载引擎" / "暂不下载"), and an optional third line can be
  // added via ``hint`` to show download size / current state.

  /**
   * Confirm dialog variant used for engine/driver install prompts.
   *
   * @param title   - Dialog title.
   * @param body    - Body message.
   * @param options - Optional custom primary/secondary labels and an extra hint line.
   * @returns `true` if confirmed, `false` on cancel/Escape.
   */
  static confirmInstall(
    title: string,
    body: string,
    options?: { primary?: string; secondary?: string; hint?: string },
  ): Promise<boolean> {
    return new Promise((resolve) => {
      const overlay = this.createOverlay();
      const card = this.card(overlay);
      this.titleEl(card, title);
      this.bodyEl(card, body);
      if (options?.hint) {
        const hint = document.createElement("p");
        hint.className = "encre-dialog-hint";
        hint.textContent = options.hint;
        card.appendChild(hint);
      }
      const { primaryBtn, secondaryBtn } = this.buttons(
        card,
        options?.primary || t("dialog.confirm"),
        options?.secondary || t("dialog.cancel"),
      );

      const done = (val: boolean) => {
        overlay.remove();
        this.overlay = null;
        resolve(val);
      };

      primaryBtn.addEventListener("click", () => done(true));
      if (secondaryBtn) secondaryBtn.addEventListener("click", () => done(false));
      primaryBtn.focus();

      overlay.addEventListener("keydown", (e) => {
        if (e.key === "Escape") done(false);
      });
    });
  }

  // ------------------------------------------------------------------
  // Progress dialog
  // ------------------------------------------------------------------
  // Shows a progress bar with status text.  The caller drives it via
  // the returned handle.  Reuses .encre-dialog-overlay and card so
  // the modal looks the same as every other dialog.

  /**
   * Shows a progress dialog and returns a handle to drive it.
   *
   * @param title           - Dialog title.
   * @param initialMessage  - Initial status text.
   * @param options         - Cancellable flag, cancel callback and indeterminate flag.
   * @returns A handle with `update/setMessage/setSubMessage/succeed/fail/cancel`.
   */
  static progress(
    title: string,
    initialMessage: string,
    options?: { cancellable?: boolean; onCancel?: () => void; indeterminate?: boolean },
  ): {
    update(progress: number, message?: string): void;
    setMessage(message: string): void;
    setSubMessage(message: string): void;
    succeed(message: string): void;
    fail(message: string): void;
    cancel(): void;
  } {
    const overlay = this.createOverlay();
    overlay.onclick = (e) => {
      if (e.target !== overlay) return;
      if (options?.cancellable === false) return;
    };
    const card = this.card(overlay);
    card.classList.add("encre-dialog-card--progress");
    this.titleEl(card, title);

    const status = document.createElement("div");
    status.className = "encre-dialog-progress-status";
    status.textContent = initialMessage;
    card.appendChild(status);

    const track = document.createElement("div");
    track.className = "encre-dialog-progress-track";
    if (options?.indeterminate) track.classList.add("is-indeterminate");
    const fill = document.createElement("div");
    fill.className = "encre-dialog-progress-fill";
    track.appendChild(fill);
    card.appendChild(track);

    const sub = document.createElement("div");
    sub.className = "encre-dialog-progress-sub";
    sub.textContent = "";
    card.appendChild(sub);

    const pct = document.createElement("span");
    pct.className = "encre-dialog-progress-pct";
    pct.textContent = options?.indeterminate ? "" : "0%";
    status.appendChild(pct);

    let cancelBtn: HTMLButtonElement | null = null;
    if (options?.cancellable !== false) {
      const footer = document.createElement("div");
      footer.className = "encre-dialog-footer";
      card.appendChild(footer);
      cancelBtn = document.createElement("button");
      cancelBtn.type = "button";
      cancelBtn.className = "btn";
      cancelBtn.textContent = t("dialog.cancel");
      cancelBtn.addEventListener("click", () => {
        handle.cancel();
      });
      footer.appendChild(cancelBtn);
    }

    let done = false;

    const close = () => {
      overlay.classList.add("encre-dialog-dismissing");
      setTimeout(() => {
        overlay.remove();
        if (this.overlay === overlay) this.overlay = null;
      }, 150);
    };

    const setFill = (value: number) => {
      const clamped = Math.max(0, Math.min(100, value));
      fill.style.width = `${clamped}%`;
    };

    const handle = {
      update(progress: number, message?: string) {
        if (done) return;
        if (!options?.indeterminate) {
          setFill(progress);
          pct.textContent = `${Math.round(progress)}%`;
        }
        if (message !== undefined) status.firstChild
          ? (status.firstChild.textContent = message)
          : (status.textContent = message);
        if (status.contains(pct) && !options?.indeterminate) {
          status.appendChild(pct);
        }
      },
      setMessage(message: string) {
        if (done) return;
        const text = document.createTextNode(message);
        status.insertBefore(text, status.firstChild);
        if (status.contains(pct) && !options?.indeterminate) {
          status.appendChild(pct);
        }
      },
      setSubMessage(message: string) {
        if (done) return;
        sub.textContent = message;
      },
      succeed(message: string) {
        if (done) return;
        done = true;
        setFill(100);
        pct.textContent = "100%";
        status.firstChild
          ? (status.firstChild.textContent = message)
          : (status.textContent = message);
        if (status.contains(pct)) status.appendChild(pct);
        track.classList.add("is-success");
        if (cancelBtn) cancelBtn.textContent = t("dialog.ok");
        if (cancelBtn) {
          cancelBtn.removeEventListener("click", () => handle.cancel());
          cancelBtn.addEventListener("click", close);
        } else {
          setTimeout(close, 1200);
        }
      },
      fail(message: string) {
        if (done) return;
        done = true;
        status.firstChild
          ? (status.firstChild.textContent = message)
          : (status.textContent = message);
        if (status.contains(pct)) status.appendChild(pct);
        track.classList.add("is-fail");
        if (cancelBtn) {
          cancelBtn.textContent = t("dialog.ok");
          cancelBtn.removeEventListener("click", () => handle.cancel());
          cancelBtn.addEventListener("click", close);
        } else {
          setTimeout(close, 1800);
        }
      },
      cancel() {
        if (done) return;
        done = true;
        if (options?.onCancel) options.onCancel();
        close();
      },
    };

    if (options?.indeterminate) {
      track.classList.add("is-indeterminate");
    }

    overlay.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && options?.cancellable !== false) {
        handle.cancel();
      }
    });

    return handle;
  }

  /** Shows a dialog whose body is an arbitrary HTML element; resolves on close. */
  static showHtmlDialog(title: string, contentEl: HTMLElement): Promise<void> {
    return new Promise((resolve) => {
      const overlay = this.createOverlay();
      const card = this.card(overlay);
      this.titleEl(card, title);
      card.appendChild(contentEl);

      const footer = document.createElement("div");
      footer.className = "encre-dialog-footer";
      const closeBtn = document.createElement("button");
      closeBtn.className = "btn btn--primary";
      closeBtn.textContent = t("dialog.confirm");
      footer.appendChild(closeBtn);
      card.appendChild(footer);

      const done = () => {
        overlay.remove();
        this.overlay = null;
        resolve();
      };

      closeBtn.addEventListener("click", done);
      overlay.addEventListener("keydown", (e) => {
        if (e.key === "Escape") done();
      });
      closeBtn.focus();
    });
  }
}
