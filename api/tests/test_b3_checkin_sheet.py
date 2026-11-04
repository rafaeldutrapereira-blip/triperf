"""
B3 — check-in en hoja unica de 9 campos en Hoy (athlete-app.html).

La hoja reutiliza estado-checkin.js (mismo contrato que estado.html, S28) y guarda
fisico + mental en un solo gesto contra /recovery/wellness y /mental/checkin.
Se ejecuta el JS real de la hoja con node, con apiFetch/DOM simulados.
"""
import json
import os
import re
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NODE = shutil.which("node")
HTML = open(os.path.join(ROOT, "athlete-app.html"), encoding="utf-8").read()
SW = open(os.path.join(ROOT, "sw.js"), encoding="utf-8").read()

ANSWERS = dict(energy=4, soreness=3, stress=2, sleep_quality=5, mood=4,
               motivation=3, anxiety=5, focus=2, confidence=4)

HARNESS = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8');
const EC = require(process.argv[2]);
const cfg = JSON.parse(process.argv[3]);
const a = html.indexOf('var _CK_GROUPS');
const b = html.indexOf('/* ── Pantalla Mental (Sprint 2 del roadmap app↔web) — mismos', a);
if (a < 0 || b < 0) { throw new Error('bloque de hoja no encontrado'); }
const src = html.slice(a, b);

const calls = [], toasts = [], els = {};
function el(id) {
  return els[id] || (els[id] = { id, value: '', disabled: false, innerHTML: '',
    classList: { add() { this.open = true; }, remove() { this.open = false; }, open: false } });
}
global.window = { EstadoCheckin: EC };
global.document = { getElementById: el, querySelector: () => null };
global._token = 'tok';
global.todayIso = () => '2026-11-04';
global._t = (k, fb) => fb;
global.toast = (m, c) => toasts.push([m, c]);
let verdictRefreshes = 0;
global.loadEstadoHoy = () => { verdictRefreshes++; };
global.apiFetch = (url, opts) => {
  const method = (opts && opts.method) || 'GET';
  calls.push({ method, url, body: opts && opts.body ? JSON.parse(opts.body) : null });
  const g = (cfg.get || {})[url];
  const status = (cfg.status || {})[url] || 200;
  const payload = g !== undefined ? g : { ok: true };
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(payload) });
};
const run = new Function('EC', src + `
  return { openCheckin, saveCheckin, ckSet, closeCheckin, get ck() { return _ck; } };`);
