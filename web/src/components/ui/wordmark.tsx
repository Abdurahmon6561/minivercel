import { cn } from "../../lib/cn";

/**
 * The product mark. Shared so the landing, the login page and the dashboard
 * header cannot drift apart - the brand is one of the few things that has to be
 * identical everywhere it appears.
 *
 * Not a link: where it should point differs per surface (the dashboard header
 * wants /projects, the login page wants nothing at all, since "/" on the
 * dashboard host would bounce straight back to /login). Callers wrap it.
 */
export function Wordmark({
  size = "sm",
  className,
}: {
  size?: "sm" | "lg";
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center", size === "lg" ? "gap-3" : "gap-2", className)}>
      <span
        aria-hidden="true"
        className={cn("leading-none text-primary", size === "lg" ? "text-2xl" : "text-lg")}
      >
        ▲
      </span>
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
