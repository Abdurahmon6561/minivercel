import type { ComponentType } from "react";
import { Monitor, Moon, Sun } from "lucide-react";

import { cn } from "../../lib/cn";
import { useTheme } from "../../lib/theme-provider";
import type { ThemePreference } from "../../lib/theme";

/**
 * A three-state segmented control, not a two-state switch and not a cycler.
 *
 * "System" is a real choice, so it needs a real control - a sun/moon switch
 * cannot express it, and a cycling button hides which states exist and can take
 * three clicks to reach the one you want. Three buttons, one click each.
 *
 * `role="group"` with `aria-pressed` rather than a radiogroup: a radiogroup
 * promises arrow-key navigation and roving tabindex, and these are three
 * ordinary toggle buttons.
 */
const OPTIONS: {
  value: ThemePreference;
  label: string;
  Icon: ComponentType<{ className?: string }>;
}[] = [
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
  { value: "system", label: "System", Icon: Monitor },
];

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, resolvedTheme, setTheme } = useTheme();

  return (
    <div
      role="group"
      aria-label="Colour theme"
      className={cn(
        "inline-flex items-center gap-0.5 rounded-md border border-border bg-surface p-0.5",
        className,
      )}
    >
      {OPTIONS.map(({ value, label, Icon }) => {
        const active = theme === value;
        // The icon alone does not say what "system" currently means, and that
        // is the one option whose effect is not obvious from its glyph.
        const description =
          value === "system" ? `System theme (currently ${resolvedTheme})` : `${label} theme`;

        return (
          <button
            key={value}
            type="button"
            aria-pressed={active}
            aria-label={description}
            title={description}
            onClick={() => setTheme(value)}
            className={cn(
              "inline-grid size-7 place-items-center rounded-sm transition-colors",
              "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
              active
                ? "bg-primary-subtle text-primary-subtle-fg"
                : "text-muted hover:bg-surface-hover hover:text-text",
            )}
          >
            <Icon className="size-3.5" />
          </button>
        );
      })}
    </div>
  );
}
