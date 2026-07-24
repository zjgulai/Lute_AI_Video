---
title: W5 Fast One-Shot Operator Runbook
doc_type: workflow
module: acceptance
topic: w5-fast-one-shot-operator
status: stable
created: 2026-07-24
updated: 2026-07-24
owner: self
source: human+ai
---

# Runbook — W5 Fast 单次执行器

## 1. 当前证据边界

本 runbook 的当前实现状态是 `L2-fixture-or-dry-run`。本地测试只验证执行器、
固定 backend-direct 路由、create-only 证据、有限只读轮询和 provider-off 恢复；
它不证明 provider 可用、生产已部署、真实生成成功、publish/delivery 可用或账务已
完成对账。

历史 W5-04 marker、activation、runtime binding 和 raw idempotency key 已永久消费，
不得复制、改名、删除 marker 后复用，也不得把 poll/ledger 命令当成再次 POST 的
授权。任何新的生产执行必须依次获得三个独立 gate：

1. exact reviewed candidate 的 provider-off 部署与 L3 验收；
2. 新 plan、activation、binding、request 和 raw key；
3. 明确写出 `submit=1`、provider mutation cap、USD nanos hard cap、自动重试 0、
   `pending_review`、publish false、delivery false 的新鲜人工授权。

缺少任一 gate 时只允许执行本地测试或只读 `contract`，不得运行 `submit`。

## 2. 组件与不变量

- `src/operations/w5_fast_one_shot.py`：依赖注入核心，负责 O_EXCL marker、一次
  POST、GET-only poll、safe ledger projection 和无条件 restore。
- `scripts/w5_fast_one_shot_operator.py`：固定访问 `http://127.0.0.1:8001`，只认
  `POST /fast/submit` 与 `GET /fast/status/{task_id}`；不接受 base URL、代理路径或
  retry 参数。
- `deploy/lighthouse/w5-fast-one-shot-window.sh`：exact-SHA 窗口。EXIT trap 在任何
  配置变更前安装；所有返回码与异常路径都恢复 byte-identical env，重建 exact
  backend，并验证 image revision、immutable Docker image ID、W5 路径消失和
  TikTok/Shopify publish flags 关闭。正确 tag 但 revision/image ID 漂移也会在环境
  变更前阻断。
- 四个私有 JSON 只能复制到固定 `/run/ai-video-w5`，恢复重建后自然销毁；禁止把
  `/`、`/app`、`/app/output`、重复分隔符或 traversal path 传给 ownership 命令。
- Safe evidence 独立写入 backend 已挂载的
  `/app/output/.w5-one-shot/<activation_id>`；父目录和 activation leaf 都必须由当前
  backend UID/GID 拥有且恰为 `0700`，其他 UID 无穿越权限。
  marker 使用 O_EXCL、`0600`、64 KiB 上限、文件和父目录 fsync、no-follow 和
  strict JSON，跨 backend recreate 保留。证据只保存 digest、稳定 ID、状态、金额和
  safe error code，不保存 raw key、API key、prompt、DSN、provider response、异常
  文本或绝对产物路径。

OpenAPI contract 必须在 marker 创建之前通过。marker 一旦创建，无论 HTTP 拒绝、
响应损坏、timeout、disconnect、进程退出或后续证据失败，都视为提交权限已消费，
禁止自动或人工无新授权重发。

## 3. 本地验证

以下命令不会读取 provider key，也不会访问生产或 provider：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q \
  tests/test_w5_fast_one_shot_operator.py \
  tests/test_w5_fast_one_shot_window.py \
  tests/test_w5_fast_one_shot_cli.py
bash -n deploy/lighthouse/w5-fast-one-shot-window.sh
.venv/bin/ruff check \
  src/operations/w5_fast_one_shot.py \
  scripts/w5_fast_one_shot_operator.py \
  tests/test_w5_fast_one_shot_operator.py \
  tests/test_w5_fast_one_shot_window.py \
  tests/test_w5_fast_one_shot_cli.py
.venv/bin/pyright \
  src/operations/w5_fast_one_shot.py \
  scripts/w5_fast_one_shot_operator.py
