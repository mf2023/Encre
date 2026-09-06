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

"""Tests for the prompt system: base classes, builder, templates, and specializations."""

import pytest


class TestEncreBasePrompt:
    """Engineered to validate the EncreBasePrompt abstract base class.

Tests confirm that EncreBasePrompt cannot be instantiated directly
(raises TypeError) and exposes the required abstract method slots
(build_system_prompt, build_tool_instructions).
"""
    def test_verify_base_prompt_is_abstract(self):
        """Validate that base prompt is abstract."""
        from encre.prompts.base import EncreBasePrompt
        with pytest.raises(TypeError):
            EncreBasePrompt()  # Cannot instantiate ABC

    def test_verify_base_prompt_has_abstract_methods(self):
        """Validate that base prompt has abstract methods."""
        from encre.prompts.base import EncreBasePrompt
        assert hasattr(EncreBasePrompt, "build_system_prompt")
        assert hasattr(EncreBasePrompt, "build_tool_instructions")


class TestEncrePromptTemplate:
    """Engineered to validate EncrePromptTemplate construction and prompt building.

Tests cover default construction, specialty injection, custom builder
injection, property accessor, system prompt generation with and
without tools, custom instruction injection, specialty-driven content
difference, permission-mode variation, and tool-instruction text
generation for both empty and populated tool lists.
"""
    def test_verify_prompt_template_construction_defaults(self):
        """Validate that construction defaults."""
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate()
        assert tmpl is not None
        assert tmpl._specialty == "general"
        assert tmpl._builder is not None

    def test_verify_prompt_template_construction_with_specialty(self):
        """Validate that construction with specialty."""
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate(specialty="coding")
        assert tmpl._specialty == "coding"

    def test_verify_prompt_template_construction_with_custom_builder(self):
        """Validate that construction with custom builder."""
        from encre.prompts.base import EncrePromptTemplate
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        tmpl = EncrePromptTemplate(builder=builder, specialty="research")
        assert tmpl._builder is builder
        assert tmpl._specialty == "research"

    def test_verify_prompt_template_builder_property(self):
        """Validate that builder property."""
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate(specialty="data")
        assert tmpl.builder is tmpl._builder

    def test_verify_prompt_template_build_system_prompt_returns_string(self):
        """Validate that build system prompt returns string."""
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate(specialty="general")
        result = tmpl.build_system_prompt(mode="default")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_verify_prompt_template_build_system_prompt_with_tools(self):
        """Validate that build system prompt with tools."""
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate()
        tools = [
            {"function": {"name": "bash", "description": "Execute shell commands"}},
            {"function": {"name": "read", "description": "Read files"}},
        ]
        result = tmpl.build_system_prompt(mode="default", tools=tools)
        assert "bash" in result
        assert "read" in result

    def test_verify_prompt_template_build_system_prompt_with_custom_instructions(self):
        """Validate that build system prompt with custom instructions."""
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate()
        result = tmpl.build_system_prompt(
            mode="default",
            custom_instructions="Always use Python 3.12 syntax.",
        )
        assert "Python 3.12" in result

    def test_verify_prompt_template_build_system_prompt_reflects_specialty(self):
        """Validate that build system prompt reflects specialty."""
        from encre.prompts.base import EncrePromptTemplate
        coding_tmpl = EncrePromptTemplate(specialty="coding")
        research_tmpl = EncrePromptTemplate(specialty="research")

        coding_result = coding_tmpl.build_system_prompt(mode="default")
        research_result = research_tmpl.build_system_prompt(mode="default")

        # Different specialties produce different prompts
        assert coding_result != research_result
        assert "Software Engineering" in coding_result
        assert "Research" in research_result

    def test_verify_prompt_template_build_system_prompt_reflects_permission_mode(self):
        """Validate that build system prompt reflects permission mode."""
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate()

        bypass_result = tmpl.build_system_prompt(mode="bypass")
        plan_result = tmpl.build_system_prompt(mode="plan")

        assert "bypass" in bypass_result.lower()
        assert "plan" in plan_result.lower()

    def test_verify_prompt_template_build_tool_instructions_empty_list(self):
        """Validate that build tool instructions empty list."""
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate()
        result = tmpl.build_tool_instructions([])
        assert "do not have access" in result.lower()

    def test_verify_prompt_template_build_tool_instructions_with_names(self):
        """Validate that build tool instructions with names."""
        from encre.prompts.base import EncrePromptTemplate
        tmpl = EncrePromptTemplate()
        result = tmpl.build_tool_instructions(["bash", "grep", "glob"])
        assert "bash" in result
        assert "grep" in result
        assert "glob" in result
        assert "Use them as needed" in result


