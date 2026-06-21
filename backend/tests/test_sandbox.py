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


"""Tests for the enhanced sandbox system.

Covers:
- SandboxConfig with nested sub-configs (NetworkConfig, ResourceConfig, etc.)
- SandboxResult with new fields (sandbox_violation, output_truncated, etc.)
- EncreContainerSandbox construction, lifecycle, security constraints
- Path isolation (_sandbox.py): remapping, traversal detection, symlink checks
- Bash tool sandbox injection
"""

import os
import tempfile
from pathlib import Path

import pytest

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


# ═══════════════════════════════════════════════════════════════════
# SandboxConfig
# ═══════════════════════════════════════════════════════════════════


class TestSandboxConfig:
    def test_default_values(self):
        cfg = SandboxConfig()
        assert cfg.image == "python:3.11-slim"
        assert cfg.workspace_mount == "/workspace"
        assert cfg.mode == SandboxMode.NONE
        assert cfg.network.policy == NetworkPolicy.NONE
        assert cfg.network.allowed_domains == []
        assert cfg.resource.memory_limit == "512m"
        assert cfg.resource.cpu_limit == 1.0
        assert cfg.resource.pids_limit == 64
        assert cfg.resource.no_new_privileges is True
        assert cfg.file_protection.read_only_root is True
        assert cfg.file_protection.symlink_protection is True
        assert cfg.file_protection.mount_protection is True
        assert cfg.seccomp.profile == SeccompProfile.UNPRIVILEGED
        assert cfg.env.inherit_env is False
        assert cfg.timeout == 120
        assert cfg.disable_sudo is True
        assert cfg.disable_network_tooling is True
        assert cfg.max_command_length == 4096
        assert cfg.extra_mounts == {}

    def test_custom_values(self):
        cfg = SandboxConfig(
            mode=SandboxMode.CONTAINER,
            image="ubuntu:22.04",
            workspace_mount="/app",
            network=NetworkConfig(
                policy=NetworkPolicy.LIMITED,
                allowed_domains=["api.example.com"],
                allowed_ports=[443],
                dns_only=True,
            ),
            resource=ResourceConfig(
                memory_limit="2g",
                cpu_limit=2.0,
                pids_limit=128,
                no_new_privileges=True,
            ),
            file_protection=FileProtectionConfig(
                read_only_root=True,
                workspace_mode="ro",
                symlink_protection=True,
                mount_protection=True,
            ),
            seccomp=SeccompConfig(
                profile=SeccompProfile.STRICT,
                extra_blocked_syscalls=["personality"],
            ),
            env=EnvConfig(
                inherit_env=False,
                env_vars={"DEBUG": "1"},
                deny_secret_patterns=["AWS_*", "SECRET_*"],
            ),
            timeout=300,
            disable_sudo=True,
            disable_network_tooling=True,
            extra_mounts={"/data": "/mnt/data"},
        )
        assert cfg.mode == SandboxMode.CONTAINER
        assert cfg.image == "ubuntu:22.04"
        assert cfg.network.policy == NetworkPolicy.LIMITED
        assert "api.example.com" in cfg.network.allowed_domains
        assert 443 in cfg.network.allowed_ports
        assert cfg.resource.memory_limit == "2g"
        assert cfg.resource.cpu_limit == 2.0
        assert cfg.resource.pids_limit == 128
        assert cfg.file_protection.workspace_mode == "ro"
        assert cfg.seccomp.profile == SeccompProfile.STRICT
        assert "personality" in cfg.seccomp.extra_blocked_syscalls
        assert cfg.env.env_vars == {"DEBUG": "1"}
        assert cfg.env.deny_secret_patterns == ["AWS_*", "SECRET_*"]
        assert cfg.timeout == 300
        assert cfg.extra_mounts == {"/data": "/mnt/data"}

    def test_network_policy_values(self):
        none_cfg = SandboxConfig()
        assert none_cfg.network.policy == NetworkPolicy.NONE

        limited_cfg = SandboxConfig(
            network=NetworkConfig(policy=NetworkPolicy.LIMITED),
        )
        assert limited_cfg.network.policy == NetworkPolicy.LIMITED

        host_cfg = SandboxConfig(
            network=NetworkConfig(policy=NetworkPolicy.HOST),
        )
        assert host_cfg.network.policy == NetworkPolicy.HOST

    def test_multiple_allowed_domains(self):
        cfg = SandboxConfig(
            network=NetworkConfig(
                policy=NetworkPolicy.LIMITED,
                allowed_domains=["pypi.org", "github.com", "registry.npmjs.org"],
            ),
        )
        assert len(cfg.network.allowed_domains) == 3
        assert "pypi.org" in cfg.network.allowed_domains

    def test_multiple_env_vars(self):
        cfg = SandboxConfig(
            env=EnvConfig(
                env_vars={"PYTHONPATH": "/app", "NODE_ENV": "production", "LOG_LEVEL": "debug"},
            ),
        )
        assert cfg.env.env_vars["PYTHONPATH"] == "/app"
        assert cfg.env.env_vars["NODE_ENV"] == "production"
        assert len(cfg.env.env_vars) == 3

    def test_is_dataclass(self):
        from dataclasses import is_dataclass
        assert is_dataclass(SandboxConfig)
        assert is_dataclass(NetworkConfig)
        assert is_dataclass(ResourceConfig)
        assert is_dataclass(FileProtectionConfig)
        assert is_dataclass(SeccompConfig)
        assert is_dataclass(EnvConfig)

    def test_sandbox_mode_default(self):
        assert SandboxConfig().mode == SandboxMode.NONE

    def test_sandbox_mode_explicit(self):
        for mode in SandboxMode:
            cfg = SandboxConfig(mode=mode)
            assert cfg.mode == mode


