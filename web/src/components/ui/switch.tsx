import { cn } from "../../lib/cn";

/**
 * An on/off switch.
 *
 * Hand-rolled rather than another Radix package, and the reasoning is the
 * mirror of why Dialog and Tabs are not: a switch has no focus trap, no roving
 * tabindex, no portal and no outside-click behaviour. It is a <button> with
 * role="switch" and aria-checked - the browser already gives it Space, Enter
 * and focus for free. There is nothing here worth 3 kB.
 *
 * A real button, not a styled checkbox, so screen readers announce the state
 * and it is keyboard-operable with no extra handlers.
 */
export function Switch({
  checked,
  onCheckedChange,
  disabled = false,
  busy = false,
  label,
}: {
  checked: boolean;
  onCheckedChange: (next: boolean) => void;
  disabled?: boolean;
  /** Dims the knob while a request is in flight, without moving it back. */
  busy?: boolean;
  /** Required: the switch is unlabelled otherwise, since it renders no text. */
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      aria-busy={busy || undefined}
      disabled={disabled || busy}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative h-6 w-11 shrink-0 rounded-full transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        "disabled:cursor-not-allowed disabled:opacity-50",
        // Success rather than primary: this reports a state that is on or off,
        // not an action, and primary is reserved for things you press.
        checked ? "bg-success" : "bg-border-strong",
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "absolute top-1 size-4 rounded-full bg-surface shadow-sm transition-[left]",
          checked ? "left-6" : "left-1",
          busy && "animate-pulse",
        )}
      />
    </button>
  );
}
