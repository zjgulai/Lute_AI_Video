"""Static guards for the Lighthouse apex landing page sidecars."""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
LANDING_DIR = REPO_ROOT / "deploy" / "lighthouse" / "landing"
RSYNC_EXCLUDES = REPO_ROOT / "deploy" / "lighthouse" / "rsync-excludes.txt"
SIDECAR_SYNC = REPO_ROOT / "deploy" / "lighthouse" / "sync-landing-sidecars.sh"
SIDECAR_REMOTE_HELPER = REPO_ROOT / "deploy" / "lighthouse" / "systems-sidecar-remote.py"
NGINX_CONF = REPO_ROOT / "deploy" / "lighthouse" / "nginx.conf"
DOCKER_COMPOSE = REPO_ROOT / "deploy" / "lighthouse" / "docker-compose.prod.yml"

AUTH_VERSION = "20260606-auth-mail"
APEX_HOST = "lute-tlz-dddd.top"
LIGHTHOUSE_ROUTED_SYSTEM_HOSTS = {
    "video",
    "voc",
    "report",
    "shopify",
    "mkt",
    "brand",
    "mas",
    "business",
    "product",
    "kg",
    "person",
    "llm",
}
EXPECTED_SYSTEM_CARDS = {
    "video.lute-tlz-dddd.top": ("AI 原生视频系统", "creation"),
    "redbook.lute-tlz-dddd.top": ("AI 效能公式链", "creation"),
    "voc.lute-tlz-dddd.top": ("客户声音分析平台", "insight"),
    "ana.lute-tlz-dddd.top": ("财经经营洞察", "insight"),
    "asset.lute-tlz-dddd.top": ("品牌资产智能中台", "growth"),
    "bos.lute-tlz-dddd.top": ("品牌经营操作系统", "growth"),
    "report.lute-tlz-dddd.top": ("E2E 洞察报告", "insight"),
    "shopify.lute-tlz-dddd.top": ("独立站监控", "growth"),
    "platform.shopify.lute-tlz-dddd.top": ("Shopify AI 经营知识库", "growth"),
    "mkt.lute-tlz-dddd.top": ("市场洞察工作台", "insight"),
    "brand.lute-tlz-dddd.top": ("品牌战略引擎", "growth"),
    "mas.lute-tlz-dddd.top": ("科学经营决策系统", "growth"),
    "business.lute-tlz-dddd.top": ("商业机会点", "growth"),
    "product.lute-tlz-dddd.top": ("AI 选品平台", "growth"),
    "kg.lute-tlz-dddd.top": ("AI 知识图谱", "ai"),
    "kgraph.lute-tlz-dddd.top": ("DocCanvas 工作台", "ai"),
    "person.lute-tlz-dddd.top": ("数字员工", "ai"),
    "llm.lute-tlz-dddd.top": ("大模型选型", "ai"),
    "xmind.lute-tlz-dddd.top": ("前车之鉴 · 思维模型工作台", "ai"),
    "scrapy.lute-tlz-dddd.top": ("数据采集平台", "operations"),
    "melwater.lute-tlz-dddd.top": ("Melwater 分析", "insight"),
    "reddit.lute-tlz-dddd.top": ("Reddit 舆情工作台", "insight"),
    "plugin.lute-tlz-dddd.top": ("插件中心", "ai"),
    "flowise.lute-tlz-dddd.top": ("AI 流程编排平台", "ai"),
    "label.lute-tlz-dddd.top": ("VOC 标签工作台", "insight"),
    "scm.lute-tlz-dddd.top": ("供应链治理", "operations"),
    "audit.lute-tlz-dddd.top": ("AI 审计一体化协作平台", "operations"),
    "present.lute-tlz-dddd.top": ("发布资产工厂", "creation"),
    "wct.lute-tlz-dddd.top": ("微信公众号文章批量下载", "creation"),
    "kb.lute-tlz-dddd.top": ("经营咨询工作台", "ai"),
    "skills.lute-tlz-dddd.top": ("AI 技能库", "creation"),
}
EXPECTED_G3_LOOP_BADGES = {
    "redbook.lute-tlz-dddd.top": {
        "enterprise": "E5 资产内容",
        "launch": "L4 内容生产",
    },
    "kgraph.lute-tlz-dddd.top": {
        "enterprise": "E8 AI 沉淀",
        "launch": "L7 AI 加速",
    },
    "xmind.lute-tlz-dddd.top": {
        "enterprise": "E4 战略中枢",
        "launch": "L7 AI 加速",
    },
}
STATIC_SITE_MOUNTS = {
    "mkt": ("/opt/mkt53/html", "/var/www/mkt53"),
    "shopify": ("/opt/momcozy-audit/html", "/var/www/momcozy-audit"),
    "report": ("/opt/voc-report/html", "/var/www/voc-report"),
    "business": ("/opt/business-insight-hub/html", "/var/www/business-insight-hub"),
    "product": ("/opt/ai-product-select/html", "/var/www/ai-product-select"),
    "person": ("/opt/ai-employ-platform/html", "/var/www/ai-employ-platform"),
    "llm": ("/opt/llm-compare-hub/html", "/var/www/llm-compare-hub"),
}