```

窗口测试使用显式 fixture mode 和临时 env；它实际运行退出码 0/2/3/5、恢复失败、
image revision/ID drift、危险 private path，以及 recreate 后同 activation 第二次
运行零 POST，但不会调用 Docker、网络、provider 或生产。

## 4. 未来单独授权后的操作顺序

下列顺序只是受控操作合同，不构成本次授权。操作者必须使用部署后 exact SHA、
reviewed backend image revision 与 immutable Docker image ID，
把四个全新私有文件放到 root-owned stage，并通过终端 stdin 临时输入 raw key；
raw key 不写文件、不进入环境变量、不出现在命令参数或日志。

1. 用 `contract` 只读检查当前 backend OpenAPI。失败时停止，尚未消费 marker。
2. 用同一 raw key 执行 `preflight`，验证 plan/activation/binding/request、当前时间、
   tenant、预算、provider caps、retry 0、pending review 和 publish/delivery false。
3. 在人工确认窗口仍有效后，只运行一次窗口脚本。脚本内部设置独立 execute gate，
   先在 persistent output volume 落盘并 fsync marker，再发送一次 POST；不提供
   第二次 submit 入口。同 activation 的再次窗口会在配置变更前看到 marker 并阻断。
4. accepted 才进入有限 GET poll；rejected 或 ambiguous 不 poll。所有路径尝试一次
   read-only ledger snapshot，并立即恢复 provider-off。
5. 必须看到 `provider-off restoration verified`，再独立复核 exact image、健康、
   W5 env 消失和 publish flags false。恢复失败返回 90，是生产阻塞，不得因业务
   结果看似成功而忽略。

Host stage 输入不由窗口脚本盲删，按私有文件保留策略单独清理。Safe evidence 位于
持久 output volume，可只读复制到批准的证据包；不得移动或删除
`submit-invoked.json` 来制造“可重试”假象。容器内 `/run/ai-video-w5` 输入会随
provider-off backend recreate 一并销毁。

## 5. 结果分类

| 状态 / 返回码 | 含义 | 后续动作 |
|---|---|---|
| `accepted`, 0 | backend 返回安全 task ID | 仅 GET poll；不得再次 POST |
| `rejected`, 2 | 明确 HTTP 拒绝 | 保留 marker/ledger，只能申请全新授权 |
| `transport_ambiguous`, 3 | backend 是否收到不可确定 | 权限已消费；只读核查，不重发 |
| `response_ambiguous`, 3 | 2xx 响应缺少可信 task/status | 按 ambiguous 处理，不猜测失败 |
| poll 非成功, 5 | 有限读取未达到 `done` | 保留 terminal evidence，人工判断 |
| restore failure, 90 | provider-off 恢复或验证失败 | 立即阻断并人工恢复，不做新 mutation |

`ledger-outcome.json` 只允许 tenant-bound idempotency/account/attempt 白名单字段，
且字符串 grammar/长度、ordinal 与 USD nanos 非负上限均会再次验证。
`result_snapshot`、unknown fields、raw response 与 provider payload 在 SQL 和投影两层
均被丢弃。账本不存在不等于 provider 未调用；ambiguous 也不等于零扣费。

## 6. 禁止事项

- 禁止使用 `/api/fast/submit`、public nginx proxy 或可配置 base URL。
- 禁止 curl/SDK retry、shell loop POST、删除/覆盖 marker、换 key 重发或 fallback。
- 禁止在 stdout/stderr、证据、命令参数、环境变量或 shell history 暴露 raw key。
- 禁止将 `pending_review` 自动提升为 accepted/published/delivered。
- 禁止把本地 fixture、OpenAPI 200、provider-off L3 或 ledger readback 单独宣称为
  全量生成环境验收成功。

## 7. 相关文档

- `docs/superpowers/plans/2026-07-24-w5-fast-one-shot-operator-governance.md`
- `docs/superpowers/plans/2026-07-23-w5-fast-runtime-binding.md`
- `docs/runbooks/provider-cost-ledger-per-job-budget.md`
- `docs/runbooks/submission-idempotency-recovery.md`
