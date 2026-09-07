import { createContext, useContext, useMemo, useState } from "react";

import type { ProjectDetail } from "./api";

/**
 * The project the sidebar is currently describing.
 *
 * There is one sidebar now, and inside a project it shows that project's name,
 * URL and sections. But the sidebar lives in `Layout`, which renders its page
 * as `children` and therefore knows nothing about what the page loaded. This
 * context is the seam: `ProjectDetail` publishes the project it fetched, and
 * the sidebar reads it.
 *
 * Deliberately only the loaded project, not the loading or error state. The
 * sidebar decides *whether* it is in a project from the URL - which is known
 * immediately - and uses this only to fill in the name and URL when they
 * arrive. That split is what stops the nav flickering in and out on every
 * navigation.
 */
interface ProjectChromeValue {
  project: ProjectDetail | null;
  setProject: (project: ProjectDetail | null) => void;
}

const ProjectChromeContext = createContext<ProjectChromeValue | null>(null);

export function ProjectChromeProvider({ children }: { children: React.ReactNode }) {
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const value = useMemo(() => ({ project, setProject }), [project]);
  return (
    <ProjectChromeContext.Provider value={value}>{children}</ProjectChromeContext.Provider>
  );
}

export function useProjectChrome(): ProjectChromeValue {
  const value = useContext(ProjectChromeContext);
  if (!value) throw new Error("useProjectChrome must be used inside ProjectChromeProvider");
  return value;
}
