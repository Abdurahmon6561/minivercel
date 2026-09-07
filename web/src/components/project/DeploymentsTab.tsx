import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, ExternalLink, Rocket, ScrollText, Undo2, Upload } from "lucide-react";

import { Badge, StatusBadge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../ui/dialog";
import { Skeleton } from "../ui/skeleton";
import { useToast } from "../ui/toast";
import { api, type Deployment, type ProjectDetail } from "../../lib/api";
import { exactTime, formatBytes, shortSha, timeAgo } from "../../lib/format";

/**
 * Deployment history.
 *
 * Built from the fields the API actually returns. There is no commit message,
 * author or build duration in `Deployment`, so those columns are absent rather
 * than faked - adding them is a backend change (a migration for finished_at,
 * and persisting the webhook payload we already receive), not a UI one.
 */

function LogDialog({ deployment }: { deployment: Deployment }) {
  const [open, setOpen] = useState(false);
  const [log, setLog] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const pre = useRef<HTMLPreElement>(null);

  // Fetched on first open, not on render: a project page can list fifty
  // deployments and the log is only ever wanted for one of them.
  const load = useCallback(async () => {
    if (log !== null || loading) return;
    setLoading(true);
    setError(null);
    try {
      setLog((await api.getBuildLog(deployment.id)).log);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [deployment.id, log, loading]);

  // The end of a build log is where the error is, so start scrolled to it.
  useEffect(() => {
    if (open && log !== null && pre.current) {
      pre.current.scrollTop = pre.current.scrollHeight;
    }
  }, [open, log]);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) void load();
      }}
    >
      {/* Through DialogTrigger, not a bare onClick: Radix owns the open state,
          so opening always runs onOpenChange - which is where the log is
          fetched. A button that called setOpen directly would open the dialog
          without ever loading anything. */}
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" icon={<ScrollText />}>
          Logs
        </Button>
      </DialogTrigger>

      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Build log</DialogTitle>
          <DialogDescription>
            The last 200 lines of the GitHub Actions run for{" "}
            <span className="font-mono text-xs">{shortSha(deployment.commit_sha) || deployment.id.slice(0, 8)}</span>.
          </DialogDescription>
        </DialogHeader>

        {loading && <Skeleton className="h-64 w-full" />}
        {error && (
          <p className="flex items-start gap-2 rounded-md border border-destructive/35 bg-destructive-subtle px-3 py-2.5 text-[13px] text-destructive-subtle-fg">
            <AlertCircle className="mt-px size-4 shrink-0" aria-hidden="true" />
            {error}
          </p>
        )}
        {log !== null && (
          <pre
            ref={pre}
            className="max-h-[55vh] overflow-auto rounded-md border border-border bg-surface-sunken px-4 py-3 font-mono text-xs leading-relaxed whitespace-pre text-muted"
          >
            {log}
          </pre>
        )}
      </DialogContent>
    </Dialog>
  );
}

