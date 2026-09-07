import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { AlertCircle, ArrowLeft, RotateCcw, Upload, X } from "lucide-react";

import { DangerZone } from "../components/project/DangerZone";
import { DeploymentsTab } from "../components/project/DeploymentsTab";
import { EnvironmentTab } from "../components/project/EnvironmentTab";
import { GitHubTab } from "../components/project/GitHubTab";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import { DropZone } from "../components/DropZone";
import { api, type Me, type ProjectDetail as Detail } from "../lib/api";
import { exactTime, timeAgo } from "../lib/format";
import { useProjectChrome } from "../lib/project-chrome";

/**
 * The panel headings. The labels and icons for the nav itself live in
 * components/Layout.tsx, which owns the sidebar - this page only needs to know
 * which section it is showing and what to call it.
 */
const SECTION_TITLES = {
  deployments: "Deployments",
  github: "GitHub",
  environment: "Environment",
  settings: "Settings",
} as const;

type TabName = keyof typeof SECTION_TITLES;
const TAB_NAMES: readonly string[] = Object.keys(SECTION_TITLES);

/** Mirrors the panel, not the page: the sidebar is already on screen. */
function DetailSkeleton() {
  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-9 w-40" />
      </div>
      <Card className="mt-6 overflow-hidden">
        {Array.from({ length: 5 }, (_, index) => (
          <div
            key={index}
            className="flex items-center gap-4 border-b border-border p-4 last:border-0"
          >
            <Skeleton className="h-5 w-20 rounded-full" />
            <Skeleton className="h-3 w-16" />
            <Skeleton className="ml-auto h-3 w-24" />
          </div>
        ))}
      </Card>
    </div>
  );
}

function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div>
      <Link
        to="/projects"
        className="inline-flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-text"
      >
        <ArrowLeft className="size-3.5" aria-hidden="true" />
        Projects
      </Link>
      <Card className="mt-8 px-6 py-14 text-center">
        <div className="mx-auto grid size-12 place-items-center rounded-xl bg-destructive-subtle text-destructive">
          <AlertCircle className="size-6" aria-hidden="true" />
        </div>
        <h2 className="mt-5 text-base font-semibold text-text">Could not load this project</h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted">{message}</p>
        <Button variant="secondary" className="mt-7" icon={<RotateCcw />} onClick={onRetry}>
          Try again
        </Button>
      </Card>
    </div>
  );
}

function SettingsTab({ project }: { project: Detail }) {
  const rows: [string, React.ReactNode][] = [
    ["Name", project.name],
    ["Slug", <span className="font-mono text-xs">{project.slug}</span>],
    ["Project ID", <span className="font-mono text-xs break-all">{project.id}</span>],
    [
      "Created",
      <span title={exactTime(project.created_at)}>{timeAgo(project.created_at)}</span>,
    ],
  ];

  return (
    <Card className="divide-y divide-border">
      {rows.map(([label, value]) => (
        <div key={label} className="flex flex-wrap items-center gap-x-6 gap-y-1 px-5 py-3.5">
          <dt className="w-28 shrink-0 text-[13px] text-muted">{label}</dt>
          <dd className="min-w-0 text-sm text-text">{value}</dd>
        </div>
      ))}
      <p className="px-5 py-3.5 text-xs leading-relaxed text-muted">
        Renaming a project is not supported: the slug is the hostname its site is
        served from, so changing it would break every link to the deployed site.
      </p>
    </Card>
  );
}

