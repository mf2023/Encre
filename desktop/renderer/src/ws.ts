/**
 * Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
 *
 * This file is part of Yim.
 * The Yim project belongs to the Dunimd Team.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * You may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 * 
 * DISCLAIMER: Users must comply with applicable AI regulations.
 * Non-compliance may result in service termination or legal liability.
 */

import { ClientMessage, ServerEvent } from "./types.js";

type EventHandler = (event: ServerEvent) => void;

const WS_PORT = 7110;

let ws: WebSocket | null = null;
let handler: EventHandler | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let pingTimer: ReturnType<typeof setInterval> | null = null;

export async function connect(onEvent: EventHandler): Promise<void> {
  handler = onEvent;

  const url = `ws://localhost:${WS_PORT}/ws`;

  try {
    ws = new WebSocket(url);

    ws.addEventListener("open", () => {
      handler?.({ type: "pong" });
      startPing();
    });

    ws.addEventListener("message", (evt: MessageEvent<string>) => {
      try {
        const event = JSON.parse(evt.data) as ServerEvent;
        handler?.(event);
      } catch {
        /* ignore malformed */
      }
    });

    ws.addEventListener("close", () => {
      stopPing();
      scheduleReconnect();
    });

    ws.addEventListener("error", () => {
      ws?.close();
    });
  } catch {
    scheduleReconnect();
  }
}

export function send(msg: ClientMessage): void {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg));
  }
}

function startPing(): void {
  stopPing();
  pingTimer = setInterval(() => {
    send({ type: "ping" });
  }, 25000);
}

function stopPing(): void {
  if (pingTimer) {
    clearInterval(pingTimer);
    pingTimer = null;
  }
}

function scheduleReconnect(): void {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect(handler!);
  }, 2000);
}

export function disconnect(): void {
  stopPing();
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  ws?.close();
  ws = null;
}
