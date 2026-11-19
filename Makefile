# 開発用コマンド（specs/001-p0-skeleton R2）。
.PHONY: erp-init sim-odoo erp-reset up-erp setup dev-api dev-web up-infra up up-prod down eval-api eval-api-down test lint gen gen-check graph graph-check licenses

setup: ## 依存をロックどおりに導入
	cd api && uv sync --locked
	cd mock/systems && uv sync --locked
	cd mcp/erp && uv sync --locked
	cd sim && uv sync --locked
	cd web && pnpm install --frozen-lockfile

dev-api: ## API を自動リロードで起動（インフラは `make up-infra`）
	cd api && uv run uvicorn arag.main:create_app --factory --reload --port 8100

dev-web: ## Web を開発モードで起動
	cd web && pnpm dev --port 3100

up-infra: ## postgres / qdrant / redis だけ起動
	docker compose up -d postgres qdrant redis

up: ## 全サービスを開発構成で起動（compose.override.yaml。ソースを載せ、変えたらその場で反映）
	docker compose up -d --build --wait --renew-anon-volumes

up-prod: ## 全サービスを本番と同じ構成で起動（build した image で動かす。push 前の確認など）
	docker compose -f compose.yaml up -d --build --wait

up-mock: ## 模擬の社内システム（specs/032）を起動し、MCP サーバとして登録する
	docker compose --profile mock up -d --build --wait mock-systems
	docker compose exec api python -m arag.cli mcp-register --mock

ODOO_DUMP ?= .data/erp/harukaze-034.dump

erp-init: ## Odoo の DB（harukaze）を空から作り直す（specs/033 T2。2〜3 分）
	docker compose --profile erp up -d --wait odoo-db
	docker compose --profile erp stop odoo erp-mcp
	docker compose --profile erp exec -T odoo-db dropdb -U odoo --if-exists harukaze
	docker compose --profile erp run --rm --no-deps -T odoo odoo --database=harukaze \
		-i stock,purchase,sale_management,l10n_jp --without-demo=all --load-language=ja_JP --stop-after-init
	docker compose --profile erp up -d odoo

sim-odoo: erp-init ## 模擬器（specs/034）の世界を Odoo に業務の流れとして入れ、スナップショットにする（30 分前後）
	cd sim && ERP_ODOO_SECRET=$$(grep '^ERP_ODOO_SECRET=' ../.env | cut -d= -f2-) uv run python -m harukaze_sim odoo
	mkdir -p $(dir $(ODOO_DUMP))
	docker compose --profile erp exec -T odoo-db pg_dump -U odoo -Fc harukaze > $(ODOO_DUMP)
	shasum -a 256 $(ODOO_DUMP)

erp-reset: ## Odoo をスナップショット（ODOO_DUMP）の状態に戻す（評価の前に。specs/033 R23）
	test -f $(ODOO_DUMP) || (echo "$(ODOO_DUMP) がありません。make sim-odoo で作ってください" && exit 1)
	docker compose --profile erp up -d --wait odoo-db
	docker compose --profile erp stop odoo erp-mcp
	docker compose --profile erp exec -T odoo-db dropdb -U odoo --if-exists harukaze
	docker compose --profile erp exec -T odoo-db createdb -U odoo harukaze
	docker compose --profile erp exec -T odoo-db pg_restore -U odoo -d harukaze --no-owner < $(ODOO_DUMP)
	docker compose --profile erp up -d odoo

up-erp: ## Odoo と ERP の MCP サーバを起こし、ARag に登録する（specs/033）
	docker compose --profile erp up -d --build --wait odoo erp-mcp
	docker compose exec api python -m arag.cli mcp-register --erp

down:
	docker compose --profile eval --profile mock --profile erp down

eval-api: ## 評価・CLI 用の api（開発用ヘッダで認証、127.0.0.1:8101）を起動
	docker compose -f compose.yaml --profile eval up -d --build --wait api-eval

eval-api-down: ## 評価・CLI 用の api を止める
	docker compose -f compose.yaml --profile eval stop api-eval

test: ## 単体テスト
	cd api && uv run pytest -q
	cd mock/systems && uv run pytest -q
	cd mcp/erp && uv run pytest -q
	cd sim && uv run pytest -q
	uv run --project api pytest -q -p no:cacheprovider --rootdir scripts scripts
	cd web && pnpm test

lint: ## 静的検査
	cd api && uv run ruff check . && uv run ruff format --check . && uv run mypy
	cd mock/systems && uv run ruff check . && uv run ruff format --check . && uv run mypy
	cd mcp/erp && uv run ruff check . && uv run ruff format --check . && uv run mypy
	cd sim && uv run ruff check . && uv run ruff format --check . && uv run mypy
	cd web && pnpm lint && pnpm typecheck

gen: ## OpenAPI 文書と TS 型を再生成
	cd api && uv run python -m arag.openapi_export
	cd web && pnpm gen:api

gen-check: gen ## 生成物がコミット済みと一致するか
	git diff --exit-code -- api/openapi.json web/src/lib/api/schema.d.ts

graph: ## 回答の流れの図をグラフの定義から書き出す（docs/agent-graph.md・web の flow-graph.json）
	cd api && uv run python -m arag.agent.diagram

graph-check: ## 書き出した図がグラフの定義と一致するか
	cd api && uv run python -m arag.agent.diagram --check

licenses: ## 依存ライセンス走査（本番依存のみ）
	mkdir -p .tmp
	cd api && uv export --no-dev --locked --no-emit-project --no-hashes -o ../.tmp/req.txt
	uv run --isolated --no-project --with-requirements .tmp/req.txt --with pip-licenses pip-licenses --format=json > .tmp/pip.json
	cd web && pnpm licenses list --prod --json > ../.tmp/pnpm.json
	python3 scripts/check_licenses.py --pip .tmp/pip.json --pnpm .tmp/pnpm.json
