import streamlit as st
import sqlite3
import os
import datetime
import secrets
import string

# ----------------------------------------------------------------
# CONFIG & DATABASE SETUP (Audited from db.py & app.py)
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
    
    # Indexes from original db.py
    c.execute("CREATE INDEX IF NOT EXISTS idx_cases_login ON cases(login)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_cases_site ON cases(site)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status)")
    
    # Seed default admin if not exists (mnnafee)
    ex = c.execute("SELECT * FROM users WHERE alias='mnnafee'").fetchone()
    if not ex:
        t = secrets.token_hex(16)
        c.execute("INSERT OR REPLACE INTO users (alias, role, sites, added, token) VALUES ('mnnafee', 'Admin', 'All', ?, ?)", 
                  (str(datetime.date.today()), t))
    conn.commit()
    conn.close()

init_db()

# ----------------------------------------------------------------
# TOKEN AUTHENTICATION
# ----------------------------------------------------------------
if "token" not in st.session_state:
    st.session_state.token = ""

def get_user_by_token(token):
    if not token:
        return None
    db = get_db()
    row = db.execute('SELECT * FROM users WHERE token=?', (token,)).fetchone()
    db.close()
    return dict(row) if row else None

# Check Streamlit query params for token support
query_params = st.query_params
if "token" in query_params and not st.session_state.token:
    st.session_state.token = query_params["token"]

current_user = get_user_by_token(st.session_state.token)

# ----------------------------------------------------------------
# LOGIN / ACCESS GATE UI
# ----------------------------------------------------------------
if not current_user:
    st.title("🔐 WBC Portal - Authentication")
    st.markdown("Please enter your access token to continue.")
    
    input_token = st.text_input("Enter Token:", type="password")
    if st.button("Login"):
        user = get_user_by_token(input_token)
        if user:
            st.session_state.token = input_token
            st.success("Access granted!")
            st.rerun()
        else:
            st.error("Invalid token. Contact admin (mnnafee) for access.")
            
    with st.expander("Developer Quick Token Lookup"):
        admin_alias = st.text_input("Alias", value="mnnafee")
        if st.button("Fetch Token"):
            db = get_db()
            row = db.execute("SELECT token FROM users WHERE alias=?", (admin_alias,)).fetchone()
            db.close()
            if row:
                st.info(f"Token for {admin_alias}: `{row['token']}`")
    st.stop()

# ----------------------------------------------------------------
# STREAMLIT DASHBOARD (UI & LOGIC)
# ----------------------------------------------------------------
st.sidebar.title(f"👤 Welcome, {current_user['alias'].upper()}")
st.sidebar.markdown(f"**Role:** {current_user['role']} | **Sites:** {current_user['sites']}")

menu = st.sidebar.selectbox("Navigation", ["Cases Dashboard", "UA Offences", "UPL Summary", "User Management", "Settings"])

db = get_db()

if menu == "Cases Dashboard":
    st.header("📋 WBC Cases Dashboard")
    
    # Role-based query logic from original app.py
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
        st.info("No cases found matching your access permissions.")

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
        st.error("Admin permission required to view this section.")
    else:
        users = db.execute('SELECT alias, role, sites, added, token FROM users').fetchall()
        st.dataframe([dict(u) for u in users], use_container_width=True)
        
        with st.form("add_user_form"):
            st.subheader("Add New User / Regenerate Access")
            new_alias = st.text_input("User Alias").strip().lower()
            new_role = st.selectbox("Role", ["Admin", "VPOC", "PXT", "HRBP", "HRA"])
            new_sites = st.text_input("Sites (comma-separated or All)", value="All")
            submitted = st.form_submit_button("Save User")
            if submitted and new_alias:
                new_token = secrets.token_hex(16)
                try:
                    db.execute('INSERT OR REPLACE INTO users (alias, role, sites, added, token) VALUES (?, ?, ?, ?, ?)',
                               (new_alias, new_role, new_sites, str(datetime.date.today()), new_token))
                    db.commit()
                    st.success(f"User {new_alias} saved successfully! Token: `{new_token}`")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

elif menu == "Settings":
    st.header("⚙️ Application Settings")
    settings_rows = db.execute('SELECT * FROM settings').fetchall()
    st.dataframe([dict(s) for s in settings_rows], use_container_width=True)

db.close()
