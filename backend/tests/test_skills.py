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

"""Tests for the skills registry, bundled skill definitions, and skill lookup."""

import pytest


class TestBundledSkillDefinition:
    """Engineered to validate BundledSkillDefinition construction and field population.

    This test class exercises the BundledSkillDefinition dataclass across 5
    scenarios: minimal construction, full field population, default value
    preservation, prompt injection with args, and prompt injection with context.
    The design ensures the skill definition type correctly stores and
    propagates all configuration fields including async prompt functions.
    """
    def test_verify_minimal_construction(self):
        """Validate that BundledSkillDefinition constructs with only required fields.

        The test exercises construction with name, description, and get_prompt_for_command
        and asserts the provided values are stored and optional fields (aliases, etc.)
        default to their documented empty/falsy values because the constructor must
        support minimal definition without requiring every field.
        """
        from encre.skills.types import BundledSkillDefinition

        async def _prompt_fn(args, ctx):
            return "test prompt"

        skill = BundledSkillDefinition(
            name="test_skill",
            description="A test skill",
            get_prompt_for_command=_prompt_fn,
        )
        assert skill.name == "test_skill"
        assert skill.description == "A test skill"
        assert skill.get_prompt_for_command is _prompt_fn
        assert skill.aliases == []

    def test_verify_all_fields_populated(self):
        """Validate that all optional fields are stored correctly when provided.

        The test exercises construction with every field populated and asserts
        each field matches the input value because full-population must round-trip
        without any field being silently dropped or defaulted.
        """
        from encre.skills.types import (
            BundledSkillDefinition,
            SkillContext,
            SkillSource,
        )

        async def _prompt_fn(args, ctx):
            return "custom prompt"

        skill = BundledSkillDefinition(
            name="full_skill",
            description="Fully populated skill",
            get_prompt_for_command=_prompt_fn,
            aliases=["fs", "full"],
            when_to_use=".py .rs",
            argument_hint="[target: file to process]",
            allowed_tools=["bash", "grep"],
            model="gpt-5.6",
            disable_model_invocation=False,
            user_invocable=True,
            context=SkillContext.INLINE,
            source=SkillSource.BUNDLED,
            file_path="/path/to/skill.md",
        )
        assert skill.name == "full_skill"
        assert skill.aliases == ["fs", "full"]
        assert skill.when_to_use == ".py .rs"
        assert skill.argument_hint == "[target: file to process]"
        assert skill.allowed_tools == ["bash", "grep"]
        assert skill.model == "gpt-5.6"
        assert skill.disable_model_invocation is False
        assert skill.user_invocable is True
        assert skill.context == SkillContext.INLINE
        assert skill.source == SkillSource.BUNDLED
        assert skill.file_path == "/path/to/skill.md"

    def test_verify_default_values(self):
        """Validate that omitted fields take their documented default values.

        The test exercises minimal construction and asserts aliases=[],
        when_to_use="", argument_hint="", allowed_tools=None, model=None,
        disable_model_invocation=False, user_invocable=True, context=INLINE,
        source=BUNDLED, and file_path="" because defaults must match the
        expected baseline for each field.
        """
        from encre.skills.types import (
            BundledSkillDefinition,
            SkillContext,
            SkillSource,
        )

        async def _prompt_fn(args, ctx):
            return "default test"

        skill = BundledSkillDefinition(
            name="defaults",
            description="Testing defaults",
            get_prompt_for_command=_prompt_fn,
        )
        assert skill.aliases == []
        assert skill.when_to_use == ""
        assert skill.argument_hint == ""
        assert skill.allowed_tools is None
        assert skill.model is None
        assert skill.disable_model_invocation is False
        assert skill.user_invocable is True
        assert skill.context == SkillContext.INLINE
        assert skill.source == SkillSource.BUNDLED
        assert skill.file_path == ""

    @pytest.mark.asyncio
    async def test_verify_get_prompt_for_command_with_args(self):
        """Validate that get_prompt_for_command passes args through to the prompt function.

        The test exercises the async prompt function with args="file.py" and
        ctx={} and asserts the returned prompt is "debug file.py" because
        the prompt injection layer must forward tool-call arguments to the
        skill's prompt function.
        """
        from encre.skills.types import BundledSkillDefinition

        async def _prompt_fn(args, ctx):
            return f"debug {args or 'nothing'}"

        skill = BundledSkillDefinition(
            name="echo",
            description="Echo skill",
            get_prompt_for_command=_prompt_fn,
        )
        result = await skill.get_prompt_for_command("file.py", {})
        assert result == "debug file.py"

    @pytest.mark.asyncio
    async def test_verify_get_prompt_for_command_with_context(self):
        """Validate that get_prompt_for_command passes ctx through to the prompt function.

        The test exercises the async prompt function with args=None and
        ctx={"mode": "verbose"} and asserts the returned prompt is
        "mode=verbose" because the context dictionary must be forwarded
        so the prompt function can make context-aware decisions.
        """
        from encre.skills.types import BundledSkillDefinition

        async def _prompt_fn(args, ctx):
            return f"mode={ctx.get('mode', 'default')}"

        skill = BundledSkillDefinition(
            name="ctx_skill",
            description="Context skill",
            get_prompt_for_command=_prompt_fn,
        )
        result = await skill.get_prompt_for_command(None, {"mode": "verbose"})
        assert result == "mode=verbose"


