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

# pkgutil-style namespace extension: the encre package spans the harness and
# core source trees; extend __path__ so core-provided subpackages resolve.
__path__ = __import__("pkgutil").extend_path(__path__, __name__)

# 鈹€鈹€ Minimal subprocess.Popen patch (Windows only) 鈹€鈹€
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
from encre.capabilities.search.codebase.indexer import EncreCodeIndex, ModuleInfo
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
from encre.improve.evolution.config import EvolutionConfig
from encre.improve.evolution.learner import EncreEvolutionLearner, ErrorRecord, SuccessRecord
from encre.improve.evolution.meta import CapabilityProfile, EncreMetaCognition
from encre.improve.evolution.optimizer import EncreStrategyOptimizer, ToolStrategy
from encre.improve.evolution.reflex import EncreReflexLoop, ReflexResult
from encre.improve.feedback.learner import CorrectionRecord, EncreFeedbackLearner
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
from encre.improve.learning import LearningEngine, SkillGenerator
from encre.improve.learning import MemoryConsolidator as LearningConsolidator
from encre.logging_config import get_logger, setup_logging
from encre.loop import EncreLoop
from encre.capabilities.search.lsp.client import EncreLSPClient
from encre.capabilities.search.lsp.manager import EncreLSPManager
from encre.capabilities.search.lsp.protocol import (
    Diagnostic as LSPDiagnostic,
)
from encre.capabilities.search.lsp.protocol import (
    HoverResult,
    LSPState,
    Position,
)
from encre.capabilities.search.lsp.protocol import (
    Location as LSPLocation,
)
from encre.capabilities.search.lsp.protocol import (
    Range as LSPRange,
)
from encre.memdir.semantic import (
    ConsolidationAction,
    MemoryConsolidator,
    SearchResult,
    SemanticMemorySearch,
    WorkingMemory,
)
from encre.migration import export_all, import_all
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
from encre.capabilities.process import create_subprocess_exec
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
    "classify_error",
    "ClassificationResult",
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
    "DangerLevel",
    "DeepSeekBackend",
    "DesktopLocateResult",
    "DesktopScreenState",
    "DisabledThinking",
    "EnabledThinking",
    "EncreAgent",
    "EncreAlwaysCompactStrategy",
    "EncreAutoCompactStrategy",
    "EncreAutoSafetyClassifier",
    "EncreBasePrompt",
    "EncreBlackboard",
    "EncreBrowserSession",
    "EncreBudgetReductionStrategy",
    "EncreCodeIndex",
    "EncreCodingPrompt",
    "EncreCompactEngine",
    "EncreConfig",
    "EncreConsensus",
    "EncreContainerSandbox",
    "EncreContextCollapseStrategy",
    "EncreDataPrompt",
    "EncreDesktopSession",
    "EncreEvolutionLearner",
    "EncreFeedbackLearner",
    "EncreGeneralPrompt",
    "EncreGitDiff",
    "EncreGitRepo",
    "EncreGoalLoop",
    "EncreGoalRunner",
    "EncreHookSystem",
    "EncreLSPClient",
    "EncreLSPManager",
    "EncreLoop",
    "EncreMCPTool",
    "EncreMailbox",
    "EncreMemorySystem",
    "EncreMetaCognition",
    "EncreMicroCompactStrategy",
    "EncreMultiStagePipeline",
    "EncreNotebookSession",
    "EncreOrchestrator",
    "EncrePlugin",
    "EncreProfileSystem",
    "EncrePromptBuilder",
    "EncrePromptTemplate",
    "EncreRateLimiter",
    "EncreReflexLoop",
    "EncreResearchPrompt",
    "EncreRollbackGit",
    "EncreSSRFGuard",
    "EncreSafetyEngine",
    "EncreScheduler",
    "EncreSemanticCompactStrategy",
    "EncreSession",
    "EncreSkillRegistry",
    "EncreSnipStrategy",
    "EncreSpecEngine",
    "EncreStrategyOptimizer",
    "EncreSwarmManager",
    "EncreSwarmSession",
    "EncreTask",
    "EncreTaskExecutor",
    "EncreTaskManager",
    "EncreTaskPlanner",
    "EncreTeammate",
    "EncreTelemetry",
    "EncreTokenBudgetStrategy",
    "EncreTool",
    "EntrypointResult",
    "ErrorCategory",
    "ErrorRecord",
    "ErrorRecoveryEngine",
    "ErrorClass",
    "EvolutionConfig",
    "FailoverBackend",
    "Finish",
    "FinishReason",
    "SystemMessage",
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
    "SkillGenerator",
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
    "encrypt",
    "encrypt_bytes",
    "ensure_keyfile",
    "export_all",
    "get_data_dir",
    "get_logger",
    "get_model",
    "get_provider",
    "import_all",
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
    "retry_with_backoff",
    "setup_logging",
]
