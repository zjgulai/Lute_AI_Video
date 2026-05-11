---
name: runbook-brand-assets-refresh
description: Runbook 文档，处理品牌资产 (momcozy.com 抓取图) 的周期刷新、按需手动刷新、灾难恢复。当用户反馈品牌包 Tab 显示陈旧产品图、新增品牌产品需要纳入、output/brand_assets 误删需要恢复时使用。
---

# Runbook — Brand Assets Refresh

| | |
|---|---|
| **触发场景** | 品牌包 Tab 显示陈旧/缺失产品图；新增 momcozy 产品需纳入；output/brand_assets 误删 |
| **影响范围** | /library 品牌包 Tab + S1-S5 QuickTemplate 下拉 |
| **预期 MTTR** | 2-5 分钟（取决于 momcozy.com 响应） |
| **相关代码** | [`scripts/scrape_momcozy.py`](file:///Users/pray/project/hermes_evo/AI_vedio/scripts/scrape_momcozy.py) · [`scripts/refresh_brand_assets.sh`](file:///Users/pray/project/hermes_evo/AI_vedio/scripts/refresh_brand_assets.sh) · [`src/routers/portfolio.py`](file:///Users/pray/project/hermes_evo/AI_vedio/src/routers/portfolio.py) |

## 一、数据流回顾

```
momcozy.com (Shopify .js endpoint)
  ↓ scrape_momcozy.py (httpx GET + parse)
/app/output/brand_assets/momcozy/
  ├── _manifest.json                  ← scraper audit trail
  ├── momcozy_presets.json            ← TemplatePreset[] for QuickTemplate
  └── {product-slug}/
      ├── info.json                   ← title, usps, source_url, price
      └── images/01.jpg ... NN.jpg    ← product hero images
  ↓ /api/portfolio/?kind=brand_kit (LRU 30s cache)
/library Brand Kit Tab + AssetPicker
  ↓ /api/portfolio/brand-presets?brand=momcozy (LRU 60s cache)
S1-S5 QuickTemplate dropdown
```

## 二、手动按需刷新（最常用）

```bash
ssh -i ai_video.pem ubuntu@101.34.52.232 "
  sudo docker cp /opt/ai-video/scripts/scrape_momcozy.py ai_video_backend:/tmp/
  sudo docker exec ai_video_backend python3 /tmp/scrape_momcozy.py --force
"
```

- `--force` 强制重抓所有已缓存产品
- 速率限制：1 秒/产品，12 个产品 ≈ 12-30 秒
- 输出实时打印 `[OK] {slug}: N images, M USPs`

**最长等 60 秒**前端就能看到新数据（受 `/brand-presets` 缓存 TTL 限制）。如果想立即生效：

```bash
ssh -i ai_video.pem ubuntu@101.34.52.232 "sudo docker compose -f /opt/ai-video/deploy/lighthouse/docker-compose.prod.yml restart backend"
```

## 三、自动周期刷新（cron）

每周日 03:30 自动跑 `refresh_brand_assets.sh`：

```bash
ssh -i ai_video.pem ubuntu@101.34.52.232 "
  sudo cp /opt/ai-video/scripts/refresh_brand_assets.sh /usr/local/bin/refresh_brand_assets.sh
  sudo chmod +x /usr/local/bin/refresh_brand_assets.sh
  echo '30 3 * * 0 root /usr/local/bin/refresh_brand_assets.sh' | sudo tee /etc/cron.d/brand-assets-refresh
"
```

日志：`/var/log/brand-assets-refresh.log`，logrotate 自动轮转。

## 四、新增/移除产品

编辑 [`scripts/scrape_momcozy.py`](file:///Users/pray/project/hermes_evo/AI_vedio/scripts/scrape_momcozy.py) 的 `PRODUCT_URLS` 数组：

```python
PRODUCT_URLS = [
    "https://momcozy.com/products/momcozy-kleanpal-pro-baby-bottle-washer",
    # ... 添加新产品 URL 到这里
]
```

提交 + 推送 + rsync + 重跑 scraper. 移除产品**不会**自动删除 `output/brand_assets/{slug}/`，需手动 `rm -rf`。

## 五、灾难恢复（output/brand_assets 误删）

### 场景 A: 备份还在
```bash
ssh -i ai_video.pem ubuntu@101.34.52.232 "
  LATEST=\$(ls -t /opt/ai-video-backups/ | head -1)
  sudo docker cp /opt/ai-video-backups/\$LATEST/output/brand_assets ai_video_backend:/app/output/
"
```

每日 03:00 cron 备份已包含 brand_assets/，保留 7 天。

### 场景 B: 备份也丢，从头重建
```bash
ssh -i ai_video.pem ubuntu@101.34.52.232 "
  sudo docker exec ai_video_backend python3 /tmp/scrape_momcozy.py --force
"
```

scraper 是幂等的，可以从零完整重建。前提：momcozy.com 还在线、产品 URL 没失效。

## 六、新增其他品牌（非 momcozy）

当前 scraper 硬编码 momcozy.com Shopify endpoint。新增品牌：

1. 抽象出 scraper 配置：把 PRODUCT_URLS 改为 `brands/{brand}.json` 读取
2. 拓展 BRAND_DIR 为 `output/brand_assets/{brand}/`
3. 后端 `/api/portfolio/brand-presets?brand={brand}` 已支持多品牌（路径参数已通用）
4. 前端 BrandKitTab 添加品牌切换 dropdown

预计 2-3h 工作量，超出本 runbook 范围。

## 七、监控

- **健康检查**: 每天看 `/api/portfolio/?kind=brand_kit` 返回 `total > 0`
- **告警阈值**: 若 `total < 100` 持续 24h，DingTalk 通知（品牌资产丢失）
- **日志**: `tail -f /var/log/brand-assets-refresh.log` 看 cron 是否正常跑

## 八、相关 Runbook

- [poyo-rejection.md](./poyo-rejection.md) — POYO 内容审核
- [pipeline-stuck.md](./pipeline-stuck.md) — Pipeline 卡死
- [../disaster_recovery_runbook.md](../disaster_recovery_runbook.md) — 整库 DR
