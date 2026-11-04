"""Consolidated Pay Defects Auditor - single-file Streamlit app.

Run:  streamlit run app.py
Needs: streamlit, pandas, numpy, openpyxl
"""
import io

import numpy as np
import pandas as pd
import streamlit as st

MAX_PUNCH_PAIRS = 7
MIN_HOURS = 5.0
VALID_PUNCH_COUNTS = (4, 6)


# ----------------------------------------------------------------------------
# File helpers
# ----------------------------------------------------------------------------
def read_any(file, header=0):
    """Read an uploaded xlsx/xls/csv file into a DataFrame."""
    name = file.name.lower()
    if name.endswith((".xlsx", ".xls", ".xlsm")):
        return pd.read_excel(file, header=header)
    return pd.read_csv(file, header=header)


def parse_tayseer(file):
    """Tayseer export has its header on the second line (row index 1)."""
    return read_any(file, header=1)


def find_col(df, *candidates):
    """Find a column whose lower-cased name contains ALL words of any candidate.

    Each candidate is a tuple of words, e.g. ("employee", "id"). Candidates are
    tried in order. Returns the column name or None.
    """
    cols = {c: str(c).strip().lower() for c in df.columns}
    for cand in candidates:
        words = [cand] if isinstance(cand, str) else list(cand)
        for original, low in cols.items():
            if all(w in low for w in words):
                return original
    return None


def clean_id(series):
    return (
        series.astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.lower()
    )


# ----------------------------------------------------------------------------
# A. Hours and punches
# ----------------------------------------------------------------------------
def audit_hours_and_punches(df):
    df = df.copy()

    df["Shift_Date_Only"] = pd.to_datetime(
        df["Shift Start Date Time"], errors="coerce"
    ).dt.date
    df["Employee ID Clean"] = clean_id(df["Employee ID"])

    punch_cols = [
        c for c in df.columns
        if "Punch IN Date Time" in str(c) or "Punch OUT Date Time" in str(c)
    ]
    for c in punch_cols:
        df[c] = pd.to_datetime(df[c], errors="coerce")

    df["Punch_Count"] = df[punch_cols].notna().sum(axis=1) if punch_cols else 0

    total_sec = pd.Series(0.0, index=df.index)
    for i in range(1, MAX_PUNCH_PAIRS + 1):
        cin, cout = f"Punch IN Date Time {i}", f"Punch OUT Date Time {i}"
        if cin in df.columns and cout in df.columns:
            diff = (df[cout] - df[cin]).dt.total_seconds()
            total_sec += diff.where(diff > 0, 0).fillna(0)
    df["Calculated_Worked_Hours"] = (total_sec / 3600.0).round(2)

    cnt, hrs = df["Punch_Count"], df["Calculated_Worked_Hours"]

    df["Audit_Punches"] = np.select(
        [cnt == 0, cnt.isin(VALID_PUNCH_COUNTS)],
        ["No Punches", "OK"],
        default="Defect",
    )
    mis = df["Audit_Punches"] == "Defect"
    df.loc[mis, "Audit_Punches"] = (
        "Defect: Mispunch (" + cnt[mis].astype(int).astype(str) + " punches)"
    )

    low = (cnt > 0) & (hrs < MIN_HOURS)
    df["Audit_Working_Hours"] = "OK"
    df.loc[low, "Audit_Working_Hours"] = (
        "Defect: <5 hrs worked (" + hrs[low].astype(str) + "h)"
    )
    return df


