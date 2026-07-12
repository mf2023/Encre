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

import json
import re
import shlex
import unicodedata
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, ClassVar

from encre.autosafety import EncreAutoSafetyClassifier
from encre.config import EncreConfig
from encre.sandbox.container import EncreContainerSandbox
from encre.sandbox.types import (
    EnvConfig,
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
from encre.ssrf import EncreSSRFGuard
from encre.utils.types import (
    PermissionAllow,
    PermissionAsk,
    PermissionDecision,
    PermissionDeny,
)


class DangerLevel(Enum):
    SAFE = auto()        # Read-only, no side effects
    LOW = auto()         # Writes to project directory only
    MEDIUM = auto()      # Writes outside project, network access
    HIGH = auto()        # System modification, privilege escalation
    CRITICAL = auto()    # Data destruction, reverse shells, kernel access


@dataclass
class BashAnalysis:
    """Result of static analysis on a bash command."""
    command: str
    danger_level: DangerLevel = DangerLevel.SAFE
    injection_detected: bool = False
    injection_details: list[str] = field(default_factory=list)
    contains_substitution: bool = False
    contains_redirect: bool = False
    contains_pipe: bool = False
    contains_chained_command: bool = False
    contains_network_access: bool = False
    contains_file_write: bool = False
    contains_system_modification: bool = False
    contains_privilege_escalation: bool = False
    contains_encoded_content: bool = False
    contains_unicode_homoglyph: bool = False
    write_targets: list[str] = field(default_factory=list)
    network_targets: list[str] = field(default_factory=list)
    subcommands: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# Immune paths -- always-deny for destructive ops even in bypass mode
# ═══════════════════════════════════════════════════════════════════════════

# Path fragments (normalized forward-slash, lowercased) that must never be
# touched by a destructive tool call, regardless of permission mode.  These
# cover agent/runtime config (``.git/``, ``.claude/``), shell init files
# (``~/.bashrc`` etc., hijackable on next shell spawn), and SSH credentials
# (``~/.ssh/``, exfiltration / forgery risk).  Read access to these is left
# to the Rust engine; this layer only guards writes/deletes.
IMMUNE_PATH_FRAGMENTS: tuple[str, ...] = (
    "/.git/",          # git internal dir (HEAD/refs/objects/config)
    "/.claude/",       # agent config dir
    "/.ssh/",          # SSH keys / known_hosts
    "/.bashrc",
    "/.zshrc",
    "/.bash_profile",
    "/.zprofile",
    "/.gitconfig",
)

# Bare filenames (no slash) matched at the path tail, for home-relative files
# when the path is exactly ``~/.bashrc`` etc.
IMMUNE_PATH_BASENAMES: tuple[str, ...] = (
    ".bashrc",
    ".zshrc",
    ".bash_profile",
    ".zprofile",
    ".gitconfig",
)

# Tool names whose primary effect is mutating the filesystem; used as a
# fallback when the tool object is unavailable and ``is_destructive`` cannot
# be probed directly.
_WRITE_TOOL_NAMES: frozenset[str] = frozenset({
    "file_write", "write_file", "file_edit", "edit_file", "file_delete",
    "delete_file", "apply_patch", "patch", "bash", "shell", "execute",
    "git_tool", "git", "mv", "cp", "rm", "sed", "tee",
})


def _normalize_path_for_immune_check(raw: str) -> str:
    """Expand ``~`` / strip quotes / forward-slash-normalize a path fragment."""
    import os

    norm = os.path.expanduser(raw.strip().strip("'\""))
    return norm.replace("\\", "/").lower()


def _extract_tool_target_paths(tool_name: str, tool_input: dict[str, Any]) -> list[str]:
    """Pull path-like strings out of a tool call for immune-path matching.

    Covers direct path fields used by the file family, ``+++ b/...`` markers
    from unified diffs (``apply_patch``), and bash redirect / mv / cp / rm /
    tee targets.  Not exhaustive -- false negatives simply fall through to the
    normal permission path, never a false allow.
    """
    out: list[str] = []
    for key in ("path", "file_path", "filename", "filepath", "target", "dest", "destination"):
        val = tool_input.get(key)
        if isinstance(val, str) and val.strip():
            out.append(val)

    patch = tool_input.get("patch") or tool_input.get("diff")
    if isinstance(patch, str):
        for m in re.finditer(r"^\+\+\+\s+b/(.+)$", patch, re.MULTILINE):
            out.append(m.group(1).strip())
        for m in re.finditer(r"^---\s+a/(.+)$", patch, re.MULTILINE):
            out.append(m.group(1).strip())

    cmd = tool_input.get("command") or tool_input.get("cmd")
    if isinstance(cmd, str) and cmd.strip():
        # Redirect targets:  >foo  >>foo  (write/append)
        for m in re.finditer(r"(?:>>?|tee(?:\s+-a)?)\s*([^\s|;&<>]+)", cmd):
            out.append(m.group(1))
        # mv / cp destination (second path argument).
        for m in re.finditer(r"\b(?:mv|cp)\s+(?:-[rRfv]+\s+)?(\S+)\s+(\S+)", cmd):
            out.append(m.group(2))
        # rm / rmdir target.
        for m in re.finditer(r"\b(?:rm|rmdir)\s+(?:-[rRfv]+\s+)?(\S+)", cmd):
            out.append(m.group(1))
        # sed -i edits its target argument.
        for m in re.finditer(r"\bsed\s+.*?-i\b\s*\S*\s+(\S+)", cmd):
            out.append(m.group(1))
        # Raw tokens that visibly reference an immune dir (defensive catch-all).
        for tok in re.split(r"\s+", cmd):
            if any(frag in tok for frag in (".git/", ".ssh/", ".claude/", ".bashrc", ".zshrc", ".gitconfig")):
                out.append(tok)
    return out


def matches_immune_path(raw_path: str) -> str | None:
    """Return the matched immune fragment, or ``None`` if the path is clean."""
    if not raw_path or not raw_path.strip():
        return None
    norm = _normalize_path_for_immune_check(raw_path)
    if not norm:
        return None
    # Ensure a leading slash so fragment matching is unambiguous when the
    # caller passes a bare relative path like ".git/config".
    probe = norm if norm.startswith("/") else "/" + norm
    for frag in IMMUNE_PATH_FRAGMENTS:
        if frag in probe:
            return frag.strip("/")
    # Basename match at tail (e.g. "~/x/.bashrc" or "~/.bashrc").
    tail = norm.rsplit("/", 1)[-1]
    if tail in IMMUNE_PATH_BASENAMES:
        return tail
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Injection detection patterns -- 30+ categories
# ═══════════════════════════════════════════════════════════════════════════

# Command substitution (primary injection vector)
_RE_COMMAND_SUBSTITUTION_DOLLAR = re.compile(r'\$\(.+\)', re.DOTALL)
_RE_COMMAND_SUBSTITUTION_BACKTICK = re.compile(r'`[^`]+`')
_RE_PROCESS_SUBSTITUTION = re.compile(r'[<(]\([^)]+\)')

# Destructive file operations
_RE_RM_RF_ROOT = re.compile(r'\brm\s+.*-(?:[a-z]*r[a-z]*f|rf).*/(?:\s|$)', re.IGNORECASE)
_RE_RM_RF_HOME = re.compile(r'\brm\s+.*-(?:[a-z]*r[a-z]*f|rf)\s+~', re.IGNORECASE)
_RE_RM_STAR = re.compile(r'\brm\s+.*-(?:[a-z]*r[a-z]*f|rf)\s+\*', re.IGNORECASE)
_RE_MKFS = re.compile(r'\bmkfs\.?\w*\s', re.IGNORECASE)
_RE_DD_WRITE = re.compile(r'\bdd\s+if=.*\s+of=', re.IGNORECASE)
_RE_REDIRECT_DEV = re.compile(r'>\s*/dev/(?:sd[a-z]+|nvme\d+n\d+|mmcblk\d+)', re.IGNORECASE)
_RE_REDIRECT_DISK = re.compile(r'>\s*/dev/(?:disk|block|mapper)/', re.IGNORECASE)
_RE_REDIRECT_ETC = re.compile(r'>\s*/etc/(?:passwd|shadow|sudoers|hosts|resolv\.conf)', re.IGNORECASE)
_RE_REDIRECT_SYSTEM = re.compile(r'>\s*/(?:etc|boot|sys|proc|dev)/', re.IGNORECASE)

# Privilege escalation
_RE_SUDO = re.compile(r'\bsudo\b', re.IGNORECASE)
_RE_CHMOD_777_ROOT = re.compile(r'\bchmod\s+.*777\s+/', re.IGNORECASE)
_RE_CHMOD_777 = re.compile(r'\bchmod\s+.*777\b', re.IGNORECASE)
_RE_CHOWN_ROOT = re.compile(r'\bchown\s+.*root', re.IGNORECASE)
_RE_SU = re.compile(r'\bsu\s+-', re.IGNORECASE)
_RE_SETUID = re.compile(r'\bchmod\s+[0-7]*[456][0-7]{2}\b', re.IGNORECASE)

# Fork bombs
_RE_FORK_BOMB = re.compile(r':\(\)\s*\{[^}]*:\|[^}]*:[^}]*\}', re.IGNORECASE)
_RE_FORK_BOMB_VAR = re.compile(r'(\w+)\s*\(\s*\)\s*\{\s*[^}]*\1\s*\|', re.IGNORECASE)

# Reverse shells and network exploitation
_RE_REVERSE_SHELL_BASH = re.compile(r'\bbash\s+-i\s*>&.*0>&1', re.IGNORECASE)
_RE_REVERSE_SHELL_NC = re.compile(r'\bnc\s+.*-(?:e|(?:l|n)vp?)\s', re.IGNORECASE)
_RE_REVERSE_SHELL_PYTHON = re.compile(
    r'python[23]?\s+-c\s+.*socket\.(?:socket|connect)', re.IGNORECASE
)
_RE_REVERSE_SHELL_SOCAT = re.compile(r'\bsocat\s+.*exec:', re.IGNORECASE)
_RE_REVERSE_SHELL_TELNET = re.compile(r'\btelnet\s+.*(?:/bin/sh|/bin/bash|cmd)', re.IGNORECASE)
_RE_BIND_SHELL = re.compile(r'\bnc\s+-[lL].*-p\s+\d+\s+-e', re.IGNORECASE)
_RE_CURL_PIPE_SHELL = re.compile(r'\bcurl\s+\S+.*\|\s*(?:ba)?sh\b', re.IGNORECASE)
_RE_WGET_PIPE_SHELL = re.compile(r'\bwget\s+\S+.*-O\s*-\s*\|\s*(?:ba)?sh\b', re.IGNORECASE)

# Encoded/obfuscated content (evasion techniques)
_RE_BASE64_EVAL = re.compile(r'\bbase64\s+.*\|.*(?:ba)?sh\b', re.IGNORECASE)
_RE_BASE64_DECODE = re.compile(r'\bbase64\s+(?:-d|--decode)', re.IGNORECASE)
_RE_HEX_EVAL = re.compile(r'\bxxd\s+.*-r.*(?:ba)?sh\b', re.IGNORECASE)
_RE_EVAL = re.compile(r'\beval\s', re.IGNORECASE)
_RE_EXEC = re.compile(r'\bexec\s+\d*>&\d*', re.IGNORECASE)

# System modification
_RE_SYSTEMCTL = re.compile(r'\bsystemctl\s+(?:stop|disable|mask)\s', re.IGNORECASE)
_RE_SERVICE = re.compile(r'\bservice\s+\S+\s+stop\b', re.IGNORECASE)
_RE_MODPROBE = re.compile(r'\bmodprobe\s+-r\s', re.IGNORECASE)
_RE_KILL = re.compile(r'\bkill\s+-9\s', re.IGNORECASE)
_RE_PKILL = re.compile(r'\bpkill\s', re.IGNORECASE)
_RE_MOUNT = re.compile(r'\bmount\s', re.IGNORECASE)
_RE_UMOUNT = re.compile(r'\bumount\s', re.IGNORECASE)
_RE_CRONTAB_MODIFY = re.compile(r'\bcrontab\s+-', re.IGNORECASE)
_RE_AT_CMD = re.compile(r'\bat\s+\d', re.IGNORECASE)
_RE_IPTABLES = re.compile(r'\biptables\s+-[ADIF]', re.IGNORECASE)

# Information disclosure
_RE_CAT_SHADOW = re.compile(r'\bcat\s+/etc/(?:shadow|passwd)\b', re.IGNORECASE)
_RE_CAT_SSH_KEY = re.compile(r'\bcat\s+.*\.ssh/', re.IGNORECASE)
_RE_READ_ENV = re.compile(r'\bcat\s+.*\.env\b', re.IGNORECASE)

# Variable expansion trickery (PATH manipulation, etc.)
_RE_PATH_VAR_MANIP = re.compile(r'\$\{(?:PATH|HOME|SHELL|IFS)[:#%/]', re.IGNORECASE)
_RE_IFS_MANIP = re.compile(r'\bIFS\s*=', re.IGNORECASE)

# Network: data exfiltration
_RE_NETCAT_SEND = re.compile(r'\bnc\s+\S+\s+\d+\s*<', re.IGNORECASE)
_RE_CURL_UPLOAD = re.compile(r'\bcurl\s+.*-F\s+\S+@\S+', re.IGNORECASE)
_RE_SCP = re.compile(r'\bscp\s+\S+@', re.IGNORECASE)
_RE_SSH_TUNNEL = re.compile(r'\bssh\s+-[DRL]\s', re.IGNORECASE)


def analyze_bash_command(command: str) -> BashAnalysis:
    """Perform multi-layer static analysis of a shell command.

    Layer 1: Tokenization via shlex (catches syntax-level tricks)
    Layer 2: Unicode homoglyph detection
    Layer 3: Regex pattern matching (30+ patterns)
    Layer 4: Subcommand extraction and per-subcommand checking
    Layer 5: Danger level classification
    """
    analysis = BashAnalysis(command=command)

    # ── Layer 1: Tokenization ──
    try:
        tokens = shlex.split(command)
        analysis.subcommands = []
        for tok in tokens:
            if (not tok.startswith("-") and "/" not in tok[:
                2]) or tok.startswith("--"):
                analysis.subcommands.append(tok)
    except ValueError:
        analysis.injection_detected = True
        analysis.injection_details.append("Unterminated quote or illegal token")

    # ── Layer 2: Unicode homoglyph detection ──
    for i, ch in enumerate(command):
        cat = unicodedata.category(ch)
        # Cf = format characters (zero-width spaces, BOM, etc.)
        # Cc = control characters (except common whitespace)
        if cat == "Cf":
            analysis.contains_unicode_homoglyph = True
            analysis.injection_detected = True
            analysis.injection_details.append(
                f"Unicode format character U+{ord(ch):04X} at position {i}"
            )
        elif cat == "Cc" and ch not in ("\n", "\r", "\t"):
            analysis.contains_unicode_homoglyph = True
            analysis.injection_detected = True
            analysis.injection_details.append(
                f"Control character U+{ord(ch):04X} at position {i}"
            )

    # ── Layer 3: Pattern matching ──

    # Command substitution
    if _RE_COMMAND_SUBSTITUTION_DOLLAR.search(command):
        analysis.contains_substitution = True
    if _RE_COMMAND_SUBSTITUTION_BACKTICK.search(command):
        analysis.contains_substitution = True
    if _RE_PROCESS_SUBSTITUTION.search(command):
        analysis.contains_substitution = True

    # Pipes
    if "|" in command and not _RE_FORK_BOMB.search(command):
        analysis.contains_pipe = True

    # Chained commands
    if re.search(r'[;&](?:\s*\n?\s*)(?:rm|dd|mkfs|chmod|chown|kill|reboot|shutdown)', command, re.IGNORECASE):
        analysis.contains_chained_command = True

    # Destructive file ops
    for pattern, desc in [
        (_RE_RM_RF_ROOT, "rm -rf on root path"),
        (_RE_RM_RF_HOME, "rm -rf on home directory"),
        (_RE_RM_STAR, "rm -rf * (recursive delete all)"),
        (_RE_MKFS, "mkfs (filesystem format)"),
        (_RE_DD_WRITE, "dd write to block device"),
        (_RE_REDIRECT_DEV, "redirect to device"),
        (_RE_REDIRECT_DISK, "redirect to disk"),
        (_RE_REDIRECT_ETC, "redirect overwrite system config"),
        (_RE_REDIRECT_SYSTEM, "redirect overwrite system path"),
    ]:
        if pattern.search(command):
            analysis.contains_file_write = True
            analysis.injection_details.append(desc)
            analysis.injection_detected = True

    # Privilege escalation
    if _RE_SUDO.search(command):
        analysis.contains_privilege_escalation = True
        analysis.injection_details.append("sudo detected")
    for pattern, desc in [
        (_RE_CHMOD_777_ROOT, "chmod 777 on root path"),
        (_RE_CHMOD_777, "chmod 777 (world-writable)"),
        (_RE_CHOWN_ROOT, "chown to root"),
        (_RE_SU, "su - (switch user)"),
        (_RE_SETUID, "setuid/setgid bit set"),
    ]:
        if pattern.search(command):
            analysis.contains_privilege_escalation = True
            analysis.contains_system_modification = True
            analysis.injection_details.append(desc)
            analysis.injection_detected = True

    # Fork bombs
    if _RE_FORK_BOMB.search(command):
        analysis.injection_details.append("fork bomb detected")
        analysis.injection_detected = True

    # Reverse shells
    for pattern, desc in [
        (_RE_REVERSE_SHELL_BASH, "bash reverse shell"),
        (_RE_REVERSE_SHELL_NC, "netcat reverse shell"),
        (_RE_REVERSE_SHELL_PYTHON, "Python reverse shell"),
        (_RE_REVERSE_SHELL_SOCAT, "socat reverse shell"),
        (_RE_REVERSE_SHELL_TELNET, "telnet reverse shell"),
        (_RE_BIND_SHELL, "netcat bind shell"),
    ]:
        if pattern.search(command):
            analysis.contains_network_access = True
            analysis.injection_details.append(desc)
            analysis.injection_detected = True

    # Pipe to shell (curl/wget | bash)
    if _RE_CURL_PIPE_SHELL.search(command):
        analysis.contains_network_access = True
        analysis.injection_details.append("curl piped to shell -- code execution from network")
        analysis.injection_detected = True
    if _RE_WGET_PIPE_SHELL.search(command):
        analysis.contains_network_access = True
        analysis.injection_details.append("wget piped to shell -- code execution from network")
        analysis.injection_detected = True

    # Encoded/obfuscated content
    for pattern, desc in [
        (_RE_BASE64_EVAL, "base64 piped to shell"),
        (_RE_BASE64_DECODE, "base64 decode"),
        (_RE_HEX_EVAL, "hex decode piped to shell"),
        (_RE_EVAL, "eval command"),
        (_RE_EXEC, "exec with redirection"),
    ]:
        if pattern.search(command):
            analysis.contains_encoded_content = True
            analysis.injection_details.append(desc)
            analysis.injection_detected = True

    # System modification
    for pattern, desc in [
        (_RE_SYSTEMCTL, "systemctl stop/disable"),
        (_RE_SERVICE, "service stop"),
        (_RE_MODPROBE, "modprobe -r (remove kernel module)"),
        (_RE_KILL, "kill -9 (force kill)"),
        (_RE_PKILL, "pkill"),
        (_RE_MOUNT, "mount"),
        (_RE_UMOUNT, "umount"),
        (_RE_CRONTAB_MODIFY, "crontab modification"),
        (_RE_AT_CMD, "at command (scheduled execution)"),
        (_RE_IPTABLES, "iptables modification"),
    ]:
        if pattern.search(command):
            analysis.contains_system_modification = True
            analysis.injection_details.append(desc)
            analysis.injection_detected = True

    # Information disclosure (read-only -- does not affect contains_file_write)
    for pattern, desc in [
        (_RE_CAT_SHADOW, "read /etc/shadow or /etc/passwd"),
        (_RE_CAT_SSH_KEY, "read SSH private keys"),
        (_RE_READ_ENV, "read .env secrets"),
    ]:
        if pattern.search(command):
            analysis.injection_details.append(desc)
            analysis.injection_detected = True

    # Variable manipulation tricks
    if _RE_PATH_VAR_MANIP.search(command):
        analysis.injection_details.append("PATH variable manipulation")
        analysis.injection_detected = True
    if _RE_IFS_MANIP.search(command):
        analysis.injection_details.append("IFS manipulation attempt")
        analysis.injection_detected = True

    # Data exfiltration
    for pattern, desc in [
        (_RE_NETCAT_SEND, "netcat data exfiltration"),
        (_RE_CURL_UPLOAD, "curl file upload"),
        (_RE_SCP, "scp to remote host"),
        (_RE_SSH_TUNNEL, "SSH tunnel"),
    ]:
        if pattern.search(command):
            analysis.contains_network_access = True
            analysis.injection_details.append(desc)

    # Network detection (broad, lower priority)
    if re.search(r'\b(curl|wget|nc|ncat|socat)\s', command, re.IGNORECASE):
        analysis.contains_network_access = True

    # ── Layer 4: Danger level classification ──
    if analysis.injection_details:
        critical_patterns = [
            "reverse shell", "bind shell", "fork bomb", "rm -rf on root",
            "mkfs", "dd write", "curl piped to shell", "wget piped to shell",
            "redirect to device", "redirect to disk", "modprobe -r",
        ]
        if any(p in " ".join(analysis.injection_details).lower() for p in critical_patterns):
            analysis.danger_level = DangerLevel.CRITICAL
        elif analysis.contains_privilege_escalation or analysis.contains_system_modification:
            analysis.danger_level = DangerLevel.HIGH
        elif analysis.contains_file_write or analysis.contains_network_access:
            analysis.danger_level = DangerLevel.MEDIUM
        else:
            analysis.danger_level = DangerLevel.LOW
    elif analysis.contains_network_access and analysis.contains_pipe:
        analysis.danger_level = DangerLevel.MEDIUM
    elif analysis.contains_network_access:
        analysis.danger_level = DangerLevel.LOW
    elif analysis.contains_file_write:
        analysis.danger_level = DangerLevel.MEDIUM
    else:
        analysis.danger_level = DangerLevel.SAFE

    return analysis


class EncreSafetyEngine:
    def __init__(
        self,
        config: EncreConfig,
        sandbox_enabled: bool = False,
        sandbox_config: SandboxConfig | None = None,
        workspace: str = "",
        auto_classifier: EncreAutoSafetyClassifier | None = None,
    ) -> None:
        self.config = config

        # Load dangerous command patterns from file if not already set
        if not config.dangerous_command_patterns:
            patterns_path = Path(__file__).parent / "dangerous_commands.txt"
            if patterns_path.exists():
                loaded: list[str] = []
                for line in patterns_path.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#") and not stripped.startswith("["):
                        loaded.append(stripped)
                config.dangerous_command_patterns = loaded

        self._sensitive_patterns: list[re.Pattern[str]] = [
            re.compile(r"(?:api[_-]?key|apikey|secret|password|token|credential|AUTH_TOKEN|PRIVATE_KEY|AWS_SECRET|GITHUB_TOKEN)", re.IGNORECASE),
        ]

        self.sandbox_enabled = sandbox_enabled
        if sandbox_enabled and workspace:
            # Build a comprehensive sandbox config from the EncreConfig
            sc = sandbox_config or SandboxConfig()

            # Inherit network policy from config if applicable
            if sc.network.policy == NetworkPolicy.NONE and config.sandbox_enabled:
                # Strict default: no network, read-only, capped resources
                sc.network = NetworkConfig(policy=NetworkPolicy.NONE)
                sc.file_protection = FileProtectionConfig(
                    read_only_root=True,
                    workspace_mode="rw",
                    symlink_protection=True,
                    mount_protection=True,
                    no_suid=True,
                )
                sc.resource = ResourceConfig(
                    memory_limit="512m",
                    cpu_limit=1.0,
                    pids_limit=64,
                    no_new_privileges=True,
                )
                sc.seccomp = SeccompConfig(profile=SeccompProfile.UNPRIVILEGED)
                sc.env = EnvConfig(inherit_env=False, env_vars={})
                sc.disable_sudo = True
                sc.disable_network_tooling = True
                sc.disable_interactive = True

            self.sandbox = EncreContainerSandbox(workspace, sc)
        else:
            self.sandbox = None
        self._ssrf_guard = EncreSSRFGuard()
        self._auto_classifier = auto_classifier

    def require_container_sandbox(self, tool_name: str) -> bool:
        """Check if a tool call should be routed through the container sandbox.

        Only ``bash`` commands are sandboxed (file operations use path
        isolation instead).  The sandbox must be enabled, available, and
        configured with a mode that supports container isolation.
        """
        if tool_name not in ("bash",):
            return False
        if not self.sandbox_enabled or self.sandbox is None:
            return False
        # Check the sandbox mode: CONTAINER or HYBRID trigger container isolation
        mode = getattr(self.sandbox.config, "mode", None)
        if mode is not None:
            return mode in (SandboxMode.CONTAINER, SandboxMode.HYBRID)
        # Legacy/default: sandbox IS container mode
        return True

    def execute_in_sandbox(self, command: str, timeout: int | None = None) -> SandboxResult:
        if self.sandbox is None:
            raise RuntimeError("Sandbox not available")
        return self.sandbox.execute(command, timeout)

    def analyze_bash(self, command: str) -> BashAnalysis:
        """Expose bash static analysis for pre-execution review."""
        return analyze_bash_command(command)

    def is_bash_safe(self, command: str) -> tuple[bool, str]:
        """Quick check: is this bash command safe to run without sandbox?"""
        analysis = analyze_bash_command(command)
        if analysis.danger_level in (DangerLevel.CRITICAL, DangerLevel.HIGH):
            return False, "; ".join(analysis.injection_details)
        if analysis.injection_detected and analysis.danger_level == DangerLevel.MEDIUM:
            return False, "; ".join(analysis.injection_details)
        if analysis.contains_unicode_homoglyph:
            return False, "Unicode homoglyph/zero-width characters detected"
        return True, ""

    async def check_tool_permission(self, tool_name: str, tool_input: dict[str, Any]) -> PermissionDecision:
        # The Rust permission engine is the single source of truth for
        # authorization.  We forward the tool name and the JSON-serialized
        # arguments so the dangerous-command regex table can inspect the
        # command string for the bash family.  The decision dict returned
        # by Rust is mapped back onto the existing PermissionAllow /
        # PermissionDeny / PermissionAsk dataclasses so the rest of the
        # agent loop (and the WS protocol) continues to work unchanged.
        try:
            from encre import native as _native
            payload = json.dumps(tool_input or {}, ensure_ascii=False)
            decision = _native.permission_check(tool_name, payload)
        except Exception:
            # Defensive fallback: never let a permission-engine failure
            # crash the agent loop.  Default to allow and let downstream
            # OS-level sandboxes (Landlock / Job Object) take over -- but
            # still run the immune-path guard below before returning.
            decision = None

        if isinstance(decision, dict):
            behavior = decision.get("behavior")
            reason = str(decision.get("reason") or "")
            rule = str(decision.get("rule") or "")
        else:
            behavior, reason, rule = None, "", ""

        # Immune-path hard deny (always-on, even in bypass mode).  The Rust
        # engine has an ALWAYS_ALLOW list but no symmetric always-deny, so a
        # bypass-mode session would auto-allow writes to ``.git/config``,
        # ``~/.ssh/authorized_keys``, ``~/.bashrc`` etc.  We block write-
        # capable tools whose target touches an immune path.  Read access is
        # left untouched (file_read of ``.git/HEAD`` stays allowed).
        immune_hit = self.check_immune_path(tool_name, tool_input)
        if immune_hit and tool_name in _WRITE_TOOL_NAMES and behavior != "deny":
            return PermissionDeny(
                reason=(
                    f"Refused: target path '{immune_hit}' is immune "
                    f"(system-sensitive: .git/.claude/.ssh/shell-init). "
                    f"Cannot be modified by the agent, even in bypass mode."
                )
            )

        if behavior == "deny":
            return PermissionDeny(reason=reason)
        if behavior == "ask":
            return PermissionAsk(reason=reason, rule=rule)
        return PermissionAllow()

    def check_immune_path(self, tool_name: str, tool_input: dict[str, Any]) -> str | None:
        """Return an immune-path fragment the tool call would mutate, or None.

        Extracts candidate target paths from the tool input and checks each
        against the immune set.  Pure path matching -- the caller (the
        executor gate or ``check_tool_permission``) decides whether an immune
        hit warrants a hard deny based on whether the operation is destructive.
        """
        candidates = _extract_tool_target_paths(tool_name, tool_input or {})
        for cand in candidates:
            hit = matches_immune_path(cand)
            if hit:
                return hit
        return None

    def record_permission_decision(self, tool_name: str, allowed: bool) -> None:
        """Persist the user's answer to a previous ``Ask`` decision.

        Once the user has allowed or denied a tool, subsequent calls for
        the same tool should follow the same verdict without re-prompting.
        """
        try:
            from encre import native as _native
            _native.permission_record_decision(tool_name, "allow" if allowed else "deny")
        except Exception:
            pass

    def set_policies(self, tools: dict[str, str], capabilities: dict[str, str]) -> None:
        """Replace the user-managed policy table inside the Rust engine.

        ``tools`` keys are tool names (``"bash"``, ``"file_write"``, ...);
        ``capabilities`` keys are capability names (``"network"``,
        ``"file"``, ``"docker"``, ...).  Values are one of
        ``"allow" | "deny" | "ask" | "default"``.
        """
        try:
            from encre import native as _native
            payload = json.dumps(
                {"tools": tools, "capabilities": capabilities},
                ensure_ascii=False,
            )
            _native.permission_set_policies(payload)
        except Exception:
            pass

    def get_policies(self) -> dict[str, dict[str, str]]:
        """Return the current policy table as ``{"tools": {...}, "capabilities": {...}}``."""
        try:
            from encre import native as _native
            raw = _native.permission_get_policies()
            parsed = json.loads(raw) if raw else {}
            tools = parsed.get("tools", {}) if isinstance(parsed, dict) else {}
            capabilities = parsed.get("capabilities", {}) if isinstance(parsed, dict) else {}
            return {"tools": tools, "capabilities": capabilities}
        except Exception:
            return {"tools": {}, "capabilities": {}}

    def _sync_policies_to_native(self) -> None:
        """Push the current ``EncreConfig.permission_settings`` map into Rust.

        We split the flat ``permission_settings`` dict into ``tools`` and
        ``capabilities`` by checking the well-known capability names.
        Everything else is treated as a per-tool override.

        **Important**: we skip pushing when ``permission_settings`` is empty
        to avoid overwriting the Rust global state — which may have been
        set by the frontend via ``set_permission_policies`` — with an empty
        policy table during ``EncreSafetyEngine`` initialization.  Only when
        the config actually carries permission settings (e.g. loaded from a
        persisted config file) do we synchronise them into Rust.
        """
        if not self.config.permission_settings:
            return  # Nothing to sync — preserve any existing Rust state.

        capability_keys = {
            "network", "file", "bash_io", "docker", "browser",
            "workflow", "git", "deploy", "desktop", "database", "misc", "mcp",
        }
        tools: dict[str, str] = {}
        capabilities: dict[str, str] = {}
        for key, value in self.config.permission_settings.items():
            if key in capability_keys:
                capabilities[key] = value
            else:
                tools[key] = value
        self.set_policies(tools, capabilities)

    async def _check_auto_mode(self, tool_name: str, tool_input: dict[str, Any]) -> PermissionDecision:
        """Auto mode: use classifier when available, fall back to pattern checks.

        Kept for compatibility with callers that still expect it; the
        unified path goes through :meth:`check_tool_permission`.
        """
        if self._auto_classifier is not None:
            from encre.autosafety import AutoDecision
            result = await self._auto_classifier.classify(tool_name, tool_input)
            if result.decision in (AutoDecision.SAFE, AutoDecision.LOW_RISK):
                return PermissionAllow()
            return PermissionAsk()

        # Fallback: pattern-based checks when no classifier configured
        if self._is_dangerous(tool_name, tool_input):
            return PermissionAsk()
        if self._is_sensitive(tool_input):
            return PermissionAsk()
        return PermissionAllow()

    async def check_yolo_permission(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        conversation_context: str = "",
        tool: Any = None,
    ) -> PermissionDecision:
        if self._auto_classifier is None or not conversation_context:
            return await self.check_tool_permission(tool_name, tool_input)

        from encre.autosafety import AutoDecision

        if self._auto_classifier is not None:
            result = await self._auto_classifier.classify_with_context(
                tool_name, tool_input, conversation_context, tool=tool,
            )
            if result.decision in (AutoDecision.SAFE, AutoDecision.LOW_RISK):
                return PermissionAllow(reason=result.reasoning)
            if result.decision == AutoDecision.BLOCK:
                return PermissionDeny(reason=result.reasoning)
            if result.decision == AutoDecision.HIGH_RISK:
                return PermissionDeny(reason=result.reasoning)

        return PermissionAsk(reason=result.reasoning if result else "")

    def _validate_url_safe(self, url: str) -> bool:
        if not url:
            return False
        if url.startswith("http://") or url.startswith("https://"):
            return self._ssrf_guard.validate_url(url)
        return False

    _DANGEROUS_PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"rm\s+-rf\s+/", re.IGNORECASE),
        re.compile(r"mkfs\s", re.IGNORECASE),
        re.compile(r"dd\s+if=.*\s+of=", re.IGNORECASE),
        re.compile(r":\(\)\s*\{.*:\(\)\s*\{.*\}", re.IGNORECASE),
        re.compile(r"chmod\s+777\s+/", re.IGNORECASE),
        re.compile(r">\s*/dev/sda", re.IGNORECASE),
    ]

    _DANGEROUS_SUBSTRINGS: ClassVar[list[str]] = [
        "rm -rf /", "mkfs", "dd if=", "chmod 777 /", "sudo ", ":(){ :|:& };:",
    ]

    def _is_dangerous(self, tool_name: str, tool_input: dict[str, Any]) -> bool:
        if tool_name == "bash":
            command = tool_input.get("command", "")
            if not command:
                return False
            safe, _ = self.is_bash_safe(command)
            return not safe

        input_str = str(tool_input)
        for pattern in self._DANGEROUS_PATTERNS:
            if pattern.search(input_str):
                return True

        return any(cmd.lower() in input_str.lower() for cmd in self._DANGEROUS_SUBSTRINGS)

    def _is_sensitive(self, tool_input: dict[str, Any]) -> bool:
        input_str = str(tool_input)
        return any(pattern.search(input_str) for pattern in self._sensitive_patterns)

    def validate_tool_output(self, _tool_name: str, output: str) -> str:
        if len(output) > self.config.tool_result_max_chars:
            output = output[: self.config.tool_result_max_chars] + "\n... (truncated)"
        return output