class TestEncreSkillRegistry:
    """Engineered to validate the EncreSkillRegistry registration, lookup, and priority semantics.

    This test class exercises the registry across 10 scenarios covering creation,
    name lookup, alias lookup, nonexistent lookup, multi-skill registration,
    listing, same-source overwrite prevention, higher-priority overwrite,
    async activation, and async activation of nonexistent skills. The design
    ensures the registry maintains correct priority ordering and alias resolution.
    """
    def test_verify_create_registry(self):
        """Validate that EncreSkillRegistry instantiates without error.

        The test exercises registry construction and asserts the instance is
        not None because registry creation is a prerequisite for all lookup
        and registration operations.
        """
        from encre.skills.registry import EncreSkillRegistry
        registry = EncreSkillRegistry()
        assert registry is not None

    def test_verify_register_and_lookup_by_name(self):
        """Validate that a registered skill is discoverable by its primary name.

        The test exercises register with a BundledSkillDefinition named "greet"
        and asserts lookup("greet") returns a non-None skill with the correct
        name and description because primary-name lookup is the core registry
        contract.
        """
        from encre.skills.registry import EncreSkillRegistry
        from encre.skills.types import BundledSkillDefinition

        async def _prompt_fn(args, ctx):
            return "hello"

        registry = EncreSkillRegistry()
        skill = BundledSkillDefinition(
            name="greet",
            description="Greeting skill",
            get_prompt_for_command=_prompt_fn,
        )
        registry.register(skill)
        found = registry.lookup("greet")
        assert found is not None
        assert found.name == "greet"
        assert found.description == "Greeting skill"

    def test_verify_lookup_nonexistent_returns_none(self):
        """Validate that lookup returns None for a skill that was never registered.

        The test exercises lookup("nonexistent") on an empty registry and
        asserts None because undefined skills must not raise but return a
        safe sentinel value.
        """
        from encre.skills.registry import EncreSkillRegistry
        registry = EncreSkillRegistry()
        assert registry.lookup("nonexistent") is None

    def test_verify_lookup_by_alias(self):
        """Validate that a skill is discoverable via any of its registered aliases.

        The test exercises register with aliases=["orig", "og"] and asserts
        both aliases resolve to the same skill with name "original" because
        alias resolution is a key registry feature for user convenience.
        """
        from encre.skills.registry import EncreSkillRegistry
        from encre.skills.types import BundledSkillDefinition

        async def _prompt_fn(args, ctx):
            return "alias test"

        registry = EncreSkillRegistry()
        skill = BundledSkillDefinition(
            name="original",
            description="Original skill",
            get_prompt_for_command=_prompt_fn,
            aliases=["orig", "og"],
        )
        registry.register(skill)

        found = registry.lookup("orig")
        assert found is not None
        assert found.name == "original"

        found2 = registry.lookup("og")
        assert found2 is not None
        assert found2.name == "original"

    def test_verify_register_multiple_skills(self):
        """Validate that multiple skills can coexist in the registry.

        The test exercises register with two distinct skills ("alpha" and
        "beta") and asserts both are discoverable because the registry must
        support multi-skill deployments.
        """
        from encre.skills.registry import EncreSkillRegistry
        from encre.skills.types import BundledSkillDefinition

        async def _prompt_fn(args, ctx):
            return "multi"

        registry = EncreSkillRegistry()
        skill_a = BundledSkillDefinition(
            name="alpha", description="Alpha", get_prompt_for_command=_prompt_fn
        )
        skill_b = BundledSkillDefinition(
            name="beta", description="Beta", get_prompt_for_command=_prompt_fn
        )
        registry.register(skill_a)
        registry.register(skill_b)
        assert registry.lookup("alpha") is not None
        assert registry.lookup("beta") is not None

    def test_verify_list_all_returns_registered_skills(self):
        """Validate that list_all returns all registered skills including the newly added one.

        The test exercises register with a single skill named "listable" and
        asserts len(list_all()) >= 1 and "listable" is in the name set because
        list_all must surface every registered skill for catalogue generation.
        """
        from encre.skills.registry import EncreSkillRegistry
        from encre.skills.types import BundledSkillDefinition

        async def _prompt_fn(args, ctx):
            return "list"

        registry = EncreSkillRegistry()
        skill = BundledSkillDefinition(
            name="listable", description="Listable", get_prompt_for_command=_prompt_fn
        )
        registry.register(skill)

        all_skills = registry.list_all()
        assert len(all_skills) >= 1
        names = [s.name for s in all_skills]
        assert "listable" in names

    def test_verify_register_with_same_source_priority_overwrites(self):
        """Validate that registering the same name with equal priority does not overwrite.

        The test exercises register twice with the same name "same" and
        source=BUNDLED (priority 3) and asserts the first registration
        wins because the registry uses a >= check that returns early when
        new_priority is not strictly greater than old_priority.
        """
        from encre.skills.registry import EncreSkillRegistry
        from encre.skills.types import BundledSkillDefinition, SkillSource

        async def _prompt_fn(args, ctx):
            return "first"

        async def _prompt_fn2(args, ctx):
            return "second"

        registry = EncreSkillRegistry()
        skill1 = BundledSkillDefinition(
            name="same", description="First", get_prompt_for_command=_prompt_fn,
            source=SkillSource.BUNDLED
        )
        skill2 = BundledSkillDefinition(
            name="same", description="Second", get_prompt_for_command=_prompt_fn2,
            source=SkillSource.BUNDLED
        )
        registry.register(skill1)
        registry.register(skill2)
        # With same priority (BUNDLED=3), the second should NOT overwrite
        # because new_priority >= old_priority returns early
        found = registry.lookup("same")
        assert found is not None
        assert found.description == "First"

    def test_verify_higher_priority_overwrites_lower(self):
        """Validate that a higher-priority registration overwrites a lower-priority one.

        The test exercises register BUNDLED (priority 3) then MANAGED (priority 0)
        for the same name "override_test" and asserts the MANAGED description
        wins because MANAGED has higher priority (lower numeric value) than
        BUNDLED and must override it.
        """
        from encre.skills.registry import EncreSkillRegistry
        from encre.skills.types import BundledSkillDefinition, SkillSource

        async def _prompt_fn(args, ctx):
            return "managed"

        async def _prompt_fn2(args, ctx):
            return "bundled"

        registry = EncreSkillRegistry()
        skill_bundled = BundledSkillDefinition(
            name="override_test", description="Bundled version",
            get_prompt_for_command=_prompt_fn2, source=SkillSource.BUNDLED
        )
        skill_managed = BundledSkillDefinition(
            name="override_test", description="Managed version",
            get_prompt_for_command=_prompt_fn, source=SkillSource.MANAGED
        )
        registry.register(skill_bundled)
        registry.register(skill_managed)
        # MANAGED (0) has higher priority than BUNDLED (3), should overwrite
        found = registry.lookup("override_test")
        assert found.description == "Managed version"

    @pytest.mark.asyncio
    async def test_verify_activate_returns_prompt(self):
        """Validate that activate returns the prompt string from the skill's prompt function.

        The test exercises register with a skill named "activable" and
        await registry.activate("activable") and asserts the returned string
        is "activated prompt content" because activate must invoke the
        get_prompt_for_command function and return its output.
        """
        from encre.skills.registry import EncreSkillRegistry
        from encre.skills.types import BundledSkillDefinition

        async def _prompt_fn(args, ctx):
            return "activated prompt content"

        registry = EncreSkillRegistry()
        skill = BundledSkillDefinition(
            name="activable", description="Activatable",
            get_prompt_for_command=_prompt_fn
        )
        registry.register(skill)
        result = await registry.activate("activable")
        assert result == "activated prompt content"

    @pytest.mark.asyncio
    async def test_verify_activate_nonexistent_returns_error(self):
        """Validate that activate returns an error string for a nonexistent skill.

        The test exercises activate("ghost") on an empty registry and
        asserts the result contains "not found" because activate must
        communicate the absence gracefully rather than raising.
        """
        from encre.skills.registry import EncreSkillRegistry
        registry = EncreSkillRegistry()
        result = await registry.activate("ghost")
        assert "not found" in result


