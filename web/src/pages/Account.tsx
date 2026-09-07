import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertCircle, LogOut, RotateCcw, Unlink } from "lucide-react";

import { useAuth } from "../auth/AuthProvider";
import { DeleteAccountDialog, loadAccountSummary } from "../components/account/DeleteAccountDialog";
import type { AccountSummary } from "../components/account/DeleteAccountDialog";
import { Avatar } from "../components/ui/avatar";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../components/ui/dialog";
import { GithubMark } from "../components/ui/github-mark";
import { Skeleton } from "../components/ui/skeleton";
import { useToast } from "../components/ui/toast";
import { api, type Me } from "../lib/api";
import { exactTime, formatBytes, timeAgo } from "../lib/format";
import { isDashboardHost, siteDomain } from "../lib/host";
import { supabase } from "../lib/supabase";

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h2 className="text-sm font-semibold text-text">{title}</h2>
      {description && (
        <p className="mt-1 max-w-xl text-[13px] leading-relaxed text-muted">
          {description}
        </p>
      )}
      <div className="mt-3">{children}</div>
    </section>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-1 px-5 py-3.5">
      <dt className="w-32 shrink-0 text-[13px] text-muted">{label}</dt>
      <dd className="min-w-0 text-sm text-text">{children}</dd>
    </div>
  );
}

