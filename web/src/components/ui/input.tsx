import { forwardRef } from "react";

import { cn } from "../../lib/cn";

/**
 * A text field.
 *
 * `bg-bg` rather than `bg-surface`: inputs sit inside cards, and a field the
 * same colour as the card it is on does not read as a field. Sunk one step
 * below its container is what makes it look editable in both themes.
 */
export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "w-full rounded-md border border-border-strong bg-bg px-3 py-2 text-sm text-text",
        "placeholder:text-muted/60",
        "transition-colors focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);

Input.displayName = "Input";
