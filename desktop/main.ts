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
 * Encre desktop application entry point (Electron main process).
 *
 * Responsibilities of this module:
 *  - Boot a Python backend service (`encre.server.app`) as a child process and
 *    manage its lifecycle (start, restart, kill on quit, free its TCP port).
 *  - Create and manage the main BrowserWindow and auxiliary child windows.
 *  - Provide a system tray icon + popup for quick session switching.
 *  - Expose an encrypted on-disk cookie store for the in-app browser.
 *  - Register a large set of IPC handlers bridging the renderer to the OS
 *    (file system, terminal/pty, git, window controls, auto-start, docs鈥?.
 *
 * All heavy interaction with the OS happens here; the renderer only talks to
 * the main process through the `electronAPI` exposed by `preload.ts`.
 */

import { app, BrowserWindow, ipcMain, shell, dialog, Tray, nativeImage, nativeTheme, session, protocol, net } from "electron";
import { ChildProcess, spawn, execSync } from "child_process";
import * as path from "path";
import * as fs from "fs";
import * as crypto from "crypto";

// Handle to the spawned Python backend process (null when not running).
let serverProcess: ChildProcess | null = null;
// The primary application window (null when hidden/closed).
let mainWindow: BrowserWindow | null = null;
// System tray icon handle.
let tray: Tray | null = null;
// Set to true right before an explicit "Quit" so the window close handler
// does not just hide the app to the tray.
let isQuitting = false;
let winKeyCapture = false;
// WebSocket / HTTP port the Python backend listens on.
const WS_PORT = 7110;
// Root directory for all Encre user data (~/.dunimd/encre).
const DATA_DIR = getDataDir();
// Set of auxiliary "child" BrowserWindows (e.g. the ESD window).
const childWindows = new Set<BrowserWindow>();
// PID file written by the Python service; used to manage its lifecycle.
const PID_FILE = path.join(DATA_DIR, "yimd.pid");
// In-memory cache for `git status` results keyed by repository path.
const GIT_STATUS_CACHE = new Map<string, { ts: number; result: any }>();
// In-memory cache for `git diff` results keyed by "repo::file" string.
const GIT_DIFF_CACHE = new Map<string, { ts: number; result: any }>();
// Time-to-live (ms) for the git caches before a fresh command is run.
const GIT_CACHE_TTL_MS = 5000;

/* 鈹€鈹€ Encrypted browser cookie store 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ */

// On-disk path to the static AES-256 key for the cookie store.
const BROWSER_KEY_FILE = path.join(DATA_DIR, "browser_key");
// On-disk path to the encrypted cookie blob.
const BROWSER_COOKIE_FILE = path.join(DATA_DIR, "browser_cookies.enc");

/**
 * Returns the AES-256 key used to encrypt/decrypt browser cookies.
 * The key is generated once and persisted to BROWSER_KEY_FILE; subsequent
 * calls reuse the stored key so cookies survive app restarts.
 * @returns A 32-byte Buffer holding the raw encryption key.
 */
function getBrowserEncryptionKey(): Buffer {
  try {
    if (fs.existsSync(BROWSER_KEY_FILE)) {
      return fs.readFileSync(BROWSER_KEY_FILE);
    }
  } catch {}
  // Generate a new 32-byte AES-256 key
  const key = crypto.randomBytes(32);
  fs.mkdirSync(DATA_DIR, { recursive: true });
  fs.writeFileSync(BROWSER_KEY_FILE, key);
  return key;
}

/**
 * Encrypts a JSON cookie string using AES-256-GCM.
 * Output layout: [iv(16 bytes) | authTag(16 bytes) | ciphertext].
 * @param json - The serialized cookie array to encrypt.
 * @returns A Buffer containing the IV, auth tag and ciphertext.
 */
function encryptCookies(json: string): Buffer {
  const key = getBrowserEncryptionKey();
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv("aes-256-gcm", key, iv);
  const encrypted = Buffer.concat([cipher.update(json, "utf-8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  // Format: iv(16) + tag(16) + encrypted data
  return Buffer.concat([iv, tag, encrypted]);
}

/**
 * Decrypts a cookie blob produced by {@link encryptCookies}.
 * Returns null on any failure (truncated data, wrong key, tampered payload).
 * @param data - The encrypted Buffer (iv | tag | ciphertext).
 * @returns The decrypted JSON string, or null if decryption fails.
 */
function decryptCookies(data: Buffer): string | null {
  try {
    const key = getBrowserEncryptionKey();
    if (data.length < 32) return null;
    const iv = data.subarray(0, 16);
    const tag = data.subarray(16, 32);
    const encrypted = data.subarray(32);
    const decipher = crypto.createDecipheriv("aes-256-gcm", key, iv);
    decipher.setAuthTag(tag);
    return decipher.update(encrypted) + decipher.final("utf-8");
  } catch {
    return null; // Decryption failure (e.g. key changed)
  }
}

/**
 * Persists an encrypted cookie JSON blob to disk. Failures are logged but
 * swallowed so the caller is never blocked.
 * @param cookieJson - Serialized cookie array to encrypt and save.
 */
function saveBrowserCookies(cookieJson: string): void {
  try {
    fs.mkdirSync(DATA_DIR, { recursive: true });
    const encrypted = encryptCookies(cookieJson);
    fs.writeFileSync(BROWSER_COOKIE_FILE, encrypted);
  } catch (e) {
    console.error("[browser] failed to save cookies:", e);
  }
}

/**
 * Loads and decrypts the persisted cookie blob from disk.
 * @returns The decrypted JSON string, or null when no file exists or the
 *          decryption fails.
 */
function loadBrowserCookies(): string | null {
  try {
    if (!fs.existsSync(BROWSER_COOKIE_FILE)) return null;
    const data = fs.readFileSync(BROWSER_COOKIE_FILE);
    return decryptCookies(data);
  } catch {
    return null;
  }
}

/**
 * Wires up the persistent, encrypted cookie store for the in-app browser
 * session (`encre-browser` partition). Responsibilities:
 *  - Loads previously saved cookies into the session on startup.
 *  - Watches cookie changes, debouncing writes to disk (500ms).
 *  - Flushes the cache synchronously on `before-quit` (async handlers are
 *    not awaited by Electron on quit).
 *  - Restricts which permissions the in-app browser may request.
 */
function setupBrowserSession(): void {
  const bs = session.fromPartition("encre-browser");

  // In-memory cache of the latest cookie JSON 鈥?used for synchronous save on quit
  let cookieCache: string | null = null;

  // Load encrypted cookies into the session
  const raw = loadBrowserCookies();
  if (raw) {
    try {
      const cookies = JSON.parse(raw);
      if (Array.isArray(cookies)) {
        for (const c of cookies) {
          try {
            const cleanDomain = typeof c.domain === 'string' ? c.domain.replace(/^\./, '') : '';
            const url = cleanDomain
              ? `http${c.secure ? "s" : ""}://${cleanDomain}${c.path || "/"}`
              : undefined;
            if (url && c.name) {
              bs.cookies.set({
                url,
                name: c.name,
                value: c.value || "",
                domain: c.domain,
                path: c.path || "/",
                secure: !!c.secure,
                httpOnly: !!c.httpOnly,
                sameSite: c.sameSite || "unspecified",
                expirationDate: c.expirationDate,
              }).catch((e: any) => console.error("[browser] cookie set failed:", e));
            }
          } catch (e) {
            console.error("[browser] cookie load error:", e);
          }
        }
      }
    } catch (e) {
      console.error("[browser] cookie JSON parse error:", e);
    }
  }

  // On every cookie change: update the in-memory cache and debounce disk write
  let saveTimer: ReturnType<typeof setTimeout> | null = null;
  bs.cookies.on("changed", () => {
    bs.cookies.get({}).then((all) => {
      cookieCache = JSON.stringify(all);
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = setTimeout(() => {
        if (cookieCache) saveBrowserCookies(cookieCache);
      }, 500);
    }).catch((e: any) => console.error("[browser] cookie save error:", e));
  });

  // Synchronous save on quit 鈥?Electron does NOT await async event handlers
  app.on("before-quit", () => {
    if (saveTimer) clearTimeout(saveTimer);
    if (cookieCache) {
      console.log("[browser] saving cookies on quit");
      saveBrowserCookies(cookieCache);
    }
  });

  // Permission handler for the in-app browser
  bs.setPermissionRequestHandler((_wc, permission, callback) => {
    const allowed = new Set(["geolocation", "notifications", "midi", "midiSysex", "pointerLock", "fullscreen", "openExternal", "clipboard-read", "clipboard-sanitized-write", "display-capture", "media"]);
    callback(allowed.has(permission));
  });
}

// Clears the in-app browser's cookies, storage and encrypted cookie file.
ipcMain.handle("browser:clear-data", async () => {
  try {
    const bs = session.fromPartition("encre-browser");
    // Clear all cookies
    const all = await bs.cookies.get({});
    for (const c of all) {
      try {
        const cleanDomain = typeof c.domain === 'string' ? c.domain.replace(/^\./, '') : '';
        const url = cleanDomain
          ? `http${c.secure ? "s" : ""}://${cleanDomain}${c.path || "/"}`
          : undefined;
        if (url) await bs.cookies.remove(url, c.name);
      } catch {}
    }
    // Clear Chromium storage (localStorage, IndexedDB, cache, etc.)
    await bs.clearStorageData();
    // Delete encrypted cookie file
    try { fs.unlinkSync(BROWSER_COOKIE_FILE); } catch {}
    return { success: true };
  } catch (e: any) {
    return { success: false, error: e.message };
  }
});

/* 鈹€鈹€ Terminal sessions 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ */

// A single terminal/pty session tracked by the main process.
interface PtySession {
  pty: any;
  terminalId: number;
}
// Map of terminal id -> session.
const terminals = new Map<number, PtySession>();
// Monotonic counter used to assign terminal ids.
let terminalSeq = 0;
// Lazily loaded `node-pty` module (optional dependency).
let _nodePty: any = null;

/**
 * Lazily requires `node-pty`. Returns null when the native module is not
 * installed, so terminal features degrade gracefully.
 * @returns The node-pty module or null.
 */
function getNodePty(): any {
  if (!_nodePty) {
    try { _nodePty = require("node-pty"); } catch { return null; }
  }
  return _nodePty;
}

/**
 * Resolves the per-user data directory for Encre (`~/.dunimd/encre`).
 * Falls back to the current directory when no HOME/USERPROFILE is set.
 * @returns Absolute path to the Encre data directory.
 */
function getDataDir(): string {
  const home = process.env.HOME || process.env.USERPROFILE || ".";
  return path.join(home, ".dunimd", "encre");
}

/* 鈹€鈹€ Service management helpers 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ */

/**
 * Reads the PID recorded in the service PID file.
 * @returns The parsed PID, or null when the file is missing/invalid.
 */
function readPidFile(): number | null {
  try {
    if (fs.existsSync(PID_FILE)) {
      const pid = parseInt(fs.readFileSync(PID_FILE, "utf-8").trim(), 10);
      return isNaN(pid) ? null : pid;
    }
  } catch { /* ignore */ }
  return null;
}

/**
 * Tests whether a process with the given PID is currently alive using a
 * signal-less `kill(pid, 0)`.
 * @param pid - The process id to test.
 * @returns True if the process exists, false otherwise.
 */
function isProcessRunning(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

/**
 * Kills a backend process (and its children) by PID.
 * On Windows uses `taskkill /F /T` (force + tree); on POSIX sends SIGKILL to
 * the process group (negative pid).
 * @param pid - The process id (or process-group id) to kill.
 */
function killServiceByPid(pid: number): void {
  try {
    if (process.platform === "win32") {
      // /F = force, /T = tree kill (children too)
      execSync(`taskkill /PID ${pid} /F /T`, { stdio: "ignore" });
    } else {
      // Kill the full process group 鈥?-pid means "process group id"
      try { process.kill(-pid, "SIGKILL"); } catch { process.kill(pid, "SIGKILL"); }
    }
  } catch { /* process already dead */ }
}

/** Force-free a TCP port by killing whatever process holds it (entire tree). */
function killProcessOnPort(port: number): void {
  try {
    if (process.platform === "win32") {
      const out = execSync(`netstat -ano | findstr "LISTENING" | findstr ":${port} "`, { encoding: "utf-8", timeout: 3000 });
      for (const line of out.split("\n")) {
        const parts = line.trim().split(/\s+/);
        const pid = parseInt(parts[parts.length - 1], 10);
        if (!isNaN(pid) && pid > 0) {
          try { execSync(`taskkill /PID ${pid} /F /T`, { stdio: "ignore" }); } catch {}
        }
      }
    } else {
      execSync(`lsof -ti:${port} | xargs kill -9 2>/dev/null`, { stdio: "ignore" });
    }
  } catch { /* nothing on that port */ }
}

/** Kills ALL Python processes whose command line contains "encre". */
function killAllEncreProcesses(): void {
  try {
    if (process.platform === "win32") {
      execSync(
        `powershell -Command "Get-CimInstance Win32_Process -Filter \\"name='python.exe'\\" | Where-Object { $_.CommandLine -match 'encre' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"`,
        { stdio: "ignore", timeout: 5000 },
      );
    } else {
      execSync(`pkill -f "python.*encre" 2>/dev/null`, { stdio: "ignore" });
    }
  } catch { /* no remaining encre processes */ }
}

/**
 * Spawns the Python backend service (`python -m encre.server.app`) as a
 * detached child process and resolves once it logs "Server ready".
 * Rejects on timeout (30s) or early exit/error.
 * @returns A promise that resolves when the server is ready.
 */
function startPythonServer(): Promise<void> {
  return new Promise((resolve, reject) => {
    const pythonCmd = process.platform === "win32" ? "python" : "python3";

    const rootDir = path.resolve(__dirname, "..", "..");
    const pythonPath =
      process.platform === "win32"
        ? `${rootDir};${process.env.PYTHONPATH || ""}`
        : `${rootDir}:${process.env.PYTHONPATH || ""}`;

    const isWin = process.platform === "win32";
    serverProcess = spawn(pythonCmd, ["-m", "encre.server.app", "--port", String(WS_PORT), "--service", "--log-level", "DEBUG"], {
      cwd: rootDir,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONPATH: pythonPath, ENCRE_DATA_DIR: DATA_DIR },
      detached: isWin ? true : false,
      windowsHide: isWin ? true : false,
    });

    // Do NOT unref 鈥?the before-quit handler needs the reference to kill
    // this process tree on exit.
    if (isWin && serverProcess) {
      // Log the PID for debugging; Python server writes its own PID file
      console.log(`[server] spawned as PID ${serverProcess.pid}`);
    }

    let resolved = false;
    const timeout = setTimeout(() => {
      if (!resolved) {
        resolved = true;
        reject(new Error("Server start timed out after 30s"));
      }
    }, 30000);

    const onData = (chunk: Buffer, src: string) => {
      const text = chunk.toString("utf-8");
      if (!resolved) {
        const match = text.match(/Server ready: ws:\/\/[\w.-]+:(\d+)\/ws/);
        if (match) {
          resolved = true;
          clearTimeout(timeout);
          resolve();
        }
      }
      if (src === "stderr") {
        console.error("[encre server]", text);
      }
    };

    serverProcess.stdout?.on("data", (chunk: Buffer) => onData(chunk, "stdout"));
    serverProcess.stderr?.on("data", (chunk: Buffer) => onData(chunk, "stderr"));

    serverProcess.on("exit", (code) => {
      if (!resolved) {
        resolved = true;
        clearTimeout(timeout);
        reject(new Error(`Server exited with code ${code}`));
      }
    });

    serverProcess.on("error", (err) => {
      if (!resolved) {
        resolved = true;
        clearTimeout(timeout);
        reject(err);
      }
    });
  });
}

/**
 * Fully restarts the backend service: kills any existing instance (via PID
 * file and/or the tracked process), frees the port, then spawns a fresh one
 * and updates the tray status.
 */
async function restartService(event: Electron.IpcMainInvokeEvent): Promise<{ success: boolean; error?: string }> {
  const sendProgress = (progress: number) => {
    try { event.sender.send("restart-progress", { progress }); } catch {}
  };
  sendProgress(5);
  // Kill existing process via PID file (most reliable across detached processes)
  const existingPid = readPidFile();
  if (existingPid !== null && isProcessRunning(existingPid)) {
    killServiceByPid(existingPid);
  }
  // Also kill serverProcess reference if we have one
  if (serverProcess) {
    try { serverProcess.kill(); } catch {}
    serverProcess = null;
  }
  // Sweep any remaining Encre server processes
  killAllEncreProcesses();
  // Clean up PID file
  try { fs.unlinkSync(PID_FILE); } catch {}
  sendProgress(30);
  // Wait briefly for port to be released
  await new Promise((r) => setTimeout(r, 1500));
  sendProgress(60);
  // Start again
  try {
    await startPythonServer();
    updateTrayStatus(true);
    sendProgress(100);
    return { success: true };
  } catch (err) {
    console.error("Failed to restart service:", err);
    updateTrayStatus(false);
    return { success: false, error: String(err) };
  }
}

// Currently selected tray locale ("en" or "zh").
let currentTrayLocale = "en";
// Currently selected tray theme ("dark" or "light").
let currentTrayTheme = "dark";
// Currently active session mode in the tray ("normal" or "iwork").
let currentTrayMode = "normal";
// Cache of all sessions shown in the tray popup.
let traySessionsCache: any[] = [];
// Cache of normal/iwork sessions shown in the tray popup.
let traySessionsBothCache: { normal: any[]; iwork: any[] } = { normal: [], iwork: [] };
// The floating tray popup window (null when not open).
let trayPopup: BrowserWindow | null = null;

// Localized strings for the tray, keyed by locale.
const TRAY_LABELS: Record<string, { openYim: string; quit: string; tooltip: string }> = {
  en: { openYim: "Open Encre", quit: "Quit", tooltip: "Encre Server" },
  zh: { openYim: "打开 Encre", quit: "退出", tooltip: "Encre Server" },
};

/**
 * Updates the tray icon tooltip based on whether the service is running.
 * @param running - Whether the backend service is currently running.
 */
function updateTrayStatus(running: boolean): void {
  if (!tray) return;
  const labels = TRAY_LABELS[currentTrayLocale] || TRAY_LABELS.en;
  tray.setToolTip(labels.tooltip);
}

/**
 * Resolves the effective tray theme from a preference string.
 * Explicit "light"/"dark" are returned as-is; "system" (or anything else)
 * defers to the OS dark-mode setting via nativeTheme.
 * @param themePreference - "light", "dark", or "system".
 * @returns The resolved concrete theme ("light" | "dark").
 */
function resolveTrayTheme(themePreference: string): string {
  if (themePreference === "light" || themePreference === "dark") return themePreference;
  return nativeTheme.shouldUseDarkColors ? "dark" : "light";
}

/**
 * Pushes the latest cached session/theme data to the open tray popup window.
 */
function sendTrayDataToPopup(): void {
  if (trayPopup && !trayPopup.isDestroyed()) {
    trayPopup.webContents.send("tray-data", {
      sessions: traySessionsCache,
      sessionsNormal: traySessionsBothCache.normal,
      sessionsIwork: traySessionsBothCache.iwork,
      activeMode: currentTrayMode,
      locale: currentTrayLocale,
      theme: currentTrayTheme,
    });
  }
}

/**
 * Closes and destroys the tray popup window if it is open.
 */
function closeTrayPopup(): void {
  if (trayPopup && !trayPopup.isDestroyed()) {
    trayPopup.close();
    trayPopup = null;
  }
}

/**
 * Shows or hides the tray popup window. When opening, it creates a small
 * frameless window, positions it above the tray icon, and loads the popup
 * HTML. Clicking outside (blur) closes it.
 */
function toggleTrayPopup(): void {
  if (trayPopup && !trayPopup.isDestroyed()) {
    closeTrayPopup();
    return;
  }

  if (!tray) return;
  const bounds = tray.getBounds();

  trayPopup = new BrowserWindow({
    width: 280,
    height: 440,
    frame: false,
    resizable: false,
    skipTaskbar: true,
    show: false,
    backgroundColor: currentTrayTheme === "dark" ? "#1a1a1a" : "#ffffff",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (process.platform === "win32" || process.platform === "darwin") {
    trayPopup.setHasShadow(true);
  }

  trayPopup.webContents.on("did-finish-load", () => {
    sendTrayDataToPopup();
  });

  trayPopup.loadFile(path.join(__dirname, "..", "renderer", "tray-popup.html"));

  trayPopup.once("ready-to-show", () => {
    if (!trayPopup || trayPopup.isDestroyed()) return;
    const popupBounds = trayPopup.getBounds();
    let x = Math.round(bounds.x + bounds.width / 2 - popupBounds.width / 2);
    let y = Math.round(bounds.y - popupBounds.height - 8);
    if (y < 0) {
      y = Math.round(bounds.y + bounds.height + 8);
    }
    trayPopup.setPosition(x, y);
    trayPopup.show();
  });

  trayPopup.on("blur", () => closeTrayPopup());
  trayPopup.on("closed", () => { trayPopup = null; });
}

/**
 * Returns the tray label set for the current locale (falls back to English).
 * @returns The localized open/quit/tooltip labels.
 */
function getTrayLabels(): { openYim: string; quit: string; tooltip: string } {
  return TRAY_LABELS[currentTrayLocale] || TRAY_LABELS.en;
}

/**
 * HTML-escapes a string for safe insertion into the tray popup markup.
 * @param s - The raw string to escape.
 * @returns The escaped string.
 */
function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/**
 * Truncates a string to `max` characters, appending an ellipsis when cut.
 * @param str - The string to truncate.
 * @param max - Maximum length (including the ellipsis).
 * @returns The truncated string.
 */
function truncate(str: string, max: number): string {
  return str.length > max ? str.slice(0, max - 1) + "…" : str;
}

/**
 * Returns the on-disk path to the Encre application icon (ICO) asset.
 * @returns Absolute path to the renderer's Encre.ico.
 */
function resolveAppIconPath(): string {
  return path.join(__dirname, "..", "renderer", "assets", "Encre.ico");
}

/**
 * Loads the Encre application icon as a NativeImage, falling back to an
 * inline 16x16 green briefcase data URL when the asset is missing.
 * @returns A NativeImage usable for windows and the tray.
 */
function loadAppIcon(): Electron.NativeImage {
  const iconPath = resolveAppIconPath();
  try {
    if (fs.existsSync(iconPath)) {
      const img = nativeImage.createFromPath(iconPath);
      if (!img.isEmpty()) return img;
    }
  } catch { /* fall through to fallback */ }
  // 16x16 green briefcase fallback (matches legacy tray look)
  const fallbackDataUrl =
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAI0lEQVR4nGNgoDZQOhr3HxsmyQBixIi2mWiXjBowasAINwAAHBA4uJJpecIAAAAASUVORK5CYII=";
  return nativeImage.createFromDataURL(fallbackDataUrl);
}

/**
 * Creates the system tray icon and wires its click/right-click handlers.
 * Left click shows/focuses the main window; right click toggles the popup.
 */
function createTray(): void {
  // Use the Encre app icon for the tray 鈥?works on Windows (ICO) and macOS/Linux.
  const icon = loadAppIcon();
  tray = new Tray(icon);
  const labels = getTrayLabels();
  tray.setToolTip(labels.tooltip);

  updateTrayStatus(true);

  tray.on("click", () => {
    if (mainWindow === null) {
      createWindow();
    } else {
      mainWindow.show();
      mainWindow.focus();
    }
  });

  tray.on("right-click", () => {
    toggleTrayPopup();
  });
}

/* 鈹€鈹€ Window creation 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€ */

/**
 * Creates the main application BrowserWindow: a frameless, hidden-by-default
 * window that loads the renderer, locks zoom to 100%, enables the dev tools,
 * and hides to the tray on close instead of quitting.
 */
function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 800,
    minHeight: 600,
    frame: false,
    titleBarStyle: "hidden",
    titleBarOverlay: false,
    backgroundColor: "#0f0f0f",
    title: "Encre",
    icon: resolveAppIconPath(),
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      webviewTag: true,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "..", "renderer", "index.html"));
  // Force developer tools on startup for debugging
  mainWindow.webContents.openDevTools();
  // Force-reset and lock zoom to 100% to avoid accidental Ctrl+-/Ctrl+wheel shrink.
  mainWindow.webContents.setZoomFactor(1);
  mainWindow.webContents.setVisualZoomLevelLimits(1, 1).catch(() => {});
  mainWindow.webContents.on("did-finish-load", () => {
    mainWindow?.webContents.setZoomFactor(1);
  });
  mainWindow.webContents.on("before-input-event", (event, input) => {
    const key = (input.key || "").toLowerCase();
    // Block Win key when capturing shortcuts, preventing Start menu from opening
    if (winKeyCapture && key === "meta") {
      event.preventDefault();
      return;
    }
    const isZoomHotkey =
      input.control &&
      (key === "-" || key === "_" || key === "+" || key === "=" || key === "0");
    if (isZoomHotkey) {
      event.preventDefault();
      mainWindow?.webContents.setZoomFactor(1);
    }
  });

  // mainWindow.webContents.openDevTools();

  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
  });

  // Override close: hide to tray instead of destroying, unless user clicked "Quit"
  mainWindow.on("close", (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow?.hide();
    }
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// 鈹€鈹€ IPC handlers 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

// Returns the backend WebSocket port to the renderer.
ipcMain.handle("getServerPort", () => {
  return WS_PORT;
});

// Opens a multi-file picker dialog.
ipcMain.handle("pickFiles", async () => {
  if (!mainWindow) return [];
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openFile", "multiSelections"],
  });
  return result.canceled ? [] : result.filePaths;
});

// Opens a directory picker dialog.
ipcMain.handle("pickDirectory", async () => {
  if (!mainWindow) return null;
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openDirectory"],
  });
  return result.canceled ? null : result.filePaths[0] || null;
});

