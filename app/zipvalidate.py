"""Zip inspection and safe extraction.

NON-NEGOTIABLE #3: every entry is validated *before* anything is extracted.
Nothing in this module executes, interprets or shells out to anything. It reads
the central directory, decides yes/no, and only then streams bytes to disk.

The threat model, and the check that covers each item:

  zip bomb            sum of uncompressed sizes from the header, checked before
                      extraction; then a per-entry byte counter during
                      extraction in case the header lied.
  path traversal      `..`, absolute paths and drive letters rejected by name,
                      then a realpath containment check against the root.
  symlink escape      unix mode bits in `external_attr` are inspected; symlinks
                      and every other non-regular file type are rejected.
  null byte / NTFS    names carrying NUL, control characters or a backslash are
                      rejected outright.
  file-count blowup   entry count checked before extraction.
  exotic codecs       only STORED and DEFLATED are accepted; BZIP2/LZMA give an
                      attacker a cheaper decompression bomb.
"""

from __future__ import annotations

import os
import posixpath
import stat
import zipfile
from dataclasses import dataclass

CHUNK = 64 * 1024

ALLOWED_COMPRESSION = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}

MAX_PATH_LENGTH = 1024
MAX_SEGMENT_LENGTH = 255

# Editor and OS droppings. Silently skipped rather than rejected: a zip made by
# macOS Finder always contains them and they would otherwise eat the file budget
# and fail deploys for reasons the user cannot see.
IGNORED_PREFIXES = ("__MACOSX/",)
IGNORED_BASENAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}


class ZipRejected(Exception):
    """The archive failed validation. The message is safe to show the user."""


@dataclass(frozen=True)
class ZipEntry:
    """One accepted regular file."""

    name: str  # original name inside the archive
    path: str  # normalised, root-relative posix path
    size: int  # uncompressed size, from the central directory


def _is_ignored(name: str) -> bool:
    if name.startswith(IGNORED_PREFIXES):
        return True
    return posixpath.basename(name) in IGNORED_BASENAMES


def _entry_is_regular_file(info: zipfile.ZipInfo) -> bool:
    """False for symlinks, devices, fifos and sockets.

    Only entries created on a unix-like system carry mode bits in the high 16
    bits of `external_attr`, and some writers store permission bits with no file
    type at all (Python's own `writestr` stores 0o600 << 16). Absent type bits
    means "no symlink here"; present type bits must say regular file.
    """
    file_type = (info.external_attr >> 16) & 0o170000
    if file_type == 0:
        return True
    return file_type == stat.S_IFREG


def _normalise(name: str) -> str:
    """Validate an archive member name and return its root-relative path.

    Raises ZipRejected on anything that could escape the extraction root or that
    cannot be represented as a storage key.
    """
    if not name:
        raise ZipRejected("archive contains an entry with an empty name")

    if "\x00" in name:
        raise ZipRejected("archive entry contains a null byte")

    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in name):
        raise ZipRejected("archive entry contains a control character")

    if "\\" in name:
        raise ZipRejected("archive entry contains a backslash: " + repr(name))

    if name.startswith("/"):
        raise ZipRejected("archive entry has an absolute path: " + repr(name))

    # Windows drive-relative names such as "C:foo" or "C:/foo".
    if len(name) >= 2 and name[1] == ":":
        raise ZipRejected("archive entry has a drive-qualified path: " + repr(name))

    segments = [seg for seg in name.split("/") if seg not in ("", ".")]
    if not segments:
        raise ZipRejected("archive entry resolves to no path: " + repr(name))

    if any(seg == ".." for seg in segments):
        raise ZipRejected("archive entry escapes the root: " + repr(name))

    if any(len(seg) > MAX_SEGMENT_LENGTH for seg in segments):
        raise ZipRejected(
            "archive entry has a path segment over %d characters" % MAX_SEGMENT_LENGTH
        )

    path = "/".join(segments)
    if len(path) > MAX_PATH_LENGTH:
        raise ZipRejected("archive entry path exceeds %d characters" % MAX_PATH_LENGTH)

    return path


def _assert_contained(root: str, relpath: str) -> str:
    """Belt-and-braces containment check on the real filesystem path.

    SPEC.md step 4: realpath(join(root, name)).startswith(realpath(root)).
    """
    real_root = os.path.realpath(root)
    target = os.path.realpath(os.path.join(real_root, *relpath.split("/")))
    if target != real_root and not target.startswith(real_root + os.sep):
        raise ZipRejected("archive entry escapes the extraction root: " + repr(relpath))
    return target


