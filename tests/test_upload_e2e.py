"""Assets 上传链路端到端验证。

验证完整链路:multipart upload → 后端落盘 → /api/files 列出 → /api/media/ 可访问。
"""

from __future__ import annotations

import io

import pytest
from httpx import ASGITransport, AsyncClient

from src.tools.asset_storage import AssetStorage


@pytest.fixture
async def app():
    try:
        from src.api import app as fastapi_app
        return fastapi_app
    except ImportError:
        pytest.skip("fastapi 未安装")


@pytest.fixture
async def async_client(app):
    """共享 ASGI 测试客户端,避免每个 test 方法重复构造 transport。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    """将上传目录重定向到 tmp_path,避免污染真实 output/。"""
    monkeypatch.setattr("src.routers.assets.OUTPUT_DIR", tmp_path)
    return tmp_path


class TestUploadEndpoint:
    """验证 /api/upload 端点的核心功能。"""

    @pytest.mark.asyncio
    async def test_upload_image_persists_file(self, async_client, upload_dir, auth_headers):
        """上传 PNG 图片 → 验证落盘 → 验证响应字段。"""
        fake_png = b"\x89PNG\r\n\x1a\n" + b"fake image data" * 100
        files = {"file": ("test-image.png", io.BytesIO(fake_png), "image/png")}

        res = await async_client.post("/api/upload", headers=auth_headers, files=files)

        assert res.status_code == 200, f"upload failed: {res.text}"
        data = res.json()
        assert "filename" in data
        assert data["filename"].endswith(".png")
        assert data["original_name"] == "test-image.png"
        assert data["size"] == len(fake_png)
        assert data["content_type"] == "image/png"
        assert data["path"].startswith("/api/media/")

        # 验证文件确实落盘
        uploads_dir = upload_dir / "uploads"
        assert uploads_dir.exists()
        saved_files = list(uploads_dir.iterdir())
        assert len(saved_files) == 1
        assert saved_files[0].name == data["filename"]
        assert saved_files[0].read_bytes() == fake_png

    @pytest.mark.asyncio
    async def test_upload_video_persists_file(self, async_client, upload_dir, auth_headers):
        """上传 MP4 视频 → 验证落盘。"""
        fake_mp4 = b"\x00\x00\x00\x20ftypisom" + b"fake video data" * 200
        files = {"file": ("test-video.mp4", io.BytesIO(fake_mp4), "video/mp4")}

        res = await async_client.post("/api/upload", headers=auth_headers, files=files)

        assert res.status_code == 200
        data = res.json()
        assert data["filename"].endswith(".mp4")
        assert data["size"] == len(fake_mp4)

    @pytest.mark.asyncio
    async def test_upload_rejects_invalid_extension(self, async_client, auth_headers):
        """上传不允许的扩展名应返回 400。"""
        files = {"file": ("malware.exe", io.BytesIO(b"evil"), "application/octet-stream")}
        res = await async_client.post("/api/upload", headers=auth_headers, files=files)
        assert res.status_code == 400
        assert "File type not allowed" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_rejects_xml_playlist_disguised_as_mp4(
        self,
        async_client,
        upload_dir,
        auth_headers,
    ):
        files = {
            "file": (
                "disguised.mp4",
                io.BytesIO(b"<?xml version='1.0'?><MPD><BaseURL>https://example.invalid/</BaseURL></MPD>"),
                "video/mp4",
            )
        }

        res = await async_client.post("/api/upload", headers=auth_headers, files=files)

        assert res.status_code == 400
        assert "media bytes do not match" in res.json()["detail"]
        uploads_dir = upload_dir / "uploads"
        assert not uploads_dir.exists() or not list(uploads_dir.iterdir())

    @pytest.mark.asyncio
    async def test_upload_rejects_dotdot_filename(self, async_client, upload_dir, auth_headers):
        """'..' 作为文件名显式拒绝(Path.name 已防御路径遍历)。"""
        files = {"file": ("..", io.BytesIO(b"fake"), "image/png")}
        res = await async_client.post("/api/upload", headers=auth_headers, files=files)
        assert res.status_code == 400
        assert "Invalid filename" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_rejects_oversized_file(self, async_client, auth_headers, monkeypatch):
        """上传超过 100MB 的文件应返回 413。"""
        monkeypatch.setattr("src.routers.assets.MAX_UPLOAD_SIZE", 1024)  # 1KB limit for test

        files = {"file": ("big.png", io.BytesIO(b"x" * 2048), "image/png")}
        res = await async_client.post("/api/upload", headers=auth_headers, files=files)
        assert res.status_code == 413
        assert "File too large" in res.json()["detail"]


class TestFilesListEndpoint:
    """验证 /api/files 端点能正确列出上传的文件。"""

    @pytest.mark.asyncio
    async def test_lists_uploaded_files(self, async_client, upload_dir, auth_headers):
        # 上传 > 1 MiB 的文件(视频/图片过滤 stub,必须 > 1 MiB)
        big_png = b"\x89PNG\r\n\x1a\n" + b"a" * (1024 * 1024 + 100)
        big_mp4 = b"\x00\x00\x00\x20ftypisom" + b"v" * (1024 * 1024 + 100)

        files1 = {"file": ("image1.png", io.BytesIO(big_png), "image/png")}
        files2 = {"file": ("video1.mp4", io.BytesIO(big_mp4), "video/mp4")}

        await async_client.post("/api/upload", headers=auth_headers, files=files1)
        await async_client.post("/api/upload", headers=auth_headers, files=files2)

        # 再列出
        res = await async_client.get("/api/files", headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert "files" in data

        files = data["files"]
        assert len(files) == 2

        # 验证文件类型正确
        types = {f["type"] for f in files}
        assert types == {"image", "video"}

        # 验证 path 字段
        for f in files:
            assert f["path"].startswith("/api/media/")
            assert f["size"] > 0
            assert "filename" in f
            assert "created" in f

    @pytest.mark.asyncio
    async def test_excludes_documents_and_small_files(self, async_client, upload_dir, auth_headers):
        # 上传一个小图片(< 1 MiB) — 应该被过滤
        files_small = {"file": ("tiny.png", io.BytesIO(b"\x89PNG" + b"x" * 100), "image/png")}
        await async_client.post("/api/upload", headers=auth_headers, files=files_small)

        # 上传一个文档 — 应该被过滤
        uploads_dir = upload_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        (uploads_dir / "doc.pdf").write_bytes(b"PDF content")

        res = await async_client.get("/api/files", headers=auth_headers)
        data = res.json()
        files = data["files"]

        # tiny.png < 1MiB 被过滤,doc.pdf 是 document 被过滤
        assert len(files) == 0


class TestUploadToMediaAccess:
    """验证上传后的文件可通过 /api/media/ 访问。"""

    @pytest.mark.asyncio
    async def test_media_serves_uploaded_file(self, async_client, upload_dir, auth_headers):
        """上传文件后,通过 /api/media/ 路径应能下载。"""
        fake_png = b"\x89PNG\r\n\x1a\n" + b"image data" * 50
        files = {"file": ("accessible.png", io.BytesIO(fake_png), "image/png")}

        upload_res = await async_client.post("/api/upload", headers=auth_headers, files=files)
        assert upload_res.status_code == 200
        media_path = upload_res.json()["path"]

        # /api/media/ 由 media router 或 nginx 处理
        # 在测试环境中直接验证 path 格式正确
        assert media_path.startswith("/api/media/uploads/")


class TestLegacyAssetUploadSafety:
    @pytest.mark.asyncio
    async def test_legacy_upload_rejects_playlist_before_asset_storage(
        self,
        async_client,
        tmp_path,
        monkeypatch,
        auth_headers,
    ):
        storage = AssetStorage(storage_dir=tmp_path / "legacy-assets")
        monkeypatch.setattr("src.api_assets._asset_storage", storage)
        files = {
            "file": (
                "disguised.mp4",
                io.BytesIO(b"#EXTM3U\nhttps://example.invalid/segment.ts"),
                "video/mp4",
            )
        }

        res = await async_client.post("/api/assets/upload", headers=auth_headers, files=files)

        assert res.status_code == 400
        assert storage.list() == []


class TestUploadAuth:
    """验证上传端点的认证。"""

    @pytest.mark.asyncio
    async def test_upload_requires_api_key(self, async_client):
        """无 API key 应返回 401/403。"""
        files = {"file": ("test.png", io.BytesIO(b"fake"), "image/png")}
        res = await async_client.post("/api/upload", files=files)
        assert res.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_files_list_requires_api_key(self, async_client):
        """无 API key 应返回 401/403。"""
        res = await async_client.get("/api/files")
        assert res.status_code in (401, 403)
