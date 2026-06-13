r"""
Daily automation script - fetches Garmin data and refreshes cache.
Run manually or schedule with Windows Task Scheduler / cron.

Windows Task Scheduler command:
  python C:\Users\rafae\triathlon-dashboard\sync_garmin.py

Or with schedule library (run this script in background):
  python sync_garmin.py --daemon
"""

import argparse
import logging
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import schedule

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("data/sync.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


def invalidate_today_cache():
    """Remove today's cached files so next dashboard load fetches fresh data."""
    today = date.today()
    cache_dir = Path("data/cache")
    removed = 0
    for f in cache_dir.glob(f"*{today}*"):
        f.unlink()
        removed += 1
    log.info("Invalidated %d cache files for %s", removed, today)


def sync():
    """Full sync: fetch last 90 days from Garmin and rebuild load timeline."""
    log.info("Starting daily Garmin sync...")
    try:
        from garmin_connector import (
            fetch_activities, fetch_hrv_status,
            fetch_sleep, build_training_load,
        )
        from dotenv import load_dotenv
        import os, json

        load_dotenv()
        ftp = float(os.getenv("FTP_WATTS", 250))
        threshold_run = float(os.getenv("THRESHOLD_PACE_RUN_SEC", 300))

        invalidate_today_cache()

        end   = date.today()
        start = end - timedelta(days=90)

        log.info("Fetching activities %s -> %s", start, end)
        df_act   = fetch_activities(start, end)
        df_hrv   = fetch_hrv_status(start, end)
        df_sleep = fetch_sleep(start, end)
        df_load  = build_training_load(df_act, ftp, threshold_run)

        # Persist to CSV for fast dashboard reload
        out_dir = Path("data")
        df_act.to_csv(out_dir / "activities.csv",     index=False)
        df_hrv.to_csv(out_dir / "hrv.csv",            index=False)
        df_sleep.to_csv(out_dir / "sleep.csv",        index=False)
        df_load.to_csv(out_dir / "training_load.csv", index=False)

        log.info("Sync complete. Activities: %d rows, Load: %d days",
                 len(df_act), len(df_load))

        # ── GPS tracks: download for outdoor activities of last 30 days ──────
        try:
            from garmin_connector import fetch_activity_gps
            email    = os.getenv("GARMIN_EMAIL", "")
            password = os.getenv("GARMIN_PASSWORD", "")
            outdoor  = df_act[
                df_act["sport"].isin(["bike", "run"]) &
                df_act["date"] >= pd.Timestamp(end - timedelta(days=30))
            ].copy() if not df_act.empty else pd.DataFrame()

            gps_ok = 0
            for _, row in outdoor.iterrows():
                act_id = int(row.get("activity_id") or 0)
                if not act_id:
                    continue
                track_f = Path("data/tracks") / f"{act_id}.json"
                if track_f.exists() and track_f.stat().st_size > 10:
                    continue   # already cached
                try:
                    pts = fetch_activity_gps(act_id,
                                             email=email or None,
                                             password=password or None)
                    if pts:
                        gps_ok += 1
                        log.info("GPS cached: activity %s (%d pts)", act_id, len(pts))
                    else:
                        log.info("GPS empty (indoor?): activity %s", act_id)
                except Exception as eg:
                    log.warning("GPS skip activity %s: %s", act_id, eg)

            log.info("GPS sync done: %d tracks downloaded", gps_ok)
        except Exception as eg2:
            log.warning("GPS sync block failed: %s", eg2)

    except Exception as e:
        log.error("Sync failed: %s", e, exc_info=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--daemon", action="store_true",
                        help="Run as daemon, sync every day at 06:00")
    args = parser.parse_args()

    if args.daemon:
        schedule.every().day.at("06:00").do(sync)
        log.info("Daemon started. Will sync daily at 06:00.")
        sync()   # run immediately on start
        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        sync()
