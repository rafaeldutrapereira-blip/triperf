"""
check_api_contracts.py — Chequeo de contrato entre las páginas HTML y los
endpoints reales de FastAPI.

Por qué existe: varios bugs reales de producción de LabX (comentarios que
no se guardaban, subida de fotos, etc.) fueron un simple mismatch de nombre
de campo entre lo que manda un fetch() del frontend y lo que espera el
Pydantic model del backend — un typo silencioso que solo se detecta cuando
un usuario real lo pisa, porque no hay nada que lo compare automáticamente.

Qué hace: para cada endpoint POST/PUT/PATCH con un body Pydantic, junta sus
campos requeridos; para cada archivo .html, extrae los fetch() con method
POST/PUT/PATCH y los campos que manda en el body (JSON.stringify({...}));
empareja por path (soportando parámetros {id} vs variables JS) y reporta
cualquier campo requerido por el backend que el frontend nunca envía.

Es heurístico (regex sobre JS, no un parser real) — pensado para correr
como chequeo rápido antes de un commit que toque fetch()s o schemas, no
como gate 100% infalible de CI. Falsos negativos son posibles si el body
se arma con variables en vez de un objeto literal; en ese caso el chequeo
simplemente no puede evaluar ese endpoint y lo reporta como "no verificable"
en vez de fallar.

Uso:
    python scripts/check_api_contracts.py
    python scripts/check_api_contracts.py --strict   # exit code 1 si hay mismatches
"""
from __future__ import annotations

import re
import sys
import argparse
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def get_backend_routes():
    """Devuelve {(method, path_template): set(required_field_names)}."""
    from api.coach_main import app

    real_routes = []
    for r in app.routes:
        if type(r).__name__ == "_IncludedRouter":
            real_routes.extend(r.original_router.routes)
        elif hasattr(r, "methods"):
            real_routes.append(r)

    contracts = {}
    for route in real_routes:
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", None)
        endpoint = getattr(route, "endpoint", None)
        if not path or not endpoint:
            continue
        for method in methods:
            if method not in ("POST", "PUT", "PATCH"):
                continue
            required = _required_fields_from_endpoint(endpoint)
            if required is None:
                continue  # no pydantic body param found on this endpoint
            contracts[(method, path)] = required
    return contracts


def _required_fields_from_endpoint(endpoint):
    """Inspecciona los parámetros de la función y devuelve los campos
    requeridos del primer BaseModel que encuentre, o None si no hay body.

    Usa typing.get_type_hints() en vez de inspect.signature(...).annotation
    a secas: varios routers (community_routes.py incluido) tienen
    `from __future__ import annotations` (PEP 563), lo que hace que
    inspect.signature devuelva las anotaciones como STRING ('_CommentIn')
    en vez de la clase real — exactamente como lo resuelve FastAPI por
    dentro para poder validar el body en runtime.
    """
    import typing
    try:
        from pydantic import BaseModel
    except ImportError:
        return None

    try:
        hints = typing.get_type_hints(endpoint)
    except Exception:
        return None

    for ann in hints.values():
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            required = set()
            fields = getattr(ann, "model_fields", None) or getattr(ann, "__fields__", {})
            for name, info in fields.items():
                is_required = getattr(info, "is_required", None)
                if callable(is_required):
                    if is_required():
                        required.add(name)
                elif getattr(info, "required", False):
                    required.add(name)
                elif info is Ellipsis:
                    required.add(name)
            return required
    return None


STRING_LITERAL_RE = re.compile(r"'([^']*)'|\"([^\"]*)\"")


def js_url_matches_path(url_expr: str, path_template: str) -> bool:
    """
    Las URLs del frontend se arman por concatenación
    (API + '/community/posts/' + actId + '/comments'), no como un string
    literal completo — comparar con una sola regex contra todo el path
    template falla en cuanto hay un '+ variable +' de por medio (las
    comillas/operadores no matchean nada). En vez de eso: se extraen SOLO
    los pedazos de string literal del JS (ignorando variables) y se arma
    una regex con comodines entre ellos; si esa regex encuentra el path
    template del backend (con sus {param} reemplazados por un comodín),
    hay match. Esto es tolerante a cómo se concatena la URL en JS y no
    depende de reconstruir el string completo.
    """
    literals = [a or b for a, b in STRING_LITERAL_RE.findall(url_expr)]
    literals = [s for s in literals if s]  # descartar comillas vacías, ej. ''
    if not literals:
        return False
    # Anclado a inicio Y fin: sin esto, la URL '/community/groups' (un solo
    # segmento) matchea por substring dentro de
    # '/community/groups/{group_id}/challenges' (path más largo) — hay que
    # exigir que el patrón cubra el path completo, no un fragmento cualquiera.
    frontend_pattern = "^" + ".*?".join(re.escape(s) for s in literals) + "$"
    backend_placeholder = re.sub(r"\{[^}]+\}", "\x00PARAM\x00", path_template)
    return re.search(frontend_pattern, backend_placeholder) is not None


