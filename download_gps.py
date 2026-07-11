"""One-time GPS download for recent outdoor activities."""
import json, sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

df = pd.read_csv("data/activities.csv")
df["date"] = pd.to_datetime(df["date"])

cutoff  = pd.Timestamp(date.today() - timedelta(days=90))
outdoor = df[
    df["sport"].isin(["bike", "run"]) &
    (df["date"] >= cutoff) &
    df["activity_id"].notna()
].copy()
print(f"Outdoor activities to check: {len(outdoor)}")

from garmin_connector import fetch_activity_gps
tracks = Path("data/tracks")
tracks.mkdir(exist_ok=True)

ok = skip = err = 0
for _, row in outdoor.iterrows():
    act_id = int(row["activity_id"])
    tf = tracks / f"{act_id}.json"
    if tf.exists() and tf.stat().st_size > 10:
        skip += 1
        continue
    try:
        pts = fetch_activity_gps(act_id)
        if pts:
            ok += 1
            print(f"  OK  {act_id}: {row['name']} ({len(pts)} pts)")
        else:
            print(f"  SKIP {act_id}: {row['name']} (no GPS / indoor)")
    except Exception as e:
        err += 1
        print(f"  ERR  {act_id}: {e}")

print(f"\nDone: {ok} downloaded, {skip} already cached, {err} errors")