# ----------------------------------------------------------------------------
# B. Rest days (DMD)
# ----------------------------------------------------------------------------
def audit_rest_days(df, df_rest):
    df = df.copy()
    df["Audit_Rest_Day"] = "OK"

    pm_col = find_col(df_rest, ("pay", "modifier"))
    date_col = find_col(df_rest, ("date",))
    if pm_col is None or date_col is None:
        df["Audit_Rest_Day"] = "Skipped: Rest Day file columns not found"
        return df

    # Match on login when both files have it, otherwise fall back to employee ID
    login_r = find_col(df_rest, ("employee", "login"), ("login",))
    login_s = find_col(df, ("employee", "login"), ("login",))
    id_r = find_col(df_rest, ("employee", "id"), ("emp", "id"))

    if login_r and login_s:
        key_r, key_s = clean_id(df_rest[login_r]), clean_id(df[login_s])
    elif id_r:
        key_r, key_s = clean_id(df_rest[id_r]), df["Employee ID Clean"].str.lower()
    else:
        df["Audit_Rest_Day"] = "Skipped: no common employee key"
        return df

    r_dates = pd.to_datetime(df_rest[date_col], errors="coerce").dt.date
    mask = df_rest[pm_col].astype(str).str.contains("Rest Day", case=False, na=False)
    pairs = set(zip(key_r[mask], r_dates[mask]))

    hit = [(k, d) in pairs for k, d in zip(key_s, df["Shift_Date_Only"])]
    df.loc[hit, "Audit_Rest_Day"] = "Defect: Scheduled on DMD Rest Day"
    return df


# ----------------------------------------------------------------------------
# C. Pending leaves (Tayseer = green badge, Blue badge)
# ----------------------------------------------------------------------------
def _leave_intervals(df_leave):
    """Return {employee_id: [(start, end), ...]} for pending leaves."""
    id_col = find_col(
        df_leave, ("employee", "id"), ("emp", "id"), ("badge", "id"),
        ("employee", "login"), ("login",), ("employee",), ("id",),
    )
    start_col = find_col(
        df_leave, ("start", "date"), ("from", "date"), ("start",), ("from",), ("date",)
    )
    end_col = find_col(df_leave, ("end", "date"), ("to", "date"), ("end",), ("to",))
    status_col = find_col(df_leave, ("status",), ("state",))

    if id_col is None or start_col is None:
        return None

    d = pd.DataFrame({
        "id": clean_id(df_leave[id_col]),
        "start": pd.to_datetime(df_leave[start_col], errors="coerce").dt.date,
    })
    d["end"] = (
        pd.to_datetime(df_leave[end_col], errors="coerce").dt.date
        if end_col else d["start"]
    )
    d["end"] = d["end"].fillna(d["start"])

    if status_col:
        st_txt = df_leave[status_col].astype(str)
        d = d[st_txt.str.contains(r"pend|submit|await|wait", case=False, na=False)]
    d = d.dropna(subset=["start"])

    out = {}
    for emp, s, e in zip(d["id"], d["start"], d["end"]):
        out.setdefault(emp, []).append((s, e))
    return out


def audit_pending_leaves(df, df_leave, label):
    df = df.copy()
    col = f"Audit_Pending_{label}_Leave"
    intervals = _leave_intervals(df_leave)
    if intervals is None:
        df[col] = f"Skipped: {label} file columns not found"
        return df

    ids = df["Employee ID Clean"].str.lower()
    res = []
    for emp, day in zip(ids, df["Shift_Date_Only"]):
        hit = any(s <= day <= e for s, e in intervals.get(emp, [])) if pd.notna(day) else False
        res.append(f"Defect: Pending {label} leave" if hit else "OK")
    df[col] = res
    return df


# ----------------------------------------------------------------------------
# Master schedule
# ----------------------------------------------------------------------------
def compile_master(df_sched, df_rest, df_tayseer, df_bb):
    df = audit_hours_and_punches(df_sched)
    df = audit_rest_days(df, df_rest)
    df = audit_pending_leaves(df, df_tayseer, "Green")
    df = audit_pending_leaves(df, df_bb, "Blue")

    audit_cols = [
        "Audit_Punches", "Audit_Working_Hours", "Audit_Rest_Day",
        "Audit_Pending_Green_Leave", "Audit_Pending_Blue_Leave",
    ]
    df["Defect_Count"] = sum(
        df[c].astype(str).str.startswith("Defect").astype(int) for c in audit_cols
    )
    df["Overall_Status"] = np.where(df["Defect_Count"] > 0, "DEFECT", "OK")
    return df, audit_cols


