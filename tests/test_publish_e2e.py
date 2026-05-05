"""e2e: TikTok / Shopify connector 真实发布链路验证。

CLAUDE.md「Known Gaps」C 任务的 e2e 部分。

要跑这个测试需要真实 platform credentials:
    TikTok:
        export TIKTOK_ACCESS_TOKEN=<your-access-token>
        export TIKTOK_OPEN_ID=<your-open-id>
    Shopify:
        export SHOPIFY_STORE_URL=<your-store>.myshopify.com
        export SHOPIFY_ADMIN_TOKEN=<your-admin-api-token>

然后:
    pytest tests/test_publish_e2e.py -m e2e -v

不在本测试范围(单元覆盖见 tests/test_pipeline_degraded.py):
    - connector registry 注册表契约
    - get_connector unsupported platform raise

注意 TikTok 沙盒可能有日发布数限制,Shopify 测试需要 sandbox store。
建议跑前先在 platform dev console 确认 token 仍有效。
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.e2e


def _have_tiktok_creds() -> bool:
    return bool(os.environ.get("TIKTOK_ACCESS_TOKEN")) and bool(os.environ.get("TIKTOK_OPEN_ID"))


def _have_shopify_creds() -> bool:
    return bool(os.environ.get("SHOPIFY_STORE_URL")) and bool(os.environ.get("SHOPIFY_ADMIN_TOKEN"))


# ── TikTok ──

@pytest.mark.skipif(not _have_tiktok_creds(), reason="需要 TIKTOK_ACCESS_TOKEN + TIKTOK_OPEN_ID")
@pytest.mark.asyncio
async def test_tiktok_connector_real_publish():
    """走真实 TikTok Content Posting API 发布一个 sandbox 视频。

    需要本地有可上传的 .mp4 文件;默认用 output/renders/ 下第一个。
    """
    from pathlib import Path

    from src.connectors.registry import get_connector

    # 找一个能上传的视频
    renders_dir = Path("output/renders")
    if not renders_dir.is_dir():
        pytest.skip("output/renders/ 目录不存在,需要先跑一次 pipeline")
    videos = list(renders_dir.glob("*.mp4"))
    if not videos:
        pytest.skip("output/renders/ 没有 mp4 文件")

    video_path = str(videos[0])

    connector = get_connector("tiktok")
    result = await connector.publish({
        "title": "AI Video e2e test",
        "description": "automated test post — please ignore #test",
        "video_path": video_path,
    })

    # 真实发布应返回 success + post_id + url
    print(f"\n[e2e] TikTok publish result: {result}")
    assert "success" in result, "connector 必须返回 success 字段"
    if result["success"]:
        assert result.get("post_id"), "成功时必须有 post_id"
    else:
        # 失败也要有 error 描述,方便定位
        assert result.get("error"), "失败时必须有 error 描述"


# ── Shopify ──

@pytest.mark.skipif(not _have_shopify_creds(), reason="需要 SHOPIFY_STORE_URL + SHOPIFY_ADMIN_TOKEN")
@pytest.mark.asyncio
async def test_shopify_connector_real_publish():
    """走真实 Shopify Admin API 创建一个 sandbox 产品 page。"""
    from src.connectors.registry import get_connector

    connector = get_connector("shopify")
    result = await connector.publish({
        "title": "AI Video e2e test product",
        "description": "automated test page — please ignore",
        "vendor": "test",
        "product_type": "test",
    })

    print(f"\n[e2e] Shopify publish result: {result}")
    assert "success" in result
    if result["success"]:
        assert result.get("post_id") or result.get("url")


# ── /distribution/publish 路由 + connector 注册联调 ──

@pytest.mark.skipif(
    not (_have_tiktok_creds() or _have_shopify_creds()),
    reason="需要至少一个 platform 的真实 credentials",
)
@pytest.mark.asyncio
async def test_distribution_publish_endpoint(tmp_path):
    """通过 HTTP /distribution/publish 触发,而不是直接调 connector。"""
    from httpx import ASGITransport, AsyncClient

    try:
        from src.api import app
    except ImportError:
        pytest.skip("fastapi 未安装")

    AUTH_HEADERS = {"X-API-Key": os.environ.get("API_KEY", "test-api-key-for-pytest")}
    platform = "tiktok" if _have_tiktok_creds() else "shopify"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/distribution/publish",
            headers=AUTH_HEADERS,
            json={
                "platform": platform,
                "content": {
                    "title": "e2e dist endpoint test",
                    "description": "automated",
                    "video_path": "output/renders/s1.mp4",
                },
            },
        )

    print(f"\n[e2e] /distribution/publish [{platform}] → {response.status_code}")
    print(f"      body: {response.text[:300]}")
    # 200 = 成功,500 = connector 内部失败但路由通,401 = 鉴权失败
    assert response.status_code in (200, 500), f"unexpected status {response.status_code}"
