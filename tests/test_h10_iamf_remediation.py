"""H10 patched FFmpeg and IAMF-removal supply-chain contracts."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PATCH = REPO_ROOT / "docker" / "ffmpeg" / (
    "86708357d126af84c16f80d9c57335d1e8c845c5.patch"
)
DVBSUB_PATCH = REPO_ROOT / "docker" / "ffmpeg" / (
    "02fc47e13f903768b75f7985a2706a6223ab4506.patch"
)
CFHD_PATCH = REPO_ROOT / "docker" / "ffmpeg" / (
    "16b2049d4d5222db6cd7c031409058571c94f6a9.patch"
)
MPEGENC_PATCH = REPO_ROOT / "docker" / "ffmpeg" / (
    "9d786e4b5e9b8482651928574de33772aeee7be1.patch"
)
LIBRIST_PATCH = REPO_ROOT / "docker" / "ffmpeg" / (
    "1c10bcc2e17255dacb717a25ab3db142ce390602.patch"
)
VC2HQ_PATCH = REPO_ROOT / "docker" / "ffmpeg" / (
    "1cdeb3c4e7f1f8566d846b9b451e01c376398818.patch"
)
DASH_PATCH = REPO_ROOT / "docker" / "ffmpeg" / (
    "65b0dab903e5975e036b30ecc58f5935d4f151e0-debian-7.1.5-backport.patch"
)
BUILD_SCRIPT = REPO_ROOT / "docker" / "ffmpeg" / "build-h10-debs.sh"
INSTALL_SCRIPT = REPO_ROOT / "docker" / "ffmpeg" / "install-h10-build-deps.sh"
VERIFY_SCRIPT = REPO_ROOT / "docker" / "ffmpeg" / "verify-h10-runtime.sh"
BACKEND_DOCKERFILE = REPO_ROOT / "Dockerfile.backend"
FRONTEND_DOCKERFILE = REPO_ROOT / "web" / "Dockerfile"
FRONTEND_DOCKERIGNORE = REPO_ROOT / "web" / ".dockerignore"
RENDERING_DOCKERFILE = REPO_ROOT / "rendering" / "Dockerfile"
CLOUDBASE_DEPLOY_GUIDE = REPO_ROOT / "deploy" / "tencent-cloudbase.md"

PATCH_SHA256 = "b800c259300e41ba3a35a626953ca7665648e7de9955e168d8477d7414e7e3f1"
DVBSUB_PATCH_SHA256 = (
    "6a06c12bab05882f3116b32e81562750c450a421d23635aaf25bddd254a80525"
)
CFHD_PATCH_SHA256 = (
    "dd5ab52749f5aabbdf02202d0bd26703079261cd429a0f6e6013299d6d468646"
)
MPEGENC_PATCH_SHA256 = (
    "2dcfec279bad372be7eb54b55f5f2c59b1c33151325317946b92da4e95039f34"
)
LIBRIST_PATCH_SHA256 = (
    "89554690fc735a902724168084150ec7b4631e42d525bd9a86b31dc5e8df8573"
)
VC2HQ_PATCH_SHA256 = (
    "849f908e6336d4b9676521c7e3405d18ef54b9b8800e58d9030ecb343868e03b"
)
DASH_PATCH_SHA256 = (
    "393142cc01e241019986194cb15b9d248b5173ccc45e23c1724ebc5f59fd73f5"
)
ORIGINAL_SOURCE_SHA256 = (
    "de668509caf9e35e3cd162473441fdb29538c6d96ed080292b3cf9e6fc5d558f"
)
DEBIAN_SOURCE_SHA256 = (
    "a1be51d8a10744952fe94fa318bf71bbc8074bed0951382c079ab7ef227f74ef"
)
H10_VERSION = "7:7.1.5-0+deb13u1+h10.5"
FFMPEG_RUNTIME_PACKAGES = {
    "ffmpeg",
    "libavcodec61",
    "libavdevice61",
    "libavfilter10",
    "libavformat61",
    "libavutil59",
    "libpostproc58",
    "libswresample5",
    "libswscale8",
}

PYTHON_IMAGE = (
    "python:3.12.13-slim-trixie@"
    "sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36"
)
FRONTEND_NODE_IMAGE = (
    "node:22-alpine@"
    "sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32"
)
RENDERER_NODE_IMAGE = (
    "node:22.23.2-trixie-slim@"
    "sha256:7b8a0c89c54499bee567618f96578e1a12a800f062fbdbfd1fb6a443fa6f6284"
)
SUPERSEDED_RENDERER_NODE_DIGEST = (
    "sha256:e6d9a389d34ff9678438af985c9913fbd1eb6ed36e80fea56644f4b4f6dd70ba"
)


def test_release_base_images_are_pinned_canonical_and_overrideable() -> None:
    backend = BACKEND_DOCKERFILE.read_text()
    frontend = FRONTEND_DOCKERFILE.read_text()
    renderer = RENDERING_DOCKERFILE.read_text()

    assert f"ARG PYTHON_IMAGE={PYTHON_IMAGE}" in backend
    assert backend.count("FROM ${PYTHON_IMAGE}") == 2
    assert f"FROM {PYTHON_IMAGE}" not in backend

    assert f"ARG NODE_IMAGE={FRONTEND_NODE_IMAGE}" in frontend
    assert frontend.count("FROM ${NODE_IMAGE}") == 2
    assert "FROM node:22-alpine" not in frontend

    assert f"ARG NODE_IMAGE={RENDERER_NODE_IMAGE}" in renderer
    assert SUPERSEDED_RENDERER_NODE_DIGEST not in renderer
    assert f"ARG FFMPEG_BUILDER_IMAGE={PYTHON_IMAGE}" in renderer
    assert renderer.count("FROM ${NODE_IMAGE}") == 2
    assert renderer.count("FROM ${FFMPEG_BUILDER_IMAGE}") == 1
    assert not renderer.startswith("# syntax=")

    for dockerfile in (backend, frontend, renderer):
        assert "docker.m.daocloud.io" not in dockerfile


def test_frontend_build_context_excludes_regenerable_local_state() -> None:
    assert FRONTEND_DOCKERIGNORE.is_file()
    entries = {
        line.strip()
        for line in FRONTEND_DOCKERIGNORE.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert {
        "node_modules/",
        ".next/",
        "out/",
        "coverage/",
        "playwright-report/",
        "test-results/",
        "blob-report/",
        "tmp/",
        ".git/",
        "*.log",
        ".DS_Store",
        ".env*",
        "*.pem",
        "*.key",
        "*.p12",
        "*.pfx",
        "id_rsa*",
        "id_ed25519*",
    } <= entries
    assert not any(entry.startswith("!") for entry in entries)


def test_frontend_runtime_declares_numeric_nonroot_identity() -> None:
    source = FRONTEND_DOCKERFILE.read_text()
    runtime = source.split("FROM ${NODE_IMAGE} AS runner", 1)[1]

    assert runtime.count("COPY --chown=1000:1000 --from=builder") == 3
    assert "USER 1000:1000" in runtime
    assert runtime.index("USER 1000:1000") < runtime.index(
        'CMD ["node", "server.js"]'
    )


def test_upstream_iamf_patch_is_exact_and_auditable() -> None:
    patch_bytes = PATCH.read_bytes()
    patch_text = patch_bytes.decode()

    assert hashlib.sha256(patch_bytes).hexdigest() == PATCH_SHA256
    assert "From 86708357d126af84c16f80d9c57335d1e8c845c5" in patch_text
    assert "libavformat/iamf_parse.c" in patch_text
    assert "count_label > len - avio_tell(pbc)" in patch_text


@pytest.mark.parametrize(
    ("patch", "expected_sha256", "commit", "source_file", "fixed_expression"),
    (
        (
            DVBSUB_PATCH,
            DVBSUB_PATCH_SHA256,
            "02fc47e13f903768b75f7985a2706a6223ab4506",
            "libavcodec/dvbsub_parser.c",
            "PARSE_BUF_SIZE - pc->packet_index",
        ),
        (
            CFHD_PATCH,
            CFHD_PATCH_SHA256,
            "16b2049d4d5222db6cd7c031409058571c94f6a9",
            "libavcodec/cfhd.c",
            "lowpass_width * 2 > s->plane[plane].width",
        ),
        (
            MPEGENC_PATCH,
            MPEGENC_PATCH_SHA256,
            "9d786e4b5e9b8482651928574de33772aeee7be1",
            "libavformat/mpegenc.c",
            "get_system_header_size(ctx) > 128 - 14",
        ),
        (
            LIBRIST_PATCH,
            LIBRIST_PATCH_SHA256,
            "1c10bcc2e17255dacb717a25ab3db142ce390602",
            "libavformat/librist.c",
            "FFMIN(data_block->payload_len, size)",
        ),
        (
            VC2HQ_PATCH,
            VC2HQ_PATCH_SHA256,
            "1cdeb3c4e7f1f8566d846b9b451e01c376398818",
            "libavformat/rtpenc_vc2hq.c",
            "size > rtp_ctx->max_payload_size",
        ),
    ),
)
def test_new_upstream_ffmpeg_patches_are_exact_and_auditable(
    patch: Path,
    expected_sha256: str,
    commit: str,
    source_file: str,
    fixed_expression: str,
) -> None:
    patch_bytes = patch.read_bytes()
    patch_text = patch_bytes.decode()

    assert hashlib.sha256(patch_bytes).hexdigest() == expected_sha256
    assert f"From {commit}" in patch_text
    assert source_file in patch_text
    assert fixed_expression in patch_text


def test_dash_backport_is_checksum_bound_and_preserves_upstream_fix() -> None:
    patch_bytes = DASH_PATCH.read_bytes()
    patch_text = patch_bytes.decode()

    assert hashlib.sha256(patch_bytes).hexdigest() == DASH_PATCH_SHA256
    assert "From 65b0dab903e5975e036b30ecc58f5935d4f151e0" in patch_text
    assert "Backport-note: the second hunk context is adapted to FFmpeg 7.1.5" in patch_text
    assert "libavformat/dashdec.c" in patch_text
    assert "rep_dest->cur_seq_no < 0" in patch_text
    assert "pls->cur_seq_no >= 0" in patch_text


def test_builder_patches_exact_debian_source_and_disables_iamf() -> None:
    source = BUILD_SCRIPT.read_text()

    assert ORIGINAL_SOURCE_SHA256 in source
    assert DEBIAN_SOURCE_SHA256 in source
    assert PATCH_SHA256 in source
    assert DVBSUB_PATCH_SHA256 in source
    assert CFHD_PATCH_SHA256 in source
    assert MPEGENC_PATCH_SHA256 in source
    assert LIBRIST_PATCH_SHA256 in source
    assert VC2HQ_PATCH_SHA256 in source
    assert DASH_PATCH_SHA256 in source
    assert H10_VERSION in source
    for variable in (
        "PATCH",
        "DVBSUB_PATCH",
        "CFHD_PATCH",
        "MPEGENC_PATCH",
        "LIBRIST_PATCH",
        "VC2HQ_PATCH",
        "DASH_PATCH",
    ):
        assert f'"${variable}_NAME"' in source
        assert f'"${variable}_SHA256" "$SOURCE_ROOT/${variable}_NAME"' in source
    assert 'mkdir -p "$BUILD_ROOT/debian/patches"' in source
    assert "--disable-demuxer=iamf" in source
    assert "--disable-libssh" in source
    assert "--disable-librist" in source
    assert "--disable-debug" in source
    assert "'s/^FLAVORS = standard static$/FLAVORS = standard/'" in source
    assert "dpkg-buildpackage -B -Ppkg.ffmpeg.noextra" in source
    assert "DEB_BUILD_OPTIONS" in source
    assert "nocheck noautodbgsym" in source
    assert "DEB_CFLAGS_MAINT_APPEND" in source and "-g0" in source
    assert "DEB_CXXFLAGS_MAINT_APPEND" in source and "-g0" in source
    for package in FFMPEG_RUNTIME_PACKAGES:
        assert package in source


def test_builder_dependencies_are_exact_and_cacheable() -> None:
    source = INSTALL_SCRIPT.read_text()

    assert 'DEBIAN_VERSION="7:7.1.5-0+deb13u1"' in source
    assert "apt-get build-dep" in source
    assert "Acquire::Retries=5" in source
    assert "DEBIAN_FRONTEND=noninteractive" in source


def test_runtime_verifier_binds_every_package_and_removes_iamf() -> None:
    source = VERIFY_SCRIPT.read_text()

    assert H10_VERSION in source
    assert "dpkg-query" in source
    assert "ffmpeg -hide_banner -demuxers" in source
    assert "ffprobe -hide_banner -formats" in source
    assert 'index($1, "D")' in source
    assert "IAMF demuxer remains enabled in ffprobe" in source
    assert "IAMF format remains enabled in ffprobe" not in source
    for forbidden_package in ("libssh-4", "librist4", "libcjson1"):
        assert forbidden_package in source
    assert "%s must not be installed" in source
    assert "SFTP protocol remains enabled" in source
    assert "RIST protocol remains enabled" in source
    assert 'find /tmp/ffmpeg-debs -maxdepth 1 -type f' in source
    assert 'dpkg-deb --fsys-tarfile "$ffmpeg_deb"' in source
    assert "changelog.Debian.gz" in source
    assert "iamf" in source
    for package in FFMPEG_RUNTIME_PACKAGES:
        assert package in source


@pytest.mark.parametrize("forbidden_package", ("libssh-4", "librist4", "libcjson1"))
def test_runtime_verifier_rejects_forbidden_package_before_inventory(
    tmp_path: Path,
    forbidden_package: str,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "dpkg-query").write_text(
        "#!/bin/sh\n"
        f"if [ \"$2\" = \"{forbidden_package}\" ]; then exit 0; fi\n"
        "if [ \"$2\" = \"libssh-4\" ] || [ \"$2\" = \"librist4\" ] || "
        "[ \"$2\" = \"libcjson1\" ]; then exit 1; fi\n"
        f"printf '%s\\n' '{H10_VERSION}'\n"
    )
    for command, output in (
        ("ffmpeg", "Demuxers:\\n D  mov             QuickTime / MOV\\n"),
        ("ffprobe", "File formats:\\n DE mov             QuickTime / MOV\\n"),
    ):
        (fake_bin / command).write_text(
            f"#!/bin/sh\nprintf '%s' '{output}'\n"
        )
    for executable in fake_bin.iterdir():
        executable.chmod(0o755)

    result = subprocess.run(
        ["/bin/sh", str(VERIFY_SCRIPT)],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin"},
        check=False,
    )

    assert result.returncode != 0
    assert f"{forbidden_package} must not be installed" in result.stderr


@pytest.mark.parametrize(
    ("failed_command", "mode"),
    (
        ("ffmpeg", "failure"),
        ("ffmpeg", "empty"),
        ("ffprobe", "failure"),
        ("ffprobe", "empty"),
    ),
)
def test_runtime_verifier_fails_closed_on_inventory_failure_or_empty_output(
    tmp_path: Path,
    failed_command: str,
    mode: str,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "dpkg-query").write_text(
        "#!/bin/sh\n"
        "if [ \"$2\" = \"libssh-4\" ] || [ \"$2\" = \"librist4\" ] || "
        "[ \"$2\" = \"libcjson1\" ]; then exit 1; fi\n"
        f"printf '%s\\n' '{H10_VERSION}'\n"
    )
    for command, valid_output in (
        ("ffmpeg", "Demuxers:\\n D  mov             QuickTime / MOV\\n"),
        ("ffprobe", "File formats:\\n DE mov             QuickTime / MOV\\n"),
    ):
        if command == failed_command and mode == "failure":
            body = "#!/bin/sh\nexit 23\n"
        elif command == failed_command:
            body = "#!/bin/sh\nexit 0\n"
        else:
            body = f"#!/bin/sh\nprintf '%s' '{valid_output}'\n"
        (fake_bin / command).write_text(body)
    for executable in fake_bin.iterdir():
        executable.chmod(0o755)

    result = subprocess.run(
        ["/bin/sh", str(VERIFY_SCRIPT)],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin"},
        check=False,
    )

    assert result.returncode != 0
    assert "inventory" in result.stderr.lower()


def test_backend_and_renderer_install_the_same_h10_packages() -> None:
    for dockerfile_path in (BACKEND_DOCKERFILE, RENDERING_DOCKERFILE):
        source = dockerfile_path.read_text()

        assert "AS ffmpeg-h10-build" in source
        assert ORIGINAL_SOURCE_SHA256 in source
        assert DEBIAN_SOURCE_SHA256 in source
        assert "install-h10-build-deps.sh" in source
        assert "build-h10-debs.sh" in source
        assert "86708357d126af84c16f80d9c57335d1e8c845c5.patch" in source
        assert "02fc47e13f903768b75f7985a2706a6223ab4506.patch" in source
        assert "16b2049d4d5222db6cd7c031409058571c94f6a9.patch" in source
        assert "9d786e4b5e9b8482651928574de33772aeee7be1.patch" in source
        assert "1c10bcc2e17255dacb717a25ab3db142ce390602.patch" in source
        assert "1cdeb3c4e7f1f8566d846b9b451e01c376398818.patch" in source
        assert (
            "65b0dab903e5975e036b30ecc58f5935d4f151e0-debian-7.1.5-backport.patch"
            in source
        )
        assert "COPY --from=ffmpeg-h10-build /ffmpeg-debs /tmp/ffmpeg-debs" in source
        assert "verify-h10-runtime.sh" in source
        assert "rm -rf /tmp/ffmpeg-debs" in source


def test_backend_runtime_upgrades_fixable_system_packages_fail_closed() -> None:
    source = BACKEND_DOCKERFILE.read_text()
    runtime = source.split("FROM ${PYTHON_IMAGE}", 2)[2]
    required_packages = {
        "bsdutils",
        "libblkid1",
        "liblastlog2-2",
        "libmount1",
        "libsmartcols1",
        "libssl3t64",
        "libuuid1",
        "login",
        "mount",
        "openssl",
        "openssl-provider-legacy",
        "util-linux",
    }

    assert "apt-get install -y --no-install-recommends --only-upgrade" in runtime
    assert "apt-get upgrade" not in runtime
    for package in required_packages:
        assert f"      {package} \\\n" in runtime
    source_minimums = {
        "bsdutils": ("util-linux", "2.41.5-0+deb13u1"),
        "libblkid1": ("util-linux", "2.41.5-0+deb13u1"),
        "liblastlog2-2": ("util-linux", "2.41.5-0+deb13u1"),
        "libmount1": ("util-linux", "2.41.5-0+deb13u1"),
        "libsmartcols1": ("util-linux", "2.41.5-0+deb13u1"),
        "libuuid1": ("util-linux", "2.41.5-0+deb13u1"),
        "login": ("util-linux", "2.41.5-0+deb13u1"),
        "mount": ("util-linux", "2.41.5-0+deb13u1"),
        "util-linux": ("util-linux", "2.41.5-0+deb13u1"),
        "libssl3t64": ("openssl", "3.5.7-1~deb13u2"),
        "openssl": ("openssl", "3.5.7-1~deb13u2"),
        "openssl-provider-legacy": ("openssl", "3.5.7-1~deb13u2"),
    }
    assert "${source:Package}" in runtime
    assert "${source:Version}" in runtime
    assert "dpkg --compare-versions" in runtime
    for package, (source_package, minimum) in source_minimums.items():
        assert (
            f"check_min_source_version {package} {source_package} '{minimum}'"
            in runtime
        )
    verifier_call = "&& /usr/local/bin/verify-h10-runtime.sh"
    assert runtime.index("--only-upgrade") < runtime.index(verifier_call)
    assert runtime.rindex("check_min_source_version") < runtime.index(verifier_call)


def test_frontend_runtime_requires_fixed_openssl_packages() -> None:
    source = FRONTEND_DOCKERFILE.read_text()
    runtime = source.split("FROM ${NODE_IMAGE} AS runner", 1)[1]

    assert "apk add --no-cache" in runtime
    assert "'libcrypto3>=3.5.8-r0'" in runtime
    assert "'libssl3>=3.5.8-r0'" in runtime
    assert runtime.index("apk add --no-cache") < runtime.index("USER 1000:1000")


def test_supported_backend_upload_bundle_includes_h10_build_inputs() -> None:
    source = CLOUDBASE_DEPLOY_GUIDE.read_text()
    upload_command = next(
        line for line in source.splitlines() if line.startswith("zip -r deploy.zip ")
    )

    assert " docker/ " in upload_command
    assert "`docker/ffmpeg/` H10 构建输入" in source
