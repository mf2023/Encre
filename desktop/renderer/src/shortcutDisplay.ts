import { getState } from "./state.js";

let _isMac: boolean | null = null;
function isMac(): boolean {
  if (_isMac === null) {
    _isMac = navigator.platform.includes("Mac") || navigator.userAgent.includes("Macintosh");
  }
  return _isMac;
}

const MOD_KEYS: Record<string, { mac: string; win: string }> = {
  ctrlcmd: { mac: "⌘", win: "Ctrl" },
  ctrl: { mac: "⌃", win: "Ctrl" },
  alt: { mac: "⌥", win: "Alt" },
  shift: { mac: "⇧", win: "Shift" },
};

function formatMod(mod: string): string {
  const m = MOD_KEYS[mod];
  if (!m) return mod.charAt(0).toUpperCase() + mod.slice(1);
  return isMac() ? m.mac : m.win;
}

const KEY_ALIASES: Record<string, string> = {
  escape: "Esc",
  backspace: "⌫",
  enter: "↵",
  up: "↑",
  down: "↓",
  left: "←",
  right: "→",
  tab: "Tab",
  space: "Space",
  "`": "`",
  ",": ",",
  ".": ".",
  ";": ";",
  "'": "'",
  "[": "[",
  "]": "]",
  "\\": "\\",
  "/": "/",
  "=": "=",
  "-": "-",
};

function formatKey(key: string): string {
  return KEY_ALIASES[key] || key.toUpperCase();
}

export function formatShortcut(pattern: string): string {
  const parts = pattern.split("+");
  const key = parts.pop() || "";
  const mods = parts.map(formatMod);
  if (isMac()) {
    return [...mods, formatKey(key)].join("");
  }
  return [...mods, formatKey(key)].join("+");
}

export function platformLabel(): "mac" | "win" {
  return isMac() ? "mac" : "win";
}

export function lookupShortcut(id: string): string | null {
  const cfg = (getState().settings.keybinds as any);
  const binds: any[] = cfg?.keybinds || [];
  const entry = binds.find((b: any) => b.id === id);
  if (!entry || !entry.keys || entry.keys.length === 0) return null;
  return formatShortcut(entry.keys[0]);
}

export function augmentTitle(existing: string, shortcut: string): string {
  if (!shortcut) return existing;
  return `${existing} (${shortcut})`;
}
