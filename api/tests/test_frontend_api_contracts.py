"""
Contract check entre las páginas HTML (fetch POST/PUT/PATCH) y los
Pydantic models reales de los endpoints — ver scripts/check_api_contracts.py
para el detalle de cómo funciona y sus limitaciones (es heurístico, basado
en regex sobre el JS, no un parser real; cobertura ~30% de las llamadas
totales porque las que usan FormData o construyen la URL de formas poco
comunes no son verificables estáticamente).

Nació de un patrón recurrente de bugs reales en esta sesión: el frontend
mandaba un campo con un nombre distinto al que el backend espera
(ej. {content: ...} en vez de {body: ...} en los comentarios de actividad),
y como nada lo comparaba automáticamente, el bug vivió sin detectarse hasta
que un usuario real lo pisó. Este test evita que un mismatch NUEVO de esa
misma clase llegue a producción sin que al menos un test lo marque.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_api_contracts import (  # noqa: E402
    get_backend_routes,
    extract_frontend_calls,
    js_url_matches_path,
)


def test_frontend_fetch_bodies_match_backend_required_fields():
    contracts = get_backend_routes()
    mismatches = []

    for html_file in sorted(REPO_ROOT.glob("*.html")):
        text = html_file.read_text(encoding="utf-8", errors="ignore")
        for method, url_expr, keys in extract_frontend_calls(text):
            if keys is None:
                continue  # body no-literal (FormData, variable) — no verificable estáticamente
            candidates = [
                (path, fields) for (m, path), fields in contracts.items()
                if m == method and js_url_matches_path(url_expr, path)
            ]
            if not candidates:
                continue
            path, required = max(candidates, key=lambda c: len(c[0]))
            missing = required - keys
            if missing:
                mismatches.append(
                    f"{html_file.name}: {method} ~{path} — faltan {sorted(missing)} "
                    f"(el fetch manda {sorted(keys)})"
                )

    assert not mismatches, "Mismatches frontend↔backend detectados:\n" + "\n".join(mismatches)
