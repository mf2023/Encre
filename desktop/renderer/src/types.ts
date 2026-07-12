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
 * Shared type definitions for the renderer.
 *
 * The single source of truth for every TypeScript type used across the
 * renderer: the server→client {@link ServerEvent} union, the client→server
 * {@link ClientMessage} union, the global {@link AppState}, message/tool-call
 * shapes, settings/config payloads, and all entity records (sessions,
 * workspaces, models, MCP, skills, memories, notifications, …).
 */

export type ServerEvent =
  | TextDelta
  | ThinkingDelta
  | ToolCallStart
  | ToolCallDelta
  | ToolCallEnd
  | ToolProgress
  | ToolResult
  | FinishEvent
  | PongEvent
  | ErrorEvent
  | SessionReady
  | ConfiguredEvent
  | TelemetryEvent
  | PlanUpdate
  | PlanProposal
  | PlanModeChanged
  | PlanResolved
  | ArtifactsUpdate
  | AssistantBoundaryEvent
  | CompactEvent
  | SystemMessageEvent
  | ModelsList
  | SessionsList
  | SessionsAll
  | ConfigData
  | ModelsUpdated
  | ModelsFetched
  | ModelValidated
  | ModelValidationError
  | SkillsUpdated
  | SkillsList
  | SkillInstalled
  | SkillInstallError
  | SkillUninstalled
  | McpUpdated
  | AgentUpdated
  | AgentStateEvent
  | SearchResults
  | RollbackLogEvent
  | RollbackCheckoutEvent
  | MessagesUpdated
  | SessionDeleted
  | SessionExported
  | SessionRenamed
  | SubAgentsUpdated
  | WorkspaceOpened
  | WorkspacesList
  | WorkspaceRemoved
  | WorkspaceClosed
  | MemoryList
  | MemoryDetailEvent
  | GlobalRulesList
  | ProjectRulesList
  | ProjectHooksList
  | GlobalRuleSaved
  | GlobalRuleDeleted
  | GlobalRuleContentEvent
  | ProfileMessage
  | IndexStatusEvent
  | GitignoreContentEvent
  | DocumentsListEvent
  | DocumentAddedEvent
  | DocumentUpdatedEvent
  | DocumentRemovedEvent
  | DocumentErrorEvent
  | PermissionRequest
  | EngineInstallRequestEvent
  | EngineInstallProgressEvent
  | EngineInstallResponseAck
  | BranchUpdated
  | BranchSwitched
  | BranchRolledBack
  | UsageStatsEvent
  | TranscriptionResult
  | GatewayStatusEvent
  | RunQueued
  | AdapterTestResultEvent
  | AutomationJobsList
  | AutomationJobHistory
  | AutomationJobCreated
  | AutomationJobCancelled
  | AutomationJobUpdate
  | AutomationJobToggled
  | AutomationJobUpdated
  | AutomationJobDeleted
  | AutomationStreamEvent
  | WorkflowStarted
  | WorkflowTask
  | WorkflowCompleted
  | ContextUsageEvent
  | ReferencesUpdateEvent
  | SpecUpdateEvent;

export interface RunQueued {
  type: "run_queued";
  position: number;
}

export interface WorkflowStarted {
  type: "workflow_started";
  workflow_id: string;
  goal: string;
  total_tasks: number;
  task_ids: string[];
  session_id?: string;
}

export interface WorkflowTask {
  type: "workflow_task";
  workflow_id: string;
  task_id: string;
  task_name: string;
  status: string;
  session_id?: string;
}

export interface WorkflowCompleted {
  type: "workflow_completed";
  workflow_id: string;
  goal: string;
  success: boolean;
  completed_count: number;
  failed_count: number;
  skipped_count: number;
  total_duration: number;
  session_id?: string;
}

export interface TranscriptionResult {
  type: "transcription_result";
  text: string;
}

export interface SearchResultEntry {
  kind: string;
  session_id?: string;
  role?: string;
  snippet: string;
  preview?: string;
  path?: string;
  line?: number;
  name?: string;
}

export interface SearchResults {
  type: "search_results";
  results: SearchResultEntry[];
}

/** A streaming delta of assistant text content. */
export interface TextDelta {
  type: "text_delta";
  text: string;
  session_id?: string;
}

export interface ThinkingDelta {
  type: "thinking_delta";
  text: string;
  session_id?: string;
}

export interface ToolCallStart {
  type: "tool_call_start";
  name: string;
  id: string;
  session_id?: string;
}

/** A streaming delta for an in-flight tool call (partial JSON arguments). */
export interface ToolCallDelta {
  type: "tool_call_delta";
  id: string;
  key: string;
  value: string;
  session_id?: string;
}

export interface ToolCallEnd {
  type: "tool_call_end";
  id: string;
  session_id?: string;
}

export interface ToolProgress {
  type: "tool_progress";
  id: string;
  tool_name: string;
  status: string;
  session_id?: string;
  sub_agent_messages?: Array<{ role: string; content: string | Array<{ type: string; text: string }>; tool_calls?: any[]; reasoning_content?: string; segments?: Array<{kind: string; text?: string; tool_id?: string}>; created_at?: number; mode?: string }>;
  sub_agent_session_id?: string;
}

