"""
Regresión XSS — coach.html::esc()
===================================
Auditoría 2026-10-17: se encontró un payload real almacenado en producción
(cuenta de test "e2e_athlete_45f464@labx-test.com", nombre literal
`<img src=x onerror=alert('XSS')>`) que rompía los atributos onclick de
coach.html, construidos como:
    onclick="openAthletePlan('ID','"+esc(u.nombre)+"')"
`esc()` escapaba entidades HTML (&<>") pero no la comilla simple — como
el delimitador del string JS embebido en el onclick también es comilla
simple, cualquier nombre con ' rompía el string y permitía inyectar JS.

Este test corre el esc() REAL de coach.html (vía Node, no una reimplemen-
tación en Python) contra el payload capturado y simula el pipeline real
del navegador: 1) el parser HTML decodifica entidades en el atributo
onclick ANTES de que el motor JS lo lea como código, 2) el resultado se
intenta parsear como JS. Si esc() está roto, el paso 2 falla con un
SyntaxError de Node (string sin cerrar) — la forma exacta en que se
manifestaba el bug real.
"""
import html
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
COACH_HTML = ROOT / "coach.html"

REAL_PRODUCTION_PAYLOAD = "<img src=x onerror=alert('XSS')>"


def _extract_esc_function() -> str:
    """Extrae el código fuente real de esc() desde coach.html (no una copia)."""
    content = COACH_HTML.read_text(encoding="utf-8")
    matches = re.findall(r"function esc\(s\)\{.*?\n\}", content, re.DOTALL)
    assert matches, "No se encontró function esc(s){...} en coach.html"
    return matches[0]


def _esc_count() -> int:
    content = COACH_HTML.read_text(encoding="utf-8")
    return len(re.findall(r"^function esc\(s\)", content, re.MULTILINE))


def _run_node(js_code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", "-e", js_code],
        capture_output=True, text=True, timeout=10,
    )


class TestEscDeduplicated:
    def test_only_one_esc_definition_in_coach_html(self):
        """2026-10-17: había 2 copias idénticas de esc() — una quedaba
        desactualizada si solo se arreglaba la otra. Debe quedar una sola."""
        assert _esc_count() == 1, (
            f"Se esperaba exactamente 1 definición de esc() en coach.html, "
            f"se encontraron {_esc_count()} — ¿volvió a duplicarse?"
        )


class TestEscEscapesSingleQuoteAsBackslash:
    """esc() debe escapar ' como \\' (escape de string JS), NO como entidad
    HTML (&#39;/&apos;) — el parser HTML decodifica entidades en atributos
    ANTES de que el motor JS lea el onclick, así que una entidad no evita
    el breakout del string."""

    def _esc(self, value: str) -> str:
        esc_src = _extract_esc_function()
        js = esc_src + f"\nprocess.stdout.write(esc({value!r}));"
        # value!r en Python usa comillas simples por defecto — convertir a
        # un literal JS válido pasándolo como string JSON (doble comilla).
        import json
        js = esc_src + f"\nprocess.stdout.write(esc({json.dumps(value)}));"
        result = _run_node(js)
        assert result.returncode == 0, f"esc() crasheó: {result.stderr}"
        return result.stdout

    def test_single_quote_escaped_as_backslash_quote(self):
        out = self._esc("O'Brien")
        assert "\\'" in out, f"Comilla simple no escapada como \\': {out!r}"
        assert "&#39;" not in out and "&apos;" not in out, (
            f"No debe usar entidad HTML para la comilla: {out!r}"
        )

    def test_backslash_itself_is_escaped_first(self):
        """Un backslash literal en el valor no debe poder combinarse con el
        \\' inyectado para formar una secuencia de escape ambigua."""
        out = self._esc("a\\'b")  # valor real: a\'b
        # Debe quedar como a\\\'b (backslash escapado + comilla escapada),
        # nunca como a\'b sin el backslash duplicado (eso dejaría la comilla
        # efectivamente sin escapar una vez que JS interpreta \\ como \).
        assert out == "a\\\\\\'b", f"Secuencia ambigua: {out!r}"


class TestRealProductionPayload:
    """El payload exacto encontrado en producción (auditoría 2026-10-17)."""

    def test_esc_neutralizes_the_real_payload(self):
        esc_src = _extract_esc_function()
        import json
        js = esc_src + f"\nprocess.stdout.write(esc({json.dumps(REAL_PRODUCTION_PAYLOAD)}));"
        result = _run_node(js)
        assert result.returncode == 0
        escaped = result.stdout
        assert "\\'" in escaped, "El payload real contiene ' — debe quedar escapada"

    def test_onclick_attribute_survives_html_decode_and_parses_as_valid_js(self):
        """
        Simula el pipeline completo del navegador:
          1. coach.html construye: onclick="fn('ID','"+esc(payload)+"')"
          2. El HTML real que termina en el DOM decodifica entidades (&amp;
             &lt; &gt; &quot;) en el valor del atributo.
          3. El motor JS parsea ese string decodificado como código.
        Antes del fix (sin escapar \\'), el paso 3 fallaba con SyntaxError
        porque el string JS quedaba sin cerrar — eso era el bug real.
        """
        esc_src = _extract_esc_function()
        import json
        # Paso 1: construir el atributo onclick como lo hace coach.html real.
        js_build = esc_src + f"""
var escaped = esc({json.dumps(REAL_PRODUCTION_PAYLOAD)});
var onclickAttrValue = "openAthletePlan('abc123','" + escaped + "')";
process.stdout.write(onclickAttrValue);
"""
        built = _run_node(js_build)
        assert built.returncode == 0
        onclick_attr_value = built.stdout

        # Paso 2: decodificar entidades HTML como lo hace el parser del
        # navegador sobre el valor de un atributo (&amp; &lt; &gt; &quot;).
        decoded = html.unescape(onclick_attr_value)

        # Paso 3: el motor JS real (Node) debe poder parsear esto como una
        # llamada de función válida — sin SyntaxError, sin que el ')'
        # literal del payload cierre la llamada antes de tiempo.
        js_parse_check = f"""
function openAthletePlan(id, nombre) {{
  if (typeof globalThis.__xss_fired === 'undefined') globalThis.__xss_fired = false;
  return {{id: id, nombre: nombre}};
}}
var result = {decoded};
process.stdout.write(JSON.stringify(result));
"""
        parsed = _run_node(js_parse_check)
        assert parsed.returncode == 0, (
            f"El onclick decodificado no parsea como JS válido — breakout "
            f"de string confirmado. stderr: {parsed.stderr}\n"
            f"onclick value: {onclick_attr_value!r}"
        )
        # El payload crudo (sin escapar) no debe aparecer como código JS
        # ejecutado fuera del string — verificamos que terminó como DATO
        # (el argumento `nombre`), no como una tercera expresión/llamada.
        import json as _json
        result_obj = _json.loads(parsed.stdout)
        assert result_obj["id"] == "abc123"
        assert "onerror" in result_obj["nombre"]  # quedó como texto, no ejecutado


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
