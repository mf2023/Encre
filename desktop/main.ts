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

import { app, BrowserWindow, ipcMain, shell, dialog, Tray, nativeImage, nativeTheme, session } from "electron";
import { ChildProcess, spawn, execSync } from "child_process";
import * as path from "path";
import * as fs from "fs";
import * as crypto from "crypto";

let serverProcess: ChildProcess | null = null;
let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let isQuitting = false;
const WS_PORT = 7110;
const DATA_DIR = getDataDir();
const childWindows = new Set<BrowserWindow>();
const PID_FILE = path.join(DATA_DIR, "yimd.pid");
const GIT_STATUS_CACHE = new Map<string, { ts: number; result: any }>();
const GIT_DIFF_CACHE = new Map<string, { ts: number; result: any }>();
const GIT_CACHE_TTL_MS = 5000;
const GIT_RUNNING_DIFFS = new Map<string, ChildProcess>();

/* ── Encrypted browser cookie store ──────────────────────────────────── */

const BROWSER_KEY_FILE = path.join(DATA_DIR, "browser_key");
const BROWSER_COOKIE_FILE = path.join(DATA_DIR, "browser_cookies.enc");

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

function encryptCookies(json: string): Buffer {
  const key = getBrowserEncryptionKey();
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv("aes-256-gcm", key, iv);
  const encrypted = Buffer.concat([cipher.update(json, "utf-8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  // Format: iv(16) + tag(16) + encrypted data
  return Buffer.concat([iv, tag, encrypted]);
}

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

function saveBrowserCookies(cookieJson: string): void {
  try {
    fs.mkdirSync(DATA_DIR, { recursive: true });
    const encrypted = encryptCookies(cookieJson);
    fs.writeFileSync(BROWSER_COOKIE_FILE, encrypted);
  } catch (e) {
    console.error("[browser] failed to save cookies:", e);
  }
}

function loadBrowserCookies(): string | null {
  try {
    if (!fs.existsSync(BROWSER_COOKIE_FILE)) return null;
    const data = fs.readFileSync(BROWSER_COOKIE_FILE);
    return decryptCookies(data);
  } catch {
    return null;
  }
}

function setupBrowserSession(): void {
  const bs = session.fromPartition("encre-browser");

  // In-memory cache of the latest cookie JSON — used for synchronous save on quit
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

  // Synchronous save on quit — Electron does NOT await async event handlers
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

/* ── Terminal sessions ──────────────────────────────────────────────────── */

interface PtySession {
  pty: any;
  terminalId: number;
}
const terminals = new Map<number, PtySession>();
let terminalSeq = 0;
let _nodePty: any = null;

function getNodePty(): any {
  if (!_nodePty) {
    try { _nodePty = require("node-pty"); } catch { return null; }
  }
  return _nodePty;
}

function getDataDir(): string {
  const home = process.env.HOME || process.env.USERPROFILE || ".";
  return path.join(home, ".dunimd", "encre");
}

/* ── Service management helpers ─────────────────────────────────────────── */

function readPidFile(): number | null {
  try {
    if (fs.existsSync(PID_FILE)) {
      const pid = parseInt(fs.readFileSync(PID_FILE, "utf-8").trim(), 10);
      return isNaN(pid) ? null : pid;
    }
  } catch { /* ignore */ }
  return null;
}

function isProcessRunning(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

function killServiceByPid(pid: number): void {
  try {
    if (process.platform === "win32") {
      // /F = force, /T = tree kill (children too)
      execSync(`taskkill /PID ${pid} /F /T`, { stdio: "ignore" });
    } else {
      // Kill the full process group — -pid means "process group id"
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

    // Do NOT unref — the before-quit handler needs the reference to kill
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

async function restartService(): Promise<void> {
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
  // Clean up PID file
  try { fs.unlinkSync(PID_FILE); } catch {}
  // Wait briefly for port to be released
  await new Promise((r) => setTimeout(r, 1500));
  // Start again
  try {
    await startPythonServer();
    updateTrayStatus(true);
  } catch (err) {
    console.error("Failed to restart service:", err);
    updateTrayStatus(false);
  }
}

let currentTrayLocale = "en";
let currentTrayTheme = "dark";
let currentTrayMode = "normal";
let traySessionsCache: any[] = [];
let traySessionsBothCache: { normal: any[]; iwork: any[] } = { normal: [], iwork: [] };
let trayPopup: BrowserWindow | null = null;

const TRAY_LABELS: Record<string, { openYim: string; quit: string; tooltip: string }> = {
  en: { openYim: "Open Encre", quit: "Quit", tooltip: "Encre Server" },
  zh: { openYim: "打开 Encre", quit: "退出", tooltip: "Encre Server" },
};

function updateTrayStatus(running: boolean): void {
  if (!tray) return;
  const labels = TRAY_LABELS[currentTrayLocale] || TRAY_LABELS.en;
  tray.setToolTip(labels.tooltip);
}

function resolveTrayTheme(themePreference: string): string {
  if (themePreference === "light" || themePreference === "dark") return themePreference;
  return nativeTheme.shouldUseDarkColors ? "dark" : "light";
}

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

function closeTrayPopup(): void {
  if (trayPopup && !trayPopup.isDestroyed()) {
    trayPopup.close();
    trayPopup = null;
  }
}

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

function getTrayLabels(): { openYim: string; quit: string; tooltip: string } {
  return TRAY_LABELS[currentTrayLocale] || TRAY_LABELS.en;
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function truncate(str: string, max: number): string {
  return str.length > max ? str.slice(0, max - 1) + "…" : str;
}

function createTray(): void {
  // Create a 16x16 tray icon — green briefcase (work icon), regenerated by gen_icon.js
  const iconDataUrl =
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAI0lEQVR4nGNgoDZQOhr3HxsmyQBixIi2mWiXjBowasAINwAAHBA4uJJpecIAAAAASUVORK5CYII=";
  const icon = nativeImage.createFromDataURL(iconDataUrl);
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

/* ── Window creation ───────────────────────────────────────────────────── */

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

// ── IPC handlers ──────────────────────────────────────────────────────────

ipcMain.handle("getServerPort", () => {
  return WS_PORT;
});

ipcMain.handle("pickFiles", async () => {
  if (!mainWindow) return [];
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openFile", "multiSelections"],
  });
  return result.canceled ? [] : result.filePaths;
});

ipcMain.handle("pickDirectory", async () => {
  if (!mainWindow) return null;
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ["openDirectory"],
  });
  return result.canceled ? null : result.filePaths[0] || null;
});

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

ipcMain.handle("getAppPath", () => {
  return getDataDir();
});

// ── Crypto keyfile access ────────────────────────────────────────────────

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

ipcMain.handle("readMachineId", () => {
  try {
    const mid = fs.readFileSync("/etc/machine-id", "utf-8").trim();
    if (mid && mid !== "uninitialized") return mid;
  } catch {
    /* fall through */
  }
  return require("os").hostname();
});

// ── Service IPC ──────────────────────────────────────────────────────────

ipcMain.handle("getServiceStatus", () => {
  const pid = readPidFile();
  let running = false;
  if (pid !== null && isProcessRunning(pid)) {
    running = true;
  }
  return { running, pid, port: WS_PORT };
});

ipcMain.handle("restartService", async () => {
  await restartService();
  return { success: true };
});

// ── Logs & Diagnostics IPC ──────────────────────────────────────────────────

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

// ── Auto-start IPC ──────────────────────────────────────────────────────

const AUTOSTART_FILE = path.join(DATA_DIR, "autostart.json");

function readAutoStartFile(): boolean {
  try {
    if (fs.existsSync(AUTOSTART_FILE)) {
      const data = JSON.parse(fs.readFileSync(AUTOSTART_FILE, "utf-8"));
      return data.openAtLogin === true;
    }
  } catch { /* ignore */ }
  return false;
}

function writeAutoStartFile(enabled: boolean): void {
  try {
    fs.mkdirSync(DATA_DIR, { recursive: true });
    fs.writeFileSync(AUTOSTART_FILE, JSON.stringify({ openAtLogin: enabled }), "utf-8");
  } catch (err) {
    console.error("Failed to write autostart.json:", err);
  }
}

ipcMain.handle("getAutoStart", () => {
  const fileSetting = readAutoStartFile();
  const loginItemSettings = app.getLoginItemSettings();
  if (fileSetting && !loginItemSettings.openAtLogin) {
    app.setLoginItemSettings({ openAtLogin: true });
  }
  return fileSetting;
});

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

// ── Tray popup IPC ──────────────────────────────────────────────────────────

ipcMain.on("tray-locale", (_event, locale: string) => {
  currentTrayLocale = locale;
  const labels = getTrayLabels();
  if (tray) tray.setToolTip(labels.tooltip);
  updateTrayStatus(true);
  sendTrayDataToPopup();
});

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

ipcMain.on("tray-sessions-update", (_event, sessions: any[]) => {
  traySessionsCache = sessions;
  sendTrayDataToPopup();
});

ipcMain.on("tray-sessions-both", (_event, payload: { normal: any[]; iwork: any[] }) => {
  traySessionsBothCache = {
    normal: payload.normal || [],
    iwork: payload.iwork || [],
  };
  sendTrayDataToPopup();
});

ipcMain.on("tray-mode", (_event, mode: string) => {
  currentTrayMode = mode === "iwork" ? "iwork" : "normal";
  sendTrayDataToPopup();
});

// Keep tray theme in sync when OS-level dark mode changes
nativeTheme.on("updated", () => {
  // We don't know the preference here ("system"/explicit), so read from
  // localStorage of the main window if possible — otherwise just resolve
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

// ── Terminal IPC ──────────────────────────────────────────────────────────

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

ipcMain.handle("terminal:write", (_event, id: number, data: string) => {
  const t = terminals.get(id);
  if (t) t.pty.write(data);
});

ipcMain.handle("terminal:resize", (_event, id: number, cols: number, rows: number) => {
  const t = terminals.get(id);
  if (t && cols > 0 && rows > 0) t.pty.resize(cols, rows);
});

ipcMain.handle("terminal:kill", (_event, id: number) => {
  const t = terminals.get(id);
  if (t) { t.pty.kill(); terminals.delete(id); }
});

// ── Files IPC ─────────────────────────────────────────────────────────────

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

ipcMain.handle("readDirectory", async (_event, dirPath: string) => {
  try {
    const stats = fs.statSync(dirPath);
    if (!stats.isDirectory()) return null;
    return { path: dirPath, name: path.basename(dirPath) };
  } catch {
    return null;
  }
});

ipcMain.handle("getDrives", async () => {
  if (process.platform === "win32") {
    try {
      const out = execSync("wmic logicaldisk get name", { encoding: "utf-8" });
      return out.split("\n").map((s: string) => s.trim()).filter((s: string) => /^[A-Z]:$/.test(s));
    } catch { return ["C:"]; }
  }
  return ["/"];
});

// ── Git IPC ───────────────────────────────────────────────────────────────

ipcMain.handle("gitStatus", async (_event, repoPath: string) => {
  const now = Date.now();
  const cached = GIT_STATUS_CACHE.get(repoPath);
  if (cached && now - cached.ts < GIT_CACHE_TTL_MS) {
    return cached.result;
  }
  return new Promise((resolve) => {
    const git = spawn("git", ["status", "--short", "--branch", "--untracked-files=normal"], { cwd: repoPath, windowsHide: process.platform === "win32" });
    let out = "";
    let err = "";
    let done = false;
    const MAX_STATUS_BYTES = 256 * 1024;
    const finish = () => { if (!done) { done = true; resolve({ error: "git status timed out" }); } };
    const t = setTimeout(() => { git.kill(); finish(); }, 15000);
    git.stdout.on("data", (d: Buffer) => {
      if (done) return;
      out += d.toString();
      if (Buffer.byteLength(out, "utf-8") > MAX_STATUS_BYTES) {
        out = out.slice(0, MAX_STATUS_BYTES) + "\n... [status truncated]\n";
        git.kill();
      }
    });
    git.stderr.on("data", (d: Buffer) => { err += d.toString(); });
    git.on("error", (e) => { clearTimeout(t); if (!done) { done = true; resolve({ error: e.message }); } });
    git.on("close", (code) => {
      clearTimeout(t);
      if (done) return;
      done = true;
      const result = code !== 0 ? { error: err || "git status failed" } : { output: out };
      GIT_STATUS_CACHE.set(repoPath, { ts: Date.now(), result });
      resolve(result);
    });
  });
});

ipcMain.handle("gitDiff", async (_event, repoPath: string, filePath?: string) => {
  const cacheKey = `${repoPath}::${filePath || "__summary__"}`;
  const now = Date.now();
  const cached = GIT_DIFF_CACHE.get(cacheKey);
  if (cached && now - cached.ts < GIT_CACHE_TTL_MS) {
    return cached.result;
  }
  return new Promise((resolve) => {
    const existing = GIT_RUNNING_DIFFS.get(cacheKey);
    if (existing) {
      try { existing.kill(); } catch {}
      GIT_RUNNING_DIFFS.delete(cacheKey);
    }
    const args = filePath
      ? ["diff", "--", filePath]
      : ["diff", "--stat=200,160,40"];
    const git = spawn("git", args, { cwd: repoPath, windowsHide: process.platform === "win32" });
    GIT_RUNNING_DIFFS.set(cacheKey, git);
    let out = "";
    let err = "";
    let done = false;
    const MAX_DIFF_BYTES = filePath ? 512 * 1024 : 128 * 1024;
    const finish = () => { if (!done) { done = true; resolve({ error: "git diff timed out" }); } };
    const t = setTimeout(() => { git.kill(); finish(); }, 30000);
    git.stdout.on("data", (d: Buffer) => {
      if (done) return;
      out += d.toString();
      if (Buffer.byteLength(out, "utf-8") > MAX_DIFF_BYTES) {
        out = out.slice(0, MAX_DIFF_BYTES) + "\n... [diff truncated]\n";
        git.kill();
      }
    });
    git.stderr.on("data", (d: Buffer) => { err += d.toString(); });
    git.on("error", (e) => { clearTimeout(t); if (!done) { done = true; resolve({ error: e.message }); } });
    git.on("close", (code) => {
      clearTimeout(t);
      if (done) return;
      done = true;
      GIT_RUNNING_DIFFS.delete(cacheKey);
      const result = code !== 0 && !out ? { error: err || "git diff failed" } : { output: out };
      GIT_DIFF_CACHE.set(cacheKey, { ts: Date.now(), result });
      resolve(result);
    });
  });
});

// Window controls
ipcMain.handle("window-minimize", (event) => {
  BrowserWindow.fromWebContents(event.sender)?.minimize();
});

ipcMain.handle("window-maximize", (event) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  if (win?.isMaximized()) {
    win.unmaximize();
  } else {
    win?.maximize();
  }
});

ipcMain.handle("window-close", (event) => {
  BrowserWindow.fromWebContents(event.sender)?.close();
});

ipcMain.handle("window-is-maximized", (event) => {
  return BrowserWindow.fromWebContents(event.sender)?.isMaximized() ?? false;
});

ipcMain.handle("toggle-devtools", (event) => {
  BrowserWindow.fromWebContents(event.sender)?.webContents.toggleDevTools();
});

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
      titleBarStyle: "hidden",
      backgroundColor: "#0f0f0f",
      title: "ESD",
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
ipcMain.on("forward-to-child", (_event, channel: string, ...args: any[]) => {
  for (const child of childWindows) {
    if (!child.isDestroyed()) {
      child.webContents.send(channel, ...args);
    }
  }
});

// ── App lifecycle ─────────────────────────────────────────────────────────

async function healthCheck(): Promise<boolean> {
  try {
    const response = await fetch(`http://localhost:${WS_PORT}/health`);
    return response.ok;
  } catch {
    return false;
  }
}

app.whenReady().then(async () => {
  // Redirect Electron user data to our cache directory
  app.setPath("userData", path.join(DATA_DIR, ".electron"));

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
      // PID is stale/zombie — kill it and restart fresh
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

app.on("window-all-closed", () => {
  // Do NOT quit — service continues running in background.
  // The system tray keeps the app alive on Windows/Linux.
  // On macOS, window hiding is the default behavior.
  if (process.platform === "darwin") {
    // macOS: standard behavior — app stays alive without windows
  } else {
    // Windows/Linux: window reference cleared, tray keeps app alive
    mainWindow = null;
  }
});

app.on("activate", () => {
  if (mainWindow === null) {
    createWindow();
  } else {
    mainWindow.show();
  }
});

app.on("before-quit", () => {
  console.log("[app] before-quit — cleaning up all child processes");
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
process.on("exit", () => {
  try { execSync(`taskkill /F /IM python.exe 2>nul`, { stdio: "ignore" }); } catch {}
  try { execSync(`taskkill /F /IM "Encre.exe" /FI "PID ne ${process.pid}" 2>nul`, { stdio: "ignore" }); } catch {}
});
