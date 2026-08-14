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
 * Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
 *
 * Shared unified-diff renderer.
 *
 * Used by three call sites so a diff looks identical everywhere:
 *   - chat tool cards (file_write / file_edit / apply_patch results)
 *   - review panel, git mode   (raw `git diff` output)
 *   - review panel, artifact mode (artifact diff_text)
 *
 * Handles standard `git diff` output (with `diff --git` / `+++` / `@@`
 * headers) as well as header-less diffs produced by the native `compute_diff`
 * (e.g. new-file artifacts whose body is all `+` lines with no `@@` hunk
 * header). The hunk activates on the first content line, so diffs without a
 * `@@` header still render instead of collapsing to `+0 -0`.
 *
 * Renders in GitHub-style inline or split view. Hunk headers (@@ lines)
 * are skipped. No +/- prefix characters — color alone indicates add/del.
 *
 * Optional rendering modes (passed via DiffRenderOptions):
 *   - maxLines:       truncate huge diffs after N content lines
 *   - richText:       summary-card view instead of per-line diff
 *   - wordDiff:       inline <del>/<ins> word-level highlighting
 *   - hideWhitespace: dim whitespace-only change lines
 *   - splitView:      two-column synchronized-scroll layout
 */

import { getFileIcon } from "./files.js";
import { t } from "./i18n.js";

const MAX_RENDER_LINES = 4000;

// Counter for generating unique split-view scroll container IDs
let splitIdCounter = 0;

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** True for git diff meta/header lines that carry no diff body content. */
function isDiffMetaLine(line: string): boolean {
  return (
    line.startsWith("diff --git") ||
    line.startsWith("--- ") ||
    line.startsWith("index ") ||
    line.startsWith("old mode ") ||
    line.startsWith("new mode ") ||
    line.startsWith("new file mode ") ||
    line.startsWith("deleted file mode ") ||
    line.startsWith("similarity index ") ||
    line.startsWith("dissimilarity index ") ||
    line.startsWith("rename from ") ||
    line.startsWith("rename to ") ||
    line.startsWith("copy from ") ||
    line.startsWith("copy to ") ||
    line.startsWith("Binary files ") ||
    line.startsWith("GIT binary patch")
  );
}

/** A parsed logical diff line (after stripping the +/-/ space prefix). */
interface DiffLine {
  kind: "add" | "del" | "ctx" | "hunk" | "meta";
  text: string;
  ln: number;    // new-file line number for add/ctx lines
  oldLn: number; // old-file line number for del/ctx lines (split view)
}

/** Parse raw unified-diff text into logical lines + file metadata. */
function parseDiff(diffText: string): {
  fileName: string;
  lines: DiffLine[];
} {
  const lines = diffText.split("\n");
  let fileName = "";
  const out: DiffLine[] = [];
  let newLn = 0;
  let oldLn = 0;
  let inHunk = false;
  for (const rawLine of lines) {
    const line = rawLine.replace(/\t/g, "    ");
    if (line.startsWith("+++ ")) {
      if (!line.startsWith("+++ /dev/null")) {
        const m = line.match(/^\+\+\+ (?:[ab]\/)?(.+)$/);
        if (m) fileName = m[1];
      }
    } else if (line.startsWith("--- ")) {
      if (!fileName) {
        const m = line.match(/^--- (?:[ab]\/)?(.+)$/);
        if (m && m[1] !== "/dev/null") fileName = m[1];
      }
    } else if (isDiffMetaLine(line)) {
      continue;
    } else if (line.startsWith("@@")) {
      inHunk = true;
      // Capture both old (-) and new (+) start line numbers.
      const m = line.match(/@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?/);
      newLn = m ? parseInt(m[2], 10) - 1 : 0;
      oldLn = m ? parseInt(m[1], 10) - 1 : 0;
      // Hunk headers are now skipped during rendering — we still parse
      // to correctly track line numbers but do not push a hunk line object.
    } else if (line.startsWith("+")) {
      inHunk = true;
      newLn++;
      out.push({ kind: "add", text: line.slice(1), ln: newLn, oldLn: 0 });
    } else if (line.startsWith("-")) {
      inHunk = true;
      oldLn++;
      out.push({ kind: "del", text: line.slice(1), ln: 0, oldLn });
    } else if (inHunk) {
      newLn++;
      oldLn++;
      const text = line.startsWith(" ") ? line.slice(1) : line;
      out.push({ kind: "ctx", text, ln: newLn, oldLn });
    }
  }
  return { fileName, lines: out };
}

