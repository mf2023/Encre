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



"""Background service wrapper for the Encre server.

Provides daemon infrastructure: PID file tracking, file logging,
stale PID detection, and signal handling for graceful shutdown.
"""

import argparse
import logging
import os
import signal
from pathlib import Path

ENCRE_DATA_DIR = Path(os.environ.get("ENCRE_DATA_DIR", Path.home() / ".dunimd" / "encre"))
PID_FILE = ENCRE_DATA_DIR / "yimd.pid"
LOG_FILE = ENCRE_DATA_DIR / "yimd.log"

logger = logging.getLogger("encre.service")


def _setup_logging(log_level: str) -> None:
    ENCRE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(str(LOG_FILE), mode="a", encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper()))
    root.addHandler(file_handler)
    logger.info("File logging initialized (level=%s, path=%s)", log_level, LOG_FILE)


def _write_pid() -> None:
    ENCRE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    logger.info("PID file written: %d -> %s", os.getpid(), PID_FILE)


def _remove_pid() -> None:
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
            logger.info("PID file removed: %s", PID_FILE)
    except Exception:
        pass


def _check_stale_pid() -> None:
    if not PID_FILE.exists():
        return
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
    except (ValueError, ProcessLookupError, OSError):
        logger.warning("Stale PID file found, cleaning up (PID was dead)")
        _remove_pid()
        logger.warning("PID file exists but process is owned by another user")


def _shutdown(signum: int, _frame) -> None:
    logger.info("Received signal %d, shutting down...", signum)
    _remove_pid()
    # Signal the main event loop to stop by raising KeyboardInterrupt
    import threading
    threading.main_thread().interrupt_main()


def run_service(
    host: str = "localhost",
    port: int = 7110,
    config_file: str | None = None,
    max_concurrent: int = 20,
    log_level: str = "INFO",
) -> None:
    _setup_logging(log_level)
    _check_stale_pid()
    _write_pid()

    logger.info("Background service starting (PID %d, host=%s, port=%d)", os.getpid(), host, port)

    signal.signal(signal.SIGTERM, _shutdown)

    from encre.server.app import run_server

    try:
        run_server(
            host=host,
            port=port,
            config_file=config_file,
            max_concurrent=max_concurrent,
        )
    finally:
        _remove_pid()


def main() -> None:
    parser = argparse.ArgumentParser(description="Encre Background Service")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=7110)
    parser.add_argument("--config", help="Path to config file")
    parser.add_argument("--max-concurrent", type=int, default=20)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    run_service(
        host=args.host,
        port=args.port,
        config_file=args.config,
        max_concurrent=args.max_concurrent,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
