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
 * Application splash screen controller.
 *
 * Manages the full-screen splash overlay shown during application startup and
 * engine bootstrap. Wraps an {@link EALoader} animation and toggles the
 * `splash-mode` body class plus the `#splash-screen` visibility.
 */

import { EALoader } from "./ealoader.js";

/**
 * Controls the startup splash screen.
 *
 * Owns a lazily-created {@link EALoader} instance used for the animated logo and
 * exposes `show`/`hide` to drive the overlay.
 */
export class SplashScreen {
  private loader: EALoader | null = null;

  /** Shows the splash overlay and (lazily) creates the EALoader animation. */
  show(): void {
    document.body.classList.add("splash-mode");
    const el = document.getElementById("splash-screen")!;
    el.classList.remove("hidden");
    if (!this.loader) {
      this.loader = new EALoader(el, {
        maxWidth: "140px",
        staticSrc: "assets/Encre.svg",
      });
    }
  }

  /** Hides the splash overlay and tears down the EALoader animation. */
  hide(): void {
    document.body.classList.remove("splash-mode");
    const el = document.getElementById("splash-screen");
    if (el) el.classList.add("hidden");
    if (this.loader) {
      this.loader.destroy();
      this.loader = null;
    }
  }
}
