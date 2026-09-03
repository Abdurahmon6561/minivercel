"""One mapping from our internal exceptions to HTTP status codes.

There were two of these - one in `routers/github.py` and an inline `502` in
`routers/projects.py` - and they disagreed. Enabling builds through
`POST /api/projects/{slug}/builds` reported a missing `workflow` scope as a 403
with the scope named; doing exactly the same thing through
`PATCH /api/projects/{slug}` with `builds_enabled: true` reported it as a bare
`502 Bad Gateway`. Same cause, same fix needed by the user, two different
answers, and only one of them said what to do.

The mapping, and the reasoning for each:

    GitOpsError                     400  our own precondition; the message is
                                         written for the user and says the fix
    GitHub 401                      401  the stored token was revoked
    GitHub 403/404 with a scope     403  see below
    GitHub 404 without a scope      404  the repository really is not there
    GitHub 403 rate limit           429  transient, with a Retry-After
    anything else from GitHub       502  GitHub itself is unhappy

The scope case is the one worth spelling out. GitHub answers a call made
without the necessary OAuth scope with **404**, not 403 - the documented
behaviour is that a token which cannot see a resource is told the resource does
not exist. Forwarded literally, that becomes "your repository was not found",
which sends the user to look for a repository that is sitting right there. So
when the failing call is one whose required scope we know (`app/github.py`
`SCOPE_FOR_CALL`), it is reported as a 403 naming the scope and the way to grant
it: the status now describes the real problem, which is permission.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from ..github import GitHubError
from ..gitops import GitOpsError


def as_http(exc: Exception) -> HTTPException:
    """Turn a GitOps/GitHub failure into the status the user can act on."""
    if isinstance(exc, GitOpsError):
        # Raised by us, never by GitHub: a missing token, a repo we refuse to
        # touch, an invalid build setting. Always self-explanatory.
        return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    if isinstance(exc, GitHubError):
        message = str(exc)

        if exc.status_code == 401:
            return HTTPException(status.HTTP_401_UNAUTHORIZED, message)

        if exc.status_code == 403 and "rate limit" in message.lower():
            return HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, message, headers={"Retry-After": "60"}
            )

        # 403 is the honest code for a permission problem, whichever status
        # GitHub chose to express it with. A 404 is only forwarded as a 404 when
        # nothing suggests a missing scope - otherwise it means "your repository
        # is gone", which is the misleading answer this exists to stop.
        if exc.status_code == 403 or (
            exc.status_code == 404 and getattr(exc, "scope_hint", None)
        ):
            return HTTPException(status.HTTP_403_FORBIDDEN, message)

        if exc.status_code == 404:
            return HTTPException(status.HTTP_404_NOT_FOUND, message)

        return HTTPException(status.HTTP_502_BAD_GATEWAY, message)

    return HTTPException(
        status.HTTP_500_INTERNAL_SERVER_ERROR, "Unexpected error talking to GitHub."
    )
