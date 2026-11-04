"""CQ3: un solo estimador de TSS (lx-tss.js) en dashboard, Mi Plan y Detalle."""
import io
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _r(name):
    with io.open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def test_helper_cargado_y_usado_en_las_tres_paginas():
    for f in ("dashboard.html", "training_plan.html", "detalle.html"):
        html = _r(f)
        assert 'src="lx-tss.js?v=1"' in html, f
        assert "window.LXTss.estimate(" in html, f


def test_sin_defaults_inventados():
    for f in ("dashboard.html", "training_plan.html", "detalle.html", "lx-tss.js"):
        t = _r(f)
        assert not re.search(r"_athleteFTP\s*\|\|\s*240", t), f
        assert not re.search(r"_athleteFCMax\s*\|\|\s*180", t), f
        assert not re.search(r"profile\.(ftp\s*\|\|\s*240|fcmax\s*\|\|\s*180)", t), f
        assert "Math.round(h * 50)" not in t, f
        assert not re.search(r"avg_hr \|\| (120|140|110)", t), f


def test_fuerza_sin_rpe_no_asume_6():
    t = _r("lx-tss.js")
    assert ": 6" not in t and "|| 6" not in t


def test_sw_precachea_helper():
    assert "/lx-tss.js?v=1" in _r("sw.js")