LANDING_SIDECARS = {
    "login.html",
    "register.html",
    "systems.html",
    "lute-auth.css",
    "lute-auth.js",
}

TRACKED_RELEASE_SIDECARS = {
    f"deploy/lighthouse/landing/{filename}" for filename in LANDING_SIDECARS
}
REMOTE_ONLY_EXCLUDES = {"deploy/lighthouse/landing/lute-*.html"}


def _attribute_urls(text: str) -> list[str]:
    return re.findall(r"""(?:href|src)=["']([^"']+)["']""", text)


class _SystemsPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[tuple[str, str, str, str, frozenset[str], str]] = []
        self.footer_hosts: list[str] = []
        self.footer_hrefs: list[str] = []
        self.category_filters: list[str] = []
        self.loop_views: list[str] = []
        self.filter_count_controls: dict[str, int] = {}
        self.empty_state_attrs: dict[str, str] | None = None
        self.has_grid = False
        self.has_search = False
        self.has_loop_summary = False
        self.has_loop_stages = False
        self._card: dict[str, object] | None = None
        self._in_card_title = False
        self._in_footer = False
        self._active_filter: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value or "" for name, value in attrs}
        classes = set(attributes.get("class", "").split())

        if "data-filter" in attributes:
            filter_name = attributes["data-filter"]
            self.category_filters.append(filter_name)
            self.filter_count_controls.setdefault(filter_name, 0)
            if tag == "button":
                self._active_filter = filter_name
        if "data-loop" in attributes:
            self.loop_views.append(attributes["data-loop"])
        if "category-count" in classes and self._active_filter is not None:
            self.filter_count_controls[self._active_filter] += 1
        if "grid" in classes:
            self.has_grid = True
        if "data-system-search" in attributes:
            self.has_search = True
        if "data-empty-state" in attributes:
            self.empty_state_attrs = attributes
        if "data-loop-summary" in attributes:
            self.has_loop_summary = True
        if "data-loop-stages" in attributes:
            self.has_loop_stages = True

        if tag == "p" and "footer" in classes:
            self._in_footer = True
        elif tag == "a" and self._in_footer:
            href = attributes.get("href", "")
            host = urlparse(href).hostname
            if host:
                self.footer_hosts.append(host)
                self.footer_hrefs.append(href)

        if tag == "a" and "card" in classes:
            assert self._card is None, "system cards must not be nested"
            href = attributes.get("href", "")
            self._card = {
                "href": href,
                "host": urlparse(href).hostname or "",
                "category": attributes.get("data-category", ""),
                "classes": classes,
                "title": [],
                "text": [],
            }
        elif self._card is not None:
            card_classes = self._card["classes"]
            assert isinstance(card_classes, set)
            card_classes.update(classes)

        if self._card is not None and tag == "h2" and "card-title" in classes:
            self._in_card_title = True

    def handle_data(self, data: str) -> None:
        if self._card is None:
            return
        text_parts = self._card["text"]
        assert isinstance(text_parts, list)
        text_parts.append(data)
        if self._in_card_title:
            title_parts = self._card["title"]
            assert isinstance(title_parts, list)
            title_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2":
            self._in_card_title = False
        elif tag == "a" and self._card is not None:
            href = self._card["href"]
            host = self._card["host"]
            category = self._card["category"]
            classes = self._card["classes"]
            title_parts = self._card["title"]
            text_parts = self._card["text"]
            assert isinstance(href, str) and isinstance(host, str) and isinstance(category, str)
            assert isinstance(classes, set) and isinstance(title_parts, list) and isinstance(text_parts, list)
            title = " ".join("".join(title_parts).split())
            text = " ".join("".join(text_parts).split())
            self.cards.append((href, host, title, category, frozenset(classes), text))
            self._card = None
        elif tag == "button" and self._active_filter is not None:
            self._active_filter = None
        elif tag == "p" and self._in_footer:
            self._in_footer = False


