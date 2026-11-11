.DEFAULT_GOAL := help
BACKEND := backend
UV := uv
COMPOSE := docker compose -f deploy/docker-compose.yml

.PHONY: help install lint fmt typecheck lint-imports test test-unit check up down migrate revision

help: ## 列出所有目标
	@echo "install lint fmt typecheck lint-imports test test-unit check up down migrate revision"

install: ## uv sync（按 uv.lock 安装）
	cd $(BACKEND) && $(UV) sync --frozen

lint: ## ruff check + ruff format --check
	cd $(BACKEND) && $(UV) run --frozen ruff check . && $(UV) run --frozen ruff format --check .

fmt: ## ruff format + ruff check --fix
	cd $(BACKEND) && $(UV) run --frozen ruff format . && $(UV) run --frozen ruff check --fix .

typecheck: ## mypy --strict
	cd $(BACKEND) && $(UV) run --frozen mypy --strict app tests

lint-imports: ## import-linter 架构契约
	cd $(BACKEND) && $(UV) run --frozen lint-imports --config pyproject.toml

test: ## pytest 全量（含覆盖率）
	cd $(BACKEND) && $(UV) run --frozen pytest

test-unit: ## pytest tests/unit
	cd $(BACKEND) && $(UV) run --frozen pytest tests/unit

check: lint typecheck lint-imports test ## 全量质量门禁

up: ## docker compose 起全栈
	$(COMPOSE) up -d --build

down: ## docker compose 停止
	$(COMPOSE) down

migrate: ## alembic upgrade head
	cd $(BACKEND) && $(UV) run --frozen alembic upgrade head

revision: ## alembic revision --autogenerate -m "msg"
	cd $(BACKEND) && $(UV) run --frozen alembic revision --autogenerate -m "$(m)"