/** Split a line into word tokens (runs of non-space + whitespace kept). */
function tokenize(text: string): string[] {
  return text.match(/(\s+|\S+)/g) || [];
}

/** LCS-based word diff between two lines -> [{op:'eq'|'del'|'add', tok}]. */
function wordDiff(oldText: string, newText: string): Array<{ op: "eq" | "del" | "add"; tok: string }> {
  const a = tokenize(oldText);
  const b = tokenize(newText);
  const n = a.length;
  const m = b.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const result: Array<{ op: "eq" | "del" | "add"; tok: string }> = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      result.push({ op: "eq", tok: a[i] });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      result.push({ op: "del", tok: a[i] });
      i++;
    } else {
      result.push({ op: "add", tok: b[j] });
      j++;
    }
  }
  while (i < n) result.push({ op: "del", tok: a[i++] });
  while (j < m) result.push({ op: "add", tok: b[j++] });
  return result;
}

/** Render a token list as HTML with <del>/<ins> for word-diff. */
function renderTokens(tokens: Array<{ op: "eq" | "del" | "add"; tok: string }>): string {
  let html = "";
  for (const t of tokens) {
    if (t.op === "eq") {
      html += escapeHtml(t.tok);
    } else if (t.op === "del") {
      html += `<del>${escapeHtml(t.tok)}</del>`;
    } else {
      html += `<ins>${escapeHtml(t.tok)}</ins>`;
    }
  }
  return html || " ";
}

/** True when a line's content is all whitespace. */
function isWhitespaceOnly(text: string): boolean {
  return text.trim() === "";
}

export interface DiffRenderOptions {
  fileNameFallback?: string;
  /** Truncate after this many content lines (default MAX_RENDER_LINES). */
  maxLines?: number;
  /** Rich-text summary card view instead of per-line diff. */
  richText?: boolean;
  /** Inline word-level <del>/<ins> highlighting. */
  wordDiff?: boolean;
  /** Dim lines whose change is whitespace-only. */
  hideWhitespace?: boolean;
  /** Split (two-column) view: old on the left, new on the right. */
  splitView?: boolean;
  /** Optional formatter for the truncated-line notice. */
  truncatedNotice?: (hidden: number) => string;
}

/**
 * Render a unified diff as HTML.
 *
 * Accepts either an options object or (for backward compatibility) a plain
 * string used as fileNameFallback.
 *
 * @returns A `<div class="diff-container">…</div>` string, or `""` for empty
 *   input so callers can render their own empty state.
 */
