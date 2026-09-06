import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";

import { cn } from "../../lib/cn";

/**
 * A dropdown menu, on Radix.
 *
 * The same "worth a dependency" case as Dialog and Tabs: focus moves into the
 * menu on open and back to the trigger on close, arrow keys and Home/End move
 * between items, typing jumps to an item, Escape closes, an outside click
 * closes, and the whole thing is positioned and flipped against the viewport.
 * Hand-rolling that is a lot of code to get subtly wrong.
 *
 * `modal` defaults to FALSE here, which is the opposite of Radix's default. A
 * modal dropdown marks the rest of the page inert while it is open, so the
 * theme toggle sitting beside it in the header would be unreachable until the
 * menu was dismissed. This is a header menu, not a dialog.
 *
 * That alone is not enough, which is worth knowing before trusting the prop:
 * with modal={false} Radix still keeps focus inside the content, and because a
 * menu of `role="menuitem"` elements has no tabbable descendants, Tab and
 * Shift+Tab move nowhere at all - focus sits on the menu container and the menu
 * stays open. `handleTabOut` below implements what the ARIA Authoring Practices
 * specify instead: Tab closes the menu and continues the page's tab sequence
 * from the trigger.
 */

/** Everything the browser will stop on, in document order. */
const TABBABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),' +
  'textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

function handleTabOut(event: React.KeyboardEvent<HTMLDivElement>) {
  if (event.key !== "Tab") return;

  // The open trigger is the anchor for "where was I in the page".
  const trigger = document.querySelector<HTMLElement>(
    '[aria-haspopup="menu"][data-state="open"]',
  );
  event.preventDefault();

  // Closing through the trigger also hands focus back to it, which is the
  // behaviour Escape already has.
  trigger?.click();

  // Then step off it in the direction the user asked for. Deferred a frame so
  // the menu has unmounted and the trigger has focus before we move on.
  requestAnimationFrame(() => {
    if (!trigger) return;
    const stops = [...document.querySelectorAll<HTMLElement>(TABBABLE)].filter(
      (el) => el.offsetParent !== null || el === trigger,
    );
    const index = stops.indexOf(trigger);
    if (index === -1) return;
    stops[index + (event.shiftKey ? -1 : 1)]?.focus();
  });
}
export const DropdownMenu = ({
  modal = false,
  ...props
}: React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Root>) => (
  <DropdownMenuPrimitive.Root modal={modal} {...props} />
);

export const DropdownMenuTrigger = DropdownMenuPrimitive.Trigger;

export function DropdownMenuContent({
  className,
  sideOffset = 8,
  align = "end",
  ...props
}: React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Content>) {
  return (
    <DropdownMenuPrimitive.Portal>
      <DropdownMenuPrimitive.Content
        align={align}
        sideOffset={sideOffset}
        {...props}
        // After the spread on purpose: a caller-supplied onKeyDown must not be
        // able to replace this one, because dropping it would silently restore
        // the focus trap. Theirs still runs.
        onKeyDown={(event) => {
          handleTabOut(event);
          props.onKeyDown?.(event);
        }}
        className={cn(
          "z-50 min-w-56 overflow-hidden rounded-xl border border-border bg-surface p-1 shadow-lg",
          className,
        )}
      />
    </DropdownMenuPrimitive.Portal>
  );
}

export function DropdownMenuItem({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Item>) {
  return (
    <DropdownMenuPrimitive.Item
      className={cn(
        "flex items-center gap-2 rounded-md px-2.5 py-2 text-sm text-text outline-none select-none",
        // Radix drives hover and keyboard focus through one attribute, so the
        // mouse and the arrow keys highlight the same way.
        "data-[highlighted]:bg-surface-hover",
        "data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export function DropdownMenuSeparator({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Separator>) {
  return (
    <DropdownMenuPrimitive.Separator
      className={cn("-mx-1 my-1 h-px bg-border", className)}
      {...props}
    />
  );
}

/**
 * A non-interactive block inside the menu - a heading, a meter, a status line.
 *
 * Deliberately not a DropdownMenuItem: the arrow keys should skip it, and
 * Enter should not "activate" a usage bar.
 */
export function DropdownMenuSection({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-2.5 py-2", className)} {...props} />;
}

export function DropdownMenuLabel({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Label>) {
  return (
    <DropdownMenuPrimitive.Label
      className={cn(
        "px-2.5 pt-1 pb-1.5 text-[11px] font-semibold tracking-[0.07em] text-muted uppercase",
        className,
      )}
      {...props}
    />
  );
}
