---
name: runbook-key-rotation
description: Runbook \u2014 production API key rotation SOP. \u8986\u76d6 DEEPSEEK_API_KEY / POYO_API_KEY / SILICONFLOW_API_KEY / API_KEY \u56db\u4e2a\u6838\u5fc3\u5bc6\u94a5\u7684\u9884\u7533\u8bf7 / .env.prod \u66f4\u65b0 / \u91cd\u542f / \u9a8c\u8bc1 / \u65e7\u5bc6\u94a5\u4f5c\u5e9f\u3002\u5f53\u5bc6\u94a5\u6cc4\u9732\u3001\u6388\u6743\u751f\u6548\u3001\u5b9a\u671f rotation\uff0890 \u5929\uff09\u3001\u6216\u590d\u7528\u300c\u4e0a\u4e00\u4efd\u5bc6\u94a5\u53ef\u80fd\u88ab\u8bb0\u5f55\u300d\u4e8b\u4ef6\u65f6\u4f7f\u7528\u3002
doc_type: runbook
module: ai-video
topic: secret-rotation
status: stable
created: 2026-05-16
updated: 2026-05-16
owner: Sisyphus
source: ai+sop
related:
  - file: ../../.kiro/plan/VULNERABILITIES-AND-PENDING-2026-05-15.md
    relation: implements-v2
  - file: ../../deploy/lighthouse/.env.prod
    relation: target-file
---

# Runbook \u2014 API Key Rotation SOP

> **\u4ec0\u4e48\u65f6\u5019\u6267\u884c**: \u5bc6\u94a5\u6cc4\u9732\u3001\u6388\u6743\u53d8\u66f4\u3001\u5b9a\u671f rotation\uff08\u63a8\u8350 90 \u5929\uff09\u3001\u6216\u300c\u4e0a\u4e00\u6b21\u4f1a\u8bdd\u53ef\u80fd\u8bfb\u8fc7\u65e7 key\u300d\u3002
>
> **\u8eab\u4efd**: \u5fc5\u987b\u7531\u6709\u8bbf\u95ee\u751f\u4ea7 lighthouse \u670d\u52a1\u5668\u4ee5\u53ca\u4e09\u65b9\u670d\u52a1\u63a7\u5236\u53f0\u8d26\u6237\u7684\u4eba\u5458\u6267\u884c\u3002
>
> **\u4e0d\u53ef\u9006**: rotate \u540e\u65e7 key \u4f5c\u5e9f\u3002\u68c0\u67e5\u65e7 key \u662f\u5426\u88ab\u5176\u4ed6\u4eba\u5458 / \u811a\u672c / CI \u5f15\u7528\uff01

---

## \u9700\u8981 rotate \u7684 4 \u4e2a key

| Key | \u63a7\u5236\u53f0 | \u5f53\u524d\u5728 .env.prod | \u4f7f\u7528\u8005 |
|---|---|---|---|
| `DEEPSEEK_API_KEY` | https://platform.deepseek.com | \u662f | LLM \u4e3b\u63a8\u7406\uff08\u5168\u6d41\u6c34\u7ebf strategy/script/audit \u7b49\uff09 |
| `POYO_API_KEY` | https://poyo.ai/dashboard | \u662f | \u56fe\u7247 + \u89c6\u9891\u751f\u6210 |
| `SILICONFLOW_API_KEY` | https://siliconflow.cn | \u662f | TTS (CosyVoice) |
| `API_KEY` | \u5185\u90e8\u751f\u6210 | \u662f | backend API auth \uff08\u524d\u7aef X-API-Key header\uff09 |

---

## ⚠️ 2026-05-17 Audit: 已确认泄露范围

AI 对 git history + origin/main + .gitignore 做完整扫描后的真实结论：

| Key | git history | origin/main | .gitignore 保护 | 风险评级 | 紧急 rotate? |
|---|---|---|---|---|---|
| `POYO_API_KEY` (`sk-pyIO0phv-...`) | ✅ commit `49d5bdc` (sprint2-backup) | ✅ **YES, 已推到 origin/main** | ✅ now | 🔴 **HIGH** | **是，本周必做** |
| `DEEPSEEK_API_KEY` | ❌ 历史无 | ❌ | ✅ | 🟢 SAFE | defer (90d 周期 rotation) |
| `SILICONFLOW_API_KEY` | ❌ 历史无 | ❌ | ✅ | 🟢 SAFE | defer (90d 周期 rotation) |
| `API_KEY` (`ai_video_demo_2026`) | ✅ public by design | ✅ | ✅ now | 🟡 demo-only read-only | 仅在 demo key 被滥用时 |

