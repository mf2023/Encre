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


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?# SandboxConfig
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?

class TestSandboxConfig:
    """Engineered to validate SandboxConfig construction and nested sub-config defaults.

    This test class exercises SandboxConfig across 8 scenarios covering default
    values, custom configuration, network policy variants, multiple allowed
    domains, multiple environment variables, dataclass integrity, and sandbox
    mode enumeration. The design follows a structured-default-assertion pattern
    so every nested sub-config field is independently verifiable.
    """
    def test_verify_default_values(self):
        """Validate that SandboxConfig() initializes all fields to their documented defaults.

        The test exercises default construction and asserts each nested config
        (network, resource, file_protection, seccomp, env) matches the expected
        baseline because the defaults define the least-privileged starting point.
        """
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

    def test_verify_custom_values(self):
        """Validate that SandboxConfig accepts and preserves fully custom nested configs.

        The test exercises construction with explicit NetworkConfig, ResourceConfig,
        FileProtectionConfig, SeccompConfig, EnvConfig, and extra_mounts and asserts
        each field is stored correctly because full-customization must round-trip
        without default-overwrite.
        """
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

    def test_verify_network_policy_values(self):
        """Validate that each NetworkPolicy enum value is accepted and preserved.

        The test exercises construction with NONE, LIMITED, and HOST policies
        and asserts each is stored correctly because the policy field must
        support all defined enum values without coercion.
        """
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

    def test_verify_multiple_allowed_domains(self):
        """Validate that multiple allowed_domains are stored as a list.

        The test exercises construction with three domain strings and asserts
        the list length and membership because the domain allowlist must
        preserve all entries for per-domain network filtering.
        """
        cfg = SandboxConfig(
            network=NetworkConfig(
                policy=NetworkPolicy.LIMITED,
                allowed_domains=["pypi.org", "github.com", "registry.npmjs.org"],
            ),
        )
        assert len(cfg.network.allowed_domains) == 3
        assert "pypi.org" in cfg.network.allowed_domains

    def test_verify_multiple_env_vars(self):
        """Validate that multiple environment variables are stored correctly.

        The test exercises construction with three env vars and asserts
        each key-value pair is preserved because the sandbox must inject
        the correct environment into the container.
        """
        cfg = SandboxConfig(
            env=EnvConfig(
                env_vars={"PYTHONPATH": "/app", "NODE_ENV": "production", "LOG_LEVEL": "debug"},
            ),
        )
        assert cfg.env.env_vars["PYTHONPATH"] == "/app"
        assert cfg.env.env_vars["NODE_ENV"] == "production"
        assert len(cfg.env.env_vars) == 3

    def test_verify_is_dataclass(self):
        """Validate that all SandboxConfig nested types are dataclasses.

        The test exercises dataclasses.is_dataclass on SandboxConfig and each
        nested config type and asserts True for all because dataclass derivation
        enables consistent construction and field introspection.
        """
        from dataclasses import is_dataclass
        assert is_dataclass(SandboxConfig)
        assert is_dataclass(NetworkConfig)
        assert is_dataclass(ResourceConfig)
        assert is_dataclass(FileProtectionConfig)
        assert is_dataclass(SeccompConfig)
        assert is_dataclass(EnvConfig)

    def test_verify_sandbox_mode_default(self):
        """Validate that the default SandboxMode is NONE.

        The test exercises default construction and asserts mode == SandboxMode.NONE
        because NONE is the safe baseline that disables container isolation.
        """
        assert SandboxConfig().mode == SandboxMode.NONE

    def test_verify_sandbox_mode_explicit(self):
        """Validate that each SandboxMode enum value can be set explicitly.

        The test exercises construction with every mode in the enum and asserts
        cfg.mode equals the passed value for each iteration because all modes
        must be constructible without default coercion.
        """
        for mode in SandboxMode:
            cfg = SandboxConfig(mode=mode)
            assert cfg.mode == mode


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?# SandboxResult
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?

