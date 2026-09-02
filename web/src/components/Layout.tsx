import { Link, NavLink, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import { useAuth } from "../auth/AuthProvider";
import { formatBytes } from "../lib/format";
import type { Me } from "../lib/api";

function QuotaBar({ me }: { me: Me }) {
  const { bytes_used: used, bytes_limit: limit } = me.usage;
  const fraction = limit ? Math.min(used / limit, 1) : 0;
  const tone =
    fraction > 0.9 ? "bg-failed" : fraction > 0.7 ? "bg-pending" : "bg-accent";

  return (
    <div className="flex items-center gap-3" title="Storage used across all projects">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-edge">
        <div
          className={`h-full ${tone}`}
          style={{ width: `${Math.max(fraction * 100, used > 0 ? 2 : 0)}%` }}
        />
      </div>
      <span className="font-mono text-xs text-muted">
        {formatBytes(used)} / {formatBytes(limit)}
      </span>
    </div>
  );
}

export function Layout({ children, me }: { children: ReactNode; me: Me | null }) {
  const { session, signOut } = useAuth();
  const location = useLocation();

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-md px-3 py-1.5 text-sm transition-colors ${
      isActive ? "bg-edge text-text" : "text-muted hover:text-text"
    }`;

  return (
    <div className="min-h-screen">
      <header className="border-b border-edge">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-4 px-6 py-4">
          <Link to="/" className="flex items-center gap-2 text-text">
            <span aria-hidden="true">▲</span>
            <span className="font-mono text-sm tracking-tight">minivercel</span>
          </Link>

          <nav className="flex items-center gap-1">
            <NavLink to="/" end className={linkClass}>
              Projects
            </NavLink>
            <NavLink to="/new" className={linkClass}>
              New
            </NavLink>
          </nav>

          <div className="ml-auto flex items-center gap-5">
            {me && <QuotaBar me={me} />}
            {me?.github.connected && (
              <span
                className="hidden items-center gap-1.5 font-mono text-xs text-muted sm:inline-flex"
                title={`GitHub connected${me.github.scopes ? ` (${me.github.scopes})` : ""}`}
              >
                <span className="h-1.5 w-1.5 rounded-full bg-ready" aria-hidden="true" />
                {me.github.login ?? "github"}
              </span>
            )}
            <span className="hidden text-sm text-muted md:inline">
              {session?.user?.email}
            </span>
            <button
              onClick={() => void signOut()}
              className="text-sm text-muted transition-colors hover:text-text"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main key={location.pathname} className="mx-auto max-w-5xl px-6 py-12">
        {children}
      </main>
    </div>
  );
}