// Reads a file from disk, returning its UTF-8 content and byte size.
ipcMain.handle("readFile", async (_event, filePath: string) => {
  try {
    const buf = fs.readFileSync(filePath);
    return {
      content: buf.toString("utf-8"),
      size: buf.length,
      mime_type: "",
      is_binary: false,
    };
  } catch {
    return null;
  }
});

// Writes a UTF-8 file to disk, creating parent directories as needed.
ipcMain.handle("writeFile", async (_event, filePath: string, data: string) => {
  try {
    const dir = path.dirname(filePath);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(filePath, data, "utf-8");
    return true;
  } catch (err) {
    console.error("writeFile error:", err);
    return false;
  }
});

// Returns the Encre data directory path.
ipcMain.handle("getAppPath", () => {
  return getDataDir();
});

// 鈹€鈹€ Crypto keyfile access 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

// Reads the user's transport-encryption keyfile (~/.encre/keyfile).
ipcMain.handle("readKeyfile", () => {
  try {
    const keyfilePath = path.join(
      process.env.HOME || process.env.USERPROFILE || ".",
      ".encre",
      "keyfile"
    );
    if (!fs.existsSync(keyfilePath)) return null;
    const buf = fs.readFileSync(keyfilePath);
    return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
  } catch {
    return null;
  }
});

