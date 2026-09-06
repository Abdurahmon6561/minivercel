import { cn } from "../../lib/cn";
import { hash } from "../../lib/hash";

/**
 * An initial in a coloured circle, keyed to the person's identity.
 *
 * The colour comes from a hash of the email, the same trick the project cards
 * use for their thumbnails, so it is stable across sessions and devices with
 * nothing stored.
 *
 * The palette is four `-subtle` token pairs rather than the cards' gradients,
 * and that is a deliberate difference: a gradient built from --accent-vivid is
 * cyan-500, and a white letter on cyan-500 is 2.6:1. Each pair below is a
 * background and a foreground designed together, so every avatar clears AA in
 * both themes no matter which one the hash picks. Decoration cannot be allowed
 * to make a name unreadable.
 */
const PALETTE = [
  "bg-primary-subtle text-primary-subtle-fg",
  "bg-accent-subtle text-accent-subtle-fg",
  "bg-info-subtle text-info-subtle-fg",
  "bg-success-subtle text-success-subtle-fg",
];

/** First character of the local part, or a neutral fallback. */
function initial(email: string | null | undefined): string {
  const first = (email ?? "").trim()[0];
  return first ? first.toUpperCase() : "?";
}

export function Avatar({
  email,
  className,
}: {
  email: string | null | undefined;
  className?: string;
}) {
  const seed = (email ?? "").toLowerCase();
  const tone = PALETTE[hash(seed) % PALETTE.length];

  return (
    <span
      // Decorative: the accessible name lives on the button that wraps this,
      // which already says whose account menu it opens.
      aria-hidden="true"
      className={cn(
        "grid size-7 shrink-0 place-items-center rounded-full text-xs font-semibold select-none",
        tone,
        className,
      )}
    >
      {initial(email)}
    </span>
  );
}
