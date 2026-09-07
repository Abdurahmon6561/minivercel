import type { ComponentType } from "react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, Check, CheckCircle2, Globe2, History, Upload, X } from "lucide-react";

import { useAuth } from "../auth/AuthProvider";
import { Button } from "../components/ui/button";
import { GithubMark } from "../components/ui/github-mark";
import { ThemeToggle } from "../components/ui/theme-toggle";
import { Wordmark } from "../components/ui/wordmark";

function Feature({ Icon, number, title, children }: { Icon: ComponentType<{ className?: string }>; number: string; title: string; children: React.ReactNode }) {
  return <article className="border-t border-border pt-5"><div className="flex items-center justify-between"><Icon className="size-5 text-accent" aria-hidden="true" /><span className="font-mono text-xs text-muted">{number}</span></div><h3 className="mt-7 text-base font-semibold tracking-tight text-text">{title}</h3><p className="mt-2 max-w-xs text-sm leading-relaxed text-muted">{children}</p></article>;
}

function SitePreview() {
  return <div className="relative mt-14 overflow-hidden rounded-2xl border border-border bg-surface shadow-lg"><div className="flex items-center gap-2 border-b border-border px-4 py-3"><span className="size-2 rounded-full bg-destructive" /><span className="size-2 rounded-full bg-warning" /><span className="size-2 rounded-full bg-success" /><div className="ml-3 min-w-0 flex-1 rounded-md bg-surface-sunken px-3 py-1.5 font-mono text-xs text-muted">blue-forest-4821.getdropbin.xyz</div></div><div className="grid min-h-60 grid-cols-[1fr_150px] sm:min-h-72 sm:grid-cols-[1fr_210px]"><div className="p-6 sm:p-9"><div className="h-2 w-16 rounded-full bg-accent/50" /><div className="mt-6 h-7 max-w-xs rounded-md bg-text/90" /><div className="mt-3 h-3 max-w-sm rounded-full bg-border-strong" /><div className="mt-2 h-3 w-3/4 rounded-full bg-border" /><div className="mt-8 h-8 w-24 rounded-md bg-primary" /></div><div className="border-l border-border bg-surface-sunken p-4 sm:p-6"><p className="text-[11px] font-semibold tracking-[0.12em] text-muted uppercase">Deployment</p><div className="mt-6 flex items-center gap-2 text-xs font-medium text-success-subtle-fg"><span className="size-2 rounded-full bg-success" /> Ready</div><p className="mt-7 font-mono text-xs text-text">7d36a4e</p><p className="mt-1 text-xs text-muted">Just now</p><div className="mt-8 h-px bg-border" /><p className="mt-4 text-xs leading-relaxed text-muted">Live from a zip upload.</p></div></div></div>;
}

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

export function Landing() {
  const { session, loading } = useAuth();
  const [params] = useSearchParams();
  const deleted = params.get("deleted") !== null;
  return <div className="min-h-screen overflow-hidden bg-bg"><header className="relative z-10"><div className="mx-auto flex max-w-7xl items-center px-6 py-5 sm:px-8"><Wordmark /><nav className="ml-10 hidden items-center gap-6 text-sm text-muted md:flex" aria-label="Marketing navigation"><a className="transition-colors hover:text-text" href="#how-it-works">How it works</a><a className="transition-colors hover:text-text" href="#features">Features</a></nav><div className="ml-auto flex items-center gap-2"><ThemeToggle />{!loading && (session ? <Link to="/projects"><Button variant="secondary" size="sm">Open dashboard</Button></Link> : <Link to="/login"><Button variant="secondary" size="sm">Sign in</Button></Link>)}</div></div></header>{deleted && <DeletedNotice />}<main><section className="relative mx-auto max-w-7xl px-6 pt-16 pb-20 sm:px-8 sm:pt-24"><div aria-hidden="true" className="absolute top-0 right-[-20%] -z-0 size-[32rem] rounded-full bg-primary/10 blur-3xl" /><div className="relative z-10 max-w-4xl"><p className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium text-muted shadow-sm"><span className="size-1.5 rounded-full bg-success" /> Static deployment, without the ceremony</p><h1 className="mt-7 text-5xl font-semibold tracking-[-0.055em] text-text sm:text-6xl lg:text-7xl">Put your site on the internet. <span className="text-primary">Fast.</span></h1><p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted sm:text-xl">Upload a zip or connect a GitHub repository. Dropbin gives every project a public URL and a deployment history you can trust.</p><div className="mt-9 flex flex-wrap gap-3"><Link to="/login"><Button variant="primary" size="lg" icon={<GithubMark />}>Start with GitHub</Button></Link><a href="#how-it-works"><Button variant="ghost" size="lg" icon={<ArrowRight />}>See the flow</Button></a></div></div><SitePreview /></section><section id="how-it-works" className="border-y border-border bg-surface"><div className="mx-auto grid max-w-7xl gap-8 px-6 py-16 sm:grid-cols-3 sm:px-8"><Feature Icon={Upload} number="01" title="Add your files">Drop in a zip with an index file, or choose a GitHub repository you already own.</Feature><Feature Icon={Globe2} number="02" title="Go live immediately">We validate and publish your files to a secure public subdomain.</Feature><Feature Icon={History} number="03" title="Keep every version">Each deploy has a clear history, so promoting a previous version is instant.</Feature></div></section><section id="features" className="mx-auto grid max-w-7xl gap-12 px-6 py-20 sm:px-8 lg:grid-cols-[1.1fr_1fr] lg:items-end"><div><p className="text-xs font-semibold tracking-[0.13em] text-accent uppercase">Built for simple shipping</p><h2 className="mt-4 max-w-lg text-3xl font-semibold tracking-[-0.035em] text-text sm:text-4xl">A calmer way to manage small sites.</h2></div><ul className="space-y-4 text-sm leading-relaxed text-muted">{["A clean project list, designed for scanning—not dashboard clutter.", "Secure GitHub imports that deploy again when your branch changes.", "Transparent storage limits and deployment states, exactly where you need them."].map((item) => <li key={item} className="flex gap-3"><Check className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />{item}</li>)}</ul></section></main><footer className="border-t border-border"><div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-8 text-sm text-muted sm:px-8"><Wordmark /><span>© {new Date().getFullYear()} Dropbin</span></div></footer></div>;
}