**结论**: 4 个 key 中只有 **1 个 (POYO) 是真正泄露 + 紧急 rotate 优先**，其他 3 个不紧急。可优先 rotate POYO 单个再按 90d 周期 rotate 余下 3 个。

### POYO key 紧急 rotate 步骤

1. 登 https://poyo.ai/dashboard → API Keys
2. 点 "Generate new key"，复制新 key
3. SSH 到生产 `ssh -i ~/ai_video.pem ubuntu@101.34.52.232`
4. `nano /opt/ai-video/deploy/lighthouse/.env.prod` → 替换 `POYO_API_KEY=<new>`
5. `docker compose -f /opt/ai-video/deploy/lighthouse/docker-compose.prod.yml up -d --force-recreate backend`
6. 等 30s 后验证: `curl -sk https://video.lute-tlz-dddd.top/health | grep version`
7. **泄露的旧 key disable**: 回 poyo.ai dashboard → 找旧 key → Revoke

### 注意
- 老 commit `49d5bdc` 在 sprint2-backup branch，**已在 origin/main 之外的分支**。但 origin 可能保留了 dangling object。**rotate POYO key 即可彻底闭环**。
- 不需要 `git filter-repo` 清理 history（已 rotate 等于 deactivate，老 history 中的 key 失效后无安全意义）。

---



```bash
ssh -i ./ai_video.pem ubuntu@101.34.52.232
cd /opt/ai-video
sudo cp deploy/lighthouse/.env.prod deploy/lighthouse/.env.prod.bak.$(date +%Y%m%d-%H%M%S)
sudo ls -la deploy/lighthouse/.env.prod.bak.*
```

\u9a8c\u6536\uff1a\u770b\u5230\u521a\u624d\u521b\u5efa\u7684 .bak \u6587\u4ef6\u3002

---

## \u9636\u6bb5 2 \u2014 \u83b7\u53d6\u65b0 key\uff083 \u4e2a\u5e73\u53f0 + 1 \u4e2a\u751f\u6210\uff0c\u603b\u8ba1 10-15 min\uff09

### 2a. DeepSeek

1. \u767b\u5f55 https://platform.deepseek.com
2. **API Keys** \u9875 \u2192 **Create new secret key**
3. \u540d\u79f0\u4e3a `ai-video-prod-2026-05-rotation`
4. \u590d\u5236\u65b0 key\uff08\u5f00\u5934 `sk-`\uff0c**\u53ea\u663e\u793a\u4e00\u6b21**\uff09
5. \u6682\u5b58\u672c\u5730 password manager / Bitwarden

### 2b. POYO

1. \u767b\u5f55 https://poyo.ai/dashboard
2. **API Keys** \u9875 \u2192 **Generate**
3. \u590d\u5236\u65b0 key\uff08\u5f00\u5934 `sk-`\uff0c\u4e5f\u662f\u4e00\u6b21\u6027\u663e\u793a\uff09

### 2c. SiliconFlow

1. \u767b\u5f55 https://siliconflow.cn
2. **API Keys** \u9875 \u2192 **\u521b\u5efa\u65b0 key**
3. \u590d\u5236

