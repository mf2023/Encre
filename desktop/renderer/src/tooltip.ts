/**
 * Custom global tooltip.
 *
 * Replaces the native OS `title` tooltip for every element in the app, on
 * every platform (Windows / macOS / Linux). The native tooltip is suppressed
 * by clearing the element's `title` attribute while it is hovered; our own
 * floating element is rendered instead.
 *
 * Styling (rounded, no fill border beyond the 1px frame) follows the design
 * system and adapts to the active theme:
 *   - background: the same colour painted behind #session-list
 *   - dark mode : 1px pure-white border, pure-white text
 *   - light mode: 1px pure-black border, pure-black text
 */

let tooltipEl: HTMLDivElement | null = null;
let currentEl: HTMLElement | null = null;
let showTimer: number | null = null;
let hideTimer: number | null = null;

const OFFSET = 8;
// Delay before the custom tooltip appears (ms).
const SHOW_DELAY = 1000;
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
    const src = currentEl.dataset.encreTooltipSrc;
    const text = currentEl.dataset.encreTooltip || "";
    if (src === "title") currentEl.setAttribute("title", text);
    else if (src === "data-tooltip") currentEl.setAttribute("data-tooltip", text);
    delete currentEl.dataset.encreTooltip;
    delete currentEl.dataset.encreTooltipSrc;
    currentEl = null;
  }
  if (tooltipEl) tooltipEl.classList.remove("encre-tooltip--visible");
}

function activate(el: HTMLElement): void {
  const attr =
    el.dataset.tooltip != null && el.dataset.tooltip !== ""
      ? "data-tooltip"
      : el.getAttribute("title")
        ? "title"
        : null;
  if (!attr) return;
  const text = (
    attr === "data-tooltip"
      ? el.dataset.tooltip || ""
      : el.getAttribute("title") || ""
  ).trim();
  if (!text) return;
  // Suppress the native OS tooltip immediately so it never flashes.
  el.dataset.encreTooltip = text;
  el.dataset.encreTooltipSrc = attr;
  el.removeAttribute(attr);
  currentEl = el;
  // Show our custom tooltip only after the configured delay.
  if (showTimer) clearTimeout(showTimer);
  showTimer = window.setTimeout(() => {
    showTimer = null;
    if (currentEl === el) show(el, text);
  }, SHOW_DELAY);
}

function handleOver(e: Event): void {
  if (currentEl) return;
  const target = e.target as HTMLElement | null;
  if (!target) return;
  const el = target.closest<HTMLElement>("[data-tooltip], [title]");
  if (!el || el.closest(SKIP_SELECTOR)) return;
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
  const el = target.closest<HTMLElement>("[data-tooltip], [title]");
  if (!el || el.closest(SKIP_SELECTOR)) return;
  activate(el);
}

function handleBlur(e: FocusEvent): void {
  if (!currentEl) return;
  const related = e.relatedTarget as Node | null;
  if (related && currentEl.contains(related)) return;
  restoreAndHide();
}

export function initTooltip(): void {
  ensureTooltip();
  syncBackground();

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
    const src = currentEl.dataset.encreTooltipSrc;
    const t = currentEl.dataset.encreTooltip || "";
    if (src === "title") currentEl.setAttribute("title", t);
    else if (src === "data-tooltip") currentEl.setAttribute("data-tooltip", t);
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
