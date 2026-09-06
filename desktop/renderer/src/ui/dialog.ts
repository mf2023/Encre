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
 * Modal dialog system with priority queue.
 *
 * All modal dialogs (confirm/prompt/alert/install/html) share a single
 * internal priority queue.  Only one modal dialog is visible at a time;
 * when it is dismissed the next-highest-priority dialog from the queue
 * is shown automatically.  This prevents dialogs from being silently
 * destroyed by later triggers (e.g. a delete confirm destroyed by a
 * theme-switch shortcut).
 *
 * Progress dialogs live in a separate overlay layer and do not
 * participate in the modal queue — they can be shown alongside other
 * dialogs without conflict.
 */

import { t } from "./i18n.js";

type Resolve<T> = (value: T) => void;

/** Priority level for modal dialogs. */
export type DialogPriority = "low" | "normal" | "high" | "critical";

const PRIORITY_RANK: Record<DialogPriority, number> = {
  low: 0,
  normal: 1,
  high: 2,
  critical: 3,
};

// ── Internal queue ──────────────────────────────────────────────────────

interface ModalEntry {
  priority: DialogPriority;
  build: () => HTMLElement;
  resolve: Resolve<any>;
  reject: (reason?: any) => void;
}

/**
 * Static collection of modal dialog builders.
 *
 * Every method returns a Promise that resolves when the user dismisses the
 * dialog.  Modal dialogs are queued by priority and displayed one at a time.
 */
export class Dialog {
  private static currentOverlay: HTMLElement | null = null;
  private static currentResolve: Resolve<any> | null = null;
  private static queue: ModalEntry[] = [];
  private static progressOverlay: HTMLElement | null = null;

  // ── DOM helpers ─────────────────────────────────────────────────────

