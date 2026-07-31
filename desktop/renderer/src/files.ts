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
 * File & attachment handling for the composer.
 *
 * Owns the composer's attachment surface: drag-and-drop, paste and file/folder
 * pickers feed into base64-backed `AttachmentMeta` records stored in app state.
 * Attachments are rendered as read-only "chips" inserted at the caret or
 * appended to the input, and kept in sync with state via a subscription.
 */

import { getMaterialFileIcon } from "@baybreezy/file-extension-icon";
import { AttachmentMeta } from "./types.js";
import { addAttachments, removeAttachment, getState, subscribe } from "./state.js";

const MAX_SINGLE_SIZE = 10 * 1024 * 1024;
const BATCH_SIZE = 5;

function readBatch<T, R>(items: T[], fn: (item: T) => Promise<R>, size: number): Promise<R[]> {
  const results: R[] = [];
  const run = async (): Promise<R[]> => {
    for (let i = 0; i < items.length; i += size) {
      const batch = items.slice(i, i + size);
      results.push(...await Promise.all(batch.map(fn)));
    }
    return results;
  };
  return run();
}

/**
 * Manages composer attachments (drag/drop, paste, picker) and their chips.
 */
/** Returns a file icon SVG data URI from baybreezy Material icons. */
export function getFileIcon(name: string): string {
  return getMaterialFileIcon(name);
}

export class Files {
  private input: HTMLElement;

  /**
   * Constructor: wires drag/drop/paste listeners and a state subscription.
   *
   * @param input - The content-editable composer element that hosts chips.
   */
  constructor(input: HTMLElement) {
    this.input = input;

    this.input.addEventListener("dragover", (e) => {
      e.preventDefault();
      this.input.classList.add("drag-over");
    });

    this.input.addEventListener("dragleave", () => {
      this.input.classList.remove("drag-over");
    });

    this.input.addEventListener("drop", async (e: DragEvent) => {
      e.preventDefault();
      this.input.classList.remove("drag-over");
      const files = e.dataTransfer?.files;
      if (files && files.length > 0) {
        await this.readDroppedFiles(files);
      }
    });

    this.input.addEventListener("paste", async (e: ClipboardEvent) => {
      const items = e.clipboardData?.items;
      if (items) {
        const pasteFiles: File[] = [];
        for (const item of items) {
          if (item.kind === "file") {
            const file = item.getAsFile();
            if (file) pasteFiles.push(file);
          }
        }
        if (pasteFiles.length > 0) {
          e.preventDefault();
          await this.readDroppedFiles(pasteFiles);
        }
      }
    });

    subscribe(() => {
      const attachments = getState().attachments;
      const existingPaths = new Set<string>();
      this.input.querySelectorAll('[data-attach]').forEach(el => {
        const path = el.getAttribute('data-path');
        if (path) {
          if (attachments.some(a => a.path === path)) {
            existingPaths.add(path);
          } else {
            el.remove();
          }
        }
      });
      const toAdd: AttachmentMeta[] = [];
      for (const a of attachments) {
        if (!existingPaths.has(a.path)) {
          toAdd.push(a);
        }
      }
      if (toAdd.length > 0) {
        const frag = document.createDocumentFragment();
        for (const a of toAdd) {
          frag.appendChild(this.makeChip(a));
        }
        this.input.appendChild(frag);
        this.input.appendChild(document.createTextNode(""));
        if ((window as any).lucide) {
          (window as any).lucide.createIcons({ nodes: [this.input] });
        }
        const ph = document.getElementById("prompt-placeholder");
        if (ph) ph.classList.add("hidden");
      }
    });
  }

  /** Opens the native file picker and reads the selected files. */
  async promptForFiles(): Promise<void> {
    if (!window.electronAPI) return;
    const paths = await window.electronAPI.pickFiles();
    if (paths.length === 0) return;
    await this.readPaths(paths);
  }

  /** Opens the native folder picker and attaches the chosen directory. */
  async promptForFolder(): Promise<void> {
    if (!window.electronAPI) return;
    const dirPath = await window.electronAPI.pickDirectory();
    if (!dirPath) return;
    await this.readDirectory(dirPath);
  }

