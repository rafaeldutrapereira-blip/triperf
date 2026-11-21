"""
BUILD 405 SIMULACION-MARCAS: corredor automatico de punta a punta (un solo comando):

    python -m api.tests.mock_vendors_runner            (desde la raiz del repo)

Pasos, sin intervencion manual:
  (a) levanta el mock de vendors en localhost (puerto libre);
  (b) crea una BD SQLite TEMPORAL (nunca la de produccion ni la del repo) + usuario atleta;
  (c) por cada marca recorre el camino real: pantalla de autorizacion del mock -> code ->
      `wearable_oauth_routes._exchange` (get_provider-equivalente + authenticate) ->
      `provider_oauth.save_connection` -> `provider_sync_service.sync_provider_user`
      (get_provider + list_activities + get_activity_detail + upsert): el MISMO punto de
      entrada que usa `POST /integrations/<marca>/sync`;
  (d) lee garmin_activities y verifica campos normalizados (+ GPX de Polar);
  (e) apaga el mock, borra la BD temporal y escribe el reporte (JSON + Markdown).

Salida: exit code 0 si todo cuadra; reporte en labx-overnight/sprint-simulacion-marcas/.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

POLAR_SYNTH_GPX = (  # SINTETICO: solo valida el cableado del parser GPX, no es dato Polar
    '<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
    '<trkpt lat="-33.4500" lon="-70.6600"><ele>520</ele></trkpt>'
    '<trkpt lat="-33.4510" lon="-70.6610"><ele>521</ele></trkpt>'
    "</trkseg></trk></gpx>"
)


@contextmanager
def _patched_env(values: dict):
    old = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _check(results: list, name: str, cond: bool, detail=None):
    results.append({"check": name, "ok": bool(cond), "detail": detail})


async def _brand_flow(provider: str, srv, SessionLocal, user_id: str, tracks_dir: Path, results: list) -> dict:
    import httpx

    from api import provider_oauth as po
    from api.models import GarminActivity
    from api.provider_sync_service import sync_provider_user
    from api.routes.wearable_oauth_routes import _exchange

    out: dict = {"provider": provider}
    # (c1) pantalla de autorizacion del mock -> code (sin seguir el redirect: lo leemos)
    auth_path = "/oauth2/authorization" if provider == "polar" else "/oauth/authorize"
    async with httpx.AsyncClient(follow_redirects=False, timeout=10) as http:
        r = await http.get(srv.base_url + auth_path,
                           params={"response_type": "code", "client_id": "cid", "redirect_uri": "http://localhost/cb", "state": "s"})
    _check(results, f"{provider}: authorize redirige con code", r.status_code == 302 and "code=" in r.headers.get("location", ""),
           r.headers.get("location"))
    code = r.headers["location"].split("code=")[1].split("&")[0]

    # (c2) intercambio de code (authenticate) + guardado de la conexion
    with SessionLocal() as db:
        token_response, member_id = await _exchange(provider, db, user_id, code)
        _check(results, f"{provider}: authenticate devuelve access_token", bool(token_response and token_response.get("access_token")))
        po.save_connection(db, user_id, provider, token_response, member_id=member_id)
        _check(results, f"{provider}: conexion guardada", po.get_connection(db, user_id, provider) is not None)

    # (c3) sync generico real (ventana enorme: los fixtures oficiales son de 2008/2015)
    with SessionLocal() as db:
        res = await sync_provider_user(db, user_id, provider, days=40000)
    out["sync_result"] = res
    _check(results, f"{provider}: sync ok con 1 actividad guardada", res.get("ok") and res.get("saved") == 1 and res.get("errors") == 0, res)

    # (d) filas normalizadas
    with SessionLocal() as db:
        rows = db.query(GarminActivity).filter(GarminActivity.user_id == user_id,
                                               GarminActivity.activity_id.like(f"{provider}_%")).all()
        out["rows"] = [{c: getattr(a, c) for c in ("activity_id", "sport", "name", "date_iso", "dur_min", "dist_km",
                                                    "avg_hr", "avg_power", "calories", "elev_m", "tss")} for a in rows]
    _check(results, f"{provider}: 1 fila en garmin_activities", len(rows) == 1, len(rows))
    row = out["rows"][0] if out["rows"] else {}

    # (c4) idempotencia: segundo sync no duplica
    with SessionLocal() as db:
        res2 = await sync_provider_user(db, user_id, provider, days=40000)
        n = db.query(GarminActivity).filter(GarminActivity.user_id == user_id,
                                            GarminActivity.activity_id.like(f"{provider}_%")).count()
    _check(results, f"{provider}: segundo sync idempotente", res2.get("ok") and res2.get("saved") == 0 and n == 1, res2)
    out["rows_after_second_sync"] = n
    return {"out": out, "row": row}


def run_end_to_end(work_dir: str | Path | None = None, gpx: bool = True) -> dict:
    """Ejecuta todo el flujo. Debe llamarse con DATABASE_URL ya fuera de produccion
    (el CLI lo garantiza; pytest usa la de conftest). Usa su PROPIA BD en work_dir."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from api.auth import hash_password
    from api.database import Base
    from api.models import User
    from api.tests.mock_vendors import POLAR_FIXTURE, WAHOO_FIXTURE, MockVendorServer
    import garmin_connector

    results: list = []
    own_tmp = work_dir is None
    tmp = tempfile.TemporaryDirectory(prefix="labx_mock405_") if own_tmp else None
    work = Path(tmp.name if tmp else work_dir)
    work.mkdir(parents=True, exist_ok=True)
    db_path = work / "mock405_test.db"
    assert db_path.resolve().parent != (REPO / "data").resolve(), "la BD de prueba no puede vivir en data/ del repo"

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    tracks_dir = work / "tracks"
    old_tracks = garmin_connector.TRACKS_DIR
    garmin_connector.TRACKS_DIR = tracks_dir  # polar.download_gps lo importa en cada llamada

    report: dict = {"db": str(db_path), "brands": {}, "checks": results}
    srv = MockVendorServer(polar_gpx=POLAR_SYNTH_GPX if gpx else None)
    env = {**srv.env(), "WAHOO_ENABLED": "true", "POLAR_ENABLED": "true",
           "WAHOO_CLIENT_ID": "mock-cid", "WAHOO_CLIENT_SECRET": "mock-secret",
           "POLAR_CLIENT_ID": "mock-cid", "POLAR_CLIENT_SECRET": "mock-secret"}
    try:
        with srv, _patched_env(env):
            with SessionLocal() as db:
                u = User(email="mock405@test.invalid", nombre="Atleta Mock 405",
                         password_hash=hash_password("Mock405Pass!"), rol="athlete",
                         plan_nivel="elite", activo=True, ftp=220, fcmax=182, weight_kg=70.0)
                db.add(u)
                db.commit()
                uid = u.id
            for brand in ("wahoo", "polar"):
                r = asyncio.run(_brand_flow(brand, srv, SessionLocal, uid, tracks_dir, results))
                report["brands"][brand] = r["out"]
                row = r["row"]
                if brand == "wahoo":
                    s = WAHOO_FIXTURE["workout_summary"]
                    _check(results, "wahoo: fecha = starts[:10]", row.get("date_iso") == WAHOO_FIXTURE["starts"][:10], row.get("date_iso"))
                    _check(results, "wahoo: duracion = minutes", row.get("dur_min") == WAHOO_FIXTURE["minutes"], row.get("dur_min"))
                    _check(results, "wahoo: distancia = distance_accum/1000", row.get("dist_km") == round(float(s["distance_accum"]) / 1000, 2), row.get("dist_km"))
                    _check(results, "wahoo: potencia y FC medias", row.get("avg_power") == round(float(s["power_avg"])) and row.get("avg_hr") == round(float(s["heart_rate_avg"])))
                    _check(results, "wahoo: TSS = power_bike_tss_last (nativo)", row.get("tss") == round(float(s["power_bike_tss_last"]), 1), row.get("tss"))
                    # El fixture trae workout_type_id=40 (KITEBOARDING en la doc de Wahoo): no se "corrige".
                    _check(results, "wahoo: deporte segun tabla documentada (id 40 -> other)", row.get("sport") == "other", row.get("sport"))
                else:
                    dist_km = round(POLAR_FIXTURE["distance"] / 1000, 2)
                    hr = POLAR_FIXTURE["heart_rate"]["average"]
                    _check(results, "polar: fecha = start_time[:10]", row.get("date_iso") == POLAR_FIXTURE["start_time"][:10], row.get("date_iso"))
                    _check(results, "polar: duracion PT2H44M = 164 min", row.get("dur_min") == 164, row.get("dur_min"))
                    _check(results, "polar: distancia", row.get("dist_km") == dist_km, row.get("dist_km"))
                    _check(results, "polar: FC media y sin potencia", row.get("avg_hr") == hr and row.get("avg_power") is None)
                    exp_tss = round(((hr / 182) ** 2) * (164 / 60) * 100, 1)
                    _check(results, "polar: TSS por %FCmax (fcmax=182)", row.get("tss") == exp_tss, {"got": row.get("tss"), "esperado": exp_tss})
                    _check(results, "polar: deporte OTHER -> other", row.get("sport") == "other", row.get("sport"))
                    gpx_file = tracks_dir / f"polar_{POLAR_FIXTURE['id']}.json"
                    if gpx:
                        pts = json.loads(gpx_file.read_text()) if gpx_file.exists() else []
                        _check(results, "polar: GPX descargado y parseado (XML sintetico)", len(pts) == 2, len(pts))
                        report["brands"][brand]["gpx_points"] = len(pts)
                    else:
                        _check(results, "polar: sin GPX en el mock -> 404 honesto, sin archivo", not gpx_file.exists())
            # errores honestos del mock
            import httpx
            b = srv.base_url
            _check(results, "mock: 401 con token malo (Wahoo)", httpx.get(f"{b}/v1/workouts", headers={"Authorization": "Bearer mal"}).status_code == 401)
            _check(results, "mock: 401 con token malo (Polar)", httpx.get(f"{b}/v3/exercises", headers={"Authorization": "Bearer mal"}).status_code == 401)
            _check(results, "mock: 404 con id inexistente (Wahoo)", httpx.get(f"{b}/v1/workouts/1", headers={"Authorization": "Bearer mock-wahoo-access-token"}).status_code == 404)
            _check(results, "mock: 404 con id inexistente (Polar)", httpx.get(f"{b}/v3/exercises/ZZZ", headers={"Authorization": "Bearer mock-polar-access-token"}).status_code == 404)
            report["mock_requests"] = list(srv.requests)
    finally:
        garmin_connector.TRACKS_DIR = old_tracks
        engine.dispose()
        if tmp:
            tmp.cleanup()
    report["mock_stopped"] = True
    report["all_ok"] = all(c["ok"] for c in results)
    return report


