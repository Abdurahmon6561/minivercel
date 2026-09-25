import { forwardRef, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "motion/react";
import { ArrowDown, FileArchive, Upload } from "lucide-react";

import { cn } from "../../lib/cn";
import { DURATION, EASE, SPRING } from "../../lib/motion";

/**
 * Four micro-illustrations for the features grid, each a small animated loop
 * of the thing it explains rather than a still screenshot - a build that
 * finishes, a rollback that happens, a file that drops, values that stay
 * masked. Static mockups only ever show one moment; these show the motion
 * the feature is actually about.
 *
 * They speak SitePreview's language rather than a decorative one: the same
 * borders, the same surface/surface-sunken pairing, the same mono for machine
 * text, and the real status tokens the dashboard uses for Ready, Building and
 * Failed. Nothing here is drawn - it is the product's own furniture at a small
 * size, so a reader recognises the screens before they ever sign in.
 *
 * Built from DOM and existing utilities instead of SVG. There is no new CSS to
 * compile and no path data to ship, which is what keeps four illustrations
 * inside a sub-kilobyte budget.
 *
 * All four are aria-hidden. Each sits directly above a title and a sentence
 * that say the same thing in words, so exposing them would only make a screen
 * reader announce "sk" followed by eight bullets.
 */

/**
 * Gates every loop below behind both `prefers-reduced-motion` and actual
 * visibility. A loop that runs on a fixed interval whether anyone is looking
 * or not is wasted work off-screen (each card keeps its own timer) and, for
 * reduced motion, an animation nobody asked to keep watching - so this
 * freezes each graphic on its first, calmest frame in either case rather
 * than merely slowing it down.
 */
function useShouldLoop(ref: React.RefObject<Element | null>): boolean {
  const reduce = useReducedMotion();
  const inView = useInView(ref, { amount: 0.4 });
  return !reduce && inView;
}

/** Shared frame, so the graphics align within whichever bento tile they land
 * in - `size="lg"` for the one featured tile that gets a bigger footprint,
 * `"md"` (the original height) everywhere else. Forwards its ref so each
 * graphic can gate its own loop on its own visibility. */
const Frame = forwardRef<
  HTMLDivElement,
  { children: React.ReactNode; dashed?: boolean; size?: "md" | "lg" }
>(function Frame({ children, dashed = false, size = "md" }, ref) {
  return (
    <div
      ref={ref}
      aria-hidden="true"
      className={`relative flex ${size === "lg" ? "h-56" : "h-36"} flex-col justify-center gap-2 overflow-hidden rounded-lg border bg-surface-sunken p-3 ${
        dashed ? "items-center border-dashed border-border-strong" : "border-border"
      }`}
    >
      {children}
    </div>
  );
});

/** One row of product furniture: mono identifier on the left, status on the right. */
function Row({ mono, children }: { mono: string; children?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-md border border-border bg-surface px-2.5 py-2">
      <span className="font-mono text-[11px] text-text">{mono}</span>
      {children}
    </div>
  );
}

function Badge({ tone, children }: { tone: "success" | "warning" | "destructive"; children: React.ReactNode }) {
  const tones = {
    success: "bg-success-subtle text-success-subtle-fg",
    warning: "bg-warning-subtle text-warning-subtle-fg",
    destructive: "bg-destructive-subtle text-destructive-subtle-fg",
  };
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${tones[tone]}`}>{children}</span>
  );
}

/**
 * Zip upload: the file actually drops, on a loop - rises out of frame,
 * settles onto the zone with a small tilt, holds so it can be read, then
 * lifts away to drop again. The drop zone itself breathes gently underneath,
 * a soft accent glow standing in for "waiting for a file".
 */
export function ZipDropGraphic({ size }: { size?: "md" | "lg" } = {}) {
  const ref = useRef<HTMLDivElement>(null);
  const loop = useShouldLoop(ref);

  return (
    <Frame dashed size={size} ref={ref}>
      <motion.div
        aria-hidden="true"
        className="pointer-events-none absolute size-20 rounded-full bg-accent-vivid/25 blur-2xl"
        animate={loop ? { opacity: [0.3, 0.7, 0.3], scale: [0.9, 1.05, 0.9] } : { opacity: 0.4 }}
        transition={{ duration: 2.4, repeat: Infinity, ease: EASE }}
      />
      <div className="relative flex flex-col items-center gap-1.5 text-muted">
        <Upload className="size-5" />
        <span className="text-[11px]">Drop to deploy</span>
      </div>
      <motion.div
        className="absolute right-3 bottom-3 flex items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1 shadow-md"
        animate={
          loop
            ? { y: [-22, 0, 0, -22], rotate: [-16, -6, -6, -16], opacity: [0, 1, 1, 0] }
            : { y: 0, rotate: -6, opacity: 1 }
        }
        transition={
          loop
            ? {
                duration: 2.8,
                times: [0, 0.3, 0.82, 1],
                repeat: Infinity,
                ease: EASE,
              }
            : { duration: DURATION.normal, ease: EASE }
        }
      >
        <FileArchive className="size-3 text-accent" />
        <span className="font-mono text-[11px] text-text">site.zip</span>
      </motion.div>
    </Frame>
  );
}

/**
 * GitHub auto-deploy: the middle row actually builds - Building crossfades
 * into Ready and back, on a loop, while the other two rows sit still as
 * context. One row is the whole story; three animating at once would just
 * be noise.
 */
export function CommitStripGraphic({ size }: { size?: "md" | "lg" } = {}) {
  const ref = useRef<HTMLDivElement>(null);
  const loop = useShouldLoop(ref);
  const [building, setBuilding] = useState(true);

  useEffect(() => {
    if (!loop) return;
    const id = window.setInterval(() => setBuilding((b) => !b), 1900);
    return () => window.clearInterval(id);
  }, [loop]);

  return (
    <Frame size={size} ref={ref}>
      <Row mono="7d36a4e">
        <Badge tone="success">Ready</Badge>
      </Row>
      <Row mono="4a91f2c">
        <AnimatePresence mode="wait" initial={false}>
          <motion.span
            key={building ? "building" : "ready"}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: DURATION.fast, ease: EASE }}
          >
            <Badge tone={building ? "warning" : "success"}>{building ? "Building" : "Ready"}</Badge>
          </motion.span>
        </AnimatePresence>
      </Row>
      <Row mono="b02e5d8">
        <Badge tone="destructive">Failed</Badge>
      </Row>
    </Frame>
  );
}

const ROLLBACK_COMMITS = [
  { sha: "9f2c1ab", time: "2 min ago" },
  { sha: "4a91f2c", time: "just now" },
];

/**
 * Rollback: the "Live" badge itself moves, via a shared `layoutId` - not two
 * rows independently fading their own copy of it in and out. Motion tracks
 * the badge's actual position across the re-render and tweens between them
 * with real spring physics, which is what makes this read as one live pill
 * genuinely relocating rather than an old one disappearing while a new one
 * appears in roughly the same place. The arrow's own pulse is the only
 * other motion, so the badge's move stays the one thing pulling focus.
 */
export function RollbackGraphic({ size }: { size?: "md" | "lg" } = {}) {
  const ref = useRef<HTMLDivElement>(null);
  const loop = useShouldLoop(ref);
  const [liveIndex, setLiveIndex] = useState(1);

  useEffect(() => {
    if (!loop) return;
    const id = window.setInterval(() => setLiveIndex((v) => (v === 1 ? 0 : 1)), 2500);
    return () => window.clearInterval(id);
  }, [loop]);

  return (
    <Frame size={size} ref={ref}>
      {ROLLBACK_COMMITS.map((commit, i) => {
        const isLive = i === liveIndex;
        return (
          <div
            key={commit.sha}
            className={cn(
              "flex items-center justify-between gap-2 rounded-md border bg-surface px-2.5 py-2 transition-colors duration-300",
              isLive ? "border-success" : "border-border",
            )}
          >
            <span className="font-mono text-[11px] text-text">{commit.sha}</span>
            {isLive ? (
              <motion.span
                layoutId="rollback-live-badge"
                transition={SPRING}
                className="flex items-center gap-1.5 rounded-full bg-success-subtle px-2 py-0.5 text-[10px] font-medium text-success-subtle-fg"
              >
                <span className="size-1.5 rounded-full bg-success" />
                Live
              </motion.span>
            ) : (
              <span className="text-[10px] text-muted">{commit.time}</span>
            )}
          </div>
        );
      })}
      <motion.div
        aria-hidden="true"
        className="absolute right-3 bottom-3 text-muted"
        animate={loop ? { y: [0, 4, 0] } : { y: 0 }}
        transition={{ duration: 1.1, repeat: Infinity, ease: EASE }}
      >
        <ArrowDown className="size-3.5" />
      </motion.div>
    </Frame>
  );
}

/**
 * Environment variables: the masked values shimmer gently, a stand-in for
 * "this stays encrypted" that a static row of dots cannot communicate on its
 * own. The masking itself is unchanged and still real - the product's actual
 * behaviour, not a stylistic choice - only the emphasis is new.
 */
export function EnvKeysGraphic({ size }: { size?: "md" | "lg" } = {}) {
  const ref = useRef<HTMLDivElement>(null);
  const loop = useShouldLoop(ref);

  return (
    <Frame size={size} ref={ref}>
      {[
        ["API_KEY", "sk••••••••"],
        ["DATABASE_URL", "po••••••••"],
        ["STRIPE_SECRET", "sk••••••••"],
      ].map(([key, masked], i) => (
        <Row key={key} mono={key}>
          <motion.span
            className="font-mono text-[11px] text-muted"
            animate={loop ? { opacity: [0.45, 1, 0.45] } : { opacity: 1 }}
            transition={{ duration: 1.8, repeat: Infinity, ease: EASE, delay: i * 0.25 }}
          >
            {masked}
          </motion.span>
        </Row>
      ))}
    </Frame>
  );
}
