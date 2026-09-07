import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AlertCircle, FileArchive, Upload, X } from "lucide-react";

import { DropZone } from "../components/DropZone";
import { ImportRepo } from "./ImportRepo";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { GithubMark } from "../components/ui/github-mark";
import { Input } from "../components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { api, type Me } from "../lib/api";
import { formatBytes } from "../lib/format";
import { siteDomain } from "../lib/host";
import { MIN_SLUG_LENGTH, isUsableSlug, slugify } from "../lib/slug";

const SOURCES = [
  { value: "zip", label: "Upload zip", Icon: FileArchive },
  { value: "github", label: "Import from GitHub", Icon: GithubMark },
] as const;

type Source = (typeof SOURCES)[number]["value"];
const SOURCE_NAMES: readonly string[] = SOURCES.map((s) => s.value);

/**
 * The URL a slug will produce, or the slug alone where there is no domain to
 * show (localhost has no wildcard DNS, and inventing one would be a lie).
 */
export function SlugPreview({ slug }: { slug: string }) {
  const domain = siteDomain();
  return (
    <span className="font-mono text-xs break-all text-muted">
      {domain ? `${slug}.${domain}` : slug}
    </span>
  );
}

function UploadZip({ me, onDeployed }: { me: Me | null; onDeployed: () => void }) {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const slug = slugify(name);
  const slugOk = !name || isUsableSlug(slug);
  const busy = progress !== null;

  async function upload() {
    if (!file) return;
    setError(null);
    setProgress(0);
    try {
      const result = await api.deploy(file, name ? { name, slug } : {}, setProgress);
      onDeployed();
      navigate(`/projects/${result.project.slug}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setProgress(null);
    }
  }

  if (busy) {
    return (
      <Card className="px-6 py-16 text-center">
        <p className="font-mono text-sm break-all text-muted">{file?.name}</p>
        <div className="mx-auto mt-6 h-1.5 w-full max-w-sm overflow-hidden rounded-full bg-surface-hover">
          <div
            className="h-full bg-primary transition-[width] duration-200"
            style={{ width: `${Math.round((progress ?? 0) * 100)}%` }}
          />
        </div>
        <p className="mt-4 text-sm text-muted">
          {progress !== null && progress < 1
            ? `Uploading ${Math.round(progress * 100)}%`
            : "Validating and publishing…"}
        </p>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      {error && (
        <div
          role="alert"
          className="flex items-start justify-between gap-4 rounded-md border border-destructive/35 bg-destructive-subtle px-4 py-3 text-[13px] leading-relaxed text-destructive-subtle-fg"
        >
          <span className="flex items-start gap-2">
            <AlertCircle className="mt-px size-4 shrink-0" aria-hidden="true" />
            {error}
          </span>
          <button onClick={() => setError(null)} aria-label="Dismiss" className="shrink-0">
            <X className="size-3.5" aria-hidden="true" />
          </button>
        </div>
      )}

      {/* Selecting a file stages it rather than deploying it, so the name can
          still be set. The old screen uploaded the moment a file was dropped,
          which made the name field unreachable in practice. */}
      {file ? (
        <Card className="flex flex-wrap items-center gap-x-4 gap-y-3 p-4">
          <div className="grid size-10 shrink-0 place-items-center rounded-lg bg-accent-subtle text-accent-vivid">
            <FileArchive className="size-5" aria-hidden="true" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate font-mono text-sm text-text" title={file.name}>
              {file.name}
            </p>
            <p className="mt-0.5 text-xs text-muted">{formatBytes(file.size)}</p>
          </div>
          <Button variant="ghost" size="sm" icon={<X />} onClick={() => setFile(null)}>
            Remove
          </Button>
        </Card>
      ) : (
        <DropZone onFile={setFile} maxBytes={me?.usage.max_deployment_bytes} />
      )}

      <label className="block">
        <span className="mb-1.5 block text-[13px] text-muted">
          Project name <span className="text-muted/70">(optional)</span>
        </span>
        <Input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="My portfolio"
          maxLength={120}
          aria-invalid={!slugOk || undefined}
          aria-describedby="slug-preview"
        />
        <span id="slug-preview" className="mt-2 block text-xs text-muted">
          {!name ? (
            "Leave blank and one will be generated for you."
          ) : slugOk ? (
            <>
              URL will be <SlugPreview slug={slug} /> — if that name is taken or
              reserved, we pick another.
            </>
          ) : (
            <span className="text-destructive">
              Needs at least {MIN_SLUG_LENGTH} letters or digits.
            </span>
          )}
        </span>
      </label>

      <div>
        <Button
          variant="primary"
          icon={<Upload />}
          disabled={!file || !slugOk}
          onClick={() => void upload()}
        >
          Upload and deploy
        </Button>
      </div>

      {me && (
        <p className="text-xs leading-relaxed text-muted">
          Up to {formatBytes(me.usage.max_deployment_bytes)} and{" "}
          {me.usage.max_files_per_deployment} files per deployment ·{" "}
          {formatBytes(me.usage.bytes_limit - me.usage.bytes_used)} of quota left
        </p>
      )}
    </div>
  );
}

export function NewProject({ me, onDeployed }: { me: Me | null; onDeployed: () => void }) {
  const [params, setParams] = useSearchParams();

  // The tab lives in the URL, the same way the project page's does, so the
  // projects empty state can link straight to the one it means and a shared
  // link opens where the sender was.
  const requested = params.get("from");
  const source: Source = SOURCE_NAMES.includes(requested ?? "")
    ? (requested as Source)
    : "zip";

  return (
    <div className="mx-auto max-w-3xl">
      <div className="border-b border-border pb-7">
        <p className="text-xs font-semibold tracking-[0.13em] text-accent uppercase">Create</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-0.035em] text-text">Deploy a new project</h1>
      <p className="mt-3 max-w-xl text-sm leading-relaxed text-muted">
        Static files only. Nothing you upload is ever executed on our servers — it
        is validated, stored, and served.
      </p>
      </div>

      <Tabs
        value={source}
        onValueChange={(next) => {
          const updated = new URLSearchParams(params);
          if (next === "zip") updated.delete("from");
          else updated.set("from", next);
          setParams(updated, { replace: true });
        }}
        className="mt-8 rounded-xl border border-border bg-surface p-4 shadow-sm sm:p-6"
      >
        {/* Horizontal here: two peers at the top of a form, not a sidebar. The
            list defaults to a row and only becomes a column at md, so this
            override keeps it a row at every width. */}
        <TabsList
          aria-label="Source"
          className="mb-6 gap-1 border-b border-border pb-0 md:flex-row"
        >
          {SOURCES.map(({ value, label, Icon }) => (
            <TabsTrigger
              key={value}
              value={value}
              className="rounded-none border-b-2 border-l-0 border-transparent data-[state=active]:border-b-primary data-[state=active]:bg-transparent data-[state=active]:text-text"
            >
              <Icon aria-hidden="true" />
              {label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="zip">
          <UploadZip me={me} onDeployed={onDeployed} />
        </TabsContent>

        <TabsContent value="github">
          {/* Still the pre-redesign importer; rebuilt in 7b. */}
          <ImportRepo me={me} onImported={onDeployed} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
