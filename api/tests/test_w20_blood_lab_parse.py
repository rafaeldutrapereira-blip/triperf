"""W20 — Blood Labs: lectura IA de informes (PDF/foto) -> borrador -> confirmacion.

La IA se mockea (api.services.blood_lab_parser._call_model).
"""
import json

import pytest

from .conftest import login
from ..models import BloodLabExam, User
from ..services import blood_lab_parser as bp

PDF = b"%PDF-1.4\n%fake report\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch, tmp_path):
    from .. import storage as st
    from ..routes import blood_lab_routes as r
    monkeypatch.setattr(r, "check_rate_limit_redis", lambda *a, **k: (True, 1))
    monkeypatch.setattr(st, "storage", st.LocalStorage(tmp_path))   # no ensuciar data/


@pytest.fixture
def headers(client, db, athlete_user):
    athlete_user.plan_nivel = "elite"
    athlete_user.sexo = "m"
    db.commit()
    return {"Authorization": f"Bearer {login(client, 'athlete@test.com', 'AthlPass123')}"}


def _mock(monkeypatch, payload):
    calls = []

    def fake(media_type, data, prompt):
        calls.append((media_type, len(data)))
        return payload if isinstance(payload, str) else "Aqui va:\n" + json.dumps(payload)

    monkeypatch.setattr(bp, "_call_model", fake)
    return calls


def _parse(client, headers, data=PDF, name="x.pdf", ctype="application/pdf"):
    return client.post("/api/labs/parse", headers=headers, files={"file": (name, data, ctype)})


# Informe A: laboratorio en espanol, unidades del catalogo + nombres alternativos
REPORT_A = {
    "exam_date": "2026-10-20", "lab_name": "Lab Central",
    "results": [
        {"key": "hb", "name_original": "Hemoglobina", "value": 15.2, "unit": "g/dL"},
        {"key": None, "name_original": "FERRITINA", "value": "48,5", "unit": "ng/mL"},
        {"key": "vitamin_d", "name_original": "25-OH Vitamina D", "value": 31, "unit": "ng/mL"},
        {"key": None, "name_original": "Leucocitos", "value": 6.1, "unit": "mil/mm3"},
    ],
}
# Informe B: formato SI / otro idioma, requiere conversion de unidades
REPORT_B = {
    "exam_date": "2026-09-02", "lab_name": None,
    "results": [
        {"key": None, "name_original": "HGB", "value": 152, "unit": "g/L"},
        {"key": "glucose", "name_original": "Glicose", "value": 5.0, "unit": "mmol/L"},
        {"key": "vitamin_d", "name_original": "Vitamin D", "value": 75, "unit": "nmol/L"},
        {"key": "cholesterol", "name_original": "Colesterol total", "value": 5.2, "unit": "mmol/L"},
        {"key": "hba1c", "name_original": "HbA1c", "value": 36, "unit": "mmol/mol"},
        {"key": "creatinine", "name_original": "Creatinina", "value": 88, "unit": "µmol/L"},
        {"key": "ferritin", "name_original": "Ferritina", "value": 90, "unit": "furlongs"},
    ],
}


def _by_key(draft):
    return {m["key"]: m for m in draft["markers"]}


def test_parse_informe_formato_a(client, headers, monkeypatch):
    calls = _mock(monkeypatch, REPORT_A)
    r = _parse(client, headers)
    assert r.status_code == 200
    d = r.json()
    assert d["exam_date"] == "2026-10-20" and d["lab_name"] == "Lab Central"
    m = _by_key(d)
    assert set(m) == {"hb", "ferritin", "vitamin_d"}      # leucocitos no esta en el catalogo
    assert m["hb"]["value"] == 15.2 and m["hb"]["unit"] == "g/dL"
    assert m["ferritin"]["value"] == 48.5                  # alias FERRITINA + coma decimal
    assert d["ignored"] == 1
    assert calls == [("application/pdf", len(PDF))]
    assert d["file_token"].endswith(".pdf")


