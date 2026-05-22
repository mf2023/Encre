#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Yim.
# The Yim project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DISCLAIMER: Users must comply with applicable AI regulations.
# Non-compliance may result in service termination or legal liability.

from yim.agent import YmiAgent
from yim.goal import YmiGoalRunner, YmiGoalLoop, GoalDefinition, GoalResult, GoalStatus, GoalEvent
from yim.scheduler import YmiScheduler, ScheduledJob, CronSchedule, ScheduleType, JobState
from yim.recovery import ErrorRecoveryEngine, RetryableExecutor, RecoveryState, RecoveryDecision, RecoveryAction, ErrorCategory
from yim.backend import create_backend
from yim.backends.base import BaseBackend
from yim.backends.registry import BackendRegistry, ModelInfo
from yim.backends.retry import RetryConfig, retry_with_backoff, DEFAULT_RETRY_CONFIG
from yim.backends.openai import OpenAIBackend
from yim.backends.anthropic import AnthropicBackend
from yim.backends.ollama import OllamaBackend
from yim.backends.deepseek import DeepSeekBackend
from yim.backends.google import GoogleBackend
from yim.backends.groq import GroqBackend
from yim.backends.local import LocalBackend
from yim.backends.bedrock import BedrockBackend
from yim.backends.openai_compatible import OpenAICompatibleBackend
from yim.crypto import encrypt, decrypt, encrypt_bytes, decrypt_bytes, ensure_keyfile
from yim.rollback import YmiRollbackGit, CommitEntry
from yim.config import YmiConfig, ModelConfig, get_data_dir
from yim.hooks.system import YmiHookSystem
from yim.hooks.types import HookStartedEvent, HookProgressEvent, HookResponseEvent
from yim.loop import YmiLoop
from yim.memdir.system import YmiMemorySystem, MemoryHeader, EntrypointResult
from yim.memdir.semantic import SemanticMemorySearch, SearchResult, WorkingMemory, MemoryConsolidator, ConsolidationAction
from yim.safety import YmiSafetyEngine, BashAnalysis, DangerLevel, analyze_bash_command
from yim.autosafety import YmiAutoSafetyClassifier, AutoDecision, ClassificationResult, UserDecisionRecord
from yim.sandbox.container import YmiContainerSandbox
from yim.sandbox.types import SandboxConfig, SandboxResult
from yim.server.app import YmiServer, run_server
from yim.server.protocol import (
    ClientMessage,
    parse_client_message,
    encode_server_message,
)
from yim.server.ws import YmiWSHandler
from yim.server.admin import handle_admin
from yim.evolution.config import EvolutionConfig
from yim.evolution.learner import YmiEvolutionLearner, SuccessRecord, ErrorRecord
from yim.evolution.optimizer import YmiStrategyOptimizer, ToolStrategy
from yim.evolution.reflex import YmiReflexLoop, ReflexResult
from yim.evolution.meta import YmiMetaCognition, CapabilityProfile
from yim.server.session_manager import SessionManager, SessionInfo
from yim.session import YmiSession, SessionCheckpoint
from yim.telemetry import YmiTelemetry, ToolCallRecord, TurnRecord, RetryRecord
from yim.logging_config import setup_logging, get_logger
from yim.native import (
    read_file as native_read_file,
    write_file as native_write_file,
    grep as native_grep,
    glob_pattern as native_glob,
    count_tokens as native_count_tokens,
    compute_diff as native_compute_diff,
    apply_diff as native_apply_diff,
    sandbox_execute as native_sandbox_execute,
    search_codebase as native_search_codebase,
)
from yim.tools.base import YmiTool
from yim.tools.registry import ToolRegistry
from yim.tools.mcp import YmiMCPTool
from yim.git.repo import YmiGitRepo, GitState
from yim.git.diff import YmiGitDiff, GitDiffResult
from yim.lsp.client import YmiLSPClient
from yim.lsp.manager import YmiLSPManager
from yim.lsp.protocol import (
    Position,
    Range as LSPRange,
    Location as LSPLocation,
    Diagnostic as LSPDiagnostic,
    HoverResult,
    LSPState,
)

