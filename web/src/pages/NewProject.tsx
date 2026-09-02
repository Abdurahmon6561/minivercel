import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ErrorBanner, Mono, Panel } from "../components/Bits";
import { DropZone } from "../components/DropZone";
import { api, type Me } from "../lib/api";
import { formatBytes } from "../lib/format";
import { ImportRepo } from "./ImportRepo";

/** Mirrors the server's rule so the error arrives before the upload does. */
function slugify(name: string): string {
  return name
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
}

export function NewProject({ me, onDeployed }: { me: Me | null; onDeployed: () => void }) {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [source, setSource] = useState<"zip" | "github">("zip");
  const slug = slugify(name);
  const slugIsUsable = !name || slug.length >= 3;
  const busy = progress !== null;

  async function upload(selected: File) {
    setFile(selected);
    setError(null);
    setProgress(0);
    try {
      const result = await api.deploy(
        selected,
        name ? { name, slug } : {},
        setProgress,
      );
      onDeployed();
      navigate(`/p/${result.project.slug}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setProgress(null);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-3 text-2xl tracking-tight text-text">New project</h1>
      <p className="mb-8 text-sm leading-relaxed text-muted">
        Static files only. Nothing you give us is ever executed on our server —
        it is validated, stored, and served.
      </p>

      <div
        role="tablist"
        aria-label="Source"
        className="mb-10 inline-flex rounded-md border border-edge bg-panel p-1"
      >
        {(["zip", "github"] as const).map((option) => (
          <button
            key={option}
            role="tab"
            aria-selected={source === option}
            disabled={busy}
            onClick={() => setSource(option)}
            className={`rounded px-4 py-1.5 text-sm transition-colors disabled:opacity-40 ${
              source === option ? "bg-edge text-text" : "text-muted hover:text-text"
            }`}
          >
            {option === "zip" ? "Upload a zip" : "Import from GitHub"}
          </button>
        ))}
      </div>

      {source === "github" && <ImportRepo me={me} onImported={onDeployed} />}

      {source === "zip" && (
        <>
      {error && (
        <div className="mb-6">
          <ErrorBanner message={error} onDismiss={() => setError(null)} />
        </div>
      )}

      <label className="mb-8 block">
        <span className="mb-2 block text-sm text-muted">
          Project name <span className="text-faint">(optional)</span>
        </span>
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          disabled={busy}
          placeholder="My portfolio"
          maxLength={120}
          className="w-full rounded-md border border-edge-bright bg-panel px-4 py-2.5 text-text placeholder:text-faint focus:border-accent focus:outline-none disabled:opacity-50"
        />
        <span className="mt-2 block text-xs text-faint">
          {name ? (
            slugIsUsable ? (
              <>
                URL will be <Mono className="text-muted">/s/{slug}/</Mono>
              </>
            ) : (
              <span className="text-failed">
                Needs at least 3 letters or digits.
              </span>
            )
          ) : (
            "Leave blank and one will be generated."
          )}
        </span>
      </label>

      {busy ? (
        <Panel className="px-6 py-16 text-center">
          <p className="font-mono text-sm break-all text-muted">{file?.name}</p>
          <div className="mx-auto mt-6 h-1.5 w-full max-w-sm overflow-hidden rounded-full bg-edge">
            <div
              className="h-full bg-accent transition-[width] duration-200"
              style={{ width: `${Math.round((progress ?? 0) * 100)}%` }}
            />
          </div>
          <p className="mt-4 text-sm text-muted">
            {progress !== null && progress < 1
              ? `Uploading ${Math.round(progress * 100)}%`
              : "Validating and publishing…"}
          </p>
        </Panel>
      ) : (
        <DropZone
          onFile={upload}
          disabled={!slugIsUsable}
          maxBytes={me?.usage.max_deployment_bytes}
        />
      )}

      {me && (
        <p className="mt-8 text-center text-xs text-faint">
          Up to {formatBytes(me.usage.max_deployment_bytes)} and{" "}
          {me.usage.max_files_per_deployment} files per deployment ·{" "}
          {formatBytes(me.usage.bytes_limit - me.usage.bytes_used)} of quota left
        </p>
      )}
        </>
      )}
    </div>
  );
}
