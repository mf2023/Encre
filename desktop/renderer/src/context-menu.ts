/**
 * Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * You may not use this file except in compliance with the License.
 */

/**
 * Positions and shows a context menu at (x, y) with viewport-boundary
 * awareness: flips left/above when the menu would overflow the window.
 * Call this instead of manually setting style.left/style.top.
 */
export function showContextMenu(menu: HTMLElement, x: number, y: number): void {
  menu.style.left = `${x}px`;
  menu.style.top = `${y}px`;
  menu.classList.remove("hidden");
  requestAnimationFrame(() => {
    const rect = menu.getBoundingClientRect();
    if (rect.right > window.innerWidth) {
      menu.style.left = `${Math.max(8, x - rect.width)}px`;
    }
    if (rect.bottom > window.innerHeight) {
      menu.style.top = `${Math.max(8, y - rect.height)}px`;
    }
    const r2 = menu.getBoundingClientRect();
    if (r2.left < 0) menu.style.left = "8px";
    if (r2.top < 0) menu.style.top = "8px";
  });
}
