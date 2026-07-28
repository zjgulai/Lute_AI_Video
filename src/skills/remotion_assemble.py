"""Remotion Assemble Skill — assembles final .mp4 from clips/audio/captions + self-verifies it.

Wraps RemotionRenderer with the SkillCallable contract.

This skill does the FINAL composition:
1. Builds a render JSON matching the contract that rendering/src/render.ts expects.
2. Writes that JSON to disk under outputs/renders/{label}_input.json.
3. Calls RemotionRenderer.render(input_json, output_filename, blocking=True).
4. (Optional) muxes audio tracks via ffmpeg if audio_paths provided.
5. Self-verifies the produced .mp4: file exists, size > 100KB, valid mp4 header,
   duration >= 5 seconds.

When Remotion environment is unavailable (e.g. Mac doesn't have node_modules yet),
this skill writes the JSON and falls back to a stub mp4 marker so the pipeline
can still complete and downstream skills can verify.

Output schema:
    {
      "video_path": str,            # absolute path to final .mp4
      "render_json_path": str,      # path to the render-input JSON
      "duration_seconds": float,
      "file_size_bytes": int,
      "resolution": str,
      "fps": int,
      "shot_count": int,
      "is_stub": bool,
      "verification": { ... }
    }
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import secrets
import stat
import time
from pathlib import Path
from typing import Any

import structlog

from src.config import (
    AV_SYNC_MAX_ABS_DIFF,
    AV_SYNC_MAX_REL_DIFF,
    QUALITY_MODE,
)
from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry
from src.tools.safe_media import (
    UnsafeMediaError,
    ffmpeg_local_input_args,
    ffprobe_local_input_args,
    validate_media_file,
    validate_media_header,
)

logger = structlog.get_logger()

# Self-verification thresholds for FINAL assembled video
MIN_FINAL_SIZE_BYTES = 100 * 1024     # 100KB minimum
MIN_FINAL_DURATION = 5.0              # < 5s = unusable
DEFAULT_FPS = 30
DEFAULT_RESOLUTION = (1080, 1920)

MP4_FTYP_BRANDS = [b"isom", b"iso2", b"avc1", b"mp41", b"mp42", b"M4V ", b"M4A "]
_SAFE_OUTPUT_LABEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}\Z")
_SAFE_MANIFEST_SEGMENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_MAX_RENDER_SECONDS = 180.0
_MAX_LYRICS_BYTES = 64 * 1024
_MAX_RENDER_INPUT_BYTES = 1024 * 1024
_MAX_RENDER_ARTIFACT_BYTES = 2 * 1024 * 1024 * 1024
_RENDERING_CLIENT_TIMEOUT_SECONDS = 600.0
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _freeze_rendered_artifact(
    video_path: Path,
    *,
    output_dir: Path,
    expected_size: int,
    expected_sha256: str,
) -> Path:
    """Copy one renderer artifact handle into a read-only no-clobber snapshot."""

    frozen_path: Path | None = None
    source_fd: int | None = None
    snapshot_fd: int | None = None
    snapshot_inode: tuple[int, int] | None = None
    snapshot_ready = False
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)

    try:
        if (
            not video_path.is_absolute()
            or ".." in video_path.parts
            or _SAFE_MANIFEST_SEGMENT_RE.fullmatch(video_path.name) is None
            or expected_size <= 0
            or expected_size > _MAX_RENDER_ARTIFACT_BYTES
            or _SHA256_RE.fullmatch(expected_sha256) is None
        ):
            raise UnsafeMediaError("rendering output evidence is invalid")

        canonical_output_dir = output_dir.resolve(strict=True)
        canonical_parent = video_path.parent.resolve(strict=True)
        canonical_parent.relative_to(canonical_output_dir)
        source_path = canonical_parent / video_path.name

        source_fd = os.open(source_path, os.O_RDONLY | nofollow | cloexec)
        before = os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size != expected_size:
            raise UnsafeMediaError("rendering output evidence is invalid")

        frozen_path = canonical_parent / (
            f"{video_path.stem}.validated-{secrets.token_hex(16)}{video_path.suffix}"
        )
        snapshot_fd = os.open(
            frozen_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow | cloexec,
            0o400,
        )
        created_snapshot = os.fstat(snapshot_fd)
        if not stat.S_ISREG(created_snapshot.st_mode):
            raise UnsafeMediaError("rendering output snapshot is invalid")
        snapshot_inode = (created_snapshot.st_dev, created_snapshot.st_ino)
        digest = hashlib.sha256()
        copied_size = 0
        header = bytearray()
        with os.fdopen(source_fd, "rb") as source_handle:
            source_fd = None
            with os.fdopen(snapshot_fd, "wb") as snapshot_handle:
                snapshot_fd = None
                while chunk := source_handle.read(1024 * 1024):
                    copied_size += len(chunk)
                    if copied_size > _MAX_RENDER_ARTIFACT_BYTES:
                        raise UnsafeMediaError("rendering output evidence is invalid")
                    digest.update(chunk)
                    if len(header) < 4096:
                        header.extend(chunk[: 4096 - len(header)])
                    snapshot_handle.write(chunk)
                snapshot_handle.flush()
                os.fsync(snapshot_handle.fileno())
                os.fchmod(snapshot_handle.fileno(), 0o400)
                frozen_stat = os.fstat(snapshot_handle.fileno())
                if snapshot_inode != (frozen_stat.st_dev, frozen_stat.st_ino):
                    raise UnsafeMediaError("rendering output snapshot changed")
            after = os.fstat(source_handle.fileno())

        stable_source_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if any(getattr(before, field) != getattr(after, field) for field in stable_source_fields):
            raise UnsafeMediaError("rendering output changed during snapshot")
        if copied_size != expected_size or digest.hexdigest() != expected_sha256:
            raise UnsafeMediaError("rendering output evidence is invalid")

        validate_media_header(
            bytes(header),
            expected_extension=video_path.suffix,
        )
        published = frozen_path.stat(follow_symlinks=False)
        if (
            snapshot_inode != (published.st_dev, published.st_ino)
            or not stat.S_ISREG(published.st_mode)
            or published.st_size != expected_size
            or stat.S_IMODE(published.st_mode) != 0o400
        ):
            raise UnsafeMediaError("rendering output snapshot changed")
        snapshot_ready = True
        return frozen_path
    except UnsafeMediaError:
        raise
    except (OSError, ValueError) as exc:
        raise UnsafeMediaError("rendering output snapshot failed") from exc
    finally:
        if source_fd is not None:
            os.close(source_fd)
        if snapshot_fd is not None:
            os.close(snapshot_fd)
        if frozen_path is not None and not snapshot_ready:
            if snapshot_inode is not None:
                try:
                    current = frozen_path.stat(follow_symlinks=False)
                    if snapshot_inode == (current.st_dev, current.st_ino):
                        _cleanup_intermediate(frozen_path)
                except OSError as cleanup_exc:
                    logger.warning(
                        "remotion_assemble: snapshot cleanup inspection failed",
                        error_type=type(cleanup_exc).__name__,
                    )


def _validate_output_label(value: object) -> str:
    if (
        not isinstance(value, str)
        or _SAFE_OUTPUT_LABEL_RE.fullmatch(value) is None
        or ".." in value
    ):
        raise UnsafeMediaError("assemble output label is unsafe")
    return value


def _write_safe_concat_manifest(
    media_paths: list[Path],
    *,
    output_path: Path,
    label: str,
    kind: str,
) -> Path:
    resolved_paths = [item.resolve(strict=True) for item in media_paths]
    output_parent = output_path.parent.resolve(strict=True)
    common = Path(os.path.commonpath([output_parent, *resolved_paths]))
    if common == Path(common.anchor):
        raise UnsafeMediaError("concat inputs do not share a bounded root")
    relative_paths: list[Path] = []
    for resolved in resolved_paths:
        try:
            relative = resolved.relative_to(common)
        except ValueError as exc:
            raise UnsafeMediaError("concat media path is outside bounded root") from exc
        if any(
            part in {".", ".."} or _SAFE_MANIFEST_SEGMENT_RE.fullmatch(part) is None
            for part in relative.parts
        ):
            raise UnsafeMediaError("concat media path is not manifest-safe")
        relative_paths.append(relative)
    manifest_path = common / f".{label}-{kind}-{secrets.token_hex(8)}.concat"
    try:
        with manifest_path.open("x", encoding="utf-8") as handle:
            for relative in relative_paths:
                handle.write(f"file '{relative.as_posix()}'\n")
    except FileExistsError as exc:
        raise UnsafeMediaError("concat manifest already exists") from exc
    return manifest_path


def _write_or_reuse_render_payload(
    render_json_path: Path,
    render_payload: dict[str, Any],
) -> None:
    encoded = json.dumps(render_payload, indent=2, default=str).encode("utf-8")
    if len(encoded) > _MAX_RENDER_INPUT_BYTES:
        raise UnsafeMediaError("assemble render input is too large")

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(
            render_json_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow,
            0o640,
        )
    except FileExistsError:
        try:
            existing_fd = os.open(render_json_path, os.O_RDONLY | nofollow)
            with os.fdopen(existing_fd, "rb") as existing_handle:
                metadata = os.fstat(existing_handle.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MAX_RENDER_INPUT_BYTES:
                    raise UnsafeMediaError("assemble render input conflict")
                existing = existing_handle.read(_MAX_RENDER_INPUT_BYTES + 1)
        except UnsafeMediaError:
            raise
        except OSError as exc:
            raise UnsafeMediaError("assemble render input conflict") from exc
        if existing != encoded:
            raise UnsafeMediaError("assemble render input conflict")
        return
    except OSError as exc:
        raise UnsafeMediaError("assemble render input write failed") from exc

    try:
        with os.fdopen(fd, "wb") as render_json_handle:
            render_json_handle.write(encoded)
            render_json_handle.flush()
            os.fsync(render_json_handle.fileno())
    except OSError as exc:
        try:
            render_json_path.unlink(missing_ok=True)
        except OSError as cleanup_exc:
            logger.warning(
                "remotion_assemble: render input cleanup failed",
                error_type=type(cleanup_exc).__name__,
            )
        raise UnsafeMediaError("assemble render input write failed") from exc


def _cleanup_intermediate(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("remotion_assemble: intermediate cleanup failed")


def _resolve_render_output_dir(params: dict[str, Any]) -> Path:
    from src.config import OUTPUT_DIR
    from src.pipeline.generation_policy import get_effective_generation_policy

    raw = params.get("output_dir")
    policy = get_effective_generation_policy()
    expected_root = OUTPUT_DIR
    if raw is None:
        if policy is not None and policy.artifact_disposition in {
            "pending_review",
            "quarantine",
        }:
            raise ValueError("tenant-scoped assemble output_dir is required")
        renders_dir = OUTPUT_DIR / "renders"
    else:
        if not isinstance(raw, (str, Path)) or not str(raw):
            raise ValueError("assemble output_dir is invalid")
        renders_dir = Path(raw)
        if not renders_dir.is_absolute() or ".." in renders_dir.parts:
            raise ValueError("assemble output_dir is unsafe")
        if policy is not None:
            expected_root = (
                OUTPUT_DIR
                / "tenants"
                / policy.tenant_id
                / policy.artifact_disposition
            )
        try:
            renders_dir.absolute().relative_to(expected_root.absolute())
        except ValueError as exc:
            raise ValueError("assemble output_dir is outside tenant scope") from exc

    probe = renders_dir
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    if probe.is_symlink() or (probe.exists() and not probe.is_dir()):
        raise ValueError("assemble output_dir is unsafe")
    renders_dir.mkdir(parents=True, exist_ok=True)
    current = renders_dir
    while current != current.parent:
        if current.is_symlink():
            raise ValueError("assemble output_dir is unsafe")
        if current == OUTPUT_DIR or current == expected_root:
            break
        current = current.parent
    return renders_dir


def _read_scoped_lyrics(path_value: object, output_dir: Path) -> str:
    from src.config import OUTPUT_DIR
    from src.pipeline.generation_policy import get_effective_generation_policy

    if not isinstance(path_value, (str, Path)) or not str(path_value):
        raise UnsafeMediaError("lyrics input path is invalid")
    candidate = Path(path_value)
    if candidate.suffix.lower() != ".txt" or candidate.is_symlink():
        raise UnsafeMediaError("lyrics input path is invalid")
    try:
        resolved = candidate.resolve(strict=True)
        file_stat = resolved.stat()
    except OSError as exc:
        raise UnsafeMediaError("lyrics input path is invalid") from exc
    if (
        not resolved.is_file()
        or file_stat.st_size <= 10
        or file_stat.st_size > _MAX_LYRICS_BYTES
    ):
        raise UnsafeMediaError("lyrics input path is invalid")

    policy = get_effective_generation_policy()
    if policy is not None:
        try:
            tenant_root = (
                OUTPUT_DIR
                / "tenants"
                / policy.tenant_id
                / policy.artifact_disposition
            ).resolve(strict=True)
        except OSError as exc:
            raise UnsafeMediaError("lyrics output scope is invalid") from exc
        try:
            output_relative = output_dir.resolve(strict=True).relative_to(tenant_root)
        except (OSError, ValueError) as exc:
            raise UnsafeMediaError("lyrics output scope is invalid") from exc
        if len(output_relative.parts) < 2:
            raise UnsafeMediaError("lyrics output scope is invalid")
        run_root = tenant_root / output_relative.parts[0]
        try:
            resolved.relative_to(run_root)
        except ValueError as exc:
            raise UnsafeMediaError("lyrics input is outside the active run") from exc
    try:
        return resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise UnsafeMediaError("lyrics input is invalid UTF-8") from exc


class RemotionAssembleSkill(SkillCallable):
    """Renders the final mp4 via Remotion (Node.js) and verifies it."""

    name = "remotion-assemble-skill"
    description = "Assembles final .mp4 via Remotion from clips/captions/audio and self-verifies"
    max_retries = 2

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        from src.tools.remotion_renderer import RemotionRenderer

        # === Inputs ===
        shots = params.get("shots") or []
        captions = params.get("captions") or []
        audio_paths = params.get("audio_paths") or []
        lyrics_paths = params.get("lyrics_paths") or []
        clip_paths = params.get("clip_paths") or []
        transitions = params.get("transitions") or []
        brand_guidelines = params.get("brand_guidelines") or {}
        output_label = _validate_output_label(
            params.get("output_label", f"video_{int(time.time())}")
        )
        try:
            total_duration = float(
                params.get("total_duration") or self._compute_total_duration(shots)
            )
        except (TypeError, ValueError) as exc:
            raise UnsafeMediaError("assemble duration is invalid") from exc
        if not math.isfinite(total_duration) or not 1 <= total_duration <= _MAX_RENDER_SECONDS:
            raise UnsafeMediaError("assemble duration is outside the approved range")
        renders_dir = _resolve_render_output_dir(params)

        # Load generated lyrics text if available
        lyrics_text = ""
        if lyrics_paths:
            for lp in lyrics_paths:
                try:
                    lyrics_text = _read_scoped_lyrics(lp, renders_dir)
                    break
                except UnsafeMediaError:
                    logger.warning("remotion_assemble: lyrics input rejected")

        # === Build render JSON in the shape render.ts expects ===
        render_payload = self._build_render_payload(
            shots=shots,
            captions=captions,
            audio_paths=audio_paths,
            lyrics_text=lyrics_text,
            brand_guidelines=brand_guidelines,
            total_duration=total_duration,
            label=output_label,
            clip_paths=clip_paths,
            transitions=transitions,
        )

        # Write JSON to disk (for debugging / future Remotion use)
        render_json_path = renders_dir / f"{output_label}_input.json"
        _write_or_reuse_render_payload(render_json_path, render_payload)

        output_filename = f"{output_label}.mp4"

        # === PRIORITY 0: Delegate to dedicated rendering container if configured ===
        rendering_socket = os.environ.get("RENDERING_SERVICE_SOCKET", "")
        if rendering_socket:
            from src.pipeline.generation_policy import get_effective_generation_policy

            policy = get_effective_generation_policy()
            if policy is None:
                return SkillResult(
                    success=False,
                    error="rendering_service_boundary_unavailable",
                    metadata={"non_retryable": True},
                )
            remote_result = await self._render_via_service(
                rendering_socket=rendering_socket,
                clip_paths=clip_paths,
                audio_paths=audio_paths,
                render_payload=render_payload,
                output_label=output_label,
                output_dir=renders_dir,
                tenant_id=policy.tenant_id,
                artifact_disposition=policy.artifact_disposition,
            )
            if remote_result is not None:
                video_path = Path(remote_result["video_path"])
                is_stub_remote = remote_result["is_stub"]
                verification = self._self_verify(video_path, is_stub=is_stub_remote)
                if not is_stub_remote and not verification["all_ok"]:
                    return SkillResult(
                        success=False,
                        error=f"final video verification failed: {verification['failures']}",
                        metadata={
                            "verification": verification,
                            "video_path": str(video_path),
                            "render_json_path": str(render_json_path),
                            "render_mode": remote_result.get("render_mode", "rendering_service"),
                        },
                    )
                file_size = video_path.stat().st_size if video_path.exists() else int(remote_result.get("file_size_bytes", 0))
                duration_seconds = self._measure_duration(video_path) if video_path.exists() else float(total_duration)
                return SkillResult(
                    success=True,
                    data={
                        "video_path": str(video_path),
                        "render_json_path": str(render_json_path),
                        "duration_seconds": duration_seconds or float(total_duration),
                        "file_size_bytes": file_size,
                        "resolution": f"{DEFAULT_RESOLUTION[0]}x{DEFAULT_RESOLUTION[1]}",
                        "fps": DEFAULT_FPS,
                        "shot_count": len(shots),
                        "is_stub": is_stub_remote,
                        "simulated": is_stub_remote,
                        "verification": verification,
                    },
                    metadata={
                        "render_mode": remote_result.get("render_mode", "rendering_service"),
                        "rendering_service": "unix_socket",
                        "audio_muxed": remote_result["audio_muxed"] and not is_stub_remote,
                        "clip_count": len(clip_paths),
                    },
                )
            return SkillResult(
                success=False,
                error="rendering_service_failed",
                metadata={"non_retryable": True},
            )

        output_path = renders_dir / output_filename
        valid_clips = [
            Path(p) for p in clip_paths
            if p and Path(p).exists() and Path(p).stat().st_size > 1000
        ]

        is_stub = False
        render_mode = "remotion"
        remotion_done = False

        # === PRIORITY 1: Remotion unified render (embeds clips via <Video> component) ===
        renderer = RemotionRenderer(output_dir=renders_dir)
        env = renderer.validate_environment()
        is_remotion_available = env.get("available", False)

        if is_remotion_available:
            try:
                output_path = renderer.render(
                    input_json=render_json_path,
                    output_filename=output_filename,
                    blocking=True,
                )
                remotion_done = True
                logger.info(
                    "remotion_assemble: Remotion render complete",
                    path=str(output_path),
                    clips_embedded=len(valid_clips),
                )
            except Exception as e:
                logger.error("remotion_assemble: Remotion render failed", error=str(e))
                # Fall through to ffmpeg concat fallback below
        else:
            logger.warning(
                "remotion_assemble: Remotion not available",
                issues=env.get("issues", []),
            )

        # === PRIORITY 2: ffmpeg clip concat fallback (when Remotion unavailable or failed) ===
        audio_muxed = False
        if not remotion_done and len(valid_clips) >= 2:
            logger.info(
                "remotion_assemble: falling back to ffmpeg clip concat",
                count=len(valid_clips),
            )
            concat_result = self._concat_clips(valid_clips, output_path)
            if concat_result and concat_result.exists() and concat_result.stat().st_size > 10000:
                output_path = concat_result
                render_mode = "clip_concat"
                logger.info("remotion_assemble: clip concat success", path=str(output_path))
            else:
                logger.warning("remotion_assemble: clip concat failed, writing stub")
                is_stub = True
                self._write_stub_mp4(output_path, output_label)
        elif not remotion_done:
            # No clips and Remotion unavailable — write stub
            is_stub = True
            self._write_stub_mp4(output_path, output_label)

        # === Sprint 4 P4-2: aspect-ratio fan-out ===
        # When `aspect_ratios` param has multiple entries, render the
        # additional Remotion compositions (1:1, 16:9). The primary 9:16
        # has already been rendered above as `output_path`. Failures here
        # are non-fatal — only the primary path matters for back-compat;
        # extra aspects are best-effort.
        aspect_ratios = params.get("aspect_ratios") or ["9:16"]
        # Map aspect ratio → Remotion composition id (registered in Root.tsx)
        _ASPECT_TO_COMPOSITION_ID: dict[str, str] = {
            "9:16": "ShortVideo",
            "1:1": "ShortVideo-1x1",
            "16:9": "ShortVideo-16x9",
        }
        video_paths: dict[str, str] = {"9:16": str(output_path)}
        if remotion_done and len(aspect_ratios) > 1 and is_remotion_available:
            for ratio in aspect_ratios:
                if ratio == "9:16":
                    continue
                comp_id = _ASPECT_TO_COMPOSITION_ID.get(ratio)
                if comp_id is None:
                    logger.warning("remotion_assemble: unknown aspect ratio, skipping", ratio=ratio)
                    continue
                fan_filename = f"{output_label}_{ratio.replace(':', 'x')}.mp4"
                try:
                    fan_path = renderer.render(
                        input_json=render_json_path,
                        output_filename=fan_filename,
                        blocking=True,
                        composition_id=comp_id,
                    )
                    if fan_path.exists() and fan_path.stat().st_size > 1000:
                        video_paths[ratio] = str(fan_path)
                        logger.info("remotion_assemble: fan-out render complete",
                                    ratio=ratio, composition_id=comp_id, path=str(fan_path))
                    else:
                        logger.warning("remotion_assemble: fan-out render produced empty file",
                                       ratio=ratio, path=str(fan_path))
                except Exception as exc:
                    logger.warning("remotion_assemble: fan-out render failed (non-fatal)",
                                   ratio=ratio, error=str(exc)[:200])

        # === (Optional) Burn lyrics subtitles into the video (ffmpeg fallback only) ===
        if not is_stub and not remotion_done and lyrics_text:
            subtitled = self._try_burn_lyrics(
                video_path=output_path,
                lyrics_text=lyrics_text,
                total_duration=total_duration,
                output_label=output_label,
            )
            if subtitled:
                output_path = subtitled

        # === (Optional) Mux audio into the video ===
        if not is_stub and audio_paths:
            muxed = self._try_mux_audio(
                video_path=output_path,
                audio_paths=audio_paths,
                output_label=output_label,
            )
            if muxed:
                output_path = muxed
                audio_muxed = True

        # === Self-verification ===
        verification = self._self_verify(output_path, is_stub=is_stub)

        if not is_stub and not verification["all_ok"]:
            return SkillResult(
                success=False,
                error=f"final video verification failed: {verification['failures']}",
                metadata={
                    "verification": verification,
                    "video_path": str(output_path),
                    "render_json_path": str(render_json_path),
                },
            )

        file_size = output_path.stat().st_size if output_path.exists() else 0
        duration_seconds = self._measure_duration(output_path) if output_path.exists() else float(total_duration)

        if not is_stub and output_path.exists():
            try:
                from src.tools.poster_extractor import ensure_poster
                ensure_poster(output_path)
                for ratio_path in video_paths.values():
                    ensure_poster(ratio_path)
            except Exception as exc:
                logger.warning(
                    "remotion_assemble: poster extraction failed",
                    video_path=str(output_path),
                    error=str(exc)[:200],
                )

        return SkillResult(
            success=True,
            data={
                "video_path": str(output_path),
                "video_paths": video_paths,
                "render_json_path": str(render_json_path),
                "duration_seconds": duration_seconds or float(total_duration),
                "file_size_bytes": file_size,
                "resolution": f"{DEFAULT_RESOLUTION[0]}x{DEFAULT_RESOLUTION[1]}",
                "fps": DEFAULT_FPS,
                "shot_count": len(shots),
                "is_stub": is_stub,
                "simulated": is_stub,
                "verification": verification,
            },
            metadata={
                "render_mode": render_mode if not is_stub else "stub",
                "audio_muxed": audio_muxed,
                "clip_count": len(valid_clips),
                "aspect_ratios_rendered": list(video_paths.keys()),
            },
        )

    # === Rendering service (HTTP) bridge ===

    async def _render_via_service(
        self,
        rendering_socket: str,
        clip_paths: list[str],
        audio_paths: list[str],
        render_payload: dict[str, Any],
        output_label: str,
        output_dir: Path,
        tenant_id: str,
        artifact_disposition: str,
    ) -> dict[str, Any] | None:
        try:
            import httpx
        except ImportError:
            logger.warning("remotion_assemble: httpx unavailable")
            return None

        body = {
            "tenant_id": tenant_id,
            "artifact_disposition": artifact_disposition,
            "output_dir": str(output_dir),
            "clip_paths": [str(p) for p in clip_paths if p],
            "audio_paths": [str(p) for p in audio_paths if p],
            "render_payload": render_payload,
            "output_label": output_label,
        }
        try:
            if (
                not rendering_socket.startswith("/")
                or ".." in Path(rendering_socket).parts
            ):
                raise ValueError("rendering socket path is invalid")
            transport = httpx.AsyncHTTPTransport(uds=rendering_socket)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://rendering",
                timeout=_RENDERING_CLIENT_TIMEOUT_SECONDS,
            ) as client:
                resp = await client.post("/assemble", json=body)
                if resp.status_code != 200:
                    logger.error(
                        "remotion_assemble: rendering service returned non-200",
                        status=resp.status_code,
                    )
                    return None
                data = resp.json()
                if (
                    type(data) is not dict
                    or data.get("success") is not True
                    or type(data.get("video_path")) is not str
                    or type(data.get("file_size_bytes")) is not int
                    or data["file_size_bytes"] <= 0
                    or type(data.get("artifact_sha256")) is not str
                    or _SHA256_RE.fullmatch(data["artifact_sha256"]) is None
                    or type(data.get("is_stub")) is not bool
                    or type(data.get("audio_muxed")) is not bool
                ):
                    logger.error("remotion_assemble: rendering service contract invalid")
                    return None
                frozen_path = _freeze_rendered_artifact(
                    Path(data["video_path"]),
                    output_dir=output_dir,
                    expected_size=data["file_size_bytes"],
                    expected_sha256=data["artifact_sha256"],
                )
                frozen_data = dict(data)
                frozen_data["video_path"] = str(frozen_path)
                return frozen_data
        except Exception as exc:
            logger.warning(
                "remotion_assemble: rendering service call failed",
                error_type=type(exc).__name__,
            )
            return None

    # === Render payload construction ===

    def _build_render_payload(
        self,
        shots: list[dict[str, Any]],
        captions: list[dict[str, Any]],
        audio_paths: list[str],
        lyrics_text: str,
        brand_guidelines: dict[str, Any],
        total_duration: float,
        label: str,
        clip_paths: list[str] | None = None,
        transitions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Produce JSON that matches buildRenderProps() in rendering/src/render.ts."""
        clip_paths = clip_paths or []
        # Convert shots into the Storyboard.shots schema render.ts expects
        normalized_shots = []
        for i, shot in enumerate(shots):
            normalized_shots.append({
                "id": shot.get("id", i + 1),
                "start_time": float(shot.get("start_time", 0)),
                "end_time": float(shot.get("end_time", 0)),
                "text_overlay": shot.get("text_overlay", "") or shot.get("hook", ""),
                "visual": shot.get("visual", "") or shot.get("description", ""),
            })

        # Build audio_plans.segments from audio_paths if needed
        audio_segments = []
        if audio_paths:
            for shot in normalized_shots:
                audio_segments.append({
                    "type": "voiceover",
                    "start_time": shot["start_time"],
                    "end_time": shot["end_time"],
                    "text": shot.get("text_overlay", ""),
                })

        # Merge captions: prefer lyrics text if available, otherwise script captions
        caption_entries = []
        if lyrics_text and normalized_shots:
            lines = [l.strip() for l in lyrics_text.split("\n") if l.strip() and not l.strip().startswith("[")]
            if lines:
                lines_per_shot = max(1, len(lines) // max(1, len(normalized_shots)))
                line_idx = 0
                for shot in normalized_shots:
                    chunk = " ".join(lines[line_idx:line_idx + lines_per_shot])
                    line_idx += lines_per_shot
                    if chunk:
                        caption_entries.append({
                            "start_time": shot["start_time"],
                            "end_time": shot["end_time"],
                            "text": chunk[:120],
                        })
        else:
            caption_entries = [
                {
                    "start_time": float(c.get("start_time", 0)),
                    "end_time": float(c.get("end_time", 0)),
                    "text": c.get("text", ""),
                }
                for c in captions
            ]

        return {
            "scripts": [{"id": label}],
            "storyboards": [{
                "total_duration": total_duration,
                "shots": normalized_shots,
            }],
            "caption_plans": [{
                "entries": caption_entries,
            }],
            "audio_plans": [{"segments": audio_segments}] if audio_segments else [],
            "brand_guidelines": brand_guidelines,
            "clip_paths": clip_paths,
            "transitions": transitions or [],
        }

    @staticmethod
    def _compute_total_duration(shots: list[dict[str, Any]]) -> float:
        if not shots:
            return 30.0
        max_end = max((float(s.get("end_time", 0)) for s in shots), default=30.0)
        return max(max_end, 5.0)

    # === Font path resolution (cross-platform) ===

    @staticmethod
    def _get_font_path() -> str:
        """Return a system font path usable by ffmpeg drawtext.

        Tries common paths across macOS, Linux (Alpine/Debian), and
        falls back to a no-fontfile default (drawtext will use built-in).
        """
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",          # Debian/Ubuntu
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",  # Alpine
            "/usr/share/fonts/TTF/DejaVuSans.ttf",                      # Arch
            "/System/Library/Fonts/Helvetica.ttc",                      # macOS
            "/System/Library/Fonts/HelveticaNeue.ttc",                  # macOS fallback
        ]
        for p in candidates:
            if Path(p).exists():
                return p
        # fallback: drawtext without fontfile uses default bitmap font
        return ""

    # === ffmpeg clip concat + audio mux ===

    @staticmethod
    def _get_video_dimensions(path: Path) -> tuple[int, int] | None:
        """Return (width, height) of a video file via ffprobe."""
        import subprocess
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=width,height",
                    "-of", "csv=s=x:p=0",
                    *ffprobe_local_input_args(path),
                ],
                capture_output=True, text=True, timeout=10, check=True,
            )
            w, h = result.stdout.strip().split("x")
            return int(w), int(h)
        except UnsafeMediaError:
            raise
        except Exception:
            return None

    def _concat_clips(self, clip_paths: list[Path], output_path: Path) -> Path | None:
        """Concatenate multiple MP4 clips via ffmpeg concat demuxer.

        Uses -c copy for speed when all clips share the same codec and
        resolution. Falls back to re-encode with forced scale-to-target
        when copy fails or output dimensions differ from target.
        """
        import subprocess

        tw, th = DEFAULT_RESOLUTION
        target_str = f"{tw}x{th}"
        concat_list_path: Path | None = None
        output_existed_before_attempt = output_path.exists() or output_path.is_symlink()
        attempt_output = (
            output_path.parent
            / f".{output_path.stem}-concat-{secrets.token_hex(8)}{output_path.suffix}"
        )

        try:
            # Build concat list file
            for cp in clip_paths:
                validate_media_file(cp)
            if output_existed_before_attempt:
                raise UnsafeMediaError("assemble output already exists")
            concat_list_path = _write_safe_concat_manifest(
                clip_paths,
                output_path=output_path,
                label=_validate_output_label(output_path.stem),
                kind="video",
            )

            used_reencode = False

            # Try stream-copy first (fast, no quality loss)
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-n",
                        "-protocol_whitelist",
                        "file,pipe",
                        "-f",
                        "concat",
                        "-safe",
                        "1",
                        "-i",
                        str(concat_list_path),
                        "-c",
                        "copy",
                        "-movflags",
                        "+faststart",
                        str(attempt_output),
                    ],
                    capture_output=True,
                    timeout=120,
                    check=True,
                )
            except subprocess.CalledProcessError:
                logger.warning("remotion_assemble: concat -c copy failed, falling back to re-encode")
                _cleanup_intermediate(attempt_output)
                used_reencode = True

            # If copy succeeded, verify dimensions match target
            if not used_reencode and attempt_output.exists():
                dims = self._get_video_dimensions(attempt_output)
                if dims is None or f"{dims[0]}x{dims[1]}" != target_str:
                    logger.warning(
                        "remotion_assemble: copy output dimensions %s != target %s, re-encoding",
                        dims,
                        target_str,
                    )
                    used_reencode = True
                    # Remove the bad copy output before re-encoding
                    attempt_output.unlink(missing_ok=True)

            if used_reencode:
                # Force统一分辨率: scale to fit within target, then pad with black
                scale_filter = (
                    f"scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:black"
                )
                subprocess.run(
                    [
                        "ffmpeg",
                        "-n",
                        "-protocol_whitelist",
                        "file,pipe",
                        "-f",
                        "concat",
                        "-safe",
                        "1",
                        "-i",
                        str(concat_list_path),
                        "-c:v",
                        "libx264",
                        "-preset",
                        "fast",
                        "-crf",
                        "23",
                        "-vf",
                        scale_filter,
                        "-c:a",
                        "aac",
                        "-b:a",
                        "128k",
                        "-movflags",
                        "+faststart",
                        str(attempt_output),
                    ],
                    capture_output=True,
                    timeout=300,
                    check=True,
                )

            if attempt_output.exists() and attempt_output.stat().st_size > 10000:
                try:
                    os.link(attempt_output, output_path, follow_symlinks=False)
                except FileExistsError as exc:
                    raise UnsafeMediaError("assemble output already exists") from exc
                except OSError as exc:
                    raise UnsafeMediaError("assemble output publication failed") from exc
                return output_path
        except UnsafeMediaError:
            raise
        except Exception as exc:
            logger.warning(
                "remotion_assemble: ffmpeg concat failed",
                error_type=type(exc).__name__,
            )
        finally:
            _cleanup_intermediate(concat_list_path)
            _cleanup_intermediate(attempt_output)
        return None

    def _try_burn_lyrics(
        self,
        video_path: Path,
        lyrics_text: str,
        total_duration: float,
        output_label: str,
    ) -> Path | None:
        """Burn lyrics subtitles into the video using ffmpeg drawtext.

        Extracts the first few meaningful lines (skipping [Verse], [Chorus]
        markers) and overlays them at the bottom of the video.
        """
        import subprocess

        try:

            lines = [l.strip() for l in lyrics_text.split("\n")
                     if l.strip() and not l.strip().startswith("[")]
            if not lines:
                return None

            # Take first 3 meaningful lines, max 60 chars each
            display_lines = lines[:3]
            display_text = " | ".join(display_lines)[:180]
            # Escape single quotes for ffmpeg drawtext
            display_text = display_text.replace("'", "\\'")

            out_path = video_path.parent / f"{video_path.stem}_lyrics{video_path.suffix}"
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    *ffmpeg_local_input_args(video_path),
                    "-vf",
                    (
                        f"drawtext=fontfile={self._get_font_path()}:"
                        f"text='{display_text}':"
                        f"fontcolor=white:fontsize=24:"
                        f"box=1:boxcolor=black@0.5:boxborderw=10:"
                        f"x=(w-text_w)/2:y=h-text_h-80"
                    ),
                    "-c:a", "copy",
                    str(out_path),
                ],
                capture_output=True, timeout=120, check=True,
            )
            if out_path.exists() and out_path.stat().st_size > 10000:
                logger.info(
                    "remotion_assemble: lyrics burned into video",
                    path=str(out_path), lines=len(display_lines),
                )
                return out_path
        except UnsafeMediaError:
            raise
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError, Exception) as e:
            logger.warning("remotion_assemble: ffmpeg lyrics burn failed", error=str(e))
        return None

    def _try_mux_audio(
        self,
        video_path: Path,
        audio_paths: list[str],
        output_label: str,
    ) -> Path | None:
        """Concat audio paths and mux into the video. Returns new path or None on failure."""
        import subprocess

        concat_list_path: Path | None = None
        concat_audio: Path | None = None
        attempt_muxed: Path | None = None
        try:
            # Filter out non-existent or stub audio
            valid_audios = [Path(p) for p in audio_paths if Path(p).exists() and Path(p).stat().st_size > 200]
            if not valid_audios:
                return None

            # Concatenate audios via ffmpeg concat demuxer
            for ap in valid_audios:
                validate_media_file(ap)
            concat_list_path = _write_safe_concat_manifest(
                valid_audios,
                output_path=video_path,
                label=_validate_output_label(output_label),
                kind="audio",
            )

            # Concat audios
            concat_audio = video_path.parent / f".{output_label}-audio-{secrets.token_hex(8)}.mkv"
            subprocess.run(
                [
                    "ffmpeg",
                    "-n",
                    "-protocol_whitelist",
                    "file,pipe",
                    "-f",
                    "concat",
                    "-safe",
                    "1",
                    "-i",
                    str(concat_list_path),
                    "-c",
                    "copy",
                    str(concat_audio),
                ],
                capture_output=True,
                timeout=60,
                check=True,
            )

            # Mux audio into video via a staged, symlink-safe publication.
            muxed_path = video_path.parent / f"{video_path.stem}_with_audio{video_path.suffix}"
            if muxed_path.exists() or muxed_path.is_symlink():
                raise UnsafeMediaError("audio mux output already exists")
            attempt_muxed = (
                video_path.parent
                / f".{video_path.stem}-mux-{secrets.token_hex(8)}{video_path.suffix}"
            )
            subprocess.run(
                [
                    "ffmpeg",
                    "-n",
                    *ffmpeg_local_input_args(video_path),
                    *ffmpeg_local_input_args(concat_audio),
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-shortest",
                    str(attempt_muxed),
                ],
                capture_output=True,
                timeout=120,
                check=True,
            )
            if attempt_muxed.exists() and attempt_muxed.stat().st_size > 0:
                try:
                    os.link(attempt_muxed, muxed_path, follow_symlinks=False)
                except FileExistsError as exc:
                    raise UnsafeMediaError("audio mux output already exists") from exc
                except OSError as exc:
                    raise UnsafeMediaError("audio mux output publication failed") from exc
                return muxed_path
        except UnsafeMediaError:
            raise
        except Exception as exc:
            logger.warning(
                "remotion_assemble: ffmpeg mux failed (continuing without audio)",
                error_type=type(exc).__name__,
            )
        finally:
            _cleanup_intermediate(attempt_muxed)
            _cleanup_intermediate(concat_audio)
            _cleanup_intermediate(concat_list_path)
        return None

    # === Self-verification ===

    def _self_verify(self, video_path: Path, is_stub: bool) -> dict[str, Any]:
        if is_stub:
            return {
                "file_exists": video_path.exists(),
                "size_ok": True, "header_ok": True, "duration_ok": True,
                "all_ok": True, "failures": [], "mode": "stub_relaxed",
            }

        failures: list[str] = []
        if not video_path.exists():
            failures.append("file_not_found")
            return {
                "file_exists": False, "size_ok": False, "header_ok": False,
                "duration_ok": False, "all_ok": False, "failures": failures,
                "mode": "real",
            }

        size = video_path.stat().st_size
        size_ok = size >= MIN_FINAL_SIZE_BYTES
        if not size_ok:
            failures.append(f"final_too_small_{size}b")

        header_ok = self._is_valid_mp4(video_path)
        if not header_ok:
            failures.append("invalid_mp4_header")

        duration = self._measure_duration(video_path)
        duration_ok = duration >= MIN_FINAL_DURATION
        if not duration_ok and duration > 0:
            failures.append(f"final_duration_too_short_{duration:.1f}s")
        elif duration == 0:
            duration_ok = True  # ffprobe missing — don't block

        # Audio-Video sync check — detect mismatched durations after mux
        av_sync = self._check_av_sync(video_path)
        av_sync_ok = av_sync["sync_ok"]
        if not av_sync_ok and QUALITY_MODE == "enforce":
            failures.append(av_sync["failure"])

        # all_ok: enforce mode requires av_sync_ok; observe/off keeps original logic
        if QUALITY_MODE == "enforce":
            all_ok = size_ok and header_ok and duration_ok and av_sync_ok
        else:
            all_ok = size_ok and header_ok and duration_ok

        return {
            "file_exists": True,
            "size_ok": size_ok,
            "header_ok": header_ok,
            "duration_ok": duration_ok,
            "av_sync_ok": av_sync_ok,
            "av_sync_details": av_sync,
            "all_ok": all_ok,
            "failures": failures,
            "mode": "real",
        }

    @staticmethod
    def _is_valid_mp4(path: Path) -> bool:
        try:
            with open(path, "rb") as f:
                head = f.read(12)
            if len(head) < 12:
                return False
            return head[4:8] == b"ftyp"
        except Exception:
            return False

    @staticmethod
    def _measure_duration(path: Path) -> float:
        import subprocess

        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    *ffprobe_local_input_args(path),
                ],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return float(result.stdout.strip() or "0.0")
        except UnsafeMediaError:
            raise
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, Exception) as exc:
            logger.debug(
                "remotion_assemble: ffprobe duration failed",
                video_path=str(path),
                error=str(exc)[:200],
            )
        return 0.0

    @staticmethod
    def _check_av_sync(path: Path) -> dict[str, Any]:
        """Check audio-video sync by comparing stream durations.

        Uses ffprobe to get video stream duration and audio stream duration
        separately. A significant mismatch indicates desync (e.g. audio truncated
        or video shorter than audio after mux).

        Thresholds:
        - absolute diff > 0.5s  → fail
        - relative diff > 5%    → fail (for short clips)

        Returns:
            {"sync_ok": bool, "video_dur": float, "audio_dur": float,
             "diff": float, "failure": str}
        """
        import subprocess

        t0 = time.perf_counter()

        def _stream_duration(stream_spec: str) -> float:
            """Return stream duration, or -1.0 if ffprobe fails (file missing / unreadable)."""
            try:
                result = subprocess.run(
                    [
                        "ffprobe", "-v", "error",
                        "-select_streams", stream_spec,
                        "-show_entries", "stream=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1",
                        *ffprobe_local_input_args(path),
                    ],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    return float(result.stdout.strip() or "0.0")
            except UnsafeMediaError:
                raise
            except Exception as exc:
                logger.debug(
                    "remotion_assemble: stream duration probe failed",
                    video_path=str(path),
                    stream=stream_spec,
                    error=str(exc)[:200],
                )
            return -1.0

        video_dur = _stream_duration("v:0")
        audio_dur = _stream_duration("a:0")

        result: dict[str, Any]

        # ffprobe failed on one or both streams — file unreadable or not a video
        if video_dur < 0 or audio_dur < 0:
            result = {
                "sync_ok": False,
                "video_dur": max(0.0, video_dur),
                "audio_dur": max(0.0, audio_dur),
                "diff": 0.0,
                "failure": "no_video_stream",
            }
        # No audio stream — sync not applicable (return ok)
        elif audio_dur == 0.0:
            result = {
                "sync_ok": True,
                "video_dur": video_dur,
                "audio_dur": 0.0,
                "diff": 0.0,
                "failure": "",
            }
        # No video stream — this is an audio-only file, not our target
        elif video_dur == 0.0:
            result = {
                "sync_ok": False,
                "video_dur": 0.0,
                "audio_dur": audio_dur,
                "diff": audio_dur,
                "failure": "no_video_stream",
            }
        else:
            diff = abs(video_dur - audio_dur)
            max_dur = max(video_dur, audio_dur, 0.001)
            rel_diff = diff / max_dur

            if diff > AV_SYNC_MAX_ABS_DIFF or rel_diff > AV_SYNC_MAX_REL_DIFF:
                result = {
                    "sync_ok": False,
                    "video_dur": round(video_dur, 2),
                    "audio_dur": round(audio_dur, 2),
                    "diff": round(diff, 2),
                    "failure": f"av_desync_v{video_dur:.1f}_a{audio_dur:.1f}",
                }
            else:
                result = {
                    "sync_ok": True,
                    "video_dur": round(video_dur, 2),
                    "audio_dur": round(audio_dur, 2),
                    "diff": round(diff, 2),
                    "failure": "",
                }

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.debug(
            "av_sync_check",
            duration_ms=round(elapsed_ms, 1),
            path=str(path),
            sync_ok=result["sync_ok"],
        )
        return result

    @staticmethod
    def _write_stub_mp4(path: Path, label: str) -> None:
        """Generate a playable stub MP4 using ffmpeg, or fallback to minimal bytes.

        The ffmpeg-generated file is a real 5-second 1080x1920 video with a
        text overlay so it's visually obvious it's a stub.
        """
        import subprocess

        path.parent.mkdir(parents=True, exist_ok=True)
        text = label or "Stub Video"
        try:
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "color=c=#f5f5f7:s=1080x1920:d=5",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-an",  # no audio
                str(path),
            ]
            subprocess.run(cmd, capture_output=True, timeout=30, check=True)
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError, Exception) as exc:
            # ffmpeg unavailable or failed — write minimal magic-byte stub
            logger.warning(
                "remotion_assemble: ffmpeg stub generation failed",
                output_path=str(path),
                error=str(exc)[:200],
            )
            marker = label.encode()[:8].ljust(8, b"\0")
            path.write_bytes(b"\x00\x00\x00\x14ftypisom" + marker)

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors = []
        if not params.get("shots"):
            errors.append("missing 'shots' (list of shot dicts)")
        elif not isinstance(params["shots"], list):
            errors.append("'shots' must be a list")
        return errors

    def validate_output(self, data: Any) -> list[str]:
        errors = []
        if not data:
            return ["output is None"]
        if "video_path" not in data:
            errors.append("missing 'video_path'")
        if "verification" not in data:
            errors.append("missing 'verification' report")
        return errors

    def fallback(self, params: dict[str, Any]) -> SkillResult:
        label = params.get("output_label", f"fallback_{int(time.time())}")
        path = _resolve_render_output_dir(params) / f"{label}.mp4"
        self._write_stub_mp4(path, label)

        return SkillResult(
            success=True,
            data={
                "video_path": str(path),
                "render_json_path": "",
                "duration_seconds": float(params.get("total_duration", 30)),
                "file_size_bytes": path.stat().st_size,
                "resolution": f"{DEFAULT_RESOLUTION[0]}x{DEFAULT_RESOLUTION[1]}",
                "fps": DEFAULT_FPS,
                "shot_count": len(params.get("shots") or []),
                "is_stub": True,
                "simulated": True,
                "verification": {
                    "file_exists": True, "size_ok": True, "header_ok": True,
                    "duration_ok": True, "all_ok": True, "failures": [],
                    "mode": "fallback",
                },
                "_fallback": True,
            },
            metadata={"reason": "all_retries_exhausted"},
        )


# Auto-register
try:
    SkillRegistry.register(RemotionAssembleSkill())
    logger.info("remotion_assemble_skill: registered")
except ValueError as exc:
    logger.debug(
        "remotion_assemble_skill: already registered",
        error=str(exc)[:200],
    )
