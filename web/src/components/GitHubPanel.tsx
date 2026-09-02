import { useState } from "react";

import { Button, ErrorBanner, Mono, Panel } from "./Bits";
import { Toggle } from "./Toggle";
import { api, type ProjectDetail } from "../lib/api";
import { exactTime, shortSha, timeAgo } from "../lib/format";

/** Colour the delivery outcome the same way deployments are coloured. */
const WEBHOOK_TONE: Record<string, string> = {
  deployed: "text-ready",
  deploying: "text-pending",
  ignored: "text-muted",
  failed: "text-failed",
};

function LastDelivery({ project }: { project: ProjectDetail }) {
  const delivery = project.last_webhook;

  if (!project.webhook_registered) {
    return (
      <p className="text-xs text-faint">
        No webhook registered. Pushes will not reach MiniVercel.
      </p>
    );
  }

  if (!delivery?.at) {
    return (
      <p className="text-xs text-faint">
        Webhook registered. No push received yet.
      </p>
    );
  }

  return (
    <div className="text-xs">
      <span className={WEBHOOK_TONE[delivery.status ?? ""] ?? "text-muted"}>
        {delivery.status}
      </span>
      <span className="text-faint"> · </span>
      <span className="text-muted">{delivery.detail}</span>
      {delivery.sha && (
        <>
          <span className="text-faint"> · </span>
          <Mono className="text-faint" title={delivery.sha}>
            {shortSha(delivery.sha)}
          </Mono>
        </>
      )}
      <span className="text-faint"> · </span>
      <span className="text-faint" title={exactTime(delivery.at)}>
        {timeAgo(delivery.at)}
      </span>
    </div>
  );
}

export function GitHubPanel({
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

  const buildSettingsDirty =
    command !== project.build_command || outputDir !== project.output_dir;

  async function patch(field: string, body: Parameters<typeof api.patchProject>[1]) {
    setBusy(field);
    setError(null);
    try {
      await api.patchProject(project.slug, body);
      await onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      // Put the fields back to what the server actually has.
      setCommand(project.build_command);
      setOutputDir(project.output_dir);
    } finally {
      setBusy(null);
    }
  }

  if (!project.repo_full_name) {
    return null;
  }

  return (
    <Panel className="mb-10 px-6 py-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-edge py-4">
        <a
          href={`https://github.com/${project.repo_full_name}`}
          target="_blank"
          rel="noreferrer noopener"
          className="font-mono text-sm text-text transition-colors hover:text-accent"
        >
          {project.repo_full_name}
        </a>
        <Mono className="rounded-full border border-edge-bright px-2 py-0.5 text-[11px] text-muted">
          {project.repo_branch}
        </Mono>
        <div className="ml-auto">
          <LastDelivery project={project} />
        </div>
      </div>

      {error && (
        <div className="py-4">
          <ErrorBanner message={error} onDismiss={() => setError(null)} />
        </div>
      )}

      <div className="divide-y divide-edge">
        <Toggle
          label="Auto-deploy on push"
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

        <Toggle
          label="Build with GitHub Actions"
          description={
            project.builds_enabled
              ? "A workflow in your repository builds the site and uploads the output. We never run npm."
              : "Deploys the repository as-is. Turn this on for a site that needs a build step; it commits a workflow file and adds a MINIVERCEL_TOKEN secret to your repository."
          }
          checked={project.builds_enabled}
          busy={busy === "builds"}
          disabled={busy !== null}
          onChange={(next) => void patch("builds", { builds_enabled: next })}
        />

        <div className={project.builds_enabled ? "py-4" : "py-4 opacity-40"}>
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-0 flex-1">
              <span className="mb-2 block text-xs text-muted">Build command</span>
              <input
                value={command}
                onChange={(event) => setCommand(event.target.value)}
                disabled={!project.builds_enabled || busy !== null}
                placeholder="npm run build"
                maxLength={200}
                className="w-full rounded-md border border-edge-bright bg-ink px-3 py-2 font-mono text-xs text-text placeholder:text-faint focus:border-accent focus:outline-none disabled:cursor-not-allowed"
              />
            </label>
            <label className="w-40">
              <span className="mb-2 block text-xs text-muted">Output directory</span>
              <input
                value={outputDir}
                onChange={(event) => setOutputDir(event.target.value)}
                disabled={!project.builds_enabled || busy !== null}
                placeholder="dist"
                maxLength={100}
                className="w-full rounded-md border border-edge-bright bg-ink px-3 py-2 font-mono text-xs text-text placeholder:text-faint focus:border-accent focus:outline-none disabled:cursor-not-allowed"
              />
            </label>
            <Button
              disabled={!project.builds_enabled || !buildSettingsDirty || busy !== null}
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
          {project.builds_enabled && buildSettingsDirty && (
            <p className="mt-2 text-xs text-pending">
              Saving rewrites the workflow file in your repository.
            </p>
          )}
        </div>
      </div>
    </Panel>
  );
}
