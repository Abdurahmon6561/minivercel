/**
 * A stable placeholder image for a project that has no screenshot yet.
 *
 * Built out of theme tokens rather than fixed hex values, for two reasons: the
 * "no hex outside tokens.css" rule holds, and the thumbnails then restate
 * themselves in dark mode instead of glowing at full light-theme saturation on
 * a near-black page.
 *
 * Keyed on the slug, so a project's tile is the same every time it is seen -
 * which is the only thing that makes it useful as recognition rather than
 * decoration. Real screenshots replace this later.
 */
import { hash } from "./hash";

const PAIRS: [string, string][] = [
  ["--primary", "--accent-vivid"],
  ["--accent-vivid", "--info"],
  ["--info", "--primary"],
  ["--accent", "--accent-vivid"],
  ["--primary", "--info"],
];

export function slugGradient(slug: string): string {
  const h = hash(slug);
  const [from, to] = PAIRS[h % PAIRS.length];
  const angle = 110 + (h % 6) * 15;
  return `linear-gradient(${angle}deg, var(${from}), var(${to}))`;
}
