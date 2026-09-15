import { Moon, Sun } from "lucide-react";

import { Button } from "./button";
import { useTheme } from "../../lib/theme-provider";

/**
 * A single icon button, not a dropdown or a three-way control.
 *
 * The underlying preference still has a "system" value (lib/theme.ts) so a
 * first-time visitor gets the OS's choice with no flash of the wrong theme -
 * that default is worth keeping. What changed is the control: light and dark
 * are the only two states worth a click here, so this shows and toggles the
 * resolved appearance directly. Reusing the shared `Button` (`variant`,
 * `size="icon"`) rather than hand-rolled classes is what keeps its border and
 * shape identical to every other button on the page instead of quietly
 * drifting from them.
 */
export function ThemeToggle({ className }: { className?: string }) {
  const { resolvedTheme, setTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  return (
    <Button
      type="button"
      variant="secondary"
      size="icon"
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      title={isDark ? "Switch to light theme" : "Switch to dark theme"}
      icon={isDark ? <Moon aria-hidden="true" /> : <Sun aria-hidden="true" />}
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className={className}
    />
  );
}
