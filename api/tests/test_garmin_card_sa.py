"""S-A: una sola tarjeta Garmin en Conexiones; la via legacy solo para admin."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = (ROOT / "athlete_profile.html").read_text(encoding="utf-8")
APP = (ROOT / "athlete-app.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")


def test_formulario_legacy_solo_en_template_admin():
    ini = WEB.index('<template id="garmin-admin-legacy-tpl">')
    fin = WEB.index("</template>", ini)
    # RETIRO-1: el formulario y el boton de conexion por credenciales ya no existen
    for ident in ("g-email", "g-pass", "garmin-form", "btn-garmin-con"):
        assert f'id="{ident}"' not in WEB, ident
    assert ini < WEB.index('id="btn-garmin-admin-dis"') < fin
    assert "garminIsAdmin()" in WEB.split("function renderGarminCard(")[1][:600]


def test_una_sola_tarjeta_sin_oficial_en_el_nombre():
    assert 'id="garmin-off"' not in WEB
    assert "Garmin (oficial)" not in WEB and "Garmin (oficial)" not in APP
    assert "Garmin Connect</span" not in WEB.split("TAB: CONEXIONES")[1][:800]
    assert "_garminOfficialRow" not in APP


def test_sin_conexion_ofrece_flujo_oficial():
    assert 'onclick="garminOfficialConnect()"' in WEB
    assert "garminOfficialConnect()" in APP.split("function _garminRow(")[1][:3500]
    assert "showGarminForm()" not in WEB.split('<template id="garmin-admin-legacy-tpl">')[0]


def test_i18n_claves_nuevas_en_tres_idiomas():
    for k in ("garmin_switch", "garmin_admin_title", "garmin_admin_connect", "garmin_admin_disconnect"):
        assert len(re.findall(rf"\b{k}:", I18N)) == 3, k
    assert "(official)" not in I18N.split("garmin_off_btn:")[1][:60]


def test_sw_build_321():
    sw = (ROOT / "sw.js").read_text(encoding="utf-8")
    m = re.search(r"BUILD_VERSION = '(\d+)'", sw)
    assert m and int(m.group(1)) >= 321