function DisconnectGithubDialog({ login, onDone }: { login: string; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function disconnect() {
    setBusy(true);
    setError(null);
    try {
      await api.forgetGithubToken();
      setOpen(false);
      onDone();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="subtle" size="sm" icon={<Unlink />}>
          Disconnect
        </Button>
      </DialogTrigger>

      <DialogContent>
        <DialogHeader>
          <DialogTitle>Disconnect GitHub?</DialogTitle>
          <DialogDescription>
            Auto-deploy stops for every project imported from a repository, and
            importing new ones will need you to connect again. Sites already
            deployed keep serving — nothing is taken down.
          </DialogDescription>
        </DialogHeader>

        <p className="mt-4 rounded-md border border-border bg-surface-sunken px-3.5 py-3 text-[13px] leading-relaxed text-muted">
          This removes the token Dropbin stored for{" "}
          <span className="font-mono text-xs text-text">{login}</span>. It does not
          revoke the authorisation on GitHub&rsquo;s side — do that from{" "}
          <a
            href="https://github.com/settings/applications"
            target="_blank"
            rel="noreferrer noopener"
            className="text-primary underline-offset-4 hover:underline"
          >
            your GitHub settings
          </a>{" "}
          if you want it gone there too.
        </p>

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
              Cancel
            </Button>
          </DialogClose>
          <Button variant="destructive" loading={busy} onClick={() => void disconnect()}>
            {busy ? "Disconnecting…" : "Disconnect GitHub"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function Account({ me, onChanged }: { me: Me | null; onChanged: () => void }) {
  const { session, signIn, signOut } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();

  const email = me?.email ?? session?.user?.email ?? "";
  const joined = session?.user?.created_at ?? null;

  // Shared with the delete dialog: the page shows the counts, and the dialog
  // shows what they mean. One fetch either way.
  const [summary, setSummary] = useState<AccountSummary | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const generation = useRef(0);

  const loadSummary = useCallback(async () => {
    const mine = ++generation.current;
    setSummaryError(null);
    setSummary(null);
    try {
      const next = await loadAccountSummary();
      if (mine === generation.current) setSummary(next);
    } catch (cause) {
      if (mine === generation.current) {
        setSummaryError(cause instanceof Error ? cause.message : String(cause));
      }
    }
  }, []);

  useEffect(() => {
    void loadSummary();
    return () => {
      generation.current++;
    };
  }, [loadSummary]);

  async function afterDelete() {
    // Order matters: drop the local session before navigating, or the app
    // re-renders as a signed-in user whose account no longer exists and every
    // request 401s.
    await supabase.auth.signOut().catch(() => {});
    toast({ title: "Your Dropbin account has been deleted." });

    // The landing, not /login - someone who just left should not be asked to
    // come back in. But the landing is served from the APEX host, and "/" on
    // app.{domain} is a redirect that sends a signed-out visitor straight to
    // /login. Going there by router would land on exactly the page this is
    // supposed to avoid, so on the dashboard host this is a real navigation
    // to the other origin. `?deleted` survives it; a toast would not.
    const domain = siteDomain();
    if (isDashboardHost() && domain) {
      window.location.assign(`${window.location.protocol}//${domain}/?deleted=1`);
      return;
    }
    navigate("/?deleted=1");
  }

  const used = me?.usage.bytes_used ?? 0;
  const limit = me?.usage.bytes_limit ?? 0;
  const fraction = limit ? Math.min(used / limit, 1) : 0;
  const tone =
    fraction > 0.9 ? "bg-destructive" : fraction > 0.7 ? "bg-warning" : "bg-primary";

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight text-text">Account</h1>

      <div className="mt-8 flex flex-col gap-9">
        {/* -- Profile ------------------------------------------------------ */}
        <Section title="Profile">
          <Card>
            <div className="flex flex-wrap items-center gap-4 px-5 py-5">
              <Avatar email={email} className="size-14 text-lg" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-text">{email}</p>
                {joined && (
                  <p className="mt-0.5 text-xs text-muted" title={exactTime(joined)}>
                    Joined {timeAgo(joined)}
                  </p>
                )}
              </div>
              <Button variant="secondary" size="sm" icon={<LogOut />} onClick={() => void signOut()}>
                Sign out
              </Button>
            </div>

            <div className="divide-y divide-border border-t border-border">
              <Row label="Email">
                <span className="break-all">{email}</span>
              </Row>
              {me?.github.connected && (
                <Row label="GitHub">
                  <span className="font-mono text-xs text-muted">
                    {me.github.login ?? "connected"}
                  </span>
                </Row>
              )}
            </div>
          </Card>
        </Section>

        {/* -- Usage -------------------------------------------------------- */}
        <Section title="Usage">
          <Card className="px-5 py-5">
            {me ? (
              <>
                <p className="text-2xl font-semibold tracking-tight text-text">
                  <span className="font-mono">{formatBytes(used)}</span>
                  <span className="text-base font-normal text-muted">
                    {" "}
                    of {formatBytes(limit)}
                  </span>
                </p>
                <div
                  className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-surface-hover"
                  role="progressbar"
                  aria-label="Storage used"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(fraction * 100)}
                >
                  <div
                    className={`h-full ${tone} transition-[width] duration-300`}
                    style={{ width: `${Math.max(fraction * 100, used > 0 ? 2 : 0)}%` }}
                  />
                </div>
                <p className="mt-3 text-[13px] leading-relaxed text-muted">
                  Storage counts all files across all your projects and deployments.
                </p>

                <dl className="mt-5 flex flex-wrap gap-x-10 gap-y-3 border-t border-border pt-4">
                  <div>
                    <dt className="text-xs text-muted">Projects</dt>
                    <dd className="mt-0.5 font-mono text-lg text-text">
                      {summary ? summary.projectNames.length : <Skeleton className="h-5 w-8" />}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Deployments</dt>
                    <dd className="mt-0.5 font-mono text-lg text-text">
                      {summary ? summary.deployments : <Skeleton className="h-5 w-8" />}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted">Environment variables</dt>
                    <dd className="mt-0.5 font-mono text-lg text-text">
                      {summary ? summary.envVars : <Skeleton className="h-5 w-8" />}
                    </dd>
                  </div>
                </dl>

                {summaryError && (
                  <p className="mt-4 flex flex-wrap items-center gap-3 text-[13px] text-muted">
                    <span className="flex items-start gap-2">
                      <AlertCircle className="mt-px size-4 shrink-0 text-destructive" aria-hidden="true" />
                      Could not count your projects.
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={<RotateCcw />}
                      onClick={() => void loadSummary()}
                    >
                      Try again
                    </Button>
                  </p>
                )}
              </>
            ) : (
              <>
                <Skeleton className="h-8 w-48" />
                <Skeleton className="mt-3 h-1.5 w-full" />
                <Skeleton className="mt-4 h-4 w-3/4" />
              </>
            )}
          </Card>
        </Section>

        {/* -- GitHub ------------------------------------------------------- */}
        <Section title="GitHub">
          <Card className="flex flex-wrap items-center gap-4 px-5 py-4">
            <GithubMark className="size-5 shrink-0 text-muted" />
            {me?.github.connected ? (
              <>
                <p className="min-w-0 flex-1 text-sm text-text">
                  Connected as{" "}
                  <span className="font-mono text-xs">{me.github.login ?? "github"}</span>
                </p>
                <DisconnectGithubDialog
                  login={me.github.login ?? "your account"}
                  onDone={onChanged}
                />
              </>
            ) : (
              <>
                <p className="min-w-0 flex-1 text-sm text-muted">
                  Not connected. Connect to import repositories and deploy on push.
                </p>
                <Button variant="primary" size="sm" onClick={() => void signIn()}>
                  Connect GitHub
                </Button>
              </>
            )}
          </Card>
        </Section>

        {/* -- Danger zone -------------------------------------------------- */}
        <section className="rounded-xl border border-destructive/30 bg-surface">
          <div className="flex flex-wrap items-start justify-between gap-4 p-5">
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-text">Delete account</h2>
              <p className="mt-1 max-w-lg text-[13px] leading-relaxed text-muted">
                Permanently delete your Dropbin account and everything in it — projects,
                deployments, stored files and environment variables — and remove the
                webhooks Dropbin added to your repositories. Your GitHub account itself is
                not affected. This cannot be undone.
              </p>
            </div>
            {email && <DeleteAccountDialog email={email} onDeleted={afterDelete} />}
          </div>
        </section>
      </div>
    </div>
  );
}