export interface ToolResult {
  type: "tool_result";
  id: string;
  content: string;
  is_error: boolean;
  session_id?: string;
  sub_agent_messages?: Array<{ role: string; content: string | Array<{ type: string; text: string }>; tool_calls?: any[]; reasoning_content?: string; segments?: Array<{kind: string; text?: string; tool_id?: string}>; created_at?: number; mode?: string }>;
  sub_agent_session_id?: string;
}

export interface FinishEvent {
  type: "finish";
  reason: string;
  usage?: Record<string, unknown>;
  assistant_message_id?: string;
  error?: string;
  session_id?: string;
}

export interface PongEvent {
  type: "pong";
}

export interface ErrorEvent {
  type: "error";
  message: string;
  code: string;
  session_id?: string;
}

export interface SessionReady {
  type: "session_ready";
  session_id: string;
  request_id?: string;
  messages?: Array<{ role: string; content: string | Array<{ type: string; text: string }>; tool_calls?: any[]; reasoning_content?: string }>;
  plan_items?: PlanItem[];
  artifacts?: ArtifactItem[];
  references?: ReferenceItem[];
  branches?: BranchMeta[];
  active_branch_id?: string;
  is_running?: boolean;
}

export interface ConfiguredEvent {
  type: "configured";
  config: Record<string, unknown>;
}