// Returns a stable machine identifier (from /etc/machine-id or hostname).
ipcMain.handle("readMachineId", () => {
  try {
    const mid = fs.readFileSync("/etc/machine-id", "utf-8").trim();
    if (mid && mid !== "uninitialized") return mid;
  } catch {
    /* fall through */
  }
  return require("os").hostname();
});

// 鈹€鈹€ Service IPC 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

// Reports whether the backend service is running (via PID file).
ipcMain.handle("getServiceStatus", () => {
  const pid = readPidFile();
  let running = false;
  if (pid !== null && isProcessRunning(pid)) {
    running = true;
  }
  return { running, pid, port: WS_PORT };
});

// Restarts the backend service on demand.
ipcMain.handle("restartService", async (event) => {
  return await restartService(event);
});

// 鈹€鈹€ Logs & Diagnostics IPC 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

// Opens the active log file (or its folder) in the system file manager.
ipcMain.handle("openLogs", async () => {
  const dataDir = getDataDir();
  if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
  }
  // Reveal the active log file in the system file manager; fall back to
  // opening the data directory root when the log file does not exist yet.
  const logFile = path.join(dataDir, "yimd.log");
  if (fs.existsSync(logFile)) {
    shell.showItemInFolder(logFile);
  } else {
    await shell.openPath(dataDir);
  }
});

