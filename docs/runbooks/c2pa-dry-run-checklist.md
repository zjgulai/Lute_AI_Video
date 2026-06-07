---
title: C2PA Dry-Run Checklist
doc_type: workflow
module: compliance
topic: c2pa-pipeline
status: stable
created: 2026-06-07
updated: 2026-06-07
owner: self
source: human+ai
description: C2PA 签名链路在不申请真实 CA 证书下的 dry-run 复核步骤。验证签名开关、manifest 形态与生产前置条件，避免直接上生产。
related:
  - file: ../architecture/adr/006-c2pa-content-credentials.md
    relation: implements-decision-of
  - file: ./c2pa-cert-application.md
    relation: prerequisite
---

# C2PA Dry-Run Checklist（不申请真实证书）

## 触发场景

- 有计划推进或复用 C2PA 签名能力，但当前仍无 CA 生产证书可用时。
- 需要验证签名开关、manifest 骨架和生产可回滚路径是否健康。

## 安全边界

- 不访问外部签名 CA。
- 不做真实视频发布。
- 不把证书私钥写入仓库。
- dry-run 中签名失败保持非阻塞（`sign_video` 返回输入路径），用于不中断既有流程；真实生产验证仍依赖后续 CA 签发。

## 1. 预检（Dry-Run）

```bash
.venv/bin/python -m pytest tests/test_sprint3_compliance_resilience.py -k c2pa
```

要求通过：

- `C2PA_ENABLED` 默认关闭时为 no-op。
- `sign_video` 在缺少 `C2PA_CERT_PATH`/`C2PA_KEY_PATH` 时不抛异常。
- `c2pa` 库缺失时不抛异常。
- `build_manifest("X")` 包含 `format=video/mp4`、`claim_generator_info` 与 `digitalSourceType=aiGeneratedContent`。

## 2. 本地自签名文件准备（仅用于流程验证）

```bash
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout /tmp/c2pa-local.key \
  -out /tmp/c2pa-local.crt \
  -days 30 -subj "/CN=video.lute-tlz-dddd.local"
```

该证书仅用于本地链路验证，不可用于对外发布。

## 3. Dry-Run 签名回归

```bash
python - << 'PY'
import os
from pathlib import Path
from src.tools.c2pa_signer import sign_video

workdir = Path("/tmp/c2pa-dry-run")
workdir.mkdir(parents=True, exist_ok=True)
video = workdir / "sample.mp4"
video.write_bytes(b"fake-mp4-bytes")

os.environ["C2PA_ENABLED"] = "1"
os.environ["C2PA_CERT_PATH"] = "/tmp/c2pa-local.crt"
os.environ["C2PA_KEY_PATH"] = "/tmp/c2pa-local.key"

out = sign_video(str(video), title="AI Video 2.0 dry-run")
print("output:", out)
print("signature_attempted:", out != str(video))
PY
```

解释：

- `signature_attempted=True`：说明签名执行链路被尝试（前提是环境已有 `c2pa-python`）。
- `signature_attempted=False`：说明环境未配置/缺依赖，属于预期退化，不作为生产失败。

## 4. 与既有证书申请流程衔接

- 按 `docs/runbooks/c2pa-cert-application.md` 完成 CA 生产证书申请后，再切到真实签名验证流程。
- 真实验收前更新 `.env.prod` / 服务参数：
  - `C2PA_ENABLED=1`
  - `C2PA_CERT_PATH=/opt/ai-video/secrets/c2pa-cert.pem`
  - `C2PA_KEY_PATH=/opt/ai-video/secrets/c2pa-key.pem`

## 5. 失败处理（不进入发布）

1. 遇到 `sign_video` 报错：先回滚 `C2PA_ENABLED=0`，确认生产 fallback 不受影响。
2. 遇到 manifest 字段缺失：修复 `build_manifest` 后再复测 dry-run。
3. 遇到链路不可用（依赖缺失）：补装 `c2pa-python` 后重测，不影响 `C2PA_ENABLED=0` 的自动化闭环。
4. 未拿到 CA 证书前，不进入 EU 市场发布链路，仅允许标记 `_unsigned_pending_c2pa=true`（如已有）。

## 相关代码

- `src/tools/c2pa_signer.py`
- `tests/test_sprint3_compliance_resilience.py`
- `src/tools/c2pa_signer.py`（`is_enabled` / `build_manifest` / `sign_video`）
