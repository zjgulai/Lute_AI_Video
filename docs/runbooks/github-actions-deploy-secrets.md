---
name: github-actions-deploy-secrets
description: GitHub Actions deploy.yml 必需 secrets 列表与配置说明。当配置 production deploy workflow 或诊断 secret-missing 失败时查阅。
doc_type: runbook
module: ci-cd
topic: deploy-secrets
status: stable
created: 2026-05-17
updated: 2026-08-13
owner: Sisyphus
---

# GitHub Actions deploy.yml — Required Secrets

## 触发方式

`deploy.yml` 在两种条件下运行：

1. **手动触发** (`workflow_dispatch`): GitHub UI → Actions → Deploy to Production → Run workflow，填写 `reason` 并选择 `execution_scope`
2. **Tag 推送**: `git tag v0.2.5 && git push origin v0.2.5` 自动触发完整部署路径

| `execution_scope` | 最后执行的成功边界 | Environment / 凭据 |
|---|---|---|
| `archive-only` | exact-main preflight、三镜像 smoke/SBOM/scan、release bundle | 不会进入任何 GitHub Environment，不读取 `DRY_RUN_*`/`DEPLOY_*` |
| `remote-dry-run` | 上述 archive + 受限 rsync dry-run artifact | 仅 `production-read-only-dry-run` 与 `DRY_RUN_*` |
| `artifact-stage-only` | 上述 dry-run + GitHub OIDC→腾讯 STS + private COS multipart upload + 同地域下载/校验/receipt + incoming 清理 | `production-artifact-staging`；读取独立 `COS_*` variables/`TRANSFER_*` secrets，不读取 `DEPLOY_*` |
| `deploy` | 完整 staging + verified incoming 原子 promotion + production deploy/health smoke | staging 成功后才进入 `production` |

手动触发默认选择 `archive-only`。所有范围都要求 workflow SHA 精确等于执行时的 exact `origin/main` tip；PR head 或 pull-request synthetic merge SHA 不能生成 canonical deployable archive。`archive-only` 成功只构成 exact-main L2 archive/CI 证据，不构成生产部署证据。

所有触发方式都先经过无生产凭证的 exact-main provenance gate。远程只读 dry-run 使用独立的 `production-read-only-dry-run` Environment；COS 中继和受限下载使用 `production-artifact-staging`；只有 verified incoming 已形成后，真实部署才经过 `production` 的 manual approval gate。

## 必需的 production Environment Secrets

在 **Settings → Environments → production → Environment secrets** 配置：

| Secret | 说明 | 示例值 |
|---|---|---|
| `DEPLOY_HOST` | 生产服务器主机/IP | `101.34.52.232` |
| `DEPLOY_USER` | SSH 用户 | `ubuntu` |
| `DEPLOY_SSH_KEY` | SSH 私钥的完整内容（含 `-----BEGIN ... -----END`） | `-----BEGIN OPENSSH PRIVATE KEY-----\n...` |
| `DEPLOY_TARGET_DIR` | 服务器上的目标目录 | `/opt/ai-video` |
| `DEPLOY_KNOWN_HOSTS` | 预先核验并固定的生产 SSH `known_hosts` 行；禁止运行时 `ssh-keyscan`/TOFU | `<host> <key-type> <public-key>` |

这些 secret 不得配置成 repository-wide secret；它们只能在 `production` 人工批准后进入 deploy job。
workflow 在任何 production SSH 或 promotion 之前要求 `DEPLOY_TARGET_DIR`
精确等于 canonical `/opt/ai-video`；空值或其他路径以
`deploy_target_root_invalid` 失败关闭。

production job 不再从 GitHub runner 直接 rsync source 或 2.28 GB image archive。它只使用上述凭据调用 root-owned transfer gate 的 `promote`，然后从 immutable `releases-<SHA>` 执行既有 `deploy.sh`。

## 只读 dry-run Environment Secrets

在独立 Environment `production-read-only-dry-run` 配置：

| Secret | 说明 |
|---|---|
| `DRY_RUN_HOST` | 只读 dry-run SSH 目标 |
| `DRY_RUN_USER` | 服务器端受限账号 |
| `DRY_RUN_SSH_KEY` | 仅允许目标路径存在性检查和 rsync dry-run 的独立私钥 |
| `DRY_RUN_TARGET_DIR` | 只读检查目标根目录 |
| `DRY_RUN_KNOWN_HOSTS` | 预先核验并固定的 SSH host key |

