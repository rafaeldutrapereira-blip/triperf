"""
LabX · Race Predictor — Streamlit App
3-Curve Predictive Intelligence System

Curve A: Garmin (biological/training history)
Curve B: Race profile (course + environment)
Curve C: Manual athlete profile (field-tested metrics)
"""

import os
import math
import json
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()

# ── Internal imports ───────────────────────────────────────────────────────
from models.bike_physics import (
    BikePhysicsParams, predict_bike, whatif_sweep,
)
from models.run_physics  import RunPhysicsParams, predict_run
from models.swim_physics import SwimPhysicsParams, predict_swim
from models.gap_analysis import (
    SplitResult, CourseProfile, AthleteMetrics, analyse_gaps,
)
from data.race_database import (
    RACE_DB, search_races, race_by_name, all_race_names,
)
from data.gpx_parser import gpx_to_race_dict, parse_gpx_bytes

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LabX · Race Predictor",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Kona palette CSS (minimal — Streamlit 1.58 safe) ──────────────────────
st.markdown("""
<style>
:root {
  --bg: #04080F; --surface: #08121E; --surface2: #0C1D30;
  --orange: #FF6535; --gold: #F0A500; --cyan: #0EA5E9;
  --green: #10B981; --red: #EF4444; --muted: #7FB3CC;
}
.kl-hero {
  background: linear-gradient(135deg, #08121E 0%, #0C1D30 100%);
  border: 1px solid #0C1D30; border-radius: 12px;
  padding: 1.2rem 1.6rem; margin-bottom: 1rem;
}
.kl-metric-box {
  background: #08121E; border: 1px solid #0C1D30;
  border-radius: 10px; padding: 1rem; text-align: center;
}
.kl-chip {
  display: inline-block; padding: .2rem .6rem;
  border-radius: 20px; font-size: .7rem; font-weight: 700;
  letter-spacing: .06em; margin: .1rem;
}
.chip-a { background: rgba(14,165,233,.15); color: #0EA5E9; }
.chip-b { background: rgba(240,165,0,.15);  color: #F0A500; }
.chip-c { background: rgba(16,185,129,.15); color: #10B981; }
.kl-alert { border-radius: 8px; padding: .65rem .9rem; margin: .35rem 0; font-size: .85rem; }
.kl-alert-warn   { background: rgba(240,165,0,.1);   border-left: 3px solid #F0A500; }
.kl-alert-danger { background: rgba(239,68,68,.1);   border-left: 3px solid #EF4444; }
.kl-alert-info   { background: rgba(14,165,233,.1);  border-left: 3px solid #0EA5E9; }
.kl-alert-ok     { background: rgba(16,185,129,.1);  border-left: 3px solid #10B981; }
.kl-rec { border-radius: 8px; padding: .6rem .9rem; margin:.3rem 0;
           background: #0C1D30; border-left: 3px solid #FF6535; font-size:.85rem; }
</style>
""", unsafe_allow_html=True)

# ── Helper formatters ──────────────────────────────────────────────────────

