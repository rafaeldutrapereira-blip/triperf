"""CQ8: la pelota de Estado (arco proporcional, rotulo del indicador que manda, idioma activo)."""
import io
import json
import os
import re
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _r(name):
    with io.open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


_JS = r"""
const fs=require('fs');
const root=process.argv[1], lang=process.argv[2], v=JSON.parse(process.argv[3]);
const m=fs.readFileSync(root+'/i18n.js','utf8').match(/var DICT = \{[\s\S]*?\n\};/);
eval(m[0]);
global.window={i18n:{t:(k)=>(DICT[lang]&&DICT[lang][k])||k}};
eval(fs.readFileSync(root+'/lx-estado-ball.js','utf8'));
const B=window.LXEstadoBall;
process.stdout.write(JSON.stringify({d:B.text(v),html:B.html(v,{size:64}),arc:B.arc(76)}));
"""


def _run(lang, v):
    out = subprocess.run(["node", "-e", _JS, ROOT, lang, json.dumps(v)],
                         capture_output=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def _verdict(governs="men", level="good", score=76, other=87):
    men = {"score": score if governs == "men" else other, "sev": 0, "level": level,
           "label": "Bueno", "text": "Buen estado mental. Entrena con confianza."}
    rec = {"score": score if governs == "rec" else other, "sev": 0, "level": "good",
           "label": "Buenas condiciones", "text": "x"}
    gov = men if governs == "men" else rec
    return {"status": "ok", "sev": 0, "score": score, "governs": governs,
            "label": gov["label"], "text": gov["text"], "mental": men, "recovery": rec}


def test_arco_refleja_el_valor():
    r = _run("es", _verdict(score=76))
    assert r["arc"]["pct"] == 76
    assert abs(r["arc"]["offset"] - 364 * 0.24) < 0.01
    m = re.search(r'class="lxb-ring"[^>]*stroke-dashoffset="([\d.]+)"', r["html"])
    assert m and abs(float(m.group(1)) - 364 * 0.24) < 0.01
    assert 'data-pct="76"' in r["html"]
    assert 'stroke="#10B981"' in r["html"]


def test_rotulo_nombra_al_indicador_que_manda_y_el_otro_secundario():
    r = _run("es", _verdict(governs="men", score=76, other=87))
    assert r["d"]["govName"] == "Mental"
    assert r["d"]["other"] == {"name": "Recuperación", "score": 87, "sev": 0}
    assert ">Mental<" in r["html"]
    r = _run("es", _verdict(governs="rec", score=60, other=80))
    assert r["d"]["govName"] == "Recuperación" and r["d"]["other"]["name"] == "Mental"


def test_pt_y_en_sin_cadenas_en_espanol():
    for lang, bueno, frase in (("pt", "Bom", "Bom estado mental"), ("en", "Good", "Good mental state")):
        r = _run(lang, _verdict())
        assert r["d"]["label"] == bueno
        assert r["d"]["text"].startswith(frase)
        assert "Bueno" not in r["d"]["label"] and "Buen estado" not in r["d"]["text"]


def test_sin_veredicto_ok_no_hay_arco():
    r = _run("es", {"status": "no_data", "sev": None, "score": None, "governs": None})
    assert r["d"] is None
    assert 'data-pct="0"' in r["html"]


def test_cableado_en_las_tres_paginas():
    app, dash, est = _r("athlete-app.html"), _r("dashboard.html"), _r("estado.html")
    for h in (app, dash, est):
        assert 'src="lx-estado-ball.js?v=1"' in h
    assert "LXEstadoBall.render(sc, v" in app and "paintRaceChip" in app
    assert "lx:langchange" in app
    assert "LXEstadoBall.render(ball, gov.raw" in dash
    assert "LXEstadoBall.text(v)" in est
    assert "/lx-estado-ball.js?v=1" in _r("sw.js")
    assert "border: 3px solid var(--border)" not in app
