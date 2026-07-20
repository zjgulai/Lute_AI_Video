from __future__ import annotations

import ast
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
import yt_dlp

from scripts import generate_portfolio_posters, generate_portfolio_thumbnails
from src.models.provider_cost import ProviderCostContractError
from src.tools import poster_extractor
from src.tools.cosyvoice_client import _validate_response_format
from src.tools.safe_media import (
    UnsafeMediaError,
    ffmpeg_local_input_args,
    validate_media_file,
)
from src.tools.video_downloader import (
    YTDLP_SAFE_FORMAT,
    VideoDownloader,
    VideoDownloadError,
)


def test_mp4_input_is_byte_validated_and_ffmpeg_is_fail_closed(tmp_path: Path) -> None:
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2")

    assert validate_media_file(media).ffmpeg_demuxer == "mov"
    assert ffmpeg_local_input_args(media) == [
        "-protocol_whitelist",
        "file,pipe",
        "-f",
        "mov",
        "-i",
        str(media),
    ]


@pytest.mark.parametrize(
    "payload",
    [
        b"<?xml version='1.0'?><MPD><BaseURL>https://example.invalid/</BaseURL></MPD>",
        b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nhttps://example.invalid/a.m3u8",
    ],
)
def test_playlist_or_xml_disguised_as_mp4_is_rejected_before_ffmpeg(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
) -> None:
    media = tmp_path / "clip.mp4"
    media.write_bytes(payload)
    calls = 0

    def forbidden(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("unsafe media must not reach FFmpeg")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(poster_extractor, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(poster_extractor, "POSTER_DIR", tmp_path / "posters")

    with pytest.raises(UnsafeMediaError, match="media bytes do not match"):
        ffmpeg_local_input_args(media)
    assert poster_extractor.ensure_poster(media) is None
    assert calls == 0


def test_extension_and_container_must_agree(tmp_path: Path) -> None:
    media = tmp_path / "clip.webm"
    media.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2")

    with pytest.raises(UnsafeMediaError, match="media bytes do not match"):
        validate_media_file(media)


@pytest.mark.parametrize(
    ("suffix", "payload", "demuxer"),
    [
        (".mp3", b"ID3\x03\x00\x00\x00\x00\x00\x00", "mp3"),
        (".opus", b"OggS\x00\x02fixture-opus", "ogg"),
        (".wav", b"RIFF\x10\x00\x00\x00WAVEfmt ", "wav"),
    ],
)
def test_cosyvoice_container_formats_are_explicitly_supported(
    tmp_path: Path,
    suffix: str,
    payload: bytes,
    demuxer: str,
) -> None:
    media = tmp_path / f"speech{suffix}"
    media.write_bytes(payload)

    assert _validate_response_format(suffix.removeprefix(".")) == suffix.removeprefix(".")
    assert validate_media_file(media).ffmpeg_demuxer == demuxer


def test_raw_pcm_is_rejected_until_layout_is_explicit(tmp_path: Path) -> None:
    media = tmp_path / "speech.pcm"
    media.write_bytes(b"\x00\x00" * 100)

    with pytest.raises(ProviderCostContractError, match="response format is unsupported"):
        _validate_response_format("pcm")
    with pytest.raises(UnsafeMediaError, match="extension is not approved"):
        validate_media_file(media)


def test_every_literal_ffmpeg_file_input_uses_the_central_guard() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    violations: list[str] = []

    runtime_paths = sorted((repo_root / "src").rglob("*.py")) + sorted(
        (repo_root / "scripts").rglob("*.py")
    )
    for source_path in runtime_paths:
        source = source_path.read_text()
        tree = ast.parse(source, filename=str(source_path))
        command_nodes: list[ast.AST] = [
            node for node in ast.walk(tree) if isinstance(node, (ast.List, ast.Tuple))
        ]
        command_nodes.extend(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_subprocess_exec"
        )

        for node in command_nodes:
            segment = ast.get_source_segment(source, node) or ""
            literals = {
                child.value
                for child in ast.walk(node)
                if isinstance(child, ast.Constant) and isinstance(child.value, str)
            }
            if "ffprobe" in literals:
                if "-version" not in literals and "ffprobe_local_input_args" not in segment:
                    violations.append(
                        f"{source_path.relative_to(repo_root)}:{getattr(node, 'lineno', 0)}:ffprobe"
                    )
            if "ffmpeg" not in literals or "-i" not in literals:
                continue
            guarded = "ffmpeg_local_input_args" in segment
            generated = "lavfi" in literals
            controlled_concat = (
                "concat" in literals
                and "-protocol_whitelist" in literals
                and "file,pipe" in literals
            )
            if not (guarded or generated or controlled_concat):
                violations.append(
                    f"{source_path.relative_to(repo_root)}:{getattr(node, 'lineno', 0)}:ffmpeg"
                )

    assert violations == []


@pytest.mark.parametrize(
    "entrypoint",
    [
        lambda source, dest: generate_portfolio_thumbnails._ffprobe_valid(source),
        generate_portfolio_thumbnails._extract_poster,
        generate_portfolio_posters.extract_poster,
    ],
)
def test_portfolio_scripts_reject_disguised_media_before_subprocess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    entrypoint,
) -> None:
    media = tmp_path / "disguised.mp4"
    media.write_bytes(b"<?xml version='1.0'?><MPD><BaseURL>https://example.invalid/</BaseURL></MPD>")
    poster = tmp_path / "poster.jpg"
    calls = 0

    def forbidden(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("unsafe media must not reach subprocess")

    monkeypatch.setattr(subprocess, "run", forbidden)

    assert entrypoint(media, poster) is False
    assert calls == 0


def _select_ytdlp_formats(formats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ydl = yt_dlp.YoutubeDL({"quiet": True, "format": YTDLP_SAFE_FORMAT})
    selector = ydl.build_format_selector(YTDLP_SAFE_FORMAT)
    return getattr(ydl, "_select_formats")(formats, selector)


def test_ytdlp_selector_never_requests_separate_stream_merge() -> None:
    separate_http = [
        {
            "format_id": "video-only",
            "url": "https://example.invalid/video.mp4",
            "ext": "mp4",
            "protocol": "https",
            "vcodec": "h264",
            "acodec": "none",
        },
        {
            "format_id": "audio-only",
            "url": "https://example.invalid/audio.m4a",
            "ext": "m4a",
            "protocol": "https",
            "vcodec": "none",
            "acodec": "aac",
        },
    ]
    separate_dash = [
        {**separate_http[0], "format_id": "dash-video", "protocol": "http_dash_segments"},
        {**separate_http[1], "format_id": "dash-audio", "protocol": "http_dash_segments"},
    ]
    combined_hls = [
        {
            "format_id": "hls-av",
            "url": "https://example.invalid/media.m3u8",
            "ext": "mp4",
            "protocol": "m3u8_native",
            "vcodec": "h264",
            "acodec": "aac",
        }
    ]
    delegated_protocols = [
        combined_hls[0],
        {
            "format_id": "dash-av",
            "url": "https://example.invalid/media.mpd",
            "ext": "mp4",
            "protocol": "http_dash_segments",
            "vcodec": "h264",
            "acodec": "aac",
        },
        {
            "format_id": "rtmp-av",
            "url": "rtmp://example.invalid/live",
            "ext": "flv",
            "protocol": "rtmp",
            "vcodec": "h264",
            "acodec": "aac",
        },
    ]

    assert "+" not in YTDLP_SAFE_FORMAT
    assert _select_ytdlp_formats(separate_http) == []
    assert _select_ytdlp_formats(separate_dash) == []
    progressive = [
        {
            "format_id": "progressive-av",
            "url": "https://example.invalid/media.mp4",
            "ext": "mp4",
            "protocol": "https",
            "vcodec": "h264",
            "acodec": "aac",
        }
    ]

    assert _select_ytdlp_formats(delegated_protocols) == []
    selected = _select_ytdlp_formats(progressive)
    assert [item["format_id"] for item in selected] == ["progressive-av"]
    assert selected[0].get("requested_formats") is None


@pytest.mark.asyncio
async def test_ytdlp_command_disables_indirect_ffmpeg_before_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    downloaded = tmp_path / "downloaded.mp4"
    downloaded.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        assert kwargs["env"]["YTDLP_NO_PLUGINS"] == "1"
        return subprocess.CompletedProcess(command, 0, stdout=str(downloaded), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    downloader = object.__new__(VideoDownloader)
    downloader.output_dir = tmp_path

    result = await downloader._real_download("https://example.invalid/video")

    assert result.local_path == str(downloaded)
    assert len(calls) == 1
    command = calls[0]
    assert command[0] == "yt-dlp"
    assert command[command.index("--format") + 1] == YTDLP_SAFE_FORMAT
    assert command[command.index("--downloader") + 1] == "native"
    assert command[command.index("--fixup") + 1] == "never"
    assert command[command.index("--concat-playlist") + 1] == "never"
    assert command[command.index("--print") + 1] == "after_move:filepath"
    assert "--no-simulate" in command
    assert "--ignore-config" in command
    assert "--no-playlist" in command
    assert all(part != "ffmpeg" for part in command)

    parsed = yt_dlp.parse_options(command[1:])
    assert parsed.ydl_opts.get("simulate") is False
    assert parsed.ydl_opts.get("forceprint") == {"after_move": ["filepath"]}


@pytest.mark.asyncio
async def test_ytdlp_hermetic_download_never_invokes_ffmpeg_before_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"
    invoked = tmp_path / "ffmpeg-invoked"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    for executable in ("ffmpeg", "ffprobe"):
        stub = fake_bin / executable
        stub.write_text('#!/bin/sh\ntouch "$FFMPEG_MARKER"\nexit 99\n')
        stub.chmod(0o755)
    monkeypatch.setenv("FFMPEG_MARKER", str(invoked))
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    class MediaHandler(BaseHTTPRequestHandler):
        def do_HEAD(self) -> None:  # noqa: N802 - stdlib callback name
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *_args: object) -> None:
            del format

    server = ThreadingHTTPServer(("127.0.0.1", 0), MediaHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    downloader = object.__new__(VideoDownloader)
    downloader.output_dir = tmp_path / "downloads"
    downloader.output_dir.mkdir()

    try:
        result = await downloader._real_download(
            f"http://127.0.0.1:{server.server_port}/fixture.mp4"
        )
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)

    downloaded = Path(result.local_path)
    assert downloaded.read_bytes() == payload
    assert not invoked.exists()


@pytest.mark.asyncio
async def test_ytdlp_aes_hls_is_rejected_without_ffmpeg_delegation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = b"""#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:1
#EXT-X-MEDIA-SEQUENCE:0
#EXT-X-KEY:METHOD=AES-128,URI="key.bin"
#EXTINF:1.0,
segment.ts
#EXT-X-ENDLIST
"""
    invoked = tmp_path / "ffmpeg-invoked"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    for executable in ("ffmpeg", "ffprobe"):
        stub = fake_bin / executable
        stub.write_text('#!/bin/sh\ntouch "$FFMPEG_MARKER"\nexit 99\n')
        stub.chmod(0o755)
    monkeypatch.setenv("FFMPEG_MARKER", str(invoked))
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    class HlsHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            body = manifest if self.path.endswith(".m3u8") else b"fixture"
            content_type = (
                "application/vnd.apple.mpegurl"
                if self.path.endswith(".m3u8")
                else "application/octet-stream"
            )
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *_args: object) -> None:
            del format

    server = ThreadingHTTPServer(("127.0.0.1", 0), HlsHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    downloader = object.__new__(VideoDownloader)
    downloader.output_dir = tmp_path / "downloads"
    downloader.output_dir.mkdir()

    try:
        with pytest.raises(VideoDownloadError, match="yt-dlp failed"):
            await downloader._real_download(
                f"http://127.0.0.1:{server.server_port}/encrypted.m3u8"
            )
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)

    assert not invoked.exists()
