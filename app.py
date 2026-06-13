"""TriPerf — Triathlon Performance Dashboard"""

import os, sys, subprocess
from datetime import date, timedelta, datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Inject Streamlit Cloud secrets into os.environ so garminconnect can read them
try:
    for _secret_key in ("GARMIN_EMAIL", "GARMIN_PASSWORD"):
        if _secret_key not in os.environ and _secret_key in st.secrets:
            os.environ[_secret_key] = str(st.secrets[_secret_key])
except Exception:
    pass

from models.predictor import AthleteProfile, TriathlonPredictor
from utils.formulas import (
    power_zones, DISTANCES, RECOMMENDED_IF,
    caloric_expenditure_bike, caloric_expenditure_run,
    caloric_expenditure_swim, swolf_to_efficiency_rating,
)

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TriPerf",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Landing page ───────────────────────────────────────────────────────────────
if not st.session_state.get("entered", False):
    import streamlit.components.v1 as components

    st.markdown("""<style>
[data-testid="stSidebar"],[data-testid="stHeader"],[data-testid="stToolbar"],
[data-testid="stDecoration"],footer,#MainMenu { display:none !important; }
.stApp { background:#FFFFFF !important; }
.block-container { padding:0 !important; max-width:100vw !important; }
iframe { display:block !important; border:none !important; }
div[data-testid="stVerticalBlock"] > div { gap:0 !important; }
div[data-testid="column"] { padding:0 !important; }

div[data-testid="stButton"] > button {
    background:#2563EB !important; color:#FFFFFF !important;
    border:none !important; border-radius:8px !important;
    font-family:'Inter',sans-serif !important; font-size:1.05rem !important;
    font-weight:700 !important; letter-spacing:.02em !important;
    padding:16px 40px !important; width:100% !important;
    transition:background .15s !important; cursor:pointer !important;
}
div[data-testid="stButton"] > button:hover { background:#1D4ED8 !important; }
</style>""", unsafe_allow_html=True)

    # ── Hero section (nav + headline + badges) — no CTA button inside iframe ──
    _HERO_HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',sans-serif;background:#fff}
.nav{position:sticky;top:0;z-index:100;background:rgba(255,255,255,.97);border-bottom:1px solid #E5E7EB;
  padding:.9rem 5vw;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:1rem}
