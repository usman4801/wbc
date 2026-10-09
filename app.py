import streamlit as st
import sqlite3
import os
import io
import csv
import copy
import math
import shutil
import hashlib
import tempfile
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
USER_MGMT_BYPASS = {"javmuhak"}                                   # aliases that can open User Management without being Admin
TOP_N_SITES = 3                                                 # Cases by Site + mountain chart show this many

UAL = ["", "Verbal Coaching", "Documented Coaching", "First Warning",
       "Second Warning", "Final Warning", "Termination"]
REASONS = {"Sick Leave": "Sick Leave", "Authorized": "Authorized", "Unauthorized": "Unauthorized",
           "Incorrect Entry on DWD": "Incorrect Entry on DWD", "Converted to PL": "Converted to PL"}
NO_DOC = {"Incorrect Entry on DWD", "Converted to PL"}            # no document needed
OPTIONAL_DOC = {"Sick Leave"}                                     # upload offered, but case can be submitted without it
UPL_REVERSING = {"Incorrect", "Incorrect Entry on DWD", "Converted to PL"}   # take a day off UPL
DOC_TYPES = ["", "Medical Certificate", "HRBP Approval", "Warning Letter", "Email Approval", "Other"]
ADMIN_ROLES = ("admin", "hrbp")                                   # lower-case; can override escalation level
EXCLUDED_ATTENDANCE = {"P", "OFF"}                                # present / weekly-off rows are not WBC cases
ALL_ACCESS_ROLES = ("admin", "vpoc", "pxt")                       # see every site
UPLOAD_DIR = os.environ.get("WBC_UPLOAD_DIR", "wbc_uploads")
S3_BUCKET = os.environ.get("WBC_S3_BUCKET", "")                   # optional: upload to S3 instead
S3_PREFIX = os.environ.get("WBC_S3_PREFIX", "wbc-uploads")

CASE_COLS = ["id", "login", "empid", "name", "site", "mgr", "shift", "agency", "absent",
             "created", "status", "outcome", "reason", "doc_type", "doc_file", "notes",
             "closed", "source", "sick_hint", "ua_escalation_level",
             "escalation_valid_until", "closedby", "on_site", "closed_by",
             "escalation_level", "escalation_action", "present_status"]

# ----------------------------------------------------------------
# SITE MAP  (ported from the old portal: Country -> BU -> Sites)
# ----------------------------------------------------------------
SITE_MAP_DEFAULT = {
    "ARE": {
        "FC/SC": ["AUH1", "AUH3", "DAD1", "DWC3", "DWC5", "DXB3", "DXB5", "DXB8"],
        "AMZL": ["AUH2", "DAD2", "DAD6", "DAD9", "DDB3", "DDB6", "DDB7", "DSH6", "DUD2", "DUD3",
                 "DUF1", "DUF2", "DXD7"],
    },
    "EGY": {
        "FC/SC": ["CAI6", "CAI9", "DEG1", "DGI8", "DXA5", "EGY2", "SPX5"],
        "AMZL": ["DAI3", "DAI4", "DEX5", "DGI7", "DRO5", "DTT4"],
    },
    "SAU": {
        "FC/SC": ["JED4", "JED7", "RUH8", "RYD5"],
        "AMZL": ["DAK1", "DHU3", "DJD1", "DJD2", "DJD7", "DME6", "DMK2", "DMM2", "DMM5", "DRU4",
                 "DRY3", "DRY4", "DRY7", "RUH5"],
    },
    "TUR": {"FC/SC": ["IST2"], "AMZL": []},
}
COUNTRY_LABELS = {"ARE": "UAE", "EGY": "Egypt", "SAU": "KSA", "TUR": "Turkiye"}
COUNTRY_FLAGS = {"ARE": "🇦🇪", "EGY": "🇪🇬", "SAU": "🇸🇦", "TUR": "🇹🇷"}
TARGET_SITES = ["AUH1", "AUH3", "DAD1", "DWC3", "DWC5", "DXB3", "DXB5", "DXB8"]   # DWD sync default


# ----------------------------------------------------------------
# DESIGN SYSTEM  (CSS + SVG helpers)
# ----------------------------------------------------------------
BASE_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root{--navy:#0f1f4b;--blue:#2563eb;--muted:#64748b;--line:#e8edf5;}
html{font-size:13.5px !important;}
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"], button, input, textarea, select {
  font-family:'Inter','Segoe UI',system-ui,-apple-system,sans-serif !important; }
