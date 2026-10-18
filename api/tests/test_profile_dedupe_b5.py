"""
B5 — Dedupe de perfil.

- "Mi Perfil" sale de Comunidad: la foto y la privacidad de actividades se
  mueven a Perfil (athlete_profile.html), con los mismos endpoints.
- Records: NO se decidió aún cuál es la fuente única (ver plan, sección 1.1).
  Este test no fija esa decisión.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMMUNITY = (ROOT / "community.html").read_text(encoding="utf-8")
PROFILE = (ROOT / "athlete_profile.html").read_text(encoding="utf-8")
I18N = (ROOT / "i18n.js").read_text(encoding="utf-8")


def test_comunidad_ya_no_tiene_tab_mi_perfil():
    assert "cmw_tab_profile" not in COMMUNITY
    assert "id=\"tab-profile\"" not in COMMUNITY
    assert "loadMyProfile" not in COMMUNITY
    assert "uploadMyAvatar" not in COMMUNITY
    assert "switchTab('profile'" not in COMMUNITY


def test_comunidad_boton_ver_mi_perfil_lleva_a_perfil():
    assert "location.href='athlete_profile.html'" in COMMUNITY


def test_perfil_tiene_foto_y_privacidad():
    for marker in ("pf-avatar-img", "uploadAvatarPerfil(this)", "deleteAvatarPerfil()",
                   "priv-details", "savePrivacyPrefs()", "loadPrivacyPrefs()"):
        assert marker in PROFILE, marker


def test_perfil_usa_los_endpoints_existentes():
    assert "/athlete/profile/avatar" in PROFILE
    assert "/athlete/community-privacy" in PROFILE


def test_endpoints_de_backend_existen():
    athlete = (ROOT / "api" / "routes" / "athlete_routes.py").read_text(encoding="utf-8")
    assert '@router.post("/profile/avatar")' in athlete
    assert '@router.delete("/profile/avatar")' in athlete
    assert "community-privacy" in athlete


def test_claves_nuevas_en_tres_idiomas():
    keys = ["prof_card_avatar", "prof_btn_avatar_change", "prof_btn_avatar_remove",
            "prof_toast_avatar_ok", "prof_toast_avatar_removed", "prof_toast_avatar_err"]
    for k in keys:
        n = len(re.findall(r"^\s*" + k + r":", I18N, re.M))
        assert n == 3, f"{k}: {n}"
