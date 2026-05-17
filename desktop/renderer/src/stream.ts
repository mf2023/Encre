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

import { ServerEvent } from "./types.js";
import * as state from "./state.js";
import { send } from "./ws.js";
import { Chat } from "./chat.js";
import { Tools } from "./tools.js";
import { Permissions } from "./permissions.js";

let chat: Chat | null = null;
let tools: Tools | null = null;
let permissions: Permissions | null = null;
let permissionResolve: ((allowed: boolean) => void) | null = null;

export function init(c: Chat, t: Tools, p: Permissions): void {
  chat = c;
  tools = t;
  permissions = p;
}

export function handleEvent(event: ServerEvent): void {
  switch (event.type) {
    case "session_ready":
      state.setSessionId(event.session_id);
      state.setConnected(true);
      if (event.messages && event.messages.length > 0) {
        state.loadSessionMessages(event.messages);
      }
      send({ type: "list_sessions" });
      send({ type: "get_config" } as any);
      break;

    case "text_delta":
      state.appendContent(event.text);
      chat?.scrollToBottom();
      break;

    case "thinking_delta":
      state.appendThinking(event.text);
      chat?.scrollToBottom();
      break;

    case "tool_call_start": {
      // Find existing (may have been auto-created by deltas arriving first) or create
      let tc = state.findToolCall(event.id);
      if (tc) {
        tc.name = event.name || tc.name;
        tc.status = "pending";
      } else {
        state.addToolCall({
          id: event.id,
          name: event.name,
          params: {},
          status: "pending",
        });
      }
      tools?.render();
      break;
    }

    case "tool_call_delta": {
      // Accumulate params bytes into the tool call — create if not yet seen
      let tc = state.findToolCall(event.id);
      if (!tc) {
        state.addToolCall({
          id: event.id,
          name: "",
          params: {},
          status: "running",
        });
        tc = state.findToolCall(event.id);
      }
      if (tc) {
        const key = event.key;
        tc.params[key] = (tc.params[key] ?? "") + event.value;
        tc.status = "running";
        tools?.render();
      }
      break;
    }

    case "tool_call_end": {
      // Try to parse accumulated JSON params into a structured form
      const tc = state.findToolCall(event.id);
      if (tc) {
        try {
          const rawArgs = tc.params["arguments"];
          if (typeof rawArgs === "string" && rawArgs) {
            tc.params = JSON.parse(rawArgs) as Record<string, unknown>;
          }
        } catch {
          // Keep raw string params if JSON parse fails
        }
        tc.status = "running";
      }
      break;
    }

    case "tool_progress":
      state.updateToolCall(event.id, { status: "running" });
      tools?.render();
      break;

    case "tool_result":
      state.updateToolCall(event.id, {
        result: event.content,
        isError: event.is_error,
        status: "done",
      });
      tools?.render();
      break;

    case "permission_request":
      if (permissionResolve) {
        permissionResolve(false);
      }
      permissions?.show(
        event.tool_name,
        event.reason,
        (allowed: boolean) => {
          send({
            type: "respond_permission",
            tool_name: event.tool_name,
            decision: allowed,
          });
          permissionResolve = null;
          permissions?.hide();
        }
      );
      break;

    case "finish":
      state.setRunning(false);
      if (event.usage) {
        const u = event.usage as Record<string, unknown>;
        const input = typeof u.input_tokens === "number" ? u.input_tokens : 0;
        const output = typeof u.output_tokens === "number" ? u.output_tokens : 0;
        const total = typeof u.total_tokens === "number" ? u.total_tokens : input + output;
        state.setTokenUsage({
          input_tokens: input,
          output_tokens: output,
          total_tokens: total,
        });
        state.finishAssistantMessage({
          input_tokens: input,
          output_tokens: output,
          total_tokens: total,
        });
      } else {
        state.finishAssistantMessage();
      }
      const btnStop = document.getElementById("btn-stop");
      btnStop?.classList.remove("cancelling");
      if (btnStop) btnStop.style.pointerEvents = "";
      chat?.render();
      send({ type: "list_sessions" });
      break;

    case "pong":
      state.setConnected(true);
      break;

    case "error":
      chat?.showError(event.message);
      state.setRunning(false);
      // Mark last assistant message as errored
      const lastMsg = state.getLastAssistantMessage();
      if (lastMsg) lastMsg.hasError = true;
      state.addNotification({
        id: crypto.randomUUID(),
        type: "error",
        title: "Error",
        message: event.message,
        timestamp: Date.now(),
        read: false,
      });
      break;

    case "configured":
      state.setSettings({ ...state.getState().settings, ...event.config });
      break;

    case "telemetry":
      state.setTelemetry(event.data);
      break;

    case "plan_update":
      state.setPlanItems(event.plan_items);
      break;

    case "models_list":
      state.setAvailableModels(event.models);
      break;

    case "sessions_list":
      state.setSessionsList(event.sessions);
      break;

    case "config_data": {
      const cfg = event.config as Record<string, unknown>;
      if (cfg.models && Array.isArray(cfg.models)) {
        state.setModelConfigs(cfg.models as any[], (cfg.active_model_index as number) || 0);
      }
      if (cfg.mcp_servers && Array.isArray(cfg.mcp_servers)) {
        state.setMcpServers(cfg.mcp_servers as any[]);
      }
      if (cfg.enabled_skills && Array.isArray(cfg.enabled_skills)) {
        state.setEnabledSkills(cfg.enabled_skills as string[]);
      }
      if (cfg.available_skills && Array.isArray(cfg.available_skills)) {
        state.setSkillsList(cfg.available_skills as any[]);
      }
      state.setAgentConfig({
        system_prompt: (cfg.system_prompt as string) || "",
        specialty: (cfg.default_specialty as string) || "general",
        permission_mode: (cfg.permission_mode as string) || "default",
        max_turns: (cfg.max_turns as number) || 25,
      });
      break;
    }

    case "models_updated": {
      state.setModelConfigs(event.models, event.active_model_index);
      send({ type: "get_config" } as any);
      break;
    }

    case "skills_updated":
      state.setEnabledSkills(event.enabled_skills);
      if (event.available_skills) {
        state.setSkillsList(event.available_skills);
      }
      break;

    case "skills_list":
      state.setSkillsList(event.skills);
      break;

    case "mcp_updated":
      state.setMcpServers(event.mcp_servers);
      break;

    case "agent_updated": {
      const ac = event.config as Record<string, unknown>;
      state.setAgentConfig({
        system_prompt: (ac.system_prompt as string) || "",
        specialty: (ac.specialty as string) || "general",
        permission_mode: (ac.permission_mode as string) || "default",
        max_turns: (ac.max_turns as number) || 25,
      });
      break;
    }

    case "search_results":
      state.setSearchResults(event.results);
      break;

    default:
      break;
  }
}
