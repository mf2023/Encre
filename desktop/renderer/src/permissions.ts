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
 * Runtime permission prompting.
 *
 * Implements the renderer-side "ask the user" branch of Encre's tool-permission
 * policy. Static allow/deny decisions are resolved once by the Rust backend and
 * never reach this layer; this module only handles the interactive prompt that
 * appears when a tool invocation needs explicit user consent, recording the
 * decision back into the backend policy table so later calls are silent.
 */

import { setPendingPermission } from "./state.js";
import { t } from "./i18n.js";
import { Dialog } from "./dialog.js";

/**
 * Unified permission prompt.
 *
 * The user only ever sees this dialog for the "ask" branch.  Static
 * allow/deny decisions are decided by Rust in a single call and never
 * surface here.  When the user clicks allow, the answer is recorded
 * in the Rust policy table so subsequent invocations of the same tool
 * are silent.
 *
 * Visually the prompt reuses the standard ``Dialog.confirm`` shell
 * (same overlay/card/buttons as the right-click "Delete" confirmation),
 * keeping a single design language across the app.
 */
export class Permissions {
  private active = false;

  /**
   * Shows the permission prompt for a tool invocation.
   *
   * @param toolName - Name of the tool requesting access.
   * @param reason   - Human-readable justification shown to the user.
   * @param cb       - Callback invoked with `true` when allowed, `false` otherwise.
   *
   * Reuses the standard install/confirm dialog shell. If a prompt is already
   * open the new request is rejected immediately (`false`) so the agent loop is
   * never blocked.
   */
  show(
    toolName: string,
    reason: string,
    cb: (allowed: boolean) => void,
  ): void {
    if (this.active) {
      // A previous request is still open -- fall through to its
      // resolver with "deny" so the agent loop is not blocked.
      cb(false);
      return;
    }
    this.active = true;
    setPendingPermission({ tool: toolName, reason });

    const title = t("permissions.title", { name: toolName });
    const body = t("permissions.body", {
      name: toolName,
      reason: reason || t("permissions.noReason"),
    });
    const allow = t("permissions.allow");
    const deny = t("permissions.deny");

    // Reuse the same modal as the "Delete" / engine-install confirm:
    // same overlay, same card, same primary/secondary buttons.
    Dialog.confirmInstall(title, body, { primary: allow, secondary: deny })
      .then((allowed) => {
        this.active = false;
        setPendingPermission(null);
        cb(allowed);
      })
      .catch(() => {
        this.active = false;
        setPendingPermission(null);
        cb(false);
      });
  }

  /**
   * Dismisses any pending permission prompt and clears the pending state.
   *
   * The underlying dialog removes itself on user interaction, so this only
   * resets the internal `active` flag and the pending-permission record.
   */
  hide(): void {
    // No persistent overlay to clean up -- Dialog.confirmInstall
    // removes itself when the user clicks a button or presses Esc.
    setPendingPermission(null);
    this.active = false;
  }
}
