import streamlit as st
import sqlite3
import os
import datetime
import pandas as pd

# ----------------------------------------------------------------
# CONFIG & MODERN UI DESIGN
# ----------------------------------------------------------------
st.set_page_config(page_title="WBC Enterprise Portal", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .main { background-color: #f4f6f9; }
    .stMetric { background-color: #ffffff; padding: 18px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.04); border-left: 5px solid #3b82f6; }
    h1, h2, h3 { color: #1e293b; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    .stSidebar { background-color: #1e293b !important; }
    </style>
""", unsafe_allow_html=True)

DB_PATH = os.environ.get("WBC_DB_PATH", "wbc.db")

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

init_db()

# ----------------------------------------------------------------
# AUTHENTICATION
# ----------------------------------------------------------------
if "token" not in st.session_state:
    st.session_state.token = ""

def get_user_by_credential(val):
    if not val:
        return None
    db = get_db()
    row = db.execute('SELECT * FROM users WHERE token=? OR alias=?', (val.strip().lower(), val.strip().lower())).fetchone()
    db.close()
    return dict(row) if row else None

query_params = st.query_params
if "token" in query_params and not st.session_state.token:
    st.session_state.token = query_params["token"]

current_user = get_user_by_credential(st.session_state.token)

# ----------------------------------------------------------------
# LOGIN SCREEN (MODERN & CLEAN)
# ----------------------------------------------------------------
if not current_user:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## 🔐 WBC Enterprise Portal Login")
        st.markdown("Please enter your authorized user alias to access the dashboard.")
        input_val = st.text_input("User Alias:", value="javmuhak", placeholder="e.g. javmuhak")
        if st.button("Sign In", use_container_width=True):
            user = get_user_by_credential(input_val)
            if user:
                st.session_state.token = user['alias']
                st.success(f"Welcome back, {user['alias'].upper()}! Role: {user['role']}")
                st.rerun()
            else:
                st.error("Invalid alias. Please verify and try again.")
    st.stop()

# ----------------------------------------------------------------
# DASHBOARD NAVIGATION & UI
# ----------------------------------------------------------------
st.sidebar.markdown(f"### 👤 {current_user['alias'].upper()}")
st.sidebar.markdown(f"**Role:** `{current_user['role']}`  \n**Sites:** `{current_user['sites']}`")
st.sidebar.markdown("---")

menu = st.sidebar.selectbox("Navigation Menu", ["Cases Dashboard", "UA Offences", "UPL Summary", "User Management", "Settings"])

db = get_db()

if menu == "Cases Dashboard":
    st.title("📋 WBC Cases & Attendance Dashboard")
    st.markdown("Real-time tracking of employee roster performance, attendance, and operational status.")
    
    # Fetch available sites for filtering
    site_rows = db.execute('SELECT DISTINCT site FROM cases WHERE site IS NOT NULL AND site != ""').fetchall()
    available_sites = ['All Sites'] + [r['site'] for r in site_rows]
    
    # Top Control Bar (Site Filter & Metrics)
    col_filter, col_spacer = st.columns([2, 4])
    with col_filter:
        selected_site = st.selectbox("🏢 Filter by Site Location:", available_sites)
        
    query = 'SELECT * FROM cases'
    params = []
    conditions = []
    
    if selected_site != 'All Sites':
        conditions.append('site = ?')
        params.append(selected_site)
        
    if current_user['role'] not in ('Admin', 'VPOC', 'PXT') and current_user['sites'] != 'All':
        user_sites = [s.strip() for s in current_user['sites'].split(',')]
        placeholders = ','.join('?' for _ in user_sites)
        conditions.append(f'site IN ({placeholders})')
        params.extend(user_sites)
        
    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
        
    query += ' ORDER BY created DESC, id DESC'
    
    cases = db.execute(query, params).fetchall()
    cases_list = [dict(r) for r in cases]
    
    # Summary Metric Cards
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Records", len(cases_list))
    m2.metric("Active Sites", len(available_sites) - 1)
    m3.metric("System Status", "Operational 🟢")
    
    st.markdown("---")
    
    if cases_list:
        st.dataframe(cases_list, use_container_width=True, height=520)
    else:
        st.info("No records found matching your selected criteria.")

elif menu == "UA Offences":
    st.title("⚠️ UA Offences Tracker")
    st.markdown("Comprehensive overview of recorded unauthorized absence offences.")
    rows = db.execute('SELECT * FROM ua_offences ORDER BY date DESC').fetchall()
    ua_list = [dict(r) for r in rows]
    if ua_list:
        st.dataframe(ua_list, use_container_width=True, height=500)
    else:
        st.info("No UA offences recorded in the database.")

elif menu == "UPL Summary":
    st.title("📊 UPL Summary Analytics")
    st.markdown("Unplanned leave and schedule performance summary.")
    rows = db.execute('SELECT * FROM upl_summary ORDER BY updated DESC').fetchall()
    upl_list = [dict(r) for r in rows]
    if upl_list:
        st.dataframe(upl_list, use_container_width=True, height=500)
    else:
        st.info("No UPL summary data available.")

elif menu == "User Management":
    st.title("👥 User Management & Access Control")
    st.markdown("Manage administrative users, roles, and facility permissions.")
    if current_user['role'] != 'Admin':
        st.error("Access Denied: Admin privileges required to view users.")
    else:
        users = db.execute('SELECT alias, role, sites, added, token FROM users').fetchall()
        st.dataframe([dict(u) for u in users], use_container_width=True, height=400)

elif menu == "Settings":
    st.title("⚙️ Application Configuration & Settings")
    st.markdown("Portal configuration, environment status, and system settings.")
    st.success("System is fully synchronized with the local database and excel repository.")

db.close()
