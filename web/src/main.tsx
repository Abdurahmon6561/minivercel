import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import { AuthProvider } from "./auth/AuthProvider";
import { ToastProvider } from "./components/ui/toast";
import { ThemeProvider } from "./lib/theme-provider";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
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
  </StrictMode>,
);
