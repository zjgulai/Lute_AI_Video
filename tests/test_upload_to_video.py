"""Test-EF(E): /api/upload 资产上传链路回归测试。

对应 CLAUDE.md「Known Gaps」E 任务的单元测试覆盖。

覆盖:
- _sanitize_filename 函数(纯单元): path traversal 拒绝 / 扩展名白名单 /
  UUID 命名 / 空文件名兜底
- /api/upload 集成测试(ASGI client): 合法上传成功 / 非法扩展名 400 /
  路径遍历名 400 / 超大文件 413 / 缺 X-API-Key 401

不在本测试范围(留 manual e2e):
- 上传 → 资产引用进 S1 pipeline → 出现在最终视频:依赖真实
  LLM/POYO + 长时跑通,放到 deploy 后 manual 验证。
"""

from __future__ import annotations

import io
import os

import pytest
from fastapi import HTTPException


# ── _sanitize_filename 纯单元 ──

class TestSanitizeFilename:
    def test_normal_filename_returns_uuid_with_ext(self):
        from src.routers.assets import _sanitize_filename

        result = _sanitize_filename("vacation.mp4")
        assert result.endswith(".mp4")
        # UUID hex 是 32 字符 + .mp4 后缀
        assert len(result) == 32 + 4

    def test_empty_filename_returns_default(self):
        from src.routers.assets import _sanitize_filename

        assert _sanitize_filename("") == "upload"
        assert _sanitize_filename(None) == "upload"

    def test_path_traversal_rejected(self):
        """显式带 .. 段的文件名(无路径分隔符)会被 _sanitize_filename 拒。

        注意:`../etc/passwd` 经 Path(...).name 后变成 "passwd",路径前缀
        已经被 stdlib 剥掉。这是 sanitize 的 first line of defense。
        我们这里测的是 Path().name 之后仍含 .. 的情况(`name..` 形式)。
        """
        from src.routers.assets import _sanitize_filename

        with pytest.raises(HTTPException) as exc:
            _sanitize_filename("evil..png")
        assert exc.value.status_code == 400
        assert "Invalid filename" in exc.value.detail

    def test_path_traversal_via_basename_strips_prefix(self):
        """`../etc/passwd` 经 Path(...).name 已被剥成 "passwd",
        然后因为没有合法扩展名触发 File type not allowed。
        这两层防御任意一层挡住即可。"""
        from src.routers.assets import _sanitize_filename

        with pytest.raises(HTTPException) as exc:
            _sanitize_filename("../etc/passwd")
        assert exc.value.status_code == 400
        # 任一错误都说明攻击被挡
        assert exc.value.detail in ("Invalid filename", "File type not allowed")

    def test_path_with_separator_normalized_by_path_name(self):
        """Python stdlib Path("a/b/c.mp4").name → "c.mp4",
        sanitize 依赖这一行为做 first line of defense。
        所以 'evil/../../system32.mp4' 实际等价于 'system32.mp4',
        这是 expected behavior 而非漏洞 — uuid rename 之后下游用不到原名。"""
        from src.routers.assets import _sanitize_filename

        result = _sanitize_filename("evil/../../system32.mp4")
        # Path 已经把它 strip 成 system32.mp4,通过白名单
        assert result.endswith(".mp4")

    def test_null_byte_rejected(self):
        from src.routers.assets import _sanitize_filename

        with pytest.raises(HTTPException):
            _sanitize_filename("evil\x00.mp4")

    def test_disallowed_extension_rejected(self):
        from src.routers.assets import _sanitize_filename

        for bad_ext in ["malware.exe", "shell.sh", "script.py", "noext"]:
            with pytest.raises(HTTPException) as exc:
                _sanitize_filename(bad_ext)
            assert exc.value.status_code == 400
            assert "File type not allowed" in exc.value.detail

    @pytest.mark.parametrize("ext", [
        ".mp4", ".mov", ".webm",
        ".png", ".jpg", ".jpeg", ".webp",
        ".mp3", ".wav", ".m4a",
        ".pdf", ".txt", ".md",
    ])
    def test_allowed_extensions_accepted(self, ext):
        from src.routers.assets import _sanitize_filename

        result = _sanitize_filename(f"upload{ext}")
        assert result.endswith(ext)

    def test_uppercase_extension_normalized_to_lowercase(self):
        """文件扩展名比较是 case-insensitive,SHOULD 通过(.MP4 → .mp4)。"""
        from src.routers.assets import _sanitize_filename

        result = _sanitize_filename("VIDEO.MP4")
        assert result.endswith(".mp4")  # 输出统一小写

    def test_returned_uuid_is_unique(self):
        """每次 sanitize 同一文件名,应该返回不同 UUID。"""
        from src.routers.assets import _sanitize_filename

        a = _sanitize_filename("test.png")
        b = _sanitize_filename("test.png")
        assert a != b


