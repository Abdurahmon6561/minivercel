import { cn } from "../../lib/cn";

/**
 * A loading placeholder.
 *
 * Skeletons rather than a spinner because the shape of the answer is already
 * known: showing the layout that is about to arrive stops the page jumping when
 * it does. The pulse stops under `prefers-reduced-motion` via index.css.
 *
 * Always aria-hidden. The live region announcing "loading" belongs once on the
 * container, not on each of nine grey rectangles.
 */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-pulse rounded-md bg-surface-hover", className)}
      {...props}
    />
  );
}
