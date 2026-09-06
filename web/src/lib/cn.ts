import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge class names, last-one-wins on conflicts.
 *
 * The shadcn convention, and the reason every component below takes a
 * `className`: `cn("px-4 py-2", "px-6")` yields `py-2 px-6` rather than two
 * competing paddings whose winner depends on stylesheet order.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
