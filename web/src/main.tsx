import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import { AuthProvider } from "./auth/AuthProvider";
import { CustomCursor } from "./components/CustomCursor";
import { LiquidIntro } from "./components/LiquidIntro";
import { ToastProvider } from "./components/ui/toast";
import { ThemeProvider } from "./lib/theme-provider";
import "./index.css";

/**
 * The intro sits over the app rather than gating its mount: everything
 * underneath (theme, auth, routing) starts working the instant the page
 * loads, so dismissing it reveals whatever is already ready instead of
 * adding its own wait on top. See LiquidIntro for why it always finishes on
 * its own (once per session, or immediately if already seen/reduced motion).
 *
 * CustomCursor is mounted here, not inside Landing - the brief asks for it
 * site-wide, and it is a no-op render (`null`) everywhere `useCanHover()` is
 * false, so mounting it once here costs nothing on the pages that don't want it.
 */
function Root() {
  const [booted, setBooted] = useState(false);

  return (
    <>
      {/* Outermost: the theme applies to the login page and to the misconfigured
          and loading states too, none of which are inside the router's tree. */}
      <ThemeProvider>
        {/* Above the router, so a toast raised just before a navigation survives
            it - "rolled back" is confirmed on the page you land on. */}
        <ToastProvider>
          <BrowserRouter>
            <AuthProvider>
              <App />
            </AuthProvider>
          </BrowserRouter>
        </ToastProvider>
      </ThemeProvider>
      <CustomCursor />
      {!booted && <LiquidIntro onDone={() => setBooted(true)} />}
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
