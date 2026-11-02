"""W1: training_detail.html solo muestra cifras reales (sin NP/FTP/velocidad/lugar inventados)."""
import re
from pathlib import Path

from .text_match import squash

SRC = (Path(__file__).resolve().parents[2] / "training_detail.html").read_text(
    encoding="utf-8"
)
S = squash(SRC)


def test_no_np_from_avg_power_factor():
    assert not re.search(r"avg_power\s*\*\s*1\.07", SRC)
    assert "1.07" not in re.sub(r"opacity[^;\n]*", "", SRC) or "avg_power*1.07" not in S


def test_no_default_ftp_240():
    assert "ATHLETE.ftp||240" not in S
    assert not re.search(r"FTP\s*=\s*[^;]*\|\|\s*\d", SRC)
    assert "FTP=+ATHLETE.ftp>0?+ATHLETE.ftp:null" in S


def test_if_and_tss_require_real_ftp():
    assert "ifv=np&&FTP?" in S
    assert "(np&&FTP?" in S


def test_no_speed_from_power():
    assert "avg_power/8" not in S


def test_no_hardcoded_places():
    for place in ("Santiago, Chile", "Las Condes", "Colina, Chile"):
        assert place not in SRC


def test_placeholders_when_no_real_data():
    assert "val:np||'???'".replace("'", '"') in S
    assert "val:spd||'???'".replace("'", '"') in S
