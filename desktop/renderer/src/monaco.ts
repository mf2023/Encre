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

let monacoReady: Promise<typeof monaco.editor> | null = null;
let monacoEditor: typeof monaco.editor | null = null;
const editors = new Set<any>();

// True once the Monaco AMD loader script has been injected into the page.
let loaderInjected = false;

/**
 * Injects the Monaco AMD loader script (monaco/vs/loader.js) and kicks off
 * the download of the full editor bundle. Previously index.html loaded
 * editor.main synchronously at startup (~3MB of JS parsed before first
 * paint); now it only starts when the first code file is opened.
 */
function ensureMonacoLoader(): void {
  const win = window as any;
  if (loaderInjected || (win.require && typeof win.require.config === "function")) return;
  loaderInjected = true;
  const script = document.createElement("script");
  script.src = "monaco/vs/loader.js";
  script.onload = () => {
    if (win.require && typeof win.require.config === "function") {
      win.require.config({ paths: { vs: "monaco/vs" } });
      win.require(["vs/editor/editor.main"], () => {});
    }
  };
  document.head.appendChild(script);
}

export function getMonaco(): Promise<typeof monaco.editor> {
  if (monacoReady) return monacoReady;
  monacoReady = new Promise((resolve) => {
    const win = window as any;
    if (win.monaco && win.monaco.editor) {
      monacoEditor = win.monaco.editor;
      resolve(monacoEditor);
      return;
    }
    // Start loading Monaco on demand instead of blocking startup.
    ensureMonacoLoader();
    const check = () => {
      if (win.monaco && win.monaco.editor) {
        monacoEditor = win.monaco.editor;
        resolve(monacoEditor);
      } else {
        setTimeout(check, 50);
      }
    };
    check();
  });
  return monacoReady;
}

export function registerEditor(editor: any) {
  editors.add(editor);
}

export function unregisterEditor(editor: any) {
  editors.delete(editor);
}

function updateTheme() {
  const isDark = document.documentElement.getAttribute("data-theme") !== "light";
  for (const ed of editors) {
    ed.updateOptions({ theme: isDark ? "vs-dark" : "vs" });
  }
}

const observer = new MutationObserver(() => updateTheme());
observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

const langMap: Record<string, string> = {
  js: "javascript", jsx: "javascript", mjs: "javascript", cjs: "javascript",
  ts: "typescript", tsx: "typescript", mts: "typescript", cts: "typescript",
  py: "python", pyw: "python", ipynb: "python",
  rs: "rust", go: "go", mod: "go",
  java: "java", class: "java",
  c: "c", cpp: "cpp", cxx: "cpp", h: "c", hpp: "cpp", cs: "csharp",
  swift: "swift", kt: "kotlin", scala: "scala",
  php: "php", rb: "ruby", rbs: "ruby",
  dart: "dart", lua: "lua", r: "r", rmd: "r",
  html: "html", htm: "html", css: "css", scss: "scss", sass: "scss", less: "less",
  json: "json", jsonc: "json", xml: "xml", svg: "xml",
  yaml: "yaml", yml: "yaml", toml: "yaml",
  md: "markdown", mdx: "markdown", txt: "plaintext", rtf: "plaintext",
  pdf: "plaintext",
  sh: "shell", bash: "shell", zsh: "shell", fish: "shell", ps1: "powershell", bat: "bat",
  sql: "sql", sqlite: "sql", db: "sql",
  dockerfile: "dockerfile", dockerignore: "plaintext",
  env: "plaintext", editorconfig: "ini",
  gitignore: "plaintext", gitattributes: "ini",
  png: "plaintext", jpg: "plaintext", jpeg: "plaintext",
  gif: "plaintext", webp: "plaintext", ico: "plaintext",
  zip: "plaintext", tar: "plaintext", gz: "plaintext", rar: "plaintext",
  mp3: "plaintext", mp4: "plaintext", wav: "plaintext",
  csv: "plaintext", xlsx: "plaintext", xls: "plaintext",
};

export function monacoLang(ext: string): string {
  return langMap[ext] || "plaintext";
}