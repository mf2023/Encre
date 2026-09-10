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

"""Tests for the recovery system: ErrorRecoveryEngine, RetryableExecutor,
RecoveryState, and correction inference."""

import asyncio

from encre.recovery import (
    ErrorCategory,
    ErrorRecoveryEngine,
    RecoveryAction,
    RecoveryConfig,
    RecoveryDecision,
    RecoveryState,
    RetryableExecutor,
    classify_error,
    compute_backoff,
)

# ===========================================================================
# ErrorCategory
# ===========================================================================

class TestErrorCategory:
    """Engineered to validate the ErrorCategory enum completeness.

    This test class exercises the ErrorCategory enum across 1 scenario to ensure
    that all expected error categories (transient, input, tool, permission,
    sandbox, model, unknown) are present. The design follows an exhaustive
    member-presence assertion pattern so that any regression adding or removing
    a category surface immediately as a test failure.
    """
    def test_verify_all_categories_exist(self):
        """Validate that ErrorCategory exposes all expected enum members.

        The test exercises hasattr checks against each documented category
        because the enum must be exhaustive for downstream classify_error
        and engine.decide logic to operate correctly.
        """
        assert hasattr(ErrorCategory, "TRANSIENT")
        assert hasattr(ErrorCategory, "INPUT_MALFORMED")
        assert hasattr(ErrorCategory, "TOOL_NOT_FOUND")
        assert hasattr(ErrorCategory, "PERMISSION_DENIED")
        assert hasattr(ErrorCategory, "TOOL_EXECUTION")
        assert hasattr(ErrorCategory, "SANDBOX_ERROR")
        assert hasattr(ErrorCategory, "MODEL_ERROR")
        assert hasattr(ErrorCategory, "UNKNOWN")


class TestClassifyError:
    """Engineered to validate the classify_error function behavior.

    This test class exercises error-message classification across 9 scenarios
    to ensure that the regex-based categorizer correctly maps textual error
    signatures to the appropriate ErrorCategory enum member. The design follows
    a per-category assertion pattern so that each classification rule can be
    independently verified and debugged.
    """
    def test_verify_transient_timeout(self):
        """Validate that transient timeouts are classified as ErrorCategory.TRANSIENT.

        The test exercises classify_error with a ConnectionError timeout message
        and asserts the TRANSIENT category because timeout-related connection
        failures are inherently recoverable via retry with backoff.
        """
        assert classify_error("ConnectionError: timeout") == ErrorCategory.TRANSIENT

    def test_verify_transient_rate_limit(self):
        """Validate that rate-limit errors are classified as ErrorCategory.TRANSIENT.

        The test exercises classify_error with a rate-limit exceeded message
        and asserts the TRANSIENT category because rate-limit violations are
        time-boxed and recoverable via backoff.
        """
        assert classify_error("Error: rate limit exceeded") == ErrorCategory.TRANSIENT

    def test_verify_permission_denied(self):
        """Validate that PermissionError messages are classified as PERMISSION_DENIED.

        The test exercises classify_error with a PermissionError message
        and asserts the PERMISSION_DENIED category because permission errors
        are not recoverable by retry 鈥?they require explicit user escalation.
        """
        assert classify_error("PermissionError: permission denied") == ErrorCategory.PERMISSION_DENIED  # noqa: E501

    def test_verify_permission_blocked_by_hook(self):
        """Validate that hook-blocked actions are classified as PERMISSION_DENIED.

        The test exercises classify_error with a hook-blocked message
        and asserts the PERMISSION_DENIED category because hook rejections
        carry the same semantics as OS-level permission denials.
        """
        assert classify_error("blocked by hook") == ErrorCategory.PERMISSION_DENIED

    def test_verify_model_error(self):
        """Validate that API/backend model errors are classified as MODEL_ERROR.

        The test exercises classify_error with an APIError message
        and asserts the MODEL_ERROR category because upstream model failures
        require backoff but not arg correction.
        """
        assert classify_error("APIError: api error in backend") == ErrorCategory.MODEL_ERROR

    def test_verify_input_malformed(self):
        """Validate that malformed JSON payloads are classified as INPUT_MALFORMED.

        The test exercises classify_error with an invalid-JSON message
        and asserts the INPUT_MALFORMED category because structured input
        errors are correctable by retry with fixed arguments.
        """
        assert classify_error("Error: invalid json in payload") == ErrorCategory.INPUT_MALFORMED

    def test_verify_tool_not_found(self):
        """Validate that unknown tool references are classified as TOOL_NOT_FOUND.

        The test exercises classify_error with an unknown-tool message
        and asserts the TOOL_NOT_FOUND category because tool-name errors
        are terminal and cannot be resolved by retry or fallback.
        """
        assert classify_error("Error: unknown tool 'fake_tool'") == ErrorCategory.TOOL_NOT_FOUND

    def test_verify_sandbox_error(self):
        """Validate that sandbox failures are classified as SANDBOX_ERROR.

        The test exercises classify_error with a sandbox-failure message
        and asserts the SANDBOX_ERROR category because sandbox-level errors
        require isolation-specific handling.
        """
        assert classify_error("sandbox failure") == ErrorCategory.SANDBOX_ERROR

    def test_verify_unknown(self):
        """Validate that unrecognized error messages fall back to UNKNOWN.

        The test exercises classify_error with an unrecognized error prefix
        and asserts the UNKNOWN category because unmatched patterns must
        never raise but default to the safe fallback enum member.
        """
        assert classify_error("SomeWeirdError: unknown failure") == ErrorCategory.UNKNOWN