def _parse_systems_page(text: str) -> _SystemsPageParser:
    parser = _SystemsPageParser()
    parser.feed(text)
    parser.close()
    assert parser._card is None, "unterminated system card"
    return parser


def _loop_metadata_hosts(text: str) -> set[str]:
    metadata_match = re.search(
        r"const loopMetadata = \{(?P<body>.*?)^\s*\};",
        text,
        re.DOTALL | re.MULTILINE,
    )
    assert metadata_match is not None
    return set(re.findall(r'^\s+"([^"/]+\.lute-tlz-dddd\.top)"\s*:', metadata_match.group("body"), re.MULTILINE))


SYSTEMS_DOM_HARNESS = REPO_ROOT / "tests" / "fixtures" / "lighthouse_systems_dom_harness.cjs"


def _run_systems_dom_contract(text: str, page: _SystemsPageParser) -> dict[str, Any]:
    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", text, re.DOTALL)
    scripts = [script for script in scripts if script.strip()]
    assert len(scripts) == 1
    assert page.empty_state_attrs is not None
    payload = {
        "script": scripts[0],
        "cards": [
            {"href": href, "category": category, "text": card_text}
            for href, _host, _title, category, _classes, card_text in page.cards
        ],
        "filters": page.category_filters,
        "filterCountControls": page.filter_count_controls,
        "loops": page.loop_views,
        "emptyState": page.empty_state_attrs,
    }
    result = subprocess.run(
        ["node", str(SYSTEMS_DOM_HARNESS)],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    decoded = json.loads(result.stdout)
    assert isinstance(decoded, dict), "DOM harness must return a JSON object"
    return decoded


def _local_landing_file_from_url(raw_url: str) -> Path | None:
    parsed = urlparse(raw_url)
    if parsed.scheme and parsed.netloc != APEX_HOST:
        return None

    path = unquote(parsed.path.lstrip("/"))
    if path in LANDING_SIDECARS:
        return LANDING_DIR / path
    return None


def _next_landing_file_from_url(raw_url: str) -> Path | None:
    parsed = urlparse(raw_url)
    next_values = parse_qs(parsed.query).get("next", [])
    if not next_values:
        return None

    next_path = next_values[0].lstrip("/")
    if next_path in LANDING_SIDECARS:
        return LANDING_DIR / next_path
    return None


def test_lighthouse_landing_entrypoint_references_existing_sidecars():
    required_files = {"index.html"} | LANDING_SIDECARS
    missing = sorted(
        filename for filename in required_files if not (LANDING_DIR / filename).exists()
    )
    assert not missing, f"landing sidecar files are missing: {missing}"

    for filename in required_files:
        text = (LANDING_DIR / filename).read_text()
        missing_refs = []
        for raw_url in _attribute_urls(text):
            for candidate in (
                _local_landing_file_from_url(raw_url),
                _next_landing_file_from_url(raw_url),
            ):
                if candidate is not None and not candidate.exists():
                    missing_refs.append(f"{filename} -> {raw_url}")
        assert not missing_refs, "landing page references missing local sidecars: " + ", ".join(
            sorted(missing_refs)
        )


def test_lighthouse_cover_enters_the_systems_directory_after_login():
    index_html = (LANDING_DIR / "index.html").read_text()
    systems_html = (LANDING_DIR / "systems.html").read_text()

    assert "next=/systems.html" in index_html
    assert "路特数据科学平台" in systems_html

    page = _parse_systems_page(systems_html)
    cards = page.cards
    card_hosts = [host for _href, host, _title, _category, _classes, _text in cards]
    card_hrefs = [href for href, _host, _title, _category, _classes, _text in cards]
    actual = {
        host: (title, category)
        for _href, host, title, category, _classes, _text in cards
    }

    assert len(cards) == len(EXPECTED_SYSTEM_CARDS)
    assert len(card_hosts) == len(set(card_hosts)), "systems directory has duplicate hosts"
    assert actual == EXPECTED_SYSTEM_CARDS
    assert Counter(category for _href, _host, _title, category, _classes, _text in cards) == Counter(
        category for _title, category in EXPECTED_SYSTEM_CARDS.values()
    )
    assert card_hrefs == [f"https://{host}" for host in card_hosts]
    footer_hosts = page.footer_hosts
    assert len(footer_hosts) == len(set(footer_hosts)), "footer has duplicate hosts"
    assert set(footer_hosts) == set(card_hosts)
    assert len(page.footer_hrefs) == len(set(page.footer_hrefs))
    assert set(page.footer_hrefs) == set(card_hrefs)

    required_classes = {"card-subtitle", "card-title", "card-desc", "card-desc-en", "status", "card-cta"}
    for _href, host, _title, _category, classes, _text in cards:
        assert required_classes <= classes, f"card content contract incomplete: {host}"

    assert "reddit.brand.lute-tlz-dddd.top" not in systems_html
    assert "distill.lute-tlz-dddd.top" not in systems_html


def test_lighthouse_system_card_parser_ignores_attribute_order():
    sample = (
        '<a data-category="ai" href="https://extra.lute-tlz-dddd.top" class="special card">'
        '<h2 class="card-title">Extra</h2></a>'
    )
    assert _parse_systems_page(sample).cards[0][:4] == (
        "https://extra.lute-tlz-dddd.top",
        "extra.lute-tlz-dddd.top",
        "Extra",
        "ai",
    )


def test_lighthouse_system_directory_loop_and_search_contract():
    systems_html = (LANDING_DIR / "systems.html").read_text()
    page = _parse_systems_page(systems_html)
    card_hosts = set(EXPECTED_SYSTEM_CARDS)
    metadata_hosts = _loop_metadata_hosts(systems_html)

    assert metadata_hosts == card_hosts
    assert page.category_filters == ["all", "creation", "insight", "growth", "operations", "ai"]
    assert page.loop_views == ["functional", "enterprise", "launch"]
    assert page.filter_count_controls == dict.fromkeys(page.category_filters, 1)
    assert page.has_grid and page.has_search and page.has_loop_summary and page.has_loop_stages

    result = _run_systems_dom_contract(systems_html, page)
    expected_hosts = sorted(EXPECTED_SYSTEM_CARDS)
    expected_counts = {"all": 31, "creation": 5, "insight": 7, "growth": 8, "operations": 3, "ai": 8}
    initial = result["initial"]
    assert initial["visibleHosts"] == expected_hosts
    assert initial["categoryCounts"] == expected_counts
    assert result["categoryVisible"] == expected_counts
    assert "31 个产品入口" in initial["summary"]
    assert all(badge["hidden"] for badge in initial["badges"].values())

    for view_name, first_stage, last_stage in [("enterprise", "E1", "E8"), ("launch", "L1", "L7")]:
        view = result[view_name]
        assert view["visibleHosts"] == expected_hosts
        assert view["pendingHosts"] == []
        assert first_stage in view["stageMarkup"] and last_stage in view["stageMarkup"]
        for host, badge in view["badges"].items():
            assert badge["ariaHidden"] is None
            assert not badge["hidden"] and badge["text"]

        for host, expected_badges in EXPECTED_G3_LOOP_BADGES.items():
            assert view["badges"][host]["text"] == expected_badges[view_name]
            assert "闭环阶段待产品负责人确认" not in view["badges"][host]["ariaLabel"]

    assert result["enterprise"]["badges"]["reddit.lute-tlz-dddd.top"]["text"] == "E1 外部感知"
    assert result["launch"]["badges"]["reddit.lute-tlz-dddd.top"]["text"] == "L1 趋势机会"
    assert result["searchPending"]["visibleHosts"] == []
    assert result["searchXmind"]["visibleHosts"] == ["xmind.lute-tlz-dddd.top"]
    assert result["searchXmind"]["emptyState"]["hidden"]

    missing = result["searchMissing"]
    assert missing["visibleHosts"] == []
    assert not missing["emptyState"]["hidden"]
    assert missing["emptyState"]["role"] == "status"
    assert missing["emptyState"]["ariaLive"] == "polite"
    assert "definitely-no-product" in missing["emptyState"]["text"]
    assert result["searchCleared"]["visibleHosts"] == expected_hosts
    assert result["searchCleared"]["emptyState"]["hidden"]


def test_lighthouse_system_domains_are_routed_before_default_ai_video_fallback():
    nginx_conf = NGINX_CONF.read_text()
    compose = DOCKER_COMPOSE.read_text()

    for host in LIGHTHOUSE_ROUTED_SYSTEM_HOSTS:
        assert f"{host}.{APEX_HOST}" in nginx_conf

    for host, (source, target) in STATIC_SITE_MOUNTS.items():
        assert f"server_name {host}.{APEX_HOST};" in nginx_conf
        assert f"root {target};" in nginx_conf
        assert f"{source}:{target}:ro" in compose

    assert f"server_name brand.{APEX_HOST} mas.{APEX_HOST};" in nginx_conf
    assert f"server_name kg.{APEX_HOST};" in nginx_conf
    assert "server promptforge_app:3000;" in nginx_conf


def test_lighthouse_auth_assets_use_one_cache_bust_version():
    auth_js = (LANDING_DIR / "lute-auth.js").read_text()
    assert f'const APP_VERSION = "{AUTH_VERSION}"' in auth_js

    for filename in ["index.html", "login.html", "register.html", "systems.html"]:
        text = (LANDING_DIR / filename).read_text()
        if "lute-auth.css" in text:
            assert f"lute-auth.css?v={AUTH_VERSION}" in text
        if "lute-auth.js" in text:
            assert f"lute-auth.js?v={AUTH_VERSION}" in text


def test_lighthouse_auth_script_uses_publishable_supabase_key_only():
    auth_js = (LANDING_DIR / "lute-auth.js").read_text()
    lower = auth_js.lower()

    assert "sb_publishable_" in auth_js
    for forbidden in ["service_role", "sb_secret_", "supabase_service"]:
        assert forbidden not in lower


def test_lighthouse_landing_sidecar_release_and_shared_root_boundaries():
    excludes = {
        line.strip()
        for line in RSYNC_EXCLUDES.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }

    missing = sorted(REMOTE_ONLY_EXCLUDES - excludes)
    assert not missing, f"remote-only landing sidecar excludes missing: {missing}"
    assert not (TRACKED_RELEASE_SIDECARS & excludes)


def test_lighthouse_landing_sidecar_sync_is_manual_dry_run_by_default():
    script = SIDECAR_SYNC.read_text()
    helper = SIDECAR_REMOTE_HELPER.read_text()

    subprocess.run(["bash", "-n", str(SIDECAR_SYNC)], check=True)

    assert 'DRY_RUN="${DRY_RUN:-1}"' in script
    assert 'ACTION="${ACTION:-sync}"' in script
    assert 'SYNC_SCOPE="${SYNC_SCOPE:-systems-only}"' in script
    assert "REMOTE_LANDING_DIR=\"$REMOTE_DIR/deploy/lighthouse/landing\"" in script
    assert "BASELINE_SYSTEMS_SHA256" in script
    assert "CANDIDATE_SYSTEMS_SHA256" in script
    assert "CONFIRM_SYSTEMS_LIVE" in script
    assert "StrictHostKeyChecking=yes" in script
    assert "SSH_KNOWN_HOSTS_FILE" in script
    assert "StrictHostKeyChecking=accept-new" not in script
    assert "--delete" not in script
    assert "RUN_TOKEN_SMOKE" not in script
    assert "deploy.sh" not in script
    assert "docker-compose" not in script
    assert "docker compose" not in script
    assert "systems.html" in script
    assert "os.replace" in helper
    assert "sync-receipt.v1.json" in helper
    assert "rollback-receipt.v1.json" in helper
    assert '"ai_video_nginx", "nginx", "-t"' in helper

    for filename in ["index.html", "login.html", "register.html", "lute-auth.css", "lute-auth.js"]:
        assert filename not in script