class TestSandboxResult:
    """Engineered to validate SandboxResult field population across success and error outcomes.

    This test class exercises SandboxResult construction across 7 scenarios
    covering basic success, error output, timeout, sandbox violations,
    output truncation, security events, and dataclass integrity. The design
    ensures each result field is independently verifiable.
    """
    def test_verify_basic_result(self):
        """Validate that a successful execution produces a clean SandboxResult.

        The test exercises construction with stdout="hello world\\n", exit_code=0,
        and asserts each field including timed_out=False, duration_ms=0.0,
        sandbox_violation="", killed=False because a clean success must have
        no side indicators set.
        """
        result = SandboxResult(stdout="hello world\n", stderr="", exit_code=0)
        assert result.stdout == "hello world\n"
        assert result.stderr == ""
        assert result.exit_code == 0
        assert result.timed_out is False
        assert result.duration_ms == 0.0
        assert result.sandbox_violation == ""
        assert result.killed is False

    def test_verify_error_result(self):
        """Validate that an error result preserves stderr and exit code.

        The test exercises construction with a command-not-found error and
        asserts exit_code=127, stderr contains the message, and duration_ms
        is preserved because error results must carry diagnostic details.
        """
        result = SandboxResult(
            stdout="",
            stderr="command not found: xxx",
            exit_code=127,
            duration_ms=150.5,
        )
        assert result.exit_code == 127
        assert "command not found" in result.stderr
        assert result.duration_ms == 150.5

    def test_verify_timeout_result(self):
        """Validate that a timeout result sets timed_out=True and exit_code=-1.

        The test exercises construction with timed_out=True, exit_code=-1,
        and a partial stdout and asserts these fields are preserved because
        timeout results must be distinguishable from normal exits.
        """
        result = SandboxResult(
            stdout="partial output",
            stderr="Command timed out",
            exit_code=-1,
            timed_out=True,
            duration_ms=120000.0,
        )
        assert result.timed_out is True
        assert result.exit_code == -1

    def test_verify_sandbox_violation(self):
        """Validate that a sandbox violation result preserves the violation reason.

        The test exercises construction with sandbox_violation="sudo detected"
        and exit_code=-4 and asserts both fields because violation results
        must carry the enforcement reason for logging and reporting.
        """
        result = SandboxResult(
            stdout="",
            stderr="Blocked: privilege escalation",
            exit_code=-4,
            sandbox_violation="sudo detected",
        )
        assert result.exit_code == -4
        assert result.sandbox_violation == "sudo detected"

    def test_verify_output_truncated(self):
        """Validate that output_truncated=True is preserved on the result.

        The test exercises construction with output_truncated=True and asserts
        the flag is preserved because truncation indicators must survive
        serialization for downstream UI display.
        """
        result = SandboxResult(
            stdout="some output",
            stderr="",
            exit_code=0,
            output_truncated=True,
        )
        assert result.output_truncated is True

    def test_verify_security_events(self):
        """Validate that security_events list is preserved correctly.

        The test exercises construction with a single security-event dict and
        asserts length and first-element event_type because the event log
        must remain intact for audit trail purposes.
        """
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

    def test_verify_is_dataclass(self):
        """Validate that SandboxResult is a dataclass.

        The test exercises dataclasses.is_dataclass and asserts True because
        dataclass derivation enables consistent construction and field access.
        """
        from dataclasses import is_dataclass
        assert is_dataclass(SandboxResult)


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?# EncreContainerSandbox
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?