export function ProjectDetail({ me, onChanged }: { me: Me | null; onChanged: () => void }) {
  const { slug = "" } = useParams();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { setProject: publishToSidebar } = useProjectChrome();

  const [project, setProject] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);

  // Tab lives in the URL so a tab is linkable and the back button steps
  // through them rather than leaving the page.
  const requested = params.get("tab");
  const tab: TabName = TAB_NAMES.includes(requested ?? "")
    ? (requested as TabName)
    : "deployments";

  const generation = useRef(0);

  const load = useCallback(
    async ({ quiet = false } = {}) => {
      const mine = ++generation.current;
      if (!quiet) {
        setError(null);
        setProject(null);
      }
      try {
        const next = await api.getProject(slug);
        if (mine === generation.current) setProject(next);
      } catch (cause) {
        // A failed poll must not blank a page that is already rendered.
        if (mine === generation.current && !quiet) {
          setError(cause instanceof Error ? cause.message : String(cause));
        }
      }
    },
    [slug],
  );

  useEffect(() => {
    void load();
    return () => {
      generation.current++;
    };
  }, [load]);

  // The sidebar renders this project's name and URL. Clearing on unmount
  // matters: without it the nav would still describe this project after
  // navigating back to the list.
  useEffect(() => {
    publishToSidebar(project);
    return () => publishToSidebar(null);
  }, [project, publishToSidebar]);

  // AUTODEPLOY.md section 8: a push-triggered or import-triggered deploy runs in
  // a background task, so nothing in this tab knows when it finishes. Poll while
  // anything is pending and stop as soon as it settles.
  const hasPending = project?.deployments.some((d) => d.status === "pending");
  useEffect(() => {
    if (!hasPending) return;
    const timer = setInterval(() => void load({ quiet: true }), 2000);
    return () => clearInterval(timer);
  }, [hasPending, load]);

  async function upload(file: File) {
    if (!project) return;
    setError(null);
    setProgress(0);
    try {
      await api.deploy(file, { project_id: project.id }, setProgress);
      setUploading(false);
      setProgress(null);
      onChanged();
      await load({ quiet: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setProgress(null);
    }
  }

  async function remove() {
    await api.deleteProject(slug);
    onChanged();
    navigate("/projects");
  }

  const retention = {
    keep: me?.usage.retention?.keep_recent_ready ?? 5,
    days: me?.usage.retention?.max_age_days ?? 7,
  };

  if (error && !project) return <LoadError message={error} onRetry={() => void load()} />;
  if (!project) return <DetailSkeleton />;

  return (
    <div>
      {/* The project's name, URL and section nav are in the sidebar now, so
          this column is only the panel. What used to be a second <aside> here
          is what made the page read as two applications side by side. */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="min-w-0 truncate text-xl font-semibold tracking-tight text-text">
          {SECTION_TITLES[tab]}
        </h1>
        <Button
          variant="primary"
          icon={uploading ? <X /> : <Upload />}
          disabled={progress !== null}
          onClick={() => setUploading((open) => !open)}
        >
          {uploading ? "Cancel" : "New deployment"}
        </Button>
      </div>

      {error && (
        <div
          role="alert"
          className="mt-6 flex items-start justify-between gap-4 rounded-md border border-destructive/35 bg-destructive-subtle px-4 py-3 text-[13px] text-destructive-subtle-fg"
        >
          <span className="flex items-start gap-2">
            <AlertCircle className="mt-px size-4 shrink-0" aria-hidden="true" />
            {error}
          </span>
          <button
            onClick={() => setError(null)}
            aria-label="Dismiss"
            className="shrink-0 rounded-sm p-0.5 hover:bg-destructive/10"
          >
            <X className="size-3.5" aria-hidden="true" />
          </button>
        </div>
      )}

      {(uploading || progress !== null) && (
        <div className="mt-6">
          {progress !== null ? (
            <Card className="px-6 py-12 text-center">
              <div className="mx-auto h-1.5 w-full max-w-sm overflow-hidden rounded-full bg-surface-hover">
                <div
                  className="h-full bg-primary transition-[width] duration-200"
                  style={{ width: `${Math.round(progress * 100)}%` }}
                />
              </div>
              <p className="mt-4 text-sm text-muted">
                {progress < 1
                  ? `Uploading ${Math.round(progress * 100)}%`
                  : "Validating and publishing…"}
              </p>
            </Card>
          ) : (
            <DropZone onFile={upload} maxBytes={me?.usage.max_deployment_bytes} />
          )}
        </div>
      )}

      <div className="mt-6">
        {tab === "deployments" && (
          <DeploymentsTab
            project={project}
            retention={retention}
            onChanged={async () => {
              await load({ quiet: true });
              onChanged();
            }}
          />
        )}
        {tab === "github" && (
          <GitHubTab project={project} onChanged={() => load({ quiet: true })} />
        )}
        {/* Mounted only while its section is open, so the variable list is
            fetched when someone looks at it rather than on every page load. */}
        {tab === "environment" && <EnvironmentTab slug={project.slug} />}
        {tab === "settings" && <SettingsTab project={project} />}
      </div>

      <DangerZone
        slug={project.slug}
        deploymentCount={project.deployments.length}
        onDelete={remove}
      />
    </div>
  );
}
