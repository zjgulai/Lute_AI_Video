"""H9 renderer and media process-boundary contracts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from src.skills.remotion_assemble import RemotionAssembleSkill, _read_scoped_lyrics
from src.tools.safe_media import UnsafeMediaError, validate_media_file

REPO_ROOT = Path(__file__).resolve().parents[1]
RENDERING_PACKAGE = REPO_ROOT / "rendering" / "package.json"
RENDERING_SERVER = REPO_ROOT / "rendering" / "server.mjs"
RENDERING_RENDER = REPO_ROOT / "rendering" / "src" / "render.ts"
RENDERING_ROOT = REPO_ROOT / "rendering" / "src" / "Root.tsx"
RENDERING_DOCKERFILE = REPO_ROOT / "rendering" / "Dockerfile"
BACKEND_DOCKERFILE = REPO_ROOT / "Dockerfile.backend"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
RELEASE_COMPOSE = REPO_ROOT / "deploy" / "lighthouse" / "docker-compose.release.yml"
PROD_COMPOSE = REPO_ROOT / "deploy" / "lighthouse" / "docker-compose.prod.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
DUAL_RUNTIME_ADR = REPO_ROOT / "docs" / "architecture" / "adr" / "001-dual-runtime.md"
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
