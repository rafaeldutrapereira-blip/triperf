"""
sync_garmin_schedule.py
=======================
Lee las sesiones planificadas en localStorage (exportadas como JSON) y
las agenda en Garmin Connect usando garmin_connector.reschedule_workout.

USO RÁPIDO
----------
1. Exporta las sesiones desde el navegador:
   Abre la consola (F12) en training_plan.html y ejecuta:
       copy(localStorage.getItem('kl_training_plan'))
   Luego pega en un archivo: data/planned_sessions.json

2. Corre este script:
       python sync_garmin_schedule.py

   O para solo las sesiones reprogramadas:
       python sync_garmin_schedule.py --rescheduled-only

3. Las sesiones se crean como workouts en Garmin Connect y quedan
   agendadas en el calendario Garmin en la fecha indicada.

NOTAS
-----
- Requiere GARMIN_EMAIL y GARMIN_PASSWORD en .env
- Garmin no tiene endpoint nativo de "mover" — se crea un workout nuevo
  en la fecha destino. Si ya existía uno para esa sesión, quedará duplicado;
  el usuario deberá borrarlo manualmente en Garmin Connect.
- Las sesiones de Garmin (source='garmin') no se tocan — solo las planificadas
  localmente (source='local' / id empieza con 'plan-').
"""

import json
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

SESSIONS_FILE = Path("data/planned_sessions.json")


def main():
    parser = argparse.ArgumentParser(description="Sync LabX planned sessions → Garmin Connect")
    parser.add_argument("--file", default=str(SESSIONS_FILE),
                        help="JSON file with planned sessions (default: data/planned_sessions.json)")
    parser.add_argument("--rescheduled-only", action="store_true",
                        help="Only sync sessions that have been rescheduled (have rescheduled_from field)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be sent without actually calling Garmin API")
    args = parser.parse_args()

    sessions_path = Path(args.file)
    if not sessions_path.exists():
        print(f"[ERROR] Sessions file not found: {sessions_path}")
        print()
        print("Export your sessions from the browser console:")
        print("  copy(localStorage.getItem('kl_training_plan'))")
        print(f"Then paste into: {sessions_path}")
        sys.exit(1)

    with sessions_path.open() as f:
        sessions = json.load(f)

    if not sessions:
        print("[INFO] No planned sessions found in file.")
        sys.exit(0)

    # Filter
    if args.rescheduled_only:
        to_sync = [s for s in sessions if s.get("rescheduled_from")]
        print(f"[INFO] Syncing {len(to_sync)} rescheduled session(s) (of {len(sessions)} total)")
    else:
        to_sync = sessions
        print(f"[INFO] Syncing {len(to_sync)} session(s)")

    if not to_sync:
        print("[INFO] Nothing to sync.")
        sys.exit(0)

    if args.dry_run:
        print("\n[DRY RUN] Would send the following to Garmin Connect:\n")
        for s in to_sync:
            old = s.get("rescheduled_from")
            tag = f"  (moved from {old})" if old else ""
            print(f"  → {s.get('date_iso')} | {s.get('sport','?').upper():4s} | {s.get('name')}{tag}")
        print()
        sys.exit(0)

    # Import connector lazily (only when actually syncing)
    from garmin_connector import reschedule_workout, schedule_workout

    results = []
    for s in to_sync:
        old_date = s.get("rescheduled_from")
        new_date = s.get("date_iso")
        name     = s.get("name", "LabX Workout")
        try:
            if old_date:
                print(f"  Rescheduling '{name}': {old_date} → {new_date} ...")
                result = reschedule_workout(s, old_date, new_date)
            else:
                print(f"  Scheduling '{name}' on {new_date} ...")
                result = schedule_workout(s, new_date)
            results.append({"session": name, "date": new_date, "status": "ok", "garmin": result})
            print(f"    ✓ Garmin workoutId: {result.get('workoutId')}")
        except Exception as e:
            print(f"    ✗ ERROR: {e}")
            results.append({"session": name, "date": new_date, "status": "error", "error": str(e)})

    ok  = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    print(f"\n[DONE] {ok} enviadas ✓  |  {err} errores ✗")

    if err > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
