"""
Cabeceras de embed: las páginas se pueden incrustar solo desde el mismo origen
(Carga en Rendimiento, Coach). Un origen externo debe seguir bloqueado.

El navegador aplica el bloqueo; aquí verificamos que el servidor manda la
política correcta: SAMEORIGIN / frame-ancestors 'self', sin permitir orígenes
externos ni 'none'.
"""
import pytest


@pytest.mark.parametrize("path", ["/dashboard.html", "/detalle.html?metric=pmc&embed=1", "/adaptive.html"])
def test_html_se_puede_incrustar_solo_desde_el_mismo_origen(client, path, monkeypatch):
    # La CSP se envía solo en producción (APP_ENV=production).
    monkeypatch.setenv("APP_ENV", "production")
    r = client.get(path)
    assert r.status_code == 200, r.status_code
    assert r.headers.get("x-frame-options") == "SAMEORIGIN"
    csp = r.headers.get("content-security-policy", "")
    assert "frame-ancestors 'self'" in csp
    assert "frame-ancestors 'none'" not in csp


def test_no_se_permite_ningun_origen_externo(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    r = client.get("/dashboard.html")
    xfo = (r.headers.get("x-frame-options") or "").upper()
    assert xfo not in ("ALLOW-FROM", "*", "ALLOWALL")
    csp = r.headers.get("content-security-policy", "")
    fa = [part.strip() for part in csp.split(";") if part.strip().startswith("frame-ancestors")]
    assert fa == ["frame-ancestors 'self'"]
