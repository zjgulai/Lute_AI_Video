---
title: 生产部署后回归复盘清单
doc_type: workflow
module: deploy
topic: production-post-deploy-regression-checklist
status: stable
created: 2026-06-07
updated: 2026-06-26
owner: self
source: human+ai
---

# 生产部署后回归复盘清单

## 触发场景

每次完成 Lighthouse `build-and-deploy.sh` 后（`DRY_RUN=0`）的上线闭环。目标是把“部署后立即看得见、可复盘”的验证固定成可复跑清单。

## 范围与目标

1. 服务可达：前端页面、关键 API、数据库持久化和容器状态
2. 风险拦截：鉴权、rate-limit、异常码、日志污染是否异常
3. 可复现证据：把检查结果落到固定产出目录，便于每次上线对比
4. 与 `RUN_TOKEN_SMOKE` 的边界：除非明确启用 token smoke，不在此清单中触发真实 provider 或发布动作

## 最近一次执行记录

2026-06-25 至 2026-06-26 已按本清单完成 Video 2.0 production no-provider deployment baseline 与后续 all-products Lighthouse 部署保护复核：

- production deployment/version-sync SHA：`bad53cdd07ab80f580bceed06e3ee1d9fa7471a9`（PR `#55` merge commit）
- rsync remote-only sidecar protection SHA：`ae094f45d9ea720d15194a4336a4a7ca86347186`（deployed source and pushed to `origin/main`）
- production `/api/health`：`status=ok`，`version=2.0.0`
- GitHub checks：`bad53cdd07ab80f580bceed06e3ee1d9fa7471a9` 上 `CI`、`e2e-ui`、`Deploy to GitHub Pages`、`e2e-prod` 均为 success；`ae094f45d9ea720d15194a4336a4a7ca86347186` 上 `CI` 与 `Deploy to GitHub Pages` 均为 success
- Lighthouse smoke：`RUN_TOKEN_SMOKE=0`，通过；Fast Mode token smoke 跳过
- strict read-only production E2E：`55 passed`
- 只读页面：`/`、`/s1`、`/s2`、`/s3`、`/s4`、`/s5`、`/fast`、`/toolbox`、`/dashboard`、`/library`、`/works`、`/settings` 均返回 `200`
- container status：backend/frontend/rendering/nginx 均 running，restart=0
- refined log gate：provider HTTP、`/api/fast/generate`、`/api/scenario/*` submit 与 5xx 计数均为 `0`
- post-deploy monitor：后续 30 分钟窗口内 `traceback_or_critical_or_5xx_or_429_count=0`，provider/submit/publish/delivery/token write/final_work write 计数均为 `0`
- 证据文件：`tmp/debug/all-products-lighthouse-dry-run-20260625T122802Z.log`、`tmp/debug/all-products-lighthouse-dry-run-20260625T123013Z.log`、`tmp/debug/all-products-lighthouse-deploy-20260625T123349Z.log`、`tmp/debug/video20-production-deploy-summary-20260625T013842Z.json`、`tmp/debug/video20-version-deploy-summary-20260625T021617Z.json`、`tmp/debug/video20-version-deploy-backend-log-20260625T0208Z.log`、`tmp/debug/video20-post-deploy-monitor-summary-20260625T023331Z.json`

边界：该记录只证明 production deployment + no-provider/read-only regression 已通过，不代表 provider full chain、full media/final assembly、publish、delivery acceptance 或 approved brand token write 已执行。

## 依赖与前提

- 服务器已执行 `deploy/lighthouse/build-and-deploy.sh`，并有成功重建容器
- 已准备非 demo 的生产 `API_KEY`（用于可选的 toolbox/API 鉴权路径检查）
- `BASE=https://video.lute-tlz-dddd.top`
- 生产证书可用；或使用 `curl -k` 进行初始核验

> `API_KEY` 若仍为 `ai_video_demo_2026`，回归清单进入“鉴权受限演练模式”，只保留无鉴权与健康检查；不得把结果误标为正式上线闭环通过。

## 一、基线 smoke（必须）

```bash
BASE=https://video.lute-tlz-dddd.top \
API_KEY=<production-api-key> \
./deploy/lighthouse/smoke.sh
```

## 三、关键 API 回归（建议）

### 3.1 无鉴权保护回归

```bash
BASE=https://video.lute-tlz-dddd.top

code=$(curl -sk -o /dev/null -w "%{http_code}" "$BASE/api/health")
echo "/api/health ${code}"
code=$(curl -sk -X POST -H "Content-Type: application/json" \
  -d '{"target_platforms":["tiktok"],"target_languages":["en"]}' \
  -o /dev/null -w "%{http_code}" "$BASE/api/pipeline/start")
echo "/api/pipeline/start $code"
```

### 3.2 鉴权 API（非 demo key 时才执行）

