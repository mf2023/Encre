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
 * Slash command registry.
 *
 * Defines the built-in and user/project-defined slash commands available in the
 * composer (e.g. `/plan`, `/spec`, `/new`, `/clear`). Commands can originate
 * from three layers — bundled, custom settings, and project-level config — and
 * are merged so that later layers override earlier ones.
 */

import { t } from "./i18n.js";

/** Distinguishes persistent "mode" commands from one-shot "action" commands. */
export type SlashCommandKind = "mode" | "action";

/**
 * A slash command exposed in the composer's command palette.
 */
export interface SlashCommand {
  id: string;
  name: string;
  title: string;
  description: string;
  icon: string;
  kind: SlashCommandKind;
  prompt?: string;
  source?: string;
  /** Session modes this command is available in. Empty/undefined = all modes. */
  availability?: string[];
  /** Alternate names that also match/trigger this command. */
  aliases?: string[];
}

const BUILTIN_SLASH_COMMANDS: SlashCommand[] = [
  {
    id: "plan",
    name: "plan",
    title: t("slashCommands.planTitle"),
    description: t("slashCommands.planDesc"),
    icon: "list-checks",
    kind: "mode",
  },
  {
    id: "spec",
    name: "spec",
    title: t("slashCommands.specTitle"),
    description: t("slashCommands.specDesc"),
    icon: "list-checks",
    kind: "mode",
  },
  {
    id: "new-session",
    name: "new",
    title: t("slashCommands.newSessionTitle"),
    description: t("slashCommands.newSessionDesc"),
    icon: "plus-circle",
    kind: "action",
  },
  {
    id: "clear-session",
    name: "clear",
    title: t("slashCommands.clearSessionTitle"),
    description: t("slashCommands.clearSessionDesc"),
    icon: "rotate-ccw",
    kind: "action",
  },
  {
    id: "steer",
    name: "steer",
    title: "Steer",
    description: "Inject a mid-conversation instruction into the running agent",
    icon: "navigation",
    kind: "action",
  },
  {
    id: "init",
    name: "init",
    title: t("slashCommands.initTitle"),
    description: t("slashCommands.initDesc"),
    icon: "wand-sparkles",
    kind: "action",
    availability: ["iwork"],
  },
];

/** Active slash commands — starts with built-in, can be overridden from backend. */
export let SLASH_COMMANDS: SlashCommand[] = [...BUILTIN_SLASH_COMMANDS];

/** Incoming command shape from the backend (both custom settings and project-level). */
/**
 * Command received from the backend (both custom settings and project-level).
 */
export interface ServerSlashCommand {
  name: string;
  title: string;
  description: string;
  icon: string;
  kind?: string;
  prompt?: string;
  source?: string;
  availability?: string[];
  aliases?: string[];
}

function normalizeServerCommand(s: ServerSlashCommand): SlashCommand {
  const id = s.name;
  const kind: SlashCommandKind = s.kind === "mode" ? "mode" : "action";
  return {
    id,
    name: s.name,
    title: s.title,
    description: s.description,
    icon: s.icon || "command",
    kind,
    prompt: s.prompt,
    source: s.source || "user",
    availability: s.availability,
    aliases: Array.isArray(s.aliases) ? s.aliases.map(a => String(a).toLowerCase()) : [],
  };
}

/** Rebuild the active slash command list from builtins, custom settings commands,
 *  and project-level commands. Each source layer overrides the previous one. */
function rebuildSlashCommands(
  customCmds: ServerSlashCommand[],
  projectCmds: ServerSlashCommand[] = [],
): void {
  const merged = new Map<string, SlashCommand>();
  for (const b of BUILTIN_SLASH_COMMANDS) {
    merged.set(b.id, { ...b, source: "bundled" });
  }
  for (const s of customCmds) {
    const cmd = normalizeServerCommand(s);
    merged.set(cmd.id, cmd);
  }
  for (const s of projectCmds) {
    const cmd = normalizeServerCommand(s);
    merged.set(cmd.id, cmd);
  }
  SLASH_COMMANDS = Array.from(merged.values());
}

