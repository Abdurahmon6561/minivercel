import type { ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";

import { fadeUpVariants } from "../../lib/motion";

/**
 * Fades and lifts its children into place the first time they cross into the
 * viewport. Landing-only: this is the page's one motion primitive for a
 * single block entering as a unit - a group of siblings that should cascade
 * in one after another (the "How it works" steps, the feature cards, the
 * comparison table rows) stagger via `motion.*` directly at the call site
 * instead, since a generic wrapper here would have to break the semantics of
 * an `<ol>`, a grid, or a `<table>` to do it.
 *
 * `whileInView` with `viewport={{ once: true }}`: Motion's own visibility
 * observer, so no manual `IntersectionObserver` bookkeeping, and it never
 * re-fires on scrolling back past a section - that would be distracting on a
 * page meant to be scrolled once, not informative.
 */
export function Reveal({
  children,
  delay = 0,
  className = "",
}: {
  children: ReactNode;
  /** Stagger against a sibling Reveal in the same section, in ms. */
  delay?: number;
  className?: string;
}) {
  const reduce = useReducedMotion();

  return (
    <motion.div
      className={className}
      variants={fadeUpVariants(!!reduce, 12, reduce ? 0 : delay / 1000)}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-80px" }}
    >
      {children}
    </motion.div>
  );
}
