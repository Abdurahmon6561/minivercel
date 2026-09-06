import { useCallback, useEffect, useRef, useState } from "react";

import { Button, Mono } from "./Bits";
import { StatusDot } from "./StatusDot";
import { api, type Deployment } from "../lib/api";
import { exactTime, formatBytes, shortSha, timeAgo } from "../lib/format";

/**
 * One row of the deployment history: status, size, and the two things Phase 5
 * added — a way to look at a past deployment, and a way to make it live.
 *
 * "Preview" and "Promote to live" are deliberately separate. Promoting is
 * instant and reversible (it moves a pointer; no files are touched either way),
 * but it changes what the public URL serves, so it gets a confirmation step and
 * the preview link that makes that confirmation informed.
 *
 * The live deployment shows the LIVE badge in place of the promote button:
 * there is nothing to promote it to, and an enabled-looking control that does
 * nothing is worse than no control.
 */

function BuildLog({ deploymentId }: { deploymentId: string }) {
  const [open, setOpen] = useState(false);
  const [log, setLog] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const preRef = useRef<HTMLPreElement>(null);

  // Fetched on first open, not on render: a project page can list fifty
  // deployments and the error is only ever wanted for one of them.
  const load = useCallback(async () => {
    if (log !== null || loading) return;
    setLoading(true);
    try {
      setLog((await api.getBuildLog(deploymentId)).log);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [deploymentId, log, loading]);

  // The end of a build log is where the error is, so start scrolled to it.
  useEffect(() => {
    if (open && log !== null && preRef.current) {
      preRef.current.scrollTop = preRef.current.scrollHeight;
    }
  }, [open, log]);

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => {
          setOpen((was) => !was);
          void load();
        }}
        aria-expanded={open}
        className="text-xs text-muted underline-offset-2 transition-colors hover:text-text hover:underline"
      >
        {open ? "Hide build log" : "Show build log"}
      </button>

      {open && (
        <div className="mt-2">
          {loading && <p className="text-xs text-muted">Loading log…</p>}
          {error && <p className="text-xs text-failed">{error}</p>}
          {log !== null && (
            <pre
              ref={preRef}
              className="max-h-80 overflow-auto rounded-md border border-edge bg-ink px-4 py-3 font-mono text-xs leading-relaxed whitespace-pre text-muted"
            >
              {log}
            </pre>
          )}
          {log !== null && (
            <p className="mt-1.5 text-[11px] text-faint">
              Last 200 lines of the GitHub Actions run.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function DeploymentRow({
  deployment,
  slug,
  onPromoted,
}: {
  deployment: Deployment;
  slug: string;
  onPromoted: () => void | Promise<void>;
}) {
  const [confirming, setConfirming] = useState(false);
  const [promoting, setPromoting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function promote() {
    setPromoting(true);
    setError(null);
    try {
      await api.promoteDeployment(slug, deployment.id);
      setConfirming(false);
      await onPromoted();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setPromoting(false);
    }
  }

  const canPromote = deployment.status === "ready" && !deployment.is_live;

  return (
    <li className="border-b border-edge px-6 py-4 last:border-0">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <div className="w-28 shrink-0">
          <StatusDot status={deployment.status} />
        </div>

        <Mono className="min-w-0 flex-1 truncate text-xs text-faint">
          {deployment.id}
        </Mono>

        {deployment.is_live && (
          <span className="rounded-full border border-ready/40 px-2 py-0.5 text-[11px] tracking-wide text-ready uppercase">
            Live
          </span>
        )}

        {deployment.commit_sha && (
          <Mono className="text-xs text-faint" title={deployment.commit_sha}>
            {shortSha(deployment.commit_sha)}
          </Mono>
        )}

        <span className="w-20 shrink-0 text-right font-mono text-xs text-faint">
          {deployment.status === "ready" ? formatBytes(deployment.size_bytes) : ""}
        </span>
        <span className="w-16 shrink-0 text-right font-mono text-xs text-faint">
          {deployment.status === "ready" ? `${deployment.file_count} files` : ""}
        </span>
        <span
          className="w-32 shrink-0 text-right text-sm text-muted"
          title={exactTime(deployment.created_at)}
        >
          {timeAgo(deployment.created_at)}
        </span>
      </div>

      {(deployment.preview_url || canPromote) && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          {deployment.preview_url && (
            <a
              href={deployment.preview_url}
              target="_blank"
              rel="noreferrer noopener"
              className="text-xs text-muted underline-offset-2 transition-colors hover:text-primary hover:underline"
            >
              Preview
            </a>
          )}
          {canPromote && !confirming && (
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="text-xs text-muted underline-offset-2 transition-colors hover:text-primary hover:underline"
            >
              Promote to live
            </button>
          )}
        </div>
      )}

      {confirming && (
        <div className="mt-3 rounded-md border border-edge-bright bg-ink px-4 py-3">
          <p className="text-sm text-text">
            Make this deployment live? <Mono>{slug}</Mono> will start serving it
            immediately.
          </p>
          <p className="mt-1.5 text-xs text-muted">
            Nothing is deleted — the current version stays in the list and can be
            promoted back.
          </p>
          <div className="mt-4 flex gap-3">
            <Button variant="primary" onClick={() => void promote()} disabled={promoting}>
              {promoting ? "Promoting…" : "Yes, make it live"}
            </Button>
            <Button onClick={() => setConfirming(false)} disabled={promoting}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {error && <p className="mt-2 text-sm text-failed">{error}</p>}
      {deployment.error && (
        <p className="mt-2 text-sm text-failed/80">{deployment.error}</p>
      )}
      {deployment.has_build_log && <BuildLog deploymentId={deployment.id} />}
    </li>
  );
}