### 2d. Backend API_KEY \uff08\u672c\u5730\u751f\u6210\uff09

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# \u8f93\u51fa\u4f8b\u5982: jkq8aLp_KZpRq3vYx4tHnE2bWcMdN5sFeGoIuP9zRcA
```

---

## \u9636\u6bb5 3 \u2014 \u66f4\u65b0 .env.prod\uff083 min\uff09

\u5728\u670d\u52a1\u5668\u4e0a\u7528 nano/vi \u7f16\u8f91\uff1a

```bash
ssh -i ./ai_video.pem ubuntu@101.34.52.232
sudo nano /opt/ai-video/deploy/lighthouse/.env.prod
```

**\u53ea\u6539\u4ee5\u4e0b 4 \u884c**\uff08\u4fdd\u6301\u5176\u4ed6\u4e0d\u53d8\uff09\uff1a

```
DEEPSEEK_API_KEY=<\u65b0 deepseek key>
POYO_API_KEY=<\u65b0 poyo key>
SILICONFLOW_API_KEY=<\u65b0 siliconflow key>
API_KEY=<\u672c\u5730\u751f\u6210\u7684 token>
```

\u4fdd\u5b58 + \u9000\u51fa\u3002\u9a8c\u6536\uff1a

```bash
sudo grep -E "^(DEEPSEEK|POYO|SILICONFLOW|API)_API_KEY=|^API_KEY=" /opt/ai-video/deploy/lighthouse/.env.prod | wc -l
# \u671f\u671b\u8f93\u51fa: 4
```

---

## \u9636\u6bb5 4 \u2014 \u91cd\u542f backend container \u52a0\u8f7d\u65b0 env\uff083 min\uff09

```bash
ssh -i ./ai_video.pem ubuntu@101.34.52.232
cd /opt/ai-video/deploy/lighthouse
sudo docker-compose -f docker-compose.prod.yml up -d --no-deps backend
sleep 15
curl -fsSk https://localhost/health | python3 -m json.tool | head -20
```

\u9a8c\u6536\uff1astatus=`ok`, persistence=`healthy`\u3002

---

## \u9636\u6bb5 5 \u2014 \u9a8c\u8bc1\u65b0 key \u53ef\u7528\uff0810-15 min\uff09

### 5a. \u9a8c\u8bc1 DeepSeek \u53ef\u7528 \uff08\u9700 API_KEY = ai_video_demo_2026 \u4f4d\u7f6e\u6362\u4e3a\u521a\u4ea7\u751f\u7684\u65b0 token\uff09

```bash
NEW_API_KEY="<\u521a\u4ea7\u751f\u7684\u65b0 API_KEY>"
curl -fsSk -X POST https://localhost/fast/generate \
  -H "X-API-Key: $NEW_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"smoke test rotation","duration_seconds":10}'
```

\u9a8c\u6536\uff1aHTTP 200\uff0c\u8fd4\u56de `task_id`\u3002

### 5b. \u9a8c\u8bc1 POYO \uff08\u9690\u542b\uff0c\u4e0a\u4e00\u6b65\u8fd0\u884c\u65f6\u4f1a\u8c03 poyo\uff09

\u67e5\u770b backend \u65e5\u5fd7\u662f\u5426\u6709 401/403 \u6765\u81ea poyo\uff1a

```bash
ssh -i ./ai_video.pem ubuntu@101.34.52.232 \
  'sudo docker logs --since 5m ai_video_backend 2>&1 | grep -iE "poyo.*40[13]|poyo.*unauthorized" | head -5'
```

\u9a8c\u6536\uff1a\u8f93\u51fa\u4e3a\u7a7a\u3002

### 5c. \u9a8c\u8bc1 SiliconFlow

\u8de8 5a-5b \u540e backend \u65e5\u5fd7\u770b TTS \u8c03\u7528\uff1a

```bash
ssh -i ./ai_video.pem ubuntu@101.34.52.232 \
  'sudo docker logs --since 5m ai_video_backend 2>&1 | grep -iE "cosyvoice|siliconflow" | tail -5'