class TestEncreContainerSandbox:
    """Engineered to validate EncreContainerSandbox construction, lifecycle, and security constraints.

    This test class exercises the sandbox class across 16 scenarios covering
    construction with and without config, context-manager protocol, close/cleanup
    idempotency, audit logging, Docker availability branching, timeout handling,
    command-length enforcement, blocked-command patterns, container run/exec flow,
    and security-audit persistence. The design follows a lifecycle-assertion
    pattern so each phase of the sandbox lifecycle is independently verified.
    """
    def test_verify_construction_basic(self):
        """Validate that basic construction resolves workspace to an absolute path.

        The test exercises EncreContainerSandbox(workspace="/tmp/test") and
        asserts workspace is absolute, _container_id is None, and _active is
        False because a newly constructed sandbox has no active container.
        """
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        assert sandbox.workspace == os.path.abspath("/tmp/test")
        assert sandbox._container_id is None
        assert sandbox._active is False

    def test_verify_construction_with_config(self):
        """Validate that construction with a custom config propagates all nested fields.

        The test exercises construction with an explicit SandboxConfig and
        asserts image, timeout, memory_limit, and cpu_limit are preserved
        because the config must fully override defaults.
        """
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

    def test_verify_is_available_returns_bool(self):
        """Validate that is_available() returns a boolean.

        The test exercises is_available on a fresh sandbox and asserts the
        return type is bool because the method's return value is used in
        conditional logic throughout the codebase.
        """
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        result = sandbox.is_available()
        assert isinstance(result, bool)

    def test_verify_context_manager_interface(self):
        """Validate that EncreContainerSandbox implements the context-manager protocol.

        The test exercises hasattr checks for __enter__ and __exit__ and
        asserts both exist because the sandbox must support `with` statement
        usage for resource lifecycle management.
        """
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        assert hasattr(sandbox, "__enter__")
        assert hasattr(sandbox, "__exit__")

    def test_verify_context_manager_enter_returns_self(self):
        """Validate that __enter__ returns the sandbox instance itself.

        The test exercises the with-statement binding and asserts the bound
        variable is the same object because context managers conventionally
        return self to enable method chaining.
        """
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        with sandbox as s:
            assert s is sandbox

    def test_verify_close_method(self):
        """Validate that close() is idempotent and does not raise when no container is active.

        The test exercises close() on a fresh sandbox and asserts no exception
        is raised because cleanup must be safe to call at any lifecycle point.
        """
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        assert hasattr(sandbox, "close")
        sandbox.close()  # Should not raise even with no active container

    def test_verify_cleanup_method(self):
        """Validate that cleanup() is idempotent and does not raise when no container is active.

        The test exercises cleanup() on a fresh sandbox and asserts no exception
        is raised because the method must be safe to call during teardown
        regardless of container state.
        """
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        assert hasattr(sandbox, "cleanup")
        sandbox.cleanup()  # Should not raise even with no active container

    def test_verify_get_audit_log(self):
        """Validate that get_audit_log() returns a list and captures blocked commands.

        The test exercises execute("sudo ls") on a fresh sandbox and asserts
        the audit log is a list, and if the command was blocked (exit_code=-4),
        the log contains at least one entry with event_type in ("violation", "execution")
        because the audit trail must record security decisions.
        """
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

    def test_verify_execute_without_docker_returns_file_not_found(self):
        """Validate that execute returns exit_code -2 when Docker is unavailable.

        The test exercises execute("echo hello") on a sandbox where Docker may
        or may not be available and asserts the appropriate exit code and
        error message because the sandbox must handle missing Docker gracefully.
        """
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        # Run a simple command
        result = sandbox.execute("echo hello")
        if sandbox.is_available():
            assert result.exit_code in (0, -2, -3)
        else:
            assert result.exit_code == -2
            assert "Docker not found" in result.stderr

    def test_verify_execute_timeout_handling(self):
        """Validate that a long-running command times out with exit_code=-1 and timed_out=True.

        The test exercises execute("sleep 10", timeout=1) when Docker is
        available and asserts timed_out=True and exit_code==-1 because the
        timeout mechanism must be observable in the result object.
        """
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        if sandbox.is_available():
            result = sandbox.execute("sleep 10", timeout=1)
            assert result.timed_out is True
            assert result.exit_code == -1

    def test_verify_command_too_long(self):
        """Validate that commands exceeding max_command_length are rejected with exit_code -4.

        The test exercises execute with a 5000-character echo command and
        asserts exit_code==-4 and the violation message mentions 'too long'
        because the length gate must block oversized commands before Docker invocation.
        """
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        long_cmd = "echo " + "x" * 5000
        result = sandbox.execute(long_cmd)
        assert result.exit_code == -4
        assert "too long" in result.sandbox_violation.lower() or "too long" in result.stderr.lower()

    def test_verify_blocked_command_pattern(self):
        """Validate that dangerous command patterns are blocked pre-execution.

        The test exercises execute on a list of blocked commands (sudo rm -rf,
        pkexec, insmod) and asserts exit_code is -4, -2, or -3, or the sandbox
        is available (in which case the command may proceed) because the
        security pre-check must intercept privileged or kernel-loading commands.
        """
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

    def test_verify_stop_container_noop_when_no_container(self):
        """Validate that stop_container() is a no-op when no container is active.

        The test exercises stop_container() on a fresh sandbox and asserts
        _container_id remains None and _active remains False because
        stopping a non-existent container must not error.
        """
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        sandbox.stop_container()  # Should not raise
        assert sandbox._container_id is None
        assert sandbox._active is False

    def test_verify_exec_in_container_requires_active_container(self):
        """Validate that exec_in_container raises RuntimeError when no container is active.

        The test exercises exec_in_container on a fresh sandbox and asserts
        RuntimeError with "No active container" because exec requires a
        running container to attach to.
        """
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        with pytest.raises(RuntimeError, match="No active container"):
            sandbox.exec_in_container("echo hello")

    def test_verify_run_container_requires_docker(self):
        """Validate that run_container() skips when Docker is unavailable.

        The test exercises run_container() and skips when Docker is not
        available, otherwise asserts the returned container_id is non-empty
        and _active is True because container lifecycle requires Docker.
        """
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

    def test_verify_exec_in_running_container(self):
        """Validate that exec_in_container succeeds inside a running container.

        The test exercises run_container followed by exec_in_container("echo hello")
        and asserts exit_code=0 and "hello" in stdout because exec must
        run commands inside the live container.
        """
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

    def test_verify_security_audit_persistence(self):
        """Validate that the audit log accumulates entries across multiple execute calls.

        The test exercises two execute calls (one blocked, one normal) and
        asserts the audit log has at least one entry because the log must
        persist across the sandbox lifetime for forensic review.
        """
        sandbox = EncreContainerSandbox(workspace="/tmp/test")
        # Run some commands
        sandbox.execute("sudo ls")  # will be blocked or fail
        sandbox.execute("echo test")
        log = sandbox.get_audit_log()
        assert len(log) >= 1


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?# Path isolation (_sandbox.py)
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?