  /** Reads dropped File objects, converting each to a base64 attachment. */
  private async readDroppedFiles(files: FileList | File[]): Promise<void> {
    const arr = Array.from(files).filter(f => f.size <= MAX_SINGLE_SIZE);
    const attachments = await readBatch(arr, async (file) => {
      const filePath = (file as any).path || file.name;
      const content = await this.fileToBase64(file);
      return {
        name: file.name,
        path: filePath,
        content,
        mime_type: file.type || "",
        size: file.size || 0,
        is_binary: false,
      } as AttachmentMeta;
    }, BATCH_SIZE);
    if (attachments.length === 0) return;
    addAttachments(attachments);
    this.batchInsertChips(attachments);
  }

  /** Reads files from absolute paths via the Electron bridge. */
  private async readPaths(paths: string[]): Promise<void> {
    const attachments = await readBatch(paths, async (fp) => {
      if (!window.electronAPI) return null;
      const result = await window.electronAPI.readFile(fp);
      if (!result || result.size === 0 || result.size > MAX_SINGLE_SIZE) return null;
      const name = fp.split(/[/\\]/).pop() ?? fp;
      return {
        name,
        path: fp,
        content: result.content,
        mime_type: result.mime_type || "",
        size: result.size,
        is_binary: result.is_binary,
      } as AttachmentMeta;
    }, BATCH_SIZE);
    const valid = attachments.filter(a => a !== null) as AttachmentMeta[];
    if (valid.length === 0) return;
    addAttachments(valid);
    this.batchInsertChips(valid);
  }

  /** Attaches a directory (represented as a special attachment) to the composer. */
  async readDirectory(dirPath: string): Promise<void> {
    const api = window.electronAPI;
    if (!api) return;
    const result = await api.readDirectory(dirPath);
    if (!result) return;
    const att: AttachmentMeta = {
      name: result.name,
      path: result.path,
      content: "",
      mime_type: "text/x-directory",
      size: 0,
      is_binary: false,
    };
    addAttachments([att]);
    this.batchInsertChips([att]);
  }

  private fileToBase64(file: File): Promise<string> {
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result as string;
        const base64 = result.split(",")[1] || result;
        resolve(base64);
      };
      reader.readAsDataURL(file);
    });
  }

  private batchInsertChips(attachments: AttachmentMeta[]): void {
    try {
      const sel = window.getSelection();
      const inInput = sel && sel.rangeCount > 0 && this.input.contains(sel.anchorNode);
      const frag = document.createDocumentFragment();
      for (const a of attachments) {
        frag.appendChild(this.makeChip(a));
      }
      if (inInput) {
        const range = sel!.getRangeAt(0);
        range.deleteContents();
        range.insertNode(frag);
        range.collapse(false);
        sel!.removeAllRanges();
        sel!.addRange(range);
      } else {
        this.input.appendChild(frag);
        this.input.appendChild(document.createTextNode(""));
      }
      if ((window as any).lucide) {
        (window as any).lucide.createIcons({ nodes: [this.input] });
      }
    } catch (e) {
      console.error("[Files] batchInsertChips error:", e);
    }
  }

  /** Returns the lucide icon name for a file based on its extension. */
  fileIcon(name: string): string {
    return getFileIcon(name);
  }

  private fmtSize(bytes: number): string {
    if (!bytes || bytes < 0) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  /** Builds a read-only attachment chip element and wires its remove button. */
  private makeChip(att: AttachmentMeta): HTMLSpanElement {
    const chip = document.createElement("span");
    chip.contentEditable = "false";
    chip.className = "mode-chip";
    chip.setAttribute("data-attach", "true");
    chip.setAttribute("data-path", att.path);
    const isDir = att.mime_type === "text/x-directory";
    const label = att.name.length > 6 ? att.name.slice(0, 6) + "..." : att.name;
    const icon = isDir ? "folder" : att.mime_type === "text/x-terminal" ? "terminal" : this.fileIcon(att.name);
    const summary = isDir ? "· folder"
      : att.mime_type === "text/x-terminal" ? `· ${att.size} line${att.size !== 1 ? "s" : ""}`
      : `· ${this.fmtSize(att.size)}`;
    chip.innerHTML = `<i data-lucide="${icon}" class="chip-icon" style="width:12px;height:12px;"></i><span class="mode-card-label">${label}</span><span class="mode-card-summary">${summary}</span><button class="mode-card-remove" data-path="${att.path}"><i data-lucide="x" class="lucide" style="width:11px;height:11px;"></i></button>`;

    chip.querySelector(".mode-card-remove")?.addEventListener("click", (e) => {
      e.stopPropagation();
      removeAttachment(att.path);
    });

    return chip;
  }
}
