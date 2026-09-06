/**
 * A stable 32-bit hash of a string (FNV-1a).
 *
 * Used to pick a consistent colour for a thing from its identity - a project
 * from its slug, a person from their email - so the same input always looks the
 * same, across sessions and devices, with nothing stored.
 *
 * Not a security primitive. It is short, fast, and reversible in principle;
 * never hash anything secret with it.
 */
export function hash(value: string): number {
  let h = 2166136261;
  for (let i = 0; i < value.length; i++) {
    h ^= value.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}
