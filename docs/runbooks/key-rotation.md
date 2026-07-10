---
title: API Key Rotation SOP
doc_type: workflow
module: operations
topic: secret-rotation
status: stable
created: 2026-05-16
updated: 2026-07-10
owner: self
source: human+ai
related:
  - file: ../../.kiro/plan/VULNERABILITIES-AND-PENDING-2026-05-15.md
    relation: implements
  - file: ../../deploy/lighthouse/.env.prod
    relation: runtime-secret-file
---

# API Key Rotation SOP

适用于 secret 泄露、授权变更、人员离职、90 天周期轮换或仓库/日志/会话可能记录过明文凭据的情况。所有 rotation 都是生产写操作，必须有明确 L4 授权、执行人和回滚窗口。

## 1. 密钥分类

| 类型 | 典型名称 | 存储位置 | 轮换方式 |
|---|---|---|---|
| Provider key | `DEEPSEEK_API_KEY`、`POYO_API_KEY`、`SILICONFLOW_API_KEY` | `deploy/lighthouse/.env.prod` | Provider 控制台签发新 key，更新环境并重建 backend，验证后 revoke 旧 key |
| 环境 API key | `API_KEY` | `deploy/lighthouse/.env.prod` | 生成新随机值，更新依赖方并重建 backend，验证后移除旧值 |
| Tenant API key | 数据库 `api_keys` 记录 | PostgreSQL | Admin 创建替代 key，安全分发，验证后 revoke 旧记录 |
| 测试 bundle key | `ai_video_demo_2026` 等固定测试值 | 代码/测试配置 | 生产默认禁用；不能作为正式 tenant key |

## 2. 已知事件与当前门禁

### 2026-05-17 provider 历史事件

历史审计记录显示一个 POYO provider key 曾进入 Git 历史。当前有效性未在本轮重新测试；在存在已完成 rotation 证据前，仍按 compromised 处理。不要从历史 commit 复制明文做验证。

### 2026-07-10 tenant key 文档事件

只读仓库审计确认，两份 tracked Markdown 曾包含同一个疑似生产 tenant application key，最早可追溯到 commit `9a4e004e346afa492e0de859a144970760f42a5c`。当前树已改为占位符，并新增回归测试阻止同类 `momcozy_mkt_*` 值再次进入 tracked Markdown。

本轮没有使用该值访问生产，也没有测试其当前有效性。由于 Git 历史仍保留旧内容，部署前必须：

1. 在 Admin Panel 按 tenant、key id、description 和 created_at 定位对应 key 记录；当前数据库只保存 hash，不能把 hash 前缀当作原 key 的 masked prefix。
2. 如果不能唯一定位，轮换受影响 tenant 的全部历史 key，而不是从 Git 历史恢复明文逐个试。
3. 创建替代 key，通过安全渠道分发并完成受保护只读 GET 验证。
4. revoke 旧 key，并从 Admin Panel/数据库状态确认其 lifecycle 为 revoked。

此事件本身不要求调用 DeepSeek、POYO 或 SiliconFlow，也不授权 provider generation。

## 3. 执行前检查

- [ ] 已记录 incident/rotation 范围、执行人、窗口和回滚人。
- [ ] 已确认要轮换的是 provider、环境还是 tenant key，不能混为一组。
- [ ] 已盘点 CI、浏览器配置、脚本、部署环境和人工持有者。
- [ ] 已确认不会把 secret 值写入终端录屏、聊天、日志、Markdown 或 Git diff。
- [ ] 涉及 provider 验证时，已取得独立 provider-call 授权和预算上限。

不要 `cat`、`grep` 或打印 `.env.prod` 的值。只能检查文件权限、变量名是否存在和容器是否加载预期变量名。

## 4. Provider 与环境 key 轮换

### 4.1 创建受控回滚副本

```bash
ssh -i ./ai_video.pem ubuntu@101.34.52.232
sudo install -d -m 0700 /root/ai-video-secret-backups
sudo install -m 0600 \
  /opt/ai-video/deploy/lighthouse/.env.prod \
  /root/ai-video-secret-backups/env.prod.$(date +%Y%m%d-%H%M%S)
```

回滚副本不得放在仓库目录，不得 commit，不得复制到普通聊天或工单附件。

### 4.2 先签发新 key

在对应 provider 控制台创建新 key；环境 `API_KEY` 使用本地安全终端生成随机值并直接写入密码管理器。新值只显示和传递一次，不写入执行记录。

### 4.3 更新环境并重建 backend

```bash
sudoedit /opt/ai-video/deploy/lighthouse/.env.prod
cd /opt/ai-video/deploy/lighthouse
sudo docker compose -f docker-compose.prod.yml up -d --force-recreate backend
sleep 15
curl -fsSk https://localhost/api/health | python3 -m json.tool >/dev/null
```

验收：`.env.prod` 仍为 `0600`，backend healthy，公开 health 未泄露 key、token、DSN 或私有路径。

### 4.4 验证与 revoke

- 环境 API key：只执行受保护的只读 GET，确认新 key 返回 200；确认依赖方切换后再移除旧值。
- Provider key：优先在 provider 控制台检查状态。任何真实 API 调用都需要独立 L4 provider-call 授权；默认不运行生成任务。
- 只有新 key 验证通过后才能 revoke 旧 key。旧 key revoke 后不可用回滚副本重新启用。

## 5. Tenant key 轮换

1. 在 `/admin/tenants/{tenant_id}` 创建新 key，填写明确 label 和过期日期；UI 默认 90 天，backend 对未传 expiry 的兼容请求也默认 90 天。
2. plaintext 只存入密码管理器并通过安全私聊交付，不进入群聊、邮件正文或文档。
3. 使用新 key 调用一个受保护的只读 GET，例如 `/api/dashboard/overview?days=7`。
4. 在 Admin Panel revoke 旧 key；如果 incident 范围不确定，revoke 该 tenant 下所有无法证明安全的历史 key。
5. 确认新 key 为 active、旧 key 为 revoked，并检查最近审计日志是否有异常来源。

不要从 Git 历史、shell history 或旧聊天中提取疑似泄露 key 来发送验证请求。

## 6. 完工证据

- [ ] rotation 范围与执行授权已记录。
- [ ] 新 key 已安全签发和分发。
- [ ] backend/tenant 只读验证通过。
- [ ] 旧 key 已 revoke，状态已回读。
- [ ] `.env.prod` 权限为 `0600`，回滚副本位于仓库外的 root-only 目录。
- [ ] 证据只包含 key 名、key id、description、状态、时间与 HTTP 状态码。
- [ ] 未记录 plaintext、hash、password、private key 或 provider response payload。
- [ ] 未经独立授权，没有执行 provider generation、publish、delivery 或业务写入。

## 7. 回滚

如果新 key 在旧 key revoke 前验证失败：恢复仓库外的最新 `env.prod` 回滚副本，重建 backend 并验证 health。不要 revoke 旧 key。

如果旧 key 已 revoke：不能通过恢复旧 `.env.prod` 回滚；必须修复新 key 配置或签发另一把新 key。
