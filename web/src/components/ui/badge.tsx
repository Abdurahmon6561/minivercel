import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "../../lib/cn";
import type { DeploymentStatus } from "../../lib/api";

const badge = cva(
  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium whitespace-nowrap",
  {
    variants: {
      tone: {
        success: "bg-success-subtle text-success-subtle-fg",
        warning: "bg-warning-subtle text-warning-subtle-fg",
        danger: "bg-destructive-subtle text-destructive-subtle-fg",
        info: "bg-info-subtle text-info-subtle-fg",
        primary: "bg-primary-subtle text-primary-subtle-fg",
        accent: "bg-accent-subtle text-accent-subtle-fg",
        neutral: "bg-surface-hover text-muted",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function Badge({
  className,
  tone,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badge>) {
  return <span className={cn(badge({ tone }), className)} {...props} />;
}

/**
 * Deployment status, coloured and named in one place.
 *
 * Colour is never the only carrier - every badge has its word next to the dot -
 * so this reads the same to someone who cannot separate the green from the
 * amber.
 *
 * `null` is a real state, not an error: a project exists from the moment it is
 * created, which can be before anything has been deployed into it.
 */
const STATUS: Record<
  DeploymentStatus | "none",
  { label: string; tone: VariantProps<typeof badge>["tone"]; pulse?: boolean }
> = {
  ready: { label: "Ready", tone: "success" },
  pending: { label: "Building", tone: "warning", pulse: true },
  failed: { label: "Failed", tone: "danger" },
  none: { label: "No deploys", tone: "neutral" },
};

export function StatusBadge({
  status,
  className,
}: {
  status: DeploymentStatus | null | undefined;
  className?: string;
}) {
  const { label, tone, pulse } = STATUS[status ?? "none"];
  return (
    <Badge tone={tone} className={className}>
      <span
        aria-hidden="true"
        className={cn("size-1.5 rounded-full bg-current", pulse && "animate-pulse")}
      />
      {label}
    </Badge>
  );
}
