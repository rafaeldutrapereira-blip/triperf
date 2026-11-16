"""
EXPORT-FIT (BUILD 387) -- encoder FIT minimo de un workout Indoor.

Solo stdlib (`struct`): escribe los mensajes `file_id`, `workout` y
`workout_step`. Lee los bloques con el mismo criterio que
`intervals_connector.blocks_to_intervals_dsl` (mismos tipos, mismas claves y
mismos valores por defecto), pero los emite como pasos FIT.

Regla de fidelidad (CERO datos inventados):
  * Un objetivo solo se escribe si sale EXACTO de los datos del bloque + el
    perfil del atleta. Si no (rampas, bici sin FTP, FC sin FCmax, valores
    ausentes o invalidos) el paso queda con objetivo ABIERTO y se informa en
    `FitExport.open_steps` con el motivo.
  * Nunca hay FTP ni FCmax por defecto.

Unidades FIT usadas:
  * duracion por tiempo: ms; por distancia: cm.
  * objetivo de potencia (custom_target_value_*): vatios + 1000.
  * objetivo de FC: bpm + 100.
  * objetivo de velocidad: mm/s.
"""
from __future__ import annotations

import logging
import struct
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Constantes del perfil FIT ────────────────────────────────────────────
FIT_EPOCH_OFFSET = 631065600          # 1989-12-31T00:00:00Z en epoch unix
_PROTOCOL_VERSION = 0x20              # 2.0
_PROFILE_VERSION = 2132               # 21.32 (solo informativo en la cabecera)

MESG_FILE_ID = 0
MESG_WORKOUT = 26
MESG_WORKOUT_STEP = 27

# Tipos base
_ENUM, _UINT8, _UINT16, _UINT32, _STRING, _UINT32Z = 0x00, 0x02, 0x84, 0x86, 0x07, 0x8C

# file_id.type
_FILE_TYPE_WORKOUT = 5
_MANUFACTURER_DEVELOPMENT = 255

# sport / sub_sport
_SPORT = {"run": 1, "bike": 2, "swim": 5}
_SUB_SPORT = {"run": 0, "bike": 6, "swim": 17}   # generic / indoor_cycling / lap_swimming

# wkt_step_duration
DUR_TIME, DUR_DISTANCE, DUR_OPEN, DUR_REPEAT_UNTIL_STEPS = 0, 1, 5, 6
# wkt_step_target
TGT_SPEED, TGT_HEART_RATE, TGT_OPEN, TGT_POWER = 0, 1, 2, 4
# intensity
INT_ACTIVE, INT_REST, INT_WARMUP, INT_COOLDOWN, INT_RECOVERY, INT_INTERVAL = 0, 1, 2, 3, 4, 5
# workout_equipment
_EQUIPMENT = {"fins": 1, "paddles": 3, "buoy": 4, "snorkel": 5}

_NAME_BYTES = 32      # tamano fijo del campo de texto (incluye el 0 final)
_UINT32_NONE = 0xFFFFFFFF
_UINT16_NONE = 0xFFFF
_UINT8_NONE = 0xFF


class FitExportError(ValueError):
    """El workout no se puede exportar (p. ej. no tiene pasos validos)."""


@dataclass
class FitStep:
    """Paso FIT en memoria (antes de serializar). `index` = message_index."""
    name: str = ""
    duration_type: int = DUR_OPEN
    duration_value: int = 0
    target_type: int = TGT_OPEN
    target_value: int = 0
    low: Optional[int] = None
    high: Optional[int] = None
    intensity: int = INT_ACTIVE
    equipment: Optional[int] = None
    index: int = 0


@dataclass
class FitExport:
    data: bytes
    steps: list = field(default_factory=list)       # FitStep
    # Pasos que quedaron con objetivo abierto: [{"step": n (1-based, solo
    # pasos reales, sin repeticiones), "name": str, "reason": code}]
    open_steps: list = field(default_factory=list)
    missing_ftp: bool = False
    missing_fcmax: bool = False
    skipped_blocks: int = 0


