---
title: AI Video Pipeline 项目整合优化方案
doc_type: architecture
module: project-governance
topic: integrated-optimization-plan
status: review
created: 2026-05-01
updated: 2026-05-01
owner: self
source: ai+human
---

# AI Video Pipeline 项目整合优化方案

**整合来源：**
- `2026-04-30_audit-api-matrix.md` — API 路由鉴权矩阵
- `2026-04-30_full-stack-audit-report.md` — 全栈与目录治理审计
- `project-deep-vulnerability-audit-2026-05-01.md` — 深层脆弱点审计（反直觉挖掘）
- `project-full-audit-report-2026-05-01.md` — 全栈深度审计

**整合原则：**
1. 去重：同一问题的多份报告描述合并为一条
2. 判定：每个问题标注"必须修复"、"建议修复"、"暂不处理（需讨论）"
3. 排序：按 P0→P1→P2 优先级，同优先级按依赖关系排序（先修基础设施，再修上层）
4. 可执行：每条给出具体文件路径、代码位置、修复思路、验收标准

---

## 一、问题全景图（去重后）

四份报告原始条目约 **60+ 条**，去重合并后为 **38 条**，按优先级分布：

| 优先级 | 数量 | 核心主题 |
|--------|------|----------|
| P0 | 12 | 安全漏洞、系统级 bug、数据丢失风险 |
| P1 | 16 | 架构债务、性能瓶颈、运维隐患 |
| P2 | 10 | 可维护性、体验优化、工程化 |

---

## 二、P0 致命问题（必须修复，本周内）

### P0-1: `_get_override` 无限递归 — D10 路由机制完全失效
- **来源：** 深度脆弱点审计
- **位置：** `src/graph/routing.py:34-36`
- **判定：** 🔴 必须修复
- **根因：** 函数体 `return _get_override().get(checkpoint_key)` 递归调用自身，缺少参数导致 `TypeError`
- **修复：** 改为 `return _HUMAN_REVIEW_OVERRIDE.get().get(checkpoint_key)`
- **工作量：** 1 行代码
- **验收：** submit_review 后 pipeline 能正常 resume，不再抛 TypeError

### P0-2: 错误降级包装器产生"幽灵状态"
- **来源：** 深度脆弱点审计
- **位置：** `src/graph/pipeline.py:45-86`
- **判定：** 🔴 必须修复
- **根因：** 节点异常后返回缺失输出键的 dict，下游节点在错误/空数据上继续执行，产出无意义视频
- **修复：** 降级包装器返回安全默认值 + 设置 `_degraded=True`，路由函数检查到 degraded 直接导向 `__end__`
- **工作量：** ~30 行
- **验收：** 任一节点异常后 pipeline 终止，不继续执行下游

### P0-3: `safe_execute` fallback 伪装成功 — 系统性故障被完全隐藏
- **来源：** 深度脆弱点审计
- **位置：** `src/skills/base.py:150`
- **判定：** 🔴 必须修复
- **根因：** 所有重试耗尽后 fallback 返回 `success=True`，调用方无法区分真实成功与降级数据
- **修复：** fallback 返回 `success=False`，或在 metadata 中显式标记 `is_fallback=True` + 调用方检查
- **工作量：** ~5 行（skill 基类）+ 所有调用方增加检查
- **验收：** API 全宕时 pipeline 报错而非产出 stub 视频

### P0-4: 失败步骤状态标记为 `"pending"` 而非 `"error"`
- **来源：** 深度脆弱点审计
- **位置：** `src/pipeline/step_runner.py:259`
- **判定：** 🔴 必须修复
- **根因：** 异常后 `step_data["status"] = "pending"`，用户永远看到"处理中"
- **修复：** 改为 `"error"`
- **工作量：** 1 行
- **验收：** 步骤失败时前端显示错误状态，轮询停止

### P0-5: SQLite fallback 在 async 中同步执行 — 事件循环阻塞
- **来源：** 深度脆弱点审计
- **位置：** `src/storage/repository.py:49-87`
- **判定：** 🔴 必须修复
- **根因：** SQLite 分支使用同步 `sqlite3` API，阻塞整个 asyncio 事件循环
- **修复：** 使用 `aiosqlite` 或 `asyncio.to_thread()` 包装
- **工作量：** ~20 行
- **验收：** PG 不可用时系统不卡死，其他请求正常响应