// Collects app/agent versions, data dir, log path and the last 200 log lines.
ipcMain.handle("getDiagnostics", async () => {
  const pkgPath = path.join(__dirname, "..", "package.json");
  const desktopVersion = JSON.parse(fs.readFileSync(pkgPath, "utf-8")).version || "0.0.0";
  const rootDir = path.resolve(__dirname, "..", "..");
  const pyprojectPath = path.join(rootDir, "pyproject.toml");
  let agentVersion = "0.0.0";
  try {
    const pyContent = fs.readFileSync(pyprojectPath, "utf-8");
    const match = pyContent.match(/^version\s*=\s*"([^"]+)"/m);
    if (match) agentVersion = match[1];
  } catch {}
  const versions = { desktop: desktopVersion, agent: agentVersion };
  const dataDir = getDataDir();
  // The live log lives at the root of the data directory as ``yimd.log``
  // (created by ``encre.server.service``). The legacy ``logs/encre.log``
  // path is no longer used.
  const logFile = path.join(dataDir, "yimd.log");
  let recentLogs: string[] = [];
  if (fs.existsSync(logFile)) {
    try {
      const stat = fs.statSync(logFile);
      // Tail the last 200 lines efficiently without slurping the whole file
      // (the live log can exceed 50 MB on long-running installations).
      const target = 200;
      const chunkSize = 256 * 1024;
      let position = stat.size;
      let buffer = Buffer.alloc(0);
      let collected: string[] = [];
      while (position > 0 && collected.length <= target + 1) {
        const readSize = Math.min(chunkSize, position);
        position -= readSize;
        const fd = fs.openSync(logFile, "r");
        const chunk = Buffer.alloc(readSize);
        fs.readSync(fd, chunk, 0, readSize, position);
        fs.closeSync(fd);
        buffer = Buffer.concat([chunk, buffer]);
        collected = buffer.toString("utf-8").split("\n");
      }
      recentLogs = collected.slice(-target);
    } catch { /* best-effort */ }
  }
  return {
    versions,
    dataDir,
    logFile,
    recentLogs,
  };
});

