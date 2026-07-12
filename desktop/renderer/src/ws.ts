/**
 * Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
 *
 * This file is part of Encre.
 * The Encre project belongs to the Dunimd Team.
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

/**
 * WebSocket transport layer.
 *
 * Manages the renderer ↔ backend WebSocket connection (default port 7110):
 * connection lifecycle, auto-reconnect, a keep-alive ping, transparent
 * AES-GCM encryption of outbound messages, and decryption of inbound events.
 * Outbound messages are queued until the socket is open.
 */

import { ClientMessage, ServerEvent } from "./types.js";
import { initCrypto, encrypt, decrypt, isReady } from "./crypto.js";
import { setConnected, getState } from "./state.js";

type EventHandler = (event: ServerEvent) => void;

const WS_PORT = 7110;

let ws: WebSocket | null = null;
let handler: EventHandler | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let pingTimer: ReturnType<typeof setInterval> | null = null;
let _cryptoInitDone = false;
let pendingQueue: ClientMessage[] = [];

async function drainQueue(): Promise<void> {
  const q = pendingQueue;
  pendingQueue = [];
  for (const msg of q) {
    await send(msg);
  }
}

/**
 * Opens the WebSocket connection and wires up event/lifecycle handlers.
 *
 * @param onEvent - Handler invoked for every (decrypted) server event.
 */
export async function connect(onEvent: EventHandler): Promise<void> {
  handler = onEvent;

  // Initialise crypto layer before the first connection
  if (!_cryptoInitDone) {
    await initCrypto();
    _cryptoInitDone = true;
  }

  const url = `ws://localhost:${WS_PORT}/ws`;

  try {
    ws = new WebSocket(url);

    ws.addEventListener("open", () => {
      handler?.({ type: "pong" });
      setConnected(true);
      startPing();
      drainQueue();
    });

    ws.addEventListener("message", async (evt: MessageEvent<string>) => {
      try {
        let raw = evt.data;
        let event: ServerEvent;

        if (isReady() && raw && typeof raw === "string" && !raw.startsWith("{")) {
          // Encrypted ciphertext — decrypt then parse
          try {
            const decrypted = await decrypt(raw);
            event = JSON.parse(decrypted) as ServerEvent;
          } catch {
            // Fallback: try plaintext parse
            event = JSON.parse(raw) as ServerEvent;
          }
        } else {
          // Plaintext (legacy or crypto unavailable)
          event = JSON.parse(raw) as ServerEvent;
        }

        handler?.(event);
      } catch {
        /* ignore malformed */
      }
    });

    ws.addEventListener("close", () => {
      stopPing();
      setConnected(false);
      scheduleReconnect();
    });

    ws.addEventListener("error", () => {
      ws?.close();
    });

    // Wait for the WebSocket to actually open before resolving
    await new Promise<void>((resolve) => {
      const onOpen = () => {
        cleanup();
        resolve();
      };
      const onError = () => {
        cleanup();
        // Reconnect will be scheduled by the close handler
        ws?.close();
        resolve();
      };
      const cleanup = () => {
        ws?.removeEventListener("open", onOpen);
        ws?.removeEventListener("error", onError);
      };
      ws?.addEventListener("open", onOpen, { once: true });
      ws?.addEventListener("error", onError, { once: true });
    });
  } catch {
    scheduleReconnect();
  }
}

/**
 * Sends a client message, encrypting it when the crypto layer is ready.
 *
 * @param msg - The client message to transmit. Queued if the socket is not open.
 */
export async function send(msg: ClientMessage): Promise<void> {
  if (ws?.readyState !== WebSocket.OPEN) {
    pendingQueue.push(msg);
    return;
  }
  try {
    const payload = JSON.stringify(msg);
    if (isReady()) {
      const encrypted = await encrypt(payload);
      ws.send(encrypted);
    } else {
      ws.send(payload);
    }
  } catch (err) {
    console.warn("[ws] send failed:", err);
  }
}

/** Sends a `retry` request for a given branch/message index. */
export function sendRetry(branch_id: string, user_message_index: number, mode?: "normal" | "detailed" | "concise"): void {
  send({ type: "retry", branch_id, user_message_index, mode, session_id: getState().sessionId });
}

/** Sends a `switch_branch` request to change the active branch. */
export function sendSwitchBranch(branch_id: string): void {
  send({ type: "switch_branch", branch_id, session_id: getState().sessionId });
}

/** Sends a `rollback` request to revert to an earlier message in a branch. */
export function sendRollback(branch_id: string, message_id: string): void {
  send({ type: "rollback", branch_id, message_id });
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

/** Closes the connection, stops ping and cancels any pending reconnect. */
export function disconnect(): void {
  stopPing();
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  ws?.close();
  ws = null;
}
