import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Button, ErrorBanner, Panel, Spinner } from "../components/Bits";
import { DeploymentRow } from "../components/DeploymentRow";
import { DropZone } from "../components/DropZone";
import { GitHubPanel } from "../components/GitHubPanel";
import { api, type Me, type ProjectDetail as Detail } from "../lib/api";

export function ProjectDetail({ me, onChanged }: { me: Me | null; onChanged: () => void }) {
  const { slug = "" } = useParams();
  const navigate = useNavigate();

  const [project, setProject] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deploying, setDeploying] = useState(false);

  const load = useCallback(async () => {
    try {
      setProject(await api.getProject(slug));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }, [slug]);

  useEffect(() => {
    void load();
  }, [load]);

  // AUTODEPLOY.md section 8: a push-triggered or import-triggered deploy runs in
  // a background task, so nothing in this tab knows when it finishes. Poll while
  // anything is pending and stop as soon as it settles - watching pending turn
  // to ready is the whole point of auto-deploy being visible.
  const hasPending = project?.deployments.some(
    (deployment) => deployment.status === "pending",
  );

  useEffect(() => {
    if (!hasPending) return;
    const timer = setInterval(() => void load(), 2000);
    return () => clearInterval(timer);
  }, [hasPending, load]);

  async function redeploy(file: File) {
    if (!project) return;
    setError(null);
    setProgress(0);
    try {
      await api.deploy(file, { project_id: project.id }, setProgress);
      setDeploying(false);
      setProgress(null);
      onChanged();
      await load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setProgress(null);
    }
  }

  async function remove() {
    try {
      await api.deleteProject(slug);
      onChanged();
      navigate("/");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setConfirmingDelete(false);
    }
  }

  // Defaults matter only for the first render, before /api/me has answered.
  const retention = {
    keep: me?.usage.retention?.keep_recent_ready ?? 5,
    days: me?.usage.retention?.max_age_days ?? 7,
  };

  if (!project) {
    return (
      <div>
        {error ? <ErrorBanner message={error} /> : <Spinner label="Loading project" />}
        <Link to="/" className="mt-6 inline-block text-sm text-muted hover:text-text">
          ← All projects
        </Link>
      </div>
    );
  }

  return (
    <div>
      <Link to="/" className="mb-8 inline-block text-sm text-muted hover:text-text">
        ← All projects
      </Link>

      <div className="mb-10 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl tracking-tight text-text">{project.name}</h1>
          <a
            href={project.url}
            target="_blank"
            rel="noreferrer noopener"
            className="mt-2 inline-block font-mono text-sm break-all text-muted transition-colors hover:text-accent"
          >
            {project.url}
          </a>
        </div>

        <div className="flex shrink-0 gap-3">
          <Button onClick={() => setDeploying((open) => !open)} disabled={progress !== null}>
            {deploying ? "Cancel" : "Upload new version"}
          </Button>
          <Button variant="danger" onClick={() => setConfirmingDelete(true)}>
            Delete
          </Button>
        </div>
      </div>

      {error && (
        <div className="mb-6">
          <ErrorBanner message={error} onDismiss={() => setError(null)} />
        </div>
      )}

      {confirmingDelete && (
        <Panel className="mb-8 border-failed/40 px-6 py-5">
          <p className="text-sm text-text">
            Delete <span className="font-mono">{project.slug}</span> and every
            deployment it has? The public URL stops working immediately, and the
            stored files are removed. This cannot be undone.
          </p>
          <div className="mt-5 flex gap-3">
            <Button variant="danger" onClick={() => void remove()}>
              Yes, delete it
            </Button>
            <Button onClick={() => setConfirmingDelete(false)}>Keep it</Button>
          </div>
        </Panel>
      )}

      {(deploying || progress !== null) && (
        <div className="mb-10">
          {progress !== null ? (
            <Panel className="px-6 py-12 text-center">
              <div className="mx-auto h-1.5 w-full max-w-sm overflow-hidden rounded-full bg-edge">
                <div
                  className="h-full bg-accent transition-[width] duration-200"
                  style={{ width: `${Math.round(progress * 100)}%` }}
                />
              </div>
              <p className="mt-4 text-sm text-muted">
                {progress < 1
                  ? `Uploading ${Math.round(progress * 100)}%`
                  : "Validating and publishing…"}
              </p>
            </Panel>
          ) : (
            <DropZone onFile={redeploy} maxBytes={me?.usage.max_deployment_bytes} />
          )}
        </div>
      )}

      <GitHubPanel project={project} onChanged={load} />

      <h2 className="mb-4 text-sm tracking-wide text-muted uppercase">
        Deployments
      </h2>

      {project.deployments.length === 0 ? (
        <Panel className="px-6 py-16 text-center text-sm text-muted">
          Nothing deployed yet.
        </Panel>
      ) : (
        <>
          <Panel>
            <ul>
              {project.deployments.map((deployment) => (
                <DeploymentRow
                  key={deployment.id}
                  deployment={deployment}
                  slug={project.slug}
                  // Promoting changes the live pointer, so both the page and
                  // the header (which shows the quota) have to catch up.
                  onPromoted={async () => {
                    await load();
                    onChanged();
                  }}
                />
              ))}
            </ul>
          </Panel>
          <p className="mt-3 text-xs text-faint">
            Every deployment is kept. The live one stays indefinitely, along with
            the {retention.keep} most recent working deployments you could roll
            back to; older ones are removed after {retention.days} days. Failed
            deployments never hold a slot — their files go straight away and the
            record is kept for {retention.days} days so you can read the error.
          </p>
        </>
      )}
    </div>
  );
}