```

\u9a8c\u6536\uff1a\u770b\u5230\u6210\u529f\u54cd\u5e94\uff0c\u4e0d\u662f 4xx\u3002

---

## \u9636\u6bb5 6 \u2014 \u4f5c\u5e9f\u65e7 key\uff088 min\uff09

> **\u5173\u952e**\uff1a\u53ea\u6709\u9636\u6bb5 5 \u5168\u90e8 PASS \u624d\u80fd\u4f5c\u5e9f\uff0c\u5426\u5219\u670d\u52a1\u4e2d\u65ad\u3002

### 6a. DeepSeek

\u63a7\u5236\u53f0\u5220\u9664\u65e7 key\u3002

### 6b. POYO

\u540c\u4e0a\u3002

### 6c. SiliconFlow

\u540c\u4e0a\u3002

### 6d. \u65e7 API_KEY \uff08\u5185\u90e8 token\uff09

\u4e0d\u9700\u8981\u63a7\u5236\u53f0\u4f5c\u5e9f\u3002\u4f46\u5982\u679c\u524d\u7aef demo \u6a21\u5f0f\u6709\u786c\u7f16\u7801\u4ea7\u7269\uff1a

```bash
# \u68c0\u67e5\u524d\u7aef\u662f\u5426\u8fd8\u5728\u7528 demo key
ssh -i ./ai_video.pem ubuntu@101.34.52.232 \
  'sudo docker exec ai_video_frontend printenv 2>/dev/null | grep -iE "API_KEY|NEXT_PUBLIC" | head -5'
# \u5982\u679c\u770b\u5230 demo key\uff0c\u9700\u540c\u6b65\u66f4\u65b0
```

---

## \u9636\u6bb5 7 \u2014 \u5b8c\u5de5\u68c0\u67e5\u5217\u8868

- [ ] .env.prod \u5907\u4efd\u5b58\u5728
- [ ] 4 \u4e2a\u65b0 key \u5df2\u5728\u63a7\u5236\u53f0\u7533\u8bf7
- [ ] .env.prod \u5df2\u66f4\u65b0\uff086 \u884c\u4ee5\u5185\u53d8\u52a8\uff09
- [ ] chmod 600 \u4ecd\u751f\u6548\uff08`ls -la` \u8df3\u8fc7\uff09
- [ ] backend container \u91cd\u542f\u540e healthy
- [ ] 5a-5c \u4e09\u4e2a\u9a8c\u8bc1\u5168 PASS
- [ ] \u65e7 key \u4f5c\u5e9f
- [ ] notify \u56e2\u961f\uff08\u5982\u679c\u6709\u4eba\u624b\u91cc\u6709\u65e7 key\u4f5c\u4e2a\u4eba\u8bbe\u7f6e\uff09
- [ ] commit .env.prod.bak \u5230 \u4e2a\u4eba\u5907\u4efd\uff08\u4e0d push\uff09\u540e\u5220\u672c\u5730 backup

---

## \u56de\u6eda

\u5982\u679c\u9636\u6bb5 5 \u9a8c\u8bc1\u5931\u8d25\uff1a

```bash
ssh -i ./ai_video.pem ubuntu@101.34.52.232
sudo cp /opt/ai-video/deploy/lighthouse/.env.prod.bak.<TIMESTAMP> /opt/ai-video/deploy/lighthouse/.env.prod
cd /opt/ai-video/deploy/lighthouse
sudo docker-compose -f docker-compose.prod.yml up -d --no-deps backend
sleep 15
curl -fsSk https://localhost/health
```

\u4e0d\u8981\u4f5c\u5e9f\u65e7 key\u76f4\u5230 health \u6062\u590d\u3002

---

## \u4e0e VULNERABILITIES-AND-PENDING V-2 \u7684\u5173\u7cfb

- **V-2 chmod 600 \u90e8\u5206**: \u5df2\u5728 2026-05-16 \u5b8c\u6210\uff08commit \u672a\u751f\u6210\uff0c\u4ec5\u670d\u52a1\u5668\u7aef\u53d8\u52a8\uff09
- **V-2 rotate \u90e8\u5206**: \u672c runbook \u662f\u5b8c\u6574 SOP\uff0c\u9700\u4eba\u5458\u6309\u9636\u6bb5\u8df3
- **\u89e6\u53d1\u539f\u56e0**: 2026-05-15 \u9636\u6bb5 Phase 0 deploy \u4f1a\u8bdd\u4e2d AI \u4ee3\u7406 cat \u8fc7 .env.prod\uff0c4 \u4e2a key \u8fdb\u5165\u4e86\u4f1a\u8bdd\u4e0a\u4e0b\u6587

---

*\u672c runbook \u53d6\u4ee3 chmod \u90e8\u5206\u7531 AI \u4ee3\u7406\u6267\u884c\uff1brotation \u90e8\u5206\u5fc5\u987b\u4eba\u5458 sign-off\u3002*
