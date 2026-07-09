---
title: Root directory governance
doc_type: workflow
module: project
topic: root-directory-governance
status: stable
created: 2026-06-01
updated: 2026-07-09
owner: self
source: human+ai
---

# Root directory governance

## 1. 目标

仓库根目录只保留项目入口文件、系统级配置和已分类顶层目录。业务文档、草稿、截图、报告、调试输出、临时脚本和中间产物不得直接落到根目录。

根目录契约在 `configs/root-directory-governance-contract.json`。新增根目录文件或顶层目录前，先确认无法放入现有标准目录，再更新契约并运行 `tests/test_root_directory_governance.py`。

## 2. 默认落点

- 文档：正式文档进入 `docs/`；未定稿文档进入 `drafts/docs/`。
- 分析：未定稿或一次性分析进入 `drafts/analysis/`。
- 临时输出：一次性结果进入 `tmp/outputs/`。
- 截图：临时截图进入 `tmp/screenshots/`。
- 调试材料：短期调试材料进入 `tmp/debug/`。
- 历史保留：失活但需要保留的内容进入 `archive/`。
- 脚本：可复用脚本进入 `scripts/`；一次性脚本进入 `drafts/scripts/` 或 `tmp/`。

## 3. 当前 tracked 根目录分类

### allowed_root_files

| path | status |
| --- | --- |
| `.dockerignore` | config |
| `.env.example` | config |
| `.gitignore` | config |
| `AGENTS.md` | entrypoint |
| `CHANGELOG.md` | entrypoint |
| `CLAUDE.md` | entrypoint |
| `CONTRIBUTING.md` | entrypoint |
| `Dockerfile` | config |
| `Dockerfile.backend` | config |
| `LICENSE` | entrypoint |
| `Makefile` | entrypoint |
| `README.md` | entrypoint |
| `SECURITY.md` | entrypoint |
| `docker-compose.yml` | config |
| `pyproject.toml` | config |
| `render.yaml` | config |
| `requirements.txt` | config |
| `uv.lock` | config |

### allowed_root_directories

| path | status |
| --- | --- |
| `.codegraph` | config |
| `.github` | config |
| `configs` | config |
| `deploy` | deployment_directory |
| `docs` | project_asset_directory |
| `eval` | test_directory |
| `migrations` | config |
| `prompts` | project_asset_directory |
| `rendering` | source_directory |
| `scripts` | source_directory |
| `src` | source_directory |
| `strategy_source` | project_asset_directory |
| `templates` | project_asset_directory |
| `tests` | test_directory |
| `web` | source_directory |

### legacy_tracked_root_directories

| path | status |
| --- | --- |
| `.sisyphus` | legacy_tracked_metadata |

## 4. 本地-only 根目录项

`local_only_root_artifacts` 必须保持 gitignored。典型项包括 `.env`、`.DS_Store`、`.venv/`、`node_modules/`、`.pytest_cache/`、`.ruff_cache/`、`output/`、`tmp/`、`drafts/`、`archive/`、`worktrees/`、`.claude/`、`.kiro/`、`.hermes/`、`.playwright-mcp/`、`.omc/`、`.next/`、`coverage/`、`htmlcov/`、`web/blob-report/`、`web/playwright-report/`、`web/test-results/`、`web/tmp/`、`rendering/output/`。

这些目录和文件可以在本地存在，但不得成为 tracked 项。若必须提升为正式资产，先迁移到正确目录并更新契约。

## 5. 禁止模式

根目录禁止新增带 `screenshot`、`capture`、`tmp`、`temp`、`draft`、`analysis`、`debug`、`final`、`report`、`output` 等语义的 tracked 文件。

根目录禁止新增 `.png`、`.jpg`、`.jpeg`、`.gif`、`.webp`、`.mp4`、`.mov`、`.avi`、`.log`、`.tmp`、`.bak` 等临时、截图、媒体或备份后缀的 tracked 文件。

发现污染时不要直接删除。先判断状态：仍有价值的迁入 `docs/`、`drafts/`、`tmp/` 或 `archive/`；无价值的删除需要单独确认。
