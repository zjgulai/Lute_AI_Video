---
title: 品牌数据资产目录接入 SOP
doc_type: workflow
module: ai-video
topic: brand-data-asset-directory-intake
status: review
created: 2026-06-03
updated: 2026-06-03
owner: self
source: human+ai
related:
  - file: ./ai-video-commercial-toolbox-phase0-backlog-review-20260603.md
    relation: implements
  - file: ../architecture/brand-asset-token-contract-review-20260603.md
    relation: implements
  - file: ../architecture/quality-contract-brand-rights-audit-review-20260603.md
    relation: feeds
  - file: ../design/asset-lifecycle-state-machine.md
    relation: respects
  - file: ../product/brand-asset-template.md
    relation: extends
---

# 品牌数据资产目录接入 SOP

> 状态边界：本文定义当用户提供一个新的品牌数据资产目录后，如何只读盘点、分类、预检、生成候选 token 和落盘建议。它不表示已接入任何真实目录，不复制、不移动、不删除用户资产。

## 1. 目标

当用户提供 `BRAND_ASSET_DIR` 后，按同一套流程完成：

- 只读资产盘点。
- 文件类型与业务类别分类。
- 授权、PII、儿童、第三方品牌、音乐、声音、claim 预检。
- Brand Asset Source 候选清单。
- Brand Asset Token 候选清单。
- S1/S2/S5 首批注入建议。
- S3/S4 hard gate 风险提示。
- 明确哪些资产可以进入 `approved`，哪些只能停留在 `candidate` 或 `review`。

## 2. 输入约束

用户提供目录时，至少给出：

```text
BRAND_ASSET_DIR=/absolute/path/to/brand-assets
brand_id=<stable-brand-id>
source_owner=<owner-or-source>
default_territory=<country-or-region>
default_allowed_uses=<reference|generation|publishing|training>
```

如果未提供授权信息，默认：

- `license_status=unknown`
- `allowed_uses=[]`
- 只允许离线盘点和 candidate token 抽取
- 不允许进入 approved bundle

## 3. 禁止动作

接入目录阶段禁止：

- 复制原始资产到仓库。
- 移动或重命名用户目录中的文件。
- 删除、压缩、转码原始资产。
- 上传到任何外部服务。
- 调用真实视频、图片、音频、LLM provider。
- 把未知授权资产标记为 approved。
- 把含儿童可识别形象的素材作为 S5 direct reference。
- 把含未授权声音的素材用于 voice clone。

## 4. 输出位置

接入阶段输出按状态落盘：

| 输出 | 位置 | 状态 |
|---|---|---|
| 目录盘点清单 | `tmp/outputs/` | 临时产物 |
| 文件类型统计 | `tmp/outputs/` | 临时产物 |
| 风险预检报告 | `drafts/analysis/` | 草稿分析 |
| BrandAssetSource 候选样例 | `drafts/analysis/` | 草稿分析 |
| BrandAssetToken 候选样例 | `drafts/analysis/` | 草稿分析 |
| 稳定 schema 更新 | `docs/architecture/` | 正式架构 |
| 接入流程更新 | `docs/workflows/` | 正式流程 |

原始资产目录本身不因盘点而进入仓库状态机。

## 5. 只读盘点流程

### 5.1 路径确认

接收目录后先确认：

- 路径是否存在。
- 是否是目录。
- 是否在仓库内。
- 是否包含明显不应读取的系统目录或密钥目录。

判断：

- 如果目录在仓库根目录下但不是标准目录，先暂停迁移建议，不直接整理。
- 如果目录在仓库外，作为外部 source，只生成索引与候选报告。

### 5.2 文件枚举

只读枚举：

```bash
find "$BRAND_ASSET_DIR" -type f -maxdepth 8
```

建议记录字段：

```text
relative_path
extension
size_bytes
mtime
depth
parent_dir
```

### 5.3 类型分类

| 类型 | 扩展名示例 | 初始类别 |
|---|---|---|
| 图片 | `.jpg`, `.jpeg`, `.png`, `.webp`, `.heic`, `.svg`, `.ai`, `.psd` | visual asset |
| 视频 | `.mp4`, `.mov`, `.m4v`, `.webm` | video asset |
| 音频 | `.mp3`, `.wav`, `.m4a`, `.aac` | audio asset |
| 文档 | `.pdf`, `.docx`, `.md`, `.txt`, `.csv`, `.xlsx` | knowledge / spec |
| 3D | `.glb`, `.gltf`, `.usdz`, `.fbx`, `.obj`, `.step` | 3d asset |
| 字幕 | `.srt`, `.vtt`, `.ass` | caption asset |
| 配置 | `.json`, `.yaml`, `.yml` | metadata |
| 未知 | 其他 | manual review |

## 6. 业务分类规则

### 6.1 品牌身份资产

识别信号：

- logo
- color
- font
- brand book
- style guide
- slogan
- tone

候选 token：

- `visual_identity`
- `tone_voice`
- `caption_style`
- `negative_guardrail`