const api = run(EC);
const tick = () => new Promise(r => setTimeout(r, 20));
(async () => {
  api.openCheckin();
  await tick();
  const loadCalls = calls.length;
  (cfg.set || []).forEach(([f, v]) => api.ckSet(f, v));
  if (cfg.note) { el('ck-notes').value = cfg.note; api.ck.notesTouched = true; }
  api.saveCheckin();
  await tick();
  process.stdout.write(JSON.stringify({
    calls, loadCalls, toasts, verdictRefreshes,
    open: el('ck-sheet-overlay').classList.open,
    answers: api.ck.answers, notes: el('ck-notes').value,
  }));
})();
"""


def _run(cfg):
    out = subprocess.run(
        [NODE, "-e", HARNESS, os.path.join(ROOT, "athlete-app.html"),
         os.path.join(ROOT, "estado-checkin.js"), json.dumps(cfg)],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)


def _expected(answers, note=None):
    out = subprocess.run(
        [NODE, "-e",
         "const EC=require(process.argv[1]);const o=JSON.parse(process.argv[2]);"
         "process.stdout.write(JSON.stringify(EC.buildPayloads(o.a,{dateIso:'2026-11-04',touched:{},"
         "notes:o.n,notesTouched:!!o.n})));",
         os.path.join(ROOT, "estado-checkin.js"), json.dumps({"a": answers, "n": note})],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)


needs_node = pytest.mark.skipif(NODE is None, reason="node no disponible")


@needs_node
def test_hoja_guarda_fisico_y_mental_en_un_gesto():
    r = _run({"set": list(ANSWERS.items()), "note": "viaje"})
    posts = [c for c in r["calls"] if c["method"] == "POST"]
    assert [p["url"] for p in posts] == ["/recovery/wellness", "/mental/checkin"]  # fisico primero
    exp = _expected(ANSWERS, "viaje")
    assert posts[0]["body"] == exp["well"]
    assert posts[1]["body"] == exp["men"]
    # los 9 campos viajan: 6 en bienestar, 5 en mental (mood/motivation compartidos)
    assert {"energy", "soreness", "stress", "sleep_quality", "mood", "motivation"} <= set(posts[0]["body"])
    assert {"anxiety", "focus", "confidence", "mood", "motivation"} <= set(posts[1]["body"])
    assert r["open"] is False  # la hoja se cierra
    assert r["toasts"][-1][1] == "ok"


@needs_node
def test_hoja_refresca_el_veredicto_de_hoy_tras_guardar():
    r = _run({"set": list(ANSWERS.items())})
    assert r["verdictRefreshes"] == 1
    # el semaforo de Hoy lee el estado-hoy del servidor, que ya incluye el check-in
    assert "apiFetch('/athlete/estado-hoy?date_iso=' + todayIso())" in HTML
    assert re.search(r"chain\.then\(function \(\) \{[\s\S]*?loadEstadoHoy\(\);", HTML)


@needs_node
def test_hoja_solo_mental_o_solo_fisico_envia_un_post():
    r = _run({"set": [["anxiety", 4], ["focus", 3]]})
    posts = [c["url"] for c in r["calls"] if c["method"] == "POST"]
    assert posts == ["/mental/checkin"]
    r = _run({"set": [["energy", 4]]})
    posts = [c["url"] for c in r["calls"] if c["method"] == "POST"]
    assert posts == ["/recovery/wellness"]


@needs_node
def test_hoja_vacia_no_envia_nada():
    r = _run({"set": []})
    assert [c for c in r["calls"] if c["method"] == "POST"] == []
    assert r["open"] is True


@needs_node
def test_hoja_precarga_lo_registrado_hoy():
    r = _run({
        "get": {
            "/recovery/wellness/2026-11-04": {"logged": True, "energy": 4, "mood": 2, "notes": "ok"},
            "/mental/dashboard?date_iso=2026-11-04": {"checkin": {"anxiety": 5, "mood": 3, "focus": 2}},
        },
        "set": [],
    })
    assert r["loadCalls"] == 2
    assert r["answers"]["energy"] == 4
    assert r["answers"]["anxiety"] == 5 and r["answers"]["focus"] == 2
    assert r["answers"]["mood"] == 2  # compartido: manda el bienestar
    assert r["notes"] == "ok"


@needs_node
def test_hoja_plan_sin_recovery_muestra_aviso_de_plan():
    r = _run({"set": list(ANSWERS.items()), "status": {"/recovery/wellness": 403}})
    assert "plan" in r["toasts"][-1][0].lower()
    assert r["toasts"][-1][1] != "ok"


def test_hoja_y_boton_en_hoy():
    assert 'onclick="openCheckin()"' in HTML
    assert 'id="ck-sheet-overlay"' in HTML
    assert '<script src="estado-checkin.js"></script>' in HTML
    # un solo contrato: la hoja usa el reparto de estado-checkin.js, no payloads propios
    assert "window.EstadoCheckin.buildPayloads" in HTML
    for f in ("energy", "soreness", "sleep_quality", "stress", "mood", "motivation",
              "anxiety", "focus", "confidence"):
        assert "['" + f + "'," in HTML


def test_checkins_viejos_ya_no_existen():
    for dead in ("submitWellness", "saveMentalCheckin", "loadWellnessToday",
                 "wl-checkin-content", "wl-tab-checkin", "mtl-ws-", "_wlInitStars",
                 "_mtlInitStars", "app_mental_checkin_save", "wl-notes"):
        assert dead not in HTML, dead
    assert "wellnessTab('checkin')" not in HTML


def test_estado_checkin_precacheado_y_build_subido():
    assert "'/estado-checkin.js'" in SW
    m = re.search(r"var BUILD_VERSION = '(\d+)'", SW)
    assert m and int(m.group(1)) >= 291
