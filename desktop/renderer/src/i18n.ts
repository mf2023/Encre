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

import { getState, subscribe, setSettings } from "./state.js";
import { zh } from "./locales/zh.js";
import { en } from "./locales/en.js";

export type Locale = "zh" | "en";

export interface LocaleMessages {
  [key: string]: string | LocaleMessages;
}

const translations: Record<Locale, LocaleMessages> = {
  zh: {},
  en: {},
};

let currentLocale: Locale = "zh";

type LocaleChangeCallback = (locale: Locale) => void;
const localeChangeCallbacks: Set<LocaleChangeCallback> = new Set();

export function setLocale(locale: Locale): void {
  currentLocale = locale;
  localStorage.setItem("encre-locale", locale);
  document.documentElement.setAttribute("data-locale", locale);
  clearLocaleCache();
  localeChangeCallbacks.forEach((cb) => cb(locale));
}

export function onLocaleChange(cb: LocaleChangeCallback): () => void {
  localeChangeCallbacks.add(cb);
  return () => localeChangeCallbacks.delete(cb);
}

export function getLocale(): Locale {
  return currentLocale;
}

export function initLocale(): void {
  const stored = localStorage.getItem("encre-locale") as Locale | null;
  if (stored === "en" || stored === "zh") {
    setLocale(stored);
    // Keep settings.language in sync so the settings UI shows the correct selection
    try {
      setSettings({ ...getState().settings, language: stored });
    } catch {}
    return;
  }
  try {
    const state = getState();
    const settingsLang = (state.settings.language as Locale) || "zh";
    setLocale(settingsLang === "en" || settingsLang === "zh" ? settingsLang : "zh");
  } catch {
    setLocale("zh");
  }
}

type StringGetter = () => string;

const pendingSubscribers: Set<StringGetter> = new Set();
const stringCache: Map<string, string> = new Map();

export function t(key: string, params?: Record<string, string | number>): string {
  const cacheKey = params ? `${currentLocale}:${key}:${JSON.stringify(params)}` : `${currentLocale}:${key}`;
  if (stringCache.has(cacheKey)) {
    return stringCache.get(cacheKey)!;
  }

  const keys = key.split(".");
  let value: unknown = translations[currentLocale];

  for (const k of keys) {
    if (value && typeof value === "object" && k in value) {
      value = (value as LocaleMessages)[k];
    } else {
      value = undefined;
      break;
    }
  }

  let result = typeof value === "string" ? value : key;

  if (params) {
    for (const [k, v] of Object.entries(params)) {
      result = result.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
    }
  }

  stringCache.set(cacheKey, result);
  return result;
}

export function subscribeLocale(fn: StringGetter): () => void {
  pendingSubscribers.add(fn);
  return () => pendingSubscribers.delete(fn);
}

export function clearLocaleCache(): void {
  stringCache.clear();
  pendingSubscribers.forEach((fn) => fn());
}

export function applyI18n(): void {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (key) {
      el.textContent = t(key);
    }
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (key && "placeholder" in (el as HTMLInputElement)) {
      (el as HTMLInputElement).placeholder = t(key);
    }
  });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    const key = el.getAttribute("data-i18n-title");
    if (key) {
      el.setAttribute("title", t(key));
    }
  });
}

export function loadTranslations(locale: Locale, messages: LocaleMessages): void {
  translations[locale] = messages;
  clearLocaleCache();
}

export function loadAllTranslations(zhMessages: LocaleMessages, enMessages: LocaleMessages): void {
  translations.zh = zhMessages;
  translations.en = enMessages;
  clearLocaleCache();
}

export function createLocaleGetter(key: string): StringGetter {
  return () => t(key);
}

// Load translations eagerly so all module-level t() calls find them
loadAllTranslations(zh, en);
