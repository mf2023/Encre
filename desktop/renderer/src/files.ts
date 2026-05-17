/**
 * Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
 *
 * This file is part of Yim.
 * The Yim project belongs to the Dunimd Team.
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

// File attachment handled via input textarea — no direct state/ws imports needed

export class Files {
  private input: HTMLTextAreaElement;

  constructor(input: HTMLTextAreaElement) {
    this.input = input;

    this.input.addEventListener("dragover", (e) => {
      e.preventDefault();
    });

    this.input.addEventListener("drop", (e: DragEvent) => {
      e.preventDefault();
      const files = e.dataTransfer?.files;
      if (files) {
        this.handleFiles(files);
      }
    });

    this.input.addEventListener("paste", (e: ClipboardEvent) => {
      const items = e.clipboardData?.items;
      if (items) {
        for (const item of items) {
          if (item.kind === "file") {
            e.preventDefault();
            const file = item.getAsFile();
            if (file) {
              this.handleFiles([file]);
            }
            break;
          }
        }
      }
    });
  }

  async promptForFiles(): Promise<void> {
    if (window.electronAPI) {
      const paths = await window.electronAPI.pickFiles();
      if (paths.length > 0) {
        let content = "I've attached the following files:\n\n";
        for (const fp of paths) {
          const name = fp.split(/[/\\]/).pop() ?? fp;
          const text = await window.electronAPI.readFile(fp);
          content += `<file name="${name}">\n${text}\n</file>\n\n`;
        }
        // Add to input for the user to review before sending
        this.input.value = this.input.value
          ? this.input.value + "\n\n" + content
          : content;
        this.input.dispatchEvent(new Event("input"));
        this.input.focus();
      }
    }
  }

  private handleFiles(files: FileList | File[]): void {
    const filenames = Array.from(files)
      .map((f) => f.name)
      .join(", ");
    if (this.input.value) {
      this.input.value += "\n";
    }
    this.input.value += `[Attached: ${filenames}]`;
  }
}