// ── Structured Log Reader ────────────────────────────────────────────

interface LogEntry {
  timestamp: string;
  level: string;
  source: string;
  message: string;
}

/**
 * Reads and filters log entries from the active log file.
 * Supports date-range filtering and pagination (newest-first).
 */
ipcMain.handle("getLogs", async (_event, filters: {
  fromDate?: string;
  toDate?: string;
  offset?: number;
  limit?: number;
}) => {
  const logFile = path.join(getDataDir(), "yimd.log");
  if (!fs.existsSync(logFile)) return { entries: [], total: 0, fileExists: false, rawLines: 0 };

  const fromMs = filters.fromDate ? new Date(filters.fromDate + "T00:00:00").getTime() : 0;
  const toMs = filters.toDate ? new Date(filters.toDate + "T23:59:59").getTime() : Infinity;
  const offset = filters.offset ?? 0;
  const limit = filters.limit ?? 500;

  const logLineRe = /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d{3})?)\s*\[(\w+)\]\s*([^:]+?):\s*(.*)$/;

  try {
    const content = fs.readFileSync(logFile, "utf-8");
    const rawLines = content.replace(/\r\n/g, "\n").split("\n");
    const rawCount = rawLines.length;

    // Parse into entries (handle multi-line messages)
    const allEntries: LogEntry[] = [];
    let current: LogEntry | null = null;

    for (const line of rawLines) {
      const m = line.match(logLineRe);
      if (m) {
        if (current) allEntries.push(current);
        current = {
          timestamp: m[1].replace(",", "."),
          level: m[2],
          source: m[3].trim(),
          message: m[4],
        };
      } else if (current && line.trim()) {
        current.message += "\n" + line;
      }
    }
    if (current) allEntries.push(current);

    // If no entries were parsed but raw lines exist, use raw lines as fallback
    const entries = allEntries.length === 0 && rawCount > 0
      ? rawLines.filter(l => l.trim()).map((line, i) => ({
          timestamp: "",
          level: "",
          source: "",
          message: line,
        }))
      : allEntries;

    // Filter by date range
    const filtered = entries.filter(e => {
      if (!e.timestamp) return true;
      const ts = new Date(e.timestamp).getTime();
      return ts >= fromMs && ts <= toMs;
    });

    // Paginate (newest first)
    const reversed = filtered.reverse();
    const total = reversed.length;
    const page = reversed.slice(offset, offset + limit);

    return { entries: page, total, fileExists: true, rawLines: rawCount };
  } catch {
    return null;
  }
});

// Reads a file and returns its content as base64 with mime type (for images, etc.).
ipcMain.handle("readFileBase64", async (_event, filePath: string) => {
  try {
    const buf = fs.readFileSync(filePath);
    const ext = path.extname(filePath).toLowerCase();
    const mimeMap: Record<string, string> = {
      ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
      ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
      ".ico": "image/x-icon", ".svg": "image/svg+xml",
      ".mp4": "video/mp4", ".webm": "video/webm",
    };
    return {
      data: buf.toString("base64"),
      mime_type: mimeMap[ext] || "application/octet-stream",
    };
  } catch {
    return null;
  }
});

// Clear/truncate the active log file.
ipcMain.handle("clearLogs", async () => {
  const logFile = path.join(getDataDir(), "yimd.log");
  try {
    fs.writeFileSync(logFile, "");
    return { success: true };
  } catch {
    return { success: false };
  }
});

// 鈹€鈹€ Auto-start IPC 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

// Path to the persisted auto-start preference file.
const AUTOSTART_FILE = path.join(DATA_DIR, "autostart.json");

/**
 * Reads the persisted auto-start preference.
 * @returns True when the app should launch at login.
 */
function readAutoStartFile(): boolean {
  try {
    if (fs.existsSync(AUTOSTART_FILE)) {
      const data = JSON.parse(fs.readFileSync(AUTOSTART_FILE, "utf-8"));
      return data.openAtLogin === true;
    }
  } catch { /* ignore */ }
  return false;
}

/**
 * Persists the auto-start preference to disk.
 * @param enabled - Whether to enable launch-at-login.
 */
function writeAutoStartFile(enabled: boolean): void {
  try {
    fs.mkdirSync(DATA_DIR, { recursive: true });
    fs.writeFileSync(AUTOSTART_FILE, JSON.stringify({ openAtLogin: enabled }), "utf-8");
  } catch (err) {
    console.error("Failed to write autostart.json:", err);
  }
}

// Returns the persisted auto-start setting, coercing the OS login item if needed.
ipcMain.handle("getAutoStart", () => {
  const fileSetting = readAutoStartFile();
  const loginItemSettings = app.getLoginItemSettings();
  if (fileSetting && !loginItemSettings.openAtLogin) {
    app.setLoginItemSettings({ openAtLogin: true });
  }
  return fileSetting;
});

// Sets the auto-start (launch-at-login) preference in the OS and on disk.
ipcMain.handle("setAutoStart", async (_event, enabled: boolean) => {
  try {
    app.setLoginItemSettings({ openAtLogin: enabled });
    writeAutoStartFile(enabled);
    return { success: true };
  } catch (err: any) {
    console.error("Failed to set auto-start:", err);
    return { success: false, error: err.message };
  }
});

// 鈹€鈹€ Tray popup IPC 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

// Updates the tray locale from the renderer.
ipcMain.on("tray-locale", (_event, locale: string) => {
  currentTrayLocale = locale;
  const labels = getTrayLabels();
  if (tray) tray.setToolTip(labels.tooltip);
  updateTrayStatus(true);
  sendTrayDataToPopup();
});

// Updates the tray theme (and popup background) from the renderer.
ipcMain.on("tray-theme", (_event, themePreference: string) => {
  currentTrayTheme = resolveTrayTheme(themePreference);
  // Update existing popup background color
  if (trayPopup && !trayPopup.isDestroyed()) {
    trayPopup.setBackgroundColor(
      currentTrayTheme === "dark"
        ? "#1a1a1a"
        : "#ffffff"
    );
  }
  sendTrayDataToPopup();
});

// Handles a tray popup action: open a session (switching to it) or quit.
ipcMain.on("tray-popup-action", (_event, payload: { action?: string; sessionId?: string }) => {
  closeTrayPopup();
  const { action, sessionId } = payload;
  if (action === "open") {
    if (mainWindow === null) {
      createWindow();
    } else {
      mainWindow.show();
      mainWindow.focus();
    }
    if (sessionId && mainWindow && !mainWindow.isDestroyed()) {
      // Wait for the renderer to finish loading before sending the switch.
      // This avoids the race where switch-session arrives before the
      // renderer's IPC listeners are registered (esp. on a fresh window).
      const sendSwitch = () => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send("switch-session", sessionId);
        }
      };
      if (mainWindow.webContents.isLoading()) {
        mainWindow.webContents.once("did-finish-load", () => {
          // give the renderer a tick to register listeners + WS connect
          setTimeout(sendSwitch, 200);
        });
      } else {
        setTimeout(sendSwitch, 100);
      }
    }
  } else if (action === "quit") {
    isQuitting = true;
    app.quit();
  }
});

