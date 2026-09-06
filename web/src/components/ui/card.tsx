import { cn } from "../../lib/cn";

/**
 * A raised surface. Border in light where the shadow is nearly invisible, a
 * heavier shadow in dark where the border alone would not separate it from the
 * page - both come from the tokens, so this is one class list, not two.
 *
 * `interactive` is for cards that are a link target: it lifts on hover and
 * establishes a containing block, which is what lets the primary link inside
 * stretch over the whole card (see `.after:absolute` in Projects).
 */
export function Card({
  className,
  interactive = false,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { interactive?: boolean }) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-surface shadow-sm",
        interactive &&
          "relative transition-[box-shadow,border-color] duration-150 hover:border-border-strong hover:shadow-md",
        className,
      )}
      {...props}
    />
  );
}
