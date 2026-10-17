# LabX — Makefile de operaciones comunes
# S17: Comandos estandarizados para desarrollo, test, CI y deploy.
#
# El deploy real es GitHub Actions (.github/workflows/deploy.yml, SSH +
# systemd en el VM de GCP) — se dispara solo con el CI de main en verde,
# no hay target `make deploy` (los targets docker/VPS que existían acá
# describían una arquitectura que nunca se desplegó; eliminados en el
# Sprint 4 de higiene junto con Dockerfile/docker-compose*/deploy/*.sh).
#
# Uso:
#   make dev           → arranca API en modo desarrollo con reload
#   make test           → tests + coverage
#   make lint           → flake8 + bandit
#   make audit          → pip-audit (vulnerabilidades de dependencias)
#   make migrate-head   → aplica migraciones Alembic

.PHONY: dev prod test test-fast lint audit migrate-head migrate-gen migrate-down migrate-history db-shell secrets deploy-smoke logs clean help

# ── Variables ──────────────────────────────────────────────────
PYTHON   := python
UVICORN  := uvicorn
APP      := api.coach_main:app
PORT     := 8000
SSH_HOST ?= labx-prod

help:
	@echo "LabX Makefile — comandos disponibles:"
	@echo "  make dev            Arranca API con hot-reload"
	@echo "  make prod           Arranca API en modo producción (gunicorn)"
	@echo "  make test           Corre tests con coverage"
	@echo "  make test-fast      Corre tests sin coverage, -x -q"
	@echo "  make lint           flake8 + bandit"
	@echo "  make audit          pip-audit (vulnerabilidades)"
	@echo "  make migrate-head   Alembic upgrade head"
	@echo "  make secrets        Genera secretos para producción"
	@echo "  make deploy-smoke   Smoke tests post-deploy (BASE_URL=...)"
	@echo "  make clean          Limpia archivos temporales"
	@echo "  make logs           Sigue logs del servicio en producción"

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

# ── Tests (patrón LabX: --noconftest + ignores de suites con credenciales
#    externas reales — Strava/Stripe/year_in_review) ──────────────────────
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
db-shell:
	sqlite3 data/labx.db

# ── Alembic ────────────────────────────────────────────────────
migrate-head:
	alembic upgrade head

migrate-gen:
	alembic revision --autogenerate -m "$(MSG)"

migrate-down:
	alembic downgrade -1

migrate-history:
	alembic history --verbose

# ── Secrets / smoke test (scripts agnósticos a la arquitectura de deploy) ──
secrets:
	@echo "Generando secretos para producción..."
	@bash deploy/generate_secrets.sh

deploy-smoke:
	bash deploy/smoke_test.sh

# ── Operación remota (VM de producción) ────────────────────────
logs:
	ssh $(SSH_HOST) "sudo journalctl -fu labx"

# ── Limpieza ───────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -f coverage.xml .coverage bandit-report.json pip-audit-report.json
	@echo "✓ Limpieza completada"
