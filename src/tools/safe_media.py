"""Fail-closed media container validation for local FFmpeg inputs.

The project accepts tenant uploads and downloads media from external services.
File extensions and HTTP content types are advisory only, so every such file
must be classified from its bytes before it can be passed to FFmpeg/FFprobe.
The command helpers also pin the demuxer and restrict nested protocols to local
files/pipes; this prevents an XML/HLS/DASH document disguised as media from
triggering autodetection or network access.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class UnsafeMediaError(ValueError):
    """Raised when a local file is not an approved media container."""


@dataclass(frozen=True)
class MediaContainer:
    kind: str
    ffmpeg_demuxer: str


_EXTENSION_KINDS: dict[str, frozenset[str]] = {
    ".mp4": frozenset({"iso-bmff"}),
    ".mov": frozenset({"iso-bmff"}),
    ".m4v": frozenset({"iso-bmff"}),
    ".m4a": frozenset({"iso-bmff"}),
    ".webm": frozenset({"matroska"}),
    ".mkv": frozenset({"matroska"}),
    ".avi": frozenset({"avi"}),
    ".mp3": frozenset({"mp3"}),
    ".wav": frozenset({"wav"}),
    ".ogg": frozenset({"ogg"}),
    ".opus": frozenset({"ogg"}),
    ".flac": frozenset({"flac"}),
    ".png": frozenset({"png"}),
    ".jpg": frozenset({"jpeg"}),
    ".jpeg": frozenset({"jpeg"}),
    ".webp": frozenset({"webp"}),
    ".gif": frozenset({"gif"}),
}

_DEMUXERS = {
    "iso-bmff": "mov",
    "matroska": "matroska",
    "avi": "avi",
    "mp3": "mp3",
    "wav": "wav",
    "ogg": "ogg",
    "flac": "flac",
    "png": "png_pipe",
    "jpeg": "image2",
    "webp": "webp_pipe",
    "gif": "gif",
}

_WAVE_FORMAT_IMA_ADPCM = 0x0011
_WAVE_FORMAT_EXTENSIBLE = 0xFFFE
_WAVE_SUBFORMAT_GUID_TAIL = bytes.fromhex("00001000800000aa00389b71")


def _wav_format_tag(header: bytes) -> int | None:
    offset = 12
    while offset + 8 <= len(header):
        chunk_id = header[offset : offset + 4]
        chunk_size = int.from_bytes(header[offset + 4 : offset + 8], "little")
        data_start = offset + 8
        data_end = data_start + chunk_size
        if data_end > len(header):
            return None
        if chunk_id == b"fmt ":
            if chunk_size < 2:
                return None
            format_tag = int.from_bytes(header[data_start : data_start + 2], "little")
            if format_tag != _WAVE_FORMAT_EXTENSIBLE:
                return format_tag
            if chunk_size < 40:
                return None
            extension_size = int.from_bytes(
                header[data_start + 16 : data_start + 18], "little"
            )
            if extension_size < 22 or 18 + extension_size > chunk_size:
                return None
            subformat = header[data_start + 24 : data_start + 40]
            if len(subformat) != 16 or subformat[4:] != _WAVE_SUBFORMAT_GUID_TAIL:
                return None
            effective_tag = int.from_bytes(subformat[:4], "little")
            if effective_tag > 0xFFFF:
                return None
            return effective_tag
        offset = data_end + (chunk_size & 1)
    return None


def _classify_header(header: bytes) -> str | None:
    stripped = header.lstrip()
    lowered = stripped[:32].lower()
    if lowered.startswith((b"<", b"#extm3u", b"[playlist]")):
        return None
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "iso-bmff"
    if header.startswith(b"\x1aE\xdf\xa3"):
        return "matroska"
    if header.startswith(b"RIFF") and header[8:12] == b"AVI ":
        return "avi"
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return "wav"
    if header.startswith(b"ID3") or (
        len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0
    ):
        return "mp3"
    if header.startswith(b"OggS"):
        return "ogg"
    if header.startswith(b"fLaC"):
        return "flac"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "webp"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    return None


def validate_media_file(
    path: str | Path,
    *,
    expected_extension: str | None = None,
) -> MediaContainer:
    """Classify an approved local media file from bytes and extension.

    The validation deliberately does not invoke FFmpeg. This keeps playlist or
    XML payloads away from vulnerable demuxers during the trust decision.
    """

    media_path = Path(path)
    if not media_path.is_file() or media_path.is_symlink():
        raise UnsafeMediaError("media input must be a regular local file")
    extension = (expected_extension or media_path.suffix).lower()
    allowed_kinds = _EXTENSION_KINDS.get(extension)
    if allowed_kinds is None:
        raise UnsafeMediaError("media extension is not approved")
    try:
        with media_path.open("rb") as handle:
            header = handle.read(4096)
    except OSError as exc:
        raise UnsafeMediaError("media input could not be read") from exc
    kind = _classify_header(header)
    if kind is None or kind not in allowed_kinds:
        raise UnsafeMediaError("media bytes do not match the approved extension")
    if kind == "wav":
        format_tag = _wav_format_tag(header)
        if format_tag is None or format_tag == _WAVE_FORMAT_IMA_ADPCM:
            raise UnsafeMediaError("WAV codec is not approved")
    return MediaContainer(kind=kind, ffmpeg_demuxer=_DEMUXERS[kind])


def ffmpeg_local_input_args(path: str | Path) -> list[str]:
    """Return a validated, demuxer-pinned, no-network FFmpeg input."""

    container = validate_media_file(path)
    return [
        "-protocol_whitelist",
        "file,pipe",
        "-f",
        container.ffmpeg_demuxer,
        "-i",
        str(path),
    ]


def ffprobe_local_input_args(path: str | Path) -> list[str]:
    """Return a validated, demuxer-pinned, no-network FFprobe input."""

    return ffmpeg_local_input_args(path)
