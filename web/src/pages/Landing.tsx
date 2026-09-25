import type { ComponentType, ReactNode } from "react";
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowDown, ArrowRight, ChevronDown, Globe2, History, Lock, PlayCircle, RefreshCw, Upload } from "lucide-react";
import {
  AnimatePresence,
  motion,
  useInView,
  useMotionTemplate,
  useMotionValue,
  useMotionValueEvent,
  useReducedMotion,
  useScroll,
  useSpring,
  useTransform,
  type MotionValue,
} from "motion/react";

import { useAuth } from "../auth/AuthProvider";
import { BlobFallback } from "../components/landing/BlobFallback";
import {
  CommitStripGraphic,
  EnvKeysGraphic,
  RollbackGraphic,
  ZipDropGraphic,
} from "../components/landing/FeatureGraphics";
import { Reveal } from "../components/landing/Reveal";
import { SitePreview } from "../components/landing/SitePreview";
import { Button } from "../components/ui/button";
import { ThemeToggle } from "../components/ui/theme-toggle";
import { Wordmark } from "../components/ui/wordmark";
import { cn } from "../lib/cn";
import { dashboardOrigin } from "../lib/host";
import {
  DURATION,
  EASE,
  SPRING,
  fadeUpVariants,
  liquidRevealVariants,
  staggerVariants,
  useCanHover,
  useCanRenderWebGL,
} from "../lib/motion";

// Lazy: the three.js/@react-three/fiber chunk is only fetched once
// `useCanRenderWebGL()` says yes. Shared between Hero and CallToAction so
// both instances come from the same chunk instead of two.
const LiquidBlob = lazy(() => import("../components/landing/LiquidBlob"));

/**
 * Whether the page has scrolled past the hero. The header is transparent -
 * no border, no shadow, no fill - while it sits directly on the hero, and
 * only becomes the floating bordered bar once there is page content behind
 * it for that chrome to separate it from.
 */
function useScrolled(threshold = 8): boolean {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    function onScroll() {
      setScrolled(window.scrollY > threshold);
    }
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [threshold]);

  return scrolled;
}

/**
 * Whether the header should be off-screen right now: hidden once scrolling
 * down past `threshold`, shown again the moment the scroll direction
 * reverses, and always shown near the top regardless of direction so it
 * never disappears while someone is still reading the hero. `useScroll` +
 * `useMotionValueEvent` reads the scroll position without a `scroll`
 * listener re-rendering the component on every frame - only the direction
 * change itself triggers a re-render, via the returned boolean.
 */
function useHideOnScroll(threshold = 120): boolean {
  const { scrollY } = useScroll();
  const [hidden, setHidden] = useState(false);

  useMotionValueEvent(scrollY, "change", (latest) => {
    const previous = scrollY.getPrevious() ?? 0;
    if (latest < threshold) {
      setHidden(false);
      return;
    }
    setHidden(latest > previous);
  });

  return hidden;
}

/**
 * The landing is served from the apex; the dashboard, /login and /register
 * live on the `app.` subdomain. A router `<Link>` cannot cross that boundary
 * - it would only ever change the path on whichever host the landing happens
 * to be running on - so every link into the dashboard is a real anchor to
 * this instead. On localhost, where there is no `app.` subdomain,
 * `dashboardOrigin()` resolves to the same origin the landing is already on.
 */
function dashboardHref(path: string): string {
  return `${dashboardOrigin()}${path}`;
}


/**
 * A small pull toward the pointer on the one button this whole page exists
 * for. Gated behind real hover support - there is no "distance from the
 * pointer" for this to react to on a touch screen, so the wrapper is inert
 * there and the button behaves like a plain link.
 */
