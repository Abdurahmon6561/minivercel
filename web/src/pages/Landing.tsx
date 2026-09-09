import type { ComponentType } from "react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, CheckCircle2, Globe2, History, Upload, X } from "lucide-react";

import { useAuth } from "../auth/AuthProvider";
import {
  CommitStripGraphic,
  EnvKeysGraphic,
  RollbackGraphic,
  ZipDropGraphic,
} from "../components/landing/FeatureGraphics";
import { ServerClusterIllustration } from "../components/landing/ServerClusterIllustration";
import { SitePreview } from "../components/landing/SitePreview";
import { Button } from "../components/ui/button";
import { GithubMark } from "../components/ui/github-mark";
import { ThemeToggle } from "../components/ui/theme-toggle";
import { Wordmark } from "../components/ui/wordmark";


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

/**
 * The three steps, then the thing they produce.
 *
 * Numbered markers are used here and nowhere else on the page, because here the
 * order is real information: you cannot roll back before you have deployed. The
 * connecting rail is each step's own top border rather than an absolutely
 * positioned line, so it survives the wrap to one column on mobile - the rail
 * becomes a divider above each step instead of a line pointing at nothing.
 */
const STEPS: { Icon: ComponentType<{ className?: string }>; number: string; title: string; body: string }[] = [
  {
    Icon: Upload,
    number: "01",
    title: "Add your files",
    body: "Import a GitHub repository you own, or drop in a zip with an index file.",
  },
  {
    Icon: Globe2,
    number: "02",
    title: "Dropbin publishes it",
    body: "Your build runs on GitHub Actions if it needs one, and the output goes live on an HTTPS subdomain.",
  },
  {
    Icon: History,
    number: "03",
    title: "Roll back any time",
    body: "Every deploy keeps its own files, so promoting a previous version takes one click.",
  },
];

function HowItWorks() {
  return (
    <section id="how-it-works" className="border-y border-border bg-surface">
      <div className="mx-auto max-w-7xl px-6 py-20 sm:px-8 sm:py-24">
        <div className="max-w-2xl">
          <p className="text-xs font-semibold tracking-[0.13em] text-accent uppercase">How it works</p>
          <h2 className="mt-4 text-3xl font-semibold tracking-[-0.035em] text-balance text-text sm:text-4xl">
            Three steps, and no configuration to learn.
          </h2>
        </div>

        <ol className="mt-14 grid gap-12 sm:grid-cols-3 sm:gap-8">
          {STEPS.map(({ Icon, number, title, body }) => (
            <li key={number} className="relative border-t border-border pt-9">
              {/* Straddles the border, and masks it with the section's own
                  background so the rail reads as passing behind the node. */}
              <span
                aria-hidden="true"
                className="absolute -top-4 left-0 flex size-8 items-center justify-center rounded-full border border-border bg-surface font-mono text-xs text-muted"
              >
                {number}
              </span>
              <h3 className="flex items-center gap-2 text-base font-semibold tracking-tight text-text">
                <Icon className="size-4 shrink-0 text-accent" aria-hidden="true" />
                {title}
              </h3>
              <p className="mt-2 max-w-xs text-sm leading-relaxed text-muted">{body}</p>
            </li>
          ))}
        </ol>

        {/* A figure, not a decorative div: it is the outcome the three steps
            produce, and the caption is what ties it to them. */}
        <figure className="mt-16">
          <SitePreview />
          <figcaption className="mt-4 text-center text-sm text-muted">
            A finished deployment: the public URL, its status, and the commit it came from.
          </figcaption>
        </figure>
      </div>
    </section>
  );
}

/**
 * The four things you actually touch.
 *
 * Each card leads with a small piece of the product rather than an icon, so the
 * screens are recognisable before anyone signs in. The graphics carry no
 * information the title and body do not also state in words, which is why they
 * are aria-hidden.
 */
const FEATURES: { Graphic: () => React.ReactElement; title: string; body: string }[] = [
  {
    Graphic: ZipDropGraphic,
    title: "Zip upload",
    body: "Drop in a zip with an index file. No repository, no build step, nothing to configure.",
  },
  {
    Graphic: CommitStripGraphic,
    title: "GitHub auto-deploy",
    body: "Connect a repository and every push to your branch deploys itself. Each attempt keeps its build log.",
  },
  {
    Graphic: RollbackGraphic,
    title: "Instant rollbacks",
    body: "Every deploy keeps its own files, so promoting an earlier one is a single click and takes effect at once.",
  },
  {
    Graphic: EnvKeysGraphic,
    title: "Environment variables",
    body: "Encrypted at rest and injected at build time. They are write-only - Dropbin never shows a value back.",
  },
];

function Features() {
  return (
    <section id="features" className="mx-auto max-w-7xl px-6 py-20 sm:px-8 sm:py-24">
      <div className="max-w-2xl">
        <p className="text-xs font-semibold tracking-[0.13em] text-accent uppercase">Features</p>
        <h2 className="mt-4 text-3xl font-semibold tracking-[-0.035em] text-balance text-text sm:text-4xl">
          The parts you actually touch.
        </h2>
      </div>

      <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
        {FEATURES.map(({ Graphic, title, body }) => (
          <article key={title}>
            <Graphic />
            <h3 className="mt-5 text-base font-semibold tracking-tight text-text">{title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">{body}</p>
          </article>
        ))}
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
        <HowItWorks />
        <Features />
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