# ── Bajo nivel ───────────────────────────────────────────────────────────
def fit_crc(data: bytes, crc: int = 0) -> int:
    """CRC-16 del formato FIT (tabla de nibbles del SDK)."""
    table = (0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
             0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400)
    for byte in data:
        tmp = table[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ table[byte & 0xF]
        tmp = table[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ table[(byte >> 4) & 0xF]
    return crc


def _definition(local: int, mesg_num: int, fields: list) -> bytes:
    """Mensaje de definicion (little endian). fields = [(num, size, base_type)]."""
    out = struct.pack("<BBBHB", 0x40 | local, 0, 0, mesg_num, len(fields))
    for num, size, base in fields:
        out += struct.pack("<BBB", num, size, base)
    return out


def _text(value: str, size: int = _NAME_BYTES) -> bytes:
    """Texto UTF-8 de largo fijo, terminado en 0, sin cortar un caracter a la mitad."""
    raw = (value or "").encode("utf-8")[: size - 1]
    while raw:
        try:
            raw.decode("utf-8")
            break
        except UnicodeDecodeError:
            raw = raw[:-1]
    return raw + b"\x00" * (size - len(raw))


def _u32(v: Optional[int]) -> int:
    return _UINT32_NONE if v is None else max(0, min(int(v), 0xFFFFFFFE))


# ── Bloques -> pasos ─────────────────────────────────────────────────────
_STEP_NAME = {"warmup": "Warm up", "cooldown": "Cool down", "steady": "Steady",
              "ramp": "Ramp", "freeride": "Free ride"}
_SWIM_NAME = {"warmup": "Warm up", "main": "Main", "drill": "Technique", "cooldown": "Cool down"}
_SWIM_STROKE = {"drill": "Drill", "kick": "Kick", "pull": "Pull"}


class _Builder:
    def __init__(self, sport: str, ftp: Optional[int], fcmax: Optional[int]):
        self.sport = sport
        self.ftp = int(ftp) if ftp and int(ftp) > 0 else None
        self.fcmax = int(fcmax) if fcmax and int(fcmax) > 0 else None
        self.steps: list[FitStep] = []
        self.open_steps: list[dict] = []
        self.missing_ftp = False
        self.missing_fcmax = False
        self._real = 0   # contador 1-based de pasos reales (para el aviso en UI)

    # -- helpers de objetivo: devuelven (target_type, low, high, razon_si_abierto)
    def _bike_target(self, frac) -> tuple:
        if frac is None or frac <= 0:
            return TGT_OPEN, None, None, "no_target"
        if not self.ftp:
            self.missing_ftp = True
            return TGT_OPEN, None, None, "no_ftp"
        w = int(round(frac * self.ftp))
        return TGT_POWER, w + 1000, w + 1000, None

    def _run_target(self, mode: str, val) -> tuple:
        if val is None or val <= 0:
            return TGT_OPEN, None, None, "no_target"
        if mode == "hr":
            if not self.fcmax:
                self.missing_fcmax = True
                return TGT_OPEN, None, None, "no_fcmax"
            bpm = int(round(val * self.fcmax))
            return TGT_HEART_RATE, bpm + 100, bpm + 100, None
        mms = int(round(1_000_000 / val))      # val = s/km  ->  mm/s
        return TGT_SPEED, mms, mms, None

    def add(self, *, name, dur_type, dur_value, target=None, intensity=INT_ACTIVE,
            equipment=None, force_open_reason=None) -> None:
        self._real += 1
        t_type, low, high, why = target if target else (TGT_OPEN, None, None, None)
        if force_open_reason:
            t_type, low, high, why = TGT_OPEN, None, None, force_open_reason
        self.steps.append(FitStep(
            name=name, duration_type=dur_type, duration_value=dur_value,
            target_type=t_type, low=low, high=high, intensity=intensity,
            equipment=equipment, index=len(self.steps)))
        if why:
            self.open_steps.append({"step": self._real, "name": name, "reason": why})

    def repeat(self, from_index: int, count: int) -> None:
        self.steps.append(FitStep(
            name="", duration_type=DUR_REPEAT_UNTIL_STEPS, duration_value=from_index,
            target_type=TGT_OPEN, target_value=count, intensity=INT_ACTIVE,
            index=len(self.steps)))

    # -- bici / run (mismo criterio y defaults que blocks_to_intervals_dsl)
    def _tgt(self, b: dict, key_bike: str, key_run: str, default_bike: float):
        if self.sport == "run":
            return self._run_target(b.get("mode", "pace"), float(b.get(key_run, 0)))
        return self._bike_target(float(b.get(key_bike, default_bike)))

    def endurance_block(self, b: dict) -> None:
        t = b.get("type", "steady")
        if t in ("warmup", "cooldown", "ramp"):
            d = int(b.get("duration", 600))
            if self.sport == "run":
                lo, hi = float(b.get("val_low", 0) or 0), float(b.get("val_high", 0) or 0)
            else:
                lo, hi = float(b.get("power_low", 0.5)), float(b.get("power_high", 0.75))
            inten = {"warmup": INT_WARMUP, "cooldown": INT_COOLDOWN}.get(t, INT_ACTIVE)
            if lo > 0 and lo == hi:
                # rampa degenerada = paso constante, expresable exacto
                tgt = self._run_target(b.get("mode", "pace"), lo) if self.sport == "run" \
                    else self._bike_target(lo)
                self.add(name=_STEP_NAME[t], dur_type=DUR_TIME, dur_value=d * 1000,
                         target=tgt, intensity=inten)
            else:
                # FIT no tiene paso-rampa: un rango (lo..hi) significa "mantente
                # dentro", no "sube de lo a hi". No se aproxima: queda abierto.
                self.add(name=_STEP_NAME[t], dur_type=DUR_TIME, dur_value=d * 1000,
                         intensity=inten, force_open_reason="ramp")
        elif t == "steady":
            d = int(b.get("duration", 300))
            self.add(name=_STEP_NAME["steady"], dur_type=DUR_TIME, dur_value=d * 1000,
                     target=self._tgt(b, "power", "val", 0.75))
        elif t == "freeride":
            d = int(b.get("duration", 300))
            self.add(name=_STEP_NAME["freeride"], dur_type=DUR_TIME, dur_value=d * 1000)
        elif t == "intervals":
            rep = int(b.get("repeat", 1))
            on_d, off_d = int(b.get("on_duration", 240)), int(b.get("off_duration", 120))
            start = len(self.steps)
            self.add(name="Interval", dur_type=DUR_TIME, dur_value=on_d * 1000,
                     target=self._tgt(b, "on_power", "on_val", 0.95), intensity=INT_INTERVAL)
            self.add(name="Recovery", dur_type=DUR_TIME, dur_value=off_d * 1000,
                     target=self._tgt(b, "off_power", "off_val", 0.55), intensity=INT_RECOVERY)
            if rep > 1:
                self.repeat(start, rep)
        else:
            raise ValueError(f"tipo de bloque desconocido: {t!r}")

    # -- natacion
    def swim_block(self, b: dict) -> None:
        reps, dist = int(b.get("reps", 1)), int(b.get("dist", 0))
        if reps < 1 or dist < 1:
            raise ValueError("reps/dist invalidos")
        rest = int(b.get("rest", 0) or 0)
        parts = [_SWIM_NAME.get(b.get("type"), "Swim"), _SWIM_STROKE.get(b.get("stroke", "full"), "")]
        name = " ".join(p for p in parts if p) + f" {dist}m"
        equipment = _EQUIPMENT.get(b.get("equipment", ""))
        pace = b.get("pace")
        if pace:
            mms = int(round(100_000 / float(pace)))     # s/100 m -> mm/s
            target = (TGT_SPEED, mms, mms, None)
        else:
            target = None
        inten = INT_WARMUP if b.get("type") == "warmup" else INT_COOLDOWN if b.get("type") == "cooldown" else INT_ACTIVE

        def swim_step():
            self.add(name=name, dur_type=DUR_DISTANCE, dur_value=dist * 100,
                     target=target, intensity=inten, equipment=equipment)

        # El descanso es ENTRE series (swim_totals cuenta reps-1): si hay mas de
        # una serie y descanso, (nado + descanso) x (reps-1) y un nado final.
        if reps > 1 and rest > 0:
            start = len(self.steps)
            swim_step()
            self.add(name="Rest", dur_type=DUR_TIME, dur_value=rest * 1000, intensity=INT_REST)
            if reps - 1 > 1:
                self.repeat(start, reps - 1)
            swim_step()
        elif reps > 1:
            start = len(self.steps)
            swim_step()
            self.repeat(start, reps)
        else:
            swim_step()


# ── Serializacion ────────────────────────────────────────────────────────
def _encode(name: str, sport: str, steps: list, when: datetime) -> bytes:
    body = bytearray()

    # file_id (local 0)
    body += _definition(0, MESG_FILE_ID, [(0, 1, _ENUM), (1, 2, _UINT16), (2, 2, _UINT16), (4, 4, _UINT32)])
    ts = int(when.timestamp()) - FIT_EPOCH_OFFSET
    body += b"\x00" + struct.pack("<BHHI", _FILE_TYPE_WORKOUT, _MANUFACTURER_DEVELOPMENT, 0, max(0, ts))

    # workout (local 1)
    body += _definition(1, MESG_WORKOUT, [
        (4, 1, _ENUM), (6, 2, _UINT16), (8, _NAME_BYTES, _STRING), (11, 1, _ENUM)])
    body += b"\x01" + struct.pack("<BH", _SPORT[sport], len(steps)) + _text(name) + struct.pack("<B", _SUB_SPORT[sport])

    # workout_step (local 2)
    body += _definition(2, MESG_WORKOUT_STEP, [
        (254, 2, _UINT16), (0, _NAME_BYTES, _STRING), (1, 1, _ENUM), (2, 4, _UINT32),
        (3, 1, _ENUM), (4, 4, _UINT32), (5, 4, _UINT32), (6, 4, _UINT32),
        (7, 1, _ENUM), (9, 1, _ENUM)])
    for s in steps:
        body += b"\x02" + struct.pack("<H", s.index) + _text(s.name) + struct.pack(
            "<BIBIIIBB", s.duration_type, _u32(s.duration_value), s.target_type,
            _u32(s.target_value), _u32(s.low), _u32(s.high), s.intensity,
            _UINT8_NONE if s.equipment is None else s.equipment)

    header = struct.pack("<BBHI4s", 14, _PROTOCOL_VERSION, _PROFILE_VERSION, len(body), b".FIT")
    header += struct.pack("<H", fit_crc(header))
    payload = header + bytes(body)
    return payload + struct.pack("<H", fit_crc(payload))


def build_workout_fit(name: str, sport: str, blocks: list, *, ftp: Optional[int] = None,
                      fcmax: Optional[int] = None, when: Optional[datetime] = None) -> FitExport:
    """Genera el .fit de un workout Indoor. Lanza FitExportError si no queda
    ningun paso valido. Los bloques invalidos/desconocidos se omiten (mismo
    criterio que el DSL) pero se CUENTAN en `skipped_blocks` para avisar."""
    if sport not in _SPORT:
        raise FitExportError("Deporte no soportado para FIT")
    bld = _Builder(sport, ftp, fcmax)
    skipped = 0
    for b in blocks or []:
        if not isinstance(b, dict):
            skipped += 1
            continue
        try:
            if sport == "swim":
                bld.swim_block(b)
            else:
                bld.endurance_block(b)
        except (TypeError, ValueError, OverflowError) as exc:
            skipped += 1
            logger.warning("Bloque %s omitido al armar FIT: %s", b.get("id"), exc)
    real = [s for s in bld.steps if s.duration_type != DUR_REPEAT_UNTIL_STEPS]
    if not real:
        raise FitExportError("El workout no tiene pasos que se puedan exportar")
    when = when or datetime.now(timezone.utc)
    data = _encode((name or "LabX Workout").strip() or "LabX Workout", sport, bld.steps, when)
    out = FitExport(data=data, steps=bld.steps, open_steps=bld.open_steps,
                    missing_ftp=bld.missing_ftp, missing_fcmax=bld.missing_fcmax,
                    skipped_blocks=skipped)
    return out


def safe_filename(name: str, date_iso: Optional[str]) -> str:
    """Nombre ASCII para la descarga: <nombre>_<fecha>.fit"""
    base = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    base = "".join(c if c.isalnum() else "_" for c in base).strip("_")[:60] or "workout"
    return f"{base}_{date_iso or datetime.now(timezone.utc).strftime('%Y-%m-%d')}.fit"
