import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { Session } from "@supabase/supabase-js";

import { api } from "../lib/api";
import { githubScopes, supabase } from "../lib/supabase";

interface AuthValue {
  session: Session | null;
  loading: boolean;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
  error: string | null;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Supabase hands back `provider_token` exactly once, on the sign-in event,
  // and never refreshes it. Miss it and the only way to get another is to make
  // the user authorise GitHub again - so capture it the moment it appears.
  // This ref stops us re-posting the same token on every auth event.
  const postedToken = useRef<string | null>(null);

  const captureProviderToken = useCallback(async (next: Session | null) => {
    const token = next?.provider_token;
    if (!token || postedToken.current === token) return;
    postedToken.current = token;

    try {
      await api.saveGithubToken({
        provider_token: token,
        scopes: githubScopes,
        // GitHub's login lands in user_metadata under one of these two keys
        // depending on how the identity was linked.
        github_login:
          (next?.user?.user_metadata?.user_name as string | undefined) ??
          (next?.user?.user_metadata?.preferred_username as string | undefined),
      });
    } catch (cause) {
      // Not fatal: the dashboard works without it. Phase 3 is what needs it,
      // and it will tell the user to reconnect.
      console.warn("Could not store the GitHub token:", cause);
      postedToken.current = null;
    }
  }, []);

  useEffect(() => {
    let active = true;

    supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      setSession(data.session);
      setLoading(false);
      void captureProviderToken(data.session);
    });

    const { data: subscription } = supabase.auth.onAuthStateChange(
      (_event, next) => {
        setSession(next);
        setLoading(false);
        void captureProviderToken(next);
      },
    );

    return () => {
      active = false;
      subscription.subscription.unsubscribe();
    };
  }, [captureProviderToken]);

  const signIn = useCallback(async () => {
    setError(null);
    const { error: cause } = await supabase.auth.signInWithOAuth({
      provider: "github",
      options: {
        scopes: githubScopes,
        redirectTo: window.location.origin,
      },
    });
    if (cause) setError(cause.message);
  }, []);

  const signOut = useCallback(async () => {
    postedToken.current = null;
    await supabase.auth.signOut();
  }, []);

  return (
    <AuthContext.Provider value={{ session, loading, signIn, signOut, error }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
