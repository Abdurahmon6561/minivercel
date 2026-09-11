/**
 * The hero's centerpiece: a code window orbited by two rings, with two status
 * chips reporting a deployment. Replaces the unDraw server-cluster illustration
 * with something that looks like the product rather than a generic dev-tool
 * stock drawing - the brief was "deploy static sites in seconds", so the
 * picture is now a deploy happening.
 *
 * Built from tokens only, same rule as everywhere else: `--primary` and
 * `--accent` for the two orbiting nodes (the app's real action/emphasis pair,
 * not an invented purple), `--success` for the "Ready" state the dashboard
 * itself uses, and `--border` / `--surface` for the device chrome. Nothing
 * here is a hex value, so it repaints correctly across both themes and the
 * light/dark boundary the rest of the page respects.
 *
 * Every absolutely-positioned child stays within the 0-100% box of its parent
 * (no negative insets, no translate past a child's own size) - a floating chip
 * or orbit dot that pokes outside its container is exactly how the comparison
 * table caused a 215px sideways scroll at 400px wide (see the browser-test
 * notes on that section). Percent sizing on the rings means they scale down
 * safely with the illustration itself rather than needing their own
 * breakpoints.
 *
 * The spin and float animations are plain CSS (`animate-[spin_..._linear_
 * infinite]` and the `animate-float` utility registered in index.css) rather
 * than JS - index.css already clamps every animation-duration to 0.01ms under
 * `prefers-reduced-motion: reduce`, so reduced motion is handled globally and
 * does not need to be re-solved here.
 */
export function DeployOrbitIllustration({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`relative mx-auto grid aspect-square w-full max-w-[26rem] place-items-center ${className}`}
    >
      {/* Orbit rings. Percent-sized against the square wrapper so they never
          exceed its bounds, and centered by translating half of their OWN
          size, not the parent's. */}
      <div className="absolute size-[94%] rounded-full border border-border" />
      <div className="absolute size-[94%] animate-[spin_20s_linear_infinite] rounded-full">
        <span
          className="absolute top-0 left-1/2 size-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary"
          style={{ boxShadow: "0 0 16px var(--primary)" }}
        />
      </div>

      <div className="absolute size-[68%] rounded-full border border-border" />
      <div className="absolute size-[68%] animate-[spin_13s_linear_infinite_reverse] rounded-full">
        <span
          className="absolute top-[64%] right-0 size-1.5 translate-x-1/2 rounded-full bg-accent"
          style={{ boxShadow: "0 0 14px var(--accent)" }}
        />
      </div>

      <div className="absolute size-[44%] animate-[spin_9s_linear_infinite] rounded-full border border-border/70" />

      {/* The device: a code window, same traffic-light language as
          SitePreview's browser frame so the two illustrations read as one
          family. */}
      <div
        className="relative w-[58%] max-w-64 overflow-hidden rounded-2xl border border-border bg-surface"
        style={{
          boxShadow:
            "var(--shadow-lg), 0 0 70px color-mix(in srgb, var(--primary) 16%, transparent)",
        }}
      >
        <div className="flex items-center gap-1.5 border-b border-border bg-surface-sunken px-3.5 py-2.5">
          <span className="size-2 rounded-full bg-destructive/70" />
          <span className="size-2 rounded-full bg-warning/70" />
          <span className="size-2 rounded-full bg-success/70" />
        </div>
        <div className="space-y-2.5 p-4">
          <div className="h-1.5 w-[42%] rounded-full bg-primary/55" />
          <div className="h-1.5 w-[64%] rounded-full bg-accent/45" />
          <div className="h-1.5 w-full rounded-full bg-border-strong" />
          <div className="h-1.5 w-[76%] rounded-full bg-border-strong" />
          <div className="h-1.5 w-[30%] rounded-full bg-primary/55" />
        </div>
      </div>

      {/* Status chips. Real shapes from the product - a commit SHA and a
          Ready state - not invented labels. Positioned with plain spacing
          tokens (top-4/left-0/etc.) rather than percentages so they cannot
          drift past the wrapper's edge at any size. */}
      <div
        className="animate-float absolute top-4 right-0 rounded-lg border border-border bg-surface/90 px-3 py-2 shadow-md backdrop-blur-sm"
        style={{ animationDelay: "-1.2s" }}
      >
        <p className="text-[9px] font-medium tracking-[0.12em] text-muted uppercase">Deployment</p>
        <p className="mt-1 flex items-center gap-1.5 text-xs font-semibold text-success">
          <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
          Ready
        </p>
      </div>

      <div
        className="animate-float absolute bottom-6 left-0 rounded-lg border border-border bg-surface/90 px-3 py-2 shadow-md backdrop-blur-sm"
        style={{ animationDelay: "-3.4s" }}
      >
        <p className="text-[9px] font-medium tracking-[0.12em] text-muted uppercase">Commit</p>
        <p className="mt-1 font-mono text-xs text-text">7d36a4e</p>
      </div>
    </div>
  );
}