# ===========================================================================
# RecoveryAction
# ===========================================================================

class TestRecoveryAction:
    """Engineered to validate the RecoveryAction enum completeness.

    This test class exercises the RecoveryAction enum across 1 scenario to
    ensure all action types (retry, fallback, degrade, skip, abort) are
    defined. The design follows an exhaustive member-presence assertion
    pattern so that missing actions surface as immediate failures.
    """
    def test_verify_all_actions_exist(self):
        """Validate that RecoveryAction exposes all expected enum members.

        The test exercises hasattr checks against each documented action
        because the enum must be exhaustive for downstream engine.decide
        and retry logic to reference valid action values.
        """
        assert hasattr(RecoveryAction, "RETRY")
        assert hasattr(RecoveryAction, "RETRY_WITH_BACKOFF")
        assert hasattr(RecoveryAction, "RETRY_WITH_FIXED_ARGS")
        assert hasattr(RecoveryAction, "FALLBACK_TOOL")
        assert hasattr(RecoveryAction, "DEGRADE")
        assert hasattr(RecoveryAction, "SKIP")
        assert hasattr(RecoveryAction, "ABORT_TURN")
        assert hasattr(RecoveryAction, "ABORT_SESSION")


# ===========================================================================
# RecoveryState
# ===========================================================================

class TestRecoveryState:
    """Engineered to validate RecoveryState initialization and mutation.

    This test class exercises RecoveryState construction across 3 scenarios
    to ensure initial fields, decision history recording, and error info
    propagation behave correctly. The design follows a state-lifecycle
    pattern so that each field is individually verifiable.
    """
    def test_verify_initial_state(self):
        """Validate that RecoveryState initializes with expected defaults.

        The test exercises RecoveryState construction with tool_name and
        tool_args and asserts each default field value because the initial
        state must be predictable for downstream executor logic.
        """
        state = RecoveryState(tool_name="test_tool", tool_args={"path": "/tmp/test"})
        assert state.tool_name == "test_tool"
        assert state.tool_args == {"path": "/tmp/test"}
        assert state.attempts == 0
        assert state.recovery_history == []
        assert state.succeeded is False
        assert state.last_error == ""
        assert state.last_category == ErrorCategory.UNKNOWN

    def test_verify_record_decision(self):
        """Validate that recovery decisions are appended to the history list.

        The test exercises append of a RecoveryDecision onto recovery_history
        and asserts the list length and first-element action because the
        history must remain append-only for correction-inference logic.
        """
        state = RecoveryState(tool_name="test_tool", tool_args={})
        decision = RecoveryDecision(action=RecoveryAction.RETRY, reason="try again")
        state.recovery_history.append(decision)
        assert len(state.recovery_history) == 1
        assert state.recovery_history[0].action == RecoveryAction.RETRY

    def test_verify_with_error_info(self):
        """Validate that RecoveryState accepts and preserves error metadata.

        The test exercises construction with last_error and last_category
        and asserts field fidelity because error context must survive state
        object creation for downstream decision logging.
        """
        state = RecoveryState(
            tool_name="test_tool",
            tool_args={"x": 1},
            last_error="something broke",
            last_category=ErrorCategory.TRANSIENT,
        )
        assert state.last_error == "something broke"
        assert state.last_category == ErrorCategory.TRANSIENT


