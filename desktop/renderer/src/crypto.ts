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
 * Encre cryptographic layer (TypeScript / Web Crypto API).
 *
 * Uses the same AES‑256‑GCM algorithm and keyfile format as the Python
 * `encre/crypto.py` module.  The master key is read (and unwrapped) once
 * at startup via the Electron preload bridge.
 *
 * All transport encryption is done through the raw-bytes path:
 *
 *   encryptRaw(plainBytes) → nonce(12) || ciphertext || tag(16)
 *   decryptRaw(packed)     → plainBytes
 *
 * Ciphertexts are then base64-encoded before being sent over WebSocket.
 */

const KEY_LENGTH = 32;       // AES-256
const NONCE_LENGTH = 12;     // GCM standard
const TAG_LENGTH = 16;       // GCM 128-bit auth tag

const HKDF_SALT = new TextEncoder().encode("encre-crypto-hkdf-v1");

let _masterKey: CryptoKey | null = null;
let _ready = false;

// ── Machine identity for key wrapping ────────────────────────────

async function getMachineId(): Promise<Uint8Array> {
  const raw = await window.electronAPI?.readMachineId();
  if (raw && raw !== "uninitialized") {
    return new TextEncoder().encode(raw);
  }
  throw new Error("Unable to determine machine identity for key wrapping");
}

async function deriveWrappingKeyRaw(): Promise<Uint8Array> {
  const ikm = await getMachineId();
  // SHA-256(salt || ikm) — matches Python _hkdf_extract
  const saltHash = await crypto.subtle.digest("SHA-256", HKDF_SALT.buffer as ArrayBuffer);
  const combined = new Uint8Array(saltHash.byteLength + ikm.byteLength);
  combined.set(new Uint8Array(saltHash), 0);
  combined.set(ikm, saltHash.byteLength);
  const hash = await crypto.subtle.digest("SHA-256", combined.buffer as ArrayBuffer);
  return new Uint8Array(hash);
}

async function importWrappingKey(rawKey: Uint8Array): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    rawKey.buffer as ArrayBuffer,
    { name: "AES-GCM" } as AesGcmParams,
    false,
    ["encrypt", "decrypt"] as KeyUsage[]
  );
}

// ── Master key management ────────────────────────────────────────

async function unwrapMasterKey(keyfileBytes: Uint8Array): Promise<CryptoKey> {
  const nonce = keyfileBytes.slice(0, NONCE_LENGTH);
  const ct = keyfileBytes.slice(NONCE_LENGTH);  // ciphertext + tag

  const wrappingKeyRaw = await deriveWrappingKeyRaw();
  const wrappingKey = await importWrappingKey(wrappingKeyRaw);

  const masterKeyRaw = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: nonce.buffer as ArrayBuffer, additionalData: new TextEncoder().encode("encre-keywrap-v1").buffer as ArrayBuffer } as AesGcmParams,
    wrappingKey,
    ct.buffer as ArrayBuffer
  );

  return crypto.subtle.importKey(
    "raw",
    masterKeyRaw,
    { name: "AES-GCM" } as AesGcmParams,
    false,
    ["encrypt", "decrypt"] as KeyUsage[]
  );
}

/**
 * Initialise the crypto layer — reads and unwraps the keyfile.
 * Must be called before encrypt/decrypt.
 */
export async function initCrypto(): Promise<void> {
  if (_ready) return;

  try {
    const keyfileBytes = await window.electronAPI?.readKeyfile();
    if (!keyfileBytes || keyfileBytes.byteLength === 0) {
      // If the keyfile doesn't exist, the TS layer can't create it
      // (that requires Python's cryptography library).
      // In practice the server creates it before the desktop frontend starts.
      console.warn("[encre/crypto] Keyfile not available — transport encryption disabled");
      _ready = true;
      return;
    }

    _masterKey = await unwrapMasterKey(new Uint8Array(keyfileBytes));
    _ready = true;
  } catch (err) {
    console.warn("[encre/crypto] Failed to initialise crypto:", err);
    _ready = true;  // don't block forever — fall back to plaintext
  }
}

// ── Encryption / decryption ──────────────────────────────────────

function getRandomNonce(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(NONCE_LENGTH));
}

/**
 * Encrypt raw bytes → nonce(12) || ciphertext || tag(16).
 */
export async function encryptRaw(plain: Uint8Array): Promise<Uint8Array> {
  if (!_masterKey) {
    return plain;  // fallback: no encryption
  }
  const nonce = getRandomNonce();
  const ct = new Uint8Array(await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: nonce.buffer as ArrayBuffer } as AesGcmParams,
    _masterKey,
    plain.buffer as ArrayBuffer
  ));
  const result = new Uint8Array(NONCE_LENGTH + ct.byteLength);
  result.set(nonce, 0);
  result.set(ct, NONCE_LENGTH);
  return result;
}

/**
 * Decrypt nonce(12) || ciphertext || tag(16) → raw bytes.
 */
export async function decryptRaw(packed: Uint8Array): Promise<Uint8Array> {
  if (!_masterKey) {
    return packed;  // fallback: no encryption
  }
  const nonce = packed.slice(0, NONCE_LENGTH);
  const ct = packed.slice(NONCE_LENGTH);
  const plain = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: nonce.buffer as ArrayBuffer } as AesGcmParams,
    _masterKey!,
    ct.buffer as ArrayBuffer
  );
  return new Uint8Array(plain);
}

/**
 * Encrypt a UTF‑8 string → base64(nonce || ciphertext || tag).
 */
export async function encrypt(plaintext: string): Promise<string> {
  if (!_masterKey) return plaintext;
  const plain = new TextEncoder().encode(plaintext);
  const packed = await encryptRaw(plain);
  return btoa(String.fromCharCode(...packed));
}

/**
 * Decrypt base64(nonce || ciphertext || tag) → UTF‑8 string.
 */
export async function decrypt(ciphertext: string): Promise<string> {
  if (!_ready) await initCrypto();
  if (!_masterKey) return ciphertext;
  try {
    const packed = Uint8Array.from(atob(ciphertext), (c) => c.charCodeAt(0));
    const plain = await decryptRaw(packed);
    return new TextDecoder().decode(plain);
  } catch {
    return ciphertext;  // fallback: cannot decrypt, return as-is
  }
}

/** Check if crypto layer is active. */
export function isReady(): boolean {
  return _ready && _masterKey !== null;
}
