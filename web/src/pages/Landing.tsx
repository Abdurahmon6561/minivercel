import type { ComponentType } from "react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, Check, CheckCircle2, Globe2, History, Minus, Upload, X } from "lucide-react";

import { useAuth } from "../auth/AuthProvider";
import { DeployOrbitIllustration } from "../components/landing/DeployOrbitIllustration";
import {
  CommitStripGraphic,
  EnvKeysGraphic,
  RollbackGraphic,
  ZipDropGraphic,
} from "../components/landing/FeatureGraphics";
import { Reveal } from "../components/landing/Reveal";
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
 * The illustration is a deploy happening - a code window orbited by the two
 * cool accents, reporting a Ready state - rather than a generic stock drawing,
 * so it reads as the product on first look instead of as decoration. See
 * DeployOrbitIllustration for why it is built from tokens, not an SVG import.
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

      <div className="mx-auto grid max-w-7xl items-center gap-14 px-6 pt-16 pb-24 sm:px-8 sm:pt-24 lg:grid-cols-[1.05fr_0.95fr] lg:gap-16 lg:pb-32">
        <Reveal className="max-w-2xl">
          <p className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium text-muted shadow-sm">
            <span className="size-1.5 rounded-full bg-success" />
            Static deployment, without the ceremony
          </p>

          {/* One size step up from the previous draft: a 5-word, 2-line
              headline is exactly the case where a bigger display size reads as
              confident rather than as an overflow bug. */}
          <h1 className="mt-7 text-6xl leading-[0.98] font-semibold tracking-[-0.055em] text-balance text-text sm:text-7xl">
            Deploy static sites in <span className="text-warm-orange">seconds</span>.
          </h1>

          <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted">
            Push a zip or a GitHub repo. Get a public URL. Roll back with one click.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Link to="/login">
              {/* The lift-on-hover is new: it marks this specific button as the
                  one action this whole page exists for, which is also why it
                  is not on the secondary button beside it. */}
              <Button
                variant="primary"
                size="lg"
                icon={<GithubMark className="size-4" />}
                className="hover:-translate-y-0.5"
              >
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
        </Reveal>

        <Reveal delay={150} className="relative lg:pl-4">
          <DeployOrbitIllustration className="lg:max-w-none" />
        </Reveal>
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
      <div className="mx-auto max-w-7xl px-6 py-24 sm:px-8 sm:py-28">
        <Reveal className="max-w-2xl">
          <p className="text-xs font-semibold tracking-[0.13em] text-accent uppercase">How it works</p>
          <h2 className="mt-4 text-3xl font-semibold tracking-[-0.035em] text-balance text-text sm:text-4xl">
            Three steps, and no configuration to learn.
          </h2>
        </Reveal>

        <Reveal delay={100}>
          <ol className="mt-14 grid gap-12 sm:grid-cols-3 sm:gap-8">
            {STEPS.map(({ Icon, number, title, body }) => (
              <li key={number} className="relative border-t border-border pt-9">
                {/* A bead straddling the border, masking it with the section's
                    own background so the rail reads as passing behind the
                    node - the number itself now lives in the heading row
                    below, big enough to carry real typographic weight rather
                    than hiding inside a small mono badge. */}
                <span aria-hidden="true" className="absolute -top-1.5 left-0 size-3 rounded-full bg-accent" />
                <h3 className="flex items-center justify-between gap-3 text-base font-semibold tracking-tight text-text">
                  <span className="flex items-center gap-2">
                    <Icon className="size-4 shrink-0 text-accent" aria-hidden="true" />
                    {title}
                  </span>
                  <span aria-hidden="true" className="font-mono text-2xl font-bold text-border-strong sm:text-3xl">
                    {number}
                  </span>
                </h3>
                <p className="mt-2 max-w-xs text-sm leading-relaxed text-muted">{body}</p>
              </li>
            ))}
          </ol>
        </Reveal>

        {/* A figure, not a decorative div: it is the outcome the three steps
            produce, and the caption is what ties it to them. */}
        <Reveal delay={200}>
          <figure className="mt-16">
            <SitePreview />
            <figcaption className="mt-4 text-center text-sm text-muted">
              A finished deployment: the public URL, its status, and the commit it came from.
            </figcaption>
          </figure>
        </Reveal>
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
    <section id="features" className="mx-auto max-w-7xl px-6 py-24 sm:px-8 sm:py-28">
      <Reveal className="max-w-2xl">
        <p className="text-xs font-semibold tracking-[0.13em] text-accent uppercase">Features</p>
        <h2 className="mt-4 text-3xl font-semibold tracking-[-0.035em] text-balance text-text sm:text-4xl">
          The parts you actually touch.
        </h2>
      </Reveal>

      <Reveal delay={100}>
        <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {/* The four graphics are built to align as equal siblings (see
              FeatureGraphics.tsx) - so the lift is what signals "this is
              worth a closer look" rather than a resize that would fight the
              graphics' own layout. */}
          {FEATURES.map(({ Graphic, title, body }) => (
            <article key={title} className="transition-transform duration-200 hover:-translate-y-1">
              <Graphic />
              <h3 className="mt-5 text-base font-semibold tracking-tight text-text">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{body}</p>
            </article>
          ))}
        </div>
      </Reveal>
    </section>
  );
}

