# 本地运行方案（零成本 / 零注册）

如果你不想使用任何云服务，以下是几种完全在本地运行的方案。

---

## 方案 A: 本地前端 + 本地后端（推荐，最简单）

**适用场景**：你自己开发和测试，不需要把后端暴露到公网。

### 1. 启动后端

```bash
cd /path/to/Lute_AI_Video
source .venv/bin/activate
uvicorn src.api:app --host 0.0.0.0 --port 8001 --reload
```

后端运行在 `http://localhost:8001`

### 2. 启动前端（开发模式）

```bash
cd /path/to/Lute_AI_Video/web
npm install
npm run dev
```

前端运行在 `http://localhost:3000`

### 3. 配置前端连接本地后端

1. 打开 `http://localhost:3000`
2. 点击右上角 ⚙️ 齿轮图标
3. Backend URL: `http://localhost:8001`
4. API Key: `ai_video_demo_2026`
5. 关闭 Demo Mode
6. Save

✅ **完成！** 前后端都在本地运行，完全免费，响应速度最快。

---

## 方案 B: GitHub Pages + localtunnel 内网穿透

**适用场景**：你想让 GitHub Pages 上的前端连接到你电脑上的后端。

### 1. 启动后端

```bash
cd /path/to/Lute_AI_Video
source .venv/bin/activate
API_KEY=ai_video_demo_2026 CORS_ORIGINS="https://zjgulai.github.io" \
  uvicorn src.api:app --host 0.0.0.0 --port 8001
```

注意：`CORS_ORIGINS` 必须包含 GitHub Pages 域名，否则浏览器会拦截跨域请求。

### 2. 安装 localtunnel（不需要注册！）

```bash
npm install -g localtunnel
```

### 3. 启动内网穿透

```bash
lt --port 8001
```

会输出一个公网 URL，类似：
```
your-url-is-ready-to-go: https://abc123.loca.lt
```

### 4. 配置前端

1. 打开 `https://zjgulai.github.io/Lute_AI_Video/`
2. 点击 ⚙️ 齿轮图标
3. Backend URL: `https://abc123.loca.lt`（localtunnel 提供的地址）
4. API Key: `ai_video_demo_2026`
5. 关闭 Demo Mode
6. Save

⚠️ **限制**：
- 你的电脑必须一直开机且联网
- localtunnel 域名每次重启都会变
- 免费版可能有速度限制

---

## 方案 C: GitHub Pages + Cloudflare Tunnel（更稳定）

**适用场景**：想要一个固定的公网域名指向本地后端。

### 1. 安装 Cloudflare Tunnel

```bash
brew install cloudflared
```

### 2. 登录 Cloudflare（需要注册，但免费）

```bash
cloudflared tunnel login
```

### 3. 创建隧道

```bash
cloudflared tunnel create lute-backend
```

### 4. 配置隧道

创建 `~/.cloudflared/config.yml`：

```yaml
tunnel: <你的-tunnel-id>
credentials-file: /Users/<用户名>/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: lute-backend.your-domain.com
    service: http://localhost:8001
  - service: http_status:404
```

### 5. 启动后端 + 隧道

```bash
# 终端 1：启动后端
uvicorn src.api:app --host 0.0.0.0 --port 8001

# 终端 2：启动隧道
cloudflared tunnel run lute-backend
```

### 6. 配置前端

Backend URL 填入 `https://lute-backend.your-domain.com`

✅ **优点**：域名固定、免费、速度稳定

---

## 方案对比

| 方案 | 成本 | 注册 | 稳定性 | 适用场景 |
|---|---|---|---|---|
| A: 本地前后端 | 免费 | 不需要 | 最高 | 本地开发测试 |
| B: localtunnel | 免费 | 不需要 | 一般 | 临时演示 |
| C: Cloudflare | 免费 | 需要 | 高 | 长期自用 |
| 腾讯云 CloudBase | 免费额度 | 需要实名 | 高 | 正式部署 |
| Render | 免费 | 需要信用卡 | 一般 | 海外访问 |

---

## 推荐

- **开发调试** → 方案 A（本地前后端）
- **给同事/朋友临时演示** → 方案 B（localtunnel）
- **长期自用** → 方案 C（Cloudflare Tunnel）或 腾讯云