# ===========================================================================
# RecoveryDecision
# ===========================================================================

class TestRecoveryDecision:
    """Engineered to validate RecoveryDecision construction with optional fields.

    This test class exercises decision construction across 4 scenarios to
    ensure that action-specific fields (fallback_tool, modified_args,
    retry_delay_seconds) are correctly stored and accessible. The design
    follows a per-action-type assertion pattern.
    """
    def test_verify_retry_decision(self):
        """Validate that a RETRY decision stores action, reason, and delay.

        The test exercises RecoveryDecision construction with retry-delay
        parameters and asserts field fidelity because downstream backoff
        logic depends on retry_delay_seconds being preserved.
        """
        d = RecoveryDecision(action=RecoveryAction.RETRY, reason="timeout", retry_delay_seconds=1.0)
        assert d.action == RecoveryAction.RETRY
        assert d.reason == "timeout"
        assert d.retry_delay_seconds == 1.0

    def test_verify_fallback_decision(self):
        """Validate that a FALLBACK_TOOL decision stores the fallback target name.

        The test exercises RecoveryDecision construction with fallback_tool
        and asserts the field is preserved because the inference engine
        reads fallback_tool to generate correction strings.
        """
        d = RecoveryDecision(
            action=RecoveryAction.FALLBACK_TOOL,
            reason="tool unavailable",
            fallback_tool="alternative_tool",
        )
        assert d.fallback_tool == "alternative_tool"

    def test_verify_fixed_args_decision(self):
        """Validate that a RETRY_WITH_FIXED_ARGS decision stores modified arguments.

        The test exercises RecoveryDecision construction with modified_args
        and asserts the dictionary is preserved because the correction
        inference layer reads it to regenerate corrected prompts.
        """
        d = RecoveryDecision(
            action=RecoveryAction.RETRY_WITH_FIXED_ARGS,
            reason="bad arg",
            modified_args={"arg1": "fixed"},
        )
        assert d.modified_args == {"arg1": "fixed"}

    def test_verify_abort_decision(self):
        """Validate that an ABORT_TURN decision stores its action type.

        The test exercises RecoveryDecision construction with ABORT_TURN
        and asserts the action is preserved because abort decisions must
        carry unambiguous terminal semantics.
        """
        d = RecoveryDecision(action=RecoveryAction.ABORT_TURN, reason="unrecoverable")
        assert d.action == RecoveryAction.ABORT_TURN


# ===========================================================================
# ErrorRecoveryEngine
# ===========================================================================

