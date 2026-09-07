import { useCallback, useRef, useState } from "react";
import { AlertCircle, UploadCloud } from "lucide-react";

import { cn } from "../lib/cn";
import { formatBytes } from "../lib/format";

/**
 * Drag-and-drop zip selection.
 *
 * Keyboard-reachable on purpose: a drop zone that is only a drop zone is
 * unusable without a mouse, so the whole thing is a <button> that opens the
 * file picker, with the drag handlers layered on top.
 *
 * It reports a validated file and stops there. What happens next is the
 * caller's decision - the new-project screen stages it behind an Upload button
 * so the name can be set first, while the project page deploys it straight
 * away. Neither behaviour belongs in here.
 */
export function DropZone({
  onFile,
  disabled = false,
  maxBytes,
  className,
}: {
  onFile: (file: File) => void;
  disabled?: boolean;
  maxBytes?: number;
  className?: string;
}) {
  const [dragging, setDragging] = useState(false);
  const [rejected, setRejected] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const accept = useCallback(
    (file: File | undefined) => {
      setRejected(null);
      if (!file) return;

      const looksLikeZip =
        file.name.toLowerCase().endsWith(".zip") ||
        file.type === "application/zip" ||
        file.type === "application/x-zip-compressed";
      if (!looksLikeZip) {
        setRejected(`${file.name} is not a .zip file.`);
        return;
      }
      // The server enforces this too, while streaming. Checking here just saves
      // the user a 50 MB upload that was always going to be refused.
      if (maxBytes && file.size > maxBytes) {
        setRejected(
          `${file.name} is ${formatBytes(file.size)}; the limit is ${formatBytes(maxBytes)}.`,
        );
        return;
      }
      onFile(file);
    },
    [maxBytes, onFile],
  );

  return (
    <div className={className}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => input.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (!disabled) accept(event.dataTransfer.files?.[0]);
        }}
        className={cn(
          "flex w-full flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-14 text-center",
          "transition-colors duration-150",
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
          "disabled:cursor-not-allowed disabled:opacity-50",
          dragging
            ? // --accent-vivid is decoration, and here it is decoration with a
              // label beside it: the words change to "Drop it" at the same
              // moment, so the colour is never the only signal.
              "border-accent-vivid bg-accent-subtle"
            : "border-border-strong bg-surface hover:border-accent-vivid hover:bg-surface-hover",
        )}
      >
        <UploadCloud
          className={cn("size-8", dragging ? "text-accent-vivid" : "text-muted")}
          aria-hidden="true"
        />
        <span className="text-[15px] font-medium text-text">
          {dragging ? "Drop it" : "Drop a .zip here, or click to choose"}
        </span>
        <span className="max-w-sm text-[13px] leading-relaxed text-muted">
          Zip the <em>contents</em> of your site folder, with{" "}
          <span className="font-mono text-xs">index.html</span> at the top level.
        </span>
      </button>

      <input
        ref={input}
        type="file"
        accept=".zip,application/zip"
        className="sr-only"
        onChange={(event) => {
          accept(event.target.files?.[0]);
          event.target.value = "";
        }}
      />

      {rejected && (
        <p
          role="alert"
          className="mt-3 flex items-start gap-2 text-[13px] leading-relaxed text-destructive"
        >
          <AlertCircle className="mt-px size-4 shrink-0" aria-hidden="true" />
          {rejected}
        </p>
      )}
    </div>
  );
}
