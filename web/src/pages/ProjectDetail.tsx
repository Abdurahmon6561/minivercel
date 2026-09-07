import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  AlertCircle,
  ArrowLeft,
  Check,
  Cog,
  Copy,
  ExternalLink,
  GitBranch,
  RotateCcw,
  Rocket,
  Upload,
  Variable,
  X,
} from "lucide-react";

import { DangerZone } from "../components/project/DangerZone";
import { DeploymentsTab } from "../components/project/DeploymentsTab";
import { EnvironmentTab } from "../components/project/EnvironmentTab";
import { GitHubTab } from "../components/project/GitHubTab";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { DropZone } from "../components/DropZone";
import { api, type Me, type ProjectDetail as Detail } from "../lib/api";
import { exactTime, timeAgo } from "../lib/format";

const TABS = [
  { value: "deployments", label: "Deployments", Icon: Rocket },
  { value: "github", label: "GitHub", Icon: GitBranch },
  { value: "environment", label: "Environment", Icon: Variable },
  { value: "settings", label: "Settings", Icon: Cog },
] as const;

type TabName = (typeof TABS)[number]["value"];
const TAB_NAMES: readonly string[] = TABS.map((t) => t.value);

function CopyUrlButton({ url }: { url: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(url);
          setCopied(true);
          setTimeout(() => setCopied(false), 1600);
        } catch {
          // Clipboard access can be refused (insecure context, permissions).
          // The URL is selectable text right beside this, so there is nothing
          // to recover from - just do not claim success.
        }
      }}
      className="rounded-sm p-1 text-muted transition-colors hover:bg-surface-hover hover:text-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      aria-label={copied ? "Copied" : "Copy URL"}
    >
      {copied ? (
        <Check className="size-3.5 text-success" aria-hidden="true" />
      ) : (
        <Copy className="size-3.5" aria-hidden="true" />
      )}
    </button>
  );
}

/** Mirrors the real two-column layout, so nothing jumps when data arrives. */
function DetailSkeleton() {
  return (
    <div>
      <Skeleton className="h-4 w-24" />
      <div className="mt-6 flex flex-col gap-6 md:flex-row md:gap-8">
        <div className="w-full shrink-0 md:w-[220px]">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="mt-2 h-3 w-48" />
          <div className="my-4 h-px bg-border" />
          <div className="flex gap-1 md:flex-col">
            {Array.from({ length: 4 }, (_, index) => (
              <Skeleton key={index} className="h-9 w-full md:w-full" />
            ))}
          </div>
          <div className="mt-5 flex flex-col gap-2">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        </div>

        <div className="min-w-0 flex-1">
          <Card className="overflow-hidden">
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
      </div>
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
  const [params, setParams] = useSearchParams();

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
      <Link
        to="/projects"
        className="inline-flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-text"
      >
        <ArrowLeft className="size-3.5" aria-hidden="true" />
        Projects
      </Link>

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

      {/* Radix's Root is the flex container itself, because the list and the
          panels have to stay inside one Tabs context while sitting in two
          different columns. */}
      <Tabs
        orientation="vertical"
        value={tab}
        onValueChange={(next) => {
          // `replace` so four sidebar clicks do not become four back-button
          // presses between here and the project list.
          const updated = new URLSearchParams(params);
          if (next === "deployments") updated.delete("tab");
          else updated.set("tab", next);
          setParams(updated, { replace: true });
        }}
        className="mt-6 flex flex-col gap-6 md:flex-row md:gap-8"
      >
        <aside className="w-full shrink-0 md:w-[220px]">
          <div className="md:sticky md:top-6">
            <h1
              className="truncate text-base font-semibold tracking-tight text-text"
              title={project.name}
            >
              {project.name}
            </h1>

            <div className="mt-1 flex items-center gap-1">
              <a
                href={project.url}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex min-w-0 items-center gap-1 font-mono text-xs text-muted transition-colors hover:text-accent"
                title={project.url}
              >
                <span className="truncate">{project.url.replace(/^https?:\/\//, "")}</span>
                <ExternalLink className="size-3 shrink-0" aria-hidden="true" />
              </a>
              <CopyUrlButton url={project.url} />
            </div>

            <div className="my-4 h-px bg-border" />

            <TabsList aria-label="Project sections">
              {TABS.map(({ value, label, Icon }) => (
                <TabsTrigger key={value} value={value}>
                  <Icon aria-hidden="true" />
                  {label}
                </TabsTrigger>
              ))}
            </TabsList>

            <div className="mt-5 flex flex-col gap-2">
              <Button
                variant="primary"
                block
                icon={uploading ? <X /> : <Upload />}
                disabled={progress !== null}
                onClick={() => setUploading((open) => !open)}
              >
                {uploading ? "Cancel" : "New deployment"}
              </Button>
              <a href={project.url} target="_blank" rel="noreferrer noopener">
                <Button variant="secondary" block icon={<ExternalLink />}>
                  Open site
                </Button>
              </a>
            </div>
          </div>
        </aside>

        {/* min-w-0 so a wide deployments table scrolls inside its own container
            instead of stretching this column past the viewport. */}
        <div className="min-w-0 flex-1">
          {(uploading || progress !== null) && (
            <div className="mb-6">
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

          <TabsContent value="deployments">
            <DeploymentsTab
              project={project}
              retention={retention}
              onChanged={async () => {
                await load({ quiet: true });
                onChanged();
              }}
            />
          </TabsContent>

          <TabsContent value="github">
            <GitHubTab project={project} onChanged={() => load({ quiet: true })} />
          </TabsContent>

          <TabsContent value="environment">
            {/* Mounted only while the tab is open, so the list is fetched when
                it is first looked at rather than on every project page load. */}
            <EnvironmentTab slug={project.slug} />
          </TabsContent>

          <TabsContent value="settings">
            <SettingsTab project={project} />
          </TabsContent>

          <DangerZone
            slug={project.slug}
            deploymentCount={project.deployments.length}
            onDelete={remove}
          />
        </div>
      </Tabs>
    </div>
  );
}
