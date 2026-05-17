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

from typing import Any

from yim.skills.types import BundledSkillDefinition, SkillContext, SkillSource


async def _debug_prompt(args: str | None, ctx: dict[str, Any]) -> str:
    target = args or "the current project"
    return f"""You are debugging: {target}

Follow this systematic debugging workflow:

## Phase 1: Information Gathering
1. Read and examine any log files present in the workspace (check for files like *.log, output.log, error.log, stderr, stdout captures, build logs, test logs, crash logs, dumps)
2. Collect error messages from the most recent run or build
3. Identify the exact error messages, stack traces, or failure points
4. Note the exact line numbers, file paths, and function names mentioned in errors

## Phase 2: Root Cause Analysis
1. Read the relevant source files at the exact line numbers indicated in the error
2. Trace the execution flow backwards from the failure point
3. Check variable states, input validation, and boundary conditions at the failure point
4. Look for common patterns: null/None dereference, index out of bounds, type mismatches, race conditions, resource exhaustion, import errors, configuration issues
5. If the error is in a dependency or library, check the library version and compatibility

## Phase 3: Reproduction and Isolation
1. Identify the minimal reproduction case
2. Determine if the issue is deterministic or intermittent
3. Check if the issue depends on specific: input data, environment variables, OS, Python version, library versions, concurrency, timing
4. Isolate the failing component from the rest of the system if possible

## Phase 4: Fix and Verify
1. Apply the minimal fix that addresses the root cause (not just the symptom)
2. Verify the fix does not introduce new issues
3. If tests exist, ensure they pass after the fix
4. Document the root cause and fix for future reference

## Output Format
Present your findings clearly:
- **Error Summary**: What failed, where, and with what message
- **Root Cause**: The underlying problem identified
- **Fix Applied**: What change was made and why
- **Verification**: Evidence the fix works

If you cannot determine the root cause, explain what additional information you need and what you have ruled out so far.
"""
