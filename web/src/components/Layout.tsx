import { Link, NavLink, useLocation, useMatch, useSearchParams } from "react-router-dom";
import type { ReactNode } from "react";
import {
  ArrowLeft,
  Cog,
  ExternalLink,
  FolderKanban,
  GitBranch,
  Plus,
  Rocket,
  UserRound,
  Variable,
} from "lucide-react";

import { useAuth } from "../auth/AuthProvider";
import { Avatar } from "./ui/avatar";
import { Button } from "./ui/button";
import { ThemeToggle } from "./ui/theme-toggle";
import { Wordmark } from "./ui/wordmark";
import { cn } from "../lib/cn";
import { useProjectChrome } from "../lib/project-chrome";
import type { Me } from "../lib/api";

/**
 * One sidebar, whose contents depend on where you are.
 *
 * There used to be two: a global one on the far left and a project one beside
 * it, which read as two applications bolted together. They are now the same
 * column - outside a project it lists the workspace, inside a project it
 * becomes that project's own nav with a way back out.
 *
 * Whether we are "inside a project" comes from the URL, not from loaded data,
 * so the nav renders on the first frame of a navigation. The project's name and
 * URL arrive a moment later through ProjectChrome; until then the slug stands
 * in for the name, which is what the address bar already says.
 */

const PROJECT_SECTIONS = [
  { tab: "deployments", label: "Deployments", Icon: Rocket },
  { tab: "github", label: "GitHub", Icon: GitBranch },
  { tab: "environment", label: "Environment", Icon: Variable },
  { tab: "settings", label: "Settings", Icon: Cog },
] as const;

const itemClass = (active: boolean) =>
  cn(
    "flex items-center gap-3 rounded-lg border-l-2 px-3 py-2 text-sm font-medium transition-colors",
    "[&_svg]:size-4 [&_svg]:shrink-0",
    active
      ? "border-l-primary bg-primary-subtle text-primary-subtle-fg"
      : "border-l-transparent text-muted hover:bg-surface-hover hover:text-text",
  );

/** The workspace nav: everything that is not inside one project. */
function WorkspaceNav() {
  return (
    <>
      <Link to="/projects/new" className="block">
        <Button variant="primary" block icon={<Plus />}>
          New project
        </Button>
      </Link>

      <nav className="mt-6 space-y-1" aria-label="Workspace">
        <NavLink to="/projects" end className={({ isActive }) => itemClass(isActive)}>
          <FolderKanban aria-hidden="true" />
          Projects
        </NavLink>
        <NavLink to="/account" className={({ isActive }) => itemClass(isActive)}>
          <UserRound aria-hidden="true" />
          Account
        </NavLink>
      </nav>
    </>
  );
}

