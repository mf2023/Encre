/**
 * Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
 *
 * This file is part of Yim.
 * The Yim project belongs to the Dunimd Team.
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

export type ServerEvent =
  | TextDelta
  | ThinkingDelta
  | ToolCallStart
  | ToolCallDelta
  | ToolCallEnd
  | ToolProgress
  | ToolResult
  | PermissionRequest
  | FinishEvent
  | PongEvent
  | ErrorEvent
  | SessionReady
  | ConfiguredEvent
  | TelemetryEvent
  | PlanUpdate
  | ModelsList
  | SessionsList
  | ConfigData
  | ModelsUpdated
  | SkillsUpdated
  | SkillsList
  | McpUpdated
  | AgentUpdated
  | SearchResults;

export interface SearchResultEntry {
  kind: string;
  session_id?: string;
  role?: string;
  snippet: string;
  preview?: string;
  path?: string;
  line?: number;
}

export interface SearchResults {
  type: "search_results";
  results: SearchResultEntry[];
}

export interface TextDelta {
  type: "text_delta";
  text: string;
}

export interface ThinkingDelta {
  type: "thinking_delta";
  text: string;
}

export interface ToolCallStart {
  type: "tool_call_start";
  name: string;
  id: string;
}

export interface ToolCallDelta {
  type: "tool_call_delta";
  id: string;
  key: string;
  value: string;
}

export interface ToolCallEnd {
  type: "tool_call_end";
  id: string;
}

export interface ToolProgress {
  type: "tool_progress";
  id: string;
  tool_name: string;
  status: string;
}

export interface ToolResult {
  type: "tool_result";
  id: string;
  content: string;
  is_error: boolean;
}

export interface PermissionRequest {
  type: "permission_request";
  tool_name: string;
  reason: string;
}

export interface FinishEvent {
  type: "finish";
  reason: string;
  usage?: Record<string, unknown>;
}

export interface PongEvent {
  type: "pong";
}

export interface ErrorEvent {
  type: "error";
  message: string;
  code: string;
}

export interface SessionReady {
  type: "session_ready";
  session_id: string;
  messages?: Array<{ role: string; content: string | Array<{ type: string; text: string }>; tool_calls?: any[] }>;
}

export interface ConfiguredEvent {
  type: "configured";
  config: Record<string, unknown>;
}

export interface TelemetryEvent {
  type: "telemetry";
  data: TelemetryData;
}

export interface TelemetryData {
  session_duration_s: number;
  total_turns: number;
  total_tool_calls: number;
  successful_tool_calls: number;
  failed_tool_calls: number;
  avg_tool_latency_ms: number;
  avg_turn_latency_ms: number;
  total_events: number;
  compactions: number;
  tool_usage: Record<string, number>;
  total_retries: number;
  retry_by_error: Record<string, number>;
}

// ── Client → Server message types ─────────────────────────────────────────

export type ClientMessage =
  | ClientRun
  | ClientRespondPermission
  | ClientCancel
  | ClientResume
  | ClientConfigure
  | ClientPing
  | ClientListModels
  | ClientListSessions
  | ClientNewSession
  | ClientGetConfig
  | ClientUpdateModels
  | ClientSetActiveModel
  | ClientDeleteModel
  | ClientUpdateSkills
  | ClientUpdateMCP
  | ClientUpdateAgent
  | ClientSearch;

export interface ClientRun {
  type: "run";
  prompt: string;
  system_prompt?: string;
  session_id?: string;
  specialty?: string;
}

export interface ClientRespondPermission {
  type: "respond_permission";
  tool_name: string;
  decision: boolean;
}

export interface ClientCancel {
  type: "cancel";
  session_id: string;
}

export interface ClientResume {
  type: "resume";
  session_id: string;
}

export interface ClientConfigure {
  type: "configure";
  config: Record<string, unknown>;
}

export interface ClientPing {
  type: "ping";
}

export interface ClientListModels {
  type: "list_models";
}

export interface ClientListSessions {
  type: "list_sessions";
}

export interface ClientNewSession {
  type: "new_session";
}

export interface ClientGetConfig {
  type: "get_config";
}

export interface ClientUpdateModels {
  type: "update_models";
  models: ModelConfigMeta[];
  active_model_index: number;
}

export interface ClientSetActiveModel {
  type: "set_active_model";
  model_index: number;
}

export interface ClientDeleteModel {
  type: "delete_model";
  model_index: number;
}

export interface ClientUpdateSkills {
  type: "update_skills";
  enabled_skills: string[];
}

export interface ClientUpdateMCP {
  type: "update_mcp";
  mcp_servers: MCPServerConfig[];
}

export interface ClientUpdateAgent {
  type: "update_agent";
  system_prompt?: string;
  specialty?: string;
  permission_mode?: string;
  max_turns?: number;
}

export interface ClientSearch {
  type: "search";
  query: string;
}

export interface ModelConfigMeta {
  name: string;
  model_id: string;
  backend_type: string;
  api_key: string;
  base_url: string;
  max_tokens: number;
  enabled: boolean;
}

export interface MCPServerConfig {
  name: string;
  command: string;
  args: string[];
  enabled: boolean;
}

export interface SkillInfo {
  name: string;
  description: string;
  aliases: string[];
  source: string;
}

export interface ModelsList {
  type: "models_list";
  models: string[];
}

export interface SessionEntryData {
  session_id: string;
  created_at: number;
  last_active: number;
  is_running: boolean;
  preview?: string;
  message_count?: number;
}

export interface SessionsList {
  type: "sessions_list";
  sessions: SessionEntryData[];
}

export interface ConfigData {
  type: "config_data";
  config: Record<string, unknown>;
}

export interface ModelsUpdated {
  type: "models_updated";
  models: ModelConfigMeta[];
  active_model_index: number;
}

export interface SkillsUpdated {
  type: "skills_updated";
  enabled_skills: string[];
  available_skills: SkillInfo[];
}

export interface SkillsList {
  type: "skills_list";
  skills: SkillInfo[];
}

export interface McpUpdated {
  type: "mcp_updated";
  mcp_servers: MCPServerConfig[];
}

export interface AgentUpdated {
  type: "agent_updated";
  config: Record<string, unknown>;
}

// ── App State ─────────────────────────────────────────────────────────────

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  thinking?: string;
  isStreaming: boolean;
  toolCalls: ToolCallState[];
  timestamp: number;
  hasError?: boolean;
  tokenUsage?: { input_tokens: number; output_tokens: number; total_tokens: number };
}

export interface ToolCallState {
  id: string;
  name: string;
  params: Record<string, unknown>;
  result?: string;
  isError?: boolean;
  status: "pending" | "running" | "done";
}

export interface PendingPermission {
  tool_name: string;
  reason: string;
  startedAt: number;
  timeout: number;
  resolve: ((allowed: boolean) => void) | null;
}

export interface AppState {
  messages: Message[];
  sessionId: string;
  connected: boolean;
  running: boolean;
  pendingPermission: PendingPermission | null;
  settings: Record<string, unknown>;
  activeToolId: string | null;
  theme: "dark" | "light";
  themePreference: "system" | "dark" | "light";
  telemetry: TelemetryData | null;
  tokenUsage: TokenUsage | null;
  planItems: PlanItem[];
  notifications: NotificationItem[];
  availableModels: string[];
  sessionsList: SessionEntryData[];
  modelConfigs: ModelConfigMeta[];
  activeModelIndex: number;
  skillsList: SkillInfo[];
  enabledSkills: string[];
  mcpServers: MCPServerConfig[];
  agentConfig: {
    system_prompt: string;
    specialty: string;
    permission_mode: string;
    max_turns: number;
  };
  searchResults: SearchResultEntry[];
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

// ── Plan ──────────────────────────────────────────────────────────────────

export interface PlanItem {
  id: string;
  text: string;
  status: "done" | "active" | "pending";
}

export interface PlanUpdate {
  type: "plan_update";
  plan_items: PlanItem[];
}

// ── Notification ──────────────────────────────────────────────────────────

export interface NotificationItem {
  id: string;
  type: "error" | "success" | "info" | "warning";
  title: string;
  message: string;
  timestamp: number;
  read: boolean;
}

// ── App State ─────────────────────────────────────────────────────────────

export function createEmptyState(): AppState {
  return {
    messages: [],
    sessionId: "",
    connected: false,
    running: false,
    pendingPermission: null,
    settings: {},
    activeToolId: null,
    theme: "dark",
    themePreference: "system",
    telemetry: null,
    tokenUsage: null,
    planItems: [],
    notifications: [],
    availableModels: [],
    sessionsList: [],
    modelConfigs: [],
    activeModelIndex: 0,
    skillsList: [],
    enabledSkills: [],
    mcpServers: [],
    agentConfig: {
      system_prompt: "",
      specialty: "general",
      permission_mode: "default",
      max_turns: 25,
    },
    searchResults: [],
  };
}