function MagneticCta({ children }: { children: ReactNode }) {
  const canHover = useCanHover();
  const ref = useRef<HTMLDivElement>(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const springX = useSpring(x, SPRING);
  const springY = useSpring(y, SPRING);

  function handleMouseMove(event: React.MouseEvent<HTMLDivElement>) {
    if (!canHover || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    // A quarter of the offset from centre, not the full distance - the
    // button should lean toward the pointer, not chase it.
    x.set((event.clientX - (rect.left + rect.width / 2)) * 0.25);
    y.set((event.clientY - (rect.top + rect.height / 2)) * 0.25);
  }

  function handleMouseLeave() {
    x.set(0);
    y.set(0);
  }

  return (
    <motion.div
      ref={ref}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      style={canHover ? { x: springX, y: springY } : undefined}
      className="inline-flex"
    >
      {children}
    </motion.div>
  );
}

/**
 * One word of a "liquid wipe" headline reveal. The outer span is the mask -
 * `overflow-hidden`, never touched by the animation itself - and the inner
 * one is what moves: translated up from below AND relaxing out of a
 * vertical squash, which is what reads as liquid settling into place rather
 * than a plain slide-up. Both properties are `transform` only (see
 * `liquidRevealVariants` in lib/motion.ts for why that constraint exists).
 * No `initial`/`animate` here on purpose - it inherits "visible" from
 * whichever ancestor stagger container triggers it.
 */
function LiquidWord({
  children,
  reduce,
  className = "",
}: {
  children: ReactNode;
  reduce: boolean;
  className?: string;
}) {
  return (
    <span className="inline-block overflow-hidden">
      <motion.span
        variants={liquidRevealVariants(reduce)}
        style={{ transformOrigin: "bottom" }}
        className={cn("inline-block", className)}
      >
        {children}
      </motion.span>
    </span>
  );
}

/**
 * A floating, product-native visual for the hero: `SitePreview`'s browser
 * mockup - real URL shape, real status tokens, the product's own furniture -
 * as the hero's interactive centrepiece instead of an unused component.
 * Tilts in 3D toward the pointer with actual spring physics (the same
 * `useMotionValue` + `useSpring(SPRING)` pattern `MagneticCta` already
 * established, not a CSS transition standing in for one), and settles back
 * to flat the instant the pointer leaves.
 *
 * The rotation range is deliberately small (max 9deg): a product screenshot
 * that flips around like a playing card stops reading as a screenshot. The
 * inner content shifts a few px counter to the tilt - real depth-parallax,
 * not just a flat plane rotating - which is what makes it read as a card
 * lifting off the page rather than a picture tilting in its frame.
 */
function HeroPreviewCard() {
  const canHover = useCanHover();
  const reduce = !!useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);

  const rawRotateX = useMotionValue(0);
  const rawRotateY = useMotionValue(0);
  const rotateX = useSpring(rawRotateX, SPRING);
  const rotateY = useSpring(rawRotateY, SPRING);
  const liftX = useSpring(useTransform(rawRotateY, [-9, 9], [-7, 7]), SPRING);
  const liftY = useSpring(useTransform(rawRotateX, [-9, 9], [7, -7]), SPRING);

  const tiltActive = canHover && !reduce;

  function onMove(event: React.MouseEvent<HTMLDivElement>) {
    if (!tiltActive || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const px = (event.clientX - rect.left) / rect.width - 0.5;
    const py = (event.clientY - rect.top) / rect.height - 0.5;
    rawRotateY.set(px * 18);
    rawRotateX.set(py * -18);
  }

  function onLeave() {
    rawRotateX.set(0);
    rawRotateY.set(0);
  }

  return (
    <motion.div variants={fadeUpVariants(reduce, 24)} className="mt-16 w-full max-w-xl">
      <div style={{ perspective: 1200 }}>
        <motion.div
          ref={ref}
          onMouseMove={onMove}
          onMouseLeave={onLeave}
          style={tiltActive ? { rotateX, rotateY, transformStyle: "preserve-3d" } : undefined}
          className="relative"
        >
          <motion.div style={tiltActive ? { x: liftX, y: liftY } : undefined}>
            <SitePreview />
          </motion.div>
          {/* A soft brand-coloured glow beneath the card, so the tilt reads
              as lifting off the page rather than a flat image rotating in
              place. */}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -inset-x-6 -bottom-6 -z-10 h-16 rounded-full bg-primary/25 blur-2xl"
          />
        </motion.div>
      </div>
    </motion.div>
  );
}

/**
 * The hero.
 *
 * Centred, not left-aligned-with-a-blob-on-the-right - the earlier
 * composition hugged the left edge of a 7xl container with the right half
 * given to the WebGL blob, which read as off-balance on anything narrower
 * than a very wide desktop. Everything sits on one centre line: badge,
 * headline, subhead, CTAs, and now the preview card below them.
 *
 * The blob is a grounding glow the button row sits on rather than a large
 * object beside the text - anchored low and centred, behind nothing that has
 * to be read. `useCanRenderWebGL()` (lib/motion.ts) gates it: reduced
 * motion, a coarse pointer, a narrow viewport, or no WebGL support at all
 * fall back to `BlobFallback`'s static gradient, which shares the same
 * tokens so the page never looks broken while deciding.
 *
 * Entrance: one stagger container (badge, headline, subhead, CTA row,
 * preview card), and the headline is itself a nested stagger container for
 * its own words (`LiquidWord`, one per word, its own liquid-wipe reveal) - a
 * parent's `animate` cascades to any descendant with its own `variants`, so
 * triggering "visible" once at the top plays the whole sequence in order.
 *
 * Two motion techniques beyond the entrance itself:
 *  - A scroll-linked parallax on the decorative layer only (`useScroll` +
 *    `useTransform`, straight out of motion-patterns). Deliberately
 *    background-only - it never touches content, gates nothing, and pins
 *    nothing, which is what keeps it categorically different from the
 *    pinned scroll-jacking this redesign already removed from "How it works".
 *  - `HeroPreviewCard`, below: real spring-physics pointer tilt on the
 *    product's own browser-chrome mockup, the hero's interactive centrepiece.
 * Both collapse to 0 under reduced motion, matching this file's existing
 * hard-skip convention rather than merely slowing down.
 */
function Hero() {
  const { session, loading } = useAuth();
  const reduce = !!useReducedMotion();
  const canRenderWebGL = useCanRenderWebGL();
  const sectionRef = useRef<HTMLDivElement>(null);

  const { scrollYProgress } = useScroll({
    target: sectionRef,
    offset: ["start start", "end start"],
  });
  const glowY = useTransform(scrollYProgress, [0, 1], [0, reduce ? 0 : 70]);
  const blobY = useTransform(scrollYProgress, [0, 1], [0, reduce ? 0 : 140]);

  return (
    <section
      ref={sectionRef}
      className="relative flex min-h-dvh items-center justify-center overflow-hidden pt-28 pb-20 text-center"
    >
      {/* Decorative only, and hidden from assistive tech: these carry no
          meaning, they set a temperature. Symmetric either side of centre
          now, where the old asymmetric placement made sense beside
          left-aligned text and would otherwise pull the eye off-centre. */}
      <motion.div
        aria-hidden="true"
        style={{ y: glowY }}
        className="pointer-events-none absolute inset-0 -z-20"
      >
        <div className="absolute -top-36 left-1/2 size-160 -translate-x-1/2 rounded-full bg-primary/12 blur-[120px]" />
        <div className="absolute top-1/3 -left-28 size-88 rounded-full bg-accent-vivid/18 blur-[100px]" />
        <div className="absolute top-1/3 -right-28 size-88 rounded-full bg-primary/15 blur-[100px]" />
      </motion.div>

      {/* The blob, now a grounding glow the button row sits on rather than a
          large object beside the text - centred, low, and behind nothing
          that has to be read. Sized well past the button row's own footprint
          on purpose: the CTAs are opaque pills at z-10, so anything directly
          behind them is fully hidden regardless of the blob's own size or
          opacity - a blob sized to roughly match the buttons was therefore
          mostly invisible, hidden under exactly the two shapes sitting on
          top of it. This is large enough that most of it falls in the open
          margin around the buttons instead, at full opacity - the dimming
          this had was fighting the same problem from the other direction and
          made it worse, not better. */}
      <motion.div
        aria-hidden="true"
        style={{ y: blobY }}
        className="pointer-events-none absolute bottom-[-6%] left-1/2 -z-10 size-[130vw] max-w-200 -translate-x-1/2 sm:size-[75vw] lg:size-[46vw]"
      >
        {canRenderWebGL ? (
          <Suspense fallback={<BlobFallback />}>
            <LiquidBlob />
          </Suspense>
        ) : (
          <BlobFallback />
        )}
      </motion.div>

      <div className="relative z-10 mx-auto w-full max-w-4xl px-6 sm:px-8">
        <motion.div
          className="flex flex-col items-center"
          variants={staggerVariants(reduce, 0.12)}
          initial="hidden"
          animate="visible"
        >
          <motion.p
            variants={fadeUpVariants(reduce, 10)}
            className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium text-muted shadow-sm"
          >
            <span className="size-1.5 rounded-full bg-success" />
            Fast <span aria-hidden="true">&middot;</span> Secure <span aria-hidden="true">&middot;</span> Global
          </motion.p>

          {/* Still oversized, now centred rather than asymmetric - a
              balanced line length reads as intentional for centre-aligned
              display type the way the old ragged-right one only worked
              left-aligned. font-display (Bricolage Grotesque) rather than
              the body's Inter, the one place on the page that
              size/character contrast gets pushed this far. */}
          <motion.h1
            variants={staggerVariants(reduce, 0.06)}
            className="mt-8 text-[15vw] leading-[0.86] font-semibold tracking-tight text-balance text-text font-display sm:text-[9vw] lg:text-[clamp(4rem,6.5vw,8rem)]"
          >
            <LiquidWord reduce={reduce}>Deploy</LiquidWord>{" "}
            <LiquidWord reduce={reduce}>static</LiquidWord>{" "}
            <br className="hidden sm:block" />
            <LiquidWord reduce={reduce}>sites</LiquidWord>{" "}
            <LiquidWord reduce={reduce}>in</LiquidWord>{" "}
            <LiquidWord reduce={reduce} className="text-accent">
              seconds
            </LiquidWord>
            .
          </motion.h1>

          <motion.p
            variants={fadeUpVariants(reduce, 12)}
            className="mt-8 max-w-xl text-lg leading-relaxed text-muted sm:text-xl"
          >
            Push a zip or a GitHub repo. Get a public URL. Roll back with one click.
          </motion.p>

          <motion.div
            variants={fadeUpVariants(reduce, 12)}
            className="mt-10 flex flex-wrap items-center justify-center gap-3"
          >
            {/* `variant="primary"` - the one solid brand colour, and the
                only filled button on the page. The magnetic pull marks this
                specific button as the one action this whole page exists for,
                which is also why it is not on the secondary button beside it. */}
            <MagneticCta>
              <a href={dashboardHref("/login")}>
                <Button variant="primary" size="lg" icon={<ArrowRight />}>
                  Get started
                </Button>
              </a>
            </MagneticCta>
            <a href="#how-it-works">
              <Button variant="secondary" size="lg" icon={<PlayCircle />}>
                See how it works
              </Button>
            </a>
          </motion.div>

          {!loading && session && (
            <p className="mt-8 text-sm text-muted">
              You are signed in.{" "}
              <Link to="/projects" className="text-primary underline-offset-4 hover:underline">
                Open your dashboard
              </Link>
            </p>
          )}

          <HeroPreviewCard />
        </motion.div>
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

/**
 * Mirrors the browser-chrome frame `SitePreview` uses, but with a body that
 * swaps per active step - unlike the shared `SitePreview` (used as-is in
 * Features), this one exists only for this scrollytelling moment, so making
 * it reactive here never touches the component Features also renders.
 * `AnimatePresence mode="wait"` because the three states are mutually
 * exclusive scenes, not overlapping layers - the outgoing one should finish
 * leaving before the next starts arriving, same principle as the step text
 * beside it.
 */
function HowItWorksMockup({ activeStep }: { activeStep: number }) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-border bg-surface shadow-lg">
      <div className="flex items-center gap-2 border-b border-border bg-surface-sunken px-4 py-3">
        <span className="size-2.5 rounded-full bg-destructive/70" />
        <span className="size-2.5 rounded-full bg-warning/70" />
        <span className="size-2.5 rounded-full bg-success/70" />
        <div className="ml-2 flex min-w-0 flex-1 items-center gap-1.5 rounded-md bg-surface px-2.5 py-1.5 font-mono text-[11px] text-muted">
          <Lock className="size-3 shrink-0" aria-hidden="true" />
          <span className="truncate">blue-forest-4821.getdropbin.xyz</span>
        </div>
      </div>

      <div className="relative h-52 p-5">
        <AnimatePresence mode="wait">
          {activeStep === 0 && (
            <motion.div
              key="upload"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
              className="flex h-full flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border-strong text-muted"
            >
              <span className="relative flex size-10 items-center justify-center rounded-full bg-accent-subtle text-accent">
                <Upload className="size-5" aria-hidden="true" />
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent/40" />
              </span>
              <p className="text-sm">Uploading site.zip&hellip;</p>
            </motion.div>
          )}

          {activeStep === 1 && (
            <motion.div
              key="build"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
              className="flex h-full flex-col items-center justify-center gap-4"
            >
              <span className="inline-flex items-center gap-2 rounded-full bg-warning-subtle px-3 py-1.5 text-xs font-medium text-warning-subtle-fg">
                <RefreshCw className="size-3.5 animate-spin" aria-hidden="true" />
                Building
              </span>
              <p className="text-sm text-muted">Running your GitHub Actions workflow&hellip;</p>
            </motion.div>
          )}

          {activeStep === 2 && (
            <motion.div
              key="rollback"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.25 }}
              className="flex h-full flex-col justify-center gap-2.5"
            >
              <div className="flex items-center justify-between gap-2 rounded-md border border-border bg-surface-sunken px-3 py-2.5">
                <span className="font-mono text-xs text-text">9f2c1ab</span>
                <span className="text-[11px] text-muted">2 min ago</span>
              </div>
              <ArrowDown className="mx-auto size-4 text-muted" aria-hidden="true" />
              <div className="flex items-center justify-between gap-2 rounded-md border border-success bg-surface px-3 py-2.5">
                <span className="font-mono text-xs text-text">4a91f2c</span>
                <span className="flex items-center gap-1.5 rounded-full bg-success-subtle px-2 py-0.5 text-[11px] font-medium text-success-subtle-fg">
                  <span className="size-1.5 rounded-full bg-success" />
                  Live
                </span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

/**
 * Three steps, told by a step selector next to a live preview that reacts to
 * whichever one is current - not the earlier pinned, scroll-scrubbed
 * timeline. That version took the scroll wheel over for the length of the
 * section (GSAP `pin: true` + `scrub`): uncomfortable on a trackpad, worse
 * on a phone, and it moved on its own timetable instead of the reader's.
 * A click-driven stepper keeps the same "watch it change" moment without
 * ever taking scrolling away from anyone.
 *
 * Auto-advance is the one bit of motion-for-its-own-sake this keeps, and it
 * is deliberately mild: a slow interval that stops dead the instant someone
 * clicks a step (autoplay fighting a reader who is actively steering is the
 * opposite of helpful), pauses the moment the section leaves view instead of
 * ticking along invisibly, and is skipped outright under reduced motion,
 * where the first step just sits still until clicked.
 */
function HowItWorks() {
  const reduce = !!useReducedMotion();
  const [activeStep, setActiveStep] = useState(0);
  const [autoplay, setAutoplay] = useState(true);
  const sectionRef = useRef<HTMLDivElement>(null);
  const inView = useInView(sectionRef, { amount: 0.5 });

  useEffect(() => {
    if (reduce || !autoplay || !inView) return;
    const id = window.setInterval(() => {
      setActiveStep((step) => (step + 1) % STEPS.length);
    }, 3400);
    return () => window.clearInterval(id);
  }, [reduce, autoplay, inView]);

  return (
    <section id="how-it-works" className="border-y border-border bg-surface">
      <div ref={sectionRef} className="mx-auto max-w-7xl px-6 py-24 sm:px-8 sm:py-28">
        <Reveal className="max-w-2xl">
          <p className="text-xs font-semibold tracking-[0.13em] text-accent uppercase">How it works</p>
          <h2 className="mt-4 font-display text-3xl font-semibold tracking-[-0.035em] text-balance text-text sm:text-4xl">
            Three steps, and no configuration to learn.
          </h2>
        </Reveal>

        <div className="mt-14 grid gap-10 lg:grid-cols-[minmax(0,26rem)_1fr] lg:items-center lg:gap-16">
          {/* Each step is its own button, not a decorative list - a reader
              who already knows which step they want should not have to wait
              for autoplay to get there. Clicking one also turns autoplay off
              for good, not just for a beat: resuming on its own after a
              deliberate choice would undo the very control this replaced
              scroll-jacking to give back. */}
          <ol className="flex flex-col gap-2">
            {STEPS.map(({ Icon, number, title, body }, i) => {
              const active = i === activeStep;
              return (
                <li key={number}>
                  <button
                    type="button"
                    onClick={() => {
                      setActiveStep(i);
                      setAutoplay(false);
                    }}
                    aria-current={active ? "step" : undefined}
                    className={cn(
                      "flex w-full items-start gap-4 rounded-xl border p-4 text-left transition-colors duration-200",
                      active
                        ? "border-accent/30 bg-accent-subtle"
                        : "border-transparent hover:bg-surface-hover",
                    )}
                  >
                    <span
                      aria-hidden="true"
                      className={cn(
                        "flex size-10 shrink-0 items-center justify-center rounded-full font-mono text-sm font-bold transition-colors duration-200",
                        active ? "bg-accent text-accent-fg" : "bg-surface-sunken text-muted",
                      )}
                    >
                      {number}
                    </span>
                    <span className="min-w-0 pt-1">
                      <span className="flex items-center gap-2 text-base font-semibold tracking-tight text-text">
                        <Icon className="size-4 shrink-0 text-accent" aria-hidden="true" />
                        {title}
                      </span>
                      <span className="mt-1.5 block text-sm leading-relaxed text-muted">{body}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>

          <div>
            <HowItWorksMockup activeStep={activeStep} />
            <p className="mt-4 text-center text-sm text-muted">
              A finished deployment: the public URL, its status, and the commit it came from.
            </p>
          </div>
        </div>
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
const FEATURES: {
  Graphic: (props?: { size?: "md" | "lg" }) => React.ReactElement;
  title: string;
  body: string;
}[] = [
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

/**
 * Bento spans, by index - not a property of each feature, since it is a
 * layout decision, not a fact about "GitHub auto-deploy" itself. Index 1
 * (GitHub auto-deploy) is the featured tile: the auto-deploy-on-push loop is
 * the single feature most likely to be why someone signs up, so it gets the
 * 2x2 corner and the bigger graphic (`size="lg"`, threaded through to
 * `Frame` in FeatureGraphics.tsx) instead of sitting as a fourth equal box.
 */
const BENTO_SPAN = [
  "sm:col-span-1 lg:col-span-1 lg:row-span-1",
  "sm:col-span-2 lg:col-span-2 lg:row-span-2",
  "sm:col-span-1 lg:col-span-1 lg:row-span-1",
  "sm:col-span-2 lg:col-span-3",
];

/**
 * The ambient "spotlight" glow that tracks the pointer across a card - a
 * radial gradient positioned at the pointer's own coordinates via
 * `useMotionTemplate`, which builds the CSS string itself from motion
 * values so the gradient's position updates without a React re-render per
 * pixel of mouse movement. An absolutely-positioned overlay, not the card's
 * own background, so it can sit above the border and below the content
 * without either of them needing to know it exists. Fades in on hover and
 * back out on leave; never mounted at all without real hover support.
 */
function CardSpotlight({
  x,
  y,
  opacity,
}: {
  x: MotionValue<number>;
  y: MotionValue<number>;
  opacity: MotionValue<number>;
}) {
  const background = useMotionTemplate`radial-gradient(320px circle at ${x}px ${y}px, var(--color-primary) 0%, transparent 75%)`;
  return (
    <motion.div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 -z-10 rounded-xl"
      style={{ background, opacity }}
    />
  );
}

function FeatureCard({
  Graphic,
  title,
  body,
  featured = false,
  className = "",
}: (typeof FEATURES)[number] & { featured?: boolean; className?: string }) {
  const canHover = useCanHover();
  const reduce = !!useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);

  const mouseX = useMotionValue(0);
  const mouseY = useMotionValue(0);
  const glowOpacity = useMotionValue(0);

  function onMove(event: React.MouseEvent<HTMLDivElement>) {
    if (!canHover || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    mouseX.set(event.clientX - rect.left);
    mouseY.set(event.clientY - rect.top);
  }

  return (
    <motion.article
      ref={ref}
      onMouseMove={onMove}
      onMouseEnter={() => canHover && glowOpacity.set(0.22)}
      onMouseLeave={() => canHover && glowOpacity.set(0)}
      variants={fadeUpVariants(reduce, 14)}
      whileHover={canHover ? { y: -6 } : undefined}
      transition={SPRING}
      className={cn(
        "relative overflow-hidden rounded-xl border border-border bg-surface p-5 transition-colors duration-300 hover:border-primary/30",
        featured && "flex flex-col justify-between",
        className,
      )}
    >
      {canHover && <CardSpotlight x={mouseX} y={mouseY} opacity={glowOpacity} />}
      <Graphic size={featured ? "lg" : undefined} />
      <div className={featured ? "mt-auto" : undefined}>
        <h3 className={cn("mt-5 font-semibold tracking-tight text-text", featured ? "text-xl" : "text-base")}>
          {title}
        </h3>
        <p className={cn("mt-2 leading-relaxed text-muted", featured ? "max-w-sm text-base" : "text-sm")}>{body}</p>
      </div>
    </motion.article>
  );
}

function Features() {
  const reduce = !!useReducedMotion();

  return (
    <section id="features" className="mx-auto max-w-7xl px-6 py-24 sm:px-8 sm:py-28">
      <Reveal className="max-w-2xl">
        <p className="text-xs font-semibold tracking-[0.13em] text-accent uppercase">Features</p>
        <h2 className="mt-4 font-display text-3xl font-semibold tracking-[-0.035em] text-balance text-text sm:text-4xl">
          The parts you actually touch.
        </h2>
      </Reveal>

      {/* Bento, not a uniform grid: one featured tile at 2x2 (see
          BENTO_SPAN), the rest sized to what is actually left over. Cascades
          in on scroll, one tile after another, rather than all four popping
          in together. */}
      <motion.div
        className="mt-12 grid grid-cols-1 gap-6 sm:grid-cols-3 lg:auto-rows-[1fr] lg:grid-cols-3"
        variants={staggerVariants(reduce, 0.08, 0.1)}
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-80px" }}
      >
        {FEATURES.map((feature, i) => (
          <FeatureCard key={feature.title} {...feature} featured={i === 1} className={BENTO_SPAN[i]} />
        ))}
      </motion.div>
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

const STATE_LABEL: Record<Cell["state"], string> = { yes: "Yes", no: "No", partial: "Partial" };
const STATE_FRACTION: Record<Cell["state"], number> = { yes: 1, partial: 0.5, no: 0 };
const STATE_TONE: Record<Cell["state"], string> = {
  yes: "bg-success",
  partial: "bg-warning",
  no: "bg-destructive",
};

/**
 * A short track that fills to the state's fraction rather than a static
 * icon - the fill is what carries the "liquid" language into the one part
 * of the page that is pure data. `scaleX` from a `left` transform-origin,
 * not a `width` change, so this is transform/opacity like everything else
 * animated on the page. Still paired with a visually hidden word: colour
 * (and fill amount) is never the only carrier of the state.
 */
/**
 * No `whileInView`/`viewport` of its own on purpose - eighteen of these
 * (6 rows x 3 columns) each running an independent IntersectionObserver
 * proved unreliable in practice (one column's bars would silently never
 * fire). `variants` alone, inheriting "visible" by propagation from the
 * `<tbody>`'s single `whileInView` a few levels up, is the same nested-
 * stagger mechanism already used for the hero's words and the feature
 * cards - one observer for the whole table instead of eighteen.
 */
function FillMark({ state, reduce }: { state: Cell["state"]; reduce: boolean }) {
  const fraction = STATE_FRACTION[state];

  return (
    <span className="inline-flex flex-col items-center gap-1.5">
      <span className="relative h-1.5 w-10 overflow-hidden rounded-full bg-border">
        <motion.span
          className={cn("absolute inset-0 rounded-full", STATE_TONE[state])}
          style={{ transformOrigin: "left" }}
          variants={{
            hidden: { scaleX: reduce ? fraction : 0 },
            visible: { scaleX: fraction, transition: { duration: reduce ? 0 : 0.7, ease: EASE } },
          }}
        />
      </span>
      <span className="sr-only">{STATE_LABEL[state]}</span>
    </span>
  );
}

/**
 * The row cascade, split out because a `<tbody>` needs its own
 * `useReducedMotion` read and `motion.tbody`/`motion.tr` directly - a
 * generic wrapper would have to sit between `<table>` and `<tbody>`, which
 * is not valid table markup.
 *
 * Rows are click-to-expand: collapsed shows only the fill marks, and
 * clicking a row reveals each column's note underneath. The note is
 * conditionally rendered (removed from the DOM when collapsed, not just
 * faded to zero height) so the row's own height actually collapses instead
 * of leaving reserved blank space - a `scaleY` trick only hides paint, it
 * does not reclaim layout space, which a real accordion needs to do.
 */
function ComparisonBody() {
  const reduce = !!useReducedMotion();
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <motion.tbody
      variants={staggerVariants(reduce, 0.06, 0.1)}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-80px" }}
    >
      {COMPARISON.map(({ feature, cells }) => {
        const isOpen = expanded === feature;
        return (
          <motion.tr
            key={feature}
            variants={fadeUpVariants(reduce, 10)}
            whileHover={{ scale: 1.01 }}
            transition={SPRING}
            style={{ transformOrigin: "center" }}
            className="relative cursor-pointer border-t border-border transition-[background-color,box-shadow] duration-300 hover:bg-surface-hover hover:shadow-[0_0_0_1px_var(--color-primary),0_10px_28px_-10px_var(--color-primary)]"
            onClick={() => setExpanded(isOpen ? null : feature)}
            aria-expanded={isOpen}
          >
            <th scope="row" className="py-5 pr-4 text-left align-top font-medium text-text">
              <span className="flex items-center gap-2">
                <ChevronDown
                  className={cn("size-3.5 shrink-0 text-muted transition-transform", isOpen && "rotate-180")}
                  aria-hidden="true"
                />
                {feature}
              </span>
            </th>
            {cells.map((cell, i) => (
              <td
                key={COLUMNS[i]}
                className={cn("px-3 py-5 text-center align-top", i === 0 && "bg-surface-sunken")}
              >
                <FillMark state={cell.state} reduce={reduce} />
                <AnimatePresence initial={false}>
                  {isOpen && cell.note && (
                    <motion.p
                      key="note"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: reduce ? 0 : DURATION.fast, ease: EASE }}
                      className="mx-auto mt-2 max-w-[22ch] text-xs leading-snug text-balance text-muted"
                    >
                      {cell.note}
                    </motion.p>
                  )}
                </AnimatePresence>
              </td>
            ))}
          </motion.tr>
        );
      })}
    </motion.tbody>
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
          <h2 className="font-display text-3xl font-semibold tracking-[-0.035em] text-balance text-text sm:text-4xl">
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
            <ComparisonBody />
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
  const reduce = !!useReducedMotion();
  const canRenderWebGL = useCanRenderWebGL();

  return (
    <section className="relative overflow-hidden">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-20">
        <div className="absolute -top-44 left-1/2 size-144 -translate-x-1/2 rounded-full bg-accent-vivid/18 blur-[120px]" />
        <div className="absolute -bottom-32 right-[6%] size-104 rounded-full bg-primary/14 blur-[110px]" />
      </div>

      {/* The blob returns, smaller and full-bleed, as a bookend to the hero
          rather than a second unrelated moment - same component, same
          `useCanRenderWebGL` gate and static fallback. */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10 flex items-center justify-center">
        <div className="size-[70vw] max-w-105 opacity-70">
          {canRenderWebGL ? (
            <Suspense fallback={<BlobFallback />}>
              <LiquidBlob />
            </Suspense>
          ) : (
            <BlobFallback />
          )}
        </div>
      </div>

      {/* A scrim between the blob and the text - full-bleed behind a
          headline is the one placement on the page where the blob's own
          brightest colours could otherwise sit directly under small text,
          which the hero's off-center placement never risked. */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 z-[-1] bg-bg/55" />

      <div className="relative mx-auto max-w-3xl px-6 py-28 text-center sm:px-8 sm:py-32">
        {/* Matches the hero's new scale, so the two warm moments bookend the
            page at the same visual weight instead of the closer reading as an
            afterthought. Same word-cascade liquid-wipe reveal as the hero
            headline, triggered on scroll rather than on mount. */}
        <motion.h2
          variants={staggerVariants(reduce, 0.1)}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-80px" }}
          className="font-display text-5xl font-semibold tracking-[-0.045em] text-balance text-text sm:text-6xl"
        >
          <LiquidWord reduce={reduce}>Start</LiquidWord> <LiquidWord reduce={reduce}>deploying.</LiquidWord>
        </motion.h2>

        {/* Spring-driven, not `Reveal`'s tween - the deliberate exception on
            this page. lib/motion.ts reserves springs for direct-manipulation
            feedback and keeps scroll entrances on EASE everywhere else; this
            closing moment is the one place a slightly more physical settle
            earns its keep, as the page's last beat rather than its rhythm. */}
        <motion.div
          initial={{ opacity: 0, y: reduce ? 0 : 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={reduce ? { duration: 0 } : { ...SPRING, delay: 0.1 }}
          className="mt-9 flex justify-center"
        >
          {/* Offering to sign in to someone already signed in is a dead end,
              so the button changes rather than the page pretending not to
              know who is reading it. Same "Get started" as the hero, for the
              same reason: /login, not GitHub specifically, is what this
              button leads to. Same magnetic pull as the hero's primary CTA
              too - the page's two real actions should feel like the same
              button, not two different ones that happen to say similar things. */}
          {!loading &&
            (session ? (
              <MagneticCta>
                <a href={dashboardHref("/projects")}>
                  <Button variant="primary" size="lg" icon={<ArrowRight />}>
                    Open your dashboard
                  </Button>
                </a>
              </MagneticCta>
            ) : (
              <MagneticCta>
                <a href={dashboardHref("/login")}>
                  <Button variant="primary" size="lg" icon={<ArrowRight />}>
                    Get started
                  </Button>
                </a>
              </MagneticCta>
            ))}
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: reduce ? 0 : 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={reduce ? { duration: 0 } : { ...SPRING, delay: 0.22 }}
        >
          <p className="mt-6 text-sm text-muted">Free while in beta. No credit card. No lock-in.</p>
        </motion.div>
      </div>
    </section>
  );
}

export function Landing() {
  const { session, loading } = useAuth();
  const scrolled = useScrolled();
  const navHidden = useHideOnScroll();
  const reduce = !!useReducedMotion();

  return (
    <div className="relative min-h-screen bg-bg">
      {/* The header is transparent until scrolled (see below), which means
          whatever is directly behind it shows through. Hero's own decorative
          wash lives inside <section> and starts only below the header, so
          without this the header sat on plain `bg-bg` while the hero right
          under it was visibly tinted - a hard seam exactly where the two
          met. This one wash spans both, painted behind everything at the
          page root instead of inside Hero, so the colour is continuous from
          the very top instead of starting partway down.

          The one gradient on the page: a single two-stop fade from the
          primary token to transparent, not the three raw-palette stops
          reused on the headline and CTA elsewhere in earlier drafts. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-168 bg-linear-to-b from-primary/12 to-transparent blur-3xl"
      />

      {/* Fixed to the top of the viewport rather than scrolling away, so
          "Sign in" and the theme toggle are always one click away no matter
          how far down the page you are.

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
          browser regardless of whether anything actually overflows it.

          The border, shadow and blurred fill only apply once `scrolled` is
          true. Sitting directly on the hero at the very top of the page,
          none of them have anything to do - the header is not separating
          itself from page content yet, since there is none behind it - so
          drawing them there just adds visual noise the hero does not need.
          `border-transparent` rather than no border at all keeps the box's
          size identical in both states, so this never causes a layout
          shift.

          `navHidden` slides the whole sticky wrapper off the top of the
          viewport on `transform` alone (never `top`, which would fight
          `position: sticky` and thrash layout on every frame) - hidden past
          `threshold` while scrolling down, shown again the moment the
          direction reverses, so "Sign in" is never more than one scroll-up
          away. */}
      <motion.div
        className="sticky top-0 z-40 px-3 pt-3 sm:px-6 sm:pt-4"
        animate={{ y: navHidden ? "-150%" : "0%" }}
        transition={{ duration: reduce ? 0 : DURATION.fast, ease: EASE }}
      >
        <header
          className={cn(
            "mx-auto max-w-7xl rounded-full border transition-[background-color,border-color,box-shadow] duration-200",
            scrolled
              ? "border-border bg-surface/95 shadow-lg backdrop-blur-md"
              : "border-transparent bg-transparent shadow-none",
          )}
        >
          <div className="flex items-center px-6 py-3.5 sm:px-8">
            <Link to="/" aria-label="Dropbin home">
              <Wordmark size="lg" />
            </Link>
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
              {/* `size="md"` (h-9/36px), not "sm" (h-8/32px): ThemeToggle next
                  to it renders `size="icon"`, which is also 36px, and the
                  two need to match or they read as misaligned even though
                  both sit on the same flex baseline. */}
              {!loading &&
                (session ? (
                  <a href={dashboardHref("/projects")}>
                    <Button variant="secondary" size="md">
                      Open dashboard
                    </Button>
                  </a>
                ) : (
                  <a href={dashboardHref("/login")}>
                    <Button variant="secondary" size="md">
                      Sign in
                    </Button>
                  </a>
                ))}
            </div>
          </div>
        </header>
      </motion.div>

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
        <Reveal className="mx-auto flex max-w-7xl flex-col items-center gap-3 px-6 py-8 text-sm text-muted sm:flex-row sm:justify-between sm:px-8">
          <div className="flex items-center gap-3">
            <Wordmark />
            <span>© {new Date().getFullYear()} Dropbin</span>
          </div>
        </Reveal>
      </footer>
    </div>
  );
}
