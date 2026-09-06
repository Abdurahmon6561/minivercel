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