### P0-6: 生产密钥提交到 Git
- **来源：** 全栈深度审计
- **位置：** `deploy/lighthouse/.env.prod`
- **判定：** 🔴 必须修复（安全红线）
- **根因：** DEEPSEEK_API_KEY、POYO_API_KEY、PostgreSQL 密码等真实密钥在仓库中
- **修复：**
  1. 立即轮换所有暴露的 API Key
  2. `git filter-branch` 或 BFG 从 Git 历史彻底删除
  3. `.gitignore` 增加 `.env.prod`
  4. 部署时通过环境变量/SSM 注入
- **工作量：** 2h
- **验收：** `git log --all --full-history -- deploy/lighthouse/.env.prod` 无输出

### P0-7: `/api/assets/*` 全路由器无 API Key 鉴权
- **来源：** API 矩阵 + 全栈审计
- **位置：** `src/api_assets.py` 所有端点
- **判定：** 🔴 必须修复
- **根因：** 与主 API 鉴权策略不一致，上传/删除/品牌包 CRUD 全部裸奔
- **修复：** 挂载 `api_assets.router` 时增加 `dependencies=[Depends(verify_api_key)]`
- **工作量：** 1 行
- **验收：** 未带 Key 访问 `/api/assets/upload` 返回 401

### P0-8: SSRF — yt-dlp 接收用户可控 URL
- **来源：** 全栈与目录治理审计
- **位置：** `src/tools/video_downloader.py`
- **判定：** 🔴 必须修复
- **根因：** yt-dlp 支持 `file://`、内网协议等，可读取本地文件或访问元数据服务
- **修复：** 严格的 URL 白名单（仅 http/https + 公网段），禁止 `file://`、RFC1918、169.254.x.x
- **工作量：** ~30 行
- **验收：** `file:///etc/passwd` 和 `http://169.254.169.254` 均被拒绝

### P0-9: SSRF — Webhook 出站 URL 无过滤
- **来源：** 全栈与目录治理审计
- **位置：** `src/tools/webhook_manager.py`
- **判定：** 🔴 必须修复
- **根因：** webhook URL 可指向内网/元数据地址
- **修复：** 注册/发送前校验 URL，拒绝私有地址段
- **工作量：** ~20 行
- **验收：** 注册 `http://169.254.169.254/latest/meta-data` 失败

### P0-10: `thread_id` 仅 8 位 hex — 熵低 + 碰撞风险
- **来源：** 全栈与目录治理审计
- **位置：** `src/api.py` `start_pipeline`
- **判定：** 🔴 必须修复
- **根因：** `str(uuid.uuid4())[:8]` 仅 ~32 bit 随机性，高并发下碰撞概率不可忽略
- **修复：** 使用完整 UUID 或加密随机 128bit+
- **工作量：** 1 行
- **验收：** thread_id 长度 >= 32 字符

### P0-11: 前端持有真实 API Key — XSS/扩展可窃取
- **来源：** 全栈与目录治理审计
- **位置：** `web/src/components/api.ts`
- **判定：** 🔴 必须修复
- **根因：** `NEXT_PUBLIC_API_KEY` 进浏览器 bundle，localStorage/cookie 存储
- **修复：**
  - 演示环境：固定 Key 仅做演示标识，不承载真实权限
  - 生产环境：用 HttpOnly Cookie / BFF 代发 / 短时 token
- **工作量：** 需讨论方案（见下方"待讨论"）
- **验收：** 浏览器 Storage 中无长期明文管理员 Key

### P0-12: 密钥注入 `_inject_api_keys` 进程级覆盖 + `_clients.clear()` 惊群
- **来源：** 全栈与目录治理审计
- **位置：** `src/api.py:115-143`
- **判定：** 🔴 必须修复
- **根因：**
  1. `api_keys` 写入 `os.environ`，多并发请求互相覆盖
  2. 每次注入后 `_clients.clear()`，其他正在执行的请求连接池被拆除
- **修复：** 改为请求级上下文（`contextvar` 或显式传参），按 Key 哈希分桶缓存 client
- **工作量：** ~50 行
- **验收：** 并发两个不同 Key 的请求，各自使用正确的 Key 调用供应商

---

## 三、P1 高危问题（建议 2-4 周内修复）

### P1-1: `_active_threads` 无限增长 — 内存泄漏
- **来源：** 深度 + 全栈审计
- **位置：** `src/api.py:50`
- **判定：** 🟡 建议修复
- **根因：** 条目只增不减，数月后数万个僵尸线程
- **修复：** pipeline 完成/拒绝/失败后清理条目；或加 TTL（24h）定时清理
- **工作量：** ~20 行