服务端必须用 forced command/权限规则限制该账号，禁止写文件、启动容器、读取 env/secrets 或执行任意 shell。未配置这组独立凭证时，`remote-dry-run` 必须阻断；不得回退复用 `DEPLOY_*`。

## Artifact staging Environment

在独立 Environment `production-artifact-staging` 配置 GitHub OIDC→腾讯 STS 角色绑定和专用 forced-command SSH 身份。workflow 只取得 `id-token: write` 来申请当前 job 的 OIDC JWT；它不保存长期 CAM key，也不从 Environment 读取 COS 临时密钥。

Environment secrets 必须恰为：

| Secret | 说明 |
|---|---|
| `TRANSFER_HOST` | 安装了 release transfer gate 的 Lighthouse 主机 |
| `TRANSFER_USER` | 只允许 forced command 的 staging 用户 |
| `TRANSFER_SSH_KEY` | 与 production deploy key 分离的 staging 私钥 |
| `TRANSFER_KNOWN_HOSTS` | 预核验固定的 staging SSH host key |

Environment variables 必须恰为：

| Variable | 说明 |
|---|---|
| `COS_BUCKET` | private、启用短生命周期治理的 `<bucket>-<appid>` 名称 |
| `COS_ENDPOINT` | 固定地域 endpoint host，例如 `cos.ap-shanghai.myqcloud.com`，必须匹配 `cos.<region>.myqcloud.com` 且不得带 scheme/path |
| `TRANSFER_TARGET_DIR` | 固定为 `/opt/ai-video`；workflow 与 gate 均 fail closed |
| `COS_STS_ROLE_ARN` | 只关联已审查 exact COS policy 的腾讯 CAM OIDC role ARN |
| `COS_OIDC_PROVIDER_ID` | 腾讯 CAM 中 GitHub OIDC 身份提供商的精确名称 |

腾讯 OIDC IdP 必须冻结 issuer=`https://token.actions.githubusercontent.com`、audience=`sts.tencentcloudapi.com`，role trust 的 subject 必须精确为 `repo:zjgulai/Lute_AI_Video:environment:production-artifact-staging`。获批 job 通过 GitHub runner 自带的不透明 OIDC transport URL/token 取一次 JWT；transport 只允许 HTTPS/443、无 userinfo/fragment、主机为 `actions.githubusercontent.com` 或其严格子域，并拒绝 redirect，但不得把它误当成固定 issuer host/path。客户端逐字段核对 repo/SHA/run/attempt/issuer/audience/subject，再对固定 `sts.tencentcloudapi.com` 发一次 no-redirect `AssumeRoleWithWebIdentity`，请求精确 `DurationSeconds=7200`。返回的 SecretId/SecretKey/Token 只落在 runner `0600` 临时文件；非秘密 receipt 记录 RoleArn、ProviderId、RequestId、请求时间与 STS 返回的 Expiration/ExpiredTime。workflow 在 COS readback 前和第一个 probe PUT 前都对该同一凭据文件复验 exact identity 与剩余 TTL 至少 3600 秒；不足时终态为 `sts_validity_gate_failed`，不得 mutation。

`configs/cos-release-governance.v1.json` 冻结完整 CAM allowlist：bucket readback 仅 `GetBucketACL`/`GetBucketPolicy`/`GetBucketLifecycle`/`GetBucketVersioning`；run-bound probe 仅 `PutObject`/`GetObject`/`DeleteObject`；exact SHA release prefix 仅 `PutObject`/`GetObject`/`InitiateMultipartUpload`/`UploadPart`/`CompleteMultipartUpload`/`AbortMultipartUpload`；三条 statement 的 `condition` 均为空且禁止额外 action/resource/statement。运行时不接受 operator 自报的 policy JSON/hash。六个共享对象位于 content-addressed prefix；每个获批 run 的 manifest 位于其 `transactions/<run>/<attempt>/` 子键。仓库自有 signer 只从该 `0600` STS 文件读取凭据，禁止 shell tracing；signed GET URL 仅通过 SSH stdin 管道传递，不写入文件、参数、GitHub output 或 artifact。

