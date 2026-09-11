import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Fades and lifts its children into place the first time they cross into the
 * viewport. Landing-only: this is the page's one motion primitive, so every
 * section entrance goes through it rather than each growing its own
 * transition classes.
 *
 * IntersectionObserver, never a scroll listener - `window.addEventListener
 * ("scroll", ...)` re-fires on every frame and is what actually janks a page,
 * which is why it is not used here.
 *
 * Reduced motion is a hard skip, not a shorter animation: the observer is
 * never attached and the children render visible immediately. A user who has
 * asked their OS for less motion should not spend even one frame looking at
 * hidden content while something decides whether to show it to them.
 *
 * Animates only `opacity` and `transform`, so the browser can composite it on
 * the GPU instead of laying the page out again on every tick.
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
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setVisible(true);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      // 0.15 fires once a section is legibly on screen, not on the first
      // sliver of it crossing the bottom edge.
      { threshold: 0.15 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      style={{ transitionDelay: visible ? `${delay}ms` : "0ms" }}
      className={`transition-[opacity,transform] duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] ${
        visible ? "translate-y-0 opacity-100" : "translate-y-3 opacity-0"
      } ${className}`}
    >
      {children}
    </div>
  );
}
