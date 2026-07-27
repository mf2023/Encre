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

export interface MediaData {
  type: "image" | "video";
  src: string;
}

function esc(s: string): string {
  const el = document.createElement("span");
  el.textContent = s;
  return el.innerHTML;
}

function resolveUrl(src: string): string {
  const normalized = src.replace(/\\/g, "/");
  if (normalized.startsWith("local://") || normalized.startsWith("http") || normalized.startsWith("data:")) {
    return normalized;
  }
  return "local:///" + normalized;
}

export class MediaViewer {
  readonly el: HTMLElement;
  private media: MediaData;
  private videoEl: HTMLVideoElement | null = null;
  private blobUrl: string | null = null;

  constructor(el: HTMLElement, media: MediaData) {
    this.el = el;
    this.media = media;
    this.init();
  }

  private init(): void {
    if (this.media.type === "image") {
      this.renderImage();
    } else if (this.media.type === "video") {
      this.el.innerHTML = `<video class="media-viewer-video" autoplay loop muted playsinline webkit-playsinline="true" x5-playsinline="true" x5-video-player-type="h5" x5-video-player-fullscreen="false"></video>`;
      this.videoEl = this.el.querySelector(".media-viewer-video");
      this.loadVideo();
    }
  }

  private renderImage(): void {
    this.el.innerHTML = `<img class="media-viewer-img" src="${esc(resolveUrl(this.media.src))}" />`;
  }

  private async loadVideo(): Promise<void> {
    try {
      const result = await window.electronAPI?.readFileBase64(this.media.src);
      if (!result) return;

      const binaryStr = atob(result.data);
      const bytes = new Uint8Array(binaryStr.length);
      for (let i = 0; i < binaryStr.length; i++) bytes[i] = binaryStr.charCodeAt(i);
      const blob = new Blob([bytes], { type: result.mime_type });
      this.blobUrl = URL.createObjectURL(blob);

      if (!this.videoEl) return;
      this.videoEl.src = this.blobUrl;
      this.videoEl.volume = 1;
      this.videoEl.muted = false;
    } catch {
      // IPC unavailable or read failed
    }
  }

  destroy(): void {
    if (this.videoEl) {
      this.videoEl.pause();
      this.videoEl.removeAttribute("src");
      this.videoEl.load();
    }
    if (this.blobUrl) {
      URL.revokeObjectURL(this.blobUrl);
      this.blobUrl = null;
    }
    this.el.innerHTML = "";
  }
}