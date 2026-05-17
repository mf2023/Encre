import { setPendingPermission } from "./state.js";

const TIMEOUT_SEC = 60;

export class Permissions {
  private overlay: HTMLElement;
  private toolName: HTMLElement;
  private reason: HTMLElement;
  private timer: HTMLElement;
  private btnAllow: HTMLElement;
  private btnDeny: HTMLElement;
  private countdown: ReturnType<typeof setInterval> | null = null;
  private startTime = 0;
  private callback: ((allowed: boolean) => void) | null = null;

  constructor() {
    this.overlay = document.getElementById("permission-overlay")!;
    this.toolName = document.getElementById("permission-tool-name")!;
    this.reason = document.getElementById("permission-reason")!;
    this.timer = document.getElementById("permission-timer")!;
    this.btnAllow = document.getElementById("btn-allow")!;
    this.btnDeny = document.getElementById("btn-deny")!;

    this.btnAllow.addEventListener("click", () => this.resolve(true));
    this.btnDeny.addEventListener("click", () => this.resolve(false));

    const btnClose = document.getElementById("btn-permission-close");
    btnClose?.addEventListener("click", () => this.resolve(false));

    this.overlay.addEventListener("click", (e) => {
      if (e.target === this.overlay) this.resolve(false);
    });
  }

  show(
    toolName: string,
    reason: string,
    cb: (allowed: boolean) => void
  ): void {
    this.callback = cb;
    this.startTime = Date.now();

    this.toolName.textContent = `Tool: ${toolName}`;
    this.reason.textContent = `Reason: ${reason}`;
    this.overlay.classList.remove("hidden");
    this.updateTimer();
    this.countdown = setInterval(() => this.updateTimer(), 500);
  }

  hide(): void {
    this.overlay.classList.add("hidden");
    if (this.countdown) {
      clearInterval(this.countdown);
      this.countdown = null;
    }
    setPendingPermission(null);
    this.callback = null;
  }

  private resolve(allowed: boolean): void {
    this.hide();
    this.callback?.(allowed);
  }

  private updateTimer(): void {
    const elapsed = Math.floor((Date.now() - this.startTime) / 1000);
    const remaining = Math.max(0, TIMEOUT_SEC - elapsed);
    this.timer.textContent = `Auto-deny in ${remaining}s`;

    if (remaining <= 0) {
      this.resolve(false);
    }
  }
}