### P1-2: `MemorySaver` 生产回退 = 状态定时炸弹
- **来源：** 深度 + 全栈审计
- **位置：** `src/graph/pipeline.py:236-259`
- **判定：** 🟡 建议修复（需确认生产配置）
- **根因：** PG 连接失败时静默回退到 MemorySaver，进程重启 = 所有状态丢失
- **修复：** 生产环境拒绝回退，直接报错；或强制要求 db_url
- **工作量：** ~5 行
- **⚠️ 需确认：** 生产环境当前是否配置了 `SUPABASE_DB_URL`？

### P1-3: 非原子文件写入 — 崩溃时状态截断丢失
- **来源：** 深度脆弱点审计
- **位置：** `src/pipeline/state_manager.py:85-89`
- **判定：** 🟡 建议修复
- **修复：** 先写 `.tmp` 文件，再 `replace()` 原子替换
- **工作量：** ~10 行

### P1-4: 双写一致性反模式 — "写时 FS 优先，读时 PG 优先"
- **来源：** 深度脆弱点审计
- **位置：** `src/pipeline/state_manager.py:102-154`
- **判定：** 🟡 建议修复
- **根因：** PG 恢复可用后可能读到比 FS 更旧的数据
- **修复：** 统一以 PG 为主存储，FS 仅作为 PG 完全不可用的缓存；或加版本号/时间戳取最新
- **工作量：** ~30 行

### P1-5: 文件上传全量读内存 — OOM 风险
- **来源：** 深度 + 全栈审计
- **位置：** `src/api.py`、`src/api_assets.py`
- **判定：** 🟡 建议修复
- **修复：** 流式分块写入（8KB chunks），限制最大上传大小（如 500MB）
- **工作量：** ~30 行

### P1-6: 前端轮询风暴 — 固定 2s 无退避
- **来源：** 深度 + 全栈审计
- **位置：** `web/src/components/StageProgress.tsx`
- **判定：** 🟡 建议修复
- **修复：** 指数退避（2s→4s→8s... 最大 30s），超过 10 次失败停止轮询并提示用户
- **工作量：** ~20 行

### P1-7: 限流器 `_rate_store.clear()` — 自我 DoS
- **来源：** 全栈与目录治理审计
- **位置：** `src/api.py:260-288`
- **判定：** 🟡 建议修复
- **根因：** 超过 1000 IP 时清空全部记录，攻击者可用伪造 IP 触发清理
- **修复：** LRU/TTL 单桶淘汰，只移除最久未使用的 IP
- **工作量：** ~30 行

### P1-8: `/api/media/*` 匿名可读 + 列表需 Key — "列表难、直链易"
- **来源：** API 矩阵 + 全栈审计
- **位置：** `src/api.py` `serve_media`
- **判定：** 🟡 建议修复
- **根因：** 知道路径即可直接拉取媒体，无需鉴权
- **修复方案（需讨论）：**
  - 方案 A：接受匿名可读，文档化威胁模型
  - 方案 B：媒体 URL 加短期签名 token（如 15 分钟有效）
  - 方案 C：媒体请求同样校验 API Key（但浏览器 `<video>`/`<img>` 无法带 Header）
- **⚠️ 需讨论：** 产品需求上是否允许匿名播放媒体？

### P1-9: `/telemetry/*` 无鉴权 — 运行指标泄露
- **来源：** API 矩阵 + 全栈审计
- **位置：** `src/telemetry_endpoint.py`
- **判定：** 🟡 建议修复
- **修复：** 增加 API Key 依赖，或限制为 localhost/Nginx 内网
- **工作量：** 1 行

### P1-10: 多 worker / 多副本 — 内存状态不共享
- **来源：** 全栈与目录治理审计
- **位置：** `src/api.py` 多处
- **判定：** 🟡 建议修复（架构层面）
- **根因：** `_active_threads`、`_rate_store`、`_background_tasks`、Webhook 表均为单进程内存，多 worker 时状态分裂
- **修复方案（需讨论）：**
  - 方案 A：单 worker + 外层扩展（简单但限制吞吐）
  - 方案 B：状态外置 Redis / PostgreSQL（正确但工程量大）
  - 方案 C：sticky session（折中，但 K8s 下复杂）
- **⚠️ 需讨论：** 当前生产部署是单 worker 还是多 worker？

