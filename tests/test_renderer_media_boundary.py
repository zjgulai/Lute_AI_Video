"""H9 renderer and media process-boundary contracts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import src.skills.remotion_assemble as assemble_module
from src.skills.remotion_assemble import (
    RemotionAssembleSkill,
    _read_scoped_lyrics,
    _write_or_reuse_render_payload,
)
from src.tools.safe_media import UnsafeMediaError, validate_media_file

REPO_ROOT = Path(__file__).resolve().parents[1]
RENDERING_PACKAGE = REPO_ROOT / "rendering" / "package.json"
RENDERING_SERVER = REPO_ROOT / "rendering" / "server.mjs"
RENDERING_HEALTHCHECK = REPO_ROOT / "rendering" / "healthcheck.mjs"
RENDERING_RENDER = REPO_ROOT / "rendering" / "src" / "render.ts"
RENDERING_ROOT = REPO_ROOT / "rendering" / "src" / "Root.tsx"
RENDERING_DOCKERFILE = REPO_ROOT / "rendering" / "Dockerfile"
BACKEND_DOCKERFILE = REPO_ROOT / "Dockerfile.backend"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
RELEASE_COMPOSE = REPO_ROOT / "deploy" / "lighthouse" / "docker-compose.release.yml"
PROD_COMPOSE = REPO_ROOT / "deploy" / "lighthouse" / "docker-compose.prod.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
DEPLOY_SCRIPT = REPO_ROOT / "deploy" / "lighthouse" / "deploy.sh"
DUAL_RUNTIME_ADR = REPO_ROOT / "docs" / "architecture" / "adr" / "001-dual-runtime.md"
REMOTION_RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "remotion-no-provider-key.md"
TRANSLATIONS = REPO_ROOT / "web" / "src" / "i18n" / "translations.ts"


def test_avi_is_rejected_before_ffmpeg_or_ffprobe(tmp_path: Path) -> None:
    crafted = tmp_path / "crafted.avi"
    crafted.write_bytes(b"RIFF" + b"\x00" * 4 + b"AVI " + b"x" * 2_000)

    with pytest.raises(UnsafeMediaError, match="extension is not approved"):
        validate_media_file(crafted)


def test_lyrics_reader_rejects_symlink_and_oversized_input(tmp_path: Path) -> None:
    output_dir = tmp_path / "assemble"
    output_dir.mkdir()
    lyrics = tmp_path / "lyrics.txt"
    lyrics.write_text("safe lyrics content")
    linked = tmp_path / "linked.txt"
    linked.symlink_to(lyrics)
    oversized = tmp_path / "oversized.txt"
    oversized.write_bytes(b"x" * (64 * 1024 + 1))

    assert _read_scoped_lyrics(lyrics, output_dir) == "safe lyrics content"
    with pytest.raises(UnsafeMediaError, match="path is invalid"):
        _read_scoped_lyrics(linked, output_dir)
    with pytest.raises(UnsafeMediaError, match="path is invalid"):
        _read_scoped_lyrics(oversized, output_dir)


def test_lyrics_reader_normalizes_missing_tenant_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "missing-output-root"
    output_dir = tmp_path / "existing-run" / "assemble"
    output_dir.mkdir(parents=True)
    lyrics = tmp_path / "lyrics.txt"
    lyrics.write_text("safe lyrics content")
    policy = SimpleNamespace(
        tenant_id="tenant-a",
        artifact_disposition="pending_review",
    )

    monkeypatch.setattr("src.config.OUTPUT_DIR", output_root)
    monkeypatch.setattr(
        "src.pipeline.generation_policy.get_effective_generation_policy",
        lambda: policy,
    )

    with pytest.raises(UnsafeMediaError, match="output scope is invalid"):
        _read_scoped_lyrics(lyrics, output_dir)


def test_render_payload_exact_replay_is_safe_and_conflicts_fail_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "video_input.json"
    payload = {"clip_paths": [], "duration": 15}

    _write_or_reuse_render_payload(path, payload)
    original = path.read_bytes()
    _write_or_reuse_render_payload(path, payload)
    assert path.read_bytes() == original
    assert os.stat(path).st_mode & 0o777 == 0o640

    with pytest.raises(UnsafeMediaError, match="render input conflict"):
        _write_or_reuse_render_payload(path, {"clip_paths": ["changed"]})

    symlink = tmp_path / "linked_input.json"
    symlink.symlink_to(path)
    with pytest.raises(UnsafeMediaError, match="render input conflict"):
        _write_or_reuse_render_payload(symlink, payload)

    with pytest.raises(UnsafeMediaError, match="render input is too large"):
        _write_or_reuse_render_payload(
            tmp_path / "oversized.json",
            {"payload": "x" * (1024 * 1024)},
        )


def test_production_ffmpeg_paths_do_not_select_vulnerable_features() -> None:
    runtime = "\n".join(
        path.read_text()
        for path in sorted((REPO_ROOT / "src").rglob("*.py"))
    ).lower()
    renderer = "\n".join(
        [
            RENDERING_SERVER.read_text().lower(),
            (REPO_ROOT / "rendering" / "media-safety.mjs").read_text().lower(),
        ]
    )

    for forbidden in ("floodfill", "swaprect", "quirc", "hqdn3d"):
        assert forbidden not in runtime
        assert forbidden not in renderer
    assert '"-safe", "0"' not in renderer
    assert '".avi"' not in runtime
    assert "_last_frame.png" not in runtime
    assert '"-c:v", "mjpeg"' in runtime


def test_renderer_package_runs_builtin_security_tests() -> None:
    package = json.loads(RENDERING_PACKAGE.read_text())

    assert package["scripts"]["test"] == "node --test"


def test_ci_and_release_preflight_run_renderer_tests_and_typecheck() -> None:
    for workflow_path, job_name in (
        (CI_WORKFLOW, "test"),
        (DEPLOY_WORKFLOW, "preflight"),
    ):
        workflow = yaml.safe_load(workflow_path.read_text())
        steps = workflow["jobs"][job_name]["steps"]
        commands = "\n".join(
            str(step.get("run", ""))
            for step in steps
            if isinstance(step, dict)
        )
        assert "rendering && npm test" in commands or any(
            step.get("working-directory") == "rendering"
            and step.get("run") == "npm test"
            for step in steps
            if isinstance(step, dict)
        )
        assert "npm exec tsc -- --noEmit" in commands


def test_current_architecture_and_ui_describe_private_uds_renderer() -> None:
    adr = DUAL_RUNTIME_ADR.read_text()
    translations = TRANSLATIONS.read_text()

    assert "rendering:3001" not in adr
    assert "Unix Domain Socket" in adr
    assert "/run/rendering/rendering.sock" in adr
    assert "rendering:3001 health" not in translations
    assert "Unix socket health" in translations


def test_renderer_server_is_uds_only_bounded_and_never_uses_unsafe_concat() -> None:
    source = RENDERING_SERVER.read_text()

    assert 'express.json({ limit: "1mb"' in source
    assert "RENDERING_SERVICE_SOCKET" in source
    assert 'app.listen(PORT, "0.0.0.0"' not in source
    assert '"-safe", "0"' not in source
    assert '"-safe", "1"' in source
    assert "validateAssembleRequest" in source
    assert "reserveRenderOperation" in source
    assert "MAX_RENDER_CONCURRENCY = 1" in source
    assert "MAX_MEDIA_FILES = 16" in (
        REPO_ROOT / "rendering" / "media-safety.mjs"
    ).read_text()
    assert "MAX_REQUEST_MEDIA_BYTES = 4 * 1024 * 1024 * 1024" in (
        REPO_ROOT / "rendering" / "media-safety.mjs"
    ).read_text()
    assert "Promise.all(clipPaths.map" not in (
        REPO_ROOT / "rendering" / "media-safety.mjs"
    ).read_text()
    assert "SERVER_RENDER_DEADLINE_MS = 540_000" in source
    assert "assertRenderDeadline" in source
    assert "checkDeadline: assertRenderDeadline" in source
    assert "state.committed" in source
    assert "detached: true" in source
    assert 'process.kill(-proc.pid, "SIGKILL")' in source
    assert "await publishLink(source, destination)" in source
    assert source.index("await setMode(source, 0o440)") < source.index(
        "await publishLink(source, destination)"
    )
    assert "await Promise.all([" in source
    assert "async function probeCommand" in source
    assert "HEALTH_PROBE_TIMEOUT_MS = 20_000" in source
    assert "timeoutMs: HEALTH_PROBE_TIMEOUT_MS" in source
    assert '"renderer_busy"' in source
    assert 'path.join(REMOTION_PROJECT, "node_modules", "remotion"' in source
    assert '"./node_modules/remotion/package.json"' not in source
    render_source = RENDERING_RENDER.read_text()
    assert render_source.count("browserExecutable: CHROME_EXECUTABLE") == 2
    assert 'const CHROME_EXECUTABLE = "/usr/bin/google-chrome-stable"' in render_source
    assert "fileURLToPath(import.meta.url)" in render_source
    assert "__dirname" not in render_source
    assert 'path.resolve(MODULE_DIR, "index.ts")' in render_source
    renderer_entry = (REPO_ROOT / "rendering" / "src" / "index.ts").read_text()
    assert "registerRoot(RemotionRoot)" in renderer_entry
    assert 'imageFormat: "jpeg"' in render_source
    assert "calculateMetadata" in RENDERING_ROOT.read_text()
    root_source = RENDERING_ROOT.read_text()
    assert "ShortVideo_1x1" not in root_source
    assert "ShortVideo_16x9" not in root_source
    assert "ShortVideo-1x1" in root_source
    assert "ShortVideo-16x9" in root_source
    assert "Number.isFinite(requestedDuration)" in root_source
    assert "requestedDuration >= 1" in root_source
    assert "requestedDuration <= 180" in root_source


def test_release_renderer_is_nonroot_readonly_capless_and_not_on_tcp_network() -> None:
    for compose_path in (RELEASE_COMPOSE, PROD_COMPOSE):
        compose = yaml.safe_load(compose_path.read_text())
        backend = compose["services"]["backend"]
        rendering = compose["services"]["rendering"]

        assert "RENDERING_SERVICE_URL" not in "\n".join(backend["environment"])
        assert (
            "RENDERING_SERVICE_SOCKET=/run/rendering/rendering.sock"
            in backend["environment"]
        )
        assert "expose" not in rendering
        assert "ports" not in rendering
        assert "networks" not in rendering
        assert rendering["network_mode"] == "none"
        assert rendering["init"] is True
        assert rendering["user"] == "999:999"
        assert rendering["read_only"] is True
        assert rendering["cpus"] == "2.0"
        assert rendering["mem_limit"] == "4g"
        assert rendering["pids_limit"] == 256
        assert rendering["cap_drop"] == ["ALL"]
        assert rendering["security_opt"] == ["no-new-privileges:true"]
        assert rendering["healthcheck"]["timeout"] == "30s"
        assert rendering["healthcheck"]["start_period"] == "60s"
        assert rendering["healthcheck"]["test"] == [
            "CMD",
            "node",
            "/app/healthcheck.mjs",
        ]
        assert backend["depends_on"]["rendering"]["condition"] == "service_healthy"
        assert rendering["build"]["args"]["RELEASE_SOURCE_SHA"] == (
            "${RELEASE_SOURCE_SHA:?RELEASE_SOURCE_SHA is required}"
        )
        assert any(
            mount == "renderer_socket:/run/rendering"
            for mount in rendering["volumes"]
        )
        assert any(
            mount == "renderer_socket:/run/rendering"
            for mount in backend["volumes"]
        )

    deploy_workflow = yaml.safe_load(DEPLOY_WORKFLOW.read_text())
    release_steps = deploy_workflow["jobs"]["build-images"]["steps"]
    smoke = next(
        step
        for step in release_steps
        if step.get("name") == "Smoke exact frontend and rendering image runtimes"
    )
    renderer_command = smoke["run"].split(
        "docker run -d --name release-smoke-rendering", 1
    )[1].split("lighthouse-rendering:", 1)[0]
    assert "--init" in renderer_command
    assert "node /app/healthcheck.mjs" in smoke["run"]

    dockerfile = RENDERING_DOCKERFILE.read_text()
    assert "COPY rendering/healthcheck.mjs" in dockerfile
    assert 'CMD ["node", "/app/healthcheck.mjs"]' in dockerfile
    assert "node /app/healthcheck.mjs" in DEPLOY_SCRIPT.read_text()
    healthcheck = RENDERING_HEALTHCHECK.read_text()
    assert "socketPath" in healthcheck
    assert 'path: "/health"' in healthcheck


def test_release_backend_has_nonwritable_fixed_xdg_media_root() -> None:
    backend_dockerfile = BACKEND_DOCKERFILE.read_text()
    assert "XDG_DATA_HOME=/usr/share" in backend_dockerfile
    assert backend_dockerfile.index("XDG_DATA_HOME=/usr/share") < (
        backend_dockerfile.index("USER 999:999")
    )

    for compose_path in (RELEASE_COMPOSE, PROD_COMPOSE):
        compose = yaml.safe_load(compose_path.read_text())
        backend = compose["services"]["backend"]
        assert "XDG_DATA_HOME=/usr/share" in backend["environment"]
        assert backend["user"] == "999:999"
        assert backend["read_only"] is True
        assert backend["cap_drop"] == ["ALL"]
        assert backend["security_opt"] == ["no-new-privileges:true"]
        assert any(mount.startswith("/tmp:") for mount in backend["tmpfs"])
        assert "/health/ready" in " ".join(backend["healthcheck"]["test"])


def test_backend_build_context_excludes_local_python_caches() -> None:
    patterns = {
        line.strip()
        for line in DOCKERIGNORE.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "**/__pycache__/" in patterns
    assert "**/*.pyc" in patterns
    assert "**/*.pyo" in patterns


def test_images_pin_existing_shared_nonroot_identity_and_fixed_google_chrome() -> None:
    renderer = RENDERING_DOCKERFILE.read_text()
    backend = BACKEND_DOCKERFILE.read_text()

    assert "node:22-alpine" not in renderer
    assert "GOOGLE_CHROME_VERSION=150.0.7871.186-1" in renderer
    assert "ARG APT_MIRROR=deb.debian.org" in renderer
    assert 's|http://${APT_MIRROR}|https://${APT_MIRROR}|g' in renderer
    assert 'test "${TARGETARCH}" = "amd64"' in renderer
    assert (
        "ADD --checksum=sha256:"
        "4193e00b6d5d5969ee63f7a69596868f546aa0e8cb077b3e0bf9cc1e2c719d00"
        in renderer
    )
    assert "google-chrome-stable_150.0.7871.186-1_amd64.deb" in renderer
    assert "ARG CHROME_PACKAGE_STAGE=chrome-download" in renderer
    assert "sha256sum -c -" in renderer
    assert renderer.index("ca-certificates") < renderer.index(
        "COPY --from=chrome-package"
    )
    assert "dpkg-query -W" in renderer
    assert "USER 999:999" in renderer
    assert (
        "HEALTHCHECK --interval=30s --timeout=30s "
        "--start-period=60s --retries=3"
        in renderer
    )
    assert "USER 999:999" in backend
    assert "getent group 999 >/dev/null || groupadd --gid 999 renderer" in renderer
    assert "chown -R 999:999 /app" not in renderer
    assert "chown 999:999 /app/output /run/rendering" in renderer
    assert renderer.index("ENV PUPPETEER_SKIP_DOWNLOAD") < renderer.index("RUN npm ci")
    assert "HOME=/tmp/renderer-home" in renderer
    assert "XDG_DATA_HOME=/usr/share" in renderer
    assert "rm -rf /tmp/renderer-home" in renderer
    assert "useradd --uid 999" in renderer
    assert "useradd --uid 999" in backend
    assert "getent group 999 >/dev/null || groupadd --gid 999 appgroup" in backend
    assert "getent passwd 999 >/dev/null" in backend
    assert "chown -R 999:999 /app" in backend
    assert "chown -R appuser:appgroup /app" not in backend


def test_stale_renderer_lock_recovery_is_scoped_and_fail_closed() -> None:
    runbook = REMOTION_RUNBOOK.read_text()

    assert "停止 renderer" in runbook
    assert "超过 540 秒" in runbook
    assert "没有同 label 的已发布 `.mp4`" in runbook
    assert "`lstat`" in runbook
    assert "禁止用宽泛的 `find ... -delete`" in runbook


def test_concat_retry_removes_partial_output_and_attempt_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clips = [tmp_path / "clip-a.mp4", tmp_path / "clip-b.mp4"]
    for clip in clips:
        clip.write_bytes(b"clip")
    output = tmp_path / "assembled.mp4"
    calls = 0

    monkeypatch.setattr(assemble_module, "validate_media_file", lambda _path: None)

    def fake_run(command: list[str], **_kwargs: object) -> None:
        nonlocal calls
        calls += 1
        attempt_output = Path(command[-1])
        if calls == 1:
            attempt_output.write_bytes(b"partial")
            raise subprocess.CalledProcessError(1, command)
        assert not attempt_output.exists()
        attempt_output.write_bytes(b"x" * 10_001)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = RemotionAssembleSkill()._concat_clips(clips, output)

    assert result == output
    assert calls == 2
    assert not list(tmp_path.glob(".*.concat"))
    assert not list(tmp_path.glob(".*-concat-*.mp4"))

    original = output.read_bytes()
    with pytest.raises(UnsafeMediaError, match="output already exists"):
        RemotionAssembleSkill()._concat_clips(clips, output)
    assert output.read_bytes() == original
    assert calls == 2


def test_audio_mux_attempt_intermediates_are_always_cleaned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video = tmp_path / "assembled.mp4"
    video.write_bytes(b"v" * 1_000)
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"a" * 1_000)

    monkeypatch.setattr(assemble_module, "validate_media_file", lambda _path: None)
    monkeypatch.setattr(
        assemble_module,
        "ffmpeg_local_input_args",
        lambda path: ["-i", str(path)],
    )

    def fake_run(command: list[str], **_kwargs: object) -> None:
        Path(command[-1]).write_bytes(b"muxed" * 100)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = RemotionAssembleSkill()._try_mux_audio(
        video_path=video,
        audio_paths=[str(audio)],
        output_label="assembled",
    )

    assert result is not None
    assert result == tmp_path / "assembled_with_audio.mp4"
    assert result.exists()
    assert not list(tmp_path.glob(".*.concat"))
    assert not list(tmp_path.glob(".*-audio-*.mkv"))


def test_concat_publication_preserves_a_concurrent_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clips = [tmp_path / "clip-a.mp4", tmp_path / "clip-b.mp4"]
    for clip in clips:
        clip.write_bytes(b"clip")
    output = tmp_path / "assembled.mp4"

    monkeypatch.setattr(assemble_module, "validate_media_file", lambda _path: None)
    monkeypatch.setattr(
        RemotionAssembleSkill,
        "_get_video_dimensions",
        staticmethod(lambda _path: (1080, 1920)),
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **_kwargs: Path(command[-1]).write_bytes(b"x" * 10_001),
    )

    def concurrent_link(
        _source: Path,
        destination: Path,
        *,
        follow_symlinks: bool,
    ) -> None:
        assert follow_symlinks is False
        destination.write_bytes(b"winner")
        raise FileExistsError

    monkeypatch.setattr(assemble_module.os, "link", concurrent_link)

    with pytest.raises(UnsafeMediaError, match="output already exists"):
        RemotionAssembleSkill()._concat_clips(clips, output)

    assert output.read_bytes() == b"winner"
    assert not list(tmp_path.glob(".*.concat"))
    assert not list(tmp_path.glob(".*-concat-*.mp4"))


@pytest.mark.asyncio
async def test_backend_renderer_bridge_uses_uds_and_rejects_loose_response_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "tenants" / "tenant-a" / "pending_review" / "run" / "assemble"
    output_dir.mkdir(parents=True)
    video = output_dir / "video-001.mp4"
    video.write_bytes(
        b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"0" * 2_000
    )
    seen: dict[str, object] = {}

    class FakeTransport:
        def __init__(self, *, uds: str) -> None:
            seen["uds"] = uds

    class FakeResponse:
        status_code = 200
        payload: dict[str, object] = {
            "success": True,
            "video_path": str(video),
            "file_size_bytes": video.stat().st_size,
            "artifact_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
            "is_stub": False,
            "audio_muxed": False,
        }

        def json(self) -> dict[str, object]:
            return self.payload

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            seen["base_url"] = kwargs["base_url"]
            seen["transport"] = kwargs["transport"]

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(
            self,
            route: str,
            *,
            json: dict[str, object],
        ) -> FakeResponse:
            seen["route"] = route
            seen["body"] = json
            return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", FakeTransport)
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    socket_path = "/run/rendering/rendering.sock"
    result = await RemotionAssembleSkill()._render_via_service(
        rendering_socket=socket_path,
        clip_paths=[],
        audio_paths=[],
        render_payload={"clip_paths": []},
        output_label="video-001",
        output_dir=output_dir,
        tenant_id="tenant-a",
        artifact_disposition="pending_review",
    )

    assert result is not None
    assert result["video_path"] == str(video)
    assert seen["uds"] == socket_path
    assert seen["base_url"] == "http://rendering"
    assert seen["route"] == "/assemble"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["output_dir"] == str(output_dir)
    assert body["tenant_id"] == "tenant-a"

    FakeResponse.payload = {
        "success": 1,
        "video_path": str(video),
        "is_stub": 0,
        "audio_muxed": 0,
    }
    loose = await RemotionAssembleSkill()._render_via_service(
        rendering_socket=socket_path,
        clip_paths=[],
        audio_paths=[],
        render_payload={"clip_paths": []},
        output_label="video-001",
        output_dir=output_dir,
        tenant_id="tenant-a",
        artifact_disposition="pending_review",
    )
    assert loose is None
