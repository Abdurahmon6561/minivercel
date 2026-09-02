import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Button, ErrorBanner, Panel, Spinner } from "../components/Bits";
import { StatusDot } from "../components/StatusDot";
import { api, type Project } from "../lib/api";
import { exactTime, formatBytes, timeAgo } from "../lib/format";

function EmptyState() {
  return (
    <Panel className="px-6 py-20 text-center">
      <p className="text-base text-text">No projects yet.</p>
      <p className="mx-auto mt-3 max-w-sm text-sm leading-relaxed text-muted">
        Zip the contents of a site folder and drop it in. It gets a public URL as
        soon as the upload finishes.
      </p>
      <Link to="/new" className="mt-8 inline-block">
        <Button variant="primary">Deploy your first site</Button>
      </Link>
    </Panel>
  );
}

function ProjectRow({ project }: { project: Project }) {
  const last = project.last_deployment;

  return (
    <li className="border-b border-edge last:border-0">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-6 py-5">
        <div className="min-w-0 flex-1">
          <Link
            to={`/p/${project.slug}`}
            className="text-base text-text transition-colors hover:text-accent"
          >
            {project.name}
          </Link>
          <div className="mt-1.5">
            <a
              href={project.url}
              target="_blank"
              rel="noreferrer noopener"
              className="font-mono text-xs break-all text-muted transition-colors hover:text-accent"
            >
              {project.url}
            </a>
          </div>
        </div>

        <div className="w-28 shrink-0">
          <StatusDot status={last?.status} />
        </div>

        <div
          className="w-36 shrink-0 text-sm text-muted"
          title={exactTime(last?.created_at)}
        >
          {last ? timeAgo(last.created_at) : "—"}
        </div>

        <div className="w-24 shrink-0 text-right font-mono text-xs text-faint">
          {last?.status === "ready" ? formatBytes(last.size_bytes) : ""}
        </div>
      </div>

      {last?.status === "failed" && last.error && (
        <p className="px-6 pb-5 -mt-1 text-sm text-failed/80">{last.error}</p>
      )}
    </li>
  );
}

export function Projects() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api
      .listProjects()
      .then((rows) => active && setProjects(rows))
      .catch((cause) => active && setError(cause.message));
    return () => {
      active = false;
    };
  }, []);

  return (
    <div>
      <div className="mb-10 flex items-center justify-between gap-4">
        <h1 className="text-2xl tracking-tight text-text">Projects</h1>
        <Link to="/new">
          <Button variant="primary">New project</Button>
        </Link>
      </div>

      {error && (
        <div className="mb-6">
          <ErrorBanner message={error} onDismiss={() => setError(null)} />
        </div>
      )}

      {projects === null && !error && <Spinner label="Loading projects" />}

      {projects !== null &&
        (projects.length === 0 ? (
          <EmptyState />
        ) : (
          <Panel>
            <ul>
              {projects.map((project) => (
                <ProjectRow key={project.id} project={project} />
              ))}
            </ul>
          </Panel>
        ))}
    </div>
  );
}