/**
 * Dropbin against the two free alternatives people actually weigh it against.
 *
 * Every cell was checked against primary documentation in September 2026, not
 * from memory, and the table is deliberately not flattering: Dropbin loses the
 * cold-start row outright and only wins one row cleanly. A comparison that made
 * us win six out of six would be worth nothing to the reader, and wrong.
 *
 * Four of the six rows are a tie on the tick alone, so the qualifier under each
 * tick is doing the real work - "public repos only" and "non-commercial only"
 * are the difference between three identical ticks and three different offers.
 * A bare tick row would be true and useless.
 *
 * Sources, all fetched rather than recalled:
 *   Pages plans/limits  docs.github.com/en/pages/.../github-pages-limits
 *   Pages HTTPS         docs.github.com/en/pages/.../securing-your-github-pages-site-with-https
 *   Vercel Hobby        vercel.com/docs/plans/hobby  (non-commercial; rollback
 *                       limited to the immediately previous deployment)
 *   Vercel SSL          vercel.com/docs/domains/working-with-ssl
 *   Render Free         render.com/docs/free  (spins down after 15 minutes
 *                       idle, ~1 minute to wake) - this is our own weak spot
 */
type Cell = { state: "yes" | "no" | "partial"; note?: string };

const COLUMNS = ["Dropbin", "GitHub Pages", "Vercel Hobby"] as const;

const COMPARISON: { feature: string; cells: [Cell, Cell, Cell] }[] = [
  {
    feature: "Free hosting",
    cells: [
      { state: "yes" },
      { state: "yes", note: "Public repos only" },
      { state: "yes", note: "Non-commercial only" },
    ],
  },
  {
    feature: "Automatic HTTPS",
    cells: [
      { state: "yes", note: "On your Dropbin subdomain" },
      { state: "yes", note: "Let's Encrypt" },
      { state: "yes", note: "Let's Encrypt" },
    ],
  },
  {
    feature: "Deploys on git push",
    cells: [
      { state: "yes", note: "Via GitHub Actions" },
      { state: "yes" },
      { state: "yes" },
    ],
  },
  {
    feature: "One-click rollback",
    cells: [
      { state: "yes", note: "Any deploy still kept" },
      { state: "no", note: "Revert the commit and rebuild" },
      { state: "partial", note: "Previous deploy only" },
    ],
  },
  {
    feature: "No credit card",
    cells: [{ state: "yes" }, { state: "yes" }, { state: "yes" }],
  },
  {
    feature: "No cold starts",
    cells: [
      { state: "no", note: "First visit after 15 min idle waits ~1 min" },
      { state: "yes", note: "Served from a CDN" },
      { state: "yes", note: "Served from a CDN" },
    ],
  },
];

/**
 * The icon is aria-hidden and paired with a visually hidden word, so the state
 * survives for a screen reader and for anyone who cannot separate the red from
 * the green - colour is never the only carrier.
 */
