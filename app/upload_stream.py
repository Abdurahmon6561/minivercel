"""Streaming multipart receiver.

SPEC.md upload flow step 2: "Stream the upload to /tmp/{uuid}.zip. Reject at
50 MB *while streaming* - do not read the whole body into memory first."

That rules out FastAPI's `UploadFile`/`request.form()`: Starlette parses the
entire multipart body before the endpoint function is entered, so by the time we
could look at a size we have already accepted it. Instead we drive
python-multipart's incremental parser over `request.stream()` ourselves and
abort mid-body the moment the counter crosses the cap - the connection is closed
with a 413 and the remaining bytes are never read.

Two cheaper checks run first: `Content-Length` when the client sends one, and
the `Content-Type` boundary.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from python_multipart.multipart import MultipartParser, parse_options_header

# Multipart framing overhead we tolerate on top of the payload cap.
ENVELOPE_SLACK = 1024 * 1024

# Total budget for ordinary (non-file) form fields.
MAX_FIELDS_BYTES = 64 * 1024
MAX_FIELDS = 20


class UploadTooLarge(Exception):
    def __init__(self, limit: int) -> None:
        super().__init__("Upload exceeds the %d byte limit." % limit)
        self.limit = limit


class MalformedUpload(Exception):
    pass


@dataclass
class ReceivedUpload:
    path: str
    size: int
    filename: str | None = None
    fields: dict[str, str] = field(default_factory=dict)


class _Receiver:
    """Callback target for MultipartParser."""

    def __init__(self, dest_path: str, max_bytes: int, file_field: str) -> None:
        self.dest_path = dest_path
        self.max_bytes = max_bytes
        self.file_field = file_field

        self.size = 0
        self.filename: str | None = None
        self.fields: dict[str, str] = {}
        self.got_file = False

        self._sink = None
        self._header_field = b""
        self._header_value = b""
        self._headers: dict[bytes, bytes] = {}
        self._is_target = False
        self._is_text_field = False
        self._text_name = ""
        self._text_value = bytearray()
        self._fields_bytes = 0

    # -- parser callbacks --------------------------------------------------

    def on_part_begin(self) -> None:
        self._headers = {}
        self._header_field = b""
        self._header_value = b""
        self._is_target = False
        self._is_text_field = False
        self._text_name = ""
        self._text_value = bytearray()

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_field += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._header_value += data[start:end]

    def on_header_end(self) -> None:
        self._headers[self._header_field.lower()] = self._header_value
        self._header_field = b""
        self._header_value = b""

    def on_headers_finished(self) -> None:
        disposition = self._headers.get(b"content-disposition", b"")
        _, params = parse_options_header(disposition)
        name = params.get(b"name", b"").decode("utf-8", "replace")
        raw_filename = params.get(b"filename")

        is_file_part = raw_filename is not None
        if is_file_part and not self.got_file and (name == self.file_field or not self.file_field):
            self._is_target = True
            self.filename = raw_filename.decode("utf-8", "replace")
            self._sink = open(self.dest_path, "wb")
        elif not is_file_part and name:
            self._is_text_field = True
            self._text_name = name

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        chunk = data[start:end]
        if self._is_target and self._sink is not None:
            self.size += len(chunk)
            if self.size > self.max_bytes:
                raise UploadTooLarge(self.max_bytes)
            self._sink.write(chunk)
        elif self._is_text_field:
            self._fields_bytes += len(chunk)
            if self._fields_bytes > MAX_FIELDS_BYTES:
                raise MalformedUpload("Form fields are too large.")
            self._text_value += chunk

    def on_part_end(self) -> None:
        if self._is_target and self._sink is not None:
            self._sink.close()
            self._sink = None
            self.got_file = True
        elif self._is_text_field:
            if len(self.fields) >= MAX_FIELDS:
                raise MalformedUpload("Too many form fields.")
            self.fields[self._text_name] = self._text_value.decode("utf-8", "replace")
        self._is_target = False
        self._is_text_field = False

    def on_end(self) -> None:
        pass

    def close(self) -> None:
        if self._sink is not None:
            self._sink.close()
            self._sink = None


def _boundary(content_type: str | None) -> bytes:
    if not content_type:
        raise MalformedUpload("Expected a multipart/form-data body.")
    value, params = parse_options_header(content_type)
    if value != b"multipart/form-data":
        raise MalformedUpload("Expected a multipart/form-data body.")
    boundary = params.get(b"boundary")
    if not boundary:
        raise MalformedUpload("multipart/form-data body has no boundary.")
    return boundary


async def receive_upload(
    request,
    dest_path: str,
    *,
    max_bytes: int,
    file_field: str = "file",
) -> ReceivedUpload:
    """Stream one multipart file part to `dest_path`.

    Raises UploadTooLarge as soon as the cap is crossed, without reading the
    rest of the body. The caller is responsible for deleting `dest_path` in a
    `finally` block (NON-NEGOTIABLE #6) - we delete it ourselves on the failure
    paths we raise from, but the caller must still guarantee it.
    """
    declared = request.headers.get("content-length")
    if declared:
        try:
            if int(declared) > max_bytes + ENVELOPE_SLACK:
                raise UploadTooLarge(max_bytes)
        except ValueError:
            raise MalformedUpload("Invalid Content-Length header.")

    boundary = _boundary(request.headers.get("content-type"))
    receiver = _Receiver(dest_path, max_bytes, file_field)
    parser = MultipartParser(
        boundary,
        callbacks={
            "on_part_begin": receiver.on_part_begin,
            "on_header_field": receiver.on_header_field,
            "on_header_value": receiver.on_header_value,
            "on_header_end": receiver.on_header_end,
            "on_headers_finished": receiver.on_headers_finished,
            "on_part_data": receiver.on_part_data,
            "on_part_end": receiver.on_part_end,
            "on_end": receiver.on_end,
        },
    )

    try:
        async for chunk in request.stream():
            if chunk:
                parser.write(chunk)
        parser.finalize()
    except (UploadTooLarge, MalformedUpload):
        receiver.close()
        _unlink(dest_path)
        raise
    except Exception as exc:
        receiver.close()
        _unlink(dest_path)
        raise MalformedUpload("Could not parse the upload: %s" % exc) from exc
    finally:
        receiver.close()

    if not receiver.got_file:
        _unlink(dest_path)
        raise MalformedUpload(
            "No file part named %r was present in the request." % file_field
        )

    return ReceivedUpload(
        path=dest_path,
        size=receiver.size,
        filename=receiver.filename,
        fields=receiver.fields,
    )


def _unlink(path: str) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError:
        pass