from yim.tools.builtin import (
    YmiFileReadTool,
    YmiFileWriteTool,
    YmiFileEditTool,
    YmiBashTool,
    YmiGrepTool,
    YmiGlobTool,
    YmiWebFetchTool,
    YmiWebSearchTool,
    YmiTodoTool,
    YmiTaskCreateTool,
    YmiTaskGetTool,
    YmiTaskListTool,
    YmiTaskUpdateTool,
    YmiTaskStopTool,
    YmiTaskOutputTool,
    YmiCronCreateTool,
    YmiCronDeleteTool,
    YmiCronListTool,
    YmiAgentTool,
    YmiLSPTool,
    YmiBrowserTool,
    YmiDatabaseTool,
    YmiDockerTool,
    YmiGitTool,
    YmiRESTTool,
    YmiPDFTool,
    YmiSpreadsheetTool,
    YmiImageTool,
    YmiDeployTool,
)
from yim.tools.builtin.notebook import YmiNotebookTool
from yim.computer.browser import YmiBrowserSession, BrowserState
from yim.swarm.teammate import YmiTeammate, TeammateHandle
from yim.swarm.mailbox import YmiMailbox, MailboxMessage
from yim.swarm.manager import YmiSwarmManager, SwarmProgress
from yim.swarm.planner import YmiTaskPlanner, TaskTree, TaskNode
from yim.swarm.roles import AgentRole, RoleRegistry
from yim.swarm.orchestrator import YmiOrchestrator, OrchestrationEvent
from yim.swarm.blackboard import YmiBlackboard, BlackboardEntry
from yim.swarm.consensus import YmiConsensus, Proposal, Vote, ConsensusResult
from yim.swarm.session import YmiSwarmSession, SwarmEvent, SwarmResult
from yim.task.manager import YmiTaskManager
from yim.task.executor import YmiTaskExecutor
from yim.task.types import YmiTask
from yim.compact.engine import YmiCompactEngine
from yim.compact.strategies import (
    YmiAlwaysCompactStrategy,
    YmiAutoCompactStrategy,
    YmiTokenBudgetStrategy,
    YmiBudgetReductionStrategy,
    YmiSemanticCompactStrategy,
    YmiSnipStrategy,
    YmiMicroCompactStrategy,
    YmiContextCollapseStrategy,
    YmiMultiStagePipeline,
)
from yim.compact.semantic import (
    SemanticToolOutputCompactor,
    ContextPartitioner,
    ContextPartition,
    ContextTier,
)
from yim.prompts.base import YmiBasePrompt, YmiPromptTemplate
from yim.prompts.system import YmiPromptBuilder
from yim.prompts.coding import YmiCodingPrompt
from yim.prompts.general import YmiGeneralPrompt
from yim.prompts.research import YmiResearchPrompt
from yim.prompts.data import YmiDataPrompt
from yim.ssrf import YmiSSRFGuard
from yim.ratelimit import YmiRateLimiter, RateLimitResult
from yim.notebook.session import YmiNotebookSession
from yim.codebase.indexer import YmiCodeIndex, ModuleInfo
from yim.feedback.learner import YmiFeedbackLearner, CorrectionRecord
from yim.plugins.types import YmiPlugin, PluginManifest, PluginSource
from yim.plugins.registry import PluginRegistry
from yim.backends.failover import FailoverBackend, BackendHealth
from yim.backends.router import RouterBackend, CostTracker, TaskCategory
from yim.skills.types import BundledSkillDefinition
from yim.skills.registry import YmiSkillRegistry
from yim.skills.bundled import create_bundled_skills
from yim.utils.types import (
    AdaptiveThinking,
    BackendError,
    BackendEvent,
    BackendFinish,
    BackendText,
    BackendToolCall,
    BackendToolCallDelta,
    DisabledThinking,
    EnabledThinking,
    Finish,
    FinishReason,
    PermissionAllow,
    PermissionAsk,
    PermissionBehavior,
    PermissionDecision,
    PermissionDeny,
    PermissionMode,
    PermissionRequest,
    TaskStatus,
    TaskType,
    TextDelta,
    ThinkingConfig,
    ThinkingDelta,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallStart,
    ToolProgress,
    ToolResult,
    create_backend_error,
    create_backend_finish,
    create_backend_text,
    create_backend_tool_call,
    create_backend_tool_call_delta,
    create_finish,
    create_permission_request,
    create_text_delta,
    create_thinking_delta,
    create_tool_call_delta,
    create_tool_call_end,
    create_tool_call_start,
    create_tool_progress,
    create_tool_result,
)

