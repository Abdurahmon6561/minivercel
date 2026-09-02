import type { DeploymentStatus } from "../lib/api";

/** Green ready / amber pending / red failed (SPEC.md Phase 2). */
const STYLES: Record<DeploymentStatus | "none", { dot: string; label: string }> = {
  ready: { dot: "bg-ready shadow-[0_0_8px_var(--color-ready)]", label: "Ready" },
  pending: { dot: "bg-pending animate-pulse", label: "Building" },
  failed: { dot: "bg-failed", label: "Failed" },
  none: { dot: "bg-faint", label: "No deploys" },
};

export function StatusDot({
  status,
  showLabel = true,
}: {
  status: DeploymentStatus | null | undefined;
  showLabel?: boolean;
}) {
  const style = STYLES[status ?? "none"];
  return (
    <span className="inline-flex items-center gap-2">
      <span
        className={`h-2 w-2 shrink-0 rounded-full ${style.dot}`}
        // The dot alone is colour-only information; give it a text equivalent
        // even when the visible label is suppressed.
        role="img"
        aria-label={style.label}
      />
      {showLabel && <span className="text-sm text-muted">{style.label}</span>}
    </span>
  );
}
