"""Every public URL this service hands out (AUTODEPLOY.md section 1).

One function, because the addendum's Phase B moves sites from a path to a
subdomain:

    path mode:       https://minivercel.onrender.com/s/blue-forest-4821/
    subdomain mode:  https://blue-forest-4821.example.com/

The database, the storage keys and the deploy pipeline are identical either way
- only the routing layer changes. Built inline in five handlers, that switch
means finding all five; built here, it is two environment variables.
"""

from __future__ import annotations

from .config import Settings


def site_url(settings: Settings, slug: str) -> str:
    """The public URL of a deployed site."""
    if settings.url_mode == "subdomain" and settings.site_domain:
        return "https://%s.%s/" % (slug, settings.site_domain)
    return "%s/s/%s/" % (settings.public_base_url, slug)


def preview_url(settings: Settings, slug: str, deployment_id: str) -> str:
    """Where a past deployment can be looked at before it is promoted.

    Built from `site_url` rather than assembled separately, so it follows the
    slug onto subdomains whenever URL_MODE changes and never becomes the one
    hard-coded `/s/` left behind.
    """
    return "%s_d/%s/" % (site_url(settings, slug), deployment_id)


def webhook_url(settings: Settings) -> str:
    """Where GitHub delivers push events.

    Always on the API origin: it is our endpoint, not a served site, so it does
    not move when sites move to subdomains.
    """
    return settings.public_base_url + "/api/webhooks/github"


def api_base_url(settings: Settings) -> str:
    """The origin a GitHub Actions runner POSTs its build output to."""
    return settings.public_base_url
