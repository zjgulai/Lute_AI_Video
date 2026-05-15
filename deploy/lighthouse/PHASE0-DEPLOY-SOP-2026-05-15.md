---
name: phase0-deploy-sop-2026-05-15
description: Phase 0 部署到 lighthouse canary 的逐步 SOP — 包含 4 项必修代码上线 + alembic migration + smoke + 监控 + 回滚指令。所有 production 操作都要求 operator 显式确认。
doc_type: deploy-sop
module: ai-video
topic: phase0-deploy
status: stable
created: 2026-05-15
updated: 2026-05-15
owner: Sisyphus
source: ai
related:
  - file: ../../docs/workflows/2026-05-15-sprint-0-3-review-and-deploy-plan.md
    relation: implements
---

# Phase 0 Deploy SOP — lighthouse canary (2026-05-15)

> **目标**：把 Phase 0 4 个 commit（02b63d8 / 30369b5 / da4acaf / 60698ad）+ 整个 Sprint 0-3 (5905958..fd9b236) 部署到 `https://101.34.52.232`，并完成 alembic migration `2d6b8e9c0f1a → 7a2f4b8c9d12`。
>
> **预计耗时**：30-45 分钟 + 24h canary 监控。
>
> **风险等级**：中。包含 1 个不可逆 SQL migration（forward-compatible，可 downgrade）。
>
> **谁执行**：用户 / DevOps operator。每个生产命令都要求 operator 显式 type 'yes' 确认。

## 前置检查（必做，在 laptop 上）

```bash
# 1. 本地代码就绪
cd /Users/pray/project/hermes_evo/AI_vedio
git status               # working tree clean (or only 4 pre-existing unrelated files)
git log --oneline -1     # 60698ad docs+test(phase0): regression tests + deploy plan + .env.example C2PA keys

# 2. 测试套件 green
source .venv/bin/activate
python3 -m pytest tests/test_phase0_regression.py \
  tests/test_medical_lexicon.py \
  tests/test_sprint3_compliance_resilience.py \
  tests/test_s2_e2e.py \
  tests/test_model_router.py \
  tests/test_model_thresholds.py \
  tests/test_video_continuity_manager.py \
  tests/test_gate_scenario_configs.py \
  tests/test_quality_gate.py \
  tests/test_candidate_scorer_weights.py -q
# Expect: 208 passed

# 3. SSH 私钥准备好
ls ~/Downloads/ai_video.pem  # or wherever yours lives
chmod 600 ~/Downloads/ai_video.pem

# 4. 远端可达
ssh -i ~/Downloads/ai_video.pem ubuntu@101.34.52.232 'echo OK; date'
```

## 步骤 1：备份生产 PG（laptop → server）

```bash
# 在 lighthouse 上执行
ssh -i ~/Downloads/ai_video.pem ubuntu@101.34.52.232 << 'REMOTE'
cd /opt/ai-video
./scripts/backup_production.sh
# 备份会写到 /opt/ai-video/backups/YYYY-MM-DD-HHMMSS/
ls -la backups/ | tail -3
REMOTE
```

✋ **Operator confirm**：备份文件存在 + 大小 > 0。

## 步骤 2：同步代码（laptop → server）

```bash
# 在 laptop 上执行
# 不要用 git pull on server — 服务器上的 .env.prod 是 gitignored 的本地文件，
# git pull 会丢配置。改用 rsync。

cd /Users/pray/project/hermes_evo/AI_vedio

# Sync src/ (Python backend)
rsync -avz --chmod=F644,D755 \
  --exclude='__pycache__' --exclude='*.pyc' \
  -e "ssh -i ~/Downloads/ai_video.pem" \
  ./src/ ubuntu@101.34.52.232:/opt/ai-video/src/

# Sync migrations/ (NEW: 7a2f4b8c9d12)
rsync -avz --chmod=F644,D755 \
  -e "ssh -i ~/Downloads/ai_video.pem" \
  ./migrations/ ubuntu@101.34.52.232:/opt/ai-video/migrations/

# Sync tests/ (so operator can re-run on server if needed)
rsync -avz --chmod=F644,D755 \
  --exclude='__pycache__' --exclude='*.pyc' \
  -e "ssh -i ~/Downloads/ai_video.pem" \
  ./tests/ ubuntu@101.34.52.232:/opt/ai-video/tests/

# Sync scripts/ (NEW: run_alembic_upgrade.sh)
rsync -avz --chmod=F644,D755 \
  -e "ssh -i ~/Downloads/ai_video.pem" \
  ./scripts/ ubuntu@101.34.52.232:/opt/ai-video/scripts/

# Sync deploy/lighthouse/ (this SOP itself + deploy.sh)
rsync -avz --chmod=F644,D755 \
  -e "ssh -i ~/Downloads/ai_video.pem" \
  ./deploy/lighthouse/ ubuntu@101.34.52.232:/opt/ai-video/deploy/lighthouse/

# Sync .env.example (template only, NOT .env.prod)
rsync -avz --chmod=F644 \
  -e "ssh -i ~/Downloads/ai_video.pem" \
  ./.env.example ubuntu@101.34.52.232:/opt/ai-video/.env.example
```

