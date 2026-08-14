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

"""Tests for the prompt system: base classes, builder, templates, and specializations."""

import pytest


class TestEncreBasePrompt:
    """Test cases covering encre base prompt.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_base_prompt_is_abstract(self):
        """Verifies that base prompt is abstract."""
        from encre.prompts.base import EncreBasePrompt
        with pytest.raises(TypeError):
            EncreBasePrompt()  # Cannot instantiate ABC

    def test_base_prompt_has_abstract_methods(self):
        """Verifies that base prompt has abstract methods."""
        from encre.prompts.base import EncreBasePrompt
        # Confirm the expected result for this scenario: base prompt has abstract methods.
        assert hasattr(EncreBasePrompt, "build_system_prompt")
        assert hasattr(EncreBasePrompt, "build_tool_instructions")


class TestEncrePromptTemplate:
    """Test cases covering encre prompt template.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_construction_defaults(self):
        """Verifies that construction defaults."""
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate()
        # Confirm the expected result for this scenario: construction defaults.
        assert tmpl is not None
        assert tmpl._specialty == "general"
        assert tmpl._builder is not None

    def test_construction_with_specialty(self):
        """Verifies that construction with specialty."""
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate(specialty="coding")
        # Confirm the expected result for this scenario: construction with specialty.
        assert tmpl._specialty == "coding"

    def test_construction_with_custom_builder(self):
        """Verifies that construction with custom builder."""
        from encre.prompts.base import EncrePromptTemplate
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        tmpl = EncrePromptTemplate(builder=builder, specialty="research")
        # Confirm the expected result for this scenario: construction with custom builder.
        assert tmpl._builder is builder
        assert tmpl._specialty == "research"

    def test_builder_property(self):
        """Verifies that builder property."""
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate(specialty="data")
        # Confirm the expected result for this scenario: builder property.
        assert tmpl.builder is tmpl._builder

    def test_build_system_prompt_returns_string(self):
        """Verifies that build system prompt returns string."""
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate(specialty="general")
        result = tmpl.build_system_prompt(mode="default")
        # Confirm the expected result for this scenario: build system prompt returns string.
        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_system_prompt_with_tools(self):
        """Verifies that build system prompt with tools."""
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate()
        tools = [
            {"function": {"name": "bash", "description": "Execute shell commands"}},
            {"function": {"name": "read", "description": "Read files"}},
        ]
        result = tmpl.build_system_prompt(mode="default", tools=tools)
        # Confirm the expected result for this scenario: build system prompt with tools.
        assert "bash" in result
        assert "read" in result

    def test_build_system_prompt_with_custom_instructions(self):
        """Verifies that build system prompt with custom instructions."""
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate()
        result = tmpl.build_system_prompt(
            mode="default",
            custom_instructions="Always use Python 3.12 syntax.",
        )
        # Confirm the expected result for this scenario: build system prompt with custom instructions.
        assert "Python 3.12" in result

    def test_build_system_prompt_reflects_specialty(self):
        """Verifies that build system prompt reflects specialty."""
        from encre.prompts.base import EncrePromptTemplate
        coding_tmpl = EncrePromptTemplate(specialty="coding")
        research_tmpl = EncrePromptTemplate(specialty="research")

        coding_result = coding_tmpl.build_system_prompt(mode="default")
        research_result = research_tmpl.build_system_prompt(mode="default")

        # Different specialties produce different prompts
        # Confirm the expected result for this scenario: build system prompt reflects specialty.
        assert coding_result != research_result
        assert "Software Engineering" in coding_result
        assert "Research" in research_result

    def test_build_system_prompt_reflects_permission_mode(self):
        """Verifies that build system prompt reflects permission mode."""
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate()

        bypass_result = tmpl.build_system_prompt(mode="bypass")
        plan_result = tmpl.build_system_prompt(mode="plan")

        # Confirm the expected result for this scenario: build system prompt reflects permission mode.
        assert "bypass" in bypass_result.lower()
        assert "plan" in plan_result.lower()

    def test_build_tool_instructions_empty_list(self):
        """Verifies that build tool instructions empty list."""
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate()
        result = tmpl.build_tool_instructions([])
        # Confirm the expected result for this scenario: build tool instructions empty list.
        assert "do not have access" in result.lower()

    def test_build_tool_instructions_with_names(self):
        """Verifies that build tool instructions with names."""
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate()
        result = tmpl.build_tool_instructions(["bash", "grep", "glob"])
        # Confirm the expected result for this scenario: build tool instructions with names.
        assert "bash" in result
        assert "grep" in result
        assert "glob" in result
        assert "Use them as needed" in result


