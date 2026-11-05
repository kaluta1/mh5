"""Video creative validation contract (Advertising Phase A foundation; NOT exposed to any upload path).

Approved provisional limits: at most 100 MB and 60 seconds. The duration is read SERVER-SIDE from the MP4
container (ISO BMFF 'moov/mvhd' box): a client-reported duration is never trusted. Only MP4 (ftyp brand
isom / mp41 / mp42 / avc1 / iso2..iso6 / dash) is accepted, because its duration can be verified here without
an external tool; WebM / MOV / anything else is refused until a verified media pipeline exists.

Why Video CPM and CPV stay NOT READY (ad_packages): the shared media store caps videos at 32 MB
(app.core.storage.MEDIA_VIDEO_MAX_BYTES) with no duration check, there is no transcoding to a safe delivery
format and no ad video player in the frontend. This module is the validation those will call.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Optional

VIDEO_MAX_BYTES = 100 * 1024 * 1024
VIDEO_MAX_DURATION_MS = 60_000
VIDEO_MIN_DURATION_MS = 1_000
ACCEPTED_BRANDS = {b"isom", b"mp41", b"mp42", b"avc1", b"iso2", b"iso3", b"iso4", b"iso5", b"iso6", b"dash"}
MP4_MIME = "video/mp4"


class VideoError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class VideoInfo:
    mime: str
    size: int
    duration_ms: int


def _boxes(data: bytes, start: int, end: int):
    """Top-level ISO BMFF boxes in data[start:end]: (type, payload_start, box_end). Bounded, never loops."""
    pos, seen = start, 0
    while pos + 8 <= end and seen < 10_000:
        size, kind = struct.unpack(">I4s", data[pos:pos + 8])
        header = 8
        if size == 1:
            if pos + 16 > end:
                raise VideoError("CORRUPT_VIDEO", "The video file is damaged")
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header or pos + size > end:
            raise VideoError("CORRUPT_VIDEO", "The video file is damaged")
        yield kind, pos + header, pos + size
        pos += size
        seen += 1


def _mvhd_duration_ms(data: bytes, start: int, end: int) -> Optional[int]:
    version = data[start]
    if version == 1:
        if start + 4 + 28 > end:
            return None
        timescale, duration = struct.unpack(">IQ", data[start + 20:start + 32])
    else:
        if start + 4 + 16 > end:
            return None
        timescale, duration = struct.unpack(">II", data[start + 12:start + 20])
    if timescale <= 0:
        return None
    return int(duration * 1000 // timescale)


def inspect(declared_mime: Optional[str], content: bytes) -> VideoInfo:
    """Validate an uploaded ad video. Raises VideoError with a clear code; never trusts the client."""
    size = len(content or b"")
    if size == 0:
        raise VideoError("EMPTY_VIDEO", "The video file is empty")
    if size > VIDEO_MAX_BYTES:
        raise VideoError("VIDEO_TOO_LARGE", "The video must be at most 100 MB")
    if (declared_mime or "").split(";")[0].strip().lower() != MP4_MIME:
        raise VideoError("UNSUPPORTED_VIDEO", "Upload an MP4 video (H.264/AAC)")
    if size < 12 or content[4:8] != b"ftyp" or content[8:12] not in ACCEPTED_BRANDS:
        raise VideoError("UNSUPPORTED_VIDEO", "The file is not an MP4 video")
    duration = None
    for kind, payload, box_end in _boxes(content, 0, size):
        if kind == b"moov":
            for inner, ipayload, iend in _boxes(content, payload, box_end):
                if inner == b"mvhd":
                    duration = _mvhd_duration_ms(content, ipayload, iend)
                    break
            break
    if duration is None:
        raise VideoError("NO_DURATION", "The video duration could not be verified (no moov/mvhd box)")
    if duration < VIDEO_MIN_DURATION_MS:
        raise VideoError("VIDEO_TOO_SHORT", "The video must last at least 1 second")
    if duration > VIDEO_MAX_DURATION_MS:
        raise VideoError("VIDEO_TOO_LONG", "The video must last at most 60 seconds")
    return VideoInfo(mime=MP4_MIME, size=size, duration_ms=duration)


def cpv_threshold_ms(duration_ms: Optional[int]) -> Optional[int]:
    """A CPV view: 10 seconds of qualifying playback, or the whole video when it is shorter. None when the
    creative's server-verified duration is unknown (then no view can qualify)."""
    from app.services.ad_packages import CPV_MIN_MS

    if not duration_ms or duration_ms <= 0:
        return None
    return min(CPV_MIN_MS, int(duration_ms))


# ---------------------------------------------------------------- workflow ad videos (2026-11-05)
#
# Owner-approved specification: MP4, H.264 video, AAC audio when there is audio, 6-30 seconds, at most 50 MB,
# 1080 x 1920 (vertical) or 1080 x 1080 (square). Everything is read from the file on the server (codec boxes
# in moov/trak/mdia/minf/stbl/stsd, size from tkhd, duration from mvhd). The shared media store caps videos at
# 32 MB (app.core.storage.MEDIA_VIDEO_MAX_BYTES), so the effective limit is the smaller of the two.

