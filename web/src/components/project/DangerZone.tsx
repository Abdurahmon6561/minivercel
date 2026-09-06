import { useState } from "react";
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

/**
 * Delete the project.
 *
 * A section under the tab content rather than a tab of its own: a destructive
 * action should be somewhere you can see it is there, not somewhere you have to
 * go looking for. It is below the fold of every tab, which is far enough.
 *
 * The confirmation asks for the slug to be typed. That is deliberate friction
 * for the one action here that cannot be undone - and it now takes the
 * project's encrypted environment variables with it, since project_env_vars
 * cascades on delete.
 */
export function DangerZone({
  slug,
  deploymentCount,
  envVarCount,
  onDelete,
}: {
  slug: string;
  deploymentCount: number;
  envVarCount?: number;
  onDelete: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const confirmed = typed.trim() === slug;

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await onDelete();
      // Deliberately no setOpen(false): onDelete navigates away, and closing
      // first would flash the page underneath.
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setBusy(false);
    }
  }

  return (
    <section className="mt-12 rounded-xl border border-destructive/30 bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-4 p-5">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-text">Delete this project</h2>
          <p className="mt-1 max-w-lg text-[13px] leading-relaxed text-muted">
            Removes the project, its {deploymentCount}{" "}
            {deploymentCount === 1 ? "deployment" : "deployments"}
            {envVarCount ? ` and ${envVarCount} environment ${envVarCount === 1 ? "variable" : "variables"}` : ""}, and
            the stored files. The public URL stops working immediately. This cannot be
            undone.
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
              <DialogTitle>Delete {slug}?</DialogTitle>
              <DialogDescription>
                Everything this project holds goes with it — every deployment, the
                stored files
                {envVarCount ? ", and its environment variables" : ""}. The public URL
                stops resolving immediately and cannot be reclaimed.
              </DialogDescription>
            </DialogHeader>

            <label className="block">
              <span className="mb-2 block text-[13px] text-muted">
                Type <span className="font-mono text-xs text-text">{slug}</span> to
                confirm
              </span>
              <input
                value={typed}
                onChange={(event) => setTyped(event.target.value)}
                autoComplete="off"
                spellCheck={false}
                disabled={busy}
                className="w-full rounded-md border border-border-strong bg-bg px-3 py-2 font-mono text-sm text-text placeholder:text-muted/60 focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-50"
              />
            </label>

            {error && (
              <p className="mt-4 flex items-start gap-2 rounded-md border border-destructive/35 bg-destructive-subtle px-3 py-2.5 text-[13px] text-destructive-subtle-fg">
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
