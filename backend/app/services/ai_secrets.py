from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_VERSION = "v1"


class ApiKeyCipher:
    """Authenticated encryption for provider keys using a deployment-owned master secret."""

    def __init__(self, master_secret: str) -> None:
        if len(master_secret) < 32:
            raise ValueError("The encryption master secret must be at least 32 characters.")
        self._aead = AESGCM(hashlib.sha256(master_secret.encode("utf-8")).digest())

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            raise ValueError("API keys must not be empty.")
        nonce = os.urandom(12)
        ciphertext = self._aead.encrypt(nonce, plaintext.encode("utf-8"), b"ai-provider-key")
        payload = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
        return f"{_VERSION}.{payload}"

    def decrypt(self, token: str) -> str:
        version, separator, payload = token.partition(".")
        if version != _VERSION or not separator:
            raise ValueError("Unsupported encrypted secret format.")
        try:
            raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        except Exception as exc:
            raise ValueError("The encrypted secret is malformed.") from exc
        if len(raw) < 13:
            raise ValueError("The encrypted secret is malformed.")
        return self._aead.decrypt(raw[:12], raw[12:], b"ai-provider-key").decode("utf-8")


def mask_api_key(api_key: str) -> str:
    stripped = api_key.strip()
    if len(stripped) <= 4:
        return "****"
    prefix = "sk-" if stripped.startswith("sk-") else ""
    return f"{prefix}****{stripped[-4:]}"
