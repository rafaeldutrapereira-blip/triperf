#!/usr/bin/env python3
"""
export_data.py
Reads CSVs from data/ (produced by sync_garmin.py) and generates
data/dashboard_data.js for the KonaLabs HTML dashboard.

Usage:
    python export_data.py

Chain with sync:
    python sync_garmin.py && python export_data.py
"""

import json
import math
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

DATA = Path("data")


# ── helpers ─────────────────────────────────────────────────────────────────

def load_csv(name):
    p = DATA / name
    if p.exists() and p.stat().st_size > 2:
        try:
            return pd.read_csv(p)
        except Exception as e:
            print(f"  [warn] Could not read {name}: {e}")
    return pd.DataFrame()


def safe_int(v):
    try:
        f = float(v)
        if math.isnan(f):
            return None
        return int(round(f))
    except Exception:
        return None


def safe_float(v, decimals=1):
    try:
        f = float(v)
        if math.isnan(f):
            return None
        return round(f, decimals)
    except Exception:
        return None


# ── sport helpers ────────────────────────────────────────────────────────────

SPORT_ICONS = {
    "swim":              "🏊",
    "pool_swimming":     "🏊",
    "open_water":        "🏊",
    "bike":              "🚴",
    "cycling":           "🚴",
    "virtual_ride":      "🚴",
    "indoor_cycling":    "🚴",
    "run":               "🏃",
    "running":           "🏃",
    "trail_run":         "🏃",
    "strength_training": "💪",
    "strength":          "💪",
}

SPORT_COLORS = {
    "swim":              "rgba(14,165,233,.12)",
    "pool_swimming":     "rgba(14,165,233,.12)",
    "open_water":        "rgba(14,165,233,.12)",
    "bike":              "rgba(255,101,53,.10)",
    "cycling":           "rgba(255,101,53,.10)",
    "virtual_ride":      "rgba(255,101,53,.10)",
    "indoor_cycling":    "rgba(255,101,53,.10)",
    "run":               "rgba(34,197,94,.10)",
    "running":           "rgba(34,197,94,.10)",
    "strength_training": "rgba(168,85,247,.10)",
    "strength":          "rgba(168,85,247,.10)",
}

SPORT_STROKE = {
    "swim":              "var(--cyan)",
    "pool_swimming":     "var(--cyan)",
    "open_water":        "var(--cyan)",
    "bike":              "var(--orange)",
    "cycling":           "var(--orange)",
    "virtual_ride":      "var(--orange)",
    "indoor_cycling":    "var(--orange)",
    "run":               "var(--green)",
    "running":           "var(--green)",
    "strength_training": "var(--purple)",
    "strength":          "var(--purple)",
}


def sport_key(raw):
    return str(raw or "").lower().strip()


# ── main ─────────────────────────────────────────────────────────────────────

