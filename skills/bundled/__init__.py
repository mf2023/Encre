#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Yim.
# The Yim project belongs to the Dunimd Team.
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

from yim.skills.types import BundledSkillDefinition, SkillContext, SkillSource


def create_bundled_skills(registry):
    from yim.skills.bundled.debug import _debug_prompt
    from yim.skills.bundled.loop import _loop_prompt
    from yim.skills.bundled.batch import _batch_prompt
    from yim.skills.bundled.verify import _verify_prompt
    from yim.skills.bundled.stuck import _stuck_prompt

    debug_skill = BundledSkillDefinition(
        name="debug",
        description="Systematic debugging workflow: gather logs, analyze root cause, isolate, fix, and verify errors",
        get_prompt_for_command=_debug_prompt,
        aliases=["dbg", "diag", "troubleshoot"],
        when_to_use=".log .txt .err .out .traceback",
        argument_hint="[target: file, module, or component to debug]",
        disable_model_invocation=False,
        user_invocable=True,
        context=SkillContext.INLINE,
        source=SkillSource.BUNDLED,
    )

    loop_skill = BundledSkillDefinition(
        name="loop",
        description="Execute a command repeatedly on a schedule using [interval] <prompt> syntax",
        get_prompt_for_command=_loop_prompt,
        aliases=["repeat", "schedule", "watch"],
        when_to_use="",
        argument_hint="[seconds] <task description>",
        disable_model_invocation=False,
        user_invocable=True,
        context=SkillContext.INLINE,
        source=SkillSource.BUNDLED,
    )

    batch_skill = BundledSkillDefinition(
        name="batch",
        description="3-phase batch execution: research/plan, spawn parallel agents, track and synthesize results",
        get_prompt_for_command=_batch_prompt,
        aliases=["parallel", "multi-agent", "farm", "orchestrate"],
        when_to_use="",
        argument_hint="[high-level task description for batch processing]",
        disable_model_invocation=False,
        user_invocable=True,
        context=SkillContext.FORK,
        source=SkillSource.BUNDLED,
    )

    verify_skill = BundledSkillDefinition(
        name="verify",
        description="Code verification pipeline: static analysis, type checking, linting, test execution, build check, smoke test",
        get_prompt_for_command=_verify_prompt,
        aliases=["check", "validate", "test", "qa"],
        when_to_use=".py .rs .js .ts .go .java .cpp .c .h",
        argument_hint="[files or directories to verify, or 'all' for entire project]",
        disable_model_invocation=False,
        user_invocable=True,
        context=SkillContext.INLINE,
        source=SkillSource.BUNDLED,
    )

    stuck_skill = BundledSkillDefinition(
        name="stuck",
        description="Self-diagnosis for stuck/looping agents: detect patterns, identify root cause, and apply recovery strategies",
        get_prompt_for_command=_stuck_prompt,
        aliases=["unstuck", "recover", "diagnose-loop", "self-fix"],
        when_to_use="",
        argument_hint="[description of what the agent is stuck on]",
        disable_model_invocation=False,
        user_invocable=True,
        context=SkillContext.INLINE,
        source=SkillSource.BUNDLED,
    )

    registry.register(debug_skill)
    registry.register(loop_skill)
    registry.register(batch_skill)
    registry.register(verify_skill)
    registry.register(stuck_skill)
