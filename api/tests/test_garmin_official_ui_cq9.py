"""CQ9: cableado estatico de la conexion oficial Garmin en perfil web y app."""
import re
from pathlib import Path

from api.tests.text_match import squash

ROOT = Path(__file__).resolve().parents[2]
WEB = (ROOT / "athlete_profile.html").read_text(encoding="utf-8")
APP = (ROOT / "athlete-app.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")
KEYS = ["name", "desc", "on", "off", "soon", "btn", "dis", "err", "dis_ok", "dis_err"]


def test_web_usa_endpoints_oficiales():
    s = squash(WEB)
    assert squash("API + '/integrations/garmin/status'") in s
    assert squash("API + '/integrations/garmin/connect'") in s
    assert squash("API + '/integrations/garmin/disconnect'") in s
    tail = s.split(squash("function garminOfficialDisconnect()"))[1][:200]
    assert 'method:"POST"' in tail


def test_app_usa_endpoints_oficiales():
    s = squash(APP)
    assert squash("apiFetch('/integrations/garmin/status')") in s
    assert squash("API + '/integrations/garmin/connect'") in s
    assert squash("'/integrations/garmin/disconnect', { method: 'POST' }") in s


def test_via_no_oficial_intacta():
    for src in (WEB, APP):
        assert "/athlete/garmin/sync-status" in src
    assert "garminSync()" in WEB and "saveGarminCreds()" in WEB
    assert "refreshGarminSync()" in APP


def test_i18n_tres_idiomas():
    for k in KEYS:
        assert len(re.findall(rf"\bgarmin_off_{k}:", I18N)) == 3, k


def test_503_se_evalua_antes_que_connected():
    for src in (WEB, APP):
        body = src.split("function garminOfficialState(")[1][:400]
        assert body.index("503") < body.index("connected")


def test_sw_build_incrementado():
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    import re
    m = re.search(r"BUILD_VERSION = '(\d+)'", sw)
    assert m and int(m.group(1)) >= 313
