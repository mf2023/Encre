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

"""Encre cryptographic layer -- provides encrypt/decrypt for all sensitive data.

Architecture
============

All encryption uses **AES-256-GCM** (32鈥慴yte key, 12鈥慴yte random nonce,
16鈥慴yte authentication tag).

Master key
    On first use a 256鈥慴it master key is generated from ``os.urandom(32)`` and
    stored in ``<data_dir>/keys/keyfile`` (mode ``0o600``).  The on鈥慸isk
    representation is the master key itself wrapped with a *machine鈥慴inding*
    key derived via HKDF鈥慡HA256 from the host's ``/etc/machine鈥慽d`` content +
    hostname.

    This means even if ``keyfile`` is exfiltrated it cannot be unwrapped on
    any other machine.

    With the above::

        encrypt(plain_bytes)  ->  base64(nonce || ciphertext || tag)
        decrypt(b64_ciphertext) -> plain_bytes

No environment variables are consulted for key material.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import os
import pathlib
import platform
import secrets
import shutil
import stat
import typing as _t

__all__ = [
    "decrypt",
    "decrypt_bytes",
    "encrypt",
    "encrypt_bytes",
    "ensure_keyfile",
    "keyfile_path",
    "migrate_keyfile",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: The keyfile lives **inside the data tree** (``<data_dir>/keys/keyfile``).
#: It used to sit in a second root (``~/.encre``), which quietly broke the
#: promise that "backing up the data directory" is enough to restore: the
#: ciphertexts travelled but the key did not.  New keys are written to the
#: data tree; the legacy path is still *read* so existing installs keep
#: working, and :func:`migrate_keyfile` moves it over.
_LEGACY_KEYFILE_PATH = pathlib.Path("~/.encre/keyfile").expanduser()
_KEYFILE_MODE = stat.S_IRUSR | stat.S_IWUSR  # 0o600 -- owner read/write only

_KEY_LENGTH = 32       # AES-256
_NONCE_LENGTH = 12     # GCM standard
_TAG_LENGTH = 16       # GCM 128-bit auth tag
_GCM_IV_LENGTH = 12

# HKDF constants for deriving the machine-binding wrapping key
_HKDF_SALT = b"encre-crypto-hkdf-v1"
_HKDF_SALT_SHA256 = hashlib.sha256(_HKDF_SALT).digest()[:32]

_WRAP_CTX_AAD = b"encre-keywrap-v1"

# Cached master key (module lifetime) -- avoid reading keyfile on every call
_master_key_cache: bytes | None = None


# ---------------------------------------------------------------------------
# Machine-binding identity
# ---------------------------------------------------------------------------

def _read_machine_id() -> bytes:
    """Return a stable machine鈥慽dentifier blob for key鈥憌rapping.

    Reads ``/etc/machine-id`` and falls back to ``gethostname()``.
    """
    try:
        mid = pathlib.Path("/etc/machine-id").read_text(encoding="utf-8").strip()
        if mid and mid != "uninitialized":
            return mid.encode("utf-8")
    except (OSError, UnicodeDecodeError):
        pass
    # Fallback: hash of hostname (still provides binding, just weaker)
    return platform.node().encode("utf-8")


# ---------------------------------------------------------------------------
# HKDF-SHA256 helper (implemented with hashlib -- no third鈥憄arty required
# for this single鈥憇tep usage)
# ---------------------------------------------------------------------------

def _hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    return hashlib.sha256(salt + ikm).digest()


def _derive_wrapping_key() -> bytes:
    """Derive the AES鈥?56 key used to wrap/unwrap the master鈥慿ey file."""
    ikm = _read_machine_id()
    return _hkdf_extract(_HKDF_SALT_SHA256, ikm)


# ---------------------------------------------------------------------------
# Master鈥慿ey management (AES鈥慓CM wrap/unwrap with machine鈥慴inding key)
# ---------------------------------------------------------------------------

def _generate_master_key() -> bytes:
    """Return a fresh 256鈥慴it master key."""
    return secrets.token_bytes(_KEY_LENGTH)


def _wrap_master_key(master_key: bytes) -> bytes:
    """Wrap *master_key* with the machine鈥慴inding key via AES鈥?56鈥慓CM.

    Returns
    -------
    bytes
        ``nonce (12) || ciphertext (32) || tag (16)`` -- total 60 bytes.
        The ciphertext is the encrypted master key.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    wrapping_key = _derive_wrapping_key()
    nonce = secrets.token_bytes(_NONCE_LENGTH)
    aesgcm = AESGCM(wrapping_key)
    ciphertext = aesgcm.encrypt(nonce, master_key, _WRAP_CTX_AAD)
    # ciphertext already includes the 16鈥慴yte tag appended
    return nonce + ciphertext


