import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Trash2 } from "lucide-react";

import { Button } from "../ui/button";
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
import { Input } from "../ui/input";
import { Skeleton } from "../ui/skeleton";
import { api, type ProjectDetail } from "../../lib/api";

/**
 * Delete the project.
 *
 * Lives at the bottom of Settings, and only there. It used to sit under every
 * section, which put an irreversible action one stray click away from someone
 * reading their deployment history. Settings is where a destructive project
 * action is looked for.
 *
 * The confirmation names what will actually be destroyed, counted when the
 * dialog opens - the same pattern as deleting an account. A warning that says
 * "and its deployments" is ignorable; one that says "4 deployments and their
 * files" is not.
 */
export function DangerZone({
  project,
  onDeleted,
}: {
  project: ProjectDetail;
  /** Runs after a 204: navigates away and confirms. */
  onDeleted: () => Promise<void> | void;
}) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [envCount, setEnvCount] = useState<number | null>(null);

  const slug = project.slug;
  const confirmed = typed.trim() === slug;
  const deployments = project.deployments.length;

  // The project payload carries its deployments, so only the variables need
  // fetching - and only once someone is actually looking at the warning.
  const loadEnvCount = useCallback(async () => {
    setEnvCount(null);
    try {
      setEnvCount((await api.listEnvVars(slug)).length);
    } catch {
      // Not countable is not a reason to block a delete. Treat it as "none to
      // mention" rather than showing an error nobody can act on.
      setEnvCount(0);
    }
  }, [slug]);

  useEffect(() => {
    if (open) void loadEnvCount();
  }, [open, loadEnvCount]);

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await api.deleteProject(slug);
      await onDeleted();
      // Deliberately no setOpen(false) or setBusy(false): onDeleted navigates
      // away, and resetting first would flash the page underneath.
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setBusy(false);
    }
  }

  const lines: string[] = [];
  if (deployments) {
    lines.push(
      deployments === 1
        ? "1 deployment and its files"
        : `${deployments} deployments and their files`,
    );
  }
  if (envCount) {
    lines.push(
      `${envCount} environment ${envCount === 1 ? "variable" : "variables"} (encrypted at rest)`,
    );
  }
  if (project.repo_full_name && project.webhook_registered) {
    lines.push(`The webhook in ${project.repo_full_name} on GitHub`);
  }

  return (
    <section className="mt-10 rounded-xl border border-destructive/30 bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-4 p-5">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-text">Delete this project</h2>
          <p className="mt-1 max-w-lg text-[13px] leading-relaxed text-muted">
            Removes the project and everything it holds. The public URL stops
            working immediately. This cannot be undone.
          </p>
        </div>

        <Dialog
          open={open}
          onOpenChange={(next) => {
            setOpen(next);
            if (!next) {
              setTyped("");
              setError(null);
            }
          }}
        >
          {/* `subtle` until it is clicked - an outlined red that opens a
              confirmation, not a filled red that acts. */}
          <DialogTrigger asChild>
            <Button variant="subtle" icon={<Trash2 />}>
              Delete project
            </Button>
          </DialogTrigger>

          <DialogContent>
            <DialogHeader>
              <DialogTitle>
                Delete <span className="font-mono text-sm">{slug}</span>?
              </DialogTitle>
              <DialogDescription>
                This removes everything below, permanently.
              </DialogDescription>
            </DialogHeader>

            {envCount === null ? (
              <div className="mt-4 space-y-2">
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            ) : lines.length > 0 ? (
              <ul className="mt-4 space-y-1.5 rounded-md border border-destructive/25 bg-destructive-subtle px-4 py-3 text-[13px] leading-relaxed text-destructive-subtle-fg">
                {lines.map((line) => (
                  <li key={line} className="flex gap-2">
                    <span aria-hidden="true">•</span>
                    <span className="min-w-0">{line}</span>
                  </li>
                ))}
              </ul>
            ) : null}

            <p className="mt-4 text-[13px] leading-relaxed text-muted">
              <span className="font-mono text-xs text-text">
                {project.url.replace(/^https?:\/\//, "")}
              </span>{" "}
              stops working immediately and the name cannot be reclaimed.
            </p>

            <label className="mt-5 block">
              <span className="mb-2 block text-[13px] text-muted">
                Type <span className="font-mono text-xs text-text">{slug}</span> to
                confirm
              </span>
              <Input
                value={typed}
                onChange={(event) => setTyped(event.target.value)}
                autoComplete="off"
                spellCheck={false}
                disabled={busy}
                className="font-mono text-sm"
              />
            </label>

            {error && (
              <p
                role="alert"
                className="mt-4 flex items-start gap-2 rounded-md border border-destructive/35 bg-destructive-subtle px-3 py-2.5 text-[13px] text-destructive-subtle-fg"
              >
                <AlertCircle className="mt-px size-4 shrink-0" aria-hidden="true" />
                {error}
              </p>
            )}

            <DialogFooter>
              <DialogClose asChild>
                <Button variant="ghost" disabled={busy}>
                  Keep it
                </Button>
              </DialogClose>
              <Button
                variant="destructive"
                disabled={!confirmed}
                loading={busy}
                onClick={() => void remove()}
              >
                {busy ? "Deleting…" : "Delete permanently"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </section>
  );
}
