---
title: Hermes-Evo 灾难恢复 Runbook
doc_type: workflow
module: operations
topic: production-backup-restore
status: stable
created: 2026-05-11
updated: 2026-07-10
owner: self
source: human+ai
---

# Hermes-Evo 灾难恢复 Runbook

**适用场景**：生产 PostgreSQL 数据丢失、主机磁盘故障、媒体目录损坏或需要回滚到已验证备份。

## 当前生产门禁

2026-07-10 只读审计确认：root cron 直接执行 `/opt/ai-video/scripts/backup_production.sh`，但 Lighthouse rsync 将该文件部署为 `0644`，日志持续出现 `Permission denied`。审计时没有确认到由该脚本生成的有效 AI Video 日备份。

因此，在以下四项形成新鲜证据前，正式部署状态为 `blocked`：

1. 新备份脚本已通过最小范围同步到生产。
2. root cron 已通过 `/bin/bash` 调用并核验唯一性。
3. 已手动生成一个 `status: complete` 的数据库与媒体全量备份。
4. `pg_dump_stats.json`、schema archive、JSONL 行数、checksum、manifest 和无 `.partial` 残留检查通过。
5. 同一备份已在隔离 PostgreSQL 中先恢复 schema、再恢复数据，并逐表核对行数。

## 一、备份策略

### 自动备份

- **频率**：每天 03:00（UTC+8）。
- **保留**：默认 15 天；可用 `RETENTION_DAYS` 调整。没有与 manifest hash 绑定的 `restore_verified.json` 时不执行删除；存在验证点后只清理其他过期 complete 目录，并始终保留最新的 restore-verified 恢复点。
- **位置**：`/opt/ai-video-backups/{YYYY-MM-DD_HHMMSS}/`。
- **原子性**：先写 `.{timestamp}.partial`，数据库与媒体校验通过后再原子重命名；失败会删除 partial，不会执行 retention cleanup。
- **互斥**：使用 `flock`，并发备份会 fail closed。
- **数据库一致性**：所有表在同一个 PostgreSQL `repeatable read`、只读事务中导出，避免跨表读取漂移。
- **schema 一致性边界**：`pg_schema.dump` 在数据事务完成后立即生成，但不能与 JSONL 数据共享同一事务。备份窗口内必须禁止 Alembic、DDL 和 schema deployment；违反该条件的备份不得作为恢复点。
- **媒体一致性边界**：`output/` 是在线文件快照，不与数据库共享事务。逐文件 SHA-256 能发现复制后损坏，但不能证明高写入期间数据库记录与媒体文件处于同一业务时点。首次基线备份、恢复点备份和恢复演练应在低写入窗口执行；需要严格 RPO 时先进入维护窗口并停止写流量。
- **内容**：
  - `pg_dump.jsonl`：PostgreSQL 逻辑备份。
  - `pg_dump_stats.json`：可机器解析的表级行数与文件大小统计。
  - `pg_schema.dump`：由与生产数据库同主版本的官方 PostgreSQL 客户端生成的 custom schema archive。
  - `pg_schema.list`：`pg_restore --list` 输出，用于校验 archive 可解析且包含全部必需表。
  - `pg_schema_signature_after.json`：schema archive 导出后的列签名；必须与数据事务内的签名一致。
  - `output/`：媒体文件目录快照。
  - `media_manifest.json`：媒体文件逐文件大小与 SHA-256。
  - `manifest.txt`：镜像、行数、文件数、SHA-256 与完成状态。
- **日志**：`/var/log/hermes-backup.log`。

### 安装或修复 cron

这是生产 crontab 写操作，只能在明确 L4 授权后执行：

```bash
sudo MIGRATE_LEGACY=1 RETENTION_DAYS=15 \
  /bin/bash /opt/ai-video/scripts/install_backup_cron.sh
sudo crontab -l | grep -F 'ai-video-production-backup'
```