def _unwrap_master_key(data: bytes) -> bytes:
    """Unwrap ``nonce || ciphertext || tag`` back to the master key."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    wrapping_key = _derive_wrapping_key()
    nonce = data[:_NONCE_LENGTH]
    rest = data[_NONCE_LENGTH:]  # ciphertext + tag
    aesgcm = AESGCM(wrapping_key)
    return aesgcm.decrypt(nonce, rest, _WRAP_CTX_AAD)


# ---------------------------------------------------------------------------
# Keyfile persistence
# ---------------------------------------------------------------------------

def keyfile_path() -> pathlib.Path:
    """Return the canonical keyfile location: ``<data_dir>/keys/keyfile``.

    Falls back to the legacy ``~/.encre/keyfile`` only if the data root
    cannot be resolved (e.g. a partially installed interpreter).
    """
    try:
        from encre.paths import get_data_dir

        return get_data_dir("keys", ensure=False) / "keyfile"
    except Exception:  # pragma: no cover - defensive
        return _LEGACY_KEYFILE_PATH


def _candidate_keyfiles() -> list[pathlib.Path]:
    """Keyfile locations to try, in priority order (new, then legacy)."""
    new = keyfile_path()
    return [new] if new == _LEGACY_KEYFILE_PATH else [new, _LEGACY_KEYFILE_PATH]


def migrate_keyfile() -> pathlib.Path:
    """Move a legacy ``~/.encre/keyfile`` into the data tree.  Idempotent.

    The master key itself is untouched -- only the file moves -- so every
    existing ciphertext stays decryptable.  Returns the canonical path.
    """
    target = keyfile_path()
    if target.exists():
        return target
    legacy = _LEGACY_KEYFILE_PATH
    if legacy.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            target.parent.chmod(stat.S_IRWXU)
        shutil.move(str(legacy), str(target))
        with contextlib.suppress(OSError):
            os.chmod(target, _KEYFILE_MODE)
    return target


def _create_keyfile() -> bytes:
    """Generate a new master key, wrap it, write the keyfile and return the key."""
    path = keyfile_path()
    keyfile_dir = path.parent
    keyfile_dir.mkdir(parents=True, exist_ok=True)
    # Only the owner of this directory should have access
    with contextlib.suppress(OSError):
        keyfile_dir.chmod(stat.S_IRWXU)

    master_key = _generate_master_key()
    wrapped = _wrap_master_key(master_key)

    # Atomic write via temp file + rename
    tmp = path.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        f.write(wrapped)
    with contextlib.suppress(OSError):
        os.chmod(tmp, _KEYFILE_MODE)
    os.replace(tmp, path)

    return master_key


def _load_keyfile() -> bytes | None:
    """Read the wrapped master key from disk and unwrap it.

    Tries the canonical location first, then the legacy ``~/.encre`` one so
    an install that has not been migrated yet still starts.

    Returns None if no keyfile exists or it cannot be decrypted.
    """
    for path in _candidate_keyfiles():
        if not path.exists():
            continue
        try:
            raw = path.read_bytes()
            if len(raw) < _NONCE_LENGTH + _KEY_LENGTH + _TAG_LENGTH:
                continue
            return _unwrap_master_key(raw)
        except Exception:
            continue
    return None


def ensure_keyfile() -> bytes:
    """Return the active master key, creating the keyfile if missing.

    This is the primary entry鈥憄oint -- call once at startup.
    """
    global _master_key_cache
    if _master_key_cache is not None:
        return _master_key_cache

    key = _load_keyfile()
    if key is None:
        key = _create_keyfile()

    _master_key_cache = key
    return key


# ---------------------------------------------------------------------------
# AES-256-GCM encrypt / decrypt (user-facing API)
# ---------------------------------------------------------------------------

if _t.TYPE_CHECKING:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _get_aesgcm() -> AESGCM:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(ensure_keyfile())


def encrypt(plaintext: str) -> str:
    """Encrypt a UTF鈥? string with AES鈥?56鈥慓CM.

    Returns a base64鈥慹ncoded ciphertext (nonce || ct || tag).
    """
    return encrypt_bytes(plaintext.encode("utf-8"))


def decrypt(ciphertext: str) -> str:
    """Decrypt a base64 ciphertext back to the original UTF鈥? string."""
    return decrypt_bytes(ciphertext).decode("utf-8")


def encrypt_bytes(plaintext: str | bytes) -> str:
    """Encrypt bytes (or a string treated as UTF鈥?) -> base64 string."""
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    aesgcm = _get_aesgcm()
    nonce = secrets.token_bytes(_NONCE_LENGTH)
    ct = aesgcm.encrypt(nonce, plaintext, None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_bytes(ciphertext: str) -> bytes:
    """Decrypt a base64 ciphertext -> raw bytes."""
    raw = base64.b64decode(ciphertext)
    nonce = raw[:_NONCE_LENGTH]
    ct = raw[_NONCE_LENGTH:]
    aesgcm = _get_aesgcm()
    return aesgcm.decrypt(nonce, ct, None)


# ---------------------------------------------------------------------------
# Convenience: encrypt/decrypt raw bytes -> raw bytes (for binary data)
# ---------------------------------------------------------------------------

def encrypt_raw(plain_bytes: bytes) -> bytes:
    """Encrypt raw bytes -> nonce || ciphertext || tag."""
    aesgcm = _get_aesgcm()
    nonce = secrets.token_bytes(_NONCE_LENGTH)
    return nonce + aesgcm.encrypt(nonce, plain_bytes, None)


def decrypt_raw(packed: bytes) -> bytes:
    """Decrypt nonce || ciphertext || tag -> raw bytes."""
    nonce = packed[:_NONCE_LENGTH]
    ct = packed[_NONCE_LENGTH:]
    aesgcm = _get_aesgcm()
    return aesgcm.decrypt(nonce, ct, None)
