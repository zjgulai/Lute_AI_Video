.PHONY: install test test-hermetic-scenarios test-hermetic-full lint typecheck monitoring-check recovery-check coverage clean ci portfolio portfolio-sync

PYTHON ?= .venv/bin/python
PROMTOOL_IMAGE ?= prom/prometheus:v3.13.1@sha256:3c42b892cf723fa54d2f262c37a0e1f80aa8c8ddb1da7b9b0df9455a35a7f893
ALERTMANAGER_IMAGE ?= prom/alertmanager:v0.32.1@sha256:51a825c2a40acc3e338fdd00d622e01ec090f72be2b3ea46be0839cd47a4d286

# ── Setup ──

install:
	uv sync --locked --extra dev

# ── Testing ──

test:
	$(PYTHON) -m pytest tests/ --tb=short -v

test-hermetic-scenarios:
	bash scripts/run_s1_s5_hermetic_regression.sh

test-hermetic-full:
	bash scripts/run_s1_s5_hermetic_regression.sh

coverage:
	$(PYTHON) -m pytest tests/ --tb=short --cov=src --cov-report=html --cov-report=xml
	@echo "=== Coverage HTML: htmlcov/index.html ==="

# ── Linting ──

lint:
	$(PYTHON) -m ruff check src tests scripts

lint-fix:
	$(PYTHON) -m ruff check src tests scripts --fix

typecheck:
	uv run --locked --extra dev pyright --pythonpath .venv/bin/python src
	uv run --locked --extra dev python scripts/check_pyright_ratchet.py

monitoring-check:
	docker run --rm --entrypoint /bin/promtool -v "$(CURDIR)/deploy/lighthouse/monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro" -v "$(CURDIR)/deploy/lighthouse/prometheus-alerts.yml:/etc/prometheus/prometheus-alerts.yml:ro" $(PROMTOOL_IMAGE) check config /etc/prometheus/prometheus.yml
	docker run --rm --entrypoint /bin/promtool -v "$(CURDIR):/workspace:ro" -w /workspace $(PROMTOOL_IMAGE) check rules deploy/lighthouse/prometheus-alerts.yml
	docker run --rm --entrypoint /bin/promtool -v "$(CURDIR):/workspace:ro" -w /workspace $(PROMTOOL_IMAGE) test rules tests/fixtures/prometheus-alerts.test.yml
	docker run --rm --entrypoint /bin/amtool -v "$(CURDIR)/deploy/lighthouse/monitoring/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro" $(ALERTMANAGER_IMAGE) check-config /etc/alertmanager/alertmanager.yml
	GRAFANA_ADMIN_PASSWORD_FILE=/dev/null RELEASE_SOURCE_SHA=monitoring-contract TEST_BUNDLE_KEY=monitoring-contract docker compose -f deploy/lighthouse/docker-compose.monitoring.yml --profile monitoring config --quiet
	$(PYTHON) -m pytest -q tests/test_prometheus_query_contract.py tests/test_monitoring_config.py tests/test_monitoring_ownership_contract.py

recovery-check:
	$(PYTHON) -m pytest -q tests/test_backup_manifest.py tests/test_offhost_backup.py tests/test_pg_restore_logical.py tests/test_backup_production_contract.py
	bash -n scripts/backup_production.sh scripts/restore_backup_database.sh scripts/install_backup_cron.sh deploy/lighthouse/build-and-deploy.sh
	uv run --locked --extra dev pyright --pythonpath .venv/bin/python scripts/pg_restore_logical.py scripts/verify_restored_database.py scripts/backup_manifest.py scripts/offhost_backup.py

# ── Cleanup ──

clean:
	rm -rf htmlcov .coverage coverage.xml .pytest_cache __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# ── CI check (full pipeline) ──

ci: lint typecheck test
	@echo "=== CI OK ==="

# ── Portfolio index ──

# 扫描 output/ 下所有付费产物,重建 assets/portfolio/index.json
# 闭环测试结束 LangGraph pipeline.completed 自动触发(见 src/tools/portfolio_hook.py)
# 这条 target 用于手动重建,例如直接跑 scripts/test_*_e2e.py 后

portfolio:
	$(PYTHON) scripts/portfolio_index.py
	$(PYTHON) scripts/generate_portfolio_thumbnails.py

# rsync 本地 output/ 到 Lighthouse 服务器 backend_output volume。
# rsync 天然增量:只传改动文件,docker cp -rn no-clobber 不覆盖已上传同名。
# 第一次跑 ~5 分钟(280MB),后续 pipeline 跑出新文件再跑只传增量。
# 跑 dry-run 看会传什么:bash scripts/sync_output_to_lighthouse.sh --dry-run
# 详见:scripts/sync_output_to_lighthouse.sh

portfolio-sync:
	bash scripts/sync_output_to_lighthouse.sh