def fmt_hms(seconds: float) -> str:
    seconds = max(0, round(seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}:{m:02d}:{s:02d}"


def fmt_ms(seconds: float) -> str:
    seconds = max(0, round(seconds))
    m = seconds // 60
    s = seconds % 60
    return f"{m}:{s:02d}"


def parse_pace(s: str) -> float:
    """Parse 'M:SS' or 'MM:SS' → seconds."""
    try:
        parts = s.strip().split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return 0.0


def parse_hms(s: str) -> float:
    """Parse 'H:MM:SS' → seconds."""
    try:
        parts = s.strip().split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return float(s) * 3600
    except Exception:
        return 0.0


# ── Session state init ─────────────────────────────────────────────────────

def _init_state():
    defaults = {
        # Curve A — Garmin
        "a_ftp":       235.0,
        "a_vo2max":    52.0,
        "a_css":       110.0,   # sec/100m
        "a_run_pace":  300.0,   # sec/km threshold
        "a_ctl":       91.0,
        "a_atl":       106.0,
        "a_tsb":       -15.0,
        "a_weight":    62.0,
        "a_loaded":    False,

        # Curve B — Race
        "race":        None,
        "b_temp":      22.0,
        "b_humidity":  60.0,
        "b_wind":      0.0,
        "b_altitude":  0.0,
        "b_goal_hms":  "5:00:00",

        # Curve C — Manual
        "c_ftp":       240.0,
        "c_css":       110.0,
        "c_run_pace":  250.0,   # sec/km (4:10/km)
        "c_weight":    62.0,
        "c_cda":       0.32,
        "c_crr":       0.003,
        "c_bike_kg":   8.0,
        "c_fcmax":     180,

        # Results
        "predictions": None,
        "gap_report":  None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # Pre-load default race so button is immediately active
    if st.session_state.race is None:
        try:
            from data.race_database import race_by_name
            default_race = race_by_name("Ironman 70.3 Pucón")
            if default_race:
                st.session_state.race = default_race
                climate = default_race.get("climate", {})
                st.session_state.b_temp     = float(climate.get("temp_c", 18))
                st.session_state.b_wind     = float(climate.get("wind_ms", 3))
                st.session_state.b_altitude = float(climate.get("altitude_m", 250))
        except Exception:
            pass


# ── Garmin loader ──────────────────────────────────────────────────────────

def _load_garmin_from_kl_data():
    """Try to read from the existing dashboard_data.js file (no API call needed)."""
    js_path = Path("data/dashboard_data.js")
    if not js_path.exists():
        return None
    try:
        text = js_path.read_text(encoding="utf-8")
        # Extract the JSON object from window.KL_DATA = {...};
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start < 0 or end <= 0:
            return None
        data = json.loads(text[start:end])
        return data
    except Exception as e:
        st.warning(f"No pude leer dashboard_data.js: {e}")
        return None


def _load_garmin_from_csv():
    """Derive Garmin metrics from local CSVs (activities.csv, training_load.csv)."""
    act_path  = Path("data/activities.csv")
    load_path = Path("data/training_load.csv")
    if not act_path.exists():
        return None
    df_act = pd.read_csv(act_path)
    df_act["date"] = pd.to_datetime(df_act["date"], errors="coerce")

    result = {}

    # FTP from most recent bike activity with ftp column
    bike = df_act[df_act.get("sport", pd.Series(dtype=str)) == "bike"]
    if not bike.empty and "ftp" in bike.columns:
        ftp_vals = bike["ftp"].dropna()
        if not ftp_vals.empty:
            result["ftp"] = float(ftp_vals.iloc[-1])

    # CSS from best long swim
    swim = df_act[df_act.get("sport", pd.Series(dtype=str)) == "swim"]
    swim_long = swim[swim.get("dist_km", swim.get("distance_m", pd.Series()) / 1000) >= 1.5] if not swim.empty else pd.DataFrame()
    if not swim_long.empty and "dur_min" in swim_long.columns:
        dist_col = "dist_km" if "dist_km" in swim_long.columns else None
        if dist_col:
            paces = (swim_long["dur_min"] * 60) / (swim_long[dist_col] * 10)
            paces = paces[(paces > 80) & (paces < 180)]
            if not paces.empty:
                result["css_s_100m"] = float(paces.nsmallest(max(2, len(paces)//3)).mean())

    # CTL/ATL/TSB from training load
    if load_path.exists():
        df_load = pd.read_csv(load_path)
        df_load["date"] = pd.to_datetime(df_load["date"], errors="coerce")
        latest = df_load.sort_values("date").iloc[-1]
        if "ctl" in latest: result["ctl"] = float(latest["ctl"])
        if "atl" in latest: result["atl"] = float(latest["atl"])
        if "tsb" in latest: result["tsb"] = float(latest["tsb"])

    return result if result else None


def _try_garmin_api():
    """Call Garmin Connect API (live). Requires .env credentials."""
    email = os.getenv("GARMIN_EMAIL", "")
    pw    = os.getenv("GARMIN_PASSWORD", "")
    if not email or not pw:
        st.error("Configura GARMIN_EMAIL y GARMIN_PASSWORD en tu .env")
        return None

    try:
        from garmin_connector import (
            fetch_activities, fetch_vo2max, build_training_load,
        )
        from datetime import date as _date
        end   = _date.today()
        start = end - timedelta(days=90)

        with st.spinner("Conectando a Garmin Connect…"):
            df_act  = fetch_activities(start, end)
            ftp_env = float(os.getenv("FTP_WATTS", 240))
            df_load = build_training_load(df_act, ftp_env, 300.0)

        latest_load = df_load.sort_values("date").iloc[-1]
        vo2  = fetch_vo2max()

        result = {
            "ftp":        ftp_env,
            "vo2max_run": vo2.get("vo2max_run") or 52.0,
            "ctl":        float(latest_load.get("ctl", 70)),
            "atl":        float(latest_load.get("atl", 75)),
            "tsb":        float(latest_load.get("tsb", -5)),
        }
        return result

    except Exception as e:
        st.error(f"Error Garmin API: {e}")
        return None


# ── Prediction engine ──────────────────────────────────────────────────────

def _run_prediction(race: dict, env: dict) -> dict:
    """
    Compute Curve A (Garmin) and Curve C (Manual) predictions for a race.
    Returns dict with keys 'A', 'C', 'target_s'.
    """
    ss  = st.session_state
    dist = race["distances"]
    swim_cfg = race.get("swim", {})
    bike_cfg = race.get("bike", {})
    run_cfg  = race.get("run",  {})

    t1_s = dist.get("t1_min", 4.0) * 60
    t2_s = dist.get("t2_min", 3.0) * 60

    race_frac_map = {"sprint": 0.97, "olympic": 0.95, "703": 0.92, "ironman": 0.85}
    run_frac_map  = {"sprint": 0.97, "olympic": 0.96, "703": 0.95, "ironman": 0.87}
    if_map        = {"sprint": 0.83, "olympic": 0.80, "703": 0.75, "ironman": 0.68}

    dist_key  = race.get("distance", "703")
    race_frac = race_frac_map.get(dist_key, 0.92)
    run_frac  = run_frac_map.get(dist_key, 0.95)
    if_factor = if_map.get(dist_key, 0.75)

    # ── Curve A — Garmin prediction ──────────────────────────────────────
    sw_a = predict_swim(SwimPhysicsParams(
        css_s_100m    = ss.a_css,
        distance_km   = dist["swim"],
        water_type    = swim_cfg.get("water_type", "lago"),
        wetsuit       = swim_cfg.get("wetsuit", True),
        current_ms    = swim_cfg.get("current_ms", 0.0),
        water_temp_c  = swim_cfg.get("water_temp_c", env.get("temp_c", 22)),
        race_fraction = race_frac,
    ))

    # Fatigue penalty from TSB
    tsb        = ss.a_tsb
    fatigue_if = if_factor * (1.0 + max(-0.12, min(0.04, tsb / 250.0)))
    bk_a = predict_bike(BikePhysicsParams(
        ftp_w          = ss.a_ftp,
        weight_kg      = ss.a_weight,
        cda            = 0.32,
        crr            = 0.004,
        distance_km    = dist["bike"],
        elevation_gain_m = bike_cfg.get("elevation_gain_m", 0),
        elevation_loss_m = bike_cfg.get("elevation_loss_m", 0),
        altitude_m     = env.get("altitude_m", 0),
        temperature_c  = env.get("temp_c", 22),
        wind_ms        = env.get("wind_ms", 0),
        profile        = bike_cfg.get("profile"),
        if_factor      = fatigue_if,
    ))

    # Run fatigue increases with TSB penalty
    run_threshold_a = ss.a_run_pace * (1.0 + max(0.0, -tsb / 200.0))
    rn_a = predict_run(RunPhysicsParams(
        threshold_pace_s_km = run_threshold_a,
        weight_kg    = ss.a_weight,
        distance_km  = dist["run"],
        elevation_gain_m = run_cfg.get("elevation_gain_m", 0),
        elevation_loss_m = run_cfg.get("elevation_loss_m", 0),
        surface      = run_cfg.get("surface", "asfalto"),
        altitude_m   = env.get("altitude_m", 0),
        temperature_c = env.get("temp_c", 22),
        race_fraction = run_frac,
        bike_if       = fatigue_if,
    ))

    pred_a = SplitResult(
        swim_s = sw_a["time_s"], t1_s = t1_s,
        bike_s = bk_a["time_s"], t2_s = t2_s,
        run_s  = rn_a["time_s"],
    )

    # ── Curve C — Manual prediction ──────────────────────────────────────
    sw_c = predict_swim(SwimPhysicsParams(
        css_s_100m    = ss.c_css,
        distance_km   = dist["swim"],
        water_type    = swim_cfg.get("water_type", "lago"),
        wetsuit       = swim_cfg.get("wetsuit", True),
        current_ms    = swim_cfg.get("current_ms", 0.0),
        water_temp_c  = swim_cfg.get("water_temp_c", env.get("temp_c", 22)),
        race_fraction = race_frac,
    ))

    bk_c = predict_bike(BikePhysicsParams(
        ftp_w          = ss.c_ftp,
        weight_kg      = ss.c_weight,
        bike_kg        = ss.c_bike_kg,
        cda            = ss.c_cda,
        crr            = ss.c_crr,
        distance_km    = dist["bike"],
        elevation_gain_m = bike_cfg.get("elevation_gain_m", 0),
        elevation_loss_m = bike_cfg.get("elevation_loss_m", 0),
        altitude_m     = env.get("altitude_m", 0),
        temperature_c  = env.get("temp_c", 22),
        wind_ms        = env.get("wind_ms", 0),
        profile        = bike_cfg.get("profile"),
        if_factor      = if_factor,
    ))

    rn_c = predict_run(RunPhysicsParams(
        threshold_pace_s_km = ss.c_run_pace,
        weight_kg    = ss.c_weight,
        distance_km  = dist["run"],
        elevation_gain_m = run_cfg.get("elevation_gain_m", 0),
        elevation_loss_m = run_cfg.get("elevation_loss_m", 0),
        surface      = run_cfg.get("surface", "asfalto"),
        altitude_m   = env.get("altitude_m", 0),
        temperature_c = env.get("temp_c", 22),
        race_fraction = run_frac,
        bike_if       = if_factor,
    ))

    pred_c = SplitResult(
        swim_s = sw_c["time_s"], t1_s = t1_s,
        bike_s = bk_c["time_s"], t2_s = t2_s,
        run_s  = rn_c["time_s"],
    )

    # ── Target B (manual goal time) ──────────────────────────────────────
    goal_s  = parse_hms(ss.b_goal_hms)
    # Distribute goal across disciplines proportionally to Curve C splits
    total_c = pred_c.total_s
    if total_c > 0 and goal_s > 0:
        ratio = goal_s / total_c
        target_b = SplitResult(
            swim_s = pred_c.swim_s * ratio, t1_s = t1_s,
            bike_s = pred_c.bike_s * ratio, t2_s = t2_s,
            run_s  = pred_c.run_s  * ratio,
        )
    else:
        target_b = pred_c

    # ── Gap analysis ─────────────────────────────────────────────────────
    course_prof = CourseProfile(
        bike_elevation_gain_m = bike_cfg.get("elevation_gain_m", 0),
        bike_distance_km      = dist["bike"],
        run_elevation_gain_m  = run_cfg.get("elevation_gain_m", 0),
        run_distance_km       = dist["run"],
        wind_ms               = env.get("wind_ms", 0),
        temperature_c         = env.get("temp_c", 22),
        altitude_m            = env.get("altitude_m", 0),
        surface               = run_cfg.get("surface", "asfalto"),
    )

    athlete_metrics = AthleteMetrics(
        garmin_ftp       = ss.a_ftp,
        manual_ftp       = ss.c_ftp,
        garmin_css       = ss.a_css,
        manual_css       = ss.c_css,
        garmin_run_pace  = ss.a_run_pace,
        manual_run_pace  = ss.c_run_pace,
        ctl              = ss.a_ctl,
        atl              = ss.a_atl,
        tsb              = ss.a_tsb,
        weight_kg        = ss.c_weight,
    )

    gap_report = analyse_gaps(pred_a, pred_c, target_b, athlete_metrics, course_prof)

    return {
        "A":          pred_a,
        "C":          pred_c,
        "B":          target_b,
        "target_s":   goal_s,
        "gap":        gap_report,
        "details": {
            "sw_a": sw_a, "bk_a": bk_a, "rn_a": rn_a,
            "sw_c": sw_c, "bk_c": bk_c, "rn_c": rn_c,
        },
        "bike_params_c": BikePhysicsParams(
            ftp_w=ss.c_ftp, weight_kg=ss.c_weight, bike_kg=ss.c_bike_kg,
            cda=ss.c_cda, crr=ss.c_crr,
            distance_km=dist["bike"],
            elevation_gain_m=bike_cfg.get("elevation_gain_m", 0),
            elevation_loss_m=bike_cfg.get("elevation_loss_m", 0),
            altitude_m=env.get("altitude_m", 0), temperature_c=env.get("temp_c", 22),
            wind_ms=env.get("wind_ms", 0),
            profile=bike_cfg.get("profile"), if_factor=if_factor,
        ),
    }


# ── Plotly charts ──────────────────────────────────────────────────────────

_COLORS = {"A": "#0EA5E9", "B": "#F0A500", "C": "#10B981"}

_THEME = dict(
    plot_bgcolor  = "#04080F",
    paper_bgcolor = "#04080F",
    font_color    = "#7FB3CC",
    font_family   = "Inter, sans-serif",
)


def _chart_comparison(preds: dict) -> go.Figure:
    """Grouped bar chart: Swim / Bike / Run splits for A, B (goal), C."""
    A, B, C = preds["A"], preds["B"], preds["C"]

    disciplines = ["Natación", "Ciclismo", "Carrera"]
    vals_A = [A.swim_s / 60, A.bike_s / 60, A.run_s / 60]
    vals_B = [B.swim_s / 60, B.bike_s / 60, B.run_s / 60]
    vals_C = [C.swim_s / 60, C.bike_s / 60, C.run_s / 60]

    fig = go.Figure()
    for label, vals, color in [
        ("Garmin (A)", vals_A, _COLORS["A"]),
        ("Meta (B)",   vals_B, _COLORS["B"]),
        ("Manual (C)", vals_C, _COLORS["C"]),
    ]:
        fig.add_trace(go.Bar(
            name=label, x=disciplines, y=vals,
            marker_color=color,
            text=[fmt_ms(v * 60) if v < 60 else fmt_hms(v * 60) for v in vals],
            textposition="outside",
            textfont=dict(size=11),
        ))

    fig.update_layout(
        barmode="group", title="Splits por Disciplina — Comparativa 3 Curvas",
        title_font_color="#F0A500",
        yaxis_title="Tiempo (min)",
        legend=dict(bgcolor="#08121E", bordercolor="#0C1D30", borderwidth=1),
        height=380,
        **_THEME,
    )
    return fig


def _chart_total_comparison(preds: dict) -> go.Figure:
    """Hero horizontal bar — total times A, B, C."""
    A, B, C = preds["A"], preds["B"], preds["C"]
    labels  = ["Meta (B)", "Manual (C)", "Garmin (A)"]
    totals  = [B.total_s, C.total_s, A.total_s]
    colors  = [_COLORS["B"], _COLORS["C"], _COLORS["A"]]
    texts   = [fmt_hms(t) for t in totals]

    fig = go.Figure(go.Bar(
        x=totals, y=labels,
        orientation="h",
        marker_color=colors,
        text=texts, textposition="inside",
        textfont=dict(size=14, color="#ffffff"),
        width=[0.45, 0.45, 0.45],
    ))
    fig.update_layout(
        title="Tiempo Total — Curvas A / Meta B / C",
        title_font_color="#F0A500",
        xaxis=dict(
            showticklabels=False, showgrid=False, zeroline=False,
            range=[0, max(totals) * 1.15],
        ),
        height=220,
        margin=dict(l=90, r=30, t=48, b=10),
        **_THEME,
    )
    return fig


def _chart_radar(preds: dict) -> go.Figure:
    """Radar chart: per-discipline performance vs goal (%)."""
    rd = preds["gap"].radar_data
    cats  = rd["disciplines"] + [rd["disciplines"][0]]

    fig = go.Figure()
    for label, key, color in [
        ("Garmin (A)", "A_pct", _COLORS["A"]),
        ("Manual (C)", "C_pct", _COLORS["C"]),
        ("Meta (B)",   "B_pct", _COLORS["B"]),
    ]:
        vals = rd[key] + [rd[key][0]]
        fig.add_trace(go.Scatterpolar(
            r=vals, theta=cats, name=label, fill="toself",
            line_color=color,
            fillcolor=color.replace(")", ",0.10)").replace("rgb", "rgba"),
        ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[80, 115],
                            gridcolor="#0C1D30", linecolor="#0C1D30",
                            tickfont=dict(size=9, color="#7FB3CC")),
            angularaxis=dict(gridcolor="#0C1D30", linecolor="#0C1D30"),
            bgcolor="#08121E",
        ),
        title="Gap Analysis — % del Objetivo por Disciplina",
        title_font_color="#F0A500",
        legend=dict(bgcolor="#08121E", bordercolor="#0C1D30"),
        height=380,
        **_THEME,
    )
    return fig


def _chart_elevation(race: dict) -> go.Figure:
    """Course elevation profile for bike segment."""
    profile = race.get("bike", {}).get("profile")
    if not profile or len(profile) < 2:
        return None

    kms  = [p[0] for p in profile]
    eles = [p[1] for p in profile]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=kms, y=eles, mode="lines",
        fill="tozeroy",
        fillcolor="rgba(255,101,53,0.12)",
        line=dict(color="#FF6535", width=2),
        name="Altitud (m)",
    ))
    fig.update_layout(
        title=f"Perfil Ciclismo — {race.get('name', '')}",
        title_font_color="#F0A500",
        xaxis_title="Km", yaxis_title="Altitud (m)",
        height=260,
        margin=dict(l=50, r=20, t=45, b=40),
        **_THEME,
    )
    return fig


def _chart_whatif_ftp(bike_params: BikePhysicsParams) -> go.Figure:
    """What-if: how bike time changes with FTP."""
    base_ftp = bike_params.ftp_w
    ftp_range = list(range(int(base_ftp) - 40, int(base_ftp) + 45, 5))
    rows      = whatif_sweep(bike_params, "ftp_w", ftp_range)

    x = [r["ftp_w"] for r in rows]
    y = [r["time_s"] / 60 for r in rows]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines+markers",
        line=dict(color=_COLORS["C"], width=2),
        marker=dict(size=5),
        name="Tiempo Ciclismo",
    ))
    fig.add_vline(x=base_ftp, line_dash="dash", line_color=_COLORS["B"],
                  annotation_text=f"FTP actual {base_ftp}W",
                  annotation_font_color=_COLORS["B"])
    fig.update_layout(
        title="What-If: FTP → Tiempo Ciclismo",
        title_font_color="#F0A500",
        xaxis_title="FTP (W)", yaxis_title="Tiempo Ciclismo (min)",
        height=300, margin=dict(l=50, r=20, t=48, b=40),
        **_THEME,
    )
    return fig