### CAM effective-role readback gate

创建 workflow dispatch 后，先让 `artifact-stage` 停在 `production-artifact-staging` Environment 审批，记录 exact `source_revision/run_id/run_attempt`；**批准 Environment 之前**，使用一次性、只读、最短可行期限的 CAM 审计 STS 凭据执行仓库命令。凭据文件必须在仓库外的 owner-only `0700` 目录中、文件 mode=`0600`、schema=`cam-readback-credentials.v1`，包含 `expiration` 与临时 `secret_id/secret_key/session_token`，不得进入聊天、日志、Git、artifact 或 receipt。审计身份只允许以下读取动作：`cam:DescribeOIDCConfig`、`cam:GetRole`、`cam:ListAttachedRolePolicies`、`cam:ListPolicyVersions`、`cam:GetPolicyVersion`、`cam:GetRolePermissionBoundary`；不得拥有 CAM/COS mutation。

```bash
umask 077
.venv/bin/python scripts/release_transfer.py cam-effective-role-readback \
  --credentials "$CAM_READBACK_CREDENTIAL_FILE" \
  --provider-id "$COS_OIDC_PROVIDER_ID" \
  --role-arn "$COS_STS_ROLE_ARN" \
  --bucket "$COS_BUCKET" \
  --endpoint-host "$COS_ENDPOINT" \
  --source-revision "$SOURCE_REVISION" \
  --workflow-run-id "$GITHUB_RUN_ID" \
  --workflow-run-attempt "$GITHUB_RUN_ATTEMPT" \
  --governance-contract configs/cos-release-governance.v1.json \
  > "$CAM_READBACK_RECEIPT"
test ! -e "$CAM_READBACK_CREDENTIAL_FILE"
```

该命令先以打开的单链接 inode 为身份读取凭据，并在任何 CAM 请求前于信号屏蔽区内清零/fsync 原 inode，再以同一已验证 parent fd 做 atomic no-replace quarantine；quarantine 的 dev/inode/type/owner/link/mode 全量匹配后才删除。路径竞态、异物、rename/unlink 双故障都保留 quarantine 并进入 manual-recovery，且不发 CAM 请求。读取、解析、请求或策略校验失败时原凭据也已消费。随后它直接以 TC3-HMAC-SHA256、no-redirect、单次请求调用固定 `cam.tencentcloudapi.com`，不是读取 operator 生成的 policy 文件。它必须取得六个服务端 `RequestId` 并一次性证明：目标 OIDC provider 启用、issuer/audience 精确且 key 自动轮换；目标 role ARN/name/ID 精确、console login 关闭、session duration=7200；trust 只有一个 `AssumeRoleWithWebIdentity` statement，federated provider 与 `oidc:iss/aud/sub` 均精确且无额外主体；attached policy 总数恰一且必须为 active（`Deactived=0`、无停用详情）；全部 policy version 已枚举且唯一 default version 的文档等于当前 SHA/run/attempt 派生 allowlist；role permission boundary 不存在。CAM 角色权限模型通过 attached policies 授权；role 自身的 inline 文档是 trust policy，已由 `GetRole` 精确核验。任何额外 attachment、停用 attachment、额外 trust statement/principal/condition、错误 default version、非空 permission boundary、缺失 RequestId 或凭据过期都失败关闭。只有 canonical `cam-effective-role-readback.v1` receipt 通过独立复核后，才允许批准 staging Environment；receipt 只含身份、版本、摘要和 RequestId，不含凭据、OIDC JWT 或 policy 原文。

专用 bucket 的 lifecycle 也由同一 contract 冻结，且不允许其他规则：`ai-video-probes-expire-v1`=`ai-video/probes/`/Enabled/Expiration 1 day；`ai-video-release-multipart-abort-v1`=`ai-video/releases/`/Enabled/AbortIncompleteMultipartUpload 1 day；`ai-video-releases-expire-v1`=`ai-video/releases/`/Enabled/Expiration 14 days。配置完成后，用 `cos-lifecycle-verify` 读回规范化 XML。`cos-privacy-verify` 还必须读回 bucket ACL，要求唯一 owner CanonicalUser=`FULL_CONTROL`，并要求 GET Bucket Policy 精确返回 `404 NoSuchBucketPolicy`；任何 AllUsers、AuthenticatedUsers、额外 grant 或任意 bucket policy 都在第一个 PUT 前失败关闭。不要把 CAM policy、OIDC JWT、STS credentials 或授权 header 写入仓库、聊天或 artifact。

