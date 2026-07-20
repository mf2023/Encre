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

import type { SessionEntryData, WorkspaceEntry } from "./types.js";

export interface WorkspaceSessionGroup {
  workspace: WorkspaceEntry;
  sessions: SessionEntryData[];
}

export interface TraySessionData {
  normal: SessionEntryData[];
  iwork: WorkspaceSessionGroup[];
}

/** Produces one stable workspace key for all renderer-side consumers. */
export function normalizeWorkspacePath(path: string): string {
  return path.trim().replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
}

/** Keeps one newest entry per session id. */
export function dedupeSessions(sessions: readonly SessionEntryData[]): SessionEntryData[] {
  const byId = new Map<string, SessionEntryData>();

  for (const session of sessions) {
    if (!session?.session_id) continue;
    const previous = byId.get(session.session_id);
    if (!previous || (session.last_active || 0) >= (previous.last_active || 0)) {
      byId.set(session.session_id, session);
    }
  }

  return [...byId.values()];
}

/**
 * Central workspace projection used by both the sidebar and the tray.
 * Unknown workspace paths are deliberately excluded so stale sessions cannot
 * create phantom workspace rows.
 */
export function getWorkspaceSessionGroups(
  workspaces: readonly WorkspaceEntry[],
  sessions: readonly SessionEntryData[],
): WorkspaceSessionGroup[] {
  const groups: WorkspaceSessionGroup[] = [];
  const groupByPath = new Map<string, WorkspaceSessionGroup>();

  for (const workspace of workspaces) {
    if (!workspace.path || !workspace.name) continue;
    const key = normalizeWorkspacePath(workspace.path);
    if (!key || groupByPath.has(key)) continue;

    const group = { workspace, sessions: [] };
    groupByPath.set(key, group);
    groups.push(group);
  }

  for (const session of dedupeSessions(sessions)) {
    if ((session.message_count || 0) <= 0) continue;
    const metadata = session.metadata || {};
    const owner = String(metadata.workspace || metadata.workspace_path || "");
    const group = groupByPath.get(normalizeWorkspacePath(owner));
    if (group) group.sessions.push(session);
  }

  return groups;
}

export function buildTraySessionData(
  normalSessions: readonly SessionEntryData[],
  iworkSessions: readonly SessionEntryData[],
  workspaces: readonly WorkspaceEntry[],
): TraySessionData {
  return {
    normal: dedupeSessions(normalSessions).filter((session) => (session.message_count || 0) > 0),
    iwork: getWorkspaceSessionGroups(workspaces, iworkSessions),
  };
}
