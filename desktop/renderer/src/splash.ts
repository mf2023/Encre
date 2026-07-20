import { EALoader } from "./ealoader.js";
import { t } from "./i18n.js";

export class SplashScreen {
  private loader: EALoader | null = null;
  private errorEl: HTMLElement | null = null;

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

    this.createErrorArea(el);
  }

  hide(): void {
    document.body.classList.remove("splash-mode");
    const el = document.getElementById("splash-screen");
    if (el) el.classList.add("hidden");
    if (this.loader) {
      this.loader.destroy();
      this.loader = null;
    }
    this.errorEl = null;
  }

  showError(message: string, onRestart: () => void): void {
    if (this.errorEl) {
      const msgEl = this.errorEl.querySelector(".splash-error-message") as HTMLElement;
      if (msgEl) msgEl.textContent = message;
      this.errorEl.classList.remove("hidden");
      const btn = this.errorEl.querySelector(".splash-restart-btn") as HTMLElement;
      if (btn) {
        btn.textContent = t("app.splashRestart");
        btn.onclick = () => {
          btn.textContent = t("app.splashRestarting");
          (btn as HTMLButtonElement).disabled = true;
          onRestart();
        };
      }
    }
  }

  private createErrorArea(parent: HTMLElement): void {
    if (this.errorEl) return;
    const el = document.createElement("div");
    el.className = "splash-error hidden";
    el.innerHTML = `
      <div class="splash-error-icon-wrap">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
      </div>
      <div class="splash-error-message"></div>
      <button class="splash-restart-btn btn btn-sm"></button>
    `;
    parent.appendChild(el);
    this.errorEl = el;
  }
}