✋ **Operator confirm**：rsync 输出没有 error。

## 步骤 3：在 server 上重建 backend 镜像 + 跑 alembic upgrade

⚠️ **重要**: Phase 0 修改了 `Dockerfile.backend`（加入 `COPY migrations ./migrations`），
因此 backend 镜像**必须重建**才能让 `/app/migrations/` 存在于容器内。
不重建就跑 `run_alembic_upgrade.sh` 会失败，因为它在容器内执行 `cd /app/migrations`。

```bash
ssh -i ~/Downloads/ai_video.pem ubuntu@101.34.52.232
cd /opt/ai-video

# 3a. 把 run_alembic_upgrade.sh 设为可执行（rsync 已经 +x，但保险）
chmod +x scripts/run_alembic_upgrade.sh

# 3b. ★ 重建 backend 镜像（Phase 0 改了 Dockerfile，必须 rebuild）
cd deploy/lighthouse
sudo docker-compose -f docker-compose.prod.yml build backend

# 3c. 重启 backend container (启动新镜像)
sudo docker-compose -f docker-compose.prod.yml up -d --no-deps backend
sleep 10

# 3d. 健康检查
curl -fsS https://101.34.52.232/health | head -5
# Expect: HTTP 200, JSON with status:ok

# 3e. 验证 migrations 在容器内可见
sudo docker-compose -f docker-compose.prod.yml exec backend ls -la /app/migrations/
# Expect: 看到 alembic.ini + alembic/ 子目录

# 3f. 跑 alembic migration（脚本会 PROMPT 确认 SQL）
cd /opt/ai-video
./scripts/run_alembic_upgrade.sh
# 脚本会显示要执行的 SQL，让你 type 'yes' 确认
# Expected SQL:
#   ALTER TABLE pipeline_states
#     ADD COLUMN IF NOT EXISTS schema_version INT,
#     ADD COLUMN IF NOT EXISTS pipeline_degraded BOOLEAN,
#     ADD COLUMN IF NOT EXISTS degraded_reason TEXT,
#     ADD COLUMN IF NOT EXISTS trace_id TEXT,
#     ADD COLUMN IF NOT EXISTS structured_errors JSONB DEFAULT '[]';
```

✋ **Operator confirm**：脚本输出 `Post-migration revision: 7a2f4b8c9d12`。

## 步骤 4：Smoke tests on production

```bash
# 仍在 lighthouse server 上
cd /opt/ai-video

# 4a. PG 状态字段持久化 smoke
sudo docker-compose -f deploy/lighthouse/docker-compose.prod.yml exec backend \
  python3 -c "
import asyncio
from src.pipeline.state_manager import PipelineStateManager
async def smoke():
    mgr = PipelineStateManager()
    state = {
        'label': 'phase0_prod_smoke',
        'scenario': 's1',
        'config': {},
        'steps': {},
        'current_step': 'strategy',
        'mode': 'auto',
        'errors': [],
        'media_synthesis_errors': [],
        'gates': {},
        'schema_version': 1,
        'pipeline_degraded': True,
        'degraded_reason': 'smoke',
        'trace_id': 'phase0prod',
        'structured_errors': [{'kind': 'test'}],
    }
    await mgr.save(state['label'], state)
    loaded = await mgr.load(state['label'])
    assert loaded['schema_version'] == 1, loaded
    assert loaded['pipeline_degraded'] is True, loaded
    assert loaded['trace_id'] == 'phase0prod', loaded
    print('✅ PG round-trip preserves all 5 fields')
asyncio.run(smoke())
"

# 4b. Budget guard smoke (Expert mode exceed → degraded, not 500)
# Use the same API_KEY from .env.prod
API_KEY=$(grep ^API_KEY= deploy/lighthouse/.env.prod | cut -d= -f2)

curl -fsS -X POST https://101.34.52.232/scenario/s5 \
  -H "X-API-Key: $API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"brand_id":"momcozy","product_sku":{"name":"smoke"},"scene_id":"living-room","story_description":"smoke","video_duration":15,"mode":"expert"}' \
  | head -20
# Expect: HTTP 200 with degraded result (if budget exceeded), NOT 500

# 4c. BrandCompliance severity smoke
sudo docker-compose -f deploy/lighthouse/docker-compose.prod.yml exec backend \
  python3 -c "
import asyncio
from src.skills.brand_compliance import BrandComplianceSkill
async def smoke():
    r = await BrandComplianceSkill().execute({
        'scripts': [{'id':'s1','segments':[{'voiceover':'Soft natural lighting with organic cotton.'}]}],
        'brand_guidelines': {'brand_name': 'Brand'},
    })
    status = r.data['reports'][0]['status']
    assert status == 'FLAGGED', f'Expected FLAGGED, got {status}'
    print(f'✅ benign-with-flagged-words script status: {status}')
asyncio.run(smoke())
"
```

