"""Extension -> content-type whitelist.

SPEC.md step 5: content-type is derived from the file extension via a whitelist
map, *never* from anything inside the zip. An unknown extension gets
`application/octet-stream`, which browsers will not execute or render inline.

Deliberately absent: anything that makes the browser treat a user upload as a
plugin or an installable (`.jar`, `.swf`, `.apk`, `.msi`, `.exe`). They fall
through to octet-stream.
"""

from __future__ import annotations

import posixpath

DEFAULT_CONTENT_TYPE = "application/octet-stream"

CONTENT_TYPES: dict[str, str] = {
    # markup / styles / scripts
    "html": "text/html; charset=utf-8",
    "htm": "text/html; charset=utf-8",
    "xhtml": "application/xhtml+xml; charset=utf-8",
    "css": "text/css; charset=utf-8",
    "js": "text/javascript; charset=utf-8",
    "mjs": "text/javascript; charset=utf-8",
    "cjs": "text/javascript; charset=utf-8",
    "map": "application/json",
    # data
    "json": "application/json",
    "jsonld": "application/ld+json; charset=utf-8",
    "webmanifest": "application/manifest+json; charset=utf-8",
    "xml": "application/xml",
    "rss": "application/rss+xml; charset=utf-8",
    "atom": "application/atom+xml; charset=utf-8",
    "csv": "text/csv; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
    "wasm": "application/wasm",
    "pdf": "application/pdf",
    # images
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "avif": "image/avif",
    "bmp": "image/bmp",
    "ico": "image/x-icon",
    "svg": "image/svg+xml",
    "apng": "image/apng",
    # fonts
    "woff": "font/woff",
    "woff2": "font/woff2",
    "ttf": "font/ttf",
    "otf": "font/otf",
    "eot": "application/vnd.ms-fontobject",
    # media
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "ogg": "audio/ogg",
    "oga": "audio/ogg",
    "flac": "audio/flac",
    "m4a": "audio/mp4",
    "mp4": "video/mp4",
    "m4v": "video/mp4",
    "webm": "video/webm",
    "mov": "video/quicktime",
    "vtt": "text/vtt; charset=utf-8",
    # misc static-site furniture
    "gz": "application/gzip",
    "zip": "application/zip",
}


def content_type_for(path: str) -> str:
    """Return the whitelisted content-type for a storage key or file name."""
    name = posixpath.basename(path)
    if "." not in name:
        return DEFAULT_CONTENT_TYPE
    ext = name.rsplit(".", 1)[1].lower()
    return CONTENT_TYPES.get(ext, DEFAULT_CONTENT_TYPE)


def has_known_extension(path: str) -> bool:
    """True when the last path segment carries any extension at all.

    Used by the serving flow to decide whether to attempt clean-URL rewriting.
    """
    name = posixpath.basename(path)
    return "." in name and not name.startswith(".")