安装器会把运行时脚本复制到 root-owned 的 `/usr/local/libexec/ai-video-backup/`，避免 root cron 执行可由部署用户改写的仓库文件。`MIGRATE_LEGACY=1` 只用于本次已知旧 cron 迁移；缺少该显式开关时，安装器发现旧无 marker 行会 fail closed。

验收：只出现一行 AI Video 备份任务，命令包含 `RETENTION_DAYS=15 /bin/bash /usr/local/libexec/ai-video-backup/backup_production.sh`；其他 root cron 行保持不变，日志文件模式为 `0600`。

### 手动备份

这是生产数据库和文件系统读取、备份目录写入及过期备份清理操作，只能在明确 L4 授权后执行：

```bash
sudo RETENTION_DAYS=15 \
  /bin/bash /usr/local/libexec/ai-video-backup/backup_production.sh
```

### 完整性核验

```bash
LATEST=$(sudo find /opt/ai-video-backups \
  -mindepth 1 -maxdepth 1 -type d \
  -name '20??-??-??_??????' -print | sort | tail -1)

sudo test -n "$LATEST"
sudo test -s "$LATEST/pg_dump.jsonl"
sudo test -s "$LATEST/pg_dump_stats.json"
sudo test -s "$LATEST/pg_schema.dump"
sudo test -s "$LATEST/pg_schema.list"
sudo test -s "$LATEST/pg_schema_signature_after.json"
sudo test -s "$LATEST/media_manifest.json"
sudo test -s "$LATEST/manifest.txt"
sudo python3 -m json.tool "$LATEST/pg_dump_stats.json" >/dev/null
sudo python3 -m json.tool "$LATEST/media_manifest.json" >/dev/null
sudo grep -Fx 'project: ai-video' "$LATEST/manifest.txt"
sudo grep -Fx 'status: complete' "$LATEST/manifest.txt"
EXPECTED_PG_SHA=$(sudo awk -F': ' '$1 == "pg_dump_sha256" {print $2}' "$LATEST/manifest.txt")
ACTUAL_PG_SHA=$(sudo sha256sum "$LATEST/pg_dump.jsonl" | awk '{print $1}')
EXPECTED_STATS_SHA=$(sudo awk -F': ' '$1 == "pg_dump_stats_sha256" {print $2}' "$LATEST/manifest.txt")
ACTUAL_STATS_SHA=$(sudo sha256sum "$LATEST/pg_dump_stats.json" | awk '{print $1}')
EXPECTED_SCHEMA_SHA=$(sudo awk -F': ' '$1 == "pg_schema_sha256" {print $2}' "$LATEST/manifest.txt")
ACTUAL_SCHEMA_SHA=$(sudo sha256sum "$LATEST/pg_schema.dump" | awk '{print $1}')
EXPECTED_SCHEMA_LIST_SHA=$(sudo awk -F': ' '$1 == "pg_schema_list_sha256" {print $2}' "$LATEST/manifest.txt")
ACTUAL_SCHEMA_LIST_SHA=$(sudo sha256sum "$LATEST/pg_schema.list" | awk '{print $1}')
EXPECTED_SCHEMA_SIGNATURE_AFTER_SHA=$(sudo awk -F': ' '$1 == "pg_schema_signature_after_sha256" {print $2}' "$LATEST/manifest.txt")
ACTUAL_SCHEMA_SIGNATURE_AFTER_SHA=$(sudo sha256sum "$LATEST/pg_schema_signature_after.json" | awk '{print $1}')
EXPECTED_MEDIA_SHA=$(sudo awk -F': ' '$1 == "media_manifest_sha256" {print $2}' "$LATEST/manifest.txt")
ACTUAL_MEDIA_SHA=$(sudo sha256sum "$LATEST/media_manifest.json" | awk '{print $1}')
test "$EXPECTED_PG_SHA" = "$ACTUAL_PG_SHA"
test "$EXPECTED_STATS_SHA" = "$ACTUAL_STATS_SHA"
test "$EXPECTED_SCHEMA_SHA" = "$ACTUAL_SCHEMA_SHA"
test "$EXPECTED_SCHEMA_LIST_SHA" = "$ACTUAL_SCHEMA_LIST_SHA"
test "$EXPECTED_SCHEMA_SIGNATURE_AFTER_SHA" = "$ACTUAL_SCHEMA_SIGNATURE_AFTER_SHA"
test "$EXPECTED_MEDIA_SHA" = "$ACTUAL_MEDIA_SHA"
PG_CLIENT_IMAGE=$(sudo awk -F': ' '$1 == "pg_client_image" {print $2}' "$LATEST/manifest.txt")
PG_CLIENT_SOURCE_TAG=$(sudo awk -F': ' '$1 == "pg_client_source_tag" {print $2}' "$LATEST/manifest.txt")
PG_SERVER_MAJOR=$(sudo awk -F': ' '$1 == "pg_server_major" {print $2}' "$LATEST/manifest.txt")
[[ "$PG_SERVER_MAJOR" =~ ^[0-9]+$ ]]
[[ "$PG_CLIENT_SOURCE_TAG" == "postgres:${PG_SERVER_MAJOR}" ]]
[[ "$PG_CLIENT_IMAGE" =~ ^postgres@sha256:[0-9a-f]{64}$ ]]
sudo docker image inspect "$PG_CLIENT_IMAGE" >/dev/null
[[ "$(sudo docker image inspect "$PG_CLIENT_SOURCE_TAG" --format='{{index .RepoDigests 0}}')" == "$PG_CLIENT_IMAGE" ]]
sudo cat "$LATEST/pg_schema.dump" \
  | sudo docker run --rm -i --network none "$PG_CLIENT_IMAGE" pg_restore --list \
  | sudo cmp - "$LATEST/pg_schema.list"
sudo python3 - "$LATEST/pg_schema.list" <<'PY'
import sys
from pathlib import Path

expected = {
    "tenants", "admin_accounts", "api_keys", "admin_sessions", "threads",
    "pipeline_states", "brand_packages", "influencers", "video_metrics",
    "publish_logs", "error_logs", "audit_logs",
}
actual = set()
for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    parts = line.split()
    if len(parts) >= 7 and parts[3:5] == ["TABLE", "public"]:
        actual.add(parts[5])
if expected - actual:
    raise SystemExit("schema archive is missing required tables")
PY
if sudo test -f "$LATEST/restore_verified.json"; then
  sudo python3 - "$LATEST" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

backup_dir = Path(sys.argv[1])
marker = json.loads((backup_dir / "restore_verified.json").read_text(encoding="utf-8"))
manifest_sha = hashlib.sha256((backup_dir / "manifest.txt").read_bytes()).hexdigest()
if marker.get("status") != "passed" or marker.get("manifest_sha256") != manifest_sha:
    raise SystemExit("restore verification marker is invalid")
PY
else
  echo "backup integrity passed, but no restore-verified marker exists"
fi
sudo python3 - "$LATEST" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

backup_dir = Path(sys.argv[1])
output_dir = backup_dir / "output"
manifest = json.loads((backup_dir / "media_manifest.json").read_text())
entries = manifest.get("files")
if not isinstance(entries, list):
    raise SystemExit("media manifest files must be a list")

declared = set()
declared_size = 0
for entry in entries:
    if not isinstance(entry, dict):
        raise SystemExit("media manifest entry must be an object")
    relative = Path(str(entry.get("path", "")))
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        raise SystemExit("unsafe media manifest path")
    media_file = output_dir / relative
    if media_file.is_symlink() or not media_file.is_file():
        raise SystemExit("media manifest references a missing or unsafe file")

    digest = hashlib.sha256()
    with media_file.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    size = media_file.stat().st_size
    if size != entry.get("size_bytes") or digest.hexdigest() != entry.get("sha256"):
        raise SystemExit("media file size or checksum mismatch")
    declared.add(relative.as_posix())
    declared_size += size

actual = set()
for path in output_dir.rglob("*"):
    if path.is_symlink():
        raise SystemExit("media snapshot contains a symlink")
    if path.is_file():
        actual.add(path.relative_to(output_dir).as_posix())
if actual != declared:
    raise SystemExit("media manifest file set mismatch")
if manifest.get("file_count") != len(declared):
    raise SystemExit("media manifest file count mismatch")
if manifest.get("total_size_bytes") != declared_size:
    raise SystemExit("media manifest total size mismatch")
PY
test -z "$(sudo find /opt/ai-video-backups -maxdepth 1 -type d -name '.*.partial' -print -quit)"
```

