import { AlertCircle } from "lucide-react";

import { useAuth } from "../auth/AuthProvider";
import { Button } from "../components/ui/button";
import { GithubMark } from "../components/ui/github-mark";
import { ThemeToggle } from "../components/ui/theme-toggle";
import { Wordmark } from "../components/ui/wordmark";

/**
 * The only unauthenticated page inside the dashboard.
 *
 * Same visual language as the landing - one header bar, the same wordmark, the
 * same card treatment - because arriving here from the landing's CTA should
 * feel like the next step rather than a different product.
 */
export function Login() {
  const { signIn, error } = useAuth();

  return (
    <div className="flex min-h-screen flex-col bg-bg">
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

      <main className="flex flex-1 items-center justify-center px-6 py-16">
        <div className="w-full max-w-sm">
          <div className="rounded-xl border border-border bg-surface p-8 shadow-md">
            <Wordmark size="lg" className="mb-6" />

            <h1 className="text-xl leading-snug font-semibold tracking-tight text-balance text-text">
              Sign in to deploy your static sites
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              A zip or a GitHub repo. Public URL in seconds.
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

            <Button
              variant="primary"
              size="lg"
              block
              className="mt-7"
              icon={<GithubMark className="size-4" />}
              onClick={() => void signIn()}
            >
              Continue with GitHub
            </Button>
          </div>

          {/* Outside the card: this explains what happens after the button, and
              belongs with the decision rather than inside the control. */}
          <div className="mt-6 px-1">
            <h2 className="text-[11px] font-semibold tracking-[0.08em] text-muted uppercase">
              What Dropbin asks for
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