def _chart_whatif_weight(bike_params: BikePhysicsParams) -> go.Figure:
    """What-if: how bike time changes with body weight."""
    base_w = bike_params.weight_kg
    w_range = [round(base_w - 8 + i * 0.5, 1) for i in range(33)]
    rows    = whatif_sweep(bike_params, "weight_kg", w_range)

    x = [r["weight_kg"] for r in rows]
    y = [r["time_s"] / 60 for r in rows]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines+markers",
        line=dict(color=_COLORS["A"], width=2),
        marker=dict(size=4),
        name="Tiempo Ciclismo",
    ))
    fig.add_vline(x=base_w, line_dash="dash", line_color=_COLORS["B"],
                  annotation_text=f"Peso actual {base_w}kg",
                  annotation_font_color=_COLORS["B"])
    fig.update_layout(
        title="What-If: Peso Corporal → Tiempo Ciclismo",
        title_font_color="#F0A500",
        xaxis_title="Peso (kg)", yaxis_title="Tiempo Ciclismo (min)",
        height=300, margin=dict(l=50, r=20, t=48, b=40),
        **_THEME,
    )
    return fig


def _chart_whatif_cda(bike_params: BikePhysicsParams) -> go.Figure:
    """What-if: CdA vs bike time."""
    base_cda = bike_params.cda
    cda_range = [round(0.20 + i * 0.01, 2) for i in range(20)]
    rows      = whatif_sweep(bike_params, "cda", cda_range)

    x = [r["cda"] for r in rows]
    y = [r["time_s"] / 60 for r in rows]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="lines+markers",
        line=dict(color="#A855F7", width=2),
        marker=dict(size=4),
        name="Tiempo Ciclismo",
    ))
    fig.add_vline(x=base_cda, line_dash="dash", line_color=_COLORS["B"],
                  annotation_text=f"CdA actual {base_cda}",
                  annotation_font_color=_COLORS["B"])
    fig.update_layout(
        title="What-If: CdA Aerodinámico → Tiempo Ciclismo",
        title_font_color="#F0A500",
        xaxis_title="CdA (m²)", yaxis_title="Tiempo Ciclismo (min)",
        height=300, margin=dict(l=50, r=20, t=48, b=40),
        **_THEME,
    )
    return fig