验收：所有校验命令成功，最后一条没有输出。首次有效生产备份还必须在隔离环境按 `media_manifest.json` 逐文件重算 SHA-256，并完成一次数据库恢复演练；只校验 manifest 文件自身的 checksum 不能替代逐文件复核。备份目录路径、manifest checksum 和备份开始/结束日志要写入部署证据；不要记录任何数据库内容或 secret。

## 二、完整恢复

恢复会写生产数据库和媒体目录。必须先停止写流量、记录目标备份、准备回滚点，并取得单独 L4 授权。

### 前置条件

- 新主机已部署 backend、frontend、nginx 与 rendering 容器。
- 目标 PostgreSQL 数据库存在、为空，且没有应用连接；不得把 schema archive 直接覆盖到非空生产库。
- `deploy/lighthouse/.env.prod` 已通过受控 secret 流程更新为目标数据库 DSN，但不得打印或 diff 其内容；backend 要在恢复完成后 force-recreate 才能加载新值。
- 已按 manifest 的 `pg_client_image` 准备同主版本官方 PostgreSQL 客户端镜像。
- 目标目录通过上面的完整性核验。
- 已确认恢复点、RPO 影响和业务负责人 sign-off。

### 步骤 1：停止公网入口和 backend

```bash
cd /opt/ai-video/deploy/lighthouse
sudo docker compose -f docker-compose.prod.yml stop nginx backend
```