### P1-11: `api.py` 单文件 1800+ 行 — 职责过重
- **来源：** 全栈深度审计
- **位置：** `src/api.py`
- **判定：** 🟡 建议修复（渐进式）
- **修复：** 按领域拆分为 `src/routers/pipeline.py`、`scenarios.py`、`fast_mode.py` 等
- **工作量：** 3-5 天（需要谨慎迁移，避免破坏现有端点）
- **⚠️ 需讨论：** 当前是否有其他开发者正在修改 api.py？拆分会引发大量 merge conflict

### P1-12: 前端 `page.tsx` 1000+ 行 — 无路由拆分
- **来源：** 全栈深度审计
- **位置：** `web/src/app/page.tsx`
- **判定：** 🟡 建议修复（渐进式）
- **修复：** 按场景拆分为独立页面（`app/s1/page.tsx`、`app/s2/page.tsx` 等）
- **工作量：** 3-5 天
- **⚠️ 需讨论：** 当前 SPA 模式是否是产品设计需求？还是技术债务？

### P1-13: 前端无全局状态管理 — 20+ useState
- **来源：** 全栈深度审计
- **位置：** `web/src/app/page.tsx`
- **判定：** 🟡 建议修复（但优先级可降低）
- **修复：** 引入 Zustand 管理全局状态
- **工作量：** 2-3 天
- **⚠️ 需讨论：** 当前 props drilling 是否已造成实际 bug？还是仅为代码异味？

### P1-14: `VIDEO_OUTPUT_DIR` 与 `_THREAD_INDEX_PATH` 路径不一致
- **来源：** 全栈与目录治理审计
- **位置：** `src/api.py`、`src/pipeline/state_manager.py`
- **判定：** 🟡 建议修复
- **根因：** thread 索引固定写仓库内 `output/`，而 `pipeline_states` 和媒体跟随 `VIDEO_OUTPUT_DIR`
- **修复：** `_THREAD_INDEX_PATH` 从 `OUTPUT_DIR` 派生
- **工作量：** ~5 行

### P1-15: Dockerfile 不包含 `strategy_source/` 和 `rendering/`
- **来源：** 全栈与目录治理审计
- **位置：** `Dockerfile.backend`
- **判定：** 🟡 建议修复
- **根因：** 精简镜像与本地全仓库行为不一致，策略配置静默缺失
- **修复：** Dockerfile 增加 COPY，或启动时校验缺失并 fail-fast
- **工作量：** ~10 行

### P1-16: Seedance 视频生成完全串行 — 5 个 clip 需 5 分钟
- **来源：** 深度脆弱点审计
- **位置：** `src/pipeline/s1_product_pipeline.py:708-776`
- **判定：** 🟡 建议修复
- **修复：** 使用 `asyncio.Semaphore(2)` + `asyncio.gather()` 实现有限并发（poyo.ai 限制并发为 2）
- **工作量：** ~20 行
- **效果：** 5 个 clip 从 ~5 分钟降到 ~1.5 分钟

---

## 四、P2 中危问题（建议 1-2 个月内处理）

### P2-1: 前端乐观更新不回滚
- **来源：** 深度脆弱点审计
- **位置：** `web/src/components/VideoWorkflow.tsx`
- **判定：** 🟢 建议修复
- **修复：** API 失败时回滚乐观更新的本地状态
- **工作量：** ~15 行

### P2-2: TTS 合并文本可能超过 poyo 200 字符限制 — 静默截断
- **来源：** 深度脆弱点审计
- **位置：** `src/pipeline/s1_product_pipeline.py:877-884`
- **判定：** 🟢 建议修复
- **修复：** 超长文本分片或截断告警
- **工作量：** ~10 行

### P2-3: `_try_save_metrics` 完全静默吞异常
- **来源：** 深度脆弱点审计
- **位置：** `src/graph/nodes.py:353-365`
- **判定：** 🟢 建议修复
- **修复：** `except Exception` 改为至少记录 warning 日志
- **工作量：** 3 行

### P2-4: `analytics_node` 同步 webhook 阻塞事件循环
- **来源：** 深度脆弱点审计
- **位置：** `src/graph/nodes.py:337`
- **判定：** 🟢 建议修复
- **修复：** `dispatch_sync` 改为 `dispatch_async`，或用 `asyncio.to_thread()` 包装
- **工作量：** ~5 行

### P2-5: 前端类型 any 泛滥
- **来源：** 全栈深度审计
- **位置：** `web/src/components/*.tsx`
- **判定：** 🟢 建议修复（渐进式）
- **修复：** 定义 API 响应类型接口，逐步替换 any
- **工作量：** 持续进行，每次修改文件时顺手补类型

