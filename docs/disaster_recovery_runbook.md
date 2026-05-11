# Hermes-Evo 灾难恢复 Runbook

**适用场景**：生产 PG 数据丢失 / 主机磁盘故障 / 需要回滚到历史备份

---

## 一、备份策略

### 自动备份
- **频率**：每天 3:00 AM（UTC+8）
- **保留**：7 天滚动（最多 7 个备份点）
- **位置**：`/opt/ai-video-backups/{YYYY-MM-DD_HHMMSS}/`
- **内容**：
  - `pg_dump.jsonl` — PG 逻辑备份（JSON Lines 格式，63 行 ≈ 668 KB）
  - `output/` — 媒体文件目录（1107 files ≈ 1.3 GB）
  - `manifest.txt` — 备份元数据
- **日志**：`/var/log/hermes-backup.log`

### 手动备份（紧急）
```bash
sudo /opt/ai-video/scripts/backup_production.sh
```

---

## 二、恢复步骤（完整灾难恢复）

### 前置条件
- 新主机已部署 docker-compose（backend + frontend + nginx + rendering 容器运行中）
- PG 表结构已初始化（`src/storage/migrations/001_init.sql` + `api_keys` 表已创建）
- 有一个可用的备份目录（如 `/opt/ai-video-backups/2026-05-10_160753/`）

### 步骤 1：停止 backend 容器（避免写冲突）
```bash
cd /opt/ai-video/deploy/lighthouse
sudo docker-compose -f docker-compose.prod.yml stop backend
```

### 步骤 2：恢复 PG 数据
```bash
BACKUP_DIR="/opt/ai-video-backups/2026-05-10_160753"  # 改成实际备份时间戳

# 拷贝 restore 脚本 + dump 文件进容器
sudo docker cp /opt/ai-video/scripts/pg_restore_logical.py ai_video_backend:/tmp/
sudo docker cp "${BACKUP_DIR}/pg_dump.jsonl" ai_video_backend:/tmp/pg_dump.jsonl

# 启动 backend（只为了跑 restore 脚本，不对外服务）
sudo docker-compose -f docker-compose.prod.yml start backend
sleep 5

# 执行恢复（--truncate-first 会清空现有数据）
sudo docker exec ai_video_backend python3 /tmp/pg_restore_logical.py /tmp/pg_dump.jsonl --truncate-first
```

**预期输出**：
```json
{
  "tables": {
    "tenants": {"available": 1, "inserted": 1},
    "api_keys": {"available": 1, "inserted": 1},
    "admin_accounts": {"available": 1, "inserted": 1},
    "pipeline_states": {"available": 58, "inserted": 58},
    ...
  }
}
```

### 步骤 3：恢复媒体文件
```bash
# 方案 A：直接 docker cp（适合小文件）
sudo docker cp "${BACKUP_DIR}/output/." ai_video_backend:/app/output/

# 方案 B：rsync（适合大文件，增量）
sudo rsync -av --info=progress2 "${BACKUP_DIR}/output/" /opt/ai-video/output/
```

### 步骤 4：重启 backend + 验证
```bash
sudo docker-compose -f docker-compose.prod.yml restart backend
sleep 10

# 验证 API 健康
curl -k https://localhost/api/health | jq .

# 验证 tenant + key 数据恢复
curl -k -H "X-API-Key: momcozy_mkt_zfFCoM3IegCtA3CyJsmAgNBIc8g" \
  https://localhost/api/portfolio/?limit=3 | jq '.files | length'
```

**预期**：
- `/api/health` 返回 `{"status":"ok"}`
- portfolio 返回 3 个文件（证明 key 认证通过 + 媒体文件可访问）

---

## 三、部分恢复（只恢复特定表）

如果只需要恢复某个表（如 `api_keys` 被误删），修改 `pg_restore_logical.py` 的 `by_table` 循环：

```python
# 只恢复 api_keys
for table, rows in by_table.items():
    if table != "api_keys":
        continue
    # ... 执行 INSERT
```

或者手动从 `pg_dump.jsonl` 提取：
```bash
grep '"_table": "api_keys"' pg_dump.jsonl > api_keys_only.jsonl
# 然后用 pg_restore_logical.py 恢复这个单表文件
```

---

## 四、验证备份完整性（定期演练）

**建议频率**：每月 1 次

1. 选一个最新备份
2. 在**测试环境**（非生产）跑完整恢复流程
3. 验证：
   - PG 所有表行数与 manifest.txt 一致
   - 媒体文件数量与 manifest.txt 一致
   - 能用恢复后的 API key 调用创作 API
4. 记录演练结果到 `/opt/ai-video-backups/drill_log.txt`

---

## 五、常见问题

### Q: 恢复后 admin 账号密码忘了
A: 用 `scripts/create_admin.py` 重置密码（会覆盖现有账号）

### Q: 恢复后 API key 不工作（401）
A: 检查 `api_keys` 表是否恢复成功：
```bash
sudo docker exec ai_video_backend python3 -c "
import asyncio
async def main():
    from src.storage.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as c:
        rows = await c.fetch('SELECT tenant_id, description FROM api_keys')
        for r in rows:
            print(r['tenant_id'], r['description'])
asyncio.run(main())
"
```

### Q: 媒体文件恢复后 /works 页面还是空
A: 检查 `pipeline_states` 表是否恢复 + 文件路径是否匹配：
```bash
sudo docker exec ai_video_backend ls /app/output/renders/ | head
```

### Q: 备份脚本失败（cron 日志报错）
A: 查看 `/var/log/hermes-backup.log`，常见原因：
- 磁盘满（`df -h` 检查）
- backend 容器未运行（`docker ps` 检查）
- PG 连接失败（检查 `.env.prod` 的 `DATABASE_URL`）

---

## 六、紧急联系

- **Ops 负责人**：[填写钉钉 / 手机]
- **腾讯云 RDS 控制台**：[填写链接]（RDS 本身也有自动备份，可作为最后防线）
- **备份脚本源码**：`/opt/ai-video/scripts/backup_production.sh`
