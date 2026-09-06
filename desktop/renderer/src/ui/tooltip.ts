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
 * Custom global tooltip.
 *
 * Replaces the native OS `title` tooltip for every element in the app, on
 * every platform (Windows / macOS / Linux). The native tooltip is permanently
 * suppressed by stripping the `title` attribute from ALL elements at init
 * time (storing the text in `data-encre-original-title`) and watching for
 * any new `title` attributes via MutationObserver.  Only our own floating
 * element is rendered.
 *
 * Also handles `data-i18n-title` (translation key) — looks up the current
 * locale and shows the translated text, so elements don't need a redundant
 * hardcoded `data-tooltip`.
 *
 * Styling (rounded, no fill border beyond the 1px frame) follows the design
 * system and adapts to the active theme:
 *   - background: the same colour painted behind #session-list
 *   - dark mode : 1px pure-white border, pure-white text
 *   - light mode: 1px pure-black border, pure-black text
 */

import { t } from "./i18n.js";

let tooltipEl: HTMLDivElement | null = null;
let currentEl: HTMLElement | null = null;
let showTimer: number | null = null;
let hideTimer: number | null = null;

const OFFSET = 8;
// Delay before the custom tooltip appears (ms).
const SHOW_DELAY = 1000;
// Native tooltip storage attribute (replaces `title` everywhere).
const TITLE_ATTR = "data-encre-original-title";
// Elements whose native tooltip we must NOT replace.
const SKIP_SELECTOR = ".window-btn, .header-window-controls";

function ensureTooltip(): HTMLDivElement {
  if (tooltipEl) return tooltipEl;
  const el = document.createElement("div");
  el.className = "encre-tooltip";
  el.setAttribute("role", "tooltip");
  document.body.appendChild(el);
  tooltipEl = el;
  return el;
}

function resolvePaintedBackground(start: HTMLElement | null): string {
  let node: HTMLElement | null = start;
  while (node) {
    const bg = getComputedStyle(node).backgroundColor;
    if (bg && bg !== "rgba(0, 0, 0, 0)" && bg !== "transparent") return bg;
    node = node.parentElement;
  }
  return "var(--bg-secondary)";
}

function syncBackground(): void {
  const el = ensureTooltip();
  el.style.background = resolvePaintedBackground(
    document.getElementById("session-list"),
  );
}

function position(el: HTMLElement): void {
  const tip = tooltipEl!;
  const rect = el.getBoundingClientRect();
  const tw = tip.offsetWidth;
  const th = tip.offsetHeight;

  let left = rect.left + rect.width / 2 - tw / 2;
  let top = rect.bottom + OFFSET;

  if (top + th > window.innerHeight - 4) {
    top = rect.top - th - OFFSET;
  }

  left = Math.max(4, Math.min(left, window.innerWidth - tw - 4));
  top = Math.max(4, Math.min(top, window.innerHeight - th - 4));

  tip.style.left = `${left}px`;
  tip.style.top = `${top}px`;
}

function positionAt(x: number, y: number): void {
  const tip = tooltipEl!;
  const tw = tip.offsetWidth;
  const th = tip.offsetHeight;

  let left = x - tw / 2;
  let top = y + OFFSET;

  if (top + th > window.innerHeight - 4) {
    top = y - th - OFFSET;
  }

  left = Math.max(4, Math.min(left, window.innerWidth - tw - 4));
  top = Math.max(4, Math.min(top, window.innerHeight - th - 4));

  tip.style.left = `${left}px`;
  tip.style.top = `${top}px`;
}

function show(el: HTMLElement, text: string): void {
  const tip = ensureTooltip();
  if (currentEl === el && tip.classList.contains("encre-tooltip--visible")) {
    tip.textContent = text;
    position(el);
    return;
  }
  tip.textContent = text;
  syncBackground();
  position(el);
  tip.classList.add("encre-tooltip--visible");
}

function restoreAndHide(): void {
  if (showTimer) {
    clearTimeout(showTimer);
    showTimer = null;
  }
  if (hideTimer) {
    clearTimeout(hideTimer);
    hideTimer = null;
  }
  if (currentEl) {
    // Never restore `title` — that would let the native OS tooltip
    // reappear.  The text stays in `data-encre-original-title` if
    // that was the original source.
    delete currentEl.dataset.encreTooltip;
    delete currentEl.dataset.encreTooltipSrc;
    currentEl = null;
  }
  if (tooltipEl) tooltipEl.classList.remove("encre-tooltip--visible");
}

function getTooltipText(el: HTMLElement): { attr: string; text: string } | null {
  // 1. Check data-i18n-title (translation key) — dynamic i18n, overrides everything.
  const i18nKey = el.getAttribute("data-i18n-title");
  if (i18nKey) {
    return { attr: "data-i18n-title", text: t(i18nKey).trim() };
  }
  // 2. Check custom tooltip (data-tooltip).
  if (el.dataset.tooltip != null && el.dataset.tooltip !== "") {
    return { attr: "data-tooltip", text: el.dataset.tooltip.trim() };
  }
  // 3. Check stored native tooltip (data-encre-original-title).
  const stored = el.getAttribute(TITLE_ATTR);
  if (stored) {
    return { attr: TITLE_ATTR, text: stored.trim() };
  }
  return null;
}

