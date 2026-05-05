.PHONY: install test lint coverage clean ci portfolio portfolio-sync

# ── Setup ──

install:
	pip install -e ".[dev]"

# ── Testing ──

test:
	python -m pytest tests/ --tb=short -v

coverage:
	python -m pytest tests/ --tb=short --cov=src --cov-report=html --cov-report=xml
	@echo "=== Coverage HTML: htmlcov/index.html ==="

# ── Linting ──

lint:
	ruff check src/

lint-fix:
	ruff check src/ --fix

# ── Cleanup ──

clean:
	rm -rf htmlcov .coverage coverage.xml .pytest_cache __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# ── CI check (full pipeline) ──

ci: lint test
	@echo "=== CI OK ==="

# ── Portfolio index ──

# 扫描 output/ 下所有付费产物,重建 assets/portfolio/index.json
# 闭环测试结束 LangGraph pipeline.completed 自动触发(见 src/tools/portfolio_hook.py)
# 这条 target 用于手动重建,例如直接跑 scripts/test_*_e2e.py 后

portfolio:
	python scripts/portfolio_index.py

# rsync 本地 output/ 到 Lighthouse 服务器 backend_output volume。
# rsync 天然增量:只传改动文件,docker cp -rn no-clobber 不覆盖已上传同名。
# 第一次跑 ~5 分钟(280MB),后续 pipeline 跑出新文件再跑只传增量。
# 跑 dry-run 看会传什么:bash scripts/sync_output_to_lighthouse.sh --dry-run
# 详见:scripts/sync_output_to_lighthouse.sh

portfolio-sync:
	bash scripts/sync_output_to_lighthouse.sh
