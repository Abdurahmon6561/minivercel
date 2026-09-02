"""Content-type whitelist, and proof it reaches the wire.

The type must come only from the extension of the destination key. Nothing in
the archive - no member comment, no extra field, no declared type on the
multipart part the user uploaded - is ever consulted (SPEC.md step 5).
"""

from __future__ import annotations

import dataclasses
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.config import get_settings
from app.mimemap import DEFAULT_CONTENT_TYPE, content_type_for
from app.supabase import SupabaseClient

from .conftest import auth_headers, deploy, make_zip


# -- the map itself ----------------------------------------------------------


def test_index_html_is_html():
    assert content_type_for("index.html") == "text/html; charset=utf-8"


def test_unknown_extension_is_octet_stream():
    assert content_type_for("data.weird") == "application/octet-stream"
    assert content_type_for("data.weird") == DEFAULT_CONTENT_TYPE


@pytest.mark.parametrize(
    "name, expected",
    [
        ("index.html", "text/html; charset=utf-8"),
        ("page.htm", "text/html; charset=utf-8"),
        ("app.css", "text/css; charset=utf-8"),
        ("app.js", "text/javascript; charset=utf-8"),
        ("app.mjs", "text/javascript; charset=utf-8"),
        ("data.json", "application/json"),
        ("logo.svg", "image/svg+xml"),
        ("logo.png", "image/png"),
        ("photo.jpg", "image/jpeg"),
        ("photo.jpeg", "image/jpeg"),
        ("photo.webp", "image/webp"),
        ("anim.gif", "image/gif"),
        ("favicon.ico", "image/x-icon"),
        ("font.woff2", "font/woff2"),
        ("font.woff", "font/woff"),
        ("readme.txt", "text/plain; charset=utf-8"),
        ("feed.xml", "application/xml"),
    ],
)
def test_whitelist_matches_the_spec_table(name, expected):
    assert content_type_for(name) == expected


@pytest.mark.parametrize(
    "name",
    [
        "archive.tar",
        "binary.bin",
        "script.php",
        "app.exe",
        "applet.jar",
        "no-extension",
        "",
        ".hidden",
        "trailing.",
        "weird.HTMLX",
    ],
)
def test_everything_else_is_octet_stream(name):
    assert content_type_for(name) == "application/octet-stream"


def test_extension_matching_is_case_insensitive():
    assert content_type_for("INDEX.HTML") == "text/html; charset=utf-8"
    assert content_type_for("Logo.PNG") == "image/png"


def test_only_the_last_extension_counts():
    """A crafted name must not smuggle a type past the map."""
    assert content_type_for("evil.html.weird") == "application/octet-stream"
    assert content_type_for("safe.weird.html") == "text/html; charset=utf-8"


def test_the_type_follows_the_key_not_the_directory():
    assert content_type_for("assets/css/app.js") == "text/javascript; charset=utf-8"
    assert content_type_for("html/index.png") == "image/png"


# -- and that it survives the trip to Supabase -------------------------------


class _Capture(BaseHTTPRequestHandler):
    requests: list = []

    def do_POST(self):
        length = int(self.headers.get("content-length") or 0)
        self.rfile.read(length)
        type(self).requests.append({"path": self.path, "headers": dict(self.headers)})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"Key":"ok"}')

    def log_message(self, *args):
        pass


@pytest.fixture
def capture_server():
    """A real socket, so this asserts what leaves the process.

    The FakeSupabase used elsewhere records what the router *passed* to upload();
    it cannot catch a header lost between there and the wire.

    Yields (recorded requests, settings pointed at the capture server).
    """
    _Capture.requests = []
    server = HTTPServer(("127.0.0.1", 0), _Capture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    settings = dataclasses.replace(
        get_settings(), supabase_url="http://127.0.0.1:%d" % server.server_port
    )
    try:
        yield _Capture.requests, settings
    finally:
        server.shutdown()
        server.server_close()


async def test_upload_puts_the_content_type_on_the_wire(capture_server):
    requests, settings = capture_server
    client = SupabaseClient(settings)
    try:
        for key in ["d1/index.html", "d1/app.css", "d1/data.weird", "d1/logo.svg"]:
            await client.upload(key, b"payload", content_type_for(key))
    finally:
        await client.aclose()

    sent = {
        request["path"].split("/sites/")[-1]: request["headers"]
        for request in requests
    }
    assert sent["d1/index.html"]["Content-Type"] == "text/html; charset=utf-8"
    assert sent["d1/app.css"]["Content-Type"] == "text/css; charset=utf-8"
    assert sent["d1/data.weird"]["Content-Type"] == "application/octet-stream"
    assert sent["d1/logo.svg"]["Content-Type"] == "image/svg+xml"


async def test_upload_sends_x_upsert_so_redeploys_overwrite(capture_server):
    requests, settings = capture_server
    client = SupabaseClient(settings)
    try:
        await client.upload("d1/index.html", b"v1", "text/html; charset=utf-8")
        await client.upload("d1/index.html", b"v2", "text/html; charset=utf-8")
    finally:
        await client.aclose()

    assert len(requests) == 2
    for request in requests:
        assert request["headers"]["x-upsert"] == "true"


# -- and that a hostile archive cannot influence it --------------------------


async def test_the_zip_cannot_dictate_the_content_type(client, supabase):
    """The uploaded part claims text/html; the stored types follow the keys."""
    payload = make_zip({"index.html": "<h1>hi</h1>", "payload.weird": b"\x00\x01"})
    response = await client.post(
        "/api/deployments",
        headers=auth_headers(),
        files={"file": ("site.zip", payload, "text/html")},
        data={"slug": "demo"},
    )
    assert response.status_code == 201

    stored = {key.rsplit("/", 1)[-1]: ct for key, ct in supabase.upload_calls}
    assert stored["index.html"] == "text/html; charset=utf-8"
    assert stored["payload.weird"] == "application/octet-stream"


async def test_every_stored_object_has_a_whitelisted_type(client, supabase):
    await deploy(
        client,
        make_zip(
            {
                "index.html": "hi",
                "a.css": "body{}",
                "b.js": "1",
                "c.png": b"\x89PNG",
                "d.unknown": b"?",
            }
        ),
    )
    for key, content_type in supabase.upload_calls:
        assert content_type == content_type_for(key)
