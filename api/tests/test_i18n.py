"""
Batería de regresión para el sistema de idiomas (ES/PT/EN) de LabX.

Nace de la auditoría de 2026-10-10 (preparación del testing con usuarios
de Brasil), que encontró varios bugs de clases distintas que ningún test
anterior detectaba:
  - el idioma quedaba hardcodeado a español pese a guardarse en localStorage
  - páginas que cargan i18n.js pero referencian claves que no existen en el
    diccionario (se ven como "lnd_xxx" crudo en pantalla en vez de texto)
  - data-i18n-html sin data-i18n (el motor nunca encuentra el elemento)
  - las copias de i18n.js embebidas en android/, ios/ y www/ (usadas por
    Capacitor para armar los builds nativos) quedando desactualizadas
    respecto al repo, porque esas copias no se regeneran solas — hay que
    correr scripts/build_www.py + `npx cap sync` a mano.

Son tests puramente estáticos (parseo de texto), sin TestClient ni
servidor — mismo patrón que test_frontend_api_contracts.py.
"""
from __future__ import annotations

import pytest
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

I18N_JS = REPO_ROOT / "i18n.js"
SW_JS = REPO_ROOT / "sw.js"

MIRROR_I18N = [
    REPO_ROOT / "www" / "i18n.js",
    REPO_ROOT / "android" / "app" / "src" / "main" / "assets" / "public" / "i18n.js",
    REPO_ROOT / "ios" / "App" / "App" / "public" / "i18n.js",
]
MIRROR_SW = [
    REPO_ROOT / "www" / "sw.js",
    REPO_ROOT / "android" / "app" / "src" / "main" / "assets" / "public" / "sw.js",
    REPO_ROOT / "ios" / "App" / "App" / "public" / "sw.js",
]

_LANGS = ("es", "pt", "en")


def _extract_block(src: str, marker: str) -> str:
    """Extrae el bloque {...} que empieza en `marker` (balanceando llaves)."""
    i = src.index(marker)
    depth = 0
    started = False
    j = i
    while j < len(src):
        c = src[j]
        if c == "{":
            depth += 1
            started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                break
        j += 1
    return src[i : j + 1]


def _dict_keys(src: str, lang: str) -> set[str]:
    block = _extract_block(src, f"{lang}: {{")
    # Quitar comentarios /* ... */ (ej. "/* Formularios */") antes de
    # extraer claves -- si no, la clave que sigue justo después de un
    # comentario no queda precedida por '{' o ',' con solo espacios en
    # medio, y el regex la pierde (falso negativo).
    block = re.sub(r"/\*.*?\*/", "", block, flags=re.DOTALL)
    # Las entradas pueden compartir línea separadas por coma
    # (`a: 'x', b: 'y',`), así que no alcanza con buscar solo al
    # inicio de línea -- se matchea cualquier "clave:" precedida por
    # '{', ',' o salto de línea + espacios.
    return set(re.findall(r"[{,]\s*([A-Za-z0-9_]+)\s*:", block))


def _load_dicts() -> dict[str, set[str]]:
    src = I18N_JS.read_text(encoding="utf-8")
    return {lang: _dict_keys(src, lang) for lang in _LANGS}


def _i18n_pages() -> list[Path]:
    """Páginas HTML en la raíz que cargan i18n.js."""
    pages = []
    for f in sorted(REPO_ROOT.glob("*.html")):
        if 'i18n.js' in f.read_text(encoding="utf-8", errors="ignore"):
            pages.append(f)
    return pages


# ──────────────────────────────────────────────────────────────────────
# 1. Paridad del diccionario entre los 3 idiomas
# ──────────────────────────────────────────────────────────────────────

def test_dict_has_same_keys_across_all_languages():
    dicts = _load_dicts()
    es, pt, en = dicts["es"], dicts["pt"], dicts["en"]

    missing_in_pt = es - pt
    missing_in_en = es - en
    extra_in_pt = pt - es
    extra_in_en = en - es

    errors = []
    if missing_in_pt:
        errors.append(f"Faltan en PT: {sorted(missing_in_pt)}")
    if missing_in_en:
        errors.append(f"Faltan en EN: {sorted(missing_in_en)}")
    if extra_in_pt:
        errors.append(f"Sobran en PT (no están en ES): {sorted(extra_in_pt)}")
    if extra_in_en:
        errors.append(f"Sobran en EN (no están en ES): {sorted(extra_in_en)}")

    assert not errors, (
        "El diccionario de i18n.js quedó desalineado entre idiomas -- "
        "window.i18n.t() va a devolver la clave cruda en el idioma que "
        "falte.\n" + "\n".join(errors)
    )


