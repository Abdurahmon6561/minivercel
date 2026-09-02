import type { ReactNode } from "react";

/* Small shared primitives. Deliberately not a component library (SPEC.md):
   these exist because the same six Tailwind classes appeared five times, not
   to build an abstraction layer. */

export function Button({
  children,
  variant = "default",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "primary" | "danger";
}) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40";
  const variants = {
    default: "border border-edge-bright bg-panel text-text hover:bg-edge",
    primary: "bg-text text-ink hover:bg-white",
    danger: "border border-failed/40 text-failed hover:bg-failed/10",
  };
  return (
    <button className={`${base} ${variants[variant]} ${className}`} {...props}>
      {children}
    </button>
  );
}

export function Panel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`rounded-lg border border-edge bg-panel ${className}`}>
      {children}
    </div>
  );
}

export function ErrorBanner({
  message,
  onDismiss,
}: {
  message: string;
  onDismiss?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex items-start justify-between gap-4 rounded-md border border-failed/40 bg-failed/10 px-4 py-3 text-sm text-failed"
    >
      <span>{message}</span>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="shrink-0 text-failed/70 hover:text-failed"
          aria-label="Dismiss"
        >
          ✕
        </button>
      )}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 text-sm text-muted" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-edge-bright border-t-accent" />
      {label}
    </div>
  );
}

/** URLs and hashes are monospace (SPEC.md Phase 2 design note). */
export function Mono({
  children,
  className = "",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { children: ReactNode }) {
  return (
    <span className={`font-mono ${className}`} {...props}>
      {children}
    </span>
  );
}
