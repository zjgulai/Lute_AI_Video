---
name: adr-001-dual-runtime
description: ADR #001 文档，记录"Python FastAPI 后端 + Node.js Remotion 渲染服务"双运行时架构的决策依据、当前实现位置、备选方案与回退路径。当评估部署拓扑、添加新组件、调试 rendering:3001 服务、或需要理解为什么 LLM 推理与视频合成走不同 runtime 时使用。
---

# ADR #001 — Dual Runtime Strategy

| | |
|---|---|
| **状态** | Accepted |
| **日期** | 2026-05-11（追溯记录 2026-04-29 决策） |
| **决策者** | 工程团队 |
| **影响** | 部署拓扑、Dockerfile 数量、CI 矩阵、运维心智模型 |

## 一、Context（为什么需要做决策）

Short Video Agent 的工作链路涉及两类完全不同的计算：

1. **LLM 推理 + 流水编排**：DeepSeek/Anthropic/Kimi API 调用、LangGraph 状态机、CosyVoice TTS、poyo 图片/视频生成 — Python 生态成熟，`langgraph` / `langchain` / `pydantic` 直接可用。
2. **视频合成（最终 .mp4 渲染）**：[Remotion 4](https://www.remotion.dev/) 用 React 描述动画，背后是 Chromium headless + ffmpeg 把 React DOM 逐帧抓为 png 再合成视频。**Remotion 仅有 Node.js 实现**，没有 Python 绑定。

如果强行把视频渲染塞进 Python 运行时，要么调子进程 `node` 启动 Remotion（每次 cold start 5-15s）、要么用 Pyppeteer/Playwright 自己重新发明 Remotion，两者都很痛。

## 二、Decision（我们决定怎么做）

**采用双运行时**：

- Python 3.11+ FastAPI 进程跑业务流水（端口 8001），见 [`src/api.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/api.py) + [`src/graph/pipeline.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/graph/pipeline.py)
- Node.js 22 Remotion 进程跑视频合成（端口 3001），见 [`rendering/server.mjs`](file:///Users/pray/project/hermes_evo/AI_vedio/rendering/server.mjs) + [`rendering/src/Root.tsx`](file:///Users/pray/project/hermes_evo/AI_vedio/rendering/src/Root.tsx)
- 两者通过 HTTP 通信：Python 把 pipeline 状态 JSON POST 到 `http://rendering:3001/assemble`，Remotion 渲染完返回 `final_video_path`
- 共用 `output/` volume（Docker bind mount），两边都能读写媒体资产

## 三、当前实现

### Python 侧
- 单 Dockerfile（[`Dockerfile.backend`](file:///Users/pray/project/hermes_evo/AI_vedio/Dockerfile.backend)，软链 `Dockerfile`）
- 入口 `uvicorn src.api:app --host 0.0.0.0 --port 8001`
- 依赖：[`requirements.txt`](file:///Users/pray/project/hermes_evo/AI_vedio/requirements.txt)（langgraph、fastapi、psycopg、bcrypt 等）
- 不打包 Node.js / Remotion / ffmpeg

### Node.js 侧
- 独立目录 [`rendering/`](file:///Users/pray/project/hermes_evo/AI_vedio/rendering)，自己的 `package.json` + `Dockerfile`
- 入口 `node server.mjs`，监听 3001
- 用 `@remotion/renderer` API 读取 pipeline state JSON → 合成 mp4
- 不打包 Python

### 编排
- 本地：[`docker-compose.yml`](file:///Users/pray/project/hermes_evo/AI_vedio/docker-compose.yml) 定义 `backend` + `rendering` + `postgres` + `frontend` 4 个服务
- 生产（Tencent Lighthouse）：[`deploy/lighthouse/docker-compose.prod.yml`](file:///Users/pray/project/hermes_evo/AI_vedio/deploy/lighthouse/docker-compose.prod.yml) 同上结构 + nginx
- 通信：backend 用 `httpx` POST `http://rendering:3001/assemble`（容器网络内互相可达）

## 四、Consequences（带来的好处和代价）

### 好处
- **各取所长**：Python 用最成熟的 LLM/AI 生态，Node 用唯一可用的 Remotion
- **故障隔离**：渲染进程 OOM 不会拖垮流水，反之亦然
- **独立伸缩**：渲染是 CPU/RAM 密集型，可以单独加配；流水主要是 IO/wait
- **构建速度**：两个 Dockerfile 各装各的，单边变更只重建一个
- **测试简化**：Python 测试不用 Node + Remotion 环境，反之同理

### 代价
- **网络一跳**：backend → rendering 多一次 HTTP，本地 docker network 几毫秒可忽略，跨主机部署时需要保证网络可达
- **共享卷**：`output/` 必须两个容器都挂载，且权限一致
- **运维复杂度 +1**：监控、日志、健康检查要做两份
- **冷启动**：rendering 进程首次启动需加载 React/Babel + 预热 Chromium，1-2s 延迟

## 五、Alternatives Considered（备选方案）

### A. 单 Python 进程 + 子进程调 `node`
- 每次 `npx remotion render` cold start 5-15s
- 子进程崩溃难以回收，pipeline 卡死
- **拒绝**：性能差 + 容错差

### B. Pyppeteer/Playwright 自己抓帧 + ffmpeg
- Remotion 是 React 组件描述动画，自己抓帧要重新发明 timeline、interpolate、audio sync
- **拒绝**：重造轮子，且永远落后于 Remotion 上游

### C. 把 Remotion server 和 Python 打到同一个 Dockerfile
- 镜像膨胀（Python + Node + Chromium ≈ 2GB+）
- 单进程崩溃影响范围扩大
- **拒绝**：违反单一职责

## 六、Rollback Plan

如果未来 Remotion 出 Python binding（不太可能）或者我们换渲染引擎：
1. Backend 改为直接调用新引擎（删 `rendering/` 目录 + httpx 调用）
2. docker-compose 删 rendering service
3. 单 runtime 即可

回退是单向的：**不会再回到子进程调 `node` 方案**（已验证性能不可接受）。

## 七、相关代码

- [`src/api.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/api.py) — backend 入口
- [`src/skills/remotion_assemble.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/skills/remotion_assemble.py) — 调 rendering 服务的 skill
- [`rendering/server.mjs`](file:///Users/pray/project/hermes_evo/AI_vedio/rendering/server.mjs) — Remotion HTTP 服务
- [`docker-compose.yml`](file:///Users/pray/project/hermes_evo/AI_vedio/docker-compose.yml) — 本地编排
- [`deploy/lighthouse/docker-compose.prod.yml`](file:///Users/pray/project/hermes_evo/AI_vedio/deploy/lighthouse/docker-compose.prod.yml) — 生产编排