class TestCreateBundledSkills:
    """Engineered to validate the create_bundled_skills pipeline and registry integration.

    This test class exercises the full bundled-skill creation flow across 9
    scenarios covering registry population, document-skill auto-activation,
    alias resolution, listing, activation, source verification, builtin
    metadata, catalogue contract, and arg substitution. The design ensures
    the bundled-skill loader produces a complete, functional skill registry.
    """

    @staticmethod
    def _full_registry():
        """Build a registry mirroring the agent's real load sequence.

        Returns:
            An EncreSkillRegistry with bundled skills created via
            create_bundled_skills and static SKILL.md skills loaded from
            the builtin directory.
        """
        from encre.skills.bundled import create_bundled_skills
        from encre.skills.builtin import builtin_skills_dir
        from encre.skills.registry import EncreSkillRegistry
        from encre.skills.types import SkillSource

        registry = EncreSkillRegistry()
        create_bundled_skills(registry)
        registry.load_from_dir(builtin_skills_dir(), source=SkillSource.BUNDLED)
        return registry

    def test_verify_create_bundled_skills_populates_registry(self):
        """Validate that create_bundled_skills registers all 5 core bundled skills.

        The test exercises _full_registry and asserts debug, loop, batch,
        verify, and stuck are all non-None with correct names because the
        bundled loader must populate the registry with the complete skill set.
        """
        registry = self._full_registry()

        # All 5 bundled skills should be registered
        debug = registry.lookup("debug")
        assert debug is not None
        assert debug.name == "debug"
        assert "debug" in debug.description.lower() or "Debug" in debug.description

        loop = registry.lookup("loop")
        assert loop is not None
        assert loop.name == "loop"

        batch = registry.lookup("batch")
        assert batch is not None
        assert batch.name == "batch"

        verify = registry.lookup("verify")
        assert verify is not None
        assert verify.name == "verify"

        stuck = registry.lookup("stuck")
        assert stuck is not None
        assert stuck.name == "stuck"

    def test_verify_document_skills_auto_activate_by_extension(self):
        """Validate that document skills auto-activate and process skills do not.

        The test exercises activate_for_paths for .pdf, .py, .csv, .mp4, and
        .mp3 files and asserts document skills (pdf, docx, pptx, xlsx, images,
        video, audio, data-files) have auto_activate=True while process skills
        (code-review, refactor, gen-test, verify, data-viz) have auto_activate=False
        because only document skills should fire on mere file references.
        """
        import asyncio
        registry = self._full_registry()

        # Document skills opt into auto-activation.
        for name in ("pdf", "docx", "pptx", "xlsx", "images", "video", "audio", "data-files"):
            skill = registry.lookup(name)
            assert skill is not None, f"missing document skill: {name}"
            assert skill.auto_activate is True, f"{name} should auto_activate"

        # Process skills must NOT auto-activate from a mere file reference.
        for name in ("code-review", "refactor", "gen-test", "verify", "data-viz"):
            skill = registry.lookup(name)
            assert skill is not None, f"missing process skill: {name}"
            assert skill.auto_activate is False, f"{name} should NOT auto_activate"

        async def run():
            # .pdf -> pdf; .py -> nothing (code-review/refactor must not fire).
            assert await registry.activate_for_paths(["/x/report.pdf"]) == ["pdf"]
            assert await registry.activate_for_paths(["/x/main.py"]) == []
            # .csv matches both data-viz and data-files when_to_use, but only
            # data-files has auto_activate -> data-viz must be excluded.
            assert await registry.activate_for_paths(["/x/data.csv"]) == ["data-files"]
            # Multiple extensions resolve to multiple skills.
            names = set(await registry.activate_for_paths(["/x/clip.mp4", "/x/song.mp3"]))
            assert names == {"video", "audio"}

        asyncio.run(run())

    def test_verify_bundled_skill_lookup_by_alias(self):
        """Validate that bundled skills are discoverable via their registered aliases.

        The test exercises lookup with alias strings "dbg", "schedule", and
        "parallel" and asserts they resolve to "debug", "loop", and "batch"
        respectively because alias resolution must work for all bundled skills.
        """
        registry = self._full_registry()

        # debug aliases: dbg, diag, troubleshoot
        found = registry.lookup("dbg")
        assert found is not None
        assert found.name == "debug"

        # loop aliases: repeat, schedule, watch
        found = registry.lookup("schedule")
        assert found is not None
        assert found.name == "loop"

        # batch aliases: parallel, multi-agent, farm, orchestrate
        found = registry.lookup("parallel")
        assert found is not None
        assert found.name == "batch"

    def test_verify_list_all_after_create_bundled_skills(self):
        """Validate that list_all includes all 5 core bundled skills.

        The test exercises list_all on the full registry and asserts the
        skill-name set is a superset of {"debug", "loop", "batch", "verify", "stuck"}
        because list_all must surface every registered skill for catalogue rendering.
        """
        registry = self._full_registry()

        all_skills = registry.list_all()
        skill_names = {s.name for s in all_skills}
        assert skill_names >= {"debug", "loop", "batch", "verify", "stuck"}

    @pytest.mark.asyncio
    async def test_verify_bundled_skill_activation(self):
        """Validate that activating a bundled skill returns a non-empty prompt string.

        The test exercises activate("debug") on the full registry and asserts
        the result is non-None and has length > 0 because activation must
        produce a prompt that the LLM can consume.
        """
        registry = self._full_registry()

        result = await registry.activate("debug")
        assert result is not None
        assert len(result) > 0

    def test_verify_bundled_skill_sources(self):
        """Validate that all listed skills have source=BUNDLED.

        The test exercises list_all and asserts every skill's source is
        SkillSource.BUNDLED because the create_bundled_skills pipeline must
        tag every produced skill with the correct source.
        """
        from encre.skills.types import SkillSource

        registry = self._full_registry()

        for skill in registry.list_all():
            assert skill.source == SkillSource.BUNDLED

    def test_verify_builtin_skills_hidden_and_static_count(self):
        """Validate that the 10 migrated static skills are hidden with non-empty bodies.

        The test exercises lookup on each static skill name and asserts
        hidden=True, source.name=="BUNDLED", and body is non-empty because
        static SKILL.md skills must be injected silently (hidden) and carry
        their markdown body for prompt rendering.
        """
        registry = self._full_registry()

        # The 10 migrated static skills + loop = 11 builtin skills total.
        static_names = {
            "debug", "verify", "stuck", "web-research", "code-review",
            "refactor", "write-docs", "data-viz", "gen-test", "batch",
        }
        for name in static_names:
            skill = registry.lookup(name)
            assert skill is not None, f"missing builtin skill: {name}"
            assert skill.hidden is True, f"{name} should be hidden"
            assert skill.source.name == "BUNDLED"
            assert skill.body, f"{name} body should not be empty"

    def test_verify_skill_catalogue_contract(self):
        """Validate that the catalogue excludes tool-* skills and includes domain skills.

        The test exercises catalogue construction by filtering list_all() for
        user_invocable and non-tool-* names and asserts representative domain
        skills (travel-flights, pdf, docx, data-viz, debug) are present and
        that tool-* skills are completely disjoint from the catalogue because
        tool-* skills are auto-injected guidance, not user-facing entries.
        """
        registry = self._full_registry()

        catalogue = [
            s for s in registry.list_all()
            if s.user_invocable and not s.name.startswith("tool-")
        ]
        catalogue_names = {s.name for s in catalogue}

        # Domain skills appear (representative sample across categories).
        for name in ("travel-flights", "pdf", "docx", "data-viz", "debug"):
            assert name in catalogue_names, f"{name} should be in the catalogue"

        # tool-* skills are excluded (auto-injected, not catalogue entries).
        tool_skills = {s.name for s in registry.list_all() if s.name.startswith("tool-")}
        assert tool_skills, "precondition: tool-* skills exist"
        assert catalogue_names.isdisjoint(tool_skills), "tool-* must not be in the catalogue"

    @pytest.mark.asyncio
    async def test_verify_builtin_skill_arg_substitution(self):
        """Validate that SKILL.md {{args}} placeholders are substituted on activation.

        The test exercises activate("debug", args="auth_service.py") and
        asserts the returned prompt contains "auth_service.py" because the
        argument-substitution layer must replace {{args}} tokens with the
        passed argument string.
        """
        registry = self._full_registry()

        result = await registry.activate("debug", args="auth_service.py")
        assert "auth_service.py" in result