  private static makeOverlay(): HTMLElement {
    const overlay = document.createElement("div");
    overlay.className = "encre-dialog-overlay";
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

  // ── Queue management ────────────────────────────────────────────────

  /**
   * Show the highest-priority entry from the queue, if any and if no
   * modal dialog is currently visible.
   */
  private static processQueue(): void {
    if (this.currentOverlay) return;
    if (this.queue.length === 0) return;

    let bestIdx = 0;
    let bestRank = PRIORITY_RANK[this.queue[0].priority];
    for (let i = 1; i < this.queue.length; i++) {
      const r = PRIORITY_RANK[this.queue[i].priority];
      if (r > bestRank) {
        bestRank = r;
        bestIdx = i;
      }
    }

    const entry = this.queue.splice(bestIdx, 1)[0];
    this.currentOverlay = entry.build();
    this.currentResolve = entry.resolve;
    document.body.appendChild(this.currentOverlay);
  }

  /**
   * Dismiss the currently visible modal dialog (remove overlay, resolve
   * its promise, and show the next queued dialog).
   */
  private static dismissCurrent(value: any): void {
    if (!this.currentOverlay) return;
    this.currentOverlay.remove();
    this.currentOverlay = null;
    const resolve = this.currentResolve;
    this.currentResolve = null;
    if (resolve) resolve(value);
    this.processQueue();
  }

  /**
   * Enqueue a modal dialog.  When it reaches the front of the queue,
   * `build` is called to create the overlay element; it must be
   * appended to `document.body` by the caller.  The overlay is
   * automatically removed when the dialog is dismissed.
   */
  private static enqueue<T>(
    priority: DialogPriority,
    build: (resolve: Resolve<T>) => HTMLElement,
  ): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      this.queue.push({
        priority,
        build: () => build(resolve),
        resolve,
        reject,
      });
      this.processQueue();
    });
  }

  // ── Public API ─────────────────────────────────────────────────────

  /** Shows a confirm dialog; resolves `true` for the primary button, `false` otherwise. */
  static confirm(title: string, message: string, priority: DialogPriority = "normal"): Promise<boolean> {
    return this.enqueue<boolean>(priority, (resolve) => {
      const overlay = this.makeOverlay();
      const card = this.card(overlay);
      this.titleEl(card, title);
      this.bodyEl(card, message);
      const { primaryBtn, secondaryBtn } = this.buttons(card, t("dialog.confirm"), t("dialog.cancel"));

      const done = (val: boolean) => {
        overlay.remove();
        this.currentOverlay = null;
        this.currentResolve = null;
        resolve(val);
        this.processQueue();
      };

      primaryBtn.addEventListener("click", () => done(true));
      if (secondaryBtn) secondaryBtn.addEventListener("click", () => done(false));
      primaryBtn.focus();

      overlay.addEventListener("keydown", (e) => {
        if (e.key === "Escape") done(false);
      });

      return overlay;
    });
  }

  /**
   * Shows a confirm dialog confined to a given container (e.g. the session
   * sidebar) instead of the full screen. Reuses the same card/overlay visuals
   * as {@link confirm} but is rendered inside `container` and covers only it.
   *
   * @param container - The element the overlay is appended to (must be
   *                    position:relative so the overlay can cover it).
   * @param options   - Optional custom primary/secondary labels.
   * @returns `true` for the primary button, `false` otherwise.
   */
  static confirmIn(
    container: HTMLElement,
    title: string,
    message: string,
    options?: { primary?: string; secondary?: string },
  ): Promise<boolean> {
    return new Promise<boolean>((resolve) => {
      const overlay = this.makeOverlay();
      overlay.classList.add("encre-dialog-overlay--inline");
      const card = this.card(overlay);
      card.classList.add("encre-dialog-card--inline");
      this.titleEl(card, title);
      this.bodyEl(card, message);
      const { primaryBtn, secondaryBtn } = this.buttons(
        card,
        options?.primary || t("dialog.confirm"),
        options?.secondary || t("dialog.cancel"),
      );

      const done = (val: boolean) => {
        overlay.remove();
        resolve(val);
      };

      primaryBtn.addEventListener("click", () => done(true));
      if (secondaryBtn) secondaryBtn.addEventListener("click", () => done(false));
      primaryBtn.focus();

      overlay.addEventListener("keydown", (e) => {
        if (e.key === "Escape") done(false);
      });
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) done(false);
      });

      container.appendChild(overlay);
    });
  }

  /**
   * Inline prompt (inside a sidebar container, not a full-screen modal).
   * Standalone — not queue-based. Resolves the entered value, or `null` on cancel.
   */
  static promptIn(
    container: HTMLElement,
    title: string,
    message: string,
    defaultValue = "",
    options?: { primary?: string; secondary?: string; placeholder?: string; inputClass?: string },
  ): Promise<string | null> {
    return new Promise<string | null>((resolve) => {
      const overlay = this.makeOverlay();
      overlay.classList.add("encre-dialog-overlay--inline");
      const card = this.card(overlay);
      card.classList.add("encre-dialog-card--inline");
      this.titleEl(card, title);
      this.bodyEl(card, message);

      const input = document.createElement("input");
      input.type = "text";
      input.className = `encre-dialog-input${options?.inputClass ? ` ${options.inputClass}` : ""}`;
      input.value = defaultValue;
      if (options?.placeholder) input.placeholder = options.placeholder;
      card.appendChild(input);

      const { primaryBtn, secondaryBtn } = this.buttons(
        card,
        options?.primary || t("dialog.save"),
        options?.secondary || t("dialog.cancel"),
      );

      const done = (val: string | null) => {
        overlay.remove();
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

      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) done(null);
      });

      container.appendChild(overlay);
    });
  }

  /**
   * Shows a text-input prompt; resolves the entered value, or `null` on cancel.
   *
   * @param options - Optional custom primary/secondary labels, placeholder and input class.
   */
  static prompt(
    title: string,
    message: string,
    defaultValue = "",
    options?: { primary?: string; secondary?: string; placeholder?: string; inputClass?: string },
    priority: DialogPriority = "normal",
  ): Promise<string | null> {
    return this.enqueue<string | null>(priority, (resolve) => {
      const overlay = this.makeOverlay();
      const card = this.card(overlay);
      this.titleEl(card, title);
      this.bodyEl(card, message);

      const input = document.createElement("input");
      input.type = "text";
      input.className = `encre-dialog-input${options?.inputClass ? ` ${options.inputClass}` : ""}`;
      input.value = defaultValue;
      if (options?.placeholder) input.placeholder = options.placeholder;
      card.appendChild(input);

      const { primaryBtn, secondaryBtn } = this.buttons(
        card,
        options?.primary || t("dialog.save"),
        options?.secondary || t("dialog.cancel"),
      );

      const done = (val: string | null) => {
        overlay.remove();
        this.currentOverlay = null;
        this.currentResolve = null;
        resolve(val);
        this.processQueue();
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

      return overlay;
    });
  }

  /** Shows an informational alert with a single OK button. */
  static alert(title: string, message: string, priority: DialogPriority = "normal"): Promise<void> {
    return this.enqueue<void>(priority, (resolve) => {
      const overlay = this.makeOverlay();
      const card = this.card(overlay);
      this.titleEl(card, title);
      this.bodyEl(card, message);
      const { primaryBtn } = this.buttons(card, t("dialog.ok"), "");

      const done = () => {
        overlay.remove();
        this.currentOverlay = null;
        this.currentResolve = null;
        resolve();
        this.processQueue();
      };

      primaryBtn.addEventListener("click", done);
      primaryBtn.focus();
      overlay.addEventListener("keydown", (e) => {
        if (e.key === "Escape" || e.key === "Enter") done();
      });

      return overlay;
    });
  }

  // ── Engine / driver install prompt ──────────────────────────────────

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
    priority: DialogPriority = "normal",
  ): Promise<boolean> {
    return this.enqueue<boolean>(priority, (resolve) => {
      const overlay = this.makeOverlay();
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
        this.currentOverlay = null;
        this.currentResolve = null;
        resolve(val);
        this.processQueue();
      };

      primaryBtn.addEventListener("click", () => done(true));
      if (secondaryBtn) secondaryBtn.addEventListener("click", () => done(false));
      primaryBtn.focus();

      overlay.addEventListener("keydown", (e) => {
        if (e.key === "Escape") done(false);
      });

      return overlay;
    });
  }

  // ── Progress dialog (separate layer) ────────────────────────────────

  /**
   * Shows a progress dialog and returns a handle to drive it.
   *
   * Progress uses a dedicated overlay layer so it never conflicts with
   * modal dialogs (confirm/prompt/alert/etc.).
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
    // Remove any existing progress overlay
    if (this.progressOverlay) {
      this.progressOverlay.remove();
      this.progressOverlay = null;
    }

    const overlay = document.createElement("div");
    overlay.className = "encre-dialog-overlay";
    this.progressOverlay = overlay;
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
        if (this.progressOverlay === overlay) this.progressOverlay = null;
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

    document.body.appendChild(overlay);

    return handle;
  }

  /** Shows a dialog whose body is an arbitrary HTML element; resolves on close. */
  static showHtmlDialog(title: string, contentEl: HTMLElement, priority: DialogPriority = "normal"): Promise<void> {
    return this.enqueue<void>(priority, (resolve) => {
      const overlay = this.makeOverlay();
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
        this.currentOverlay = null;
        this.currentResolve = null;
        resolve();
        this.processQueue();
      };

      closeBtn.addEventListener("click", done);
      overlay.addEventListener("keydown", (e) => {
        if (e.key === "Escape") done();
      });
      closeBtn.focus();

      return overlay;
    });
  }
}
