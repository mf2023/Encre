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

const esbuild = require("esbuild");
const path = require("path");
const fs = require("fs");

const desktop = __dirname;

// Main process
esbuild.buildSync({
  entryPoints: [path.join(desktop, "main.ts")],
  bundle: true,
  platform: "node",
  target: "node20",
  outfile: path.join(desktop, "dist", "main.js"),
  external: ["electron", "node-pty"],
});

// Preload
esbuild.buildSync({
  entryPoints: [path.join(desktop, "preload.ts")],
  bundle: true,
  platform: "node",
  target: "node20",
  outfile: path.join(desktop, "dist", "preload.js"),
  external: ["electron"],
});

// Renderer
esbuild.buildSync({
  entryPoints: [path.join(desktop, "renderer", "src", "app.ts")],
  bundle: true,
  platform: "browser",
  target: "es2022",
  outfile: path.join(desktop, "renderer", "bundle.js"),
  jsx: "automatic",
  jsxImportSource: "react",
});

// Copy Monaco Editor files
const monacoSrc = path.join(desktop, "node_modules", "monaco-editor", "min", "vs");
const monacoDst = path.join(desktop, "renderer", "vs");
if (fs.existsSync(monacoSrc)) {
  copyRecursive(monacoSrc, monacoDst);
  console.log("Monaco Editor files copied.");
}

// Copy xterm CSS
const xtermCssSrc = path.join(desktop, "node_modules", "@xterm", "xterm", "css", "xterm.css");
const xtermCssDst = path.join(desktop, "renderer", "xterm.css");
if (fs.existsSync(xtermCssSrc)) {
  fs.copyFileSync(xtermCssSrc, xtermCssDst);
  console.log("xterm.css copied.");
}

function copyRecursive(src, dst) {
  fs.mkdirSync(dst, { recursive: true });
  const entries = fs.readdirSync(src, { withFileTypes: true });
  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const dstPath = path.join(dst, entry.name);
    if (entry.isDirectory()) {
      copyRecursive(srcPath, dstPath);
    } else {
      fs.copyFileSync(srcPath, dstPath);
    }
  }
}

// Generate tray icon
require("./gen_icon.js");

console.log("Build complete.");
