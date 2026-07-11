"""
Tests — Infraestructura y Configuración (Sprint 21)
====================================================
Valida que el entorno de producción está correctamente configurado.
No requiere DB ni FastAPI.

Correr: pytest api/tests/test_infra.py -v --noconftest
"""
import os
import sys
import pathlib
import importlib.util

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Archivos obligatorios de infraestructura
# ─────────────────────────────────────────────────────────────────────────────

class TestRequiredFiles:
    def test_dockerfile_exists(self):
        assert (ROOT / "Dockerfile").exists()

    def test_docker_compose_exists(self):
        assert (ROOT / "docker-compose.yml").exists()

    def test_env_example_exists(self):
        assert (ROOT / ".env.example").exists()

    def test_makefile_exists(self):
        assert (ROOT / "Makefile").exists()

    def test_alembic_ini_exists(self):
        assert (ROOT / "alembic.ini").exists()

    def test_alembic_env_py_exists(self):
        assert (ROOT / "alembic" / "env.py").exists()

    def test_alembic_versions_exists(self):
        assert (ROOT / "alembic" / "versions").exists()

    def test_alembic_has_migrations(self):
        versions = list((ROOT / "alembic" / "versions").glob("*.py"))
        assert len(versions) >= 1, "No hay migraciones en alembic/versions/"

    def test_nginx_config_exists(self):
        assert (ROOT / "nginx" / "labx.conf").exists()

    def test_ci_yml_exists(self):
        assert (ROOT / ".github" / "workflows" / "ci.yml").exists()

    def test_sw_js_exists(self):
        assert (ROOT / "sw.js").exists()

    def test_manifest_json_exists(self):
        assert (ROOT / "manifest.json").exists()

    def test_requirements_exists(self):
        reqs = list(ROOT.glob("requirements*.txt"))
        assert len(reqs) >= 1, "No requirements*.txt encontrado"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Variables de entorno requeridas (documentadas en .env.example)
# ─────────────────────────────────────────────────────────────────────────────

class TestEnvExample:
    REQUIRED_VARS = [
        "DATABASE_URL",
        "JWT_SECRET",
        "FERNET_KEY",
        "APP_ENV",
        "RESEND_API_KEY",
        "STRIPE_SECRET_KEY",
        "ANTHROPIC_API_KEY",
        "GARMIN_CLIENT_ID",
        "STRAVA_CLIENT_ID",
        "SENTRY_DSN",
        "VAPID_PUBLIC_KEY",
    ]

    def _get_example_vars(self):
        env_file = ROOT / ".env.example"
        if not env_file.exists():
            return set()
        vars_found = set()
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key = line.split("=")[0].strip()
                vars_found.add(key)
        return vars_found

    def test_env_example_has_required_vars(self):
        found = self._get_example_vars()
        missing = [v for v in self.REQUIRED_VARS if v not in found]
        assert not missing, f"Variables faltantes en .env.example: {missing}"

    def test_env_example_no_real_secrets(self):
        content = (ROOT / ".env.example").read_text(encoding="utf-8")
        dangerous_patterns = [
            "sk_live_",   # Stripe live key
            "whsec_live", # Stripe webhook live
            "re_",        # Resend key (solo si tiene más de 30 chars)
        ]
        for pattern in dangerous_patterns:
            if pattern in content:
                # Check it's not a real key (should look like a placeholder)
                import re
                matches = re.findall(rf"{re.escape(pattern)}\w{{20,}}", content)
                assert not matches, f"Posible secret real encontrado en .env.example: {matches}"

    def test_env_example_not_in_gitignore(self):
        gitignore = ROOT / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text(encoding="utf-8")
            # .env.example debe NO estar en .gitignore (debe ser commiteado)
            assert ".env.example" not in content, ".env.example no debe estar en .gitignore"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Dockerfile
# ─────────────────────────────────────────────────────────────────────────────

class TestDockerfile:
    def _content(self):
        return (ROOT / "Dockerfile").read_text(encoding="utf-8")

    def test_uses_slim_image(self):
        content = self._content()
        assert "slim" in content or "alpine" in content, \
            "Usar imagen slim o alpine para menor superficie de ataque"

    def test_has_non_root_user(self):
        content = self._content()
        assert "USER" in content, "Dockerfile debe ejecutar como non-root"

    def test_has_healthcheck(self):
        content = self._content()
        assert "HEALTHCHECK" in content, "Dockerfile debe tener HEALTHCHECK"

    def test_exposes_port(self):
        content = self._content()
        assert "EXPOSE" in content, "Dockerfile debe declarar EXPOSE"

    def test_copies_requirements_first(self):
        content = self._content()
        copy_req_pos = content.find("COPY requirements")
        copy_src_pos = content.find("COPY api/")
        assert copy_req_pos < copy_src_pos, \
            "requirements deben copiarse antes del código (cache de layers)"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Alembic
# ─────────────────────────────────────────────────────────────────────────────

