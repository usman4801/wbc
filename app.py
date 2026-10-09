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
.site-row{display:grid;grid-template-columns:70px 1fr 46px;align-items:center;gap:8px;
  padding:11px 0;border-bottom:1px solid #f0f3f8;}
.site-row:last-child{border-bottom:none;}
.site-l{display:flex;align-items:center;gap:8px;font-size:.8rem;font-weight:600;color:#1e293b;}
.site-l i{width:8px;height:8px;border-radius:50%;display:inline-block;flex:none;}
.site-n{font-size:.8rem;font-weight:600;color:#1e293b;}
.bar{height:6px;background:#eef2f9;border-radius:99px;overflow:hidden;margin-top:3px;}
.bar span{display:block;height:100%;border-radius:99px;}
.site-p{font-size:.7rem;color:var(--muted);text-align:right;}

/* ---------- dialog ---------- */
.kv{display:grid;grid-template-columns:130px 1fr;gap:7px 12px;font-size:.84rem;}
.kv b{color:#475569;font-weight:600;}
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
<div><b>WBC Portal</b><small>Workplace Behaviour &amp; Compliance</small></div></div>
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


def sites_html(df):
    if df.empty:
        return '<div class="card-s" style="padding:16px 0">No data yet.</div>'
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
def current():
    return st.session_state["_user"]


def page_shell(title, sub, wave=False):
    st.markdown(topbar_html(current(), title, sub, wave), unsafe_allow_html=True)


def set_page(p):
    st.session_state.cases_page = p


@st.dialog("Case details")
def show_case(r):
    rows = [("Case ID", clean_id(r["id"])), ("Employee", r["name"]), ("Login", r["login"]),
            ("Employee ID", clean_id(r["empid"])), ("Site", r["site"]), ("Manager", r["mgr"]),
            ("Shift", r["shift"]), ("Agency", r["agency"]), ("Attendance / absent", r["absent"]),
            ("Opened", r["created"]), ("Status", r["status"]), ("Outcome", r["outcome"]),
            ("Reason", r["reason"]), ("Notes", r["notes"])]
    body = "".join(f"<b>{esc(k)}</b><span>{esc(v) or '–'}</span>" for k, v in rows)
    st.markdown(f'<div class="kv">{body}</div>', unsafe_allow_html=True)


def cases_table(view):
    """Styled table with real 'View' buttons + pagination."""
    total = len(view)
    pages = max(1, math.ceil(total / PAGE_SIZE))
    cur = min(max(1, st.session_state.get("cases_page", 1)), pages)
    st.session_state.cases_page = cur
    start = (cur - 1) * PAGE_SIZE
    chunk = view.iloc[start:start + PAGE_SIZE]
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
            h1, h2, h3 = st.columns([2.0, 2.3, 1.2], vertical_alignment="center")
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
                st.session_state.cases_page = 1
            cases_table(view)

    with right:
        with st.container(border=True, key="card_sites"):
            st.markdown(card_header_html("pin", "Cases by Site", "Total cases at each site"), unsafe_allow_html=True)
            st.markdown(sites_html(df), unsafe_allow_html=True)


def page_cases():
    df = load_cases(current())
    page_shell("Cases Dashboard", "Real-time tracking of employee roster performance, attendance, and operational status.")
    st.markdown(chips_html([
        ("Total Records", len(df)),
        ("Active Sites", df.loc[df["site"] != "", "site"].nunique()),
        ("System Status", "Operational")]), unsafe_allow_html=True)
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
            st.dataframe(out, use_container_width=True, height=440, hide_index=True)
            st.download_button("⬇ Export CSV", out.to_csv(index=False).encode(), "wbc_cases.csv", "text/csv")


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


def page_users():
    user = current()
    page_shell("User Management", "Manage administrative users, roles, and facility permissions.")
    if user["role"] != "Admin":
        st.error("Access Denied: Admin privileges required to view users.")
        return
    data = read_table("SELECT alias, role, sites, added, token FROM users")
    with st.container(border=True, key="card_users"):
        st.markdown(card_header_html("user", "Portal Users", "Roles and facility permissions"), unsafe_allow_html=True)
        st.dataframe(data, use_container_width=True, height=380, hide_index=True)


def page_settings():
    user = current()
    page_shell("Settings", "Portal configuration, environment status, and system settings.")
    with st.container(border=True, key="card_settings"):
        st.markdown(card_header_html("target", "System Status", "Environment and database"), unsafe_allow_html=True)
        st.success("System is fully synchronized with the local database and excel repository.")
        st.markdown(f'<div class="kv"><b>Database</b><span>{esc(os.path.abspath(DB_PATH))}</span>'
                    f'<b>Signed in as</b><span>{esc(user["alias"])} ({esc(user["role"])})</span>'
                    f'<b>Sites</b><span>{esc(user["sites"])}</span></div>', unsafe_allow_html=True)


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