def test_dict_values_are_not_empty():
    """Una clave con valor vacío '' se ve como texto en blanco en pantalla."""
    src = I18N_JS.read_text(encoding="utf-8")
    for lang in _LANGS:
        block = _extract_block(src, f"{lang}: {{")
        empty = re.findall(r"([A-Za-z0-9_]+)\s*:\s*''", block)
        assert not empty, f"Claves con valor vacío en '{lang}': {empty}"


# ──────────────────────────────────────────────────────────────────────
# 2. Toda página que carga i18n.js solo referencia claves que existen
# ──────────────────────────────────────────────────────────────────────

def test_every_data_i18n_key_exists_in_dictionary():
    dicts = _load_dicts()
    es_keys = dicts["es"]
    pattern = re.compile(
        r'data-i18n(?:-placeholder|-title)?="([a-zA-Z0-9_]+)"'
    )

    missing_by_page: dict[str, list[str]] = {}
    for page in _i18n_pages():
        text = page.read_text(encoding="utf-8", errors="ignore")
        used = set(pattern.findall(text))
        missing = sorted(k for k in used if k not in es_keys)
        if missing:
            missing_by_page[page.name] = missing

    assert not missing_by_page, (
        "Hay páginas con data-i18n apuntando a claves que no existen en "
        "el diccionario -- el usuario va a ver la clave cruda en vez de "
        "texto traducido:\n"
        + "\n".join(f"  {p}: {ks}" for p, ks in missing_by_page.items())
    )


def test_no_orphan_data_i18n_html_without_data_i18n():
    """
    Gotcha real encontrado en landing.html (2026-10-10): el motor de
    i18n.js selecciona elementos con `document.querySelectorAll('[data-i18n]')`.
    Un elemento que solo tiene `data-i18n-html="key"` (sin `data-i18n`)
    nunca se encuentra, y por lo tanto nunca se traduce -- sin ningún
    error visible, el contenido simplemente se queda fijo en español.
    """
    pattern = re.compile(r"<[^>]*\bdata-i18n-html=\"[^\"]*\"[^>]*>")
    offenders: dict[str, list[str]] = {}

    for page in _i18n_pages():
        text = page.read_text(encoding="utf-8", errors="ignore")
        for tag in pattern.findall(text):
            if "data-i18n=" not in tag:
                offenders.setdefault(page.name, []).append(tag[:80])

    assert not offenders, (
        "Elementos con data-i18n-html pero sin data-i18n (nunca se "
        "traducen, sin error visible):\n"
        + "\n".join(f"  {p}: {tags}" for p, tags in offenders.items())
    )


# ──────────────────────────────────────────────────────────────────────
# 3. Las copias embebidas en Android/iOS/www están sincronizadas con el
#    repo -- si no, los fixes de idioma nunca llegan a la app instalada.
# ──────────────────────────────────────────────────────────────────────

def test_mobile_mirrors_match_root_i18n():
    root_src = I18N_JS.read_text(encoding="utf-8")
    stale = [str(p.relative_to(REPO_ROOT)) for p in MIRROR_I18N
             if p.exists() and p.read_text(encoding="utf-8") != root_src]
    missing = [str(p.relative_to(REPO_ROOT)) for p in MIRROR_I18N if not p.exists()]
    if len(missing) == len(MIRROR_I18N):
        # Copias gitignored: en un checkout limpio (CI) no existen hasta correr build_www + cap sync
        pytest.skip("copias móviles no generadas en este checkout")

    assert not missing, (
        f"Copias de i18n.js faltantes (correr `npx cap sync`): {missing}"
    )
    assert not stale, (
        "Las copias de i18n.js en android/ios/www NO coinciden con el "
        "repo -- un usuario con la app instalada no recibe los fixes de "
        "idioma hasta que se regeneren con "
        "`python scripts/build_www.py && npx cap sync`.\n"
        f"Desactualizadas: {stale}"
    )


