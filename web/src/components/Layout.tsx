import { Link, NavLink, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { LogOut } from "lucide-react";

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

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-md px-3 py-1.5 text-sm transition-colors ${
      isActive ? "bg-surface-hover text-text" : "text-muted hover:text-text"
    }`;

  return (
    <div className="min-h-screen">
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-5xl items-center gap-4 px-6 py-4">
          <Link to="/projects">
            <Wordmark />
          </Link>

          <nav className="flex items-center gap-1">
            <NavLink to="/projects" end className={linkClass}>
              Projects
            </NavLink>
            <NavLink to="/projects/new" className={linkClass}>
              New
            </NavLink>
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <ThemeToggle />
            <AccountMenu me={me} />
          </div>
        </div>
      </header>

      <main key={location.pathname} className="mx-auto max-w-5xl px-6 py-12">
        {children}
      </main>
    </div>
  );
}
