interface ElectronAPI {
  getServerPort(): Promise<number>;
  pickFiles(): Promise<string[]>;
  readFile(filePath: string): Promise<string>;
  readKeyfile(): Promise<ArrayBuffer>;
  readMachineId(): Promise<string>;
  getAppPath(): Promise<string>;
  windowMinimize(): Promise<void>;
  windowMaximize(): Promise<void>;
  windowClose(): Promise<void>;
  windowIsMaximized(): Promise<boolean>;
  toggleDevTools(): Promise<void>;
}

interface Window {
  electronAPI?: ElectronAPI;
}
