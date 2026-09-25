import { Check } from "lucide-react";

import { LogoMark } from "../ui/wordmark";
import { landingOrigin } from "../../lib/host";

const PITCH = [
  "Push a zip or a GitHub repo",
  "A public URL the moment it's ready",
  "Roll back to any deployment in one click",
  "250 MB free, no credit card",
];

/**
 * The brand pane shared by /login and /register.
 *
 * Solid `bg-primary`, not a token tuned for `bg-surface`: this is the one
 * place in the dashboard that is unapologetically a colour block rather than
 * a themed surface, which is what makes it read as a poster rather than as
 * another panel. Hidden below `lg` rather than stacked above the form - on a
 * phone there is only room for one of the two, and the form is the one that
 * has to be there.
 *
 * The dot grid is the one texture in the whole dashboard: everywhere else a
 * flat token fill is the rule, but a pane whose entire job is to be looked at
 * rather than worked in can afford it, and it is what keeps a large flat
 * colour field from reading as an unfinished placeholder.
 */
export function BrandPane() {
  return (
    <div className="relative hidden overflow-hidden bg-primary p-10 text-primary-fg lg:flex lg:flex-col lg:justify-between">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(currentColor_1px,transparent_1px)] bg-size-[22px_22px] opacity-[0.15]"
      />
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute -top-24 -right-16 size-96 rounded-full bg-accent-vivid/25 blur-[100px]" />
      </div>

      {/* Leaves the dashboard entirely, so this is a real anchor to the apex
          - a router Link cannot cross the host boundary. The only clickable
          logo at this breakpoint: the header's is `lg:hidden` because this
          pane is not. */}
      <a href={landingOrigin()} aria-label="Dropbin home" className="relative inline-flex items-center gap-2.5">
        <LogoMark variant="bare" className="size-6" />
        <span className="text-lg font-semibold tracking-tight">Dropbin</span>
      </a>

      <div className="relative max-w-sm">
        <h2 className="text-4xl leading-[1.05] font-semibold tracking-[-0.03em] text-balance">
          Deploy static sites in seconds.
        </h2>
        <ul className="mt-8 space-y-2.5">
          {PITCH.map((line) => (
            <li
              key={line}
              className="flex items-center gap-2.5 rounded-lg bg-primary-fg/10 px-3.5 py-2.5 text-sm text-primary-fg/90"
            >
              <Check className="size-4 shrink-0" aria-hidden="true" />
              {line}
            </li>
          ))}
        </ul>
      </div>

      {/* A real artefact of the product rather than a stock claim, echoing
          the landing hero's own "Ready" chip - the same proof, shown again
          where someone deciding whether to sign in will actually see it. */}
      <div className="relative inline-flex flex-wrap items-center gap-3 rounded-lg border border-primary-fg/15 bg-primary-fg/10 px-4 py-3">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-primary-fg/15 px-2.5 py-1 text-[11px] font-medium text-primary-fg">
          <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
          Ready
        </span>
        <span className="font-mono text-[13px] break-all text-primary-fg/70">
          your-project.getdropbin.xyz
        </span>
      </div>
    </div>
  );
}
