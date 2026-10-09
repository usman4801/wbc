import streamlit as st
import sqlite3
import os
import math
import datetime
import html as _html
import pandas as pd

# ----------------------------------------------------------------
# PAGE CONFIG
# ----------------------------------------------------------------
st.set_page_config(page_title="WBC Portal", page_icon="🛡️", layout="wide",
                   initial_sidebar_state="expanded")

DB_PATH = os.environ.get("WBC_DB_PATH", "wbc.db")
PAGE_SIZE = 8

CASE_COLS = ["id", "login", "empid", "name", "site", "mgr", "shift", "agency", "absent",
             "created", "status", "outcome", "reason", "doc_type", "doc_file", "notes",
             "closed", "source", "sick_hint", "ua_escalation_level",
             "escalation_valid_until", "closedby", "on_site"]


# ----------------------------------------------------------------
# DESIGN SYSTEM  (CSS + SVG helpers)
# ----------------------------------------------------------------
def _ico(body):
    return ("%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='black' "
            "fill-rule='evenodd'%3E%3Cpath d='" + body + "'/%3E%3C/svg%3E")


NAV_ICONS = [
    _ico("M12 3 2 12h3v8h5v-6h4v6h5v-8h3z"),
    _ico("M4 4h16a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zm1 4v3h5V8zm7 0v3h7V8zm-7 5v3h5v-3zm7 0v3h7v-3z"),
    _ico("M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5zm0 5 3 1.5v2.5c0 2.3-1.2 4.2-3 5.2-1.8-1-3-2.9-3-5.2V8.5z"),
    _ico("M4 20V10h3v10zm6 0V4h3v16zm6 0v-7h3v7z"),
    _ico("M12 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10zm0 2c-4.4 0-8 2.2-8 5v3h16v-3c0-2.8-3.6-5-8-5z"),
    _ico("M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zm9.4 5.5v-3l-2.3-.5a7.6 7.6 0 0 0-.8-1.9l1.3-2-2.1-2.1-2 1.3a7.6 7.6 0 0 0-1.9-.8l-.5-2.3h-3l-.5 2.3a7.6 7.6 0 0 0-1.9.8l-2-1.3-2.1 2.1 1.3 2a7.6 7.6 0 0 0-.8 1.9l-2.3.5v3l2.3.5c.2.7.5 1.3.8 1.9l-1.3 2 2.1 2.1 2-1.3c.6.4 1.2.6 1.9.8l.5 2.3h3l.5-2.3c.7-.2 1.3-.5 1.9-.8l2 1.3 2.1-2.1-1.3-2c.4-.6.6-1.2.8-1.9z"),
]

_nav_css = "".join(
    f'[data-testid="stSidebar"] [data-testid="stRadio"] label:nth-of-type({i + 1}) p'
    f'{{--ico:url("data:image/svg+xml;utf8,{icon}");}}\n'
    for i, icon in enumerate(NAV_ICONS))

BASE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root{--navy:#0f1f4b;--blue:#2563eb;--muted:#64748b;--line:#e8edf5;}
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"], button, input, textarea, select {
  font-family:'Inter','Segoe UI',system-ui,-apple-system,sans-serif !important; }