export interface TelemetryEvent {
  type: "telemetry";
  data: TelemetryData;
  session_id?: string | null;
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

export interface UsageStatsSessionEntry {
  session_id: string;
  model: string;
  /** "active" = currently configured, "deleted" = no longer in config,
   *  "unknown" = session had no recorded model. */
  model_status?: "active" | "deleted" | "unknown";
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  turns: number;
  tool_calls: number;
  first_active: number;
}

export interface UsageStatsData {
  total_sessions: number;
  total_tokens: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tool_calls: number;
  tool_call_breakdown: Record<string, number>;
  model_breakdown: Record<string, {
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    turns: number;
  }>;
  sessions: UsageStatsSessionEntry[];
}

export interface UsageStatsEvent {
  type: "usage_stats";
  stats: UsageStatsData;
}

export interface GatewayStatusEvent {
  type: "gateway_status";
  status: GatewayStatusData;
}

export interface AdapterTestResultEvent {
  type: "adapter_test_result";
  adapter_id: string;
  success: boolean;
  message: string;
}

export interface AutomationJobsList {
  type: "automation_jobs_list";
  jobs: any[];
}

export interface AutomationJobHistory {
  type: "automation_job_history";
  history: any[];
}

export interface AutomationJobCreated {
  type: "automation_job_created";
}

export interface AutomationJobCancelled {
  type: "automation_job_cancelled";
  job_id: string;
}

export interface AutomationJobUpdate {
  type: "automation_job_update";
  history?: any[];
}

export interface AutomationJobToggled {
  type: "automation_job_toggled";
}

export interface AutomationJobUpdated {
  type: "automation_job_updated";
}

export interface AutomationJobDeleted {
  type: "automation_job_deleted";
}

export interface AutomationStreamEvent {
  type: "automation_stream_event";
  job_id: string;
  event_type: string;
  event_data: Record<string, unknown>;
}

// ── Client → Server message types ─────────────────────────────────────────

/** The client→server message union sent over the WebSocket. */
export type ClientMessage =
  | ClientRun
  | ClientCancel
  | ClientResume
  | ClientConfigure
  | ClientPing
  | ClientListModels
  | ClientListSessions
  | ClientListAllSessions
  | ClientNewSession
  | ClientGetConfig
  | ClientUpdateModels
  | ClientSetActiveModel
  | ClientDeleteModel
  | ClientFetchModels
  | ClientValidateModel
  | ClientUpdateSkills
  | ClientInstallSkill
  | ClientUninstallSkill
  | ClientUpdateSkill
  | ClientUpdateMCP
  | ClientUpdateAgent
  | ClientSearch
  | ClientRollbackLog
  | ClientRollbackCheckout
  | ClientEditMessage
  | ClientDeleteMessage
  | ClientDeleteSession
  | ClientExportSession
  | ClientRenameSession
  | ClientListWorkspaces
  | ClientOpenWorkspace
  | ClientCloseWorkspace
  | ClientRemoveWorkspace
  | ClientUpdateSubAgents
  | ClientGetMemoryList
  | ClientGetMemoryDetail
  | ClientListGlobalRules
  | ClientListProjectRules
  | ClientSaveGlobalRule
  | ClientDeleteGlobalRule
  | ClientGetGlobalRuleContent
  | ClientGetProfile
  | ClientRespondPermission
  | ClientRespondTakeover
  | ClientRespondPlan
  | ClientRespondQuestion
  | ClientSetPlanMode
  | ClientRetry
  | ClientSwitchBranch
  | ClientRollback
  | ClientReindexWorkspace
  | ClientDeleteIndex
  | ClientGetUsageStats
  | ClientTranscribeAudio
  | ClientTestAdapter
  | ClientAutomationListJobs
  | ClientAutomationGetHistory
  | ClientAutomationUpdateJob
  | ClientAutomationCreateJob
  | ClientAutomationDeleteJob
  | ClientAutomationToggleJob
  | ClientSteer;

export interface ClientSteer {
  type: "steer";
  session_id?: string;
  prompt: string;
}

export interface ClientTranscribeAudio {
  type: "transcribe_audio";
  audio_data: string;
  format?: string;
}

export interface ClientGetUsageStats {
  type: "get_usage_stats";
}

export interface ClientTestAdapter {
  type: "test_adapter";
  adapter_id: string;
  config: Record<string, unknown>;
}

export interface ClientAutomationListJobs {
  type: "automation_list_jobs";
}

export interface ClientAutomationGetHistory {
  type: "automation_get_history";
}

export interface ClientAutomationUpdateJob {
  type: "automation_update_job";
  job_id: string;
  name: string;
  prompt: string;
  cron: string;
  tag: string;
  model_index: number;
}

export interface ClientAutomationCreateJob {
  type: "automation_create_job";
  name: string;
  prompt: string;
  cron: string;
  tag: string;
  model_index: number;
}

export interface ClientAutomationDeleteJob {
  type: "automation_delete_job";
  job_id: string;
}

export interface ClientAutomationToggleJob {
  type: "automation_toggle_job";
  job_id: string;
}

export interface ClientRun {
  type: "run";
  prompt: string;
  system_prompt?: string;
  session_id?: string;
  specialty?: string;
  attachments?: AttachmentMeta[];
}

export interface ClientCancel {
  type: "cancel";
  session_id: string;
}

export interface ClientResume {
  type: "resume";
  session_id: string;
  request_id?: string;
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

export interface ClientListAllSessions {
  type: "list_all_sessions";
}

export interface ClientNewSession {
  type: "new_session";
  request_id?: string;
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

export interface ClientFetchModels {
  type: "fetch_models";
  backend_type: string;
  api_key: string;
  base_url: string;
}

export interface ClientValidateModel {
  type: "validate_model";
  backend_type: string;
  api_key: string;
  base_url: string;
  model_id: string;
  max_tokens: number;
  name?: string;
  /** Index of the model being edited; omit or -1 to add a new model. */
  model_index?: number;
}

export interface ClientUpdateSkills {
  type: "update_skills";
  enabled_skills: string[];
}

export interface ClientInstallSkill {
  type: "install_skill";
  name: string;
  content: string;
  file_path: string;
}

export interface ClientUninstallSkill {
  type: "uninstall_skill";
  name: string;
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

export interface ClientRollbackLog {
  type: "rollback_log";
  session_id?: string;
}

export interface ClientRollbackCheckout {
  type: "rollback_checkout";
  session_id?: string;
  commit_hash: string;
}

export interface ClientEditMessage {
  type: "edit_message";
  message_index: number;
  new_content: string;
  session_id?: string;
}

export interface ClientDeleteMessage {
  type: "delete_message";
  message_index: number;
  session_id?: string;
}

export interface ClientDeleteSession {
  type: "delete_session";
  session_id: string;
}

export interface ClientExportSession {
  type: "export_session";
  session_id: string;
}

export interface ClientRenameSession {
  type: "rename_session";
  session_id: string;
  new_name: string;
}

export interface ClientListWorkspaces {
  type: "list_workspaces";
}

export interface ClientOpenWorkspace {
  type: "open_workspace";
  path: string;
  request_id?: string;
}

export interface ClientCloseWorkspace {
  type: "close_workspace";
  path: string;
  request_id?: string;
}

export interface ClientRemoveWorkspace {
  type: "remove_workspace";
  path: string;
}

export interface ClientReindexWorkspace {
  type: "reindex_workspace";
}

export interface ClientDeleteIndex {
  type: "delete_index";
}

export interface ClientUpdateSubAgents {
  type: "update_sub_agents";
  agents: SubAgentConfig[];
}

export interface ModelConfigMeta {
  name: string;
  model_id: string;
  backend_type: string;
  api_key: string;
  base_url: string;
  max_tokens: number;
  context_window: number;
  enabled: boolean;
}

export interface ContextUsageEvent {
  type: "context_usage";
  context_tokens: number;
  context_window: number;
  session_id?: string;
}

export interface AgentStateSnapshot {
  task_stage: string;
  task_stage_history: Array<Record<string, unknown>>;
  working_set: Record<string, unknown>;
  turn_summaries: Array<Record<string, unknown>>;
  delegate_history: Array<Record<string, unknown>>;
  stuck_events: Array<Record<string, unknown>>;
  tool_semantics: Record<string, unknown>;
}

export interface AgentStateEvent {
  type: "agent_state";
  state: AgentStateSnapshot;
  session_id?: string;
}

export interface MCPServerConfig {
  /** Server name (used as key in mcpServers map). */
  name: string;
  /** Transport type: "stdio" or "http". */
  type: "stdio" | "http";
  /** Executable command (stdio only). */
  command?: string;
  /** Command arguments (stdio only). */
  args?: string[];
  /** Remote URL (http only). */
  url?: string;
  /** HTTP headers (http only). */
  headers?: Record<string, string>;
  /** Environment variables (stdio only). */
  env?: Record<string, string>;
  /** Working directory (stdio only). */
  cwd?: string;
  /** Request timeout in seconds (http only, default 60). */
  timeout?: number;
  /** Disabled flag (default false). */
  disabled?: boolean;
}

export interface SubAgentConfig {
  name: string;
  description: string;
  system_prompt: string;
  hidden?: boolean;
}

export interface SkillInfo {
  name: string;
  description: string;
  aliases: string[];
  source: string;
  body: string;
  argument_hint: string;
  allowed_tools: string[] | null;
  when_to_use: string;
  context: string;
  model: string | null;
  disable_model_invocation: boolean;
  user_invocable: boolean;
  license: string;
  compatibility: string;
  metadata: Record<string, string>;
}

export interface ClientUpdateSkill {
  type: "update_skill";
  name: string;
  content: string;
}

export interface ModelsList {
  type: "models_list";
  models: string[];
}

export interface WorkspaceEntry {
  id: string;
  path: string;
  name: string;
  opened_at: number;
  session_count?: number;
  index_status?: string;
  index_files?: number;
}

export interface WorkspaceOpened {
  type: "workspace_opened";
  path: string;
  name: string;
  id?: string;
  workspaces: WorkspaceEntry[];
  index_status?: string;
  index_files?: number;
}

export interface WorkspacesList {
  type: "workspaces_list";
  workspaces: WorkspaceEntry[];
}

export interface WorkspaceRemoved {
  type: "workspace_removed";
  path: string;
  workspaces: WorkspaceEntry[];
}

export interface SessionEntryData {
  session_id: string;
  created_at: number;
  last_active: number;
  is_running: boolean;
  preview?: string;
  name?: string;
  channel?: string;
  message_count?: number;
  metadata?: Record<string, unknown>;
}

export interface SessionsList {
  type: "sessions_list";
  sessions: SessionEntryData[];
}

export interface SessionsAll {
  type: "sessions_all";
  normal: SessionEntryData[];
  iwork: SessionEntryData[];
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

export interface ModelsFetched {
  type: "models_fetched";
  models: string[];
}

export interface ModelValidated {
  type: "model_validated";
}

export interface ModelValidationError {
  type: "model_validation_error";
  message: string;
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

export interface SkillInstalled {
  type: "skill_installed";
  name: string;
  available_skills: SkillInfo[];
}

export interface SkillInstallError {
  type: "skill_install_error";
  name: string;
  message: string;
}

export interface SkillUninstalled {
  type: "skill_uninstalled";
  name: string;
  available_skills: SkillInfo[];
}

export interface McpUpdated {
  type: "mcp_updated";
  mcp_servers: MCPServerConfig[];
}

export interface RollbackLogEvent {
  type: "rollback_log";
  session_id: string;
  commits: RollbackCommitEntry[];
}

export interface RollbackCommitEntry {
  hash: string;
  parent: string | null;
  timestamp: number;
  turn_count: number;
  message: string;
}

export interface RollbackCheckoutEvent {
  type: "rollback_checkout";
  session_id: string;
  commit_hash: string;
  messages: Array<{ role: string; content: string | Array<{ type: string; text: string }>; tool_calls?: any[]; reasoning_content?: string }>;
  turn_count: number;
  plan_items?: PlanItem[];
  artifacts?: any[];
  user_input?: string;
}

export interface MessagesUpdated {
  type: "messages_updated";
  session_id: string;
  commit_hash: string;
  messages: Array<{ role: string; content: string | Array<{ type: string; text: string }>; tool_calls?: any[]; reasoning_content?: string }>;
  plan_items?: PlanItem[];
  artifacts?: any[];
}

export interface SessionDeleted {
  type: "session_deleted";
  session_id: string;
}

export interface SessionExported {
  type: "session_exported";
  session_id: string;
  markdown: string;
  filename: string;
}

export interface SessionRenamed {
  type: "session_renamed";
  session_id: string;
  new_name: string;
}

export interface AgentUpdated {
  type: "agent_updated";
  config: Record<string, unknown>;
}

export interface SubAgentsUpdated {
  type: "sub_agents_updated";
  sub_agents: SubAgentConfig[];
}

export interface WorkspaceClosed {
  type: "workspace_closed";
}

export interface MemoryEntry {
  name: string;
  path: string;
  size: number;
  modified: number;
  preview: string;
  title?: string;
  tags?: string[];
  type?: string;
}

export interface MemoryList {
  type: "memory_list";
  entries: MemoryEntry[];
}

export interface ClientGetMemoryList {
  type: "get_memory_list";
}

export interface ClientGetMemoryDetail {
  type: "get_memory_detail";
  path: string;
}

export interface ClientListGlobalRules {
  type: "list_global_rules";
}

export interface ClientListProjectRules {
  type: "list_project_rules";
}

export interface ClientSaveGlobalRule {
  type: "save_global_rule";
  name: string;
  content: string;
}

export interface ClientDeleteGlobalRule {
  type: "delete_global_rule";
  name: string;
}

export interface ClientGetGlobalRuleContent {
  type: "get_global_rule_content";
  name: string;
}

export interface ClientGetProfile {
  type: "get_profile";
}

export interface MemoryDetailEvent {
  type: "memory_detail";
  path: string;
  content: string;
  error?: string;
}

export interface GlobalRulesList {
  type: "global_rules_list";
  rules: GlobalRuleEntry[];
}

export interface GlobalRuleEntry {
  name: string;
  path: string;
  size: number;
  modified: number;
}

export interface ProjectRulesList {
  type: "project_rules_list";
  rules: ProjectRuleEntry[];
}

export interface ProjectRuleEntry {
  name: string;
  path: string;
  priority: number;
  modified: number;
}

export interface ProjectHooksList {
  type: "project_hooks_list";
  hooks: ProjectHookEntry[];
}

export interface ProjectHookEntry {
  handler_id: string;
  event_type: string;
  source_path: string;
  matcher: string;
  command: string;
  hook_type: string;
  timeout_ms: number;
}

export interface GlobalRuleSaved {
  type: "global_rule_saved";
  name: string;
}

export interface GlobalRuleDeleted {
  type: "global_rule_deleted";
  name: string;
}

export interface GlobalRuleContentEvent {
  type: "global_rule_content";
  name: string;
  content: string;
  error?: string;
}

export interface ProfileData {
  name: string;
  language_preference: string;
  timezone: string;
  expertise_level: string;
  domain: string;
  formality: string;
  detail_preference: string;
  tone: string;
  response_style: string;
  preferred_languages: string[];
  preferred_frameworks: string[];
  skill_levels: Record<string, string>;
  os: string;
  editor: string;
  testing_preference: string;
  learning_style: string;
  typical_session_length: string;
  common_goals: string[];
  error_tolerance: string;
  confidence: Record<string, number>;
  schema_version: number;
  last_updated: number;
  update_count: number;
  summary: string;
}

export interface ProfileMessage {
  type: "profile_data";
  profile: ProfileData;
}

export interface IndexStatusEvent {
  type: "index_status";
  files: number;
  status: string;
  progress?: number;
  workspace_id?: string;
}

export interface GitignoreContentEvent {
  type: "gitignore_content";
  path: string;
  content: string;
}

export interface DocumentsListEvent {
  type: "documents_list";
  documents: DocumentEntry[];
}

export interface DocumentAddedEvent {
  type: "document_added";
  document: DocumentEntry;
}

export interface DocumentUpdatedEvent {
  type: "document_updated";
  document: DocumentEntry;
}

export interface DocumentRemovedEvent {
  type: "document_removed";
  id: string;
}

export interface DocumentErrorEvent {
  type: "document_error";
  message: string;
}

export interface PermissionRequest {
  type: "permission_request";
  tool_name: string;
  reason: string;
}

export interface PermissionPolicy {
  value: "allow" | "deny" | "ask" | "default";
  source?: "user" | "project" | "session" | "cli" | "hook" | "default";
}

export interface PermissionPolicies {
  tools: Record<string, PermissionPolicy>;
  capabilities: Record<string, PermissionPolicy>;
}

export interface EngineInstallRequestEvent {
  type: "engine_install_request";
  request_id: string;
  engine: string;
  title: string;
  body: string;
  hint?: string;
  options?: Array<{
    id: string;
    label: string;
    description?: string;
    kind?: "primary" | "secondary" | "danger";
  }>;
}

export interface EngineInstallProgressEvent {
  type: "engine_install_progress";
  request_id: string;
  pct: number;
  message: string;
  sub_message?: string;
  indeterminate?: boolean;
  status?: "running" | "success" | "fail" | "cancelled";
  message_code?: string;
  message_args?: Record<string, string>;
  sub_message_code?: string;
  sub_message_args?: Record<string, string>;
}

export interface EngineInstallResponseAck {
  type: "engine_install_response_ack";
  request_id: string;
  choice: string;
  resolved: boolean;
}

export interface ReferencesUpdateEvent {
  type: "references_update";
  references: import("./types.js").ReferenceItem[];
  session_id?: string;
}

export interface BranchMeta {
  id: string;
  parent_branch_id: string | null;
  fork_point_message_id: string | null;
  created_at: number;
  messages_count: number;
  tokens: { input: number; output: number; total: number };
}

export interface BranchUpdated {
  type: "branch_updated";
  session_id: string;
  active_branch_id: string;
  branches: BranchMeta[];
  messages?: Message[];
}

export interface BranchRolledBack {
  type: "branch_rolled_back";
  session_id: string;
  branch_id: string;
  removed_message_ids: string[];
}

export interface ClientGetProfile {
  type: "get_profile";
}

export interface ClientRespondPermission {
  type: "respond_permission";
  tool_name: string;
  decision: boolean;
}

export interface ClientRespondTakeover {
  type: "respond_takeover";
  decision: boolean;
}

export interface ClientRespondPlan {
  type: "respond_plan";
  proposal_id: string;
  approved: boolean;
}

export interface ClientRespondQuestion {
  type: "respond_question";
  tool_call_id: string;
  answers: string;
}

export interface ClientSetPlanMode {
  type: "set_plan_mode";
  active: boolean;
  reason?: string;
}

export interface ClientRetry {
  type: "retry";
  branch_id: string;
  user_message_index: number;
  mode?: "normal" | "detailed" | "concise";
  session_id?: string;
}

export interface ClientSwitchBranch {
  type: "switch_branch";
  branch_id: string;
  session_id: string;
}

export interface ClientRollback {
  type: "rollback";
  branch_id: string;
  message_id: string;
}

// ── Attachment ────────────────────────────────────────────────────────────

/** An attachment (file/folder) attached to a composer message. */
export interface AttachmentMeta {
  name: string;
  path: string;
  content: string;
  mime_type: string;
  size: number;
  is_binary: boolean;
}

// ── App State ─────────────────────────────────────────────────────────────

export interface TimelineSegment {
  kind: "thinking" | "text" | "tool";
  toolId?: string;
  text?: string;  // accumulated text content for text segments
}

/** A single chat message (user or assistant) with its timeline segments. */
export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  thinking?: string;
  thinkingElapsed?: number;  // duration in seconds
  isStreaming: boolean;
  toolCalls: ToolCallState[];
  segments: TimelineSegment[];
  timestamp: number;
  hasError?: boolean;
  /** Turn status card data — populated from backend events. */
  errorMessage?: string;
  errorCode?: string;
  interruptedReason?: string;
  turnStatusText?: string;  // e.g. "任务完成" from backend
  cancelledText?: string;   // set when user presses stop button (reason="cancelled")
  mode?: string;  // "plan" | "spec" | "terminal" for mode-based messages
  fileRefs?: { name: string; size: number; icon: string; path?: string; mime_type?: string }[];
  tokenUsage?: { input_tokens: number; output_tokens: number; total_tokens: number };
  _index?: number;
  serverId?: string;  // server-side message ID (for retry matching)
  parentId?: string;
}

/** The resolved state of a single tool call (status, params, result). */
export interface ToolCallState {
  id: string;
  name: string;
  params: Record<string, unknown>;
  result?: string;
  subAgentMessages?: Message[];
  subAgentSessionId?: string;
  isError?: boolean;
  status: "pending" | "running" | "done";
}

export interface DocumentEntry {
  id: string;
  name: string;
  source: string;
  status: string;
  original_url: string;
  original_path: string;
  content_path: string;
  file_type: string;
  size: number;
  added_at: number;
}

export interface CustomCommand {
  name: string;
  title: string;
  description: string;
  icon: string;
  prompt?: string;
}

/** Per-session snapshot of all session-scoped state. */
export interface SessionSnapshot {
  messages: Message[];
  tokenUsage: TokenUsage | null;
  telemetry: TelemetryData | null;
  planItems: PlanItem[];
  planModeActive: boolean;
  planProposals: PlanProposal[];
  artifacts: ArtifactItem[];
  references: ReferenceItem[];
  compactEvents: CompactInfo[];
  systemMessages: SystemMessageInfo[];
  branches: BranchMeta[];
  activeBranchId: string;
  spec: SpecData | null;
  running: boolean;
  agentState?: AgentStateSnapshot | null;
}

/** The complete global application state held by the state store. */
export interface AppState {
  messages: Message[];
  attachments: AttachmentMeta[];
  sessionId: string;
  sessionStore: Record<string, SessionSnapshot>;
  connected: boolean;
  running: boolean;  // active session running state (derived from runningSessions)
  subAgentView: ToolCallState | null;
  subAgentBreadcrumb: Array<{sessionId: string; name: string; toolCallId: string; parentToolCallId: string | null}>;
  settings: Record<string, unknown>;
  activeToolId: string | null;
  theme: "dark" | "light";
  themePreference: "system" | "dark" | "light";
  telemetry: TelemetryData | null;
  usageStats: UsageStatsData | null;
  tokenUsage: TokenUsage | null;
  planItems: PlanItem[];
  planModeActive: boolean;
  planProposals: PlanProposal[];
  notifications: NotificationItem[];
  availableModels: string[];
  sessionsList: SessionEntryData[];
  modelConfigs: ModelConfigMeta[];
  activeModelIndex: number;
  skillsList: SkillInfo[];
  enabledSkills: string[];
  mcpServers: MCPServerConfig[];
  subAgents: SubAgentConfig[];
  agentConfig: {
    system_prompt: string;
    specialty: string;
    permission_mode: string;
    max_turns: number;
  };
  searchResults: SearchResultEntry[];
  automationHistory: any[];
  workspaces: WorkspaceEntry[];
  activeWorkspace: string;
  workspaceMode: "iwork" | "normal";
  indexStatus: "idle" | "ready" | "indexing" | "error" | "no_workspace";
  indexFiles: number;
  indexProgress: number;
  indexCurrentFile?: string;
  gitignoreContent: string;
  docsList: DocumentEntry[];
  gatewayStatus: GatewayStatusData | null;
  toolsInfo: ToolsInfo;
  modelCatalog: ModelCatalog;
  mcpCatalog: McpCatalog;
  artifacts: ArtifactItem[];
  references: ReferenceItem[];
  compactEvents: CompactInfo[];
  systemMessages: SystemMessageInfo[];
  memoryList: MemoryEntry[];
  memoryDetail: { path: string; content: string; error?: string } | null;
  globalRules: GlobalRuleEntry[];
  projectRules: ProjectRuleEntry[];
  projectHooks: ProjectHookEntry[];
  viewingGlobalRule: { name: string; content: string; error?: string } | null;
  profile: ProfileData | null;
  inputMode: string;
  pendingPermission: string | null;
  permissionPolicies: PermissionPolicies;
  tempChat: boolean;
  customCommands: CustomCommand[];
  branches: BranchMeta[];
  activeBranchId: string;
  pendingQueueCount: number;
  queuedPrompts: QueuedPrompt[];
  runQueuePosition: number | null;
  workflowState: WorkflowState | null;
  contextTokens: number;
  contextWindow: number;
  agentState: AgentStateSnapshot | null;
  spec: SpecData | null;
}

export interface WorkflowTaskInfo {
  taskId: string;
  taskName: string;
  status: string;
}

export interface WorkflowState {
  workflowId: string;
  goal: string;
  totalTasks: number;
  taskIds: string[];
  active: boolean;
  tasks: WorkflowTaskInfo[];
  completedCount: number;
  failedCount: number;
  skippedCount: number;
  success?: boolean;
  totalDuration?: number;
}

export interface QueuedPrompt {
  text: string;
  mode?: string;
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface ArtifactItem {
  path: string;
  name: string;
  ext: string;
  size: number;
  tool: string;
  created_at: number;
  diff_text?: string;
}

export interface ReferenceItem {
  tool: string;
  summary: string;
  icon: string;
  timestamp: number;
  branch_id?: string;
}

export interface GatewayAdapterInfo {
  name: string;
  platform: string;
  connected: boolean;
  capabilities: string[];
  last_seen: number;
  error?: string;
}

export interface GatewayStatusData {
  running: boolean;
  host: string;
  port: number;
  adapters: GatewayAdapterInfo[];
  uptime_seconds: number;
}

export interface ToolsInfo {
  base: string[];
  unlocked: string[];
  active: string[];
  by_category: Record<string, string[]>;
  total_available: number;
}

// ── Model Catalog ─────────────────────────────────────────────────────────

export interface ModelEntry {
  id: string;
  label: string;
  context: number;
  modalities: string[];
}

export interface ProviderEntry {
  id: string;
  label: string;
  base_url: string;
  docs: string;
  allow_custom: boolean;
  auth: string;
  models: ModelEntry[];
}

export interface ModelCatalog {
  providers: ProviderEntry[];
  default_output_tokens: Record<string, number>;
}

// ── MCP Catalog ──────────────────────────────────────────────────────────────

export interface McpProviderEntry {
  id: string;
  label: string;
  description: string;
  config: {
    type: "stdio" | "http";
    command?: string;
    args?: string[];
    url?: string;
    env?: Record<string, string>;
  };
  env_fields: Record<string, { label: string; secret?: boolean }>;
  docs: string;
}

export interface McpCatalog {
  providers: McpProviderEntry[];
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
  session_id?: string;
}

export interface PlanProposal {
  type: "plan_proposal";
  proposal_id: string;
  tool_call_id: string;
  tool_name: string;
  tool_args?: Record<string, unknown>;
  preview: string;
  diff_text?: string;
  file_path?: string;
  original?: string;
  proposed?: string;
  added?: number;
  removed?: number;
  risk?: "low" | "medium" | "high";
  session_id?: string;
}

export interface PlanModeChanged {
  type: "plan_mode_changed";
  active: boolean;
  reason?: string;
  session_id?: string;
}

export interface PlanResolved {
  type: "plan_resolved";
  proposal_id: string;
  tool_call_id: string;
  approved: boolean;
  session_id?: string;
}

export interface ArtifactsUpdate {
  type: "artifacts_update";
  artifacts: ArtifactItem[];
  session_id?: string;
}

export interface ReferencesUpdate {
  type: "references_update";
  references: ReferenceItem[];
  session_id?: string;
}

export interface BranchSwitched {
  type: "branch_switched";
  session_id: string;
  branch_id: string;
  messages: Message[];
  branches: BranchMeta[];
  artifacts?: ArtifactItem[];
  references?: ReferenceItem[];
  tokens: TokenUsage | null;
}

export interface AssistantBoundaryEvent {
  type: "assistant_boundary";
  session_id?: string;
}

export interface CompactEvent {
  type: "compact";
  old_count: number;
  new_count: number;
  old_tokens: number;
  new_tokens: number;
}

export interface SystemMessageEvent {
  type: "system_message";
  content: string;
  kind: string;
  session_id: string;
}

export interface CompactInfo {
  old_count: number;
  new_count: number;
  old_tokens: number;
  new_tokens: number;
}

export interface SystemMessageInfo {
  content: string;
  kind: string;
  timestamp: number;
}

export interface SpecSection {
  title: string;
  content: string;
}

export interface SpecData {
  title: string;
  sections: SpecSection[];
  status: string;
  feedback: string;
  raw_text: string;
  metadata: Record<string, unknown>;
}

export interface SpecUpdateEvent {
  type: "spec_update";
  spec: SpecData | null;
  status: string;
  feedback?: string;
  session_id: string;
}

// ── Edit proposal (Codex-style inline diff / accept-reject) ─────────────

/**
 * Pending file edit surfaced by the agent loop.  Emitted by
 * `file_edit` with `dry_run=true`; the desktop renderer can display
 * an inline diff and write the file on accept.
 */
export interface EditProposalData {
  kind: "edit_proposal";
  tool_call_id: string;
  file_path: string;
  diff_text: string;
  original: string;
  proposed: string;
  added: number;
  removed: number;
  summary: string;
}

export interface EditProposal {
  type: "edit_proposal";
  tool_call_id: string;
  file_path: string;
  diff_text: string;
  original: string;
  proposed: string;
  added: number;
  removed: number;
  summary: string;
}

export function createEmptySessionSnapshot(): SessionSnapshot {
  return {
    messages: [],
    tokenUsage: null,
    telemetry: null,
    planItems: [],
    planModeActive: false,
    planProposals: [],
    artifacts: [],
    references: [],
    compactEvents: [],
    systemMessages: [],
    branches: [],
    activeBranchId: "",
    spec: null,
    running: false,
    agentState: null,
  };
}

// ── Notification ──────────────────────────────────────────────────────────

/** A notification item shown in the bell panel / toasts. */
export interface NotificationItem {
  id: string;
  type: "error" | "success" | "info" | "warning";
  title: string;
  message: string;
  source?: string;
  timestamp: number;
  read: boolean;
}

// ── App State ─────────────────────────────────────────────────────────────

export function createEmptyState(): AppState {
  const sessionSnapshot = createEmptySessionSnapshot();
  return {
    messages: sessionSnapshot.messages,
    attachments: [],
    sessionId: "",
    sessionStore: {},
    connected: false,
    running: sessionSnapshot.running,
    subAgentView: null,
    subAgentBreadcrumb: [],
    settings: {},
    activeToolId: null,
    theme: "dark",
    themePreference: "system",
    telemetry: null,
    usageStats: null,
    tokenUsage: sessionSnapshot.tokenUsage,
    planItems: sessionSnapshot.planItems,
    planModeActive: sessionSnapshot.planModeActive,
    planProposals: sessionSnapshot.planProposals,
    notifications: [],
    availableModels: [],
    sessionsList: [],
    modelConfigs: [],
    activeModelIndex: 0,
    skillsList: [],
    enabledSkills: [],
    mcpServers: [],
    subAgents: [],
    artifacts: sessionSnapshot.artifacts,
    references: sessionSnapshot.references,
    compactEvents: sessionSnapshot.compactEvents,
    systemMessages: sessionSnapshot.systemMessages || [],
    spec: null,
    memoryList: [],
    memoryDetail: null,
    globalRules: [],
    projectRules: [],
    projectHooks: [],
    viewingGlobalRule: null,
    profile: null,
    inputMode: "",
    pendingPermission: null,
    permissionPolicies: { tools: {}, capabilities: {} },
    tempChat: false,
    customCommands: [],
    agentConfig: {
      system_prompt: "",
      specialty: "general",
      permission_mode: "default",
      max_turns: 0,
    },
    searchResults: [],
    automationHistory: [],
    workspaces: [],
    activeWorkspace: "",
    workspaceMode: "normal",
    indexStatus: "idle",
    indexFiles: 0,
    indexProgress: 0,
    indexCurrentFile: undefined,
    gitignoreContent: "",
    docsList: [],
    gatewayStatus: null,
    toolsInfo: {
      base: [],
      unlocked: [],
      active: [],
      by_category: {},
      total_available: 0,
    },
    modelCatalog: { providers: [], default_output_tokens: {} },
    mcpCatalog: { providers: [] },
    branches: sessionSnapshot.branches,
    activeBranchId: sessionSnapshot.activeBranchId,
    pendingQueueCount: 0,
    queuedPrompts: [],
    runQueuePosition: null,
    workflowState: null,
    contextTokens: 0,
    contextWindow: 0,
    agentState: null,
  };
}
