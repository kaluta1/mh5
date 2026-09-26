"""Lossless removal of hidden image metadata at upload (Child/Teen Safety s.10).

s.10: "Strip unnecessary metadata from uploaded photographs and videos,
including geolocation metadata where technically appropriate. Do not publish
hidden EXIF/GPS metadata."

Scope (Phase 5, deliberately narrow):
- JPEG: drops APP1 (EXIF, XMP), APP3-APP13 and APP15 (IPTC/Photoshop, vendor
  data), non-ICC APP2 (FlashPix, MPF) and COM segments, and any bytes after
  the end-of-image marker (appended secondary images such as MPF depth/preview
  frames carry their own EXIF/GPS). APP0 (JFIF), APP2 ICC_PROFILE and APP14
  (Adobe colour transform) are kept. The EXIF orientation tag alone is re-added
  so photos keep displaying upright. Pixel data is never re-encoded.
- PNG: drops eXIf, tEXt, zTXt, iTXt and tIME chunks.
- WebP: drops EXIF and XMP chunks and clears their VP8X flags.
- GIF and every video format: not handled here (no reliable pure-Python
  stripping). They are reported as NOT sanitized; the Phase 5 contest workflow
  then refuses to publicly activate a minor's entry that uses them.

The result is re-checked with Pillow. On any failure the caller gets the
original bytes and sanitized=False (fail safe: never claim a strip that did not
happen).
"""
from __future__ import annotations

import logging
import struct
from io import BytesIO
from typing import Tuple

from PIL import Image

logger = logging.getLogger(__name__)

_EXIF_ORIENTATION = 0x0112
_EXIF_GPS_IFD = 0x8825