// Receives the full session list from the renderer for the tray popup.
ipcMain.on("tray-sessions-update", (_event, sessions: any[]) => {
  traySessionsCache = sessions;
  sendTrayDataToPopup();
});

// Receives the split normal/iwork session lists for the tray popup.
ipcMain.on("tray-sessions-both", (_event, payload: { normal: any[]; iwork: any[] }) => {
  traySessionsBothCache = {
    normal: payload.normal || [],
    iwork: payload.iwork || [],
  };
  sendTrayDataToPopup();
});

// Updates the active session mode ("normal"/"iwork") for the tray popup.
ipcMain.on("tray-mode", (_event, mode: string) => {
  currentTrayMode = mode === "iwork" ? "iwork" : "normal";
  sendTrayDataToPopup();
});

// Keep tray theme in sync when OS-level dark mode changes
nativeTheme.on("updated", () => {
  // We don't know the preference here ("system"/explicit), so read from
  // localStorage of the main window if possible 鈥?otherwise just resolve
  // with whatever currentTrayTheme already is.
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.executeJavaScript(
      `localStorage.getItem("encre-theme") || "system"`
    ).then((pref: string) => {
      const resolved = resolveTrayTheme(pref);
      if (resolved !== currentTrayTheme) {
        currentTrayTheme = resolved;
        if (trayPopup && !trayPopup.isDestroyed()) {
          trayPopup.setBackgroundColor(
            currentTrayTheme === "dark" ? "#1a1a1a" : "#ffffff"
          );
        }
        sendTrayDataToPopup();
      }
    }).catch(() => {});
  }
});

// 鈹€鈹€ Terminal IPC 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

// Spawns a new pseudo-terminal (pty) session for the in-app terminal.
ipcMain.handle("terminal:spawn", async (_event, shell?: string, shellArgs?: string[]) => {
  const pty = getNodePty();
  if (!pty) return { error: "node-pty not available" };
  try {
    const sh = shell || (
      process.platform === "win32"
        ? process.env.COMSPEC || "cmd.exe"
        : process.env.SHELL || "bash"
    );
    const args = shellArgs || [];
    const id = ++terminalSeq;
    const term = pty.spawn(sh, args, {
      name: "xterm-256color",
      cols: 80,
      rows: 24,
      cwd: process.env.HOME || process.env.USERPROFILE || ".",
      env: process.env as Record<string, string>,
    });
    terminals.set(id, { pty: term, terminalId: id });
    term.onData((data: string) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send("terminal:data", { id, data });
      }
    });
    term.onExit(() => {
      terminals.delete(id);
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send("terminal:exit", { id });
      }
    });
    return { id };
  } catch (e: any) {
    return { error: e.message || "Failed to spawn terminal" };
  }
});

// Enumerates available shells (Windows: cmd/PowerShell/Git Bash/WSL; else POSIX).
ipcMain.handle("terminal:listShells", async () => {
  const shells: Array<{ name: string; path: string; args?: string[] }> = [];
  if (process.platform === "win32") {
    const comspec = process.env.COMSPEC || "C:\\Windows\\System32\\cmd.exe";
    shells.push({ name: "Command Prompt", path: comspec });

    const psPaths = [
      "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
      "C:\\Windows\\System32\\powershell.exe",
    ];
    for (const p of psPaths) {
      try { if (fs.existsSync(p)) { shells.push({ name: "Windows PowerShell", path: p }); break; } } catch {}
    }

    for (const pwsh of ["pwsh", "pwsh.exe"]) {
      try {
        const found = execSync(`where ${pwsh} 2>nul`, { encoding: "utf-8" }).trim().split("\n")[0];
        if (found) {
          shells.push({ name: "PowerShell Core", path: found.trim() });
          break;
        }
      } catch {}
    }

    for (const bash of ["bash", "bash.exe"]) {
      try {
        const found = execSync(`where ${bash} 2>nul`, { encoding: "utf-8" }).trim().split("\n")[0];
        if (found) {
          shells.push({ name: "Git Bash", path: found.trim(), args: ["--login"] });
          break;
        }
      } catch {}
    }

    try {
      const out = execSync("wsl --list 2>nul || wsl -l 2>nul", { encoding: "utf-8" });
      if (out.trim()) {
        shells.push({ name: "WSL", path: "wsl.exe" });
      }
    } catch {}
  } else {
    try { if (fs.existsSync("/bin/bash")) shells.push({ name: "Bash", path: "/bin/bash" }); } catch {}
    try { if (fs.existsSync("/bin/zsh")) shells.push({ name: "Zsh", path: "/bin/zsh" }); } catch {}
    try { if (fs.existsSync("/bin/fish")) shells.push({ name: "Fish", path: "/bin/fish" }); } catch {}
    try { if (fs.existsSync("/bin/sh")) shells.push({ name: "sh", path: "/bin/sh" }); } catch {}
  }
  return shells;
});

// Writes input data to a running terminal session.
ipcMain.handle("terminal:write", (_event, id: number, data: string) => {
  const t = terminals.get(id);
  if (t) t.pty.write(data);
});

// Resizes a running terminal session to the given columns/rows.
ipcMain.handle("terminal:resize", (_event, id: number, cols: number, rows: number) => {
  const t = terminals.get(id);
  if (t && cols > 0 && rows > 0) t.pty.resize(cols, rows);
});

// Kills a running terminal session and removes it from the registry.
ipcMain.handle("terminal:kill", (_event, id: number) => {
  const t = terminals.get(id);
  if (t) { t.pty.kill(); terminals.delete(id); }
});

// 鈹€鈹€ Files IPC 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

