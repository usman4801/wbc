import streamlit as st
import io
import re
import copy
import math
import json
import datetime
import html as _html
from concurrent.futures import ThreadPoolExecutor
import pandas as pd

try:                                                  # same pattern as the other Canopy tool: plain boto3 + IAM role
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    _boto3_installed = True
except ImportError:
    boto3 = None
    ClientError = NoCredentialsError = Exception
    _boto3_installed = False

# ----------------------------------------------------------------
# PAGE CONFIG
# ----------------------------------------------------------------
st.set_page_config(page_title="WBC Portal", page_icon="🛡️", layout="wide",
                   initial_sidebar_state="expanded")

# ----------------------------------------------------------------
# CANOPY STORAGE (S3) - the ONLY storage this app uses
#   s3://<S3_BUCKET>/<S3_PREFIX><FOLDER>/<daily file>.xlsx     e.g. javmuhak/wbc/DXB5/DMD-DXB5-09102026.xlsx
#   s3://<S3_BUCKET>/<S3_PREFIX>_state/...                      cases worked, UA offences, users, custom sites (JSON)
#   s3://<S3_BUCKET>/<S3_PREFIX>_uploads/<case id>/<file>       warning letters / medical certificates
# Credentials come from the container's IAM role - nothing is hard-coded.
# ----------------------------------------------------------------
S3_BUCKET = "canopy-app-data-prod-796301651950"
S3_PREFIX = "javmuhak/wbc/"
STATE_DIR = "_state"
UPLOAD_DIR = "_uploads"
LOOKBACK_DAYS = 45                       # daily files older than this are not read (closed cases are always kept)

# Which sites live in which storage folder. A folder you create later is picked up automatically
# (its sites are read from the files); add it here only if you want the site list shown before it has data.
SITE_FOLDERS = {
    "DXB5": ["DUF7", "DUF8", "DWC3", "DXB5", "DXB6", "DXB8", "DXF2", "XAEC"],
    "AUH1": ["AUH1", "DAD1", "AUH3"],
    "DXB3": [],                          # remaining sites - add them here when you decide
}

PAGE_SIZE = 8
USER_MGMT_BYPASS = {"javmuhak"}                                   # aliases that can open User Management without being Admin
TOP_N_SITES = 3                                                 # Cases by Site + mountain chart show this many

UAL = ["", "Verbal Coaching", "Documented Coaching", "First Warning",
       "Second Warning", "Final Warning", "Termination"]
REASONS = {"Sick Leave": "Sick Leave", "Authorized": "Authorized", "Authorized Unpaid": "Authorized Unpaid",
           "Unauthorized": "Unauthorized",
           "Incorrect Entry on DWD": "Incorrect Entry on DWD", "Converted to PL": "Converted to PL"}
NO_DOC = {"Authorized", "Authorized Unpaid", "Incorrect Entry on DWD", "Converted to PL"}   # no upload shown
OPTIONAL_DOC = {"Sick Leave"}                                     # upload offered, but case can be submitted without it
UPL_REVERSING = {"Incorrect", "Incorrect Entry on DWD", "Converted to PL"}   # take a day off UPL
DOC_TYPES = ["", "Medical Certificate", "HRBP Approval", "Warning Letter", "Email Approval", "Other"]
ADMIN_ROLES = ("admin", "hrbp")                                   # lower-case; can override escalation level
EXCLUDED_ATTENDANCE = {"P", "OFF"}                                # present / weekly-off rows are not WBC cases
ALL_ACCESS_ROLES = ("admin", "vpoc", "pxt")                       # see every site

CASE_COLS = ["id", "login", "empid", "name", "site", "mgr", "shift", "agency", "absent",
             "created", "status", "outcome", "reason", "doc_type", "doc_file", "notes",
             "closed", "source", "sick_hint", "ua_escalation_level",
             "escalation_valid_until", "closedby", "on_site", "closed_by",
             "escalation_level", "escalation_action", "present_status", "folder"]

# fields a user changes while working a case - these are what gets saved to storage
WORKFLOW_KEYS = ["status", "outcome", "reason", "doc_type", "doc_file", "notes", "closed", "closedby", "closed_by",
                 "escalation_level", "escalation_action", "ua_escalation_level", "escalation_valid_until",
                 "present_status"]

DEFAULT_USERS = [{"alias": "mnnafee", "role": "Admin", "sites": "All"},
                 {"alias": "javmuhak", "role": "VPOC", "sites": "All"}]

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
.st-key-signout button, .st-key-refresh button{background:transparent;border:1px solid var(--line);color:var(--muted);
  border-radius:10px;font-size:.8rem;margin-top:8px;}

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