_JPEG_KEEP_APP = {0xE0, 0xEE}           # APP0 JFIF, APP14 Adobe
_PNG_DROP = {b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"}
_WEBP_DROP = {b"EXIF", b"XMP "}


class MetadataStripError(ValueError):
    pass


# ---------------------------------------------------------------------------
# JPEG
# ---------------------------------------------------------------------------

def _jpeg_orientation(content: bytes) -> int:
    try:
        with Image.open(BytesIO(content)) as image:
            value = image.getexif().get(_EXIF_ORIENTATION)
        return int(value) if value in range(2, 9) else 1
    except Exception:
        return 1


def _orientation_segment(orientation: int) -> bytes:
    exif = Image.Exif()
    exif[_EXIF_ORIENTATION] = orientation
    payload = exif.tobytes()  # b"Exif\0\0" + TIFF header + IFD0 with the orientation tag only
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


def _strip_jpeg(content: bytes) -> bytes:
    if not content.startswith(b"\xff\xd8"):
        raise MetadataStripError("not a JPEG")
    orientation = _jpeg_orientation(content)
    out = bytearray(b"\xff\xd8")
    inserted_orientation = orientation == 1
    pos, size = 2, len(content)
    while pos < size:
        if content[pos] != 0xFF:
            raise MetadataStripError("malformed JPEG marker")
        while pos < size and content[pos] == 0xFF:   # fill bytes
            pos += 1
        if pos >= size:
            raise MetadataStripError("truncated JPEG")
        marker = content[pos]
        pos += 1
        if marker == 0xD9:                            # EOI before any scan
            out += b"\xff\xd9"
            return bytes(out)
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:  # standalone markers
            out += bytes((0xFF, marker))
            continue
        if pos + 2 > size:
            raise MetadataStripError("truncated JPEG segment")
        length = struct.unpack(">H", content[pos:pos + 2])[0]
        if length < 2 or pos + length > size:
            raise MetadataStripError("invalid JPEG segment length")
        segment = content[pos - 2:pos + length]
        body = content[pos + 2:pos + length]
        pos += length
        if marker == 0xDA:                            # SOS: entropy-coded data follows
            if not inserted_orientation:
                out += _orientation_segment(orientation)
                inserted_orientation = True
            out += segment
            end = _find_eoi(content, pos)
            out += content[pos:end]                   # scans (incl. later DHT/SOS) up to and incl. EOI
            return bytes(out)                         # anything after EOI is dropped
        keep = True
        if 0xE0 <= marker <= 0xEF:
            keep = marker in _JPEG_KEEP_APP or (marker == 0xE2 and body.startswith(b"ICC_PROFILE\x00"))
        elif marker == 0xFE:                          # COM
            keep = False
        if keep:
            if not inserted_orientation and not (marker == 0xE0):
                out += _orientation_segment(orientation)
                inserted_orientation = True
            out += segment
    raise MetadataStripError("JPEG without image data")


def _find_eoi(content: bytes, pos: int) -> int:
    size = len(content)
    while pos < size - 1:
        if content[pos] == 0xFF:
            nxt = content[pos + 1]
            if nxt == 0xD9:
                return pos + 2
            if nxt == 0x00 or nxt == 0xFF or 0xD0 <= nxt <= 0xD7:
                pos += 1 if nxt == 0xFF else 2
                continue
            # A marker segment between progressive scans (DHT, SOS, DRI, ...).
            if pos + 4 <= size:
                length = struct.unpack(">H", content[pos + 2:pos + 4])[0]
                if 0xE0 <= nxt <= 0xEF or nxt == 0xFE:
                    raise MetadataStripError("metadata segment between scans")
                pos += 2 + length
                continue
        pos += 1
    raise MetadataStripError("JPEG end-of-image marker not found")


# ---------------------------------------------------------------------------
# PNG / WebP
# ---------------------------------------------------------------------------

def _strip_png(content: bytes) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    if not content.startswith(signature):
        raise MetadataStripError("not a PNG")
    out = bytearray(signature)
    pos = len(signature)
    while pos + 12 <= len(content):
        length = struct.unpack(">I", content[pos:pos + 4])[0]
        ctype = content[pos + 4:pos + 8]
        end = pos + 12 + length
        if end > len(content):
            raise MetadataStripError("truncated PNG chunk")
        if ctype not in _PNG_DROP:
            out += content[pos:end]
        pos = end
        if ctype == b"IEND":
            return bytes(out)                          # trailing bytes after IEND are dropped
    raise MetadataStripError("PNG without IEND")


def _strip_webp(content: bytes) -> bytes:
    if len(content) < 12 or content[:4] != b"RIFF" or content[8:12] != b"WEBP":
        raise MetadataStripError("not a WebP")
    riff_end = min(len(content), 8 + struct.unpack("<I", content[4:8])[0])
    chunks = bytearray()
    pos = 12
    while pos + 8 <= riff_end:
        ctype = content[pos:pos + 4]
        length = struct.unpack("<I", content[pos + 4:pos + 8])[0]
        end = pos + 8 + length + (length & 1)
        if pos + 8 + length > riff_end:
            raise MetadataStripError("truncated WebP chunk")
        chunk = bytearray(content[pos:min(end, riff_end)])
        if ctype == b"VP8X" and length >= 1:
            chunk[8] &= ~(0x08 | 0x04) & 0xFF          # clear EXIF and XMP flags
        if ctype not in _WEBP_DROP:
            chunks += chunk
        pos = end
    return b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WEBP" + bytes(chunks)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_STRIPPERS = {"image/jpeg": _strip_jpeg, "image/png": _strip_png, "image/webp": _strip_webp}


def has_hidden_metadata(content: bytes) -> bool:
    """True when Pillow still finds EXIF beyond the orientation tag, GPS data or
    XMP/text metadata. Used to verify a strip."""
    with Image.open(BytesIO(content)) as image:
        exif = image.getexif()
        if any(tag != _EXIF_ORIENTATION for tag in exif.keys()) or exif.get_ifd(_EXIF_GPS_IFD):
            return True
        # The raw "exif" block is judged by its tags above (orientation only is allowed).
        info_keys = {k.lower() for k in image.info.keys()}
        return bool(info_keys & {"xmp", "xml:com.adobe.xmp", "comment", "photoshop", "iptc"})


def strip_image_metadata(content: bytes, content_type: str) -> Tuple[bytes, bool]:
    """(bytes to store, sanitized). sanitized=True only when the strip ran and the
    result verifiably decodes without hidden metadata."""
    stripper = _STRIPPERS.get((content_type or "").lower())
    if stripper is None:
        return content, False
    try:
        cleaned = stripper(content)
        with Image.open(BytesIO(cleaned)) as image:
            image.verify()
        if has_hidden_metadata(cleaned):
            raise MetadataStripError("metadata still present after strip")
        return cleaned, True
    except Exception as exc:  # never fail the upload here; report "not sanitized" instead
        logger.warning("Image metadata strip skipped (%s): %s", content_type, type(exc).__name__)
        return content, False
