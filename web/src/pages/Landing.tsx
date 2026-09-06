import type { ComponentType } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Globe, History, Upload } from "lucide-react";

import { useAuth } from "../auth/AuthProvider";
import { Button } from "../components/ui/button";
import { GithubMark } from "../components/ui/github-mark";
import { ThemeToggle } from "../components/ui/theme-toggle";
import { Wordmark } from "../components/ui/wordmark";

/**
 * The marketing page, served at `/` on the apex domain.
 *
 * Rules this page lives by, in order of how easy they are to break:
 *
 *  1. It fetches nothing. No /api/me, no project list, no session round-trip.
 *     It renders on first paint from static markup, which is the whole reason
 *     the apex serves the bundle instead of redirecting into the dashboard.
 *  2. It reads `session` from the auth context but never *waits* on it. The
 *     only thing session changes is which button sits top-right, so that one
 *     control is withheld until auth resolves and everything else paints
 *     immediately.
 */

function Feature({
  Icon,
  title,
  children,
}: {
  Icon: ComponentType<{ className?: string }>;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-surface p-5 shadow-sm">
      {/* --accent-vivid is decorative only, which is exactly what this is: the
          title beside it carries the same meaning, so the colour is never the
          thing doing the work. */}
      <div className="mb-4 grid size-9 place-items-center rounded-md bg-accent-subtle text-accent-vivid">
        <Icon className="size-4.5" />
      </div>
      <h3 className="mb-1.5 text-sm font-semibold text-text">{title}</h3>
      <p className="text-[13px] leading-relaxed text-muted">{children}</p>
    </div>
  );
}

export function Landing() {
  const { session, loading } = useAuth();

  // Honour the OS setting rather than relying on `scroll-behavior: smooth`,
  // which the reduced-motion block in index.css does not cover.
  const scrollToFeatures = (event: React.MouseEvent) => {
    event.preventDefault();
    const target = document.getElementById("features");
    if (!target) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    target.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
  };

  return (
    <div className="min-h-screen bg-bg">
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-5xl items-center gap-4 px-6 py-4">
          <Wordmark />
          <div className="ml-auto flex items-center gap-3">
            <ThemeToggle />
            {/* Withheld, not guessed: rendering "Sign in" and then swapping it
                for "Open dashboard" a moment later is worse than a brief gap. */}
            {!loading &&
              (session ? (
                <Link to="/projects">
                  <Button variant="secondary" size="sm">
                    Open dashboard
                  </Button>
                </Link>
              ) : (
                <Link to="/login">
                  <Button variant="ghost" size="sm">
                    Sign in
                  </Button>
                </Link>
              ))}
          </div>
        </div>
      </header>

      <main>
        <section className="mx-auto max-w-5xl px-6 pt-20 pb-16 sm:pt-28">
          <h1 className="max-w-3xl text-4xl leading-[1.1] font-bold tracking-tight text-balance text-text sm:text-5xl">
            Deploy a static site from a zip or a GitHub repo.
          </h1>
          <p className="mt-5 max-w-xl text-lg leading-relaxed text-muted">
            Public URL in seconds. <span className="text-accent">No config.</span>
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link to="/login">
              <Button variant="primary" size="lg" icon={<GithubMark className="size-4" />}>
                Continue with GitHub
              </Button>
            </Link>
            <a href="#features" onClick={scrollToFeatures}>
              <Button variant="secondary" size="lg" icon={<ArrowRight className="size-4" />}>
                See how it works
              </Button>
            </a>
          </div>

          {/* A real artefact of the product rather than an abstract graphic:
              this is the shape of a URL you actually get. */}
          <div className="mt-14 inline-flex flex-wrap items-center gap-3 rounded-lg border border-border bg-surface px-4 py-3 shadow-sm">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-success-subtle px-2.5 py-1 text-[11px] font-medium text-success-subtle-fg">
              <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
              Ready
            </span>
            <span className="font-mono text-[13px] break-all text-muted">
              blue-forest-4821.getdropbin.xyz
            </span>
          </div>
        </section>

        <section
          id="features"
          className="mx-auto max-w-5xl scroll-mt-8 border-t border-border px-6 py-16"
        >
          <h2 className="mb-8 text-xs font-semibold tracking-[0.09em] text-muted uppercase">
            What you get
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Feature Icon={Upload} title="Drop in a zip">
              Zip the contents of your site folder and drop it in. It is validated,
              stored, and served — never executed.
            </Feature>
            <Feature Icon={GithubMark} title="Deploy on push">
              Import a repository and every push to your branch deploys. Builds run in
              your own GitHub Actions.
            </Feature>
            <Feature Icon={History} title="Roll back instantly">
              Every deployment stays reachable. Promoting an old one moves a pointer, so
              it is instant and reversible.
            </Feature>
            <Feature Icon={Globe} title="A subdomain each">
              Each project gets its own name under a wildcard certificate, live the
              moment the upload finishes.
            </Feature>
          </div>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-3 px-6 py-8">
          <span className="text-[13px] text-muted">
            © {new Date().getFullYear()} Dropbin
          </span>
        </div>
      </footer>
    </div>
  );
}