def test_mobile_mirrors_match_root_sw():
    root_src = SW_JS.read_text(encoding="utf-8")
    stale = [str(p.relative_to(REPO_ROOT)) for p in MIRROR_SW
             if p.exists() and p.read_text(encoding="utf-8") != root_src]
    missing = [str(p.relative_to(REPO_ROOT)) for p in MIRROR_SW if not p.exists()]
    if len(missing) == len(MIRROR_SW):
        # Copias gitignored: en un checkout limpio (CI) no existen hasta correr build_www + cap sync
        pytest.skip("copias móviles no generadas en este checkout")

    assert not missing, f"Copias de sw.js faltantes (correr `npx cap sync`): {missing}"
    assert not stale, (
        "Las copias de sw.js en android/ios/www NO coinciden con el "
        f"repo: {stale}"
    )


def test_sw_build_version_was_bumped_for_i18n_changes():
    """
    sw.js precachea i18n.js y login.html con estrategia cache-first -- un
    deploy que toque esos archivos SIN incrementar BUILD_VERSION deja a
    cualquier usuario con la PWA instalada sirviendo la versión vieja
    indefinidamente (hasta que cierre la app por completo, lo cual la
    mayoría de la gente nunca hace). Este test no puede saber si el
    commit actual "debería" haber bumpeado la versión, pero sí puede
    congelar que no baje de la última conocida.
    """
    text = SW_JS.read_text(encoding="utf-8")
    m = re.search(r"BUILD_VERSION\s*=\s*'(\d+)'", text)
    assert m, "No se encontró BUILD_VERSION en sw.js"
    version = int(m.group(1))
    assert version >= 144, (
        f"BUILD_VERSION ({version}) es menor al mínimo esperado (144, "
        "fijado en la corrección de idioma de 2026-10-10) -- revisar que "
        "no se haya revertido sw.js sin querer."
    )


# ──────────────────────────────────────────────────────────────────────
# 4. El idioma debe leerse de localStorage, no quedar fijo
#    (regresión directa del bug F1 de la auditoría)
# ──────────────────────────────────────────────────────────────────────

def test_i18n_script_tag_has_no_query_string():
    """
    Bug real encontrado en vivo (2026-10-10, Sprint 2b): cuatro páginas
    cargaban <script src="i18n.js?v=1">, un cache key de Cloudflare
    DISTINTO al que usan las otras 16 páginas (<script src="i18n.js">,
    sin query). Cloudflare cachea cada URL+query por separado -- la
    variante ?v=1 quedó congelada desde la primera vez que alguien la
    pidió, mientras la variante sin query sí se actualizaba en cada
    deploy. Resultado: durante buena parte de una sesión de trabajo,
    `curl .../i18n.js` (sin query, usado para verificar cada deploy)
    mostraba el diccionario actualizado, pero el navegador real --que
    pide exactamente la URL del atributo src, con su query string--
    seguía sirviendo una copia vieja, invisible a esa verificación.
    Mientras no haya un mecanismo real de cache-busting (ver nota en
    sw.js sobre BUILD_VERSION), la regla simple es: ninguna página debe
    agregar su propio query string a i18n.js.
    """
    offenders = []
    for page in _i18n_pages():
        text = page.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'<script[^>]+src="(i18n\.js[^"]*)"', text):
            src = m.group(1)
            if src != "i18n.js":
                offenders.append(f"{page.name}: src=\"{src}\"")

    assert not offenders, (
        "Página(s) cargando i18n.js con un query string distinto al resto "
        "del sitio -- Cloudflare lo cachea como una URL aparte y puede "
        "quedar desactualizada sin que un `curl .../i18n.js` (sin query) "
        "lo note:\n" + "\n".join(offenders)
    )


def test_lang_is_not_hardcoded():
    text = I18N_JS.read_text(encoding="utf-8")
    assert "var _lang = 'es';" not in text.replace(" ", "") or \
           "localStorage" in text, (
        "El idioma inicial parece estar hardcodeado de nuevo sin leer "
        "localStorage -- esto fue el bug crítico F1 de la auditoría "
        "2026-10-10 (el idioma no persistía entre páginas)."
    )
    assert "lx_lang" in text, "i18n.js ya no referencia la clave lx_lang de localStorage"
