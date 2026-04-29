# 腾讯云 CloudBase 云托管部署指南

## 方案概述

使用腾讯云 CloudBase 云托管（容器型）部署后端，按量计费，有免费额度。

**优点**：
- 国内访问速度快
- 不需要信用卡（但需要腾讯云实名认证）
- 支持 Dockerfile 自定义环境
- 有免费额度（每月前 1000 分钟 CPU 免费）

**缺点**：
- 需要腾讯云实名认证
- 按量计费，长期使用有费用
- 文件上传（asset library）不是持久化存储

---

## 前置要求

1. 腾讯云账号（已完成实名认证）
2. 本项目的 `Dockerfile.backend` 和 `requirements.txt`

---

## 部署步骤

### Step 1: 创建 CloudBase 环境

1. 访问 [腾讯云 CloudBase 控制台](https://console.cloud.tencent.com/tcb)
2. 点击「新建环境」
3. 选择「云托管」类型
4. 环境名称填写：`lute-ai-video`
5. 选择「按量计费」
6. 等待环境创建完成（约 1-2 分钟）

### Step 2: 创建云托管服务

1. 进入刚创建的环境 → 点击「云托管」
2. 点击「新建服务」
3. 服务名称：`lute-backend`
4. 部署方式选择：**「从 GitHub 部署」**（推荐）或「上传代码包」

#### 方式 A: 从 GitHub 部署（推荐）

1. 点击「从 GitHub 部署」
2. 授权 GitHub 账号
3. 选择仓库：`zjgulai/Lute_AI_Video`
4. 分支选择：`main`
5. 端口填写：`8001`（与 Dockerfile 中的 EXPOSE 一致）
6. 高级设置 → 环境变量：

| 变量名 | 值 |
|---|---|
| `API_KEY` | `ai_video_demo_2026` |
| `CORS_ORIGINS` | `https://zjgulai.github.io` |
| `VIDEO_OUTPUT_DIR` | `/app/output` |
| `DEFAULT_LLM_PROVIDER` | `kimi` |
| `LOG_LEVEL` | `INFO` |

7. 点击「创建并部署」

#### 方式 B: 上传代码包

1. 在项目根目录执行：
```bash
cd /path/to/Lute_AI_Video
zip -r deploy.zip Dockerfile.backend requirements.txt src/ scripts/ pyproject.toml
```

2. 点击「上传代码包」
3. 上传 `deploy.zip`
4. 端口填写：`8001`
5. 配置环境变量（同上）
6. 点击「创建并部署」

### Step 3: 等待部署完成

- 首次构建约 3-5 分钟
- 构建完成后，服务状态变为「运行中」
- 访问地址类似：`https://lute-backend-xxx.ap-shanghai.app.tcloudbase.com`

### Step 4: 配置前端

1. 打开 GitHub Pages 站点：`https://zjgulai.github.io/Lute_AI_Video/`
2. 点击右上角 ⚙️ 齿轮图标
3. Backend URL 填入 CloudBase 提供的访问地址
4. API Key 填入：`ai_video_demo_2026`
5. 关闭 Demo Mode
6. 点击 Test Connection → Save
7. 刷新页面

---

## 费用说明

CloudBase 云托管按量计费：
- **CPU**：前 1000 分钟/月免费，超出后约 ¥0.05/分钟
- **内存**：前 1000 GB·分钟/月免费
- **流量**：前 1GB/月免费

对于个人测试项目，免费额度通常够用。

---

## 故障排查

### 构建失败
- 检查 Dockerfile 中的 `requirements.txt` 路径是否正确
- 检查是否有系统依赖需要安装（如 `libpq-dev`）

### 服务启动失败
- 检查端口是否配置正确（Dockerfile 中 EXPOSE 8001，CloudBase 也要填 8001）
- 检查环境变量是否正确设置

### 前端无法连接
- 检查 `CORS_ORIGINS` 是否包含 `https://zjgulai.github.io`
- 检查 API_KEY 是否匹配

---

## 备选方案

如果 CloudBase 部署遇到问题，可以考虑：
1. **腾讯云轻量应用服务器**（Lighthouse）- 固定 IP，24小时运行
2. **本地运行 + 内网穿透** - 见 `local-ngrok.md`
