import { FileArchive } from "lucide-react";

import { GithubMark } from "../ui/github-mark";

/**
 * The hero's centerpiece: a zip file and a GitHub repository, both flowing
 * into one live site with a public URL - the literal shape of the sentence
 * beside it ("Push a zip or a GitHub repo. Get a public URL."), rather than
 * the orbiting-rings-around-a-code-editor drawing this replaces, which read
 * as "some dev tool" and not specifically as Dropbin.
 *
 * Built from tokens only, same rule as everywhere else on the page: no hex
 * value here, so both themes come from the same classes. The result card
 * reuses SitePreview's browser-chrome language (traffic lights, a real URL
 * shape in the address bar) so this and the "how it works" section read as
 * one family rather than two different mockups of "a website".
 *
 * Every absolutely-positioned child stays within the 0-100% box of its
 * parent - see the browser-test notes on the comparison table's 215px
 * sideways scroll for why that rule exists.
 */
export function DeploySourcesIllustration({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`relative mx-auto grid aspect-square w-full max-w-[26rem] place-items-center ${className}`}
    >
      <div className="w-full max-w-80">
        {/* The two ways in - real inputs, not a metaphor for them. */}
        <div className="flex items-center justify-center gap-3">
          <div className="flex items-center gap-2 rounded-xl border border-border bg-surface px-3.5 py-2.5 shadow-sm">
            <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-accent-subtle text-accent-vivid">
              <FileArchive className="size-4" aria-hidden="true" />
            </span>
            <span className="font-mono text-xs text-text">site.zip</span>
          </div>
          <div className="flex items-center gap-2 rounded-xl border border-border bg-surface px-3.5 py-2.5 shadow-sm">
            <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary-subtle text-primary-subtle-fg">
              <GithubMark className="size-3.5" aria-hidden="true" />
            </span>
            <span className="font-mono text-xs text-text">owner/repo</span>
          </div>
        </div>

        {/* The connector: a dot travelling from source to site is "in
            seconds" made visible, rather than a static arrow claiming it. */}
        <div className="relative mx-auto my-4 h-9 w-px">
          <div
            aria-hidden="true"
            className="absolute inset-0 w-px"
            style={{
              backgroundImage:
                "repeating-linear-gradient(to bottom, var(--border) 0, var(--border) 4px, transparent 4px, transparent 9px)",
            }}
          />
          <span
            className="absolute left-1/2 top-0 size-2 -translate-x-1/2 rounded-full bg-primary"
            style={{
              boxShadow: "0 0 10px var(--primary)",
              animation: "flow-dot 2.2s ease-in-out infinite",
            }}
          />
        </div>

        {/* The result: the same browser chrome SitePreview uses, so this
            reads as "the thing you get", not a second unrelated mockup. */}
        <div
          className="relative overflow-hidden rounded-2xl border border-border bg-surface"
          style={{
            boxShadow:
              "var(--shadow-lg), 0 0 70px color-mix(in srgb, var(--primary) 16%, transparent)",
          }}
        >
          <div className="flex items-center gap-1.5 border-b border-border bg-surface-sunken px-3.5 py-2.5">
            <span className="size-2 rounded-full bg-destructive/70" />
            <span className="size-2 rounded-full bg-warning/70" />
            <span className="size-2 rounded-full bg-success/70" />
            <div className="ml-2 min-w-0 flex-1 truncate rounded-md bg-surface px-2.5 py-1 font-mono text-[10px] text-muted">
              blue-forest-4821.getdropbin.xyz
            </div>
          </div>
          <div className="space-y-2.5 p-4">
            <div className="h-1.5 w-[42%] rounded-full bg-primary/55" />
            <div className="h-1.5 w-[64%] rounded-full bg-accent/45" />
            <div className="h-1.5 w-full rounded-full bg-border-strong" />
            <div className="h-1.5 w-[76%] rounded-full bg-border-strong" />
            <div className="h-1.5 w-[30%] rounded-full bg-primary/55" />
          </div>
        </div>
      </div>

      {/* Status chips. Real shapes from the product - a Ready state and a
          commit SHA, in the tokens the dashboard itself uses. */}
      <div
        className="animate-float absolute top-4 right-0 rounded-lg border border-border bg-surface/90 px-3 py-2 shadow-md backdrop-blur-sm"
        style={{ animationDelay: "-1.2s" }}
      >
        <p className="text-[9px] font-medium tracking-[0.12em] text-muted uppercase">Deployment</p>
        <p className="mt-1 flex items-center gap-1.5 text-xs font-semibold text-success">
          <span className="size-1.5 rounded-full bg-current" aria-hidden="true" />
          Ready
        </p>
      </div>

      <div
        className="animate-float absolute bottom-4 left-0 rounded-lg border border-border bg-surface/90 px-3 py-2 shadow-md backdrop-blur-sm"
        style={{ animationDelay: "-3.4s" }}
      >
        <p className="text-[9px] font-medium tracking-[0.12em] text-muted uppercase">Commit</p>
        <p className="mt-1 font-mono text-xs text-text">7d36a4e</p>
      </div>
    </div>
  );
}