// Lists directory entries (directories first, then alphabetical).
ipcMain.handle("listDirectory", async (_event, dirPath: string) => {
  try {
    const entries = fs.readdirSync(dirPath, { withFileTypes: true });
    return entries.map((d) => ({
      name: d.name,
      isDirectory: d.isDirectory(),
      isFile: d.isFile(),
    })).sort((a, b) => {
      if (a.isDirectory !== b.isDirectory) return a.isDirectory ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
  } catch {
    return [];
  }
});

// Returns metadata for a single directory path (or null if not a directory).
ipcMain.handle("readDirectory", async (_event, dirPath: string) => {
  try {
    const stats = fs.statSync(dirPath);
    if (!stats.isDirectory()) return null;
    return { path: dirPath, name: path.basename(dirPath) };
  } catch {
    return null;
  }
});

// Returns the list of available drives/roots (Windows letters, else "/").
ipcMain.handle("getDrives", async () => {
  if (process.platform === "win32") {
    try {
      const out = execSync("wmic logicaldisk get name", { encoding: "utf-8" });
      return out.split("\n").map((s: string) => s.trim()).filter((s: string) => /^[A-Z]:$/.test(s));
    } catch { return ["C:"]; }
  }
  return ["/"];
});

// 鈹€鈹€ Git IPC (proxied to Python backend) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

ipcMain.handle("gitStatus", async (_event, repoPath: string) => {
  const now = Date.now();
  const cached = GIT_STATUS_CACHE.get(repoPath);
  if (cached && now - cached.ts < GIT_CACHE_TTL_MS) {
    return cached.result;
  }
  try {
    const res = await fetch(`http://localhost:${WS_PORT}/git/status?workspace=${encodeURIComponent(repoPath)}`);
    const data: any = await res.json();
    const result = data.error ? { error: data.error } : { output: data.output || "" };
    GIT_STATUS_CACHE.set(repoPath, { ts: Date.now(), result });
    return result;
  } catch (e) {
    return { error: (e as Error).message };
  }
});

ipcMain.handle("gitDiff", async (_event, repoPath: string, filePath?: string) => {
  const cacheKey = `${repoPath}::${filePath || "__summary__"}`;
  const now = Date.now();
  const cached = GIT_DIFF_CACHE.get(cacheKey);
  if (cached && now - cached.ts < GIT_CACHE_TTL_MS) {
    return cached.result;
  }
  try {
    const params = new URLSearchParams({ workspace: repoPath, filter: "all" });
    if (filePath) params.set("file", filePath);
    const res = await fetch(`http://localhost:${WS_PORT}/git/diff?${params}`);
    const data: any = await res.json();
    const result = data.error ? { error: data.error } : { output: data.output || "" };
    GIT_DIFF_CACHE.set(cacheKey, { ts: Date.now(), result });
    return result;
  } catch (e) {
    return { error: (e as Error).message };
  }
});

ipcMain.handle("gitDiffEx", async (_event, repoPath: string, filter: string, filePath?: string) => {
  const cacheKey = `${repoPath}::${filter}::${filePath || "__summary__"}`;
  const now = Date.now();
  const cached = GIT_DIFF_CACHE.get(cacheKey);
  if (cached && now - cached.ts < GIT_CACHE_TTL_MS) {
    return cached.result;
  }
  try {
    const params = new URLSearchParams({ workspace: repoPath, filter });
    if (filePath) params.set("file", filePath);
    const res = await fetch(`http://localhost:${WS_PORT}/git/diff?${params}`);
    const data: any = await res.json();
    const result = data.error ? { error: data.error } : { output: data.output || "" };
    GIT_DIFF_CACHE.set(cacheKey, { ts: Date.now(), result });
    return result;
  } catch (e) {
    return { error: (e as Error).message };
  }
});

ipcMain.handle("gitCommit", async (_event, repoPath: string, message: string) => {
  try {
    const params = new URLSearchParams({ workspace: repoPath, message });
    const res = await fetch(`http://localhost:${WS_PORT}/git/commit?${params}`);
    const data: any = await res.json();
    return data.error ? { error: data.error } : { output: data.output || "" };
  } catch (e) {
    return { error: (e as Error).message };
  }
});

ipcMain.handle("gitPush", async (_event, repoPath: string) => {
  try {
    const params = new URLSearchParams({ workspace: repoPath });
    const res = await fetch(`http://localhost:${WS_PORT}/git/push?${params}`);
    const data: any = await res.json();
    return data.error ? { error: data.error } : { output: data.output || "" };
  } catch (e) {
    return { error: (e as Error).message };
  }
});

ipcMain.handle("gitCreatePr", async (_event, repoPath: string) => {
  try {
    const params = new URLSearchParams({ workspace: repoPath });
    const res = await fetch(`http://localhost:${WS_PORT}/git/pr?${params}`);
    const data: any = await res.json();
    return {
      error: data.error || "",
      output: data.output || "",
      compare_url: data.compare_url || "",
    };
  } catch (e) {
    return { error: (e as Error).message, output: "", compare_url: "" };
  }
});

ipcMain.handle("gitBehind", async (_event, repoPath: string) => {
  try {
    const params = new URLSearchParams({ workspace: repoPath });
    const res = await fetch(`http://localhost:${WS_PORT}/git/behind?${params}`);
    const data: any = await res.json();
    return { behind: data.behind ?? -1, error: data.error || "" };
  } catch (e) {
    return { behind: -1, error: (e as Error).message };
  }
});

ipcMain.handle("gitPull", async (_event, repoPath: string) => {
  try {
    const params = new URLSearchParams({ workspace: repoPath });
    const res = await fetch(`http://localhost:${WS_PORT}/git/pull?${params}`);
    const data: any = await res.json();
    return data.error ? { error: data.error } : { output: data.output || "" };
  } catch (e) {
    return { error: (e as Error).message };
  }
});

// Win key capture flag — set by renderer when shortcuts panel is open
ipcMain.handle("setWinKeyCapture", (_event, enabled: boolean) => {
  winKeyCapture = enabled;
});

// Window controls
// Minimizes the window that sent the request.
ipcMain.handle("window-minimize", (event) => {
  BrowserWindow.fromWebContents(event.sender)?.minimize();
});

// Toggles maximize state of the requesting window.
ipcMain.handle("window-maximize", (event) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  if (win?.isMaximized()) {
    win.unmaximize();
  } else {
    win?.maximize();
  }
});

// Closes the requesting window.
ipcMain.handle("window-close", (event) => {
  BrowserWindow.fromWebContents(event.sender)?.close();
});

// Reports whether the requesting window is currently maximized.
ipcMain.handle("window-is-maximized", (event) => {
  return BrowserWindow.fromWebContents(event.sender)?.isMaximized() ?? false;
});

// Toggles the dev tools for the requesting window.
ipcMain.handle("toggle-devtools", (event) => {
  BrowserWindow.fromWebContents(event.sender)?.webContents.toggleDevTools();
});

// Opens a folder in the OS file explorer.
ipcMain.handle("openFolder", async (_event, folderPath: string) => {
  if (typeof folderPath !== "string") return false;
  try {
    await shell.openPath(folderPath);
    return true;
  } catch {
    return false;
  }
});

// Opens an external URL in the OS browser (http/https/mailto only).
ipcMain.handle("open-external", async (_event, url: string) => {
  // Only allow http/https URLs for security
  if (typeof url !== "string") return false;
  let parsed: URL;
  try {
    parsed = new URL(url);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:" && parsed.protocol !== "mailto:") return false;
  } catch {
    return false;
  }
  try {
    await shell.openExternal(url);
    return true;
  } catch {}
  // Fallback: if shell.openExternal fails (e.g. on some Windows configs),
  // try the platform-native open command
  try {
    const { exec } = require("child_process");
    const cmd = process.platform === "win32"
      ? `start "" "${url}"`
      : process.platform === "darwin"
        ? `open "${url}"`
        : `xdg-open "${url}"`;
    exec(cmd);
    return true;
  } catch {
    return false;
  }
});

// Returns desktop (npm) and agent (pyproject) version strings.
ipcMain.handle("getAppVersions", () => {
  const rootDir = path.resolve(__dirname, "..", "..");
  const pkgPath = path.join(__dirname, "..", "package.json");
  const pyprojectPath = path.join(rootDir, "pyproject.toml");
  const desktopVersion = JSON.parse(fs.readFileSync(pkgPath, "utf-8")).version || "0.0.0";
  let agentVersion = "0.0.0";
  try {
    const pyContent = fs.readFileSync(pyprojectPath, "utf-8");
    const match = pyContent.match(/^version\s*=\s*"([^"]+)"/m);
    if (match) agentVersion = match[1];
  } catch {}
  return { desktop: desktopVersion, agent: agentVersion };
});

// Returns the license text from the repository docs.
ipcMain.handle("getLicenseContent", async () => {
  const rootDir = path.resolve(__dirname, "..", "..");
  const candidates = ["docs/LICENSE", "docs/LICENSE.txt", "docs/LICENSE.md", "LICENSE", "LICENSE.txt", "LICENSE.md"];
  for (const name of candidates) {
    const p = path.join(rootDir, name);
    if (fs.existsSync(p)) {
      return fs.readFileSync(p, "utf-8");
    }
  }
  return "License file not found.";
});

