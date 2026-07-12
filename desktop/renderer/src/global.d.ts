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
 * Global type ambient declarations for the renderer.
 *
 * Declares the shapes exposed on `window` by the Electron preload bridge
 * (`electronAPI`) and the `lucide` icon runtime, plus ambient interfaces used
 * across the renderer and a module shim for `markdown-it`.
 */

interface DirEntry {
  name: string;
  isDirectory: boolean;
  isFile: boolean;
}

/** Result of reading a single file through the Electron bridge. */
interface FileReadResult {
  content: string;
  mime_type: string;
  size: number;
  is_binary: boolean;
}

/** The surface of the Electron preload bridge exposed as `window.electronAPI`. */
interface ElectronAPI {
  getServerPort(): Promise<number>;
  pickFiles(): Promise<string[]>;
  pickDirectory(): Promise<string | null>;
  readFile(filePath: string): Promise<FileReadResult>;
  readDirectory(dirPath: string): Promise<{ path: string; name: string } | null>;
  writeFile(filePath: string, data: string): Promise<boolean>;
  readKeyfile(): Promise<ArrayBuffer>;
  readMachineId(): Promise<string>;
  getAppPath(): Promise<string>;
  windowMinimize(): Promise<void>;
  windowMaximize(): Promise<void>;
  windowClose(): Promise<void>;
  windowIsMaximized(): Promise<boolean>;
  toggleDevTools(): Promise<void>;
  terminalSpawn(shell?: string, shellArgs?: string[]): Promise<{ id?: number; error?: string }>;
  terminalWrite(id: number, data: string): Promise<void>;
  terminalResize(id: number, cols: number, rows: number): Promise<void>;
  terminalKill(id: number): Promise<void>;
  terminalListShells(): Promise<Array<{ name: string; path: string; args?: string[] }>>;
  onTerminalData(callback: (data: { id: number; data: string }) => void): () => void;
  onTerminalExit(callback: (data: { id: number }) => void): () => void;
  listDirectory(dirPath: string): Promise<DirEntry[]>;
  getDrives(): Promise<string[]>;
  gitStatus(repoPath: string): Promise<{ output?: string; error?: string }>;
  gitDiff(repoPath: string, filePath?: string): Promise<{ output?: string; error?: string }>;
  getServiceStatus(): Promise<{ running: boolean; pid: number | null; port: number }>;
  restartService(): Promise<{ success: boolean }>;
  getAutoStart(): Promise<boolean>;
  setAutoStart(enabled: boolean): Promise<{ success: boolean; error?: string }>;
  trayLocaleUpdate(locale: string): void;
  trayThemeUpdate(themePreference: string): void;
  trayPopupAction(action: string | null, sessionId: string | null): void;
  traySessionsUpdate(sessions: any[]): void;
  traySessionsBothUpdate(payload: { normal: any[]; iwork: any[] }): void;
  trayModeUpdate(mode: string): void;
  onTrayData(callback: (data: {
    sessions: any[];
    sessionsNormal?: any[];
    sessionsIwork?: any[];
    activeMode?: string;
    locale: string;
    theme: string;
  }) => void): () => void;
  onSwitchSession(callback: (sessionId: string) => void): () => void;
  browserClearData(): Promise<{ success: boolean; error?: string }>;
  openExternal(url: string): Promise<boolean>;
  getAppVersions(): Promise<{ desktop: string; agent: string }>;
  getLicenseContent(): Promise<string>;
  getDocumentContent(docId: string, region?: string): Promise<string>;
  openChildWindow(view: string, label: string): Promise<void>;
  onChildAddTab(callback: (view: string, label: string) => void): () => void;
  forwardToChild(channel: string, ...args: any[]): void;
  onChildEvent(channel: string, callback: (data: any) => void): () => void;
  openLogs(): Promise<void>;
  getDiagnostics(): Promise<{
    versions: { desktop: string; agent: string };
    dataDir: string;
    logFile: string;
    recentLogs: string[];
  }>;
}

/** Global `Window` augmentation exposing the Electron bridge and icon runtime. */
interface Window {
  electronAPI?: ElectronAPI;
  lucide?: any;
}

/** Ambient module shim so `import Fuse from "fuse.js"` type-checks without types. */
declare module "markdown-it" {
  const MarkdownIt: any;
  export default MarkdownIt;
}
