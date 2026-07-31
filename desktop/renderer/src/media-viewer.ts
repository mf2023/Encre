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
  controls?: boolean;
}

function esc(s: string): string {
  const el = document.createElement("span");
  el.textContent = s;
  return el.innerHTML;
}

function resolveUrl(src: string): string {
  const normalized = src.replace(/\\/g, "/");
  if (normalized.startsWith("local://") || normalized.startsWith("file://") || normalized.startsWith("http") || normalized.startsWith("data:")) {
    return normalized;
  }
  return "local:///" + normalized;
}

function dataUrlFromBase64(data: string, mimeType: string): string {
  const binaryStr = atob(data);
  const bytes = new Uint8Array(binaryStr.length);
  for (let i = 0; i < binaryStr.length; i++) bytes[i] = binaryStr.charCodeAt(i);
  const blob = new Blob([bytes], { type: mimeType });
  return URL.createObjectURL(blob);
}

const _allViewers: MediaViewer[] = [];

export function stopAllMedia(): void {
  _allViewers.forEach(v => v.destroy());
  _allViewers.length = 0;
}

export class MediaViewer {
  readonly el: HTMLElement;
  private media: MediaData;
  private imgEl: HTMLImageElement | null = null;
  private videoEl: HTMLVideoElement | null = null;
  private blobUrl: string | null = null;

  constructor(el: HTMLElement, media: MediaData) {
    this.el = el;
    this.media = media;
    _allViewers.push(this);
    this.init();
  }

  private init(): void {
    if (this.media.type === "image") {
      this.el.innerHTML = `<img class="media-viewer-img" alt="" />`;
      this.imgEl = this.el.querySelector(".media-viewer-img");
      this.loadMedia();
    } else if (this.media.type === "video") {
      const videoAttrs = this.media.controls
        ? `controls loop muted playsinline webkit-playsinline="true" x5-playsinline="true" x5-video-player-type="h5" x5-video-player-fullscreen="false"`
        : `autoplay loop muted playsinline webkit-playsinline="true" x5-playsinline="true" x5-video-player-type="h5" x5-video-player-fullscreen="false"`;
      this.el.innerHTML = `<video class="media-viewer-video" ${videoAttrs}></video>`;
      this.videoEl = this.el.querySelector(".media-viewer-video");
      this.loadMedia();
    }
  }

  private async loadMedia(): Promise<void> {
    try {
      const filePath = this.media.src.replace(/^local:\/\/\//, "").replace(/^local:\/\//, "").replace(/^file:\/\/\//, "").replace(/^file:\/\//, "");
      const result = await window.electronAPI?.readFileBase64(filePath);
      if (result) {
        this.blobUrl = dataUrlFromBase64(result.data, result.mime_type);
        if (this.imgEl) this.imgEl.src = this.blobUrl;
        if (this.videoEl) {
          this.videoEl.src = this.blobUrl;
          this.videoEl.volume = 1;
          this.videoEl.muted = false;
        }
        return;
      }
    } catch {
      // IPC unavailable — fall through to direct src
    }
    // Fallback: use resolved URL directly (browser / demo context)
    const url = resolveUrl(this.media.src);
    if (this.imgEl) this.imgEl.src = url;
    if (this.videoEl) this.videoEl.src = url;
  }

  destroy(): void {
    if (this.videoEl) {
      this.videoEl.pause();
      this.videoEl.removeAttribute("src");
      this.videoEl.load();
    }
    if (this.imgEl) this.imgEl.removeAttribute("src");
    if (this.blobUrl) {
      URL.revokeObjectURL(this.blobUrl);
      this.blobUrl = null;
    }
    this.el.innerHTML = "";
  }
}

(window as any).__stopAllMedia = stopAllMedia;