服务器安装与核验命令：

```bash
sudo SOURCE_ROOT=/path/to/exact-release \
  scripts/install_release_transfer_gate.sh install
sudo scripts/install_release_transfer_gate.sh verify
scripts/install_release_transfer_gate.sh print-authorized-command
```

安装器先在 root-owned、content-addressed immutable version 目录中写入两份 Python
文件与 canonical wrapper，逐字节比较 exact release source、解析 AST、导入并运行
原子 rename 自检；全部通过后才以一次 `os.replace` 原子切换固定 wrapper symlink。
所有 root Python 辅助片段和运行时 gate 都使用 CPython `-I` 隔离模式；runtime 自检
按 exact version 目录中的绝对路径加载模块，不信任调用者 cwd、`PYTHONPATH` 或同名模块。
安装器以 `O_NOFOLLOW|O_EXCL` 创建或不截断地打开单链接、regular、
`root:root:0600` 锁文件；symlink、hardlink、FIFO、目录及身份/权限漂移都在修改目标前
失败关闭。该安全 fd 持有 root-only `flock`，切换前保存旧 pointer；切换或最终核验失败会原子恢复旧
pointer，因此并发 forced-command 只能观察到完整旧版本或完整新版本，不能观察 mixed pair。
version 摘要先从 exact source 冻结；候选目录写完、发布后以及 pointer 切换紧邻前都会从
候选自身三份字节按同一算法重算，并要求精确等于目录名。source 在摘要冻结后发生任何
整体或单文件漂移都会在发布前失败关闭，不能把新字节放进旧摘要目录。
作为输入的 exact release 根、`scripts/`、`deploy/`、`deploy/lighthouse/` 也必须是
非 symlink `root:root:0755`，两份输入文件必须是单链接 `root:root:0755`；因此非 root
调用者不能在 hash/copy 间替换 source。
`INSTALL_ROOT`、`versions` 与具体 version 目录都必须是非 symlink 的
`root:root:0755`，安装锁必须是 `root:root:0600`；这些权限会在 pointer 切换紧邻前后
复验，任何 group/world-writable 或身份漂移都会保持旧 pointer 并失败关闭。成功输出
版本和三者 SHA-256 receipt；随后创建并校验 root-owned `0700`
`/var/lib/ai-video-release-transfer`，并要求它与 `/opt/ai-video` 位于同一
filesystem，并实际执行一次临时 `RENAME_NOREPLACE` 跨根 rename/cleanup 探针；
`/opt/ai-video` 必须是非 symlink、`root:root:0755`，该 device/inode 会在自检和
production promotion 的不可逆 rename 紧邻前再次复验；任何身份、owner 或 mode 漂移
都会保持 verified incoming 并失败关闭。
`EXDEV`、旧/混装文件或 wrapper 漂移都会阻断。incoming 只存在于该 staging root，production promotion 才原子
rename 到 `/opt/ai-video/releases-<SHA>`。不得把 staging root 改回 deploy
用户可写目录。
安装失败的 EXIT handler 会依次尝试 pointer rollback、candidate、pointer temp
和 previous temp 清理；单项失败不能短路后续清理，任一清理失败均保留原始失败并输出
`release_transfer_gate_install_cleanup_failed`，不得报告安装成功。
若 pointer rollback 本身失败，previous pointer 快照必须保留用于人工恢复，
同时仍继续清理 candidate 与 pointer temp。

