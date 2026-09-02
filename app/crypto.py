"""Symmetric encryption for the one secret we have to store and read back.

A GitHub provider token cannot be hashed - Phase 3 has to present the original
value to api.github.com. So it is encrypted with a key that lives only in the
server's environment, which puts a database dump and a live credential on
different sides of a line.

Deliberately fail-closed: with no key configured, storing a token raises rather
than silently writing plaintext. A missing environment variable must not quietly
downgrade the security of the most sensitive row in the database.
"""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken

from .config import Settings

log = logging.getLogger("minivercel.crypto")


class EncryptionUnavailable(RuntimeError):
    """GITHUB_TOKEN_KEY is missing or unusable."""


def _cipher(settings: Settings) -> Fernet:
    key = settings.github_token_key
    if not key:
        raise EncryptionUnavailable(
            "GITHUB_TOKEN_KEY is not set. Generate one with: python -c "
            '"from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise EncryptionUnavailable(
            "GITHUB_TOKEN_KEY is not a valid Fernet key (32 url-safe base64 bytes)."
        ) from exc


def encrypt(value: str, settings: Settings) -> str:
    return _cipher(settings).encrypt(value.encode()).decode()


def decrypt(value: str, settings: Settings) -> str:
    """Raises EncryptionUnavailable if the key is wrong or the value corrupt.

    A rotated key makes every stored token undecryptable. That is recoverable -
    the user signs in with GitHub again - so the caller should treat a failure
    here as "no token stored", never as a fatal error.
    """
    try:
        return _cipher(settings).decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise EncryptionUnavailable(
            "Stored token could not be decrypted. GITHUB_TOKEN_KEY may have "
            "changed; the user needs to reconnect GitHub."
        ) from exc
