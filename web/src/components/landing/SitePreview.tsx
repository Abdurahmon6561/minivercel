/**
 * A browser frame showing a deployed Dropbin site.
 *
 * The landing's core product-native visual, and the language the other section
 * graphics extend. Kept out of pages/Landing.tsx because "how it works" builds
 * its three-step diagram around it.
 *
 * Every value in it is real: the URL shape a project actually gets, a Ready
 * badge in the same tokens the dashboard uses, and a short commit SHA.
 */
export function SitePreview() {
  return <div className="relative overflow-hidden rounded-2xl border border-border bg-surface shadow-lg"><div className="flex items-center gap-2 border-b border-border px-4 py-3"><span className="size-2 rounded-full bg-destructive" /><span className="size-2 rounded-full bg-warning" /><span className="size-2 rounded-full bg-success" /><div className="ml-3 min-w-0 flex-1 rounded-md bg-surface-sunken px-3 py-1.5 font-mono text-xs text-muted">blue-forest-4821.getdropbin.xyz</div></div><div className="grid min-h-60 grid-cols-[1fr_150px] sm:min-h-72 sm:grid-cols-[1fr_210px]"><div className="p-6 sm:p-9"><div className="h-2 w-16 rounded-full bg-accent/50" /><div className="mt-6 h-7 max-w-xs rounded-md bg-text/90" /><div className="mt-3 h-3 max-w-sm rounded-full bg-border-strong" /><div className="mt-2 h-3 w-3/4 rounded-full bg-border" /><div className="mt-8 h-8 w-24 rounded-md bg-primary" /><div className="mt-9 grid grid-cols-3 gap-3"><div className="h-14 rounded-lg border border-border bg-surface-sunken" /><div className="h-14 rounded-lg border border-border bg-surface-sunken" /><div className="h-14 rounded-lg border border-border bg-surface-sunken" /></div></div><div className="border-l border-border bg-surface-sunken p-4 sm:p-6"><p className="text-[11px] font-semibold tracking-[0.12em] text-muted uppercase">Deployment</p><div className="mt-6 flex items-center gap-2 text-xs font-medium text-success-subtle-fg"><span className="size-2 rounded-full bg-success" /> Ready</div><p className="mt-7 font-mono text-xs text-text">7d36a4e</p><p className="mt-1 text-xs text-muted">Just now</p><div className="mt-8 h-px bg-border" /><p className="mt-4 text-xs leading-relaxed text-muted">Live from a zip upload.</p></div></div></div>;
}
