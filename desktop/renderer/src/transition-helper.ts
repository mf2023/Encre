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
 * View transition helper.
 *
 * Provides a single, centralized slide-in/slide-out animation used when
 * switching between primary views (chat ↔ automation, etc.). Keeps all views in
 * sync with the same easing/duration as the sidebar collapse animation.
 */

export class TransitionHelper {
  /** 默认动画时长（与侧边栏折叠动画 0.28s 同步） */
  static readonly DEFAULT_DURATION = 280;

  /**
   * 执行统一的滑出/滑入过渡。
   *
   * 执行顺序:
   *   1. setup() — 预变更（DOM 排序、class 切换等，在设置初始位置之前执行）
   *   2. 退出元素设置 transition 属性（保持当前位置）
   *   3. 进入元素移除 hidden，定位到右侧起始位置 translateX(100%)
   *   4. 强制回流
   *   5. 同时触发所有 CSS transition（退出→-100%, 进入→0）
   *   6. 动画完成后清理并 resolve
   */
  static async slide(opts: {
    exit?: HTMLElement[];
    enter?: HTMLElement[];
    setup?: () => void;
    duration?: number;
  }): Promise<void> {
    const d = opts.duration ?? TransitionHelper.DEFAULT_DURATION;
    const exitEls = opts.exit ?? [];
    const enterEls = opts.enter ?? [];

    if (exitEls.length === 0 && enterEls.length === 0) {
      opts.setup?.();
      return;
    }

    return new Promise((resolve) => {
      requestAnimationFrame(() => {
        // ── 0. 预变更：在设置初始位置之前执行（DOM 排序等） ──
        opts.setup?.();

        // ── 1. 设置初始状态 ──
        // 退出元素：设置 transition 属性（保持当前位置）
        for (const el of exitEls) {
          el.style.transition = `transform ${d}ms cubic-bezier(0.4, 0, 0.2, 1), opacity ${d}ms cubic-bezier(0.4, 0, 0.2, 1)`;
        }

        // 进入元素：移除 hidden，定位到右侧起始位置（无过渡）
        for (const el of enterEls) {
          el.classList.remove("hidden");
          el.style.transition = "none";
          el.style.transform = "translateX(100%)";
          el.style.opacity = "0";
        }

        // ── 2. 强制回流 —— 所有初始状态生效 ──
        void document.body.offsetHeight;

        // ── 3. 同时触发所有 CSS transition ──
        for (const el of exitEls) {
          el.style.transform = "translateX(-100%)";
          el.style.opacity = "0";
        }
        for (const el of enterEls) {
          el.style.transition = `transform ${d}ms cubic-bezier(0.4, 0, 0.2, 1), opacity ${d}ms cubic-bezier(0.4, 0, 0.2, 1)`;
          el.style.transform = "translateX(0)";
          el.style.opacity = "1";
        }

        // ── 4. 动画完成后清理 ──
        setTimeout(() => {
          for (const el of exitEls) {
            el.classList.add("hidden");
            el.style.transition = "";
            el.style.transform = "";
            el.style.opacity = "";
          }
          for (const el of enterEls) {
            el.style.transition = "";
            el.style.transform = "";
            el.style.opacity = "";
          }
          resolve();
        }, d + 50);
      });
    });
  }

  /** Resolves after `ms` milliseconds. */
  static wait(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
