import { useCallback, useRef, useState } from "react";

import { formatBytes } from "../lib/format";

/**
 * Drag-and-drop zip upload (SPEC.md Phase 2 `/new`).
 *
 * Keyboard-reachable on purpose: a drop zone that is only a drop zone is
 * unusable without a mouse, so the whole thing is a <button> that opens the
 * file picker, with the drag handlers layered on top.
 */
export function DropZone({
  onFile,
  disabled = false,
  maxBytes,
}: {
  onFile: (file: File) => void;
  disabled?: boolean;
  maxBytes?: number;
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
    <div>
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
        className={`flex w-full flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed px-6 py-16 text-center transition-colors ${
          dragging
            ? "border-accent bg-accent/5"
            : "border-edge-bright bg-panel hover:border-faint"
        } disabled:cursor-not-allowed disabled:opacity-50`}
      >
        <span className="text-3xl leading-none text-faint" aria-hidden="true">
          ↑
        </span>
        <span className="text-base text-text">
          {dragging ? "Drop it" : "Drop a .zip here, or click to choose"}
        </span>
        <span className="max-w-sm text-sm text-muted">
          Zip the <em>contents</em> of your site folder, with{" "}
          <span className="font-mono">index.html</span> at the top level.
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
        <p role="alert" className="mt-3 text-sm text-failed">
          {rejected}
        </p>
      )}
    </div>
  );
}
