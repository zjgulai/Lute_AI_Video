---
title: Lighthouse rsync artifact exclude guard
doc_type: workflow
module: deploy
topic: lighthouse-rsync-artifact-exclude
status: stable
created: 2026-06-01
updated: 2026-09-01
owner: self
source: human+ai
---

# Lighthouse rsync artifact exclude guard

## 目的

锁定 Lighthouse 同步边界，防止本地构建产物、Playwright 报告、截图、临时输出、草稿/归档材料、本地工作态目录、参考截图、生产 secret 和未跟踪的 remote-only production sidecars 进入新的不可变 release 目录。Canonical rsync 目标是发布前必须不存在的 `/opt/ai-video/releases-$SHA`，不是共享根 `/opt/ai-video`。

## 不变量

- 唯一排除清单是 `deploy/lighthouse/rsync-excludes.txt`。
- source manifest 中的每个 tracked 路径都必须被 canonical rsync 传入新的不可变 release 目录；测试必须执行真实 manifest → rsync → validate 闭环。
- canonical rsync 必须使用 NUL-safe `git ls-files -z` 生成的精确 `--files-from --from0` 白名单，并额外加入生成的 `source-manifest.v1.json`。ignored/untracked 文件即使存在于 clean worktree，也不得进入 release。
- `--from0` 会同时改变 `--files-from` 与 `--exclude-from` 的分隔语义；因此 canonical
  wrapper/workflow 必须先把换行格式的共享排除清单转换成 mode-0600 的 NUL-delimited
  临时文件，再通过 `--exclude-from` 传给 rsync。不得把换行格式清单直接与 `--from0`
  混用；测试必须断言无 `discarding over-long filter` 且显式列入 file list 的
  `.env.local`、`private.key` 仍被排除。
- `deploy/lighthouse/build-and-deploy.sh` 必须使用 GNU rsync 3.x 执行 `--chmod=F644,D755`；在 macOS 上优先选择 `/opt/homebrew/bin/rsync` 或 `/usr/local/bin/rsync`，也允许 `RSYNC_BIN=/path/to/rsync` 覆盖。
- `.github/workflows/deploy.yml` 必须从
  `deploy/lighthouse/rsync-excludes.txt` 生成 NUL-delimited 临时排除表，不得维护
  inline exclude 副本。
