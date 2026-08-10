---
title: Remotion no provider key
doc_type: workflow
module: rendering
topic: remotion-no-provider-key
status: stable
created: 2026-06-01
updated: 2026-07-28
owner: self
source: human+ai
---

# Remotion No Provider Key

## 1. 适用范围

本 runbook 约束 `rendering/` 子包、Lighthouse rendering service 和 CI/deploy 中的 Remotion 构建/测试边界。机器可读契约是 [`configs/remotion-no-provider-key-contract.json`](../../configs/remotion-no-provider-key-contract.json)，测试入口是 [`tests/test_remotion_no_provider_key_guard.py`](../../tests/test_remotion_no_provider_key_guard.py)。

## 2. 当前规则

- `rendering/` 只能做本地 Remotion bundle/render、clip concat、audio mux 和 health probe。
- `rendering/` 禁止读取 `POYO_API_KEY`、`DEEPSEEK_API_KEY`、`SILICONFLOW_API_KEY`、`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`SEEDANCE_API_KEY`、发布平台 token 或 `RUN_TOKEN_SMOKE`。
- `rendering/` 禁止引用 provider API host，例如 `api.poyo.ai`、`api.deepseek.com`、`api.siliconflow.cn`、`api.siliconflow.com`。
- 允许的环境变量只限本地运行控制：`HOME`、`NODE_ENV`、`OUTPUT_DIR`、`PUPPETEER_SKIP_DOWNLOAD`、`RENDERING_SERVICE_SOCKET`、`XDG_DATA_HOME`；镜像固定 `XDG_DATA_HOME=/usr/share`，只读根文件系统阻止请求控制 MIME magic。Remotion 的 `selectComposition` 与 `renderMedia` 都代码级固定到镜像内 `/usr/bin/google-chrome-stable`，不得通过环境变量替换可执行文件。
- Lighthouse `rendering` service 不使用 `env_file`，不监听 TCP，且 `network_mode=none`；backend 只通过 `renderer_socket:/run/rendering` 上的 Unix Domain Socket 调用。
- renderer 与 backend 沿用现有持久卷兼容的固定非 root 身份 `999:999`；renderer root filesystem 只读、`cap_drop=ALL`、`no-new-privileges`，限制为 2 CPU、4 GiB、256 PIDs 和单任务并发，临时文件只写入受限 tmpfs、socket volume 与 tenant output volume。canonical compose 与 release smoke 必须启用 Docker init 进程回收器，避免 Chrome/FFmpeg 后代进程退出后耗尽 PID 上限。
- `/assemble` 只接受 strict JSON：tenant、disposition、output dir、label、clip/audio 列表和 render payload 必须完整且无额外字段。路径必须位于同一 tenant/run 的 `pending_review|quarantine` 根内，拒绝 symlink、URL、控制字符、跨 run/tenant、AVI、container/magic 不一致和不允许 codec。单请求在读取/哈希前统一限制为最多 16 个唯一媒体文件、合计 4 GiB 与最多 64 个 timeline item；禁止重复路径放大与并行无界哈希。
- 所有媒体在已打开的原始文件句柄上冻结 SHA-256，再复制成 request-private snapshot 并复算一致性；FFprobe/FFmpeg 在 input 前固定 protocol/codec/demuxer/probe/stream allowlist，concat manifest 只写安全相对路径并固定 `-safe 1`、`file,pipe`。
- renderer 的 540 秒总 deadline 必须短于 backend 600 秒 UDS 客户端 deadline；子进程超时终止完整 process group。相同 output label 使用 atomic hard-link no-clobber；在 link commit 前完成 source chmod、fsync、size/SHA 计算，commit 后清理失败只能记录稳定告警，不能把已发布成功翻转为失败。backend 必须复核返回的 artifact size 和 SHA-256。
- 540 秒 deadline 覆盖命令、snapshot copy、hash 与 publish 全过程；health 中每个 Chrome/FFmpeg probe 最多 20 秒，backend UDS consumer 最多等待 25 秒，两者仍小于 renderer 容器 30 秒 health timeout。canonical compose 在首次启动 backend 前等待 renderer `service_healthy`；backend 自身的持续健康检查仍只调用数据库 `/health/ready`，不把较慢的 renderer 详情探针串进 10 秒 Docker 健康预算。
- render payload 固定为 1–180 秒、有限 shot/caption/audio 数量与一致时间区间；Remotion composition 按请求时长计算帧数，并固定 JPEG 中间帧和镜像内 Google Chrome。
- 本地 `docker-compose.yml` 不单独定义 provider-enabled rendering service，只把 `./rendering` 作为后端容器内本地工具目录挂载。

## 3. 变更流程

1. 修改 `rendering/` 前先确认该逻辑是否属于本地组装；需要调用 provider 的逻辑必须放回 backend tools/skills/pipeline 层。
2. 新增 rendering 环境变量时先更新 contract，并说明它不是 provider credential。
3. CI/deploy 如需新增 `working-directory: rendering` 或 `cd rendering` 步骤，禁止注入 provider key，禁止设置 `RUN_TOKEN_SMOKE=1`。
4. 静态守卫本身不执行 Docker build 或真实媒体 render；H9 的 Node 测试会启动一个临时 UDS 监听器验证 schema 拒绝，但不访问生产、不调用 provider、不消耗 poyo.ai tokens。

## 4. 本地验证

```bash
.venv/bin/python -m pytest tests/test_remotion_no_provider_key_guard.py tests/test_docs_link_check_scope.py -q
.venv/bin/ruff check tests/test_remotion_no_provider_key_guard.py tests/test_docs_link_check_scope.py
cd rendering && npm test && npm exec tsc -- --noEmit
git diff --check
```

2026-07-28 H9 最终本地候选以两个独立容器、共享 output/socket volumes、`network_mode=none`
验证了真实 backend-to-renderer UDS 路径。renderer exact image
`sha256:6c4827ebb2fd40087eac8bb56f03ac0aa7048e829cb3e86f0c152c2bf7f29efe`
与最终 backend exact image
`sha256:5d1be497c4b220695e58057f3ed56634c8129248e6e5eb444aa594cab37f3924`
共同返回健康 `200`。启用 Docker init 后连续 20 次 UDS health 全部成功，最慢
`0.664` 秒，随后生成 non-stub Remotion 产物 `91950` bytes / SHA-256
`1be49b2f1a38461d49e7cd4a4ba7e5c3aa212325e667b46769dda5cb9caf8222`，backend 复算一致；
运行后 PID 1 是 `docker-init`、僵尸进程 `0`、总进程 `5`。此前同一 image 未启用 init
的长运行容器累积约 215 个僵尸进程并退化到 stub，此失败证据是新增 runtime gate 的依据。
重复 label 返回 `409 render_output_conflict`，不允许的 MPEG-4 Part 2 返回
`422 media_codec_invalid`。codec probe 运行在 request-private reservation 内，可能短暂
创建 `.renderer-*.lock`；`finally` 随后清理该目录，最终视频产物不存在。该证据仅为
本地 provider-off 候选，不是 GitHub release 或生产部署证据。

## 5. 失败处理

- `rendering/` 出现 provider key：删除该读取点，把 provider 调用放回后端 provider client。
- `rendering` compose service 出现 `env_file`：移除，避免 `.env.prod` 中的 provider credentials 泄入渲染容器。
- `rendering` 出现 TCP listener、外部 network、`-safe 0`、AVI 或 caller-controlled absolute manifest：删除该入口并恢复 UDS/strict snapshot 边界。
- CI rendering 步骤注入 provider env：拆分为无 token build/test；真实生成只能
  使用全新的 W5 exact-authorization 计划，旧 P2/L4C 流程不可复用。
- 进程被 SIGKILL 或主机异常断电后若遗留 `.renderer-<label>.lock`：先停止 renderer，确认对应 tenant/run 目录中没有同 label 的已发布 `.mp4`，并确认 lock 的修改时间已超过 540 秒总 deadline；再对该精确目录执行 `lstat`，确认它是普通目录且不是 symlink，最后只删除这一条精确 lock 目录并重启 renderer。禁止在 renderer 运行时清理、禁止跨 tenant/run 扫描删除，也禁止用宽泛的 `find ... -delete`。
- 固定 Chrome `.deb` URL 或 checksum 失效：Docker build 必须失败关闭；重新从受信上游取得精确版本与 SHA-256，经独立构建/扫描复验后同时更新版本和 checksum，禁止临时切换到未固定的 latest URL。