把 `print-authorized-command` 输出的固定 command 前缀与 staging 公钥组合到 staging 用户的唯一 `authorized_keys` 行。另在 root-owned sudoers drop-in 中只允许该用户执行 `/usr/local/sbin/ai-video-release-transfer-gate --staging-command *`；wrapper 把 sshd 提供的 `SSH_ORIGINAL_COMMAND` 作为单一非 shell 参数交给 root gate，gate 再按精确五字段语法和 staging action allowlist 解析。不得设置 `SETENV`，不得授予该用户其他 sudo 命令。安装脚本本身不会修改账号、sudoers、SSH 配置或 `authorized_keys`。该身份只能执行 `probe`、`stage`、`receipt`、`cleanup`，不能执行 `promote`、shell、任意或变更型 Docker、migration、backup、cron、nginx、provider、publish 或 delivery；gate 仅允许固定的 read-only `docker ps` runtime safety probe。

## 必需的 GitHub Environment

在 **Settings → Environments** 创建 `production`：

1. Click **New environment** → name: `production`
2. **Required reviewers**: 添加 1+ 个人审批者（manual approval gate）
3. **Wait timer**: 可选，0-30 分钟延迟（默认 0）
4. **Deployment branches**: 限制为 `main` + tags `v*.*.*`

同时创建 `production-read-only-dry-run` 和 `production-artifact-staging`，都限制为 `main` + tags `v*.*.*`。前者只放 `DRY_RUN_*`，后者只放上面的 `COS_*`/`TRANSFER_*`；两者都不持有 production deploy key。`production-artifact-staging` 与 `production` 都必须禁止 administrator bypass，并保留显式人工审批。

## Preflight 阶段

`deploy.yml` 在执行 `deploy` job 前会跑：

- `preflight`: ruff check + pytest + frontend `eslint` + `tsc --noEmit` + Vitest + `next build`
- `build-images`: 构建 backend/frontend/rendering 三个 SHA-tagged image，校验 revision label、backend production import、frontend HTTP 和 rendering/ffmpeg/Chromium health；不读取 provider secret
- `remote-dry-run`: 只使用受限 `DRY_RUN_*` 身份生成 rsync dry-run artifact，不读取 `DEPLOY_*`
`artifact-stage` 的全部 signed URL（包括 resume readback）有效期取请求值与总期限剩余秒数的较小值，最高 1,800 秒；剩余不足 60 秒时不签名。probe DELETE 使用独立 fresh 30 秒 cleanup deadline，不继承已经过期的 transfer deadline，且仍只尝试一次。
- `artifact-stage`: 先按 producer digest 对 GitHub artifact 原始 ZIP 做硬校验，校验成功后才解包；随后启动一个 runner monotonic 1,800 秒总期限，通过 GitHub OIDC 现场取得并绑定 exact role/SHA/run/attempt 的单次 STS，再检查 bucket 从未启用 versioning、exact lifecycle、owner-only ACL 与 absent bucket policy。它使用仓库自有 no-redirect、每请求单次 attempt 客户端，先分别通过 64 MiB runner→COS 与 COS→Lighthouse 两腿吞吐门禁，再执行 serial 64 MiB multipart/create-only upload。probe 在 PUT 前即标记为可能存在，因此 response 丢失也会对精确 key 做一次幂等 DELETE。所有 URL 必须精确等于 `<COS_BUCKET>.<COS_ENDPOINT>`，manifest 与 probe 的 bucket/region 必须一致。服务器从 signed URL stdin 下载到 root-owned `/var/lib/ai-video-release-transfer/.incoming-<SHA>-<run>-<attempt>`；runner 仅传播剩余秒数，同时用该剩余值硬限制 probe/stage/receipt 三条 SSH pipeline，server 建立自己的 monotonic deadline，socket timeout、信号与总超时都进入同一 abort/`.part`/incoming 清理路径。deadline 必须覆盖下载后的 hash、archive/source 验证与 receipt commit；既有 probe receipt/symlink 在下载前失败关闭。receipt 与 incoming mkdir 在文件系统 mutation 前建立 intent，在屏蔽受控 signal 的临界区记录已创建 inode；提交后的 deadline/signal 失败只清理同 inode、同身份状态，foreign race、所有权不明或删除失败必须保留并标记 manual recovery。server 用 manifest 真实总字节重算门禁，规范化 source mode，并在 promotion 前重新核验每个 source byte、symlink target、精确文件/目录集合与类型；canonical manifest bytes、全量 SHA/size/source tree/archive safety/receipt 通过后才标 `verified`