class TestErrorRecoveryEngine:
    """Engineered to validate ErrorRecoveryEngine decision-making across error types.

    This test class exercises the engine.decide method across 13 scenarios
    covering transient retries, permission skips, fallback chains, max-retry
    limits, tool-not-found aborts, model-error backoff, and input-correction
    loops. The design follows a per-error-path assertion pattern so that
    each decision branch is independently verifiable.
    """
    def test_verify_decide_transient_first_attempt(self):
        """Validate that transient errors on first attempt trigger RETRY_WITH_BACKOFF.

        The test exercises engine.decide with a ConnectionError timeout message
        at attempt 0 and asserts RETRY_WITH_BACKOFF because the engine must
        choose a backoff-based retry for transient network failures.
        """
        engine = ErrorRecoveryEngine()
        decision = engine.decide(
            tool_name="file_read",
            tool_args={"path": "/tmp/test"},
            error_message="ConnectionError: timeout",
            attempt=0,
        )
        assert decision.action == RecoveryAction.RETRY_WITH_BACKOFF
        assert decision.retry_delay_seconds > 0

    def test_verify_decide_permission_skip(self):
        """Validate that permission errors trigger SKIP without retry.

        The test exercises engine.decide with a PermissionError message
        and asserts SKIP because permission denials are terminal and
        retrying would not change the outcome.
        """
        engine = ErrorRecoveryEngine()
        decision = engine.decide(
            tool_name="file_read",
            tool_args={"path": "/tmp/test"},
            error_message="PermissionError: permission denied",
            attempt=0,
        )
        assert decision.action == RecoveryAction.SKIP

    def test_verify_decide_max_retries_with_fallback(self):
        """Validate that exhausted retries invoke the fallback tool chain.

        The test exercises engine.decide at attempt 3 (past MAX_RETRIES=3)
        with a RuntimeError and asserts FALLBACK_TOOL or SKIP because the
        engine must pivot to fallback_depth-0 when retry count is exhausted.
        """
        engine = ErrorRecoveryEngine()
        decision = engine.decide(
            tool_name="file_read",
            tool_args={"path": "/tmp/test"},
            error_message="RuntimeError: something broke",
            attempt=3,
            fallback_depth=0,
        )
        # file_read has "bash" as fallback at depth 0
        assert decision.action in (RecoveryAction.FALLBACK_TOOL, RecoveryAction.SKIP)

    def test_verify_decide_max_retries_no_fallback_chain(self):
        """Validate that exhausted retries on an unknown tool yield SKIP or ABORT.

        The test exercises engine.decide at attempt 5 for a nonexistent tool
        and asserts SKIP or ABORT_TURN because no fallback chain exists for
        unknown tools, making further retries futile.
        """
        engine = ErrorRecoveryEngine()
        decision = engine.decide(
            tool_name="nonexistent_tool",
            tool_args={},
            error_message="RuntimeError: persistent failure",
            attempt=5,
        )
        assert decision.action in (RecoveryAction.SKIP, RecoveryAction.ABORT_TURN)

    def test_verify_decide_tool_not_found(self):
        """Validate that unknown-tool errors trigger ABORT_TURN immediately.

        The test exercises engine.decide with a tool-not-found message
        and asserts ABORT_TURN because referencing a nonexistent tool
        is a structural error that cannot be recovered by retry.
        """
        engine = ErrorRecoveryEngine()
        decision = engine.decide(
            tool_name="nonexistent",
            tool_args={},
            error_message="Error: unknown tool 'nonexistent'",
            attempt=0,
        )
        assert decision.action == RecoveryAction.ABORT_TURN

    def test_verify_decide_model_error(self):
        """Validate that model/API errors trigger RETRY_WITH_BACKOFF.

        The test exercises engine.decide with an APIError message
        and asserts RETRY_WITH_BACKOFF because model failures are
        transient and benefit from exponential backoff.
        """
        engine = ErrorRecoveryEngine()
        decision = engine.decide(
            tool_name="file_read",
            tool_args={"path": "/tmp/test"},
            error_message="APIError: internal server error",
            attempt=0,
        )
        assert decision.action == RecoveryAction.RETRY_WITH_BACKOFF

    def test_verify_decide_input_malformed_first_attempt(self):
        """Validate that input-malformed errors on first attempt trigger RETRY_WITH_FIXED_ARGS.

        The test exercises engine.decide with an invalid-JSON payload message
        at attempt 0 and asserts RETRY_WITH_FIXED_ARGS because the engine
        should correct the input structure before retrying.
        """
        engine = ErrorRecoveryEngine()
        decision = engine.decide(
            tool_name="file_write",
            tool_args={"path": "/tmp/test"},
            error_message="Error: invalid json in payload",
            attempt=0,
        )
        assert decision.action == RecoveryAction.RETRY_WITH_FIXED_ARGS

    def test_verify_decide_input_malformed_second_attempt(self):
        """Validate that repeated input-malformed errors trigger ABORT_TURN.

        The test exercises engine.decide with an invalid-JSON payload message
        at attempt 1 (second failure) and asserts ABORT_TURN because the
        engine should not retry the same bad input indefinitely.
        """
        engine = ErrorRecoveryEngine()
        decision = engine.decide(
            tool_name="file_write",
            tool_args={"path": "/tmp/test"},
            error_message="Error: invalid json in payload",
            attempt=1,
        )
        assert decision.action == RecoveryAction.ABORT_TURN

    def test_verify_session_error_limit(self):
        """Validate that exceeding _max_session_errors triggers ABORT_SESSION.

        The test exercises engine.decide with _session_errors at 10 (the
        configured limit) and asserts ABORT_SESSION because session-level
        error accumulation warrants a hard stop to prevent runaway loops.
        """
        engine = ErrorRecoveryEngine()
        engine._session_errors = 10  # reaches _max_session_errors
        decision = engine.decide(
            tool_name="test",
            tool_args={},
            error_message="any error",
            attempt=0,
        )
        assert decision.action == RecoveryAction.ABORT_SESSION

    def test_verify_reset_session(self):
        """Validate that reset_session clears accumulated error state.

        The test exercises reset_session after populating _session_errors
        and _last_errors and asserts both are cleared because the method
        must provide a clean slate for a new turn.
        """
        engine = ErrorRecoveryEngine()
        engine._session_errors = 5
        engine._last_errors = ["e1", "e2", "e3"]
        engine.reset_session()
        assert engine._session_errors == 0
        assert engine._last_errors == []

    def test_verify_infer_correction_fallback(self):
        """Validate that infer_correction extracts the fallback tool name from history.

        The test exercises infer_correction on a state whose history contains
        a FALLBACK_TOOL decision and asserts the tool name appears in the
        output string because the inference layer must generate a useful
        prompt hint for the LLM.
        """
        state = RecoveryState(tool_name="bad_tool", tool_args={})
        state.recovery_history = [
            RecoveryDecision(action=RecoveryAction.FALLBACK_TOOL, reason="unavailable", fallback_tool="good_tool"),  # noqa: E501
        ]
        correction = ErrorRecoveryEngine.infer_correction(state)
        assert "good_tool" in correction

    def test_verify_infer_correction_fixed_args(self):
        """Validate that infer_correction references modified args in the output.

        The test exercises infer_correction on a state whose history contains
        a RETRY_WITH_FIXED_ARGS decision and asserts the output contains
        'modified args' because the hint must communicate what changed.
        """
        state = RecoveryState(tool_name="test", tool_args={})
        state.recovery_history = [
            RecoveryDecision(
                action=RecoveryAction.RETRY_WITH_FIXED_ARGS,
                reason="bad arg",
                modified_args={"x": 1},
            ),
        ]
        correction = ErrorRecoveryEngine.infer_correction(state)
        assert "modified args" in correction.lower()

    def test_verify_infer_correction_empty_history(self):
        """Validate that infer_correction returns an empty string when history is empty.

        The test exercises infer_correction on a fresh state with no
        recovery_history and asserts the empty-string return because
        there is no prior context to extract a hint from.
        """
        state = RecoveryState(tool_name="test", tool_args={})
        assert ErrorRecoveryEngine.infer_correction(state) == ""

    def test_verify_infer_correction_from_history(self):
        """Validate that infer_correction_from_history extracts backoff hints.

        The test exercises the classmethod with a RETRY_WITH_BACKOFF history
        entry and asserts 'backoff' appears in the output because the
        inference layer must surface delay information to the LLM.
        """
        history = [
            RecoveryDecision(action=RecoveryAction.RETRY_WITH_BACKOFF, reason="timeout", retry_delay_seconds=5.0),  # noqa: E501
        ]
        correction = ErrorRecoveryEngine.infer_correction_from_history(history, "test_tool")
        assert "backoff" in correction.lower()

    def test_verify_infer_correction_from_history_empty(self):
        """Validate that infer_correction_from_history returns empty for an empty history list.

        The test exercises the classmethod with [] and asserts an empty
        string because there are no decisions to infer from.
        """
        assert ErrorRecoveryEngine.infer_correction_from_history([], "test") == ""

    def test_verify_infer_correction_from_history_last_wins(self):
        """Validate that the last-decision wins when inferring corrections from history.

        The test exercises the classmethod with two decisions where the last
        is FALLBACK_TOOL and asserts the output contains the last fallback
        tool name because recency takes priority over earlier retried paths.
        """
        history = [
            RecoveryDecision(action=RecoveryAction.RETRY, reason="first"),
            RecoveryDecision(action=RecoveryAction.FALLBACK_TOOL, reason="last", fallback_tool="better_tool"),  # noqa: E501
        ]
        correction = ErrorRecoveryEngine.infer_correction_from_history(history, "old_tool")
        assert "better_tool" in correction


