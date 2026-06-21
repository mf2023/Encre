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

interface Star {
  orbitRadius: number;
  radius: number;
  orbitX: number;
  orbitY: number;
  timePassed: number;
  speed: number;
  alpha: number;
}

const MAX_STARS = 3000;
const HUE = 217;
const TRAIL_ALPHA = 0.5;

/**
 * Mount the rotating galaxy into a container element.
 * Returns a cleanup function that stops the animation.
 */
export function mountNebula(container: HTMLElement): () => void {
  const canvas = document.createElement("canvas");
  canvas.id = "galaxy-canvas";
  canvas.style.cssText = "position:absolute;inset:0;width:100%;height:100%;display:block";
  container.appendChild(canvas);

  const ctx = canvas.getContext("2d")!;
  if (!ctx) {
    container.innerHTML = "";
    return () => {};
  }

  let w = 0;
  let h = 0;
  let animId = 0;
  let mouseX = w / 2;
  let mouseY = h / 2;

  // Pre-rendered glow sprite
  const glowCanvas = document.createElement("canvas");
  const glowCtx = glowCanvas.getContext("2d")!;
  glowCanvas.width = 100;
  glowCanvas.height = 100;
  const half = glowCanvas.width / 2;
  const gradient = glowCtx.createRadialGradient(half, half, 0, half, half, half);
  gradient.addColorStop(0.025, "#ccc");
  gradient.addColorStop(0.1, "hsl(" + HUE + ", 61%, 33%)");
  gradient.addColorStop(0.25, "hsl(" + HUE + ", 64%, 6%)");
  gradient.addColorStop(1, "transparent");
  glowCtx.fillStyle = gradient;
  glowCtx.beginPath();
  glowCtx.arc(half, half, half, 0, Math.PI * 2);
  glowCtx.fill();

  const stars: Star[] = [];

  function maxOrbit(x: number, y: number): number {
    const max = Math.max(x, y);
    const diameter = Math.round(Math.sqrt(max * max + max * max));
    return diameter / 2;
  }

  function resize(): void {
    const rect = container.getBoundingClientRect();
    w = rect.width;
    h = rect.height;
    const dpr = devicePixelRatio || 1;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // Repopulate stars with new dimensions
    stars.length = 0;
    const orbitMax = maxOrbit(w, h);
    for (let i = 0; i < MAX_STARS; i++) {
      const orbitRadius = Math.floor(Math.random() * (orbitMax + 1));
      stars.push({
        orbitRadius,
        radius: Math.floor(Math.random() * (orbitRadius - 60 + 1) + 60) / 8,
        orbitX: w / 2,
        orbitY: h / 2,
        timePassed: Math.floor(Math.random() * (MAX_STARS + 1)),
        speed: Math.floor(Math.random() * (orbitRadius + 1)) / 50000,
        alpha: Math.floor(Math.random() * (10 - 2 + 1) + 2) / 10,
      });
    }
    mouseX = w / 2;
    mouseY = h / 2;
  }

  function draw(): void {
    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = TRAIL_ALPHA;
    ctx.fillStyle = "hsla(" + HUE + ", 64%, 6%, 2)";
    ctx.fillRect(0, 0, w, h);

    ctx.globalCompositeOperation = "lighter";

    for (let i = 0, len = stars.length; i < len; i++) {
      const s = stars[i];
      // Orbit around mouse position instead of center
      const x = Math.sin(s.timePassed) * s.orbitRadius + mouseX;
      const y = Math.cos(s.timePassed) * s.orbitRadius + mouseY;

      // Random twinkle
      if (Math.floor(Math.random() * 10) === 1 && s.alpha > 0) {
        s.alpha -= 0.05;
      } else if (Math.floor(Math.random() * 10) === 2 && s.alpha < 1) {
        s.alpha += 0.05;
      }

      ctx.globalAlpha = Math.max(0, Math.min(1, s.alpha));
      ctx.drawImage(glowCanvas, x - s.radius / 2, y - s.radius / 2, s.radius, s.radius);
      s.timePassed += s.speed;
    }

    animId = requestAnimationFrame(draw);
  }

  function onMouseMove(e: MouseEvent): void {
    if (w === 0 || h === 0) return;
    const rect = container.getBoundingClientRect();
    mouseX = e.clientX - rect.left;
    mouseY = e.clientY - rect.top;
    // Clamp within bounds so stars don't fly out of view
    mouseX = Math.max(0, Math.min(w, mouseX));
    mouseY = Math.max(0, Math.min(h, mouseY));
  }

  function onMouseLeave(): void {
    mouseX = w / 2;
    mouseY = h / 2;
  }

  function cleanup(): void {
    cancelAnimationFrame(animId);
    canvas.remove();
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseleave", onMouseLeave);
  }

  // Init
  resize();

  window.addEventListener("mousemove", onMouseMove);
  window.addEventListener("mouseleave", onMouseLeave);

  const ro = new ResizeObserver(() => resize());
  ro.observe(container);

  draw();

  return () => {
    ro.disconnect();
    cleanup();
  };
}