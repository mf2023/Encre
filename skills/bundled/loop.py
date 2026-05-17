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

import re
from typing import Any

from yim.skills.types import BundledSkillDefinition, SkillContext, SkillSource

_LOOP_PATTERN = re.compile(r"^\s*\[(\d+(?:\.\d+)?)\]\s*(.+)", re.DOTALL)


async def _loop_prompt(args: str | None, ctx: dict[str, Any]) -> str:
    if args is None:
        args = ""
    match = _LOOP_PATTERN.match(args)
    if match is None:
        return f"""You are in a loop execution mode. The command syntax is: [interval] <prompt>

The interval specifies how frequently (in seconds) to execute the prompt. Minimum interval is 1 second.

However, the input provided did not match the expected format. Received:
  "{args}"

Please ask the user to specify the command in the format: [interval] <prompt>
Example: [10] Run the build and report any errors

Also provide the following guidance to the user:
- Use shorter intervals (1-5s) for rapid feedback loops like file watching
- Use medium intervals (10-30s) for build/test cycles
- Use longer intervals (60-300s) for monitoring tasks
- Add [stop] or press Ctrl+C to terminate the loop
"""

    interval_str = match.group(1).strip()
    prompt_text = match.group(2).strip()

    try:
        interval_seconds = float(interval_str)
    except ValueError:
        interval_seconds = 5.0

    if interval_seconds < 1.0:
        interval_seconds = 1.0

    return f"""You are executing a loop with the following configuration:

## Loop Schedule
- **Interval**: {interval_seconds} seconds
- **Task**: {prompt_text}

## Execution Protocol
1. Execute the following task exactly once per iteration:
   ```
   {prompt_text}
   ```
2. After completing the task, wait {interval_seconds} seconds before the next iteration
3. Before each new iteration, check if the user has requested a stop (via stop command, interrupt, or explicit instruction)
4. Track iteration count and report progress periodically (every 10 iterations or every major state change)

## Iteration Rules
- Each iteration is independent unless the task specifies state accumulation
- If an iteration fails, log the failure and continue to the next iteration (do not halt the loop)
- If 3 consecutive iterations fail with the same error, stop the loop and report the persistent failure
- The loop runs indefinitely until explicitly stopped by the user

## Output Format
For each iteration, report:
- Iteration number
- Result summary (success/failure with brief detail)
- Any state changes or notable observations

On the first iteration, include a header: "Loop started: {prompt_text} [every {interval_seconds}s]"

If you detect that the underlying task is a monitoring task (checking build status, watching files, etc.), adapt your output to highlight deltas/changes rather than repeating unchanged state.
"""
