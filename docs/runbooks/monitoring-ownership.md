---
title: Monitoring Ownership and Alert Validation
doc_type: workflow
module: operations
topic: monitoring-ownership
status: stable
created: 2026-07-22
updated: 2026-07-22
owner: self
source: human+ai
---

# Monitoring Ownership and Alert Validation

## 触发场景

修改 Prometheus exporter、告警 PromQL、Grafana panel、Alertmanager receiver、`/metrics`
访问边界或 monitoring Compose profile 时，必须执行本手册。以下任一情况都视为契约漂移：

- rule/dashboard 引用了 exporter 不存在的 metric、label 或 enum；
- pipeline、HTTP 或 background-task 指标没有真实更新路径；
- public nginx 将匿名 `/metrics` 代理到公网；
- Alertmanager 指向未受仓库配置管理的 receiver；
- Prometheus、Alertmanager 或 Grafana 镜像失去精确 digest pin。

## 影响范围与预期 MTTR

- 影响：告警失效、dashboard 无数据、重复/错误成功计数、匿名指标暴露。
- 本地契约修复目标：10-30 min。
- 真实 firing/resolved drill、生产 reload 或网络策略变更不属于本地修复，必须单独授权。

## 单一事实源

- Metric schema：`configs/prometheus-metrics-contract.yaml`
- Exporter：`src/telemetry_prometheus.py`
- Rules：`deploy/lighthouse/prometheus-alerts.yml`
- Rule fixtures：`tests/fixtures/prometheus-alerts.test.yml`
- Dashboard：`deploy/lighthouse/grafana-dashboard.json`
- Prometheus/Alertmanager/Grafana provisioning：`deploy/lighthouse/monitoring/`
- Internal-only profile：`deploy/lighthouse/docker-compose.monitoring.yml`
- Public boundary：`deploy/lighthouse/ai_video_locations.conf`

Prometheus 只在 `monitoring_internal` 网络直接抓取 `backend:8001/metrics`。canonical nginx
对 public `location = /metrics` 返回 `404`，不得 proxy。Alertmanager 的
`local-fixture` receiver 只指向同一 internal network 上的 `alert-receiver:8080`；fixture
只验证 JSON webhook transport，不发送外部通知，也不能作为 W3-08 的真实通知证据。

Pipeline completion 使用服务端字段 `config.pipeline_completion_metric_v1` 作为持久 claim。
PostgreSQL 必须通过带 `RETURNING` 的条件 `UPDATE` 竞争；SQLite 必须在写事务中竞争；纯文件
回退必须在同 label 的跨进程文件锁内检查并原子替换。只有 claim winner 可以递增
`pipeline_runs_total`。这保证并发 resume/入口重复 finalize 不会重复计数。claim 必须先持久化
再发指标，因此进程若恰在二者之间崩溃，允许少计一次但禁止重放重复计数；Prometheus
进程内 counter 本身也不是业务完成账本，业务终态始终以持久 lifecycle state 为准。
所有普通 state save/update 也必须在数据库事务或同一文件锁内保留已经存在的 claim，禁止
用调用方的 stale `config` 覆盖它。配置了 `DATABASE_URL` 或运行于 production 环境时，
PostgreSQL claim store 不可用必须 fail-closed；不得改用文件回退生成第二份 completion 权威。
claim winner 的 `outcome`、`error_count` 和 `scenario` 必须在同一数据库事务或文件锁内从
当前持久终态重新派生；调用方提供的旧终态只能贡献计时元数据，不能决定指标结果。即使旧
success/failure runner 先进入 finalizer，最终 claim 与发出的 metric 也必须匹配 durable state。

## 本地验证

```bash
make monitoring-check
RELEASE_SOURCE_SHA=w3-e2-local \
TEST_BUNDLE_KEY=fixture-only-not-production \
GRAFANA_ADMIN_PASSWORD_FILE=/absolute/path/to/local-password-file \
docker compose \
  -f deploy/lighthouse/docker-compose.monitoring.yml \
  --profile monitoring config --quiet
pytest -q \
  tests/test_prometheus_metrics_endpoint.py \
  tests/test_telemetry_prometheus_new_metrics.py \
  tests/test_bg_registry.py \
  tests/test_monitoring_fixture_receiver.py
```

Grafana password file 必须由操作者在仓库外创建、权限设为 `0600`，不得提交或打印。
`make monitoring-check` 使用 digest-pinned `promtool` 和 `amtool`，依次验证完整 Prometheus
config、rule 语法、
全部现有告警的 non-firing/firing/resolved fixtures、Alertmanager config，以及
exporter/rule/dashboard/ownership Python contracts。Compose 检查必须使用 `--quiet`，避免
在输出中展开环境值。

## 分类响应

1. `unknown metric`：先核对 exporter 是否真的注册并更新该 family；没有更新路径就删除
   rule/panel，不得保留永久为零的假指标。
2. label/enum 不一致：以 `prometheus-metrics-contract.v1` 和实际 exporter labels 为准，
   同步 rule、fixture、dashboard legend。
3. completion 重复：检查 PostgreSQL 条件更新、SQLite 写事务或文件锁是否仍是唯一 claim
   路径，并确认普通 stale save 不会删除既有 claim；不得用进程内集合去重，也不得先发指标
   后保存。配置了 PostgreSQL 时若 claim store 不可用，应停止 finalization 并修复数据库，
   不得切到文件 claim。若 claim outcome 与业务终态相反，检查 winner 是否仍在锁/事务内从
   durable state 派生，而不是信任调用方缓存的 terminal state。
4. promtool fixture 失败：分别检查 `for` 时长、range window、histogram bucket 和
   evaluation interval，不通过修改 expected alert 去掩盖表达式错误。
5. amtool 失败：修复 `alertmanager.yml` 后重跑；不得改成未知公网 webhook。
6. `/metrics` 公网可达：这是部署边界故障。先准备可回滚 nginx 变更，再走独立生产授权；
   本地配置通过不代表生产已 reload。

## 回滚与证据边界

本地回滚只恢复本批 monitoring 配置与 exporter 变更，并重新执行完整
`make monitoring-check`。生产回滚必须使用已审查的部署包装器和既有 nginx 备份，禁止
rsync 或容器内热改。

当前本地闭环不证明 Prometheus/Grafana 已部署，不证明生产 `/metrics` 已关闭，也不证明
外部通知接收成功。W3-08 只有在单独授权的真实 firing 和 resolved notification drill
均有接收回执后才能关闭。
