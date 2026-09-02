"""Per-project deploy tokens (SPEC.md Phase 4 point 4).

A deploy token is what a GitHub Actions runner presents instead of a user's JWT.
It is scoped to exactly one project and can do exactly one thing: create a
deployment for that project. It cannot list projects, read `/api/me`, delete
anything, or touch another project - the only lookup that accepts it returns a
single project row, and every route other than the upload rejects it.

The token is stored as `sha256(token)` and never in the clear. We hand the raw
value to GitHub's Actions secrets API once, at creation, and then forget it:
there is no endpoint that can read it back, because there is nothing to read.

`mvd_` prefix so the upload route can tell a deploy token from a JWT without
attempting to parse one as the other, and so a leaked value is recognisable in a
log or a paste.
"""

from __future__ import annotations

import hashlib
import secrets

PREFIX = "mvd_"
TOKEN_BYTES = 32


def generate() -> str:
    return PREFIX + secrets.token_urlsafe(TOKEN_BYTES)


def looks_like_deploy_token(value: str) -> bool:
    return value.startswith(PREFIX)


def fingerprint(token: str) -> str:
    """sha256 hex. The only form of the token that touches the database."""
    return hashlib.sha256(token.encode()).hexdigest()


def redact(token: str) -> str:
    """A safe way to mention a token in a log line.

    Never log the token. If you must identify one, log this: it is the prefix
    plus the first eight characters of the hash, which is enough to correlate
    two log lines and useless to anyone who steals it.
    """
    return "%s…%s" % (PREFIX, fingerprint(token)[:8])