[data-testid="stAppViewContainer"]{background:#f6f8fc;}
[data-testid="stHeader"]{background:transparent;}
[data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer{display:none !important;}
[data-testid="stMainBlockContainer"]{padding:0.4rem 1.5rem 1.5rem;max-width:100%;}
h1,h2,h3{color:var(--navy);}

/* ---------- sidebar ---------- */
[data-testid="stSidebarNav"]{display:none !important;}
[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#fff 0%,#fff 55%,#f2f1ff 80%,#e3e2ff 100%);
  border-right:1px solid var(--line);min-width:230px !important;max-width:230px !important;}
[data-testid="stSidebarHeader"]{min-height:0;height:auto;padding:.3rem .8rem 0;}
[data-testid="stSidebarContent"]{padding:0 .7rem;}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{gap:.2rem;}
.brand{display:flex;align-items:center;gap:10px;padding:4px 4px 16px;}
.brand b{display:block;font-size:1.2rem;font-weight:800;color:var(--navy);line-height:1.1;}
.brand small{display:block;font-size:.62rem;color:var(--muted);margin-top:3px;white-space:nowrap;}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]{
  padding:.55rem .75rem;border-radius:10px;gap:.7rem;color:#475569;font-weight:500;}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover{background:#f1f5fb;}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] *{color:#475569;font-size:.9rem;white-space:nowrap;}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"]{background:#e6eefd;}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] *{color:var(--blue);font-weight:600;}
.side-foot{position:fixed;left:24px;bottom:28px;font-size:.95rem;line-height:1.35;font-weight:500;
  background:linear-gradient(90deg,#3b5bdb,#7c5cff);-webkit-background-clip:text;background-clip:text;color:transparent;}
.side-foot span{display:block;width:28px;height:2px;margin-top:7px;background:#6366f1;border-radius:2px;}
.st-key-signout button{background:transparent;border:1px solid var(--line);color:var(--muted);
  border-radius:10px;font-size:.8rem;margin-top:12px;}

/* ---------- top bar ---------- */
.topbar{display:flex;justify-content:space-between;align-items:center;margin:0 0 10px;}
.tb-left{display:flex;align-items:center;gap:10px;}
.wave{font-size:1.5rem;}
.tb-title{font-size:1.3rem;font-weight:800;color:var(--navy);line-height:1.15;}
.tb-sub{font-size:.8rem;color:var(--muted);}
.tb-right{display:flex;align-items:center;gap:18px;}
.online{display:inline-flex;align-items:center;gap:7px;background:#e3f8ee;color:#059669;
  font-size:.72rem;font-weight:600;padding:6px 12px;border-radius:999px;}
.online i{width:7px;height:7px;border-radius:50%;background:#10b981;display:inline-block;}
.tb-date{display:flex;align-items:center;gap:8px;font-size:.72rem;color:#475569;line-height:1.35;}
.tb-sep{width:1px;height:30px;background:var(--line);}
.tb-user{display:flex;align-items:center;gap:9px;}
.avatar{width:36px;height:36px;border-radius:50%;background:#dbe7ff;color:var(--blue);
  display:flex;align-items:center;justify-content:center;}
.tb-user b{display:block;font-size:.82rem;color:var(--navy);}
.tb-user small{display:block;font-size:.68rem;color:var(--muted);}

/* ---------- stat chips (replace the 5 KPI boxes) ---------- */
.chips{display:flex;flex-wrap:wrap;gap:9px;margin:2px 0 14px;}
.chip{display:inline-flex;align-items:center;gap:8px;padding:7px 13px;border-radius:10px;color:#fff;
  font-size:.78rem;font-weight:600;background:linear-gradient(135deg,#9a88f7,#7b6be8);
  box-shadow:0 4px 12px rgba(123,107,232,.26);}
.chip b{background:rgba(255,255,255,.24);padding:1px 9px;border-radius:7px;font-size:.8rem;font-weight:700;}

/* ---------- cards ---------- */
[class*="st-key-card_"]{background:#fff;border:1px solid var(--line) !important;border-radius:14px !important;
  box-shadow:0 2px 10px rgba(30,60,120,.05);padding:8px 12px 12px;}
.card-h{display:flex;align-items:center;gap:10px;}
.card-ico{width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;
  background:#e3edff;color:var(--blue);flex:none;}
.card-t{font-size:.92rem;font-weight:700;color:var(--navy);line-height:1.2;}
.card-s{font-size:.72rem;color:var(--muted);}
[class*="st-key-card_"] [data-testid="stTextInput"] input,
[class*="st-key-card_"] [data-baseweb="select"] > div{border-radius:10px;border-color:#dfe6f1;font-size:.8rem;min-height:36px;}

/* ---------- case table ---------- */
[class*="st-key-thead_"]{background:#f4f6fb;border-radius:8px;padding:8px 10px;margin-top:4px;gap:0;}
[class*="st-key-row_"]{border-bottom:1px solid #eef2f7;padding:5px 10px;gap:0;}
[class*="st-key-row_"]:hover{background:#fafcff;}
[class*="st-key-thead_"] [data-testid="stHorizontalBlock"],
[class*="st-key-row_"] [data-testid="stHorizontalBlock"]{align-items:center;gap:.4rem;}
.th{font-size:.72rem;font-weight:600;color:#475569;}
.td{font-size:.78rem;color:#334155;}
.td.id{color:#1e293b;font-weight:500;white-space:nowrap;}
.pill{display:inline-block;padding:3px 13px;border-radius:999px;font-size:.72rem;font-weight:600;}
.p-open{background:#ffe8ea;color:#e11d48;}
.p-review{background:#fff1d6;color:#d97706;}
.p-closed{background:#d9f7ea;color:#059669;}
.p-pending{background:#ece8ff;color:#7c3aed;}
.p-other{background:#eef2f7;color:#475569;}
[class*="st-key-view_"] button{border:none;background:transparent;color:var(--blue);font-weight:600;
  font-size:.78rem;padding:0;min-height:0;box-shadow:none;}
[class*="st-key-view_"] button:hover{background:transparent;color:#1d4ed8;}
.showing{font-size:.74rem;color:var(--muted);padding-top:6px;}
[class*="st-key-pager"] button{min-height:30px;padding:0 6px;border-radius:8px;border:1px solid #dfe6f1;
  background:#fff;color:#475569;font-size:.76rem;}
[class*="st-key-pager"] button[data-testid="stBaseButton-primary"]{background:var(--blue);border-color:var(--blue);color:#fff;}

/* ---------- cases by site ---------- */
.sites-scroll{max-height:520px;overflow-y:auto;}
.site-row{display:grid;grid-template-columns:70px 1fr 46px;align-items:center;gap:8px;
  padding:11px 0;border-bottom:1px solid #f0f3f8;}
.site-row:last-child{border-bottom:none;}
.site-l{display:flex;align-items:center;gap:8px;font-size:.8rem;font-weight:600;color:#1e293b;}
.site-l i{width:8px;height:8px;border-radius:50%;display:inline-block;flex:none;}
.site-n{font-size:.8rem;font-weight:600;color:#1e293b;}
.bar{height:6px;background:#eef2f9;border-radius:99px;overflow:hidden;margin-top:3px;}
.bar span{display:block;height:100%;border-radius:99px;}
.site-p{font-size:.7rem;color:var(--muted);text-align:right;}

/* ---------- mountain chart widget ---------- */
.mtn-top{display:flex;justify-content:space-between;align-items:center;gap:10px;
  background:linear-gradient(135deg,#f3f0ff,#e8f0ff);border-radius:12px;padding:10px 14px;margin:8px 0 6px;}
.mtn-k{font-size:.66rem;font-weight:700;color:#6d5bd0;text-transform:uppercase;letter-spacing:.5px;}
.mtn-v{font-size:1.25rem;font-weight:800;color:var(--navy);line-height:1.15;}
.mtn-badge{display:inline-flex;align-items:center;gap:6px;padding:6px 12px;border-radius:999px;color:#fff;
  font-size:.74rem;font-weight:700;background:linear-gradient(135deg,#9a88f7,#7b6be8);
  box-shadow:0 4px 12px rgba(123,107,232,.26);white-space:nowrap;}
.mtn-cap{font-size:.68rem;color:var(--muted);margin:2px 0 0 2px;}
.mtn-legend{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:6px;}
.mtn-tile{border:1px solid var(--line);border-top-width:3px;border-radius:10px;padding:7px 10px;background:#fff;}
.mtn-tile em{display:block;font-style:normal;font-size:.72rem;font-weight:600;color:#475569;}
.mtn-tile b{display:block;font-size:1.1rem;font-weight:800;color:var(--navy);line-height:1.2;}
.mtn-tile small{display:block;font-size:.66rem;color:var(--muted);}

/* ---------- dialog ---------- */
.kv{display:grid;grid-template-columns:130px 1fr;gap:7px 12px;font-size:.84rem;}
.kv b{color:#475569;font-weight:600;}
.kv.kv2{grid-template-columns:120px 1fr 120px 1fr;}
.esc-box{background:linear-gradient(135deg,#fff1f2,#fef3c7);border:1.5px solid #f97316;border-radius:10px;
  padding:10px 14px;margin:4px 0 10px;font-size:.8rem;color:#78350f;line-height:1.6;}
.esc-t{font-size:.68rem;font-weight:700;color:#9a3412;text-transform:uppercase;letter-spacing:.5px;margin-bottom:3px;}
.esc-lvl{font-size:1rem;font-weight:800;color:#c2410c;}
</style>
"""

LOGIN_CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"]{display:none !important;}
[data-testid="stAppViewContainer"]{background:linear-gradient(135deg,#eaf1ff 0%,#f4f1ff 60%,#e6e4ff 100%);}
.st-key-card_login{padding:22px 26px 24px;box-shadow:0 10px 40px rgba(37,99,235,.10);}
.st-key-card_login .brand{justify-content:center;padding-bottom:4px;}
.login-t{text-align:center;font-size:1.25rem;font-weight:800;color:#0f1f4b;margin:8px 0 2px;}
.login-s{text-align:center;font-size:.8rem;color:#64748b;margin-bottom:8px;}
.st-key-card_login button[data-testid="stBaseButton-secondary"]{background:#7b6be8;color:#fff;border:none;
  border-radius:10px;font-weight:600;min-height:40px;}
</style>
"""

ICONS = {
    "target": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
    "pin": '<path d="M12 21s7-6.2 7-11a7 7 0 1 0-14 0c0 4.8 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/>',
    "check": '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 12l3 3 5-6"/>',
    "cal": '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
    "list": '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
    "chart": '<path d="M3 20h18"/><path d="M4 16l5-6 4 4 7-9"/>',
}


def svg(name, size=22):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')


BRAND_HTML = """
<div class="brand">
<svg width="36" height="40" viewBox="0 0 40 44"><defs><linearGradient id="bg1" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="#3b82f6"/><stop offset="1" stop-color="#1e3a8a"/></linearGradient></defs>
<path d="M20 2 4 8v14c0 11 7 18 16 21 9-3 16-10 16-21V8z" fill="url(#bg1)"/>
<path d="M20 10 10 14v8c0 7 4 11 10 14 6-3 10-7 10-14v-8z" fill="none" stroke="#fff" stroke-width="1.8" opacity=".7"/>
<path d="M15 22l4 4 7-8" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
<div><b>WBC Portal</b><small>Welcome Back Conversation</small></div></div>
"""

SPARKLE = ('<svg width="14" height="14" viewBox="0 0 24 24" fill="#fff"><path d="M12 2l2.2 6.3L20.5 10l-6.3 2.2L12 18.5l'
           '-2.2-6.3L3.5 10l6.3-1.7zM19 15l.9 2.4 2.4.9-2.4.9L19 21.6l-.9-2.4-2.4-.9 2.4-.9z"/></svg>')

SITE_COLORS = ["#3b82f6", "#10b981", "#8b5cf6", "#f59e0b", "#06b6d4"]


def esc(v):
    return _html.escape("" if v is None else str(v))


def clean_id(v):
    """Excel numbers arrive as '20808951.0' - hide the trailing .0."""
    t = "" if v is None else str(v)
    return t[:-2] if t.endswith(".0") else t


def now_local():
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("Asia/Dubai"))
    except Exception:
        return datetime.datetime.now()


def topbar_html(user, title, sub, wave=False):
    n = now_local()
    role = {"Admin": "Administrator"}.get(user["role"], user["role"])
    name = user["alias"].capitalize()
    w = '<span class="wave">👋</span>' if wave else ""
    return f"""
<div class="topbar">
 <div class="tb-left">{w}
  <div><div class="tb-title">{esc(title)}</div><div class="tb-sub">{esc(sub)}</div></div></div>
 <div class="tb-right">
  <span class="online"><i></i>System Online</span>
  <div class="tb-date">{svg('cal', 20)}<div>{n.strftime('%b %d, %Y')}<br>{n.strftime('%I:%M %p')}</div></div>
  <span class="tb-sep"></span>
  <div class="tb-user"><div class="avatar">{svg('user', 20)}</div>
   <div><b>{esc(name)}</b><small>{esc(role)}</small></div></div>
 </div></div>"""


def card_header_html(icon, title, sub):
    return (f'<div class="card-h"><div class="card-ico">{svg(icon, 18)}</div>'
            f'<div><div class="card-t">{esc(title)}</div><div class="card-s">{esc(sub)}</div></div></div>')


def chips_html(items):
    """Compact pill chips (label + number) - replaces the big KPI boxes."""
    body = "".join(f'<div class="chip">{SPARKLE}<span>{esc(l)}</span><b>{esc(v)}</b></div>' for l, v in items)
    return f'<div class="chips">{body}</div>'


def pill_html(group, label):
    cls = {"open": "p-open", "review": "p-review", "closed": "p-closed", "pending": "p-pending"}.get(group, "p-other")
    return f'<span class="pill {cls}">{esc(label)}</span>'


# ----------------------------------------------------------------
# ACCESS HELPERS
# ----------------------------------------------------------------
def is_all_access(user):
    """Admin / VPOC / PXT, or a user whose sites column is 'All' (any case)."""
    return (str(user.get("role", "")).lower() in ALL_ACCESS_ROLES
            or str(user.get("sites") or "").strip().lower() == "all")


def allowed_sites(user):
    """None = every site, otherwise the list of sites this user may see."""
    if is_all_access(user):
        return None
    return [s.strip() for s in str(user.get("sites") or "").split(",") if s.strip()]


def is_admin(user):
    return str(user.get("role", "")).lower() == "admin"


def is_admin_role(user):
    return str(user.get("role", "")).lower() in ADMIN_ROLES


def to_excel_bytes(df, sheet="Cases"):
    try:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name=sheet)
        return buf.getvalue()
    except Exception:
        return None


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


# ----------------------------------------------------------------
# DATABASE
# ----------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_columns(c, table, cols):
    have = {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
    for col, ddl in cols.items():
        if col not in have:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


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
    c.execute('''CREATE TABLE IF NOT EXISTS access_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, alias TEXT, name TEXT, email TEXT,
        country TEXT, bu TEXT, sites TEXT, role TEXT, status TEXT DEFAULT "pending",
        requested_at TEXT DEFAULT '', reviewed_by TEXT, reviewed_at TEXT,
        reject_reason TEXT DEFAULT "")''')
    c.execute('''CREATE TABLE IF NOT EXISTS custom_sites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        country TEXT NOT NULL, bu TEXT NOT NULL, site TEXT NOT NULL,
        active INTEGER DEFAULT 1, added_by TEXT, added_at TEXT,
        UNIQUE(country, bu, site))''')

    # columns used by the case-close flow / old portal schema (safe, idempotent)
    ensure_columns(c, "cases", {
        "closed_by": "TEXT DEFAULT ''", "escalation_level": "TEXT DEFAULT ''",
        "escalation_action": "TEXT DEFAULT ''", "present_status": "TEXT DEFAULT ''",
        "ua_escalation_level": "INTEGER DEFAULT 0", "escalation_valid_until": "TEXT DEFAULT ''",
        "closedby": "TEXT DEFAULT ''", "on_site": "TEXT DEFAULT ''"})
    ensure_columns(c, "ua_offences", {"offence_type": "TEXT DEFAULT ''", "name": "TEXT DEFAULT ''",
                                      "empid": "TEXT DEFAULT ''"})
    ensure_columns(c, "users", {"token": "TEXT", "added": "TEXT"})

    # Indexes
    c.execute("CREATE INDEX IF NOT EXISTS idx_cases_login ON cases(login)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_cases_site ON cases(site)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_cases_created ON cases(created)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ua_login ON ua_offences(login)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ua_site ON ua_offences(site)")

    # Seed default users - IGNORE (not REPLACE) so imported users / tokens are never overwritten
    c.execute("INSERT OR IGNORE INTO users (alias, role, sites, added, token) VALUES ('mnnafee', 'Admin', 'All', ?, 'mnnafee')",
              (str(datetime.date.today()),))
    c.execute("INSERT OR IGNORE INTO users (alias, role, sites, added, token) VALUES ('javmuhak', 'VPOC', 'All', ?, 'javmuhak')",
              (str(datetime.date.today()),))
    conn.commit()

    # ONE-TIME AUTO-IMPORT FROM 'Roster' SHEET OF EXCEL (only into an empty database, only once)
    count = c.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    done = c.execute("SELECT 1 FROM settings WHERE key='excel_imported'").fetchone()
    if count == 0 and not done:
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
                    if site.strip().lower() in ("nan", ""):
                        site = ""
                    mgr = str(row.get('Line Manager', ''))
                    shift = str(row.get('Shift', ''))
                    agency = str(row.get('3P', ''))
                    attendance = str(row.get('Attendance ', row.get('Attendance', 'Open')))
                    doj = str(row.get('DOJ', str(datetime.date.today())))
                    if attendance.strip().upper() in EXCLUDED_ATTENDANCE:
                        continue                                  # Present / OFF - no welcome back conversation needed

                    case_id = f"CASE-{psoft_no if psoft_no and psoft_no != 'nan' else idx}"

                    c.execute('''INSERT OR IGNORE INTO cases (
                        id, login, empid, name, site, mgr, shift, agency, absent, created, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                              (str(case_id), str(amz_id), str(psoft_no), str(name), str(site), str(mgr), str(shift), str(agency), str(attendance), str(doj)[:10], "Open"))

                c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('excel_imported', ?)", (file_path,))
                conn.commit()
            except Exception as e:
                print("Error loading excel sheet:", e)

    conn.close()


def get_user_by_credential(val):
    if not val:
        return None
    val = val.strip()
    db = get_db()
    # tokens from the old portal are mixed-case, aliases are lower-case
    row = db.execute('SELECT * FROM users WHERE token=? OR alias=?', (val, val.lower())).fetchone()
    db.close()
    return dict(row) if row else None


def load_cases(user):
    query_, params, conds = 'SELECT * FROM cases', [], []
    allowed = allowed_sites(user)
    if allowed is not None:
        if not allowed:
            conds.append("1=0")
        else:
            conds.append(f"site IN ({','.join('?' for _ in allowed)})")
            params.extend(allowed)
    if conds:
        query_ += ' WHERE ' + ' AND '.join(conds)
    query_ += ' ORDER BY created DESC, id DESC'
    db = get_db()
    rows = [dict(r) for r in db.execute(query_, params).fetchall()]
    db.close()
    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=CASE_COLS)
    for col in CASE_COLS:
        if col not in df.columns:
            df[col] = ""
    df = df.fillna("")
    df = df[~df["absent"].astype(str).str.strip().str.upper().isin(EXCLUDED_ATTENDANCE)]
    return prepare(df)


def query(sql, params=()):
    db = get_db()
    rows = [dict(r) for r in db.execute(sql, params).fetchall()]
    db.close()
    return rows


def execute(sql, params=()):
    db = get_db()
    db.execute(sql, params)
    db.commit()
    db.close()


def read_table(sql):
    db = get_db()
    rows = [dict(r) for r in db.execute(sql).fetchall()]
    db.close()
    return pd.DataFrame(rows)


# ----------------------------------------------------------------
# SITES  (country -> BU -> site, plus admin-added custom sites)
# ----------------------------------------------------------------
def get_site_map():
    merged = copy.deepcopy(SITE_MAP_DEFAULT)
    try:
        for r in query("SELECT country, bu, site FROM custom_sites WHERE active=1"):
            merged.setdefault(r["country"], {}).setdefault(r["bu"], [])
            if r["site"] not in merged[r["country"]][r["bu"]]:
                merged[r["country"]][r["bu"]].append(r["site"])
    except Exception:
        pass
    return merged


def site_meta(smap):
    """site -> (country, bu)"""
    return {s: (c, bu) for c, bus in smap.items() for bu, ss in bus.items() for s in ss}


def _valid_or_reset(key, options):
    if key in st.session_state and st.session_state[key] not in options:
        del st.session_state[key]


def site_filters(df, key, cols):
    """Country -> BU -> Site selector (from the old portal). Returns the filtered cases."""
    smap = get_site_map()
    meta = site_meta(smap)
    allowed = allowed_sites(current())
    counts = df["site"].value_counts().to_dict() if not df.empty else {}

    country_opts = ["All"] + list(smap.keys())
    _valid_or_reset(f"{key}_country", country_opts)
    country = cols[0].selectbox(
        "Country", country_opts, key=f"{key}_country", label_visibility="collapsed",
        format_func=lambda c: "All Countries" if c == "All" else f"{COUNTRY_FLAGS.get(c, '')} {COUNTRY_LABELS.get(c, c)}")

    bu_opts = ["All"] + sorted({bu for c, bus in smap.items() if country in ("All", c) for bu in bus})
    _valid_or_reset(f"{key}_bu", bu_opts)
    bu = cols[1].selectbox("BU", bu_opts, key=f"{key}_bu", label_visibility="collapsed",
                           format_func=lambda b: "All BUs" if b == "All" else b)

    pool = [s for s, (c, b) in meta.items() if country in ("All", c) and bu in ("All", b)]
    if country == "All" and bu == "All":
        pool += [s for s in counts if s and s not in meta]          # sites found in data but not in the map
    if allowed is not None:
        pool = [s for s in pool if s in allowed]
    pool = sorted(set(pool))
    site_opts = ["All"] + pool
    _valid_or_reset(f"{key}_site", site_opts)
    site = cols[2].selectbox("Site", site_opts, key=f"{key}_site", label_visibility="collapsed",
                             format_func=lambda s: "All Sites" if s == "All" else f"{s} ({counts.get(s, 0)})")

    if site != "All":
        return df[df["site"] == site]
    if country != "All" or bu != "All":
        return df[df["site"].isin(pool)]
    return df


def agency_filter(df, key, col):
    """Agency (3P) filter - like the old portal. Blank agencies are grouped as 'Unassigned'."""
    ag = df["agency"].astype(str).str.strip().replace({"": "Unassigned", "nan": "Unassigned", "None": "Unassigned"})
    counts = ag.value_counts().to_dict()
    opts = ["All"] + sorted(counts)
    _valid_or_reset(key, opts)
    pick = col.selectbox("Agency", opts, key=key, label_visibility="collapsed",
                         format_func=lambda a: "All Agencies" if a == "All" else f"{a} ({counts.get(a, 0)})")
    return df if pick == "All" else df[ag == pick]


# ----------------------------------------------------------------
# CASES BY SITE (top 3, open cases only) + MOUNTAIN CHART
# ----------------------------------------------------------------
def top_open_sites(df, n=TOP_N_SITES):
    """Returns (open cases with a site, [(site, open_count), ...] for the top n sites)."""
    if df.empty:
        return df, []
    op = df[(df["_g"] == "open") & (df["site"].astype(str).str.strip() != "")]
    counts = op["site"].value_counts().to_dict()
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
    return op, top


def sites_html(df):
    op, top = top_open_sites(df)
    if not top:
        return '<div class="card-s" style="padding:16px 0">No open cases right now.</div>'
    total, peak = max(len(op), 1), max(top[0][1], 1)
    rows = []
    for i, (site, c) in enumerate(top):
        col = SITE_COLORS[i % len(SITE_COLORS)]
        rows.append(f'<div class="site-row"><div class="site-l"><i style="background:{col}"></i>{esc(site)}</div>'
                    f'<div><div class="site-n">{int(c)}</div><div class="bar"><span style="width:{c / peak * 100:.0f}%;background:{col}"></span></div></div>'
                    f'<div class="site-p">{c / total * 100:.1f}%</div></div>')
    return '<div class="sites-scroll">' + "".join(rows) + '</div>'


def _smooth_path(pts, top, base):
    """Smooth curve through points (Catmull-Rom -> cubic Bezier), kept inside the plot area."""
    if len(pts) < 3:
        return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < len(pts) else p2
        c1x, c1y = p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6
        c2x, c2y = p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6
        c1y, c2y = min(max(c1y, top), base), min(max(c2y, top), base)
        d += f" C{c1x:.1f},{c1y:.1f} {c2x:.1f},{c2y:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


def mountain_html(df):
    """Mountain (area) chart: open cases over time for the top 3 sites, plus a leader banner and totals."""
    op, top = top_open_sites(df)
    if not top:
        return '<div class="card-s" style="padding:16px 0">No open cases to compare.</div>'
    names = [s for s, _ in top]
    colors = {s: SITE_COLORS[i % len(SITE_COLORS)] for i, s in enumerate(names)}
    total_open = max(len(op), 1)
    lead, lead_n = top[0]

    banner = (f'<div class="mtn-top"><div><div class="mtn-k">Highest open cases</div>'
              f'<div class="mtn-v">🏆 {esc(lead)}</div></div>'
              f'<div class="mtn-badge">{lead_n} open · {lead_n / total_open * 100:.1f}%</div></div>')

    d = op[op["site"].isin(names) & op["_created"].notna()].copy()
    if d.empty:
        chart = '<div class="card-s" style="padding:12px 0">No dated open cases to chart.</div>'
        caption = ""
    else:
        span = (d["_created"].max() - d["_created"].min()).days
        freq = "W" if span <= 120 else "M"
        d["_b"] = d["_created"].dt.to_period(freq)
        buckets = pd.period_range(d["_b"].min(), d["_b"].max(), freq=freq)[-12:]
        piv = d.groupby(["_b", "site"]).size().unstack(fill_value=0)
        piv = piv.reindex(index=buckets, columns=names, fill_value=0)
        series = {s: [int(v) for v in piv[s]] for s in names}
        n = len(buckets)
        if n == 1:                                                   # a single bucket: draw it flat so it still shows
            series = {s: v * 2 for s, v in series.items()}
        npts = len(series[names[0]])
        labels = [p.start_time.strftime("%d %b") if freq == "W" else p.strftime("%b %y") for p in buckets]
        caption = f'<div class="mtn-cap">Open cases by {"week" if freq == "W" else "month"} opened</div>'

        W, H, L, R, T, B = 440, 215, 30, 14, 16, 30
        base = H - B
        ymax = max(max(max(v) for v in series.values()), 1)
        step = max(1, math.ceil(ymax / 4))
        ytop = step * 4

        def x_at(i):
            return L + (W - L - R) * i / (npts - 1)

        def y_at(v):
            return base - (base - T) * v / ytop

        parts = [f'<svg viewBox="0 0 {W} {H}" width="100%" style="display:block"><defs>']
        for i, s in enumerate(names):
            c = colors[s]
            parts.append(f'<linearGradient id="mg{i}" x1="0" y1="0" x2="0" y2="1">'
                         f'<stop offset="0" stop-color="{c}" stop-opacity=".55"/>'
                         f'<stop offset="1" stop-color="{c}" stop-opacity=".03"/></linearGradient>')
        parts.append('</defs>')
        for k in range(5):                                           # grid + y labels
            y = y_at(k * step)
            parts.append(f'<line x1="{L}" y1="{y:.1f}" x2="{W - R}" y2="{y:.1f}" stroke="#eef2f9" stroke-width="1"/>')
            parts.append(f'<text x="{L - 6}" y="{y + 3:.1f}" text-anchor="end" font-size="9.5" fill="#94a3b8">{k * step}</text>')
        for i, s in enumerate(names):                                # largest site is drawn first (at the back)
            pts = [(x_at(j), y_at(v)) for j, v in enumerate(series[s])]
            line = _smooth_path(pts, T, base)
            area = f'{line} L{pts[-1][0]:.1f},{base} L{pts[0][0]:.1f},{base} Z'
            parts.append(f'<path d="{area}" fill="url(#mg{i})"/>')
            parts.append(f'<path d="{line}" fill="none" stroke="{colors[s]}" stroke-width="2.2" '
                         f'stroke-linecap="round" stroke-linejoin="round"/>')
            pk = max(range(npts), key=lambda j: series[s][j])
            parts.append(f'<circle cx="{pts[pk][0]:.1f}" cy="{pts[pk][1]:.1f}" r="3.6" fill="#fff" '
                         f'stroke="{colors[s]}" stroke-width="2"/>')
        for i, lab in enumerate(labels):                             # x labels
            if n > 6 and i % 2:
                continue
            x = (L + W - R) / 2 if n == 1 else x_at(i)
            parts.append(f'<text x="{x:.1f}" y="{H - 10}" text-anchor="middle" font-size="9.5" fill="#94a3b8">{esc(lab)}</text>')
        parts.append('</svg>')
        chart = "".join(parts)

    tiles = []
    for i, (s, c) in enumerate(top):
        tiles.append(f'<div class="mtn-tile" style="border-top-color:{colors[s]}"><em>{"🏆 " if i == 0 else ""}{esc(s)}</em>'
                     f'<b>{int(c)}</b><small>{c / total_open * 100:.1f}% of open</small></div>')
    return banner + caption + chart + '<div class="mtn-legend">' + "".join(tiles) + '</div>'


# ----------------------------------------------------------------
# OLD-DATABASE IMPORT  (merge / replace from a wbc.db of the old portal)
# ----------------------------------------------------------------
# table -> (primary key column or None, de-dupe condition used when merging)
IMPORT_TABLES = {
    "cases": ("id", None),
    "upl_summary": ("login", None),
    "users": ("alias", None),
    "ua_offences": (None, "m.login=o.login AND m.date=o.date AND IFNULL(m.offence_type,'')=IFNULL(o.offence_type,'')"),
    "access_requests": (None, "IFNULL(m.alias,'')=IFNULL(o.alias,'') AND IFNULL(m.requested_at,'')=IFNULL(o.requested_at,'')"),
    "custom_sites": (None, "m.country=o.country AND m.bu=o.bu AND m.site=o.site"),
}


def import_old_db(raw, replace=False, drop_roster_placeholders=False):
    if not raw.startswith(b"SQLite format 3"):
        return False, "That file is not a SQLite database (expected the old wbc.db)."
    init_db()
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{DB_PATH}.bak_{stamp}"
    shutil.copy2(DB_PATH, backup)
    tmp = os.path.join(tempfile.gettempdir(), f"wbc_import_{stamp}.db")
    with open(tmp, "wb") as fh:
        fh.write(raw)
    conn = sqlite3.connect(DB_PATH)
    report = []
    try:
        conn.execute("ATTACH DATABASE ? AS old", (tmp,))
        for table, (key, dedupe) in IMPORT_TABLES.items():
            if not conn.execute("SELECT 1 FROM old.sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                continue
            new_cols = [r[1] for r in conn.execute(f"PRAGMA main.table_info({table})")]
            old_cols = {r[1] for r in conn.execute(f"PRAGMA old.table_info({table})")}
            cols = [c for c in new_cols if c in old_cols and not (key is None and c == "id")]
            if not cols:
                continue
            col_sql = ",".join(f'"{c}"' for c in cols)
            sel_sql = ",".join(f'o."{c}"' for c in cols)
            if replace:
                conn.execute(f"DELETE FROM main.{table}")
            if key:                                              # same key -> old (accurate) row wins
                cur = conn.execute(f"INSERT OR REPLACE INTO main.{table} ({col_sql}) SELECT {sel_sql} FROM old.{table} o")
            elif dedupe:
                cur = conn.execute(f"INSERT INTO main.{table} ({col_sql}) SELECT {sel_sql} FROM old.{table} o "
                                   f"WHERE NOT EXISTS (SELECT 1 FROM main.{table} m WHERE {dedupe})")
            else:
                cur = conn.execute(f"INSERT OR IGNORE INTO main.{table} ({col_sql}) SELECT {sel_sql} FROM old.{table} o")
            report.append(f"{table}: {cur.rowcount}")
        removed = 0
        if drop_roster_placeholders and not replace:
            cur = conn.execute("DELETE FROM main.cases WHERE id LIKE 'CASE-%' AND status IN ('Open','In Progress') "
                               "AND id NOT IN (SELECT id FROM old.cases)")
            removed = cur.rowcount
        conn.execute("INSERT OR REPLACE INTO main.settings (key, value) VALUES ('excel_imported', 'old-db-import')")
        conn.commit()
        conn.execute("DETACH DATABASE old")
    except Exception as e:
        conn.rollback()
        return False, f"Import failed, nothing changed: {e}  (backup: {backup})"
    finally:
        conn.close()
        try:
            os.remove(tmp)
        except OSError:
            pass
    msg = "Imported - " + ", ".join(report) if report else "Imported - no matching tables found in that file."
    if removed:
        msg += f", removed {removed} untouched roster placeholder cases"
    return True, msg + f".  Backup of the previous database: {os.path.basename(backup)}"


# ----------------------------------------------------------------
# DWD SYNC  (ported from the old /api/sync/dwd)
# ----------------------------------------------------------------
def yesterday_ast():
    ast = datetime.timezone(datetime.timedelta(hours=4))
    return (datetime.datetime.now(ast) - datetime.timedelta(days=1)).date()


def run_dwd_sync(csv_text, date_str, sites):
    done_key = f"dwd_sync_{date_str}"
    if query("SELECT 1 FROM settings WHERE key=?", (done_key,)):
        return False, f"{date_str} has already been synced - running it twice would double-count UPL days."
    raw_rows = list(csv.DictReader(io.StringIO(csv_text)))
    rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in raw_rows]
    if not rows:
        return False, "The CSV is empty."
    if "login" not in rows[0] or "absent" not in rows[0]:
        return False, "The CSV needs at least the columns: login, absent (also site, empid, name, agency, shift, mgr)."

    absent = []
    for r in rows:
        if r.get("absent", "") != "1":
            continue
        site = r.get("site", "")
        if sites and site not in sites:
            continue
        absent.append({"login": r.get("login", "").lower(), "empid": r.get("empid", ""), "name": r.get("name", ""),
                       "site": site, "agency": r.get("agency", "") or "Amazon", "shift": r.get("shift", ""),
                       "mgr": r.get("mgr", ""), "date": date_str})

    db = get_db()
    created = skipped = 0
    try:
        for emp in absent:
            short = hashlib.md5((emp["login"] + "|" + emp["date"]).encode()).hexdigest()[:8].upper()
            if db.execute("SELECT id FROM cases WHERE login=? AND absent=?", (emp["login"], emp["date"])).fetchone():
                skipped += 1
                continue
            db.execute("INSERT OR IGNORE INTO cases (id,login,empid,name,site,agency,shift,mgr,absent,created,source) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       ("WBC-AUTO-" + short, emp["login"], emp["empid"], emp["name"], emp["site"], emp["agency"],
                        emp["shift"], emp["mgr"], emp["date"], emp["date"], "dwd_sync"))
            created += 1
        for r in rows:                                           # UPL summary: +1 scheduled day per row (as before)
            lg = r.get("login", "").lower()
            if not lg:
                continue
            is_abs = 1 if r.get("absent", "") == "1" else 0
            if db.execute("SELECT 1 FROM upl_summary WHERE login=?", (lg,)).fetchone():
                db.execute("UPDATE upl_summary SET scheduled_days=scheduled_days+1, upl_days=upl_days+?, updated=? WHERE login=?",
                           (is_abs, date_str, lg))
            else:
                db.execute("INSERT INTO upl_summary (login,site,scheduled_days,upl_days,updated) VALUES (?,?,1,?,?)",
                           (lg, r.get("site", ""), is_abs, date_str))
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (done_key, datetime.datetime.now().isoformat()))
        db.commit()
    except Exception as e:
        db.rollback()
        return False, f"Sync failed, nothing saved: {e}"
    finally:
        db.close()
    return True, f"{date_str}: {created} new cases created, {skipped} already existed ({len(absent)} absent in selected sites)."


# ----------------------------------------------------------------
# UI BUILDING BLOCKS
# ----------------------------------------------------------------
def current():
    return st.session_state["_user"]


def page_shell(title, sub, wave=False):
    flash = st.session_state.pop("_flash", None)
    if flash:
        st.toast(flash, icon="✅")
    st.markdown(topbar_html(current(), title, sub, wave), unsafe_allow_html=True)


def set_page(p):
    st.session_state.cases_page = p


# ----------------------------------------------------------------
# CASE WORKFLOW  (remarks, authorized / unauthorized, escalation, warning letter, verbatim)
# ----------------------------------------------------------------
def ua_status(dates, today=None):
    """Offence chain: an offence counts only if the previous one is within 90 days."""
    today = today or datetime.date.today()
    ds = sorted({datetime.date.fromisoformat(str(d)[:10]) for d in dates if d})
    chain = []
    for i, d in enumerate(ds):
        if i == 0 or (d - ds[i - 1]).days <= 90:
            chain.append(d)
        else:
            chain = [d]
    recent = [d for d in chain if (today - d).days <= 90]
    level = min(len(recent), 6)
    valid = (recent[-1] + datetime.timedelta(days=90)).isoformat() if recent else ""
    return {"count": len(recent), "level": level, "valid_until": valid}


def ua_for(login):
    rows = query("SELECT date FROM ua_offences WHERE login=? ORDER BY date", (login,))
    return ua_status([r["date"] for r in rows])


def next_escalation(login):
    lvl = min(ua_for(login)["level"] + 1, 6)
    valid = (datetime.date.today() + datetime.timedelta(days=90)).isoformat()
    return lvl, UAL[lvl], valid


def save_upload(case_id, up):
    safe = up.name.replace("/", "_").replace("\\", "_")
    if S3_BUCKET:
        import boto3
        boto3.client("s3").upload_fileobj(io.BytesIO(up.getvalue()), S3_BUCKET, f"{S3_PREFIX}/{case_id}/{safe}",
                                          ExtraArgs={"ContentType": up.type or "application/octet-stream"})
    else:
        folder = os.path.join(UPLOAD_DIR, case_id)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, safe), "wb") as fh:
            fh.write(up.getvalue())
    return safe


def show_existing_doc(case_id, filename, tag="a"):
    if not filename:
        return
    if S3_BUCKET:
        try:
            import boto3
            url = boto3.client("s3").generate_presigned_url(
                "get_object", Params={"Bucket": S3_BUCKET, "Key": f"{S3_PREFIX}/{case_id}/{filename}"}, ExpiresIn=300)
            st.link_button(f"📎 {filename}", url)
            return
        except Exception:
            pass
    path = os.path.join(UPLOAD_DIR, case_id, filename)
    if os.path.exists(path):
        with open(path, "rb") as fh:
            st.download_button(f"📎 {filename}", fh.read(), filename, key=f"dl_{tag}_{case_id}")
    else:
        st.caption(f"Current document: {filename}")


def close_case(case, user, label, remarks, doc_type, up, override):
    outcome = REASONS[label]
    today = str(datetime.date.today())
    esc_level, esc_action, valid_until = "", "", ""
    needs_doc = outcome not in NO_DOC and outcome not in OPTIONAL_DOC      # Sick Leave: document is optional
    if outcome == "Unauthorized":
        if override and is_admin_role(user):
            lvl = int(override)
        else:
            lvl = next_escalation(case["login"])[0]
        esc_level, esc_action = str(lvl), UAL[lvl]
        valid_until = (datetime.date.today() + datetime.timedelta(days=90)).isoformat()
        needs_doc = lvl >= 2                    # L1 verbal coaching needs no letter
    if needs_doc and up is None and not case.get("doc_file"):
        return False, ("Please upload the warning letter document." if outcome == "Unauthorized"
                       else "Please upload a supporting document.")
    doc_file = case.get("doc_file") or ""
    if up is not None:
        try:
            doc_file = save_upload(case["id"], up)
        except Exception as e:
            return False, f"Upload failed: {e}"
    if outcome in NO_DOC or (outcome in OPTIONAL_DOC and not doc_file):
        doc_type = ""
    elif outcome == "Sick Leave" and doc_file and not doc_type:
        doc_type = "Medical Certificate"
    execute("""UPDATE cases SET status='Closed', outcome=?, reason=?, doc_type=?, doc_file=?, closed=?,
               closed_by=?, closedby=?, escalation_level=?, escalation_action=?,
               ua_escalation_level=?, escalation_valid_until=? WHERE id=?""",
            (outcome, remarks, doc_type, doc_file, today, user["alias"], user["alias"], esc_level, esc_action,
             int(esc_level or 0), valid_until, case["id"]))
    prev = case.get("outcome") or ""
    if prev not in UPL_REVERSING and outcome in UPL_REVERSING:
        execute("UPDATE upl_summary SET upl_days=MAX(0,upl_days-1) WHERE login=?", (case["login"],))
    elif prev in UPL_REVERSING and outcome not in UPL_REVERSING:
        execute("UPDATE upl_summary SET upl_days=upl_days+1 WHERE login=?", (case["login"],))
    msg = f"{clean_id(case['id'])} closed: {outcome}."
    if outcome == "Unauthorized":
        if not query("SELECT 1 FROM ua_offences WHERE login=? AND date=?", (case["login"], today)):
            try:
                execute("INSERT INTO ua_offences (login,name,empid,site,date) VALUES (?,?,?,?,?)",
                        (case["login"], case.get("name", ""), case.get("empid", ""), case.get("site", ""), today))
            except Exception:
                execute("INSERT INTO ua_offences (login,site,date) VALUES (?,?,?)",
                        (case["login"], case.get("site", ""), today))
        msg += f" Escalation: L{esc_level} - {esc_action}. Valid until {ua_for(case['login'])['valid_until']}."
    return True, msg


def _case_date(row):
    for k in ("absent", "closed", "created"):
        d = pd.to_datetime(row.get(k), errors="coerce")
        if pd.notna(d):
            return d.date()
    return None


def build_verbatim(c):
    login, name = c["login"], c.get("name") or c["login"]
    today = datetime.date.today()
    hist = query("SELECT date, offence_type FROM ua_offences WHERE login=? ORDER BY date", (login,))
    ua = ua_for(login)
    lvl, action, _ = next_escalation(login)
    ua_cases = query("SELECT absent, closed, created, escalation_action FROM cases "
                     "WHERE login=? AND outcome='Unauthorized'", (login,))
    timeline = [(h["date"], h.get("offence_type") or "Unauthorized") for h in hist]
    seen = {t[0] for t in timeline}
    case_dates = []
    for x in ua_cases:
        d = _case_date(x)
        if d:
            case_dates.append(d)
            if str(d) not in seen:
                timeline.append((str(d), x.get("escalation_action") or "Unauthorized"))
    timeline.sort()
    day_count = {}
    for d in case_dates:
        day_count[d.strftime("%A")] = day_count.get(d.strftime("%A"), 0) + 1
    top_day = max(day_count, key=day_count.get) if day_count else "N/A"
    wk = sum(1 for d in case_dates if d.weekday() in (6, 0, 4, 5))       # Sun, Mon, Fri, Sat
    weekend = bool(case_dates) and wk > len(case_dates) / 2
    cut = today - datetime.timedelta(days=183)
    recent6 = [d for d in case_dates if d >= cut]
    older6 = [d for d in case_dates if d < cut]
    cur_lvl = f"L{ua['level']} ({UAL[ua['level']]})" if ua["level"] else "None (First Offence)"
    absent = c.get("absent") or "today"
    line = "━" * 37
    v = f"📋 WBC COACHING VERBATIM\n{line}\n\n👤 ASSOCIATE PROFILE\n"
    v += f"Name: {name} | Login: {login} | Site: {c.get('site') or '-'}\n"
    v += f"Absent: {absent} | Current UA Level: {cur_lvl}\nThis Escalation: L{lvl} — {action}\n"
    v += f"Total UA Offences on Record: {len(timeline)}" + (f" | Last Action Issued: {timeline[-1][1]}" if timeline else "") + "\n\n"
    if timeline:
        v += "📅 UA HISTORY (Most Recent 5)\n" + "".join(f"  • {d} — {t}\n" for d, t in reversed(timeline[-5:])) + "\n"
    v += "📊 ABSENCE TREND (Last 6 Months)\n"
    v += f"Total UAs in last 6 months: {len(recent6)}" + (f" (vs {len(older6)} in prior period)" if older6 else "") + "\n"
    v += f"Most frequent absence day: {top_day}" + (f" ({day_count[top_day]}x)" if top_day in day_count else "") + "\n"
    v += ("⚠️ Pattern: Absences cluster around weekends/weekly off days.\n" if weekend
          else "Pattern: No clear weekend clustering observed.\n")
    if older6 and len(recent6) > len(older6):
        v += "📈 Trend is WORSENING — increased absences in last 6 months.\n"
    elif older6 and len(recent6) < len(older6):
        v += "📉 Trend IMPROVING compared to prior 6 months.\n"
    v += f"\n💬 SUGGESTED OPENING\n{line}\n"
    v += (f'"{name}, I appreciate you coming in today. I wanted to have a quick conversation about your attendance. '
          f'Our records show that you were absent on {absent}. ')
    if ua["level"] == 0:
        v += ("This is your first unplanned absence on record, and I wanted to check in with you to understand if "
              'everything is okay. We care about your wellbeing and want to make sure we support you where needed."\n\n')
    else:
        suf = "nd" if ua["level"] == 1 else "rd" if ua["level"] == 2 else "th"
        v += (f"This is your {ua['level'] + 1}{suf} unplanned absence in the last 90 days. "
              f'As per our attendance policy, this requires a formal {action}."\n\n')
    if weekend:
        v += (f"💬 PATTERN DISCUSSION\n{line}\n"
              f'"I also want to flag that I have noticed a pattern where your absences tend to occur around {top_day}s '
              "or near your weekly off. I want to understand if there is something we can help address — whether it is "
              'a personal matter, transportation, or something else. Is there anything you would like to share?"\n\n')
    v += f"💬 CLOSING\n{line}\n"
    if lvl <= 1:
        v += ('"I am noting this conversation as a Verbal Coaching. My expectation is that going forward, any absence '
              "will be planned and approved in advance. If there is ever a genuine emergency, please inform your manager "
              'as early as possible. Do you have any questions or concerns you would like to raise?"\n')
    elif lvl <= 3:
        v += (f'"I am issuing you a {action} today which will remain valid for 90 days. Further unplanned absences during '
              "this period will result in escalated action. Please sign this document to acknowledge the discussion. "
              'This is not disciplinary action — it is a support mechanism to help you improve your attendance."\n')
    else:
        v += (f'"I must be direct with you — we have reached L{lvl} — {action}. This is a serious concern and further '
              "absences may result in escalation to the next level. We strongly encourage you to review your "
              "commitments and attendance moving forward. Do you understand the seriousness of this situation and do "
              'you have anything to add?"\n')
    return v


def open_case(case_id):
    """Same as the old 'click a case': mark it In Progress, then open the work window."""
    rows = query("SELECT status FROM cases WHERE id=?", (case_id,))
    if rows and rows[0]["status"] == "Open":
        execute("UPDATE cases SET status='In Progress' WHERE id=?", (case_id,))
    case_dialog(case_id)


@st.dialog("Case details", width="large")
def case_dialog(case_id):
    rows = query("SELECT * FROM cases WHERE id=?", (case_id,))
    if not rows:
        st.error("Case not found.")
        return
    c, user = rows[0], current()
    ua = ua_for(c["login"])
    info = [("Case ID", clean_id(c["id"])), ("Login", c["login"]), ("Employee ID", clean_id(c["empid"])),
            ("Name", c["name"]), ("Site", c["site"]), ("Manager", c["mgr"]), ("Shift", c["shift"]),
            ("Agency", c["agency"]), ("Attendance / absent", c["absent"]),
            ("Current UA", f"L{ua['level']} — {UAL[ua['level']]}" if ua["count"] else "None")]
    # two columns of label/value pairs, so the form below fits on screen without scrolling
    st.markdown('<div class="kv kv2">' + "".join(f"<b>{esc(k)}</b><span>{esc(v) or '–'}</span>" for k, v in info) + "</div>",
                unsafe_allow_html=True)

    if c["status"] == "Closed":
        st.success(f"Closed {c.get('closed') or ''} by {c.get('closed_by') or c.get('closedby') or '-'}: "
                   f"{c['outcome']}" + (f" | L{c['escalation_level']} — {c['escalation_action']}" if c.get("escalation_level") else ""))
        if c.get("reason"):
            st.caption(f"Remarks: {c['reason']}")
        show_existing_doc(c["id"], c.get("doc_file"), "closed")
        if not st.checkbox("Edit / re-close this case", key=f"edit_{case_id}"):
            return
    elif c.get("sick_hint"):
        st.info("💡 Roster hint: leave type indicates Sick Leave.")

    labels = ["Select reason..."] + list(REASONS)
    prev = {v: k for k, v in REASONS.items()}.get(c.get("outcome") or "", "")
    default = labels.index(prev) if prev in labels else (labels.index("Sick Leave") if c.get("sick_hint") else 0)
    label = st.selectbox("Reason of absence", labels, index=default, key=f"reason_{case_id}")
    chosen = label != "Select reason..."

    remarks = st.text_area("Remarks", value=c.get("reason") or "", key=f"remarks_{case_id}", height=110,
                           placeholder="Write your remarks about this case / the conversation with the associate...")

    override, show_doc, doc_default, optional_doc = "", False, "", False
    if chosen:
        show_doc = label not in NO_DOC
        optional_doc = label in OPTIONAL_DOC
        if label == "Sick Leave":
            doc_default = "Medical Certificate"
        if label == "Unauthorized":
            lvl, action, valid = next_escalation(c["login"])
            if is_admin_role(user):
                override = st.selectbox("HRBP override (optional)", ["", "1", "2", "3", "4", "5", "6"],
                                        format_func=lambda v: "— Keep auto level —" if not v else f"L{v} — {UAL[int(v)]}",
                                        key=f"override_{case_id}")
                if override:
                    lvl, action = int(override), UAL[int(override)]
            show_doc = lvl >= 2
            doc_default = "Warning Letter" if lvl >= 2 else ""
            st.markdown(f'<div class="esc-box"><div class="esc-t">⚡ Auto Escalation — UA Offence</div>'
                        f'<span class="esc-lvl">L{lvl} — {esc(action)}</span><br>Valid until: {valid}<br>'
                        f'Required action: {esc(action)} '
                        f'{"(No document required for Verbal Coaching)" if lvl <= 1 else "(Warning letter required)"}</div>',
                        unsafe_allow_html=True)

    doc_type, up = "", None
    if show_doc:
        d1, d2 = st.columns([1, 2])
        start = c.get("doc_type") or doc_default
        doc_type = d1.selectbox("Document type", DOC_TYPES, key=f"dtype_{case_id}",
                                index=DOC_TYPES.index(start) if start in DOC_TYPES else 0)
        up = d2.file_uploader("Upload sick leave certificate (optional)" if optional_doc else "Supporting document",
                              type=["pdf", "jpg", "jpeg", "png", "doc", "docx"], key=f"file_{case_id}")
        if optional_doc:
            st.caption("Optional - you can submit the case with or without the sick leave document.")
        show_existing_doc(c["id"], c.get("doc_file"), "form")
        if c.get("doc_file"):
            st.caption("Upload a new file only if you want to replace the current one.")

    if label == "Unauthorized":
        with st.expander("🧠 Verbatim coach"):
            if st.button("Generate verbatim", key=f"verb_btn_{case_id}"):
                st.session_state[f"verb_{case_id}"] = build_verbatim(c)
            if st.session_state.get(f"verb_{case_id}"):
                st.code(st.session_state[f"verb_{case_id}"], language=None)

    # always visible, even before a reason is picked
    if st.button("✅ Submit", type="primary", key=f"close_{case_id}", use_container_width=True):
        if not chosen:
            st.error("Please select a reason of absence before submitting.")
        else:
            ok, msg = close_case(c, user, label, remarks, doc_type, up, override)
            if ok:
                st.session_state["_flash"] = msg
                st.rerun()
            else:
                st.error(msg)


def cases_table(view, page_size=PAGE_SIZE):
    """Styled table with real 'View' buttons + pagination."""
    total = len(view)
    pages = max(1, math.ceil(total / page_size))
    cur = min(max(1, st.session_state.get("cases_page", 1)), pages)
    st.session_state.cases_page = cur
    start = (cur - 1) * page_size
    chunk = view.iloc[start:start + page_size]
    widths = [1.7, 0.9, 1.4, 1.2, 1.3, 0.9, 0.9]

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
            c[0].markdown(f'<div class="td id">{esc(clean_id(r["id"]))}</div>', unsafe_allow_html=True)
            c[1].markdown(f'<div class="td">{esc(r["site"])}</div>', unsafe_allow_html=True)
            c[2].markdown(f'<div class="td">{esc(r["_type"])}</div>', unsafe_allow_html=True)
            c[3].markdown(pill_html(r["_g"], r["status"] or "Open"), unsafe_allow_html=True)
            c[4].markdown(f'<div class="td">{opened}</div>', unsafe_allow_html=True)
            c[5].markdown(f'<div class="td">{days}</div>', unsafe_allow_html=True)
            with c[6]:
                with st.container(key=f"view_{cur}_{n}"):
                    if st.button("👁 View", key=f"viewbtn_{cur}_{n}"):
                        open_case(r["id"])

    first, last = (start + 1 if total else 0), min(start + page_size, total)
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
def page_dashboard():
    user = current()
    df = load_cases(user)
    page_shell(f"Welcome back, {user['alias'].capitalize()}",
               "Here's what's happening with your WBC Portal today.", wave=True)

    g = df["_g"]
    pending = ~g.isin(["open", "closed"])
    st.markdown(chips_html([
        ("Total Cases", len(df)), ("Open Cases", int((g == "open").sum())),
        ("Closed Cases", int((g == "closed").sum())), ("Pending Cases", int(pending.sum())),
        ("Pending > 5 Days", int((pending & (df["_days"] > 5)).sum()))]), unsafe_allow_html=True)

    left, right = st.columns([2.35, 1], gap="medium")
    with left:
        with st.container(border=True, key="card_recent"):
            h1, h2 = st.columns([1.6, 2.4], vertical_alignment="center")
            h1.markdown(card_header_html("check", "Recent Cases", "Latest cases across all sites"), unsafe_allow_html=True)
            search = h2.text_input("Search", placeholder="Search by Case ID, Site, Type, Name, Login...",
                                   label_visibility="collapsed", key="q_search")

            f1, f2, f3, f4, f5 = st.columns([1, 0.8, 1.2, 1.1, 0.9])
            view = site_filters(df, "dash", [f1, f2, f3])
            view = agency_filter(view, "dash_agency", f4)
            size = int(f5.selectbox("Rows per page", [8, 25, 50, 100, 200], key="q_size",
                                    format_func=lambda n: f"{n} / page", label_visibility="collapsed"))

            if search.strip():
                s = search.strip().lower()
                hay = (view["id"] + " " + view["site"] + " " + view["_type"] + " " + view["name"] + " " + view["login"] + " " + view["agency"]).str.lower()
                view = view[hay.str.contains(s, regex=False)]

            bar1, bar2, bar3 = st.columns([3, 1, 1], vertical_alignment="center")
            bar1.markdown(f'<div class="showing">{len(view)} cases match - downloads include all of them, not just this page</div>',
                          unsafe_allow_html=True)
            export = view[CASE_COLS]
            bar2.download_button("⬇ CSV", export.to_csv(index=False).encode(), "wbc_cases.csv", "text/csv",
                                 key="dl_csv_dash", use_container_width=True)
            xl = to_excel_bytes(export)
            if xl:
                bar3.download_button("⬇ Excel", xl, "wbc_cases.xlsx",
                                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                     key="dl_xlsx_dash", use_container_width=True)

            sig = (search, tuple(st.session_state.get(f"dash_{k}") for k in ("country", "bu", "site", "agency")), size)
            if st.session_state.get("_sig") != sig:
                st.session_state["_sig"] = sig
                st.session_state.cases_page = 1
            cases_table(view, size)

    with right:
        with st.container(border=True, key="card_sites"):
            st.markdown(card_header_html("pin", "Cases by Site", f"Top {TOP_N_SITES} sites by open cases"),
                        unsafe_allow_html=True)
            st.markdown(sites_html(df), unsafe_allow_html=True)
        with st.container(border=True, key="card_mountain"):
            st.markdown(card_header_html("chart", "Site Comparison", f"Open cases - top {TOP_N_SITES} sites side by side"),
                        unsafe_allow_html=True)
            st.markdown(mountain_html(df), unsafe_allow_html=True)


def page_cases():
    df = load_cases(current())
    page_shell("Cases Dashboard", "Real-time tracking of employee roster performance, attendance, and operational status.")
    st.markdown(chips_html([
        ("Total Records", len(df)),
        ("Active Sites", df.loc[df["site"] != "", "site"].nunique()),
        ("System Status", "Operational")]), unsafe_allow_html=True)
    with st.container(border=True, key="card_cases"):
        st.markdown(card_header_html("list", "All Cases", "Filter and export the full case list"), unsafe_allow_html=True)
        a, b, c, d, e = st.columns([1, 0.8, 1.2, 1.1, 1.1])
        view = site_filters(df, "cd", [a, b, c])
        view = agency_filter(view, "cd_agency", d)
        status = e.selectbox("Status", ["All Status", "Open", "In Review / Pending", "Closed"],
                             label_visibility="collapsed", key="cd_status")
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
            st.dataframe(out, use_container_width=True, height=440, hide_index=True)
            d1, d2, _ = st.columns([1, 1, 4])
            d1.download_button("⬇ Export CSV", out.to_csv(index=False).encode(), "wbc_cases.csv", "text/csv",
                               key="dl_csv_cases", use_container_width=True)
            xl = to_excel_bytes(out)
            if xl:
                d2.download_button("⬇ Export Excel", xl, "wbc_cases.xlsx",
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   key="dl_xlsx_cases", use_container_width=True)


def table_page(title, sub, icon, card_title, card_sub, sql, chips, empty_msg, key):
    page_shell(title, sub)
    data = read_table(sql)
    items = chips(data)
    if items:
        st.markdown(chips_html(items), unsafe_allow_html=True)
    with st.container(border=True, key=f"card_{key}"):
        st.markdown(card_header_html(icon, card_title, card_sub), unsafe_allow_html=True)
        if data.empty:
            st.info(empty_msg)
        else:
            st.dataframe(data, use_container_width=True, height=440, hide_index=True)
            st.download_button("⬇ Export CSV", data.to_csv(index=False).encode(), f"{key}.csv", "text/csv",
                               key=f"dl_{key}")


def ua_chips(d):
    if d.empty:
        return []
    return [("Total Offences", len(d)), ("Employees", d["login"].nunique()), ("Sites Affected", d["site"].nunique())]


def upl_chips(d):
    if d.empty:
        return []
    sched, upl = int(d["scheduled_days"].sum()), int(d["upl_days"].sum())
    return [("Employees Tracked", len(d)), ("Total UPL Days", upl),
            ("Overall UPL %", f"{upl / sched * 100:.1f}%" if sched else "0%")]


def page_ua():
    table_page("UA Offences Tracker", "Comprehensive overview of recorded unauthorized absence offences.", "list",
               "UA Offences", "Most recent offences first", "SELECT * FROM ua_offences ORDER BY date DESC",
               ua_chips, "No UA offences recorded in the database.", "ua")


def page_upl():
    table_page("UPL Summary Analytics", "Unplanned leave and schedule performance summary.", "list",
               "UPL Summary", "Unplanned leave per employee", "SELECT * FROM upl_summary ORDER BY updated DESC",
               upl_chips, "No UPL summary data available.", "upl")


DISC_COLS = ["closed", "id", "login", "name", "empid", "site", "mgr", "agency", "absent", "outcome",
             "escalation_level", "escalation_action", "escalation_valid_until", "doc_type", "doc_file",
             "reason", "closed_by"]
DISC_LABELS = {"closed": "Closed Date", "id": "Case ID", "login": "Login", "name": "Name", "empid": "Employee ID",
               "site": "Site", "mgr": "Manager", "agency": "Agency", "absent": "Absent Date", "outcome": "Decision",
               "escalation_level": "Escalation Level", "escalation_action": "Disciplinary Action",
               "escalation_valid_until": "Valid Until", "doc_type": "Document Type", "doc_file": "Document File",
               "reason": "Remarks", "closed_by": "Closed By"}


def page_disciplinary():
    user = current()
    df = load_cases(user)
    page_shell("Disciplinary Actions", "Every closed case: Authorized / Unauthorized decision, escalation and warning letter.")
    closed = df[df["_g"] == "closed"].copy()
    closed["closed_by"] = closed["closed_by"].where(closed["closed_by"] != "", closed["closedby"])
    st.markdown(chips_html([
        ("Closed Cases", len(closed)),
        ("Unauthorized", int((closed["outcome"] == "Unauthorized").sum())),
        ("Authorized", int((closed["outcome"] == "Authorized").sum())),
        ("Other", int((~closed["outcome"].isin(["Unauthorized", "Authorized"])).sum()))]), unsafe_allow_html=True)
    with st.container(border=True, key="card_disc"):
        st.markdown(card_header_html("check", "Disciplinary Action Register",
                                     "Saved automatically when a case is closed from the Dashboard"),
                    unsafe_allow_html=True)
        a, b, c, d, e = st.columns([1, 0.8, 1.2, 1.1, 1.1])
        view = site_filters(closed, "da", [a, b, c])
        view = agency_filter(view, "da_agency", d)
        decisions = ["All Decisions"] + sorted(o for o in closed["outcome"].unique() if o)
        _valid_or_reset("da_outcome", decisions)
        pick = e.selectbox("Decision", decisions, key="da_outcome", label_visibility="collapsed")
        if pick != "All Decisions":
            view = view[view["outcome"] == pick]
        out = view[DISC_COLS].sort_values("closed", ascending=False).rename(columns=DISC_LABELS)
        if out.empty:
            st.info("No closed cases yet. When a case is closed as Authorized or Unauthorized it appears here "
                    "(for old cases, import the old wbc.db in Settings).")
        else:
            st.dataframe(out, use_container_width=True, height=440, hide_index=True)
            d1, d2, _ = st.columns([1, 1, 4])
            d1.download_button("⬇ Export CSV", out.to_csv(index=False).encode(), "disciplinary_actions.csv",
                               "text/csv", key="dl_csv_disc", use_container_width=True)
            xl = to_excel_bytes(out, "Disciplinary Actions")
            if xl:
                d2.download_button("⬇ Export Excel", xl, "disciplinary_actions.xlsx",
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   key="dl_xlsx_disc", use_container_width=True)


def page_sync():
    user = current()
    page_shell("DWD Sync", "Create absence cases from the daily DWD CSV (same logic as the old portal).")
    if not is_all_access(user):
        st.error("Access Denied: only Admin / VPOC / PXT can run the DWD sync.")
        return
    with st.container(border=True, key="card_sync"):
        st.markdown(card_header_html("list", "Upload DWD CSV",
                                     "Columns: login, empid, name, site, agency, shift, mgr, absent (1 = absent)"),
                    unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2])
        d = c1.date_input("Absence date", value=yesterday_ast(), key="sync_date")
        pool = sorted(set(TARGET_SITES) | set(site_meta(get_site_map())))
        sites = c2.multiselect("Sites to include", pool, default=TARGET_SITES, key="sync_sites")
        up = st.file_uploader("DWD CSV", type=["csv"], key="sync_csv")
        if st.button("Run sync", type="primary", disabled=up is None, key="sync_run"):
            ok, msg = run_dwd_sync(up.getvalue().decode("utf-8-sig", errors="replace"), str(d), sites)
            (st.success if ok else st.error)(msg)


def page_users():
    user = current()
    page_shell("User Management", "Manage administrative users, roles, and facility permissions.")
    if not (is_admin(user) or str(user.get("alias", "")).lower() in USER_MGMT_BYPASS):
        st.error("Access Denied: Admin privileges required to view users.")
        return
    data = read_table("SELECT alias, role, sites, added, token FROM users")
    with st.container(border=True, key="card_users"):
        st.markdown(card_header_html("user", "Portal Users", "Roles and facility permissions"), unsafe_allow_html=True)
        st.dataframe(data, use_container_width=True, height=380, hide_index=True)

    with st.container(border=True, key="card_sitesadmin"):
        st.markdown(card_header_html("pin", "Manage Sites", "Add a site to the Country / BU / Site selector"),
                    unsafe_allow_html=True)
        a, b, c, d = st.columns([1, 1, 1, 0.7], vertical_alignment="bottom")
        country = a.selectbox("Country", list(SITE_MAP_DEFAULT), key="ns_country",
                              format_func=lambda x: f"{COUNTRY_FLAGS.get(x, '')} {COUNTRY_LABELS.get(x, x)}")
        bu = b.selectbox("BU", ["FC/SC", "AMZL"], key="ns_bu")
        site = c.text_input("Site code", placeholder="e.g. DXB9", key="ns_site").strip().upper()
        if d.button("Add site", key="ns_add", disabled=not site):
            execute("INSERT OR IGNORE INTO custom_sites (country,bu,site,active,added_by,added_at) VALUES (?,?,?,1,?,?)",
                    (country, bu, site, user["alias"], str(datetime.date.today())))
            execute("UPDATE custom_sites SET active=1 WHERE country=? AND bu=? AND site=?", (country, bu, site))
            st.session_state["_flash"] = f"{site} added."
            st.rerun()
        custom = query("SELECT id, country, bu, site FROM custom_sites WHERE active=1 ORDER BY country, bu, site")
        for r in custom:
            x, y = st.columns([5, 1], vertical_alignment="center")
            x.markdown(f'<div class="td">{COUNTRY_FLAGS.get(r["country"], "")} {esc(r["country"])} · {esc(r["bu"])} · <b>{esc(r["site"])}</b></div>',
                       unsafe_allow_html=True)
            if y.button("Remove", key=f"rm_site_{r['id']}"):
                execute("UPDATE custom_sites SET active=0 WHERE id=?", (r["id"],))
                st.rerun()
        if not custom:
            st.caption("No custom sites yet - the built-in site list (UAE, Egypt, KSA, Turkiye) is always available.")


def page_settings():
    user = current()
    page_shell("Settings", "Portal configuration, environment status, and system settings.")
    db_path = os.path.abspath(DB_PATH)
    exists = os.path.exists(db_path)
    size_kb = os.path.getsize(db_path) / 1024 if exists else 0
    modified = (datetime.datetime.fromtimestamp(os.path.getmtime(db_path)).strftime("%b %d, %Y %I:%M %p") if exists else "–")
    counts = {t: query(f"SELECT COUNT(*) n FROM {t}")[0]["n"] for t in ("cases", "ua_offences", "upl_summary", "users")}
    excel = [f for f in os.listdir(".") if f.lower().endswith((".xlsx", ".xls"))]
    src = query("SELECT value FROM settings WHERE key='excel_imported'")
    if src and src[0]["value"] == "old-db-import":
        src_label = "Old portal database (imported)"
    elif src:
        src_label = f"Excel file: {src[0]['value']} (sheet 'Roster', one case per employee)"
    elif excel:
        src_label = f"Excel file in app folder: {excel[0]} (sheet 'Roster')"
    else:
        src_label = "No Excel file found - cases come from DWD Sync / manual entry"
    docs = f"S3 bucket: {S3_BUCKET}/{S3_PREFIX}" if S3_BUCKET else os.path.abspath(UPLOAD_DIR)
    with st.container(border=True, key="card_settings"):
        st.markdown(card_header_html("target", "System Status", "Environment and database"), unsafe_allow_html=True)
        st.markdown(
            f'<div class="kv"><b>Database file</b><span>{esc(db_path)}</span>'
            f'<b>DB size / modified</b><span>{size_kb:,.0f} KB / {esc(modified)}</span>'
            f'<b>Records</b><span>{counts["cases"]} cases · {counts["ua_offences"]} UA offences · '
            f'{counts["upl_summary"]} UPL rows · {counts["users"]} users</span>'
            f'<b>Cases loaded from</b><span>{esc(src_label)}</span>'
            f'<b>Documents saved in</b><span>{esc(docs)}</span>'
            f'<b>Signed in as</b><span>{esc(user["alias"])} ({esc(user["role"])})</span>'
            f'<b>Sites</b><span>{esc(user["sites"])}</span></div>', unsafe_allow_html=True)
        st.warning("Cases are stored in a local SQLite file. On Streamlit Cloud this file is temporary and can be "
                   "reset on reboot or redeploy, so download a backup regularly.")
        if is_admin(user) and exists:
            with open(db_path, "rb") as fh:
                st.download_button("⬇ Download database backup (wbc.db)", fh.read(), "wbc.db",
                                   "application/octet-stream", key="dl_db")

    if is_admin(user):
        with st.container(border=True, key="card_clean"):
            st.markdown(card_header_html("check", "Remove P / OFF cases",
                                         "Present and weekly-off rows never show in the app; this deletes them from the database"),
                        unsafe_allow_html=True)
            n_pf = query("SELECT COUNT(*) n FROM cases WHERE UPPER(TRIM(absent)) IN ('P','OFF') AND status != 'Closed'")[0]["n"]
            st.write(f"{n_pf} unclosed cases with attendance P or OFF are stored in the database.")
            sure = st.checkbox("Yes, delete them permanently", key="clean_sure", disabled=n_pf == 0)
            if st.button("Delete P / OFF cases", disabled=not sure, key="clean_run"):
                execute("DELETE FROM cases WHERE UPPER(TRIM(absent)) IN ('P','OFF') AND status != 'Closed'")
                st.session_state["_flash"] = f"{n_pf} P / OFF cases deleted."
                st.rerun()

        with st.container(border=True, key="card_import"):
            st.markdown(card_header_html("list", "Import old database",
                                         "Bring cases, UA offences, UPL, users and sites over from the old portal's wbc.db"),
                        unsafe_allow_html=True)
            up = st.file_uploader("Old wbc.db", type=["db", "sqlite", "sqlite3"], key="imp_file")
            mode = st.radio("Mode", ["Merge into current data (old rows win on the same ID)",
                                     "Replace everything with the old database"], key="imp_mode")
            replace = mode.startswith("Replace")
            drop = st.checkbox("Also delete untouched roster placeholder cases (CASE-… still Open) that are not in the old database",
                               key="imp_drop", disabled=replace)
            st.caption("A timestamped backup of the current database is created first.")
            if st.button("Import", type="primary", disabled=up is None, key="imp_run"):
                ok, msg = import_old_db(up.getvalue(), replace=replace, drop_roster_placeholders=drop)
                (st.success if ok else st.error)(msg)


# ----------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------
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

    st.session_state["_user"] = user

    # ---------- navigation ----------
    pages = [
        st.Page(page_dashboard, title="Dashboard", icon=":material/home:", url_path="dashboard", default=True),
        st.Page(page_cases, title="Cases Dashboard", icon=":material/table_chart:", url_path="cases"),
        st.Page(page_ua, title="UA Offences Tracker", icon=":material/shield:", url_path="ua-offences"),
        st.Page(page_upl, title="UPL Summary Analytics", icon=":material/bar_chart:", url_path="upl-summary"),
        st.Page(page_disciplinary, title="Disciplinary Actions", icon=":material/gavel:", url_path="disciplinary"),
        st.Page(page_sync, title="DWD Sync", icon=":material/sync:", url_path="dwd-sync"),
        st.Page(page_users, title="User Management", icon=":material/person:", url_path="users"),
        st.Page(page_settings, title="Settings", icon=":material/settings:", url_path="settings"),
    ]
    try:
        nav = st.navigation(pages, position="hidden")
    except TypeError:           # older Streamlit: default nav is hidden by CSS instead
        nav = st.navigation(pages)

    with st.sidebar:
        st.markdown(BRAND_HTML, unsafe_allow_html=True)
        for p in pages:
            st.page_link(p, label=p.title, icon=p.icon)
        with st.container(key="signout"):
            if st.button("Sign out", use_container_width=True):
                st.session_state.clear()
                st.query_params.clear()
                st.rerun()
        st.markdown('<div class="side-foot">Better Workplace<br>Safer Tomorrow<span></span></div>', unsafe_allow_html=True)

    nav.run()


if __name__ == "__main__":
    main()
