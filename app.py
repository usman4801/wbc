import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Pay Defects Audit Tool", layout="wide")

st.title("🛡️ Pay Defects & Payroll Anomaly Auditor")
st.markdown("Upload your monthly payroll tracking files to flag schedule, punch, rest day, and leave defects before cutoff.")

# ---------------------------------------------------------
# File Uploaders
# ---------------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    f_schedule = st.file_uploader("1. Upload Schedule File (schedule.csv / .xlsx)", type=["csv", "xlsx", "xls"])
    f_shift = st.file_uploader("2. Upload Shift Interval File (shift_interval.csv / .xlsx)", type=["csv", "xlsx", "xls"])

with col2:
    f_dmd = st.file_uploader("3. Upload DMD File (DMD.csv / .xlsx)", type=["csv", "xlsx", "xls"])
    f_tayseer = st.file_uploader("4. Upload Tayseer File (tayseer.csv / .xlsx)", type=["csv", "xlsx", "xls"])

def load_file(uploaded_file):
    if uploaded_file.name.endswith(('.xlsx', '.xls')):
        return pd.read_excel(uploaded_file)
    return pd.read_csv(uploaded_file)

# Helper function to match column names case-insensitively
def find_col(df, options):
    for col in df.columns:
        clean = col.strip().lower().replace(" ", "_")
        for opt in options:
            if opt in clean:
                return col
    return None

# ---------------------------------------------------------
# Audit Processing
# ---------------------------------------------------------
if st.button("🚀 Run Audit", type="primary"):
    if not (f_schedule and f_shift and f_dmd and f_tayseer):
        st.error("Please upload all 4 files before running the audit.")
    else:
        try:
            df_schedule = load_file(f_schedule)
            df_shift = load_file(f_shift)
            df_dmd = load_file(f_dmd)
            df_tayseer = load_file(f_tayseer)

            # 1. Audit Schedule File (< 5 hours and punch != 4, 6)
            schedule_defects = []
            col_hrs = find_col(df_schedule, ["working_hour", "work_hour", "total_hour", "hours"])
            col_punches = find_col(df_schedule, ["punch", "total_punch", "punches"])

            for _, row in df_schedule.iterrows():
                reasons = []
                if col_hrs and pd.notna(row.get(col_hrs)):
                    try:
                        if float(row[col_hrs]) < 5.0:
                            reasons.append("Working hours less than 5 hrs")
                    except (ValueError, TypeError):
                        pass

                if col_punches and pd.notna(row.get(col_punches)):
                    try:
                        if int(row[col_punches]) not in [4, 6]:
                            reasons.append(f"Mispunch: {row[col_punches]} punches (expected 4 or 6)")
                    except (ValueError, TypeError):
                        pass

                if reasons:
                    defect_row = row.to_dict()
                    defect_row["Defect_Reason"] = "; ".join(reasons)
                    schedule_defects.append(defect_row)

            df_schedule_res = pd.DataFrame(schedule_defects)

            # 2. Audit Shift Interval vs DMD (Rest Day Mismatch)
            col_id_dmd = find_col(df_dmd, ["associate_id", "employee_id", "login", "id", "badge"])
            col_date_dmd = find_col(df_dmd, ["date", "shift_date", "day"])
            col_shift_dmd = find_col(df_dmd, ["shift", "rest", "schedule", "type"])

            col_id_shift = find_col(df_shift, ["associate_id", "employee_id", "login", "id", "badge"])
            col_date_shift = find_col(df_shift, ["date", "shift_date", "day"])
            col_shift_shift = find_col(df_shift, ["shift", "rest", "schedule", "type"])

            rest_day_mismatches = pd.DataFrame()
            if all([col_id_dmd, col_date_dmd, col_id_shift, col_date_shift, col_shift_dmd, col_shift_shift]):
                merged_shifts = pd.merge(
                    df_dmd,
                    df_shift,
                    left_on=[col_id_dmd, col_date_dmd],
                    right_on=[col_id_shift, col_date_shift],
                    suffixes=("_dmd", "_shift_interval"),
                    how="inner"
                )

                dmd_type = merged_shifts[f"{col_shift_dmd}_dmd"].astype(str).str.upper()
                shift_type = merged_shifts[f"{col_shift_shift}_shift_interval"].astype(str).str.upper()

                rest_day_mismatches = merged_shifts[
                    dmd_type.str.contains("REST|OFF") & (shift_type != dmd_type)
                ].copy()

                if not rest_day_mismatches.empty:
                    rest_day_mismatches["Defect_Reason"] = "Rest Day Mismatch: DMD is Rest Day, but Shift Interval differs"

            # 3. Audit Tayseer (Pending Leaves)
            col_status = find_col(df_tayseer, ["status", "approval", "leave_status", "state"])
            tayseer_pending = pd.DataFrame()
            if col_status:
                tayseer_pending = df_tayseer[
                    df_tayseer[col_status].astype(str).str.upper().str.contains("PENDING")
                ].copy()
                if not tayseer_pending.empty:
                    tayseer_pending["Defect_Reason"] = "Leave Approval Pending in Tayseer"

            # ---------------------------------------------------------
            # Display Results in Tabs
            # ---------------------------------------------------------
            st.success("Audit complete!")
            tab1, tab2, tab3 = st.tabs(["1. Schedule & Punches", "2. Rest Day Mismatches", "3. Pending Tayseer Leaves"])

            with tab1:
                st.subheader(f"Schedule & Punch Defects ({len(df_schedule_res)})")
                if not df_schedule_res.empty:
                    st.dataframe(df_schedule_res)
                else:
                    st.info("No hours (<5h) or punch count defects found.")

            with tab2:
                st.subheader(f"Rest Day Mismatches ({len(rest_day_mismatches)})")
                if not rest_day_mismatches.empty:
                    st.dataframe(rest_day_mismatches)
                else:
                    st.info("No Rest Day discrepancies found between DMD and Shift Interval.")

            with tab3:
                st.subheader(f"Pending Leaves in Tayseer ({len(tayseer_pending)})")
                if not tayseer_pending.empty:
                    st.dataframe(tayseer_pending)
                else:
                    st.info("No pending leaves found in Tayseer.")

            # Download Combined Report
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                (df_schedule_res if not df_schedule_res.empty else pd.DataFrame([{"Status": "Clean"}])).to_excel(writer, sheet_name="Schedule_Defects", index=False)
                (rest_day_mismatches if not rest_day_mismatches.empty else pd.DataFrame([{"Status": "Clean"}])).to_excel(writer, sheet_name="Rest_Day_Mismatches", index=False)
                (tayseer_pending if not tayseer_pending.empty else pd.DataFrame([{"Status": "Clean"}])).to_excel(writer, sheet_name="Pending_Leaves", index=False)

            st.download_button(
                label="📥 Download Full Excel Audit Report",
                data=output.getvalue(),
                file_name="payroll_defects_audit_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        except Exception as e:
            st.error(f"Error during processing: {e}")