[data-testid="stAppViewContainer"]{background:#f6f8fc;}
[data-testid="stHeader"]{background:transparent;}
[data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer{display:none !important;}
[data-testid="stMainBlockContainer"]{padding:0.6rem 1.8rem 2rem;max-width:100%;}
h1,h2,h3{color:var(--navy);}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#fff 0%,#fff 55%,#f2f1ff 80%,#e3e2ff 100%);
  border-right:1px solid var(--line);min-width:262px !important;max-width:262px !important;}
[data-testid="stSidebarHeader"]{min-height:0;height:auto;padding:.4rem 1rem 0;}
[data-testid="stSidebarContent"]{padding:0 .9rem;}
.brand{display:flex;align-items:center;gap:12px;padding:6px 6px 22px;}
.brand b{display:block;font-size:1.3rem;font-weight:800;color:var(--navy);line-height:1.1;}
.brand small{display:block;font-size:.64rem;color:var(--muted);margin-top:3px;white-space:nowrap;}
[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"]{gap:4px;}
[data-testid="stSidebar"] [data-testid="stRadio"] label{
  width:100%;padding:12px;border-radius:10px;cursor:pointer;margin:0;}
[data-testid="stSidebar"] [data-testid="stRadio"] label > div:first-child{display:none;}
[data-testid="stSidebar"] [data-testid="stRadio"] label p{
  display:flex;align-items:center;gap:12px;font-size:.9rem;font-weight:500;color:#475569;margin:0;white-space:nowrap;}
[data-testid="stSidebar"] [data-testid="stRadio"] label p::before{
  content:"";width:20px;height:20px;flex:none;background-color:currentColor;
  -webkit-mask:var(--ico) center/contain no-repeat;mask:var(--ico) center/contain no-repeat;opacity:.75;}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover{background:#f1f5fb;}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked){background:#e6eefd;}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p{color:var(--blue);font-weight:600;}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p::before{opacity:1;}
.side-foot{position:fixed;left:26px;bottom:34px;font-size:1.02rem;line-height:1.35;font-weight:500;
  background:linear-gradient(90deg,#3b5bdb,#7c5cff);-webkit-background-clip:text;background-clip:text;color:transparent;}
.side-foot span{display:block;width:30px;height:2px;margin-top:8px;background:#6366f1;border-radius:2px;}
.st-key-signout button{background:transparent;border:1px solid var(--line);color:var(--muted);
  border-radius:10px;font-size:.82rem;margin-top:14px;}

/* ---------- top bar ---------- */
.topbar{display:flex;justify-content:space-between;align-items:center;margin:2px 0 14px;}
.tb-left{display:flex;align-items:center;gap:12px;}
.wave{font-size:1.8rem;}
.tb-title{font-size:1.5rem;font-weight:800;color:var(--navy);line-height:1.15;}
.tb-sub{font-size:.88rem;color:var(--muted);}
.tb-right{display:flex;align-items:center;gap:22px;}
.online{display:inline-flex;align-items:center;gap:8px;background:#e3f8ee;color:#059669;
  font-size:.78rem;font-weight:600;padding:7px 14px;border-radius:999px;}
.online i{width:8px;height:8px;border-radius:50%;background:#10b981;display:inline-block;}
.tb-date{display:flex;align-items:center;gap:10px;font-size:.76rem;color:#475569;line-height:1.35;}
.tb-date svg{color:#475569;}
.tb-sep{width:1px;height:34px;background:var(--line);}
.tb-user{display:flex;align-items:center;gap:10px;}
.avatar{width:42px;height:42px;border-radius:50%;background:#dbe7ff;color:var(--blue);
  display:flex;align-items:center;justify-content:center;}
.tb-user b{display:block;font-size:.88rem;color:var(--navy);}
.tb-user small{display:block;font-size:.72rem;color:var(--muted);}

/* ---------- hero ---------- */
.hero{position:relative;overflow:hidden;border-radius:16px;padding:30px 32px;margin-bottom:16px;min-height:140px;
  background:linear-gradient(100deg,#eef4ff 0%,#f1f0ff 55%,#e6e4ff 100%);border:1px solid #e6ecf8;}
.hero::before{content:"";position:absolute;right:-60px;bottom:-90px;width:520px;height:220px;border-radius:50%;
  background:radial-gradient(closest-side,rgba(165,150,255,.35),rgba(165,150,255,0));}
.hero-pill{display:inline-block;background:#dbe8ff;color:var(--blue);font-size:.78rem;font-weight:600;
  padding:4px 14px;border-radius:999px;}
.hero-title{font-size:1.9rem;font-weight:800;color:var(--navy);margin:10px 0 4px;}
.hero-sub{font-size:.92rem;color:var(--muted);}
.hero-art{position:absolute;right:46px;top:14px;}

/* ---------- KPI cards ---------- */
.kpi{background:#fff;border:1px solid var(--line);border-bottom:3px solid var(--c);border-radius:14px;
  padding:16px 16px 12px;box-shadow:0 2px 10px rgba(30,60,120,.05);box-sizing:border-box;}
.kpi-top{display:flex;align-items:center;gap:12px;}
.kpi-ico{width:46px;height:46px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex:none;}
.kpi-mid{flex:1;min-width:0;}
.kpi-label{font-size:.82rem;font-weight:600;color:#1e293b;white-space:nowrap;}
.kpi-val{font-size:2rem;font-weight:800;color:var(--navy);line-height:1.15;}
.kpi-val.sm{font-size:1.35rem;padding:6px 0;}
.kpi-row{display:flex;align-items:flex-end;justify-content:space-between;gap:8px;}
.kpi-spark{width:84px;flex:none;margin-bottom:2px;}
.kpi-delta{margin-top:8px;font-size:.72rem;color:var(--muted);display:flex;align-items:center;gap:8px;}
.kpi-delta em{font-style:normal;}
.d-up{color:#059669;background:#e3f8ee;padding:1px 7px;border-radius:6px;font-weight:600;}
.d-down{color:#e11d48;background:#ffe8ea;padding:1px 7px;border-radius:6px;font-weight:600;}
.d-flat{color:#64748b;background:#eef2f7;padding:1px 7px;border-radius:6px;font-weight:600;}

/* ---------- cards ---------- */
[class*="st-key-card_"]{background:#fff;border:1px solid var(--line) !important;border-radius:14px !important;
  box-shadow:0 2px 10px rgba(30,60,120,.05);padding:10px 14px 14px;}
.card-h{display:flex;align-items:center;gap:12px;}
.card-ico{width:44px;height:44px;border-radius:12px;display:flex;align-items:center;justify-content:center;
  background:#e3edff;color:var(--blue);flex:none;}
.card-t{font-size:1rem;font-weight:700;color:var(--navy);line-height:1.2;}
.card-s{font-size:.78rem;color:var(--muted);}
[class*="st-key-card_"] [data-testid="stTextInput"] input,
[class*="st-key-card_"] [data-baseweb="select"] > div{border-radius:10px;border-color:#dfe6f1;font-size:.82rem;}

/* ---------- case table ---------- */
[class*="st-key-thead_"]{background:#f4f6fb;border-radius:8px;padding:10px 12px;margin-top:6px;gap:0;}
[class*="st-key-row_"]{border-bottom:1px solid #eef2f7;padding:8px 12px;gap:0;}
[class*="st-key-row_"]:hover{background:#fafcff;}
[class*="st-key-thead_"] [data-testid="stHorizontalBlock"],
[class*="st-key-row_"] [data-testid="stHorizontalBlock"]{align-items:center;gap:.5rem;}
.th{font-size:.76rem;font-weight:600;color:#475569;}
.td{font-size:.84rem;color:#334155;}
.td.id{color:#1e293b;font-weight:500;}
.pill{display:inline-block;padding:4px 16px;border-radius:999px;font-size:.76rem;font-weight:600;}
.p-open{background:#ffe8ea;color:#e11d48;}
.p-review{background:#fff1d6;color:#d97706;}
.p-closed{background:#d9f7ea;color:#059669;}
.p-pending{background:#ece8ff;color:#7c3aed;}
.p-other{background:#eef2f7;color:#475569;}
[class*="st-key-view_"] button{border:none;background:transparent;color:var(--blue);font-weight:600;
  font-size:.84rem;padding:0;min-height:0;box-shadow:none;}
[class*="st-key-view_"] button:hover{background:transparent;color:#1d4ed8;}
.showing{font-size:.78rem;color:var(--muted);padding-top:8px;}
[class*="st-key-pager"] button{min-height:34px;padding:0 6px;border-radius:8px;border:1px solid #dfe6f1;
  background:#fff;color:#475569;font-size:.8rem;}
[class*="st-key-pager"] button[data-testid="stBaseButton-primary"]{background:var(--blue);border-color:var(--blue);color:#fff;}

/* ---------- cases by site ---------- */
.site-row{display:grid;grid-template-columns:86px 1fr 52px;align-items:center;gap:10px;
  padding:14px 0;border-bottom:1px solid #f0f3f8;}
.site-row:last-child{border-bottom:none;}
.site-l{display:flex;align-items:center;gap:10px;font-size:.88rem;font-weight:600;color:#1e293b;}
.site-l i{width:9px;height:9px;border-radius:50%;display:inline-block;flex:none;}
.site-n{font-size:.88rem;font-weight:600;color:#1e293b;}
.bar{height:7px;background:#eef2f9;border-radius:99px;overflow:hidden;margin-top:4px;}
.bar span{display:block;height:100%;border-radius:99px;}
.site-p{font-size:.74rem;color:var(--muted);text-align:right;}

/* ---------- dialog ---------- */
.kv{display:grid;grid-template-columns:140px 1fr;gap:8px 12px;font-size:.88rem;}
.kv b{color:#475569;font-weight:600;}
</style>
""" + "<style>\n" + _nav_css + "</style>"

LOGIN_CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"]{display:none !important;}
[data-testid="stAppViewContainer"]{background:linear-gradient(135deg,#eaf1ff 0%,#f4f1ff 60%,#e6e4ff 100%);}
.st-key-card_login{padding:26px 30px 28px;box-shadow:0 10px 40px rgba(37,99,235,.10);}
.st-key-card_login .brand{justify-content:center;padding-bottom:6px;}
.login-t{text-align:center;font-size:1.35rem;font-weight:800;color:#0f1f4b;margin:10px 0 2px;}
.login-s{text-align:center;font-size:.85rem;color:#64748b;margin-bottom:10px;}
.st-key-card_login button[data-testid="stBaseButton-secondary"]{background:#2563eb;color:#fff;border:none;
  border-radius:10px;font-weight:600;min-height:42px;}
</style>
"""

ICONS = {
    "doc": '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h6"/>',
    "target": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
    "box": '<rect x="4" y="9" width="16" height="11" rx="2"/><path d="M4 13h16M12 9v11M8 9V6a2 2 0 0 1 4 0M16 9V6a2 2 0 0 0-4 0"/>',
    "cube": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
    "shieldclock": '<path d="M12 3l7 3v5c0 5-3 8.5-7 10-4-1.5-7-5-7-10V6z"/><path d="M12 8v4l3 2"/>',
    "pin": '<path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/>',
    "check": '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 12l3 3 5-6"/>',
    "cal": '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
    "list": '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
}


def svg(name, size=22):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')


BRAND_HTML = """
<div class="brand">
<svg width="40" height="44" viewBox="0 0 40 44"><defs><linearGradient id="bg1" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#3b82f6"/><stop offset="1" stop-color="#1e3a8a"/></linearGradient></defs>
<path d="M20 2 4 8v14c0 11 7 18 16 21 9-3 16-10 16-21V8z" fill="url(#bg1)"/>
<path d="M20 10 10 14v8c0 7 4 11 10 14 6-3 10-7 10-14v-8z" fill="none" stroke="#fff" stroke-width="1.8" opacity=".7"/>
<path d="M15 22l4 4 7-8" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
<div><b>WBC Portal</b><small>Workplace Behaviour &amp; Compliance</small></div></div>
"""

HERO_ART = """
<svg class="hero-art" width="230" height="130" viewBox="0 0 230 130">
<defs><linearGradient id="ha" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f8faff"/><stop offset="1" stop-color="#dfe3ff"/></linearGradient>
<linearGradient id="hs" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6aa0ff"/><stop offset="1" stop-color="#5b4be0"/></linearGradient></defs>
<g transform="rotate(6 125 70)"><rect x="70" y="10" width="130" height="104" rx="10" fill="url(#ha)" stroke="#d3daf5"/>
<rect x="86" y="30" width="62" height="7" rx="3.5" fill="#bcc8f2"/><rect x="86" y="48" width="86" height="7" rx="3.5" fill="#c9d3f5"/>
<rect x="86" y="66" width="52" height="7" rx="3.5" fill="#d4dcf7"/></g>
<path d="M172 54l26 10v20c0 16-11 26-26 31-15-5-26-15-26-31V64z" fill="url(#hs)"/>
<path d="M162 86l8 8 15-17" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M58 30l-14-8M52 46l-18-2M60 14l-6-12" stroke="#4aa8ff" stroke-width="3" stroke-linecap="round"/></svg>
"""

SITE_COLORS = ["#3b82f6", "#10b981", "#8b5cf6", "#f59e0b", "#06b6d4"]


def esc(v):
    return _html.escape("" if v is None else str(v))


def now_local():
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("Asia/Dubai"))
    except Exception:
        return datetime.datetime.now()


def topbar_html(user):
    n = now_local()
    role = {"Admin": "Administrator"}.get(user["role"], user["role"])
    name = user["alias"].capitalize()
    return f"""
<div class="topbar">
 <div class="tb-left"><span class="wave">👋</span>
  <div><div class="tb-title">Welcome back, {esc(name)}</div>
  <div class="tb-sub">Here's what's happening with your WBC Portal today.</div></div></div>
 <div class="tb-right">
  <span class="online"><i></i>System Online</span>
  <div class="tb-date">{svg('cal', 22)}<div>{n.strftime('%b %d, %Y')}<br>{n.strftime('%I:%M %p')}</div></div>
  <span class="tb-sep"></span>
  <div class="tb-user"><div class="avatar">{svg('user', 22)}</div>
   <div><b>{esc(name)}</b><small>{esc(role)}</small></div></div>
 </div></div>"""


def hero_html(pill, title, sub):
    return (f'<div class="hero"><span class="hero-pill">{esc(pill)}</span>'
            f'<div class="hero-title">{esc(title)}</div><div class="hero-sub">{esc(sub)}</div>'
            f'{HERO_ART}</div>')


def card_header_html(icon, title, sub, bg="#e3edff", fg="#2563eb"):
    return (f'<div class="card-h"><div class="card-ico" style="background:{bg};color:{fg}">{svg(icon, 22)}</div>'
            f'<div><div class="card-t">{esc(title)}</div><div class="card-s">{esc(sub)}</div></div></div>')


def spark_svg(values, color, uid):
    w, h = 84, 36
    mx = max(values) if values else 0
    n = len(values)
    if n < 2:
        values, n = [0, 0], 2
    pts = []
    for i, v in enumerate(values):
        x = i * (w - 2) / (n - 1) + 1
        y = h - 4 - ((v / mx) * (h - 10) if mx else 0)
        pts.append((x, y))
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"M{pts[0][0]:.1f},{h} L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + f" L{pts[-1][0]:.1f},{h} Z"
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}"><defs><linearGradient id="sp{uid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{color}" stop-opacity=".25"/><stop offset="1" stop-color="{color}" stop-opacity="0"/>'
            f'</linearGradient></defs><path d="{area}" fill="url(#sp{uid})"/>'
            f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/></svg>')


def delta_html(pct):
    if pct is None:
        return '<span class="d-flat">–</span><em>vs. last 30 days</em>'
    cls, arrow = ("d-up", "↑") if pct >= 0 else ("d-down", "↓")
    return f'<span class="{cls}">{arrow} {abs(pct):.0f}%</span><em>vs. last 30 days</em>'


def kpi_html(label, value, color, soft, icon, spark=None, delta="", small=False, uid=0):
    sp = f'<div class="kpi-spark">{spark_svg(spark, color, uid)}</div>' if spark is not None else ""
    cls = "kpi-val sm" if small else "kpi-val"
    return (f'<div class="kpi" style="--c:{color}"><div class="kpi-top">'
            f'<div class="kpi-ico" style="background:{soft};color:{color}">{svg(icon, 24)}</div>'
            f'<div class="kpi-mid"><div class="kpi-label">{esc(label)}</div>'
            f'<div class="kpi-row"><div class="{cls}">{esc(value)}</div>{sp}</div></div>'
            f'</div><div class="kpi-delta">{delta}</div></div>')


def pill_html(group, label):
    cls = {"open": "p-open", "review": "p-review", "closed": "p-closed", "pending": "p-pending"}.get(group, "p-other")
    return f'<span class="pill {cls}">{esc(label)}</span>'


def sites_html(df):
    if df.empty:
        return '<div class="card-s" style="padding:18px 0">No data yet.</div>'
    counts = df["site"].fillna("").replace("", "Unassigned").value_counts().head(5)
    total, top = len(df), int(counts.max())
    rows = []
    for i, (site, c) in enumerate(counts.items()):
        col = SITE_COLORS[i % len(SITE_COLORS)]
        rows.append(f'<div class="site-row"><div class="site-l"><i style="background:{col}"></i>{esc(site)}</div>'
                    f'<div><div class="site-n">{int(c)}</div><div class="bar"><span style="width:{c / top * 100:.0f}%;background:{col}"></span></div></div>'
                    f'<div class="site-p">{c / total * 100:.1f}%</div></div>')
    return "".join(rows)


# ----------------------------------------------------------------
# DATA HELPERS
# ----------------------------------------------------------------
def status_group(s):
    s = (s or "").strip().lower()
    if s == "open":
        return "open"
    if s == "closed":
        return "closed"
    if s in ("in review", "in progress", "review"):
        return "review"
    if s == "pending":
        return "pending"
    return "other"


def prepare(df):
    today = pd.Timestamp.today().normalize()
    df = df.copy()
    df["_g"] = df["status"].map(status_group)
    df["_created"] = pd.to_datetime(df["created"], errors="coerce")
    end = pd.to_datetime(df["closed"], errors="coerce").where(df["_g"] == "closed").fillna(today)
    df["_days"] = (end - df["_created"]).dt.days
    df["_type"] = df["outcome"].replace("", pd.NA).fillna("Attendance")
    return df


def series_and_trend(df, mask):
    sub = df[mask]
    today = pd.Timestamp.today().normalize()
    days = pd.date_range(today - pd.Timedelta(days=13), today)
    per_day = sub["_created"].dt.normalize().value_counts()
    vals = [int(per_day.get(d, 0)) for d in days]
    cur = int(((sub["_created"] > today - pd.Timedelta(days=30)) & (sub["_created"] < today + pd.Timedelta(days=1))).sum())
    prev = int(((sub["_created"] > today - pd.Timedelta(days=60)) & (sub["_created"] <= today - pd.Timedelta(days=30))).sum())
    pct = None if prev == 0 else (cur - prev) / prev * 100
    return vals, pct


# ----------------------------------------------------------------
# DATABASE  (unchanged logic from your original file)
# ----------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)) if os.path.dirname(os.path.abspath(DB_PATH)) else '.', exist_ok=True)
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS cases (
        id TEXT PRIMARY KEY, login TEXT NOT NULL, empid TEXT, name TEXT,
        site TEXT, mgr TEXT, shift TEXT, agency TEXT, absent TEXT, created TEXT,
        status TEXT DEFAULT "Open", outcome TEXT DEFAULT "", reason TEXT DEFAULT "",
        doc_type TEXT DEFAULT "", doc_file TEXT DEFAULT "", notes TEXT DEFAULT "",
        closed TEXT DEFAULT "", source TEXT DEFAULT "csv", sick_hint INTEGER DEFAULT 0,
        ua_escalation_level INTEGER DEFAULT 0, escalation_valid_until TEXT DEFAULT "",
        closedby TEXT DEFAULT "", on_site TEXT DEFAULT "")''')
    c.execute('''CREATE TABLE IF NOT EXISTS ua_offences (
        id INTEGER PRIMARY KEY AUTOINCREMENT, login TEXT NOT NULL, name TEXT DEFAULT "",
        empid TEXT DEFAULT "", site TEXT, date TEXT NOT NULL,
        offence_type TEXT DEFAULT "")''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        alias TEXT PRIMARY KEY, role TEXT NOT NULL, sites TEXT DEFAULT "All",
        added TEXT, token TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS upl_summary (login TEXT PRIMARY KEY, site TEXT DEFAULT '', scheduled_days INTEGER DEFAULT 0, upl_days INTEGER DEFAULT 0, updated TEXT DEFAULT '')''')

    # Indexes
    c.execute("CREATE INDEX IF NOT EXISTS idx_cases_login ON cases(login)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_cases_site ON cases(site)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status)")

    # Seed default users
    c.execute("INSERT OR REPLACE INTO users (alias, role, sites, added, token) VALUES ('mnnafee', 'Admin', 'All', ?, 'mnnafee')",
              (str(datetime.date.today()),))
    c.execute("INSERT OR REPLACE INTO users (alias, role, sites, added, token) VALUES ('javmuhak', 'VPOC', 'All', ?, 'javmuhak')",
              (str(datetime.date.today()),))

    conn.commit()

    # AUTO-IMPORT DATA FROM 'Roster' SHEET OF EXCEL
    count = c.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    if count == 0:
        excel_files = [f for f in os.listdir('.') if f.endswith('.xlsx') or f.endswith('.xls')]
        if excel_files:
            try:
                file_path = excel_files[0]
                xls = pd.ExcelFile(file_path)
                sheet_name = 'Roster' if 'Roster' in xls.sheet_names else xls.sheet_names[0]

                df = pd.read_excel(file_path, sheet_name=sheet_name, skiprows=5)
                df.columns = [str(c).strip() for c in df.columns]

                for idx, row in df.iterrows():
                    psoft_no = str(row.get('Psoft No', ''))
                    amz_id = str(row.get('AMZ ID', f'AUTO-{idx}'))
                    if amz_id == 'nan' or not amz_id:
                        amz_id = f'AUTO-{idx}'

                    name = str(row.get('EMP Name', ''))
                    site = str(row.get('Building', 'AUH1'))
                    mgr = str(row.get('Line Manager', ''))
                    shift = str(row.get('Shift', ''))
                    agency = str(row.get('3P', ''))
                    attendance = str(row.get('Attendance ', row.get('Attendance', 'Open')))
                    doj = str(row.get('DOJ', str(datetime.date.today())))

                    case_id = f"CASE-{psoft_no if psoft_no and psoft_no != 'nan' else idx}"

                    c.execute('''INSERT OR IGNORE INTO cases (
                        id, login, empid, name, site, mgr, shift, agency, absent, created, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                              (str(case_id), str(amz_id), str(psoft_no), str(name), str(site), str(mgr), str(shift), str(agency), str(attendance), str(doj)[:10], "Open"))

                conn.commit()
            except Exception as e:
                print("Error loading excel sheet:", e)

    conn.close()


def get_user_by_credential(val):
    if not val:
        return None
    db = get_db()
    row = db.execute('SELECT * FROM users WHERE token=? OR alias=?', (val.strip().lower(), val.strip().lower())).fetchone()
    db.close()
    return dict(row) if row else None


def load_cases(user):
    query, params, conds = 'SELECT * FROM cases', [], []
    if user['role'] not in ('Admin', 'VPOC', 'PXT') and user['sites'] != 'All':
        user_sites = [s.strip() for s in user['sites'].split(',')]
        conds.append(f"site IN ({','.join('?' for _ in user_sites)})")
        params.extend(user_sites)
    if conds:
        query += ' WHERE ' + ' AND '.join(conds)
    query += ' ORDER BY created DESC, id DESC'
    db = get_db()
    rows = [dict(r) for r in db.execute(query, params).fetchall()]
    db.close()
    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=CASE_COLS)
    for col in CASE_COLS:
        if col not in df.columns:
            df[col] = ""
    return prepare(df.fillna(""))


def read_table(sql):
    db = get_db()
    rows = [dict(r) for r in db.execute(sql).fetchall()]
    db.close()
    return pd.DataFrame(rows)


# ----------------------------------------------------------------
# UI BUILDING BLOCKS
# ----------------------------------------------------------------
def page_shell(user, pill, title, sub):
    st.markdown(topbar_html(user), unsafe_allow_html=True)
    st.markdown(hero_html(pill, title, sub), unsafe_allow_html=True)


def set_page(p):
    st.session_state.page = p


@st.dialog("Case details")
def show_case(r):
    rows = [("Case ID", r["id"]), ("Employee", r["name"]), ("Login", r["login"]), ("Employee ID", r["empid"]),
            ("Site", r["site"]), ("Manager", r["mgr"]), ("Shift", r["shift"]), ("Agency", r["agency"]),
            ("Attendance / absent", r["absent"]), ("Opened", r["created"]), ("Status", r["status"]),
            ("Outcome", r["outcome"]), ("Reason", r["reason"]), ("Notes", r["notes"])]
    body = "".join(f"<b>{esc(k)}</b><span>{esc(v) or '–'}</span>" for k, v in rows)
    st.markdown(f'<div class="kv">{body}</div>', unsafe_allow_html=True)


def cases_table(view):
    """Styled table with real 'View' buttons + pagination."""
    total = len(view)
    pages = max(1, math.ceil(total / PAGE_SIZE))
    cur = min(max(1, st.session_state.get("page", 1)), pages)
    st.session_state.page = cur
    start = (cur - 1) * PAGE_SIZE
    chunk = view.iloc[start:start + PAGE_SIZE]
    widths = [1.3, 0.9, 1.5, 1.2, 1.3, 1.0, 1.0]

    with st.container(key="thead_cases"):
        for col, t in zip(st.columns(widths), ["Case ID", "Site", "Type", "Status", "Opened Date", "Days Open", "Actions"]):
            col.markdown(f'<div class="th">{t}</div>', unsafe_allow_html=True)

    if chunk.empty:
        st.info("No cases match your search.")
    for n, (_, r) in enumerate(chunk.iterrows()):
        opened = r["_created"].strftime("%b %d, %Y") if pd.notna(r["_created"]) else "–"
        days = "–" if pd.isna(r["_days"]) else int(r["_days"])
        with st.container(key=f"row_{cur}_{n}"):
            c = st.columns(widths)
            c[0].markdown(f'<div class="td id">{esc(r["id"])}</div>', unsafe_allow_html=True)
            c[1].markdown(f'<div class="td">{esc(r["site"])}</div>', unsafe_allow_html=True)
            c[2].markdown(f'<div class="td">{esc(r["_type"])}</div>', unsafe_allow_html=True)
            c[3].markdown(pill_html(r["_g"], r["status"] or "Open"), unsafe_allow_html=True)
            c[4].markdown(f'<div class="td">{opened}</div>', unsafe_allow_html=True)
            c[5].markdown(f'<div class="td">{days}</div>', unsafe_allow_html=True)
            with c[6]:
                with st.container(key=f"view_{cur}_{n}"):
                    if st.button("👁  View", key=f"viewbtn_{cur}_{n}"):
                        show_case(r.to_dict())

    first, last = (start + 1 if total else 0), min(start + PAGE_SIZE, total)
    with st.container(key="pager"):
        w0 = max(1, min(cur - 2, pages - 4))
        nums = list(range(w0, min(pages, w0 + 4) + 1))
        cols = st.columns([6] + [0.5] * (len(nums) + 2))
        cols[0].markdown(f'<div class="showing">Showing {first}–{last} of {total} cases</div>', unsafe_allow_html=True)
        cols[1].button("‹", key="pg_prev", disabled=cur <= 1, on_click=set_page, args=(cur - 1,))
        for i, p in enumerate(nums):
            cols[2 + i].button(str(p), key=f"pg_{p}", type="primary" if p == cur else "secondary",
                               on_click=set_page, args=(p,))
        cols[-1].button("›", key="pg_next", disabled=cur >= pages, on_click=set_page, args=(cur + 1,))


# ----------------------------------------------------------------
# PAGES
# ----------------------------------------------------------------
def page_dashboard(user, df):
    page_shell(user, "Cases", "Cases Overview", "Track, manage and resolve workplace behaviour cases efficiently.")

    g = df["_g"]
    pending = ~g.isin(["open", "closed"])
    defs = [
        ("Total Cases", pd.Series(True, index=df.index), "#f43f5e", "#ffe4e8", "doc"),
        ("Open Cases", g == "open", "#10b981", "#d9f7ea", "target"),
        ("Closed Cases", g == "closed", "#3b82f6", "#dbeafe", "box"),
        ("Pending Cases", pending, "#f59e0b", "#fef0d3", "cube"),
        ("Pending > 5 Days", pending & (df["_days"] > 5), "#8b5cf6", "#ede9fe", "shieldclock"),
    ]
    for i, (col, (label, mask, color, soft, icon)) in enumerate(zip(st.columns(5), defs)):
        vals, pct = series_and_trend(df, mask)
        col.markdown(kpi_html(label, int(mask.sum()), color, soft, icon, vals, delta_html(pct), uid=i),
                     unsafe_allow_html=True)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    left, right = st.columns([2.35, 1], gap="medium")

    with left:
        with st.container(border=True, key="card_recent"):
            h1, h2, h3 = st.columns([2.1, 2.3, 1.2], vertical_alignment="center")
            h1.markdown(card_header_html("check", "Recent Cases", "Latest cases across all sites"), unsafe_allow_html=True)
            search = h2.text_input("Search", placeholder="Search by Case ID, Site, Type...",
                                   label_visibility="collapsed", key="q_search")
            sites = ["All Sites"] + sorted(s for s in df["site"].unique() if s)
            site = h3.selectbox("Site", sites, label_visibility="collapsed", key="q_site")

            view = df
            if site != "All Sites":
                view = view[view["site"] == site]
            if search.strip():
                s = search.strip().lower()
                hay = (view["id"] + " " + view["site"] + " " + view["_type"] + " " + view["name"] + " " + view["login"]).str.lower()
                view = view[hay.str.contains(s, regex=False)]
            sig = (search, site)
            if st.session_state.get("_sig") != sig:
                st.session_state["_sig"] = sig
                st.session_state.page = 1
            cases_table(view)

    with right:
        with st.container(border=True, key="card_sites"):
            st.markdown(card_header_html("pin", "Cases by Site", "Total cases at each site"), unsafe_allow_html=True)
            st.markdown(sites_html(df), unsafe_allow_html=True)


def page_cases(user, df):
    page_shell(user, "Cases", "Cases Dashboard",
               "Real-time tracking of employee roster performance, attendance, and operational status.")
    k = st.columns(3)
    k[0].markdown(kpi_html("Total Records", len(df), "#f43f5e", "#ffe4e8", "doc", delta="Across all visible sites"), unsafe_allow_html=True)
    k[1].markdown(kpi_html("Active Sites", df.loc[df["site"] != "", "site"].nunique(),
                           "#3b82f6", "#dbeafe", "pin", delta="Sites with cases"), unsafe_allow_html=True)
    k[2].markdown(kpi_html("System Status", "Operational", "#10b981", "#d9f7ea", "target", delta="All services running", small=True),
                  unsafe_allow_html=True)
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    with st.container(border=True, key="card_cases"):
        a, b, c = st.columns([2.4, 1.3, 1.3], vertical_alignment="center")
        a.markdown(card_header_html("list", "All Cases", "Filter and export the full case list"), unsafe_allow_html=True)
        site = b.selectbox("Site", ["All Sites"] + sorted(s for s in df["site"].unique() if s),
                           label_visibility="collapsed", key="cd_site")
        status = c.selectbox("Status", ["All Status", "Open", "In Review / Pending", "Closed"],
                             label_visibility="collapsed", key="cd_status")
        view = df
        if site != "All Sites":
            view = view[view["site"] == site]
        if status == "Open":
            view = view[view["_g"] == "open"]
        elif status == "Closed":
            view = view[view["_g"] == "closed"]
        elif status != "All Status":
            view = view[~view["_g"].isin(["open", "closed"])]
        out = view[CASE_COLS]
        if out.empty:
            st.info("No records found matching your selected criteria.")
        else:
            st.dataframe(out, use_container_width=True, height=470, hide_index=True)
            st.download_button("⬇ Export CSV", out.to_csv(index=False).encode(), "wbc_cases.csv", "text/csv")


def simple_table_page(user, pill, title, sub, icon, card_title, card_sub, sql, kpis, empty_msg):
    page_shell(user, pill, title, sub)
    data = read_table(sql)
    cards = kpis(data)
    if cards:
        for col, html_ in zip(st.columns(len(cards)), cards):
            col.markdown(html_, unsafe_allow_html=True)
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    with st.container(border=True, key=f"card_{pill.lower().replace(' ', '')}"):
        st.markdown(card_header_html(icon, card_title, card_sub), unsafe_allow_html=True)
        if data.empty:
            st.info(empty_msg)
        else:
            st.dataframe(data, use_container_width=True, height=460, hide_index=True)


def ua_kpis(d):
    if d.empty:
        return []
    return [kpi_html("Total Offences", len(d), "#f43f5e", "#ffe4e8", "shieldclock", delta="All recorded offences"),
            kpi_html("Employees", d["login"].nunique(), "#8b5cf6", "#ede9fe", "user", delta="Unique logins"),
            kpi_html("Sites Affected", d["site"].nunique(), "#3b82f6", "#dbeafe", "pin", delta="Distinct sites")]


def upl_kpis(d):
    if d.empty:
        return []
    sched, upl = int(d["scheduled_days"].sum()), int(d["upl_days"].sum())
    pct = f"{upl / sched * 100:.1f}%" if sched else "0%"
    return [kpi_html("Employees Tracked", len(d), "#3b82f6", "#dbeafe", "user", delta="In UPL summary"),
            kpi_html("Total UPL Days", upl, "#f59e0b", "#fef0d3", "cube", delta=f"of {sched} scheduled days"),
            kpi_html("Overall UPL %", pct, "#8b5cf6", "#ede9fe", "shieldclock", delta="UPL / scheduled")]


def page_users(user):
    page_shell(user, "Access Control", "User Management", "Manage administrative users, roles, and facility permissions.")
    if user["role"] != "Admin":
        st.error("Access Denied: Admin privileges required to view users.")
        return
    data = read_table("SELECT alias, role, sites, added, token FROM users")
    with st.container(border=True, key="card_users"):
        st.markdown(card_header_html("user", "Portal Users", "Roles and facility permissions"), unsafe_allow_html=True)
        st.dataframe(data, use_container_width=True, height=400, hide_index=True)


def page_settings(user):
    page_shell(user, "System", "Settings", "Portal configuration, environment status, and system settings.")
    with st.container(border=True, key="card_settings"):
        st.markdown(card_header_html("target", "System Status", "Environment and database"), unsafe_allow_html=True)
        st.success("System is fully synchronized with the local database and excel repository.")
        st.markdown(f'<div class="kv"><b>Database</b><span>{esc(os.path.abspath(DB_PATH))}</span>'
                    f'<b>Signed in as</b><span>{esc(user["alias"])} ({esc(user["role"])})</span>'
                    f'<b>Sites</b><span>{esc(user["sites"])}</span></div>', unsafe_allow_html=True)


# ----------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------
NAV = ["Dashboard", "Cases Dashboard", "UA Offences Tracker", "UPL Summary Analytics", "User Management", "Settings"]


def main():
    st.markdown(BASE_CSS, unsafe_allow_html=True)
    init_db()

    if "token" not in st.session_state:
        st.session_state.token = ""
    if "token" in st.query_params and not st.session_state.token:
        st.session_state.token = st.query_params["token"]
    user = get_user_by_credential(st.session_state.token)

    # ---------- login ----------
    if not user:
        st.markdown(LOGIN_CSS, unsafe_allow_html=True)
        st.markdown("<div style='height:9vh'></div>", unsafe_allow_html=True)
        _, mid, _ = st.columns([1, 1.2, 1])
        with mid:
            with st.container(border=True, key="card_login"):
                st.markdown(BRAND_HTML + '<div class="login-t">Welcome back</div>'
                            '<div class="login-s">Enter your authorized user alias to access the portal.</div>',
                            unsafe_allow_html=True)
                alias = st.text_input("User alias", value="javmuhak", placeholder="e.g. javmuhak",
                                      label_visibility="collapsed")
                if st.button("Sign In", use_container_width=True):
                    u = get_user_by_credential(alias)
                    if u:
                        st.session_state.token = u["alias"]
                        st.rerun()
                    else:
                        st.error("Invalid alias. Please verify and try again.")
        st.stop()

    # ---------- sidebar ----------
    with st.sidebar:
        st.markdown(BRAND_HTML, unsafe_allow_html=True)
        menu = st.radio("Navigation", NAV, label_visibility="collapsed", key="nav")
        with st.container(key="signout"):
            if st.button("Sign out", use_container_width=True):
                st.session_state.clear()
                st.query_params.clear()
                st.rerun()
        st.markdown('<div class="side-foot">Better Workplace<br>Safer Tomorrow<span></span></div>', unsafe_allow_html=True)

    # ---------- pages ----------
    if menu == "Dashboard":
        page_dashboard(user, load_cases(user))
    elif menu == "Cases Dashboard":
        page_cases(user, load_cases(user))
    elif menu == "UA Offences Tracker":
        simple_table_page(user, "Compliance", "UA Offences Tracker",
                          "Comprehensive overview of recorded unauthorized absence offences.", "list",
                          "UA Offences", "Most recent offences first",
                          "SELECT * FROM ua_offences ORDER BY date DESC", ua_kpis,
                          "No UA offences recorded in the database.")
    elif menu == "UPL Summary Analytics":
        simple_table_page(user, "Analytics", "UPL Summary Analytics",
                          "Unplanned leave and schedule performance summary.", "list",
                          "UPL Summary", "Unplanned leave per employee",
                          "SELECT * FROM upl_summary ORDER BY updated DESC", upl_kpis,
                          "No UPL summary data available.")
    elif menu == "User Management":
        page_users(user)
    else:
        page_settings(user)


if __name__ == "__main__":
    main()