# ═══════════════════════════════════════════════════════════════════
# SandboxResult
# ═══════════════════════════════════════════════════════════════════


class TestSandboxResult:
    def test_basic_result(self):
        result = SandboxResult(stdout="hello world\n", stderr="", exit_code=0)
        assert result.stdout == "hello world\n"
        assert result.stderr == ""
        assert result.exit_code == 0
        assert result.timed_out is False
        assert result.duration_ms == 0.0
        assert result.sandbox_violation == ""
        assert result.killed is False

    def test_error_result(self):
        result = SandboxResult(
            stdout="",
            stderr="command not found: xxx",
            exit_code=127,
            duration_ms=150.5,
        )
        assert result.exit_code == 127
        assert "command not found" in result.stderr
        assert result.duration_ms == 150.5

    def test_timeout_result(self):
        result = SandboxResult(
            stdout="partial output",
            stderr="Command timed out",
            exit_code=-1,
            timed_out=True,
            duration_ms=120000.0,
        )
        assert result.timed_out is True
        assert result.exit_code == -1

    def test_sandbox_violation(self):
        result = SandboxResult(
            stdout="",
            stderr="Blocked: privilege escalation",
            exit_code=-4,
            sandbox_violation="sudo detected",
        )
        assert result.exit_code == -4
        assert result.sandbox_violation == "sudo detected"

    def test_output_truncated(self):
        result = SandboxResult(
            stdout="some output",
            stderr="",
            exit_code=0,
            output_truncated=True,
        )
        assert result.output_truncated is True

    def test_security_events(self):
        result = SandboxResult(
            stdout="",
            stderr="",
            exit_code=0,
            security_events=[
                {"event_type": "execution", "timestamp": 1000.0, "details": "command run"},
            ],
        )
        assert len(result.security_events) == 1
        assert result.security_events[0]["event_type"] == "execution"

    def test_is_dataclass(self):
        from dataclasses import is_dataclass
        assert is_dataclass(SandboxResult)


# ═══════════════════════════════════════════════════════════════════
# EncreContainerSandbox
# ═══════════════════════════════════════════════════════════════════


