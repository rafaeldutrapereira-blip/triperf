"""
BUILD 405 SIMULACION-MARCAS: servidor HTTP local (solo stdlib) que responde como
las APIs de Wahoo Cloud y Polar AccessLink para validar, sin cuenta ni dispositivo,
el lado de LabX (OAuth, sync, normalizacion, guardado).

Honestidad del mock:
  - Los DATOS de actividad salen VERBATIM de api/tests/fixtures/{wahoo,polar}/ (ejemplos
    oficiales de cada doc). El mock no inventa campos ni valores de actividad.
  - Lo unico "inventado" es el sobre de OAuth (tokens falsos `mock-*`), que no es dato
    del vendor: solo permite ejercitar el intercambio de code y el 401 con token malo.
  - Errores honestos: 401 con token malo/ausente, 404 con id inexistente o ruta desconocida.
  - GPX de Polar: 404 por defecto (no hay fixture oficial). Si un test pasa `polar_gpx`,
    se sirve ese XML SINTETICO solo para verificar el cableado del parser; no es dato Polar.

Uso: srv = MockVendorServer(); srv.start(); srv.env() -> dict de env para wahoo.py/polar.py.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

FIXTURES = Path(__file__).parent / "fixtures"
WAHOO_FIXTURE = json.loads((FIXTURES / "wahoo" / "doc_sample_get_workout.json").read_text(encoding="utf-8"))
POLAR_FIXTURE = json.loads((FIXTURES / "polar" / "doc_sample_exercise.json").read_text(encoding="utf-8"))

WAHOO_CODE = "mock-wahoo-code"
POLAR_CODE = "mock-polar-code"
WAHOO_ACCESS = "mock-wahoo-access-token"
WAHOO_REFRESH = "mock-wahoo-refresh-token"
POLAR_ACCESS = "mock-polar-access-token"


class _Handler(BaseHTTPRequestHandler):
    server_version = "LabXMockVendors/405"

    def log_message(self, fmt, *args):  # silencio: el registro va en self.server.requests
        pass

    # -- utilidades ---------------------------------------------------------
    def _send(self, status: int, body=None, ctype="application/json", headers=None):
        raw = b"" if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode("utf-8"))
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def _bearer_ok(self, expected: str) -> bool:
        return self.headers.get("Authorization", "") == f"Bearer {expected}"

    def _log(self, parsed):
        self.server.requests.append({"method": self.command, "path": parsed.path})

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    # -- GET ----------------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        self._log(u)
        p = u.path

        # Polar: pantalla de autorizacion -> redirige con code falso (no hay UI real)
        if p == "/oauth2/authorization":
            back = q.get("redirect_uri")
            if not back:
                return self._send(400, {"error": "invalid_request"})
            sep = "&" if "?" in back else "?"
            return self._send(302, None, headers={"Location": f"{back}{sep}{urlencode({'code': POLAR_CODE, 'state': q.get('state', '')})}"})
        # Wahoo: idem
        if p == "/oauth/authorize":
            back = q.get("redirect_uri")
            if not back:
                return self._send(400, {"error": "invalid_request"})
            sep = "&" if "?" in back else "?"
            return self._send(302, None, headers={"Location": f"{back}{sep}{urlencode({'code': WAHOO_CODE, 'state': q.get('state', '')})}"})

        # Wahoo Cloud API
        if p.startswith("/v1/workouts"):
            if not self._bearer_ok(WAHOO_ACCESS):
                return self._send(401, {"error": "invalid_token"})
            if p == "/v1/workouts":
                page = int(q.get("page", 1))
                return self._send(200, {"workouts": [WAHOO_FIXTURE] if page == 1 else []})
            wid = p.rsplit("/", 1)[1]
            if wid == str(WAHOO_FIXTURE["id"]):
                return self._send(200, WAHOO_FIXTURE)
            return self._send(404, {"error": "not_found"})

        # Polar AccessLink
        if p.startswith("/v3/exercises"):
            if not self._bearer_ok(POLAR_ACCESS):
                return self._send(401, {"error": "invalid_token"})
            if p == "/v3/exercises":
                return self._send(200, {"exercises": [POLAR_FIXTURE]})
            parts = p.split("/")  # ['', 'v3', 'exercises', id, (gpx)]
            if len(parts) >= 4 and parts[3] == POLAR_FIXTURE["id"]:
                if len(parts) == 4:
                    return self._send(200, POLAR_FIXTURE)
                if len(parts) == 5 and parts[4] == "gpx" and self.server.polar_gpx:
                    return self._send(200, self.server.polar_gpx.encode("utf-8"), ctype="application/gpx+xml")
            return self._send(404, {"error": "not_found"})

        return self._send(404, {"error": "not_found"})

    # -- POST ---------------------------------------------------------------
    def do_POST(self):
        u = urlparse(self.path)
        self._log(u)
        p = u.path
        q = {k: v[0] for k, v in parse_qs(u.query).items()}

        if p == "/oauth/token":  # Wahoo: parametros en query (como wahoo.py)
            gt = q.get("grant_type")
            if gt == "authorization_code" and q.get("code") == WAHOO_CODE:
                return self._send(200, {"access_token": WAHOO_ACCESS, "token_type": "bearer",
                                        "expires_in": 7200, "refresh_token": WAHOO_REFRESH})
            if gt == "refresh_token" and q.get("refresh_token") == WAHOO_REFRESH:
                return self._send(200, {"access_token": WAHOO_ACCESS, "token_type": "bearer",
                                        "expires_in": 7200, "refresh_token": WAHOO_REFRESH})
            return self._send(401, {"error": "invalid_grant"})

        if p == "/v2/oauth2/token":  # Polar: form + Basic auth
            form = {k: v[0] for k, v in parse_qs(self._body().decode("utf-8")).items()}
            if not self.headers.get("Authorization", "").startswith("Basic "):
                return self._send(401, {"error": "invalid_client"})
            if form.get("grant_type") == "authorization_code" and form.get("code") == POLAR_CODE:
                return self._send(200, {"access_token": POLAR_ACCESS, "token_type": "bearer",
                                        "expires_in": 31535999, "x_user_id": 1})
            return self._send(400, {"error": "invalid_grant"})

        if p == "/v3/users":  # registro de usuario Polar (member-id)
            if not self._bearer_ok(POLAR_ACCESS):
                return self._send(401, {"error": "invalid_token"})
            try:
                body = json.loads(self._body() or b"{}")
            except ValueError:
                return self._send(400, {"error": "invalid_json"})
            if not body.get("member-id"):
                return self._send(400, {"error": "member-id requerido"})
            n = self.server.polar_registered = getattr(self.server, "polar_registered", 0) + 1
            return self._send(409 if n > 1 else 200, {"member-id": body["member-id"]})

        return self._send(404, {"error": "not_found"})


class MockVendorServer:
    def __init__(self, polar_gpx: str | None = None):
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._httpd.requests = []
        self._httpd.polar_gpx = polar_gpx
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}"

    @property
    def requests(self) -> list[dict]:
        return self._httpd.requests

    def env(self) -> dict[str, str]:
        b = self.base_url
        return {
            "WAHOO_API_BASE_URL": f"{b}/v1", "WAHOO_TOKEN_URL": f"{b}/oauth/token",
            "POLAR_API_BASE_URL": f"{b}/v3", "POLAR_TOKEN_URL": f"{b}/v2/oauth2/token",
            "POLAR_AUTH_URL": f"{b}/oauth2/authorization",
        }

    def start(self) -> "MockVendorServer":
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=5)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