- 必须排除 frontend build artifacts：`web/.next`、`web/.next.old`、`web/dist`。
- 必须排除 report / trace artifacts：`.playwright-cli`、`web/playwright-report`、`web/test-results`、`web/blob-report`。
- 必须排除 screenshots / tmp outputs：`tmp/screenshots`、`tmp/outputs`、`web/tmp`、`web/tmp/screenshots`、`output_uploaded`。
- 必须排除 local workspace state：`*.sqlite3`、`.codegraph`、`.hermes`、`worktrees`、`drafts`、`archive`、`ref`。本地账本或测试数据库不得进入 release sync。
- 必须排除 production secret / cert：`.env`、`.env.local`、`.env.production`、`.env.prod`、`*.pem`、`*.key`、`*.crt`、`deploy/lighthouse/.env.prod`、`deploy/lighthouse/.portal-auth.env`、`server.crt`、`server.key`。
- `deploy/lighthouse/plugin-hub.htpasswd` 是 remote-only production authentication sidecar，必须由共享 exclude SSOT 保护，不能被 AI Video 发布覆盖或删除。
- 必须排除未跟踪或 secret-bearing 的 remote-only production sidecars：`backups`、`deploy/lighthouse/backups`、`deploy/lighthouse/portal-auth`、`deploy/lighthouse/skills.conf`、`deploy/lighthouse/auth_gate.conf`、`deploy/lighthouse/momcozy-platform.conf`、`deploy/lighthouse/plugin-hub.htpasswd`、`deploy/lighthouse/*.conf.*backup*`、`deploy/lighthouse/*.candidate`。
- tracked 的 `deploy/lighthouse/docker-compose.prod.yml`、`deploy/lighthouse/nginx.conf`、`landing/login.html`、`landing/register.html`、`landing/systems.html`、`landing/lute-auth.css`、`landing/lute-auth.js` 只作为已审查 source copy 进入新的不可变 release 目录。`deploy.sh` 不得把这些副本复制到共享根；真实 shared-root sidecar 仍只由独立入口管理。
- 仍须排除未跟踪的 remote-only landing sidecars：`landing/lute-*.html`、`landing/voc-zh_messages.json`、`landing/.portal.htpasswd`、`landing/brand-placeholder.html`。
- apex 产品目录 sidecar 的唯一手动同步入口是 `deploy/lighthouse/sync-landing-sidecars.sh`。该入口固定 `SYNC_SCOPE=systems-only` 且默认 `DRY_RUN=1`；不接受任意文件参数，不使用 `--delete`，不调用 `deploy.sh`，不重启容器，不触发生成接口，也不会同步 `index.html`、认证页面或认证资产。
- `deploy/lighthouse/landing/systems.html` 是产品门户唯一 tracked 源。`tests/test_lighthouse_landing_static_contract.py` 必须锁定 exact card host/title/category、card/footer parity、canonical Reddit、XMind 候选、Distill 排除、闭环未归类清单、动态计数与搜索空状态；不能只断言历史 host 子集或卡片总数。
- G3 已把产品负责人确认的闭环映射固化为：Redbook `E5/L4`、DocCanvas `E8/L7`、XMind `E4/L7`。映射通过本地静态契约验证，但没有因此提升为生产部署证据或 XMind 性能通过证据。
- live 同步必须同时提供 fresh `BASELINE_SYSTEMS_SHA256` 与本地 `CANDIDATE_SYSTEMS_SHA256`，使用 pinned `SSH_KNOWN_HOSTS_FILE` 并显式设置 `CONFIRM_SYSTEMS_LIVE=1`。远端 helper 以 `python3 -I` 隔离执行，在 `deploy/lighthouse/.landing-sidecar-sync` 私有、同文件系统 transaction 中完成 non-blocking lock、二次 baseline CAS、stage fd SHA/fsync/identity 校验、原子替换、create-only backup/intent/receipt 和 post SHA readback。JSON record 先写同目录私有 partial 并 fsync，再以 hard-link create-only 原子发布，因此 final record 名只能 absent 或完整有效。`/opt/ai-video` 根目录允许由 `root` 持有；可写 state 只落在已验证由 SSH 用户持有、且不在公网 landing root 内的 `deploy/lighthouse` sibling。
- final receipt 发布失败时，helper 会在同一 lock 内从已验证 baseline backup 原子补偿；进程中断导致 candidate 已激活但 final receipt 缺失时，有效 activation intent 可作为受限 rollback recovery record。回滚仍要求 active candidate SHA、两份 backup SHA 与 intent/receipt 精确一致。只读 inspector 同样校验 state 父目录身份、record schema/字段/时间戳、backup SHA 与 exact artifact set；symlink、损坏 record、遗留 `rollback.partial` 或未知 artifact 一律停止为 ambiguous/error。
- default dry-run 只执行 production read-only baseline/nginx 检查与 rsync `--dry-run`；不会创建 transaction、backup 或 receipt。lock 为 non-blocking，`nginx -t` 与 rsync I/O 均有界。live 返回失败或 SSH 状态不明时，必须先以 `ACTION=inspect` 只读核对 active SHA 和 transaction artifacts，禁止盲目重跑。
- `tests/test_lighthouse_systems_sync.py` 与 `tests/test_lighthouse_systems_recovery.py` 是 L2 hermetic transaction 证据，只证明 fixture 中的精确文件白名单、零写入失败路径、CAS、备份、receipt、crash residue 检查和回滚；它们不等于生产 live 证据。
- XMind 严格性能预算的 SSOT 是 `configs/xmind-performance-budget.json`，执行器是 `scripts/check_xmind_performance.py`。固定四路由、桌面/移动 profile、一次 warm-up 加五次有效样本、exact `run_id=1..5` 与 nearest-rank p75；browser sample 必须绑定 exact requested/final URL、实际 viewport、逐次 cache-disabled、24 小时内 UTC 时间，且 `0 < TTFB <= FCP <= LCP`。synthetic search 固定在 desktop 模型库 exact URL，同样要求实际 `1440x900` viewport、cache-disabled、24 小时 freshness、exact `run_id=1..5` 与正耗时；五个固定搜索词每次至少有 1 个可见结果并保持显示计数一致。缺路由、缺 profile、缺 warm-up、缺样本、旧证据或测量错误一律 `BLOCKED`。传输 GET、browser lab、synthetic-search-response 与 field CWV 是四种不同证据，不得互相替代；没有 CrUX/RUM 时 field CWV 必须写 `UNKNOWN`。
- `scripts/xmind_transport_probe.py` 只使用默认 TLS 验证、禁止 redirect、限制 encoded/decoded 读取上限，并把 malformed gzip、incomplete body 和网络异常转换为结构化 `BLOCKED` sample。browser lab JSON 仍是外部采集输入：evaluator 会强制身份、freshness 与完整性字段，但不提供加密签名或证明采集器未伪造；因此 receipt provenance 仍须由执行门禁保管，不能把任意手写 JSON 当独立证据。
- 2026-09-01 的 production read-only browser snapshot 已观察到 `/models/index.html` 约 3.55 MB HTML、约 30,844 DOM nodes，并出现超出 4,000 ms 单次 LCP 上限的样本；`/router.html` 也出现 6,392 ms LCP 长尾。在 `390x844` 移动视口下，模型库页面还出现 `scrollWidth=502px`、单列 grid `486.719px` 的横向溢出；`.search-box input` 的实际 `flex: 0 1 auto` 是首要布局根因候选。当前严格结论是 `BLOCKED`，不是性能验收通过。该快照不含生产写入，也不授权加入 RUM。