### 6.2 产品事实资产

识别信号：

- sku
- product spec
- faq
- claims
- certification
- comparison
- manual

候选 token：

- `product_truth`
- `platform_compliance`
- `negative_guardrail`

### 6.3 视觉参考资产

识别信号：

- product image
- scene image
- lifestyle
- operation demo
- b-roll
- packaging

候选 token：

- `visual_reference`
- `visual_identity`
- `motion_editing`

### 6.4 音频资产

识别信号：

- voice
- music
- sound effect
- podcast
- narration

候选 token：

- `tone_voice`
- `rights_license`
- `negative_guardrail`

硬规则：

- voice clone 必须有 consent。
- music / sound effect 必须有 license。

### 6.5 历史表现资产

识别信号：

- top videos
- performance report
- ctr
- watch time
- conversion
- comments

候选 token：

- `performance_signal`
- `persona_audience`
- `motion_editing`

硬规则：

- performance signal 只能作为 soft token。
- 不得覆盖 rights、claim 或 safety hard gate。

## 7. 风险预检

每个 asset source 必须标记：

```json
{
  "risk_flags": {
    "pii": false,
    "minor_visible": false,
    "third_party_brand": false,
    "third_party_music": false,
    "voice_clone_candidate": false,
    "medical_claim": false,
    "platform_sensitive": false,
    "unknown_license": true
  }
}
```

默认判定：

| 风险 | 默认处理 |
|---|---|
| `unknown_license=true` | candidate only |
| `minor_visible=true` | S5 direct reference blocked |
| `third_party_music=true` | audio token blocked until license exists |
| `voice_clone_candidate=true` | blocked until consent exists |
| `medical_claim=true` | requires evidence ref |
| `third_party_brand=true` | visual reference review required |

## 8. BrandAssetSource 候选生成

候选对象：

```json
{
  "source_asset_id": "bas_<brand_id>_<hash>",
  "brand_id": "<brand_id>",
  "asset_state": "external_source",
  "asset_kind": "brand_video",
  "source_path": "<absolute-or-canonical-source-path>",
  "relative_path": "<relative-path-from-brand-asset-dir>",
  "media_type": "video",
  "source_owner": "<source_owner>",
  "rights": {
    "license_status": "unknown",
    "territory": [],
    "expires_at": null,
    "allowed_uses": [],
    "consent_required": false,
    "consent_ref": null
  },
  "risk_flags": {}
}
```

规则：

- `source_asset_id` 使用稳定 hash，不使用文件名直接当 id。
- `source_path` 只进入本地草稿或私有报告，不进入公开页面。
- 外部目录中的资产先标为 `external_source`，不伪装成 `brand_kit`。

## 9. BrandAssetToken 候选生成

候选 token 默认：

```json
{
  "status": "candidate",
  "review": {
    "review_status": "pending",
    "reviewed_by": null,
    "reviewed_at": null
  }
}
```

升级到 `approved` 的条件：

- 授权状态明确。
- 场景范围明确。
- 平台范围明确。
- hard / soft 强度明确。
- 没有未处理风险标记。
- 有人工 review 记录。

## 10. 首批注入建议

### S1

优先资产：

- 产品规格。
- 产品图。
- 操作视频。
- FAQ。
- 禁用 claim。

首批 token：

- `product_truth`
- `visual_reference`
- `negative_guardrail`
- `caption_style`

### S2

优先资产：

- 品牌视频。
- 品牌书。
- campaign reference。
- slogan / tone examples。

首批 token：

- `visual_identity`
- `tone_voice`
- `motion_editing`
- `caption_style`

### S5

优先资产：

- lifestyle 品牌视频。
- 场景图。
- 语气样例。
- 安全边界。

首批 token：

- `persona_audience`
- `visual_identity`
- `motion_editing`
- `negative_guardrail`

S5 禁止：

- 真实儿童可识别脸部或全身 direct reference。
- 未授权家庭视频 direct reference。

### S3 / S4

先只做 hard gate：

- S3：source fingerprint、likeness permission、copyright boundary。
- S4：footage rights、person consent、caption/platform compliance。

## 11. 目录接入报告结构

当目录给出后，接入报告建议包含：

```text
1. 目录摘要
2. 文件类型统计
3. 业务分类统计
4. 风险预检摘要
5. 可进入 candidate 的资产
6. 必须补授权或人工确认的资产
7. 建议抽取的 BrandAssetToken
8. S1/S2/S5 注入建议
9. S3/S4 hard gate 风险
10. 下一步落盘建议
```

## 12. 验收标准

目录接入完成的最低标准：

- 原始目录未被修改。
- 所有输出在 `tmp/outputs/` 或 `drafts/analysis/`。
- 每个候选 source 都有 `source_asset_id`。
- 每个候选 token 都有 `status=candidate` 或 `status=review`。
- 未知授权资产没有进入 approved。
- S5 direct reference 安全边界明确。
- 后续需要用户补充的信息被列成清单。