### P2-6: 无前端测试
- **来源：** 全栈深度审计
- **位置：** `web/`
- **判定：** 🟢 建议修复
- **修复：** 配置 Vitest + React Testing Library，为核心组件补测试
- **工作量：** 1-2 天（配置）+ 持续补充

### P2-7: 前后端类型不同步
- **来源：** 全栈深度审计
- **位置：** 全局
- **判定：** 🟢 建议修复
- **修复：** 从 Pydantic 模型自动生成 TypeScript 类型（`datamodel-code-generator` 或 OpenAPI → `openapi-typescript`）
- **工作量：** 1 天配置 + 持续同步

### P2-8: 根目录大 tar 文件与散落文档
- **来源：** 全栈深度审计
- **位置：** 根目录
- **判定：** 🟢 建议修复
- **修复：** `lute-ai-video-backend.tar` 移入 `archive/` 或 `tmp/`，根目录 MD 归档到 `plan/`
- **工作量：** 30 分钟

### P2-9: 无数据库迁移管理
- **来源：** 全栈深度审计
- **位置：** `src/storage/`
- **判定：** 🟢 建议修复
- **修复：** 引入 Alembic 管理 schema 变更
- **工作量：** 1 天

### P2-10: 日志中对密钥脱敏不足
- **来源：** 全栈与目录治理审计
- **位置：** 全局
- **判定：** 🟢 建议修复
- **修复：** structlog 处理器中过滤 `sk-`、API Key 等敏感字段
- **工作量：** ~20 行

---

## 五、优化执行路线图

### Phase 0: 止血（本周，1-2 天）

只做 P0 中的单行/小修复，立即止损：

| 编号 | 任务 | 文件 | 预估时间 |
|------|------|------|----------|
| P0-1 | 修复 `_get_override` 递归 | `routing.py` | 5 分钟 |
| P0-4 | 失败步骤标记 `"error"` | `step_runner.py` | 5 分钟 |
| P0-5 | SQLite fallback 异步化 | `repository.py` | 2 小时 |
| P0-6 | 轮换泄露密钥 + 从 Git 删除 | 外部控制台 | 2 小时 |
| P0-7 | api_assets 增加鉴权 | `api.py` | 5 分钟 |
| P0-10 | thread_id 用完整 UUID | `api.py` | 5 分钟 |

### Phase 1: 安全硬化（下周，3-5 天）

| 编号 | 任务 | 文件 | 预估时间 |
|------|------|------|----------|
| P0-8 | yt-dlp URL 白名单 | `video_downloader.py` | 4 小时 |
| P0-9 | Webhook 出站过滤 | `webhook_manager.py` | 2 小时 |
| P0-11 | 前端密钥模型重构 | `api.ts` + 后端 | 需讨论方案 |
| P0-12 | 密钥注入上下文化 | `api.py` | 1 天 |
| P0-2 | 降级包装器返回安全默认值 | `pipeline.py` | 4 小时 |
| P0-3 | fallback 显式标记失败 | `base.py` + 调用方 | 4 小时 |
| P1-7 | 限流器重写 | `api.py` | 4 小时 |

### Phase 2: 数据与状态治理（第 3-4 周）

| 编号 | 任务 | 文件 | 预估时间 |
|------|------|------|----------|
| P1-1 | `_active_threads` TTL 清理 | `api.py` | 4 小时 |
| P1-2 | 禁止 MemorySaver 生产回退 | `pipeline.py` | 1 小时 |
| P1-3 | 原子文件写入 | `state_manager.py` | 2 小时 |
| P1-4 | 双写一致性修复 | `state_manager.py` | 4 小时 |
| P1-5 | 流式文件上传 | `api.py`, `api_assets.py` | 4 小时 |
| P1-14 | thread 索引路径统一 | `api.py` | 1 小时 |
| P1-15 | Dockerfile 补全 | `Dockerfile.backend` | 2 小时 |

### Phase 3: 性能与架构（第 5-8 周）

| 编号 | 任务 | 文件 | 预估时间 |
|------|------|------|----------|
| P1-6 | 轮询指数退避 | `StageProgress.tsx` | 2 小时 |
| P1-16 | Seedance 并发生成 | `s1_product_pipeline.py` | 4 小时 |
| P1-11 | api.py 拆分 router（渐进） | `src/routers/` | 3-5 天 |
| P1-12 | 前端路由拆分（渐进） | `web/src/app/` | 3-5 天 |
| P1-8 | 媒体访问策略（需讨论） | `api.py` | 需讨论 |
| P1-10 | 多 worker 状态共享（需讨论） | 架构层 | 需讨论 |

