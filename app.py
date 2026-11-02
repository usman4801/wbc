import streamlit as st
import pandas as pd
import numpy as np
import io

st.set_page_config(page_title="Pay Defects Master Auditor", layout="wide")

st.title("🛡️ Consolidated Pay Defects Auditor (Master Schedule)")
st.markdown("Upload all raw files to audit hours, mispunches, rest days, and pending leaves, compiling everything into the master schedule.")

# ---------------------------------------------------------
# Uploaders
# ---------------------------------------------------------
col1, col2 = st.columns(2)
with col1:
    f_sched = st.file_uploader("1. Schedule File (schedule file no 1.xlsx)", type=["xlsx", "csv"])
    f_rest = st.file_uploader("2. Rest Day / DMD File (Rest Day - Oct-26.xlsx)", type=["xlsx", "csv"])

with col2:
    f_tayseer = st.file_uploader("3. Tayseer File (Green Badge Leaves)", type=["xlsx", "csv"])
    f_bb = st.file_uploader("4. Blue Badge Leave File (Blue badge leave.xlsx)", type=["xlsx", "csv"])

def parse_tayseer(file):
    # Header is at row index 1 (second line)
    df = pd.read_excel(file, header=1) if file.name.endswith(('.xlsx', '.xls')) else pd.read_csv(file, header=1)
    return df

if st.button("🚀 Run Audit & Compile Master Schedule", type="primary"):
    if not (f_sched and f_rest and f_tayseer and f_bb):
        st.error("Please upload all 4 files.")
    else:
        with st.spinner("Processing large dataset... this may take a moment."):
            # 1. Load Files
            df_sched = pd.read_excel(f_sched) if f_sched.name.endswith(('.xlsx', '.xls')) else pd.read_csv(f_sched)
            df_rest = pd.read_excel(f_rest) if f_rest.name.endswith(('.xlsx', '.xls')) else pd.read_csv(f_rest)
            df_tayseer = parse_tayseer(f_tayseer)
            df_bb = pd.read_excel(f_bb) if f_bb.name.endswith(('.xlsx', '.xls')) else pd.read_csv(f_bb)

            # Standardize Schedule Dates
            df_sched['Shift_Date_Only'] = pd.to_datetime(df_sched['Shift Start Date Time'], errors='coerce').dt.date
            df_sched['Employee ID Clean'] = df_sched['Employee ID'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)

            # -----------------------------------------------------
            # A. Calculate Actual Hours & Punch Counts
            # -----------------------------------------------------
            punch_cols = [c for c in df_sched.columns if 'Punch IN Date Time' in c or 'Punch OUT Date Time' in c]
            
            # Ensure punch timestamps are datetime
            for c in punch_cols:
                df_sched[c] = pd.to_datetime(df_sched[c], errors='coerce')

            # Punch Count
            df_sched['Punch_Count'] = df_sched[punch_cols].notna().sum(axis=1)

            # Actual Worked Hours Calculation
            def calculate_punch_hours(row):
                total_sec = 0
                for i in range(1, 8):
                    cin = row.get(f'Punch IN Date Time {i}')
                    cout = row.get(f'Punch OUT Date Time {i}')
                    if pd.notna(cin) and pd.notna(cout):
                        diff = (cout - cin).total_seconds()
                        if diff > 0:
                            total_sec += diff
                return round(total_sec / 3600.0, 2)

            df_sched['Calculated_Worked_Hours'] = df_sched.apply(calculate_punch_hours, axis=1)

            # Audit Working Hours & Punches
            def audit_schedule_row(row):
                cnt = row['Punch_Count']
                hrs = row['Calculated_Worked_Hours']
                
                # Check punch mispunch (only 4 and 6 are valid, 0 is rest/unworked)
                if cnt == 0:
                    punch_status = "No Punches"
                elif cnt in [4, 6]:
                    punch_status = "OK"
                else:
                    punch_status = f"Defect: Mispunch ({cnt} punches)"

                # Check working hours (<5 hrs)
                if cnt > 0 and hrs < 5.0:
                    hrs_status = f"Defect: <5 hrs worked ({hrs}h)"
                else:
                    hrs_status = "OK"

                return punch_status, hrs_status

            results = df_sched.apply(audit_schedule_row, axis=1)
            df_sched['Audit_Punches'] = [r[0] for r in results]
            df_sched['Audit_Working_Hours'] = [r[1] for r in results]

            # -----------------------------------------------------
            # B. Audit Rest Days (Rest Day - Oct-26.xlsx)
            # -----------------------------------------------------
            df_rest['Date_Clean'] = pd.to_datetime(df_rest['Date'], errors='coerce').dt.date
            rest_mask = df_rest['Pay Modifier Names'].astype(str).str.contains("Rest Day", case=False, na=False)
            dmd_rest_pairs = set(zip(df_rest.loc[rest_mask, 'Employee Login'].astype(str).str.strip().str.lower(), df_rest.loc[rest_mask, 'Date_Clean']))

            # Flag if scheduled shift occurs on a confirmed DMD Rest Day
            def check_rest_sync(row):
                login = str(row.get('Employee Login', '')).strip().lower()
                dt