# ── /api/upload 集成测试 ──

@pytest.fixture(scope="module")
def app():
    """加载 FastAPI app(测试模块共享,避免每 test 重建)。"""
    try:
        from src.api import app as fastapi_app
        return fastapi_app
    except ImportError:
        pytest.skip("fastapi not installed", allow_module_level=True)


AUTH_HEADERS = {"X-API-Key": os.environ.get("API_KEY", "test-api-key-for-pytest")}


class TestUploadEndpoint:
    @pytest.mark.asyncio
    async def test_upload_png_succeeds(self, app, tmp_path, monkeypatch):
        """上传一个小 PNG 文件应该返回 200 + 路径信息。"""
        from httpx import ASGITransport, AsyncClient

        # 隔离 OUTPUT_DIR 避免污染真实 output/。
        # 注意:src.routers.assets 顶部 `from src.config import OUTPUT_DIR`
        # 已经把 OUTPUT_DIR 绑定到模块 namespace,所以 monkeypatch src.config 无效,
        # 必须 patch 模块本身的 OUTPUT_DIR。
        from src.routers import assets as assets_mod
        monkeypatch.setattr(assets_mod, "OUTPUT_DIR", tmp_path)

        # 1×1 PNG header(够小,真实文件签名)
        png_bytes = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000d49444154789c63000100000005000100"
            "0d0a2db40000000049454e44ae426082"
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/upload",
                headers=AUTH_HEADERS,
                files={"file": ("tiny.png", io.BytesIO(png_bytes), "image/png")},
            )

        assert response.status_code == 200, f"unexpected status: {response.text}"
        data = response.json()
        assert data["filename"].endswith(".png")
        assert data["original_name"] == "tiny.png"
        assert data["path"].startswith("/api/media/")
        assert data["size"] == len(png_bytes)
        assert data["content_type"] == "image/png"

    @pytest.mark.asyncio
    async def test_upload_exe_rejected(self, app):
        """非允许扩展名(.exe)应该 400。"""
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/upload",
                headers=AUTH_HEADERS,
                files={"file": ("malware.exe", io.BytesIO(b"MZ\x90\x00"), "application/x-dosexec")},
            )
        assert response.status_code == 400
        assert "File type not allowed" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_traversal_filename_rejected(self, app):
        """文件名带 .. 路径遍历应该 400。"""
        from httpx import ASGITransport, AsyncClient

        # FastAPI/python-multipart 通常自动 strip path 前缀;
        # 但显式 .. 段应被服务器侧 _sanitize_filename 拦下。
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/upload",
                headers=AUTH_HEADERS,
                files={"file": ("..hidden.png", io.BytesIO(b"PNG"), "image/png")},
            )
        # 注:Path("..hidden.png").name == "..hidden.png",含 .. 触发 400
        assert response.status_code == 400
        assert "Invalid filename" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_without_api_key_returns_401(self, app):
        """缺 X-API-Key 应该 401(verify_api_key dependency 拦截)。"""
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/upload",
                files={"file": ("a.png", io.BytesIO(b"PNG"), "image/png")},
            )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_upload_oversize_returns_413(self, app, monkeypatch):
        """超过 MAX_UPLOAD_SIZE 应该 413。

        实际跑 100MB 太慢,monkeypatch 把限制改小,上传少量字节触发。
        """
        from httpx import ASGITransport, AsyncClient
        from src.routers import assets as assets_mod

        # 把 100MB 限制调到 100B,触发 413
        monkeypatch.setattr(assets_mod, "MAX_UPLOAD_SIZE", 100)

        big_payload = b"X" * 200  # 200B > 100B 限制
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/upload",
                headers=AUTH_HEADERS,
                files={"file": ("big.png", io.BytesIO(big_payload), "image/png")},
            )
        assert response.status_code == 413
        assert "too large" in response.json()["detail"].lower()
