"""Static contract for tenant-bound media access at the Lighthouse edge."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_VIDEO_LOCATIONS = REPO_ROOT / "deploy" / "lighthouse" / "ai_video_locations.conf"
PORTFOLIO_OPS_DOC = REPO_ROOT / "docs" / "workflows" / "portfolio-ops-stable.md"

ACTIVE_MEDIA_HEADING_RE = re.compile(
    r"^###[ \t]+[^\n]*Canonical backend proxy[^\n]*$",
    re.M,
)
HISTORICAL_MEDIA_HEADING_RE = re.compile(
    r"^####[ \t]+Historical / non-canonical（禁止恢复）[ \t]*$",
    re.M,
)
NGINX_FENCE_RE = re.compile(
    r"^```[ \t]*nginx[ \t]*\n(?P<body>.*?)^```[ \t]*$",
    re.M | re.S | re.I,
)
DIRECT_MEDIA_BYPASS_RE = re.compile(
    r"^[ \t]*(?:alias|try_files)\s+",
    re.M | re.I,
)
MEDIA_LOCATION_RE = re.compile(
    r"^[ \t]*location[ \t]+/api/media/[ \t]*\{(?P<body>.*?)^[ \t]*\}",
    re.M | re.S,
)
BACKEND_PROXY_RE = re.compile(
    r"^[ \t]*proxy_pass[ \t]+http://ai_video_backend;[ \t]*$",
    re.M,
)


def test_protected_media_is_not_served_by_direct_alias():
    text = AI_VIDEO_LOCATIONS.read_text()
    media_blocks = re.findall(
        r"location[^\n{]*/api/media/[^\n{]*\{(?P<body>.*?)\n\}",
        text,
        re.S,
    )
    assert len(media_blocks) == 1
    body = media_blocks[0]
    assert "alias /var/www/media/" not in text
    assert "@backend_media" not in text
    assert "alias /var/www/media/" not in body
    assert "proxy_pass http://ai_video_backend" in body
    assert "try_files" not in body


def _assert_portfolio_ops_contract(text: str) -> None:
    active_headings = list(ACTIVE_MEDIA_HEADING_RE.finditer(text))
    assert len(active_headings) == 1, "active canonical media section must exist exactly once"
    active_heading = active_headings[0]

    next_h3 = re.search(r"^###[ \t]+", text[active_heading.end() :], re.M)
    active_end = (
        active_heading.end() + next_h3.start()
        if next_h3 is not None
        else len(text)
    )

    historical_headings = list(HISTORICAL_MEDIA_HEADING_RE.finditer(text))
    assert len(historical_headings) == 1, "historical media section must exist exactly once"
    historical_heading = historical_headings[0]
    assert active_heading.end() < historical_heading.start() < active_end

    active_contract = text[active_heading.end() : historical_heading.start()]
    historical_contract = text[historical_heading.end() : active_end]

    nginx_fences = list(NGINX_FENCE_RE.finditer(active_contract))
    assert len(nginx_fences) == 1, "active media section must have one nginx config block"
    nginx_config = nginx_fences[0].group("body")
    media_locations = list(MEDIA_LOCATION_RE.finditer(nginx_config))
    assert len(media_locations) == 1, "active config must define one /api/media/ location"
    assert BACKEND_PROXY_RE.search(media_locations[0].group("body"))

    assert DIRECT_MEDIA_BYPASS_RE.search(text) is None
    assert "protected runtime media" in active_contract
    assert "GET /api/media/sign" in active_contract
    assert "短期签名 URL" in active_contract
    assert "`brand_assets`" in active_contract
    assert "`demo`" in active_contract

    assert re.search(r"^```[ \t]*nginx\b", historical_contract, re.M | re.I) is None
    assert MEDIA_LOCATION_RE.search(historical_contract) is None
    assert BACKEND_PROXY_RE.search(historical_contract) is None


def test_portfolio_ops_uses_canonical_backend_proxy_for_protected_media():
    _assert_portfolio_ops_contract(PORTFOLIO_OPS_DOC.read_text())


VALID_PORTFOLIO_CONTRACT_SAMPLE = """### Media 访问的 Canonical backend proxy
protected runtime media 必须经过 backend。
```nginx
location /api/media/ {
    proxy_pass http://ai_video_backend;
}
```
1. 请求 `GET /api/media/sign?path=<url-encoded-canonical-path>&purpose=view`。
2. 使用响应中的短期签名 URL。
3. 只有 `brand_assets` 与 `demo` 为 public roots。
#### Historical / non-canonical（禁止恢复）
仅作历史背景，不是可执行运维步骤。
"""


PORTFOLIO_CONTRACT_COUNTEREXAMPLES = (
    pytest.param(
        VALID_PORTFOLIO_CONTRACT_SAMPLE.replace(
            "    proxy_pass http://ai_video_backend;",
            "    alias     /var/www/media/;\n    proxy_pass http://ai_video_backend;",
        ),
        id="whitespace-direct-alias",
    ),
    pytest.param(
        VALID_PORTFOLIO_CONTRACT_SAMPLE.replace(
            "    proxy_pass http://ai_video_backend;",
            "    try_files\t$uri @backend_media;\n    proxy_pass http://ai_video_backend;",
        ),
        id="whitespace-try-files",
    ),
    pytest.param(
        """#### Historical / non-canonical（禁止恢复）
Canonical backend proxy
```nginx
location /api/media/ {
    proxy_pass http://ai_video_backend;
}
```
GET /api/media/sign
brand_assets demo
""",
        id="canonical-strings-only-in-history",
    ),
    pytest.param(
        "Canonical backend proxy\nproxy_pass http://ai_video_backend;\nGET /api/media/sign\n",
        id="three-string-shell",
    ),
    pytest.param(
        VALID_PORTFOLIO_CONTRACT_SAMPLE.replace(
            "仅作历史背景，不是可执行运维步骤。",
            """仅作历史背景，不是可执行运维步骤。
```nginx
location /api/media/ {
    proxy_pass http://ai_video_backend;
}
```""",
        ),
        id="copyable-historical-nginx",
    ),
)


@pytest.mark.parametrize("counterexample", PORTFOLIO_CONTRACT_COUNTEREXAMPLES)
def test_portfolio_ops_contract_rejects_bypass_counterexamples(counterexample: str):
    with pytest.raises(AssertionError):
        _assert_portfolio_ops_contract(counterexample)