function PromoteDialog({
  deployment,
  slug,
  projectUrl,
  onPromoted,
}: {
  deployment: Deployment;
  slug: string;
  projectUrl: string;
  onPromoted: () => Promise<void> | void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { toast } = useToast();

  async function promote() {
    setBusy(true);
    setError(null);
    try {
      await api.promoteDeployment(slug, deployment.id);
      setOpen(false);
      // Rolling back changes what the PROJECT url serves, but the only link on
      // this row is "Preview", which opens the deployment-specific /_d/{id}/
      // address. People clicked it, saw a URL that was not their site, and
      // concluded the rollback had failed. Name the URL that actually changed.
      toast({
        title: "Rolled back",
        description: "Your site now serves this deployment.",
        action: { label: projectUrl.replace(/^https?:\/\//, ""), href: projectUrl },
      });
      await onPromoted();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" icon={<Undo2 />}>
          Roll back
        </Button>
      </DialogTrigger>

      <DialogContent>
        <DialogHeader>
          <DialogTitle>Make this deployment live?</DialogTitle>
          <DialogDescription>
            <span className="font-mono text-xs">{slug}</span> starts serving it
            immediately. Nothing is deleted — this moves a pointer, so the version
            that is live now stays in the list and can be promoted back.
          </DialogDescription>
        </DialogHeader>

        {error && (
          <p className="flex items-start gap-2 rounded-md border border-destructive/35 bg-destructive-subtle px-3 py-2.5 text-[13px] text-destructive-subtle-fg">
            <AlertCircle className="mt-px size-4 shrink-0" aria-hidden="true" />
            {error}
          </p>
        )}

        <DialogFooter>
          <DialogClose asChild>
            <Button variant="ghost" disabled={busy}>
              Cancel
            </Button>
          </DialogClose>
          <Button variant="primary" loading={busy} onClick={() => void promote()}>
            {busy ? "Promoting…" : "Yes, make it live"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Row({
  deployment,
  slug,
  projectUrl,
  onChanged,
}: {
  deployment: Deployment;
  slug: string;
  projectUrl: string;
  onChanged: () => Promise<void> | void;
}) {
  const ready = deployment.status === "ready";
  const canPromote = ready && !deployment.is_live;

  return (
    <>
      <tr className="border-b border-border last:border-0">
        <td className="py-3 pr-4 pl-4 align-middle">
          <div className="flex items-center gap-2">
            <StatusBadge status={deployment.status} />
            {deployment.is_live && <Badge tone="primary">Live</Badge>}
          </div>
        </td>
        <td className="py-3 pr-4 align-middle font-mono text-xs text-muted">
          {deployment.commit_sha ? (
            <span title={deployment.commit_sha}>{shortSha(deployment.commit_sha)}</span>
          ) : (
            // Not a missing commit - there was never going to be one. The icon
            // makes the row read as "this came from a zip" rather than as a
            // project with a broken commit field.
            <span
              className="inline-flex items-center gap-1.5"
              title="Deployed from a zip upload, not a git commit"
            >
              <Upload className="size-3.5 shrink-0" aria-hidden="true" />
              Uploaded ZIP
            </span>
          )}
        </td>
        <td className="py-3 pr-4 text-right align-middle font-mono text-xs text-muted">
          {ready ? formatBytes(deployment.size_bytes) : "—"}
        </td>
        <td className="hidden py-3 pr-4 text-right align-middle font-mono text-xs text-muted sm:table-cell">
          {ready ? deployment.file_count : "—"}
        </td>
        <td
          className="py-3 pr-4 text-right align-middle text-xs whitespace-nowrap text-muted"
          title={exactTime(deployment.created_at)}
        >
          {timeAgo(deployment.created_at)}
        </td>
        <td className="py-2 pr-4 align-middle">
          <div className="flex items-center justify-end gap-1">
            {deployment.preview_url && (
              <a href={deployment.preview_url} target="_blank" rel="noreferrer noopener">
                <Button variant="ghost" size="sm" icon={<ExternalLink />}>
                  Preview
                </Button>
              </a>
            )}
            {deployment.has_build_log && <LogDialog deployment={deployment} />}
            {canPromote && (
              <PromoteDialog
                deployment={deployment}
                slug={slug}
                projectUrl={projectUrl}
                onPromoted={onChanged}
              />
            )}
          </div>
        </td>
      </tr>

      {deployment.error && (
        <tr className="border-b border-border last:border-0">
          <td colSpan={6} className="px-4 pb-3 text-xs leading-relaxed text-destructive">
            {deployment.error}
          </td>
        </tr>
      )}
    </>
  );
}

export function DeploymentsTab({
  project,
  onChanged,
  retention,
}: {
  project: ProjectDetail;
  onChanged: () => Promise<void> | void;
  retention: { keep: number; days: number };
}) {
  if (project.deployments.length === 0) {
    return (
      <Card className="px-6 py-14 text-center">
        <div className="mx-auto grid size-12 place-items-center rounded-xl bg-accent-subtle text-accent-vivid">
          <Rocket className="size-6" aria-hidden="true" />
        </div>
        <h3 className="mt-5 text-base font-semibold text-text">Nothing deployed yet</h3>
        <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-muted">
          Upload a zip with <span className="font-mono text-xs">New deployment</span>, or
          push to the connected branch if this project came from GitHub.
        </p>
      </Card>
    );
  }

  return (
    <>
      <Card className="overflow-hidden">
        {/* The table scrolls inside its own container so the page body never
            scrolls sideways on a narrow screen. */}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-collapse text-left">
            <thead>
              <tr className="border-b border-border">
                {[
                  ["Status", "text-left"],
                  ["Commit", "text-left"],
                  ["Size", "text-right"],
                  ["Files", "text-right hidden sm:table-cell"],
                  ["Deployed", "text-right"],
                  ["", "text-right"],
                ].map(([label, align]) => (
                  <th
                    key={label || "actions"}
                    scope="col"
                    className={`px-4 py-2.5 text-[11px] font-medium tracking-[0.06em] text-muted uppercase ${align} ${label === "Status" ? "" : "pl-0"}`}
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {project.deployments.map((deployment) => (
                <Row
                  key={deployment.id}
                  deployment={deployment}
                  slug={project.slug}
                  projectUrl={project.url}
                  onChanged={onChanged}
                />
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <p className="mt-3 text-xs leading-relaxed text-muted">
        Every deployment is kept. The live one stays indefinitely, along with the{" "}
        {retention.keep} most recent working deployments you could roll back to; older
        ones are removed after {retention.days} days. Failed deployments never hold a
        slot — their files go straight away and the record is kept for {retention.days}{" "}
        days so you can read the error.
      </p>
    </>
  );
}