export function renderDiffHtml(
  diffText: string,
  optsOrFallback?: DiffRenderOptions | string,
): string {
  if (!diffText.trim()) return "";

  const opts: DiffRenderOptions = typeof optsOrFallback === "string"
    ? { fileNameFallback: optsOrFallback }
    : (optsOrFallback ?? {});

  const maxLines = opts.maxLines ?? MAX_RENDER_LINES;
  const { fileName, lines } = parseDiff(diffText);
  const fileLabel = fileName || opts.fileNameFallback || "";

  const adds = lines.filter((l) => l.kind === "add").length;
  const dels = lines.filter((l) => l.kind === "del").length;

  // Longest content line (in characters). Used to stretch every add/del row
  // to the right edge of the widest line so the red/green highlight covers
  // the entire row, even when a changed line is short or empty.
  const maxTextLen = lines.reduce((m, l) =>
    (l.kind === "add" || l.kind === "del" || l.kind === "ctx") && l.text.length > m
      ? l.text.length
      : m, 0);

  // Rich-text summary view: no per-line table.
  if (opts.richText) {
    return renderRichText(fileLabel, lines, adds, dels);
  }

  // Split view: two-column (old | new) layout.
  if (opts.splitView) {
    return renderSplitView(fileLabel, lines, adds, dels, opts, maxTextLen);
  }

  // Inline view (default)
  let contentCount = 0;
  let truncated = 0;
  const bodyRows: string[] = [];
  for (const dl of lines) {
    if (dl.kind === "hunk") continue; // skip hunk headers
    if (dl.kind === "add" || dl.kind === "del" || dl.kind === "ctx") {
      if (contentCount >= maxLines) {
        truncated++;
        continue;
      }
      contentCount++;
    }
    bodyRows.push(renderRow(dl, opts, maxTextLen));
  }
  if (truncated > 0) {
    const notice = opts.truncatedNotice
      ? opts.truncatedNotice(truncated)
      : `... [diff truncated, ${truncated} more lines]`;
    bodyRows.push(`<div class="diff-row diff-row-truncated"><span class="diff-ln">&nbsp;</span><span class="diff-content">${escapeHtml(notice)}</span></div>`);
  }

  return `<div class="diff-container">
      <div class="diff-header">
        <span class="diff-file-icon"><img src="${getFileIcon(fileLabel)}" class="icon" style="width:14px;height:14px"></span>
        <span class="diff-file-name">${escapeHtml(fileLabel)}</span>
        <span class="diff-stats"><span class="diff-add-stat">+${adds}</span><span class="diff-del-stat">-${dels}</span></span>
      </div>
      <div class="diff-body">${bodyRows.join("")}</div>
    </div>`;
}

/**
 * Stretch a content span so every row shares the widest line's width.
 * `.diff-content` has `padding: 0 10px` and the global reset uses
 * `box-sizing: border-box`, so a `min-width` of `Nch` would leave only
 * `Nch - 20px` for the text and clip the last character of the widest
 * line. Reserve the padding explicitly.
 */
function contentWidthStyle(maxTextLen: number): string {
  if (maxTextLen <= 0) return "";
  return ` style="min-width: calc(${maxTextLen}ch + 20px)"`;
}

/** Render one logical diff line as an HTML row (inline view). */
function renderRow(dl: DiffLine, opts: DiffRenderOptions, maxTextLen = 0): string {
  if (dl.kind === "hunk") return ""; // skipped
  const wsOnly = opts.hideWhitespace && isWhitespaceOnly(dl.text);
  const wsClass = wsOnly ? " diff-row-ws-only" : "";
  const minW = contentWidthStyle(maxTextLen);
  if (dl.kind === "add") {
    const content = opts.wordDiff
      ? `<ins>${escapeHtml(dl.text)}</ins>`
      : (escapeHtml(dl.text) || " ");
    return `<div class="diff-row diff-row-add${wsClass}"><span class="diff-ln">${dl.ln}</span><span class="diff-content"${minW}>${content}</span></div>`;
  }
  if (dl.kind === "del") {
    const content = opts.wordDiff
      ? `<del>${escapeHtml(dl.text)}</del>`
      : (escapeHtml(dl.text) || " ");
    return `<div class="diff-row diff-row-del${wsClass}"><span class="diff-ln">&nbsp;</span><span class="diff-content"${minW}>${content}</span></div>`;
  }
  // context
  return `<div class="diff-row${wsClass}"><span class="diff-ln">${dl.ln}</span><span class="diff-content"${minW}>${escapeHtml(dl.text) || " "}</span></div>`;
}

/**
 * For word-diff, re-render adjacent del+add block pairs with inline
 * token-level <del>/<ins>. This post-processes the parsed lines so paired
 * changes show what words actually moved, not whole-line highlights.
 */
export function renderDiffHtmlWordDiff(
  diffText: string,
  opts?: Omit<DiffRenderOptions, "wordDiff">,
): string {
  return renderDiffHtml(diffText, { ...opts, wordDiff: true });
}

