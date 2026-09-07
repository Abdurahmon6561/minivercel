import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes, useParams, useSearchParams } from "react-router-dom";

import { useAuth } from "./auth/AuthProvider";
import { ErrorBanner, Spinner } from "./components/Bits";
import { Layout } from "./components/Layout";
import { api, type Me } from "./lib/api";
import { isDashboardHost } from "./lib/host";
import { ProjectChromeProvider } from "./lib/project-chrome";
import { Account } from "./pages/Account";
import { Landing } from "./pages/Landing";
import { Login } from "./pages/Login";
import { NewProject } from "./pages/NewProject";
import { ProjectDetail } from "./pages/ProjectDetail";
import { Projects } from "./pages/Projects";
import { configError } from "./lib/supabase";

function Misconfigured({ message }: { message: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center px-6">
      <div className="max-w-md">
        <ErrorBanner message={message} />
      </div>
    </div>
  );
}

/**
 * What `/` means depends on the host, because both serve this same bundle.
 *
 *   getdropbin.xyz       the landing, signed in or not - someone who typed the
 *                        apex came for the marketing page, and the header
 *                        offers them a way through to the dashboard
 *   app.getdropbin.xyz   never a page of its own; a redirect to wherever the
 *                        session says they belong
 */
function Root() {
  const { session, loading } = useAuth();

  if (!isDashboardHost()) return <Landing />;

  // Only the dashboard host waits. The redirect target depends on the session,
  // and navigating before it resolves would bounce a signed-in user through
  // /login - which on the OAuth return would also discard the URL fragment
  // supabase-js reads the session out of.
  if (loading) return <div className="min-h-screen bg-bg" />;

  return <Navigate to={session ? "/projects" : "/login"} replace />;
}

/**
 * The old project URL. Kept so existing bookmarks and any link already shared
 * keep working; `replace` so it does not sit in the history and bounce a back
 * press straight forward again.
 */
function LegacyProjectRedirect() {
  const { slug = "" } = useParams();
  if (import.meta.env.DEV) {
    console.warn(
      `[dropbin] /p/${slug} is the old project URL - redirecting to /projects/${slug}. ` +
        "The scheme changed in step 6; update any bookmark or hard-coded link.",
    );
  }
  return <Navigate to={`/projects/${slug}`} replace />;
}

/** The old new-project URL. Query string is carried over so /new?from=github
 *  still lands on the importer. */
function LegacyNewRedirect() {
  const [params] = useSearchParams();
  const query = params.toString();
  if (import.meta.env.DEV) {
    console.warn(
      "[dropbin] /new is the old new-project URL - redirecting to /projects/new. " +
        "The scheme changed in step 7; update any bookmark or hard-coded link.",
    );
  }
  return <Navigate to={`/projects/new${query ? `?${query}` : ""}`} replace />;
}

/** Everything behind the marketing page: needs config, auth, and the header. */
function Dashboard() {
  const { session, loading } = useAuth();
  const [me, setMe] = useState<Me | null>(null);

  // Quota and GitHub state live in the header on every page, so they are
  // fetched once here and refreshed after anything that changes them.
  const refreshMe = useCallback(() => {
    if (!session) {
      setMe(null);
      return;
    }
    api
      .me()
      .then(setMe)
      .catch(() => setMe(null));
  }, [session]);

  useEffect(refreshMe, [refreshMe]);

  if (configError) return <Misconfigured message={configError} />;

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Signing in" />
      </div>
    );
  }

  if (!session) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    // Above Layout: the sidebar it renders reads the current project from
    // here, and the page that publishes it is inside.
    <ProjectChromeProvider>
      <Layout me={me}>
        <Routes>
        <Route path="/projects" element={<Projects />} />
        <Route path="/account" element={<Account me={me} onChanged={refreshMe} />} />
        {/* Before /projects/:slug, or "new" would be read as a slug. */}
        <Route
          path="/projects/new"
          element={<NewProject me={me} onDeployed={refreshMe} />}
        />
        <Route
          path="/projects/:slug"
          element={<ProjectDetail me={me} onChanged={refreshMe} />}
        />
        <Route path="/p/:slug" element={<LegacyProjectRedirect />} />
        <Route path="/new" element={<LegacyNewRedirect />} />
        <Route path="/login" element={<Navigate to="/projects" replace />} />
        <Route
          path="*"
          element={
            <div className="py-20 text-center">
              <p className="text-lg text-text">Page not found.</p>
            </div>
          }
        />
        </Routes>
      </Layout>
    </ProjectChromeProvider>
  );
}

export function App() {
  return (
    <Routes>
      {/* `/` is matched here so the landing renders without the config check,
          the auth gate, or the header - none of which it needs, and all of
          which would delay its first paint. */}
      <Route path="/" element={<Root />} />
      <Route path="*" element={<Dashboard />} />
    </Routes>
  );
}
