.PHONY: install test lint coverage clean ci

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