function activate(el: HTMLElement): void {
  const info = getTooltipText(el);
  if (!info || !info.text) return;
  el.dataset.encreTooltip = info.text;
  el.dataset.encreTooltipSrc = info.attr;
  currentEl = el;
  if (showTimer) clearTimeout(showTimer);
  showTimer = window.setTimeout(() => {
    showTimer = null;
    if (currentEl === el) show(el, info!.text);
  }, SHOW_DELAY);
}

function handleOver(e: Event): void {
  const target = e.target as HTMLElement | null;
  if (!target) return;
  const el = target.closest<HTMLElement>(
    `[data-tooltip], [data-i18n-title], [${TITLE_ATTR}]`,
  );
  if (!el || el.closest(SKIP_SELECTOR)) return;
  // Same element already active — nothing to do.
  if (currentEl === el) return;
  // Different element — cancel pending timers, hide tooltip, reactivate.
  if (showTimer) clearTimeout(showTimer);
  if (hideTimer) clearTimeout(hideTimer);
  showTimer = null;
  hideTimer = null;
  if (tooltipEl) tooltipEl.classList.remove("encre-tooltip--visible");
  currentEl = null;
  activate(el);
}

function handleOut(e: Event): void {
  if (!currentEl) return;
  const related = (e as MouseEvent).relatedTarget as Node | null;
  if (related && currentEl.contains(related)) return;
  restoreAndHide();
}

function handleFocus(e: FocusEvent): void {
  if (currentEl) return;
  const target = e.target as HTMLElement | null;
  if (!target) return;
  const el = target.closest<HTMLElement>(
    `[data-tooltip], [data-i18n-title], [${TITLE_ATTR}]`,
  );
  if (!el || el.closest(SKIP_SELECTOR)) return;
  activate(el);
}

function handleBlur(e: FocusEvent): void {
  if (!currentEl) return;
  const related = e.relatedTarget as Node | null;
  if (related && currentEl.contains(related)) return;
  restoreAndHide();
}

/**
 * Strip `title` from `el`, storing the original value in
 * `data-encre-original-title` so the custom tooltip can still use it.
 */
function stripTitle(el: Element): void {
  const existing = el.getAttribute(TITLE_ATTR);
  const t = el.getAttribute("title");
  if (t && !existing) {
    el.setAttribute(TITLE_ATTR, t);
  }
  el.removeAttribute("title");
}

export function initTooltip(): void {
  ensureTooltip();
  syncBackground();

  // ─────────────────────────────────────────────────────────────────
  // 1. Strip `title` from every existing element so the native OS
  //    tooltip can never fire on any platform.
  // ─────────────────────────────────────────────────────────────────
  document.querySelectorAll("[title]").forEach(stripTitle);

  // ─────────────────────────────────────────────────────────────────
  // 2. Watch for dynamically added `title` attributes and strip them
  //    immediately, before the browser has a chance to render the
  //    native tooltip.
  // ─────────────────────────────────────────────────────────────────
  const titleObserver = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type === "attributes" && mutation.attributeName === "title") {
        stripTitle(mutation.target as Element);
      }
    }
  });
  titleObserver.observe(document.body, {
    subtree: true,
    attributes: true,
    attributeFilter: ["title"],
  });

  // ─────────────────────────────────────────────────────────────────
  // 3. Capture-phase handlers — also strip `title` on every mouseover
  //    as a safety net in case the MutationObserver misses something
  //    (e.g. a title set by a third-party script).
  // ─────────────────────────────────────────────────────────────────
  document.addEventListener(
    "mouseover",
    (e) => {
      const target = e.target as HTMLElement | null;
      if (target?.hasAttribute("title")) stripTitle(target);
    },
    true,
  );

  document.addEventListener("mouseover", handleOver, true);
  document.addEventListener("mouseout", handleOut, true);
  document.addEventListener("focusin", handleFocus, true);
  document.addEventListener("focusout", handleBlur, true);

  window.addEventListener(
    "scroll",
    () => {
      if (hideTimer) clearTimeout(hideTimer);
      hideTimer = window.setTimeout(restoreAndHide, 0);
    },
    true,
  );
  window.addEventListener("blur", restoreAndHide);
  document.addEventListener("pointerdown", restoreAndHide, true);

  const themeObserver = new MutationObserver(() => syncBackground());
  themeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
}

/**
 * Show the custom tooltip at an arbitrary viewport position with custom text.
 * Used by canvas-based widgets (e.g. the Chart.js usage chart) that have no
 * single DOM element to attach `data-tooltip` to. Bypasses the hover delay.
 */
export function showTooltipAt(text: string, x: number, y: number): void {
  if (!text) return;
  const tip = ensureTooltip();
  if (showTimer) {
    clearTimeout(showTimer);
    showTimer = null;
  }
  // Detach from any element-driven tooltip so we don't fight the scheduler.
  if (currentEl) {
    delete currentEl.dataset.encreTooltip;
    delete currentEl.dataset.encreTooltipSrc;
    currentEl = null;
  }
  tip.textContent = text;
  syncBackground();
  positionAt(x, y);
  tip.classList.add("encre-tooltip--visible");
}

/** Hide a tooltip previously shown via {@link showTooltipAt}. */
export function hideTooltip(): void {
  if (tooltipEl) tooltipEl.classList.remove("encre-tooltip--visible");
}
