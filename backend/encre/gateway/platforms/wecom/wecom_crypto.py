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
Inspired by the Hermes Agent project (https://github.com/NousResearch/hermes-agent.git).
Thanks to Hermes Agent for the inspiration on this module.

WeCom BizMsgCrypt-compatible AES-CBC encryption for callback mode.

This module implements the same wire format as Tencent's official
``WXBizMsgCrypt`` helper so that WeCom can verify, encrypt and decrypt the
callback payloads exchanged with a self-built enterprise application.

The format is, per message:

* A 16-byte random prefix.
* A 4-byte network-order content length.
* The plaintext (XML) content.
* The ``receive_id`` (corp id) appended as a trailing UTF-8 string.
* The whole blob is PKCS#7 padded to a 32-byte block size, AES-256-CBC
  encrypted with the key derived from ``EncodingAESKey`` (base64 with one
  ``=`` padding), then base64 encoded.
* A SHA-1 signature over the sorted ``[token, timestamp, nonce, encrypt]``
  list authenticates the envelope.

The module intentionally has no external network dependencies: it only uses
the standard library plus ``cryptography`` for the AES primitive.
"""

import base64
import hashlib
import os
import secrets
import socket
import struct
import time
from typing import Optional
from xml.etree import ElementTree as ET

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class WeComCryptoError(Exception):
    """Base error for all WeCom crypto failures.

    Every signature, decryption and encryption failure raised by this module
    subclasses this exception so callers can catch them uniformly.
    """


class SignatureError(WeComCryptoError):
    """Raised when the supplied message signature does not match ours."""


class DecryptError(WeComCryptoError):
    """Raised when decryption, padding or receiver-id validation fails."""


class EncryptError(WeComCryptoError):
    """Raised when encryption (or blob assembly) fails."""


class PKCS7Encoder:
    """PKCS#7 padding/unescaping using WeCom's 32-byte block size.

    WeCom callbacks pad to a 32-byte block rather than the AES-native 16-byte
    block, matching Tencent's reference implementation.
    """

    block_size = 32

    @classmethod
    def encode(cls, text: bytes) -> bytes:
        """Pad ``text`` to a multiple of the block size.

        Args:
            text: The raw bytes to pad.

        Returns:
            bytes: ``text`` plus the PKCS#7 padding bytes.
        """
        amount_to_pad = cls.block_size - (len(text) % cls.block_size)
        if amount_to_pad == 0:
            amount_to_pad = cls.block_size
        pad = bytes([amount_to_pad]) * amount_to_pad
        return text + pad

    @classmethod
    def decode(cls, decrypted: bytes) -> bytes:
        """Strip and validate PKCS#7 padding from ``decrypted``.

        Args:
            decrypted: The decrypted bytes (with padding).

        Returns:
            bytes: The unpadded plaintext.

        Raises:
            DecryptError: When the payload is empty or the padding is invalid.
        """
        if not decrypted:
            raise DecryptError("empty decrypted payload")
        pad = decrypted[-1]
        if pad < 1 or pad > cls.block_size:
            raise DecryptError("invalid PKCS7 padding")
        if decrypted[-pad:] != bytes([pad]) * pad:
            raise DecryptError("malformed PKCS7 padding")
        return decrypted[:-pad]


def _sha1_signature(token: str, timestamp: str, nonce: str, encrypt: str) -> str:
    """Compute the WeCom envelope signature.

    WeCom signs a callback by sorting ``[token, timestamp, nonce, encrypt]``
    lexicographically, concatenating them and returning the SHA-1 hex digest.

    Args:
        token: The app's callback token.
        timestamp: The request timestamp string.
        nonce: The request nonce string.
        encrypt: The base64-encoded ciphertext.

    Returns:
        str: The 40-character SHA-1 hex digest.
    """
    parts = sorted([token, timestamp, nonce, encrypt])
    return hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()


class WXBizMsgCrypt:
    """Minimal WeCom callback crypto helper compatible with BizMsgCrypt semantics.

    This helper verifies and decrypts inbound callbacks (``verify_url``,
    ``decrypt``) and encrypts outbound replies (``encrypt``). It validates the
    envelope signature before any decryption and asserts the embedded
    ``receive_id`` matches the configured corp id.
    """

    def __init__(self, token: str, encoding_aes_key: str, receive_id: str):
        """Initialise the crypto helper and derive the AES key/IV.

        Args:
            token: The callback token shared with WeCom.
            encoding_aes_key: The 43-character ``EncodingAESKey`` (base64
                without its trailing ``=``).
            receive_id: The corp id expected to appear inside decrypted blobs.

        Raises:
            ValueError: When any argument is missing or ``encoding_aes_key`` is
            not exactly 43 characters.
        """
        if not token:
            raise ValueError("token is required")
        if not encoding_aes_key:
            raise ValueError("encoding_aes_key is required")
        if len(encoding_aes_key) != 43:
            raise ValueError("encoding_aes_key must be 43 chars")
        if not receive_id:
            raise ValueError("receive_id is required")

        self.token = token
        self.receive_id = receive_id
        # WeCom stores the key as base64 with a single omitted ``=``; restore it
        # so base64 can decode a 32-byte AES key, the first 16 bytes of which
        # serve as the fixed CBC initialisation vector.
        self.key = base64.b64decode(encoding_aes_key + "=")
        self.iv = self.key[:16]

    def verify_url(self, msg_signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        """Decrypt the ``echostr`` from WeCom's URL-verification handshake.

        Args:
            msg_signature: The signature supplied in the handshake query.
            timestamp: The handshake timestamp.
            nonce: The handshake nonce.
            echostr: The encrypted echo string to decrypt.

        Returns:
            str: The plaintext echo string to return to WeCom.

        Raises:
            SignatureError: When the signature does not match.
            DecryptError: When decryption fails.
        """
        plain = self.decrypt(msg_signature, timestamp, nonce, echostr)
        return plain.decode("utf-8")

    def decrypt(self, msg_signature: str, timestamp: str, nonce: str, encrypt: str) -> bytes:
        """Verify and decrypt an encrypted envelope.

        The signature is checked first. The base64 ciphertext is AES-256-CBC
        decrypted, PKCS#7 unpadded, and split into the 16-byte random prefix,
        the 4-byte content length, the XML content and the trailing
        ``receive_id``. The receiver id is validated before returning.

        Args:
            msg_signature: The envelope signature to verify.
            timestamp: The envelope timestamp.
            nonce: The envelope nonce.
            encrypt: The base64-encoded ciphertext.

        Returns:
            bytes: The decrypted XML content.

        Raises:
            SignatureError: When the signature does not match.
            DecryptError: On base64, AES, padding or receiver-id failures.
        """
        expected = _sha1_signature(self.token, timestamp, nonce, encrypt)
        if expected != msg_signature:
            raise SignatureError("signature mismatch")
        try:
            cipher_text = base64.b64decode(encrypt)
        except Exception as exc:
            raise DecryptError(f"invalid base64 payload: {exc}") from exc
        try:
            cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.iv), backend=default_backend())
            decryptor = cipher.decryptor()
            padded = decryptor.update(cipher_text) + decryptor.finalize()
            plain = PKCS7Encoder.decode(padded)
            content = plain[16:]  # skip 16-byte random prefix
            xml_length = socket.ntohl(struct.unpack("I", content[:4])[0])
            xml_content = content[4:4 + xml_length]
            receive_id = content[4 + xml_length:].decode("utf-8")
        except WeComCryptoError:
            raise
        except Exception as exc:
            raise DecryptError(f"decrypt failed: {exc}") from exc

        if receive_id != self.receive_id:
            raise DecryptError("receive_id mismatch")
        return xml_content

    def encrypt(self, plaintext: str, nonce: Optional[str] = None, timestamp: Optional[str] = None) -> str:
        """Encrypt ``plaintext`` and wrap it in a signed XML envelope.

        Args:
            plaintext: The XML string to encrypt.
            nonce: Optional nonce; one is generated when omitted.
            timestamp: Optional timestamp string; the current time is used when
                omitted.

        Returns:
            str: The full XML envelope containing ``Encrypt`` and
            ``MsgSignature``/``TimeStamp``/``Nonce`` children.
        """
        nonce = nonce or self._random_nonce()
        timestamp = timestamp or str(int(time.time()))
        encrypt = self._encrypt_bytes(plaintext.encode("utf-8"))
        signature = _sha1_signature(self.token, timestamp, nonce, encrypt)
        root = ET.Element("xml")
        ET.SubElement(root, "Encrypt").text = encrypt
        ET.SubElement(root, "MsgSignature").text = signature
        ET.SubElement(root, "TimeStamp").text = timestamp
        ET.SubElement(root, "Nonce").text = nonce
        return ET.tostring(root, encoding="unicode")

    def _encrypt_bytes(self, raw: bytes) -> str:
        """Assemble and AES-encrypt the WeCom message blob.

        The blob is ``random_prefix(16) || len(4 BE) || raw || receive_id``,
        PKCS#7 padded to 32 bytes and AES-256-CBC encrypted, then base64
        encoded for transport.

        Args:
            raw: The plaintext bytes to encrypt.

        Returns:
            str: The base64-encoded ciphertext.

        Raises:
            EncryptError: When assembly or encryption fails.
        """
        try:
            random_prefix = os.urandom(16)
            msg_len = struct.pack("I", socket.htonl(len(raw)))
            payload = random_prefix + msg_len + raw + self.receive_id.encode("utf-8")
            padded = PKCS7Encoder.encode(payload)
            cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.iv), backend=default_backend())
            encryptor = cipher.encryptor()
            encrypted = encryptor.update(padded) + encryptor.finalize()
            return base64.b64encode(encrypted).decode("utf-8")
        except Exception as exc:
            raise EncryptError(f"encrypt failed: {exc}") from exc

    @staticmethod
    def _random_nonce(length: int = 10) -> str:
        """Generate a URL-safe alphanumeric nonce of ``length`` characters.

        Args:
            length: Desired nonce length (default 10).

        Returns:
            str: The randomly generated nonce.
        """
        alphabet = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
        return "".join(secrets.choice(alphabet) for _ in range(length))
