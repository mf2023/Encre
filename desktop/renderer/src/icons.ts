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
 * Platform brand icon helper.
 *
 * Every platform icon lives as a static, official brand-colored SVG file
 * under `assets/platforms/<adapter-id>.svg`. Icons are matched by filename
 * only — no SVG markup is hardcoded here. This helper simply renders an
 * `<img>` element pointing at the corresponding folder file.
 */

export const PLATFORM_ICON_BASE = "assets/platforms";

export const SEARCH_ENGINE_ICON_BASE = "assets/search-engines";

/** Absolute URL of the icon file for the given adapter id. */
export function platformIconSrc(id: string): string {
  return `${PLATFORM_ICON_BASE}/${id}.svg`;
}

/** Absolute URL of the icon file for the given search-engine id (e.g. "bing"). */
export function searchEngineIconSrc(id: string): string {
  return `${SEARCH_ENGINE_ICON_BASE}/${id}.svg`;
}

/**
 * Build an `<img>` tag pointing at an arbitrary static icon file.
 *
 * @param src        icon file URL (folder-based, matched by filename)
 * @param size       rendered width/height in px
 * @param extraClass extra CSS class(es) appended to the element
 * @param extraStyle extra inline CSS appended to the style attribute
 */
export function assetIconHtml(src: string, size = 22, extraClass = "", extraStyle = ""): string {
  const cls = extraClass ? ` class="adapter-platform-icon ${extraClass}"` : ` class="adapter-platform-icon"`;
  const style = `flex-shrink:0;object-fit:contain;user-select:none;-webkit-user-drag:none${extraStyle ? ";" + extraStyle : ""}`;
  return `<img src="${src}" alt="" width="${size}" height="${size}" draggable="false"${cls} style="${style}" />`;
}

/**
 * Build an `<img>` tag pointing at the platform icon file for an adapter id
 * (e.g. "telegram" → assets/platforms/telegram.svg).
 *
 * @param id         adapter id (must match the icon filename, e.g. `qqbot`)
 * @param size       rendered width/height in px
 * @param extraClass extra CSS class(es) appended to the element
 * @param extraStyle extra inline CSS appended to the style attribute
 */
export function platformIconHtml(id: string, size = 22, extraClass = "", extraStyle = ""): string {
  return assetIconHtml(platformIconSrc(id), size, extraClass, extraStyle);
}