/* ---------- clickable stat chips (dashboard) ---------- */
[class*="st-key-chip_"] button{background:linear-gradient(135deg,#9a88f7,#7b6be8);border:none;color:#fff;border-radius:10px;
  min-height:38px;box-shadow:0 4px 12px rgba(123,107,232,.26);}
[class*="st-key-chip_"] button *{color:#fff !important;font-size:.78rem;font-weight:600;}
[class*="st-key-chip_"] button strong{background:rgba(255,255,255,.24);padding:1px 9px;border-radius:7px;margin-left:6px;}
[class*="st-key-chip_"] button:hover{filter:brightness(1.07);}
[class*="st-key-chip_"] button[data-testid="stBaseButton-primary"]{background:linear-gradient(135deg,#5b49c9,#4636b0);
  box-shadow:0 0 0 3px rgba(123,107,232,.35),0 4px 12px rgba(91,73,201,.35);}

/* ---------- CSV / Excel export buttons ---------- */
[class*="st-key-dl_csv"] button, .st-key-dl_ua button, .st-key-dl_upl button{
  background:#fff;border:1.5px solid #5b8def;color:#2563eb;border-radius:10px;font-weight:600;font-size:.78rem;min-height:34px;padding:0 10px;}
[class*="st-key-dl_csv"] button:hover, .st-key-dl_ua button:hover, .st-key-dl_upl button:hover{
  background:#eff5ff;border-color:#2563eb;color:#1d4ed8;}
[class*="st-key-dl_csv"] button *, .st-key-dl_ua button *, .st-key-dl_upl button *{color:#2563eb !important;}
[class*="st-key-dl_xlsx"] button{background:linear-gradient(135deg,#12a58c,#0b7a6a);border:none;color:#fff;
  border-radius:10px;font-weight:600;font-size:.78rem;min-height:34px;padding:0 10px;box-shadow:0 3px 8px rgba(15,157,132,.25);}
[class*="st-key-dl_csv"] button p, [class*="st-key-dl_xlsx"] button p, .st-key-dl_ua button p, .st-key-dl_upl button p{
  font-size:.78rem;margin:0;}
[class*="st-key-dl_xlsx"] button:hover{filter:brightness(1.08);color:#fff;}
[class*="st-key-dl_xlsx"] button *{color:#fff !important;}

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
.login-help{text-align:center;font-size:.72rem;color:#94a3b8;margin-top:10px;}
.login-help b{color:#64748b;}
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


def to_excel_bytes(df, sheet="Cases"):
    try:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name=sheet)
        return buf.getvalue()
    except Exception:
        return None


# ----------------------------------------------------------------
# S3 LAYER  (connection pattern copied from the Workforce Compliance tool already running on Canopy)
# ----------------------------------------------------------------
@st.cache_resource(ttl=120, show_spinner=False)
def _s3_connect():
    """(client, message). client is None when S3 cannot be reached. Re-checked every 2 minutes."""
    if not _boto3_installed:
        return None, "boto3 is not installed - add boto3 to requirements.txt"
    try:
        client = boto3.client("s3")
        resp = client.list_objects_v2(Bucket=S3_BUCKET, Prefix=S3_PREFIX, MaxKeys=1)
        return client, f"S3 OK - found {resp.get('KeyCount', 0)} objects"
    except NoCredentialsError as e:
        return None, f"No credentials: {e}"
    except ClientError as e:
        return None, f"Client error: {e}"
    except Exception as e:
        return None, f"Unknown error: {type(e).__name__}: {e}"


def s3_client():
    return _s3_connect()[0]


def s3_status():
    client, msg = _s3_connect()
    return {"connected": client is not None, "bucket": S3_BUCKET, "prefix": S3_PREFIX, "message": msg}


def _key(rel):
    return S3_PREFIX + str(rel).replace("\\", "/").lstrip("/")


def _is_missing(e):
    code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
    return code in ("NoSuchKey", "404", "NotFound")


def s3_read(rel, client=None):
    """Bytes of an object, or None if it does not exist. Other errors are raised."""
    c = client or s3_client()
    if c is None:
        raise RuntimeError("S3 is not connected")
    try:
        return c.get_object(Bucket=S3_BUCKET, Key=_key(rel))["Body"].read()
    except ClientError as e:
        if _is_missing(e):
            return None
        raise


def s3_write(rel, data, content_type=None):
    c = s3_client()
    if c is None:
        raise RuntimeError("S3 is not connected")
    extra = {"ContentType": content_type} if content_type else {}
    c.put_object(Bucket=S3_BUCKET, Key=_key(rel), Body=data, **extra)


def s3_list(rel_prefix="", client=None):
    """Every object under S3_PREFIX + rel_prefix -> [{key (relative), size, modified, etag}]."""
    c = client or s3_client()
    if c is None:
        raise RuntimeError("S3 is not connected")
    out = []
    for page in c.get_paginator("list_objects_v2").paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX + rel_prefix):
        for o in page.get("Contents", []):
            rel = o["Key"][len(S3_PREFIX):]
            if rel and not rel.endswith("/"):
                out.append({"key": rel, "size": o["Size"], "modified": o["LastModified"], "etag": o.get("ETag", "")})
    return out


def s3_folders(client=None):
    """Data folders directly under the prefix (AUH1, DXB3, DXB5, ... - anything not starting with _ or .)."""
    c = client or s3_client()
    if c is None:
        raise RuntimeError("S3 is not connected")
    names = []
    for page in c.get_paginator("list_objects_v2").paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX, Delimiter="/"):
        for p in page.get("CommonPrefixes", []):
            n = p["Prefix"][len(S3_PREFIX):].strip("/")
            if n and not n.startswith(("_", ".")):
                names.append(n)
    return sorted(names)


def _clean(v):
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            pass
    return v


def _json_default(o):
    if isinstance(o, (datetime.date, datetime.datetime, pd.Timestamp)):
        return str(o)[:10]
    if hasattr(o, "item"):
        try:
            return o.item()
        except Exception:
            pass
    return str(o)


def read_json(rel, default=None):
    data = s3_read(rel)
    if data is None:
        return default
    try:
        return json.loads(data.decode("utf-8"))
    except Exception:
        return default


def write_json(rel, obj):
    s3_write(rel, json.dumps(obj, ensure_ascii=False, default=_json_default).encode("utf-8"), "application/json")


def _safe(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(s)).strip("_") or "x"


def _read_many(rels, client):
    def one(rel):
        try:
            data = s3_read(rel, client)
            return json.loads(data.decode("utf-8")) if data else None
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(one, rels))


@st.cache_data(ttl=30, show_spinner=False)
def load_state_records(prefix):
    """All small JSON records under a state folder (one file per case / UA offence, so people never overwrite each other)."""
    c = s3_client()
    if c is None:
        return []
    rels = [o["key"] for o in s3_list(prefix, c) if o["key"].endswith(".json")]
    return [r for r in _read_many(rels, c) if isinstance(r, dict)]


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
    """Admin role, or an alias in USER_MGMT_BYPASS (e.g. javmuhak: shown as VPOC but has every admin power)."""
    return (str(user.get("role", "")).lower() == "admin"
            or str(user.get("alias", "")).lower() in USER_MGMT_BYPASS)


def is_admin_role(user):
    return str(user.get("role", "")).lower() in ADMIN_ROLES or is_admin(user)


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
    # an "open" case that is only a planned leave (PL) is not an absence - it is never counted as open
    df["_open"] = (df["_g"] == "open") & (df["absent"].astype(str).str.strip().str.upper() != "PL")
    return df


# ----------------------------------------------------------------
# DAILY FILES -> CASES  (read straight from Canopy storage)
# ----------------------------------------------------------------
ROSTER_FIELDS = {                          # normalised header names (lower-case, letters+digits only)
    "name": ("empname", "employeename", "name"),
    "amz": ("amzid", "login", "alias", "amazonid"),
    "psoft": ("psoftno", "psoft", "psoftid", "employeeid", "empid"),
    "site": ("building", "site", "warehouse"),
    "mgr": ("linemanager", "manager", "managername", "mgr"),
    "shift": ("shift",),
    "agency": ("3p", "agency", "vendor"),
    "att": ("attendance", "attendence"),            # the AUH1 file spells it "Attendence"
}
ROW_COLS = ["empid", "login", "name", "site", "mgr", "shift", "agency", "att", "date", "folder"]


def _norm(v):
    return re.sub(r"[^a-z0-9]", "", str(v).lower())


def _s(v):
    if v is None:
        return ""
    t = str(v).strip()
    return "" if t.lower() in ("nan", "none", "nat") else t


def file_date(name):
    """DWD-AUH1-09102026.xlsx -> 2026-10-09 (day, month, year)."""
    m = re.search(r"(\d{8})", name)
    if not m:
        return None
    try:
        return datetime.datetime.strptime(m.group(1), "%d%m%Y").date()
    except ValueError:
        return None


def parse_roster_bytes(data, folder, fdate):
    """One daily .xlsx -> one row per employee (Roster sheet; header row is found by looking for EMP Name / AMZ ID)."""
    xls = pd.ExcelFile(io.BytesIO(data))
    sheet = xls.sheet_names[0]
    if "Roster" in xls.sheet_names:
        sheet = "Roster"
    else:
        for sn in xls.sheet_names:
            if any(w in sn.lower() for w in ("roster", "employee", "staff")):
                sheet = sn
                break
    raw = xls.parse(sheet, header=None, dtype=str)
    if raw.empty:
        return pd.DataFrame(columns=ROW_COLS)
    hdr = 0
    for i in range(min(15, len(raw))):
        vals = {_norm(v) for v in raw.iloc[i].tolist() if pd.notna(v)}
        if vals & {"empname", "amzid", "sno"}:
            hdr = i
            break
    heads, seen = [], {}
    for j, v in enumerate(raw.iloc[hdr].tolist()):
        h = (_norm(v) if pd.notna(v) else "") or f"col{j}"
        if h in seen:
            seen[h] += 1
            h = f"{h}_{seen[h]}"
        else:
            seen[h] = 0
        heads.append(h)
    df = raw.iloc[hdr + 1:].copy()
    df.columns = heads
    df = df.reset_index(drop=True)

    def pick(field):
        for cand in ROSTER_FIELDS[field]:
            if cand in df.columns:
                return df[cand].map(_s)
        return pd.Series([""] * len(df), index=df.index, dtype=object)

    empid = pick("psoft").map(clean_id)
    login = pick("amz").map(clean_id).str.lower()
    login = login.where(login != "", empid)
    site = pick("site")
    site = site.where(site != "", folder)
    out = pd.DataFrame({"empid": empid, "login": login, "name": pick("name"), "site": site,
                        "mgr": pick("mgr"), "shift": pick("shift"), "agency": pick("agency"),
                        "att": pick("att").str.upper()})
    out = out[((out["login"] != "") | (out["name"] != "")) & (out["att"] != "")].copy()
    out["date"] = fdate.isoformat()
    out["folder"] = folder
    return out[ROW_COLS].reset_index(drop=True)


@st.cache_resource(show_spinner=False)
def _parse_store():
    """Parsed files, kept between reruns so only NEW or CHANGED files are downloaded again."""
    return {}


@st.cache_data(ttl=300, show_spinner="Loading cases from Canopy storage...")
def load_roster(lookback_days):
    """Every employee-day from the daily files of the last `lookback_days` days, across all storage folders."""
    info = {"folders": {}, "files": 0, "rows": 0, "warnings": []}
    client = s3_client()
    if client is None:
        info["warnings"].append("S3 is not connected.")
        return pd.DataFrame(columns=ROW_COLS), info
    cutoff = now_local().date() - datetime.timedelta(days=lookback_days)
    try:
        folders = s3_folders(client)
    except Exception as e:
        info["warnings"].append(f"Could not list storage folders: {type(e).__name__}: {e}")
        return pd.DataFrame(columns=ROW_COLS), info

    jobs = []
    for folder in folders:
        meta = info["folders"].setdefault(folder, {"total": 0, "loaded": 0, "latest": ""})
        try:
            objs = s3_list(folder + "/", client)
        except Exception as e:
            info["warnings"].append(f"{folder}/: {type(e).__name__}: {e}")
            continue
        for o in objs:
            name = o["key"].rsplit("/", 1)[-1]
            if not name.lower().endswith(".xlsx") or name.startswith("~$"):
                continue
            meta["total"] += 1
            fd = file_date(name)
            if fd is None or fd < cutoff:
                continue
            jobs.append((o, folder, fd))
    jobs.sort(key=lambda j: j[0]["modified"])                    # if two files share a date, the newest upload wins

    store = _parse_store()

    def work(job):
        o, folder, fd = job
        ck = (o["key"], o["etag"])
        if ck in store:
            return store[ck], None
        try:
            data = s3_read(o["key"], client)
            if data is None:
                return None, f"{o['key']}: file not found"
            df = parse_roster_bytes(data, folder, fd)
            store[ck] = df
            return df, None
        except Exception as e:
            return None, f"{o['key']}: {type(e).__name__}: {e}"

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(work, jobs))

    live = {(o["key"], o["etag"]) for o, _, _ in jobs}
    for k in [k for k in list(store) if k not in live]:
        store.pop(k, None)

    frames = []
    for (o, folder, fd), (df, err) in zip(jobs, results):
        if err:
            info["warnings"].append(err)
            continue
        if df is None or df.empty:
            info["warnings"].append(f"{o['key']}: no readable rows (check the Roster sheet and the Attendance column)")
            continue
        frames.append(df)
        meta = info["folders"][folder]
        meta["loaded"] += 1
        meta["latest"] = max(meta["latest"], fd.isoformat())
    info["files"] = len(frames)
    if not frames:
        return pd.DataFrame(columns=ROW_COLS), info
    rows = pd.concat(frames, ignore_index=True)
    rows = rows.drop_duplicates(["folder", "date", "login"], keep="last")
    info["rows"] = len(rows)
    return rows, info


@st.cache_data(ttl=300, show_spinner=False)
def load_case_base(lookback_days):
    """Absence rows (anything except P / OFF) become cases: one case per employee per day."""
    rows, _ = load_roster(lookback_days)
    if rows.empty:
        return pd.DataFrame(columns=CASE_COLS)
    d = rows[~rows["att"].isin(EXCLUDED_ATTENDANCE)].copy()
    if d.empty:
        return pd.DataFrame(columns=CASE_COLS)
    key = d["empid"].where(d["empid"] != "", d["login"])
    d["id"] = "WBC-" + d["date"].str.replace("-", "", regex=False) + "-" + key.map(_safe)
    d = d.drop_duplicates("id", keep="last")
    base = pd.DataFrame({"id": d["id"], "login": d["login"], "empid": d["empid"], "name": d["name"],
                         "site": d["site"], "mgr": d["mgr"], "shift": d["shift"], "agency": d["agency"],
                         "absent": d["att"], "created": d["date"], "status": "Open", "source": "dwd_s3",
                         "sick_hint": (d["att"] == "SL").astype(int), "folder": d["folder"]})
    for col in CASE_COLS:
        if col not in base.columns:
            base[col] = ""
    return base[CASE_COLS]


def load_cases(user=None):
    """Cases from the daily files + whatever people have done to them (saved in storage). user=None -> no site filter."""
    base = load_case_base(LOOKBACK_DAYS)
    recs = load_state_records(f"{STATE_DIR}/cases/")
    rows = {r["id"]: r for r in base.to_dict("records")}
    for r in recs:
        cid = r.get("id")
        if not cid:
            continue
        if cid in rows:
            rows[cid].update({k: r[k] for k in WORKFLOW_KEYS if k in r})
        else:
            rows[cid] = dict(r)                                   # older than the lookback window: kept from its saved copy
    df = pd.DataFrame(list(rows.values())) if rows else pd.DataFrame(columns=CASE_COLS)
    for col in CASE_COLS:
        if col not in df.columns:
            df[col] = ""
    df = df.fillna("")
    allowed = allowed_sites(user) if user else None
    if allowed is not None:
        df = df[df["site"].isin(allowed)]
    df = df[~df["absent"].astype(str).str.strip().str.upper().isin(EXCLUDED_ATTENDANCE)]
    # planned leave (PL) is not an absence: PL rows that are not closed never show up as cases
    is_pl = df["absent"].astype(str).str.strip().str.upper() == "PL"
    df = df[~(is_pl & (df["status"].astype(str).str.strip().str.lower() != "closed"))]
    df = df.sort_values(["created", "id"], ascending=False)
    return prepare(df)


def get_case(case_id):
    df = load_cases(None)
    r = df[df["id"] == case_id]
    return r.iloc[0].to_dict() if not r.empty else None


def save_case_state(case):
    rec = {k: _clean(case.get(k, "")) for k in CASE_COLS}
    write_json(f"{STATE_DIR}/cases/{_safe(rec['id'])}.json", rec)
    load_state_records.clear()


def ua_offences_df():
    cols = ["login", "name", "empid", "site", "date", "offence_type"]
    recs = load_state_records(f"{STATE_DIR}/ua/")
    df = pd.DataFrame(recs) if recs else pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df[cols].fillna("").sort_values("date", ascending=False).reset_index(drop=True)


def upl_summary_df():
    """UPL per employee, worked out from the daily files: scheduled days = every day except OFF;
    UPL days = absence days (not P / OFF / PL) minus cases closed as Incorrect Entry / Converted to PL."""
    cols = ["login", "site", "scheduled_days", "upl_days", "updated"]
    rows, _ = load_roster(LOOKBACK_DAYS)
    if rows.empty:
        return pd.DataFrame(columns=cols)
    sched = rows[rows["att"] != "OFF"]
    absent = rows[~rows["att"].isin(EXCLUDED_ATTENDANCE | {"PL"})]
    cases = load_cases(None)
    rev = cases[cases["outcome"].isin(UPL_REVERSING)]["login"].value_counts()
    g = sched.groupby("login").agg(site=("site", "last"), scheduled_days=("date", "count"), updated=("date", "max"))
    g["upl_days"] = absent.groupby("login").size().reindex(g.index, fill_value=0)
    g["upl_days"] = (g["upl_days"] - rev.reindex(g.index, fill_value=0)).clip(lower=0).astype(int)
    g = g.reset_index()
    return g[cols].sort_values("updated", ascending=False).reset_index(drop=True)


# ----------------------------------------------------------------
# USERS + CUSTOM SITES  (small JSON files in storage)
# ----------------------------------------------------------------
@st.cache_data(ttl=30, show_spinner=False)
def load_users():
    users = None
    try:
        users = read_json(f"{STATE_DIR}/users.json", None)
    except Exception:
        users = []                                        # storage hiccup: fall back to the built-in logins, don't overwrite
    else:
        if not isinstance(users, list):
            users = [dict(u, added=str(datetime.date.today())) for u in DEFAULT_USERS]
            try:
                write_json(f"{STATE_DIR}/users.json", users)
            except Exception:
                pass
    have = {str(u.get("alias", "")).lower() for u in users}
    for d in DEFAULT_USERS:                               # the two built-in logins can never be locked out
        if d["alias"] not in have:
            users.append(dict(d, added=str(datetime.date.today())))
    return users


def save_users(users):
    write_json(f"{STATE_DIR}/users.json", users)
    load_users.clear()


def get_user_by_credential(val):
    if not val:
        return None
    val = val.strip().lower()
    for u in load_users():
        if str(u.get("alias", "")).lower() == val:
            return {"alias": u["alias"], "role": u.get("role", "VPOC"), "sites": u.get("sites") or "All",
                    "added": u.get("added", "")}
    return None


@st.cache_data(ttl=60, show_spinner=False)
def load_custom_sites():
    try:
        data = read_json(f"{STATE_DIR}/custom_sites.json", [])
    except Exception:
        return []
    return data if isinstance(data, list) else []


def save_custom_sites(items):
    write_json(f"{STATE_DIR}/custom_sites.json", items)
    load_custom_sites.clear()


# ----------------------------------------------------------------
# SITES  (country -> BU -> site, plus admin-added custom sites)
# ----------------------------------------------------------------
def get_site_map():
    merged = copy.deepcopy(SITE_MAP_DEFAULT)
    for r in load_custom_sites():
        if not r.get("active", 1):
            continue
        merged.setdefault(r["country"], {}).setdefault(r["bu"], [])
        if r["site"] not in merged[r["country"]][r["bu"]]:
            merged[r["country"]][r["bu"]].append(r["site"])
    return merged


def site_meta(smap):
    """site -> (country, bu)"""
    return {s: (c, bu) for c, bus in smap.items() for bu, ss in bus.items() for s in ss}


def _valid_or_reset(key, options):
    if key in st.session_state and st.session_state[key] not in options:
        del st.session_state[key]


def folder_groups(df, allowed):
    """storage folder -> its sites: the configured SITE_FOLDERS plus every site actually found in that folder's files."""
    groups = {f: list(ss) for f, ss in SITE_FOLDERS.items()}
    if not df.empty and "folder" in df.columns:
        for f, ss in df[df["folder"] != ""].groupby("folder")["site"]:
            lst = groups.setdefault(f, [])
            for s in ss.unique():
                if s and s not in lst:
                    lst.append(s)
    if allowed is not None:
        groups = {f: [s for s in ss if s in allowed] for f, ss in groups.items()}
    return {f: sorted(ss) for f, ss in groups.items() if ss}


def site_filters(df, key, cols):
    """Country -> BU -> Site selector.
    The main site of each storage folder (AUH1, DXB5, DXB3 ...) selects ALL the sub-sites that live in the same
    files - e.g. choosing "AUH1" shows AUH1 + AUH3 + DAD1. Every site can still be chosen on its own."""
    smap = get_site_map()
    meta = site_meta(smap)
    allowed = allowed_sites(current())
    counts = df["site"].value_counts().to_dict() if not df.empty else {}
    groups = folder_groups(df, allowed)

    country_opts = ["All"] + list(smap.keys())
    _valid_or_reset(f"{key}_country", country_opts)
    country = cols[0].selectbox(
        "Country", country_opts, key=f"{key}_country", label_visibility="collapsed",
        format_func=lambda c: "All Countries" if c == "All" else f"{COUNTRY_FLAGS.get(c, '')} {COUNTRY_LABELS.get(c, c)}")

    bu_opts = ["All"] + sorted({bu for c, bus in smap.items() if country in ("All", c) for bu in bus})
    _valid_or_reset(f"{key}_bu", bu_opts)
    bu = cols[1].selectbox("BU", bu_opts, key=f"{key}_bu", label_visibility="collapsed",
                           format_func=lambda b: "All BUs" if b == "All" else b)

    narrowed = country != "All" or bu != "All"
    pool = [s for s, (c, b) in meta.items() if country in ("All", c) and bu in ("All", b)]
    if not narrowed:
        pool += [s for s in counts if s and s not in meta]          # sites found in data but not in the map
        pool += [s for ss in groups.values() for s in ss if s not in meta]
    if allowed is not None:
        pool = [s for s in pool if s in allowed]
    pool = sorted(set(pool))
    visible = {f: ss for f, ss in groups.items() if len(ss) > 1 and any(s in pool for s in ss)}
    site_opts = ["All"] + [f"@{f}" for f in sorted(visible)] + pool
    _valid_or_reset(f"{key}_site", site_opts)

    def fmt_site(s):
        if s == "All":
            return "All Sites"
        if s.startswith("@"):
            f = s[1:]
            subs = [x for x in visible[f] if x != f]
            n = int(df["site"].isin(visible[f]).sum()) if not df.empty else 0
            return f"{f} + sub-sites: {', '.join(subs)} ({n})"
        if s in visible:                                          # a main site is also listed on its own
            return f"{s} only ({counts.get(s, 0)})"
        return f"{s} ({counts.get(s, 0)})"

    site = cols[2].selectbox("Site", site_opts, key=f"{key}_site", label_visibility="collapsed", format_func=fmt_site)

    if site.startswith("@"):
        f = site[1:]
        out = df[(df["folder"] == f) | df["site"].isin(groups.get(f, []))]
        return out[out["site"].isin(pool)] if narrowed else out
    if site != "All":
        return df[df["site"] == site]
    if narrowed:
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
    op = df[df["_open"] & (df["site"].astype(str).str.strip() != "")]
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
              f'<div class="mtn-v">{esc(lead)}</div></div>'
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
        tiles.append(f'<div class="mtn-tile" style="border-top-color:{colors[s]}"><em>{esc(s)}</em>'
                     f'<b>{int(c)}</b><small>{c / total_open * 100:.1f}% of open</small></div>')
    return banner + caption + chart + '<div class="mtn-legend">' + "".join(tiles) + '</div>'


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


def set_chip(k):
    """Clicking a stat chip filters the case list; clicking the active chip again shows everything."""
    st.session_state["dash_chip"] = "total" if st.session_state.get("dash_chip", "total") == k else k


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


def ua_records(login=None):
    recs = load_state_records(f"{STATE_DIR}/ua/")
    return [r for r in recs if login is None or r.get("login") == login]


def ua_for(login):
    return ua_status([r.get("date") for r in ua_records(login)])


def next_escalation(login):
    lvl = min(ua_for(login)["level"] + 1, 6)
    valid = (datetime.date.today() + datetime.timedelta(days=90)).isoformat()
    return lvl, UAL[lvl], valid


def save_upload(case_id, up):
    safe = up.name.replace("/", "_").replace("\\", "_")
    s3_write(f"{UPLOAD_DIR}/{case_id}/{safe}", up.getvalue(), up.type or "application/octet-stream")
    return safe


def show_existing_doc(case_id, filename, tag="a"):
    if not filename:
        return
    data = None
    try:
        data = s3_read(f"{UPLOAD_DIR}/{case_id}/{filename}")
    except Exception:
        pass
    if data:
        st.download_button(f"📎 {filename}", data, filename, key=f"dl_{tag}_{case_id}")
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

    rec = {k: case.get(k, "") for k in CASE_COLS}
    rec.update({"status": "Closed", "outcome": outcome, "reason": remarks, "doc_type": doc_type,
                "doc_file": doc_file, "closed": today, "closed_by": user["alias"], "closedby": user["alias"],
                "escalation_level": esc_level, "escalation_action": esc_action,
                "ua_escalation_level": int(esc_level or 0), "escalation_valid_until": valid_until})
    try:
        save_case_state(rec)
    except Exception as e:
        return False, f"Could not save to Canopy storage: {e}"

    msg = f"{case['id']} closed: {outcome}."
    if outcome == "Unauthorized":
        try:                                    # one offence per associate per day - saving again just overwrites it
            write_json(f"{STATE_DIR}/ua/{_safe(case['login'])}__{today}.json",
                       {"login": case["login"], "name": case.get("name", ""), "empid": case.get("empid", ""),
                        "site": case.get("site", ""), "date": today, "offence_type": ""})
            load_state_records.clear()
        except Exception as e:
            return False, f"Case closed, but the UA offence could not be saved: {e}"
        msg += f" Escalation: L{esc_level} - {esc_action}. Valid until {ua_for(case['login'])['valid_until']}."
    return True, msg


def _case_date(row):
    for k in ("created", "absent", "closed"):
        d = pd.to_datetime(row.get(k), errors="coerce")
        if pd.notna(d):
            return d.date()
    return None


def build_verbatim(c):
    login, name = c["login"], c.get("name") or c["login"]
    today = datetime.date.today()
    hist = [{"date": r.get("date"), "offence_type": r.get("offence_type")}
            for r in sorted(ua_records(login), key=lambda r: str(r.get("date")))]
    ua = ua_for(login)
    lvl, action, _ = next_escalation(login)
    all_cases = load_cases(None)
    ua_cases = all_cases[(all_cases["login"] == login) & (all_cases["outcome"] == "Unauthorized")].to_dict("records")
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
    absent = c.get("created") or "today"
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
    c = get_case(case_id)
    if c and c.get("status") == "Open":
        c["status"] = "In Progress"
        try:
            save_case_state(c)
        except Exception as e:
            st.toast(f"Could not mark the case In Progress: {e}", icon="⚠️")
    case_dialog(case_id)


@st.dialog("Case details", width="large")
def case_dialog(case_id):
    c = get_case(case_id)
    if not c:
        st.error("Case not found.")
        return
    user = current()
    ua = ua_for(c["login"])
    info = [("Case ID", c["id"]), ("Login", c["login"]), ("Employee ID", clean_id(c["empid"])),
            ("Name", c["name"]), ("Site", c["site"]), ("Manager", c["mgr"]), ("Shift", c["shift"]),
            ("Agency", c["agency"]), ("Attendance code", c["absent"]), ("Absence date", c["created"]),
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
        file_types = ["pdf", "jpg", "jpeg", "png", "doc", "docx"]
        if optional_doc:                                   # Sick Leave: optional upload only
            up = st.file_uploader("Upload sick leave certificate (optional)", type=file_types, key=f"file_{case_id}")
            st.caption("Optional - you can submit the case with or without the sick leave document.")
        else:                                              # Unauthorized L2+: warning letter (required)
            d1, d2 = st.columns([1, 2])
            start = c.get("doc_type") or doc_default
            doc_type = d1.selectbox("Document type", DOC_TYPES, key=f"dtype_{case_id}",
                                    index=DOC_TYPES.index(start) if start in DOC_TYPES else 0)
            up = d2.file_uploader("Supporting document", type=file_types, key=f"file_{case_id}")
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
    chip_defs = [("total", "Total Cases", pd.Series(True, index=df.index)),
                 ("open", "Open Cases", df["_open"]),
                 ("closed", "Closed Cases", g == "closed"),
                 ("pending", "Pending Cases", pending),
                 ("pending5", "Pending > 5 Days", pending & (df["_days"] > 5))]
    active = st.session_state.get("dash_chip", "total")
    if active not in {k for k, _, _ in chip_defs}:
        active = "total"
    for col, (k, label, mask) in zip(st.columns([1, 1, 1, 1, 1.2, 2.6]), chip_defs):
        with col:
            with st.container(key=f"chip_{k}"):
                st.button(f"✦ {label}  **{int(mask.sum())}**", key=f"chipbtn_{k}",
                          type="primary" if k == active else "secondary",
                          on_click=set_chip, args=(k,), use_container_width=True)
    base = df[{k: m for k, _, m in chip_defs}[active]]          # the chip picked above filters the case list

    left, right = st.columns([2.35, 1], gap="medium")
    with left:
        with st.container(border=True, key="card_recent"):
            h1, h2 = st.columns([1.6, 2.4], vertical_alignment="center")
            h1.markdown(card_header_html("check", "Recent Cases", "Latest cases across all sites"), unsafe_allow_html=True)
            search = h2.text_input("Search", placeholder="Search by Case ID, Site, Type, Name, Login...",
                                   label_visibility="collapsed", key="q_search")

            f1, f2, f3, f4, f5 = st.columns([1, 0.8, 1.2, 1.1, 0.9])
            view = site_filters(base, "dash", [f1, f2, f3])
            view = agency_filter(view, "dash_agency", f4)
            size = int(f5.selectbox("Rows per page", [8, 25, 50, 100, 200], key="q_size",
                                    format_func=lambda n: f"{n} / page", label_visibility="collapsed"))

            if search.strip():
                s = search.strip().lower()
                hay = (view["id"] + " " + view["site"] + " " + view["_type"] + " " + view["name"] + " " + view["login"] + " " + view["agency"]).str.lower()
                view = view[hay.str.contains(s, regex=False)]

            bar1, bar2, bar3 = st.columns([7, 1, 1], vertical_alignment="center")
            bar1.markdown(f'<div class="showing" style="padding-top:0">{len(view)} cases match - downloads include all of them, not just this page</div>',
                          unsafe_allow_html=True)
            export = view[CASE_COLS]
            bar2.download_button("⬇ CSV", export.to_csv(index=False).encode(), "wbc_cases.csv", "text/csv",
                                 key="dl_csv_dash", use_container_width=True)
            xl = to_excel_bytes(export)
            if xl:
                bar3.download_button("⬇ Excel", xl, "wbc_cases.xlsx",
                                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                     key="dl_xlsx_dash", use_container_width=True)

            sig = (search, tuple(st.session_state.get(f"dash_{k}") for k in ("country", "bu", "site", "agency")), size, active)
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
            view = view[view["_open"]]
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


def table_page(title, sub, icon, card_title, card_sub, loader, chips, empty_msg, key):
    page_shell(title, sub)
    data = loader()
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
               "UA Offences", "Most recent offences first", ua_offences_df,
               ua_chips, "No UA offences recorded yet.", "ua")


def page_upl():
    table_page("UPL Summary Analytics", "Unplanned leave and schedule performance summary.", "list",
               "UPL Summary", f"Unplanned leave per employee, from the daily files of the last {LOOKBACK_DAYS} days",
               upl_summary_df, upl_chips, "No UPL summary data available.", "upl")


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
            st.info("No closed cases yet. When a case is closed as Authorized or Unauthorized it appears here.")
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


ACCESS_ROLES = ["VPOC", "HRBP"]               # the only two roles that can be given


def can_manage_access(user):
    return is_admin(user) or str(user.get("alias", "")).lower() in USER_MGMT_BYPASS


def _add_access():
    alias = str(st.session_state.get("acc_alias", "")).strip().lower()
    role = st.session_state.get("acc_role", ACCESS_ROLES[0])
    sites = st.session_state.get("acc_sites", []) or []
    users = list(load_users())
    if not re.fullmatch(r"[a-z0-9._-]+", alias):
        st.session_state["_acc_msg"] = (False, "Enter a valid alias (letters, numbers, dot, dash or underscore - no spaces).")
    elif role not in ACCESS_ROLES:
        st.session_state["_acc_msg"] = (False, "Role must be VPOC or HRBP.")
    elif any(str(u.get("alias", "")).lower() == alias for u in users):
        st.session_state["_acc_msg"] = (False, f"{alias} already has access.")
    else:
        users.append({"alias": alias, "role": role,
                      "sites": ",".join(sites) if (sites and role == "HRBP") else "All",
                      "added": str(datetime.date.today())})
        try:
            save_users(users)
        except Exception as e:
            st.session_state["_acc_msg"] = (False, f"Could not save to Canopy storage: {e}")
            return
        st.session_state["_acc_msg"] = (True, f"{alias} can now open the portal as {role}.")
        st.session_state["acc_alias"] = ""
        st.session_state["acc_sites"] = []


def page_users():
    user = current()
    page_shell("Admin Access", "Give people access to the portal. Anyone added here can sign in with their alias.")
    if not can_manage_access(user):
        st.error("Access Denied: only an admin can give portal access.")
        return

    with st.container(border=True, key="card_access_add"):
        st.markdown(card_header_html("user", "Give Access", "Add a login - they can open the tool straight away"),
                    unsafe_allow_html=True)
        a, b, c, d = st.columns([1.2, 0.8, 1.6, 0.8], vertical_alignment="bottom")
        a.text_input("User alias", placeholder="e.g. mnnafee", key="acc_alias")
        b.selectbox("Role", ACCESS_ROLES, key="acc_role")
        site_choices = sorted(set(site_meta(get_site_map())) | {s for ss in SITE_FOLDERS.values() for s in ss})
        c.multiselect("Sites - HRBP only (empty = all sites; VPOC always sees all)", site_choices, key="acc_sites")
        d.button("Add access", type="primary", key="acc_add", on_click=_add_access, use_container_width=True)
        msg = st.session_state.pop("_acc_msg", None)
        if msg:
            (st.success if msg[0] else st.error)(msg[1])

    people = sorted(load_users(), key=lambda p: (str(p.get("added", "")), str(p.get("alias", ""))), reverse=True)
    with st.container(border=True, key="card_users"):
        st.markdown(card_header_html("list", "People with access", f"{len(people)} logins can open the portal"),
                    unsafe_allow_html=True)
        for p in people:
            x, y = st.columns([5, 1], vertical_alignment="center")
            x.markdown(f'<div class="td"><b>{esc(p["alias"])}</b> · {esc(p.get("role", ""))} · '
                       f'{esc(p.get("sites") or "All")} · added {esc(p.get("added", ""))}</div>', unsafe_allow_html=True)
            locked = (p["alias"] == user["alias"] or str(p.get("role", "")).lower() == "admin"
                      or p["alias"] in USER_MGMT_BYPASS or p["alias"] in {d["alias"] for d in DEFAULT_USERS})
            if not locked and y.button("Remove", key=f"rm_user_{p['alias']}"):
                try:
                    save_users([u for u in load_users() if u.get("alias") != p["alias"]])
                    st.session_state["_flash"] = f"{p['alias']} no longer has access."
                except Exception as e:
                    st.error(f"Could not save to Canopy storage: {e}")
                st.rerun()

    with st.container(border=True, key="card_sitesadmin"):
        st.markdown(card_header_html("pin", "Manage Sites", "Add a site to the Country / BU / Site selector"),
                    unsafe_allow_html=True)
        a, b, c, d = st.columns([1, 1, 1, 0.7], vertical_alignment="bottom")
        country = a.selectbox("Country", list(SITE_MAP_DEFAULT), key="ns_country",
                              format_func=lambda x: f"{COUNTRY_FLAGS.get(x, '')} {COUNTRY_LABELS.get(x, x)}")
        bu = b.selectbox("BU", ["FC/SC", "AMZL"], key="ns_bu")
        site = c.text_input("Site code", placeholder="e.g. DXB9", key="ns_site").strip().upper()
        if d.button("Add site", key="ns_add", disabled=not site):
            items = [r for r in load_custom_sites() if not (r["country"] == country and r["bu"] == bu and r["site"] == site)]
            items.append({"country": country, "bu": bu, "site": site, "active": 1,
                          "added_by": user["alias"], "added_at": str(datetime.date.today())})
            try:
                save_custom_sites(items)
                st.session_state["_flash"] = f"{site} added."
            except Exception as e:
                st.error(f"Could not save to Canopy storage: {e}")
            st.rerun()
        custom = sorted([r for r in load_custom_sites() if r.get("active", 1)],
                        key=lambda r: (r["country"], r["bu"], r["site"]))
        for i, r in enumerate(custom):
            x, y = st.columns([5, 1], vertical_alignment="center")
            x.markdown(f'<div class="td">{COUNTRY_FLAGS.get(r["country"], "")} {esc(r["country"])} · {esc(r["bu"])} · <b>{esc(r["site"])}</b></div>',
                       unsafe_allow_html=True)
            if y.button("Remove", key=f"rm_site_{i}"):
                items = [q for q in load_custom_sites()
                         if not (q["country"] == r["country"] and q["bu"] == r["bu"] and q["site"] == r["site"])]
                try:
                    save_custom_sites(items)
                except Exception as e:
                    st.error(f"Could not save to Canopy storage: {e}")
                st.rerun()
        if not custom:
            st.caption("No custom sites yet - the built-in site list (UAE, Egypt, KSA, Turkiye) is always available.")


def page_settings():
    user = current()
    page_shell("Settings", "Portal configuration, Canopy storage connection and system status.")
    s = s3_status()
    rows, info = load_roster(LOOKBACK_DAYS)
    cases = load_cases(None)
    n_state = len(load_state_records(f"{STATE_DIR}/cases/"))
    n_ua = len(load_state_records(f"{STATE_DIR}/ua/"))
    n_users = len(load_users())
    latest = max((m["latest"] for m in info["folders"].values() if m["latest"]), default="–")

    with st.container(border=True, key="card_settings"):
        st.markdown(card_header_html("target", "Canopy Storage", "Where this portal reads and saves everything"),
                    unsafe_allow_html=True)
        st.markdown(
            f'<div class="kv"><b>Connection</b><span>{"✅ Connected" if s["connected"] else "❌ Not connected"} - {esc(s["message"])}</span>'
            f'<b>Bucket</b><span>{esc(s["bucket"])}</span>'
            f'<b>Folder (prefix)</b><span>{esc(s["prefix"])}</span>'
            f'<b>Daily files read</b><span>{info["files"]} files · {info["rows"]:,} employee-days · '
            f'last {LOOKBACK_DAYS} days · newest file {esc(latest)}</span>'
            f'<b>Cases</b><span>{len(cases)} cases ({n_state} worked on / closed and saved) · {n_ua} UA offences · {n_users} users</span>'
            f'<b>Saved to</b><span>{esc(STATE_DIR)}/ (cases, UA offences, users, sites) and {esc(UPLOAD_DIR)}/ (documents)</span>'
            f'<b>Signed in as</b><span>{esc(user["alias"])} ({esc(user["role"])})</span>'
            f'<b>Sites</b><span>{esc(user["sites"])}</span></div>', unsafe_allow_html=True)
        st.caption("Data refreshes automatically every few minutes; use 'Reload data' in the sidebar to pull new files right away.")

        folder_rows = []
        for f in sorted(set(info["folders"]) | set(SITE_FOLDERS)):
            m = info["folders"].get(f)
            folder_rows.append({"Folder": f, "Sites": ", ".join(SITE_FOLDERS.get(f, [])) or "(read from files)",
                                "Files in folder": m["total"] if m else "not found in storage",
                                f"Files read (last {LOOKBACK_DAYS} days)": m["loaded"] if m else 0,
                                "Newest file": (m["latest"] or "–") if m else "–"})
        st.dataframe(pd.DataFrame(folder_rows), use_container_width=True, hide_index=True)
        for w in info["warnings"][:15]:
            st.warning(w)
        if len(info["warnings"]) > 15:
            st.caption(f"... and {len(info['warnings']) - 15} more warnings.")


# ----------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------
def main():
    st.markdown(BASE_CSS, unsafe_allow_html=True)

    # ---------- storage must be reachable (it is the only database) ----------
    conn = s3_status()
    if not conn["connected"]:
        st.markdown(LOGIN_CSS, unsafe_allow_html=True)
        st.markdown("<div style='height:9vh'></div>", unsafe_allow_html=True)
        _, mid, _ = st.columns([1, 1.6, 1])
        with mid:
            with st.container(border=True, key="card_login"):
                st.markdown(BRAND_HTML + '<div class="login-t">Canopy storage is not connected</div>', unsafe_allow_html=True)
                st.error(conn["message"])
                st.code(f"bucket: {conn['bucket']}\nprefix: {conn['prefix']}")
                if st.button("Retry connection", use_container_width=True):
                    _s3_connect.clear()
                    st.rerun()
        st.stop()

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
                alias = st.text_input("User alias", placeholder="e.g. mnnafee",
                                      label_visibility="collapsed")
                if st.button("Sign In", use_container_width=True):
                    u = get_user_by_credential(alias)
                    if u:
                        st.session_state.token = u["alias"]
                        st.rerun()
                    else:
                        st.error("Invalid alias. Please verify and try again.")
                st.markdown('<div class="login-help">Access issue? Contact <b>mnnafee</b></div>', unsafe_allow_html=True)
        st.stop()

    st.session_state["_user"] = user

    # ---------- navigation ----------
    pages = [
        st.Page(page_dashboard, title="Dashboard", icon=":material/home:", url_path="dashboard", default=True),
        st.Page(page_cases, title="Cases Dashboard", icon=":material/table_chart:", url_path="cases"),
        st.Page(page_ua, title="UA Offences Tracker", icon=":material/shield:", url_path="ua-offences"),
        st.Page(page_upl, title="UPL Summary Analytics", icon=":material/bar_chart:", url_path="upl-summary"),
        st.Page(page_disciplinary, title="Disciplinary Actions", icon=":material/gavel:", url_path="disciplinary"),
        st.Page(page_settings, title="Settings", icon=":material/settings:", url_path="settings"),
    ]
    if can_manage_access(user):          # only people who can give access see this page
        pages.insert(5, st.Page(page_users, title="Admin Access", icon=":material/admin_panel_settings:",
                                url_path="admin-access"))
    try:
        nav = st.navigation(pages, position="hidden")
    except TypeError:           # older Streamlit: default nav is hidden by CSS instead
        nav = st.navigation(pages)

    with st.sidebar:
        st.markdown(BRAND_HTML, unsafe_allow_html=True)
        for p in pages:
            st.page_link(p, label=p.title, icon=p.icon)
        with st.container(key="refresh"):
            if st.button("↻ Reload data", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
        with st.container(key="signout"):
            if st.button("Sign out", use_container_width=True):
                st.session_state.clear()
                st.query_params.clear()
                st.rerun()
        st.markdown('<div class="side-foot">Better Workplace<br>Safer Tomorrow<span></span></div>', unsafe_allow_html=True)

    nav.run()


if __name__ == "__main__":
    main()