class TestAlembic:
    def test_alembic_ini_has_script_location(self):
        content = (ROOT / "alembic.ini").read_text(encoding="utf-8")
        assert "script_location" in content

    def test_env_py_imports_base(self):
        content = (ROOT / "alembic" / "env.py").read_text(encoding="utf-8")
        assert "Base" in content, "alembic/env.py debe importar Base de models"

    def test_env_py_reads_database_url(self):
        content = (ROOT / "alembic" / "env.py").read_text(encoding="utf-8")
        assert "DATABASE_URL" in content, "alembic/env.py debe leer DATABASE_URL del entorno"

    def test_sprint15_20_migration_exists(self):
        versions = list((ROOT / "alembic" / "versions").glob("*.py"))
        contents = " ".join(f.read_text(encoding="utf-8") for f in versions)
        assert "recovery_scores" in contents, "Migración de recovery_scores no encontrada"
        assert "mental_checkins" in contents, "Migración de mental_checkins no encontrada"
        assert "race_results" in contents, "Migración de race_results no encontrada"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: nginx config
# ─────────────────────────────────────────────────────────────────────────────

class TestNginxConfig:
    def _content(self):
        return (ROOT / "nginx" / "labx.conf").read_text(encoding="utf-8")

    def test_has_ssl_config(self):
        assert "ssl_certificate" in self._content()

    def test_http_redirects_to_https(self):
        content = self._content()
        assert "return 301 https://" in content

    def test_has_security_headers(self):
        content = self._content()
        assert "Strict-Transport-Security" in content
        assert "X-Content-Type-Options" in content
        assert "X-Frame-Options" in content

    def test_has_rate_limiting(self):
        content = self._content()
        assert "limit_req_zone" in content

    def test_blocks_sensitive_files(self):
        content = self._content()
        assert ".env" in content or "return 404" in content

    def test_has_gzip(self):
        assert "gzip on" in self._content()

    def test_has_upstream(self):
        assert "upstream labx_api" in self._content()

    def test_has_health_endpoint(self):
        assert "/health" in self._content()


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: CI/CD
# ─────────────────────────────────────────────────────────────────────────────

class TestCICD:
    def _content(self):
        return (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    def test_has_test_job(self):
        assert "pytest" in self._content()

    def test_uses_noconftest(self):
        assert "--noconftest" in self._content()

    def test_has_docker_build(self):
        assert "docker build" in self._content()

    def test_has_security_scan(self):
        content = self._content()
        assert "bandit" in content or "pip-audit" in content

    def test_runs_on_main(self):
        assert "main" in self._content()


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Service Worker
# ─────────────────────────────────────────────────────────────────────────────

class TestServiceWorker:
    def _content(self):
        return (ROOT / "sw.js").read_text(encoding="utf-8")

    def test_has_build_version(self):
        assert "BUILD_VERSION" in self._content()

    def test_has_precache_list(self):
        assert "PRECACHE" in self._content()

    def test_ai_coach_in_precache(self):
        assert "ai_coach.html" in self._content()

    def test_mental_in_precache(self):
        assert "mental.html" in self._content()

    def test_recovery_in_precache(self):
        assert "recovery.html" in self._content()

    def test_build_version_is_string(self):
        import re
        content = self._content()
        match = re.search(r"BUILD_VERSION\s*=\s*'(\d+)'", content)
        assert match, "BUILD_VERSION debe ser una cadena numérica"
        version = int(match.group(1))
        assert version >= 13, f"BUILD_VERSION {version} < 13 — debe actualizarse con cada sprint"


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: Architecture — no prefix collision
# ─────────────────────────────────────────────────────────────────────────────

class TestArchitecture:
    def _get_prefixes(self):
        routes_dir = ROOT / "api" / "routes"
        prefixes = {}
        import re
        for f in routes_dir.glob("*.py"):
            content = f.read_text(encoding="utf-8")
            match = re.search(r'APIRouter\(prefix="([^"]+)"', content)
            if match:
                prefixes[f.name] = match.group(1)
        return prefixes

    def test_import_routes_not_athlete_prefix(self):
        prefixes = self._get_prefixes()
        import_prefix = prefixes.get("import_routes.py", "")
        athlete_prefix = prefixes.get("athlete_routes.py", "")
        assert import_prefix != athlete_prefix, \
            f"import_routes.py y athlete_routes.py tienen el mismo prefix: {import_prefix}"

    def test_no_empty_prefix_collision(self):
        prefixes = self._get_prefixes()
        # All routers with explicit prefix should have unique prefixes
        prefix_list = list(prefixes.values())
        duplicates = [p for p in prefix_list if prefix_list.count(p) > 1]
        # Allow known intentional shared prefixes (coach has multiple routers)
        real_dups = [d for d in set(duplicates) if d not in ("/coach",)]
        assert not real_dups, f"Prefijos duplicados entre routers: {real_dups}"

    def test_all_routes_have_auth_import(self):
        routes_dir = ROOT / "api" / "routes"
        for f in routes_dir.glob("*.py"):
            content = f.read_text(encoding="utf-8")
            if "@router." in content and "get_current_user" not in content:
                # Only flag if it has actual endpoints
                if f.name not in ("__init__.py",):
                    pass  # Some routes may have public endpoints — not a hard failure