```bash
BASE=https://video.lute-tlz-dddd.top
API_KEY=<production-api-key>

for p in "/api/toolbox/tools" \
         "/api/toolbox/runs?limit=1"; do
  code=$(curl -sk -H "X-API-Key: $API_KEY" -o /dev/null -w "%{http_code}" "$BASE$p")
  echo "$p $code"
done

code=$(curl -sk -H "X-API-Key: $API_KEY" -o /tmp/unused-response -w "%{http_code}" "$BASE/api/toolbox/runs/audit-summaries?limit=1")
echo "/api/toolbox/runs/audit-summaries $code"
rm -f /tmp/unused-response
```

`/api/scenario/{scenario}/state/{label}` 在未携带有效 `label` 时可能返回 `401/404/422`，不计入失败。

> 非 demo 的 `API_KEY` 下，建议再补跑 `GET /api/toolbox/tools`，并校验 `evidence_level == L2-fixture-or-dry-run`。

## 四、容器与 nginx 现场核验（建议）

```bash
ssh -i <SSH_KEY> ubuntu@101.34.52.232 <<'SSH'
cd /opt/ai-video
sudo docker compose -f deploy/lighthouse/docker-compose.prod.yml ps
for c in ai_video_backend ai_video_frontend ai_video_nginx ai_video_rendering ai_video_db; do
  if sudo docker inspect "$c" >/dev/null 2>&1; then
    sudo docker inspect --format='{{.Name}} {{.State.Running}} {{.State.Status}} {{.RestartCount}}' "$c"
  else
    echo "$c MISSING"
  fi
done
sudo docker logs --since 15m ai_video_backend | grep -Ei "error|failed|traceback|429|poyo.*401|poyo.*403" | tail -n 200 || true
sudo docker logs --since 15m ai_video_nginx | grep -Ei "error|upstream|502|503|504|429" | tail -n 200 || true
SSH
```

异常标准：

- `5xx` 或 `429` 在短窗口持续出现且与用户操作无关
- `poyo` 授权错误频发（如 `401/403`）
- 容器持续重启（`RestartCount` 持续增长）

## 五、统一产出模板（建议）

每次回归结束后生成一条 JSON 证据（示例）：

```json
{
  "run_at": "2026-06-07T00:00:00+08:00",
  "base": "https://video.lute-tlz-dddd.top",
  "api_key_mode": "demo|non_demo",
  "smoke_script": "deploy/lighthouse/smoke.sh",
  "smoke_status": "pass",
  "checks": {
    "health": true,
    "post_deploy_playwright": "skipped|pass|fail",
    "toolbox_readonly": "skipped|pass|fail",
    "page_smoke": "pass",
    "container_stability": "pass"
  },
  "notes": "若 api_key_mode=demo，toolbox_readonly 与鉴权接口应记录 skipped 并保留原因"
}
```

保存路径建议：

- `tmp/outputs/production-post-deploy-regression-YYYYMMDD.json`
- 附带 `tmp/outputs/production-smoke-YYYYMMDD.log` 与 `tmp/outputs/production-page-smoke-YYYYMMDD.txt`

## 六、验收结论

只有以下条件同时满足才可将本轮标记为“P2-3 通过”：

1. 页面与 `/api/health` 基线通过
2. 无 key 的鉴权保护通过
3. `RUN_TOKEN_SMOKE=0` 时无真实生成动作（未触发 provider 调用）
4. 两个以上关键容器未出现异常重启趋势
5. 无明显持续性 `5xx/429/poyo auth failure`
6. `tmp/outputs/production-post-deploy-regression-YYYYMMDD.json` 已写入并附带关键日志命中摘要

不满足任一条件时，停止新功能验收与 token-smoke，先修复后重跑。

要求至少通过：

1. `GET /api/health` 返回 `200`
2. `persistence.backend == postgresql`
3. 无 key 的鉴权保护返回 `401`
4. `RUN_TOKEN_SMOKE=0` 时 `POST /api/fast/generate` 保持跳过

将基线输出转存证据：

```bash
BASE=https://video.lute-tlz-dddd.top API_KEY=<production-api-key> \
./deploy/lighthouse/smoke.sh | tee tmp/outputs/production-smoke-$(date +%Y%m%d).log
```

## 二、页面可达性（建议）

以下页面应返回 200/307（重定向视为可达）：

`/`, `/s1`, `/s2`, `/s3`, `/s4`, `/s5`, `/fast`, `/footage`, `/settings`, `/admin/login`, `/brand-packages`, `/influencers`, `/library`

```bash
BASE=https://video.lute-tlz-dddd.top
for p in / /s1 /s2 /s3 /s4 /s5 /fast /footage /settings /admin/login /brand-packages /influencers /library; do
  code=$(curl -sk -o /dev/null -w "%{http_code}" "$BASE$p")
  echo "$p $code"
done | tee tmp/outputs/production-page-smoke-$(date +%Y%m%d).txt
```