/** The nav for one project, with the way back out above it. */
function ProjectNav({ slug }: { slug: string }) {
  const { project } = useProjectChrome();
  const [params] = useSearchParams();
  const active = params.get("tab") ?? "deployments";

  return (
    <>
      <Link
        to="/projects"
        className="inline-flex items-center gap-1.5 px-1 text-[13px] text-muted transition-colors hover:text-text"
      >
        <ArrowLeft className="size-3.5" aria-hidden="true" />
        Projects
      </Link>

      <div className="mt-3 px-1">
        <p
          className="truncate text-sm font-semibold text-text"
          title={project?.name ?? slug}
        >
          {project?.name ?? slug}
        </p>
        {project && (
          <a
            href={project.url}
            target="_blank"
            rel="noreferrer noopener"
            className="mt-1 inline-flex min-w-0 max-w-full items-center gap-1 font-mono text-xs text-muted transition-colors hover:text-accent"
            title={project.url}
          >
            <span className="truncate">{project.url.replace(/^https?:\/\//, "")}</span>
            <ExternalLink className="size-3 shrink-0" aria-hidden="true" />
          </a>
        )}
      </div>

      <div className="my-4 h-px bg-border" />

      {/* Links, not tab buttons: these change the URL and are worth
          middle-clicking or copying, which a <button role="tab"> is not. */}
      <nav className="space-y-1" aria-label="Project sections">
        {PROJECT_SECTIONS.map(({ tab, label, Icon }) => (
          <Link
            key={tab}
            to={
              tab === "deployments"
                ? `/projects/${slug}`
                : `/projects/${slug}?tab=${tab}`
            }
            replace
            aria-current={active === tab ? "page" : undefined}
            className={itemClass(active === tab)}
          >
            <Icon aria-hidden="true" />
            {label}
          </Link>
        ))}
      </nav>

      {project && (
        <a
          href={project.url}
          target="_blank"
          rel="noreferrer noopener"
          className="mt-5 block"
        >
          <Button variant="secondary" block icon={<ExternalLink />}>
            Open site
          </Button>
        </a>
      )}
    </>
  );
}

/**
 * Theme and identity.
 *
 * The avatar is the way to /account, which is where signing out now lives.
 * The Sign out button that stood here between the dropdown being removed and
 * /account existing has served its purpose and is gone: two ways to sign out,
 * one of them a bare icon in a corner, is worse than one clearly labelled.
 */
function SidebarFooter({
  me,
  layout,
}: {
  me: Me | null;
  /**
   * `stacked` for the 248px sidebar, where identity and controls on one line
   * squeezes the address down to "abd…". `inline` for the mobile bar, which
   * drops the address entirely and has the full width to play with.
   */
  layout: "stacked" | "inline";
}) {
  const { session } = useAuth();
  const email = me?.email ?? session?.user?.email ?? null;

  if (layout === "inline") {
    return (
      <div className="flex items-center gap-2">
        <Link
          to="/account"
          aria-label={email ? `Account: ${email}` : "Account"}
          className="rounded-full focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <Avatar email={email} />
        </Link>
        <ThemeToggle />
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <Link
        to="/account"
        className="flex items-center gap-2 rounded-lg px-1 py-1 transition-colors hover:bg-surface-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        aria-label={email ? `Account: ${email}` : "Account"}
      >
        <Avatar email={email} />
        <span className="min-w-0 truncate text-[13px] text-muted" title={email ?? undefined}>
          {email ?? "Signed in"}
        </span>
      </Link>
      <ThemeToggle />
    </div>
  );
}

export function Layout({ children, me }: { children: ReactNode; me: Me | null }) {
  const location = useLocation();

  // From the URL, so the correct nav is on screen from the first frame.
  // "/projects/new" is a page, not a project.
  const inProject = useMatch("/projects/:slug");
  const slug =
    inProject && inProject.params.slug !== "new" ? inProject.params.slug! : null;

  const sidebar = slug ? <ProjectNav slug={slug} /> : <WorkspaceNav />;

  return (
    <div className="min-h-screen bg-bg lg:grid lg:grid-cols-[248px_minmax(0,1fr)]">
      {/* Desktop: a real column. */}
      <aside className="hidden border-r border-border bg-surface lg:sticky lg:top-0 lg:flex lg:h-screen lg:flex-col lg:p-4">
        <Link to="/projects" className="mb-6 block px-1">
          <Wordmark />
        </Link>

        <div className="min-h-0 flex-1 overflow-y-auto">{sidebar}</div>

        <div className="mt-4 border-t border-border pt-3">
          <SidebarFooter me={me} layout="stacked" />
        </div>
      </aside>

      {/* Below lg the same content becomes a strip across the top: no drawer,
          no hamburger, nothing hidden behind a tap. */}
      <div className="min-w-0">
        <div className="sticky top-0 z-20 border-b border-border bg-bg/95 backdrop-blur lg:hidden">
          <div className="flex items-center gap-3 px-5 py-3">
            <Link to="/projects">
              <Wordmark />
            </Link>
            <div className="ml-auto">
              <SidebarFooter me={me} layout="inline" />
            </div>
          </div>

          {slug && <MobileProjectHeader slug={slug} />}

          <div className="flex items-center gap-1 overflow-x-auto px-3 pb-2">
            {slug ? <MobileProjectStrip slug={slug} /> : <MobileWorkspaceStrip />}
          </div>
        </div>

        <main
          key={location.pathname}
          className="mx-auto w-full max-w-7xl px-5 py-8 sm:px-8 sm:py-10"
        >
          {children}
        </main>
      </div>
    </div>
  );
}

function MobileProjectHeader({ slug }: { slug: string }) {
  const { project } = useProjectChrome();
  return (
    <div className="flex items-center gap-2 px-5 pb-1">
      <Link to="/projects" aria-label="Back to projects" className="shrink-0 text-muted">
        <ArrowLeft className="size-4" aria-hidden="true" />
      </Link>
      <p className="truncate text-sm font-semibold text-text">{project?.name ?? slug}</p>
    </div>
  );
}

const stripClass = (active: boolean) =>
  cn(
    "flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[13px] font-medium whitespace-nowrap transition-colors",
    "[&_svg]:size-3.5 [&_svg]:shrink-0",
    active
      ? "bg-primary-subtle text-primary-subtle-fg"
      : "text-muted hover:bg-surface-hover hover:text-text",
  );

function MobileWorkspaceStrip() {
  return (
    <>
      <NavLink to="/projects" end className={({ isActive }) => stripClass(isActive)}>
        <FolderKanban aria-hidden="true" />
        Projects
      </NavLink>
      <NavLink to="/account" className={({ isActive }) => stripClass(isActive)}>
        <UserRound aria-hidden="true" />
        Account
      </NavLink>
      <NavLink to="/projects/new" className={({ isActive }) => stripClass(isActive)}>
        <Plus aria-hidden="true" />
        New
      </NavLink>
    </>
  );
}

function MobileProjectStrip({ slug }: { slug: string }) {
  const [params] = useSearchParams();
  const active = params.get("tab") ?? "deployments";

  return (
    <>
      {PROJECT_SECTIONS.map(({ tab, label, Icon }) => (
        <Link
          key={tab}
          to={tab === "deployments" ? `/projects/${slug}` : `/projects/${slug}?tab=${tab}`}
          replace
          aria-current={active === tab ? "page" : undefined}
          className={stripClass(active === tab)}
        >
          <Icon aria-hidden="true" />
          {label}
        </Link>
      ))}
    </>
  );
}
