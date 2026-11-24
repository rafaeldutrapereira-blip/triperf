"""La raiz estatica no debe exponer .env, .git, data/, bases de datos ni codigo."""
import pytest

BLOCKED = ["/.env", "/%2eenv", "/.git/config", "/data/x", "/data/labx.db", "/x.db",
           "/x.sqlite3", "/x.sqlite-wal", "/api/coach_main.py", "/requirements-api.txt",
           "/vendor/../.env"]
PUBLIC = ["/sw.js", "/public_activity.html", "/dashboard.html", "/nav.js"]


@pytest.mark.parametrize("path", BLOCKED)
def test_blocked(client, path):
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", PUBLIC)
def test_public(client, path):
    assert client.get(path).status_code == 200