METHOD_RE = re.compile(r"method\s*:\s*['\"](\w+)['\"]")
JSON_BODY_RE = re.compile(r"body\s*:\s*JSON\.stringify\(\s*\{", re.DOTALL)
KEY_RE = re.compile(r"(?:^|[,{])\s*(?:'([^']+)'|\"([^\"]+)\"|([a-zA-Z_$][\w$]*))\s*:")


def _find_matching(text: str, open_idx: int, open_ch: str, close_ch: str) -> int:
    """Índice del cierre que balancea open_ch/close_ch empezando en open_idx
    (que debe apuntar al propio open_ch)."""
    depth = 0
    i = open_idx
    while i < len(text):
        if text[i] == open_ch:
            depth += 1
        elif text[i] == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def extract_frontend_calls(html_text: str):
    """Devuelve lista de (method, url_snippet, set(keys_enviadas)|None).
    Usa conteo de profundidad de paréntesis/llaves en vez de un regex simple,
    porque las llamadas reales anidan objetos (fetch(url, {body: JSON.stringify({...})}))."""
    calls = []
    for m in re.finditer(r"fetch\(", html_text):
        call_start = m.start()
        paren_open = m.end() - 1
        paren_close = _find_matching(html_text, paren_open, '(', ')')
        if paren_close == -1:
            continue
        args_text = html_text[paren_open + 1:paren_close]

        comma_idx = args_text.find(',')
        if comma_idx == -1:
            continue  # fetch(url) sin segundo argumento -> GET, no aplica
        url_expr = args_text[:comma_idx].strip()
        rest = args_text[comma_idx + 1:]

        brace_idx = rest.find('{')
        if brace_idx == -1:
            continue
        brace_close = _find_matching(rest, brace_idx, '{', '}')
        if brace_close == -1:
            continue
        opts = rest[brace_idx + 1:brace_close]

        method_m = METHOD_RE.search(opts)
        method = method_m.group(1).upper() if method_m else "GET"
        if method not in ("POST", "PUT", "PATCH"):
            continue

        body_m = JSON_BODY_RE.search(opts)
        if not body_m:
            calls.append((method, url_expr, None))  # FormData u otro body no verificable
            continue
        inner_open = body_m.end() - 1
        inner_close = _find_matching(opts, inner_open, '{', '}')
        if inner_close == -1:
            calls.append((method, url_expr, None))
            continue
        body_obj = opts[inner_open + 1:inner_close]

        keys = set()
        for km in KEY_RE.finditer(body_obj):
            keys.add(next(g for g in km.groups() if g))
        calls.append((method, url_expr, keys))
    return calls


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    contracts = get_backend_routes()

    html_files = sorted(REPO.glob("*.html"))
    total_checked = 0
    total_mismatch = 0
    total_unverifiable = 0
    total_ambiguous = 0

    for html_file in html_files:
        text = html_file.read_text(encoding="utf-8", errors="ignore")
        calls = extract_frontend_calls(text)
        for method, url_expr, keys in calls:
            candidates = [
                (path, fields) for (m, path), fields in contracts.items()
                if m == method and js_url_matches_path(url_expr, path)
            ]
            if not candidates:
                continue  # ningún endpoint con body pydantic matchea esta URL
            if len(candidates) > 1:
                # Más de un endpoint matchea la misma URL literal — quedarse
                # con el path más largo/específico (menos ambiguo), pero
                # marcarlo para no confiar ciegamente en el resultado.
                total_ambiguous += 1
            path, required = max(candidates, key=lambda c: len(c[0]))
            total_checked += 1
            if keys is None:
                total_unverifiable += 1
                continue
            missing = required - keys
            if missing:
                total_mismatch += 1
                print(f"[MISMATCH] {html_file.name}: {method} ~{path} — "
                      f"faltan campos requeridos {sorted(missing)} (el fetch manda {sorted(keys)})")

    print()
    print(f"Endpoints con contrato verificable: {total_checked} "
          f"({total_unverifiable} no verificables por body no-literal, "
          f"{total_ambiguous} con match ambiguo) — "
          f"{total_mismatch} mismatches encontrados.")

    if args.strict and total_mismatch:
        sys.exit(1)


if __name__ == "__main__":
    main()
