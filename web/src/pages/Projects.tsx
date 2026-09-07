import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, ExternalLink, FolderPlus, Plus, RotateCcw, Upload } from "lucide-react";

import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { GithubMark } from "../components/ui/github-mark";
import { Skeleton } from "../components/ui/skeleton";
import { StatusBadge } from "../components/ui/badge";
import { api, type Project } from "../lib/api";
import { exactTime, formatBytes, timeAgo } from "../lib/format";
import { slugGradient } from "../lib/gradient";

function PageHeader() {
  return (
    <div className="mb-10 flex flex-wrap items-end justify-between gap-5 border-b border-border pb-7">
      <div>
        <p className="text-xs font-semibold tracking-[0.13em] text-accent uppercase">Your workspace</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-0.035em] text-text">Projects</h1>
        <p className="mt-2 text-sm text-muted">Every site you have deployed, in one place.</p>
      </div>
      <Link to="/projects/new">
        <Button variant="primary" icon={<Plus />}>
          New project
        </Button>
      </Link>
    </div>
  );
}

function ProjectCard({ project }: { project: Project }) {
  const last = project.last_deployment;
  const failed = last?.status === "failed";

  return (
    <Card interactive className="group flex flex-col overflow-hidden transition-transform hover:-translate-y-0.5">
      {/* Placeholder art until real screenshots exist. Purely decorative, so it
          is hidden from assistive tech - the project name is right below it. */}
      <div
        aria-hidden="true"
        className="h-24 shrink-0 opacity-90 transition-transform duration-300 group-hover:scale-[1.02]"
        style={{ background: slugGradient(project.slug) }}
      />

      <div className="flex min-w-0 flex-1 flex-col p-5">
        {/*
          The card is one link target with a second link inside it, which cannot
          be nested anchors. So the name owns the card via a stretched
          pseudo-element, and the URL sits above it on the z-axis - both stay
          real links, keyboard reachable and independently focusable.
        */}
        <h2 className="min-w-0 text-[15px] font-semibold text-text">
          <Link
            to={`/projects/${project.slug}`}
            className="after:absolute after:inset-0 after:content-[''] hover:text-primary"
          >
            {project.name}
          </Link>
        </h2>

        <a
          href={project.url}
          target="_blank"
          rel="noreferrer noopener"
          onClick={(event) => event.stopPropagation()}
          className="relative z-10 mt-1.5 inline-flex w-fit max-w-full items-center gap-1.5 font-mono text-xs break-all text-muted transition-colors hover:text-accent"
        >
          <span className="truncate">{project.url.replace(/^https?:\/\//, "")}</span>
          <ExternalLink className="size-3 shrink-0" aria-hidden="true" />
        </a>

        <div className="mt-5 flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-border pt-3.5">
          <StatusBadge status={last?.status} />
          <span className="text-xs text-muted" title={exactTime(last?.created_at)}>
            {last ? timeAgo(last.created_at) : "never deployed"}
          </span>
          {last?.status === "ready" && (
            <span className="ml-auto font-mono text-xs text-muted">
              {formatBytes(last.size_bytes)}
            </span>
          )}
        </div>

        {failed && last.error && (
          <p className="mt-3 line-clamp-2 text-xs leading-relaxed text-destructive">
            {last.error}
          </p>
        )}
      </div>
    </Card>
  );
}

function LoadingGrid() {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label="Loading projects"
      className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
    >
      {/* Six, because that is what a full first screen looks like - a single
          placeholder would understate the layout it is standing in for. */}
      {Array.from({ length: 6 }, (_, index) => (
        <Card key={index} className="overflow-hidden">
          <Skeleton className="h-20 rounded-none" />
          <div className="p-4">
            <Skeleton className="h-4 w-2/5" />
            <Skeleton className="mt-2.5 h-3 w-4/5" />
            <div className="mt-5 flex items-center gap-3 pt-3">
              <Skeleton className="h-5 w-20 rounded-full" />
              <Skeleton className="h-3 w-24" />
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <Card className="px-6 py-16 text-center">
      <div className="mx-auto grid size-12 place-items-center rounded-xl bg-accent-subtle text-accent-vivid">
        <FolderPlus className="size-6" aria-hidden="true" />
      </div>
      <h2 className="mt-5 text-base font-semibold text-text">No projects yet</h2>
      <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-muted">
        Start by uploading a zip or connecting a GitHub repo. Either way you get a
        public URL as soon as it finishes.
      </p>
      <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
        <Link to="/projects/new?from=zip">
          <Button variant="primary" icon={<Upload />}>
            Upload a zip
          </Button>
        </Link>
        <Link to="/projects/new?from=github">
          <Button variant="secondary" icon={<GithubMark className="size-4" />}>
            Import from GitHub
          </Button>
        </Link>
      </div>
    </Card>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Card className="px-6 py-14 text-center">
      <div className="mx-auto grid size-12 place-items-center rounded-xl bg-destructive-subtle text-destructive">
        <AlertCircle className="size-6" aria-hidden="true" />
      </div>
      <h2 className="mt-5 text-base font-semibold text-text">
        Could not load your projects
      </h2>
      {/* The API's own words. It already distinguishes an expired session from a
          cold start, and rewriting that here would lose the distinction. */}
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted">{message}</p>
      <Button variant="secondary" className="mt-7" icon={<RotateCcw />} onClick={onRetry}>
        Try again
      </Button>
    </Card>
  );
}

export function Projects() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // One fetch path for both the first load and every retry. The generation
  // counter is what makes retrying safe: a slow first request that fails after
  // the user has already retried must not overwrite the newer result, and an
  // unmount must not set state at all.
  const generation = useRef(0);

  const load = useCallback(async () => {
    const mine = ++generation.current;
    setError(null);
    setProjects(null);
    try {
      const rows = await api.listProjects();
      if (mine === generation.current) setProjects(rows);
    } catch (cause) {
      if (mine === generation.current) {
        setError(cause instanceof Error ? cause.message : String(cause));
      }
    }
  }, []);

  useEffect(() => {
    void load();
    return () => {
      // Invalidate anything still in flight.
      generation.current++;
    };
  }, [load]);

  return (
    <div>
      <PageHeader />

      {error ? (
        <ErrorState message={error} onRetry={() => void load()} />
      ) : projects === null ? (
        <LoadingGrid />
      ) : projects.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      )}
    </div>
  );
}
