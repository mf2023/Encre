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
 * Motion helper.
 *
 * Every view and panel transition in the app is declared in CSS — see the
 * "Unified Motion" block near the end of styles.css. JavaScript never writes
 * inline `transform`, `opacity` or `transition`; it toggles classes and lets
 * the stylesheet do the animating.
 *
 * That is what keeps switching free of residue. There is no inline state to
 * clean up afterwards, and an interrupted transition simply continues from
 * wherever it had reached instead of wedging the next one.
 *
 * This module exists for the one thing CSS alone cannot give a caller: the
 * shared duration token, read back so the stylesheet stays the single source
 * of truth for timing.
 */

export class TransitionHelper {
  /**
   * Duration of the slowest motion step (view / panel travel) in
   * milliseconds, read from `--duration-slow`.
   *
   * Deliberately resolved on every call rather than cached: the token is
   * overridden under `prefers-reduced-motion`, and a caller that sequences
   * work against the animation should honour the reduced value too.
   */
  static get DEFAULT_DURATION(): number {
    return TransitionHelper.step("--duration-slow", 280);
  }

  /**
   * Reads a `--duration-*` token and returns it in milliseconds. Accepts
   * both `s` and `ms` units, and falls back when the token is absent (for
   * example before the stylesheet has loaded).
   */
  static step(token: string, fallback: number): number {
    if (typeof document === "undefined") return fallback;
    const raw = getComputedStyle(document.documentElement)
      .getPropertyValue(token)
      .trim();
    if (!raw) return fallback;
    const value = parseFloat(raw);
    if (!Number.isFinite(value)) return fallback;
    return raw.endsWith("ms") ? Math.round(value) : Math.round(value * 1000);
  }
}
