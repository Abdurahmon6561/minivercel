import { useState } from "react";
import { AlertCircle, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { Button } from "../components/ui/button";
import { GithubMark } from "../components/ui/github-mark";
import { Input } from "../components/ui/input";
import { ThemeToggle } from "../components/ui/theme-toggle";
import { Wordmark } from "../components/ui/wordmark";

/**
 * The only unauthenticated page inside the dashboard.
 *
 * Same visual language as the landing - one header bar, the same wordmark, the
 * same card treatment - because arriving here from the landing's CTA should
 * feel like the next step rather than a different product.
 *
 * Two ways in, not one: GitHub used to be the only account there was, which
 * meant creating a Dropbin account and authorising a GitHub app were the same
 * click. They are not the same decision - someone who only wants to upload a
 * zip has no reason to grant repository access first - so email+password is
 * now a first-class way to get an account (via /register), and GitHub is
 * something you connect later, from the new-project page, only when you
 * actually want to import a repo.
 */
export function Login() {
  const { signIn, signInWithPassword, error } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [signing, setSigning] = useState(false);

  async function submit() {
    if (!email.trim() || !password || signing) return;
    setSigning(true);
    await signInWithPassword(email.trim(), password);
    setSigning(false);
  }

  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden bg-bg">
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-5xl items-center gap-4 px-6 py-4">
          {/* Not a link. On the dashboard host "/" resolves straight back to
              /login for a signed-out visitor, so it would look broken. */}
          <Wordmark />
          <div className="ml-auto">
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="relative flex flex-1 items-center justify-center px-6 py-16">
        <div aria-hidden="true" className="absolute bottom-[-18rem] left-[-12rem] size-[34rem] rounded-full bg-primary/10 blur-3xl" />
        <div className="relative w-full max-w-md">
          <div className="rounded-2xl border border-border bg-surface p-7 shadow-lg sm:p-9">
            <Wordmark size="lg" className="mb-6" />

            <p className="text-xs font-semibold tracking-[0.13em] text-accent uppercase">Get started</p>
            <h1 className="mt-3 text-2xl leading-snug font-semibold tracking-[-0.03em] text-balance text-text">
              Sign in to deploy your static sites
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              Upload a zip in seconds. Connect GitHub later, only if you want to import a repo.
            </p>

            {error && (
              <div
                role="alert"
                className="mt-6 flex items-start gap-2.5 rounded-md border border-destructive/35 bg-destructive-subtle px-3.5 py-3 text-[13px] leading-relaxed text-destructive-subtle-fg"
              >
                <AlertCircle className="mt-px size-4 shrink-0" aria-hidden="true" />
                <span>{error}</span>
              </div>
            )}

            <label className="mt-7 block text-left">
              <span className="mb-1.5 block text-[13px] text-muted">Email address</span>
              <Input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
              />
            </label>
            <label className="mt-4 block text-left">
              <span className="mb-1.5 block text-[13px] text-muted">Password</span>
              <Input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
                onKeyDown={(event) => {
                  if (event.key === "Enter") void submit();
                }}
              />
            </label>
            <Button
              variant="primary"
              size="lg"
              block
              className="mt-5"
              icon={<ArrowRight />}
              disabled={!email.trim() || !password || signing}
              onClick={() => void submit()}
            >
              {signing ? "Signing in…" : "Sign in"}
            </Button>

            <p className="mt-4 text-center text-sm text-muted">
              No account yet?{" "}
              <Link to="/register" className="font-medium text-primary hover:underline">
                Create one
              </Link>
            </p>

            <div className="my-6 flex items-center gap-3 text-xs font-medium text-muted">
              <span className="h-px flex-1 bg-border" aria-hidden="true" />
              or
              <span className="h-px flex-1 bg-border" aria-hidden="true" />
            </div>

            <Button
              variant="secondary"
              size="lg"
              block
              icon={<GithubMark className="size-4" />}
              onClick={() => void signIn()}
            >
              Continue with GitHub
            </Button>
          </div>

          {/* Outside the card: this explains what GitHub is for, and belongs
              with the decision rather than inside either control. Not a
              requirement of signing up any more, so it is framed as what
              connecting it later unlocks. */}
          <div className="mt-6 border-t border-border px-1 pt-6">
            <h2 className="text-[11px] font-semibold tracking-[0.08em] text-muted uppercase">
              What connecting GitHub asks for
            </h2>
            <dl className="mt-3 space-y-2 text-[13px] leading-relaxed">
              <div className="flex gap-2.5">
                <dt className="font-mono text-xs text-accent">repo</dt>
                <dd className="text-muted">
                  Read the repository you import and register the push webhook.
                </dd>
              </div>
              <div className="flex gap-2.5">
                <dt className="font-mono text-xs text-accent">workflow</dt>
                <dd className="text-muted">
                  Commit the build workflow. GitHub does not grant this with{" "}
                  <span className="font-mono text-[11px]">repo</span> alone.
                </dd>
              </div>
            </dl>
            <p className="mt-3 text-[13px] leading-relaxed text-muted">
              Builds run in your own GitHub Actions — we never run your code. You can
              revoke access at any time from GitHub settings.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
