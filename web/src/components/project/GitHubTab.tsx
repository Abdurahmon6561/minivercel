import { useState } from "react";
import { AlertCircle, ExternalLink, GitBranch } from "lucide-react";

import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
import { GithubMark } from "../ui/github-mark";
import { Input } from "../ui/input";
import { Switch } from "../ui/switch";
import { api, type ProjectDetail } from "../../lib/api";
import { exactTime, shortSha, timeAgo } from "../../lib/format";

/**
 * The GitHub connection: what it is wired to, and the two independent switches
 * that decide what a push actually does.
 *
 * There is no Disconnect here on purpose. Unlinking a repository has real
 * open questions - what happens to the deployments it produced, whether the
 * workflow file we committed should be removed from the user's repo - and a
 * button that guesses at those is worse than no button. Turning both switches
 * off already stops everything happening.
 */

/** Colour the delivery outcome the same way a deployment is coloured. */
const WEBHOOK_TONE: Record<string, string> = {
  deployed: "text-success",
  deploying: "text-warning",
  ignored: "text-muted",
  failed: "text-destructive",
};

function LastDelivery({ project }: { project: ProjectDetail }) {
  const delivery = project.last_webhook;

  if (!project.webhook_registered) {
    return (
      <p className="text-xs text-muted">
        No webhook registered — pushes will not reach Dropbin.
      </p>
    );
  }
  if (!delivery?.at) {
    return <p className="text-xs text-muted">Webhook registered. No push received yet.</p>;
  }

  return (
    <p className="flex flex-wrap items-center gap-x-1.5 text-xs text-muted">
      <span className={WEBHOOK_TONE[delivery.status ?? ""] ?? "text-muted"}>
        {delivery.status}
      </span>
      {delivery.detail && <span>· {delivery.detail}</span>}
      {delivery.sha && (
        <span className="font-mono" title={delivery.sha}>
          · {shortSha(delivery.sha)}
        </span>
      )}
      <span title={exactTime(delivery.at)}>· {timeAgo(delivery.at)}</span>
    </p>
  );
}

function SwitchRow({
  title,
  description,
  checked,
  busy,
  disabled,
  onChange,
}: {
  title: string;
  description: string;
  checked: boolean;
  busy: boolean;
  disabled: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-6 px-5 py-4">
      <div className="min-w-0">
        <h3 className="text-sm font-medium text-text">{title}</h3>
        <p className="mt-1 max-w-xl text-[13px] leading-relaxed text-muted">{description}</p>
      </div>
      <Switch
        label={title}
        checked={checked}
        busy={busy}
        disabled={disabled}
        onCheckedChange={onChange}
      />
    </div>
  );
}

export function GitHubTab({
  project,
  onChanged,
}: {
  project: ProjectDetail;
  onChanged: () => void | Promise<void>;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [command, setCommand] = useState(project.build_command);
  const [outputDir, setOutputDir] = useState(project.output_dir);

  const dirty =
    command !== project.build_command || outputDir !== project.output_dir;

  async function patch(field: string, body: Parameters<typeof api.patchProject>[1]) {
    setBusy(field);
    setError(null);
    try {
      await api.patchProject(project.slug, body);
      await onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      // Put the fields back to what the server actually has, so the form never
      // shows a value that was rejected.
      setCommand(project.build_command);
      setOutputDir(project.output_dir);
    } finally {
      setBusy(null);
    }
  }

  if (!project.repo_full_name) {
    return (
      <Card className="px-6 py-14 text-center">
        <div className="mx-auto grid size-12 place-items-center rounded-xl bg-accent-subtle text-accent-vivid">
          <GithubMark className="size-6" />
        </div>
        <h3 className="mt-5 text-base font-semibold text-text">Not connected to GitHub</h3>
        <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-muted">
          This project was created from a zip upload. Importing a repository creates a
          new project rather than attaching one to this.
        </p>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {error && (
        <div
          role="alert"
          className="flex items-start gap-2.5 rounded-md border border-destructive/35 bg-destructive-subtle px-4 py-3 text-[13px] leading-relaxed text-destructive-subtle-fg"
        >
          <AlertCircle className="mt-px size-4 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </div>
      )}

      <Card className="flex flex-wrap items-center gap-x-3 gap-y-2 px-5 py-4">
        <GithubMark className="size-4 shrink-0 text-muted" />
        <a
          href={`https://github.com/${project.repo_full_name}`}
          target="_blank"
          rel="noreferrer noopener"
          className="inline-flex items-center gap-1.5 font-mono text-sm text-text transition-colors hover:text-accent"
        >
          {project.repo_full_name}
          <ExternalLink className="size-3" aria-hidden="true" />
        </a>
        <Badge tone="accent" className="font-mono">
          <GitBranch className="size-3" aria-hidden="true" />
          {project.repo_branch}
        </Badge>
        <div className="ml-auto">
          <LastDelivery project={project} />
        </div>
      </Card>

      <Card className="divide-y divide-border">
        <SwitchRow
          title="Auto-deploy on push"
          description={
            project.auto_deploy_enabled
              ? `Every push to ${project.repo_branch} deploys.`
              : "Pushes are received and recorded, but nothing deploys. The webhook stays registered, so turning this back on takes effect immediately."
          }
          checked={project.auto_deploy_enabled}
          busy={busy === "auto"}
          disabled={busy !== null}
          onChange={(next) => void patch("auto", { auto_deploy_enabled: next })}
        />

        <SwitchRow
          title="Build with GitHub Actions"
          description={
            project.builds_enabled
              ? "A workflow in your repository builds the site and uploads the output. We never run your code on our servers."
              : "Deploys the repository as-is. Turn this on for a site that needs a build step; it commits a workflow file and adds a MINIVERCEL_TOKEN secret to your repository."
          }
          checked={project.builds_enabled}
          busy={busy === "builds"}
          disabled={busy !== null}
          onChange={(next) => void patch("builds", { builds_enabled: next })}
        />

        {/* Dimmed rather than hidden when builds are off: the settings are
            still the ones that will be used, and hiding them makes the toggle
            feel like it did something unrelated. */}
        <div className={project.builds_enabled ? "px-5 py-4" : "px-5 py-4 opacity-50"}>
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-0 flex-1">
              <span className="mb-1.5 block text-[13px] text-muted">Build command</span>
              <Input
                value={command}
                onChange={(event) => setCommand(event.target.value)}
                disabled={!project.builds_enabled || busy !== null}
                placeholder="npm run build"
                maxLength={200}
                className="font-mono text-xs"
              />
            </label>
            <label className="w-40">
              <span className="mb-1.5 block text-[13px] text-muted">Output directory</span>
              <Input
                value={outputDir}
                onChange={(event) => setOutputDir(event.target.value)}
                disabled={!project.builds_enabled || busy !== null}
                placeholder="dist"
                maxLength={100}
                className="font-mono text-xs"
              />
            </label>
            <Button
              variant="secondary"
              loading={busy === "settings"}
              disabled={!project.builds_enabled || !dirty || busy !== null}
              onClick={() =>
                void patch("settings", {
                  builds_enabled: true,
                  build_command: command,
                  output_dir: outputDir,
                })
              }
            >
              {busy === "settings" ? "Saving…" : "Save"}
            </Button>
          </div>

          {project.builds_enabled && dirty && (
            <p className="mt-2.5 text-xs text-warning">
              Saving rewrites the workflow file in your repository.
            </p>
          )}
        </div>
      </Card>
    </div>
  );
}