def _to_markdown(rep: dict) -> str:
    lines = ["# Corrida automatica SIMULACION-MARCAS (BUILD 405)", "",
             f"Resultado: **{'OK' if rep['all_ok'] else 'FALLO'}** ({sum(c['ok'] for c in rep['checks'])}/{len(rep['checks'])} chequeos). "
             "BD de prueba temporal (eliminada al terminar). Mock apagado.", "", "## Chequeos", ""]
    lines += [f"- {'OK ' if c['ok'] else 'FALLA'} {c['check']}" + ("" if c["ok"] or c["detail"] is None else f" -> {c['detail']}") for c in rep["checks"]]
    for brand, b in rep["brands"].items():
        lines += ["", f"## {brand}: filas guardadas", "", "```json", json.dumps(b["rows"], indent=2, ensure_ascii=False), "```",
                  f"sync: `{json.dumps(b['sync_result'])}`"]
    lines += ["", "## Peticiones recibidas por el mock", ""] + [f"- {r['method']} {r['path']}" for r in rep["mock_requests"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    # Antes de importar api.*: la BD global del proceso NUNCA es la de produccion.
    boot = tempfile.mkdtemp(prefix="labx_mock405_boot_")
    os.environ["DATABASE_URL"] = f"sqlite:///{Path(boot) / 'boot.db'}"
    os.environ["APP_ENV"] = "test"
    os.environ.setdefault("JWT_SECRET", "mock405-secret-key-not-for-prod-0123456789")
    sys.path.insert(0, str(REPO))
    rep = run_end_to_end()
    out_dir = Path(os.environ.get("MOCK405_REPORT_DIR", REPO.parents[1] / "labx-overnight" / "sprint-simulacion-marcas"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "corrida-mock-405.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    md = _to_markdown(rep)
    (out_dir / "corrida-mock-405.md").write_text(md, encoding="utf-8")
    print(md)
    return 0 if rep["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
