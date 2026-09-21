import { useEffect } from "react";
import { motion, useMotionValue, useReducedMotion, useSpring, useTransform } from "motion/react";

import { useCanHover } from "../lib/motion";

const FOLLOW_SPRING = { stiffness: 500, damping: 40, mass: 0.4 };
// Effectively zero lag, not a smaller spring - the lag itself is where any
// motion-discomfort risk lives, not the cursor's shape.
const INSTANT_SPRING = { stiffness: 6000, damping: 120, mass: 0.1 };

const HOVER_SELECTOR = 'a, button, [role="button"], input, textarea, select, summary';

/**
 * A small droplet that follows the pointer with a liquid lag (a spring, not
 * a 1:1 position) and swells over anything interactive. Site-wide, mounted
 * once in main.tsx, gated entirely behind `useCanHover()` - there is no
 * pointer to follow on a touch screen, and `mouseover`/`mousemove` there
 * fire from synthetic post-tap events that would leave a phantom cursor
 * stuck wherever was last tapped rather than tracking anything live.
 *
 * Solid `bg-primary`, not `mix-blend-mode: difference` - blend modes invert
 * per-channel against whatever sits underneath, which reads as the cursor
 * randomly shifting hue (green, olive) over anything that isn't the page's
 * own flat background, rather than as one consistent brand colour. The
 * `ring-bg` halo is what keeps it visible if it ever crosses a same-colour
 * primary button instead: a thin ring in the page's own background colour,
 * which flips with the theme on its own since it is the same token.
 */
export function CustomCursor() {
  const canHover = useCanHover();
  const reduce = useReducedMotion();

  const mouseX = useMotionValue(-100);
  const mouseY = useMotionValue(-100);
  const hoverMv = useMotionValue(0);

  const springConfig = reduce ? INSTANT_SPRING : FOLLOW_SPRING;
  const x = useSpring(mouseX, springConfig);
  const y = useSpring(mouseY, springConfig);
  const scale = useTransform(hoverMv, [0, 1], [1, 2.4]);

  useEffect(() => {
    if (!canHover) return;

    function onMove(e: MouseEvent) {
      mouseX.set(e.clientX);
      mouseY.set(e.clientY);
    }
    function onOver(e: MouseEvent) {
      hoverMv.set((e.target as Element | null)?.closest(HOVER_SELECTOR) ? 1 : 0);
    }

    document.documentElement.classList.add("custom-cursor-active");
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseover", onOver);

    return () => {
      document.documentElement.classList.remove("custom-cursor-active");
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseover", onOver);
    };
  }, [canHover, mouseX, mouseY, hoverMv]);

  if (!canHover) return null;

  return (
    <motion.div
      aria-hidden="true"
      className="pointer-events-none fixed top-0 left-0 z-200 size-3 rounded-full bg-primary ring-2 ring-bg"
      style={{ x, y, translateX: "-50%", translateY: "-50%", scale }}
    />
  );
}
