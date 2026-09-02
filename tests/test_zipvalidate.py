"""Security tests for the zip pipeline. These are the ones that matter."""

from __future__ import annotations

import io
import os
import zipfile

import pytest

from app import zipvalidate
from app.zipvalidate import ZipEntry, ZipRejected, extract, inspect, strip_redundant_root

from .conftest import make_zip

LIMITS = {"max_files": 500, "max_bytes": 50 * 1024 * 1024}


def write(tmp_path, data: bytes, name: str = "site.zip") -> str:
    path = os.path.join(str(tmp_path), name)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


def raw_zip(names: dict[str, bytes]) -> bytes:
    """Build an archive with member names written verbatim.

    `ZipFile.writestr` sanitises what an attacker would not: it truncates at the
    first NUL and rewrites os.sep to `/` on Windows. A real hostile archive is
    produced by any zip writer that does neither, so set the name after the
    ZipInfo is constructed and reproduce the actual attack.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in names.items():
            info = zipfile.ZipInfo("placeholder")
            info.filename = name
            zf.writestr(info, content)
    return buffer.getvalue()


def inspect_bytes(tmp_path, data: bytes, **overrides):
    limits = {**LIMITS, **overrides}
    return inspect(
        write(tmp_path, data), extraction_root=os.path.join(str(tmp_path), "out"), **limits
    )


# -- happy path -------------------------------------------------------------


def test_accepts_an_ordinary_site(tmp_path):
    entries = inspect_bytes(
        tmp_path,
        make_zip(
            {
                "index.html": "<h1>hi</h1>",
                "assets/app.css": "body{}",
                "assets/img/logo.png": b"\x89PNG",
            }
        ),
    )
    assert {entry.path for entry in entries} == {
        "index.html",
        "assets/app.css",
        "assets/img/logo.png",
    }


def test_directory_entries_are_not_files(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("assets/", b"")
        zf.writestr("index.html", b"x")
    entries = inspect_bytes(tmp_path, buffer.getvalue())
    assert [entry.path for entry in entries] == ["index.html"]


def test_macos_droppings_are_skipped_not_rejected(tmp_path):
    entries = inspect_bytes(
        tmp_path,
        make_zip(
            {
                "index.html": "x",
                "__MACOSX/._index.html": b"junk",
                ".DS_Store": b"junk",
                "assets/.DS_Store": b"junk",
            }
        ),
    )
    assert [entry.path for entry in entries] == ["index.html"]


# -- path traversal ---------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "../escape.html",
        "a/../../escape.html",
        "/etc/passwd",
        "..",
        "foo/../../../../../../tmp/pwned",
    ],
)
def test_rejects_traversal(tmp_path, name):
    with pytest.raises(ZipRejected):
        inspect_bytes(tmp_path, raw_zip({name: b"x"}))


@pytest.mark.parametrize(
    "name, reason",
    [
        ("a\\b.html", "backslash"),
        ("..\\..\\windows\\evil.html", "backslash"),
        ("index.html\x00.js", "null byte"),
        ("index\n.html", "control character"),
        ("index\x7f.html", "control character"),
        ("C:/windows/evil.html", "drive-qualified"),
        ("C:evil.html", "drive-qualified"),
        ("/etc/passwd", "absolute"),
        ("../escape.html", "escapes the root"),
        ("", "empty name"),
    ],
)
def test_normalise_rejects_hostile_names(name, reason):
    """`_normalise` is the check; assert it directly.

    Going through `zipfile` for these would test CPython, not us: its reader
    truncates member names at the first NUL on every platform and rewrites
    os.sep to `/` on Windows, so several of these never survive the parse.
    That sanitising is welcome but it is not ours, and it is not guaranteed.
    """
    with pytest.raises(ZipRejected, match=reason):
        zipvalidate._normalise(name)


@pytest.mark.parametrize(
    "name", ["a\\b.html", "index.html\x00.js", "..\\..\\evil.html", "C:/evil.html"]
)
def test_hostile_names_never_produce_a_hostile_path(tmp_path, name):
    """End to end: rejected, or neutralised into something safely contained."""
    try:
        entries = inspect_bytes(tmp_path, raw_zip({name: b"x"}))
    except ZipRejected:
        return
    root = os.path.realpath(os.path.join(str(tmp_path), "out"))
    for entry in entries:
        assert "\x00" not in entry.path
        assert "\\" not in entry.path
        target = os.path.realpath(os.path.join(root, *entry.path.split("/")))
        assert target.startswith(root + os.sep)


# -- symlinks ---------------------------------------------------------------


def _zip_with_symlink() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("index.html", b"<h1>hi</h1>")
        info = zipfile.ZipInfo("secret")
        info.create_system = 3  # unix
        info.external_attr = (0o120777 << 16)  # S_IFLNK | rwx
        zf.writestr(info, b"/etc/passwd")
    return buffer.getvalue()


def test_rejects_symlink_entries(tmp_path):
    with pytest.raises(ZipRejected, match="symlink"):
        inspect_bytes(tmp_path, _zip_with_symlink())


def test_rejects_special_files(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        info = zipfile.ZipInfo("fifo")
        info.create_system = 3
        info.external_attr = 0o010644 << 16  # S_IFIFO
        zf.writestr(info, b"")
    with pytest.raises(ZipRejected):
        inspect_bytes(tmp_path, buffer.getvalue())


# -- limits -----------------------------------------------------------------


def test_rejects_too_many_files(tmp_path):
    payload = {"f%03d.html" % index: "x" for index in range(12)}
    with pytest.raises(ZipRejected, match="the limit is 10"):
        inspect_bytes(tmp_path, make_zip(payload), max_files=10)


def test_rejects_zip_bomb_by_declared_size(tmp_path):
    """A 10 MB file of zeros compresses to a few KB. The header still says 10 MB."""
    data = make_zip({"index.html": b"\0" * (10 * 1024 * 1024)})
    assert len(data) < 200 * 1024, "test fixture should be highly compressible"
    with pytest.raises(ZipRejected, match="uncompressed"):
        inspect_bytes(tmp_path, data, max_bytes=1024 * 1024)


def test_rejects_exotic_compression(tmp_path):
    data = make_zip({"index.html": "x" * 4096}, compression=zipfile.ZIP_BZIP2)
    with pytest.raises(ZipRejected, match="compression method"):
        inspect_bytes(tmp_path, data)


def test_rejects_empty_archive(tmp_path):
    with pytest.raises(ZipRejected, match="no files"):
        inspect_bytes(tmp_path, make_zip({}))


def test_rejects_non_zip(tmp_path):
    with pytest.raises(ZipRejected, match="not a valid zip"):
        inspect_bytes(tmp_path, b"this is not a zip file, it is a lie")


def test_rejects_duplicate_paths(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("index.html", b"first")
        zf.writestr("./index.html", b"second")
    with pytest.raises(ZipRejected, match="duplicate"):
        inspect_bytes(tmp_path, buffer.getvalue())


# -- extraction -------------------------------------------------------------


def test_extract_writes_only_inside_the_root(tmp_path):
    root = os.path.join(str(tmp_path), "out")
    zip_path = write(tmp_path, make_zip({"index.html": "hi", "a/b/c.txt": "deep"}))
    entries = inspect(zip_path, extraction_root=root, **LIMITS)
    extract(zip_path, entries, root, max_bytes=LIMITS["max_bytes"])

    written = set()
    for base, _, files in os.walk(root):
        for name in files:
            written.add(os.path.relpath(os.path.join(base, name), root).replace(os.sep, "/"))
    assert written == {"index.html", "a/b/c.txt"}


def test_extract_stops_when_the_header_lied(tmp_path, monkeypatch):
    """Central directory says 4 bytes; the stream delivers far more."""
    root = os.path.join(str(tmp_path), "out")
    zip_path = write(tmp_path, make_zip({"index.html": "x" * 100_000}))
    entries = inspect(zip_path, extraction_root=root, **LIMITS)
    lying = [ZipEntry(name=entries[0].name, path=entries[0].path, size=4)]

    with pytest.raises(ZipRejected, match="larger than its declared size"):
        extract(zip_path, lying, root, max_bytes=LIMITS["max_bytes"])


def test_extract_honours_the_total_budget(tmp_path):
    root = os.path.join(str(tmp_path), "out")
    zip_path = write(tmp_path, make_zip({"index.html": "x" * 500_000}))
    entries = inspect(zip_path, extraction_root=root, **LIMITS)
    with pytest.raises(ZipRejected, match="uncompressed"):
        extract(zip_path, entries, root, max_bytes=1000)


# -- redundant root ---------------------------------------------------------


def test_strips_single_wrapping_directory():
    entries = [
        ZipEntry("mysite/index.html", "mysite/index.html", 10),
        ZipEntry("mysite/a.css", "mysite/a.css", 10),
    ]
    assert [e.path for e in strip_redundant_root(entries)] == ["index.html", "a.css"]


def test_keeps_root_when_index_is_already_there():
    entries = [
        ZipEntry("index.html", "index.html", 10),
        ZipEntry("docs/index.html", "docs/index.html", 10),
    ]
    assert [e.path for e in strip_redundant_root(entries)] == [
        "index.html",
        "docs/index.html",
    ]


def test_keeps_root_when_several_top_level_directories():
    entries = [
        ZipEntry("a/index.html", "a/index.html", 10),
        ZipEntry("b/index.html", "b/index.html", 10),
    ]
    assert len(strip_redundant_root(entries)) == 2
    assert strip_redundant_root(entries)[0].path == "a/index.html"


def test_module_has_no_execution_primitives():
    """NON-NEGOTIABLE #1, enforced mechanically."""
    source = open(zipvalidate.__file__, encoding="utf-8").read()
    for forbidden in ("subprocess", "os.system", "eval(", "exec(", "popen", "pty."):
        assert forbidden not in source
