# GAP-18: CI/CD Pipeline Setup

> **目标：** 为项目建立 GitHub Actions CI/CD 管道——每次 push/PR 自动运行 lint + test，
> 覆盖 Python 3.11/3.12 矩阵，生成覆盖率报告。

---

## 架构概览

### GitHub Actions 工作流

```
.github/workflows/
├── ci.yml              # 主要 CI —— push + PR
├── test-matrix.yml      # 多 Python 版本矩阵（可选）
└── release.yml          # 打 tag 自动发布（可选）
```

### 第一阶段：CI（ci.yml，核心）

```yaml
on: [push, pull_request]

jobs:
  ci:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11"]
    steps:
      - checkout
      - setup python
      - pip install -e ".[dev]"
      - ruff check src/
      - python -m pytest tests/ --tb=short -v
```

### 第二阶段：覆盖率（上传到 Codecov / 加 badge）

```yaml
- name: Test with coverage
  run: python -m pytest tests/ --tb=short -v --cov=src --cov-report=xml
  
- name: Upload coverage
  uses: codecov/codecov-action@v4
```

### 第三阶段：Docker（可选——打 tag 自动构建）

---

## 实现任务

### Task 1: `.github/workflows/ci.yml`

**核心 CI 工作流：**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"
      - run: pip install ruff
      - run: ruff check src/ --output-format=github
      
  test:
    name: Test (Python ${{ matrix.python-version }})
    needs: lint
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
      fail-fast: false
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: "pip"
      - run: pip install -e ".[dev]"
      - run: python -m pytest tests/ --tb=short -v --cov=src --cov-report=xml
        env:
          # Mock API keys to prevent LLM call failures
          OPENAI_API_KEY: "sk-test"
          ANTHROPIC_API_KEY: "sk-ant-test"
      - uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
          fail_ci_if_error: false
```

**关键设计决策：**
- `concurrency.cancel-in-progress: true`——多次 push 只跑最新一次
- `fail-fast: false`——3.11 失败不影响 3.12 结果
- `cache: pip`——提速依赖安装
- 用 `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` 环境变量注入 mock key（排除 LLM 调用失败隐患）

### Task 2: `pyproject.toml` 更新

将 `ruff` 从 `[dev]` 移到单独 checks：

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]  # pycodestyle + pyflakes + isort + pep8-naming

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "--tb=short -v"

[tool.coverage.run]
source = ["src"]
omit = ["*/tests/*", "*/prompts/*"]
```

### Task 3: `Makefile`

添加常用本地命令（可选，为了开发体验）：

```makefile
.PHONY: install test lint coverage clean

install:
	pip install -e ".[dev]"

test:
	python -m pytest tests/ --tb=short -v

lint:
	ruff check src/

coverage:
	python -m pytest tests/ --tb=short --cov=src --cov-report=html
	open htmlcov/index.html || true

clean:
	rm -rf htmlcov .coverage coverage.xml .pytest_cache __pycache__
```

### Task 4: 验证

- 确保 CI 语法正确
- 确保 `.github/workflows/` 在 .gitignore 中不被忽略
- 回归测试保持 318+ 通过

---

## 质量门槛

- [x] Push/PR 触发 Lint + Test
- [x] Python 3.11/3.12 双版本
- [x] Ruff lint（pycodestyle + pyflakes + isort）
- [x] 覆盖率报告（xml 格式，可上传）
- [x] Makefile 本地开发命令
- [x] pip cache 加速
- [x] concurrency cancel-in-progress
