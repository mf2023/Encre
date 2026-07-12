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

"""Hashing and lightweight cryptography tool.

Computes checksums (md5/sha1/sha256) and HMACs, and performs base64 / symmetric
cipher (AES) encode-decode helpers without external key management.
"""


import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from encre.tools.base import build_tool


async def _hash_crypto_execute(**kwargs: Any) -> str:
    """Hash crypto execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    action = kwargs.get("action", "")
    algorithm = kwargs.get("algorithm", "sha256")
    data = kwargs.get("data", "")
    file_path = kwargs.get("file_path", "")
    key = kwargs.get("key", "")
    mode = kwargs.get("mode", "CBC")
    encoding = kwargs.get("encoding", "hex")

    loop = asyncio.get_event_loop()

    if action == "hash":
        if not data and not file_path:
            return "Missing required field: data or file_path"

        def _hash() -> str:
            """Hash."""
            try:
                h = hashlib.new(algorithm)
                if file_path:
                    if not os.path.exists(file_path):
                        return f"File not found: {file_path}"
                    with open(file_path, "rb") as f:
                        while True:
                            chunk = f.read(65536)
                            if not chunk:
                                break
                            h.update(chunk)
                    result = h.hexdigest() if encoding == "hex" else base64.b64encode(h.digest()).decode()
                    return json.dumps({
                        "algorithm": algorithm,
                        "hash": result,
                        "encoding": encoding,
                        "file": file_path,
                        "size": os.path.getsize(file_path),
                    }, ensure_ascii=False, indent=2)
                else:
                    h.update(data.encode("utf-8"))
                    result = h.hexdigest() if encoding == "hex" else base64.b64encode(h.digest()).decode()
                    return json.dumps({
                        "algorithm": algorithm,
                        "hash": result,
                        "encoding": encoding,
                    }, ensure_ascii=False, indent=2)
            except ValueError as e:
                return f"Unsupported algorithm: {algorithm}. {e}"
            except OSError as e:
                return f"File error: {e}"

        return await loop.run_in_executor(None, _hash)

    elif action == "hmac":
        if not data:
            return "Missing required field: data"
        if not key:
            return "Missing required field: key"

        def _hmac() -> str:
            """Hmac."""
            try:
                import hmac as hmac_mod
                h = hmac_mod.new(key.encode("utf-8"), data.encode("utf-8"), algorithm)
                result = h.hexdigest() if encoding == "hex" else base64.b64encode(h.digest()).decode()
                return json.dumps({
                    "algorithm": f"HMAC-{algorithm.upper()}",
                    "hash": result,
                    "encoding": encoding,
                }, ensure_ascii=False, indent=2)
            except ValueError as e:
                return f"HMAC error: {e}"

        return await loop.run_in_executor(None, _hmac)

    elif action == "checksum":
        if not file_path:
            return "Missing required field: file_path"

        def _checksum() -> str:
            """Checksum."""
            try:
                if not os.path.exists(file_path):
                    return f"File not found: {file_path}"
                results = {}
                algs = algorithm.split(",") if "," in algorithm else [algorithm]
                for alg in algs:
                    alg = alg.strip()
                    h = hashlib.new(alg)
                    with open(file_path, "rb") as f:
                        while True:
                            chunk = f.read(65536)
                            if not chunk:
                                break
                            h.update(chunk)
                    results[alg] = h.hexdigest()
                return json.dumps({
                    "file": file_path,
                    "size": os.path.getsize(file_path),
                    "checksums": results,
                }, ensure_ascii=False, indent=2)
            except ValueError as e:
                return f"Unsupported algorithm: {e}"
            except OSError as e:
                return f"File error: {e}"

        return await loop.run_in_executor(None, _checksum)

    elif action == "encrypt":
        if not data:
            return "Missing required field: data"
        if not key:
            return "Missing required field: key"

        def _encrypt() -> str:
            """Encrypt."""
            try:
                from cryptography.hazmat.backends import default_backend
                from cryptography.hazmat.primitives import padding
                from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

                key_bytes = hashlib.sha256(key.encode("utf-8")).digest()
                iv = os.urandom(16)
                data_bytes = data.encode("utf-8")

                padder = padding.PKCS7(128).padder()
                padded_data = padder.update(data_bytes) + padder.finalize()

                if mode.upper() == "CBC":
                    cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv), backend=default_backend())
                elif mode.upper() == "ECB":
                    cipher = Cipher(algorithms.AES(key_bytes), modes.ECB(), backend=default_backend())
                elif mode.upper() == "CTR":
                    nonce = os.urandom(8)
                    cipher = Cipher(algorithms.AES(key_bytes), modes.CTR(nonce), backend=default_backend())
                    iv = nonce
                    padded_data = data_bytes
                elif mode.upper() == "GCM":
                    cipher = Cipher(algorithms.AES(key_bytes), modes.GCM(iv), backend=default_backend())
                    padded_data = data_bytes
                else:
                    return f"Unsupported mode: {mode}. Supported: CBC, ECB, CTR, GCM"

                encryptor = cipher.encryptor()
                ct = encryptor.update(padded_data) + encryptor.finalize()

                tag = getattr(encryptor, "tag", b"")
                result = {
                    "ciphertext": base64.b64encode(ct).decode(),
                    "iv": base64.b64encode(iv).decode(),
                    "algorithm": f"AES-{mode}",
                    "encoding": "base64",
                }
                if tag:
                    result["tag"] = base64.b64encode(tag).decode()
                return json.dumps(result, ensure_ascii=False, indent=2)
            except ImportError:
                return "cryptography library required. Install: pip install cryptography"
            except Exception as e:
                return f"Encryption failed: {e}"

        return await loop.run_in_executor(None, _encrypt)

    elif action == "decrypt":
        if not data:
            return "Missing required field: data (base64 ciphertext)"
        if not key:
            return "Missing required field: key"

        def _decrypt() -> str:
            """Decrypt."""
            try:
                from cryptography.hazmat.backends import default_backend
                from cryptography.hazmat.primitives import padding
                from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

                key_bytes = hashlib.sha256(key.encode("utf-8")).digest()
                ct = base64.b64decode(data)
                iv_raw = kwargs.get("iv", "")
                if not iv_raw:
                    return "Missing required field: iv (base64)"
                iv = base64.b64decode(iv_raw)

                if mode.upper() == "CBC":
                    cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv), backend=default_backend())
                elif mode.upper() == "ECB":
                    cipher = Cipher(algorithms.AES(key_bytes), modes.ECB(), backend=default_backend())
                elif mode.upper() == "CTR":
                    cipher = Cipher(algorithms.AES(key_bytes), modes.CTR(iv), backend=default_backend())
                elif mode.upper() == "GCM":
                    tag_raw = kwargs.get("tag", "")
                    if not tag_raw:
                        return "Missing required field: tag for GCM mode"
                    tag = base64.b64decode(tag_raw)
                    cipher = Cipher(algorithms.AES(key_bytes), modes.GCM(iv, tag), backend=default_backend())
                else:
                    return f"Unsupported mode: {mode}"

                decryptor = cipher.decryptor()
                padded_data = decryptor.update(ct) + decryptor.finalize()

                if mode.upper() in ("CBC", "ECB"):
                    unpadder = padding.PKCS7(128).unpadder()
                    plaintext = unpadder.update(padded_data) + unpadder.finalize()
                else:
                    plaintext = padded_data

                return json.dumps({
                    "plaintext": plaintext.decode("utf-8"),
                    "algorithm": f"AES-{mode}",
                }, ensure_ascii=False, indent=2)
            except ImportError:
                return "cryptography library required. Install: pip install cryptography"
            except Exception as e:
                return f"Decryption failed: {e}"

        return await loop.run_in_executor(None, _decrypt)

    elif action == "base64_encode":
        if not data:
            return "Missing required field: data"
        if file_path:
            try:
                raw = Path(file_path).read_bytes()
                return base64.b64encode(raw).decode()
            except OSError as e:
                return f"File error: {e}"
        return base64.b64encode(data.encode("utf-8")).decode()

    elif action == "base64_decode":
        if not data:
            return "Missing required field: data"
        if file_path:
            try:
                decoded = base64.b64decode(data)
                Path(file_path).write_bytes(decoded)
                return f"Decoded to {file_path} ({len(decoded)} bytes)"
            except OSError as e:
                return f"File error: {e}"
            except Exception as e:
                return f"Base64 decode failed: {e}"
        try:
            return base64.b64decode(data).decode("utf-8")
        except UnicodeDecodeError:
            return f"Binary data decoded ({len(base64.b64decode(data))} bytes). Use file_path to write to file."
        except Exception as e:
            return f"Base64 decode failed: {e}"

    return f"Unknown action: {action}. Supported: hash, hmac, checksum, encrypt, decrypt, base64_encode, base64_decode"


EncreHashCryptoTool = build_tool(
    name="hash_crypto",
    description="Hashing (MD5/SHA), HMAC, checksums, AES encrypt/decrypt (CBC/ECB/CTR/GCM), Base64 encode/decode.",
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["hash", "hmac", "checksum", "encrypt", "decrypt", "base64_encode", "base64_decode"],
                "description": "Action to perform",
            },
            "algorithm": {
                "type": "string",
                "description": "Hash algorithm: md5, sha1, sha256, sha512 (default sha256). Comma-separated for checksum.",
            },
            "data": {"type": "string", "description": "Text data to hash/encrypt/encode"},
            "file_path": {"type": "string", "description": "Path to file (for hash/checksum/base64)"},
            "key": {"type": "string", "description": "Secret key (for HMAC/AES)"},
            "mode": {
                "type": "string",
                "enum": ["CBC", "ECB", "CTR", "GCM"],
                "description": "AES cipher mode (default CBC)",
            },
            "encoding": {
                "type": "string",
                "enum": ["hex", "base64"],
                "description": "Output encoding (default hex)",
            },
            "iv": {"type": "string", "description": "Base64 IV (required for decrypt)"},
            "tag": {"type": "string", "description": "Base64 auth tag (for GCM decrypt)"},
        },
        "required": ["action"],
    },
    execute=_hash_crypto_execute,
    intents=["general", "coding", "system"],
    category="system",
    semantic_type="general",
    cost_level="low",
    retryability="auto",
    is_concurrency_safe=lambda _: True,
    is_readonly=lambda _: True,
)
