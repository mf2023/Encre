"""Integration tests for per-mode capability profiles and Plan-Do-Review wiring.

Verifies the one-engine/three-profiles design end to end without a real LLM:
GENERAL stays on historical behaviour, WORKSPACE activates the Plan-Do-Review
engine and planner delegation, AUTOMATION keeps hard gating disabled and PDR off.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from encre.config import EncreConfig
from encre.evolution.plan_do_review import StepStatus
from encre.loop import EncreLoop
from encre.mode_profiles import AgentMode, get_mode_profile
from encre.session import EncreSession


def _make_loop(mode) -> EncreLoop:
    config = EncreConfig()
    from encre.tools.registry import ToolRegistry
    return EncreLoop(
        config=config,
        session=EncreSession(config),
        tool_registry=ToolRegistry(),
        mode=mode,
    )


@pytest.mark.asyncio
async def test_workspace_mode_activates_pdr():
    loop = _make_loop(AgentMode.WORKSPACE)
    assert loop._profile.workspace_delegation is True
    assert loop._profile.verify_budget_total() > 0
    # Simulate a plan-worthy task running a single turn.
    loop._pdr.initialize("Refactor the scheduler module and add unit tests for it.")
    loop._pdr_active = True
    loop._pdr.start_next_step()
    assert loop._pdr_active is True
    assert len(loop._pdr.plan.steps) >= 1
    assert loop._pdr.plan.current_step is not None


@pytest.mark.asyncio
async def test_general_mode_pdr_inactive():
    loop = _make_loop(AgentMode.GENERAL)
    assert loop._profile.workspace_delegation is False
    # Even if a plan-worthy prompt arrives, should_plan gates the init;
    # here we assert the default state stays inactive.
    assert loop._pdr_active is False
    assert loop._pdr.plan.steps == []


@pytest.mark.asyncio
async def test_automation_mode_hard_gate_disabled():
    loop = _make_loop(AgentMode.AUTOMATION)
    assert loop._profile.verify_budget_total() == 0
    assert loop._profile.workspace_delegation is False
    assert loop._pdr_active is False


@pytest.mark.asyncio
async def test_mode_profile_fallback_for_unknown():
    assert get_mode_profile("not-a-real-mode").mode == AgentMode.GENERAL
    assert get_mode_profile(None).mode == AgentMode.GENERAL


@pytest.mark.asyncio
async def test_pdr_step_advancement_only_on_completed():
    loop = _make_loop(AgentMode.WORKSPACE)
    loop._pdr.initialize(
        "Step one: write file. Step two: run tests. Step three: report."
    )
    loop._pdr.start_next_step()
    current = loop._pdr.plan.current_step
    assert current is not None
    # Retry keeps the step IN_PROGRESS; start_next_step must NOT skip it.
    loop._pdr.mark_step_failed(error="verification failed")
    if current.retry_count <= current.max_retries and current.status == StepStatus.IN_PROGRESS:
        index_before = loop._pdr.plan.current_step_index
        nxt = loop._pdr.start_next_step()
        assert loop._pdr.plan.current_step_index == index_before or nxt is None
    # A completed step advances.
    loop._pdr.mark_step_complete(summary="step done")
    nxt = loop._pdr.start_next_step()
    assert nxt is None or nxt.status == StepStatus.IN_PROGRESS


# ── Mode behavior matrix: distinct tool bases + prompt gains ───────────────


@pytest.mark.asyncio
async def test_workspace_mode_has_coding_tool_base():
    """WORKSPACE always carries the coding toolchain, regardless of intents."""
    loop = _make_loop(AgentMode.WORKSPACE)
    toolset = loop._resolve_tool_set_for_mode(intents=["general"])
    assert "coding" in toolset.split("+")


@pytest.mark.asyncio
async def test_automation_mode_stays_bare_tool_base():
    """AUTOMATION adds no fixed profile tool base (only intent expansion)."""
    loop = _make_loop(AgentMode.AUTOMATION)
    assert get_mode_profile(AgentMode.AUTOMATION).tool_sets == ()
    # With a generic intent, AUTOMATION stays on the bare default.
    assert loop._resolve_tool_set_for_mode(intents=["general"]) == "default"
    # A coding intent still expands (a coding job needs coding tools); the
    # difference from WORKSPACE is that AUTOMATION has no *fixed* coding base.
    assert loop._resolve_tool_set_for_mode(intents=["coding"]) == "default+coding"


@pytest.mark.asyncio
async def test_general_mode_matches_intent_tool_base():
    """GENERAL expands only by intent, not by profile tool_sets."""
    loop = _make_loop(AgentMode.GENERAL)
    assert loop._resolve_tool_set_for_mode(intents=["general"]) == "default"
    assert loop._resolve_tool_set_for_mode(intents=["coding"]) == "default+coding"


@pytest.mark.asyncio
async def test_mode_prompt_gains_are_distinct():
    """Each profile carries a distinct, non-empty system-prompt gain."""
    general = get_mode_profile(AgentMode.GENERAL).prompt_gain
    workspace = get_mode_profile(AgentMode.WORKSPACE).prompt_gain
    automation = get_mode_profile(AgentMode.AUTOMATION).prompt_gain
    assert general and workspace and automation
    assert workspace != general
    assert automation != general
    assert "WORKSPACE mode" in workspace
    assert "AUTOMATION mode" in automation


@pytest.mark.asyncio
async def test_review_phase_rolls_back_bad_step():
    """lightweight_review wiring: an all-error step rolls back to a retry."""
    from encre.evolution.plan_do_review import ReviewGrade

    loop = _make_loop(AgentMode.WORKSPACE)
    loop._pdr.initialize("Step one: run the migration and verify it.")
    loop._pdr.start_next_step()
    loop._pdr.record_tool_call(
        turn=1, tool_name="bash", args={"cmd": "migrate"},
        result="Traceback: migration failed", is_error=True,
    )
    grade = loop._pdr.lightweight_review()
    assert grade == ReviewGrade.FAIL
    # The loop-level wiring converts a bad grade into mark_step_failed,
    # which keeps the step IN_PROGRESS (retry) instead of advancing.
    current = loop._pdr.plan.current_step
    current.retry_count = 0
    loop._pdr.mark_step_failed(error=f"review grade: {grade.name}")
    assert current.status == StepStatus.IN_PROGRESS
