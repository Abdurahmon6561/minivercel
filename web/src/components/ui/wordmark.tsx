import { cn } from "../../lib/cn";

/**
 * The mark: a single drop, badged in a rounded square.
 *
 * The previous version drew the drop as an arrow falling onto a tray, which
 * read - correctly - as a plain download icon with no connection to the
 * product. This is a shape instead of a pictogram: a raindrop silhouette
 * with one glossy highlight, which is legible and ownable even at
 * favicon size, where a multi-part icon turns to mush.
 *
 * `variant="bare"` strips the badge and paints the drop in `currentColor`,
 * for the one place (BrandPane) where the surrounding surface is already
 * `bg-primary` - a primary-on-primary badge there would vanish.
 */
export function LogoMark({
  className,
  variant = "badge",
}: {
  className?: string;
  variant?: "badge" | "bare";
}) {
  const drop = (
    <path d="M12 5.25c0 0-4.55 6.98-4.55 10.4 0 2.51 2.04 4.55 4.55 4.55s4.55-2.04 4.55-4.55c0-3.42-4.55-10.4-4.55-10.4Z" />
  );
  const highlight = (
    <ellipse
      cx="10.35"
      cy="11.1"
      rx="1.05"
      ry="2"
      transform="rotate(-25 10.35 11.1)"
      className="fill-primary/45"
    />
  );

  if (variant === "bare") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" className={className}>
        <g fill="currentColor">{drop}</g>
        {highlight}
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className}>
      <rect x="1" y="1" width="22" height="22" rx="6.5" className="fill-primary" />
      <g className="fill-primary-fg">{drop}</g>
      {highlight}
    </svg>
  );
}

/**
 * The product mark. Shared so the landing, the login page and the dashboard
 * header cannot drift apart - the brand is one of the few things that has to be
 * identical everywhere it appears.
 *
 * Not a link: where it should point differs per surface (the dashboard header
 * wants /projects, the login page wants the marketing site). Callers wrap it.
 */
export function Wordmark({
  size = "sm",
  className,
}: {
  size?: "sm" | "lg";
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center", size === "lg" ? "gap-2.5" : "gap-2", className)}>
      <LogoMark className={size === "lg" ? "size-7" : "size-5"} />
      <span
        className={cn(
          "font-semibold tracking-tight text-text",
          size === "lg" ? "text-lg" : "text-sm",
        )}
      >
        Dropbin
      </span>
    </span>
  );
}
