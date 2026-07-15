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

  constructor(el: HTMLElement, media: MediaData) {
    this.el = el;
    this.media = media;
    this.render();
  }

  private render(): void {
    if (this.media.type === "image") {
      this.renderImage();
    } else if (this.media.type === "video") {
      this.renderVideo();
    }
  }

  private renderImage(): void {
    this.el.innerHTML = `<img class="media-viewer-img" src="${esc(resolveUrl(this.media.src))}" />`;
  }

  private renderVideo(): void {
    const url = resolveUrl(this.media.src);
    this.el.innerHTML = `<video class="media-viewer-video" src="${esc(url)}" autoplay loop muted playsinline webkit-playsinline="true" x5-playsinline="true" x5-video-player-type="h5" x5-video-player-fullscreen="false"></video>`;
    this.videoEl = this.el.querySelector(".media-viewer-video");
    if (!this.videoEl) return;
    this.videoEl.volume = 1;
    this.videoEl.muted = false;
  }

  destroy(): void {
    if (this.videoEl) {
      this.videoEl.pause();
      this.videoEl.removeAttribute("src");
      this.videoEl.load();
    }
    this.el.innerHTML = "";
  }
}