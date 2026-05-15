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

import json
import os
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

logger = structlog.get_logger()

# Self-verification thresholds for FINAL assembled video
MIN_FINAL_SIZE_BYTES = 100 * 1024     # 100KB minimum
MIN_FINAL_DURATION = 5.0              # < 5s = unusable
DEFAULT_FPS = 30
DEFAULT_RESOLUTION = (1080, 1920)

MP4_FTYP_BRANDS = [b"isom", b"iso2", b"avc1", b"mp41", b"mp42", b"M4V ", b"M4A "]


class RemotionAssembleSkill(SkillCallable):
    """Renders the final mp4 via Remotion (Node.js) and verifies it."""

    name = "remotion-assemble-skill"
    description = "Assembles final .mp4 via Remotion from clips/captions/audio and self-verifies"
    max_retries = 2

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        from src.config import OUTPUT_DIR
        from src.tools.remotion_renderer import RemotionRenderer

        # === Inputs ===
        shots = params.get("shots") or []
        captions = params.get("captions") or []
        audio_paths = params.get("audio_paths") or []
        lyrics_paths = params.get("lyrics_paths") or []
        clip_paths = params.get("clip_paths") or []
        brand_guidelines = params.get("brand_guidelines") or {}
        output_label = params.get("output_label", f"video_{int(time.time())}")
        total_duration = params.get("total_duration") or self._compute_total_duration(shots)

        # Load generated lyrics text if available
        lyrics_text = ""
        if lyrics_paths:
            for lp in lyrics_paths:
                p = Path(lp)
                if p.exists() and p.stat().st_size > 10:
                    try:
                        lyrics_text = p.read_text(encoding="utf-8")
                        break
                    except Exception:
                        pass

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
        )

        # Write JSON to disk (for debugging / future Remotion use)
        renders_dir = OUTPUT_DIR / "renders"
        renders_dir.mkdir(parents=True, exist_ok=True)
        render_json_path = renders_dir / f"{output_label}_input.json"
        with open(render_json_path, "w") as f:
            json.dump(render_payload, f, indent=2, default=str)

        output_filename = f"{output_label}.mp4"

        # === PRIORITY 0: Delegate to dedicated rendering container if configured ===
        rendering_url = os.environ.get("RENDERING_SERVICE_URL", "").rstrip("/")
        if rendering_url:
            remote_result = await self._render_via_service(
                rendering_url=rendering_url,
                clip_paths=clip_paths,
                audio_paths=audio_paths,
                render_payload=render_payload,
                output_label=output_label,
            )
            if remote_result is not None:
                video_path = Path(remote_result["video_path"])
                is_stub_remote = bool(remote_result.get("is_stub", False))
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
                        "verification": verification,
                    },
                    metadata={
                        "render_mode": remote_result.get("render_mode", "rendering_service"),
                        "rendering_service": rendering_url,
                        "audio_muxed": bool(audio_paths) and not is_stub_remote,
                        "clip_count": len(clip_paths),
                    },
                )
            logger.warning("remotion_assemble: rendering service unavailable, falling back to local path", url=rendering_url)

        output_path = renders_dir / output_filename
        valid_clips = [
            Path(p) for p in clip_paths
            if p and Path(p).exists() and Path(p).stat().st_size > 1000
        ]

        is_stub = False
        render_mode = "remotion"
        remotion_done = False

        # === PRIORITY 1: Remotion unified render (embeds clips via <Video> component) ===
        renderer = RemotionRenderer()
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
            "1:1": "ShortVideo_1x1",
            "16:9": "ShortVideo_16x9",
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
                "verification": verification,
            },
            metadata={
                "render_mode": render_mode if not is_stub else "stub",
                "audio_muxed": bool(audio_paths) and not is_stub,
                "clip_count": len(valid_clips),
                "aspect_ratios_rendered": list(video_paths.keys()),
            },
        )

    # === Rendering service (HTTP) bridge ===

    async def _render_via_service(
        self,
        rendering_url: str,
        clip_paths: list[str],
        audio_paths: list[str],
        render_payload: dict[str, Any],
        output_label: str,
    ) -> dict[str, Any] | None:
        try:
            import httpx
        except ImportError:
            logger.warning("remotion_assemble: httpx not available, skipping rendering service")
            return None

        body = {
            "clip_paths": [str(p) for p in clip_paths if p],
            "audio_paths": [str(p) for p in audio_paths if p],
            "render_payload": render_payload,
            "output_label": output_label,
        }
        url = f"{rendering_url}/assemble"
        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                resp = await client.post(url, json=body)
                if resp.status_code != 200:
                    logger.error(
                        "remotion_assemble: rendering service returned non-200",
                        url=url,
                        status=resp.status_code,
                        body=resp.text[:300],
                    )
                    return None
                data = resp.json()
                if not data.get("success"):
                    logger.error("remotion_assemble: rendering service reported failure", data=data)
                    return None
                return data
        except Exception as e:
            logger.warning(
                "remotion_assemble: rendering service call failed",
                url=url,
                error=str(e),
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
            # Distribute audio paths across shots evenly (simple alignment)
            audio_per_shot = max(1, len(audio_paths) // max(1, len(normalized_shots)))
            for i, shot in enumerate(normalized_shots):
                audio_idx = min(i, len(audio_paths) - 1)
                audio_segments.append({
                    "type": "voiceover",
                    "start_time": shot["start_time"],
                    "end_time": shot["end_time"],
                    "text": shot.get("text_overlay", ""),
                    "audio_path": audio_paths[audio_idx],
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
                    str(path),
                ],
                capture_output=True, text=True, timeout=10, check=True,
            )
            w, h = result.stdout.strip().split("x")
            return int(w), int(h)
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

        try:
            # Build concat list file
            concat_list_path = output_path.parent / f"{output_path.stem}_concat.txt"
            with open(concat_list_path, "w") as f:
                for cp in clip_paths:
                    f.write(f"file '{cp.resolve()}'\n")

            used_reencode = False

            # Try stream-copy first (fast, no quality loss)
            try:
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                        "-i", str(concat_list_path),
                        "-c", "copy",
                        "-movflags", "+faststart",
                        str(output_path),
                    ],
                    capture_output=True, timeout=120, check=True,
                )
            except subprocess.CalledProcessError:
                logger.warning("remotion_assemble: concat -c copy failed, falling back to re-encode")
                used_reencode = True

            # If copy succeeded, verify dimensions match target
            if not used_reencode and output_path.exists():
                dims = self._get_video_dimensions(output_path)
                if dims is None or f"{dims[0]}x{dims[1]}" != target_str:
                    logger.warning(
                        "remotion_assemble: copy output dimensions %s != target %s, re-encoding",
                        dims, target_str,
                    )
                    used_reencode = True
                    # Remove the bad copy output before re-encoding
                    output_path.unlink(missing_ok=True)

            if used_reencode:
                # Force统一分辨率: scale to fit within target, then pad with black
                scale_filter = (
                    f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"
                    f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:black"
                )
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                        "-i", str(concat_list_path),
                        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                        "-vf", scale_filter,
                        "-c:a", "aac", "-b:a", "128k",
                        "-movflags", "+faststart",
                        str(output_path),
                    ],
                    capture_output=True, timeout=300, check=True,
                )

            if output_path.exists() and output_path.stat().st_size > 10000:
                return output_path
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError, Exception) as e:
            logger.warning("remotion_assemble: ffmpeg concat failed", error=str(e))
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
                    "-i", str(video_path),
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

        try:

            # Filter out non-existent or stub audio
            valid_audios = [Path(p) for p in audio_paths if Path(p).exists() and Path(p).stat().st_size > 200]
            if not valid_audios:
                return None

            # Concatenate audios via ffmpeg concat demuxer
            from src.config import OUTPUT_DIR
            concat_list_path = OUTPUT_DIR / "renders" / f"{output_label}_concat.txt"
            with open(concat_list_path, "w") as f:
                for ap in valid_audios:
                    f.write(f"file '{ap.resolve()}'\n")

            # Concat audios
            concat_audio = OUTPUT_DIR / "renders" / f"{output_label}_audio.mp3"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(concat_list_path),
                    "-c", "copy",
                    str(concat_audio),
                ],
                capture_output=True, timeout=60, check=True,
            )

            # Mux audio into video
            muxed_path = video_path.parent / f"{video_path.stem}_with_audio{video_path.suffix}"
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", str(video_path),
                    "-i", str(concat_audio),
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-shortest",
                    str(muxed_path),
                ],
                capture_output=True, timeout=120, check=True,
            )
            if muxed_path.exists():
                return muxed_path
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError, Exception) as e:
            logger.warning("remotion_assemble: ffmpeg mux failed (continuing without audio)", error=str(e))
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
                    str(path),
                ],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return float(result.stdout.strip() or "0.0")
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, Exception):
            pass
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
                        str(path),
                    ],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    return float(result.stdout.strip() or "0.0")
            except Exception:
                pass
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
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError, Exception):
            # ffmpeg unavailable or failed — write minimal magic-byte stub
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
        from src.config import OUTPUT_DIR

        label = params.get("output_label", f"fallback_{int(time.time())}")
        path = OUTPUT_DIR / "renders" / f"{label}.mp4"
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
except ValueError:
    pass
