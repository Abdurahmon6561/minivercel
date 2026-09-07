import { createContext, useCallback, useContext, useMemo, useState } from "react";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { CheckCircle2, X } from "lucide-react";

import { cn } from "../../lib/cn";

/**
 * Transient confirmations, top-right.
 *
 * On Radix for the reasons that make a toast harder than a fixed-position div:
 * it is a live region announced to screen readers without stealing focus, it
 * pauses its own timer on hover and on window blur so a message cannot expire
 * while being read, it is dismissable by swipe, and F8 jumps to it. Those are
 * the parts people skip when they hand-roll one.
 *
 * The API is a hook rather than a component, because the callers are event
 * handlers - "the rollback succeeded" is known inside a promise, not during a
 * render.
 */

export interface ToastAction {
  label: string;
  /** Opened in a new tab. Toasts are transient; navigating away kills them. */
  href: string;
}

interface ToastMessage {
  id: number;
  title: string;
  description?: React.ReactNode;
  action?: ToastAction;
}

interface ToastValue {
  toast: (message: Omit<ToastMessage, "id">) => void;
}

const ToastContext = createContext<ToastValue | null>(null);

/** How long a toast stays. Long enough to read a URL and decide to click it. */
const DURATION_MS = 8000;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [messages, setMessages] = useState<ToastMessage[]>([]);

  const toast = useCallback((message: Omit<ToastMessage, "id">) => {
    // Date.now() would collide for two toasts raised in the same millisecond.
    setMessages((current) => [...current, { ...message, id: nextId++ }]);
  }, []);

  const value = useMemo<ToastValue>(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      <ToastPrimitive.Provider duration={DURATION_MS} swipeDirection="right">
        {children}

        {messages.map((message) => (
          <ToastPrimitive.Root
            key={message.id}
            onOpenChange={(open) => {
              // Drop it from state once Radix has finished closing it, so the
              // list does not grow for the life of the session.
              if (!open) setMessages((current) => current.filter((m) => m.id !== message.id));
            }}
            className={cn(
              "flex items-start gap-3 rounded-xl border border-border bg-surface p-4 shadow-lg",
              // Hand-written keyframes in index.css, not `animate-in`: that
              // class comes from tailwindcss-animate, which is not installed -
              // it compiled to nothing and the toast simply appeared.
              "data-[state=open]:animate-toast-in",
              "data-[state=closed]:animate-toast-out",
              "data-[swipe=move]:translate-x-(--radix-toast-swipe-move-x)",
              "data-[swipe=end]:animate-toast-out",
            )}
          >
            <CheckCircle2
              className="mt-0.5 size-4 shrink-0 text-success"
              aria-hidden="true"
            />
            <div className="min-w-0 flex-1">
              <ToastPrimitive.Title className="text-sm font-semibold text-text">
                {message.title}
              </ToastPrimitive.Title>
              {message.description && (
                <ToastPrimitive.Description className="mt-1 text-[13px] leading-relaxed text-muted">
                  {message.description}
                </ToastPrimitive.Description>
              )}
              {message.action && (
                <ToastPrimitive.Action asChild altText={message.action.label}>
                  <a
                    href={message.action.href}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="mt-2 inline-block font-mono text-xs break-all text-primary underline-offset-4 hover:underline"
                  >
                    {message.action.label}
                  </a>
                </ToastPrimitive.Action>
              )}
            </div>
            <ToastPrimitive.Close
              aria-label="Dismiss"
              className="shrink-0 rounded-sm p-1 text-muted transition-colors hover:bg-surface-hover hover:text-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              <X className="size-3.5" aria-hidden="true" />
            </ToastPrimitive.Close>
          </ToastPrimitive.Root>
        ))}

        {/* Fixed, above dialogs, and narrow enough not to cover the header's
            account menu on a small screen. */}
        <ToastPrimitive.Viewport className="fixed top-4 right-4 z-60 flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2 outline-none" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}

let nextId = 1;

export function useToast(): ToastValue {
  const value = useContext(ToastContext);
  if (!value) throw new Error("useToast must be used inside ToastProvider");
  return value;
}
