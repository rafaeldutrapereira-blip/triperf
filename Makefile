# LabX — Makefile de operaciones comunes
# S17: Comandos estandarizados para desarrollo, test, CI y deploy.
#
# Uso:
#   make dev           → arranca API en modo desarrollo con reload
#   make test          → tests + coverage
#   make lint          → flake8 + bandit
#   make audit         → pip-audit (vulnerabilidades de dependencias)
#   make migrate       → aplica migraciones Alembic (si existe)
#   make deploy        → deploy producción (requiere SSH_HOST)

.PHONY: dev test lint audit migrate deploy clean help

# ── Variables ──────────────────────────────────────────────────
PYTHON   := python
UVICORN  := uvicorn
APP      := api.coach_main:app
PORT     := 8000
SSH_HOST ?= labx-prod

help:
	@echo "LabX Makefile — comandos disponibles:"
	@echo "  make dev      Arranca API con hot-reload"
	@echo "  make prod     Arranca API en modo producción (gunicorn)"
	@echo "  make test     Corre tests con coverage"
	@echo "  make lint     flake8 + bandit"
	@echo "  make audit    pip-audit (vulnerabilidades)"
	@echo "  make migrate  Alembic upgrade head"
	@echo "  make deploy   Sincroniza y reinicia en producción"
	@echo "  make clean    Limpia archivos temporales"
	@echo "  make logs     Sigue logs del servicio en producción"

# ── Desarrollo ─────────────────────────────────────────────────
dev:
	$(UVICORN) $(APP) --reload --host 0.0.0.0 --port $(PORT)

prod:
	gunicorn $(APP) \
		--workers 4 \
		--worker-class uvicorn.workers.UvicornWorker \
		--bind 0.0.0.0:$(PORT) \
		--timeout 60 \
		--access-logfile - \
		--error-logfile - \
		--preload

# ── Tests ──────────────────────────────────────────────────────
test:
	pytest api/tests/ -v \
		--cov=api \
		--cov-report=term-missing \
		--cov-report=xml:coverage.xml \
		--cov-fail-under=50 \
		-p no:warnings

test-fast:
	pytest api/tests/ -x -q --tb=short -p no:warnings

# ── Lint & Seguridad ───────────────────────────────────────────
lint:
	flake8 api/ \
		--max-line-length=120 \
		--extend-ignore=E501,W503 \
		--exclude=api/tests/
	bandit -r api/ \
		--skip B101,B601 \
		--severity-level HIGH \
		-f text

audit:
	pip-audit --format json -o pip-audit-report.json || true
	@$(PYTHON) -c "\
import json, sys; \
data = json.load(open('pip-audit-report.json')); \
vulns = data.get('vulnerabilities', []); \
critical = [v for v in vulns if any(f.get('fix_versions') for f in v.get('fix_versions', [{}]))]; \
print(f'pip-audit: {len(vulns)} vulnerabilidades encontradas'); \
sys.exit(1 if vulns else 0)"

# ── Base de datos ──────────────────────────────────────────────
migrate:
	@if [ -f alembic.ini ]; then \
		alembic upgrade head; \
	else \
		echo "No se encontró alembic.ini — las migraciones son automáticas en startup"; \
	fi

db-shell:
	sqlite3 data/labx.db

# ── Secrets generation ─────────────────────────────────────────
secrets:
	@echo "Generando secretos para producción..."
	@bash deploy/generate_secrets.sh

# ── Deploy ─────────────────────────────────────────────────────
deploy:
	@echo "→ Deploy a producción via deploy.sh..."
	bash deploy/deploy.sh

deploy-update:
	bash deploy/update.sh

deploy-rollback:
	bash deploy/rollback.sh

deploy-smoke:
	bash deploy/smoke_test.sh

logs:
	ssh $(SSH_HOST) "sudo journalctl -fu labx-api"

nginx-reload:
	ssh $(SSH_HOST) "sudo nginx -t && sudo systemctl reload nginx"

# ── Docker ─────────────────────────────────────────────────────
docker-build:
	docker build -t labx-api:latest .

docker-dev:
	docker compose up

docker-prod:
	docker compose --profile prod up -d

docker-test:
	docker compose run --rm api pytest api/tests/ --noconftest -q \
	  --ignore=api/tests/test_strava.py \
	  --ignore=api/tests/test_stripe.py

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f api

# ── Alembic ────────────────────────────────────────────────────
migrate-head:
	alembic upgrade head

migrate-gen:
	alembic revision --autogenerate -m "$(MSG)"

migrate-down:
	alembic downgrade -1

migrate-history:
	alembic history --verbose

# ── test con noconftest (patrón LabX) ──────────────────────────
test:
	pytest api/tests/ -v --noconftest \
		--ignore=api/tests/test_strava.py \
		--ignore=api/tests/test_stripe.py \
		--ignore=api/tests/test_year_in_review.py \
		--cov=api --cov-report=term-missing \
		--cov-report=xml:coverage.xml

test-fast:
	pytest api/tests/ -x -q --noconftest \
		--ignore=api/tests/test_strava.py \
		--ignore=api/tests/test_stripe.py \
		--ignore=api/tests/test_year_in_review.py

# ── Limpieza ───────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -f coverage.xml .coverage bandit-report.json pip-audit-report.json
	@echo "✓ Limpieza completada"
