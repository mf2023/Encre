import { app, BrowserWindow, ipcMain, dialog } from "electron";
import { ChildProcess, spawn } from "child_process";
import * as path from "path";
import * as fs from "fs";

let serverProcess: ChildProcess | null = null;
let mainWindow: BrowserWindow | null = null;
const WS_PORT = 7110;

function getDataDir(): string {
  const home = process.env.HOME || process.env.USERPROFILE || ".";
  return path.join(home, ".dunimd", "yim");
}

function startPythonServer(): Promise<void> {
  return new Promise((resolve, reject) => {
    const pythonCmd = process.platform === "win32" ? "python" : "python3";

    const rootDir = path.resolve(__dirname, "..", "..");
    const pythonPath =
      process.platform === "win32"
        ? `${rootDir}\\..;${process.env.PYTHONPATH || ""}`
        : `${rootDir}/..:${process.env.PYTHONPATH || ""}`;

    const portStr = String(WS_PORT);
    serverProcess = spawn(pythonCmd, ["-m", "yim.server.app", "--port", portStr], {
      cwd: rootDir,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PYTHONPATH: pythonPath, YIM_DATA_DIR: getDataDir() },
    });

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
        console.error("[yim server]", text);
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
    title: "Yim",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, "..", "renderer", "index.html"));

  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
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

ipcMain.handle("readFile", async (_event, filePath: string) => {
  try {
    return fs.readFileSync(filePath, "utf-8");
  } catch (err) {
    return "";
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
      ".yim",
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

// Window controls
ipcMain.handle("window-minimize", () => {
  mainWindow?.minimize();
});

ipcMain.handle("window-maximize", () => {
  if (mainWindow?.isMaximized()) {
    mainWindow.unmaximize();
  } else {
    mainWindow?.maximize();
  }
});

ipcMain.handle("window-close", () => {
  mainWindow?.close();
});

ipcMain.handle("window-is-maximized", () => {
  return mainWindow?.isMaximized() ?? false;
});

ipcMain.handle("toggle-devtools", () => {
  mainWindow?.webContents.toggleDevTools();
});

// ── App lifecycle ─────────────────────────────────────────────────────────

app.whenReady().then(async () => {
  try {
    await startPythonServer();
    console.log(`Server started on port ${WS_PORT}`);
  } catch (err) {
    console.error("Failed to start server:", err);
  }
  createWindow();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("activate", () => {
  if (mainWindow === null) {
    createWindow();
  }
});

app.on("before-quit", () => {
  if (serverProcess) {
    serverProcess.kill();
    serverProcess = null;
  }
});
