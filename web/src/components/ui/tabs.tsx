import * as TabsPrimitive from "@radix-ui/react-tabs";

import { cn } from "../../lib/cn";

/**
 * Tabs, on Radix.
 *
 * The dependency buys the keyboard contract: arrow keys move between tabs,
 * Home/End jump to the ends, and only the active tab is in the tab order
 * (roving tabindex) so Tab moves out to the panel rather than through five
 * triggers. Hand-rolling that correctly is more code than the library.
 *
 * Underline rather than a filled pill: these sit directly above their own
 * content, and a filled indicator competes with the primary button in the
 * header for the eye.
 */

export const Tabs = TabsPrimitive.Root;

export function TabsList({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      className={cn(
        // Scrolls rather than wraps on a narrow screen, so the row never
        // becomes two lines and shifts the content below it.
        "flex items-center gap-1 overflow-x-auto border-b border-border",
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
        "relative shrink-0 px-3 py-2.5 text-sm font-medium whitespace-nowrap",
        "text-muted transition-colors hover:text-text",
        "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring",
        // The underline sits on the same pixel row as the list's bottom border
        // so the active tab reads as joined to its panel.
        "after:absolute after:inset-x-2 after:-bottom-px after:h-0.5 after:rounded-full after:content-['']",
        "data-[state=active]:text-text data-[state=active]:after:bg-primary",
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
        "pt-6 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
        className,
      )}
      {...props}
    />
  );
}
