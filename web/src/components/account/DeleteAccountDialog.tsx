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
import { api } from "../../lib/api";

/**
 * Closing an account.
 *
 * The friction is one thing: typing the email address. That is the pattern
 * GitHub, Vercel and Netlify all use, and it is enough - explicit intent plus
 * destructive language plus real numbers. No countdown, no confirmation email,
 * no "are you really sure" chain; those read as distrust and train people to
 * click through warnings.
 *
 * The numbers have to be REAL, which is the whole reason this component
 * fetches. A warning that says "this will delete your projects" is ignorable;
 * one that names them is not.
 */

export interface AccountSummary {
  projectNames: string[];
  deployments: number;
  envVars: number;
  /** owner/name for every repository we will remove a webhook from. */
  repos: string[];
}

/**
 * Count what deletion will destroy.
 *
 * N+1 by necessity: the project list carries only the most recent deployment,
 * and env vars are per project, so a total needs one detail call and one env
 * call each. Run once when the dialog opens rather than on the button, so the
 * numbers are on screen before anyone decides.
 */
export async function loadAccountSummary(): Promise<AccountSummary> {
  const projects = await api.listProjects();

  const details = await Promise.all(
    projects.map(async (project) => {
      const [detail, envVars] = await Promise.all([
        api.getProject(project.slug).catch(() => null),
        api.listEnvVars(project.slug).catch(() => []),
      ]);
      return {
        name: project.name,
        repo: project.repo_full_name,
        deployments: detail?.deployments.length ?? 0,
        envVars: envVars.length,
      };
    }),
  );

  return {
    projectNames: details.map((d) => d.name),
    deployments: details.reduce((total, d) => total + d.deployments, 0),
    envVars: details.reduce((total, d) => total + d.envVars, 0),
    repos: details.map((d) => d.repo).filter((repo): repo is string => Boolean(repo)),
  };
}

/** A truncated, readable list: "a, b, c and 2 more". */
function nameList(names: string[], limit = 3): string {
  if (names.length <= limit) return names.join(", ");
  return `${names.slice(0, limit).join(", ")} and ${names.length - limit} more`;
}

function Consequences({ summary }: { summary: AccountSummary }) {
  const lines: string[] = [];
  if (summary.projectNames.length) {
    lines.push(
      `${summary.projectNames.length} ${summary.projectNames.length === 1 ? "project" : "projects"} — ${nameList(summary.projectNames)}`,
    );
  }
  if (summary.deployments) {
    lines.push(
      `${summary.deployments} ${summary.deployments === 1 ? "deployment" : "deployments"} and their files`,
    );
  }
  if (summary.envVars) {
    lines.push(
      `${summary.envVars} environment ${summary.envVars === 1 ? "variable" : "variables"}`,
    );
  }
  if (summary.repos.length) {
    lines.push(`The Dropbin webhook in ${nameList(summary.repos)}`);
  }

  // An empty account gets no list at all - four "0 things" lines would be
  // noise, and the sentence below already says what happens.
  if (lines.length === 0) return null;

  return (
    <ul className="mt-4 space-y-1.5 rounded-md border border-destructive/25 bg-destructive-subtle px-4 py-3 text-[13px] leading-relaxed text-destructive-subtle-fg">
      {lines.map((line) => (
        <li key={line} className="flex gap-2">
          <span aria-hidden="true">•</span>
          <span className="min-w-0">{line}</span>
        </li>
      ))}
    </ul>
  );
}

export function DeleteAccountDialog({
  email,
  onDeleted,
}: {
  email: string;
  /** Runs after a 204: clears the session and leaves the dashboard. */
  onDeleted: () => Promise<void> | void;
}) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<AccountSummary | null>(null);

  // Case-insensitive: addresses are not case sensitive in practice, and
  // rejecting a correctly-typed address on capitalisation is a puzzle, not
  // friction.
  const confirmed = typed.trim().toLowerCase() === email.trim().toLowerCase();

  const load = useCallback(async () => {
    setSummary(null);
    try {
      setSummary(await loadAccountSummary());
    } catch {
      // A summary that cannot be counted must not block the deletion. Show the
      // dialog with no list rather than an error the user cannot act on.
      setSummary({ projectNames: [], deployments: 0, envVars: 0, repos: [] });
    }
  }, []);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await api.deleteAccount();
      await onDeleted();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setBusy(false);
    }
  }

  return (
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
      <DialogTrigger asChild>
        <Button variant="destructive" icon={<Trash2 />}>
          Delete account
        </Button>
      </DialogTrigger>

      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Delete your Dropbin account?</DialogTitle>
          <DialogDescription>
            This removes everything below, permanently. Your GitHub account itself
            is not affected — only the webhooks Dropbin added.
          </DialogDescription>
        </DialogHeader>

        {summary === null ? (
          <div className="mt-4 space-y-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        ) : (
          <Consequences summary={summary} />
        )}

        <label className="mt-5 block">
          <span className="mb-2 block text-[13px] text-muted">
            Type <span className="font-mono text-xs text-text">{email}</span> to confirm
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
              Keep my account
            </Button>
          </DialogClose>
          <Button
            variant="destructive"
            disabled={!confirmed || summary === null}
            loading={busy}
            onClick={() => void remove()}
          >
            {busy ? "Deleting…" : "Delete permanently"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
