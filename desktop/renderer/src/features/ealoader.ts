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
 * Animated brand-logo loader component.
 *
 * A self-contained, theme-aware animated SVG loader used across the app
 * (splash screen, engine install, etc.). It auto-swaps the source when the
 * document `data-theme` attribute changes and supports a static-image mode.
 */

/**
 * EALoader - a reusable animated brand-logo loader.
 *
 * Renders the EN-W / EN-B animated SVG into the given parent element.
 * The svg keeps its intrinsic 793:123 aspect ratio and stretches to
 * 100% of the parent's content width, capped by `--ea-loader-max-w`
 * (defaults to 240px).  No hard-coded width / height is ever baked in,
 * so the loader fits any container it's dropped into.
 *
 * The source is swapped automatically when the document's
 * `data-theme` attribute changes (the same attribute the rest of
 * the app reads via state.setTheme).
 *
 * When `opts.staticSrc` is provided, the loader renders a static
 * image instead of the theme-aware animated SVGs, and skips the
 * MutationObserver for theme changes.
 */
export class EALoader {
  private readonly el: HTMLDivElement;
  private readonly img: HTMLImageElement;
  private observer: MutationObserver | null = null;
  private isDark: boolean;
  private readonly _staticMode: boolean;
  private readonly _staticLightSrc: string | undefined;
  private readonly _staticDarkSrc: string | undefined;

  /**
   * Creates the loader inside `parent`.
   *
   * @param parent - Element to append the loader to.
   * @param opts   - Optional `maxWidth` (CSS value, capped by `--ea-loader-max-w`)
   *                 and `staticSrc` (when provided, render a static image, no observer).
   *                 When `staticSrc` is paired with `staticDarkSrc`, the loader
   *                 swaps between the two on theme change (static mode still observes).
   */
  constructor(parent: HTMLElement, opts: { maxWidth?: string; staticSrc?: string; staticDarkSrc?: string } = {}) {
    this._staticMode = !!opts.staticSrc;
    this._staticLightSrc = opts.staticSrc;
    this._staticDarkSrc = opts.staticDarkSrc;
    this.isDark = EALoader.readDark();
    this.el = document.createElement("div");
    this.el.className = "ea-loader";
    if (opts.maxWidth) {
      this.el.style.setProperty("--ea-loader-max-w", opts.maxWidth);
    }
    this.img = document.createElement("img");
    this.img.alt = "";
    this.img.draggable = false;
    this.img.decoding = "async";
    this.img.src = this._staticMode
      ? (this.isDark && this._staticDarkSrc ? this._staticDarkSrc : this._staticLightSrc!)
      : EALoader.srcFor(this.isDark);
    if (opts.staticSrc) this.el.classList.add("ea-loader--static");
    this.el.appendChild(this.img);
    parent.appendChild(this.el);

    if (typeof MutationObserver !== "undefined") {
      this.observer = new MutationObserver(() => this.refresh());
      this.observer.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["data-theme"],
      });
    }
  }

  /** Re-read the current theme and swap the source if it flipped. */
  refresh(): void {
    const nowDark = EALoader.readDark();
    if (nowDark !== this.isDark) {
      this.isDark = nowDark;
      this.img.src = this._staticMode
        ? (nowDark && this._staticDarkSrc ? this._staticDarkSrc : this._staticLightSrc!)
        : EALoader.srcFor(this.isDark);
    }
  }

  /** Detach listeners and remove the loader from the DOM. */
  destroy(): void {
    if (this.observer) {
      this.observer.disconnect();
      this.observer = null;
    }
    if (this.el.parentNode) this.el.parentNode.removeChild(this.el);
  }

  private static srcFor(dark: boolean): string {
    return dark ? "assets/Encre-load-dm.svg" : "assets/Encre-load-lm.svg";
  }

  private static readDark(): boolean {
    const attr = document.documentElement.getAttribute("data-theme");
    if (attr === "dark") return true;
    if (attr === "light") return false;
    try {
      return window.matchMedia("(prefers-color-scheme: dark)").matches;
    } catch {
      return true;
    }
  }
}