__all__ = [
    "encrypt",
    "decrypt",
    "encrypt_bytes",
    "decrypt_bytes",
    "ensure_keyfile",
    "YmiRollbackGit",
    "CommitEntry",
    "YmiAgent",
    "YmiGoalRunner",
    "YmiGoalLoop",
    "GoalDefinition",
    "GoalResult",
    "GoalStatus",
    "GoalEvent",
    "YmiScheduler",
    "ScheduledJob",
    "CronSchedule",
    "ScheduleType",
    "JobState",
    "ErrorRecoveryEngine",
    "RetryableExecutor",
    "RecoveryState",
    "RecoveryDecision",
    "RecoveryAction",
    "ErrorCategory",
    "YmiLoop",
    "YmiSession",
    "SessionCheckpoint",
    "YmiTelemetry",
    "ToolCallRecord",
    "TurnRecord",
    "RetryRecord",
    "setup_logging",
    "get_logger",
    "RetryConfig",
    "retry_with_backoff",
    "DEFAULT_RETRY_CONFIG",
    "native_read_file",
    "native_write_file",
    "native_grep",
    "native_glob",
    "native_count_tokens",
    "native_compute_diff",
    "native_apply_diff",
    "native_sandbox_execute",
    "native_search_codebase",
    "YmiSafetyEngine",
    "BashAnalysis",
    "DangerLevel",
    "analyze_bash_command",
    "YmiAutoSafetyClassifier",
    "AutoDecision",
    "ClassificationResult",
    "UserDecisionRecord",
    "YmiConfig",
    "ModelConfig",
    "get_data_dir",
    "YmiTool",
    "ToolRegistry",
    "YmiMCPTool",
    "YmiHookSystem",
    "HookStartedEvent",
    "HookProgressEvent",
    "HookResponseEvent",
    "YmiMemorySystem",
    "MemoryHeader",
    "EntrypointResult",
    "SemanticMemorySearch",
    "SearchResult",
    "WorkingMemory",
    "MemoryConsolidator",
    "ConsolidationAction",
    "YmiContainerSandbox",
    "SandboxConfig",
    "SandboxResult",
    "YmiFileReadTool",
    "YmiFileWriteTool",
    "YmiFileEditTool",
    "YmiBashTool",
    "YmiGrepTool",
    "YmiGlobTool",
    "YmiWebFetchTool",
    "YmiWebSearchTool",
    "YmiTodoTool",
    "YmiTaskCreateTool",
    "YmiTaskGetTool",
    "YmiTaskListTool",
    "YmiTaskUpdateTool",
    "YmiTaskStopTool",
    "YmiTaskOutputTool",
    "YmiCronCreateTool",
    "YmiCronDeleteTool",
    "YmiCronListTool",
    "YmiAgentTool",
    "YmiNotebookTool",
    "YmiDatabaseTool",
    "YmiDockerTool",
    "YmiGitTool",
    "YmiRESTTool",
    "YmiPDFTool",
    "YmiSpreadsheetTool",
    "YmiImageTool",
    "YmiDeployTool",
    "YmiNotebookSession",
    "YmiSSRFGuard",
    "YmiRateLimiter",
    "RateLimitResult",
    "YmiCodeIndex",
    "ModuleInfo",
    "YmiFeedbackLearner",
    "CorrectionRecord",
    "YmiTaskManager",
    "YmiTaskExecutor",
    "YmiTask",
    "YmiCompactEngine",
    "YmiAlwaysCompactStrategy",
    "YmiAutoCompactStrategy",
    "YmiTokenBudgetStrategy",
    "YmiBudgetReductionStrategy",
    "YmiSemanticCompactStrategy",
    "YmiSnipStrategy",
    "YmiMicroCompactStrategy",
    "YmiContextCollapseStrategy",
    "YmiMultiStagePipeline",
    "SemanticToolOutputCompactor",
    "ContextPartitioner",
    "ContextPartition",
    "ContextTier",
    "YmiBasePrompt",
    "YmiPromptTemplate",
    "YmiPromptBuilder",
    "YmiCodingPrompt",
    "YmiGeneralPrompt",
    "YmiResearchPrompt",
    "YmiDataPrompt",
    "YmiLSPTool",
    "YmiBrowserTool",
    "YmiBrowserSession",
    "BrowserState",
    "YmiEvolutionLearner",
    "EvolutionConfig",
    "SuccessRecord",
    "ErrorRecord",
    "YmiStrategyOptimizer",
    "ToolStrategy",
    "YmiReflexLoop",
    "ReflexResult",
    "YmiMetaCognition",
    "CapabilityProfile",
    "YmiTeammate",
    "TeammateHandle",
    "YmiMailbox",
    "MailboxMessage",
    "YmiSwarmManager",
    "SwarmProgress",
    "YmiTaskPlanner",
    "TaskTree",
    "TaskNode",
    "AgentRole",
    "RoleRegistry",
    "YmiOrchestrator",
    "OrchestrationEvent",
    "YmiBlackboard",
    "BlackboardEntry",
    "YmiConsensus",
    "Proposal",
    "Vote",
    "ConsensusResult",
    "YmiSwarmSession",
    "SwarmEvent",
    "SwarmResult",
    "YmiGitRepo",
    "GitState",
    "YmiGitDiff",
    "GitDiffResult",
    "YmiLSPClient",
    "YmiLSPManager",
    "Position",
    "LSPRange",
    "LSPLocation",
    "LSPDiagnostic",
    "HoverResult",
    "LSPState",
    "YmiSkillRegistry",
    "BundledSkillDefinition",
    "create_bundled_skills",
    "YmiServer",
    "run_server",
    "YmiWSHandler",
    "handle_admin",
    "SessionManager",
    "SessionInfo",
    "ClientMessage",
    "parse_client_message",
    "encode_server_message",
    "BaseBackend",
    "BackendRegistry",
    "ModelInfo",
    "OpenAIBackend",
    "AnthropicBackend",
    "OllamaBackend",
    "DeepSeekBackend",
    "GoogleBackend",
    "GroqBackend",
    "LocalBackend",
    "BedrockBackend",
    "OpenAICompatibleBackend",
    "FailoverBackend",
    "BackendHealth",
    "RouterBackend",
    "CostTracker",
    "TaskCategory",
    "YmiPlugin",
    "PluginManifest",
    "PluginSource",
    "PluginRegistry",
    "create_backend",
    "TextDelta",
    "ThinkingDelta",
    "ToolCallStart",
    "ToolCallDelta",
    "ToolCallEnd",
    "ToolProgress",
    "ToolResult",
    "PermissionRequest",
    "Finish",
    "FinishReason",
    "PermissionMode",
    "PermissionBehavior",
    "PermissionAllow",
    "PermissionDeny",
    "PermissionAsk",
    "PermissionDecision",
    "TaskType",
    "TaskStatus",
    "ThinkingConfig",
    "AdaptiveThinking",
    "EnabledThinking",
    "DisabledThinking",
    "BackendText",
    "BackendToolCall",
    "BackendToolCallDelta",
    "BackendFinish",
    "BackendError",
    "BackendEvent",
    "create_text_delta",
    "create_thinking_delta",
    "create_tool_call_start",
    "create_tool_call_delta",
    "create_tool_call_end",
    "create_tool_progress",
    "create_tool_result",
    "create_permission_request",
    "create_finish",
    "create_backend_text",
    "create_backend_tool_call",
    "create_backend_tool_call_delta",
    "create_backend_finish",
    "create_backend_error",
]