class TestLoopSkillInjection:
    """Engineered to validate loop-level tool-skill and doc-skill auto-injection wiring.

    This test class exercises _collect_tool_skill, _collect_doc_skills,
    _render_active_tool_skills, and _render_active_doc_skills across 5
    scenarios covering tool-skill round-trip injection, idempotent
    re-collection, unknown-tool no-op, doc-skill auto-activation by
    extension, and process-skill suppression on code files. The design
    ensures the loop's skill-injection layer produces correct system-prompt
    additions without duplicating entries.
    """

    @staticmethod
    def _stub_loop():
        """Create a lightweight stub carrying the attributes the loop methods read.

        Returns:
            A types.SimpleNamespace with skill_registry, _skill_mgr, and
            the bound loop methods (_collect_tool_skill, _collect_doc_skills,
            _render_active_tool_skills, _render_active_doc_skills).
        """
        import types

        from encre.loop import EncreLoop
        from encre.skills.bundled import create_bundled_skills
        from encre.skills.builtin import builtin_skills_dir
        from encre.skills.registry import EncreSkillRegistry
        from encre.skills.types import SkillSource

        registry = EncreSkillRegistry()
        create_bundled_skills(registry)
        registry.load_from_dir(builtin_skills_dir(), source=SkillSource.BUNDLED)

        from encre.loop_skills import SkillManager
        stub = types.SimpleNamespace(
            skill_registry=registry,
            _skill_mgr=SkillManager(registry),
        )
        stub._active_tool_skills = stub._skill_mgr._active_tool_skills
        stub._active_doc_skills = stub._skill_mgr._active_doc_skills
        stub._collect_tool_skill = EncreLoop._collect_tool_skill.__get__(stub)
        stub._collect_doc_skills = EncreLoop._collect_doc_skills.__get__(stub)
        stub._render_active_tool_skills = EncreLoop._render_active_tool_skills.__get__(stub)
        stub._render_active_doc_skills = EncreLoop._render_active_doc_skills.__get__(stub)
        return stub

    @pytest.mark.asyncio
    async def test_verify_tool_skill_round_trip_injects_and_renders(self):
        """Validate that collecting a used tool surfaces its tool-<name> guidance in the render.

        The test exercises _collect_tool_skill("bash") then _render_active_tool_skills
        and asserts the rendered string contains "tool-bash", "When to Use", and the
        expected header prefix because tool-skill injection must make the guidance
        available in the system prompt after a tool is used.
        """
        stub = self._stub_loop()

        # Before any tool runs, nothing is rendered.
        assert stub._render_active_tool_skills() == ""

        await stub._collect_tool_skill("bash")
        rendered = stub._render_active_tool_skills()

        assert "tool-bash" in rendered
        assert "When to Use" in rendered
        assert rendered.startswith("## Tool Skills (auto-activated)")

    @pytest.mark.asyncio
    async def test_verify_tool_skill_collection_is_idempotent(self):
        """Validate that re-collecting the same tool does not duplicate the entry.

        The test exercises _collect_tool_skill("bash") twice and asserts the
        _active_tool_skills dict is identical after the second call because
        idempotency prevents prompt bloat from repeated tool usage.
        """
        stub = self._stub_loop()

        await stub._collect_tool_skill("bash")
        first = dict(stub._active_tool_skills)

        await stub._collect_tool_skill("bash")
        assert stub._active_tool_skills == first

    @pytest.mark.asyncio
    async def test_verify_unknown_tool_is_a_noop(self):
        """Validate that collecting an unknown tool silently does nothing.

        The test exercises _collect_tool_skill("does_not_exist_xyz") and
        asserts _active_tool_skills is empty and render returns "" because
        unknown tools must not produce phantom guidance entries.
        """
        stub = self._stub_loop()

        await stub._collect_tool_skill("does_not_exist_xyz")
        assert stub._active_tool_skills == {}
        assert stub._render_active_tool_skills() == ""

    @pytest.mark.asyncio
    async def test_verify_doc_skill_auto_activates_by_extension(self):
        """Validate that referencing a .pdf file activates the pdf document skill.

        The test exercises _collect_doc_skills with {"path": "/tmp/report.pdf"}
        and asserts "pdf" is in _active_doc_skills and the render contains the
        expected header and skill heading because document skills must
        auto-activate based on file extension matching.
        """
        stub = self._stub_loop()

        await stub._collect_doc_skills({"path": "/tmp/report.pdf"})
        assert "pdf" in stub._active_doc_skills

        rendered = stub._render_active_doc_skills()
        assert "## Document Skills (auto-activated)" in rendered
        assert "### pdf" in rendered

    @pytest.mark.asyncio
    async def test_verify_process_skills_do_not_auto_activate_on_code_files(self):
        """Validate that referencing a .py file does NOT activate process skills.

        The test exercises _collect_doc_skills with {"path": "/tmp/main.py"}
        and asserts _active_doc_skills is empty because process skills
        (code-review, refactor, etc.) have auto_activate=False and must
        only fire when explicitly invoked, not from a bare file reference.
        """
        stub = self._stub_loop()

        await stub._collect_doc_skills({"path": "/tmp/main.py"})
        assert stub._active_doc_skills == {}, "process skill leaked on a .py reference"
