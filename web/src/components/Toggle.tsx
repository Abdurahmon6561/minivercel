/**
 * A labelled on/off switch.
 *
 * A real <button role="switch"> with aria-checked rather than a styled
 * checkbox: screen readers announce the state, and it is keyboard-operable
 * without extra handlers.
 */
export function Toggle({
  checked,
  onChange,
  label,
  description,
  disabled = false,
  busy = false,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
  busy?: boolean;
}) {
  return (
    <div className="flex items-start justify-between gap-6 py-4">
      <div className="min-w-0">
        <div className="text-sm text-text">{label}</div>
        {description && (
          <p className="mt-1 text-xs leading-relaxed text-muted">{description}</p>
        )}
      </div>

      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled || busy}
        onClick={() => onChange(!checked)}
        className={`relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
          checked ? "bg-ready" : "bg-edge-bright"
        }`}
      >
        <span
          className={`absolute top-1 h-4 w-4 rounded-full bg-ink transition-[left] ${
            checked ? "left-6" : "left-1"
          } ${busy ? "animate-pulse" : ""}`}
        />
      </button>
    </div>
  );
}