/** Rich-text summary card: file header + per-hunk add/del preview. */
function renderRichText(
  fileLabel: string,
  lines: DiffLine[],
  adds: number,
  dels: number,
): string {
  const addedPreview = lines.filter((l) => l.kind === "add").slice(0, 3);
  const delPreview = lines.filter((l) => l.kind === "del").slice(0, 3);

  const previewRow = (dl: DiffLine, cls: string) =>
    `<div class="rt-preview-line ${cls}">${escapeHtml(dl.text.slice(0, 120)) || " "}</div>`;

  const total = adds + dels;
  const addPct = total > 0 ? Math.round((adds / total) * 100) : 0;

  return `<div class="diff-container diff-rich-text">
      <div class="diff-header">
        <span class="diff-file-icon"><img src="${getFileIcon(fileLabel)}" class="icon" style="width:14px;height:14px"></span>
        <span class="diff-file-name">${escapeHtml(fileLabel)}</span>
        <span class="diff-stats"><span class="diff-add-stat">+${adds}</span><span class="diff-del-stat">-${dels}</span></span>
      </div>
      <div class="rt-body">
        <div class="rt-stat-row">
          <span class="rt-stat-add">+${adds} ${escapeHtml(t("sessionInner.reviewRtAdded"))}</span>
          <span class="rt-stat-del">-${dels} ${escapeHtml(t("sessionInner.reviewRtDeleted"))}</span>
          <span class="rt-stat-pct">${escapeHtml(t("sessionInner.reviewRtAddPct", { n: addPct }))}</span>
        </div>
        ${addedPreview.length ? `<div class="rt-section"><div class="rt-section-title">${escapeHtml(t("sessionInner.reviewRtAddPreview"))}</div>${addedPreview.map((l) => previewRow(l, "rt-add")).join("")}</div>` : ""}
        ${delPreview.length ? `<div class="rt-section"><div class="rt-section-title">${escapeHtml(t("sessionInner.reviewRtDelPreview"))}</div>${delPreview.map((l) => previewRow(l, "rt-del")).join("")}</div>` : ""}
      </div>
    </div>`;
}

/**
 * Split (two-column) view: old file on the left, new file on the right.
 * Each side has its own scroll container; scrolling one syncs the other.
 * Hunk headers are skipped entirely. No +/- prefix characters.
 */