### 步骤 2：通过 fail-closed wrapper 恢复 PostgreSQL

```bash
set -Eeuo pipefail
BACKUP_DIR="/opt/ai-video-backups/<YYYY-MM-DD_HHMMSS>"
EXPECTED_RESTORE_HOST='<new-empty-rds-host>'

# 交互输入空目标库 DSN；不回显、不写日志，wrapper 会核对 hostname 和 public 表数为 0。
read -rsp 'Target PostgreSQL DATABASE_URL: ' TARGET_DATABASE_URL
echo
printf '%s\n' "$TARGET_DATABASE_URL" \
  | sudo env \
      EXPECTED_RESTORE_HOST="$EXPECTED_RESTORE_HOST" \
      RESTORE_SCOPE=production \
      RESTORE_CONFIRMATION=RESTORE_EMPTY_DATABASE \
      ALLOW_PRODUCTION_RESTORE=1 \
      PRODUCTION_RESTORE_CONFIRMATION=I_ACKNOWLEDGE_PRODUCTION_DATABASE_RESTORE \
      /bin/bash /opt/ai-video/scripts/restore_backup_database.sh "$BACKUP_DIR"
unset TARGET_DATABASE_URL
```

wrapper 会验证备份 checksum、digest-pinned PostgreSQL 客户端、目标 hostname、空库状态和 schema list；schema 使用 `--single-transaction`，数据导入使用单独事务，随后逐表核对 12 表行数并写入与 manifest hash 绑定的 `restore_verified.json`。它不会启动 backend，也不允许 `--truncate-first`。schema archive 是恢复生产历史类型、约束、索引和 extension 的单一证据，不得用当前仓库的 `001_init.sql` 替代。

### 步骤 3：恢复媒体

```bash
BACKEND_IMAGE_ID=$(sudo docker inspect ai_video_backend --format='{{.Image}}')
sudo docker run --rm \
  --network none \
  --read-only \
  --tmpfs /tmp \
  --user 0:0 \
  --volumes-from ai_video_backend \
  -v "$BACKUP_DIR:/backup:ro" \
  --entrypoint sh \
  "$BACKEND_IMAGE_ID" \
  -eu -c 'cp -a /backup/output/. /app/output/'
```