### Phase 4: 工程化（持续）

| 编号 | 任务 | 说明 |
|------|------|------|
| P2-5 | 类型补全 | 每次改代码顺手补 |
| P2-6 | 前端测试 | 先配 Vitest，核心组件优先 |
| P2-7 | 前后端类型同步 | OpenAPI → TS 自动生成 |
| P2-9 | Alembic 迁移 | 新表/改表必须通过迁移 |
| P2-10 | 日志脱敏 | structlog processor |

---

## 六、待讨论事项（需要你的决策）

以下问题的修复方案涉及产品决策或架构方向，需要确认：

### ❓ 讨论 1: 生产部署模式
**问题：** P1-2（MemorySaver 回退）、P1-10（多 worker 状态共享）的修复方向取决于部署模式。
- 当前生产是单 worker（`uvicorn` 无 `--workers`）还是多 worker？
- 是否使用了 K8s 多副本？
- `SUPABASE_DB_URL` 在生产环境是否稳定配置？

**我的建议：** 如果当前是单 worker + PG 稳定，P1-2 和 P1-10 的紧迫性可降低；如果是多 worker，必须尽快外置状态到 Redis/PG。

### ❓ 讨论 2: 媒体访问策略
**问题：** P1-8（`/api/media/*` 匿名可读）。
- 产品设计是否要求"知道链接就能播放"？（类似 S3 presigned URL）
- 还是必须鉴权后才能播放？

**我的建议：**
- 如果是公开分享场景：保持匿名可读，但加短期签名 token（15 分钟）防止长期直链泄露
- 如果是内部系统：所有媒体请求带 API Key，前端通过 BFF 代理获取

### ❓ 讨论 3: 前端密钥模型
**问题：** P0-11（前端持有真实 API Key）。
- 当前固定 Demo Key `ai_video_demo_2026` 的用途是什么？
- 是否有真实用户需要各自独立的 Key？

**我的建议：**
- 如果只是演示/内部工具：保持固定 Key，但将其权限限制为只读/生成，禁止删除/发布
- 如果是多租户产品：必须废除前端持 Key 模式，改为 JWT/Session

### ❓ 讨论 4: api.py 拆分时机
**问题：** P1-11（api.py 1800+ 行拆分）。
- 当前是否有其他开发者正在修改 api.py？
- 是否即将添加新端点？

**我的建议：**
- 如果有并发的 feature 开发，等当前批次合并后再拆分，避免大量 conflict
- 如果暂时没有大改动，可以立即拆分

### ❓ 讨论 5: 前端路由拆分
**问题：** P1-12（page.tsx 拆分为多页面）。
- 当前 SPA 模式（所有场景在一个页面内切换）是否是产品设计需求？
- 还是仅因为开发时未使用 Next.js App Router？

**我的建议：**
- 如果场景切换需要保持状态（如正在生成的视频），SPA 有其合理性
- 可以考虑"伪路由"——URL hash 变化对应不同场景，保持 SPA 体验的同时支持浏览器前进/后退

---

## 七、验收标准汇总

| 检查项 | 验收命令/方法 |
|--------|---------------|
| P0-1 修复 | `pytest tests/test_routing.py -k d10` 通过 |
| P0-4 修复 | 触发步骤失败，确认 state 中 `"status": "error"` |
| P0-5 修复 | PG 断开时 API 响应时间 < 500ms（非阻塞） |
| P0-6 修复 | `git log --all -- deploy/lighthouse/.env.prod` 无输出 |
| P0-7 修复 | `curl -X POST /api/assets/upload` → 401 |
| P0-8 修复 | `curl /pipeline/start` 带 `file://` URL → 400 |
| P0-10 修复 | thread_id 长度 >= 32 |
| P1-6 修复 | 后端故障时前端轮询间隔从 2s 递增到 30s |
| P1-16 修复 | 5 个 clip 总耗时 < 2 分钟 |
| 全栈安全 | `curl` 不带 Key 访问所有 `/api/*` → 除 media 外全部 401 |

---

*整合完成时间：2026-05-01*
*来源报告：4 份审计报告，去重后 38 条优化项*
*待讨论项：5 项（需产品/架构决策）*