def inspect(
    zip_path: str,
    *,
    extraction_root: str,
    max_files: int,
    max_bytes: int,
) -> list[ZipEntry]:
    """Validate an archive and return the entries that may be extracted.

    Nothing is written to disk. Raises ZipRejected with a user-safe message.
    """
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise ZipRejected("not a valid zip archive: %s" % exc) from exc

    with zf:
        infos = zf.infolist()

        if len(infos) > max_files:
            raise ZipRejected(
                "archive contains %d entries, the limit is %d" % (len(infos), max_files)
            )

        total = 0
        entries: list[ZipEntry] = []
        seen: set[str] = set()

        for info in infos:
            name = info.filename

            if info.is_dir():
                continue
            if _is_ignored(name):
                continue

            if info.compress_type not in ALLOWED_COMPRESSION:
                raise ZipRejected(
                    "archive entry uses an unsupported compression method (%d): %r"
                    % (info.compress_type, name)
                )

            if not _entry_is_regular_file(info):
                raise ZipRejected(
                    "archive entry is a symlink or special file, which is not "
                    "allowed: " + repr(name)
                )

            path = _normalise(name)
            _assert_contained(extraction_root, path)

            if path in seen:
                raise ZipRejected("archive contains a duplicate path: " + repr(path))
            seen.add(path)

            if info.file_size < 0:
                raise ZipRejected("archive entry declares a negative size")

            total += info.file_size
            if total > max_bytes:
                raise ZipRejected(
                    "archive expands to more than %d bytes uncompressed" % max_bytes
                )

            entries.append(ZipEntry(name=name, path=path, size=info.file_size))

        if len(entries) > max_files:
            raise ZipRejected(
                "archive contains %d files, the limit is %d" % (len(entries), max_files)
            )

        if not entries:
            raise ZipRejected("archive contains no files")

    return entries


def strip_redundant_root(entries: list[ZipEntry]) -> list[ZipEntry]:
    """Drop a single wrapping directory, if and only if it is unambiguous.

    `zip -r site.zip mysite` produces `mysite/index.html`, not `index.html`, and
    a user who does that would otherwise get a 404 with no explanation. Only
    applied when every entry shares one top-level directory AND there is no
    `index.html` at the true root. Phase 3 relies on the same behaviour to strip
    GitHub's `owner-repo-sha1/` wrapper.
    """
    if not entries:
        return entries

    if any(entry.path == "index.html" for entry in entries):
        return entries

    roots = {entry.path.split("/", 1)[0] for entry in entries}
    if len(roots) != 1:
        return entries

    root = roots.pop()
    stripped: list[ZipEntry] = []
    for entry in entries:
        remainder = entry.path[len(root) + 1 :]
        if not remainder:
            return entries  # a file named exactly like the root; leave it alone
        stripped.append(ZipEntry(name=entry.name, path=remainder, size=entry.size))
    return stripped


#: Where a static site generator leaves its output, in the order SPEC.md
#: Phase 3 step 4 specifies. First one containing an index.html wins.
BUILD_OUTPUT_DIRS = ("dist", "build", "public", "_site")


def select_site_root(entries: list[ZipEntry]) -> tuple[list[ZipEntry], str | None]:
    """Find the directory that is actually the site, and re-root to it.

    A repository is not a website. After GitHub's `owner-repo-sha/` wrapper is
    stripped, `index.html` is usually not at the top: it is under `dist/` or
    `build/`, next to `src/`, `package.json` and everything else.

    Returns (entries, chosen subdirectory or None). Entries outside the chosen
    directory are dropped - deploying a repo's `src/` and `node_modules/`
    alongside its built output would burn the 500-file budget on files no
    browser will ever ask for.
    """
    if any(entry.path == "index.html" for entry in entries):
        return entries, None

    for candidate in BUILD_OUTPUT_DIRS:
        prefix = candidate + "/"
        if not any(entry.path == prefix + "index.html" for entry in entries):
            continue
        rerooted = [
            ZipEntry(name=entry.name, path=entry.path[len(prefix) :], size=entry.size)
            for entry in entries
            if entry.path.startswith(prefix) and len(entry.path) > len(prefix)
        ]
        if rerooted:
            return rerooted, candidate

    return entries, None


def extract(
    zip_path: str,
    entries: list[ZipEntry],
    destination: str,
    *,
    max_bytes: int,
) -> None:
    """Extract validated entries under `destination`.

    Sizes are re-counted while streaming: the central directory is attacker
    controlled, so a header that claims 1 KB and delivers 1 GB is stopped here.
    """
    os.makedirs(destination, exist_ok=True)
    by_name = {entry.name: entry for entry in entries}
    written = 0

    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            entry = by_name.get(info.filename)
            if entry is None:
                # Directory marker, ignored dropping, or an entry inspect()
                # already decided to skip.
                continue

            target = _assert_contained(destination, entry.path)
            os.makedirs(os.path.dirname(target), exist_ok=True)

            remaining = entry.size
            with zf.open(info) as source, open(target, "wb") as sink:
                while True:
                    chunk = source.read(CHUNK)
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    written += len(chunk)
                    if remaining < 0:
                        raise ZipRejected(
                            "archive entry is larger than its declared size: "
                            + repr(entry.path)
                        )
                    if written > max_bytes:
                        raise ZipRejected(
                            "archive expands to more than %d bytes uncompressed"
                            % max_bytes
                        )
                    sink.write(chunk)