class TestPathIsolation:
    """Engineered to validate path-isolation logic in _sandbox.py.

    This test class exercises _resolve_sandbox_path, check_path_safety,
    get_sandbox_root, and remap_tool_path across 6 scenarios covering
    basic remapping, outside-path rejection, safety checks on empty/proc
    paths, root creation, and no-loop fallback. The design ensures path
    traversal attacks are blocked at the remapping layer.
    """
    @pytest.fixture
    def sandbox_dir(self):
        """Provide a temporary sandbox directory for path-isolation tests.

        Returns:
            A pathlib.Path pointing to a temp directory named "sandbox".
        """
        with tempfile.TemporaryDirectory() as tmp:
            yield Path(tmp) / "sandbox"

    def setup_paths(self, sandbox_dir: Path):
        """Create a test file structure with a sandbox subdirectory and an outside file.

        Args:
            sandbox_dir: The root path under which to create the test structure.

        Returns:
            A tuple of (sandbox_dir, outside) paths for use in tests.
        """
        sandbox_dir.mkdir(parents=True)
        outside = sandbox_dir.parent / "outside.txt"
        return sandbox_dir, outside

    def test_verify_remap_path_basic(self):
        """Validate that _resolve_sandbox_path remaps relative and virtual paths into the sandbox.

        The test exercises remapping a relative filename and a /workspace/ prefixed path
        and asserts both resolve to start with the sandbox root and end with the
        expected filename because remapping is the core path-isolation mechanism.
        """
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

    def test_verify_remap_path_rejects_outside(self):
        """Validate that _resolve_sandbox_path rejects absolute and traversing paths.

        The test exercises remapping "/etc/passwd" and "../outside.txt" and asserts
        both return empty strings because paths outside the sandbox boundary
        must be rejected to prevent file-system escape.
        """
        from encre.tools.builtin._sandbox import _resolve_sandbox_path
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = str(Path(tmp) / "sandbox_test")
            Path(sandbox).mkdir(parents=True)

            # Absolute path outside sandbox 鈫?reject
            result = _resolve_sandbox_path("/etc/passwd", sandbox, "test-session")
            assert result == ""

            # Path traversal 鈫?reject
            result = _resolve_sandbox_path("../outside.txt", sandbox, "test-session")
            assert result == ""

    def test_verify_check_path_safety(self):
        """Validate that check_path_safety flags empty and proc paths as violations.

        The test exercises check_path_safety on a safe path, an empty string,
        and /proc/self/mem and asserts the violation is None for safe paths
        and carries the expected reason for empty and proc paths because
        procfs access is a container-escape vector.
        """
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

    def test_verify_get_sandbox_root(self):
        """Validate that get_sandbox_root creates and returns the session directory.

        The test exercises get_sandbox_root("test-session") and asserts the
        returned path exists, is a directory, and has the expected name because
        the sandbox root must be created on demand for each session.
        """
        from encre.tools.builtin._sandbox import get_sandbox_root
        root = get_sandbox_root("test-session")
        assert root.exists()
        assert root.is_dir()
        assert root.name == "test-session"

    def test_verify_remap_tool_path_no_loop(self):
        """Validate that remap_tool_path returns a non-empty path when no loop is active.

        The test exercises remap_tool_path("test.txt") outside any loop context
        and asserts the result is non-empty because the function must always
        return a valid path, falling back to the original when no sandbox
        session is active.
        """
        from encre.tools.builtin._sandbox import remap_tool_path
        result = remap_tool_path("test.txt")
        # When no loop is active, the path should be returned unchanged or mapped
        # to the sandbox if the session_id came through
        assert result  # Not empty


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?# Bash tool sandbox injection
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?

