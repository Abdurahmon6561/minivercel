import { useEffect, useState } from "react";
import { useReducedMotion, type Variants } from "motion/react";

/**
 * The motion system.
 *
 * One easing curve, one spring, reused everywhere an animation is added -
 * five different eases across a page is what makes motion read as bolted-on
 * rather than designed. Tweens (entrances, scroll reveals) use EASE; springs
 * are reserved for direct-manipulation feedback (hover, tap, drag) where a
 * physical response reads as more alive than an eased curve ever will.
 */
export const EASE = [0.21, 0.47, 0.32, 0.98] as const;

export const DURATION = {
  fast: 0.2,
  normal: 0.4,
  slow: 0.6,
} as const;

export const SPRING = { type: "spring", stiffness: 420, damping: 30 } as const;

/**
 * Reduced motion is a hard skip here, not a shorter animation - matching the
 * rule already established for the landing's Reveal component: a user who
 * asked their OS for less motion should not spend even one frame looking at
 * hidden content while something decides whether to show it to them. So the
 * "hidden" state below collapses onto "visible" and the transition duration
 * drops to zero, rather than merely getting faster.
 */
export function fadeUpVariants(reduce: boolean, distance = 16, delay = 0): Variants {
  return {
    hidden: reduce ? { opacity: 1, y: 0 } : { opacity: 0, y: distance },
    visible: {
      opacity: 1,
      y: 0,
      transition: reduce ? { duration: 0 } : { duration: DURATION.normal, ease: EASE, delay },
    },
  };
}

export function staggerVariants(reduce: boolean, staggerChildren = 0.06, delayChildren = 0): Variants {
  return {
    hidden: {},
    visible: {
      transition: reduce ? { staggerChildren: 0, delayChildren: 0 } : { staggerChildren, delayChildren },
    },
  };
}

/**
 * Gates hover-only motion (lift, scale, magnetic pull) behind real hover
 * support. Tailwind's own `hover:` has done this automatically since v3.4,
 * but Motion's `whileHover` fires on any pointer, touch included, so JS-driven
 * hover effects need this explicitly or they get stuck "on" after a tap.
 */
export function useCanHover(): boolean {
  const [canHover, setCanHover] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(hover: hover) and (pointer: fine)");
    setCanHover(query.matches);
    function onChange(e: MediaQueryListEvent) {
      setCanHover(e.matches);
    }
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return canHover;
}

/**
 * The "liquid wipe" word/line reveal used across the redesign's headlines.
 * Technically transform-only - a real `clip-path` animation would violate
 * the "transform/opacity only" rule the same way animating `width` would,
 * so this fakes the wipe the same way the project's accordion pattern fakes
 * a height change: an `overflow-hidden` wrapper the variant does not touch,
 * and an inner element that slides up from below AND relaxes out of a
 * vertical squash, which is what reads as liquid settling into place rather
 * than a plain slide-up.
 *
 * Usage contract (not enforceable from the variant object alone): the
 * immediate parent must be `inline-block` + `overflow-hidden`, and this
 * element needs `transformOrigin: "bottom"` so the squash anchors at the
 * baseline instead of drifting from the center.
 */
export function liquidRevealVariants(reduce: boolean, delay = 0): Variants {
  return {
    hidden: reduce ? { y: "0%", scaleY: 1 } : { y: "110%", scaleY: 1.4 },
    visible: {
      y: "0%",
      scaleY: 1,
      transition: reduce ? { duration: 0 } : { duration: DURATION.slow, ease: EASE, delay },
    },
  };
}

/**
 * Whether it's worth mounting the WebGL blob at all: off under reduced
 * motion (it is a purely decorative distortion loop, exactly what that
 * preference asks to skip), off on a coarse pointer or a narrow viewport
 * (mobile GPUs and the pointer-reactive distortion this drives are a desktop
 * feature), and off if the browser cannot actually create a context - so a
 * locked-down browser or an old GPU falls back to the static gradient
 * instead of a console error. Callers still need their own `Suspense`
 * fallback for the moment before this resolves and while the R3F chunk
 * itself is loading.
 */
export function useCanRenderWebGL(): boolean {
  const reduce = useReducedMotion();
  const [canRender, setCanRender] = useState(false);

  useEffect(() => {
    if (reduce) {
      setCanRender(false);
      return;
    }
    if (typeof window === "undefined" || !window.matchMedia) {
      setCanRender(false);
      return;
    }
    if (window.matchMedia("(pointer: coarse), (max-width: 767px)").matches) {
      setCanRender(false);
      return;
    }
    try {
      const canvas = document.createElement("canvas");
      const gl = canvas.getContext("webgl2") ?? canvas.getContext("webgl");
      setCanRender(!!gl);
    } catch {
      setCanRender(false);
    }
  }, [reduce]);

  return canRender;
}