/** Merge user-defined custom slash commands (from settings) into the active list.
 *  Custom definitions override built-ins; project-level commands are preserved. */
/**
 * Merges user-defined custom slash commands (from settings) into the active list.
 *
 * Custom definitions override built-ins; existing project-level commands are
 * preserved during the rebuild.
 *
 * @param serverCmds - Custom commands coming from the settings backend.
 */
export function applyServerCommands(serverCmds: ServerSlashCommand[]): void {
  const project = SLASH_COMMANDS.filter((c) => c.source === "project");
  rebuildSlashCommands(serverCmds, project);
}

/** Merge project-level slash commands (from .encre/commands or .claude/commands)
 *  into the active list. Project definitions override built-ins and custom commands. */
/**
 * Merges project-level slash commands (`.encre/commands`, `.claude/commands`).
 *
 * Project definitions override built-ins and custom commands.
 *
 * @param projectCmds - Project-level commands discovered by the backend.
 */
export function applyProjectCommands(projectCmds: ServerSlashCommand[]): void {
  const custom = SLASH_COMMANDS.filter((c) => c.source !== "project" && c.source !== "bundled");
  rebuildSlashCommands(custom, projectCmds);
}

/**
 * Finds a slash command by name or id (case-insensitive, leading `/` trimmed).
 *
 * @param name - The command name or id to look up.
 * @returns The matching command, or `undefined`.
 */
export function findSlashCommand(name: string): SlashCommand | undefined {
  const normalized = name.toLowerCase().replace(/^\//, "");
  return SLASH_COMMANDS.find(
    (cmd) =>
      cmd.name === normalized ||
      cmd.id === normalized ||
      (cmd.aliases && cmd.aliases.includes(normalized)),
  );
}

/**
 * Parses a raw composer input string into a slash command plus trailing text.
 *
 * @param text - The raw input text.
 * @returns `{ command, rest, exact }` when it begins with a known command, else `null`.
 */
export function parseSlashInput(text: string): { command: SlashCommand; rest: string; exact: boolean } | null {
  const trimmed = text.trimStart();
  if (!trimmed.startsWith("/")) return null;

  const match = /^\/([^\s/]+)(?:\s+([\s\S]*))?$/.exec(trimmed);
  if (!match) return null;

  const command = findSlashCommand(match[1]);
  if (!command) return null;
  return {
    command,
    rest: match[2] || "",
    exact: trimmed === `/${command.name}`,
  };
}

function isAvailableInMode(cmd: SlashCommand, mode?: string): boolean {
  if (!mode) return true;
  if (!cmd.availability || cmd.availability.length === 0) return true;
  return cmd.availability.includes(mode);
}

/**
 * Returns slash commands whose name/title/description match the query.
 *
 * @param query - The (already `/`-stripped) search query; empty returns all.
 * @param mode  - Optional session mode to filter by (e.g. "iwork", "normal").
 */
export function matchingSlashCommands(query: string, mode?: string): SlashCommand[] {
  const normalized = query.toLowerCase().replace(/^\//, "");
  let cmds = mode ? SLASH_COMMANDS.filter((cmd) => isAvailableInMode(cmd, mode)) : SLASH_COMMANDS;
  if (!normalized) return cmds;
  return cmds.filter((cmd) =>
    cmd.name.startsWith(normalized) ||
    (cmd.aliases && cmd.aliases.some((a) => a.startsWith(normalized))) ||
    cmd.title.toLowerCase().includes(normalized) ||
    cmd.description.toLowerCase().includes(normalized)
  );
}

/** Whether a command matches the typed query by name or alias (for highlight). */
export function commandMatchesQuery(cmd: SlashCommand, query: string): boolean {
  const q = query.toLowerCase().replace(/^\//, "");
  if (!q) return true;
  const aliasMatch = cmd.aliases ? cmd.aliases.some((a) => a.startsWith(q)) : false;
  return cmd.name.toLowerCase().startsWith(q) || aliasMatch;
}