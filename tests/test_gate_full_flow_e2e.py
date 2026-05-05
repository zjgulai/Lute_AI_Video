"""e2e: gate_1/2/3 候选生成全链路验证。

CLAUDE.md「Known Gaps」B 任务的 e2e 部分:
gate_4_final 不依赖 LLM 已经在 tests/test_s1_gate_full_flow.py 覆盖。
gate_1_script / gate_2_keyframe / gate_3_clips 调 SkillRegistry 实际跑
LLM 生成 3 个 standard/creative/conservative variants,需要真实 API key。

要跑这个测试:
    export DEEPSEEK_API_KEY=<your-deepseek-key>      # gate_1_script LLM
    export POYO_API_KEY=<your-poyo-key>              # gate_2_keyframe + gate_3_clips
    pytest tests/test_gate_full_flow_e2e.py -m e2e -v

测试会:
    1. POST /scenario/s1/start (mode=step_by_step) 初始化 S1 label
    2. 推进到 strategy + scripts step(LLM 调用)
    3. POST /scenario/s1/gate/<label>/gate_1_script/generate
    4. 验证返回 3 个 candidates(standard/creative/conservative)
    5. 每个 candidate 有 score 字段(CandidateScorer 评分)
    6. POST /scenario/s1/gate/.../approve 选 1 个 → 后台续跑

不在本测试范围:
    - gate_2 / gate_3 因为它们依赖 gate_1 approve 后续跑,
      需要等 storyboards / keyframe_images 步骤完成,
      工作量过大。先覆盖 gate_1,后续按需扩展。

CI 友好: 默认 skip,无 API key 不跑。需要真实 key + 长时跑通。
"""

from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not (os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("POYO_API_KEY")),
        reason="需要 DEEPSEEK_API_KEY + POYO_API_KEY,跑真实 LLM 生成候选",
    ),
]

AUTH_HEADERS = {"X-API-Key": os.environ.get("API_KEY", "test-api-key-for-pytest")}


@pytest.fixture
async def app():
    try:
        from src.api import app as fastapi_app
        return fastapi_app
    except ImportError:
        pytest.skip("fastapi 未安装")


@pytest.mark.asyncio
async def test_gate_1_script_generates_3_scored_candidates(app):
    """端到端:启动 S1 step-by-step → 跑到 scripts → gate_1_script generate
    → 3 个 candidates with scores。
    """
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=600) as client:
        # 1. 启动 S1 step_by_step
        start = await client.post(
            "/scenario/s1/start",
            headers=AUTH_HEADERS,
            json={
                "product_catalog": {
                    "products": [{
                        "name": "Wearable Breast Pump X1",
                        "usps": [
                            {"priority": "P0", "text": "Hands-free, fits in bra"},
                            {"priority": "P0", "text": "Hospital-grade suction"},
                        ],
                    }]
                },
                "brand_guidelines": {"brand_name": "TestBrand"},
                "target_platforms": ["tiktok"],
                "target_languages": ["en"],
                "video_duration": 30,
                "mode": "step_by_step",
            },
        )
        assert start.status_code == 200, f"start failed: {start.text}"
        label = start.json()["label"]
        print(f"\n[e2e] label={label}")

        # 2. 跑 strategy step
        r = await client.post(
            f"/scenario/s1/step/strategy",
            headers=AUTH_HEADERS,
            json={"label": label},
        )
        assert r.status_code == 200, f"strategy step failed: {r.text}"

        # 3. 跑 scripts step(为 gate_1 准备 input)
        r = await client.post(
            f"/scenario/s1/step/scripts",
            headers=AUTH_HEADERS,
            json={"label": label},
        )
        assert r.status_code == 200, f"scripts step failed: {r.text}"

        # 4. gate_1_script generate 3 候选
        gen = await client.post(
            f"/scenario/s1/gate/{label}/gate_1_script/generate",
            headers=AUTH_HEADERS,
        )
        assert gen.status_code == 200, f"gate generate failed: {gen.text}"

        candidates = gen.json().get("candidates", [])
        print(f"[e2e] gate_1 returned {len(candidates)} candidates")

        # 验证 3 个候选 standard / creative / conservative
        assert len(candidates) == 3, f"应返回 3 个候选,实际 {len(candidates)}"
        variants = {c["variant"] for c in candidates}
        assert variants == {"standard", "creative", "conservative"}, (
            f"variants={variants},缺 standard/creative/conservative"
        )

        # 5. 每个候选有 score(CandidateScorer 评分)
        for c in candidates:
            assert "score" in c, f"candidate {c['id']} 缺 score"
            assert "overall" in c["score"], f"candidate {c['id']} score 缺 overall"
            assert 0 <= c["score"]["overall"] <= 1, "score.overall 应在 [0,1]"

        # 6. approve 选 standard candidate 触发后台续跑
        standard = next(c for c in candidates if c["variant"] == "standard")
        approve = await client.post(
            f"/scenario/s1/gate/{label}/gate_1_script/approve",
            headers=AUTH_HEADERS,
            json={"selected_ids": [standard["id"]]},
        )
        assert approve.status_code == 200, f"approve failed: {approve.text}"
        result = approve.json()
        # backend 应该返回 resuming=True 表示后台开始续跑
        assert result.get("resuming") is True or result.get("approved") is True, (
            f"approve result missing resuming/approved: {result}"
        )

        print(f"[e2e] gate_1 approve result: {result}")


@pytest.mark.asyncio
async def test_gate_regenerate_single_candidate(app):
    """端到端:gate_1 generate 后,regenerate 单个候选,该候选被替换。"""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=600) as client:
        start = await client.post(
            "/scenario/s1/start",
            headers=AUTH_HEADERS,
            json={
                "product_catalog": {"products": [{"name": "Test", "usps": []}]},
                "target_platforms": ["tiktok"],
                "target_languages": ["en"],
                "mode": "step_by_step",
            },
        )
        assert start.status_code == 200
        label = start.json()["label"]

        # 跑到 scripts
        await client.post("/scenario/s1/step/strategy", headers=AUTH_HEADERS, json={"label": label})
        await client.post("/scenario/s1/step/scripts", headers=AUTH_HEADERS, json={"label": label})

        # 第一次 generate
        gen1 = await client.post(
            f"/scenario/s1/gate/{label}/gate_1_script/generate",
            headers=AUTH_HEADERS,
        )
        candidates_1 = gen1.json().get("candidates", [])
        assert len(candidates_1) == 3
        target = next(c for c in candidates_1 if c["variant"] == "creative")
        target_id = target["id"]

        # regenerate 这一个 candidate
        regen = await client.post(
            f"/scenario/s1/gate/{label}/gate_1_script/regenerate/{target_id}",
            headers=AUTH_HEADERS,
        )
        assert regen.status_code == 200, f"regenerate failed: {regen.text}"

        # 重新 fetch state 看 candidate 是否被替换
        state = await client.get(
            f"/scenario/s1/gate/{label}/gate_1_script",
            headers=AUTH_HEADERS,
        )
        new_candidates = state.json().get("candidates", [])
        assert len(new_candidates) == 3
        new_creative = next(c for c in new_candidates if c["variant"] == "creative")
        # data 应该不同(LLM 重生成)
        assert new_creative["data"] != target["data"], "regenerate 应该产出不同 data"

        print(f"\n[e2e] regenerate creative: {target_id} → {new_creative['id']}")
