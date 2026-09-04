"""Project slug generation (AUTODEPLOY.md section 2).

Two jobs: invent a readable slug when nobody supplied a usable one, and refuse
the handful of words that would collide with our own routing.

RESERVED is the security control. In path mode `/s/api/` is harmless, but the
addendum's Phase B puts every slug on `{slug}.yourdomain.com`, where a project
called `api` hijacks the API and `www` hijacks the marketing site. Enforcing it
now costs nothing; retrofitting it after slugs are live means breaking URLs
people have already shared.

Phase 3 made this reachable rather than theoretical: an imported project takes
its slug from the repository name, and repositories called `docs`, `app` or
`assets` are extremely common.
"""

from __future__ import annotations

import secrets

ADJECTIVES = [
    "blue", "swift", "quiet", "bold", "warm", "clever", "silent",
    "bright", "gentle", "rapid", "solid", "amber", "cosmic", "lucky",
]
NOUNS = [
    "forest", "river", "harbor", "meadow", "canyon", "summit", "orbit",
    "ember", "lantern", "compass", "anchor", "prairie", "beacon", "vault",
]

#: Words that must never become a slug. Anything that is one of our own path
#: segments, or a hostname people expect to mean something else - and, since
#: the getdropbin.xyz migration (AUTODEPLOY.md section 1), an actual
#: subdomain: `{slug}.getdropbin.xyz` puts every one of these at the same
#: level as `api.` and `app.`, where a convincing-looking `login` or `oauth`
#: subdomain is a phishing setup, not just an ugly URL.
RESERVED = frozenset(
    {
        # This project's own routing (app/main.py, app/hostrouting.py).
        "api", "app", "www", "s", "health", "openapi", "redoc",
        "webhooks", "deployments", "projects", "auth",
        # Ours, beyond the addendum's list.
        "dashboard", "docs", "status", "login", "static", "assets", "mail",
        # Hostnames and paths people expect to mean something else - the
        # platform's own migration checklist.
        "cdn", "test", "staging", "dev", "prod", "production", "blog",
        "shop", "store", "help", "support", "about", "contact", "home",
        "root", "public", "private", "logout", "register", "signup",
        "oauth", "callback", "webhook", "cron", "job", "jobs", "admin",
    }
)


def generate_slug() -> str:
    """A readable slug: adjective-noun-NNNN.

    14 x 14 x 9000 is about 1.7M combinations, so collisions are rare - but the
    caller still retries, because "rare" is not "never".
    """
    return "%s-%s-%d" % (
        secrets.choice(ADJECTIVES),
        secrets.choice(NOUNS),
        secrets.randbelow(9000) + 1000,
    )


def is_reserved(slug: str) -> bool:
    return slug.lower() in RESERVED
