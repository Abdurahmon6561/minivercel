import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ErrorBanner, Mono, Spinner } from "../components/Bits";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { api, type GithubRepo, type Me } from "../lib/api";
import { timeAgo } from "../lib/format";

/**
 * Import from GitHub (SPEC.md Phase 3).
 *
 * Two ways in, because the picker cannot always work: a repo list needs a
 * connected token and push access, and someone importing an organisation repo
 * they were just added to may not see it yet. The owner/name field always works.
 */
export function ImportRepo({ me, onImported }: { me: Me | null; onImported: () => void }) {
  const navigate = useNavigate();
  const [repos, setRepos] = useState<GithubRepo[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [manual, setManual] = useState("");
  const [branch, setBranch] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const connected = me?.github.connected ?? false;

  // Warn before they click Import rather than after. GitHub reports a missing
  // scope as 404, so without this the first sign that a sign-in was too narrow
  // is an error claiming the repository does not exist.
  const granted = new Set(
    (me?.github.scopes ?? "").split(",").map((scope) => scope.trim()).filter(Boolean),
  );
  const canHook =
    granted.size === 0 ||
    granted.has("repo") ||
    granted.has("admin:repo_hook") ||
    granted.has("write:repo_hook");

  useEffect(() => {
    if (!connected) return;
    let active = true;
    api
      .listGithubRepos()
      .then((rows) => active && setRepos(rows))
      .catch((cause) => active && setListError(cause.message));
    return () => {
      active = false;
    };
  }, [connected]);

  async function importRepo(full: string, ref?: string) {
    setBusy(full);
    setError(null);
    try {
      const project = await api.importRepo(full, ref);
      onImported();
      navigate(`/projects/${project.slug}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setBusy(null);
    }
  }

  if (!connected) {
    return (
      <Card className="px-6 py-12 text-center">
        <p className="text-base font-semibold text-text">Connect GitHub to continue</p>
        <p className="mx-auto mt-3 max-w-sm text-sm leading-relaxed text-muted">
          Sign out and sign in again to authorise GitHub. The token is what lets
          us read the repository and register the push webhook.
        </p>
      </Card>
    );
  }

  return (
    <div>
      {!canHook && (
        <Card className="mb-6 border-warning/40 bg-warning-subtle px-5 py-4">
          <p className="text-sm text-text">
            Your GitHub sign-in cannot register webhooks.
          </p>
          <p className="mt-2 text-xs leading-relaxed text-muted">
            It was authorised with{" "}
            <Mono className="text-faint">{me?.github.scopes}</Mono>, which does
            not cover repository hooks — so importing will fail, and GitHub
            reports that as “not found” rather than as a permissions problem.
            Sign out and sign in again to re-authorise.
          </p>
        </Card>
      )}

      {error && (
        <div className="mb-6">
          <ErrorBanner message={error} onDismiss={() => setError(null)} />
        </div>
      )}

      <Card className="mb-8 p-5 sm:p-6">
        <div className="mb-5">
          <h2 className="text-base font-semibold text-text">Import a repository</h2>
          <p className="mt-1 text-sm text-muted">Paste a repository path or choose one from your account.</p>
        </div>
      <div className="flex flex-wrap items-end gap-3">
        <label className="min-w-0 flex-1">
          <span className="mb-2 block text-sm text-muted">Repository</span>
          <input
            value={manual}
            onChange={(event) => setManual(event.target.value)}
            placeholder="owner/name"
            disabled={busy !== null}
            className="w-full rounded-md border border-border-strong bg-surface px-4 py-2.5 font-mono text-sm text-text placeholder:text-muted focus:border-primary focus:outline-none disabled:opacity-50"
          />
        </label>
        <label className="w-40">
          <span className="mb-2 block text-sm text-muted">
            Branch <span className="text-faint">(optional)</span>
          </span>
          <input
            value={branch}
            onChange={(event) => setBranch(event.target.value)}
            placeholder="default"
            disabled={busy !== null}
            className="w-full rounded-md border border-border-strong bg-surface px-4 py-2.5 font-mono text-sm text-text placeholder:text-muted focus:border-primary focus:outline-none disabled:opacity-50"
          />
        </label>
        <Button
          variant="primary"
          disabled={!manual.trim() || busy !== null}
          onClick={() => void importRepo(manual.trim(), branch.trim() || undefined)}
        >
          {busy === manual.trim() ? "Importing…" : "Import"}
        </Button>
      </div>
      </Card>

      <h2 className="mb-3 text-sm tracking-wide text-muted uppercase">
        Your repositories
      </h2>

      {listError && <ErrorBanner message={listError} />}
      {repos === null && !listError && <Spinner label="Loading repositories" />}

      {repos !== null && repos.length === 0 && (
        <Card className="px-6 py-12 text-center text-sm text-muted">
          No repositories you can push to.
        </Card>
      )}

      {repos !== null && repos.length > 0 && (
        <Card className="overflow-hidden">
          <ul>
            {repos.map((repo) => (
              <li
                key={repo.full_name}
                className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-edge px-6 py-4 last:border-0"
              >
                <div className="min-w-0 flex-1">
                  <Mono className="text-sm break-all text-text">{repo.full_name}</Mono>
                  {repo.description && (
                    <p className="mt-1 truncate text-xs text-muted">{repo.description}</p>
                  )}
                </div>
                {repo.private && (
                  <span className="rounded-full border border-edge-bright px-2 py-0.5 text-[11px] text-muted">
                    private
                  </span>
                )}
                <span className="w-32 text-right text-xs text-faint">
                  {repo.pushed_at ? timeAgo(repo.pushed_at) : ""}
                </span>
                <Button
                  disabled={busy !== null}
                  onClick={() => void importRepo(repo.full_name, repo.default_branch)}
                >
                  {busy === repo.full_name ? "Importing…" : "Import"}
                </Button>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <p className="mt-8 text-center text-xs leading-relaxed text-muted">
        Importing registers a push webhook and deploys once immediately, so the
        site is live without pushing anything. If the repository needs a build
        step, enable builds on the project page afterwards.
      </p>
    </div>
  );
}
