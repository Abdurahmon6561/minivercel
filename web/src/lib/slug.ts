/**
 * The client's copy of the server's slug rule (app/store.py `slugify`).
 *
 * Duplicated on purpose, and only for the preview: it lets the new-project
 * screen show the URL someone is about to get while they type, instead of after
 * a round trip. The server remains the authority and may still pick something
 * else - a slug that is reserved (`docs`, `api`) or already taken is replaced
 * there - which is why the preview copy says "will be" rather than "is".
 *
 * Keep in step with app/store.py. The extension list is the interesting part:
 * a repository or a project called `MacBook-React.jsx` should be served from
 * `macbook-react`, because the extension describes a file and nothing about
 * the site is a `.jsx`.
 */
const FILE_EXTENSIONS = [
  ".html", ".jsx", ".tsx", ".js", ".ts", ".md", ".py", ".go", ".rs", ".rb",
];

/** The minimum the server will accept before it falls back to a generated name. */
export const MIN_SLUG_LENGTH = 3;
export const MAX_SLUG_LENGTH = 48;

function stripFileExtension(name: string): string {
  const lowered = name.toLowerCase();
  for (const extension of FILE_EXTENSIONS) {
    if (lowered.endsWith(extension) && name.length > extension.length) {
      return name.slice(0, -extension.length);
    }
  }
  return name;
}

function slugChars(name: string): string {
  return name
    .normalize("NFKD")
    // Drop the combining marks NFKD just separated out, so "Nâmes" becomes
    // "names" rather than "na-mes".
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, MAX_SLUG_LENGTH)
    .replace(/^-+|-+$/g, "");
}

export function slugify(name: string): string {
  const slug = slugChars(stripFileExtension(name));
  if (slug.length >= MIN_SLUG_LENGTH) return slug;

  // Stripping took the only usable part - `v2.py` leaves `v2`. Prefer the whole
  // name over nothing, exactly as the server does.
  const withExtension = slugChars(name);
  return withExtension.length >= MIN_SLUG_LENGTH ? withExtension : slug;
}

/** Is this something the server will accept as-is? */
export function isUsableSlug(slug: string): boolean {
  return slug.length >= MIN_SLUG_LENGTH && slug.length <= MAX_SLUG_LENGTH;
}
