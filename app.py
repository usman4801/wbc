import streamlit as st
import sqlite3
import os
import datetime
import pandas as pd

# ----------------------------------------------------------------
# CONFIG & DATABASE SETUP
# ----------------------------------------------------------------
st.set_page_config(page_title="WBC Portal", layout="wide")

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
    
    # AUTO-IMPORT EXCEL FILE PROPERLY
    count = c.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    if count == 0:
        excel_files = [f for f in os.listdir('.') if f.endswith('.xlsx') or f.endswith('.xls')]
        if excel_files:
            try:
                file_path = excel_files[0]
                df = pd.read_excel(file_path)
                # Normalize column names to lowercase/stripped to avoid mismatch
                df.columns = [str(col).strip().lower() for col in df.columns]
                
                for _, row in df.iterrows():
                    # Helper to safely fetch values from various possible column header names
                    def get_val(keys, default=""):
                        for k in keys:
                            if k in df.columns and pd.notna(row[k]):
                                return str(row[k])
                        return default

                    case_id = get_val(['id', 'case_id', 'case id'], f"AUTO-{datetime.datetime.now().timestamp()}")
                    login = get_val(['login', 'username', 'user'], 'unknown')
                    empid = get_val(['empid', 'emp_id', 'employee id', 'id'])
                    name = get_val(['name', 'employee name', 'full name'])
                    site = get_val(['site', 'location', 'facility'])
                    mgr = get_val(['mgr', 'manager', 'supervisor'])
                    shift = get_val(['shift', 'timing'])
                    agency = get_val(['agency', 'vendor'])
                    absent = get_val(['absent', 'absence_date', 'date'])
                    created = get_val(['created', 'date', 'created_at'], str(datetime.date.today()))
                    status = get_val(['status'], 'Open')
                    
                    c.execute('''INSERT OR REPLACE INTO cases (
                        id, login, empid, name, site, mgr, shift, agency, absent, created, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                    (case_id, login, empid, name, site, mgr, shift, agency, absent, created, status))
                
                conn.commit()
            except Exception as e:
                print("Error auto-importing excel:", e)
                
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
# LOGIN SCREEN
# ----------------------------------------------------------------
if not current_user:
    st.title("🔐 WBC Portal - Authentication")
    st.markdown("Apna alias likhein (mis ke taur par **javmuhak** ya **mnnafee**) aur login karein.")
    
    input_val = st.text_input("Enter Alias:", value="javmuhak")
    if st.button("Login"):
        user = get_user_by_credential(input_val)
        if user:
            st.session_state.token = user['alias']
            st.success(f"Khushamdid, {user['alias'].upper()}! Role: {user['role']}")
            st.rerun()
        else:
            st.error("Invalid alias. Dobara check karein.")
    
    st.stop()

# ----------------------------------------------------------------
# STREAMLIT DASHBOARD
# ----------------------------------------------------------------
st.sidebar.title(f"👤 Welcome, {current_user['alias'].upper()}")
st.sidebar.markdown(f"**Role:** {current_user['role']} | **Sites:** {current_user['sites']}")

# Add a button to reset/re-import database if needed
if st.sidebar.button("🔄 Refresh Data from Excel"):
    if os.path.exists("wbc.db"):
        os.remove("wbc.db")
    st.rerun()

menu = st.sidebar.selectbox("Navigation", ["Cases Dashboard", "UA Offences", "UPL Summary", "User Management", "Settings"])

db = get_db()

if menu == "Cases Dashboard":
    st.header("📋 WBC Cases Dashboard")
    if current_user['role'] in ('Admin', 'VPOC', 'PXT') or current_user['sites'] == 'All':
        cases = db.execute('SELECT * FROM cases ORDER BY created DESC, id DESC').fetchall()
    else:
        sites = [s.strip() for s in current_user['sites'].split(',')]
        placeholders = ','.join('?' for _ in sites)
        cases = db.execute(f'SELECT * FROM cases WHERE site IN ({placeholders}) ORDER BY created DESC', sites).fetchall()
    
    cases_list = [dict(r) for r in cases]
    if cases_list:
        st.dataframe(cases_list, use_container_width=True)
    else:
        st.info("No cases found in the database.")

elif menu == "UA Offences":
    st.header("⚠️ UA Offences Tracker")
    rows = db.execute('SELECT * FROM ua_offences ORDER BY date DESC').fetchall()
    ua_list = [dict(r) for r in rows]
    if ua_list:
        st.dataframe(ua_list, use_container_width=True)
    else:
        st.info("No UA offences recorded.")

elif menu == "UPL Summary":
    st.header("📊 UPL Summary Analytics")
    rows = db.execute('SELECT * FROM upl_summary ORDER BY updated DESC').fetchall()
    upl_list = [dict(r) for r in rows]
    if upl_list:
        st.dataframe(upl_list, use_container_width=True)
    else:
        st.info("No UPL summary data available.")

elif menu == "User Management":
    st.header("👥 User Management & Access")
    if current_user['role'] != 'Admin':
        st.error("Admin permission required to view users.")
    else:
        users = db.execute('SELECT alias, role, sites, added, token FROM users').fetchall()
        st.dataframe([dict(u) for u in users], use_container_width=True)

elif menu == "Settings":
    st.header("⚙️ Application Settings")
    settings_rows = db.execute('SELECT * FROM settings').fetchall()
    st.dataframe([dict(s) for s in settings_rows], use_container_width=True)

db.close()