# ===========================================================================
# RetryableExecutor
# ===========================================================================

class TestRetryableExecutor:
    """Engineered to validate RetryableExecutor lifecycle and recovery integration.

    This test class exercises the execute method across 6 scenarios covering
    success, flaky-retry, permission-skip, history collection, retry callback
    wiring, and custom engine injection. The design follows a lifecycle
    assertion pattern so that each executor capability is independently verified.
    """
    def test_verify_execute_success(self):
        """Validate that execute returns a succeeded result on the first attempt.

        The test exercises execute with a synchronous-success callback
        and asserts succeeded=True, the correct final_result, and call_count=1
        because the executor must not retry when the underlying operation succeeds.
        """
        async def _test():
            executor = RetryableExecutor()
            call_count = 0

            async def succeed(args):
                nonlocal call_count
                call_count += 1
                return "success"

            result = await executor.execute(
                tool_name="test",
                tool_args={},
                execute_fn=succeed,
            )
            assert result.succeeded is True
            assert result.final_result == "success"
            assert call_count == 1

        asyncio.run(_test())

    def test_verify_execute_retry_then_success(self):
        """Validate that execute retries transient failures until success.

        The test exercises execute with a flaky callback that fails twice
        then succeeds and asserts succeeded=True, final_result, and call_count=3
        because the executor must persist across transient failures per config.
        """
        async def _test():
            executor = RetryableExecutor()
            call_count = 0

            async def flaky(args):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise ConnectionError("timeout transient failure")
                return "eventual success"

            result = await executor.execute(
                tool_name="test",
                tool_args={},
                execute_fn=flaky,
            )
            assert result.succeeded is True
            assert result.final_result == "eventual success"
            assert call_count == 3

        asyncio.run(_test())

    def test_verify_execute_skips_on_permission_error(self):
        """Validate that execute marks permission errors as succeeded with a skip marker.

        The test exercises execute with a callback that always raises
        PermissionError and asserts succeeded=True with 'Skipped' in the
        result because permission denials are treated as terminal successes
        (no retry, no error propagation).
        """
        async def _test():
            executor = RetryableExecutor()
            call_count = 0

            async def permission_denied(args):
                nonlocal call_count
                call_count += 1
                raise PermissionError("permission denied")

            result = await executor.execute(
                tool_name="test",
                tool_args={},
                execute_fn=permission_denied,
            )
            # Permission denied -> SKIP, which marks state as succeeded
            assert result.succeeded is True
            assert "Skipped" in result.final_result
            assert call_count == 1

        asyncio.run(_test())

    def test_verify_execute_collects_recovery_history(self):
        """Validate that execute accumulates recovery history across failures.

        The test exercises execute with a callback that always raises
        ConnectionError and asserts recovery_history is non-empty because
        the executor must track every decision for later correction inference.
        """
        async def _test():
            executor = RetryableExecutor()

            async def always_fails(args):
                raise ConnectionError("timeout")

            result = await executor.execute(
                tool_name="unknown_tool",
                tool_args={},
                execute_fn=always_fails,
            )
            assert len(result.recovery_history) > 0

        asyncio.run(_test())

    def test_verify_execute_on_retry_callback(self):
        """Validate that the on_retry callback receives decision and attempt data.

        The test exercises execute with a flaky callback and an on_retry
        listener and asserts the callback fires at least once because the
        retry hook enables external observability into the recovery loop.
        """
        async def _test():
            executor = RetryableExecutor()
            callbacks = []

            def on_retry(decision, attempt):
                callbacks.append((decision.action, attempt))

            call_count = 0

            async def flaky(args):
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise ConnectionError("timeout")
                return "ok"

            result = await executor.execute(
                tool_name="test",
                tool_args={},
                execute_fn=flaky,
                on_retry=on_retry,
            )
            assert result.succeeded is True
            assert len(callbacks) >= 1

        asyncio.run(_test())

    def test_verify_custom_recovery_engine(self):
        """Validate that execute accepts a custom ErrorRecoveryEngine instance.

        The test exercises execute with a custom engine and a success callback
        and asserts succeeded=True and the expected final_result because the
        executor must delegate decision-making to any conforming engine.
        """
        async def _test():
            engine = ErrorRecoveryEngine()
            executor = RetryableExecutor(recovery=engine)

            async def works(args):
                return "done"

            result = await executor.execute("t", {}, works)
            assert result.succeeded is True
            assert result.final_result == "done"

        asyncio.run(_test())


