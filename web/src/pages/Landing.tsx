import type { ComponentType } from "react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, Check, CheckCircle2, Globe2, History, Upload, X } from "lucide-react";

import { useAuth } from "../auth/AuthProvider";
import { ServerClusterIllustration } from "../components/landing/ServerClusterIllustration";
import { Button } from "../components/ui/button";
import { GithubMark } from "../components/ui/github-mark";
import { ThemeToggle } from "../components/ui/theme-toggle";
import { Wordmark } from "../components/ui/wordmark";

function Feature({ Icon, number, title, children }: { Icon: ComponentType<{ className?: string }>; number: string; title: string; children: React.ReactNode }) {
  return <article className="border-t border-border pt-5"><div className="flex items-center justify-between"><Icon className="size-5 text-accent" aria-hidden="true" /><span className="font-mono text-xs text-muted">{number}</span></div><h3 className="mt-7 text-base font-semibold tracking-tight text-text">{title}</h3><p className="mt-2 max-w-xs text-sm leading-relaxed text-muted">{children}</p></article>;
}


/**
 * Shown once, after an account is deleted.
 *
 * The confirmation cannot be a toast: deleting an account ends on the apex
 * host, and crossing origins throws away every bit of in-memory state a toast
 * lives in. A query flag is the only thing that survives the trip.
 */
function DeletedNotice() {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;
  return (
    <div className="border-b border-success/30 bg-success-subtle">
      <div className="mx-auto flex max-w-7xl items-center gap-3 px-6 py-3 sm:px-8">
        <CheckCircle2 className="size-4 shrink-0 text-success" aria-hidden="true" />
        <p className="min-w-0 flex-1 text-sm text-success-subtle-fg">
          Your Dropbin account has been deleted.
        </p>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          aria-label="Dismiss"
          className="shrink-0 rounded-sm p-1 text-success-subtle-fg/70 transition-colors hover:text-success-subtle-fg"
        >
          <X className="size-3.5" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}

/**
 * The hero.
 *
 * The warm tokens appear here and only here, as two blurred washes behind the
 * headline and one highlighted word - which is the rule written above them in
 * tokens.css. They are not on the button, the pill or the badge; those stay
 * indigo, cool and semantic.
 *
 * `text-primary` on the illustration wrapper is what currentColor resolves to
 * inside it, so the accent in the drawing is the brand indigo in both themes
 * rather than unDraw's purple.
 */
function Hero() {
  const { session, loading } = useAuth();

  return (
    <section className="relative overflow-hidden">
      {/* Decorative only, and hidden from assistive tech: these carry no
          meaning, they set a temperature. */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -top-32 right-[-10%] size-[34rem] rounded-full bg-warm-orange/20 blur-[110px]" />
        <div className="absolute top-24 right-[18%] size-[22rem] rounded-full bg-warm-pink/15 blur-[100px]" />
        <div className="absolute -bottom-40 -left-24 size-[30rem] rounded-full bg-primary/10 blur-[110px]" />
      </div>

      <div className="mx-auto grid max-w-7xl items-center gap-14 px-6 pt-16 pb-20 sm:px-8 sm:pt-24 lg:grid-cols-[1.05fr_0.95fr] lg:gap-16 lg:pb-28">
        <div className="max-w-2xl">
          <p className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium text-muted shadow-sm">
            <span className="size-1.5 rounded-full bg-success" />
            Static deployment, without the ceremony
          </p>

          <h1 className="mt-7 text-5xl leading-[1.03] font-semibold tracking-[-0.055em] text-balance text-text sm:text-6xl">
            Deploy static sites in <span className="text-warm-orange">seconds</span>.
          </h1>

          <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted">
            Push a zip or a GitHub repo. Get a public URL. Roll back with one click.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link to="/login">
              <Button variant="primary" size="lg" icon={<GithubMark className="size-4" />}>
                Continue with GitHub
              </Button>
            </Link>
            <a href="#how-it-works">
              <Button variant="ghost" size="lg" icon={<ArrowRight />}>
                See how it works
              </Button>
            </a>
          </div>

          {/* A real artefact of the product rather than a stock claim: this is
              the shape of a URL you actually get. */}
          <div className="mt-10 inline-flex flex-wrap items-center gap-3 rounded-lg border border-border bg-surface px-4 py-3 shadow-sm">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-success-subtle px-2.5 py-1 text-[11px] font-medium text-success-subtle-fg">
              <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
              Ready
            </span>
            <span className="font-mono text-[13px] break-all text-muted">
              blue-forest-4821.getdropbin.xyz
            </span>
          </div>

          {!loading && session && (
            <p className="mt-6 text-sm text-muted">
              You are signed in.{" "}
              <Link to="/projects" className="text-primary underline-offset-4 hover:underline">
                Open your dashboard
              </Link>
            </p>
          )}
        </div>

        <div className="relative lg:pl-4">
          <ServerClusterIllustration className="mx-auto w-full max-w-[30rem] text-primary lg:max-w-none" />
        </div>
      </div>
    </section>
  );
}

export function Landing() {
  const { session, loading } = useAuth();
  const [params] = useSearchParams();
  const deleted = params.get("deleted") !== null;

  return (
    <div className="min-h-screen overflow-hidden bg-bg">
      <header className="relative z-10">
        <div className="mx-auto flex max-w-7xl items-center px-6 py-5 sm:px-8">
          <Wordmark />
          <nav
            className="ml-10 hidden items-center gap-6 text-sm text-muted md:flex"
            aria-label="Marketing navigation"
          >
            <a className="transition-colors hover:text-text" href="#how-it-works">
              How it works
            </a>
            <a className="transition-colors hover:text-text" href="#features">
              Features
            </a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
            {!loading &&
              (session ? (
                <Link to="/projects">
                  <Button variant="secondary" size="sm">
                    Open dashboard
                  </Button>
                </Link>
              ) : (
                <Link to="/login">
                  <Button variant="secondary" size="sm">
                    Sign in
                  </Button>
                </Link>
              ))}
          </div>
        </div>
      </header>

      {deleted && <DeletedNotice />}

      <main>
        <Hero />
        <section id="how-it-works" className="border-y border-border bg-surface"><div className="mx-auto grid max-w-7xl gap-8 px-6 py-16 sm:grid-cols-3 sm:px-8"><Feature Icon={Upload} number="01" title="Add your files">Drop in a zip with an index file, or choose a GitHub repository you already own.</Feature><Feature Icon={Globe2} number="02" title="Go live immediately">We validate and publish your files to a secure public subdomain.</Feature><Feature Icon={History} number="03" title="Keep every version">Each deploy has a clear history, so promoting a previous version is instant.</Feature></div></section><section id="features" className="mx-auto grid max-w-7xl gap-12 px-6 py-20 sm:px-8 lg:grid-cols-[1.1fr_1fr] lg:items-end"><div><p className="text-xs font-semibold tracking-[0.13em] text-accent uppercase">Built for simple shipping</p><h2 className="mt-4 max-w-lg text-3xl font-semibold tracking-[-0.035em] text-text sm:text-4xl">A calmer way to manage small sites.</h2></div><ul className="space-y-4 text-sm leading-relaxed text-muted">{["A clean project list, designed for scanning—not dashboard clutter.", "Secure GitHub imports that deploy again when your branch changes.", "Transparent storage limits and deployment states, exactly where you need them."].map((item) => <li key={item} className="flex gap-3"><Check className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />{item}</li>)}</ul></section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-8 text-sm text-muted sm:px-8">
          <Wordmark />
          <span>© {new Date().getFullYear()} Dropbin</span>
        </div>
      </footer>
    </div>
  );
}
