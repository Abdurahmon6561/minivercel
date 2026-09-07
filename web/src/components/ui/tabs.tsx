import * as TabsPrimitive from "@radix-ui/react-tabs";

import { cn } from "../../lib/cn";

/**
 * Tabs, on Radix, styled as a sidebar.
 *
 * The dependency buys the keyboard contract: arrow keys move between tabs,
 * Home/End jump to the ends, and only the active tab is in the tab order
 * (roving tabindex) so Tab moves out to the panel rather than through four
 * triggers. `orientation="vertical"` is what switches those arrows from
 * Left/Right to Up/Down - Radix handles it natively, so there is no hand-rolled
 * key handling here.
 *
 * One thing worth knowing: `orientation` is a single value, not a responsive
 * one. The list is set vertical, and below `md` it is *styled* as a horizontal
 * scrolling strip while the keys stay Up/Down. That mismatch is deliberate and
 * costs nothing in practice - the strip only exists on touch widths, where
 * there are no arrow keys to press.
 */

export const Tabs = TabsPrimitive.Root;

export function TabsList({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      className={cn(
        "flex gap-1",
        // Mobile: a horizontal strip that scrolls rather than wraps, so the
        // row never becomes two lines and shifts the content below it.
        "overflow-x-auto pb-1",
        // md and up: the sidebar proper.
        "md:flex-col md:items-stretch md:overflow-x-visible md:pb-0",
        className,
      )}
      {...props}
    />
  );
}

export function TabsTrigger({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "flex shrink-0 items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm font-medium whitespace-nowrap",
        "text-muted transition-colors hover:bg-surface-hover hover:text-text",
        "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring",
        // The 2px indigo rule on the leading edge. Transparent when inactive so
        // the label never shifts by two pixels as the selection moves.
        "border-l-2 border-transparent",
        "data-[state=active]:border-l-primary data-[state=active]:bg-primary-subtle data-[state=active]:text-primary-subtle-fg",
        "[&_svg]:size-4 [&_svg]:shrink-0",
        className,
      )}
      {...props}
    />
  );
}

export function TabsContent({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      className={cn(
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        className,
      )}
      {...props}
    />
  );
}