# ── UI sections ────────────────────────────────────────────────────────────

def _section_curve_a():
    st.markdown("### 🔵 Curva A — Datos Garmin")
    st.caption("Métricas extraídas de tu historial biológico y de entrenamiento.")

    col_btn1, col_btn2, col_btn3 = st.columns(3)
    with col_btn1:
        if st.button("📂 Cargar desde dashboard_data.js", use_container_width=True):
            data = _load_garmin_from_kl_data()
            if data:
                if data.get("ctl"):      st.session_state.a_ctl      = float(data["ctl"])
                if data.get("atl"):      st.session_state.a_atl      = float(data["atl"])
                tsb = data.get("tsb") or (st.session_state.a_ctl - st.session_state.a_atl)
                st.session_state.a_tsb = float(tsb)
                # Try to get FTP from environment
                ftp_env = float(os.getenv("FTP_WATTS", 240))
                st.session_state.a_ftp = ftp_env
                st.session_state.a_loaded = True
                st.success("✅ Datos Garmin cargados desde dashboard_data.js")
            else:
                st.warning("No encontré dashboard_data.js. Ingresa los datos manualmente.")

    with col_btn2:
        if st.button("📊 Derivar desde CSVs locales", use_container_width=True):
            data = _load_garmin_from_csv()
            if data:
                for k, v in data.items():
                    state_key = f"a_{k.replace('_s_100m', '').replace('css', 'css').replace('run_pace', 'run_pace')}"
                    if k == "ftp":       st.session_state.a_ftp      = v
                    if k == "css_s_100m": st.session_state.a_css     = v
                    if k == "ctl":       st.session_state.a_ctl      = v
                    if k == "atl":       st.session_state.a_atl      = v
                    if k == "tsb":       st.session_state.a_tsb      = v
                st.session_state.a_loaded = True
                st.success("✅ Métricas derivadas de activities.csv y training_load.csv")
            else:
                st.warning("No encontré CSVs. Asegúrate de haber corrido sync_garmin.py")

    with col_btn3:
        if st.button("🌐 Conectar API Garmin (live)", use_container_width=True):
            data = _try_garmin_api()
            if data:
                if data.get("ftp"):        st.session_state.a_ftp    = data["ftp"]
                if data.get("vo2max_run"): st.session_state.a_vo2max = data["vo2max_run"]
                if data.get("ctl"):        st.session_state.a_ctl    = data["ctl"]
                if data.get("atl"):        st.session_state.a_atl    = data["atl"]
                if data.get("tsb"):        st.session_state.a_tsb    = data["tsb"]
                st.session_state.a_loaded = True
                st.success("✅ Conectado a Garmin Connect")

    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.session_state.a_ftp     = st.number_input("FTP Garmin (W)", 100, 500,
                                        int(st.session_state.a_ftp), 5, key="ai_ftp")
        st.session_state.a_vo2max  = st.number_input("VO2Max Garmin", 30.0, 90.0,
                                        float(st.session_state.a_vo2max), 0.5, key="ai_vo2")
    with col2:
        css_display = fmt_ms(st.session_state.a_css)
        css_in = st.text_input("CSS Natación (min:sec/100m)", css_display, key="ai_css")
        css_parsed = parse_pace(css_in)
        if css_parsed > 0: st.session_state.a_css = css_parsed

        rp_display = fmt_ms(st.session_state.a_run_pace)
        rp_in = st.text_input("Umbral Carrera (min:sec/km)", rp_display, key="ai_rp")
        rp_parsed = parse_pace(rp_in)
        if rp_parsed > 0: st.session_state.a_run_pace = rp_parsed
    with col3:
        st.session_state.a_ctl    = st.number_input("CTL", 0.0, 200.0,
                                        float(st.session_state.a_ctl), 1.0, key="ai_ctl")
        st.session_state.a_atl    = st.number_input("ATL", 0.0, 200.0,
                                        float(st.session_state.a_atl), 1.0, key="ai_atl")
        st.session_state.a_tsb    = st.number_input("TSB (Forma)", -80.0, 50.0,
                                        float(st.session_state.a_tsb), 1.0, key="ai_tsb")
        st.session_state.a_weight = st.number_input("Peso Garmin (kg)", 40.0, 120.0,
                                        float(st.session_state.a_weight), 0.5, key="ai_wt")

    # Readiness badge
    readiness = max(0, min(100, 50 + st.session_state.a_tsb * 2))
    color = "#10B981" if readiness > 60 else ("#F0A500" if readiness > 35 else "#EF4444")
    st.markdown(
        f"<div style='margin-top:.5rem'>"
        f"<span class='kl-chip' style='background:rgba(16,185,129,.12);color:{color};font-size:.85rem'>"
        f"Readiness: {readiness:.0f}/100 · CTL {st.session_state.a_ctl:.0f} · "
        f"ATL {st.session_state.a_atl:.0f} · TSB {st.session_state.a_tsb:.0f}"
        f"</span></div>",
        unsafe_allow_html=True,
    )


