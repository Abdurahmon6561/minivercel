/**
 * Theme resolution and persistence.
 *
 * Three states, not two. "system" is the default and is a real, selectable
 * value - not the absence of a choice - because a user whose OS switches at
 * sunset wants the dashboard to switch with it, and that is impossible to
 * express with a light/dark boolean.
 *
 * The stored value is the *preference* ("system"); the resolved value is what
 * is actually painted ("light" | "dark"). `applyTheme` writes `data-theme` on
 * <html> for the two explicit cases and removes it for "system", which hands
 * the decision to the `prefers-color-scheme` block in styles/tokens.css.
 *
 * Every function here is deliberately plain DOM: `index.html` runs
 * `resolvePreference`'s logic inline before first paint to avoid a flash of the
 * wrong theme, and that script cannot import a module.
 */

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

/** Named by the brief. Changing it silently resets everyone's choice. */
export const THEME_STORAGE_KEY = "minivercel-theme";

export const THEME_PREFERENCES: readonly ThemePreference[] = [
  "light",
  "dark",
  "system",
];

function isPreference(value: unknown): value is ThemePreference {
  return value === "light" || value === "dark" || value === "system";
}

const DARK_QUERY = "(prefers-color-scheme: dark)";

/** What the OS currently reports. Defaults to light where matchMedia is absent. */
export function systemTheme(): ResolvedTheme {
  return typeof window !== "undefined" && window.matchMedia?.(DARK_QUERY).matches
    ? "dark"
    : "light";
}

/**
 * The stored preference, or "system" when nothing is stored or the value is
 * junk. localStorage throws outright in a locked-down browser rather than
 * returning null, so this can never be an unguarded read.
 */
export function storedPreference(): ThemePreference {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY);
    return isPreference(raw) ? raw : "system";
  } catch {
    return "system";
  }
}

export function storePreference(preference: ThemePreference): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    /* Private mode, or site data blocked. The theme still applies for this
       page load; it just will not be remembered. Not worth surfacing. */
  }
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  return preference === "system" ? systemTheme() : preference;
}

/**
 * Paint the preference.
 *
 * "system" *removes* the attribute rather than writing the currently resolved
 * value, so that a running tab follows an OS change with no JavaScript at all -
 * the media query in tokens.css handles it.
 */
export function applyTheme(preference: ThemePreference): void {
  const root = document.documentElement;
  if (preference === "system") {
    root.removeAttribute("data-theme");
  } else {
    root.setAttribute("data-theme", preference);
  }
  // Kept in sync so the browser paints native form controls, scrollbars and the
  // overscroll area to match. tokens.css sets this too, but only for the cases
  // its selectors match; this covers all three from one place.
  root.style.colorScheme = resolveTheme(preference);
}

/**
 * Subscribe to OS theme changes. Returns an unsubscribe function.
 *
 * The caller is expected to ignore the callback unless the preference is
 * "system"; this only reports what the OS did.
 */
export function watchSystemTheme(
  onChange: (theme: ResolvedTheme) => void,
): () => void {
  if (typeof window === "undefined" || !window.matchMedia) return () => {};
  const query = window.matchMedia(DARK_QUERY);
  const handler = (event: MediaQueryListEvent) =>
    onChange(event.matches ? "dark" : "light");
  query.addEventListener("change", handler);
  return () => query.removeEventListener("change", handler);
}