# ===========================================================================
# RecoveryConfig
# ===========================================================================

class TestRecoveryConfig:
    """Engineered to validate RecoveryConfig constants and lookup tables.

    This test class exercises config constants, fallback chains, and
    error-pattern mappings across 3 scenarios to ensure the static
    configuration values are consistent with downstream engine logic.
    """
    def test_verify_constants(self):
        """Validate that RecoveryConfig exposes the expected numerical constants.

        The test exercises direct attribute access on RecoveryConfig and
        asserts exact values because the engine's backoff and retry limits
        depend on these constants being stable.
        """
        assert RecoveryConfig.MAX_RETRIES == 3
        assert RecoveryConfig.MAX_FALLBACK_DEPTH == 2
        assert RecoveryConfig.BASE_BACKOFF_SECONDS == 1.0
        assert RecoveryConfig.MAX_BACKOFF_SECONDS == 60.0
        assert RecoveryConfig.BACKOFF_MULTIPLIER == 2.0

    def test_verify_fallback_chains(self):
        """Validate that RecoveryConfig.FALLBACK_CHAINS covers common file tools.

        The test exercises membership checks on the fallback-chains dict
        and asserts presence of file_read, grep, glob, web_fetch, and
        file_edit because these are the primary tools the engine must
        fall back to when execution fails.
        """
        assert "file_read" in RecoveryConfig.FALLBACK_CHAINS
        assert "grep" in RecoveryConfig.FALLBACK_CHAINS
        assert "glob" in RecoveryConfig.FALLBACK_CHAINS
        assert "web_fetch" in RecoveryConfig.FALLBACK_CHAINS
        assert "file_edit" in RecoveryConfig.FALLBACK_CHAINS

    def test_verify_error_patterns(self):
        """Validate that RecoveryConfig.ERROR_PATTERNS maps substrings to correct categories.

        The test exercises key membership and value checks on the error-patterns
        dict and asserts the mapped ErrorCategory for each known pattern because
        classify_error relies on these substrings for regex matching.
        """
        patterns = RecoveryConfig.ERROR_PATTERNS
        assert patterns["timed out"] == ErrorCategory.TRANSIENT
        assert patterns["rate limit"] == ErrorCategory.TRANSIENT
        assert patterns["permission denied"] == ErrorCategory.PERMISSION_DENIED
        assert patterns["unknown tool"] == ErrorCategory.TOOL_NOT_FOUND
        assert patterns["api error"] == ErrorCategory.MODEL_ERROR
        assert patterns["sandbox"] == ErrorCategory.SANDBOX_ERROR


