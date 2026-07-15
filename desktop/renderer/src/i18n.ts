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
 * Internationalization (i18n) subsystem.
 *
 * Provides the translation core for the renderer: a `t()` string getter with
 * `{placeholder}` interpolation and a two-tier locale fallback (current locale
 * then English), cached lookups, plus DOM binding helpers that refresh text,
 * placeholders and titles on any element carrying `data-i18n*` attributes.
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

/** Sets the active locale, persists it and notifies subscribers. */
export function setLocale(locale: Locale): void {
  currentLocale = locale;
  localStorage.setItem("encre-locale", locale);
  document.documentElement.setAttribute("data-locale", locale);
  clearLocaleCache();
  localeChangeCallbacks.forEach((cb) => cb(locale));
}

/** Registers a callback fired whenever the locale changes; returns an unsubscribe fn. */
export function onLocaleChange(cb: LocaleChangeCallback): () => void {
  localeChangeCallbacks.add(cb);
  return () => localeChangeCallbacks.delete(cb);
}

/** Returns the currently active locale. */
export function getLocale(): Locale {
  return currentLocale;
}

/** Initializes the locale from storage/settings, falling back to `"zh"`. */
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

/**
 * Translates a dotted key (e.g. `chat.send`) with optional `{param}` interpolation.
 *
 * @param key    - Dotted translation key.
 * @param params - Optional map of placeholder name → value.
 * @returns The translated string, or the key itself when no translation exists.
 */
export function t(key: string, params?: Record<string, string | number>): string {
  const cacheKey = params ? `${currentLocale}:${key}:${JSON.stringify(params)}` : `${currentLocale}:${key}`;
  if (stringCache.has(cacheKey)) {
    return stringCache.get(cacheKey)!;
  }

  const keys = key.split(".");
  const lookup = (locale: Locale): unknown => {
    let value: unknown = translations[locale];
    for (const k of keys) {
      if (value && typeof value === "object" && k in value) {
        value = (value as LocaleMessages)[k];
      } else {
        return undefined;
      }
    }
    return value;
  };

  let value = lookup(currentLocale);
  if (typeof value !== "string" && currentLocale !== "en") {
    value = lookup("en");
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

/** Registers a getter invoked whenever the locale cache is cleared. */
export function subscribeLocale(fn: StringGetter): () => void {
  pendingSubscribers.add(fn);
  return () => pendingSubscribers.delete(fn);
}

/** Clears the translation cache and re-runs all pending locale subscribers. */
export function clearLocaleCache(): void {
  stringCache.clear();
  pendingSubscribers.forEach((fn) => fn());
}

/** Applies translations to all `data-i18n*` elements in the document. */
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
      el.setAttribute("data-tooltip", t(key));
    }
  });
}

/** Replaces the translation table for a single locale and clears the cache. */
export function loadTranslations(locale: Locale, messages: LocaleMessages): void {
  translations[locale] = messages;
  clearLocaleCache();
}

/** Loads both locale tables at once and clears the cache. */
export function loadAllTranslations(zhMessages: LocaleMessages, enMessages: LocaleMessages): void {
  translations.zh = zhMessages;
  translations.en = enMessages;
  clearLocaleCache();
}

/** Creates a cached string getter bound to a fixed translation key. */
export function createLocaleGetter(key: string): StringGetter {
  return () => t(key);
}

// Load translations eagerly so all module-level t() calls find them
loadAllTranslations(zh, en);
