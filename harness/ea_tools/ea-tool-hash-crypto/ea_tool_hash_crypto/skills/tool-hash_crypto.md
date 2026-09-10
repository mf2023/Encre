---
name: tool-hash_crypto
description: "Compute hashes (MD5/SHA1/SHA256/SHA512), HMACs, and file checksums, perform AES symmetric encrypt/decrypt (CBC/ECB/CTR/GCM), and base64 encode/decode. Use this instead of shelling out to openssl or python one-liners -- it returns structured JSON and streams large files in chunks for hashing."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# hash_crypto

Compute hashes (MD5/SHA1/SHA256/SHA512), HMACs, and file checksums, perform AES symmetric encrypt/decrypt (CBC/ECB/CTR/GCM), and base64 encode/decode. Use this instead of shelling out to openssl or python one-liners -- it returns structured JSON and streams large files in chunks for hashing.

WHEN to use: verify file integrity (checksums), hash a string, sign a payload with HMAC, encrypt/decrypt a secret with a passphrase, or do quick base64 conversions.
WHEN NOT to use: for password storage use a slow KDF (argon2/bcrypt) rather than plain sha256; for TLS/SSL or public-key cryptography use a dedicated library; for production key management use a vault.
TIPS: for checksum, pass a comma-separated 'algorithm' (e.g. 'sha256,sha1') to compute several checksums in one pass; the AES key is derived as sha256(passphrase), so the same passphrase reproduces the same key; GCM mode is recommended for authenticated encryption (it returns a tag you must keep for decrypt).
PITFALLS: avoid MD5/SHA1 for security-sensitive purposes -- prefer SHA256 or stronger; AES ECB mode is insecure for most data -- prefer CBC or GCM; decrypt requires the exact iv (and tag for GCM) returned by the matching encrypt call.
