import { Link, NavLink, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { FolderKanban, LogOut, Menu, Plus, X } from "lucide-react";
import { useState } from "react";

import { useAuth } from "../auth/AuthProvider";
import { Avatar } from "./ui/avatar";
import { Button } from "./ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSection,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import { GithubMark } from "./ui/github-mark";
import { ThemeToggle } from "./ui/theme-toggle";
import { Wordmark } from "./ui/wordmark";
import { formatBytes } from "../lib/format";
import type { Me } from "../lib/api";

/**
 * The header carries four things: the wordmark, the nav, the theme toggle and
 * the account menu. It used to carry seven, with the quota bar, the GitHub
 * status pill and the email competing for the same row - all three are status,
 * none of them is navigation, and they belong behind the avatar.
 */

function UsageSection({ me }: { me: Me }) {
  const { bytes_used: used, bytes_limit: limit } = me.usage;
  const fraction = limit ? Math.min(used / limit, 1) : 0;
  const tone =
    fraction > 0.9 ? "bg-destructive" : fraction > 0.7 ? "bg-warning" : "bg-primary";

  return (
    <DropdownMenuSection>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[13px] text-text">Usage</span>
        <span className="font-mono text-xs text-muted">
          {formatBytes(used)} / {formatBytes(limit)}
        </span>
      </div>
      <div
        className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-hover"
        role="progressbar"
        aria-label="Storage used across all projects"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(fraction * 100)}
      >
        <div
          className={`h-full ${tone} transition-[width] duration-300`}
          // A user with a few kilobytes stored should still see that the bar is
          // not empty; zero stays zero.
          style={{ width: `${Math.max(fraction * 100, used > 0 ? 2 : 0)}%` }}
        />
      </div>
    </DropdownMenuSection>
  );
}

function GithubSection({ me, onConnect }: { me: Me; onConnect: () => void }) {
  return (
    <DropdownMenuSection>
      <div className="flex items-center gap-2">
        <GithubMark className="size-3.5 shrink-0 text-muted" />
        {me.github.connected ? (
          // Status only. "Reconnect" would start the same OAuth flow as
          // "Connect", so offering it to someone already connected just asks
          // them to guess whether something is wrong.
          <span className="min-w-0 truncate text-[13px] text-muted">
            Connected as{" "}
            <span className="font-mono text-xs text-text">{me.github.login ?? "github"}</span>
          </span>
        ) : (
          <span className="text-[13px] text-muted">Not connected</span>
        )}
      </div>
      {!me.github.connected && (
        <Button variant="secondary" size="sm" className="mt-2 w-full" onClick={onConnect}>
          Connect GitHub
        </Button>
      )}
    </DropdownMenuSection>
  );
}

function AccountMenu({ me }: { me: Me | null }) {
  const { session, signIn, signOut } = useAuth();
  const email = me?.email ?? session?.user?.email ?? null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="rounded-full transition-shadow focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          aria-label={email ? `Account menu for ${email}` : "Account menu"}
        >
          <Avatar email={email} />
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent>
        <DropdownMenuLabel>Signed in as</DropdownMenuLabel>
        <DropdownMenuSection className="pt-0">
          <span className="block truncate text-[13px] text-text" title={email ?? undefined}>
            {email ?? "unknown"}
          </span>
        </DropdownMenuSection>

        {me && (
          <>
            <DropdownMenuSeparator />
            <UsageSection me={me} />
            <DropdownMenuSeparator />
            <GithubSection me={me} onConnect={() => void signIn()} />
          </>
        )}

        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void signOut()}>
          <LogOut className="size-4 shrink-0 text-muted" aria-hidden="true" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function Layout({ children, me }: { children: ReactNode; me: Me | null }) {
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
      isActive ? "bg-primary-subtle text-primary-subtle-fg" : "text-muted hover:bg-surface-hover hover:text-text"
    }`;

  return (
    <div className="min-h-screen bg-bg lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[280px] flex-col border-r border-border bg-surface p-4 transition-transform duration-200 lg:sticky lg:top-0 lg:h-screen lg:w-auto lg:translate-x-0 ${
          mobileOpen ? "translate-x-0 shadow-lg" : "-translate-x-full"
        }`}
      >
        <div className="flex h-11 items-center justify-between px-2">
          <Link to="/projects" onClick={() => setMobileOpen(false)}>
            <Wordmark />
          </Link>
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-label="Close navigation"
            onClick={() => setMobileOpen(false)}
          >
            <X />
          </Button>
        </div>

        <Link to="/projects/new" className="mt-7" onClick={() => setMobileOpen(false)}>
          <Button variant="primary" block icon={<Plus />}>
            New project
          </Button>
        </Link>

        <nav className="mt-7 space-y-1" aria-label="Main navigation">
          <NavLink to="/projects" end className={linkClass} onClick={() => setMobileOpen(false)}>
            <FolderKanban className="size-4" aria-hidden="true" />
            Projects
          </NavLink>
          <NavLink to="/projects/new" className={linkClass} onClick={() => setMobileOpen(false)}>
            <Plus className="size-4" aria-hidden="true" />
            Create project
          </NavLink>
        </nav>

        <div className="mt-auto border-t border-border pt-4">
          <p className="px-3 pb-3 text-[11px] font-semibold tracking-[0.12em] text-muted uppercase">
            Workspace
          </p>
          <div className="flex items-center justify-between px-2">
            <ThemeToggle />
            <AccountMenu me={me} />
          </div>
        </div>
      </aside>

      {mobileOpen && (
        <button
          type="button"
          aria-label="Close navigation overlay"
          className="fixed inset-0 z-30 bg-text/20 backdrop-blur-[1px] lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <div className="min-w-0">
        <header className="sticky top-0 z-20 border-b border-border bg-bg/90 backdrop-blur">
          <div className="flex h-16 items-center gap-3 px-5 sm:px-8">
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden"
              aria-label="Open navigation"
              onClick={() => setMobileOpen(true)}
            >
              <Menu />
            </Button>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-text">Workspace</p>
              <p className="hidden text-xs text-muted sm:block">Deploy and manage your sites</p>
            </div>
            <div className="ml-auto flex items-center gap-2 lg:hidden">
              <ThemeToggle />
              <AccountMenu me={me} />
            </div>
          </div>
        </header>

        <main key={location.pathname} className="mx-auto w-full max-w-7xl px-5 py-8 sm:px-8 sm:py-10">
          {children}
        </main>
      </div>
    </div>
  );
}