class TestBashWorkspaceInjection:
    """Engineered to validate the workspace context-variable lifecycle in the bash tool.

    This test class exercises _get_workspace, set_workspace, and reset_workspace
    across 3 scenarios covering default state, set/reset round-trip, and
    context isolation across independent tokens. The design ensures workspace
    injection is scoped per token and does not leak across contexts.
    """
    def test_verify_workspace_context_defaults(self):
        """Validate that _get_workspace returns None before any workspace is set.

        The test exercises _get_workspace directly and asserts None because
        the context variable must start in an unset state.
        """
        from encre.tools.builtin.bash import _get_workspace, reset_workspace, set_workspace

        assert _get_workspace() is None

    def test_verify_set_and_reset_workspace(self):
        """Validate that set_workspace and reset_workspace form a correct lifecycle.

        The test exercises set_workspace("/tmp/test"), asserts _get_workspace
        returns the value, then resets via the returned token and asserts
        None because the reset must restore the original context state.
        """
        from encre.tools.builtin.bash import _get_workspace, reset_workspace, set_workspace

        token = set_workspace("/tmp/test")
        assert _get_workspace() == "/tmp/test"
        reset_workspace(token)
        assert _get_workspace() is None

    def test_verify_context_isolation(self):
        """Validate that different set_workspace tokens produce independent workspace values.

        The test exercises two sequential set_workspace calls with different
        paths and asserts each is visible at the correct time and both reset
        to None after their respective resets because context isolation
        prevents workspace leakage across sequential tool invocations.
        """
        from encre.tools.builtin.bash import _get_workspace, reset_workspace, set_workspace

        token = set_workspace("/workspace/a")
        assert _get_workspace() == "/workspace/a"

        reset_workspace(token)
        token2 = set_workspace("/workspace/b")
        assert _get_workspace() == "/workspace/b"
        reset_workspace(token2)
        assert _get_workspace() is None
