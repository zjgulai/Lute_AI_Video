# 腾讯云 CloudBase 云托管 — 手把手部署指南

> 预计总耗时：10-15 分钟（首次部署）

---

## 前置检查 ✅

- [x] 腾讯云账号已完成**个人实名认证**
- [x] GitHub 仓库 `zjgulai/Lute_AI_Video` 已推送最新代码（包含 Dockerfile）

---

## Step 1: 创建 CloudBase 环境（2分钟）

1. 浏览器访问 → [https://console.cloud.tencent.com/tcb](https://console.cloud.tencent.com/tcb)
2. 点击页面中央的 **「新建环境」** 大按钮
3. 弹窗填写：
   - **环境名称**：`lute-ai-video`
   - **环境ID**：`lute-ai-video-xxx`（自动生成，无需修改）
   - **计费方式**：选择 **「按量计费」**
4. 点击 **「确定」**
5. 等待环境创建完成（约 30-60 秒，页面会自动跳转）

> 💡 如果提示需要开通云开发服务，点击同意即可。

---

## Step 2: 进入云托管创建服务（1分钟）

1. 环境创建完成后，左侧菜单找到 **「云托管」**（图标是 🐳 容器）
2. 点击 **「云托管」**
3. 点击页面中央的 **「新建服务」** 按钮
4. 弹窗填写：
   - **服务名称**：`lute-backend`
   - **备注**：（可选）AI Video Backend
5. 点击 **「确定」**

---

## Step 3: 配置部署方式 — 从 GitHub 部署（2分钟）

1. 服务创建后，进入服务详情页
2. 点击 **「新建版本」** 或 **「部署」** 按钮
3. 部署方式选择：**「从 GitHub 部署」**
4. 首次使用需要授权 GitHub：
   - 点击 **「授权 GitHub」**
   - 浏览器会跳转到 GitHub 授权页面 → 点击 **「Authorize TencentCloudBase」**
   - 授权完成后自动返回腾讯云控制台
5. 返回后填写：
   - **仓库**：`zjgulai/Lute_AI_Video`
   - **分支**：`main`
   - **Dockerfile 路径**：`Dockerfile`（我们已经创建了软链接，根目录的 Dockerfile 就是正确的）
   - **容器端口**：`8001`（必须与 Dockerfile 中 EXPOSE 一致）

---

## Step 4: 配置环境变量（最关键！）（2分钟）

在同一页面找到 **「高级配置」** 或 **「环境变量」** 区域，点击展开，然后添加以下变量：

| 变量名 | 值 | 说明 |
|---|---|---|
| `API_KEY` | `ai_video_demo_2026` | API 认证密钥 |
| `CORS_ORIGINS` | `https://zjgulai.github.io` | 允许 GitHub Pages 跨域访问 |
| `VIDEO_OUTPUT_DIR` | `/app/output` | 视频输出目录 |
| `DEFAULT_LLM_PROVIDER` | `kimi` | 默认 LLM 提供商 |
| `LOG_LEVEL` | `INFO` | 日志级别 |

> ⚠️ **重要**：`CORS_ORIGINS` 必须填 `https://zjgulai.github.io`，否则前端无法连接！

---

## Step 5: 启动部署（3-5分钟）

1. 确认所有信息填写无误
2. 点击页面底部 **「开始部署」** 或 **「创建版本」**
3. 页面会跳转到**版本详情页**，显示构建日志
4. 等待状态从 **「构建中」** → **「部署中」** → **「运行中」**

> ⏱️ 首次构建大约需要 **3-5 分钟**（安装 Python 依赖）。
> 
> 如果构建失败，点击「构建日志」查看错误信息，通常是依赖安装问题。

---

## Step 6: 获取公网访问地址（1分钟）

1. 版本状态变为 **「运行中」** 后，返回服务列表页
2. 找到你的服务 `lute-backend`
3. 在「访问地址」列，会显示一个公网 URL：
   ```
   https://lute-backend-xxx.ap-shanghai.app.tcloudbase.com
   ```
4. **复制这个 URL**，后面配置前端要用！

> 💡 也可以点击服务名称进入详情页，在「服务访问」区域找到地址。

---

## Step 7: 配置前端连接腾讯云后端（1分钟）

1. 浏览器打开你的 GitHub Pages 站点：
   ```
   https://zjgulai.github.io/Lute_AI_Video/
   ```
2. 点击页面右上角 **⚙️ 齿轮图标**（Settings）
3. 填入：
   - **Backend URL**：`https://lute-backend-xxx.ap-shanghai.app.tcloudbase.com`（Step 6 复制的地址）
   - **API Key**：`ai_video_demo_2026`
   - **Demo Mode**：❌ 关闭（取消勾选）
4. 点击 **「Test Connection」**
   - 应该显示绿色 ✅ `Connected`
5. 点击 **「Save」**
6. 按 **F5** 刷新页面

---

## Step 8: 验证部署成功

1. 刷新后的页面应该显示正常 UI
2. 选择一个场景（如 Product Direct）
3. 填入产品信息，点击生成
4. 打开浏览器开发者工具（F12）→ Network 标签
5. 观察请求是否发送到了 `https://lute-backend-xxx...` 而不是本地
6. 如果看到 `pipeline/start` 请求返回 200，说明部署成功！🎉

---

## 费用说明 💰

CloudBase 云托管按量计费，每月有免费额度：

| 资源 | 免费额度 | 超出单价 |
|---|---|---|
| CPU | 1000 分钟/月 | ~¥0.05/分钟 |
| 内存 | 1000 GB·分钟/月 | ~¥0.02/GB·分钟 |
| 出流量 | 1 GB/月 | ~¥0.8/GB |

对于个人测试项目，**免费额度通常够用**。

---

## 常见问题

### Q1: 构建失败，提示 "Dockerfile not found"
- 检查 Dockerfile 路径是否填的是 `Dockerfile`（不是 `Dockerfile.backend`）
- 我们已经创建了软链接，根目录下应该有 Dockerfile

### Q2: 服务启动后访问返回 502/503
- 检查容器端口是否填了 `8001`
- 检查 Dockerfile 中 CMD 是否正确启动了服务

### Q3: 前端 Test Connection 失败
- 检查 `CORS_ORIGINS` 环境变量是否包含 `https://zjgulai.github.io`
- 检查 `API_KEY` 是否匹配
- 注意：环境变量修改后需要**重新部署**才能生效

### Q4: 文件上传后丢失
- CloudBase 容器不是持久化存储，每次重新部署文件会丢失
- 这是正常行为，生产环境建议搭配腾讯云 COS 对象存储

---

## 升级选项

如果 CloudBase 的免费额度不够用，或者你需要持久化存储：

**腾讯云轻量应用服务器（Lighthouse）**
- 新用户通常有 1 个月免费试用
- 有固定公网 IP，24小时运行
- 可以安装 Docker，完全自主控制
- 价格：约 ¥30-50/月（最基础配置）

> 需要 Lighthouse 部署指南的话，告诉我！
