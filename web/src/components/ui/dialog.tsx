import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";

import { cn } from "../../lib/cn";

/**
 * A modal dialog, on Radix.
 *
 * Worth a dependency rather than a div with `position: fixed`. A correct modal
 * has to trap focus, restore it to the trigger on close, lock body scroll,
 * close on Escape and on an outside click, mark everything behind it inert, and
 * wire aria-modal/labelledby/describedby - each of which is easy to write and
 * easy to get subtly wrong in a way only keyboard and screen-reader users hit.
 *
 * Every colour below is a token, so the same markup renders in both themes.
 */

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export function DialogContent({
  className,
  children,
  ...props
}: React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>) {
  return (
    <DialogPrimitive.Portal>
      {/* The scrim is deliberately dark in both themes: in light it is what
          says "the page behind is inert", and a light scrim on a light page
          says nothing at all. */}
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/45 backdrop-blur-[2px]" />
      <DialogPrimitive.Content
        className={cn(
          "fixed top-1/2 left-1/2 z-50 w-[calc(100vw-2rem)] max-w-md",
          "-translate-x-1/2 -translate-y-1/2",
          "rounded-xl border border-border bg-surface p-6 shadow-lg",
          // A long build log must scroll inside the dialog, never push the
          // page behind it sideways.
          "max-h-[calc(100vh-4rem)] overflow-y-auto",
          className,
        )}
        {...props}
      >
        {children}
        <DialogPrimitive.Close
          className="absolute top-4 right-4 rounded-sm p-1 text-muted transition-colors hover:bg-surface-hover hover:text-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          aria-label="Close"
        >
          <X className="size-4" aria-hidden="true" />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export function DialogHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mb-4 flex flex-col gap-1.5 pr-8", className)} {...props} />;
}

export function DialogTitle({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>) {
  return (
    <DialogPrimitive.Title
      className={cn("text-base font-semibold tracking-tight text-text", className)}
      {...props}
    />
  );
}

export function DialogDescription({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>) {
  return (
    <DialogPrimitive.Description
      className={cn("text-sm leading-relaxed text-muted", className)}
      {...props}
    />
  );
}

export function DialogFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("mt-6 flex flex-wrap items-center justify-end gap-2.5", className)}
      {...props}
    />
  );
}
