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

import asyncio
import json
import logging
from pathlib import Path

from yim.config import YmiConfig
from yim.crypto import ensure_keyfile
from yim.server.admin import handle_admin
from yim.server.session_manager import SessionManager
from yim.server.ws import YmiWSHandler

logger = logging.getLogger("yim.server")


class YmiServer:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 7110,
        config: YmiConfig | None = None,
        max_concurrent: int = 20,
        idle_timeout: float = 3600.0,
    ) -> None:
        self.host = host
        self.port = port
        self.config = config or YmiConfig()
        self._manager = SessionManager(
            max_concurrent=max_concurrent,
            idle_timeout=idle_timeout,
        )
        self._ws_handler = YmiWSHandler(self._manager, config=self.config)
        self._cleanup_task: asyncio.Task[None] | None = None

    async def _handle_connection(self, ws) -> None:
        try:
            await self._ws_handler.handle(ws)
        except Exception:
            logger.exception("Unhandled error in WebSocket handler")

    async def _handle_http(self, path: str, request_headers) -> tuple[int, str, dict[str, str]] | None:
        result = handle_admin(path, self._manager)
        if result is None:
            return None
        status, body, header_list = result
        headers_dict = {k: v for k, v in header_list}
        return status, body, headers_dict

    async def start(self) -> None:
        try:
            import websockets
        except ImportError:
            raise ImportError(
                "websockets library is required to run the server. "
                "Install it with: pip install websockets"
            )

        logger.info(f"Starting yim server on {self.host}:{self.port}")

        async def process_request(connection, request):
            path = request.path
            if path and path.startswith("/ws"):
                return None  # Let websockets handle it
            # Handle HTTP admin endpoints
            result = handle_admin(path, self._manager)
            if result is None:
                return connection.respond(404, "Not Found")
            status, body, _header_list = result
            headers = {}
            for k, v in _header_list:
                headers[k] = v
            return connection.respond(status, body, headers)

        self._ws_server = await websockets.serve(
            self._handle_connection,
            self.host,
            self.port,
            process_request=process_request,
            ping_interval=30,
            ping_timeout=10,
            max_size=10 * 1024 * 1024,  # 10MB max message
        )
        # Resolve actual port when port=0 (OS-assigned)
        actual_port = self.port
        if actual_port == 0 and self._ws_server.sockets:
            actual_port = self._ws_server.sockets[0].getsockname()[1]

        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(f"Server ready: ws://{self.host}:{actual_port}/ws")
        logger.info(f"Admin API: http://{self.host}:{actual_port}/health")
        # Also emit to stdout for parent processes that parse stdout
        print(f"Server ready: ws://{self.host}:{actual_port}/ws", flush=True)

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(300)
            removed = await self._manager.cleanup_idle()
            if removed:
                logger.debug(f"Cleaned up {removed} idle sessions")

    async def serve_forever(self) -> None:
        await self.start()
        await asyncio.Future()  # Run forever

    async def stop(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        if hasattr(self, '_ws_server') and self._ws_server:
            self._ws_server.close()
            await self._ws_server.wait_closed()
        await self._manager.shutdown()
        logger.info("Server stopped")


def run_server(
    host: str = "localhost",
    port: int = 7110,
    config: YmiConfig | None = None,
    max_concurrent: int = 20,
    config_file: str | None = None,
) -> None:
    """Convenience function to run the server synchronously."""
    # Ensure the crypto keyfile exists before anything else
    ensure_keyfile()

    if config_file:
        config = YmiConfig.from_file(config_file)
    elif config is None:
        config = YmiConfig.from_file()  # Try auto-discovery

    server = YmiServer(
        host=host,
        port=port,
        config=config,
        max_concurrent=max_concurrent,
    )
    try:
        asyncio.run(server.serve_forever())
    except KeyboardInterrupt:
        logger.info("Server interrupted, shutting down...")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Yim Agent Server")
    parser.add_argument("--host", default="localhost", help="Host to bind to")
    parser.add_argument("--port", type=int, default=7110, help="Port to bind to")
    parser.add_argument("--config", help="Path to config file (yaml/toml)")
    parser.add_argument("--max-concurrent", type=int, default=20, help="Max concurrent agent sessions")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = None
    if args.config:
        config = YmiConfig.from_file(args.config)

    run_server(
        host=args.host,
        port=args.port,
        config=config,
        max_concurrent=args.max_concurrent,
    )
