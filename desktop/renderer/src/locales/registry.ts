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

import type { LocaleMessages } from "../features/i18n.js";
import { zh } from "./zh.js";
import { en } from "./en.js";
import { zhHant } from "./zh-Hant.js";
import { ja } from "./ja.js";
import { ko } from "./ko.js";
import { de } from "./de.js";
import { es } from "./es.js";
import { pt } from "./pt.js";
import { tr } from "./tr.js";
import { ar } from "./ar.js";
import { he } from "./he.js";

export const LOCALE_REGISTRY = {
  zh: zh,
  en: en,
  "zh-Hant": zhHant,
  ja: ja,
  ko: ko,
  de: de,
  es: es,
  pt: pt,
  tr: tr,
  ar: ar,
  he: he,
} as const satisfies Record<string, LocaleMessages>;

export const ALL_LOCALES: readonly string[] = ['zh', 'en', 'zh-Hant', 'ja', 'ko', 'de', 'es', 'pt', 'tr', 'ar', 'he'];