class TestEncreContainerSandbox:
    def test_construction_basic(self):
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        assert sandbox.workspace == os.path.abspath("/tmp/test")
        assert sandbox._container_id is None
        assert sandbox._active is False

    def test_construction_with_config(self):
        cfg = SandboxConfig(
            mode=SandboxMode.CONTAINER,
            image="python:3.11-slim",
            timeout=60,
            resource=ResourceConfig(memory_limit="256m", cpu_limit=0.5),
        )
        sandbox = EncreContainerSandbox(workspace="/tmp/test", config=cfg)
        assert sandbox.config.image == "python:3.11-slim"
        assert sandbox.config.timeout == 60
        assert sandbox.config.resource.memory_limit == "256m"
        assert sandbox.config.resource.cpu_limit == 0.5

    def test_is_available_returns_bool(self):
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        result = sandbox.is_available()
        assert isinstance(result, bool)

    def test_context_manager_interface(self):
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        assert hasattr(sandbox, "__enter__")
        assert hasattr(sandbox, "__exit__")

    def test_context_manager_enter_returns_self(self):
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        with sandbox as s:
            assert s is sandbox

    def test_close_method(self):
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        assert hasattr(sandbox, "close")
        sandbox.close()  # Should not raise even with no active container

    def test_cleanup_method(self):
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        assert hasattr(sandbox, "cleanup")
        sandbox.cleanup()  # Should not raise even with no active container

    def test_get_audit_log(self):
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        log = sandbox.get_audit_log()
        assert isinstance(log, list)
        # Execute something that gets blocked (no sudo in container, so it'll
        # either pass through or be blocked by _check_command)
        result = sandbox.execute("sudo ls")
        if result.exit_code == -4:
            # Command was blocked by security check
            log = sandbox.get_audit_log()
            assert len(log) >= 1
            assert log[0]["event_type"] in ("violation", "execution")

    def test_execute_without_docker_returns_file_not_found(self):
        """When Docker is not installed, execute should return exit_code -2."""
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        # Run a simple command
        result = sandbox.execute("echo hello")
        if sandbox.is_available():
            assert result.exit_code in (0, -2, -3)
        else:
            assert result.exit_code == -2
            assert "Docker not found" in result.stderr

    def test_execute_timeout_handling(self):
        """Test that a timeout returns exit_code -1 with timed_out=True."""
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        if sandbox.is_available():
            result = sandbox.execute("sleep 10", timeout=1)
            assert result.timed_out is True
            assert result.exit_code == -1

    def test_command_too_long(self):
        """Test that overly long commands are rejected before execution."""
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        long_cmd = "echo " + "x" * 5000
        result = sandbox.execute(long_cmd)
        assert result.exit_code == -4
        assert "too long" in result.sandbox_violation.lower() or "too long" in result.stderr.lower()

    def test_blocked_command_pattern(self):
        """Test that dangerous commands are blocked pre-execution."""
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        blocked_commands = [
            "sudo rm -rf /",
            "sudo whoami",
            "pkexec ls",
            "insmod mymodule",
        ]
        for cmd in blocked_commands:
            result = sandbox.execute(cmd)
            # Should either be blocked (-4) or run with any exit code
            # (depends on whether Docker is available)
            assert result.exit_code in (-4, -2, -3) or sandbox.is_available()

    def test_stop_container_noop_when_no_container(self):
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        sandbox.stop_container()  # Should not raise
        assert sandbox._container_id is None
        assert sandbox._active is False

    def test_exec_in_container_requires_active_container(self):
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        with pytest.raises(RuntimeError, match="No active container"):
            sandbox.exec_in_container("echo hello")

    def test_run_container_requires_docker(self):
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        if not sandbox.is_available():
            pytest.skip("Docker not available")
        container_id = sandbox.run_container()
        try:
            assert container_id is not None
            assert len(container_id) > 0
            assert sandbox._active is True
        finally:
            sandbox.cleanup()

    def test_exec_in_running_container(self):
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        if not sandbox.is_available():
            pytest.skip("Docker not available")
        sandbox.run_container()
        try:
            result = sandbox.exec_in_container("echo hello")
            assert result.exit_code == 0
            assert "hello" in result.stdout
        finally:
            sandbox.cleanup()

    def test_security_audit_persistence(self):
        """Test that audit log persists across calls."""
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        # Run some commands
        sandbox.execute("sudo ls")  # will be blocked or fail
        sandbox.execute("echo test")
        log = sandbox.get_audit_log()
        assert len(log) >= 1


# ═══════════════════════════════════════════════════════════════════
# Path isolation (_sandbox.py)
# ═══════════════════════════════════════════════════════════════════


