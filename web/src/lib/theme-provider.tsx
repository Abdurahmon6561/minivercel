import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  applyTheme,
  storePreference,
  storedPreference,
  systemTheme,
  watchSystemTheme,
  type ResolvedTheme,
  type ThemePreference,
} from "./theme";

interface ThemeValue {
  /** What the user chose. Persisted. */
  theme: ThemePreference;
  /** What is actually painted right now. Never "system". */
  resolvedTheme: ResolvedTheme;
  setTheme: (next: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeValue | null>(null);

/**
 * React wrapper around lib/theme.ts, which owns all the DOM and storage work.
 *
 * The OS preference is held in state rather than read on demand. The CSS does
 * not need it - the `prefers-color-scheme` block in tokens.css repaints on its
 * own - but React consumers do: without this, the toggle would keep showing a
 * sun after the OS switched to dark at sunset.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  // Read straight from localStorage on the first render, matching what the
  // pre-paint script in index.html already put on <html>. Any other initial
  // value would repaint on mount, which is the flash we are avoiding.
  const [theme, setThemeState] = useState<ThemePreference>(storedPreference);
  const [system, setSystem] = useState<ResolvedTheme>(systemTheme);

  useEffect(() => watchSystemTheme(setSystem), []);

  // `system` is a dependency even though applyTheme takes only the preference:
  // when the preference is "system" and the OS flips, the attribute does not
  // change but `style.color-scheme` has to, or native controls and the
  // scrollbar stay in the old theme.
  useEffect(() => {
    applyTheme(theme);
  }, [theme, system]);

  const setTheme = useCallback((next: ThemePreference) => {
    setThemeState(next);
    storePreference(next);
  }, []);

  const value = useMemo<ThemeValue>(
    () => ({
      theme,
      // Not `resolveTheme(theme)`: that helper calls matchMedia at call time,
      // which is correct for the pre-paint path but not reactive here.
      resolvedTheme: theme === "system" ? system : theme,
      setTheme,
    }),
    [theme, system, setTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("useTheme must be used inside ThemeProvider");
  return value;
}
