import { createClient } from "@supabase/supabase-js";

/**
 * The anon key is public by design - it is the key that is *supposed* to be in
 * the browser, and RLS is what makes that safe. The service_role key must never
 * appear here (SPEC.md non-negotiable #4); if you ever find yourself pasting a
 * key that starts with the service_role JWT into `.env`, stop.
 */
const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const configError =
  !url || !anonKey
    ? "VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY are not set. Copy web/.env.example to web/.env and fill them in."
    : !import.meta.env.VITE_API_BASE_URL
      ? "VITE_API_BASE_URL is not set. Point it at your deployed API."
      : null;

export const supabase = createClient(url ?? "http://unset", anonKey ?? "unset", {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    // The OAuth callback comes back with the session in the URL fragment.
    detectSessionInUrl: true,
    flowType: "pkce",
  },
});

export const githubScopes = import.meta.env.VITE_GITHUB_SCOPES || "public_repo";