✋ **Operator confirm**：3 个 smoke 全部 ✅。

## 步骤 5：24h 监控启动

部署完成后 24h 内重点盯以下指标（参考 deploy plan §五）：

| 指标 | 告警阈值 | 抓什么 |
|---|---|---|
| 空 final_video 比例 | > 5% | silent assemble failure |
| heuristic scoring 比例 | 飙升超 baseline | gpt-4o vision 失效降级 |
| stuck run 比例 | > 2% | 预算异常 / 状态丢失 |

监控命令：

```bash
ssh -i ~/Downloads/ai_video.pem ubuntu@101.34.52.232 << 'REMOTE'
cd /opt/ai-video
# 抓最近 24h 日志
sudo docker-compose -f deploy/lighthouse/docker-compose.prod.yml logs --since 24h backend \
  | grep -E "pipeline_degraded|budget|schema version|heuristic.*True" | tail -50
REMOTE
```

## Phase 0 → Phase 1 升级条件

24h 后，如果以下全 ✅：

- ✅ 0 个 HTTP 500 错误（除了已知 mock-mode 错误）
- ✅ 步骤 4 的 3 个 smoke test 仍 pass（重跑）
- ✅ 监控指标都在阈值内
- ✅ 没有 ImportError / NameError / AttributeError 在日志中

→ 可以进 Phase 1（参考 deploy plan §四 Phase 1 章节）。

## 回滚（如果 Phase 0 出问题）

```bash
ssh -i ~/Downloads/ai_video.pem ubuntu@101.34.52.232
cd /opt/ai-video

# 1. 回滚代码到 Sprint 2 final
sudo git fetch origin
sudo git checkout bb5ea5b   # Sprint 2 最后一个 commit

# 2. 回滚 alembic
./scripts/run_alembic_upgrade.sh --downgrade

# 3. 重启 backend
cd deploy/lighthouse
sudo docker-compose -f docker-compose.prod.yml restart backend

# 4. 验证
curl -fsS https://101.34.52.232/health
```

✋ 回滚后立即开 incident ticket，记录回滚原因 + 截图日志，等 root cause 修复后再次尝试部署。

## 失败模式表

| 症状 | 可能原因 | 立即响应 |
|---|---|---|
| `alembic upgrade` 失败 with "Multiple heads" | 上次部署引入了未合并的 migration | 不要继续，联系上游 DBA |
| Backend 起来后 `/health` 500 | env / cert / 配置文件被改坏 | 看 `docker logs`；如果是 import error 回滚 |
| Smoke 4a 报 KeyError | rsync 没把 alembic migration 同步过去 | 重跑 rsync，再跑 alembic upgrade |
| Smoke 4b 返回 500 | Phase 0 #2 没生效 / step_runner 修改没同步 | 检查 backend container 内 step_runner.py 行 47-50 应该是 check_budget 在 try: 之后 |
| Smoke 4c status='BLOCKED' | Phase 0 #3 没生效 / brand_compliance.py 没同步 | 检查 backend container 内 brand_compliance.py 行 71 应该读 `_medical_lexicon_severity` |

---

*本 SOP 由 Sprint 0-3 部署计划派生。任何步骤失败都不要继续 — 回滚 + 报告。*