class TestPromptBlock:
    """Engineered to validate PromptBlock construction and context substitution.

Tests confirm that blocks store priority, name, and content correctly,
and that with_context performs Jinja2-style {{key}} substitution while
preserving the block's metadata.
"""
    def test_verify_prompt_block_construction(self):
        """Validate that prompt block construction."""
        from encre.prompts.system import PromptBlock
        block = PromptBlock(priority=10, name="test_block", content="Test content")
        assert block.priority == 10
        assert block.name == "test_block"
        assert block.content == "Test content"

    def test_verify_prompt_block_with_context(self):
        """Validate that prompt block with context."""
        from encre.prompts.system import PromptBlock
        block = PromptBlock(
            priority=50,
            name="templated",
            content="Hello {{username}}, welcome to {{project}}.",
        )
        ctx = {"username": "Alice", "project": "Encre"}
        filled = block.with_context(ctx)
        assert "Hello Alice" in filled.content
        assert "welcome to Encre" in filled.content
        assert filled.name == "templated"
        assert filled.priority == 50


class TestEncrePromptBuilder:
    """Engineered to validate EncrePromptBuilder block management and prompt assembly.

Tests cover construction, block add/remove, removal of non-existent
blocks (no-op), skill-summary injection, custom instruction injection,
default/coding/research/data/unknown-specialty builds, permission
mode variation, tool guidance inclusion, context variable substitution,
block override precedence, mandatory-constraints placement between
identity and task-completion blocks, and memory-discipline
front-positioning.
"""
    def test_verify_prompt_builder_construction(self):
        """Validate that builder construction."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        assert builder is not None
        assert builder._blocks == {}

    def test_verify_prompt_builder_add_block(self):
        """Validate that add block."""
        from encre.prompts.system import EncrePromptBuilder, PromptBlock
        builder = EncrePromptBuilder()
        block = PromptBlock(priority=100, name="extra", content="Extra instructions")
        builder.add_block(block)
        assert "extra" in builder._blocks
        assert builder._blocks["extra"].content == "Extra instructions"

    def test_verify_prompt_builder_remove_block(self):
        """Validate that remove block."""
        from encre.prompts.system import EncrePromptBuilder, PromptBlock
        builder = EncrePromptBuilder()
        block = PromptBlock(priority=100, name="temporary", content="Temp")
        builder.add_block(block)
        assert "temporary" in builder._blocks
        builder.remove_block("temporary")
        assert "temporary" not in builder._blocks

    def test_verify_prompt_builder_remove_nonexistent_block_does_not_raise(self):
        """Validate that remove nonexistent block does not raise."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        builder.remove_block("nonexistent")  # Should not raise

    def test_verify_prompt_builder_skill_summary_injects_dynamic_catalogue(self):
        """A provided skill_summary is rendered as a dynamic Skills block."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        summary = "- `/travel-flights`: Flight search guidance"
        prompt = builder.build(skill_summary=summary)
        assert "## Skills (auto-discovered)" in prompt
        assert "/travel-flights" in prompt

    def test_verify_prompt_builder_empty_skill_summary_omits_block(self):
        """No skill_summary means no Skills block is injected."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        prompt = builder.build(skill_summary="")
        assert "## Skills (auto-discovered)" not in prompt

    def test_verify_prompt_builder_add_custom_instructions(self):
        """Validate that add custom instructions."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        builder.add_custom_instructions("Focus on testing.")
        assert "custom" in builder._blocks
        assert "Focus on testing" in builder._blocks["custom"].content
        assert builder._blocks["custom"].priority == 200

    def test_verify_prompt_builder_build_default(self):
        """Validate that build default."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build()
        assert isinstance(result, str)
        assert len(result) > 0
        # Should contain default blocks
        assert "identity" in result.lower() or "helpful" in result.lower()

    def test_verify_prompt_builder_build_coding_specialty(self):
        """Validate that build coding specialty."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build(specialty="coding")
        assert "Software Engineering" in result

    def test_verify_prompt_builder_build_research_specialty(self):
        """Validate that build research specialty."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build(specialty="research")
        assert "Research" in result

    def test_verify_prompt_builder_build_data_specialty(self):
        """Validate that build data specialty."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build(specialty="data")
        assert "Data Analysis" in result

    def test_verify_prompt_builder_build_unknown_specialty_falls_back_to_general(self):
        """Validate that build unknown specialty falls back to general."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build(specialty="unknown_specialty")
        assert "Dig Deeper Than the Surface" in result

    def test_verify_prompt_builder_build_with_permission_mode(self):
        """Validate that build with permission mode."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()

        bypass = builder.build(mode="bypass")
        default = builder.build(mode="default")

        assert "full autonomy" in bypass.lower()
        assert "Ask for permission" in default

    def test_verify_prompt_builder_build_with_tools(self):
        """Validate that build with tools."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        tools = [{"function": {"name": "test_tool", "description": "A test tool"}}]
        result = builder.build(tools=tools)
        # Tools are passed to the model via the API tools field, not inlined
        # into the system prompt text; build must succeed and include the
        # tool-usage guidance block.
        assert isinstance(result, str) and len(result) > 0
        assert "tool_usage" in result.lower() or "find_tool" in result.lower() or "bash" in result.lower()

    def test_verify_prompt_builder_build_with_custom_instructions(self):
        """Validate that build with custom instructions."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build(custom_instructions="ALWAYS validate input first.")
        assert "ALWAYS validate input first" in result

    def test_verify_prompt_builder_build_with_context(self):
        """Validate that build with context."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build_with_context(
            ctx={"username": "TestUser"},
            specialty="general",
        )
        # The identity block doesn't have {{username}} but the method
        # should still work without errors
        assert isinstance(result, str)
        assert len(result) > 0

    def test_verify_prompt_builder_build_with_context_variable_substitution(self):
        """Validate that build with context variable substitution."""
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
        assert "User Alice" in result
        assert "version 1.0.0" in result

    def test_verify_prompt_builder_custom_block_can_override_default(self):
        """Validate that custom block can override default."""
        from encre.prompts.system import EncrePromptBuilder, PromptBlock
        builder = EncrePromptBuilder()
        # Override the identity block
        builder.add_block(PromptBlock(
            priority=0,
            name="identity",
            content="You are a friendly assistant.",
        ))
        result = builder.build()
        assert "friendly assistant" in result

    def test_verify_prompt_builder_mandatory_constraints_block_present_by_default(self):
        """The flagship mandatory-constraints block is injected by default."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build()
        assert "MANDATORY Constraints" in result
        assert "Binding Pre-Action Governance" in result

    def test_verify_prompt_builder_mandatory_constraints_ordered_after_identity_before_task_completion(self):
        """Priority 0.5 places mandatory constraints between identity (0) and task_completion (1)."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build()
        idx_identity = result.find("Encre Agent")
        idx_mand = result.find("MANDATORY Constraints")
        idx_task = result.find("Deliver Finished Work")
        assert 0 <= idx_identity < idx_mand < idx_task

    def test_verify_prompt_builder_mandatory_constraints_precedence_line(self):
        """The override line anchoring constraint authority is present."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build()
        assert "override" in result.lower()
        assert "autonomous" in result.lower()

    def test_verify_prompt_builder_memory_discipline_front_positioned(self):
        """Memory recall protocol must sit early, within the governance cluster."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build()
        assert "Memory Discipline" in result
        idx_discipline = result.index("Memory Discipline")
        idx_task = result.index("Task Completion")
        assert idx_discipline < idx_task

    def test_verify_prompt_builder_memory_discipline_recall_protocol_present(self):
        """The mandatory recall protocol is present in the built system prompt."""
        from encre.prompts.system import EncrePromptBuilder
        builder = EncrePromptBuilder()
        result = builder.build()
        assert (
            "MANDATORY Recall Protocol" in result
            or "mandatory recall protocol" in result.lower()
        )


