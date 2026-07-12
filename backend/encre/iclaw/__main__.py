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

"""
Entry point for ``python -m encre.iclaw``.

Spawned by the desktop application as a headless background daemon.
Prints ``ICLAW_READY`` to stdout when the WS server is up so the desktop
app can parse the URL and connect.

Args:
    --host                     Bind address (default: 127.0.0.1)
    --port                     WebSocket port (default: 18791)
    --max-concurrent           Max concurrent sessions (default: 20)
    --scheduler-poll-interval  Scheduler polling interval in seconds (default: 30)
    --consolidation-interval   Memory consolidation seconds (default: 3600, 0=disabled)
    --compact                  Enable context compaction (default: true)
    --no-compact               Disable context compaction
    --evolution                Enable evolution learning (default: true)
    --no-evolution             Disable evolution learning
    --reflex                   Enable reflex loop (default: true)
    --no-reflex                Disable reflex loop
    --metacognition            Enable metacognition (default: true)
    --no-metacognition         Disable metacognition
    --feedback                 Enable feedback learning (default: true)
    --no-feedback              Disable feedback learning
    --swarm                    Enable swarm / multi-agent (default: true)
    --no-swarm                 Disable swarm / multi-agent
    --hooks                    Enable hook system (default: true)
    --no-hooks                 Disable hook system
    --log-level                Logging level (default: INFO)
    --stop                     Stop a running daemon via PID file
    --status                   Check if daemon is running (prints "running"/"stopped")
"""

import argparse
import asyncio
import contextlib
import logging

from encre.agent import EncreAgent
from encre.config import EncreConfig
from encre.iclaw import _data_dir, _log_path, is_running, run_iclaw, stop_daemon


def main() -> None:
    """Parse CLI arguments and run (or signal) the iClaw daemon."""
    # Configure the argument parser with all daemon tunables.
    parser = argparse.ArgumentParser(
        description="iClaw -- Encre background daemon",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18791)
    parser.add_argument("--max-concurrent", type=int, default=20)
    parser.add_argument("--scheduler-poll-interval", type=float, default=30.0,
                        help="Scheduler polling interval in seconds")
    parser.add_argument("--consolidation-interval", type=int, default=3600)

    parser.add_argument("--compact", action="store_true", default=True,
                        dest="compact", help="Enable context compaction")
    parser.add_argument("--no-compact", action="store_false",
                        dest="compact", help="Disable context compaction")
    parser.add_argument("--evolution", action="store_true", default=True,
                        dest="evolution", help="Enable evolution learning")
    parser.add_argument("--no-evolution", action="store_false",
                        dest="evolution", help="Disable evolution learning")
    parser.add_argument("--reflex", action="store_true", default=True,
                        dest="reflex", help="Enable reflex loop")
    parser.add_argument("--no-reflex", action="store_false",
                        dest="reflex", help="Disable reflex loop")
    parser.add_argument("--metacognition", action="store_true", default=True,
                        dest="metacognition", help="Enable metacognition")
    parser.add_argument("--no-metacognition", action="store_false",
                        dest="metacognition", help="Disable metacognition")
    parser.add_argument("--feedback", action="store_true", default=True,
                        dest="feedback", help="Enable feedback learning")
    parser.add_argument("--no-feedback", action="store_false",
                        dest="feedback", help="Disable feedback learning")
    parser.add_argument("--swarm", action="store_true", default=True,
                        dest="swarm", help="Enable swarm / multi-agent")
    parser.add_argument("--no-swarm", action="store_false",
                        dest="swarm", help="Disable swarm / multi-agent")
    parser.add_argument("--hooks", action="store_true", default=True,
                        dest="hooks", help="Enable hook system")
    parser.add_argument("--no-hooks", action="store_false",
                        dest="hooks", help="Disable hook system")

    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--stop", action="store_true",
                        help="Stop a running daemon")
    parser.add_argument("--status", action="store_true",
                        help="Check if daemon is running")

    args = parser.parse_args()

    # --stop / --status bypass normal startup and act on the running daemon.
    if args.stop:
        if is_running():
            stop_daemon()
            print("iClaw daemon stopped", flush=True)
        else:
            print("iClaw daemon is not running", flush=True)
        return

    if args.status:
        if is_running():
            print("running", flush=True)
        else:
            print("stopped", flush=True)
        return

    _data_dir().mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        filename=str(_log_path()),
    )

    config = EncreConfig()
    # Build the agent and launch the daemon lifecycle under asyncio.
    agent = EncreAgent(config=config)

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run_iclaw(
            agent=agent,
            host=args.host,
            port=args.port,
            max_concurrent=args.max_concurrent,
            consolidation_interval=args.consolidation_interval,
            scheduler_poll_interval=args.scheduler_poll_interval,
            enable_compact=args.compact,
            enable_evolution=args.evolution,
            enable_reflex=args.reflex,
            enable_metacognition=args.metacognition,
            enable_feedback=args.feedback,
            enable_swarm=args.swarm,
            enable_hooks=args.hooks,
        ))


if __name__ == "__main__":
    main()
