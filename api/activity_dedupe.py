"""
Deduplicacion de actividades (PILA 374).

La misma sesion real llega por varias vias (empuje oficial de Garmin, intervals.icu,
Strava, importes de archivo) y cada via crea su propia fila en garmin_activities.
Aqui vive TODO lo comun:

  * `find_duplicate_groups` / `find_match`: matcher conservador (ante la duda NO fusiona).
  * `mark_new_activity`: marca al vuelo una fila recien insertada (ingesta futura).
  * `install_read_filter`: filtro central de lectura. Toda consulta ORM sobre
    GarminActivity excluye las filas con `duplicate_of_id` no nulo, asi listados,
    totales y recalculate_training_load no cuentan la sesion dos veces. Quien necesite
    ver TODAS las filas (matcher, script, auditoria) usa
    `.execution_options(include_duplicates=True)`.

NUNCA se borra una fila: marcar es reversible (duplicate_of_id = NULL).

ORIGEN (Paso 0): no existe columna source/provider. El origen solo se deduce del prefijo de
activity_id: "intervals:" , "strava_", "import_", "polar:"/"wahoo:" (provider_sync_service) y
SIN prefijo = Garmin (empuje oficial y sync legacy comparten ids, no son distinguibles).
Es una pista, no una verdad: se usa para exigir que las dos filas vengan de origenes
distintos (una misma via no duplica su propia sesion), nunca como unica evidencia.

HORA DE INICIO: GarminActivity no la persiste. El matcher la usa solo si ambas filas
exponen `start_local` (datetime); hoy no ocurre, asi que las senales activas son
deporte + fecha + duracion + distancia (+ nombre solo para desempatar).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

# ── Umbrales (documentados en reporte-374.md) ───────────────────────────────
DUR_TOL_MIN = 12.0        # tolerancia de duracion: max(12 min, 25 % de la mayor)
DUR_TOL_PCT = 0.25
DIST_TOL_PCT = 0.10       # distancia (si ambas > 0) debe coincidir dentro de 10 %
DIST_STRONG_PCT = 0.03    # distancia casi identica: permite duraciones mas dispares
DUR_LOOSE_MIN = 25.0      # con distancia casi identica: max(25 min, 50 % de la mayor)
DUR_LOOSE_PCT = 0.50
START_TOL_MIN = 30.0      # solo si ambas filas tienen hora de inicio

_KNOWN_PREFIXES = ("intervals:", "strava_", "import_", "polar:", "wahoo:")


def origin_of(activity_id: str | None) -> str:
    a = (activity_id or "").lower()
    for p in _KNOWN_PREFIXES:
        if a.startswith(p):
            return p.rstrip(":_")
    return "garmin"


def _family(sport: str | None) -> str | None:
    s = (sport or "").strip().lower()
    return s or None


def _name_tokens(name: str | None) -> set[str]:
    t = unicodedata.normalize("NFKD", (name or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z0-9]{3,}", t)}


def _name_sim(a, b) -> float:
    ta, tb = _name_tokens(getattr(a, "name", None)), _name_tokens(getattr(b, "name", None))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _rel(a: float, b: float) -> float:
    return abs(a - b) / max(a, b)


def pair_score(a, b) -> float | None:
    """None = NO son la misma sesion; si lo son, puntaje de cercania (menor = mejor)."""
    if a.user_id != b.user_id or not a.date_iso or a.date_iso != b.date_iso:
        return None
    fa, fb = _family(a.sport), _family(b.sport)
    if fa is None or fa != fb:
        return None
    if origin_of(a.activity_id) == origin_of(b.activity_id):
        return None  # una misma via no duplica su propia sesion
    da, db_ = float(a.dur_min or 0), float(b.dur_min or 0)
    if da <= 0 or db_ <= 0:
        return None  # sin duracion no hay con que distinguir: ante la duda, no fusionar
    sa, sb = getattr(a, "start_local", None), getattr(b, "start_local", None)
    if isinstance(sa, datetime) and isinstance(sb, datetime) \
            and abs((sa - sb).total_seconds()) / 60 > START_TOL_MIN:
        return None
    big = max(da, db_)
    ddur = abs(da - db_)
    dist_a, dist_b = float(a.dist_km or 0), float(b.dist_km or 0)
    both_dist = dist_a > 0 and dist_b > 0
    ddist = _rel(dist_a, dist_b) if both_dist else 0.0
    dur_ok = ddur <= max(DUR_TOL_MIN, DUR_TOL_PCT * big)
    if both_dist:
        strong = ddist <= DIST_STRONG_PCT and ddur <= max(DUR_LOOSE_MIN, DUR_LOOSE_PCT * big)
        if not ((ddist <= DIST_TOL_PCT and dur_ok) or strong):
            return None
    elif not dur_ok:
        return None
    return ddur / big + ddist + (1.0 - _name_sim(a, b)) * 0.05


def find_match(candidate, others) -> object | None:
    """Mejor fila de `others` que sea la misma sesion que `candidate`, o None."""
    best, best_s = None, None
    for o in others:
        if o is candidate or o.id == candidate.id:
            continue
        s = pair_score(candidate, o)
        if s is not None and (best_s is None or s < best_s):
            best, best_s = o, s
    return best


def completeness(a) -> tuple:
    """Mayor = fila mas completa: campos con dato, luego duracion registrada, luego id estable."""
    fields = ("name", "dur_min", "dist_km", "avg_hr", "avg_power", "pace_str", "swim_pace",
              "calories", "elev_m", "aerobic_te", "anaerobic_te", "te_label", "photo_path",
              "strava_photos_json", "swolf", "avg_cadence_spm", "pool_length_m")
    filled = sum(1 for f in fields if getattr(a, f, None) not in (None, "", 0, 0.0))
    if (a.tss or 0) > 0:
        filled += 1
    return (filled, float(a.dur_min or 0), a.id or "")


def _group_day(rows: list) -> list[list]:
    """Agrupa filas de UN usuario/fecha. Cada grupo: a lo sumo una fila por origen."""
    parent = {r.id: r.id for r in rows}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    # Emparejamiento codicioso 1:1 por mejor puntaje (no encadena sesiones distintas).
    pairs = []
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            s = pair_score(a, b)
            if s is not None:
                pairs.append((s, a, b))
    pairs.sort(key=lambda t: (t[0], t[1].id, t[2].id))
    members: dict[str, dict[str, object]] = {r.id: {origin_of(r.activity_id): r} for r in rows}
    for _, a, b in pairs:
        ra, rb = find(a.id), find(b.id)
        if ra == rb:
            continue
        oa, ob = members[ra], members[rb]
        if set(oa) & set(ob):
            continue  # el grupo ya tiene una fila de ese origen: seria otra sesion
        # Todos los miembros de ambos grupos deben ser compatibles entre si.
        if any(pair_score(x, y) is None for x in oa.values() for y in ob.values()):
            continue
        parent[rb] = ra
        oa.update(ob)
        members.pop(rb)
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(find(r.id), []).append(r)
    return [g for g in groups.values() if len(g) > 1]


def find_duplicate_groups(db: Session, user_id: str | None = None) -> list[dict]:
    """Grupos de filas que son la misma sesion (incluye filas ya marcadas, para idempotencia).
    -> [{user_id, date_iso, canonical, duplicates:[...]}]"""
    from .models import GarminActivity
    q = db.query(GarminActivity).execution_options(include_duplicates=True)
    if user_id:
        q = q.filter(GarminActivity.user_id == user_id)
    by_day: dict[tuple, list] = {}
    for r in q.all():
        if r.date_iso:
            by_day.setdefault((r.user_id, r.date_iso), []).append(r)
    out = []
    for (uid, day), rows in sorted(by_day.items()):
        if len(rows) < 2:
            continue
        for g in _group_day(rows):
            canon = max(g, key=completeness)
            out.append({"user_id": uid, "date_iso": day, "canonical": canon,
                        "duplicates": [r for r in g if r is not canon]})
    return out


def reason_for(canon, dup) -> str:
    return (f"misma sesion: {origin_of(dup.activity_id)} {dup.dur_min}min "
            f"~ {origin_of(canon.activity_id)} {canon.dur_min}min (dia, deporte, duracion/distancia)")[:200]


def apply_groups(groups: list[dict]) -> int:
    """Marca duplicados (sin commit). Idempotente: solo escribe lo que cambia."""
    n = 0
    for g in groups:
        for d in g["duplicates"]:
            if d.duplicate_of_id != g["canonical"].id:
                d.duplicate_of_id = g["canonical"].id
                d.duplicate_reason = reason_for(g["canonical"], d)
                n += 1
        # La canonica nunca queda marcada como duplicada.
        if g["canonical"].duplicate_of_id is not None:
            g["canonical"].duplicate_of_id = None
            g["canonical"].duplicate_reason = None
            n += 1
    return n


def mark_new_activity(db: Session, row) -> object | None:
    """Ingesta futura: tras insertar/flush `row`, la compara con las filas del mismo
    usuario y dia. Si es la misma sesion, marca la MENOS completa como duplicada de la otra
    (puede ser `row` o la existente). Devuelve la fila marcada o None. Best-effort."""
    from .models import GarminActivity
    try:
        if not row.date_iso or not row.user_id:
            return None
        if row.id is None:
            db.flush()
        others = (db.query(GarminActivity).execution_options(include_duplicates=True)
                  .filter(GarminActivity.user_id == row.user_id,
                          GarminActivity.date_iso == row.date_iso,
                          GarminActivity.id != row.id,
                          GarminActivity.duplicate_of_id.is_(None)).all())
        other = find_match(row, others)
        if other is None:
            return None
        canon, dup = (row, other) if completeness(row) > completeness(other) else (other, row)
        dup.duplicate_of_id = canon.id
        dup.duplicate_reason = reason_for(canon, dup)
        # Si la marcada era canonica de otras, se reapuntan.
        for x in (db.query(GarminActivity).execution_options(include_duplicates=True)
                  .filter(GarminActivity.duplicate_of_id == dup.id).all()):
            x.duplicate_of_id = canon.id
        return dup
    except Exception:  # nunca romper un sync por la deduplicacion
        return None


# ── Filtro central de lectura ───────────────────────────────────────────────

def install_read_filter() -> None:
    from .models import GarminActivity

    @event.listens_for(Session, "do_orm_execute")
    def _hide_duplicates(state):
        if not state.is_select or state.execution_options.get("include_duplicates"):
            return
        state.statement = state.statement.options(with_loader_criteria(
            GarminActivity, GarminActivity.duplicate_of_id.is_(None),
            include_aliases=True))