## 验证命令

```bash
.venv/bin/python -m pytest tests/test_lighthouse_rsync_artifact_guard.py -q
.venv/bin/python -m pytest tests/test_lighthouse_landing_static_contract.py -q
.venv/bin/python -m pytest tests/test_lighthouse_systems_sync.py tests/test_lighthouse_systems_recovery.py tests/test_xmind_performance_budget.py -q
```

公开只读 transport gate 可单独执行：

```bash
.venv/bin/python scripts/check_xmind_performance.py
```

该命令固定访问已登记的四个 XMind 公网页面。未提供完整 browser lab 与 synthetic search evidence 时会按设计返回 `BLOCKED`；transport PASS 不能写成浏览器性能或 field CWV PASS。

## 修改流程

1. 新增本地产物目录时，先更新 `deploy/lighthouse/rsync-excludes.txt`。
2. 同步更新 `configs/lighthouse-rsync-artifact-exclude-contract.yaml` 和测试里的分类清单。
3. 手工部署前先执行 `DRY_RUN=1 SSH_KEY=/path/to/ai_video.pem deploy/lighthouse/build-and-deploy.sh`。
   Wrapper 只接受 clean、与 `origin/main` 同步的 `main`；默认 dry-run。真实部署必须显式
   `DRY_RUN=0 RELEASE_SOURCE_SHA="$(git rev-parse HEAD)"`，绑定已复核 source SHA。
   - dry-run 若出现 `deploy/lighthouse/plugin-hub.htpasswd`，先修复 exclude 边界，不允许继续部署。
4. dry-run 输出如出现 `.env.local`、`.env.production`、`.env.prod`、证书、私钥、`*.sqlite3`、`.next`、`.playwright-cli`、`web/playwright-report`、`tmp/screenshots`、`output`、`output_uploaded`、`backups`、`.codegraph`、`deploy/lighthouse/portal-auth`、`deploy/lighthouse/skills.conf`、`deploy/lighthouse/auth_gate.conf`、`deploy/lighthouse/momcozy-platform.conf`、`deploy/lighthouse/*.conf.*backup*`、`deploy/lighthouse/*.candidate`、`drafts`、`archive`、`ref` 等路径，先修 file-list/exclude 边界，不允许继续部署。tracked source-copy sidecars 出现在新的 `releases-$SHA` 目录是预期行为，但不得出现在共享根更新命令中。
5. 如需同步 `systems.html`，不要取消默认发布排除项。先通过独立只读 SSH 取得 fresh production SHA，再计算 tracked candidate SHA：