# ===========================================================================
# compute_backoff
# ===========================================================================

class TestComputeBackoff:
    """Engineered to validate the compute_backoff exponential-backoff function.

    This test class exercises the backoff calculation across 3 scenarios
    covering the first attempt, a mid-retry attempt, and the max-wait cap.
    The design ensures jitter is within the expected tolerance band.
    """
    def test_verify_first_attempt(self):
        """Validate that compute_backoff returns approximately base * 2^0 with jitter.

        The test exercises compute_backoff at attempt 0 with base=1.0
        and asserts the delay falls in [0.75, 1.25] because the jitter
        band is +-25% of the calculated delay.
        """
        delay = compute_backoff(0, base=1.0, max_wait=60.0)
        assert 0.75 <= delay <= 1.25  # base * 2^0 = 1.0, +/- 25% jitter

    def test_verify_third_attempt(self):
        """Validate that compute_backoff returns approximately base * 2^3 with jitter.

        The test exercises compute_backoff at attempt 3 with base=1.0
        and asserts the delay falls in [6.0, 10.0] because 2^3=8 and
        the jitter band is +-25%.
        """
        delay = compute_backoff(3, base=1.0, max_wait=60.0)
        assert 6.0 <= delay <= 10.0  # base * 2^3 = 8.0, +/- 25%

    def test_verify_respects_max_wait(self):
        """Validate that compute_backoff caps the delay at max_wait with jitter tolerance.

        The test exercises compute_backoff at attempt 10 with max_wait=30.0
        and asserts the delay does not exceed max_wait plus jitter because
        the cap prevents unbounded wait times in long retry sequences.
        """
        delay = compute_backoff(10, base=1.0, max_wait=30.0)
        assert delay <= 37.5  # max_wait + 25% jitter cap