### 步骤 4：保持入口关闭并执行内部验证

```bash
sudo docker compose -f docker-compose.prod.yml up -d --no-deps --force-recreate backend
sleep 15
sudo docker exec ai_video_backend python3 -c "
import json, urllib.request
payload = json.load(urllib.request.urlopen('http://127.0.0.1:8001/health'))
assert payload['status'] == 'ok'
"

# 核对 restore 输出、表行数、媒体文件数和 manifest 后才恢复入口。
sudo docker compose -f docker-compose.prod.yml start nginx
sleep 5
curl -fsSk https://localhost/api/health | python3 -m json.tool

RECOVERY_API_KEY='<production-api-key>'
curl -fsSk \
  -H "X-API-Key: $RECOVERY_API_KEY" \
  'https://localhost/api/portfolio/?limit=3' \
  | python3 -m json.tool >/dev/null
unset RECOVERY_API_KEY
```

验收：nginx 在数据库和媒体恢复、内部 health、行数与 manifest 核对完成前始终停止；恢复入口后 public health 为 `ok`，受保护只读接口认证成功。不得把 key、响应中的业务数据或 dump 内容写入证据文件。

## 三、恢复演练

建议每月在隔离环境完成一次：

1. 选择最新的 `status: complete` 备份。
2. 校验 stats、JSONL 行数、checksum 与 media count。
3. 在空的非生产数据库先执行 `pg_restore --schema-only`，再导入 JSONL 数据。
4. 运行 health 与受保护只读接口检查。
5. 将时间、备份目录、结果和问题记录到受控运维记录，不写 secret。

生产机上的 `drill_log.txt` 不能替代隔离环境恢复证据。

## 四、常见故障

### cron 日志出现 `Permission denied`

根因通常是部署同步把脚本模式设为 `0644`，而 cron 直接执行脚本。不要只做临时 `chmod +x`，因为下次 rsync 会再次覆盖。运行 `install_backup_cron.sh`，确认 cron 显式使用 `/bin/bash`。

### 备份失败或留下 partial

检查：

```bash
sudo tail -100 /var/log/hermes-backup.log
sudo df -h
sudo docker ps --filter name=ai_video_backend
sudo find /opt/ai-video-backups -maxdepth 1 -type d -name '.*.partial' -print
```

失败脚本会自动删除本轮 partial；如果进程被强制终止后仍有 partial，先确认没有备份进程和锁持有者，再按独立清理授权处理。不要把 partial 当作恢复点。

### 恢复后 API key 返回 401

先核对 `api_keys` 表是否被恢复及 key 是否已过期或撤销。诊断输出只显示 tenant、key id、description 和状态，不得打印 plaintext key、hash 或伪装成原 key 前缀的 hash preview。

### 恢复后 `/works` 为空

确认 `pipeline_states` 已恢复，并检查容器内 `/app/output/renders/` 与 manifest 的媒体计数是否一致。

## 五、回滚与升级

- 备份脚本失败：保留所有既有完整备份，修复原因后重新执行；不得先清理旧备份。
- 恢复失败：停止 backend，保留失败现场，按预先记录的恢复前备份回滚。
- 数据库 dump 本身使用单个 `repeatable read` 事务，但数据库 dump 与媒体快照不是同一事务点；高写入期恢复前要评估时间差，严格恢复点应先停止写流量。
- RDS 平台备份是最后防线，不能替代本项目的应用级逻辑备份与恢复演练。

## 六、责任人

- **Ops 负责人**：在受控通讯录维护，不写入公开仓库。
- **腾讯云 RDS 控制台**：由授权运维账号访问。
- **脚本源码**：`scripts/backup_production.sh`、`scripts/install_backup_cron.sh`、`scripts/pg_dump_logical.py`、`scripts/pg_restore_logical.py`。