def _section_curve_b():
    st.markdown("### 🟡 Curva B — Circuito de Carrera")
    st.caption("Selecciona una carrera o ingresa datos del circuito manualmente.")

    # Race search
    race_names  = ["— Seleccionar —"] + sorted([r["name"] for r in RACE_DB.values()])
    col_sel, col_gpx = st.columns([3, 2])
    with col_sel:
        selected = st.selectbox("Buscar carrera en base de datos", race_names, key="b_race_sel")
        if selected != "— Seleccionar —":
            race = race_by_name(selected)
            if race:
                st.session_state.race = race
                climate = race.get("climate", {})
                st.session_state.b_temp     = float(climate.get("temp_c",    22))
                st.session_state.b_wind     = float(climate.get("wind_ms",   0))
                st.session_state.b_altitude = float(climate.get("altitude_m", 0))
                st.session_state.b_humidity = float(climate.get("humidity",  60))

    with col_gpx:
        st.markdown("**O importa un archivo GPX**")
        gpx_type = st.selectbox("Tipo de distancia", ["703", "olympic", "sprint", "ironman"],
                                 key="gpx_type")
        gpx_file = st.file_uploader("Archivo .gpx (segmento ciclismo)", type=["gpx"],
                                     key="gpx_upload")
        if gpx_file is not None:
            try:
                gpx_bytes = gpx_file.read()
                gpx_name  = gpx_file.name.replace(".gpx", "").replace("_", " ").title()
                race_from_gpx = gpx_to_race_dict(gpx_bytes, name=gpx_name, race_type=gpx_type)
                st.session_state.race = race_from_gpx
                parsed = race_from_gpx["_gpx_parsed"]
                st.success(
                    f"✅ GPX cargado — {parsed['distance_km']:.1f} km · "
                    f"D+ {parsed['elevation_gain_m']:.0f}m · "
                    f"{parsed['stats']['n_pts_raw']} puntos GPS"
                )
            except Exception as e:
                st.error(f"Error leyendo GPX: {e}")

    if st.session_state.race:
        race = st.session_state.race
        dist = race["distances"]
        swim = race.get("swim", {})
        bike = race.get("bike", {})
        run  = race.get("run",  {})
        refs = race.get("reference_times", {})

        # Race info card
        st.markdown(
            f"<div class='kl-hero'>"
            f"<b style='color:#F0A500;font-size:1.1rem'>{race.get('flag','')} {race['name']}</b>"
            f"&nbsp;<span class='kl-chip chip-b'>{race['type']}</span>"
            f"<br><span style='color:#7FB3CC;font-size:.82rem'>"
            f"📍 {race.get('location','')} &nbsp;|&nbsp; 📅 {race.get('date','')} "
            f"&nbsp;|&nbsp; 🏢 {race.get('org','')}</span><br>"
            f"<span style='font-size:.8rem;color:#3D6880'>{race.get('notes','')}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Distance chips
        st.markdown(
            f"<span class='kl-chip chip-a'>🏊 {dist['swim']} km</span>"
            f"<span class='kl-chip chip-b'>🚵 {dist['bike']} km</span>"
            f"<span class='kl-chip chip-c'>🏃 {dist['run']} km</span>"
            f"<span class='kl-chip' style='background:#0C1D30;color:#7FB3CC'>"
            f"D+ Bike: {bike.get('elevation_gain_m',0):.0f}m</span>"
            f"<span class='kl-chip' style='background:#0C1D30;color:#7FB3CC'>"
            f"Agua: {swim.get('water_type','—')} {'🥶' if swim.get('water_temp_c',20)<18 else ''}</span>"
            f"<span class='kl-chip' style='background:#0C1D30;color:#7FB3CC'>"
            f"Neopreno: {'✅' if swim.get('wetsuit') else '❌'}</span>",
            unsafe_allow_html=True,
        )

        # Reference times
        if refs:
            st.markdown(
                f"<span style='color:#7FB3CC;font-size:.78rem'>"
                f"Tiempos referencia → "
                f"Ganador: <b style='color:#F0A500'>{refs.get('winner_total','—')}</b> &nbsp;·&nbsp; "
                f"AG 35-39: <b style='color:#0EA5E9'>{refs.get('ag_35_39_winner','—')}</b> &nbsp;·&nbsp; "
                f"Mediana: <b style='color:#7FB3CC'>{refs.get('median_total','—')}</b></span>",
                unsafe_allow_html=True,
            )

        # Elevation profile chart
        elev_fig = _chart_elevation(race)
        if elev_fig:
            st.plotly_chart(elev_fig, use_container_width=True)

    st.divider()
    st.markdown("**Condiciones del Día (ajusta para simulación)**")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.session_state.b_temp     = st.slider("Temperatura (°C)", 5, 42,
                                          int(st.session_state.b_temp), key="b_temp_sl")
    with col2:
        st.session_state.b_humidity = st.slider("Humedad (%)", 20, 100,
                                          int(st.session_state.b_humidity), key="b_hum_sl")
    with col3:
        st.session_state.b_wind     = st.slider("Viento (m/s)", 0.0, 15.0,
                                          float(st.session_state.b_wind), 0.5, key="b_wind_sl")
    with col4:
        st.session_state.b_altitude = st.number_input("Altitud (m s.n.m.)", 0, 4000,
                                          int(st.session_state.b_altitude), 50, key="b_alt_in")

    st.session_state.b_goal_hms = st.text_input(
        "🎯 Tu Meta (H:MM:SS)", st.session_state.b_goal_hms,
        help="Tiempo objetivo total de carrera", key="b_goal_in",
    )


def _section_curve_c():
    st.markdown("### 🟢 Curva C — Perfil Manual del Atleta")
    st.caption("Valores validados por tests de campo. Tienen MÁXIMA PRIORIDAD sobre Garmin.")

    # Load from localStorage (athlete_profile)
    profile_path = Path("data/athlete_profile.json")
    if profile_path.exists() and st.button("📥 Importar desde Perfil del Atleta (athlete_profile.json)"):
        try:
            prof = json.loads(profile_path.read_text(encoding="utf-8"))
            if prof.get("ftp"):      st.session_state.c_ftp      = float(prof["ftp"])
            if prof.get("weight"):   st.session_state.c_weight   = float(prof["weight"])
            if prof.get("css"):
                p = parse_pace(prof["css"])
                if p > 0: st.session_state.c_css = p
            if prof.get("runPace"):
                p = parse_pace(prof["runPace"])
                if p > 0: st.session_state.c_run_pace = p
            if prof.get("fcmax"):   st.session_state.c_fcmax = int(prof["fcmax"])
            st.success("✅ Perfil importado")
        except Exception as e:
            st.error(f"Error leyendo perfil: {e}")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Potencia**")
        st.session_state.c_ftp    = st.number_input("FTP Manual (W)", 100, 600,
                                        int(st.session_state.c_ftp), 5, key="ci_ftp")
        st.session_state.c_weight = st.number_input("Peso Corporal (kg)", 40.0, 120.0,
                                        float(st.session_state.c_weight), 0.5, key="ci_wt")
        wkg = st.session_state.c_ftp / max(0.1, st.session_state.c_weight)
        st.caption(f"W/kg: **{wkg:.2f}**")
    with col2:
        st.markdown("**Aerodinámica (Ciclismo)**")
        st.session_state.c_cda    = st.number_input("CdA (m²)", 0.18, 0.45,
                                        float(st.session_state.c_cda), 0.01, key="ci_cda",
                                        help="TT aero: 0.22–0.28 · Road: 0.30–0.38")
        st.session_state.c_crr    = st.number_input("Crr (resistencia rodadura)", 0.001, 0.010,
                                        float(st.session_state.c_crr), 0.001,
                                        format="%.3f", key="ci_crr")
        st.session_state.c_bike_kg = st.number_input("Peso bici + equipo (kg)", 4.0, 20.0,
                                        float(st.session_state.c_bike_kg), 0.5, key="ci_bk")
    with col3:
        st.markdown("**Ritmos**")
        css_disp = fmt_ms(st.session_state.c_css)
        css_in   = st.text_input("CSS Natación (min:sec/100m)", css_disp, key="ci_css")
        p = parse_pace(css_in)
        if p > 0: st.session_state.c_css = p

        rp_disp  = fmt_ms(st.session_state.c_run_pace)
        rp_in    = st.text_input("Umbral Carrera (min:sec/km)", rp_disp, key="ci_rp",
                                  help="Ritmo al que podrías correr 1 hora a máximo esfuerzo sostenido")
        p = parse_pace(rp_in)
        if p > 0: st.session_state.c_run_pace = p

        st.session_state.c_fcmax = st.number_input("FC Máxima (bpm)", 140, 220,
                                        int(st.session_state.c_fcmax), 1, key="ci_fc")

    # Summary box
    st.markdown(
        f"<div class='kl-hero' style='margin-top:.8rem'>"
        f"<span class='kl-chip chip-c'>FTP {st.session_state.c_ftp}W</span>"
        f"<span class='kl-chip chip-c'>W/kg {wkg:.2f}</span>"
        f"<span class='kl-chip chip-c'>CSS {fmt_ms(st.session_state.c_css)}/100m</span>"
        f"<span class='kl-chip chip-c'>Umbral {fmt_ms(st.session_state.c_run_pace)}/km</span>"
        f"<span class='kl-chip chip-c'>CdA {st.session_state.c_cda}</span>"
        f"<span class='kl-chip chip-c'>Peso total {st.session_state.c_weight + st.session_state.c_bike_kg:.0f}kg</span>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _section_results(preds: dict):
    """Render full results dashboard."""
    A, B, C = preds["A"], preds["B"], preds["C"]
    gap     = preds["gap"]
    details = preds["details"]

    # ── Hero total times ───────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## 📊 Resultados de Predicción")

    col1, col2, col3, col4 = st.columns(4)
    gap_ac_sign = "+" if gap.gap_a_vs_c_s >= 0 else ""
    gap_cb_sign = "+" if gap.gap_c_vs_b_s >= 0 else ""
    gap_ab_sign = "+" if gap.gap_a_vs_b_s >= 0 else ""

    with col1:
        delta_color = "#EF4444" if gap.gap_a_vs_b_s > 0 else "#10B981"
        st.markdown(
            f"<div class='kl-metric-box'>"
            f"<div style='color:#0EA5E9;font-size:.75rem;font-weight:700;letter-spacing:.1em'>GARMIN (A)</div>"
            f"<div style='color:#0EA5E9;font-size:2.1rem;font-weight:800;font-family:Barlow Condensed,sans-serif'>{fmt_hms(A.total_s)}</div>"
            f"<div style='color:{delta_color};font-size:.75rem'>{gap_ab_sign}{fmt_hms(abs(gap.gap_a_vs_b_s))} vs meta</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"<div class='kl-metric-box' style='border-color:#F0A500'>"
            f"<div style='color:#F0A500;font-size:.75rem;font-weight:700;letter-spacing:.1em'>TU META (B)</div>"
            f"<div style='color:#F0A500;font-size:2.1rem;font-weight:800;font-family:Barlow Condensed,sans-serif'>{fmt_hms(B.total_s)}</div>"
            f"<div style='color:#7FB3CC;font-size:.75rem'>Objetivo deseado</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with col3:
        delta_color = "#EF4444" if gap.gap_c_vs_b_s > 0 else "#10B981"
        st.markdown(
            f"<div class='kl-metric-box'>"
            f"<div style='color:#10B981;font-size:.75rem;font-weight:700;letter-spacing:.1em'>MANUAL (C)</div>"
            f"<div style='color:#10B981;font-size:2.1rem;font-weight:800;font-family:Barlow Condensed,sans-serif'>{fmt_hms(C.total_s)}</div>"
            f"<div style='color:{delta_color};font-size:.75rem'>{gap_cb_sign}{fmt_hms(abs(gap.gap_c_vs_b_s))} vs meta</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with col4:
        disc_color = "#EF4444" if abs(gap.ftp_discrepancy_pct) > 8 else "#10B981"
        disc_sign  = "+" if gap.ftp_discrepancy_pct >= 0 else ""
        st.markdown(
            f"<div class='kl-metric-box'>"
            f"<div style='color:#A855F7;font-size:.75rem;font-weight:700;letter-spacing:.1em'>BRECHA A↔C</div>"
            f"<div style='color:{disc_color};font-size:1.3rem;font-weight:800'>{gap_ac_sign}{fmt_hms(abs(gap.gap_a_vs_c_s))}</div>"
            f"<div style='color:{disc_color};font-size:.72rem'>FTP: {disc_sign}{gap.ftp_discrepancy_pct:.1f}%</div>"
            f"<div style='color:#7FB3CC;font-size:.72rem'>Manual vs Garmin</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── Alerts ────────────────────────────────────────────────────────
    if gap.alerts:
        st.markdown("")
        for alert in gap.alerts:
            css_cls = {
                "warning": "kl-alert-warn",
                "danger":  "kl-alert-danger",
                "info":    "kl-alert-info",
                "success": "kl-alert-ok",
            }.get(alert.get("type","info"), "kl-alert-info")
            st.markdown(
                f"<div class='kl-alert {css_cls}'>{alert['msg']}</div>",
                unsafe_allow_html=True,
            )

    # ── Comparison charts ─────────────────────────────────────────────
    st.markdown("")
    col_l, col_r = st.columns([3, 2])
    with col_l:
        st.plotly_chart(_chart_comparison(preds), use_container_width=True)
    with col_r:
        st.plotly_chart(_chart_radar(preds), use_container_width=True)

    # ── Split breakdown table ─────────────────────────────────────────
    st.markdown("### Desglose por Segmento")
    sw_a, bk_a, rn_a = details["sw_a"], details["bk_a"], details["rn_a"]
    sw_c, bk_c, rn_c = details["sw_c"], details["bk_c"], details["rn_c"]

    df_splits = pd.DataFrame({
        "Segmento": ["🏊 Natación", "T1", "🚵 Ciclismo", "T2", "🏃 Carrera", "⏱ TOTAL"],
        "Garmin (A)": [
            fmt_hms(A.swim_s), fmt_hms(A.t1_s),
            fmt_hms(A.bike_s), fmt_hms(A.t2_s),
            fmt_hms(A.run_s),  fmt_hms(A.total_s),
        ],
        "Meta (B)": [
            fmt_hms(B.swim_s), fmt_hms(B.t1_s),
            fmt_hms(B.bike_s), fmt_hms(B.t2_s),
            fmt_hms(B.run_s),  fmt_hms(B.total_s),
        ],
        "Manual (C)": [
            fmt_hms(C.swim_s), fmt_hms(C.t1_s),
            fmt_hms(C.bike_s), fmt_hms(C.t2_s),
            fmt_hms(C.run_s),  fmt_hms(C.total_s),
        ],
        "Ritmo/Velocidad (C)": [
            f"{fmt_ms(sw_c['effective_pace_s_100m'])}/100m",
            "—",
            f"{bk_c['avg_speed_kmh']:.1f} km/h",
            "—",
            f"{fmt_ms(rn_c['effective_pace_s_km'])}/km",
            "—",
        ],
        "Potencia/Factor (C)": [
            f"CSS × {sw_c['factors']['wetsuit']:.2f}",
            "—",
            f"{bk_c['avg_power_w']:.0f}W (IF {bk_c['if_factor']:.2f})",
            "—",
            f"Fatiga ×{rn_c['factors']['fatigue']:.2f}",
            "—",
        ],
    })
    st.dataframe(df_splits, use_container_width=True, hide_index=True,
                  column_config={
                      "Garmin (A)":       st.column_config.TextColumn(width="small"),
                      "Meta (B)":         st.column_config.TextColumn(width="small"),
                      "Manual (C)":       st.column_config.TextColumn(width="small"),
                  })

    # ── What-If simulator ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🎛️ Simulador What-If")
    st.caption("Mueve los sliders y observa cómo cambia tu predicción de ciclismo (Curva C).")

    bp = preds["bike_params_c"]
    col_s1, col_s2, col_s3 = st.columns(3)

    with col_s1:
        new_ftp = st.slider("FTP (W)", 150, 400, int(bp.ftp_w), 5, key="wi_ftp")
    with col_s2:
        new_wt  = st.slider("Peso corporal (kg)", 45.0, 100.0, float(bp.weight_kg), 0.5, key="wi_wt")
    with col_s3:
        new_cda = st.slider("CdA (m²)", 0.18, 0.42, float(bp.cda), 0.01, key="wi_cda")

    # Compute live result
    bp_wi = BikePhysicsParams(
        ftp_w=new_ftp, weight_kg=new_wt, bike_kg=bp.bike_kg,
        cda=new_cda, crr=bp.crr,
        distance_km=bp.distance_km,
        elevation_gain_m=bp.elevation_gain_m, elevation_loss_m=bp.elevation_loss_m,
        altitude_m=bp.altitude_m, temperature_c=bp.temperature_c, wind_ms=bp.wind_ms,
        profile=bp.profile, if_factor=bp.if_factor,
    )
    wi_result  = predict_bike(bp_wi)
    base_bike  = bk_c["time_s"]
    wi_delta_s = wi_result["time_s"] - base_bike
    wi_sign    = "+" if wi_delta_s >= 0 else ""
    wi_color   = "#EF4444" if wi_delta_s > 0 else "#10B981"

    st.markdown(
        f"<div class='kl-hero' style='text-align:center'>"
        f"<span style='color:#7FB3CC;font-size:.8rem'>CICLISMO WHAT-IF</span><br>"
        f"<span style='color:#10B981;font-size:2rem;font-weight:800'>{fmt_hms(wi_result['time_s'])}</span>"
        f"&nbsp;"
        f"<span style='color:{wi_color};font-size:1rem'>"
        f"({wi_sign}{fmt_hms(abs(wi_delta_s))} vs actual)</span>"
        f"<br><span style='color:#7FB3CC;font-size:.8rem'>"
        f"{wi_result['avg_speed_kmh']:.1f} km/h · {wi_result['avg_power_w']:.0f}W"
        f"</span></div>",
        unsafe_allow_html=True,
    )

    col_wh1, col_wh2, col_wh3 = st.columns(3)
    with col_wh1:
        st.plotly_chart(_chart_whatif_ftp(bp), use_container_width=True)
    with col_wh2:
        st.plotly_chart(_chart_whatif_weight(bp), use_container_width=True)
    with col_wh3:
        st.plotly_chart(_chart_whatif_cda(bp), use_container_width=True)

    # ── Recommendations ───────────────────────────────────────────────
    if gap.recommendations:
        st.markdown("---")
        st.markdown("### 🏋️ Plan de Acción — Motor de Recomendación")
        st.caption(f"Disciplina más débil detectada: **{gap.weakest_discipline}**")

        for rec in gap.recommendations:
            priority_color = {
                "high":    "#EF4444",
                "medium":  "#F0A500",
                "success": "#10B981",
            }.get(rec.get("priority","medium"), "#7FB3CC")

            st.markdown(
                f"<div class='kl-rec' style='border-left-color:{priority_color}'>"
                f"<b style='color:{priority_color}'>{rec['category']}</b><br>"
                f"<span style='color:#B0C4D8'>{rec['msg']}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # ── Export ────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📥 Exportar Reporte")
    col_exp1, col_exp2 = st.columns(2)

    with col_exp1:
        # Build CSV report
        rows = []
        for label, result in [("Garmin_A", A), ("Meta_B", B), ("Manual_C", C)]:
            rows.append({
                "Curva": label,
                "Swim_s":  round(result.swim_s),
                "T1_s":    round(result.t1_s),
                "Bike_s":  round(result.bike_s),
                "T2_s":    round(result.t2_s),
                "Run_s":   round(result.run_s),
                "Total_s": round(result.total_s),
                "Swim_fmt":  fmt_hms(result.swim_s),
                "Bike_fmt":  fmt_hms(result.bike_s),
                "Run_fmt":   fmt_hms(result.run_s),
                "Total_fmt": fmt_hms(result.total_s),
            })
        df_export = pd.DataFrame(rows)
        csv_bytes  = df_export.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Descargar CSV — Splits",
            data=csv_bytes,
            file_name=f"kona_prediccion_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with col_exp2:
        # Build JSON report
        report = {
            "generated_at":  datetime.now().isoformat(),
            "race":          st.session_state.race.get("name") if st.session_state.race else "—",
            "garmin_A":      {"swim": fmt_hms(A.swim_s), "bike": fmt_hms(A.bike_s),
                              "run": fmt_hms(A.run_s), "total": fmt_hms(A.total_s)},
            "target_B":      {"swim": fmt_hms(B.swim_s), "bike": fmt_hms(B.bike_s),
                              "run": fmt_hms(B.run_s), "total": fmt_hms(B.total_s)},
            "manual_C":      {"swim": fmt_hms(C.swim_s), "bike": fmt_hms(C.bike_s),
                              "run": fmt_hms(C.run_s), "total": fmt_hms(C.total_s)},
            "gap_A_vs_B_min": round(gap.gap_a_vs_b_s / 60, 1),
            "gap_C_vs_B_min": round(gap.gap_c_vs_b_s / 60, 1),
            "ftp_discrepancy_pct": round(gap.ftp_discrepancy_pct, 1),
            "weakest_discipline": gap.weakest_discipline,
            "alerts_count":       len(gap.alerts),
        }
        json_bytes = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
        st.download_button(
            "⬇️ Descargar JSON — Reporte completo",
            data=json_bytes,
            file_name=f"kona_reporte_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
            use_container_width=True,
        )


# ── Main app ────────────────────────────────────────────────────────────────

def main():
    _init_state()

    # ── Header ───────────────────────────────────────────────────────────
    st.markdown(
        "<h1 style='font-family:Barlow Condensed,sans-serif;font-size:2.2rem;"
        "font-weight:800;color:#F0A500;letter-spacing:.08em;margin-bottom:0'>"
        "KONA<span style='color:#FF6535'>LABS</span> · RACE PREDICTOR"
        "</h1>"
        "<p style='color:#7FB3CC;font-size:.85rem;margin-top:.2rem'>"
        "Sistema de Predicción 3 Curvas · Garmin + Circuito + Perfil Manual"
        "</p>",
        unsafe_allow_html=True,
    )

    # ── 3 Curve tabs ─────────────────────────────────────────────────────
    tab_a, tab_b, tab_c = st.tabs([
        "🔵 Curva A — Garmin",
        "🟡 Curva B — Circuito",
        "🟢 Curva C — Perfil Manual",
    ])

    with tab_a:
        _section_curve_a()

    with tab_b:
        _section_curve_b()

    with tab_c:
        _section_curve_c()

    # ── Calculate button ──────────────────────────────────────────────────
    st.markdown("")

    def _do_calculate():
        env = {
            "temp_c":     st.session_state.b_temp,
            "humidity":   st.session_state.b_humidity,
            "wind_ms":    st.session_state.b_wind,
            "altitude_m": st.session_state.b_altitude,
        }
        try:
            preds = _run_prediction(st.session_state.race, env)
            st.session_state.predictions = preds
        except Exception as e:
            st.error(f"Error al calcular: {e}")

    # Auto-calculate on first load when default race is ready
    if st.session_state.race is not None and st.session_state.predictions is None:
        _do_calculate()

    can_calculate = st.session_state.race is not None
    col_btn, col_race_label = st.columns([3, 2])
    with col_btn:
        if st.button("⚡ CALCULAR PREDICCIÓN 3 CURVAS", type="primary",
                      disabled=not can_calculate, use_container_width=True):
            with st.spinner("Calculando predicciones con modelos físicos…"):
                _do_calculate()
    with col_race_label:
        if st.session_state.race:
            st.markdown(
                f"<div style='padding:.55rem 0;color:#7FB3CC;font-size:.85rem'>"
                f"📍 <b style='color:#F0A500'>{st.session_state.race.get('name','')}</b>"
                f" &nbsp;·&nbsp; {st.session_state.race.get('type','')}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.info("Selecciona una carrera en **Curva B**")

    # ── Results ───────────────────────────────────────────────────────────
    if st.session_state.predictions:
        _section_results(st.session_state.predictions)


if __name__ == "__main__":
    main()