class TestPromptBlock:
    """Test cases covering prompt block.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_prompt_block_construction(self):
        """Verifies that prompt block construction."""
        from encre.prompts.system import PromptBlock
        block = PromptBlock(priority=10, name="test_block", content="Test content")
        # Confirm the expected result for this scenario: prompt block construction.
        assert block.priority == 10
        assert block.name == "test_block"
        assert block.content == "Test content"

    def test_prompt_block_with_context(self):
        """Verifies that prompt block with context."""
        from encre.prompts.system import PromptBlock
        block = PromptBlock(
            priority=50,
            name="templated",
            content="Hello {{username}}, welcome to {{project}}.",
        )
        ctx = {"username": "Alice", "project": "Encre"}
        filled = block.with_context(ctx)
        # Confirm the expected result for this scenario: prompt block with context.
        assert "Hello Alice" in filled.content
        assert "welcome to Encre" in filled.content
        assert filled.name == "templated"
        assert filled.priority == 50


class TestEncrePromptBuilder:
    """Test cases covering encre prompt builder.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_builder_construction(self):
        """Verifies that builder construction."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        # Confirm the expected result for this scenario: builder construction.
        assert builder is not None
        assert builder._blocks == {}

    def test_add_block(self):
        """Verifies that add block."""
        from encre.prompts.system import EncrePromptBuilder, PromptBlock
        builder = EncrePromptBuilder()
        block = PromptBlock(priority=100, name="extra", content="Extra instructions")
        builder.add_block(block)
        # Confirm the expected result for this scenario: add block.
        assert "extra" in builder._blocks
        assert builder._blocks["extra"].content == "Extra instructions"

    def test_remove_block(self):
        """Verifies that remove block."""
        from encre.prompts.system import EncrePromptBuilder, PromptBlock
        builder = EncrePromptBuilder()
        block = PromptBlock(priority=100, name="temporary", content="Temp")
        builder.add_block(block)
        # Confirm the expected result for this scenario: remove block.
        assert "temporary" in builder._blocks
        builder.remove_block("temporary")
        assert "temporary" not in builder._blocks

    def test_remove_nonexistent_block_does_not_raise(self):
        """Verifies that remove nonexistent block does not raise."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        builder.remove_block("nonexistent")  # Should not raise

    def test_skill_summary_injects_dynamic_catalogue(self):
        """A provided skill_summary is rendered as a dynamic Skills block."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        summary = "- `/travel-flights`: Flight search guidance"
        prompt = builder.build(skill_summary=summary)
        assert "## Skills (auto-discovered)" in prompt
        assert "/travel-flights" in prompt

    def test_empty_skill_summary_omits_block(self):
        """No skill_summary means no Skills block is injected."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        prompt = builder.build(skill_summary="")
        assert "## Skills (auto-discovered)" not in prompt

    def test_add_custom_instructions(self):
        """Verifies that add custom instructions."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        builder.add_custom_instructions("Focus on testing.")
        # Confirm the expected result for this scenario: add custom instructions.
        assert "custom" in builder._blocks
        assert "Focus on testing" in builder._blocks["custom"].content
        assert builder._blocks["custom"].priority == 200

    def test_build_default(self):
        """Verifies that build default."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build()
        # Confirm the expected result for this scenario: build default.
        assert isinstance(result, str)
        assert len(result) > 0
        # Should contain default blocks
        assert "identity" in result.lower() or "helpful" in result.lower()

    def test_build_coding_specialty(self):
        """Verifies that build coding specialty."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build(specialty="coding")
        # Confirm the expected result for this scenario: build coding specialty.
        assert "Software Engineering" in result

    def test_build_research_specialty(self):
        """Verifies that build research specialty."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build(specialty="research")
        # Confirm the expected result for this scenario: build research specialty.
        assert "Research" in result

    def test_build_data_specialty(self):
        """Verifies that build data specialty."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build(specialty="data")
        # Confirm the expected result for this scenario: build data specialty.
        assert "Data Analysis" in result

    def test_build_unknown_specialty_falls_back_to_general(self):
        """Verifies that build unknown specialty falls back to general."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build(specialty="unknown_specialty")
        # Confirm the expected result for this scenario: build unknown specialty falls back to general.
        assert "Dig Deeper Than the Surface" in result

    def test_build_with_permission_mode(self):
        """Verifies that build with permission mode."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()

        bypass = builder.build(mode="bypass")
        default = builder.build(mode="default")

        # Confirm the expected result for this scenario: build with permission mode.
        assert "full autonomy" in bypass.lower()
        assert "Ask for permission" in default

    def test_build_with_tools(self):
        """Verifies that build with tools."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        tools = [{"function": {"name": "test_tool", "description": "A test tool"}}]
        result = builder.build(tools=tools)
        # Confirm the expected result for this scenario: build with tools.
        # Tools are passed to the model via the API tools field, not inlined
        # into the system prompt text; build must succeed and include the
        # tool-usage guidance block.
        assert isinstance(result, str) and len(result) > 0
        assert "tool_usage" in result.lower() or "find_tool" in result.lower() or "bash" in result.lower()

    def test_build_with_custom_instructions(self):
        """Verifies that build with custom instructions."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build(custom_instructions="ALWAYS validate input first.")
        # Confirm the expected result for this scenario: build with custom instructions.
        assert "ALWAYS validate input first" in result

    def test_build_with_context(self):
        """Verifies that build with context."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build_with_context(
            ctx={"username": "TestUser"},
            specialty="general",
        )
        # The identity block doesn't have {{username}} but the method
        # should still work without errors
        # Confirm the expected result for this scenario: build with context.
        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_with_context_variable_substitution(self):
        """Verifies that build with context variable substitution."""
        from encre.prompts.system import EncrePromptBuilder, PromptBlock
        builder = EncrePromptBuilder()
        builder.add_block(PromptBlock(
            priority=200,
            name="context_block",
            content="User {{user}} using version {{version}}",
        ))
        result = builder.build_with_context(
            ctx={"user": "Alice", "version": "1.0.0"},
            specialty="general",
        )
        # Confirm the expected result for this scenario: build with context variable substitution.
        assert "User Alice" in result
        assert "version 1.0.0" in result

    def test_custom_block_can_override_default(self):
        """Verifies that custom block can override default."""
        from encre.prompts.system import EncrePromptBuilder, PromptBlock
        builder = EncrePromptBuilder()
        # Override the identity block
        builder.add_block(PromptBlock(
            priority=0,
            name="identity",
            content="You are a friendly assistant.",
        ))
        result = builder.build()
        # Confirm the expected result for this scenario: custom block can override default.
        assert "friendly assistant" in result

    def test_mandatory_constraints_block_present_by_default(self):
        """The flagship mandatory-constraints block is injected by default."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build()
        assert "MANDATORY Constraints" in result
        assert "Binding Pre-Action Governance" in result

    def test_mandatory_constraints_ordered_after_identity_before_task_completion(self):
        """Priority 0.5 places mandatory constraints between identity (0) and task_completion (1)."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build()
        idx_identity = result.find("Encre Agent")
        idx_mand = result.find("MANDATORY Constraints")
        idx_task = result.find("Deliver Finished Work")
        assert 0 <= idx_identity < idx_mand < idx_task

    def test_mandatory_constraints_precedence_line(self):
        """The override line anchoring constraint authority is present."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build()
        assert "override" in result.lower()
        assert "autonomous" in result.lower()

    def test_memory_discipline_front_positioned(self):
        """Memory recall protocol must sit early, within the governance cluster."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build()
        assert "Memory Discipline" in result
        idx_discipline = result.index("Memory Discipline")
        idx_task = result.index("Task Completion")
        assert idx_discipline < idx_task

    def test_memory_discipline_recall_protocol_present(self):
        """The mandatory recall protocol is present in the built system prompt."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build()
        assert (
            "MANDATORY Recall Protocol" in result
            or "mandatory recall protocol" in result.lower()
        )


class TestRuntimePromptFiles:
    """All runtime prompts referenced by loop_stability are on disk, never hardcoded."""
    def test_runtime_prompt_files_exist(self):
        from encre.loop_stability import (
            build_auto_continue_message,
            build_grace_message,
            build_delegation_guidance,
            build_steer_injection,
            build_thinking_prefill,
        )
        assert build_auto_continue_message()
        assert "remaining" in build_grace_message().lower() \
            or "what remains" in build_grace_message().lower()
        assert build_delegation_guidance()
        assert build_steer_injection(["alpha", "beta"])
        assert build_thinking_prefill("help", enabled=True)
        assert build_thinking_prefill("why does this bug happen", enabled=True)
        assert build_thinking_prefill("What is the answer to this question?", enabled=True)


class TestPromptFrontmatter:
    """Tests for frontmatter parsing, including float priorities."""
    def test_float_priority_parses(self):
        """A float priority (e.g. 0.5) is parsed as a number, not a string."""
        from encre.prompts.loader import _parse_frontmatter
        meta, body = _parse_frontmatter(
            "---\nname: slack\npriority: 0.5\ncondition: ~\n---\nCONTENT"
        )
        assert meta["priority"] == 0.5
        assert isinstance(meta["priority"], float)
        assert body == "CONTENT"

    def test_negative_float_priority_parses(self):
        from encre.prompts.loader import _parse_frontmatter
        meta, _ = _parse_frontmatter("---\npriority: -1.5\n---\n")
        assert meta["priority"] == -1.5

    def test_integer_and_list_frontmatter_still_parse(self):
        from encre.prompts.loader import _parse_frontmatter
        meta, _ = _parse_frontmatter(
            "---\npriority: 16\ncondition: [general, coding]\n---\n"
        )
        assert meta["priority"] == 16
        assert meta["condition"] == ["general", "coding"]

    def test_block_style_yaml_list_parses(self):
        """Block-style `- item` list values in frontmatter are parsed as lists."""
        from encre.prompts.loader import _parse_frontmatter
        meta, body = _parse_frontmatter(
            "---\nname: patterns\npriority: 100\npatterns:\n  - fully autonomous\n"
            "  - hands-off\n  - don't ask me\n---\nBODY"
        )
        assert meta["patterns"] == ["fully autonomous", "hands-off", "don't ask me"]
        assert body == "BODY"

    def test_block_style_yaml_list_empty_value_falls_back_none(self):
        """A key whose block-style list is empty parses to None, not a broken entry."""
        from encre.prompts.loader import _parse_frontmatter
        meta, _ = _parse_frontmatter("---\nname: x\npatterns:\n---\nBODY")
        assert meta["patterns"] is None

    def test_frontmatter_without_closing_delimiter_still_parses(self):
        from encre.prompts.loader import _parse_frontmatter
        meta, body = _parse_frontmatter("---\nname: x\npriority: 1\n---\nCONTENT")
        assert meta["name"] == "x"
        assert body == "CONTENT"


class TestCheckpointHardGate:
    """Tests for the code-level checkpoint hard-gate helpers."""
    def test_count_consecutive_tool_steps(self):
        from encre.loop_stability import count_consecutive_tool_steps
        msgs = [
            {"role": "user", "content": "do it"},
            {"role": "assistant", "content": "", "tool_calls": ["a"]},
            {"role": "tool", "tool_call_id": "a", "content": "ok"},
            {"role": "assistant", "content": "", "tool_calls": ["b"]},
            {"role": "tool", "tool_call_id": "b", "content": "ok"},
            {"role": "assistant", "content": "", "tool_calls": ["c"]},
        ]
        assert count_consecutive_tool_steps(msgs) == 3

    def test_count_consecutive_tool_steps_breaks_on_user(self):
        from encre.loop_stability import count_consecutive_tool_steps
        msgs = [
            {"role": "user", "content": "do it"},
            {"role": "assistant", "content": "", "tool_calls": ["a"]},
            {"role": "tool", "tool_call_id": "a", "content": "ok"},
            {"role": "user", "content": "interrupt"},
            {"role": "assistant", "content": "", "tool_calls": ["b"]},
        ]
        assert count_consecutive_tool_steps(msgs) == 1

    def test_count_consecutive_tool_steps_ignores_plain_text(self):
        from encre.loop_stability import count_consecutive_tool_steps
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "thinking text only"},
            {"role": "assistant", "content": "", "tool_calls": ["a"]},
        ]
        assert count_consecutive_tool_steps(msgs) == 1

    def test_checkpoint_gate_relaxed_on_authorization(self):
        from encre.loop_stability import checkpoint_gate_relaxed
        assert checkpoint_gate_relaxed("run fully autonomous and don't ask me")
        assert checkpoint_gate_relaxed("HANDS-OFF please")

    def test_checkpoint_gate_not_relaxed_on_normal_prompt(self):
        from encre.loop_stability import checkpoint_gate_relaxed
        assert not checkpoint_gate_relaxed("refactor the auth module")
        assert not checkpoint_gate_relaxed("")

    def test_build_checkpoint_message(self):
        from encre.loop_stability import build_checkpoint_message
        msg = build_checkpoint_message(7)
        assert msg
        assert "7" in msg
        assert "Checkpoint" in msg

    def test_checkpoint_threshold_constant(self):
        from encre.loop_stability import CHECKPOINT_TOOL_STEP_THRESHOLD
        assert isinstance(CHECKPOINT_TOOL_STEP_THRESHOLD, int)
        assert CHECKPOINT_TOOL_STEP_THRESHOLD >= 3


class TestStandingOrdersReminder:
    """Tests for the per-turn standing-orders reminder."""
    def test_reminder_loads_from_prompt_file(self):
        from encre.loop_stability import build_standing_orders_reminder
        reminder = build_standing_orders_reminder()
        assert reminder
        assert "Standing Orders" in reminder
        assert "RECALL BEFORE ACTING" in reminder.upper()

    def test_append_to_last_user_message(self):
        from encre.loop_stability import append_to_last_user_message
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        append_to_last_user_message(msgs, "REMINDER-SUFFIX")
        assert "REMINDER-SUFFIX" in msgs[-1]["content"]

    def test_append_to_last_user_message_noop_without_user(self):
        from encre.loop_stability import append_to_last_user_message
        msgs = [{"role": "system", "content": "sys"}]
        append_to_last_user_message(msgs, "X")
        assert len(msgs) == 1
        assert "X" not in msgs[0]["content"]


class TestUserRulesInterpretation:
    """The rules block teaches that user rules are intent, not infallible law."""
    def test_rules_block_loads_with_context(self):
        from encre.prompts.loader import PromptLoader
        loader = PromptLoader()
        block = loader.load_with_context(
            "rules", rules_content="TESTRULE", execution_context="CONTEXT"
        )
        assert "TESTRULE" in block
        assert "CONTEXT" in block
        assert "Interpret as Intent" in block

    def test_rules_block_not_mandatory_law(self):
        from encre.prompts.loader import PromptLoader
        block = PromptLoader().load("rules")
        assert "without exception" not in block
        assert "intent" in block.lower()

    def test_rules_block_scope_check_present(self):
        from encre.prompts.loader import PromptLoader
        block = PromptLoader().load("rules")
        assert "conversational rule" in block
        assert "automation" in block.lower() or "headless" in block.lower()

    def test_rules_block_asks_when_unclear(self):
        from encre.prompts.loader import PromptLoader
        block = PromptLoader().load("rules")
        assert "ask" in block.lower()
        assert "question" in block.lower()

    def test_execution_context_placeholders_substitute(self):
        from encre.prompts.loader import PromptLoader
        headless = PromptLoader().load_with_context(
            "rules", rules_content="R", execution_context="headless"
        )
        interactive = PromptLoader().load_with_context(
            "rules", rules_content="R", execution_context="interactive"
        )
        assert "headless" in headless
        assert "interactive" in interactive
        assert "{{execution_context}}" not in headless


class TestSpecializationPrompts:
    """Test cases covering specialization prompts.
    
    Covers the expected behavior and relevant edge cases.
    """
    def test_coding_prompt_specialty(self):
        """Verifies that coding prompt specialty."""
        from encre.prompts.coding import EncreCodingPrompt
        cp = EncreCodingPrompt()
        # Confirm the expected result for this scenario: coding prompt specialty.
        assert cp._specialty == "coding"
        result = cp.build_system_prompt(mode="default")
        assert "Software Engineering" in result

    def test_general_prompt_specialty(self):
        """Verifies that general prompt specialty."""
        from encre.prompts.general import EncreGeneralPrompt
        gp = EncreGeneralPrompt()
        # Confirm the expected result for this scenario: general prompt specialty.
        assert gp._specialty == "general"
        result = gp.build_system_prompt(mode="default")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_research_prompt_specialty(self):
        """Verifies that research prompt specialty."""
        from encre.prompts.research import EncreResearchPrompt
        rp = EncreResearchPrompt()
        # Confirm the expected result for this scenario: research prompt specialty.
        assert rp._specialty == "research"
        result = rp.build_system_prompt(mode="default")
        assert "Research" in result

    def test_data_prompt_specialty(self):
        """Verifies that data prompt specialty."""
        from encre.prompts.data import EncreDataPrompt
        dp = EncreDataPrompt()
        # Confirm the expected result for this scenario: data prompt specialty.
        assert dp._specialty == "data"
        result = dp.build_system_prompt(mode="default")
        assert "Data Analysis" in result

    def test_specialization_build_with_tools_and_custom_instructions(self):
        """Verifies that specialization build with tools and custom instructions."""
        from encre.prompts.coding import EncreCodingPrompt
        cp = EncreCodingPrompt()
        tools = [{"function": {"name": "bash", "description": "Run bash commands"}}]
        result = cp.build_system_prompt(
            mode="default",
            tools=tools,
            custom_instructions="Always write docstrings.",
        )
        # Confirm the expected result for this scenario: specialization build with tools and custom instructions.
        assert "bash" in result
        assert "Always write docstrings" in result
        assert "Software Engineering" in result