const DOCUMENT_FILES: Record<string, string> = {
  privacy: "docs/PRIVACY.md",
  terms: "docs/TERMS.md",
  thanks: "docs/THANKS.md",
  "data-rules": "docs/DATA_PROCESSING_RULES.md",
  minors: "docs/MINORS_PRIVACY.md",
};

// Returns the text of a policy/legal document (with optional CN region variant).
ipcMain.handle("getDocumentContent", async (_event, docId: string, region: string = "intl") => {
  const rootDir = path.resolve(__dirname, "..", "..");
  let fileName = DOCUMENT_FILES[docId];
  if (!fileName) return `Document "${docId}" not found.`;

  if (region === "cn") {
    const ext = path.extname(fileName);
    const base = fileName.slice(0, -ext.length);
    const cnFile = base + "_CN" + ext;
    if (fs.existsSync(path.join(rootDir, cnFile))) {
      fileName = cnFile;
    }
  }

  const p = path.join(rootDir, fileName);
  try {
    return fs.readFileSync(p, "utf-8");
  } catch {
    return `Document "${fileName}" not found.`;
  }
});

// Opens (or reuses and tabs into) a child window for a given view/label.
ipcMain.handle("openChildWindow", (_event, view: string, label: string) => {
  // Find existing child window, or create one
  let child: BrowserWindow | null = null;
  for (const w of childWindows) {
    if (!w.isDestroyed()) { child = w; break; }
  }
  if (!child) {
    child = new BrowserWindow({
      width: 960,
      height: 700,
      minWidth: 600,
      minHeight: 400,
      frame: false,
      backgroundColor: "#0f0f0f",
      title: "ESD",
      icon: resolveAppIconPath(),
      show: false,
      webPreferences: {
        preload: path.join(__dirname, "preload.js"),
        contextIsolation: true,
        nodeIntegration: false,
        webviewTag: true,
      },
    });
    childWindows.add(child);
    child.on("closed", () => childWindows.delete(child!));
    child.loadFile(path.join(__dirname, "..", "renderer", "index.html"), {
      query: { child: view, label },
    });
    // Force-reset and lock zoom to 100% to avoid accidental Ctrl+-/Ctrl+wheel shrink.
    child.webContents.setZoomFactor(1);
    child.webContents.setVisualZoomLevelLimits(1, 1).catch(() => {});
    child.webContents.on("did-finish-load", () => {
      child?.webContents.setZoomFactor(1);
    });
    child.webContents.on("before-input-event", (event, input) => {
      const key = (input.key || "").toLowerCase();
      const isZoomHotkey =
        input.control &&
        (key === "-" || key === "_" || key === "+" || key === "=" || key === "0");
      if (isZoomHotkey) {
        event.preventDefault();
      }
    });
    const createdChild = child;
    child.webContents.openDevTools();
    child.once("ready-to-show", () => createdChild.show());
  } else {
    child.webContents.send("child-window:add-tab", view, label);
    child.focus();
  }
});

// Forward arbitrary events from main renderer to all child windows
// (used for streaming to the ESD child window).
// Forwards an arbitrary event from the main renderer to all child windows.
ipcMain.on("forward-to-child", (_event, channel: string, ...args: any[]) => {
  for (const child of childWindows) {
    if (!child.isDestroyed()) {
      child.webContents.send(channel, ...args);
    }
  }
});

// 鈹€鈹€ App lifecycle 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

/**
 * Pings the backend `/health` endpoint to verify it is responsive.
 * @returns True when the service answers with an OK status.
 */
async function healthCheck(): Promise<boolean> {
  try {
    const response = await fetch(`http://localhost:${WS_PORT}/health`);
    return response.ok;
  } catch {
    return false;
  }
}

// Application entry: runs once Electron is ready.
app.whenReady().then(async () => {
  // Pin the AppUserModelID so Windows taskbar/notification icons attach to Encre
  // (and not the generic electron.exe icon).
  app.setAppUserModelId("com.encre.desktop");

  // Redirect Electron user data to our cache directory
  app.setPath("userData", path.join(DATA_DIR, ".electron"));

  // Register local:// protocol to serve local files (for notification media, etc.)
  protocol.handle("local", (request) => {
    const filePath = decodeURIComponent(request.url.slice("local://".length)).replace(/^\//, "");
    const resolved = path.resolve(filePath);
    try {
      fs.accessSync(resolved);
      return net.fetch("file:///" + resolved.replace(/\\/g, "/"));
    } catch {
      return new Response("Not found", { status: 404 });
    }
  });

  // Set up encrypted browser cookie store
  setupBrowserSession();
  // Force-free the port before anything else (kills orphaned processes from dead terminals)
  killProcessOnPort(WS_PORT);

  // Check if service is already running from a previous session
  const existingPid = readPidFile();
  if (existingPid !== null && isProcessRunning(existingPid)) {
    const healthy = await healthCheck();
    if (healthy) {
      console.log(`Background service already running (PID ${existingPid}), connecting`);
      updateTrayStatus(true);
    } else {
      // PID is stale/zombie 鈥?kill it and restart fresh
      console.log(`Server PID ${existingPid} is unresponsive, restarting`);
      killServiceByPid(existingPid);
      await new Promise(r => setTimeout(r, 1500));
      try {
        await startPythonServer();
      } catch (err) {
        console.error("Failed to start background service:", err);
        updateTrayStatus(false);
      }
    }
  } else {
    try {
      await startPythonServer();
      console.log(`Background service started on port ${WS_PORT}`);
    } catch (err) {
      console.error("Failed to start background service:", err);
      updateTrayStatus(false);
    }
  }

  createWindow();
  createTray();

  // Apply persisted auto-start setting on each launch
  const autoStart = readAutoStartFile();
  if (autoStart) {
    app.setLoginItemSettings({ openAtLogin: true });
  }
});

// Keep the app alive (tray) when all windows close; do not quit.
app.on("window-all-closed", () => {
  // Do NOT quit 鈥?service continues running in background.
  // The system tray keeps the app alive on Windows/Linux.
  // On macOS, window hiding is the default behavior.
  if (process.platform === "darwin") {
    // macOS: standard behavior 鈥?app stays alive without windows
  } else {
    // Windows/Linux: window reference cleared, tray keeps app alive
    mainWindow = null;
  }
});

// macOS dock re-activation: recreate/show the main window.
app.on("activate", () => {
  if (mainWindow === null) {
    createWindow();
  } else {
    mainWindow.show();
  }
});

// Tear down everything (terminals, backend, port) on quit.
app.on("before-quit", () => {
  console.log("[app] before-quit 鈥?cleaning up all child processes");
  // Kill all terminal sessions
  for (const [, t] of terminals) {
    try { t.pty.kill(); } catch {}
  }
  terminals.clear();

  // Kill Python backend via PID file (tree kill on Windows)
  const pid = readPidFile();
  if (pid !== null) {
    killServiceByPid(pid);
  }

  // Direct kill the serverProcess reference if we still hold it
  if (serverProcess) {
    if (serverProcess.pid) killServiceByPid(serverProcess.pid);
    try { serverProcess.kill(); } catch {}
    serverProcess = null;
  }

  // Extra: force-free the port (catches any orphans)
  killProcessOnPort(WS_PORT);

  // Clean up PID file
  try { fs.unlinkSync(PID_FILE); } catch {}
});

// On exit, make absolutely sure nothing is left running
// Last-resort cleanup: force-kill stray python/Encre processes on exit.
process.on("exit", () => {
  try { execSync(`taskkill /F /IM python.exe 2>nul`, { stdio: "ignore" }); } catch {}
  try { execSync(`taskkill /F /IM "Encre.exe" /FI "PID ne ${process.pid}" 2>nul`, { stdio: "ignore" }); } catch {}
});