def test_parse_informe_formato_b_convierte_unidades(client, headers, monkeypatch):
    _mock(monkeypatch, REPORT_B)
    d = _parse(client, headers, PNG, "foto.png", "image/png").json()
    m = _by_key(d)
    assert m["hb"]["value"] == pytest.approx(15.2)         # HGB (alias) g/L -> g/dL
    assert m["hb"]["converted"] is True
    assert m["glucose"]["value"] == pytest.approx(90.1, abs=0.1)
    assert m["vitamin_d"]["value"] == pytest.approx(30.0, abs=0.1)
    assert m["cholesterol"]["value"] == pytest.approx(201.1, abs=0.2)
    assert m["hba1c"]["value"] == pytest.approx(5.4, abs=0.05)
    assert m["creatinine"]["value"] == pytest.approx(0.995, abs=0.01)
    # unidad desconocida: valor intacto y marcado para revision
    assert m["ferritin"]["value"] == 90 and m["ferritin"]["unit_doubtful"] is True
    assert all(x["unit"] == bp.convert_value(x["key"], 1, None)[1] for x in d["markers"])
    assert d["exam_date"] == "2026-09-02" and d["file_token"].endswith(".png")


def test_borrador_no_persiste_hasta_confirmar(client, db, headers, monkeypatch):
    _mock(monkeypatch, REPORT_A)
    d = _parse(client, headers).json()
    db.expire_all()
    assert db.query(BloodLabExam).count() == 0
    # confirmar con el POST /exams existente
    r = client.post("/api/labs/exams", headers=headers, json={
        "date_iso": d["exam_date"], "lab_name": d["lab_name"],
        "values": {m["key"]: m["value"] for m in d["markers"]},
        "source_file_token": d["file_token"],
    })
    assert r.status_code == 200
    db.expire_all()
    assert db.query(BloodLabExam).count() == 1
    exam_id = r.json()["exam_id"]
    f = client.get(f"/api/labs/exams/{exam_id}/file", headers=headers)
    assert f.status_code == 200 and f.content == PDF
    # borrar el examen borra el archivo
    assert client.delete(f"/api/labs/exams/{exam_id}", headers=headers).status_code == 200
    assert client.get(f"/api/labs/exams/{exam_id}/file", headers=headers).status_code == 404


def test_token_ajeno_no_se_asocia(client, db, headers, monkeypatch):
    """Un usuario no puede parsear/adjuntar a nombre de otro: el area pendiente es por usuario."""
    from ..storage import storage
    other = f"blood_lab_pending/otro-usuario/{'a' * 32}.pdf"
    storage.save(other, PDF)
    r = client.post("/api/labs/exams", headers=headers, json={
        "date_iso": "2026-10-01", "values": {"hb": 15.0},
        "source_file_token": "a" * 32 + ".pdf",
    })
    assert r.status_code == 200
    assert client.get(f"/api/labs/exams/{r.json()['exam_id']}/file", headers=headers).status_code == 404
    assert storage.exists(other)          # el archivo del otro usuario no se tocó
    storage.delete(other)
    r = client.post("/api/labs/exams", headers=headers, json={
        "date_iso": "2026-10-01", "values": {"hb": 15.0},
        "source_file_token": "../../etc/passwd",
    })
    assert r.status_code == 200           # token invalido se ignora, el examen se guarda igual


def test_parse_requiere_auth_y_plan(client, db, athlete_user, monkeypatch):
    _mock(monkeypatch, REPORT_A)
    assert _parse(client, {}).status_code == 401
    athlete_user.plan_nivel = "basic"
    db.commit()
    h = {"Authorization": f"Bearer {login(client, 'athlete@test.com', 'AthlPass123')}"}
    assert _parse(client, h).status_code == 403


def test_parse_ia_no_disponible(client, db, headers, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = _parse(client, headers)
    assert r.status_code == 503
    assert db.query(BloodLabExam).count() == 0


def test_parse_respuesta_ia_ilegible(client, headers, monkeypatch):
    _mock(monkeypatch, "no puedo leer esto")
    assert _parse(client, headers).status_code == 503


def test_parse_archivo_invalido(client, headers, monkeypatch):
    _mock(monkeypatch, REPORT_A)
    assert _parse(client, headers, b"MZ\x90 not a report", "x.exe", "application/pdf").status_code == 400


def test_fecha_futura_o_basura_se_descarta(client, headers, monkeypatch):
    _mock(monkeypatch, {"exam_date": "2999-01-01", "results": [
        {"key": "hb", "value": "abc", "unit": "g/dL"},
        {"key": "hb", "value": 14.0, "unit": "g/dL"},
        {"key": "hb", "value": 99, "unit": "g/dL"},          # duplicado: se queda el primero valido
        {"key": "nope", "name_original": "Lo que sea", "value": 1, "unit": "x"},
    ]})
    d = _parse(client, headers).json()
    assert d["exam_date"] is None
    assert [m["value"] for m in d["markers"]] == [14.0]