```bash
candidate_sha="$(python3 -c 'import hashlib, pathlib; print(hashlib.sha256(pathlib.Path("deploy/lighthouse/landing/systems.html").read_bytes()).hexdigest())')"
baseline_sha="<fresh-read-only-production-systems-sha256>"

SSH_KEY=/path/to/private-key \
SSH_KNOWN_HOSTS_FILE=/path/to/pinned-known-hosts \
BASELINE_SYSTEMS_SHA256="$baseline_sha" \
CANDIDATE_SYSTEMS_SHA256="$candidate_sha" \
DRY_RUN=1 \
deploy/lighthouse/sync-landing-sidecars.sh
```

只有获得针对这两个 exact SHA 的独立 live 授权后，才可执行：

```bash
SSH_KEY=/path/to/private-key \
SSH_KNOWN_HOSTS_FILE=/path/to/pinned-known-hosts \
BASELINE_SYSTEMS_SHA256="$baseline_sha" \
CANDIDATE_SYSTEMS_SHA256="$candidate_sha" \
DRY_RUN=0 \
CONFIRM_SYSTEMS_LIVE=1 \
deploy/lighthouse/sync-landing-sidecars.sh
```

G3 没有执行上述 live 命令。成功后仍须按 receipt 的 post SHA 验证 `https://lute-tlz-dddd.top/systems.html` 的 card/loop/search 行为；只检查 HTTP 200 不足以验收。

6. 回滚必须使用同一 baseline/candidate SHA transaction，先 dry-run：

```bash
ACTION=rollback \
SSH_KEY=/path/to/private-key \
SSH_KNOWN_HOSTS_FILE=/path/to/pinned-known-hosts \
BASELINE_SYSTEMS_SHA256="$baseline_sha" \
CANDIDATE_SYSTEMS_SHA256="$candidate_sha" \
DRY_RUN=1 \
deploy/lighthouse/sync-landing-sidecars.sh
```

任何 live 失败或连接状态不明时，先执行只读 inspection：

```bash
ACTION=inspect \
SSH_KEY=/path/to/private-key \
SSH_KNOWN_HOSTS_FILE=/path/to/pinned-known-hosts \
BASELINE_SYSTEMS_SHA256="$baseline_sha" \
CANDIDATE_SYSTEMS_SHA256="$candidate_sha" \
DRY_RUN=1 \
deploy/lighthouse/sync-landing-sidecars.sh
```

live 回滚同样需要 `DRY_RUN=0 CONFIRM_SYSTEMS_LIVE=1` 和新的精确授权。transaction 位于远端 `deploy/lighthouse/.landing-sidecar-sync/systems.html/<baseline>--<candidate>/`；inspection 输出会区分 no-transaction、prepared、active candidate/receipt missing、activated、rolled back 与 ambiguous。任何 SHA 漂移、路径身份异常或 ambiguous 状态都必须停止自动处置。

## 相关文件

- `deploy/lighthouse/rsync-excludes.txt`
- `deploy/lighthouse/build-and-deploy.sh`
- `deploy/lighthouse/sync-landing-sidecars.sh`
- `deploy/lighthouse/systems-sidecar-remote.py`
- `deploy/lighthouse/systems-sidecar-inspect.py`
- `.github/workflows/deploy.yml`
- `configs/lighthouse-rsync-artifact-exclude-contract.yaml`
- `configs/xmind-performance-budget.json`
- `scripts/check_xmind_performance.py`
- `scripts/xmind_transport_probe.py`
- `tests/test_lighthouse_rsync_artifact_guard.py`
- `tests/test_lighthouse_landing_static_contract.py`
- `tests/test_lighthouse_systems_sync.py`
- `tests/test_lighthouse_systems_recovery.py`
- `tests/test_xmind_performance_budget.py`