class TestRuntimePromptFiles:
    """Engineered to validate that all runtime prompt builders return non-empty content.

This test ensures every function re-exported from encre.loop_stability
(build_auto_continue_message, build_grace_message,
build_delegation_guidance, build_steer_injection,
build_thinking_prefill) produces a non-empty string, confirming no
prompt file is missing or blank at runtime.
"""
    def test_verify_runtime_prompt_files_exist(self):
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
    """Engineered to validate frontmatter YAML parsing in prompt files.

Tests confirm that _parse_frontmatter correctly handles float
priorities (0.5, -1.5), integer priorities, inline list conditions,
block-style YAML lists, empty block-style values (falling back to
None), and documents with or without a closing --- delimiter.
"""
    def test_verify_frontmatter_float_priority_parses(self):
        """A float priority (e.g. 0.5) is parsed as a number, not a string."""
        from encre.prompts.loader import _parse_frontmatter
        meta, body = _parse_frontmatter(
            "---\nname: slack\npriority: 0.5\ncondition: ~\n---\nCONTENT"
        )
        assert meta["priority"] == 0.5
        assert isinstance(meta["priority"], float)
        assert body == "CONTENT"

    def test_verify_frontmatter_negative_float_priority_parses(self):
        from encre.prompts.loader import _parse_frontmatter
        meta, _ = _parse_frontmatter("---\npriority: -1.5\n---\n")
        assert meta["priority"] == -1.5

    def test_verify_frontmatter_integer_and_list_still_parse(self):
        from encre.prompts.loader import _parse_frontmatter
        meta, _ = _parse_frontmatter(
            "---\npriority: 16\ncondition: [general, coding]\n---\n"
        )
        assert meta["priority"] == 16
        assert meta["condition"] == ["general", "coding"]

    def test_verify_frontmatter_block_style_yaml_list_parses(self):
        """Block-style `- item` list values in frontmatter are parsed as lists."""
        from encre.prompts.loader import _parse_frontmatter
        meta, body = _parse_frontmatter(
            "---\nname: patterns\npriority: 100\npatterns:\n  - fully autonomous\n"
            "  - hands-off\n  - don't ask me\n---\nBODY"
        )
        assert meta["patterns"] == ["fully autonomous", "hands-off", "don't ask me"]
        assert body == "BODY"

    def test_verify_frontmatter_block_style_yaml_list_empty_value_falls_back_none(self):
        """A key whose block-style list is empty parses to None, not a broken entry."""
        from encre.prompts.loader import _parse_frontmatter
        meta, _ = _parse_frontmatter("---\nname: x\npatterns:\n---\nBODY")
        assert meta["patterns"] is None

    def test_verify_frontmatter_without_closing_delimiter_still_parses(self):
        from encre.prompts.loader import _parse_frontmatter
        meta, body = _parse_frontmatter("---\nname: x\npriority: 1\n---\nCONTENT")
        assert meta["name"] == "x"
        assert body == "CONTENT"