.logo{font-size:1.15rem;font-weight:800;color:#111827;letter-spacing:-.02em}
.logo span{color:#2563EB}
.links{display:flex;gap:2rem;font-size:.82rem;font-weight:500;color:#6B7280}
.badge{font-size:.78rem;font-weight:600;color:#2563EB;border:1.5px solid #2563EB;border-radius:5px;padding:.4rem 1rem}
.hero{background:linear-gradient(135deg,#EFF6FF 0%,#FFFFFF 60%,#F0FDF4 100%);
  padding:4rem 5vw 3.5rem;position:relative;overflow:hidden}
.bg1{position:absolute;top:-60px;right:-80px;width:500px;height:500px;
  background:radial-gradient(circle,rgba(37,99,235,.06) 0%,transparent 70%);pointer-events:none}
.bg2{position:absolute;bottom:-40px;left:10%;width:400px;height:400px;
  background:radial-gradient(circle,rgba(16,185,129,.05) 0%,transparent 70%);pointer-events:none}
.inner{max-width:720px;position:relative}
.pill{display:inline-flex;align-items:center;gap:.5rem;background:#EFF6FF;border:1px solid #BFDBFE;
  border-radius:20px;padding:.3rem .9rem;margin-bottom:1.5rem}
.dot{width:7px;height:7px;background:#2563EB;border-radius:50%;display:inline-block}
.pill-txt{font-size:.72rem;font-weight:600;color:#2563EB;letter-spacing:.05em;text-transform:uppercase}
h1{font-size:clamp(2.4rem,5.5vw,4rem);font-weight:900;color:#111827;line-height:1.08;
  margin:0 0 1.2rem;letter-spacing:-.03em}
.sub{font-size:1.05rem;color:#4B5563;line-height:1.7;max-width:520px;margin:0 0 2rem}
.badges{display:flex;flex-wrap:wrap;gap:.7rem}
.sp{display:flex;align-items:center;gap:.45rem;border-radius:5px;padding:.45rem 1rem;border:1px solid;
  font-size:.8rem;font-weight:600}
.sw{background:#F0F9FF;border-color:#BAE6FD;color:#0369A1}
.bk{background:#FFFBEB;border-color:#FDE68A;color:#92400E}
.rn{background:#F0FDF4;border-color:#BBF7D0;color:#166534}
.st{background:#FAF5FF;border-color:#E9D5FF;color:#7C3AED}
</style></head><body>
<nav class="nav">
  <div class="logo">Tri<span>Perf</span></div>
  <div class="links"><span>Plan</span><span>Train</span><span>Analyze</span><span>Predict</span></div>
  <div class="badge">Garmin Connected &#10003;</div>
</nav>
<section class="hero">
  <div class="bg1"></div><div class="bg2"></div>
  <div class="inner">
    <div class="pill"><span class="dot"></span>
      <span class="pill-txt">Garmin Connect &middot; Rafael Dutra &middot; 2026</span></div>
    <h1>Your complete<br>triathlon platform.</h1>
    <p class="sub">Built for the complete triathlete. Track every session, plan with precision,
      analyze your load, and race smarter &mdash; all connected to Garmin.</p>
    <div class="badges">
      <div class="sp sw"><span>&#127946;</span>Swimming</div>
      <div class="sp bk"><span>&#128692;</span>Cycling</div>
      <div class="sp rn"><span>&#127939;</span>Running</div>
      <div class="sp st"><span>&#127947;</span>Strength</div>
    </div>
  </div>
</section>
</body></html>"""

    # ── Bottom section (stats + pillars + features + why + footer) ─────────────
    _BOTTOM_HTML = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Inter',sans-serif;background:#fff;color:#111827}
.stats{background:#111827;padding:2rem 5vw}
.stats-inner{display:flex;flex-wrap:wrap;gap:0;justify-content:space-around;max-width:900px;margin:0 auto}
.stat{text-align:center;padding:0 2rem;border-right:1px solid rgba(255,255,255,.1)}
.stat:last-child{border-right:none}
.snum{font-size:2.4rem;font-weight:800;color:#fff;line-height:1}
.slbl{font-size:.7rem;font-weight:500;color:#9CA3AF;margin:.3rem 0 0;text-transform:uppercase;letter-spacing:.1em}
.pillars{background:#F9FAFB;padding:4rem 5vw}
.sec-title{text-align:center;margin-bottom:3rem}
.eyebrow{font-size:.72rem;font-weight:600;color:#2563EB;text-transform:uppercase;letter-spacing:.12em;margin:0 0 .6rem}
h2{font-size:2rem;font-weight:800;color:#111827;letter-spacing:-.02em}
.grid4{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1.2rem;max-width:960px;margin:0 auto}
.card{background:#fff;border:1px solid #E5E7EB;border-radius:10px;padding:1.8rem}
.ctit{font-size:1.5rem;font-weight:900;letter-spacing:-.02em;margin:0 0 .5rem}
.csub{font-size:.88rem;font-weight:600;color:#111827;margin:0 0 .5rem}
.cdesc{font-size:.8rem;color:#6B7280;line-height:1.6}
.features{background:#fff}
.frow{padding:4rem 5vw;display:flex;align-items:center;gap:4rem;flex-wrap:wrap}
.frow.alt{background:#F9FAFB;flex-direction:row-reverse}
.ftxt{flex:1;min-width:260px}
.fey{font-size:.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.12em;margin:0 0 .7rem}
h3{font-size:1.7rem;font-weight:800;color:#111827;margin:0 0 1rem;letter-spacing:-.02em}
.fp{font-size:.9rem;color:#4B5563;line-height:1.7;margin:0 0 1.2rem}
.checks{display:flex;flex-direction:column;gap:.5rem}
.chk{display:flex;align-items:center;gap:.6rem}
.chk-ico{font-weight:700}
.chk-txt{font-size:.83rem;color:#374151}
.fcard{flex:1;min-width:260px;border-radius:12px;padding:2rem;border:1px solid #E5E7EB}
.krow{display:flex;justify-content:space-between;margin-bottom:1.2rem}
.kpi{text-align:center}
.knum{font-size:1.8rem;font-weight:800}
.klbl{font-size:.65rem;color:#6B7280;margin:.2rem 0 0;text-transform:uppercase;letter-spacing:.08em}
.bwrap{background:#DBEAFE;border-radius:6px;height:6px;margin-bottom:.4rem;overflow:hidden}
.bfill{background:#2563EB;height:100%;width:68%;border-radius:6px}
.blbl{font-size:.72rem;color:#6B7280}
.slist{display:flex;flex-direction:column;gap:.7rem}
.sess{display:flex;align-items:center;justify-content:space-between;border-radius:7px;padding:.7rem .9rem;border-left:3px solid}
.sleft{display:flex;align-items:center;gap:.6rem}
.sname{font-size:.8rem;font-weight:600;color:#111827}
.sdet{font-size:.7rem;color:#6B7280}
.sdur{font-size:.72rem;font-weight:600}
.rlist{display:flex;flex-direction:column;gap:.6rem}
.race{display:flex;justify-content:space-between;align-items:center;padding:.6rem .9rem;border:1px solid #E5E7EB;border-radius:7px}
.race.hi{border:2px solid #2563EB;background:#EFF6FF}
.rname{font-size:.82rem;font-weight:600;color:#374151}
.race.hi .rname{color:#1D4ED8;font-weight:700}
.rtime{font-size:.82rem;font-weight:700;color:#2563EB}
.race.hi .rtime{color:#1D4ED8}
.why{background:#111827;padding:4rem 5vw}
.why-title{text-align:center;margin-bottom:3rem}
.why h2{color:#fff}
.why-sub{font-size:.95rem;color:#9CA3AF;max-width:500px;margin:.5rem auto 0;line-height:1.6}
.wgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1.2rem;max-width:960px;margin:0 auto}
.wcard{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);border-radius:10px;padding:1.5rem}
.wico{font-size:1.4rem;margin:0 0 .6rem}
.wttl{font-size:.9rem;font-weight:700;color:#fff;margin:0 0 .4rem}
.wdesc{font-size:.78rem;color:#9CA3AF;line-height:1.55}
footer{background:#0F172A;padding:2rem 5vw;display:flex;flex-wrap:wrap;align-items:center;
  justify-content:space-between;gap:1rem;border-top:1px solid rgba(255,255,255,.06)}
.flogo{font-size:1rem;font-weight:800;color:#fff}
.flogo span{color:#3B82F6}
.fmid{font-size:.72rem;color:#6B7280}
.fright{font-size:.72rem;color:#4B5563}
</style></head><body>

<section class="stats">
  <div class="stats-inner">
    <div class="stat"><div class="snum">240</div><div class="slbl">FTP Watts</div></div>
    <div class="stat"><div class="snum">168+</div><div class="slbl">Activities tracked</div></div>
    <div class="stat"><div class="snum">4</div><div class="slbl">Disciplines</div></div>
    <div class="stat"><div class="snum">57</div><div class="slbl">VO&#8322;Max Bike</div></div>
    <div class="stat"><div class="snum">9</div><div class="slbl">Dashboard pages</div></div>
  </div>
</section>

<section class="pillars">
  <div class="sec-title">
    <p class="eyebrow">All-in-one, for the complete triathlete</p>
    <h2>Everything you need. Nothing you don't.</h2>
  </div>
  <div class="grid4">
    <div class="card" style="border-top:3px solid #2563EB"><p class="ctit" style="color:#2563EB">PLAN.</p>
      <p class="csub">Structured training plans</p>
      <p class="cdesc">Coach uploads sessions by discipline. Planned vs actual comparison built-in.</p></div>
    <div class="card" style="border-top:3px solid #10B981"><p class="ctit" style="color:#10B981">TRAIN.</p>
      <p class="csub">Garmin-connected. Always in sync.</p>
      <p class="cdesc">Every session auto-synced. Swim, bike, run, strength &mdash; all in one place.</p></div>
    <div class="card" style="border-top:3px solid #F59E0B"><p class="ctit" style="color:#F59E0B">ANALYZE.</p>
      <p class="csub">Real progress. No guesswork.</p>
      <p class="cdesc">CTL, ATL, TSB, ACWR, power zones, pace zones &mdash; science-backed metrics.</p></div>
    <div class="card" style="border-top:3px solid #A855F7"><p class="ctit" style="color:#A855F7">PREDICT.</p>
      <p class="csub">Race ready. Every time.</p>
      <p class="cdesc">Physics-based race predictions for Sprint, Olympic, 70.3, and Ironman.</p></div>
  </div>
</section>

<section class="features">
  <div class="frow">
    <div class="ftxt">
      <p class="fey" style="color:#2563EB">Training Load</p>
      <h3>Real progress.<br>No guesswork.</h3>
      <p class="fp">Track your fitness with Coggan's PMC model. CTL tells you your fitness level,
        ATL shows your fatigue, and TSB reveals your form. Know exactly when you're ready to race.</p>
      <div class="checks">
        <div class="chk"><span class="chk-ico" style="color:#2563EB">&#10003;</span><span class="chk-txt">Performance Management Chart (90 days)</span></div>
        <div class="chk"><span class="chk-ico" style="color:#2563EB">&#10003;</span><span class="chk-txt">ACWR injury risk monitoring</span></div>
        <div class="chk"><span class="chk-ico" style="color:#2563EB">&#10003;</span><span class="chk-txt">Weekly TSS by discipline</span></div>
      </div>
    </div>
    <div class="fcard" style="background:linear-gradient(135deg,#EFF6FF,#F0FDF4)">
      <div class="krow">
        <div class="kpi"><div class="knum" style="color:#2563EB">55</div><div class="klbl">CTL</div></div>
        <div class="kpi"><div class="knum" style="color:#EF4444">62</div><div class="klbl">ATL</div></div>
        <div class="kpi"><div class="knum" style="color:#8B5CF6">-7</div><div class="klbl">TSB</div></div>
        <div class="kpi"><div class="knum" style="color:#F59E0B">1.13</div><div class="klbl">ACWR</div></div>
      </div>
      <div class="bwrap"><div class="bfill"></div></div>
      <p class="blbl">Training Phase &mdash; building fitness</p>
    </div>
  </div>
  <div class="frow alt">
    <div class="ftxt">
      <p class="fey" style="color:#10B981">Training Plan</p>
      <h3>Expertise.<br>No guesswork.</h3>
      <p class="fp">Coaches upload structured sessions for each discipline. Athletes train with
        purpose. Compare planned vs actual automatically &mdash; see what's working.</p>
      <div class="checks">
        <div class="chk"><span class="chk-ico" style="color:#10B981">&#10003;</span><span class="chk-txt">Sessions for Swim &middot; Bike &middot; Run &middot; Strength</span></div>
        <div class="chk"><span class="chk-ico" style="color:#10B981">&#10003;</span><span class="chk-txt">Planned vs actual comparison</span></div>
        <div class="chk"><span class="chk-ico" style="color:#10B981">&#10003;</span><span class="chk-txt">Weekly calendar view</span></div>
      </div>
    </div>
    <div class="fcard" style="background:#fff">
      <p style="font-size:.7rem;font-weight:600;color:#6B7280;text-transform:uppercase;letter-spacing:.1em;margin:0 0 1rem">Upcoming sessions</p>
      <div class="slist">
        <div class="sess" style="background:#EFF6FF;border-color:#06B6D4">
          <div class="sleft"><span>&#127946;</span><div><p class="sname">CSS Threshold</p><p class="sdet">4x400m on 20s rest</p></div></div>
          <span class="sdur" style="color:#2563EB">60 min</span></div>
        <div class="sess" style="background:#FFFBEB;border-color:#F59E0B">
          <div class="sleft"><span>&#128692;</span><div><p class="sname">FTP Intervals</p><p class="sdet">3x10min @ 240W</p></div></div>
          <span class="sdur" style="color:#D97706">90 min</span></div>
        <div class="sess" style="background:#F0FDF4;border-color:#10B981">
          <div class="sleft"><span>&#127939;</span><div><p class="sname">Tempo Run</p><p class="sdet">10km @ 4:20/km</p></div></div>
          <span class="sdur" style="color:#059669">50 min</span></div>
      </div>
    </div>
  </div>
  <div class="frow">
    <div class="ftxt">
      <p class="fey" style="color:#A855F7">Race Predictor</p>
      <h3>Race ready.<br>Every time.</h3>
      <p class="fp">Physics-based race time predictions for all triathlon distances.
        Riegel model for swim and run, Newton-Raphson bike physics.</p>
      <div class="checks">
        <div class="chk"><span class="chk-ico" style="color:#A855F7">&#10003;</span><span class="chk-txt">Sprint &middot; Olympic &middot; 70.3 &middot; Ironman</span></div>
        <div class="chk"><span class="chk-ico" style="color:#A855F7">&#10003;</span><span class="chk-txt">FTP sensitivity analysis</span></div>
        <div class="chk"><span class="chk-ico" style="color:#A855F7">&#10003;</span><span class="chk-txt">Brick run fatigue simulator</span></div>
      </div>
    </div>
    <div class="fcard" style="background:#fff">
      <p style="font-size:.7rem;font-weight:600;color:#6B7280;text-transform:uppercase;letter-spacing:.1em;margin:0 0 1rem">Race predictions &middot; FTP 240W</p>
      <div class="rlist">
        <div class="race"><span class="rname">Sprint</span><span class="rtime">1:02:30</span></div>
        <div class="race"><span class="rname">Olympic</span><span class="rtime">2:11:00</span></div>
        <div class="race hi"><span class="rname">70.3</span><span class="rtime">4:48:00</span></div>
        <div class="race"><span class="rname">Ironman</span><span class="rtime">10:30:00</span></div>
      </div>
    </div>
  </div>
</section>

<section class="why">
  <div class="why-title">
    <h2>Why TriPerf?</h2>
    <p class="why-sub">Everything TrainingPeaks does &mdash; built specifically for you, connected to your Garmin data.</p>
  </div>
  <div class="wgrid">
    <div class="wcard"><p class="wico">&#9889;</p><p class="wttl">Garmin native</p>
      <p class="wdesc">Direct sync from Garmin Connect. Real data, no manual entry.</p></div>
    <div class="wcard"><p class="wico">&#128202;</p><p class="wttl">Science-backed</p>
      <p class="wdesc">Coggan PMC, Riegel model, Newton-Raphson bike physics, Laursen fatigue.</p></div>
    <div class="wcard"><p class="wico">&#127947;</p><p class="wttl">4 disciplines</p>
      <p class="wdesc">Swim, bike, run, and strength &mdash; complete triathlete tracking.</p></div>
    <div class="wcard"><p class="wico">&#127919;</p><p class="wttl">Coach + athlete</p>
      <p class="wdesc">Plan sessions, track execution, compare planned vs actual automatically.</p></div>
  </div>
</section>

<footer>
  <span class="flogo">Tri<span>Perf</span></span>
  <span class="fmid">Powered by Garmin Connect &middot; Streamlit &middot; Python &middot; Plotly</span>
  <span class="fright">2026 &middot; Rafael Dutra &middot; Ironman Triathlete</span>
</footer>
</body></html>"""

    components.html(_HERO_HTML, height=490, scrolling=False)
    _c1, _c2, _c3 = st.columns([2, 3, 2])
    with _c2:
        if st.button("⚡  Enter Dashboard  →", use_container_width=True, key="cta_enter"):
            st.session_state.entered = True
            st.rerun()
    components.html(_BOTTOM_HTML, height=2700, scrolling=False)
    st.stop()

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Ocultar barra superior de Streamlit */
[data-testid="stHeader"]     { display: none !important; }
[data-testid="stToolbar"]    { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }
#MainMenu, footer            { display: none !important; }

/* Contenido principal */
.block-container { padding: 1.5rem 2rem 3rem !important; max-width: 100% !important; }

/* Sidebar oscuro */
[data-testid="stSidebar"] {
    background: #0F172A !important;
    border-right: 1px solid #1E293B !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] div  { color: #CBD5E1 !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3   { color: #F1F5F9 !important; }

/* KPI cards */
[data-testid="metric-container"] {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 16px 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

/* Charts */
[data-testid="stPlotlyChart"] > div {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 4px;
}

/* Tables */
[data-testid="stDataFrame"] {
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    overflow: hidden;
}

/* Expanders */
[data-testid="stExpander"] {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)

# ── Constantes de color ────────────────────────────────────────────────────────
CARD = "#FFFFFF"
TEXT2 = "#64748B"
ACCENT = "#3B82F6"
COL_CTL  = "#3B82F6"
COL_ATL  = "#EF4444"
COL_TSB  = "#8B5CF6"
COL_SWIM = "#06B6D4"
COL_BIKE = "#F59E0B"
COL_RUN  = "#10B981"
COL_STR  = "#A855F7"
SPORT_COLORS = {"swim": COL_SWIM, "bike": COL_BIKE, "run": COL_RUN, "str": COL_STR}
SPORT_ICONS  = {"swim": "🏊", "bike": "🚴", "run": "🏃", "str": "🏋️"}
RACE_LABELS  = {"sprint": "Sprint", "olympic": "Olympic", "703": "70.3", "ironman": "Ironman"}

# ── Helpers ────────────────────────────────────────────────────────────────────
def _parse_pace(s, default=260.0):
    try:
        p = s.strip().split(":")
        return int(p[0]) * 60 + int(p[1])
    except:
        return default

def _fmt_pace(sec):
    return f"{int(sec)//60}:{int(sec)%60:02d}"

def _fmt_dur(sec):
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"

def section(title, sub=""):
    st.caption(f"**{title.upper()}**{'  ·  ' + sub if sub else ''}")

# ── KPI helper functions ────────────────────────────────────────────────────────

def _readiness_score(tsb: float, hrv_df: pd.DataFrame, sleep_df: pd.DataFrame):
    """Daily Readiness Score 0–100. Returns (score, label, color, components)."""
    # TSB component: optimal range -5 to +20
    if -5 <= tsb <= 20:
        tsb_s = 85 + min(15, (tsb + 5) / 25 * 15)
    elif -20 <= tsb < -5:
        tsb_s = 50 + (tsb + 20) / 15 * 35
    elif 20 < tsb <= 30:
        tsb_s = 85 - (tsb - 20) * 2
    else:
        tsb_s = max(0, 50 + max(-30, min(-20, tsb)) / 30 * 50)
    tsb_s = round(min(100, max(0, tsb_s)))

    # HRV component: last night vs 7-day avg
    hrv_s = 70
    if not hrv_df.empty and "hrv_last_night" in hrv_df.columns:
        last7 = hrv_df.dropna(subset=["hrv_last_night"]).tail(7)
        if len(last7) >= 2:
            ratio = last7["hrv_last_night"].iloc[-1] / (last7["hrv_last_night"].mean() or 1)
            hrv_s = 95 if ratio >= 1.05 else 80 if ratio >= 0.97 else 60 if ratio >= 0.90 else max(20, int(ratio * 70))

    # Sleep component: last 3-night average score
    sleep_s = 70
    if not sleep_df.empty and "sleep_score" in sleep_df.columns:
        avg = sleep_df.dropna(subset=["sleep_score"]).tail(3)["sleep_score"].mean()
        if pd.notna(avg):
            sleep_s = round(float(avg))

    total = round(min(100, max(0, 0.40 * tsb_s + 0.35 * hrv_s + 0.25 * sleep_s)))
    if total >= 80:   lbl, col = "Ready to Train Hard", "#10B981"
    elif total >= 62: lbl, col = "Moderate Load OK",   "#3B82F6"
    elif total >= 44: lbl, col = "Light Session Only",  "#F59E0B"
    else:             lbl, col = "Rest / Recovery",     "#EF4444"
    return total, lbl, col, {"TSB": tsb_s, "HRV": hrv_s, "Sleep": sleep_s}


def _ef_bike(df: pd.DataFrame) -> pd.DataFrame:
    """Efficiency Factor per bike session: NP (or Avg Power) / HR."""
    d = df.copy()
    pwr = d["norm_power"].fillna(d["avg_power"]) if "avg_power" in d.columns else d.get("norm_power", pd.Series(dtype=float))
    hr  = d.get("avg_hr", pd.Series(dtype=float))
    mask = pwr.notna() & hr.notna() & (hr > 50) & (pwr > 0)
    d.loc[mask, "ef"] = (pwr[mask] / hr[mask]).round(3)
    return d[mask][["date", "ef"]].sort_values("date").copy()


def _ef_run(df: pd.DataFrame) -> pd.DataFrame:
    """Efficiency Factor per run session: speed (m/s) / HR."""
    d = df.copy()
    pace = d.get("avg_pace_sec_km", pd.Series(dtype=float))
    hr   = d.get("avg_hr", pd.Series(dtype=float))
    mask = pace.notna() & hr.notna() & (hr > 50) & (pace > 0)
    d.loc[mask, "ef"] = ((1000.0 / pace[mask]) / hr[mask]).round(4)
    return d[mask][["date", "ef"]].sort_values("date").copy()


def _race_readiness(tsb: float, hrv_df: pd.DataFrame, sleep_df: pd.DataFrame,
                    compliance_pct: float):
    """Race Readiness Index 0–100. Returns (score, label, color)."""
    # TSB: ideal +5 to +15 before race
    if 5 <= tsb <= 15:     tsb_s = 100
    elif 0 <= tsb < 5:     tsb_s = 80
    elif 15 < tsb <= 25:   tsb_s = 85
    elif -10 <= tsb < 0:   tsb_s = 60
    else:                  tsb_s = 25

    # HRV trend
    hrv_s = 70
    if not hrv_df.empty and "hrv_last_night" in hrv_df.columns:
        last7 = hrv_df.dropna(subset=["hrv_last_night"]).tail(7)
        if len(last7) >= 3:
            slope = last7["hrv_last_night"].iloc[-1] - last7["hrv_last_night"].iloc[0]
            hrv_s = 90 if slope > 0 else 75 if abs(slope) < 2 else 45

    # Sleep quality
    sleep_s = 70
    if not sleep_df.empty and "sleep_score" in sleep_df.columns:
        avg = sleep_df.dropna(subset=["sleep_score"]).tail(7)["sleep_score"].mean()
        if pd.notna(avg):
            sleep_s = 100 if avg >= 80 else 75 if avg >= 65 else 50 if avg >= 50 else 25

    comp_s = min(100, round(compliance_pct))

    total = round(min(100, max(0, 0.30*tsb_s + 0.20*hrv_s + 0.15*sleep_s + 0.25*comp_s + 0.10*75)))
    if total >= 85:   lbl, col = "🏆 Peak Race Readiness",  "#10B981"
    elif total >= 70: lbl, col = "✓ Ready to Race",         "#3B82F6"
    elif total >= 50: lbl, col = "⚡ Building Fitness",     "#F59E0B"
    else:             lbl, col = "🔄 Recovery Phase",       "#EF4444"
    return total, lbl, col

def _load_blood_tests() -> dict:
    import json as _json
    p = DATA_DIR / "blood_tests.json"
    if not p.exists():
        return {}
    return _json.loads(p.read_text(encoding="utf-8"))

# ── Training Detail helpers ────────────────────────────────────────────────────

def _gen_activity_route(distance_m: float, sport: str, seed: int = 42):
    """Generate a simulated GPS loop route as lat/lon lists."""
    import numpy as _np
    rng  = _np.random.default_rng(seed)
    lat0, lon0 = 38.72, -9.14           # Lisbon area; override as needed
    km   = max(1.0, float(distance_m) / 1000.0)
    r_lat = (km / (2 * 3.14159)) / 111.0
    r_lon = r_lat / max(0.01, float(_np.cos(_np.radians(lat0))))
    n    = 100
    ang  = _np.linspace(0, 2 * _np.pi, n + 1)
    # Cumulative noise gives a more realistic irregular loop
    noise_l = rng.normal(0, 0.14, n + 1).cumsum() * r_lat * 0.11
    noise_o = rng.normal(0, r_lon * 0.12, n + 1)
    lats = (lat0 + r_lat * _np.sin(ang) + noise_l).tolist()
    lons = (lon0 + r_lon * _np.cos(ang) + noise_o).tolist()
    return lats, lons


def _gen_timeseries_td(dur_sec: float, sport: str,
                       avg_pwr=None, avg_hr=None, max_hr=None, avg_pace=None):
    """Simulated per-30s time-series scaled to real activity stats."""
    import numpy as _np
    n   = min(200, max(40, int(float(dur_sec) / 30)))
    rng = _np.random.default_rng(17)
    t   = _np.linspace(0, 1, n)

    warm = _np.clip(t / 0.12, 0, 1)
    cool = _np.clip((1.0 - t) / 0.10, 0, 1)
    blk1 = _np.clip(_np.sin(_np.pi * _np.clip((t - 0.20) / 0.22, 0, 1)), 0, 1)
    blk2 = _np.clip(_np.sin(_np.pi * _np.clip((t - 0.62) / 0.22, 0, 1)), 0, 1)
    ci   = warm * cool * (0.65 + _np.maximum(blk1, blk2) * 0.35) + rng.normal(0, 0.025, n)
    ci   = _np.clip(ci, 0, 1)

    # Power (bike only)
    if sport == "bike" and avg_pwr and float(avg_pwr) > 0:
        pw = float(avg_pwr) * 0.78 + ci * float(avg_pwr) * 0.74 + rng.normal(0, 18, n)
        power = pw.clip(0).round(0).astype(int).tolist()
    elif sport == "bike":
        power = (140 + ci * 145 + rng.normal(0, 20, n)).clip(0).round(0).astype(int).tolist()
    else:
        power = None

    # HR
    hr_base = float(avg_hr or 135) * 0.78
    hr_peak = float(max_hr or (float(avg_hr or 155) * 1.10))
    hr_list = (hr_base + ci * (hr_peak - hr_base) + rng.normal(0, 3, n))\
              .clip(50, 220).round(0).astype(int).tolist()

    # Altitude (m)
    ag  = 420 if sport == "bike" else 160 if sport == "run" else 0
    alt = (80 + _np.sin(t * _np.pi) * ag * 0.68
           + _np.sin(t * _np.pi * 4) * ag * 0.12
           + rng.normal(0, 5, n)).clip(0)
    altitude = alt.round(0).astype(int).tolist()

    # Speed (km/h)
    if sport == "bike":
        bs  = 3600.0 / float(avg_pace) if avg_pace and float(avg_pace) > 0 else 36.0
        spd = (bs * (0.62 + ci * 0.58) + rng.normal(0, 1.8, n)).clip(5)
    elif sport == "run":
        bs  = 3600.0 / float(avg_pace) if avg_pace and float(avg_pace) > 0 else 12.0
        spd = (bs * (0.88 + ci * 0.22) + rng.normal(0, 0.35, n)).clip(3)
    elif sport == "swim":
        spd = (3.2 + ci * 1.5 + rng.normal(0, 0.12, n)).clip(1)
    else:
        spd = (8.0 + ci * 6.0 + rng.normal(0, 0.8, n)).clip(0)
    speed = spd.round(1).tolist()

    # Time labels (MM:SS or H:MM:SS)
    labels = []
    for i in range(n):
        s = int(i * float(dur_sec) / n)
        labels.append(f"{s//3600}:{(s%3600)//60:02d}:{s%60:02d}"
                      if dur_sec >= 3600 else f"{s//60:02d}:{s%60:02d}")

    return {"time": labels, "power": power, "hr": hr_list,
            "altitude": altitude, "speed": speed}


def chart(fig, height=300, margin=None):
    m = margin or dict(l=4, r=4, t=12, b=4)
    fig.update_layout(
        height=height, template="plotly_white", margin=m,
        plot_bgcolor=CARD, paper_bgcolor=CARD,
        font=dict(family="Inter, sans-serif", size=11, color=TEXT2),
        legend=dict(font_size=11, bgcolor="rgba(0,0,0,0)", orientation="h", y=1.06),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#F1F5F9", tickfont_size=10, zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="#F1F5F9", tickfont_size=10, zeroline=False)
    return fig

# ── Data & Profile ────────────────────────────────────────────────────────────
DATA_DIR    = Path(__file__).parent / "data"
PROFILE_PATH = DATA_DIR / "athlete_profile.json"

_PROFILE_DEFAULTS = {
    "name":           "Rafael Dutra",
    "age":            35,
    "weight_kg":      62.0,
    "height_cm":      175,
    "ftp_w":          240,
    "threshold_run":  "4:20",
    "css_swim":       "1:50",
    "vo2max_run":     55.0,
    "vo2max_bike":    57.0,
    "lthr":           168,
    "garmin_email":   "",
    "target_race":    "703",
    "target_date":    "",
    "notes":          "",
}

def load_profile() -> dict:
    import json as _json
    if PROFILE_PATH.exists():
        try:
            data = _json.loads(PROFILE_PATH.read_text())
            return {**_PROFILE_DEFAULTS, **data}
        except Exception:
            pass
    return _PROFILE_DEFAULTS.copy()

def save_profile(data: dict):
    import json as _json
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(_json.dumps(data, indent=2, ensure_ascii=False))

@st.cache_data(ttl=300)
def load_data():
    def _read(name):
        p = DATA_DIR / f"{name}.csv"
        if p.exists() and p.stat().st_size > 10:
            return pd.read_csv(p, parse_dates=["date"])
        return pd.DataFrame()

    df_load = _read("training_load")
    df_act  = _read("activities")
    df_slp  = _read("sleep")
    df_hrv  = _read("hrv")

    if not df_act.empty and "sport" in df_act.columns:
        df_act = (df_act[df_act["sport"].isin(["swim", "bike", "run", "str"])]
                  .sort_values("date", ascending=False)
                  .reset_index(drop=True))
    return df_load, df_act, df_slp, df_hrv

def last_sync():
    p = DATA_DIR / "activities.csv"
    if p.exists():
        return datetime.fromtimestamp(p.stat().st_mtime).strftime("%b %d %H:%M")
    return "—"

# ── Load athlete profile ───────────────────────────────────────────────────────
_prof  = load_profile()
ftp    = int(_prof["ftp_w"])
t_run  = str(_prof["threshold_run"])
t_swim = str(_prof["css_swim"])
weight = float(_prof["weight_kg"])
vo2r   = float(_prof["vo2max_run"])
vo2b   = float(_prof["vo2max_bike"])

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚡ TriPerf")
    st.caption("Triathlon Performance Dashboard")
    st.markdown("---")

    page = st.radio(
        "nav",
        ["👤 Athlete Profile", "📋 Training Plan", "📊 Dashboard",
         "📈 Training Load", "🏊 Swimming", "🚴 Cycling",
         "🏃 Running", "🍎 Nutrition", "🏆 Race Predictor",
         "🩸 Blood Labs", "🗺️ Training Detail"],
        label_visibility="collapsed",
    )

    st.markdown("---")

    # Compact athlete card (read-only)
    st.caption("ATHLETE")
    st.markdown(f"**{_prof['name']}**")
    st.caption(
        f"FTP {ftp}W  ·  {weight:.0f} kg\n\n"
        f"Run {t_run}/km  ·  Swim {t_swim}/100m\n\n"
        f"VO₂ run {vo2r:.0f}  ·  bike {vo2b:.0f}"
    )

    st.markdown("---")
    if st.button("🔄 Sync Garmin", use_container_width=True):
        with st.spinner("Syncing Garmin…"):
            try:
                python = sys.executable
                res = subprocess.run(
                    [python, "sync_garmin.py"],
                    capture_output=True, text=True, timeout=180,
                    cwd=str(Path(__file__).parent),
                )
                if res.returncode == 0:
                    st.cache_data.clear()
                    st.success("Sync complete!")
                    st.rerun()
                else:
                    st.error(res.stderr[-300:] or "Sync error")
            except Exception as e:
                st.error(str(e))

    st.markdown(" ")
    st.caption(f"Last sync: {last_sync()}")

# ── Setup ──────────────────────────────────────────────────────────────────────
profile = AthleteProfile(
    ftp_w=ftp,
    threshold_run_sec_km=_parse_pace(t_run),
    threshold_swim_sec_100m=_parse_pace(t_swim, 110.0),
    vo2max_run=vo2r, vo2max_bike=vo2b, weight_kg=weight,
)
predictor = TriathlonPredictor(profile, riegel_weight=0.35)
df_load, df_act, df_sleep, df_hrv = load_data()
has_data = not df_act.empty

# ── Page header ────────────────────────────────────────────────────────────────
PAGE_TITLES = {
    "📊 Dashboard": "Performance Dashboard",
    "📋 Training Plan": "Training Plan",
    "📈 Training Load": "Training Load",
    "🏊 Swimming": "Swimming",
    "🚴 Cycling": "Cycling",
    "🏃 Running": "Running",
    "🍎 Nutrition": "Nutrition",
    "👤 Athlete Profile": "Athlete Profile",
    "🏆 Race Predictor": "Race Predictor",
    "🩸 Blood Labs":       "Blood Labs · Biochemistry",
    "🗺️ Training Detail": "Training Detail · Activity Analysis",
}
col_h, col_s = st.columns([5, 1])
col_h.markdown(f"## {PAGE_TITLES.get(page, page)}")
col_h.caption(f"Last sync: {last_sync()}  ·  {len(df_act)} activities")
if has_data:
    col_s.success("● Live")
else:
    col_s.warning("● No data")
st.divider()


# ── Training Plan helpers ──────────────────────────────────────────────────────
PLAN_PATH = DATA_DIR / "training_plan.csv"
PLAN_COLS  = ["id","date","sport","workout_type","description",
              "target_duration_min","target_distance_km","target_intensity",
              "target_zones","notes"]

WORKOUT_TYPES = {
    "swim": ["Base / Endurance","CSS Threshold","Speed / Intervals","Open Water","Recovery"],
    "bike": ["Base / Z2","FTP Intervals","VO2Max","Race Pace","Long Ride","Recovery"],
    "run":  ["Easy / Z2","Tempo","Intervals","Long Run","Race Pace","Brick Run","Recovery"],
    "str":  ["Full Body","Upper Body","Lower Body","Core","Power / Olympic","Mobility","Circuit"],
}
INTENSITY_OPTS = ["Z1 Recovery","Z2 Base","Z3 Tempo","Z4 Threshold","Z5 VO2Max","Race Pace"]
INTENSITY_STR  = ["Light (RPE 4–5)","Moderate (RPE 6–7)","Heavy (RPE 8–9)","Max Effort (RPE 10)"]

def _load_plan() -> pd.DataFrame:
    if PLAN_PATH.exists() and PLAN_PATH.stat().st_size > 5:
        df = pd.read_csv(PLAN_PATH, parse_dates=["date"])
        for c in PLAN_COLS:
            if c not in df.columns:
                df[c] = None
        return df
    return pd.DataFrame(columns=PLAN_COLS)

def _save_plan(df: pd.DataFrame):
    df.to_csv(PLAN_PATH, index=False)

df_plan = _load_plan()

def _match_actual(plan_row: pd.Series, df_act: pd.DataFrame) -> pd.Series | None:
    """Return actual activity matching the planned sport and date (±1 day)."""
    if df_act.empty:
        return None
    d = pd.Timestamp(plan_row["date"])
    mask = (df_act["sport"] == plan_row["sport"]) & \
           (df_act["date"] >= d - timedelta(days=1)) & \
           (df_act["date"] <= d + timedelta(days=1))
    matched = df_act[mask]
    return matched.iloc[0] if not matched.empty else None

# ══════════════════════════════════════════════════════════════════════════════
# 📋 TRAINING PLAN
# ══════════════════════════════════════════════════════════════════════════════
if page == "📋 Training Plan":

    # ── Tabs: Agregar / Ver plan / Comparar ───────────────────────────────────
    tab_add, tab_week, tab_compare = st.tabs(
        ["➕ Add Workout", "📅 Weekly View", "📊 Planned vs Actual"]
    )

    # ──────────────────────────────────────────────────────────────────────────
    with tab_add:
        section("New Workout", "Fill in the targets for the session")
        st.markdown(" ")

        f1, f2, f3 = st.columns(3)
        w_date  = f1.date_input("Date", value=date.today() + timedelta(days=1))
        _disc_labels = {"swim":"🏊 Swim","bike":"🚴 Bike","run":"🏃 Run","str":"🏋️ Strength"}
        w_sport = f2.selectbox("Discipline", ["swim","bike","run","str"],
                               format_func=lambda s: _disc_labels[s])
        w_type  = f3.selectbox("Workout type", WORKOUT_TYPES[w_sport])

        f4, f5, f6 = st.columns(3)
        w_dur  = f4.number_input("Duration (min)", 0, 600, 60, 5)
        if w_sport != "str":
            w_dist  = f5.number_input("Distance (km)", 0.0, 300.0, 0.0, 0.5)
            w_inten = f6.selectbox("Intensity / Target zone", INTENSITY_OPTS)
        else:
            w_sets  = f5.number_input("Sets / Exercises", 0, 50, 0, 1)
            w_inten = f6.selectbox("Intensity (RPE)", INTENSITY_STR)
            w_dist  = 0.0

        # Zone targets según disciplina
        st.markdown(" ")
        z1, z2 = st.columns(2)
        if w_sport == "bike":
            w_zones = z1.text_input("Power target (W or %FTP)", placeholder="e.g.  240W  or  88–95%FTP")
            w_desc  = z2.text_input("Description", placeholder="e.g.  3×10min @ threshold")
        elif w_sport == "run":
            w_zones = z1.text_input("Pace target (/km)", placeholder="e.g.  4:10–4:30/km")
            w_desc  = z2.text_input("Description", placeholder="e.g.  10km tempo progression")
        elif w_sport == "str":
            w_zones = z1.text_input("Key exercises", placeholder="e.g.  Squat 4×6 · Deadlift 3×5 · Pull-ups")
            w_desc  = z2.text_input("Focus / Goal", placeholder="e.g.  Lower body strength, pre-race activation")
        else:
            w_zones = z1.text_input("Pace target (/100m)", placeholder="e.g.  1:45–1:55/100m")
            w_desc  = z2.text_input("Description", placeholder="e.g.  4×400m on 20s rest")

        w_notes = st.text_area("Coach notes (optional)", height=80, placeholder="Technique cues, RPE targets, equipment…")

        st.markdown(" ")
        if st.button("💾  Save Workout", use_container_width=False):
            new_id  = int(df_plan["id"].max() + 1) if not df_plan.empty else 1
            new_row = pd.DataFrame([{
                "id":                   new_id,
                "date":                 pd.Timestamp(w_date),
                "sport":                w_sport,
                "workout_type":         w_type,
                "description":          w_desc,
                "target_duration_min":  w_dur if w_dur > 0 else None,
                "target_distance_km":   w_dist if w_dist > 0 else None,
                "target_intensity":     w_inten,
                "target_zones":         w_zones,
                "notes":                w_notes,
            }])
            df_plan = pd.concat([df_plan, new_row], ignore_index=True)
            _save_plan(df_plan)
            st.success(f"Workout saved — {w_sport.upper()} on {w_date}")
            st.rerun()

    # ──────────────────────────────────────────────────────────────────────────
    with tab_week:
        section("Upcoming Plan", "Next 14 days")

        if df_plan.empty:
            st.info("No workouts planned yet. Use the **Add Workout** tab to create sessions.")
        else:
            today_ts = pd.Timestamp.today().normalize()
            window   = df_plan[df_plan["date"] >= today_ts].sort_values("date")

            if window.empty:
                st.info("No upcoming workouts. Add new sessions in the **Add Workout** tab.")
            else:
                sport_icon = {"swim":"🏊","bike":"🚴","run":"🏃","str":"🏋️"}
                sport_col  = {"swim":COL_SWIM,"bike":COL_BIKE,"run":COL_RUN,"str":COL_STR}

                for _, row in window.iterrows():
                    sp   = row["sport"]
                    icon = sport_icon.get(sp,"🔵")
                    col  = sport_col.get(sp,"#94A3B8")
                    dt   = pd.Timestamp(row["date"])
                    label= "Tomorrow" if dt.date() == date.today()+timedelta(1) else dt.strftime("%a %b %d")

                    with st.container():
                        ca, cb, cc, cd, ce = st.columns([1.2, 2, 2, 2, 1])
                        ca.markdown(f"**{label}**")
                        cb.markdown(f"{icon} **{row['workout_type']}**")

                        parts = []
                        if pd.notna(row.get("target_duration_min")) and row["target_duration_min"]:
                            parts.append(f"{int(row['target_duration_min'])} min")
                        if pd.notna(row.get("target_distance_km")) and row["target_distance_km"]:
                            parts.append(f"{row['target_distance_km']:.1f} km")
                        cc.caption("  ·  ".join(parts) if parts else "—")

                        cd.caption(str(row.get("target_zones","")) or str(row.get("target_intensity","")) or "—")

                        if ce.button("🗑", key=f"del_{row['id']}", help="Delete"):
                            df_plan = df_plan[df_plan["id"] != row["id"]]
                            _save_plan(df_plan)
                            st.rerun()
                    st.divider()

            # Full plan table
            with st.expander("📋 Full plan (all workouts)", expanded=False):
                if not df_plan.empty:
                    display = df_plan.copy()
                    display["date"] = display["date"].dt.strftime("%Y-%m-%d")
                    display["sport"] = display["sport"].map({"swim":"🏊 Swim","bike":"🚴 Bike","run":"🏃 Run"})
                    st.dataframe(
                        display[["date","sport","workout_type","target_duration_min",
                                  "target_distance_km","target_zones","description","notes"]],
                        hide_index=True, use_container_width=True,
                        column_config={
                            "date":                 st.column_config.TextColumn("Date",     width=90),
                            "sport":                st.column_config.TextColumn("Sport",    width=100),
                            "workout_type":         st.column_config.TextColumn("Type",     width=150),
                            "target_duration_min":  st.column_config.NumberColumn("Min",   width=60),
                            "target_distance_km":   st.column_config.NumberColumn("Km",    width=60),
                            "target_zones":         st.column_config.TextColumn("Target",  width=150),
                            "description":          st.column_config.TextColumn("Description", width=200),
                            "notes":                st.column_config.TextColumn("Notes",   width=200),
                        }
                    )

    # ──────────────────────────────────────────────────────────────────────────
    with tab_compare:
        section("Planned vs Actual", "Sessions completed in the last 30 days")

        past = df_plan[df_plan["date"] < pd.Timestamp.today()].sort_values("date", ascending=False)

        if past.empty:
            st.info("No past planned sessions yet.")
        elif df_act.empty:
            st.info("No Garmin activity data. Sync from the sidebar.")
        else:
            rows_cmp = []
            for _, p in past.head(20).iterrows():
                actual = _match_actual(p, df_act)
                sp = p["sport"]

                planned_dur  = p.get("target_duration_min")
                planned_dist = p.get("target_distance_km")

                if actual is not None:
                    act_dur  = round(actual["duration_sec"] / 60, 1)
                    act_dist = round(actual["distance_m"]   / 1000, 2)
                    status   = "✅ Done"

                    # Delta
                    dur_delta  = ""
                    dist_delta = ""
                    if pd.notna(planned_dur) and planned_dur:
                        diff = act_dur - float(planned_dur)
                        dur_delta = f"{diff:+.0f} min"
                    if pd.notna(planned_dist) and planned_dist:
                        diff = act_dist - float(planned_dist)
                        dist_delta = f"{diff:+.2f} km"

                    if sp == "bike":
                        act_detail = f"{actual.get('norm_power') or actual.get('avg_power') or 0:.0f}W NP"
                    elif sp == "run":
                        act_detail = (_fmt_pace(actual["avg_pace_sec_km"]) + "/km"
                                      if actual.get("avg_pace_sec_km") else "—")
                    else:
                        act_detail = f"{act_dist:.2f} km"
                else:
                    act_dur = act_dist = "—"
                    dur_delta = dist_delta = act_detail = ""
                    status = "❌ Missed"

                rows_cmp.append({
                    "Date":          pd.Timestamp(p["date"]).strftime("%b %d"),
                    "Sport":         {"swim":"🏊","bike":"🚴","run":"🏃","str":"🏋️"}.get(sp, sp),
                    "Planned type":  p["workout_type"],
                    "Planned dur":   f"{int(planned_dur)} min" if pd.notna(planned_dur) and planned_dur else "—",
                    "Actual dur":    f"{act_dur} min" if act_dur != "—" else "—",
                    "Δ Duration":    dur_delta,
                    "Actual detail": act_detail,
                    "Status":        status,
                })

            df_cmp = pd.DataFrame(rows_cmp)
            st.dataframe(df_cmp, hide_index=True, use_container_width=True,
                column_config={
                    "Date":         st.column_config.TextColumn("Date",        width=70),
                    "Sport":        st.column_config.TextColumn("Sport",       width=60),
                    "Planned type": st.column_config.TextColumn("Planned",     width=150),
                    "Planned dur":  st.column_config.TextColumn("Plan",        width=70),
                    "Actual dur":   st.column_config.TextColumn("Actual",      width=70),
                    "Δ Duration":   st.column_config.TextColumn("Delta",       width=75),
                    "Actual detail":st.column_config.TextColumn("Detail",      width=100),
                    "Status":       st.column_config.TextColumn("Status",      width=80),
                })

            # Summary
            n_done   = sum(1 for r in rows_cmp if "✅" in r["Status"])
            n_missed = sum(1 for r in rows_cmp if "❌" in r["Status"])
            st.markdown(" ")
            s1, s2, s3 = st.columns(3)
            s1.metric("Sessions planned",   len(rows_cmp))
            s2.metric("Completed",          n_done,   delta=None)
            s3.metric("Missed",             n_missed, delta=None)

        # Garmin push stub
        st.markdown("---")
        section("Push to Garmin", "Send planned workouts to the athlete's device")
        st.info("""
**Coming soon** — The Garmin Connect API supports structured workout push via `add_workout()`.

To enable this, the `garminconnect` library needs to be extended with:
- Structured workout format (FIT file or JSON payload per sport)
- Scheduled date mapping to the athlete's calendar

For now, workouts are saved locally and compared against synced Garmin data.
        """)


# ══════════════════════════════════════════════════════════════════════════════
# 📊 DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📊 Dashboard":
    latest = df_load.iloc[-1] if not df_load.empty else {}
    prev   = df_load.iloc[-8] if len(df_load) > 7 else {}

    ctl  = float(latest.get("ctl",  55))
    atl  = float(latest.get("atl",  60))
    tsb  = float(latest.get("tsb",  -5))
    acwr = float(latest.get("acwr", 1.05))
    ctl_d = ctl - float(prev.get("ctl", ctl))
    atl_d = atl - float(prev.get("atl", atl))

    # ── Daily Readiness Score ─────────────────────────────────────────────────
    rdy, rdy_lbl, rdy_color, rdy_cmp = _readiness_score(tsb, df_hrv, df_sleep)

    # ── Fila 1: Readiness + sus 3 componentes ────────────────────────────────
    def _dot(v): return "🟢" if v >= 70 else "🟡" if v >= 50 else "🔴"
    section("Daily Readiness", "How ready are you to train today?")
    rd0, rd1, rd2, rd3 = st.columns(4)
    rd0.metric("⚡ Readiness Score", f"{rdy} / 100", rdy_lbl)
    rd1.metric(f"{_dot(rdy_cmp['TSB'])}  Form (TSB)",
               f"{rdy_cmp['TSB']:.0f} / 100",
               "Optimal" if 60 <= rdy_cmp['TSB'] <= 100 else "High fatigue" if rdy_cmp['TSB'] < 40 else "")
    rd2.metric(f"{_dot(rdy_cmp['HRV'])}  HRV Status",
               f"{rdy_cmp['HRV']:.0f} / 100",
               "No HRV data" if df_hrv.empty else "Stable" if rdy_cmp['HRV'] >= 70 else "Below avg")
    rd3.metric(f"{_dot(rdy_cmp['Sleep'])}  Sleep Quality",
               f"{rdy_cmp['Sleep']:.0f} / 100",
               "No sleep data" if df_sleep.empty else "Good" if rdy_cmp['Sleep'] >= 70 else "Poor")

    st.markdown(" ")

    # ── Fila 2: Training load KPIs ────────────────────────────────────────────
    section("Training Load", "Last 7 days vs previous week")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CTL — Fitness",  f"{ctl:.1f}",  f"{ctl_d:+.1f} vs last week")
    c2.metric("ATL — Fatigue",  f"{atl:.1f}",  f"{atl_d:+.1f}")
    c3.metric("TSB — Form",     f"{tsb:.1f}",
              "Race Ready ✓" if tsb > 10 else "Training" if tsb > -15 else "⚠ Fatigue")
    c4.metric("ACWR",           f"{acwr:.2f}",
              "Safe ✓" if 0.8 <= acwr <= 1.3 else "⚠ Injury risk")

    st.markdown(" ")
    left, right = st.columns([2, 1], gap="medium")

    with left:
        section("Performance Chart", "90-day CTL / ATL / TSB")
        if not df_load.empty:
            df90 = df_load.tail(90)
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Scatter(x=df90["date"], y=df90["ctl"], name="CTL",
                line=dict(color=COL_CTL, width=2.5)), secondary_y=False)
            fig.add_trace(go.Scatter(x=df90["date"], y=df90["atl"], name="ATL",
                line=dict(color=COL_ATL, width=2)), secondary_y=False)
            fig.add_trace(go.Scatter(x=df90["date"], y=df90["tsb"], name="TSB",
                line=dict(color=COL_TSB, width=1.5),
                fill="tozeroy", fillcolor="rgba(139,92,246,0.08)"), secondary_y=True)
            fig.add_hline(y=0, line_dash="dot", line_color="#CBD5E1", secondary_y=True)
            fig.update_yaxes(title_text="CTL/ATL", secondary_y=False, title_font_size=10)
            fig.update_yaxes(title_text="TSB",     secondary_y=True,  title_font_size=10)
            st.plotly_chart(chart(fig, 320, dict(l=0, r=0, t=14, b=0)), use_container_width=True)
        else:
            st.info("No training load data — click Sync Garmin in the sidebar.")

    with right:
        today = pd.Timestamp.today().normalize()
        since = today - timedelta(days=6)
        df_week = df_act[df_act["date"] >= since].copy() if has_data else pd.DataFrame()
        section("This Week", since.strftime("%b %d") + " – " + today.strftime("%b %d"))

        REF = {"swim": 15, "bike": 250, "run": 60}
        for sp in ["swim", "bike", "run"]:
            sub = df_week[df_week["sport"] == sp] if not df_week.empty else pd.DataFrame()
            km  = sub["distance_m"].sum() / 1000 if not sub.empty else 0
            sec_t = sub["duration_sec"].sum() if not sub.empty else 0
            n   = len(sub)
            ca, cb = st.columns([3, 1])
            ca.markdown(f"**{SPORT_ICONS[sp]} {sp.title()}**")
            cb.markdown(f"**{km:.1f} km**")
            st.progress(min(1.0, km / REF[sp]))
            st.caption(f"{n} sessions · {_fmt_dur(sec_t)}" if n else "No sessions")

        # Strength — sin distancia, mostramos sesiones y tiempo
        str_sub  = df_week[df_week["sport"] == "str"] if not df_week.empty else pd.DataFrame()
        str_n    = len(str_sub)
        str_sec  = str_sub["duration_sec"].sum() if not str_sub.empty else 0
        ca, cb = st.columns([3, 1])
        ca.markdown(f"**🏋️ Strength**")
        cb.markdown(f"**{str_n} sess**")
        st.progress(min(1.0, str_n / 3))   # referencia: 3 sesiones/semana
        st.caption(f"{str_n} sessions · {_fmt_dur(str_sec)}" if str_n else "No sessions")

        st.divider()
        tss_tot = df_week["tss"].fillna(0).sum() if not df_week.empty else 0
        sec_tot = df_week["duration_sec"].sum() if not df_week.empty else 0
        ta, tb = st.columns(2)
        ta.metric("TSS",  f"{tss_tot:.0f}")
        tb.metric("Time", _fmt_dur(sec_tot))

    st.markdown(" ")
    bot_l, bot_r = st.columns([1, 2], gap="medium")

    with bot_l:
        # Plan compliance for Race Readiness
        _plan_done = 0; _plan_total = 1
        if not df_plan.empty:
            _cutoff = pd.Timestamp.today().normalize() - timedelta(days=28)
            _recent = df_plan[pd.to_datetime(df_plan["date"]) >= _cutoff]
            if not _recent.empty:
                _plan_total = len(_recent)
                _plan_done  = sum(1 for _, row in _recent.iterrows()
                                  if not df_act.empty and _match_actual(row, df_act) is not None)
        _compliance = (_plan_done / _plan_total * 100) if _plan_total else 75

        rri, rri_lbl, rri_col = _race_readiness(tsb, df_hrv, df_sleep, _compliance)
        target_race = _prof.get("target_race", "703")
        target_date = _prof.get("target_date", "")
        days_to_race = None
        if target_date:
            try:
                days_to_race = (datetime.strptime(target_date, "%Y-%m-%d") - datetime.today()).days
            except Exception:
                pass

        section("Race Readiness Index",
                f"Target: {RACE_LABELS.get(target_race, target_race)}"
                + (f"  ·  {days_to_race}d away" if days_to_race and days_to_race > 0 else ""))

        rri_a, rri_b = st.columns([1, 1])
        with rri_a:
            st.metric("Race Readiness", f"{rri}/100", rri_lbl)
        with rri_b:
            st.metric("Plan Compliance", f"{_compliance:.0f}%",
                      f"{_plan_done}/{_plan_total} sessions last 28d")
        st.markdown(" ")

        # Gauge-style bar
        bar_pct = rri
        bar_c   = rri_col.replace("#", "%23")
        st.markdown(f"""
<div style="background:#F1F5F9;border-radius:6px;height:10px;margin:4px 0 10px">
  <div style="background:{rri_col};height:100%;width:{bar_pct}%;border-radius:6px;
    transition:width .4s"></div>
</div>""", unsafe_allow_html=True)

        # Component breakdown
        comp_labels = [
            ("TSB Form",    "Training Stress Balance in optimal range", tsb, 5, 15),
            ("HRV Status",  "Heart Rate Variability trend (7 days)",    None, None, None),
            ("Sleep",       "Average sleep quality last 7 nights",      None, None, None),
            ("Compliance",  "Training plan adherence last 28 days",     _compliance, 80, 100),
        ]
        for lbl, desc, val, lo, hi in comp_labels:
            v_ok = (val is not None and lo is not None and lo <= val <= hi)
            icon = "✅" if v_ok else ("—" if val is None else "⚠️")
            v_str = f"{val:.0f}" if val is not None else "—"
            st.caption(f"{icon} **{lbl}** — {desc}")

    with bot_r:
        section("Recent Activities", "Last 10")
        if has_data:
            rows = []
            for _, r in df_act.head(10).iterrows():
                sp = r["sport"]
                dt = pd.to_datetime(r["date"])
                day = ("Today" if dt.date() == date.today()
                       else "Yesterday" if dt.date() == date.today() - timedelta(1)
                       else dt.strftime("%b %d"))
                if sp == "bike":
                    detail = f"{r.get('norm_power') or r.get('avg_power') or 0:.0f}W"
                elif sp == "run":
                    detail = (_fmt_pace(r["avg_pace_sec_km"]) + "/km"
                              if r.get("avg_pace_sec_km") else "—")
                else:
                    detail = f"{r['distance_m']/1000:.1f} km"
                rows.append({
                    "": SPORT_ICONS[sp],
                    "Activity": str(r.get("name", sp))[:38],
                    "Date": day,
                    "Duration": _fmt_dur(r["duration_sec"]),
                    "Detail": detail,
                    "TSS": f"{r.get('tss') or 0:.0f}",
                })
            st.dataframe(
                pd.DataFrame(rows), hide_index=True, use_container_width=True,
                column_config={
                    "": st.column_config.TextColumn("", width=30),
                    "Activity": st.column_config.TextColumn("Activity", width=180),
                    "Date": st.column_config.TextColumn("Date", width=75),
                    "Duration": st.column_config.TextColumn("Duration", width=80),
                    "Detail": st.column_config.TextColumn("Detail", width=85),
                    "TSS": st.column_config.TextColumn("TSS", width=50),
                },
            )
        else:
            st.info("No activities — click Sync Garmin in the sidebar.")

    # ── Strength KPIs ─────────────────────────────────────────────────────────
    st.markdown(" ")
    section("🏋️ Strength & Conditioning", "Last 30 days")

    df_str = df_act[df_act["sport"] == "str"].copy() if has_data else pd.DataFrame()
    today_ts  = pd.Timestamp.today().normalize()
    last_30   = today_ts - timedelta(days=29)
    last_7    = today_ts - timedelta(days=6)
    df_str30  = df_str[df_str["date"] >= last_30] if not df_str.empty else pd.DataFrame()
    df_str7   = df_str[df_str["date"] >= last_7]  if not df_str.empty else pd.DataFrame()

    last_str  = df_str["date"].max() if not df_str.empty else None
    last_str_label = (
        "Today"     if last_str and last_str.date() == date.today()     else
        "Yesterday" if last_str and last_str.date() == date.today() - timedelta(1) else
        last_str.strftime("%b %d") if last_str else "—"
    )
    # Frecuencia: sesiones por semana (rolling 4 sem)
    freq_4w = len(df_str30) / 4 if not df_str30.empty else 0
    avg_dur  = df_str30["duration_sec"].mean() / 60 if not df_str30.empty else 0

    sk1, sk2, sk3, sk4 = st.columns(4)
    sk1.metric("Sessions this week",  len(df_str7),               "goal: 3/wk")
    sk2.metric("Sessions last 30d",   len(df_str30))
    sk3.metric("Avg frequency",       f"{freq_4w:.1f} /wk",       "rolling 4 weeks")
    sk4.metric("Avg session length",  f"{avg_dur:.0f} min" if avg_dur else "—",
               f"last: {last_str_label}")

    if not df_str30.empty:
        st.markdown(" ")
        str_l, str_r = st.columns(2, gap="medium")

        with str_l:
            section("Weekly Strength Sessions", "Count by week")
            df_str30["week"] = df_str30["date"].dt.to_period("W").dt.start_time
            wk_str = df_str30.groupby("week").size().reset_index(name="sessions")
            fig_s = px.bar(wk_str, x="week", y="sessions",
                           color_discrete_sequence=[COL_STR])
            fig_s.update_layout(xaxis_title="", yaxis_title="Sessions",
                                yaxis=dict(tickmode="linear", dtick=1))
            fig_s.add_hline(y=3, line_dash="dot", line_color="#94A3B8",
                            annotation_text="Goal 3/wk", annotation_font_size=9)
            st.plotly_chart(chart(fig_s, 240, dict(l=0, r=0, t=14, b=0)),
                            use_container_width=True)

        with str_r:
            section("Session Duration", "Minutes per session")
            df_str_plot = df_str30.copy()
            df_str_plot["dur_min"] = df_str_plot["duration_sec"] / 60
            fig_d = go.Figure()
            fig_d.add_trace(go.Scatter(
                x=df_str_plot["date"], y=df_str_plot["dur_min"],
                mode="markers+lines",
                line=dict(color=COL_STR, width=2),
                marker=dict(size=7, color=COL_STR),
            ))
            fig_d.add_hline(y=45, line_dash="dot", line_color="#94A3B8",
                            annotation_text="45 min target", annotation_font_size=9)
            fig_d.update_yaxes(title_text="min")
            st.plotly_chart(chart(fig_d, 240, dict(l=0, r=0, t=14, b=0)),
                            use_container_width=True)
    else:
        st.info("No strength sessions in the last 30 days. Add them manually in **📋 Training Plan** or sync from Garmin.")


# ══════════════════════════════════════════════════════════════════════════════
# 📈 TRAINING LOAD
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📈 Training Load":
    if df_load.empty:
        st.info("No training load data. Sync Garmin from the sidebar.")
        st.stop()

    lat = df_load.iloc[-1]
    ctl, atl = float(lat["ctl"]), float(lat["atl"])
    tsb, acwr = float(lat["tsb"]), float(lat["acwr"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CTL", f"{ctl:.1f}", "Chronic Load")
    c2.metric("ATL", f"{atl:.1f}", "Acute Load")
    c3.metric("TSB", f"{tsb:.1f}",
              "Race Ready ✓" if tsb > 10 else "Training" if tsb > -15 else "⚠ Fatigue")
    c4.metric("ACWR", f"{acwr:.2f}", "Safe ✓" if 0.8 <= acwr <= 1.3 else "⚠ Injury risk")

    st.markdown(" ")
    section("Performance Management Chart", "CTL / ATL / TSB / Daily TSS")

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=df_load["date"], y=df_load["tss"], name="TSS",
        marker_color="#E2E8F0", opacity=0.7), secondary_y=False)
    fig.add_trace(go.Scatter(x=df_load["date"], y=df_load["ctl"], name="CTL",
        line=dict(color=COL_CTL, width=2.5)), secondary_y=False)
    fig.add_trace(go.Scatter(x=df_load["date"], y=df_load["atl"], name="ATL",
        line=dict(color=COL_ATL, width=2)), secondary_y=False)
    fig.add_trace(go.Scatter(x=df_load["date"], y=df_load["tsb"], name="TSB",
        line=dict(color=COL_TSB, width=1.5),
        fill="tozeroy", fillcolor="rgba(139,92,246,0.08)"), secondary_y=True)
    fig.add_hline(y=0, line_dash="dot", line_color="#CBD5E1", secondary_y=True)
    st.plotly_chart(chart(fig, 380, dict(l=0, r=0, t=14, b=0)), use_container_width=True)

    st.markdown(" ")
    c1, c2 = st.columns(2, gap="medium")

    with c1:
        section("Weekly TSS", "By sport")
        if not df_act.empty:
            dfw = df_act.copy()
            dfw["week"] = dfw["date"].dt.to_period("W").dt.start_time
            wk = dfw.groupby(["week", "sport"])["tss"].sum().reset_index()
            fig2 = px.bar(wk, x="week", y="tss", color="sport", barmode="stack",
                          color_discrete_map=SPORT_COLORS)
            fig2.update_layout(xaxis_title="", yaxis_title="TSS", legend_title_text="")
            st.plotly_chart(chart(fig2, 280, dict(l=0, r=0, t=14, b=0)), use_container_width=True)

    with c2:
        section("ACWR", "Safe zone 0.8–1.3")
        fig3 = go.Figure()
        fig3.add_hrect(y0=0.8, y1=1.3, fillcolor="rgba(16,185,129,0.07)", line_width=0)
        fig3.add_hrect(y0=1.3, y1=3.0, fillcolor="rgba(239,68,68,0.05)",  line_width=0)
        fig3.add_trace(go.Scatter(
            x=df_load["date"].tail(90), y=df_load["acwr"].tail(90),
            line=dict(color=COL_BIKE, width=2.5),
            fill="tozeroy", fillcolor="rgba(245,158,11,0.07)", name="ACWR"))
        fig3.add_hline(y=0.8, line_dash="dot", line_color="#94A3B8",
                       annotation_text="Min", annotation_font_size=9)
        fig3.add_hline(y=1.3, line_dash="dot", line_color="#EF4444",
                       annotation_text="Max", annotation_font_size=9)
        fig3.update_yaxes(range=[0, max(2.0, float(df_load["acwr"].max()) + 0.2)],
                          title_text="ACWR")
        st.plotly_chart(chart(fig3, 280, dict(l=0, r=0, t=14, b=0)), use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# 🏊 SWIMMING
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🏊 Swimming":
    df_s = df_act[df_act["sport"] == "swim"].sort_values("date").copy() if has_data else pd.DataFrame()
    if df_s.empty:
        st.info("No swim sessions. Sync Garmin from the sidebar.")
        st.stop()

    avg_sw = df_s["swolf"].dropna().mean() if "swolf" in df_s.columns else None
    swolf_ok = avg_sw is not None and pd.notna(avg_sw)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sessions",   str(len(df_s)))
    c2.metric("Total Dist", f"{df_s['distance_m'].sum() / 1000:.0f} km")
    c3.metric("Total Time", _fmt_dur(df_s["duration_sec"].sum()))
    c4.metric("Avg SWOLF",  f"{avg_sw:.0f}" if swolf_ok else "—",
              swolf_to_efficiency_rating(int(avg_sw)) if swolf_ok else "")

    st.markdown(" ")
    c1, c2 = st.columns(2, gap="medium")

    with c1:
        section("Weekly Volume", "km")
        df_s["week"] = df_s["date"].dt.to_period("W").dt.start_time
        wk = df_s.groupby("week")["distance_m"].sum().reset_index()
        wk["km"] = wk["distance_m"] / 1000
        fig = px.bar(wk, x="week", y="km", color_discrete_sequence=[COL_SWIM])
        fig.update_layout(xaxis_title="", yaxis_title="km")
        st.plotly_chart(chart(fig, 280, dict(l=0, r=0, t=14, b=0)), use_container_width=True)

    with c2:
        section("Pace vs CSS", f"Threshold {t_swim}/100m")
        col = "avg_pace_100m"
        df_p = df_s.dropna(subset=[col]) if col in df_s.columns else pd.DataFrame()
        if not df_p.empty:
            thr = _parse_pace(t_swim, 110.0)
            fig2 = go.Figure()
            fig2.add_hline(y=thr, line_dash="dash", line_color="#94A3B8",
                           annotation_text=f"CSS {_fmt_pace(thr)}/100m", annotation_font_size=9)
            fig2.add_trace(go.Scatter(x=df_p["date"], y=df_p[col],
                mode="markers+lines", line=dict(color=COL_SWIM, width=2), marker_size=5))
            fig2.update_yaxes(autorange="reversed", title_text="sec/100m")
            st.plotly_chart(chart(fig2, 280, dict(l=0, r=0, t=14, b=0)), use_container_width=True)
        else:
            st.info("No pace data in swim sessions.")


# ══════════════════════════════════════════════════════════════════════════════
# 🚴 CYCLING
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🚴 Cycling":
    df_b = df_act[df_act["sport"] == "bike"].sort_values("date").copy() if has_data else pd.DataFrame()
    if df_b.empty:
        st.info("No cycling sessions. Sync Garmin from the sidebar.")
        st.stop()

    avg_np = df_b["norm_power"].dropna().mean() if "norm_power" in df_b.columns else None
    avg_if = df_b["if_factor"].dropna().mean()  if "if_factor"  in df_b.columns else None

    # W/kg KPI
    wkg_ftp  = round(ftp / weight, 2)
    ef_b_df  = _ef_bike(df_b)
    ef_b_now = ef_b_df["ef"].tail(10).mean() if not ef_b_df.empty else None
    ef_b_pre = ef_b_df["ef"].head(max(1, len(ef_b_df)-10)).mean() if len(ef_b_df) > 10 else None
    ef_b_delta = ((ef_b_now - ef_b_pre) / ef_b_pre * 100) if ef_b_now and ef_b_pre and ef_b_pre > 0 else None

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Sessions",   str(len(df_b)))
    c2.metric("Total Dist", f"{df_b['distance_m'].sum() / 1000:.0f} km")
    c3.metric("Total Time", _fmt_dur(df_b["duration_sec"].sum()))
    c4.metric("FTP W/kg",   f"{wkg_ftp:.2f}",
              "Cat 2 ✓" if wkg_ftp >= 4.0 else "Cat 3 ✓" if wkg_ftp >= 3.2 else "Building")
    c5.metric("Aerobic EF", f"{ef_b_now:.3f}" if ef_b_now else "—",
              (f"{ef_b_delta:+.1f}%" if ef_b_delta else "") + " trend")

    st.markdown(" ")
    c1, c2 = st.columns(2, gap="medium")

    with c1:
        section("Power", f"NP · Avg · FTP {ftp}W")
        df_pw = df_b.dropna(subset=["avg_power"])
        if not df_pw.empty:
            fig = go.Figure()
            if "norm_power" in df_pw.columns and df_pw["norm_power"].notna().any():
                fig.add_trace(go.Scatter(x=df_pw["date"], y=df_pw["norm_power"], name="NP",
                    mode="markers+lines", line=dict(color=COL_ATL, width=2), marker_size=5))
            fig.add_trace(go.Scatter(x=df_pw["date"], y=df_pw["avg_power"], name="Avg",
                mode="markers", marker=dict(color=COL_BIKE, size=6, opacity=0.8)))
            fig.add_hline(y=ftp, line_dash="dash", line_color=ACCENT,
                          annotation_text=f"FTP {ftp}W", annotation_font_size=9)
            fig.update_yaxes(title_text="Watts")
            st.plotly_chart(chart(fig, 290, dict(l=0, r=0, t=14, b=0)), use_container_width=True)
        else:
            st.info("No power data.")

    with c2:
        section("Power Zones", "Sessions per zone")
        df_pw2 = df_b.dropna(subset=["avg_power"])
        if not df_pw2.empty:
            zones = power_zones(ftp)
            zdata = [
                {"Zone": n.split(" ", 1)[-1],
                 "Sessions": int(((df_pw2["avg_power"] >= lo) & (df_pw2["avg_power"] < hi)).sum())}
                for n, (lo, hi) in zones.items()
            ]
            fig2 = px.bar(pd.DataFrame(zdata), x="Zone", y="Sessions", color="Zone",
                color_discrete_sequence=["#DBEAFE","#BFDBFE","#93C5FD","#60A5FA",
                                         "#3B82F6","#2563EB","#1D4ED8"])
            fig2.update_layout(showlegend=False, xaxis_title="", yaxis_title="Sessions")
            st.plotly_chart(chart(fig2, 290, dict(l=0, r=0, t=14, b=0)), use_container_width=True)

    section("Weekly Volume & TSS")
    df_b["week"] = df_b["date"].dt.to_period("W").dt.start_time
    wk = df_b.groupby("week").agg(
        km=("distance_m", lambda x: x.sum() / 1000),
        tss=("tss", "sum"),
    ).reset_index()
    fig3 = make_subplots(specs=[[{"secondary_y": True}]])
    fig3.add_trace(go.Bar(x=wk["week"], y=wk["km"], name="km",
        marker_color=COL_BIKE, opacity=0.8), secondary_y=False)
    fig3.add_trace(go.Scatter(x=wk["week"], y=wk["tss"], name="TSS",
        line=dict(color=ACCENT, width=2.5), mode="lines+markers", marker_size=5),
        secondary_y=True)
    st.plotly_chart(chart(fig3, 260, dict(l=0, r=0, t=14, b=0)), use_container_width=True)

    # ── KPI 2 + 3: Aerobic EF Trend + W/kg Monthly Trend ─────────────────────
    st.markdown(" ")
    ef_col, wkg_col = st.columns(2, gap="medium")

    with ef_col:
        section("Aerobic Efficiency Factor", "NP / HR — higher is better")
        if not ef_b_df.empty:
            ef_b_plot = ef_b_df.tail(90)
            ef_ma = ef_b_plot["ef"].rolling(5, min_periods=1).mean()
            ef_baseline = ef_b_df["ef"].mean()
            fig_ef = go.Figure()
            fig_ef.add_trace(go.Scatter(
                x=ef_b_plot["date"], y=ef_b_plot["ef"],
                name="EF session", mode="markers",
                marker=dict(color=COL_BIKE, size=6, opacity=0.6)))
            fig_ef.add_trace(go.Scatter(
                x=ef_b_plot["date"], y=ef_ma,
                name="5-session MA", mode="lines",
                line=dict(color=COL_CTL, width=2.5)))
            fig_ef.add_hline(y=ef_baseline, line_dash="dot", line_color="#94A3B8",
                annotation_text=f"Avg {ef_baseline:.3f}", annotation_font_size=9)
            fig_ef.update_yaxes(title_text="EF (W/bpm)")
            st.plotly_chart(chart(fig_ef, 280, dict(l=0, r=0, t=14, b=0)),
                            use_container_width=True)
            if ef_b_delta:
                trend_txt = ("📈 Aerobic efficiency improving" if ef_b_delta > 3
                             else "➡️ Stable aerobic base" if ef_b_delta > -3
                             else "📉 Efficiency declining — increase Z2 work")
                st.caption(trend_txt)
        else:
            st.info("Need HR + power data to compute EF.")

    with wkg_col:
        section("Monthly W/kg Trend", f"Current FTP: {wkg_ftp:.2f} W/kg")
        df_b_wkg = df_b.copy()
        df_b_wkg["month"] = df_b_wkg["date"].dt.to_period("M").dt.start_time
        pwr_col = "norm_power" if "norm_power" in df_b_wkg.columns else "avg_power"
        monthly = (df_b_wkg.dropna(subset=[pwr_col])
                   .groupby("month")[pwr_col].mean()
                   .reset_index(name="avg_pwr"))
        monthly["wkg"] = (monthly["avg_pwr"] / weight).round(2)
        if not monthly.empty:
            fig_wkg = go.Figure()
            fig_wkg.add_trace(go.Bar(
                x=monthly["month"], y=monthly["wkg"],
                name="W/kg", marker_color=COL_BIKE, opacity=0.75))
            for lvl, lbl, col_ in [(4.0,"Cat 2","#10B981"),
                                    (3.2,"Cat 3","#3B82F6"),
                                    (2.5,"Cat 4","#94A3B8")]:
                fig_wkg.add_hline(y=lvl, line_dash="dot", line_color=col_,
                    annotation_text=lbl, annotation_font_size=9)
            fig_wkg.add_hline(y=wkg_ftp, line_dash="solid", line_color=COL_ATL,
                annotation_text=f"FTP {wkg_ftp:.2f}", annotation_font_size=9)
            fig_wkg.update_yaxes(title_text="W/kg")
            st.plotly_chart(chart(fig_wkg, 280, dict(l=0, r=0, t=14, b=0)),
                            use_container_width=True)
        else:
            st.info("Need power data for W/kg trend.")


# ══════════════════════════════════════════════════════════════════════════════
# 🏃 RUNNING
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🏃 Running":
    df_r = df_act[df_act["sport"] == "run"].sort_values("date").copy() if has_data else pd.DataFrame()
    if df_r.empty:
        st.info("No running sessions. Sync Garmin from the sidebar.")
        st.stop()

    df_pace = df_r.dropna(subset=["avg_pace_sec_km"])
    avg_pace = df_pace["avg_pace_sec_km"].mean() if not df_pace.empty else None
    avg_cad  = df_r["avg_cadence"].dropna().mean() if "avg_cadence" in df_r.columns else None

    ef_r_df  = _ef_run(df_r)
    ef_r_now = ef_r_df["ef"].tail(10).mean() if not ef_r_df.empty else None
    ef_r_pre = ef_r_df["ef"].head(max(1, len(ef_r_df)-10)).mean() if len(ef_r_df) > 10 else None
    ef_r_delta = ((ef_r_now - ef_r_pre) / ef_r_pre * 100) if ef_r_now and ef_r_pre and ef_r_pre > 0 else None

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Sessions",    str(len(df_r)))
    c2.metric("Total Dist",  f"{df_r['distance_m'].sum() / 1000:.0f} km")
    c3.metric("Avg Pace",    _fmt_pace(avg_pace) + "/km" if avg_pace else "—")
    c4.metric("Avg Cadence", f"{avg_cad:.0f} spm" if avg_cad else "—",
              "✓" if avg_cad and 175 <= avg_cad <= 185 else ("↑ High" if avg_cad and avg_cad > 185 else "↓ Low" if avg_cad else ""))
    c5.metric("Run Aero EF", f"{ef_r_now:.4f}" if ef_r_now else "—",
              (f"{ef_r_delta:+.1f}% trend" if ef_r_delta else ""))

    st.markdown(" ")
    c1, c2 = st.columns(2, gap="medium")

    with c1:
        section("Pace Trend", f"vs threshold {t_run}/km")
        if not df_pace.empty:
            thr = _parse_pace(t_run)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_pace["date"], y=df_pace["avg_pace_sec_km"] / 60,
                mode="markers+lines", line=dict(color=COL_RUN, width=2.5), marker_size=5))
            fig.add_hline(y=thr / 60, line_dash="dash", line_color=ACCENT,
                          annotation_text=f"Threshold {_fmt_pace(thr)}/km", annotation_font_size=9)
            fig.update_yaxes(autorange="reversed", title_text="min/km")
            st.plotly_chart(chart(fig, 290, dict(l=0, r=0, t=14, b=0)), use_container_width=True)

    with c2:
        section("HR Zones", "LTHR 168 bpm")
        df_hr = df_r.dropna(subset=["avg_hr"])
        if not df_hr.empty:
            lthr = 168
            zones_hr = {
                "Z1 <75%":   (0,          0.75 * lthr),
                "Z2 75-85%": (0.75 * lthr, 0.85 * lthr),
                "Z3 85-92%": (0.85 * lthr, 0.92 * lthr),
                "Z4 92-100%":(0.92 * lthr, lthr),
                "Z5 >LTHR":  (lthr,        999),
            }
            zc = pd.DataFrame([
                {"Zone": z, "Sessions": int(((df_hr["avg_hr"] >= lo) & (df_hr["avg_hr"] < hi)).sum())}
                for z, (lo, hi) in zones_hr.items()
            ])
            fig2 = px.bar(zc, x="Zone", y="Sessions", color="Zone",
                color_discrete_sequence=["#DBEAFE","#60A5FA","#F59E0B","#EF4444","#7F1D1D"])
            fig2.update_layout(showlegend=False, xaxis_title="", yaxis_title="Sessions")
            st.plotly_chart(chart(fig2, 290, dict(l=0, r=0, t=14, b=0)), use_container_width=True)

    vol_col, ef_r_col = st.columns(2, gap="medium")
    with vol_col:
        section("Weekly Volume")
        df_r["week"] = df_r["date"].dt.to_period("W").dt.start_time
        wk = df_r.groupby("week").agg(km=("distance_m", lambda x: x.sum() / 1000)).reset_index()
        fig3 = px.bar(wk, x="week", y="km", color_discrete_sequence=[COL_RUN])
        fig3.update_layout(xaxis_title="", yaxis_title="km")
        st.plotly_chart(chart(fig3, 260, dict(l=0, r=0, t=14, b=0)), use_container_width=True)

    with ef_r_col:
        section("Aerobic Efficiency Factor", "Speed / HR — higher = more aerobic")
        if not ef_r_df.empty:
            ef_r_plot = ef_r_df.tail(90)
            ef_r_ma   = ef_r_plot["ef"].rolling(5, min_periods=1).mean()
            ef_r_base = ef_r_df["ef"].mean()
            fig_efr = go.Figure()
            fig_efr.add_trace(go.Scatter(
                x=ef_r_plot["date"], y=ef_r_plot["ef"],
                name="EF session", mode="markers",
                marker=dict(color=COL_RUN, size=6, opacity=0.6)))
            fig_efr.add_trace(go.Scatter(
                x=ef_r_plot["date"], y=ef_r_ma,
                name="5-session MA", mode="lines",
                line=dict(color=COL_CTL, width=2.5)))
            fig_efr.add_hline(y=ef_r_base, line_dash="dot", line_color="#94A3B8",
                annotation_text=f"Avg {ef_r_base:.4f}", annotation_font_size=9)
            fig_efr.update_yaxes(title_text="EF (m·s⁻¹/bpm)")
            st.plotly_chart(chart(fig_efr, 260, dict(l=0, r=0, t=14, b=0)),
                            use_container_width=True)
            if ef_r_delta:
                trend_txt = ("📈 Run economy improving" if ef_r_delta > 3
                             else "➡️ Stable run base" if ef_r_delta > -3
                             else "📉 Declining — add Z2 / easy runs")
                st.caption(trend_txt)
        else:
            st.info("Need pace + HR data to compute Run EF.")


# ══════════════════════════════════════════════════════════════════════════════
# 🍎 NUTRITION
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🍎 Nutrition":
    section("Caloric Expenditure", "Weekly by sport")
    if has_data:
        df_cal = df_act.copy()
        def _kcal(row):
            if row["sport"] == "bike": return caloric_expenditure_bike(row.get("avg_power") or ftp * 0.72, row["duration_sec"])
            if row["sport"] == "run":  return caloric_expenditure_run(weight, row["distance_m"] / 1000)
            if row["sport"] == "swim": return caloric_expenditure_swim(weight, row["duration_sec"] / 60)
            return 0
        df_cal["kcal"] = df_cal.apply(_kcal, axis=1)
        df_cal["week"] = df_cal["date"].dt.to_period("W").dt.start_time
        wk_cal = df_cal.groupby(["week", "sport"])["kcal"].sum().reset_index()
        fig = px.bar(wk_cal, x="week", y="kcal", color="sport", barmode="stack",
                     color_discrete_map=SPORT_COLORS)
        fig.update_layout(xaxis_title="", yaxis_title="kcal", legend_title_text="")
        st.plotly_chart(chart(fig, 300, dict(l=0, r=0, t=14, b=0)), use_container_width=True)
    else:
        st.info("Sync Garmin to see caloric expenditure.")

    st.markdown(" ")
    section("Race Nutrition Calculator",
            "Plan personalizado basado en tu predicción de carrera")

    # ── Selector + personalización ────────────────────────────────────────────
    _sel1, _sel2, _sel3 = st.columns([2, 1, 1])
    race_sel   = _sel1.selectbox("Distancia objetivo", list(RACE_LABELS.keys()),
                                  format_func=lambda k: RACE_LABELS[k])
    _sweat_opt = _sel2.selectbox("Sudoración",
                                   ["Normal (~600 ml/hr)", "Alta (~900 ml/hr)",
                                    "Muy alta (~1.2 L/hr)"])
    _heat_opt  = _sel3.selectbox("Temperatura ambiente",
                                   ["Frío/Templado (<20°C)", "Cálido (20-28°C)",
                                    "Caluroso (>28°C)"])

    pred     = predictor.predict(race_sel)
    total_h  = pred.total_sec / 3600
    b_kcal   = caloric_expenditure_bike(ftp * RECOMMENDED_IF[race_sel]["bike"],
                                         pred.bike.time_sec)
    r_kcal   = caloric_expenditure_run(weight, DISTANCES[race_sel]["run"] / 1000)
    s_kcal   = caloric_expenditure_swim(weight, pred.swim.time_sec / 60)
    tot_kcal = b_kcal + r_kcal + s_kcal

    # Adjustment factors
    _sweat_ml  = {"Normal (~600 ml/hr)": 600, "Alta (~900 ml/hr)": 900,
                  "Muy alta (~1.2 L/hr)": 1200}[_sweat_opt]
    _heat_f    = {"Frío/Templado (<20°C)": 1.0, "Cálido (20-28°C)": 1.15,
                  "Caluroso (>28°C)": 1.30}[_heat_opt]
    _fluid_hr  = int(_sweat_ml * _heat_f)
    _cho_hr    = {"sprint": 35, "olympic": 60, "703": 75, "ironman": 85}[race_sel]
    _sod_hr    = int({"sprint": 200, "olympic": 450, "703": 750, "ironman": 900}[race_sel]
                     * _heat_f)
    _cho_total = int(_cho_hr * (total_h - 0.5) if total_h > 0.5 else _cho_hr * total_h)
    _fl_total  = int(_fluid_hr * total_h)
    _sod_total = int(_sod_hr  * total_h)

    # ── Top KPI strip ─────────────────────────────────────────────────────────
    _k1, _k2, _k3, _k4, _k5, _k6 = st.columns(6)
    _k1.metric("⏱ Tiempo est.",  pred.total_display)
    _k2.metric("🔥 Energía",     f"{tot_kcal:.0f} kcal")
    _k3.metric("🍯 CHO total",   f"{_cho_total} g",    f"~{_cho_hr} g/hr")
    _k4.metric("💧 Fluidos",     f"{_fl_total/1000:.1f} L", f"~{_fluid_hr} ml/hr")
    _k5.metric("🧂 Sodio",       f"{_sod_total:,} mg",  f"~{_sod_hr} mg/hr")
    _k6.metric("⚡ Ratio CHO",
               "2:1 gluc:fruc" if total_h > 2.5 else "1:1 / libre",
               "Necesario >2.5h" if total_h > 2.5 else "")

    st.markdown(" ")

    # ── Segment timing ────────────────────────────────────────────────────────
    _sw_min = pred.swim.time_sec / 60
    _t1_min = {"sprint": 4.0, "olympic": 5.0, "703": 7.0, "ironman": 8.0}[race_sel]
    _bk_min = pred.bike.time_sec / 60
    _t2_min = {"sprint": 2.0, "olympic": 3.0, "703": 5.0, "ironman": 6.0}[race_sel]
    _rn_min = pred.run.time_sec / 60
    _tot_min = _sw_min + _t1_min + _bk_min + _t2_min + _rn_min
    _ss = {  # segment start minutes
        "swim": 0, "t1": _sw_min,
        "bike": _sw_min + _t1_min,
        "t2":   _sw_min + _t1_min + _bk_min,
        "run":  _sw_min + _t1_min + _bk_min + _t2_min,
    }

    # ── Build hour-by-hour plan checkpoints ───────────────────────────────────
    # Each checkpoint: what to consume FROM previous checkpoint TO here
    # cho_g / fluid_ml / sodium_mg refer to intake IN the interval ending here
    def _cp(t_min, seg, interval_lbl, cho, fluid, sodium, action, examples):
        return dict(t_min=round(t_min, 1), seg=seg, interval=interval_lbl,
                    cho_g=cho, fluid_ml=fluid, sodium_mg=sodium,
                    action=action, examples=examples)

    _SEG_ICON = {"swim": "🏊", "t1": "⚡T1", "bike": "🚴",
                 "t2": "⚡T2", "run": "🏃"}

    if race_sel == "sprint":
        _plan_rows = [
            _cp(_ss["swim"],  "swim", "Natación",
                0, 0, 0,
                "Sin ingesta. Hidrata bien en los 10min previos.",
                "200ml agua T-10min"),
            _cp(_ss["t1"],    "t1",   "T1",
                0, 0, 0,
                "Transición rápida. No comas en T1.",
                "—"),
            _cp(_ss["bike"] + _bk_min * 0.5, "bike", f"Bici ~{_ss['bike']+_bk_min*0.5:.0f}min",
                22, 300, 100,
                "Único gel en bici + botella isotónica. No esperes a tener sed.",
                "1 gel GU/Maurten · 300ml Gatorade"),
            _cp(_ss["t2"],    "t2",   "T2",
                0, 100, 0,
                "Pequeño sorbo. No gel en T2.",
                "100ml agua"),
            _cp(_ss["run"] + _rn_min * 0.5, "run", f"Run ~{_ss['run']+_rn_min*0.5:.0f}min",
                0, 200, 50,
                "Agua en los puestos de avituallamiento cada 1km.",
                "200ml agua"),
            _cp(_tot_min,     "run",  "META 🏁",
                0, 200, 100,
                "Hidratación y CHO de recuperación inmediata.",
                "Plátano + 500ml isotónico"),
        ]
    elif race_sel == "olympic":
        _plan_rows = [
            _cp(_ss["swim"],  "swim", f"Natación ({_sw_min:.0f}min)",
                0, 0, 0,
                "No es posible consumir nada. Nadar relajado los primeros 200m.",
                "—"),
            _cp(_ss["t1"],    "t1",   "T1",
                22, 150, 100,
                "Gel al salir del agua + pequeño sorbo de isotónico mientras te cambias.",
                "1 gel · 150ml Maurten/Gatorade"),
            _cp(_ss["bike"] + _bk_min * 0.33, "bike",
                f"Bici km~{DISTANCES['olympic']['bike']//3//1000:.0f}",
                35, 400, 200,
                "Primer bloque bici. Gel + botella isotónica completa.",
                "1 gel + 400ml isotónico"),
            _cp(_ss["bike"] + _bk_min * 0.66, "bike",
                f"Bici km~{DISTANCES['olympic']['bike']*2//3//1000:.0f}",
                30, 350, 200,
                "Segunda botella o recarga de hidratación. ½ barra energética.",
                "½ barra Clif/Powerbar + 350ml agua"),
            _cp(_ss["t2"],    "t2",   "T2",
                22, 100, 0,
                "Gel rápido al bajar de la bici.",
                "1 gel"),
            _cp(_ss["run"] + _rn_min * 0.35, "run",
                f"Run km~{DISTANCES['olympic']['run'] * 0.35 // 1000:.0f}",
                22, 250, 150,
                "Gel en el primer avituallamiento (~km 3.5).",
                "1 gel + 250ml agua"),
            _cp(_ss["run"] + _rn_min * 0.70, "run",
                f"Run km~{DISTANCES['olympic']['run'] * 0.7 // 1000:.0f}",
                0, 200, 100,
                "Solo agua. El gel anterior sigue activo.",
                "200ml agua"),
            _cp(_tot_min,     "run",  "META 🏁",
                0, 300, 200,
                "Recuperación inmediata. CHO + proteína en 30min.",
                "Plátano + isotónico + barrita proteína"),
        ]
    elif race_sel == "703":
        _plan_rows = [
            _cp(_ss["swim"],  "swim", f"Natación ({_sw_min:.0f}min)",
                0, 0, 0,
                "Sin ingesta. Usa traje adecuado y nada en calma los 400m iniciales.",
                "—"),
            _cp(_ss["t1"],    "t1",   "T1",
                22, 200, 150,
                "Gel + sorbo de isotónico. Bolsillo especial bike ya cargado.",
                "1 gel · 200ml isotónico"),
            _cp(_ss["bike"] + _bk_min * 0.20, "bike",
                f"Bici km~{DISTANCES['703']['bike'] * 0.2 // 1000:.0f}",
                int(70 * _heat_f), int(700 * _heat_f), int(700 * _heat_f),
                "Primer bloque. Ritmo moderado, activa la ingesta temprano.",
                "2 geles + 700ml isotónico"),
            _cp(_ss["bike"] + _bk_min * 0.40, "bike",
                f"Bici km~{DISTANCES['703']['bike'] * 0.4 // 1000:.0f}",
                int(70 * _heat_f), int(700 * _heat_f), int(700 * _heat_f),
                "Barra sólida si toleras bien. Mantén cadencia de ingesta.",
                "1 barra Clif + 1 gel + 700ml isotónico"),
            _cp(_ss["bike"] + _bk_min * 0.60, "bike",
                f"Bici km~{DISTANCES['703']['bike'] * 0.6 // 1000:.0f}",
                int(70 * _heat_f), int(700 * _heat_f), int(700 * _heat_f),
                "Mitad de la bici. Mantén el plan aunque no tengas apetito.",
                "2 geles + 700ml isotónico"),
            _cp(_ss["bike"] + _bk_min * 0.80, "bike",
                f"Bici km~{DISTANCES['703']['bike'] * 0.8 // 1000:.0f}",
                int(60 * _heat_f), int(600 * _heat_f), int(600 * _heat_f),
                "Último bloque bici. Reduce sólidos, prioriza geles fluidos.",
                "2 geles + 600ml agua+electrolitos"),
            _cp(_ss["t2"],    "t2",   "T2",
                22, 200, 200,
                "Gel + cola si la hubiera. Prepárate para el run.",
                "1 gel · 200ml cola"),
            _cp(_ss["run"] + _rn_min * 0.25, "run",
                f"Run km~{DISTANCES['703']['run'] * 0.25 // 1000:.0f}",
                int(50 * _heat_f), int(500 * _heat_f), int(600 * _heat_f),
                "Inicia run con suavidad. 2 geles primeros 30min + agua cada puesto.",
                "2 geles + 500ml agua"),
            _cp(_ss["run"] + _rn_min * 0.55, "run",
                f"Run km~{DISTANCES['703']['run'] * 0.55 // 1000:.0f}",
                int(40 * _heat_f), int(450 * _heat_f), int(600 * _heat_f),
                "Cola en puestos de avituallamiento + gel. Gestiona el calor.",
                "1 gel + cola + 450ml agua"),
            _cp(_ss["run"] + _rn_min * 0.80, "run",
                f"Run km~{DISTANCES['703']['run'] * 0.8 // 1000:.0f}",
                int(25 * _heat_f), int(350 * _heat_f), int(400 * _heat_f),
                "Últimos km. Solo lo que toleras: gel, agua, cola.",
                "1 gel o cola + agua"),
            _cp(_tot_min,     "run",  "META 🏁",
                0, 400, 500,
                "Recuperación: CHO + proteína + sal en <30min post-meta.",
                "Isotónico + plátano + proteína"),
        ]
    else:  # ironman
        _plan_rows = [
            _cp(_ss["swim"],  "swim", f"Natación ({_sw_min:.0f}min)",
                0, 0, 0,
                "Sin ingesta. Arranca suave los primeros 500m. Ahorra glucógeno.",
                "—"),
            _cp(_ss["t1"],    "t1",   "T1",
                25, 300, 200,
                "Gel + banana en T1. Empieza isotónico. Bolsos especiales ya preparados.",
                "1 gel + ½ banana · 300ml isotónico"),
            _cp(_ss["bike"] + _bk_min * 0.12, "bike",
                f"Bici km~{DISTANCES['ironman']['bike'] * 0.12 // 1000:.0f}",
                int(65 * _heat_f), int(700 * _heat_f), int(800 * _heat_f),
                "Inicio bici: ritmo conservador, activa ingesta temprano.",
                "2 geles + 700ml isotónico Maurten 320"),
            _cp(_ss["bike"] + _bk_min * 0.25, "bike",
                f"Bici km~{DISTANCES['ironman']['bike'] * 0.25 // 1000:.0f}",
                int(80 * _heat_f), int(800 * _heat_f), int(900 * _heat_f),
                "Hora 2 de bici. Alterna geles y sólidos según tolerancia.",
                "1 barra + 1 gel + 800ml isotónico"),
            _cp(_ss["bike"] + _bk_min * 0.38, "bike",
                f"Bici km~{DISTANCES['ironman']['bike'] * 0.38 // 1000:.0f}",
                int(80 * _heat_f), int(800 * _heat_f), int(900 * _heat_f),
                "Mantén ritmo de ingesta. Puesto especial de avituallamiento.",
                "2 geles + 800ml isotónico · bolso especial"),
            _cp(_ss["bike"] + _bk_min * 0.50, "bike",
                f"Bici km~{DISTANCES['ironman']['bike'] * 0.5 // 1000:.0f}",
                int(80 * _heat_f), int(800 * _heat_f), int(900 * _heat_f),
                "Mitad del Ironman. Come aunque no tengas hambre.",
                "Rice balls / banana + geles + 800ml agua+electrolitos"),
            _cp(_ss["bike"] + _bk_min * 0.63, "bike",
                f"Bici km~{DISTANCES['ironman']['bike'] * 0.63 // 1000:.0f}",
                int(80 * _heat_f), int(800 * _heat_f), int(900 * _heat_f),
                "Hora 5. Máxima ingesta antes de transición a run.",
                "2 geles + 800ml isotónico"),
            _cp(_ss["bike"] + _bk_min * 0.80, "bike",
                f"Bici km~{DISTANCES['ironman']['bike'] * 0.8 // 1000:.0f}",
                int(70 * _heat_f), int(700 * _heat_f), int(800 * _heat_f),
                "Reduce sólidos. Solo geles fluidos y bebida.",
                "2 geles + 700ml isotónico"),
            _cp(_ss["t2"],    "t2",   "T2",
                30, 300, 300,
                "Gel + cola en T2. Ajusta medias si hay ampollas.",
                "1 gel · 300ml cola"),
            _cp(_ss["run"] + _rn_min * 0.14, "run",
                f"Run km~{DISTANCES['ironman']['run'] * 0.14 // 1000:.0f}",
                int(45 * _heat_f), int(500 * _heat_f), int(700 * _heat_f),
                "Inicio run muy conservador. Geles + cola en cada puesto.",
                "2 geles + 500ml agua + cola"),
            _cp(_ss["run"] + _rn_min * 0.30, "run",
                f"Run km~{DISTANCES['ironman']['run'] * 0.30 // 1000:.0f}",
                int(40 * _heat_f), int(500 * _heat_f), int(700 * _heat_f),
                "Cola es tu mejor aliada a esta altura. Mezcla agua.",
                "1 gel + 300ml cola + 200ml agua"),
            _cp(_ss["run"] + _rn_min * 0.50, "run",
                f"Run km~{DISTANCES['ironman']['run'] * 0.5 // 1000:.0f}",
                int(35 * _heat_f), int(450 * _heat_f), int(700 * _heat_f),
                "Mitad del run. Alterna cola, agua y sal. Electrolitos si tienes calambres.",
                "Cola + sal + agua · pretzels si los tolerás"),
            _cp(_ss["run"] + _rn_min * 0.70, "run",
                f"Run km~{DISTANCES['ironman']['run'] * 0.7 // 1000:.0f}",
                int(30 * _heat_f), int(400 * _heat_f), int(700 * _heat_f),
                "Modo supervivencia. Caldo de pollo si disponible. Cola + agua.",
                "Caldo pollo + cola + 400ml agua"),
            _cp(_ss["run"] + _rn_min * 0.88, "run",
                f"Run km~{DISTANCES['ironman']['run'] * 0.88 // 1000:.0f}",
                int(20 * _heat_f), int(300 * _heat_f), int(400 * _heat_f),
                "Últimos km. Cola para el sprint final. Cero sólidos.",
                "300ml cola"),
            _cp(_tot_min,     "run",  "META 🏁",
                0, 500, 500,
                "FINISH LINE. Recuperación: isotónico + proteína + sal inmediato.",
                "Isotónico + plátano + batido proteína"),
        ]

    _plan_df = pd.DataFrame(_plan_rows)
    # Cumulative totals
    _plan_df["cum_cho"]   = _plan_df["cho_g"].cumsum()
    _plan_df["cum_fluid"] = _plan_df["fluid_ml"].cumsum()
    _plan_df["cum_na"]    = _plan_df["sodium_mg"].cumsum()
    _plan_df["seg_icon"]  = _plan_df["seg"].map(_SEG_ICON)

    # ── TABS ─────────────────────────────────────────────────────────────────
    _nt1, _nt2, _nt3 = st.tabs(["📊 Resumen", "🕐 Plan Hora a Hora", "📋 Pre-Carrera"])

    # ── TAB 1: Resumen ────────────────────────────────────────────────────────
    with _nt1:
        _rc1, _rc2 = st.columns(2, gap="medium")
        with _rc1:
            _fig_pie = go.Figure(go.Pie(
                labels=["Natación", "Ciclismo", "Corrida"],
                values=[s_kcal, b_kcal, r_kcal],
                marker_colors=[COL_SWIM, COL_BIKE, COL_RUN],
                hole=0.50, textinfo="label+percent", textfont_size=12,
            ))
            _fig_pie.update_layout(showlegend=False,
                                   title_text="Distribución de energía por disciplina",
                                   title_font_size=12)
            st.plotly_chart(chart(_fig_pie, 280, dict(l=0, r=0, t=36, b=0)),
                            use_container_width=True)
        with _rc2:
            _guidelines = {
                "sprint":  (
                    "**CHO:** 30-45 g total  ·  Depende casi 100% del glucógeno almacenado\n\n"
                    "**Fluidos:** 400-600 ml totales · Sin tiempo para hidratarse en nado\n\n"
                    "**Sodio:** Mínimo (~200 mg). El tiempo es muy corto para pérdidas críticas\n\n"
                    "**Estrategia clave:** 1 gel en bici es suficiente. No sobre-nutras: más peso = más lento"
                ),
                "olympic": (
                    "**CHO:** 60-90 g total  ·  1:1 glucosa:fructosa\n\n"
                    "**Fluidos:** 800-1200 ml totales  ·  ~500ml/hr\n\n"
                    "**Sodio:** 400-600 mg total · Bebida isotónica es suficiente\n\n"
                    "**Estrategia clave:** Gel en T1 + gel/barra en bici + gel en run km 3-4. Total: 3-4 geles"
                ),
                "703":     (
                    "**CHO:** 250-360 g total  ·  2:1 glucosa:fructosa obligatorio\n\n"
                    "**Fluidos:** 2.5-3.5 L totales  ·  700ml/hr en bici\n\n"
                    "**Sodio:** 3000-5000 mg  ·  Sal en cada hora de bici\n\n"
                    "**Estrategia clave:** Bici es la ventana de alimentación principal (60-70g/hr). "
                    "Run: máximo geles + cola. Nunca pases >45min sin comer en la bici."
                ),
                "ironman": (
                    "**CHO:** 600-900 g total  ·  2:1 glucosa:fructosa obligatorio (hasta 90g/hr)\n\n"
                    "**Fluidos:** 6-8 L totales  ·  800ml/hr + ajuste por calor\n\n"
                    "**Sodio:** 7000-12000 mg  ·  700-1000mg/hr durante toda la carrera\n\n"
                    "**Estrategia clave:** Come cuando no tengas hambre. Para Ironman el problema "
                    "no es comer demasiado, sino comer muy poco. Bolso especial km 90 bici y km 21 run."
                ),
            }
            st.info(_guidelines[race_sel])
            st.markdown(" ")
            _split_data = [
                ("🏊 Natación", _fmt_dur(pred.swim.time_sec), f"{s_kcal:.0f} kcal", "Sin ingesta"),
                ("🚴 Ciclismo", _fmt_dur(pred.bike.time_sec), f"{b_kcal:.0f} kcal",
                 f"{'~' + str(int(b_kcal * 0.5)) + ' g CHO'} inyectados"),
                ("🏃 Corrida",  _fmt_dur(pred.run.time_sec),  f"{r_kcal:.0f} kcal",
                 "Geles + cola principalmente"),
            ]
            for _icon, _time, _kcal_s, _note in _split_data:
                st.caption(f"**{_icon}**  {_time}  ·  {_kcal_s}  ·  {_note}")

    # ── TAB 2: Plan Hora a Hora ───────────────────────────────────────────────
    with _nt2:
        # ── Chart 1: Race timeline (segment Gantt) ────────────────────────────
        section("Timeline de carrera + puntos de alimentación")
        _seg_defs = [
            ("swim", "🏊 Natación",  _ss["swim"],  _sw_min,  COL_SWIM),
            ("t1",   "T1",           _ss["t1"],    _t1_min,  "#94A3B8"),
            ("bike", "🚴 Ciclismo",  _ss["bike"],  _bk_min,  COL_BIKE),
            ("t2",   "T2",           _ss["t2"],    _t2_min,  "#94A3B8"),
            ("run",  "🏃 Corrida",   _ss["run"],   _rn_min,  COL_RUN),
        ]
        _fig_tl = go.Figure()
        for _sk, _sl, _start, _dur, _col in _seg_defs:
            _fig_tl.add_trace(go.Bar(
                x=[_dur], y=["Carrera"], orientation="h", base=_start,
                marker_color=_col, name=_sl,
                text=f"{_sl} {_fmt_dur(_dur * 60)}", textposition="inside",
                textfont=dict(color="#FFFFFF", size=10, family="Inter"),
                hovertemplate=f"<b>{_sl}</b><br>Inicio: {_start:.0f}min<br>Duración: {_dur:.0f}min<extra></extra>",
            ))
        # Nutrition markers on the timeline
        for _, _row in _plan_df[_plan_df["cho_g"] > 0].iterrows():
            _fig_tl.add_vline(
                x=_row["t_min"], line_dash="dot", line_color="#6366F1", line_width=1.5,
                annotation_text=f"{_row['cho_g']:.0f}g",
                annotation_position="top",
                annotation_font_size=8, annotation_font_color="#6366F1",
            )
        _fig_tl.update_layout(
            barmode="stack",
            xaxis=dict(title="Minutos desde el inicio", showgrid=True,
                       gridcolor="#F1F5F9", ticksuffix="min"),
            yaxis=dict(showticklabels=False),
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            height=130, margin=dict(l=4, r=4, t=32, b=24),
            plot_bgcolor=CARD, paper_bgcolor=CARD,
            font=dict(family="Inter, sans-serif", size=10, color=TEXT2),
        )
        st.plotly_chart(_fig_tl, use_container_width=True)

        st.markdown(" ")

        # ── Chart 2: CHO + Fluids per interval ───────────────────────────────
        section("CHO e Hidratación por intervalo",
                "Barras = CHO (g) · Línea = Fluidos acumulados (ml)")
        _race_rows = _plan_df[_plan_df["seg"] != "pre"].copy()
        _fig_nu = make_subplots(specs=[[{"secondary_y": True}]])
        _bar_colors = [
            {"swim": COL_SWIM, "t1": "#CBD5E1", "bike": COL_BIKE,
             "t2": "#CBD5E1", "run": COL_RUN}.get(r["seg"], ACCENT)
            for _, r in _race_rows.iterrows()
        ]
        _fig_nu.add_trace(go.Bar(
            x=_race_rows["interval"], y=_race_rows["cho_g"],
            name="CHO (g)", marker_color=_bar_colors, opacity=0.85,
            text=_race_rows["cho_g"].apply(lambda v: f"{v}g" if v > 0 else ""),
            textposition="outside", textfont=dict(size=9),
            hovertemplate="<b>%{x}</b><br>CHO: %{y}g<extra></extra>",
        ), secondary_y=False)
        _fig_nu.add_trace(go.Scatter(
            x=_race_rows["interval"], y=_race_rows["cum_fluid"],
            name="Fluidos acum. (ml)", mode="lines+markers",
            line=dict(color=ACCENT, width=2.5),
            marker=dict(size=7, color=ACCENT, line=dict(color="#FFFFFF", width=1.5)),
            hovertemplate="<b>%{x}</b><br>Fluidos acum.: %{y}ml<extra></extra>",
        ), secondary_y=True)
        _fig_nu.update_yaxes(title_text="CHO por intervalo (g)", secondary_y=False,
                              showgrid=True, gridcolor="#F1F5F9")
        _fig_nu.update_yaxes(title_text="Fluidos acumulados (ml)", secondary_y=True,
                              showgrid=False)
        _fig_nu.update_xaxes(showgrid=False, tickangle=-30)
        st.plotly_chart(chart(_fig_nu, 300, dict(l=0, r=0, t=14, b=80)),
                        use_container_width=True)

        st.markdown(" ")

        # ── Detailed plan table ───────────────────────────────────────────────
        section("Plan detallado cronológico", "Datos ajustados por condiciones y sudoración")
        _display_df = _plan_df[["seg_icon", "interval", "cho_g", "fluid_ml",
                                  "sodium_mg", "cum_cho", "cum_fluid", "action",
                                  "examples"]].copy()
        _display_df.columns = [
            "Seg", "Checkpoint", "CHO (g)", "Fluidos (ml)", "Sodio (mg)",
            "CHO acum. (g)", "Fluido acum. (ml)", "Acción", "Ejemplos"
        ]
        st.dataframe(
            _display_df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Seg":              st.column_config.TextColumn(width="small"),
                "Checkpoint":       st.column_config.TextColumn(width="medium"),
                "CHO (g)":          st.column_config.NumberColumn(width="small", format="%d g"),
                "Fluidos (ml)":     st.column_config.NumberColumn(width="small", format="%d ml"),
                "Sodio (mg)":       st.column_config.NumberColumn(width="small", format="%d mg"),
                "CHO acum. (g)":    st.column_config.ProgressColumn(
                                        min_value=0, max_value=int(_plan_df["cum_cho"].max()),
                                        format="%d g", width="medium"),
                "Fluido acum. (ml)":st.column_config.ProgressColumn(
                                        min_value=0, max_value=int(_plan_df["cum_fluid"].max()),
                                        format="%d ml", width="medium"),
                "Acción":           st.column_config.TextColumn(width="large"),
                "Ejemplos":         st.column_config.TextColumn(width="large"),
            }
        )

        st.markdown(" ")
        # Totals summary row
        _tot_cols = st.columns(4, gap="medium")
        _tot_cols[0].metric("CHO total plan",   f"{int(_plan_df['cho_g'].sum())} g",
                             f"Rec: {_cho_total} g")
        _tot_cols[1].metric("Fluidos total",     f"{int(_plan_df['fluid_ml'].sum())} ml",
                             f"Rec: {_fl_total} ml")
        _tot_cols[2].metric("Sodio total",       f"{int(_plan_df['sodium_mg'].sum())} mg",
                             f"Rec: {_sod_total} mg")
        _tot_cols[3].metric("Checkpoints",       f"{len(_plan_df)} puntos",
                             f"c/ ~{_tot_min/len(_plan_df):.0f} min")

    # ── TAB 3: Pre-Carrera ────────────────────────────────────────────────────
    with _nt3:
        _pre_race_plans = {
            "sprint": [
                ("T-24h (día anterior)",    "Cena normal",
                 "Pasta/arroz 80g seco + proteína + verdura",
                 "6-7 g CHO/kg peso corporal. Sin cambios radicales en la dieta.",
                 "#F1F5F9"),
                ("T-3h",                    "Desayuno pre-carrera",
                 "Avena 60g + plátano + café · 2-3 tostadas con mermelada",
                 "60-90g CHO. Bajo en fibra y grasa. Conocido y probado en entrenamientos.",
                 "#FFFFFF"),
                ("T-60min",                 "Snack ligero",
                 "Barra de arroz o banana pequeña (25g CHO)",
                 "Opcional si el desayuno fue pequeño. Evita azúcares simples sin fibra.",
                 "#F1F5F9"),
                ("T-30min",                 "Hidratación activa",
                 "400-500ml agua o isotónico diluido",
                 "Objetivo: orina amarillo pálido. No tomar más de 500ml para evitar necesidad de baño.",
                 "#FFFFFF"),
                ("T-15min",                 "Gel de activación (opcional)",
                 "1 gel cafeína (100mg) si usas cafeína en entrenos",
                 "Solo si está probado en entrenamiento. No probar nada nuevo el día de carrera.",
                 "#F1F5F9"),
                ("T-0 (línea de salida)",   "Lista final",
                 "Gel en bolsillo listo. Botella montada en bici. Últimos 100ml agua.",
                 "Revisa: electrolitos guardados, geles accesibles, bidón lleno.",
                 "#EFF6FF"),
            ],
            "olympic": [
                ("T-24h (día anterior)",    "Carga suave de carbohidratos",
                 "Arroz/pasta 100g seco + pollo + verdura cocida. Cena temprana.",
                 "7-8 g CHO/kg. Evita alimentos nuevos, picantes o con alto contenido en fibra.",
                 "#F1F5F9"),
                ("T-12h (noche anterior)",  "Snack nocturno",
                 "Yogur + miel + plátano (30g CHO)",
                 "Opcional. Útil si la carrera es muy temprano y el desayuno será pequeño.",
                 "#FFFFFF"),
                ("T-3h",                    "Desayuno pre-carrera",
                 "Avena 80g + miel + plátano + café · o arroz con mermelada",
                 "90-120g CHO. Bajo en fibra. Probado en entrenamientos largos previos.",
                 "#F1F5F9"),
                ("T-60min",                 "Snack CHO",
                 "Barra energética o 2 tostadas con miel (40-50g CHO)",
                 "Mantiene glucosa estable sin sobrecargar. Con ~250ml agua.",
                 "#FFFFFF"),
                ("T-30min",                 "Hidratación pre-race",
                 "500ml isotónico diluido (50%) + sal si hace calor",
                 "Si temperatura >22°C: añade 500mg sal. No más de 500ml.",
                 "#F1F5F9"),
                ("T-15min",                 "Gel de activación + cafeína",
                 "1 gel cafeína (SIS Caffeine, GU Roctane) 22g CHO + 75mg cafeína",
                 "Activa el sistema nervioso. Timing preciso: 15min antes del agua.",
                 "#FFFFFF"),
                ("T-0 (línea de salida)",   "Checklist final",
                 "2 geles accesibles · bidón lleno · sal en bolsillo · últimos 100ml",
                 "Revisa que el bidón esté en porta-bidón. Posición cinta de corazón.",
                 "#EFF6FF"),
            ],
            "703": [
                ("T-48h (2 días antes)",    "Inicio carga de carbohidratos",
                 "8-10 g CHO/kg/día. Arroz, pasta, pan, plátanos, jugos. Reduce entrenamiento.",
                 "Satura glucógeno muscular y hepático. Reduce grasas y fibra estos 2 días.",
                 "#F1F5F9"),
                ("T-24h",                   "Cena carga final",
                 "Pasta/arroz 150g seco + pollo 200g + aceite oliva + pan",
                 "Última gran comida. Cena temprana (no después de las 20h). Sin alcohol.",
                 "#FFFFFF"),
                ("T-4h",                    "Desayuno pre-carrera",
                 "Arroz 120g + miel + plátano 2 uds + café con leche · o avena especial",
                 "140-180g CHO. Conocido. Sin fibra, sin grasa. Tiempo suficiente para digestión.",
                 "#F1F5F9"),
                ("T-2h",                    "Snack de mantenimiento",
                 "Barra energética o arroz con miel (60g CHO) + 300ml agua",
                 "Evita el bajón de glucosa en la espera. Solo si toleras bien.",
                 "#FFFFFF"),
                ("T-60min",                 "Hidratación activa",
                 "500-600ml isotónico completo + 500mg sal extra si caluroso",
                 "Orina amarillo pálido. Ajusta sodio según temperatura.",
                 "#F1F5F9"),
                ("T-30min",                 "Gel + electrolitos",
                 "1 gel Maurten 100 + 1 pastilla electrolítica (Precision Hydration/SIS)",
                 "Últimos CHO antes del agua. La cápsula de sodio puede reducir calambres.",
                 "#FFFFFF"),
                ("T-15min",                 "Gel de activación",
                 "1 gel cafeína (100mg) · últimos 200ml agua",
                 "Si usas cafeína: timing perfecto para pico en inicio de bici.",
                 "#F1F5F9"),
                ("T-0 (línea de salida)",   "Checklist final 70.3",
                 "3 geles en bolsillos · 2 bidones llenos (1 isotónico, 1 agua) · sal tabs · bolso especial preparado",
                 "Bolso especial: 3 geles + barra + 2 salt tabs + cambio calcetines.",
                 "#EFF6FF"),
            ],
            "ironman": [
                ("T-72h (3 días antes)",    "Inicio protocolo carga",
                 "8-10 g CHO/kg/día. Arroz, pasta, pan, plátanos, jugos, batatas.",
                 "Reducción de entrenamiento (taper). Hydra extra: 1ml/kcal consumida.",
                 "#F1F5F9"),
                ("T-48h",                   "Día carga alta",
                 "10 g CHO/kg mínimo. Cada comida incluye CHO: desayuno/almuerzo/cena + snacks",
                 "Evita grasas saturadas, fibra >30g, alcohol. Puede haber hinchazón: es normal (glucógeno = agua).",
                 "#FFFFFF"),
                ("T-24h",                   "Cena pre-race clásica",
                 "Pasta 200g seco + salsa tomate simple + pollo 200g + pan + arroz con leche",
                 "Sin sorpresas. Nada nuevo. Sin picante. Sin mariscos. Cena antes de las 19h.",
                 "#F1F5F9"),
                ("T-5h",                    "Desayuno Ironman",
                 "Avena 150g + 3 plátanos + 2 rebanadas pan miel + 2 cafés con leche + zumo",
                 "200-250g CHO. El desayuno más grande del año. Tiempo amplio para digestión.",
                 "#FFFFFF"),
                ("T-3h",                    "Snack intermedio",
                 "Barra de arroz casera 80g CHO · o 2 plátanos + miel + tostada",
                 "Mantiene glucosa sin sobrecargar. Con 400ml isotónico diluido.",
                 "#F1F5F9"),
                ("T-90min",                 "Hydra activa",
                 "600ml isotónico completo + pastilla sodio (500-1000mg)",
                 "Ajusta según temperatura. >28°C: añade 1000mg sodio.",
                 "#FFFFFF"),
                ("T-45min",                 "Gel + salt tabs",
                 "2 geles Maurten 100 (50g CHO) + 2 salt tabs Precision Hydration",
                 "Carga final de CHO. El sodio extra ayuda a retener fluidos iniciales.",
                 "#F1F5F9"),
                ("T-20min",                 "Gel cafeína",
                 "1 gel cafeína 150mg (GU Roctane / Maurten caffeína) + 150ml agua",
                 "Timing para pico en inicio de bici (~90min post-ingesta).",
                 "#FFFFFF"),
                ("T-0 (línea de salida)",   "Checklist final IRONMAN",
                 "Bici: 2 bidones (Maurten 320) + barra sólida · Bolso especial: 4 geles + 2 barras + 4 salt tabs + vaseline + cambio calcetines",
                 "Transición especial (km 90 bici / km 21 run): verifica que el bolso llegó antes que tú.",
                 "#EFF6FF"),
            ],
        }

        section("Protocolo Pre-Carrera",
                f"{RACE_LABELS[race_sel]} — {pred.total_display} estimado")
        st.markdown(" ")

        for _timing, _category, _food, _note, _bg in _pre_race_plans[race_sel]:
            _is_start = "T-0" in _timing
            with st.container():
                _pc1, _pc2, _pc3 = st.columns([1.2, 2, 3])
                _pc1.markdown(
                    f"**{'🏁 ' if _is_start else ''}{_timing}**"
                )
                _pc2.markdown(f"*{_category}*")
                _pc3.markdown(f"**{_food}**")
                if _note:
                    st.caption(f"↳ {_note}")
                st.divider()

        st.markdown(" ")
        st.info(
            f"**📌 Regla de oro para {RACE_LABELS[race_sel]}:**  "
            f"No pruebes nada nuevo el día de la carrera. "
            f"Toda la estrategia nutricional debe estar practicada en entrenamientos largos. "
            f"Coloca los geles en el mismo lugar siempre (bolsillo jersey, tri-suit, aero-bag)."
        )


# ══════════════════════════════════════════════════════════════════════════════
# 👤 ATHLETE PROFILE
# ══════════════════════════════════════════════════════════════════════════════
elif page == "👤 Athlete Profile":
    import json as _json

    # Load current values
    _p = load_profile()

    # ── KPI summary (top) ─────────────────────────────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("FTP",            f"{int(_p['ftp_w'])} W")
    k2.metric("Weight",         f"{_p['weight_kg']:.1f} kg")
    k3.metric("Run threshold",  f"{_p['threshold_run']}/km")
    k4.metric("CSS Swim",       f"{_p['css_swim']}/100m")
    k5.metric("VO₂Max Bike",    f"{_p['vo2max_bike']:.0f}")

    st.markdown(" ")

    # ── Edit form ─────────────────────────────────────────────────────────────
    with st.form("profile_form"):
        section("Personal")
        p1, p2, p3, p4 = st.columns(4)
        e_name   = p1.text_input("Full name",     value=_p["name"])
        e_age    = p2.number_input("Age",          1, 99,  int(_p["age"]))
        e_weight = p3.number_input("Weight (kg)",  30.0, 120.0, float(_p["weight_kg"]), 0.5)
        e_height = p4.number_input("Height (cm)",  100, 220, int(_p["height_cm"]))

        st.markdown(" ")
        section("Performance benchmarks")
        b1, b2, b3 = st.columns(3)
        e_ftp   = b1.number_input("FTP (W)",            100, 500, int(_p["ftp_w"]))
        e_trun  = b2.text_input("Run threshold (/km)",  value=_p["threshold_run"],
                                 help="Pace at lactate threshold, e.g. 4:20")
        e_tswim = b3.text_input("CSS Swim (/100m)",     value=_p["css_swim"],
                                 help="Critical Swim Speed, e.g. 1:50")

        b4, b5, b6 = st.columns(3)
        e_vo2r  = b4.number_input("VO₂Max Run",   20.0, 90.0, float(_p["vo2max_run"]), 0.5)
        e_vo2b  = b5.number_input("VO₂Max Bike",  20.0, 90.0, float(_p["vo2max_bike"]), 0.5)
        e_lthr  = b6.number_input("LTHR (bpm)",   100, 220, int(_p["lthr"]))

        st.markdown(" ")
        section("Goals")
        g1, g2 = st.columns(2)
        e_race  = g1.selectbox("Target race", ["sprint","olympic","703","ironman"],
                                index=["sprint","olympic","703","ironman"].index(_p.get("target_race","703")),
                                format_func=lambda k: RACE_LABELS.get(k, k))
        e_tdate = g2.text_input("Target date", value=_p.get("target_date",""),
                                 placeholder="e.g.  2025-10-12")

        st.markdown(" ")
        section("Notes")
        e_notes = st.text_area("Coach / personal notes", value=_p.get("notes",""), height=80)

        st.markdown(" ")
        saved = st.form_submit_button("💾  Save Profile", use_container_width=False)

    if saved:
        new_prof = {
            "name":          e_name,
            "age":           int(e_age),
            "weight_kg":     float(e_weight),
            "height_cm":     int(e_height),
            "ftp_w":         int(e_ftp),
            "threshold_run": e_trun,
            "css_swim":      e_tswim,
            "vo2max_run":    float(e_vo2r),
            "vo2max_bike":   float(e_vo2b),
            "lthr":          int(e_lthr),
            "target_race":   e_race,
            "target_date":   e_tdate,
            "notes":         e_notes,
            "garmin_email":  _p.get("garmin_email",""),
        }
        save_profile(new_prof)
        st.success("Profile saved — changes will apply on next page load.")
        st.rerun()

    # ── Training zones (auto-calculated) ──────────────────────────────────────
    st.markdown(" ")
    st.divider()
    section("Training Zones", "Calculated from your benchmarks")

    z_col1, z_col2, z_col3 = st.columns(3, gap="medium")

    with z_col1:
        st.markdown("**🚴 Bike Power Zones** (FTP based)")
        zones_bike = power_zones(ftp)
        rows_b = []
        for zname, (lo, hi) in zones_bike.items():
            hi_str = f"{hi:.0f}" if hi < 9999 else "MAX"
            rows_b.append({"Zone": zname, "Range (W)": f"{lo:.0f} – {hi_str}"})
        st.dataframe(pd.DataFrame(rows_b), hide_index=True, use_container_width=True)

    with z_col2:
        st.markdown("**🏃 Run Pace Zones** (threshold based)")
        thr_s = _parse_pace(t_run)
        run_zones = [
            ("Z1 Recovery",   thr_s * 1.30, 9999),
            ("Z2 Base",       thr_s * 1.15, thr_s * 1.30),
            ("Z3 Tempo",      thr_s * 1.05, thr_s * 1.15),
            ("Z4 Threshold",  thr_s * 0.98, thr_s * 1.05),
            ("Z5 VO₂Max",     0,             thr_s * 0.98),
        ]
        rows_r = []
        for zname, lo, hi in run_zones:
            lo_s = _fmt_pace(lo) if lo > 0 else "—"
            hi_s = _fmt_pace(hi) if hi < 9999 else "MAX"
            rows_r.append({"Zone": zname, "Pace (/km)": f"{lo_s} – {hi_s}"})
        st.dataframe(pd.DataFrame(rows_r), hide_index=True, use_container_width=True)

    with z_col3:
        st.markdown("**🏊 Swim Pace Zones** (CSS based)")
        css_s = _parse_pace(t_swim, 110.0)
        swim_zones = [
            ("Z1 Recovery",   css_s * 1.20, 9999),
            ("Z2 Base",       css_s * 1.08, css_s * 1.20),
            ("Z3 Threshold",  css_s * 0.97, css_s * 1.08),
            ("Z4 Race Pace",  css_s * 0.90, css_s * 0.97),
            ("Z5 Speed",      0,             css_s * 0.90),
        ]
        rows_s = []
        for zname, lo, hi in swim_zones:
            lo_s = _fmt_pace(lo) if lo > 0 else "—"
            hi_s = _fmt_pace(hi) if hi < 9999 else "MAX"
            rows_s.append({"Zone": zname, "Pace (/100m)": f"{lo_s} – {hi_s}"})
        st.dataframe(pd.DataFrame(rows_s), hide_index=True, use_container_width=True)

    # ── HR zones ──────────────────────────────────────────────────────────────
    st.markdown(" ")
    lthr_val = int(_p["lthr"])
    st.markdown(f"**❤️ HR Zones** (LTHR {lthr_val} bpm)")
    hr_zones = [
        ("Z1 Recovery",   int(lthr_val * 0.68), int(lthr_val * 0.75)),
        ("Z2 Base",       int(lthr_val * 0.75), int(lthr_val * 0.82)),
        ("Z3 Tempo",      int(lthr_val * 0.82), int(lthr_val * 0.89)),
        ("Z4 Threshold",  int(lthr_val * 0.89), int(lthr_val * 0.97)),
        ("Z5 VO₂Max",     int(lthr_val * 0.97), int(lthr_val * 1.05)),
    ]
    hc = st.columns(5)
    for i, (zname, lo, hi) in enumerate(hr_zones):
        hc[i].metric(zname, f"{lo}–{hi}", "bpm")


# ══════════════════════════════════════════════════════════════════════════════
# 🏆 RACE PREDICTOR
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🏆 Race Predictor":
    section("Model", "Physics bike · Riegel · T2 fatigue")
    st.markdown(" ")

    preds = predictor.predict_all()
    dist_lbl = {
        "sprint":  "750m · 20km · 5km",
        "olympic": "1.5km · 40km · 10km",
        "703":     "1.9km · 90km · 21km",
        "ironman": "3.8km · 180km · 42km",
    }
    cols = st.columns(4, gap="medium")
    for i, (key, label) in enumerate(RACE_LABELS.items()):
        p = preds[key]
        cols[i].metric(
            f"{label}  ·  {dist_lbl[key]}",
            p.total_display,
            f"IF {p.bike.target_if:.2f} · {p.bike.target_power}W NP",
        )

    st.markdown(" ")
    section("Split Detail", "Swim · T1 · Bike · T2 · Run")
    rows = []
    for key, label in RACE_LABELS.items():
        p = preds[key]
        rows.append({
            "Race": label,
            "Swim": p.swim.time_display, "Swim Pace": p.swim.pace_display,
            "T1": "4:00",
            "Bike": p.bike.time_display, "Bike Pace": p.bike.pace_display,
            "IF": f"{p.bike.target_if:.2f}", "NP": f"{p.bike.target_power}W",
            "T2": "2:00",
            "Run": p.run.time_display,  "Run Pace": p.run.pace_display,
            "Total": p.total_display,
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    st.markdown(" ")
    tab1, tab2 = st.tabs(["📊 FTP Sensitivity", "🧱 Brick Simulator"])

    with tab1:
        c1, _ = st.columns([1, 2])
        dist_sens = c1.selectbox("Distance", list(RACE_LABELS.keys()), index=2,
                                  format_func=lambda k: RACE_LABELS[k])
        st.dataframe(predictor.sensitivity_table(dist_sens),
                     hide_index=True, use_container_width=True)

    with tab2:
        from utils.formulas import run_fatigue_factor
        b1, b2 = st.columns(2)
        sim_dist = b1.selectbox("Race", ["olympic", "703", "ironman"],
                                 format_func=lambda k: RACE_LABELS[k])
        rec_if = RECOMMENDED_IF[sim_dist]["bike"]
        sim_if = b2.slider(f"Bike IF  (rec {rec_if:.2f})", 0.60, 0.95, rec_if, 0.01)
        fat = run_fatigue_factor(sim_if, sim_dist)
        base = _parse_pace(t_run)
        deg = base * fat
        diff = deg - base
        dm, ds = int(diff) // 60, int(diff) % 60
        b3, b4, b5 = st.columns(3)
        b3.metric("Bike IF",   f"{sim_if:.2f}", "✓ OK" if sim_if <= rec_if + 0.03 else "⚠ Over")
        b4.metric("Run Pace",  f"{_fmt_pace(deg)}/km", f"+{dm}:{ds:02d} vs solo")
        b5.metric("Fatigue",   f"x{fat:.3f}")
        if sim_if > rec_if + 0.03:
            st.warning(f"⚠ IF {sim_if:.2f} > recommended {rec_if:.2f} for {RACE_LABELS[sim_dist]}. Run will suffer.")


# ══════════════════════════════════════════════════════════════════════════════
# 🩸 BLOOD LABS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🩸 Blood Labs":
    _bt = _load_blood_tests()
    if not _bt or not _bt.get("exams"):
        st.info("No blood test data found. Add exams to `data/blood_tests.json`.")
        st.stop()

    _bm    = _bt["biomarkers"]
    _exams = sorted(_bt["exams"], key=lambda e: e["date"])
    _latest = _exams[-1]
    _prev   = _exams[-2] if len(_exams) >= 2 else None

    # ── Build tidy DataFrame for trend charts ─────────────────────────────────
    _bt_rows = []
    for _e in _exams:
        _row = {"date": pd.to_datetime(_e["date"]), "context": _e.get("context", "")}
        _row.update(_e["values"])
        _bt_rows.append(_row)
    _bt_df = pd.DataFrame(_bt_rows).sort_values("date").reset_index(drop=True)
    _exam_dates = _bt_df["date"].tolist()

    # ── Helper: score a single marker 0-100 ───────────────────────────────────
    def _score(val, key):
        if val is None or key not in _bm:
            return None
        bm    = _bm[key]
        lo, hi = bm["ref_low"], bm["ref_high"]
        d     = bm.get("direction", "range")
        if d == "lower":
            if val <= hi * 0.50: return 96
            if val <= hi * 0.75: return 86
            if val <= hi:        return 72
            if val <= hi * 1.25: return 45
            return 20
        elif d == "higher":
            if val >= lo * 1.30: return 96
            if val >= lo * 1.15: return 88
            if val >= lo:        return 72
            if val >= lo * 0.85: return 50
            return 28
        else:
            mid  = (lo + hi) / 2
            half = (hi - lo) / 2 or 1
            if lo <= val <= hi:
                return round(max(80, 100 - abs(val - mid) / half * 20))
            elif val < lo:
                return max(0, round(70 - (lo - val) / half * 55))
            else:
                return max(0, round(70 - (val - hi) / half * 55))

    # ── Helper: ref range label ────────────────────────────────────────────────
    def _ref_label(key):
        bm = _bm[key]
        lo, hi, d = bm["ref_low"], bm["ref_high"], bm.get("direction", "range")
        if d == "lower":  return f"< {hi:.0f}"
        if d == "higher": return f"> {lo:.0f}"
        lo_str = f"{lo:.0f}" if lo == int(lo) else str(lo)
        hi_str = f"{hi:.0f}" if hi == int(hi) else str(hi)
        return f"{lo_str} – {hi_str}"

    # ── Helper: status badge ───────────────────────────────────────────────────
    def _status_badge(val, key):
        if val is None: return "—"
        bm = _bm[key]
        lo, hi = bm["ref_low"], bm["ref_high"]
        d  = bm.get("direction", "range")
        if d == "lower":
            if val > hi:           return "🔴 Alto"
            if val > hi * 0.85:    return "🟡 Límite"
            return "✅ OK"
        elif d == "higher":
            if val < lo:           return "🔴 Bajo"
            if val < lo * 1.10:    return "🟡 Límite"
            return "✅ OK"
        else:
            if val < lo or val > hi:        return "🔴 Fuera rango"
            if val < lo * 1.08 or val > hi * 0.92: return "🟡 Límite"
            return "✅ Normal"

    # ── Helper: render a trend line chart for a list of marker keys ────────────
    def _trend_chart(keys, title, height=300):
        cols_available = [k for k in keys if k in _bt_df.columns]
        if not cols_available:
            st.caption("Sin datos para esta categoría.")
            return
        section(title)
        # one chart per marker so each gets its own y-axis + ref band
        ncols = min(2, len(cols_available))
        grid  = st.columns(ncols, gap="medium")
        for idx, key in enumerate(cols_available):
            bm  = _bm.get(key, {})
            lbl = bm.get("label", key)
            unit = bm.get("unit", "")
            lo  = bm.get("ref_low", None)
            hi  = bm.get("ref_high", None)
            d   = bm.get("direction", "range")
            vals = _bt_df[["date", key]].dropna(subset=[key])
            with grid[idx % ncols]:
                fig = go.Figure()
                # Reference band
                if lo is not None and hi is not None and d == "range":
                    fig.add_hrect(y0=lo, y1=hi,
                                  fillcolor="rgba(16,185,129,0.08)",
                                  line_width=0,
                                  annotation_text=f"Ref {_ref_label(key)} {unit}",
                                  annotation_position="top right",
                                  annotation_font_size=9,
                                  annotation_font_color="#64748B")
                elif hi is not None and d == "lower":
                    fig.add_hline(y=hi, line_dash="dot", line_color="#EF4444",
                                  annotation_text=f"Límite {hi} {unit}",
                                  annotation_font_size=9)
                elif lo is not None and d == "higher":
                    fig.add_hline(y=lo, line_dash="dot", line_color="#EF4444",
                                  annotation_text=f"Mín {lo} {unit}",
                                  annotation_font_size=9)
                # Data line
                line_color = "#3B82F6" if len(vals) < 2 else (
                    "#10B981" if float(vals[key].iloc[-1]) >= float(vals[key].iloc[0])
                    else "#EF4444"
                )
                fig.add_trace(go.Scatter(
                    x=vals["date"], y=vals[key],
                    mode="lines+markers+text",
                    line=dict(color=line_color, width=2.5),
                    marker=dict(size=10, color=line_color,
                                line=dict(color="#FFFFFF", width=2)),
                    text=[f"{v}" for v in vals[key]],
                    textposition="top center",
                    textfont=dict(size=11, color=line_color),
                    name=lbl,
                    hovertemplate=f"<b>{lbl}</b><br>%{{x|%d %b %Y}}<br>%{{y}} {unit}<extra></extra>",
                ))
                fig.update_xaxes(showgrid=False, tickformat="%b %Y")
                fig.update_yaxes(title_text=unit, showgrid=True,
                                 gridcolor="#F1F5F9")
                st.plotly_chart(chart(fig, height, dict(l=0, r=8, t=22, b=0)),
                                use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════════
    # KPI COMPUTATION (used across tabs)
    # ══════════════════════════════════════════════════════════════════════════
    lv = _latest["values"]

    # KPI 1 — Recuperación Muscular (CK + LDH)
    _ck_s   = _score(lv.get("ck"),  "ck")
    _ldh_s  = _score(lv.get("ldh"), "ldh")
    _scores_muscle = [s for s in [_ck_s, _ldh_s] if s is not None]
    _kpi_muscle = round(sum(_scores_muscle) / len(_scores_muscle)) if _scores_muscle else None

    # KPI 2 — Transporte de O2 (Hb + Hct)
    _hb_s   = _score(lv.get("hemoglobina"),  "hemoglobina")
    _hct_s  = _score(lv.get("hematocrito"),  "hematocrito")
    _eri_s  = _score(lv.get("eritrocitos"),  "eritrocitos")
    _scores_o2 = [s for s in [_hb_s, _hct_s, _eri_s] if s is not None]
    _kpi_o2 = round(sum(_scores_o2) / len(_scores_o2)) if _scores_o2 else None

    # KPI 3 — Micronutrientes & Hormonal (VitD + B12 + TSH)
    _vitd_s = _score(lv.get("vitamina_d"),   "vitamina_d")
    _b12_s  = _score(lv.get("vitamina_b12"), "vitamina_b12")
    _tsh_s  = _score(lv.get("tsh"),          "tsh") if lv.get("tsh") else None
    _scores_micro = [s for s in [_vitd_s, _b12_s, _tsh_s] if s is not None]
    _kpi_micro = round(sum(_scores_micro) / len(_scores_micro)) if _scores_micro else None

    def _score_label(s):
        if s is None: return ("Sin datos", "#94A3B8")
        if s >= 88:   return ("Excelente",   "#10B981")
        if s >= 74:   return ("Bueno",       "#3B82F6")
        if s >= 58:   return ("Monitorear",  "#F59E0B")
        if s >= 42:   return ("Atención",    "#F97316")
        return             ("Alerta",        "#EF4444")

    # Notable changes (|Δ%| > 12%) for alerts
    _alerts = []
    if _prev:
        pv = _prev["values"]
        for _k, _bm_def in _bm.items():
            _v_new = lv.get(_k)
            _v_old = pv.get(_k)
            if _v_new is None or _v_old is None or _v_old == 0:
                continue
            _delta_pct = (_v_new - _v_old) / abs(_v_old) * 100
            if abs(_delta_pct) > 12:
                _direction = "sube" if _delta_pct > 0 else "baja"
                _icon = "📈" if _delta_pct > 0 else "📉"
                _bm_dir = _bm_def.get("direction", "range")
                # Determine if this direction is concerning
                _concern = (
                    (_bm_dir == "higher" and _delta_pct < 0) or
                    (_bm_dir == "lower"  and _delta_pct > 0) or
                    (_bm_dir == "range"  and abs(_delta_pct) > 18)
                )
                _alerts.append({
                    "key": _k,
                    "label": _bm_def["label"],
                    "old": _v_old,
                    "new": _v_new,
                    "delta_pct": _delta_pct,
                    "icon": _icon,
                    "concern": _concern,
                    "unit": _bm_def["unit"],
                })
        _alerts.sort(key=lambda a: abs(a["delta_pct"]), reverse=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TABS
    # ══════════════════════════════════════════════════════════════════════════
    _t1, _t2, _t3, _t4 = st.tabs(["🏥 Resumen Clínico", "📈 Tendencias", "🔗 Correlación Garmin", "📥 Importar Examen"])

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 1 — RESUMEN CLÍNICO
    # ─────────────────────────────────────────────────────────────────────────
    with _t1:
        # ── Exam metadata strip ───────────────────────────────────────────────
        _lbl1, _lbl2 = f"Último: **{_latest['date']}**", (f"Anterior: **{_prev['date']}**" if _prev else "Sin examen anterior")
        st.caption(f"{_lbl1}  ·  {_lbl2}  ·  {_latest.get('context','')}")
        st.markdown(" ")

        # ── 3 KPI cards ───────────────────────────────────────────────────────
        section("Indicadores Clave de Rendimiento", "Basados en último examen")
        _ka, _kb, _kc = st.columns(3, gap="medium")

        def _kpi_card(col, title, score, icon, lines):
            _lbl, _col = _score_label(score)
            col.metric(f"{icon}  {title}",
                       f"{score} / 100" if score else "—",
                       f"{_lbl}")
            for _ln in lines:
                col.caption(_ln)

        _kpi_card(_ka, "Recuperación Muscular", _kpi_muscle, "💪",
                  [f"CK: {lv.get('ck','—')} U/L  ·  LDH: {lv.get('ldh','—')} U/L",
                   "CK refleja daño muscular post-esfuerzo"])
        _kpi_card(_kb, "Transporte de Oxígeno", _kpi_o2, "🫀",
                  [f"Hb: {lv.get('hemoglobina','—')} g/dL  ·  Hct: {lv.get('hematocrito','—')}%",
                   f"Eritrocitos: {lv.get('eritrocitos','—')} ×10⁶/µL"])
        _kpi_card(_kc, "Micronutrientes", _kpi_micro, "🧬",
                  [f"Vit D: {lv.get('vitamina_d','—')} ng/mL  ·  B12: {lv.get('vitamina_b12','—')} pg/mL",
                   f"TSH: {lv.get('tsh','—')} uU/mL"])

        st.markdown(" ")

        # ── Alerts ────────────────────────────────────────────────────────────
        if _alerts:
            section("Variaciones Notables", f"Δ > 12% entre {_prev['date'] if _prev else '—'} y {_latest['date']}")
            _alert_concern  = [a for a in _alerts if a["concern"]]
            _alert_positive = [a for a in _alerts if not a["concern"]]

            if _alert_concern:
                _msg = "  ·  ".join(
                    f"**{a['label']}** {a['icon']} {a['old']} → {a['new']} {a['unit']} ({a['delta_pct']:+.1f}%)"
                    for a in _alert_concern[:4]
                )
                st.warning(f"⚠️ Requiere atención:  {_msg}")
            if _alert_positive:
                _msg = "  ·  ".join(
                    f"**{a['label']}** {a['icon']} {a['old']} → {a['new']} {a['unit']} ({a['delta_pct']:+.1f}%)"
                    for a in _alert_positive[:4]
                )
                st.success(f"✅ Mejoras registradas:  {_msg}")

        st.markdown(" ")

        # ── Full biomarker table ──────────────────────────────────────────────
        section("Tabla Completa de Biomarcadores")
        _cat_order = ["hemograma", "muscular", "lipidos", "enzimas",
                      "renal", "bioquimica", "vitaminas", "electrolitos", "hormonal"]
        _cat_labels = {
            "hemograma":    "🩸 Hemograma",
            "muscular":     "💪 Muscular",
            "lipidos":      "🫀 Perfil Lipídico",
            "enzimas":      "⚗️ Enzimas",
            "renal":        "🫘 Función Renal",
            "bioquimica":   "🔬 Bioquímica",
            "vitaminas":    "🌟 Vitaminas",
            "electrolitos": "⚡ Electrolitos",
            "hormonal":     "🧪 Hormonal",
        }
        for _cat in _cat_order:
            _cat_keys = [k for k, v in _bm.items() if v.get("category") == _cat]
            _cat_rows = []
            for _k in _cat_keys:
                _bm_def = _bm[_k]
                _v_new  = lv.get(_k)
                _v_old  = _prev["values"].get(_k) if _prev else None
                if _v_new is None and _v_old is None:
                    continue
                _delta_str = "—"
                if _v_new is not None and _v_old is not None and _v_old != 0:
                    _dp = (_v_new - _v_old) / abs(_v_old) * 100
                    _arrow = "▲" if _dp > 0 else "▼"
                    _delta_str = f"{_arrow} {abs(_dp):.1f}%"
                _cat_rows.append({
                    "Marcador":         _bm_def["label"],
                    "Referencia":       _ref_label(_k) + f" {_bm_def['unit']}",
                    _prev["date"] if _prev else "Anterior":  _v_old if _v_old is not None else "—",
                    _latest["date"]:    _v_new if _v_new is not None else "—",
                    "Δ":               _delta_str,
                    "Estado":          _status_badge(_v_new, _k),
                })
            if _cat_rows:
                with st.expander(_cat_labels.get(_cat, _cat), expanded=(_cat in ["hemograma", "muscular", "vitaminas"])):
                    st.dataframe(pd.DataFrame(_cat_rows), hide_index=True,
                                 use_container_width=True)

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 2 — TENDENCIAS
    # ─────────────────────────────────────────────────────────────────────────
    with _t2:
        st.caption(f"Evolución temporal  ·  {len(_exams)} exámenes  ·  {_exam_dates[0].strftime('%b %Y')} → {_exam_dates[-1].strftime('%b %Y')}")
        st.markdown(" ")

        _trend_cats = st.tabs([
            "🩸 Hemograma", "💪 Muscular", "🫀 Lípidos",
            "🌟 Vitaminas", "🫘 Renal", "🧪 Hormonal", "⚡ Electrolitos",
        ])

        with _trend_cats[0]:
            _trend_chart(["hemoglobina", "hematocrito"],  "Hemoglobina & Hematocrito", 280)
            st.markdown(" ")
            _trend_chart(["eritrocitos", "leucocitos", "plaquetas"], "Series Celulares", 260)
            st.markdown(" ")
            _trend_chart(["vcm", "hcm", "chcm"], "Índices Eritrocitarios", 250)
            st.markdown(" ")
            _trend_chart(["sedimentacion"], "Sedimentación (Inflamación)", 230)

        with _trend_cats[1]:
            _trend_chart(["ck", "ldh"], "CK & LDH — Marcadores Musculares", 300)
            st.markdown(" ")
            _trend_chart(["got_ast", "gpt_alt", "ggt", "fosfatasas_alc"],
                         "Enzimas Hepáticas & Musculares", 280)

        with _trend_cats[2]:
            _trend_chart(["colesterol_total", "hdl", "ldl"], "Perfil de Colesterol", 300)
            st.markdown(" ")
            _trend_chart(["trigliceridos", "ac_urico"], "Triglicéridos & Ácido Úrico", 260)

        with _trend_cats[3]:
            _trend_chart(["vitamina_d", "vitamina_b12"], "Vitaminas D & B12", 300)

        with _trend_cats[4]:
            _trend_chart(["creatinina", "tfge"], "Creatinina & TFGe", 280)
            st.markdown(" ")
            _trend_chart(["nitrogeno_ureico", "urea"], "Nitrógeno Ureico & Urea", 260)

        with _trend_cats[5]:
            _trend_chart(["tsh", "ft4"], "Tiroides — TSH & FT4", 280)
            st.markdown(" ")
            _trend_chart(["psa_total"], "PSA Total", 230)

        with _trend_cats[6]:
            _trend_chart(["na", "k", "cl"], "Sodio, Potasio & Cloro", 280)
            st.markdown(" ")
            _trend_chart(["calcio", "fosforo"], "Calcio & Fósforo", 260)

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 3 — CORRELACIÓN GARMIN
    # ─────────────────────────────────────────────────────────────────────────
    with _t3:
        st.caption("Superposición de biomarcadores con métricas Garmin Connect")
        st.markdown(" ")

        # ── 1. CK / LDH vs ATL ───────────────────────────────────────────────
        section("Marcadores Musculares vs Carga Aguda (ATL)",
                "CK & LDH medidos en fechas de examen superpuestos con ATL")

        _ck_atl_pairs, _ldh_atl_pairs = [], []
        for _e in _exams:
            _edate = pd.to_datetime(_e["date"])
            _ck_v  = _e["values"].get("ck")
            _ldh_v = _e["values"].get("ldh")
            _atl_v = None
            if not df_load.empty and "atl" in df_load.columns:
                _near = df_load.iloc[(df_load["date"] - _edate).abs().argsort()[:1]]
                if len(_near):
                    _atl_v = float(_near["atl"].values[0])
            _ck_atl_pairs.append((_edate, _ck_v, _atl_v))
            _ldh_atl_pairs.append((_edate, _ldh_v, _atl_v))

        if not df_load.empty:
            _fig_ck = make_subplots(specs=[[{"secondary_y": True}]])
            # ATL line (background context)
            _df90 = df_load.tail(180)
            _fig_ck.add_trace(go.Scatter(
                x=_df90["date"], y=_df90["atl"], name="ATL (carga aguda)",
                line=dict(color=COL_ATL, width=2),
                fill="tozeroy", fillcolor="rgba(239,68,68,0.06)",
            ), secondary_y=False)
            # CTL line
            _fig_ck.add_trace(go.Scatter(
                x=_df90["date"], y=_df90["ctl"], name="CTL (fitness)",
                line=dict(color=COL_CTL, width=1.5, dash="dot"),
            ), secondary_y=False)
            # CK dots at exam dates (secondary y)
            _ck_dates  = [p[0] for p in _ck_atl_pairs if p[1] is not None]
            _ck_vals   = [p[1] for p in _ck_atl_pairs if p[1] is not None]
            _ldh_dates = [p[0] for p in _ldh_atl_pairs if p[2] is not None]
            _ldh_vals  = [p[1] for p in _ldh_atl_pairs if p[1] is not None]
            if _ck_dates:
                _fig_ck.add_trace(go.Scatter(
                    x=_ck_dates, y=_ck_vals, name="CK (examen)",
                    mode="markers+text",
                    marker=dict(size=16, color="#8B5CF6",
                                symbol="diamond",
                                line=dict(color="#FFFFFF", width=2)),
                    text=[f"CK {v:.0f}" for v in _ck_vals],
                    textposition="top center",
                    textfont=dict(size=10),
                ), secondary_y=True)
            if _ldh_vals:
                _fig_ck.add_trace(go.Scatter(
                    x=_ldh_dates, y=_ldh_vals, name="LDH (examen)",
                    mode="markers+text",
                    marker=dict(size=14, color="#F59E0B",
                                symbol="star",
                                line=dict(color="#FFFFFF", width=2)),
                    text=[f"LDH {v:.0f}" for v in _ldh_vals],
                    textposition="bottom center",
                    textfont=dict(size=10),
                ), secondary_y=True)
            # Vertical reference lines at exam dates
            for _ep in _exam_dates:
                _fig_ck.add_vline(x=_ep, line_dash="dot", line_color="#CBD5E1",
                                  line_width=1)
            _fig_ck.update_yaxes(title_text="ATL / CTL (TSS)", secondary_y=False,
                                  showgrid=True, gridcolor="#F1F5F9")
            _fig_ck.update_yaxes(title_text="CK / LDH (U/L)", secondary_y=True,
                                  showgrid=False)
            _fig_ck.update_xaxes(showgrid=False, tickformat="%b %Y")
            st.plotly_chart(chart(_fig_ck, 340, dict(l=0, r=0, t=14, b=0)),
                            use_container_width=True)
            st.caption(
                "**Interpretación:** CK baja (120 U/L) con ATL moderado indica recuperación completa. "
                "CK > 500 sostenido con ATL > 60 señala sobreentrenamiento. "
                "Las líneas punteadas verticales marcan fechas de extracción."
            )
        else:
            st.info("Sincroniza Garmin para ver ATL superpuesto con CK/LDH.")

        st.markdown(" ")
        st.divider()

        # ── 2. Hemoglobina / Hematocrito vs VO2max ───────────────────────────
        section("Hemoglobina & Hematocrito vs VO₂max estimado por Garmin",
                "Capacidad de transporte de O2 y fitness aeróbico")

        _hb_vals_list  = [(pd.to_datetime(e["date"]), e["values"].get("hemoglobina"))
                          for e in _exams if e["values"].get("hemoglobina")]
        _hct_vals_list = [(pd.to_datetime(e["date"]), e["values"].get("hematocrito"))
                          for e in _exams if e["values"].get("hematocrito")]

        _col_hb, _col_vo2 = st.columns([3, 2], gap="medium")
        with _col_hb:
            _fig_hb = make_subplots(specs=[[{"secondary_y": True}]])
            _fig_hb.add_trace(go.Scatter(
                x=[p[0] for p in _hb_vals_list],
                y=[p[1] for p in _hb_vals_list],
                name="Hemoglobina (g/dL)",
                mode="lines+markers+text",
                line=dict(color="#EF4444", width=2.5),
                marker=dict(size=12, color="#EF4444",
                            line=dict(color="#FFFFFF", width=2)),
                text=[str(p[1]) for p in _hb_vals_list],
                textposition="top center", textfont=dict(size=11),
            ), secondary_y=False)
            _fig_hb.add_hrect(y0=15.5, y1=17.5,
                               fillcolor="rgba(16,185,129,0.08)", line_width=0,
                               annotation_text="Óptimo atleta 15.5-17.5",
                               annotation_position="bottom right",
                               annotation_font_size=9)
            _fig_hb.add_trace(go.Scatter(
                x=[p[0] for p in _hct_vals_list],
                y=[p[1] for p in _hct_vals_list],
                name="Hematocrito (%)",
                mode="lines+markers+text",
                line=dict(color="#F59E0B", width=2, dash="dot"),
                marker=dict(size=10, color="#F59E0B",
                            line=dict(color="#FFFFFF", width=2)),
                text=[str(p[1]) for p in _hct_vals_list],
                textposition="bottom center", textfont=dict(size=11),
            ), secondary_y=True)
            _fig_hb.update_yaxes(title_text="Hemoglobina (g/dL)", secondary_y=False,
                                  range=[13.0, 18.5], showgrid=True, gridcolor="#F1F5F9")
            _fig_hb.update_yaxes(title_text="Hematocrito (%)", secondary_y=True,
                                  range=[39, 56], showgrid=False)
            _fig_hb.update_xaxes(showgrid=False, tickformat="%b %Y")
            st.plotly_chart(chart(_fig_hb, 300, dict(l=0, r=0, t=14, b=0)),
                            use_container_width=True)

        with _col_vo2:
            st.markdown(" ")
            _vo2r_val = float(_prof.get("vo2max_run", 0))
            _vo2b_val = float(_prof.get("vo2max_bike", 0))
            _hb_latest = lv.get("hemoglobina", 0) or 0
            _hct_latest = lv.get("hematocrito", 0) or 0

            # Fick equation approximation: VO2max ∝ [Hb] × CO (cardiac output)
            # Empirical: each 1 g/dL Hb change ≈ ~2-3% change in VO2max
            _hb_ref = 15.5
            _hb_factor = round((_hb_latest - _hb_ref) / _hb_ref * 100, 1)

            st.metric("VO₂max Run (Garmin)", f"{_vo2r_val:.0f} mL/kg/min",
                      "Excelente (>60)" if _vo2r_val >= 60 else
                      "Bueno (55-60)" if _vo2r_val >= 55 else "Promedio")
            st.metric("VO₂max Bike (Garmin)", f"{_vo2b_val:.0f} mL/kg/min")
            st.metric("Hb vs referencia atleta",
                      f"{_hb_latest} g/dL",
                      f"≈ {_hb_factor:+.1f}% impacto en VO₂max")
            st.markdown(" ")
            st.caption(
                "**Ecuación de Fick:**\n\n"
                "VO₂max = CO × (CaO₂ − CvO₂)\n\n"
                "Donde CaO₂ ∝ [Hb]. Una caída de 0.5 g/dL Hb "
                "(17.0→16.5) representa ≈ 1-2% reducción teórica en VO₂max. "
                "Tu nivel actual sigue siendo élite."
            )

        st.markdown(" ")
        st.divider()

        # ── 3. Vitamina D vs Sleep Score ──────────────────────────────────────
        section("Vitamina D vs Calidad de Sueño",
                "Promedio sleep score ± 14 días antes de cada examen")

        _vitd_sleep_rows = []
        for _e in _exams:
            _edate = pd.to_datetime(_e["date"])
            _vd    = _e["values"].get("vitamina_d")
            _avg_sleep = None
            if not df_sleep.empty and "sleep_score" in df_sleep.columns:
                _win = df_sleep[
                    (df_sleep["date"] >= _edate - pd.Timedelta(days=14)) &
                    (df_sleep["date"] <= _edate)
                ].dropna(subset=["sleep_score"])
                if not _win.empty:
                    _avg_sleep = round(float(_win["sleep_score"].mean()), 1)
            _vitd_sleep_rows.append({
                "date": _edate,
                "examdate": _e["date"],
                "vitamina_d": _vd,
                "avg_sleep": _avg_sleep,
            })

        _col_vd1, _col_vd2 = st.columns([3, 2], gap="medium")
        with _col_vd1:
            _fig_vd = make_subplots(specs=[[{"secondary_y": True}]])
            _vd_dates  = [r["date"] for r in _vitd_sleep_rows if r["vitamina_d"]]
            _vd_vals   = [r["vitamina_d"] for r in _vitd_sleep_rows if r["vitamina_d"]]
            _sl_dates  = [r["date"] for r in _vitd_sleep_rows if r["avg_sleep"]]
            _sl_vals   = [r["avg_sleep"] for r in _vitd_sleep_rows if r["avg_sleep"]]

            # Vitamin D optimal band
            _fig_vd.add_hrect(y0=40, y1=70,
                               fillcolor="rgba(16,185,129,0.08)", line_width=0,
                               annotation_text="Óptimo atleta (40-70)",
                               annotation_position="top right",
                               annotation_font_size=9)
            _fig_vd.add_hline(y=30, line_dash="dot", line_color="#F59E0B",
                               annotation_text="Mínimo suficiente (30)",
                               annotation_position="bottom right",
                               annotation_font_size=9)
            _fig_vd.add_trace(go.Scatter(
                x=_vd_dates, y=_vd_vals, name="Vitamina D (ng/mL)",
                mode="lines+markers+text",
                line=dict(color="#F59E0B", width=3),
                marker=dict(size=13, color="#F59E0B",
                            line=dict(color="#FFFFFF", width=2)),
                text=[str(v) for v in _vd_vals],
                textposition="top center", textfont=dict(size=12),
            ), secondary_y=False)
            if _sl_vals:
                _fig_vd.add_trace(go.Scatter(
                    x=_sl_dates, y=_sl_vals, name="Sleep Score avg (14d)",
                    mode="markers+text",
                    marker=dict(size=14, color="#8B5CF6", symbol="circle",
                                line=dict(color="#FFFFFF", width=2)),
                    text=[str(v) for v in _sl_vals],
                    textposition="bottom center", textfont=dict(size=11),
                ), secondary_y=True)
            _fig_vd.update_yaxes(title_text="Vitamina D (ng/mL)", secondary_y=False,
                                  range=[20, 75], showgrid=True, gridcolor="#F1F5F9")
            _fig_vd.update_yaxes(title_text="Sleep Score (0-100)", secondary_y=True,
                                  range=[40, 100], showgrid=False)
            _fig_vd.update_xaxes(showgrid=False, tickformat="%b %Y")
            st.plotly_chart(chart(_fig_vd, 300, dict(l=0, r=0, t=14, b=0)),
                            use_container_width=True)

        with _col_vd2:
            st.markdown(" ")
            _vd_latest = lv.get("vitamina_d", 0) or 0
            _vd_prev   = (_prev["values"].get("vitamina_d") if _prev else None) or 0
            _vd_delta  = _vd_latest - _vd_prev if _vd_prev else 0

            if _vd_latest < 30:
                _vd_status = "🔴 Insuficiente — suplementar"
            elif _vd_latest < 40:
                _vd_status = "🟡 Subóptimo para atleta"
            elif _vd_latest < 60:
                _vd_status = "✅ Óptimo"
            else:
                _vd_status = "⚠️ Revisar"

            st.metric("Vitamina D actual", f"{_vd_latest} ng/mL",
                      f"{_vd_delta:+.1f} ng/mL vs anterior" if _vd_prev else None)
            st.markdown(" ")
            st.caption(
                f"**Estado:** {_vd_status}\n\n"
                "**¿Por qué importa para triatlón?**\n\n"
                "- Fuerza muscular y potencia (↓Vit D → ↓ contractilidad)\n"
                "- Inmunidad (↓Vit D → mayor riesgo ITRS post-esfuerzo)\n"
                "- Recuperación ósea (estrés repetitivo: run + bike)\n"
                "- Calidad de sueño (receptores VDR en hipocampo)\n\n"
                "**Recomendación:** Con {:.0f} ng/mL considera 2000–4000 UI/día "
                "de D3 + K2 hasta próximo control.".format(_vd_latest)
            )

        st.markdown(" ")
        st.divider()

        # ── 4. Correlation explanation table ─────────────────────────────────
        section("Guía de Correlaciones Bioquímicas × Garmin", "Marco de referencia")
        _corr_data = [
            {"Biomarcador": "CK (Creatinquinasa)",
             "Señal Garmin":    "ATL (Carga Aguda)",
             "Correlación esperada": "CK sube 24-48h post-esfuerzo intenso (ATL alto). CK basal <200 = buena recuperación.",
             "Acción si correlaciona": "Si CK > 400 con ATL > 60 por >5 días → reducir carga"},
            {"Biomarcador": "LDH",
             "Señal Garmin":    "TSB (Forma)",
             "Correlación esperada": "LDH elevado con TSB muy negativo indica fatiga acumulada.",
             "Acción si correlaciona": "TSB < -20 + LDH > 260 → semana recuperación activa"},
            {"Biomarcador": "Hemoglobina / Hematocrito",
             "Señal Garmin":    "VO₂max estimado",
             "Correlación esperada": "R ≈ 0.7–0.85. Cada +1 g/dL Hb ≈ +2-3% VO₂max.",
             "Acción si correlaciona": "Hb < 14.5 con plateau en VO₂ → revisar fe sérico"},
            {"Biomarcador": "Vitamina D",
             "Señal Garmin":    "Sleep Score / Body Battery",
             "Correlación esperada": "VitD bajo (<30) asocia a peor calidad de sueño y Body Battery reducida.",
             "Acción si correlaciona": "VitD < 30 + Sleep < 65 → suplementación + revisar luz solar"},
            {"Biomarcador": "TSH / FT4 (Tiroides)",
             "Señal Garmin":    "Resting HR / HRV",
             "Correlación esperada": "Hipotiroidismo → HR elevada en reposo, HRV baja. Hipertiroidismo → HR > 70 en reposo.",
             "Acción si correlaciona": "TSH > 3.5 + RHR elevada → evaluación médica"},
            {"Biomarcador": "Ácido Úrico",
             "Señal Garmin":    "Carga semanal total (TSS)",
             "Correlación esperada": "Se eleva con semanas de TSS > 600 (catabolismo celular intenso).",
             "Acción si correlaciona": "Ac. Úrico > 6.5 en período de alta carga → hidratación y descanso"},
        ]
        st.dataframe(pd.DataFrame(_corr_data), hide_index=True, use_container_width=True)

    # ─────────────────────────────────────────────────────────────────────────
    # TAB 4 — IMPORTAR EXAMEN
    # ─────────────────────────────────────────────────────────────────────────
    with _t4:
        import json as _json
        from utils.lab_parser import (
            extract_text_pdf, parse_lab_values,
            parse_csv_bytes, parse_xlsx_bytes,
            generate_csv_template, generate_xlsx_template,
        )

        # ── Save helper ───────────────────────────────────────────────────────
        def _save_blood_exam(date_str: str, context: str,
                              lab_name: str, values: dict) -> tuple[bool, str]:
            p = DATA_DIR / "blood_tests.json"
            if p.exists():
                data = _json.loads(p.read_text(encoding="utf-8"))
            else:
                data = {"biomarkers": _bm, "exams": []}
            new_exam = {
                "date": date_str,
                "lab": lab_name or "Laboratorio Clínico",
                "context": context,
                "values": {k: v for k, v in values.items()
                           if v is not None and v != 0.0},
            }
            existing = [i for i, e in enumerate(data["exams"])
                        if e["date"] == date_str]
            if existing:
                data["exams"][existing[0]] = new_exam
                msg = f"Examen del **{date_str}** actualizado con {len(new_exam['values'])} marcadores."
                action = "updated"
            else:
                data["exams"].append(new_exam)
                data["exams"].sort(key=lambda e: e["date"])
                msg = f"Examen del **{date_str}** guardado con {len(new_exam['values'])} marcadores."
                action = "saved"
            p.write_text(_json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return True, msg

        # ── Category groups for the review form ───────────────────────────────
        _FORM_CATS = [
            ("🩸 Hemograma",         ["hemoglobina", "hematocrito", "eritrocitos",
                                       "vcm", "hcm", "chcm",
                                       "leucocitos", "plaquetas", "sedimentacion"]),
            ("💪 Muscular",           ["ck", "ldh"]),
            ("🫀 Lípidos",            ["colesterol_total", "hdl", "ldl",
                                       "trigliceridos", "ac_urico"]),
            ("⚗️ Enzimas",            ["got_ast", "gpt_alt", "ggt",
                                       "fosfatasas_alc", "bilirrubina_total"]),
            ("🫘 Renal",              ["creatinina", "tfge",
                                       "nitrogeno_ureico", "urea"]),
            ("🔬 Bioquímica",         ["glucosa", "proteinas_totales",
                                       "albumina", "globulinas"]),
            ("🌟 Vitaminas",          ["vitamina_d", "vitamina_b12"]),
            ("⚡ Electrolitos",       ["na", "k", "cl", "calcio", "fosforo"]),
            ("🧪 Hormonal",           ["tsh", "ft4", "psa_total"]),
        ]

        # ── UI: header ────────────────────────────────────────────────────────
        st.caption("Sube el informe de tu laboratorio (PDF, CSV o Excel) "
                   "para actualizar automáticamente el historial.")
        st.markdown(" ")

        _dl_col, _up_col = st.columns([1, 2], gap="large")

        with _dl_col:
            section("Plantillas descargables", "Rellena y sube para entrada manual")
            _tpl_csv  = generate_csv_template(_bm)
            _tpl_xlsx = generate_xlsx_template(_bm)
            st.download_button(
                "📄 Plantilla CSV",
                _tpl_csv, "plantilla_examen.csv", "text/csv",
                use_container_width=True,
            )
            st.download_button(
                "📊 Plantilla Excel (.xlsx)",
                _tpl_xlsx,
                "plantilla_examen.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            st.markdown(" ")
            st.caption(
                "**Flujo recomendado:**\n\n"
                "1. Descarga plantilla Excel\n"
                "2. Abre el PDF de tu laboratorio\n"
                "3. Copia los valores a la columna **valor**\n"
                "4. Sube el Excel aquí\n\n"
                "O sube directamente el PDF del informe y el sistema intentará extraer los valores automáticamente."
            )

        with _up_col:
            section("Subir informe", "PDF · CSV · Excel")
            _uploaded_file = st.file_uploader(
                "Arrastra o selecciona el archivo",
                type=["pdf", "csv", "xlsx", "xls"],
                key="bl_file_upload",
                label_visibility="collapsed",
            )

        st.markdown(" ")
        st.divider()

        # ── Process upload → extract values into session_state ────────────────
        if _uploaded_file is not None:
            _file_sig = f"{_uploaded_file.name}_{_uploaded_file.size}"
            if st.session_state.get("bl_file_sig") != _file_sig:
                _raw_bytes = _uploaded_file.read()
                _ext = _uploaded_file.name.rsplit(".", 1)[-1].lower()
                with st.spinner(f"Procesando {_uploaded_file.name}…"):
                    if _ext == "pdf":
                        _raw_text  = extract_text_pdf(_raw_bytes)
                        _extracted = parse_lab_values(_raw_text)
                    elif _ext == "csv":
                        _extracted = parse_csv_bytes(_raw_bytes)
                    else:
                        _extracted = parse_xlsx_bytes(_raw_bytes)
                st.session_state["bl_extracted"]  = _extracted
                st.session_state["bl_file_sig"]   = _file_sig
                st.session_state["bl_file_name"]  = _uploaded_file.name

        # ── Extraction summary banner ─────────────────────────────────────────
        _extracted_vals: dict = st.session_state.get("bl_extracted", {})
        _n_found   = len(_extracted_vals)
        _n_total   = len(_bm)
        _file_name = st.session_state.get("bl_file_name", "")

        if _extracted_vals:
            _pct = _n_found / _n_total * 100
            _bar_color = "#10B981" if _pct >= 60 else "#F59E0B" if _pct >= 30 else "#EF4444"
            st.success(
                f"**{_file_name}** — {_n_found} / {_n_total} marcadores extraídos ({_pct:.0f}%) · "
                f"Revisa y corrige los valores antes de guardar."
            )
        elif _uploaded_file is None and not _extracted_vals:
            st.info("Sube un archivo para continuar, o completa el formulario manualmente.")

        st.markdown(" ")

        # ── Review + manual entry form ────────────────────────────────────────
        section("Revisar y completar valores",
                "Corrige los extraídos · Agrega los faltantes · Deja en blanco los no medidos")

        # Form key changes when a new file is uploaded (forces re-render with new defaults)
        _form_key = f"exam_form_{st.session_state.get('bl_file_sig', 'manual')}"

        with st.form(_form_key, border=True):
            # ── Exam metadata ─────────────────────────────────────────────────
            _meta_c1, _meta_c2, _meta_c3 = st.columns([1, 2, 1])
            _exam_date_input = _meta_c1.date_input(
                "Fecha del examen",
                value=pd.Timestamp.today().date(),
                format="YYYY-MM-DD",
            )
            _context_input = _meta_c2.text_input(
                "Contexto / nota",
                value="Control de rutina",
                placeholder="ej: Pre-temporada, post-Ironman, control anual…",
            )
            _lab_input = _meta_c3.text_input(
                "Laboratorio",
                value="Laboratorio Clínico",
            )

            st.markdown(" ")

            # ── Biomarker inputs grouped by category ──────────────────────────
            _form_values: dict[str, Any] = {}
            for _cat_label, _cat_keys in _FORM_CATS:
                with st.expander(
                    _cat_label + (
                        f"  ·  {sum(1 for k in _cat_keys if k in _extracted_vals)} extraídos"
                        if _extracted_vals else ""
                    ),
                    expanded=any(k in _extracted_vals for k in _cat_keys) or not _extracted_vals,
                ):
                    _grid = st.columns(3, gap="small")
                    for _ci, _key in enumerate(_cat_keys):
                        _bm_def   = _bm.get(_key, {})
                        _lbl      = _bm_def.get("label", _key)
                        _unit     = _bm_def.get("unit", "")
                        _was_extr = _key in _extracted_vals
                        _prefix   = "✅ " if _was_extr else ""
                        _default  = float(_extracted_vals[_key]) if _was_extr else None

                        _v = _grid[_ci % 3].number_input(
                            f"{_prefix}{_lbl}",
                            value=_default,
                            min_value=0.0,
                            step=0.01,
                            format="%g",
                            help=f"{_unit}  ·  Ref: {_bm_def.get('ref_low','?')}–{_bm_def.get('ref_high','?')}  {_unit}\n\n{_bm_def.get('athlete_note','')}",
                            key=f"bl_{_form_key}_{_key}",
                        )
                        _form_values[_key] = _v

            st.markdown(" ")

            # ── Extracted-but-not-in-form catch-all ───────────────────────────
            _leftover = {k: v for k, v in _extracted_vals.items()
                         if not any(k in ck for _, ck in _FORM_CATS)}
            if _leftover:
                with st.expander(f"🔍 Otros valores extraídos ({len(_leftover)})"):
                    for _k, _v in _leftover.items():
                        st.caption(f"**{_k}**: {_v}")

            # ── Submit ────────────────────────────────────────────────────────
            _save_col, _clear_col, _ = st.columns([2, 1, 3])
            _do_save  = _save_col.form_submit_button(
                "💾  Guardar examen", use_container_width=True, type="primary"
            )
            _do_clear = _clear_col.form_submit_button(
                "🗑 Limpiar", use_container_width=True
            )

            if _do_save:
                _date_str = str(_exam_date_input)
                _ok, _msg = _save_blood_exam(
                    _date_str, _context_input, _lab_input, _form_values
                )
                if _ok:
                    st.success(f"✅ {_msg}")
                    # Clear upload state so next visit is clean
                    for _sk in ("bl_extracted", "bl_file_sig", "bl_file_name"):
                        st.session_state.pop(_sk, None)
                    st.rerun()
                else:
                    st.error(_msg)

            if _do_clear:
                for _sk in ("bl_extracted", "bl_file_sig", "bl_file_name"):
                    st.session_state.pop(_sk, None)
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# 🗺️ TRAINING DETAIL
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🗺️ Training Detail":

    if not has_data:
        st.info("No activities found. Sync Garmin from the sidebar.")
        st.stop()

    # ── Activity selector ──────────────────────────────────────────────────────
    _acts = df_act.head(60).reset_index(drop=True)

    def _act_lbl(r):
        ic  = SPORT_ICONS.get(r["sport"], "📊")
        dt  = pd.Timestamp(r["date"]).strftime("%d %b %Y")
        d_m = float(r.get("distance_m") or 0)
        d_s = f"  {d_m/1000:.1f} km" if d_m > 100 else ""
        dur = _fmt_dur(float(r.get("duration_sec") or 0))
        nm  = str(r.get("name") or r["sport"])[:35]
        return f"{ic}  {dt}  ·  {nm}{d_s}  ·  {dur}"

    _sel = st.selectbox(
        "Actividad",
        range(len(_acts)),
        format_func=lambda i: _act_lbl(_acts.iloc[i]),
        label_visibility="collapsed",
    )
    act = _acts.iloc[_sel]

    # ── Extract metrics ────────────────────────────────────────────────────────
    def _fv(col):
        """Safe float: returns None for NaN, None, or 0."""
        v = act.get(col)
        try:
            x = float(v)
            return None if (x != x or x == 0) else x   # x!=x catches NaN
        except Exception:
            return None

    _sport      = act.get("sport", "bike")
    _dur_sec    = float(act.get("duration_sec") or 0)
    _dist_m     = float(act.get("distance_m") or 0)
    _avg_hr     = _fv("avg_hr")
    _max_hr     = _fv("max_hr")
    _calories   = _fv("calories")
    _avg_pwr    = _fv("avg_power")
    _norm_pwr   = _fv("norm_power")
    _tss_v      = _fv("tss")
    _if_val     = _fv("if_factor")
    _avg_pace   = _fv("avg_pace_sec_km")
    _avg_pace_sw= _fv("avg_pace_100m")
    _avg_cad    = _fv("avg_cadence")
    _swolf_v    = _fv("swolf")
    _aer_te     = _fv("aerobic_te")
    _act_col    = SPORT_COLORS.get(_sport, ACCENT)
    _act_icon   = SPORT_ICONS.get(_sport, "📊")
    _act_nm     = str(act.get("name") or _sport)
    _act_dt     = pd.Timestamp(act["date"]).strftime("%A, %d %b %Y · %H:%M")

    # ── Activity header ────────────────────────────────────────────────────────
    st.markdown(f"### {_act_icon} {_act_nm}")
    st.caption(f"{_act_dt}")
    st.markdown(" ")

    # ── KPI row ────────────────────────────────────────────────────────────────
    _kc1, _kc2, _kc3, _kc4, _kc5, _kc6 = st.columns(6)
    _kc1.metric("⏱ Tiempo",    _fmt_dur(_dur_sec))
    _kc2.metric("📍 Distancia", f"{_dist_m/1000:.2f} km" if _dist_m > 100 else "—")

    if _sport == "bike" and _avg_pace and _avg_pace > 0:
        _kc3.metric("⚡ Vel. Media", f"{3600.0 / _avg_pace:.1f} km/h")
    elif _sport == "run" and _avg_pace and _avg_pace > 0:
        _kc3.metric("🏃 Ritmo",     _fmt_pace(_avg_pace) + " /km")
    elif _sport == "swim" and _avg_pace_sw and _avg_pace_sw > 0:
        _kc3.metric("🏊 Ritmo",     _fmt_pace(_avg_pace_sw) + " /100m")
    else:
        _kc3.metric("⚡ Vel. Media", "—")

    if _avg_hr and _max_hr:
        _kc4.metric("❤ FC",       f"{int(_avg_hr)} / {int(_max_hr)} bpm", "avg / max")
    elif _avg_hr:
        _kc4.metric("❤ FC Media", f"{int(_avg_hr)} bpm")
    else:
        _kc4.metric("❤ FC", "—")

    _kc5.metric("📊 TSS", f"{_tss_v:.0f}" if _tss_v else "—",
                f"IF {_if_val:.2f}" if _if_val else None)
    _kc6.metric("🔥 Calorías", f"{int(_calories)}" if _calories else "—")
    st.markdown(" ")

    # ── Map + performance breakdown ────────────────────────────────────────────
    _map_col, _stat_col = st.columns([3, 2], gap="large")

    with _map_col:
        if _sport == "swim":
            section("Ruta", "Natación en piscina")
            st.info("🏊 Sin ruta GPS — actividad en piscina")
        else:
            # ── Auto-load real GPS from Garmin (cached locally) ────────────────
            _act_id   = int(act.get("activity_id") or 0)
            _track_f  = DATA_DIR / "tracks" / f"{_act_id}.json"
            _gps_real = False

            if _act_id and _track_f.exists():
                # Already cached — load instantly
                import json as _json
                try:
                    _pts = _json.loads(_track_f.read_text())
                    if _pts:
                        _lats = [p["lat"] for p in _pts]
                        _lons = [p["lon"] for p in _pts]
                        _elev = [p.get("ele", 0) for p in _pts]
                        _gps_real = True
                except Exception:
                    pass

            if not _gps_real and _act_id:
                # Not cached yet — fetch from Garmin with spinner
                with st.spinner("Cargando GPS desde Garmin Connect…"):
                    try:
                        from garmin_connector import fetch_activity_gps
                        _g_email = os.environ.get("GARMIN_EMAIL", "")
                        _g_pw    = os.environ.get("GARMIN_PASSWORD", "")
                        _pts = fetch_activity_gps(_act_id,
                                                  email=_g_email or None,
                                                  password=_g_pw or None)
                        if _pts:
                            _lats = [p["lat"] for p in _pts]
                            _lons = [p["lon"] for p in _pts]
                            _elev = [p.get("ele", 0) for p in _pts]
                            _gps_real = True
                        else:
                            st.warning("⚠️ Esta actividad no tiene GPS (ej: piscina / trainer indoor).")
                    except Exception as _gps_err:
                        st.error(f"❌ Error GPS: {_gps_err}")

            if not _gps_real:
                # Fallback: simulated route
                _seed    = int(abs(hash(str(_act_id))) % 9999)
                _lats, _lons = _gen_activity_route(_dist_m or 8000, _sport, seed=_seed)
                _elev    = [0] * len(_lats)

            _map_src = "GPS real · Garmin Connect" if _gps_real else "GPS simulado"
            section("Ruta", _map_src)

            _clat  = sum(_lats) / len(_lats)
            _clon  = sum(_lons) / len(_lons)
            _zoom  = 12 if _dist_m < 15000 else 11 if _dist_m < 40000 else 10
            _n_pts = len(_lats)
            _sizes = [10 if i in (0, _n_pts - 1) else 3 for i in range(_n_pts)]

            _fig_map = go.Figure(go.Scattermapbox(
                lat=_lats, lon=_lons,
                mode="lines+markers",
                line=dict(width=3, color=_act_col),
                marker=dict(size=_sizes, color=_act_col, opacity=0.85),
                customdata=_elev,
                hovertemplate=(
                    "Lat %{lat:.5f} · Lon %{lon:.5f}<br>"
                    "Alt %{customdata:.0f} m<extra></extra>"
                ),
                name="Ruta",
            ))
            _fig_map.update_layout(
                mapbox=dict(
                    style="open-street-map",
                    center=dict(lat=_clat, lon=_clon),
                    zoom=_zoom,
                ),
                height=360,
                margin=dict(l=0, r=0, t=0, b=0),
                showlegend=False,
            )
            st.plotly_chart(_fig_map, use_container_width=True)

    with _stat_col:
        section("Performance", "Métricas detalladas de la sesión")
        st.markdown(" ")

        _detail_stats = []
        if _avg_pwr:   _detail_stats.append(("💪 Pot. Media",    f"{int(_avg_pwr)} W"))
        if _norm_pwr:  _detail_stats.append(("⚙ Pot. Norm. (NP)", f"{int(_norm_pwr)} W"))
        if _if_val:    _detail_stats.append(("📈 Intensidad (IF)", f"{_if_val:.2f}"))
        if _tss_v:     _detail_stats.append(("📊 TSS",             f"{_tss_v:.0f}"))
        if _avg_cad and _sport == "bike":
            _detail_stats.append(("🔄 Cadencia",  f"{int(_avg_cad)} rpm"))
        elif _avg_cad and _sport == "run":
            _detail_stats.append(("👣 Cadencia",  f"{int(_avg_cad)} spm"))
        if _swolf_v:   _detail_stats.append(("🌀 SWOLF",          f"{_swolf_v:.1f}"))
        if _aer_te:    _detail_stats.append(("🫁 Aerobic TE",      f"{_aer_te:.1f}"))
        if _calories:  _detail_stats.append(("🔥 Calorías",        f"{int(_calories)} kcal"))

        # W/kg if bike + has power
        if _sport == "bike" and _avg_pwr and weight > 0:
            _detail_stats.append(("⚖ W/kg",  f"{_avg_pwr / weight:.2f}"))
        # Zone label
        if _sport == "bike" and _avg_pwr and ftp > 0:
            _pz = power_zones(ftp)
            _zn = next((k for k, (lo, hi) in _pz.items() if lo <= _avg_pwr < hi), "—")
            _detail_stats.append(("🎯 Zona Potencia", _zn[:18]))

        if _detail_stats:
            for _di in range(0, len(_detail_stats), 2):
                _dc1, _dc2 = st.columns(2)
                _dc1.metric(_detail_stats[_di][0], _detail_stats[_di][1])
                if _di + 1 < len(_detail_stats):
                    _dc2.metric(_detail_stats[_di + 1][0], _detail_stats[_di + 1][1])
        else:
            st.caption("Conecta Garmin con datos de potencia y HR para ver métricas detalladas.")

    st.markdown(" ")

    # ── Synchronized performance charts ───────────────────────────────────────
    section("Análisis de Rendimiento", "Potencia · FC · Altitud · Velocidad — datos simulados calibrados")

    _ts = _gen_timeseries_td(_dur_sec, _sport, _avg_pwr, _avg_hr, _max_hr, _avg_pace)

    # Overlay real elevation from GPS track when available
    if _gps_real and len(_elev) >= 4:
        import numpy as _np2
        _elev_arr = _np2.array(_elev, dtype=float)
        _n_ts     = len(_ts["altitude"])
        # Resample elevation to match timeseries length
        _idx = _np2.linspace(0, len(_elev_arr) - 1, _n_ts).astype(int)
        _ts["altitude"] = _elev_arr[_idx].round(0).astype(int).tolist()

    _fig_perf = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.10,
        subplot_titles=[
            ("⚡ Potencia (W) & Frecuencia Cardíaca (bpm)"
             if _sport == "bike" and _ts["power"]
             else "❤ Frecuencia Cardíaca (bpm)"),
            "⛰ Altitud (m) & Velocidad (km/h)",
        ],
        specs=[[{"secondary_y": True}], [{"secondary_y": True}]],
    )

    if _sport == "bike" and _ts["power"]:
        # Row 1 primary: Power (area)
        _fig_perf.add_trace(go.Scatter(
            x=_ts["time"], y=_ts["power"],
            name="Potencia",
            fill="tozeroy", fillcolor="rgba(245,158,11,0.15)",
            line=dict(color=COL_BIKE, width=1.8),
            hovertemplate="%{y} W<extra>Potencia</extra>",
        ), row=1, col=1, secondary_y=False)
        # Row 1 secondary: HR (line)
        _fig_perf.add_trace(go.Scatter(
            x=_ts["time"], y=_ts["hr"],
            name="FC",
            line=dict(color=COL_ATL, width=1.8, dash="solid"),
            hovertemplate="%{y} bpm<extra>FC</extra>",
        ), row=1, col=1, secondary_y=True)
        # FTP reference
        _fig_perf.add_hline(y=ftp, line_dash="dash", line_color="#94A3B8",
                            annotation_text=f"FTP {ftp}W",
                            annotation_font_size=9,
                            row=1, col=1, secondary_y=False)
        _fig_perf.update_yaxes(title_text="Watts", row=1, col=1, secondary_y=False)
        _fig_perf.update_yaxes(title_text="bpm",   row=1, col=1, secondary_y=True,
                               showgrid=False)
    else:
        # Row 1 primary: HR only (area)
        _fig_perf.add_trace(go.Scatter(
            x=_ts["time"], y=_ts["hr"],
            name="FC",
            fill="tozeroy", fillcolor="rgba(239,68,68,0.12)",
            line=dict(color=COL_ATL, width=1.8),
            hovertemplate="%{y} bpm<extra>FC</extra>",
        ), row=1, col=1, secondary_y=False)
        _fig_perf.update_yaxes(title_text="bpm", row=1, col=1, secondary_y=False)

    # Row 2 primary: Altitude (area)
    _fig_perf.add_trace(go.Scatter(
        x=_ts["time"], y=_ts["altitude"],
        name="Altitud",
        fill="tozeroy", fillcolor="rgba(6,182,212,0.18)",
        line=dict(color=COL_SWIM, width=1.8),
        hovertemplate="%{y} m<extra>Altitud</extra>",
    ), row=2, col=1, secondary_y=False)
    # Row 2 secondary: Speed (line)
    _fig_perf.add_trace(go.Scatter(
        x=_ts["time"], y=_ts["speed"],
        name="Velocidad",
        line=dict(color=COL_RUN, width=1.8),
        hovertemplate="%{y} km/h<extra>Vel.</extra>",
    ), row=2, col=1, secondary_y=True)

    _fig_perf.update_yaxes(title_text="m alt.", row=2, col=1, secondary_y=False)
    _fig_perf.update_yaxes(title_text="km/h",   row=2, col=1, secondary_y=True,
                           showgrid=False)

    _fig_perf.update_layout(
        height=500,
        template="plotly_white",
        margin=dict(l=4, r=4, t=32, b=4),
        plot_bgcolor=CARD, paper_bgcolor=CARD,
        font=dict(family="Inter, sans-serif", size=11, color=TEXT2),
        legend=dict(orientation="h", y=1.06, font_size=11, bgcolor="rgba(0,0,0,0)"),
        hovermode="x unified",
    )
    _fig_perf.update_xaxes(showgrid=True, gridcolor="#F1F5F9", tickfont_size=10)
    _fig_perf.update_yaxes(showgrid=True, gridcolor="#F1F5F9", tickfont_size=10)
    st.plotly_chart(_fig_perf, use_container_width=True)

    # ── Power zone distribution (bike + power only) ───────────────────────────
    if _sport == "bike" and _ts["power"] and ftp > 0:
        st.markdown(" ")
        section("Distribución de Zonas", "% de tiempo en cada zona de potencia")

        _pz      = power_zones(ftp)
        _pw_arr  = _ts["power"]
        _z_names  = list(_pz.keys())
        _z_counts = [sum(1 for p in _pw_arr if lo <= p < hi) for lo, hi in _pz.values()]
        _z_total  = sum(_z_counts) or 1
        _z_pcts   = [round(c / _z_total * 100, 1) for c in _z_counts]
        _z_cols   = ["#94A3B8","#22C55E","#F59E0B","#F97316","#EF4444","#8B5CF6","#C026D3"]

        _fig_z = go.Figure()
        for _zn, _zp, _zc in zip(_z_names, _z_pcts, _z_cols):
            _fig_z.add_trace(go.Bar(
                x=[_zp], y=["Zonas"],
                name=_zn,
                orientation="h",
                marker_color=_zc,
                text=f"{_zp:.0f}%" if _zp >= 4 else "",
                textposition="inside",
                insidetextanchor="middle",
                hovertemplate=f"{_zn}: {_zp:.1f}%<extra></extra>",
            ))
        _fig_z.update_layout(
            barmode="stack", height=88,
            margin=dict(l=0, r=0, t=0, b=0),
            template="plotly_white",
            plot_bgcolor=CARD, paper_bgcolor=CARD,
            legend=dict(orientation="h", y=-0.6, font_size=10, bgcolor="rgba(0,0,0,0)"),
        )
        _fig_z.update_xaxes(visible=False)
        _fig_z.update_yaxes(visible=False)
        st.plotly_chart(_fig_z, use_container_width=True)

