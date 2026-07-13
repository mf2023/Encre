#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
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

from __future__ import annotations

# ── Minimal subprocess.Popen patch (Windows only) ──
# We only patch Popen.__init__, the single universal entry point for
# ALL subprocess creation.  This catches every call path (third-party
# libraries, the indexer, any overlooked tool) so they never pop a
# visible console window on Windows.  Code that explicitly uses the
# _popen wrappers sets its own creationflags and is left alone.
# The patch is deliberately minimal: one function, one origin point.
import os as _os

if _os.name == "nt":
    import subprocess as _subprocess
    _orig = _subprocess.Popen.__init__
    def _make_patched(orig):
        _si = _subprocess.STARTUPINFO(
            dwFlags=_subprocess.STARTF_USESHOWWINDOW,
            wShowWindow=_subprocess.SW_HIDE,
        )
        def patched(self, args, **kwargs):
            kwargs.setdefault("creationflags", 0x08000000)
            kwargs.setdefault("startupinfo", _si)
            return orig(self, args, **kwargs)
        return patched
    _subprocess.Popen.__init__ = _make_patched(_orig)
    del _orig, _make_patched
del _os

from encre.adapters import (
    BaseAdapter,
    DingTalkAdapter,
    DiscordAdapter,
    EmailAdapter,
    FeishuAdapter,
    SignalAdapter,
    SlackAdapter,
    TelegramAdapter,
    WeComAdapter,
    WeixinAdapter,
    WhatsAppAdapter,
)
from encre.agent import EncreAgent
from encre.autosafety import (
    AutoDecision,
    ClassificationResult,
    EncreAutoSafetyClassifier,
    UserDecisionRecord,
)
from encre.backend import create_backend
from encre.backends.anthropic import AnthropicBackend
from encre.backends.auth import AuthManager
from encre.backends.base import BaseBackend
from encre.backends.bedrock import BedrockBackend
from encre.backends.catalog import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    catalog_payload,
    default_output_tokens,
    get_model,
    get_provider,
)
from encre.backends.catalog import (
    PROVIDERS as MODEL_PROVIDERS,
)
from encre.backends.connection import (
    ConnectionErrorCategory,
    ConnectionHealthMonitor,
    HeartbeatSession,
    format_connection_error,
)
from encre.backends.deepseek import DeepSeekBackend
from encre.backends.failover import BackendHealth, FailoverBackend
from encre.backends.google import GoogleBackend
from encre.backends.groq import GroqBackend
from encre.backends.local import LocalBackend
from encre.backends.ollama import OllamaBackend
from encre.backends.openai import OpenAIBackend
from encre.backends.openai_compatible import OpenAICompatibleBackend
from encre.backends.registry import BackendRegistry, ModelInfo
from encre.backends.retry import (
    DEFAULT_RETRY_CONFIG,
    ErrorClass,
    RetryConfig,
    RetryEvent,
    classify_error,
    retry_with_backoff,
)
from encre.backends.router import CostTracker, RouterBackend, TaskCategory
from encre.channels import Channel, EventRouter, TerminalChannel
from encre.codebase.indexer import EncreCodeIndex, ModuleInfo
from encre.compact.engine import EncreCompactEngine
from encre.compact.semantic import (
    ContextPartition,
    ContextPartitioner,
    ContextTier,
    SemanticToolOutputCompactor,
)
from encre.compact.strategies import (
    EncreAlwaysCompactStrategy,
    EncreAutoCompactStrategy,
    EncreBudgetReductionStrategy,
    EncreContextCollapseStrategy,
    EncreMicroCompactStrategy,
    EncreMultiStagePipeline,
    EncreSemanticCompactStrategy,
    EncreSnipStrategy,
    EncreTokenBudgetStrategy,
)
from encre.computer.browser import BrowserState, BrowserViewport, EncreBrowserSession
from encre.computer.desktop import (
    DesktopLocateResult,
    DesktopScreenState,
    EncreDesktopSession,
)
from encre.config import EncreConfig, ModelConfig, SubAgentConfig, get_data_dir
from encre.crypto import (
    decrypt,
    decrypt_bytes,
    encrypt,
    encrypt_bytes,
    ensure_keyfile,
)
from encre.evolution.config import EvolutionConfig
from encre.evolution.learner import EncreEvolutionLearner, ErrorRecord, SuccessRecord
from encre.evolution.meta import CapabilityProfile, EncreMetaCognition
from encre.evolution.optimizer import EncreStrategyOptimizer, ToolStrategy
from encre.evolution.reflex import EncreReflexLoop, ReflexResult
from encre.feedback.learner import CorrectionRecord, EncreFeedbackLearner
from encre.gateway import GatewayClient, GatewayServer
from encre.git.diff import EncreGitDiff, GitDiffResult
from encre.git.repo import EncreGitRepo, GitState
from encre.goal import (
    EncreGoalLoop,
    EncreGoalRunner,
    GoalDefinition,
    GoalEvent,
    GoalResult,
    GoalStatus,
)
from encre.hooks.system import EncreHookSystem
from encre.hooks.types import HookProgressEvent, HookResponseEvent, HookStartedEvent
from encre.iclaw import DaemonStats, IClawDaemon, IClawEngine, run_iclaw
from encre.learning import LearningEngine, SkillGenerator
from encre.learning import MemoryConsolidator as LearningConsolidator
from encre.logging_config import get_logger, setup_logging
from encre.loop import EncreLoop
from encre.lsp.client import EncreLSPClient
from encre.lsp.manager import EncreLSPManager
from encre.lsp.protocol import (
    Diagnostic as LSPDiagnostic,
)
from encre.lsp.protocol import (
    HoverResult,
    LSPState,
    Position,
)
from encre.lsp.protocol import (
    Location as LSPLocation,
)
from encre.lsp.protocol import (
    Range as LSPRange,
)
from encre.memdir.semantic import (
    ConsolidationAction,
    MemoryConsolidator,
    SearchResult,
    SemanticMemorySearch,
    WorkingMemory,
)
from encre.memdir.system import EncreMemorySystem, EntrypointResult, MemoryHeader
from encre.native import (
    apply_diff as native_apply_diff,
)
from encre.native import (
    compute_diff as native_compute_diff,
)
from encre.native import (
    count_tokens as native_count_tokens,
)
from encre.native import (
    execute_shell as native_shell_execute,
)
from encre.native import (
    glob_pattern as native_glob,
)
from encre.native import (
    grep as native_grep,
)
from encre.native import (
    read_file as native_read_file,
)
from encre.native import (
    sandbox_execute as native_sandbox_execute,
)
from encre.native import (
    search_codebase as native_search_codebase,
)
from encre.native import (
    write_file as native_write_file,
)
from encre.notebook.session import EncreNotebookSession
from encre.plugins.registry import PluginRegistry
from encre.plugins.types import EncrePlugin, PluginManifest, PluginSource
from encre.profile import EncreProfileSystem, UserProfile
from encre.prompts.base import EncreBasePrompt, EncrePromptTemplate
from encre.prompts.coding import EncreCodingPrompt
from encre.prompts.data import EncreDataPrompt
from encre.prompts.general import EncreGeneralPrompt
from encre.prompts.research import EncreResearchPrompt
from encre.prompts.system import EncrePromptBuilder
from encre.ratelimit import EncreRateLimiter, RateLimitResult
from encre.recovery import (
    ErrorCategory,
    ErrorRecoveryEngine,
    RecoveryAction,
    RecoveryDecision,
    RecoveryState,
    RetryableExecutor,
)
from encre.rollback import CommitEntry, EncreRollbackGit
from encre.rules.loader import RulesLoader
from encre.safety import (
    BashAnalysis,
    DangerLevel,
    EncreSafetyEngine,
    analyze_bash_command,
)
from encre.sandbox.container import EncreContainerSandbox
from encre.sandbox.types import (
    CGroupLimit,
    EnvConfig,
    FileProtection,
    FileProtectionConfig,
    NetworkConfig,
    NetworkPolicy,
    ResourceConfig,
    SandboxConfig,
    SandboxMode,
    SandboxResult,
    SeccompConfig,
    SeccompProfile,
)
from encre.scheduler import (
    CronSchedule,
    EncreScheduler,
    JobState,
    ScheduledJob,
    ScheduleType,
)
from encre.session import BranchMeta, EncreSession, SessionCheckpoint
from encre.skills.bundled import create_bundled_skills
from encre.skills.registry import EncreSkillRegistry
from encre.skills.types import BundledSkillDefinition
from encre.soul.system import EncreSoulSystem, SoulFiles
from encre.spec import EncreSpecEngine, SpecDocument, SpecSection, SpecStatus
from encre.ssrf import EncreSSRFGuard
from encre.swarm.blackboard import BlackboardEntry, EncreBlackboard
from encre.swarm.consensus import ConsensusResult, EncreConsensus, Proposal, Vote
from encre.swarm.mailbox import EncreMailbox, MailboxMessage
from encre.swarm.manager import EncreSwarmManager, SwarmProgress
from encre.swarm.orchestrator import EncreOrchestrator, OrchestrationEvent
from encre.swarm.planner import EncreTaskPlanner, TaskNode, TaskTree
from encre.swarm.roles import AgentRole, RoleRegistry
from encre.swarm.session import EncreSwarmSession, SwarmEvent, SwarmResult
from encre.swarm.teammate import EncreTeammate, TeammateHandle
from encre.task.executor import EncreTaskExecutor
from encre.task.manager import EncreTaskManager
from encre.task.types import EncreTask
from encre.telemetry import EncreTelemetry, RetryRecord, ToolCallRecord, TurnRecord
from encre.tools.base import EncreTool
from encre.tools.builtin import (
    EncreAgentTool,
    EncreApplyPatchTool,
    EncreBashKillTool,
    EncreBashListTool,
    EncreBashOutputTool,
    EncreBashTool,
    EncreBrowserTool,
    EncreCronCreateTool,
    EncreCronDeleteTool,
    EncreCronListTool,
    EncreDatabaseTool,
    EncreDeployTool,
    EncreDesktopTool,
    EncreDockerTool,
    EncreFileEditTool,
    EncreFileReadTool,
    EncreFileWriteTool,
    EncreFindToolTool,
    EncreGitTool,
    EncreGlobTool,
    EncreGrepTool,
    EncreImageTool,
    EncreInfoTool,
    EncreLSPTool,
    EncrePDFTool,
    EncreRESTTool,
    EncreSpreadsheetTool,
    EncreTaskCreateTool,
    EncreTaskGetTool,
    EncreTaskListTool,
    EncreTaskOutputTool,
    EncreTaskStopTool,
    EncreTaskUpdateTool,
    EncreTodoTool,
    EncreWebFetchTool,
    EncreWebSearchTool,
)
from encre.tools.builtin._popen import create_subprocess_exec
from encre.tools.builtin.notebook import EncreNotebookTool
from encre.tools.discovery import BASE_TOOLS, ToolDiscovery
from encre.tools.mcp import EncreMCPTool
from encre.tools.mcp_manager import (
    MCPManager,
    MCPServerSpec,
    bootstrap_mcp_servers,
    default_mcp_config_path,
)
from encre.tools.registry import ToolRegistry
from encre.utils.idgen import BranchIDGenerator
from encre.utils.types import (
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
    SystemMessage,
    PermissionAllow,
    PermissionAsk,
    PermissionBehavior,
    PermissionDecision,
    PermissionDeny,
    PermissionMode,
    PermissionRequest,
    PlanUpdate,
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
    create_system_message,
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
    "BASE_TOOLS",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "DEFAULT_RETRY_CONFIG",
    "MODEL_PROVIDERS",
    "AdaptiveThinking",
    "AgentRole",
    "AnthropicBackend",
    "AutoDecision",
    "AuthManager",
    "BackendError",
    "BackendEvent",
    "BackendFinish",
    "BackendHealth",
    "BackendRegistry",
    "BackendText",
    "BackendToolCall",
    "BackendToolCallDelta",
    "BaseAdapter",
    "BaseBackend",
    "BashAnalysis",
    "BedrockBackend",
    "BlackboardEntry",
    "BranchIDGenerator",
    "BranchMeta",
    "BrowserState",
    "BrowserViewport",
    "BundledSkillDefinition",
    "CapabilityProfile",
    "Channel",
    "classify_error",
    "ClassificationResult",
    "ClientMessage",
    "ConnectionErrorCategory",
    "ConnectionHealthMonitor",
    "format_connection_error",
    "CommitEntry",
    "ConsensusResult",
    "ConsolidationAction",
    "ContextPartition",
    "ContextPartitioner",
    "ContextTier",
    "CorrectionRecord",
    "CostTracker",
    "CronSchedule",
    "DaemonStats",
    "DangerLevel",
    "DeepSeekBackend",
    "DesktopLocateResult",
    "DesktopScreenState",
    "DingTalkAdapter",
    "DisabledThinking",
    "DiscordAdapter",
    "EmailAdapter",
    "EnabledThinking",
    "EncreAgent",
    "EncreAgentTool",
    "EncreAlwaysCompactStrategy",
    "EncreApplyPatchTool",
    "EncreAutoCompactStrategy",
    "EncreAutoSafetyClassifier",
    "EncreBasePrompt",
    "EncreBashKillTool",
    "EncreBashListTool",
    "EncreBashOutputTool",
    "EncreBashTool",
    "EncreBlackboard",
    "EncreBrowserSession",
    "EncreBrowserTool",
    "EncreBudgetReductionStrategy",
    "EncreCodeIndex",
    "EncreCodingPrompt",
    "EncreCompactEngine",
    "EncreConfig",
    "EncreConsensus",
    "EncreContainerSandbox",
    "EncreContextCollapseStrategy",
    "EncreCronCreateTool",
    "EncreCronDeleteTool",
    "EncreCronListTool",
    "EncreDataPrompt",
    "EncreDatabaseTool",
    "EncreDeployTool",
    "EncreDesktopSession",
    "EncreDesktopTool",
    "EncreDockerTool",
    "EncreEvolutionLearner",
    "EncreFeedbackLearner",
    "EncreFileEditTool",
    "EncreFileReadTool",
    "EncreFileWriteTool",
    "EncreFindToolTool",
    "EncreGeneralPrompt",
    "EncreGitDiff",
    "EncreGitRepo",
    "EncreGitTool",
    "EncreGlobTool",
    "EncreGoalLoop",
    "EncreGoalRunner",
    "EncreGrepTool",
    "EncreHookSystem",
    "EncreImageTool",
    "EncreInfoTool",
    "EncreLSPClient",
    "EncreLSPManager",
    "EncreLSPTool",
    "EncreLoop",
    "EncreMCPTool",
    "EncreMailbox",
    "EncreMemorySystem",
    "EncreMetaCognition",
    "EncreMicroCompactStrategy",
    "EncreMultiStagePipeline",
    "EncreNotebookSession",
    "EncreNotebookTool",
    "EncreOrchestrator",
    "EncrePDFTool",
    "EncrePlugin",
    "EncreProfileSystem",
    "EncrePromptBuilder",
    "EncrePromptTemplate",
    "EncreRESTTool",
    "EncreRateLimiter",
    "EncreReflexLoop",
    "EncreResearchPrompt",
    "EncreRollbackGit",
    "EncreSSRFGuard",
    "EncreSafetyEngine",
    "EncreScheduler",
    "EncreSemanticCompactStrategy",
    "EncreServer",
    "EncreSession",
    "EncreSkillRegistry",
    "EncreSnipStrategy",
    "EncreSpecEngine",
    "EncreSpreadsheetTool",
    "EncreStrategyOptimizer",
    "EncreSwarmManager",
    "EncreSwarmSession",
    "EncreTask",
    "EncreTaskCreateTool",
    "EncreTaskExecutor",
    "EncreTaskGetTool",
    "EncreTaskListTool",
    "EncreTaskManager",
    "EncreTaskOutputTool",
    "EncreTaskPlanner",
    "EncreTaskStopTool",
    "EncreTaskUpdateTool",
    "EncreTeammate",
    "EncreTelemetry",
    "EncreTodoTool",
    "EncreTokenBudgetStrategy",
    "EncreTool",
    "EncreWSHandler",
    "EncreWebFetchTool",
    "EncreWebSearchTool",
    "EntrypointResult",
    "ErrorCategory",
    "ErrorRecord",
    "ErrorRecoveryEngine",
    "ErrorClass",
    "EventRouter",
    "EvolutionConfig",
    "FailoverBackend",
    "FeishuAdapter",
    "Finish",
    "FinishReason",
    "SystemMessage",
    "GatewayClient",
    "GatewayServer",
    "GitDiffResult",
    "GitState",
    "GoalDefinition",
    "GoalEvent",
    "GoalResult",
    "GoalStatus",
    "GoogleBackend",
    "GroqBackend",
    "HeartbeatSession",
    "HookProgressEvent",
    "HookResponseEvent",
    "HookStartedEvent",
    "HoverResult",
    "IClawDaemon",
    "IClawEngine",
    "JobState",
    "LSPDiagnostic",
    "LSPLocation",
    "LSPRange",
    "LSPState",
    "LearningConsolidator",
    "LearningEngine",
    "LocalBackend",
    "MCPManager",
    "MCPServerSpec",
    "MailboxMessage",
    "MemoryConsolidator",
    "MemoryHeader",
    "ModelConfig",
    "ModelInfo",
    "ModuleInfo",
    "OllamaBackend",
    "OpenAIBackend",
    "OpenAICompatibleBackend",
    "OrchestrationEvent",
    "PermissionAllow",
    "PermissionAsk",
    "PermissionBehavior",
    "PermissionDecision",
    "PermissionDeny",
    "PermissionMode",
    "PermissionRequest",
    "PlanUpdate",
    "PluginManifest",
    "PluginRegistry",
    "PluginSource",
    "Position",
    "Proposal",
    "RateLimitResult",
    "RecoveryAction",
    "RecoveryDecision",
    "RecoveryState",
    "ReflexResult",
    "RetryConfig",
    "RetryEvent",
    "RetryRecord",
    "RetryableExecutor",
    "RoleRegistry",
    "RouterBackend",
    "RulesLoader",
    "SandboxConfig",
    "SandboxResult",
    "ScheduleType",
    "ScheduledJob",
    "SearchResult",
    "SemanticMemorySearch",
    "SemanticToolOutputCompactor",
    "SessionCheckpoint",
    "SessionInfo",
    "SessionManager",
    "SignalAdapter",
    "SkillGenerator",
    "SlackAdapter",
    "SpecDocument",
    "SpecSection",
    "SpecStatus",
    "SuccessRecord",
    "SwarmEvent",
    "SwarmProgress",
    "SwarmResult",
    "TaskCategory",
    "TaskNode",
    "TaskStatus",
    "TaskTree",
    "TaskType",
    "TeammateHandle",
    "TelegramAdapter",
    "TerminalChannel",
    "TextDelta",
    "ThinkingConfig",
    "ThinkingDelta",
    "ToolCallDelta",
    "ToolCallEnd",
    "ToolCallRecord",
    "ToolCallStart",
    "ToolDiscovery",
    "ToolProgress",
    "ToolRegistry",
    "ToolResult",
    "ToolStrategy",
    "TurnRecord",
    "UserDecisionRecord",
    "UserProfile",
    "Vote",
    "WeComAdapter",
    "WeixinAdapter",
    "WhatsAppAdapter",
    "WorkingMemory",
    "analyze_bash_command",
    "bootstrap_mcp_servers",
    "catalog_payload",
    "create_backend",
    "create_backend_error",
    "create_backend_finish",
    "create_backend_text",
    "create_backend_tool_call",
    "create_backend_tool_call_delta",
    "create_bundled_skills",
    "create_finish",
    "create_system_message",
    "create_permission_request",
    "create_text_delta",
    "create_thinking_delta",
    "create_tool_call_delta",
    "create_tool_call_end",
    "create_tool_call_start",
    "create_tool_progress",
    "create_tool_result",
    "decrypt",
    "decrypt_bytes",
    "default_mcp_config_path",
    "default_output_tokens",
    "encode_server_message",
    "encrypt",
    "encrypt_bytes",
    "ensure_keyfile",
    "get_data_dir",
    "get_logger",
    "get_model",
    "get_provider",
    "handle_admin",
    "native_apply_diff",
    "native_compute_diff",
    "native_count_tokens",
    "native_glob",
    "native_grep",
    "native_read_file",
    "native_sandbox_execute",
    "native_search_codebase",
    "native_shell_execute",
    "native_write_file",
    "parse_client_message",
    "retry_with_backoff",
    "run_iclaw",
    "run_server",
    "setup_logging",
]

# Lazy imports for server module (avoids RuntimeWarning when running python -m encre.server.app)
_server_lazy_map = {
    "EncreServer": ("encre.server.app", "EncreServer"),
    "run_server": ("encre.server.app", "run_server"),
    "ClientMessage": ("encre.server.protocol", "ClientMessage"),
    "parse_client_message": ("encre.server.protocol", "parse_client_message"),
    "encode_server_message": ("encre.server.protocol", "encode_server_message"),
    "EncreWSHandler": ("encre.server.ws", "EncreWSHandler"),
    "handle_admin": ("encre.server.admin", "handle_admin"),
    "SessionManager": ("encre.server.session_manager", "SessionManager"),
    "SessionInfo": ("encre.server.session_manager", "SessionInfo"),
}

def __getattr__(name):
    if name in _server_lazy_map:
        import importlib
        mod_path, attr = _server_lazy_map[name]
        return getattr(importlib.import_module(mod_path), attr)
    raise AttributeError(f"module 'encre' has no attribute '{name}'")
