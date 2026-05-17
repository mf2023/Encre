import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("electronAPI", {
  getServerPort: (): Promise<number> => ipcRenderer.invoke("getServerPort"),

  pickFiles: (): Promise<string[]> => ipcRenderer.invoke("pickFiles"),

  readFile: (filePath: string): Promise<string> =>
    ipcRenderer.invoke("readFile", filePath),

  getAppPath: (): Promise<string> => ipcRenderer.invoke("getAppPath"),

  // Window controls
  windowMinimize: (): Promise<void> => ipcRenderer.invoke("window-minimize"),
  windowMaximize: (): Promise<void> => ipcRenderer.invoke("window-maximize"),
  windowClose: (): Promise<void> => ipcRenderer.invoke("window-close"),
  windowIsMaximized: (): Promise<boolean> =>
    ipcRenderer.invoke("window-is-maximized"),

  toggleDevTools: (): Promise<void> =>
    ipcRenderer.invoke("toggle-devtools"),
});
