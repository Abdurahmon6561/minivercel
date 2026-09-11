import { forwardRef } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";

import { cn } from "../../lib/cn";

/**
 * The one button.
 *
 * Every class below resolves to a token from styles/tokens.css - there is no
 * hex value here, and no `dark:` variant either. Both themes come from the same
 * `bg-surface` / `text-text` utilities because those utilities compile to
 * `var(--surface)` and `var(--text)`, which the theme swaps underneath. If you
 * find yourself reaching for `dark:`, the token is missing.
 *
 * Variants, and when to use which:
 *
 *   primary      the one action this screen exists for. At most one per view.
 *   secondary    a real alternative to the primary action.
 *   ghost        navigation and toolbar affordances; no chrome until hovered.
 *   destructive  removes data. Filled red, so it can never be clicked absently.
 *   subtle       destructive's quieter form - outlined, for a delete that opens
 *                a confirmation rather than one that acts immediately.
 *   link         inline in prose, where a button-shaped thing would be wrong.
 *
 * Fully rounded at every size, not `rounded-md`. The landing page's CTAs were
 * pill-shaped from the start; the dashboard's were not, which is what made the
 * product read as two different pieces of software stitched together the
 * moment you followed "Continue with GitHub" from one into the other. This is
 * the one place that shape lives, so a dashboard button and a landing button
 * are now the same shape everywhere by construction rather than by each
 * caller remembering to add `rounded-full`.
 */
const button = cva(
  [
    "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap",
    "font-medium select-none cursor-pointer",
    // 150ms is the ceiling for something that should feel instant. Only the
    // properties that actually change animate: transitioning `all` also
    // animates layout on a width change, which reads as lag.
    "transition-[background-color,border-color,color,box-shadow,transform] duration-150",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
    // A disabled button must still look like a button, or the user reads the
    // screen as broken rather than as blocked - and the cursor should say
    // "blocked" rather than "clickable".
    //
    // No `pointer-events-none`: a native disabled <button> already fires no
    // click, so suppressing pointer events only costs the not-allowed cursor
    // that tells the user why nothing happened.
    "disabled:cursor-not-allowed disabled:opacity-50",
    "[&_svg]:pointer-events-none [&_svg]:shrink-0",
  ],
  {
    variants: {
      variant: {
        primary:
          "bg-primary text-primary-fg shadow-sm hover:bg-primary-hover active:translate-y-px",
        secondary:
          "border border-border-strong bg-surface text-text shadow-sm hover:bg-surface-hover active:translate-y-px",
        ghost: "text-muted hover:bg-surface-hover hover:text-text",
        destructive:
          "bg-destructive text-destructive-fg shadow-sm hover:bg-destructive-hover active:translate-y-px",
        subtle:
          "border border-destructive/35 text-destructive hover:border-destructive/60 hover:bg-destructive-subtle",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-8 rounded-full px-3.5 text-xs [&_svg]:size-3.5",
        md: "h-9 rounded-full px-5 text-sm [&_svg]:size-4",
        lg: "h-11 rounded-full px-6 text-[15px] [&_svg]:size-4",
        icon: "size-9 rounded-full [&_svg]:size-4",
      },
      block: { true: "w-full", false: "" },
    },
    compoundVariants: [
      // `link` is text, not a control: the height and padding of a real button
      // would leave it floating in the middle of a sentence.
      { variant: "link", size: "sm", class: "h-auto px-0" },
      { variant: "link", size: "md", class: "h-auto px-0" },
      { variant: "link", size: "lg", class: "h-auto px-0" },
    ],
    defaultVariants: { variant: "secondary", size: "md", block: false },
  },
);

export interface ButtonProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "color">,
    VariantProps<typeof button> {
  /** Swap the leading icon for a spinner and block interaction. */
  loading?: boolean;
  /** Rendered before the label. Pass a lucide icon; it is sized by `size`. */
  icon?: React.ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant,
      size,
      block,
      loading = false,
      icon,
      disabled,
      children,
      type = "button",
      ...props
    },
    ref,
  ) => (
    <button
      ref={ref}
      // Buttons inside a form default to `submit`, which is almost never what
      // is wanted from a component used this widely.
      type={type}
      disabled={disabled || loading}
      // The label is replaced by nothing while loading - the spinner sits where
      // the icon was and the text stays - so `aria-busy` is what tells a screen
      // reader anything happened.
      aria-busy={loading || undefined}
      className={cn(button({ variant, size, block }), className)}
      {...props}
    >
      {loading ? <Loader2 className="animate-spin" aria-hidden="true" /> : icon}
      {children}
    </button>
  ),
);

Button.displayName = "Button";

export { button as buttonVariants };
