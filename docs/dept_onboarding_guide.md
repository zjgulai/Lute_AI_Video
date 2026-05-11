---
name: dept-onboarding-guide
description: 部门接入 Hermes-Evo AI 视频创作平台的 SOP。覆盖 admin 创建 tenant、发 API key、部门同事粘贴 key 进入创作流程的完整步骤。当新部门要接入时使用。
---

# Hermes-Evo 部门接入指南

**适用于**：路特集团内部任何想用 AI 视频创作平台的部门  
**前置条件**：你联系了 admin（运营方）拿到了部门专属 API key  
**生效环境**：`https://101.34.52.232`

---

## 一、Admin 操作（运营侧，每个新部门做一次）

### 1.1 登录 Admin Panel

1. 打开 `https://101.34.52.232/admin/login`
2. 用 admin 账号登录（当前账号：`zhoujianaaa123@gmail.com`）
3. 自动跳到 `/admin/dashboard`

### 1.2 创建租户（tenant）

1. 顶 Nav 点 **租户** → 进入 `/admin/tenants`
2. 点右上角 **创建租户**
3. 填写：
   - **tenant_id**（小写字母 + 数字 + 连字符，3-32 位，唯一）—— 推荐用部门英文短码，如 `momcozy-marketing` / `momcozy-brand` / `momcozy-ecom`
   - **display_name**（中文部门全称）—— 如「Momcozy 市场营销部」
4. 点保存 → 列表出现新租户

### 1.3 发 API key

1. 列表里点新租户名 → 进入 `/admin/tenants/{tenant_id}`
2. 找到 **API Keys** 区块，点 **创建 Key**
3. 填：
   - **description**（描述用途）—— 如「市场部张三 - 投放 TikTok 短视频」
   - **expires_at**（可选过期时间）—— 推荐 90 天
4. 点保存 → **plaintext key 只显示一次**，立即复制
5. 通过钉钉私聊（不要群里）发给部门负责人

### 1.4 撤销 key（员工离职 / key 泄露）

1. 同一个 tenant 详情页 → API Keys 列表
2. 找到对应 key → 点 **撤销**
3. 确认后 key 立即失效，所有用 该 key 的请求会返回 401

---

## 二、部门同事操作（每人首次接入）

### 2.1 拿到 key

通过钉钉私聊收到形如 `momcozy_mkt_zfFCoM3IegCtA3CyJsmAgNBIc8g` 的字符串。**这就是你的 X-API-Key**。

### 2.2 首次访问平台

1. 打开 `https://101.34.52.232`（建议 Chrome/Edge）
2. 看到品牌欢迎页 → 点「**开始创作**」
3. 弹出 **「需要 API Key 才能创作」** 模态
4. 在密码输入框粘贴你的 key
5. 点「进入创作」按钮 → 几秒验证 → 自动消失模态

### 2.3 安全提醒

- key 只保存在你**当前浏览器**（localStorage），换浏览器要重新输
- 不要把 key 贴到聊天群、截图、邮件正文
- 如果不小心泄露，立刻钉钉联系 admin 撤销
- 离开公司前主动让 admin 撤销自己的 key

### 2.4 修改 key（如果换 key）

1. 顶 Nav 点 ⚙️ **设置** → 进入 `/settings`
2. 滚到 **API Key** 字段
3. 改填新 key → 点「测试连接」确认绿色「Connected」
4. 点「保存」

---

## 三、常见问题

### Q: 输入 key 后还是提示「Key 无效」

可能原因：
- key 复制时多了空格 / 换行
- key 过期了（超过 admin 设的 expires_at）
- key 被 admin 撤销了
- 浏览器 localStorage 被禁用（隐私模式）

解决：联系 admin 重新发 key，或换正常浏览器。

### Q: 创作页面 401 Unauthorized

- 确认 SettingsPanel 里 key 字段确实填了你的 key（不是空）
- 测试连接看返回什么状态码
- 如果一直 401，可能 key 已过期 / 撤销

### Q: 我的部门已经有 key 了，但不知道是谁分到我

部门负责人统一管理，问他要。如果他也不知道，让 admin 在 `/admin/tenants/{tenant_id}` 看 key 列表。

### Q: 一个部门能有几个 key？

无限制。建议：
- 每个员工一把独立 key（方便单人撤销，不影响其他人）
- 或部门共享 1 个 key（简单但泄露后必须重发所有人）
- 不要把所有员工合 1 把测试用 key 一起用，无法审计

### Q: API key 和 admin 账号是一回事吗？

**不是**：
- **API key（X-API-Key header）**：创作 API 用，业务流程
- **admin session cookie（浏览器登录）**：管理后台用，admin 专属

普通员工只需要 API key，不需要 admin 账号。

---

## 四、附录：当前已开通租户

| tenant_id | display_name | 状态 |
|---|---|---|
| `default` | （隐式 default tenant） | 用于 `ai_video_demo_2026` 调用 |
| `momcozy-marketing` | Momcozy 市场营销部 (sample) | 测试用 |

---

## 五、Admin 的内部 SOP（运营自己存）

### 命名规则
- tenant_id: `momcozy-{dept-short}` ，如 `momcozy-marketing`、`momcozy-brand`、`momcozy-ecom`、`momcozy-content`
- key description 必填，内容包含「使用人 - 用途」

### Key 轮换周期
- 默认 expires_at = 90 天
- 部门有员工离职 / 异常风险时立即手动撤销重发

### 安全事件响应
1. 收到 key 泄露报告
2. 立即在 `/admin/tenants/{tid}` 撤销该 key
3. 根据 `/api/admin/logs` 看 key 在最近 24 小时是否被滥用
4. 联系 ops 确认是否要再做 PG 临时审计

### Demo key 的去留
- `ai_video_demo_2026`（env-var fallback）当前还在用，对应 tenant_id=`default`
- 上线 30 天后建议禁用：删除 `.env.prod` 里的 `API_KEY` 行 + 重启 backend
- 之后所有用户必须有部门发的真 key 才能用
