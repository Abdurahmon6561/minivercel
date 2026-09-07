/**
 * Which host is this bundle being served from?
 *
 * The apex (`getdropbin.xyz`) and the dashboard subdomain (`app.getdropbin.xyz`)
 * serve the same build - see app/hostrouting.py - so `/` has to mean two
 * different things depending on where it was requested from. This is the only
 * place that decides which.
 *
 * Deliberately a prefix check rather than a configured domain: it needs no
 * build-time variable, works on preview deployments, and treats anything that
 * is not the dashboard subdomain as marketing. On localhost that means `/` is
 * the landing and the dashboard lives at `/projects`, which is what you want
 * when developing the landing.
 */
export function isDashboardHost(): boolean {
  if (typeof window === "undefined") return false;
  return window.location.hostname.startsWith("app.");
}

/**
 * Where an OAuth round-trip should come back to.
 *
 * Sign-in can start from either host - the landing's CTA sits on the apex - but
 * it must always finish in the dashboard, so this returns the dashboard origin
 * regardless of where it was called from.
 *
 * The ORIGIN, deliberately, with no path on the end. Supabase checks
 * `redirectTo` against an allow-list configured in its dashboard, and
 * `https://app.{domain}` is the value already in use and known to work. Adding
 * `/projects` would only be honoured if that list is a wildcard, and if it is
 * not, Supabase silently falls back to the project's Site URL - a broken
 * sign-in that only shows up in production. Landing on `/` costs one
 * client-side redirect (App's `Root` sends a signed-in user to /projects) and
 * depends on nothing outside this repo.
 *
 * Localhost has no `app.` subdomain, so there it stays put.
 */
export function dashboardOrigin(): string {
  if (typeof window === "undefined") return "";
  const { protocol, host, hostname, origin } = window.location;

  const isLocal =
    hostname === "localhost" ||
    hostname === "[::1]" ||
    /^\d{1,3}(\.\d{1,3}){3}$/.test(hostname);
  if (isLocal || isDashboardHost()) return origin;

  return `${protocol}//app.${host}`;
}

/**
 * The domain a project's site is served from, or null when there isn't one.
 *
 * `app.getdropbin.xyz` -> `getdropbin.xyz`, so the new-project screen can show
 * `{slug}.getdropbin.xyz` before the project exists. Returns null on localhost
 * and bare IPs, where there is no wildcard DNS and a preview would be a lie -
 * callers show the slug on its own there.
 */
export function siteDomain(): string | null {
  if (typeof window === "undefined") return null;
  const { hostname } = window.location;
  const isLocal =
    hostname === "localhost" ||
    hostname === "[::1]" ||
    !hostname.includes(".") ||
    /^\d{1,3}(\.\d{1,3}){3}$/.test(hostname);
  if (isLocal) return null;
  return hostname.startsWith("app.") ? hostname.slice("app.".length) : hostname;
}
