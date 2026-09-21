import { useEffect, useState } from "react";
import { motion, useReducedMotion, type Variants } from "motion/react";

import { EASE } from "../lib/motion";

/**
 * The droplet fills like liquid pooling, then the page reveals. Replaces the
 * earlier video-based BootSplash: once per browser *session* (sessionStorage,
 * not "once per reload" the way the video was), and a hard skip under
 * `prefers-reduced-motion` - no shortened version, matching the rest of the
 * app's convention for that preference.
 *
 * The same drop path `LogoMark` (ui/wordmark.tsx) uses, so the brand mark and
 * this intro are one shape, not two drawings that can drift apart.
 *
 * "Liquid fill" is a `<clipPath>` rect grown via `scaleY` from a bottom
 * `transformOrigin`, not an animated `clip-path`/`mask` property - see
 * lib/motion.ts's `liquidRevealVariants` doc for why: only `transform`/
 * `opacity` are allowed to animate per-frame, and a literal clip-path
 * interpolation would violate that the same way animating `width` would.
 */
const SESSION_KEY = "dropbin-intro-seen";
const FILL_MS = 900;
const HOLD_MS = 150;
const FADE_MS = 300;

const DROP_PATH =
  "M12 5.25c0 0-4.55 6.98-4.55 10.4 0 2.51 2.04 4.55 4.55 4.55s4.55-2.04 4.55-4.55c0-3.42-4.55-10.4-4.55-10.4Z";

const fillVariants: Variants = {
  hidden: { scaleY: 0 },
  visible: { scaleY: 1, transition: { duration: FILL_MS / 1000, ease: EASE } },
};

/** Pure read, same pattern lib/theme.ts's `storedPreference()` already uses
 * for a first-render storage check. */
function alreadySeenThisSession(): boolean {
  try {
    return sessionStorage.getItem(SESSION_KEY) === "1";
  } catch {
    return false;
  }
}

function markSeen(): void {
  try {
    sessionStorage.setItem(SESSION_KEY, "1");
  } catch {
    /* Private mode, or site data blocked. The intro just replays next load
       in that tab - harmless, not worth surfacing. */
  }
}

export function LiquidIntro({ onDone }: { onDone: () => void }) {
  const reduce = useReducedMotion();
  const [fadingOut, setFadingOut] = useState(false);
  const [seen] = useState(alreadySeenThisSession);

  const shouldRender = !seen && !reduce;

  useEffect(() => {
    markSeen();

    if (!shouldRender) {
      onDone();
      return;
    }

    // Matches BootSplash's own scroll lock: `fixed` alone does not stop the
    // page underneath from scrolling if a visitor drags/wheels during it.
    const html = document.documentElement;
    const previousOverflow = html.style.overflow;
    html.style.overflow = "hidden";

    const fadeTimer = window.setTimeout(() => setFadingOut(true), FILL_MS + HOLD_MS);
    const doneTimer = window.setTimeout(onDone, FILL_MS + HOLD_MS + FADE_MS);

    return () => {
      window.clearTimeout(fadeTimer);
      window.clearTimeout(doneTimer);
      html.style.overflow = previousOverflow;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldRender]);

  if (!shouldRender) return null;

  return (
    <motion.div
      className="fixed inset-0 z-100 flex items-center justify-center bg-bg"
      initial={{ opacity: 1 }}
      animate={{ opacity: fadingOut ? 0 : 1 }}
      transition={{ duration: FADE_MS / 1000, ease: EASE }}
    >
      <svg viewBox="0 0 24 24" className="size-16 sm:size-20" aria-hidden="true">
        <defs>
          <clipPath id="liquid-intro-clip">
            <motion.rect
              x="0"
              y="0"
              width="24"
              height="24"
              style={{ transformOrigin: "0px 24px" }}
              variants={fillVariants}
              initial="hidden"
              animate="visible"
            />
          </clipPath>
        </defs>
        {/* The outline is visible from the first frame, so the shape reads
            immediately - the fill is what animates, not the reveal of the
            shape itself. */}
        <path d={DROP_PATH} className="fill-none stroke-primary/30" strokeWidth="0.75" />
        <g clipPath="url(#liquid-intro-clip)">
          <path d={DROP_PATH} className="fill-primary" />
        </g>
      </svg>
    </motion.div>
  );
}
