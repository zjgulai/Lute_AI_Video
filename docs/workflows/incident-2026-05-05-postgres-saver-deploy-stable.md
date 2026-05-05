---
title: PostgresSaver 部署事故复盘 - 2026-05-05
doc_type: workflow
module: deploy
topic: incident-postgres-saver-rollout
status: stable
created: 2026-05-05
updated: 2026-05-05
owner: self
source: human+ai
---

# PostgresSaver 部署事故复盘 — 2026-05-05

## 事故概述

部署本期 15 个 commit (PR-1~PR-14) 到 Lighthouse 生产时,backend container 进入
restart loop,docker daemon 资源紧张,服务器 ssh + http 全部 timeout 大约 5 分钟。
用户控制台强制重启服务器后逐步恢复,最终 smoke 4/4 通过,但事故暴露了部署流程的
重大漏洞。

**业务影响**: ~5 分钟生产 502 + ~30 分钟内总恢复时间。
**根本原因**: 部署流程跳过了"requirements.txt 变更必须 rebuild image"步骤。

## 时间线

| 时间 | 事件 |
|---|---|
| T+0 | 本地 build frontend (`NEXT_PUBLIC_IS_DEMO=false`),11 static page 成功 |
| T+1 | rsync src/ + web/ + deploy/lighthouse/ + requirements.txt 到 lighthouse |
| T+2 | `docker compose restart backend frontend` |
| T+3 | smoke 4/4 全 502 — backend 启动失败 |
| T+4 | 看 docker logs:`RuntimeError: PostgreSQL connection failed (No module named 'psycopg')` |
| T+5 | backend container 进入 restart loop(restart policy `unless-stopped`) |
| T+6 | 试 `sudo docker exec ... pip install`,失败:Container is restarting |
| T+7 | 试 `sudo docker compose build backend`,跑 22 分钟无产出 — buildkit 卡死 |
| T+8 | curl /api/health 返回 status 0(timeout) — 整个 nginx 也响应不了 |
| T+9 | ssh 也 timeout `Connection timed out during banner exchange` |
| T+10 | 用户腾讯云控制台**强制重启服务器** |
| T+11 | 服务器重启后 ssh 通,uptime 0 min,内存 6.2 GB free(不是 OOM,是 CPU 满) |
| T+12 | `docker stop ai_video_backend` 阻断 restart loop |
| T+13 | `docker buildx prune` 清理 buildkit cache |
| T+14 | 第二次 `docker build` 又卡 22 分钟无产出 |
| T+15 | 改方案:`docker run lighthouse-backend:latest sleep 600` 起临时容器 |
| T+16 | `docker exec ... pip install -i https://mirrors.aliyun.com/pypi/simple/` 成功 30 秒 |
| T+17 | `docker commit backend_pip_install lighthouse-backend:latest` |
| T+18 | `docker compose up -d backend` → 起来但 unhealthy + logs 空 |
| T+19 | `docker inspect`:发现 CMD 被覆盖成 `[sleep 3600]`(commit 时把 sleep 也带过去了) |
| T+20 | `docker commit --change 'CMD [...]'` 修回 uvicorn |
| T+21 | smoke 4/4 全过 ✅ |

## 6 个关键发现

### 1. `mount src/:ro` 不会触发依赖重装

`docker-compose.prod.yml`:
```yaml
backend:
  volumes:
    - ../../src:/app/src:ro          # 代码 mount
    - ../../requirements.txt:/app/requirements.txt:ro  # 这个 mount 也是 ro
```

rsync 让 host 上 src/ + requirements.txt 更新,但 backend 容器内的 Python 解释器
**不会自动重装新依赖**。即使 requirements.txt 出现新 `psycopg`,容器里的
`/usr/local/lib/python3.12/site-packages` 里没有 psycopg。

`pip install` 是 image build 时跑的,运行时不会再跑。

### 2. backend image 4 days 没 rebuild

```
$ sudo docker images lighthouse-backend
REPOSITORY             TAG       CREATED        SIZE
lighthouse-backend     latest    4 days ago     517MB
```

部署流程缺少"requirements.txt changed → rebuild"的检查。直接 `docker compose
restart` 用的是 4 天前的旧 image,没有新依赖。

### 3. restart loop + docker daemon 死锁

backend 启动失败 → restart policy 重启 → 又失败 → 无限循环。

加上 `docker compose build` 同时跑(下载层、安装包),buildkit 占用大量 IO/CPU,
配合 restart loop 容器分秒级重启,把单核小机器的 CPU 排队拉满。最终 sshd 也
排不到 CPU 时间片应答 banner exchange,看上去像服务器宕机。

### 4. docker buildkit 在大陆访问 PyPI 容易卡死

```
$ sudo docker compose -f docker-compose.prod.yml build backend
# 22 minutes, no output, no new image, load average 0.00
```

buildkit 跑 `pip install -r requirements.txt`,connection 到 pypi.org 慢/丢包。
buildkit 的 retry 不会被 `--progress=plain` 输出,看起来"安静卡死"。

更稳的:用阿里云 mirror。

### 5. `docker commit` 会保留容器 CMD 覆盖

```bash
sudo docker run --name backend_pip_install lighthouse-backend:latest sleep 600
sudo docker commit backend_pip_install lighthouse-backend:latest
# 新 image 的 CMD 是 [sleep 600],不是原来的 [uvicorn ...]
```