只要 provenance、preflight、build-images、remote-dry-run 或 artifact-stage 任意失败，production deploy job 都不会启动。`artifact-stage-only` 成功后必须删除 verified incoming；它只证明 transfer path，不构成 image load、backup/restore、migration、应用切换或 production acceptance。transfer step 的 EXIT handler 会先删 probe，再对可能存在的 remote transaction 做精确 cleanup；若 receipt 已形成后 evidence upload 才失败，或 `deploy` 的审批被拒绝、job 被跳过/失败，`cleanup-staged-release` 也会重新进入 `production-artifact-staging`，仅用 `TRANSFER_*` 身份对精确 SHA/run/attempt/manifest 执行一次补偿，并始终上传 bounded terminal evidence。它不能读取 COS/DEPLOY 凭据，也不能删除已 promotion 的 final release；失败终态统一为 `incoming_cleanup_failed`，不得写成已清理。

`resume_transfer=true` 仅用于新的人工审批 run 显式复用 content-addressed、create-only COS 对象；runner 会对六个共享对象逐一执行一字节 signed-range readback，并核对总大小以及上传时固化的 SHA-256/size metadata。完全一致的对象才可复用，缺失对象才会 create-only 上传，任何不一致立即失败。它不会自动重跑失败的 stage，也不会放宽服务器重新校验。默认值永远是 `false`；partial incoming、receipt drift 或过期一律失败关闭，不得在同一个 run 自动重试。

安装器的跨 staging/release root 原子 no-replace 自检绑定本次 probe inode；成功或失败后只能删除该 inode。若 destination 被竞态目录、文件或 symlink 占据，必须保留异物并以 manual recovery 失败关闭，禁止对两侧路径做无身份 `rmdir`。

服务器 `.part` 下载从 `O_EXCL` open/fstat 到下载与外层 probe cleanup 共享同一 inode intent；EEXIST 并发赢家必须保留并稳定失败，下载中路径被替换或 owned partial 删除失败必须保留异物并进入 manual recovery，禁止无身份 `unlink`。

前端 build 使用 `NEXT_PUBLIC_IS_DEMO=true`，只验证构建完整性，不读取生产 API key 或 POYO key。

## Provider-off acceptance

deploy job 末尾使用正常 TLS 校验访问 canonical `https://video.lute-tlz-dddd.top/api/health`，除 `status=ok` 外还要求 `persistence.backend=postgresql`、`persistence.status=healthy`、`tables_verified=true`。IP fallback 和 `curl -k` 都不能作为成功证据。

远程 canonical deploy 永久以 `RUN_TOKEN_SMOKE=0`、`RUN_DEPLOY_SMOKE=0` 执行，不读取 API key、不调用生成接口。真实生成验证只能走独立的 exact-authorization harness，不能通过 deploy workflow 解锁。

## Failure Recovery

如果 deploy 后 smoke 失败：

1. 不要立即重新跑 — 先看 `Trigger remote deploy` 步骤的输出
2. SSH 进服务器：`ssh -i ai_video.pem ubuntu@101.34.52.232`
3. 查 docker logs：`docker compose -f /opt/ai-video/deploy/lighthouse/docker-compose.prod.yml logs --tail=200 backend`
4. 修代码后跑新的 tag 推送，避免 amend 旧 commit

如果 transfer 失败：

1. 先下载 `release-transfer-<SHA>-<run>-<attempt>` evidence，区分 `probe`、upload、stage、receipt 或 cleanup 终态；receipt 不含 URL/secret。
2. 禁止直接创建 `releases-<SHA>` 或手工把 `.incoming-*` 改名；先核对 state marker、manifest SHA、run/attempt 和 current/previous/container 引用。
3. 只有明确的新授权可选择 `resume_transfer=true`。原 run 不自动 retry；COS lifecycle 负责过期对象，人工删除必须绑定 exact prefix。
4. stage-only 与失败路径不得留下 active/final release。deploy 补偿 cleanup 可能需要 staging Environment 的第二次人工批准；若整个 workflow 被取消、该批准被拒绝，或 gate 检测到 final/process/container/marker 歧义，GitHub 不得宣称已清理，必须使用 evidence 中的精确身份执行受限手工 cleanup。任何状态不明都停止自动处置并进入人工恢复。