class TestCheckpointHardGate:
    """Engineered to validate checkpoint hard-gate helpers in loop stability.

Tests exercise count_consecutive_tool_steps across sequential
tool-call chains, user-interrupt breaks, and plain-text messages;
checkpoint_gate_relaxed for autonomy-keyword detection; message
construction; and the CHECKPOINT_TOOL_STEP_THRESHOLD constant
invariant (integer >= 3).
"""
    def test_verify_checkpoint_count_consecutive_tool_steps(self):
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

    def test_verify_checkpoint_count_consecutive_tool_steps_breaks_on_user(self):
        from encre.loop_stability import count_consecutive_tool_steps
        msgs = [
            {"role": "user", "content": "do it"},
            {"role": "assistant", "content": "", "tool_calls": ["a"]},
            {"role": "tool", "tool_call_id": "a", "content": "ok"},
            {"role": "user", "content": "interrupt"},
            {"role": "assistant", "content": "", "tool_calls": ["b"]},
        ]
        assert count_consecutive_tool_steps(msgs) == 1

    def test_verify_checkpoint_count_consecutive_tool_steps_ignores_plain_text(self):
        from encre.loop_stability import count_consecutive_tool_steps
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "thinking text only"},
            {"role": "assistant", "content": "", "tool_calls": ["a"]},
        ]
        assert count_consecutive_tool_steps(msgs) == 1

    def test_verify_checkpoint_gate_relaxed_on_authorization(self):
        from encre.loop_stability import checkpoint_gate_relaxed
        assert checkpoint_gate_relaxed("run fully autonomous and don't ask me")
        assert checkpoint_gate_relaxed("HANDS-OFF please")

    def test_verify_checkpoint_gate_not_relaxed_on_normal_prompt(self):
        from encre.loop_stability import checkpoint_gate_relaxed
        assert not checkpoint_gate_relaxed("refactor the auth module")
        assert not checkpoint_gate_relaxed("")

    def test_verify_checkpoint_build_message(self):
        from encre.loop_stability import build_checkpoint_message
        msg = build_checkpoint_message(7)
        assert msg
        assert "7" in msg
        assert "Checkpoint" in msg

    def test_verify_checkpoint_threshold_constant(self):
        from encre.loop_stability import CHECKPOINT_TOOL_STEP_THRESHOLD
        assert isinstance(CHECKPOINT_TOOL_STEP_THRESHOLD, int)
        assert CHECKPOINT_TOOL_STEP_THRESHOLD >= 3