def summarize(df, audit_cols):
    rows = [("Total schedule rows", len(df))]
    labels = {
        "Audit_Punches": "Mispunches",
        "Audit_Working_Hours": "Under 5 hrs worked",
        "Audit_Rest_Day": "Scheduled on rest day",
        "Audit_Pending_Green_Leave": "Pending green badge leaves",
        "Audit_Pending_Blue_Leave": "Pending blue badge leaves",
    }
    for c in audit_cols:
        rows.append((labels[c], int(df[c].astype(str).str.startswith("Defect").sum())))
    rows.append(("Rows with any defect", int((df["Overall_Status"] == "DEFECT").sum())))
    return pd.DataFrame(rows, columns=["Check", "Count"])


def to_excel_bytes(df, summary):
    """Master schedule workbook: Master, Defects Only, Summary."""
    buf = io.BytesIO()
    out = df.copy()
    # Excel cannot store timezone-aware datetimes
    for c in out.columns:
        if isinstance(out[c].dtype, pd.DatetimeTZDtype):
            out[c] = out[c].dt.tz_localize(None)
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        out.to_excel(xw, sheet_name="Master Schedule", index=False)
        out[out["Overall_Status"] == "DEFECT"].to_excel(
            xw, sheet_name="Defects Only", index=False
        )
        summary.to_excel(xw, sheet_name="Summary", index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "A2"
            for col in ws.columns:
                width = max(len(str(col[0].value or "")), 10) + 2
                ws.column_dimensions[col[0].column_letter].width = min(width, 40)
    return buf.getvalue()



st.set_page_config(
    page_title="Consolidated Pay Defects Auditor",
    page_icon="🛡️",
    layout="wide",
)

# ----------------------------------------------------------------------------
# Styling (matches the reference dashboard)
# ----------------------------------------------------------------------------
CSS = """
<style>
.stApp {
    background:
        radial-gradient(circle at 0% 0%, #e6dffb 0, transparent 22%),
        radial-gradient(circle at 100% 100%, #cfe5fb 0, transparent 24%),
        #f6f8fe;
}
#MainMenu, footer, header[data-testid="stHeader"] {visibility: hidden;}
.block-container {max-width: 1250px; padding-top: 2rem; padding-bottom: 3rem;}

/* ---------- Header ---------- */
.hero {display:flex; align-items:center; gap:28px; padding:6px 0 18px 0;}
.hero svg {flex:none;}
.hero .divider {width:2px; height:92px; background:#cfc8ee;}
.hero h1 {margin:0; font-size:2.6rem; font-weight:800; color:#1b1f5e; letter-spacing:-0.5px;}
.hero p {margin:6px 0 0 0; font-size:1.2rem; color:#6d7498;}

/* ---------- Upload cards ---------- */
[class*="st-key-card"] {
    background:#ffffff; border-radius:22px; padding:22px 24px 24px 24px;
    box-shadow:0 8px 30px rgba(70,70,150,.08);
}
.card-head {display:flex; align-items:center; gap:18px; margin-bottom:14px;}
.num {width:48px; height:48px; border-radius:50%; color:#fff; font-weight:800;
      font-size:1.35rem; display:flex; align-items:center; justify-content:center; flex:none;}
.icon {width:82px; height:82px; border-radius:50%; display:flex; align-items:center;
       justify-content:center; font-size:2.3rem; flex:none;}
.card-title {font-size:1.45rem; font-weight:800; color:#1b1f5e; line-height:1.15;}
.card-sub {font-size:1.05rem; color:#7a80a3; margin-top:4px;}

[class*="st-key-card"] [data-testid="stFileUploaderDropzone"] {
    border-radius:16px; border-width:2px; border-style:dashed; padding:18px 20px;
}
[class*="st-key-card"] [data-testid="stFileUploaderDropzone"] button {
    border:none; border-radius:999px; font-weight:700; padding:.55rem 1.8rem;
}
[class*="st-key-card"] [data-testid="stFileUploaderDropzoneInstructions"] small {color:#7a80a3;}

/* colour themes */
.st-key-card1 {background:#ffffff;}
.st-key-card1 [data-testid="stFileUploaderDropzone"] {background:#f6f2ff; border-color:#a68cf0;}
.st-key-card1 [data-testid="stFileUploaderDropzone"] button {background:#e6dcff; color:#4b21c9;}
.st-key-card2 [data-testid="stFileUploaderDropzone"] {background:#effbf8; border-color:#33c4ae;}
.st-key-card2 [data-testid="stFileUploaderDropzone"] button {background:#cdf3ec; color:#0b8c78;}
.st-key-card3 {background:#fffaf5;}
.st-key-card3 [data-testid="stFileUploaderDropzone"] {background:#fff6ee; border-color:#f4a45c;}
.st-key-card3 [data-testid="stFileUploaderDropzone"] button {background:#ffe1c8; color:#e8661a;}
.st-key-card4 [data-testid="stFileUploaderDropzone"] {background:#f1f7ff; border-color:#6cb0f5;}
.st-key-card4 [data-testid="stFileUploaderDropzone"] button {background:#d8e8fd; color:#1769d6;}

/* ---------- Run button ---------- */
div.stButton > button[kind="primary"] {
    background:linear-gradient(90deg,#8a3ffc 0%,#2f5bea 100%); border:none; color:#fff;
    font-size:1.25rem; font-weight:700; border-radius:999px; padding:.85rem 2.5rem;
    box-shadow:0 10px 26px rgba(80,70,220,.35); transition:transform .15s;
}
div.stButton > button[kind="primary"]:hover {transform:translateY(-2px); color:#fff;}

/* ---------- Help pill ---------- */
[data-testid="stPopover"] > div > button {
    border-radius:999px; border:1px solid #dcd6f5; background:#fff; color:#4b21c9;
    font-weight:700; padding:.5rem 1.4rem; box-shadow:0 4px 14px rgba(90,70,200,.10);
}

/* ---------- Metrics ---------- */
[data-testid="stMetric"] {
    background:#fff; border-radius:16px; padding:14px 18px;
    box-shadow:0 6px 20px rgba(70,70,150,.07);
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

SHIELD_SVG = """
<svg width="130" height="130" viewBox="0 0 130 130" xmlns="http://www.w3.org/2000/svg">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#7c3aed"/><stop offset="1" stop-color="#4338ca"/></linearGradient></defs>
  <path d="M65 8 L108 24 V60 C108 88 90 108 65 120 C40 108 22 88 22 60 V24 Z" fill="url(#g)"/>
  <path d="M44 62 L59 77 L88 46" fill="none" stroke="#fff" stroke-width="10"
        stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M10 40 l12 6 M6 58 h14 M12 76 l12 -6" stroke="#6d4cf0" stroke-width="5"
        stroke-linecap="round"/>
</svg>
"""

# ----------------------------------------------------------------------------
# Header
# ----------------------------------------------------------------------------
left, right = st.columns([6, 1])
with left:
    st.markdown(
        f"""
        <div class="hero">
          {SHIELD_SVG}
          <div class="divider"></div>
          <div>
            <h1>Consolidated Pay Defects Auditor</h1>
            <p>Upload your files to audit hours, mispunches, rest days and more.</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with right:
    with st.popover("❓ Help"):
        st.markdown(
            """
**How it works**
1. Upload the 4 files (XLSX or CSV).
2. Click **Run Audit & Compile Master Schedule**.
3. Review the summary and download the master workbook.

**Checks performed**
- Valid punch count (only 4 or 6 punches are OK)
- Worked hours under 5 hrs
- Shift scheduled on a DMD rest day
- Pending green badge (Tayseer) leaves
- Pending blue badge leaves
            """
        )


# ----------------------------------------------------------------------------
# Upload cards
# ----------------------------------------------------------------------------
def card(key, number, color, icon_bg, icon, title, subtitle, uploader_label):
    with st.container(key=key):
        st.markdown(
            f"""
            <div class="card-head">
              <div class="num" style="background:{color}">{number}</div>
              <div class="icon" style="background:{icon_bg}">{icon}</div>
              <div>
                <div class="card-title">{title}</div>
                <div class="card-sub">{subtitle}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return st.file_uploader(
            uploader_label, type=["xlsx", "xls", "csv"],
            key=f"up_{key}", label_visibility="collapsed",
        )


col1, col2 = st.columns(2, gap="large")
with col1:
    f_sched = card("card1", 1, "#7c3aed", "#ece6fb", "📅",
                   "Schedule File", "(schedule file no 1.xlsx)", "Schedule file")
with col2:
    f_rest = card("card2", 2, "#14b8a6", "#d9f5f0", "🛏️",
                  "Rest Day / DMD File", "(Rest Day - Oct-26.xlsx)", "Rest day file")

col3, col4 = st.columns(2, gap="large")
with col3:
    f_tayseer = card("card3", 3, "#f97316", "#ffe9d6", "🛡️",
                     "Tayseer File", "(Green Badge Leaves)", "Tayseer file")
with col4:
    f_bb = card("card4", 4, "#2563eb", "#dbe8fd", "🏅",
                "Blue Badge Leave File", "(Blue badge leave.xlsx)", "Blue badge file")

st.write("")
_, mid, _ = st.columns([1.2, 1.6, 1.2])
with mid:
    run = st.button("🚀  Run Audit & Compile Master Schedule  →",
                    type="primary", use_container_width=True)

# ----------------------------------------------------------------------------
# Run
# ----------------------------------------------------------------------------
if run:
    if not (f_sched and f_rest and f_tayseer and f_bb):
        st.error("Please upload all 4 files.")
    else:
        try:
            with st.spinner("Processing large dataset... this may take a moment."):
                df_sched = read_any(f_sched)
                df_rest = read_any(f_rest)
                df_tayseer = parse_tayseer(f_tayseer)
                df_bb = read_any(f_bb)

                missing = [c for c in ("Shift Start Date Time", "Employee ID")
                           if c not in df_sched.columns]
                if missing:
                    st.error(f"Schedule file is missing required column(s): {', '.join(missing)}")
                    st.stop()

                master, audit_cols = compile_master(
                    df_sched, df_rest, df_tayseer, df_bb
                )
                summary = summarize(master, audit_cols)
                st.session_state["master"] = master
                st.session_state["summary"] = summary
                st.session_state["xlsx"] = to_excel_bytes(master, summary)
        except Exception as e:  # show a readable error instead of a crash
            st.error(f"Audit failed: {e}")
            st.stop()

# ----------------------------------------------------------------------------
# Results
# ----------------------------------------------------------------------------
if "master" in st.session_state:
    master = st.session_state["master"]
    summary = st.session_state["summary"]

    st.success("Audit complete. Master schedule compiled.")

    metric_cols = st.columns(len(summary))
    for mc, (_, r) in zip(metric_cols, summary.iterrows()):
        mc.metric(r["Check"], f"{r['Count']:,}")

    st.download_button(
        "⬇️ Download Master Schedule (Excel)",
        data=st.session_state["xlsx"],
        file_name="Master_Schedule_Audit.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="secondary",
    )

    tab_all, tab_def = st.tabs(["Master Schedule", "Defects Only"])
    with tab_all:
        st.dataframe(master, use_container_width=True, height=450)
    with tab_def:
        st.dataframe(master[master["Overall_Status"] == "DEFECT"],
                     use_container_width=True, height=450)