function StateMark({ state }: { state: Cell["state"] }) {
  const marks = {
    yes: { Icon: Check, className: "text-success", label: "Yes" },
    no: { Icon: X, className: "text-destructive", label: "No" },
    partial: { Icon: Minus, className: "text-muted", label: "Partial" },
  };
  const { Icon, className, label } = marks[state];
  return (
    <>
      <Icon className={`mx-auto size-5 ${className}`} aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </>
  );
}

function Comparison() {
  return (
    <section className="border-y border-border bg-surface">
      <div className="mx-auto max-w-7xl px-6 py-24 sm:px-8 sm:py-28">
        {/* No eyebrow here on purpose: How it works and Features already carry
            one each, and a third small-caps label above this headline would
            push the page past one eyebrow per three sections. The headline
            itself ("wins, and where it doesn't") already says "honestly". */}
        <Reveal className="max-w-2xl">
          <h2 className="text-3xl font-semibold tracking-[-0.035em] text-balance text-text sm:text-4xl">
            Where Dropbin wins, and where it doesn't.
          </h2>
        </Reveal>

        {/* Below sm the last two columns sit off-screen, and a cut-off edge is
            too quiet an affordance on a phone - without this the table reads as
            a one-column list of Dropbin ticks, which is the opposite of the
            section's point. */}
        <p className="mt-6 text-xs text-muted sm:hidden">
          Scroll the table sideways to see GitHub Pages and Vercel Hobby.
        </p>

        {/* The table scrolls inside its own container so the page body never
            does - three columns of qualifiers will not fit a phone.

            `relative` is load-bearing, not decorative. Without a positioned
            ancestor the min-w-2xl table leaked past the scroll container and
            made the whole viewport scroll 215px sideways at 400px wide - the
            wrapper clipped it visually while window.scrollX still moved, so it
            was invisible in a screenshot and only showed up in the assertion.
            Marking the wrapper as a containing block stops the leak; `contain:
            paint` also worked, `isolation` did not. */}
        <Reveal delay={100} className="relative mt-12 -mx-6 overflow-x-auto px-6 sm:mx-0 sm:px-0">
          <table className="w-full min-w-2xl border-collapse text-sm">
            <caption className="sr-only">
              Dropbin compared with GitHub Pages and the Vercel Hobby plan
            </caption>
            <thead>
              <tr>
                <th className="w-[28%] pb-4 text-left font-medium text-muted" scope="col">
                  <span className="sr-only">Capability</span>
                </th>
                {COLUMNS.map((name, i) => (
                  <th
                    key={name}
                    scope="col"
                    className={`pb-4 text-center text-sm font-semibold tracking-tight ${
                      i === 0 ? "text-text" : "text-muted"
                    }`}
                  >
                    {name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {COMPARISON.map(({ feature, cells }) => (
                <tr key={feature} className="border-t border-border">
                  <th scope="row" className="py-5 pr-4 text-left align-top font-medium text-text">
                    {feature}
                  </th>
                  {cells.map((cell, i) => (
                    <td
                      key={COLUMNS[i]}
                      className={`px-3 py-5 text-center align-top ${
                        i === 0 ? "bg-surface-sunken" : ""
                      }`}
                    >
                      <StateMark state={cell.state} />
                      {cell.note && (
                        <p className="mx-auto mt-1.5 max-w-[22ch] text-xs leading-snug text-balance text-muted">
                          {cell.note}
                        </p>
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </Reveal>

        <p className="mt-8 max-w-2xl text-xs leading-relaxed text-muted">
          Checked against GitHub and Vercel documentation in September 2026. Free tiers change
          often, so verify anything here before you rely on it. Dropbin serves every request
          through a single small instance that sleeps when idle. If you need a site that is
          always warm, GitHub Pages and Vercel both put your files on a CDN and Dropbin does not.
        </p>
      </div>
    </section>
  );
}

/**
 * The closing call to action.
 *
 * Warm returns here, and only here after the hero. The two washes bookend the
 * page - warm at the top, warm at the bottom, everything in between cool - so
 * the accent reads as a frame rather than a colour sprinkled through the
 * content. They are lighter than the hero's, because the hero should stay the
 * loudest thing on the page.
 *
 * The headline deliberately has no highlighted word. "seconds" in the hero is
 * the page's one display highlight, and repeating the trick here would spend it
 * twice and make neither land.
 */
function CallToAction() {
  const { session, loading } = useAuth();

  return (
    <section className="relative overflow-hidden">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -top-44 left-1/2 size-[36rem] -translate-x-1/2 rounded-full bg-warm-orange/18 blur-[120px]" />
        <div className="absolute -bottom-32 right-[6%] size-[26rem] rounded-full bg-warm-pink/14 blur-[110px]" />
      </div>

      <Reveal className="mx-auto max-w-3xl px-6 py-28 text-center sm:px-8 sm:py-32">
        {/* Matches the hero's new scale, so the two warm moments bookend the
            page at the same visual weight instead of the closer reading as an
            afterthought. */}
        <h2 className="text-5xl font-semibold tracking-[-0.045em] text-balance text-text sm:text-6xl">
          Start deploying.
        </h2>

        <div className="mt-9 flex justify-center">
          {/* Offering GitHub sign-in to someone already signed in is a dead
              end, so the button changes rather than the page pretending not to
              know who is reading it. */}
          {!loading &&
            (session ? (
              <Link to="/projects">
                <Button variant="primary" size="lg" icon={<ArrowRight />}>
                  Open your dashboard
                </Button>
              </Link>
            ) : (
              <Link to="/login">
                <Button variant="primary" size="lg" icon={<GithubMark className="size-4" />}>
                  Continue with GitHub
                </Button>
              </Link>
            ))}
        </div>

        <p className="mt-6 text-sm text-muted">
          Free while in beta. No credit card. No lock-in.
        </p>
      </Reveal>
    </section>
  );
}

export function Landing() {
  const { session, loading } = useAuth();
  const [params] = useSearchParams();
  const deleted = params.get("deleted") !== null;

  return (
    <div className="min-h-screen bg-bg">
      {/* Fixed to the top of the viewport rather than scrolling away, so
          "Continue with GitHub" and the theme toggle are always one click
          away no matter how far down the page you are.

          A floating rounded bar with visible margin either side, not an
          edge-to-edge strip - the outer div carries the sticky positioning
          and the inset (its padding is what leaves the page background
          visible at the corners), and the actual bordered, rounded surface
          is the `<header>` inside it. Splitting them this way means the
          inset survives scrolling: a rounded/margined header with no
          separate positioning wrapper would need its OWN top/side margin,
          which pulls it a few pixels short of true position:sticky's top
          edge and reintroduces the "gap that isn't quite there" bug that a
          plain `top-2` offset alone would leave.

          `sticky`, not `fixed`: a truly fixed header needs a matching
          top-padding spacer on the content below it, which drifts out of
          sync the moment the header's own height changes. Sticky achieves
          the same pinned-at-top behaviour without that second number to
          maintain, and the two decorative-blob sections below now clip
          themselves (`overflow-hidden` on each `<section>`) rather than
          relying on a wrapper-level `overflow-hidden` - that wrapper rule
          would otherwise make this element's nearest ancestor a clipping
          container, which silently breaks `position: sticky` in every
          browser regardless of whether anything actually overflows it. */}
      <div className="sticky top-0 z-40 px-3 pt-3 sm:px-6 sm:pt-4">
        <header className="mx-auto max-w-7xl rounded-full border border-border bg-surface/95 shadow-lg backdrop-blur-md">
          <div className="flex items-center px-6 py-3.5 sm:px-8">
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
      </div>

      {deleted && <DeletedNotice />}

      <main>
        <Hero />
        <HowItWorks />
        <Features />
        <Comparison />
        <CallToAction />
      </main>

      {/* Deliberately bare. This is a hosting platform, not a publication - a
          column of link lists would be inventing pages that do not exist. The
          unDraw credit is here because we use their artwork in the hero, and
          the licence asks for attribution somewhere on the site. */}
      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-7xl flex-col items-center gap-3 px-6 py-8 text-sm text-muted sm:flex-row sm:justify-between sm:px-8">
          <div className="flex items-center gap-3">
            <Wordmark />
            <span>© {new Date().getFullYear()} Dropbin</span>
          </div>
          <a
            className="transition-colors hover:text-text"
            href="https://undraw.co"
            target="_blank"
            rel="noreferrer"
          >
            Illustrations by unDraw
          </a>
        </div>
      </footer>
    </div>
  );
}
