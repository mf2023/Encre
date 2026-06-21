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

import { t } from "./i18n.js";

export type SlashCommandKind = "mode" | "action";

export interface SlashCommand {
  id: string;
  name: string;
  title: string;
  description: string;
  icon: string;
  kind: SlashCommandKind;
  prompt?: string;
  source?: string;
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
];

/** Active slash commands — starts with built-in, can be overridden from backend. */
export let SLASH_COMMANDS: SlashCommand[] = [...BUILTIN_SLASH_COMMANDS];

/** Incoming command shape from the backend (both custom settings and project-level). */
export interface ServerSlashCommand {
  name: string;
  title: string;
  description: string;
  icon: string;
  kind?: string;
  prompt?: string;
  source?: string;
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
export function applyServerCommands(serverCmds: ServerSlashCommand[]): void {
  const project = SLASH_COMMANDS.filter((c) => c.source === "project");
  rebuildSlashCommands(serverCmds, project);
}

/** Merge project-level slash commands (from .encre/commands or .claude/commands)
 *  into the active list. Project definitions override built-ins and custom commands. */
export function applyProjectCommands(projectCmds: ServerSlashCommand[]): void {
  const custom = SLASH_COMMANDS.filter((c) => c.source !== "project" && c.source !== "bundled");
  rebuildSlashCommands(custom, projectCmds);
}

export function findSlashCommand(name: string): SlashCommand | undefined {
  const normalized = name.toLowerCase().replace(/^\//, "");
  return SLASH_COMMANDS.find((cmd) => cmd.name === normalized || cmd.id === normalized);
}

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

export function matchingSlashCommands(query: string): SlashCommand[] {
  const normalized = query.toLowerCase().replace(/^\//, "");
  if (!normalized) return SLASH_COMMANDS;
  return SLASH_COMMANDS.filter((cmd) =>
    cmd.name.startsWith(normalized) ||
    cmd.title.toLowerCase().includes(normalized) ||
    cmd.description.toLowerCase().includes(normalized)
  );
}