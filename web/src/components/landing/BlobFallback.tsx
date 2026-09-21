/**
 * What renders instead of `LiquidBlob` on a coarse pointer, a narrow
 * viewport, under reduced motion, or for the instant before the lazy
 * three.js chunk resolves (`Suspense`'s fallback). A static gradient orb
 * built from the same tokens the rest of the page's decorative washes use
 * (`--primary`, `--warm-orange`) - never a blank box, and never a colour
 * the WebGL version doesn't already share.
 */
export function BlobFallback() {
  return (
    <div
      aria-hidden="true"
      className="size-full rounded-full bg-linear-to-br from-primary/70 via-primary/40 to-warm-orange/25 blur-2xl"
    />
  );
}
