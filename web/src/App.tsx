import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth/AuthProvider";
import { ErrorBanner, Spinner } from "./components/Bits";
import { Layout } from "./components/Layout";
import { api, type Me } from "./lib/api";
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

export function App() {
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
    <Layout me={me}>
      <Routes>
        <Route path="/" element={<Projects />} />
        <Route path="/new" element={<NewProject me={me} onDeployed={refreshMe} />} />
        <Route
          path="/p/:slug"
          element={<ProjectDetail me={me} onChanged={refreshMe} />}
        />
        <Route path="/login" element={<Navigate to="/" replace />} />
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
  );
}