def run():
    print("KonaLabs — export_data.py")
    print(f"Reading CSVs from {DATA.resolve()}")

    df_load  = load_csv("training_load.csv")
    df_act   = load_csv("activities.csv")
    df_sleep = load_csv("sleep.csv")
    df_hrv   = load_csv("hrv.csv")

    out = {"generated": date.today().isoformat()}

    # ── 1. Latest training load (CTL / ATL / TSB) ───────────────────────────
    ctl = atl = tsb = ctl_change = atl_delta = None

    if not df_load.empty:
        df_load["date"] = pd.to_datetime(df_load["date"])
        df_load = df_load.sort_values("date").reset_index(drop=True)
        last = df_load.iloc[-1]

        ctl = safe_int(last["ctl"])
        atl = safe_int(last["atl"])
        tsb = safe_float(last["tsb"], 1)

        # deltas vs 7 days ago
        cutoff = df_load["date"].max() - timedelta(days=7)
        prev = df_load[df_load["date"] <= cutoff]
        if not prev.empty:
            p = prev.iloc[-1]
            ctl_change = safe_float(float(last["ctl"]) - float(p["ctl"]), 1)
            atl_delta  = safe_float(float(last["atl"]) - float(p["atl"]), 1)

        print(f"  CTL={ctl}  ATL={atl}  TSB={tsb}  dCTL={ctl_change}")

    out.update(ctl=ctl, atl=atl, tsb=tsb, ctl_change=ctl_change, atl_delta=atl_delta)

    # ── 2. Readiness (TSB-based heuristic, 0-100) ───────────────────────────
    readiness = None
    if tsb is not None:
        readiness = max(20, min(100, int(round(60 + float(tsb) * 1.5))))
    out["readiness"] = readiness
    print(f"  Readiness (computed)={readiness}")

    # ── 3. HRV (from hrv.csv if available) ──────────────────────────────────
    hrv_7d = None
    if not df_hrv.empty:
        try:
            df_hrv["date"] = pd.to_datetime(df_hrv["date"])
            df_hrv = df_hrv.sort_values("date")
            cutoff = df_hrv["date"].max() - timedelta(days=7)
            recent_hrv = df_hrv[df_hrv["date"] >= cutoff]
            col = [c for c in df_hrv.columns if "hrv" in c.lower() and c != "date"]
            if col and not recent_hrv.empty:
                hrv_7d = safe_int(recent_hrv[col[0]].mean())
        except Exception as e:
            print(f"  [warn] HRV parse: {e}")
    out["hrv"] = hrv_7d

    # ── 4. Sleep (last available) ────────────────────────────────────────────
    sleep_score = sleep_h = None
    if not df_sleep.empty:
        try:
            df_sleep["date"] = pd.to_datetime(df_sleep["date"])
            df_sleep = df_sleep.sort_values("date")
            valid = df_sleep[df_sleep["sleep_duration_h"] > 0]
            if not valid.empty:
                last_s = valid.iloc[-1]
                sleep_score = safe_int(last_s.get("sleep_score"))
                sleep_h = safe_float(last_s.get("sleep_duration_h"), 1)
        except Exception as e:
            print(f"  [warn] Sleep parse: {e}")
    out["sleep_score"] = sleep_score
    out["sleep_h"] = sleep_h

    # ── 5. TSS this week ────────────────────────────────────────────────────
    tss_week = tss_week_target = None
    if not df_load.empty:
        latest_date = df_load["date"].max()
        mon = latest_date - timedelta(days=latest_date.weekday())
        week_rows = df_load[df_load["date"] >= mon]
        tss_week = safe_int(week_rows["tss"].sum()) if not week_rows.empty else 0
        tss_week_target = 520  # planned — could be loaded from training_plan.csv
    out["tss_week"] = tss_week
    out["tss_week_target"] = tss_week_target
    print(f"  TSS this week={tss_week}  target={tss_week_target}")

    # ── 6. PMC (weekly, last 16 weeks) ──────────────────────────────────────
    pmc = []
    if not df_load.empty:
        df_load_pmc = df_load.copy()
        df_load_pmc["week"] = df_load_pmc["date"].dt.to_period("W")
        weekly = (
            df_load_pmc
            .groupby("week", sort=True)
            .agg(ctl=("ctl", "last"), atl=("atl", "last"), tss=("tss", "sum"))
            .reset_index()
        )
        weekly = weekly.tail(16).reset_index(drop=True)
        n = len(weekly)
        for i, row in weekly.iterrows():
            label = f"S{i+1}" if i < n - 1 else "HOY"
            pmc.append({
                "l":   label,
                "ctl": safe_int(row["ctl"]),
                "atl": safe_int(row["atl"]),
                "tss": safe_int(row["tss"]),
            })
    out["pmc"] = pmc
    print(f"  PMC weeks={len(pmc)}")

    # ── 7. Recent activities (last 7) ────────────────────────────────────────
    activities = []
    if not df_act.empty:
        df_act["date"] = pd.to_datetime(df_act["date"])
        df_act = df_act.sort_values("date", ascending=False).reset_index(drop=True)

        for _, row in df_act.head(7).iterrows():
            s   = sport_key(row.get("sport"))
            dur = int(row["duration_sec"] / 60) if pd.notna(row.get("duration_sec")) else 0
            dist_m = float(row["distance_m"]) if pd.notna(row.get("distance_m")) else 0
            dist_km = round(dist_m / 1000, 1) if dist_m > 0 else None

            tss_v = safe_int(row.get("tss"))
            avg_hr = safe_int(row.get("avg_hr"))
            avg_pw = safe_int(row.get("norm_power") or row.get("avg_power"))
            pace_raw = safe_float(row.get("avg_pace_sec_km"), 1)

            # Format pace as M:SS/km
            pace_str = None
            if pace_raw and pace_raw > 0 and s in ("run", "running"):
                m, sc = divmod(int(pace_raw), 60)
                pace_str = f"{m}:{sc:02d}/km"

            # swim pace per 100m
            swim_pace = None
            if pace_raw and pace_raw > 0 and "swim" in s:
                p100 = pace_raw / 10
                m2, sc2 = divmod(int(p100), 60)
                swim_pace = f"{m2}:{sc2:02d}/100m"

            act_date = row["date"]
            activities.append({
                "activity_id": int(row["activity_id"]) if pd.notna(row.get("activity_id")) else None,
                "name":        str(row["name"]),
                "sport":       s,
                "icon":        SPORT_ICONS.get(s, "🏅"),
                "color":       SPORT_COLORS.get(s, "rgba(61,104,128,.1)"),
                "stroke":      SPORT_STROKE.get(s, "var(--muted)"),
                "date_label":  act_date.strftime("%d %b").lstrip("0") if hasattr(act_date, 'strftime') else str(act_date)[:10],
                "date_iso":    str(act_date)[:10],
                "dur_min":     dur,
                "dist_km":     dist_km,
                "avg_hr":      avg_hr,
                "avg_power":   avg_pw,
                "tss":         tss_v,
                "calories":    safe_int(row.get("calories")),
                "pace_str":    pace_str,
                "swim_pace":   swim_pace,
                "swolf":       safe_int(row.get("swolf")),
            })

    out["activities"] = activities
    print(f"  Activities={len(activities)}")

    # ── 8. Weekly discipline breakdown ──────────────────────────────────────
    disc = {"swim_km": 0.0, "bike_km": 0.0, "run_km": 0.0, "strength_n": 0}
    if not df_act.empty:
        latest_act = df_act["date"].max()
        mon = latest_act - timedelta(days=latest_act.weekday())
        week_act = df_act[df_act["date"] >= mon]
        for _, row in week_act.iterrows():
            s = sport_key(row.get("sport"))
            dist = float(row["distance_m"]) / 1000 if pd.notna(row.get("distance_m")) and float(row.get("distance_m", 0)) > 0 else 0
            if "swim" in s:
                disc["swim_km"] += dist
            elif "bike" in s or "ride" in s or "cycling" in s:
                disc["bike_km"] += dist
            elif "run" in s:
                disc["run_km"] += dist
            elif "strength" in s:
                disc["strength_n"] += 1
        disc = {k: round(v, 1) if isinstance(v, float) else v for k, v in disc.items()}
    out["weekly_disc"] = disc
    print(f"  Weekly: Swim {disc['swim_km']}km  Bike {disc['bike_km']}km  Run {disc['run_km']}km  Str {disc['strength_n']}")

    # ── 9. Write JS ──────────────────────────────────────────────────────────
    DATA.mkdir(exist_ok=True)
    js_path = DATA / "dashboard_data.js"
    js = (
        f"/* KonaLabs dashboard_data.js — generated {date.today()} */\n"
        f"/* DO NOT EDIT MANUALLY — regenerate with: python export_data.py */\n"
        f"window.KL_DATA = {json.dumps(out, indent=2, default=str, ensure_ascii=False)};\n"
    )
    js_path.write_text(js, encoding="utf-8")
    print(f"\nOK Written: {js_path}")
    print(f"  Size: {js_path.stat().st_size} bytes")


if __name__ == "__main__":
    run()