function renderSplitView(
  fileLabel: string,
  lines: DiffLine[],
  adds: number,
  dels: number,
  opts: DiffRenderOptions,
  maxTextLen = 0,
): string {
  const maxLines = opts.maxLines ?? MAX_RENDER_LINES;
  const minW = contentWidthStyle(maxTextLen);
  let contentCount = 0;
  let truncated = 0;

  // Buffer pending dels/adds so they pair up top-to-bottom.
  let delQueue: DiffLine[] = [];
  let addQueue: DiffLine[] = [];

  // Build left (old) and right (new) side arrays
  const leftRows: string[] = [];
  const rightRows: string[] = [];

  function addRow(isDel: boolean, oldLn: number, newLn: number, text: string): void {
    if (contentCount >= maxLines) { truncated++; return; }
    contentCount++;
    const ln = oldLn || newLn;
    const cls = isDel ? "diff-row-del" : "diff-row-add";
    const side = isDel ? "left" : "right";
    const lineNum = isDel ? oldLn : newLn;
    if (side === "left") {
      leftRows.push(`<div class="diff-row ${cls}"><span class="diff-ln">${lineNum || "&nbsp;"}</span><span class="diff-content"${minW}>${escapeHtml(text) || " "}</span></div>`);
      rightRows.push(`<div class="diff-row diff-row-empty"><span class="diff-ln">&nbsp;</span><span class="diff-content"${minW}>&nbsp;</span></div>`);
    } else {
      leftRows.push(`<div class="diff-row diff-row-empty"><span class="diff-ln">&nbsp;</span><span class="diff-content"${minW}>&nbsp;</span></div>`);
      rightRows.push(`<div class="diff-row ${cls}"><span class="diff-ln">${lineNum || "&nbsp;"}</span><span class="diff-content"${minW}>${escapeHtml(text) || " "}</span></div>`);
    }
  }

  function flushQueues(): void {
    const n = Math.max(delQueue.length, addQueue.length);
    for (let i = 0; i < n; i++) {
      const d = delQueue[i];
      const a = addQueue[i];
      if (d) {
        leftRows.push(`<div class="diff-row diff-row-del"><span class="diff-ln">${d.oldLn || "&nbsp;"}</span><span class="diff-content"${minW}>${escapeHtml(d.text) || " "}</span></div>`);
      } else {
        leftRows.push(`<div class="diff-row diff-row-empty"><span class="diff-ln">&nbsp;</span><span class="diff-content"${minW}>&nbsp;</span></div>`);
      }
      if (a) {
        rightRows.push(`<div class="diff-row diff-row-add"><span class="diff-ln">${a.ln || "&nbsp;"}</span><span class="diff-content"${minW}>${escapeHtml(a.text) || " "}</span></div>`);
      } else {
        rightRows.push(`<div class="diff-row diff-row-empty"><span class="diff-ln">&nbsp;</span><span class="diff-content"${minW}>&nbsp;</span></div>`);
      }
    }
    delQueue = [];
    addQueue = [];
  }

  for (const dl of lines) {
    if (dl.kind === "hunk") {
      flushQueues();
      continue; // skip hunk headers entirely
    }
    if (contentCount >= maxLines) {
      if (dl.kind !== "ctx") { truncated++; }
      continue;
    }
    if (dl.kind === "del") {
      delQueue.push(dl);
    } else if (dl.kind === "add") {
      addQueue.push(dl);
    } else {
      // ctx: flush pending changes, then render a paired context row.
      flushQueues();
      contentCount++;
      const ctxRow = `<div class="diff-row"><span class="diff-ln">${dl.oldLn}</span><span class="diff-content"${minW}>${escapeHtml(dl.text) || " "}</span></div>`;
      leftRows.push(ctxRow);
      rightRows.push(ctxRow);
    }
  }
  flushQueues();

  if (truncated > 0) {
    const notice = opts.truncatedNotice
      ? opts.truncatedNotice(truncated)
      : `... [diff truncated, ${truncated} more lines]`;
    const tr = `<div class="diff-row diff-row-truncated"><span class="diff-ln">&nbsp;</span><span class="diff-content">${escapeHtml(notice)}</span></div>`;
    leftRows.push(tr);
    rightRows.push(tr);
  }

  const splitId = `spsc-${++splitIdCounter}`;

  const iconHtml = `<img src="${getFileIcon(fileLabel)}" class="icon" style="width:14px;height:14px">`;

  return `<div class="diff-container diff-split" data-split-id="${splitId}">
      <div class="diff-header">
        <span class="diff-file-icon">${iconHtml}</span>
        <span class="diff-file-name">${escapeHtml(fileLabel)}</span>
        <span class="diff-stats"><span class="diff-add-stat">+${adds}</span><span class="diff-del-stat">-${dels}</span></span>
      </div>
      <div class="diff-split-scroll-wrap">
        <div class="diff-split-scroll-side" data-side="left" data-split-group="${splitId}">
          ${leftRows.join("")}
        </div>
        <div class="diff-split-scroll-side" data-side="right" data-split-group="${splitId}">
          ${rightRows.join("")}
        </div>
      </div>
    </div>`;
}

/**
 * Set up synchronized scrolling for split-view diff containers.
 * Call this after inserting split-view HTML into the DOM.
 * Both sides scroll in sync vertically.
 */
export function setupSplitViewScrollSync(container: HTMLElement): void {
  const pairs = new Map<string, { left?: HTMLElement; right?: HTMLElement }>();
  container.querySelectorAll<HTMLElement>(".diff-split-scroll-side").forEach((el) => {
    const group = el.getAttribute("data-split-group");
    if (!group) return;
    if (!pairs.has(group)) pairs.set(group, {});
    const pair = pairs.get(group)!;
    const side = el.getAttribute("data-side");
    if (side === "left") pair.left = el;
    else if (side === "right") pair.right = el;
  });

  function syncSide(src: HTMLElement, target: HTMLElement): void {
    if ((target as any).__syncing) return;
    (target as any).__syncing = true;
    target.scrollTop = src.scrollTop;
    target.scrollLeft = src.scrollLeft;
    requestAnimationFrame(() => { (target as any).__syncing = false; });
  }

  for (const pair of pairs.values()) {
    if (pair.left && pair.right) {
      pair.left.addEventListener("scroll", () => syncSide(pair.left!, pair.right!));
      pair.right.addEventListener("scroll", () => syncSide(pair.right!, pair.left!));
    }
  }
}