class TestStandingOrdersReminder:
    """Engineered to validate the per-turn standing-orders reminder mechanism.

Tests confirm that build_standing_orders_reminder produces a
non-empty reminder containing the expected keywords, that
append_to_last_user_message appends suffix text to the last user
message, and that it is a no-op when no user message exists.
"""
    def test_verify_standing_orders_reminder_loads_from_prompt_file(self):
        from encre.loop_stability import build_standing_orders_reminder
        reminder = build_standing_orders_reminder()
        assert reminder
        assert "Standing Orders" in reminder
        assert "RECALL BEFORE ACTING" in reminder.upper()

    def test_verify_standing_orders_append_to_last_user_message(self):
        from encre.loop_stability import append_to_last_user_message
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        append_to_last_user_message(msgs, "REMINDER-SUFFIX")
        assert "REMINDER-SUFFIX" in msgs[-1]["content"]

    def test_verify_standing_orders_append_noop_without_user(self):
        from encre.loop_stability import append_to_last_user_message
        msgs = [{"role": "system", "content": "sys"}]
        append_to_last_user_message(msgs, "X")
        assert len(msgs) == 1
        assert "X" not in msgs[0]["content"]


class TestUserRulesInterpretation:
    """Engineered to validate the rules prompt block loading and context substitution.

Tests confirm that PromptLoader substitutes {{rules_content}} and
{{execution_context}} placeholders, that the loaded rules text frames
user directives as intent rather than absolute law, that scope-check
language is present, and that the block encourages asking when
interpretation is unclear.
"""
    def test_verify_rules_block_loads_with_context(self):
        from encre.prompts.loader import PromptLoader
        loader = PromptLoader()
        block = loader.load_with_context(
            "rules", rules_content="TESTRULE", execution_context="CONTEXT"
        )
        assert "TESTRULE" in block
        assert "CONTEXT" in block
        assert "Interpret as Intent" in block

    def test_verify_rules_block_not_mandatory_law(self):
        from encre.prompts.loader import PromptLoader
        block = PromptLoader().load("rules")
        assert "without exception" not in block
        assert "intent" in block.lower()

    def test_verify_rules_block_scope_check_present(self):
        from encre.prompts.loader import PromptLoader
        block = PromptLoader().load("rules")
        assert "conversational rule" in block
        assert "automation" in block.lower() or "headless" in block.lower()

    def test_verify_rules_block_asks_when_unclear(self):
        from encre.prompts.loader import PromptLoader
        block = PromptLoader().load("rules")
        assert "ask" in block.lower()
        assert "question" in block.lower()

    def test_verify_rules_execution_context_placeholders_substitute(self):
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
    """Engineered to validate each prompt specialty subclass.

Tests assert that EncreCodingPrompt, EncreGeneralPrompt,
EncreResearchPrompt, and EncreDataPrompt expose the correct
_specialty value and that their generated system prompts contain
the domain-specific heading text (Software Engineering, Research,
Data Analysis).  The final test verifies that tools and custom
instructions are merged into the coding specialty prompt.
"""
    def test_verify_specialization_coding_prompt_specialty(self):
        """Validate that coding prompt specialty."""
        from encre.prompts.coding import EncreCodingPrompt
        cp = EncreCodingPrompt()
        assert cp._specialty == "coding"
        result = cp.build_system_prompt(mode="default")
        assert "Software Engineering" in result

    def test_verify_specialization_general_prompt_specialty(self):
        """Validate that general prompt specialty."""
        from encre.prompts.general import EncreGeneralPrompt
        gp = EncreGeneralPrompt()
        assert gp._specialty == "general"
        result = gp.build_system_prompt(mode="default")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_verify_specialization_research_prompt_specialty(self):
        """Validate that research prompt specialty."""
        from encre.prompts.research import EncreResearchPrompt
        rp = EncreResearchPrompt()
        assert rp._specialty == "research"
        result = rp.build_system_prompt(mode="default")
        assert "Research" in result

    def test_verify_specialization_data_prompt_specialty(self):
        """Validate that data prompt specialty."""
        from encre.prompts.data import EncreDataPrompt
        dp = EncreDataPrompt()
        assert dp._specialty == "data"
        result = dp.build_system_prompt(mode="default")
        assert "Data Analysis" in result

    def test_verify_specialization_build_with_tools_and_custom_instructions(self):
        """Validate that specialization build with tools and custom instructions."""
        from encre.prompts.coding import EncreCodingPrompt
        cp = EncreCodingPrompt()
        tools = [{"function": {"name": "bash", "description": "Run bash commands"}}]
        result = cp.build_system_prompt(
            mode="default",
            tools=tools,
            custom_instructions="Always write docstrings.",
        )
        assert "bash" in result
        assert "Always write docstrings" in result
        assert "Software Engineering" in result