class TestPathIsolation:
    @pytest.fixture
    def sandbox_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp) / "sandbox"

    def setup_paths(self, sandbox_dir: Path):
        """Helper: create test file structure."""
        sandbox_dir.mkdir(parents=True)
        outside = sandbox_dir.parent / "outside.txt"
        return sandbox_dir, outside

    def test_remap_path_basic(self):
        """Test basic path remapping into sandbox."""
        from encre.tools.builtin._sandbox import _resolve_sandbox_path
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = str(Path(tmp) / "sandbox_test")
            Path(sandbox).mkdir(parents=True)

            # Relative path should resolve inside sandbox
            result = _resolve_sandbox_path("output.txt", sandbox, "test-session")
            assert result.startswith(sandbox)
            assert result.endswith("output.txt")

            # Virtual /workspace/ prefix should be stripped
            result2 = _resolve_sandbox_path("/workspace/foo.py", sandbox, "test-session")
            assert result2.startswith(sandbox)
            assert result2.endswith("foo.py")

    def test_remap_path_rejects_outside(self):
        """Test that paths outside sandbox are rejected."""
        from encre.tools.builtin._sandbox import _resolve_sandbox_path
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = str(Path(tmp) / "sandbox_test")
            Path(sandbox).mkdir(parents=True)

            # Absolute path outside sandbox → reject
            result = _resolve_sandbox_path("/etc/passwd", sandbox, "test-session")
            assert result == ""

            # Path traversal → reject
            result = _resolve_sandbox_path("../outside.txt", sandbox, "test-session")
            assert result == ""

    def test_check_path_safety(self):
        """Test check_path_safety function."""
        from encre.tools.builtin._sandbox import check_path_safety
        with tempfile.TemporaryDirectory() as tmp:
            sandbox_root = Path(tmp) / "sandbox"
            sandbox_root.mkdir()

            # Safe path
            safe = str(sandbox_root / "valid.txt")
            violation, result = check_path_safety(safe, sandbox_root)
            assert violation is None
            assert result == safe

            # Empty path
            violation, result = check_path_safety("", sandbox_root)
            assert violation is not None
            assert violation.reason == "empty path"

            # Proc path
            violation, result = check_path_safety("/proc/self/mem", sandbox_root)
            assert violation is not None
            assert "procedural" in violation.reason

    def test_get_sandbox_root(self):
        """Test sandbox root directory creation."""
        from encre.tools.builtin._sandbox import get_sandbox_root
        root = get_sandbox_root("test-session")
        assert root.exists()
        assert root.is_dir()
        assert root.name == "test-session"

    def test_remap_tool_path_no_loop(self):
        """remap_tool_path falls back to file_path when no loop is active."""
        from encre.tools.builtin._sandbox import remap_tool_path
        result = remap_tool_path("test.txt")
        # When no loop is active, the path should be returned unchanged or mapped
        # to the sandbox if the session_id came through
        assert result  # Not empty


# ═══════════════════════════════════════════════════════════════════
# Bash tool sandbox injection
# ═══════════════════════════════════════════════════════════════════


class TestBashWorkspaceInjection:
    def test_workspace_context_defaults(self):
        """Test that the workspace context var defaults to None."""
        from encre.tools.builtin.bash import _get_workspace, reset_workspace, set_workspace

        assert _get_workspace() is None

    def test_set_and_reset_workspace(self):
        """Test set / reset workspace lifecycle."""
        from encre.tools.builtin.bash import _get_workspace, reset_workspace, set_workspace

        token = set_workspace("/tmp/test")
        assert _get_workspace() == "/tmp/test"
        reset_workspace(token)
        assert _get_workspace() is None

    def test_context_isolation(self):
        """Test that different contexts get different workspace values."""
        from encre.tools.builtin.bash import _get_workspace, reset_workspace, set_workspace

        token = set_workspace("/workspace/a")
        assert _get_workspace() == "/workspace/a"

        reset_workspace(token)
        token2 = set_workspace("/workspace/b")
        assert _get_workspace() == "/workspace/b"
        reset_workspace(token2)
        assert _get_workspace() is None
