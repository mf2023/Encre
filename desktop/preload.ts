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

import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("electronAPI", {
  getServerPort: (): Promise<number> => ipcRenderer.invoke("getServerPort"),

  pickFiles: (): Promise<string[]> => ipcRenderer.invoke("pickFiles"),
  pickFolder: (): Promise<string | null> => ipcRenderer.invoke("pickFolder"),
  pickDirectory: (): Promise<string | null> => ipcRenderer.invoke("pickDirectory"),
  readFile: (filePath: string) =>
    ipcRenderer.invoke("readFile", filePath),
  readDirectory: (dirPath: string) =>
    ipcRenderer.invoke("readDirectory", dirPath),

  writeFile: (filePath: string, data: string): Promise<boolean> =>
    ipcRenderer.invoke("writeFile", filePath, data),

  getAppPath: (): Promise<string> => ipcRenderer.invoke("getAppPath"),

  // Crypto keyfile access for transport encryption
  readKeyfile: (): Promise<ArrayBuffer | null> =>
    ipcRenderer.invoke("readKeyfile"),

  readMachineId: (): Promise<string> =>
    ipcRenderer.invoke("readMachineId"),

  // Window controls
  windowMinimize: (): Promise<void> => ipcRenderer.invoke("window-minimize"),
  windowMaximize: (): Promise<void> => ipcRenderer.invoke("window-maximize"),
  windowClose: (): Promise<void> => ipcRenderer.invoke("window-close"),
  windowIsMaximized: (): Promise<boolean> =>
    ipcRenderer.invoke("window-is-maximized"),

  toggleDevTools: (): Promise<void> =>
    ipcRenderer.invoke("toggle-devtools"),

  // Terminal
  terminalSpawn: (shell?: string, shellArgs?: string[]): Promise<{ id?: number; error?: string }> =>
    ipcRenderer.invoke("terminal:spawn", shell, shellArgs),
  terminalWrite: (id: number, data: string): Promise<void> =>
    ipcRenderer.invoke("terminal:write", id, data),
  terminalResize: (id: number, cols: number, rows: number): Promise<void> =>
    ipcRenderer.invoke("terminal:resize", id, cols, rows),
  terminalKill: (id: number): Promise<void> =>
    ipcRenderer.invoke("terminal:kill", id),
  terminalListShells: (): Promise<Array<{ name: string; path: string; args?: string[] }>> =>
    ipcRenderer.invoke("terminal:listShells"),
  onTerminalData: (callback: (data: { id: number; data: string }) => void) => {
    const handler = (_event: any, data: any) => callback(data);
    ipcRenderer.on("terminal:data", handler);
    return () => { ipcRenderer.removeListener("terminal:data", handler); };
  },
  onTerminalExit: (callback: (data: { id: number }) => void) => {
    const handler = (_event: any, data: any) => callback(data);
    ipcRenderer.on("terminal:exit", handler);
    return () => { ipcRenderer.removeListener("terminal:exit", handler); };
  },

  // Files
  listDirectory: (dirPath: string): Promise<Array<{ name: string; isDirectory: boolean; isFile: boolean }>> =>
    ipcRenderer.invoke("listDirectory", dirPath),
  getDrives: (): Promise<string[]> =>
    ipcRenderer.invoke("getDrives"),

  // Git
  gitStatus: (repoPath: string): Promise<{ output?: string; error?: string }> =>
    ipcRenderer.invoke("gitStatus", repoPath),
  gitDiff: (repoPath: string, filePath?: string): Promise<{ output?: string; error?: string }> =>
    ipcRenderer.invoke("gitDiff", repoPath, filePath),

  // Service
  getServiceStatus: (): Promise<{ running: boolean; pid: number | null; port: number }> =>
    ipcRenderer.invoke("getServiceStatus"),
  restartService: (): Promise<{ success: boolean }> =>
    ipcRenderer.invoke("restartService"),

  // Auto-start
  getAutoStart: (): Promise<boolean> =>
    ipcRenderer.invoke("getAutoStart"),
  setAutoStart: (enabled: boolean): Promise<{ success: boolean; error?: string }> =>
    ipcRenderer.invoke("setAutoStart", enabled),

  // Tray
  trayLocaleUpdate: (locale: string): void => {
    ipcRenderer.send("tray-locale", locale);
  },
  trayThemeUpdate: (themePreference: string): void => {
    ipcRenderer.send("tray-theme", themePreference);
  },
  trayPopupAction: (action: string | null, sessionId: string | null): void => {
    ipcRenderer.send("tray-popup-action", { action, sessionId });
  },
  traySessionsUpdate: (sessions: any[]): void => {
    ipcRenderer.send("tray-sessions-update", sessions);
  },
  traySessionsBothUpdate: (payload: { normal: any[]; iwork: any[] }): void => {
    ipcRenderer.send("tray-sessions-both", payload);
  },
  trayModeUpdate: (mode: string): void => {
    ipcRenderer.send("tray-mode", mode);
  },
  onTrayData: (callback: (data: {
    sessions: any[];
    sessionsNormal?: any[];
    sessionsIwork?: any[];
    activeMode?: string;
    locale: string;
    theme: string;
  }) => void): (() => void) => {
    const handler = (_event: any, data: any) => callback(data);
    ipcRenderer.on("tray-data", handler);
    return () => { ipcRenderer.removeListener("tray-data", handler); };
  },
  onSwitchSession: (callback: (sessionId: string) => void): (() => void) => {
    const handler = (_event: any, sessionId: string) => callback(sessionId);
    ipcRenderer.on("switch-session", handler);
    return () => { ipcRenderer.removeListener("switch-session", handler); };
  },

  // Browser
  browserClearData: (): Promise<{ success: boolean; error?: string }> =>
    ipcRenderer.invoke("browser:clear-data"),

  // Open external URLs in system browser
  openExternal: (url: string): Promise<boolean> =>
    ipcRenderer.invoke("open-external", url),

  getAppVersions: (): Promise<{ desktop: string; agent: string }> =>
    ipcRenderer.invoke("getAppVersions"),

  getLicenseContent: (): Promise<string> =>
    ipcRenderer.invoke("getLicenseContent"),

  getDocumentContent: (docId: string, region?: string): Promise<string> =>
    ipcRenderer.invoke("getDocumentContent", docId, region),

  openChildWindow: (view: string, label: string): Promise<void> =>
    ipcRenderer.invoke("openChildWindow", view, label),

  onChildAddTab: (callback: (view: string, label: string) => void): (() => void) => {
    const handler = (_event: any, view: string, label: string) => callback(view, label);
    ipcRenderer.on("child-window:add-tab", handler);
    return () => { ipcRenderer.removeListener("child-window:add-tab", handler); };
  },

  forwardToChild: (channel: string, ...args: any[]): void => {
    ipcRenderer.send("forward-to-child", channel, ...args);
  },

  onChildEvent: (channel: string, callback: (data: any) => void): (() => void) => {
    const handler = (_event: any, data: any) => callback(data);
    ipcRenderer.on(channel, handler);
    return () => { ipcRenderer.removeListener(channel, handler); };
  },

  openLogs: (): Promise<void> =>
    ipcRenderer.invoke("openLogs"),

  getDiagnostics: (): Promise<{
    versions: { desktop: string; agent: string };
    dataDir: string;
    logFile: string;
    recentLogs: string[];
  }> => ipcRenderer.invoke("getDiagnostics"),
});