后果:`docker compose up -d backend` 起来后容器在 sleep 而不是跑 uvicorn,
docker logs 空,health check fail。

修法:`docker commit --change 'CMD ["uvicorn", "src.api:app", "--host",
"0.0.0.0", "--port", "8001"]'`。

### 6. `restart policy: unless-stopped` 让事故扩大

backend container 启动失败时 docker 立即重启,这本是好事(瞬时网络抖动恢复)。
但 import-time RuntimeError 是**永久性失败**,restart 永远救不回来,反而把
机器拖垮。

应该限制 restart 次数(如 max-retries 5)或对 import error 这种 fatal 用 `no`
restart policy + 监控告警。

## 部署流程修正

### 必须做的(已实施)

1. **Dockerfile.backend 配 PyPI mirror**(commit `XXXXXXX`):
   ```dockerfile
   ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
   ARG PIP_TRUSTED_HOST=mirrors.aliyun.com
   ENV PIP_INDEX_URL=$PIP_INDEX_URL
   ENV PIP_TRUSTED_HOST=$PIP_TRUSTED_HOST
   ```
   下次 `docker build` 在大陆环境秒级完成,海外环境 build 时
   `--build-arg PIP_INDEX_URL=https://pypi.org/simple/` 覆盖。

### 应该做的(下次部署前)

2. **deploy.sh 加 requirements.txt 变更检查**:
   ```bash
   # phase 0: 检查 requirements.txt 是否需要 rebuild
   if ! diff -q requirements.txt $(docker inspect lighthouse-backend:latest \
        --format='{{index .Config.Labels "requirements_hash"}}') &>/dev/null; then
     echo "requirements.txt changed → rebuild backend image"
     sudo docker compose -f docker-compose.prod.yml build --no-cache backend
   fi
   ```
   或者更简单:**deploy 前 git diff 看 requirements.txt 是否变,变了就先 build**。

3. **build-and-deploy.sh 用 docker save → scp → docker load 模式**:
   - 本地 build image (用本地缓存) → save 成 tar.gz → 传服务器 → load
   - 避免服务器侧 docker build 卡 buildkit
   - 已经在脚本里写了,但实际部署没用这个流程

4. **restart policy 改 `on-failure:5`**:
   失败 5 次后停止重启,人工介入。避免 restart loop 无限拖累系统。

5. **deploy.sh 失败时打印 docker logs** + abort:
   现在 deploy.sh phase 3 health check 失败只打印状态码,没看 backend logs,
   不能立即定位问题。

## 紧急恢复 SOP

如果再次出现 backend 启动失败 + 服务器响应缓慢:

### Step 1: 阻断 restart loop

```bash
ssh -i ai_video.pem ubuntu@101.34.52.232 \
  "sudo docker stop ai_video_backend"
```

如果 ssh 也连不上 → **腾讯云控制台强制重启服务器**(uptime 重置 + restart loop
也被打断)。

### Step 2: 检查根因

```bash
sudo docker logs --tail 50 ai_video_backend 2>&1
```

常见错误:
- `ImportError: No module named 'X'` → 依赖没装
- `RuntimeError: PostgreSQL connection failed` → DATABASE_URL 错或 PG 没起
- `Cannot allocate memory` → OOM
- `Address already in use` → 端口冲突

### Step 3: 选择修复路径

| 错误类型 | 修复路径 |
|---|---|
| 依赖缺失(常见) | `docker run + pip install + commit --change CMD` 三步法 |
| PG 连接失败 | 检查 .env.prod 的 DATABASE_URL + check_pg_health |
| OOM | 关掉一些容器先,然后 docker system prune |
| 端口冲突 | sudo lsof -i:8001 看占用 |

### 三步法详细命令

```bash
# 1. 起临时容器装依赖(用阿里云 mirror)
sudo docker run -d --name backend_pip_install \
  lighthouse-backend:latest sleep 3600

sudo docker exec backend_pip_install pip install --no-cache-dir \
  -i https://mirrors.aliyun.com/pypi/simple/ \
  --trusted-host mirrors.aliyun.com \
  '<missing-deps>'

# 2. 验证 import OK
sudo docker exec backend_pip_install python -c \
  "import <module>; print('OK')"

# 3. commit 成新 image,**必须用 --change 重置 CMD**
sudo docker stop backend_pip_install
sudo docker commit \
  --change 'CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8001"]' \
  backend_pip_install lighthouse-backend:latest
sudo docker rm backend_pip_install

# 4. 重建 backend
sudo docker rm ai_video_backend 2>/dev/null
cd /opt/ai-video/deploy/lighthouse
sudo docker compose -f docker-compose.prod.yml up -d backend

# 5. 等 30s + 验证
sleep 30
bash smoke.sh
```

## 经验总结

1. **修改 requirements.txt 必须先 rebuild image,不能直接 restart container**
2. **docker buildkit 在大陆容易卡 PyPI**,Dockerfile 配阿里云 mirror 必须
3. **docker commit 会保留 CMD 覆盖**,临时容器记得用 `--change` 修
4. **restart policy `unless-stopped` 加 import error = 死循环**,上限 5 次更安全
5. **ssh 也连不上 ≠ OOM**,可能只是 CPU 满 + sshd 排队,7 GB 内存的机器不会真 OOM
6. **腾讯云控制台强制重启** 是最后救命稻草,用过没问题(没掉数据,docker volume 都 ok)