AD_VIDEO_SPEC_MAX_BYTES = 50 * 1024 * 1024
AD_VIDEO_MIN_MS, AD_VIDEO_MAX_MS = 6_000, 30_000
AD_VIDEO_SIZES = ((1080, 1920), (1080, 1080))


def _store_cap() -> int:
    from app.core.storage import MEDIA_VIDEO_MAX_BYTES

    return int(MEDIA_VIDEO_MAX_BYTES)


AD_VIDEO_MAX_BYTES = min(AD_VIDEO_SPEC_MAX_BYTES, _store_cap())


@dataclass(frozen=True)
class AdVideoInfo:
    mime: str
    size: int
    duration_ms: int
    width: int
    height: int
    video_codec: str
    audio_codec: Optional[str]


def rules() -> dict:
    return {"container": "MP4", "video_codec": "H.264", "audio_codec": "AAC (when the video has audio)",
            "min_seconds": AD_VIDEO_MIN_MS // 1000, "max_seconds": AD_VIDEO_MAX_MS // 1000,
            "max_bytes": AD_VIDEO_MAX_BYTES, "spec_max_bytes": AD_VIDEO_SPEC_MAX_BYTES,
            "sizes": [f"{w}x{h}" for w, h in AD_VIDEO_SIZES],
            "note": ("The media store currently accepts videos up to 32 MB, below the 50 MB specification."
                     if AD_VIDEO_MAX_BYTES < AD_VIDEO_SPEC_MAX_BYTES else None),
            "delivery": "Not delivered yet: Video CPM and CPV are not ready (no ad video player). Preview only."}


def _find(data: bytes, start: int, end: int, kind: bytes):
    for k, p, e in _boxes(data, start, end):
        if k == kind:
            return p, e
    return None


def _tracks(data: bytes, moov_start: int, moov_end: int):
    """(handler, width, height, codec) per track."""
    out = []
    for kind, p, e in _boxes(data, moov_start, moov_end):
        if kind != b"trak":
            continue
        width = height = 0
        tkhd = _find(data, p, e, b"tkhd")
        if tkhd and tkhd[1] - tkhd[0] >= 8:
            width, height = struct.unpack(">II", data[tkhd[1] - 8:tkhd[1]])
            width, height = width >> 16, height >> 16
        handler = codec = None
        mdia = _find(data, p, e, b"mdia")
        if mdia:
            hdlr = _find(data, mdia[0], mdia[1], b"hdlr")
            if hdlr and hdlr[1] - hdlr[0] >= 12:
                handler = data[hdlr[0] + 8:hdlr[0] + 12]
            minf = _find(data, mdia[0], mdia[1], b"minf")
            stbl = _find(data, minf[0], minf[1], b"stbl") if minf else None
            stsd = _find(data, stbl[0], stbl[1], b"stsd") if stbl else None
            if stsd and stsd[1] - stsd[0] >= 16:
                codec = data[stsd[0] + 12:stsd[0] + 16]
        out.append((handler, int(width), int(height), codec))
    return out


def inspect_ad_video(declared_mime: Optional[str], content: bytes) -> AdVideoInfo:
    """Validate an advertising video against the workflow specification. Raises VideoError."""
    size = len(content or b"")
    if size > AD_VIDEO_MAX_BYTES:
        raise VideoError("VIDEO_TOO_LARGE", f"The video must be at most {AD_VIDEO_MAX_BYTES // (1024 * 1024)} MB")
    base = inspect(declared_mime, content)              # MP4 container, brand, duration (mvhd)
    if base.duration_ms < AD_VIDEO_MIN_MS or base.duration_ms > AD_VIDEO_MAX_MS:
        raise VideoError("VIDEO_DURATION", "The video must last between 6 and 30 seconds")
    moov = _find(content, 0, size, b"moov")
    tracks = _tracks(content, moov[0], moov[1]) if moov else []
    video = [t for t in tracks if t[0] == b"vide"]
    audio = [t for t in tracks if t[0] == b"soun"]
    if len(video) != 1:
        raise VideoError("UNSUPPORTED_VIDEO", "The file must contain exactly one video track")
    if video[0][3] not in (b"avc1", b"avc3"):
        raise VideoError("UNSUPPORTED_CODEC", "The video must be encoded with H.264")
    if any(a[3] != b"mp4a" for a in audio):
        raise VideoError("UNSUPPORTED_CODEC", "The audio must be AAC")
    width, height = video[0][1], video[0][2]
    if (width, height) not in AD_VIDEO_SIZES:
        raise VideoError("UNSUPPORTED_SIZE", "The video must be 1080 x 1920 (vertical) or 1080 x 1080 (square)")
    return AdVideoInfo(mime=MP4_MIME, size=size, duration_ms=base.duration_ms, width=width, height=height,
                       video_codec="H.264", audio_codec="AAC" if audio else None)
