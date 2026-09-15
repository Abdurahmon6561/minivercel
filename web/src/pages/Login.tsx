import { useState } from "react";
import { AlertCircle, ArrowRight, Mail } from "lucide-react";
import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { BrandPane } from "../components/auth/BrandPane";
import { Button } from "../components/ui/button";
import { GithubMark } from "../components/ui/github-mark";
import { Input } from "../components/ui/input";
import { PasswordInput } from "../components/ui/password-input";
import { ThemeToggle } from "../components/ui/theme-toggle";
import { Wordmark } from "../components/ui/wordmark";
import { landingOrigin } from "../lib/host";

/**
 * The only unauthenticated page inside the dashboard.
 *
 * A fixed-height split screen, not a scrolling centred card: everything
 * needed to sign in fits in one view with nothing to scroll past, and the
 * brand pane fills the space a long, mostly-empty page used to leave beside
 * a narrow form.
 *
 * Two ways in, not one: GitHub used to be the only account there was, which
 * meant creating a Dropbin account and authorising a GitHub app were the same
 * click. They are not the same decision - someone who only wants to upload a
 * zip has no reason to grant repository access first - so email+password is
 * now a first-class way to get an account (via /register), and GitHub is
 * something you connect later, from the new-project page (which explains
 * what its scopes are for at the point that actually matters), only when you
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
    <div className="grid h-dvh overflow-hidden bg-bg lg:grid-cols-2">
      <BrandPane />

      <div className="flex h-dvh flex-col overflow-y-auto">
        <header className="flex items-center gap-4 px-6 py-5 sm:px-10">
          {/* Leaves the dashboard entirely, so this is a real anchor to the
              apex - a router Link cannot cross the host boundary. */}
          <a href={landingOrigin()} aria-label="Dropbin home" className="lg:hidden">
            <Wordmark />
          </a>
          <div className="ml-auto">
            <ThemeToggle />
          </div>
        </header>

        <main className="flex flex-1 items-center justify-center px-6 pb-10 sm:px-10">
          <div className="w-full max-w-sm">
            <p className="text-xs font-semibold tracking-[0.13em] text-accent uppercase">Get started</p>
            <h1 className="mt-3 text-2xl leading-snug font-semibold tracking-[-0.03em] text-balance text-text">
              Sign in to Dropbin
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              Upload a zip in seconds, or connect GitHub for auto-deploy on push.
            </p>

            {error && (
              <div
                role="alert"
                className="mt-5 flex items-start gap-2.5 rounded-md border border-destructive/35 bg-destructive-subtle px-3.5 py-3 text-[13px] leading-relaxed text-destructive-subtle-fg"
              >
                <AlertCircle className="mt-px size-4 shrink-0" aria-hidden="true" />
                <span>{error}</span>
              </div>
            )}

            <label className="mt-6 block text-left">
              <span className="mb-1.5 block text-[13px] text-muted">Email address</span>
              <div className="relative">
                <Mail
                  className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted"
                  aria-hidden="true"
                />
                <Input
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@example.com"
                  autoComplete="email"
                  className="pl-9"
                />
              </div>
            </label>
            <label className="mt-3.5 block text-left">
              <span className="mb-1.5 block text-[13px] text-muted">Password</span>
              <PasswordInput
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
              className="mt-4"
              icon={<ArrowRight />}
              disabled={!email.trim() || !password || signing}
              onClick={() => void submit()}
            >
              {signing ? "Signing in…" : "Sign in"}
            </Button>

            <p className="mt-3.5 text-center text-sm text-muted">
              No account yet?{" "}
              <Link to="/register" className="font-medium text-primary hover:underline">
                Create one
              </Link>
            </p>

            <div className="my-5 flex items-center gap-3 text-xs font-medium text-muted">
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
        </main>
      </div>
    </div>
  );
}
