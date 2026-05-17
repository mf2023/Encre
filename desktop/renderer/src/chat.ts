import { getState, subscribe } from "./state.js";
import type { Message } from "./types.js";
import MarkdownIt from "markdown-it";
import hljs from "highlight.js";

const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  breaks: true,
});

md.renderer.rules.fence = (tokens, idx) => {
  const token = tokens[idx];
  const lang = token.info ? token.info.trim().split(/\s+/)[0] : "";
  let content = token.content;

  if (lang && hljs.getLanguage(lang)) {
    try {
      content = hljs.highlight(content, { language: lang }).value;
    } catch {
      content = escapeHtml(content);
    }
  } else {
    content = escapeHtml(content);
  }

  const attr = lang ? ` class="hljs language-${lang}"` : ' class="hljs"';
  return `<pre><code${attr}>${content}</code></pre>\n`;
};

md.renderer.rules.code_inline = (tokens, idx) => {
  const content = tokens[idx].content;
  return `<code class="inline-code">${escapeHtml(content)}</code>`;
};

function renderMarkdown(text: string): string {
  if (!text) return "";
  const trimmed = text.replace(/\n+$/, "");
  const html = md.render(trimmed);
  return html.replace(/(?:<br\s*\/?>\s*)+$/, "").replace(/<p>\s*<\/p>\s*$/, "");
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export class Chat {
  private ml: HTMLElement;
  private welcomeScreen: HTMLElement;
  private container: HTMLElement;
  private userScrolledUp = false;
  private renderedCount = 0;
  private lastRenderedContent = "";
  private lastRenderedThinking = "";
  private lastRenderedToolCards = "";
  private hadThinkingPhase = false;
  private userToggledThinking = false;

  constructor() {
    this.ml = document.getElementById("message-list")!;
    this.welcomeScreen = document.getElementById("welcome-screen")!;
    this.container = document.getElementById("chat-container")!;

    this.container.addEventListener("scroll", () => {
      const { scrollTop, scrollHeight, clientHeight } = this.container;
      this.userScrolledUp = scrollHeight - scrollTop - clientHeight > 100;
    });

    subscribe(() => this.render());
  }

  render(): void {
    const state = getState();
    this.toggleWelcome(state.messages.length === 0);

    const msgs = state.messages;

    if (msgs.length === 0) {
      this.ml.innerHTML = "";
      this.renderedCount = 0;
      return;
    }

    if (msgs.length !== this.renderedCount || !this.isLastStreaming(msgs)) {
      this.fullRender(msgs);
    } else {
      this.incrementalUpdate(msgs);
    }
  }

  private isLastStreaming(msgs: Message[]): boolean {
    const last = msgs[msgs.length - 1];
    return last.role === "assistant" && last.isStreaming;
  }

  private fullRender(msgs: Message[]): void {
    let html = "";

    for (const msg of msgs) {
      html += this.renderMessageHTML(msg);
    }

    this.ml.innerHTML = html;
    this.renderedCount = msgs.length;
    this.lastRenderedContent = "";
    this.lastRenderedThinking = "";
    this.lastRenderedToolCards = "";
    this.hadThinkingPhase = false;
    this.userToggledThinking = false;
    this.bindToolClicks();
    this.autoScroll(msgs);
  }

  private incrementalUpdate(msgs: Message[]): void {
    const lastMsg = msgs[msgs.length - 1];
    const lastEl = this.ml.lastElementChild;
    if (!lastEl) return;

    const contentEl = lastEl.querySelector(".message-content");
    const thinkingDetails = lastEl.querySelector(".thinking") as HTMLElement | null;
    const thinkingEl = lastEl.querySelector(".thinking-content");
    const headerEl = lastEl.querySelector(".message-header");
    const bodyEl = lastEl.querySelector(".message-body");
    const toolCardsEl = lastEl.querySelector(".tool-cards");

    if (!contentEl) return;

    const preserveScroll = this.userScrolledUp;
    const savedScrollTop = preserveScroll ? this.container.scrollTop : 0;

    if (lastMsg.thinking) {
      this.hadThinkingPhase = true;
      const newThinking = renderMarkdown(lastMsg.thinking);
      if (thinkingEl && thinkingDetails) {
        if (newThinking !== this.lastRenderedThinking) {
          thinkingEl.innerHTML = newThinking;
          this.lastRenderedThinking = newThinking;
        }
        if (!thinkingDetails.open && !this.userToggledThinking) {
          thinkingDetails.open = true;
        }
      } else {
        if (contentEl && lastEl.classList.contains("assistant")) {
          if (thinkingDetails) {
            thinkingDetails.insertAdjacentHTML(
              "beforeend",
              `<div class="thinking-content">${newThinking}</div>`
            );
          } else {
            contentEl.insertAdjacentHTML(
              "beforebegin",
              `<details class="thinking" open>
                <summary><i data-lucide="chevron-right" class="lucide"></i> 思考过程</summary>
                <div class="thinking-content">${newThinking}</div>
              </details>`
            );
          }
          this.lastRenderedThinking = newThinking;
          const newDetails = contentEl.parentElement?.querySelector(".thinking") as HTMLElement | null;
          if (newDetails) {
            newDetails.addEventListener("toggle", () => {
              this.userToggledThinking = true;
            });
          }
          if (typeof (window as any).lucide !== "undefined") {
            (window as any).lucide.createIcons({ root: contentEl.parentElement });
          }
        }
      }
    } else if (
      this.hadThinkingPhase &&
      thinkingDetails &&
      thinkingDetails.open &&
      !this.userToggledThinking &&
      (lastMsg.content.trim().length > 0 || lastMsg.toolCalls.length > 0)
    ) {
      thinkingDetails.open = false;
      this.hadThinkingPhase = false;
    }

    const newContent = renderMarkdown(lastMsg.content);
    if (newContent !== this.lastRenderedContent) {
      contentEl.innerHTML = newContent;
      this.lastRenderedContent = newContent;
    }

    if (!headerEl && bodyEl && lastEl.classList.contains("assistant")) {
      bodyEl.insertAdjacentHTML(
        "afterbegin",
        `<div class="message-header"><span class="message-model">Yim Agent</span></div>`
      );
    }

    if (lastMsg.toolCalls.length > 0 && lastEl.classList.contains("assistant")) {
      const toolKey = JSON.stringify(
        lastMsg.toolCalls.map((tc) => ({
          i: tc.id,
          n: tc.name,
          s: tc.status,
          r: tc.result?.slice(0, 200),
          e: tc.isError,
          p: tc.params,
        }))
      );
      if (toolKey !== this.lastRenderedToolCards) {
        let toolHtml = "";
        for (const tc of lastMsg.toolCalls) {
          const isShell =
            tc.name === "bash" || tc.name === "shell" || tc.name === "terminal";
          const isFileTool = [
            "glob",
            "read",
            "write",
            "grep",
            "search",
            "run_command",
          ].includes(tc.name);
          toolHtml += (isShell || isFileTool)
            ? this.renderTerminalCard(tc)
            : this.renderGenericToolCard(tc);
        }
        const newToolHtml = `<div class="tool-cards">${toolHtml}</div>`;
        if (toolCardsEl) {
          const wrapper = toolCardsEl.parentNode;
          const temp = document.createElement("div");
          temp.innerHTML = newToolHtml.trim();
          wrapper?.replaceChild(temp.firstElementChild!, toolCardsEl);
        } else if (bodyEl) {
          bodyEl.insertAdjacentHTML("beforeend", newToolHtml);
        }
        this.bindToolClicks();
        this.lastRenderedToolCards = toolKey;
      }
    }

    if (preserveScroll) {
      this.container.scrollTop = savedScrollTop;
    }

    this.autoScroll(msgs);
  }

  private renderTerminalCard(tc: ToolCallState): string {
    const isShell = tc.name === "bash" || tc.name === "shell" || tc.name === "terminal";
    let displayCommand = "";
    let displayName = tc.name;

    if (isShell) {
      displayCommand = (tc.params.command as string) || "";
      displayName = "yim";
    } else {
      const paramKeys = Object.keys(tc.params).filter(k => k !== "id");
      displayCommand = paramKeys.map(k => {
        const v = tc.params[k];
        return typeof v === "string" ? `${k}: ${v}` : `${k}: ${JSON.stringify(v)}`;
      }).join("  ");
      displayName = tc.name;
    }

    const statusLabel = tc.isError
      ? "执行失败"
      : tc.status === "running"
        ? "正在运行..."
        : tc.status === "done"
          ? "执行完成"
          : "等待执行";

    const statusClass = tc.isError
      ? "term-status-error"
      : tc.status === "running"
        ? "term-status-running"
        : tc.status === "done"
          ? "term-status-done"
          : "term-status-pending";

    const expanded = tc.result || tc.isError ? " expanded" : "";

    return `<div class="terminal-card${expanded}" data-tool-id="${tc.id}">
      <div class="terminal-header">
        <div class="terminal-header-left">
          <i data-lucide="${isShell ? 'terminal' : 'wrench'}" class="lucide terminal-icon"></i>
          <span class="terminal-name">${displayName}</span>
          <span class="terminal-label ${statusClass}">${statusLabel}</span>
          <i data-lucide="chevron-down" class="lucide terminal-chevron"></i>
        </div>
        <a class="terminal-link" href="#" title="在终端查看">
          在终端查看
          <i data-lucide="arrow-up-right" class="lucide"></i>
        </a>
      </div>
      <div class="terminal-body">
        <div class="terminal-command">
          <span class="terminal-prompt">${isShell ? "$" : ">"}</span>
          <code>${escapeHtml(displayCommand)}</code>
        </div>
        ${
          tc.result
            ? `<pre class="terminal-output ${tc.isError ? "output-error" : ""}">${escapeHtml(tc.result)}</pre>`
            : ""
        }
      </div>
    </div>`;
  }

  private renderGenericToolCard(tc: ToolCallState): string {
    const badgeClass = tc.isError
      ? "tool-badge-error"
      : tc.status === "running"
        ? "tool-badge-running"
        : tc.status === "done"
          ? "tool-badge-done"
          : "tool-badge-default";
    const badgeText = tc.isError
      ? "失败"
      : tc.status === "running"
        ? "运行中"
        : tc.status === "done"
          ? "已完成"
          : "等待中";
    const bodyClass = tc.isError ? "error" : "";
    return `<div class="tool-card" data-tool-id="${tc.id}">
              <div class="tool-card-header">
                <i data-lucide="wrench" class="lucide tool-card-icon"></i>
                <span class="tool-card-label">${escapeHtml(tc.name)}</span>
                <div class="tool-badge ${badgeClass}">
                  <span>${badgeText}</span>
                  <i data-lucide="chevron-down" class="lucide tool-badge-chevron"></i>
                </div>
              </div>
              ${
                tc.result
                  ? `<div class="tool-card-body ${bodyClass}"><pre>${escapeHtml(tc.result)}</pre></div>`
                  : ""
              }
            </div>`;
  }

  private renderMessageHTML(msg: Message): string {
    const isUser = msg.role === "user";
    const hasContent =
      msg.content.trim().length > 0 || msg.toolCalls.length > 0;

    if (isUser) {
      return `<div class="message user">
          <div class="message-bubble">
            <div class="message-content">${renderMarkdown(msg.content)}</div>
            ${hasContent ? `<div class="message-footer">
              <span class="message-model"></span>
              <div class="message-actions">
                <button class="msg-action" title="Edit"><i data-lucide="pencil" class="lucide"></i></button>
                <button class="msg-action" title="Copy"><i data-lucide="copy" class="lucide"></i></button>
                <button class="msg-action msg-action-danger" title="Delete"><i data-lucide="trash-2" class="lucide"></i></button>
              </div>
            </div>` : ""}
          </div>
        </div>`;
    }

    let thinkingBlock = "";
    if (msg.thinking) {
      thinkingBlock = `<details class="thinking" open>
            <summary><i data-lucide="chevron-right" class="lucide"></i> 思考过程</summary>
            <div class="thinking-content">${renderMarkdown(msg.thinking)}</div>
          </details>`;
    }

    let toolCards = "";
    if (msg.toolCalls.length > 0) {
      toolCards = `<div class="tool-cards">`;
      for (const tc of msg.toolCalls) {
        const isShell = tc.name === "bash" || tc.name === "shell" || tc.name === "terminal";

        if (isShell) {
          toolCards += this.renderTerminalCard(tc);
        } else {
          toolCards += this.renderGenericToolCard(tc);
        }
      }
      toolCards += `</div>`;
    }

    const errorClass = msg.hasError ? " has-error" : "";

    let tokenLine = "";
    if (msg.tokenUsage && msg.tokenUsage.total_tokens > 0) {
      const inp = this.fmtTokens(msg.tokenUsage.input_tokens);
      const out = this.fmtTokens(msg.tokenUsage.output_tokens);
      const tot = this.fmtTokens(msg.tokenUsage.total_tokens);
      tokenLine = `<div class="message-tokens">↑ ${inp} ↓ ${out} · ${tot} tokens</div>`;
    }

    return `<div class="message assistant${errorClass}">
          <div class="message-body">
            <div class="message-header">
              <span class="message-model">Yim Agent</span>
            </div>
            ${thinkingBlock}
            <div class="message-content">${renderMarkdown(msg.content)}</div>
            ${toolCards}
            ${tokenLine}
          </div>
        </div>`;
  }

  private autoScroll(msgs: Message[]): void {
    if (msgs.length === 0) return;
    const lastMsg = msgs[msgs.length - 1];
    if (lastMsg.role === "user") {
      this.scrollToBottom();
      return;
    }
    if (!this.userScrolledUp) {
      this.scrollToBottom();
    }
  }

  private toggleWelcome(show: boolean): void {
    if (show) {
      this.welcomeScreen.classList.remove("hidden");
      this.ml.classList.add("hidden");
    } else {
      this.welcomeScreen.classList.add("hidden");
      this.ml.classList.remove("hidden");
    }
  }

  scrollToBottom(): void {
    const container = document.getElementById("chat-container");
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  }

  private fmtTokens(n: number): string {
    if (n >= 1000) return (n / 1000).toFixed(1) + "k";
    return String(n);
  }

  showError(message: string): void {
    const div = document.createElement("div");
    div.className = "error-toast";
    div.textContent = message;
    document.body.appendChild(div);
    setTimeout(() => div.remove(), 5000);
  }

  private bindToolClicks(): void {
    const cards = this.ml.querySelectorAll(".tool-card, .terminal-card");
    cards.forEach((card) => {
      card.addEventListener("click", () => {
        const toolId = card.getAttribute("data-tool-id");
        if (toolId) {
          card.classList.toggle("expanded");
        }
      });
    });
    const thinkBlocks = this.ml.querySelectorAll(".thinking");
    thinkBlocks.forEach((block) => {
      block.addEventListener("toggle", () => {
        this.userToggledThinking = true;
      });
    });
    if (typeof (window as any).lucide !== "undefined") {
      (window as any).lucide.createIcons();
    }
  }
}
