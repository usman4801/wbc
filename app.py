import pandas as pd

def audit_pay_defects(schedule_path, shift_interval_path, dmd_path, tayseer_path, output_path="pay_defects_audit_report.xlsx"):
    # Load all files (supports .csv or .xlsx)
    def load_file(path):
        return pd.read_excel(path) if path.endswith(('.xlsx', '.xls')) else pd.read_csv(path)

    df_schedule = load_file(schedule_path)
    df_shift = load_file(shift_interval_path)
    df_dmd = load_file(dmd_path)
    df_tayseer = load_file(tayseer_path)

    # ---------------------------------------------------------
    # 1. Audit Schedule File
    # ---------------------------------------------------------
    # Expected columns: Associate_ID, Date, Working_Hours, Punch_Count
    schedule_defects = []

    for idx, row in df_schedule.iterrows():
        reasons = []
        # Check working hours (< 5 hours is incorrect)
        if pd.notna(row.get('Working_Hours')) and float(row['Working_Hours']) < 5.0:
            reasons.append("Working hours less than 5 hrs")
        
        # Check punch count (only 4 and 6 are valid)
        punch_cnt = row.get('Punch_Count')
        if pd.notna(punch_cnt) and int(punch_cnt) not in [4, 6]:
            reasons.append(f"Mispunch: {int(punch_cnt)} punches (expected 4 or 6)")

        if reasons:
            defect_row = row.to_dict()
            defect_row['Defect_Reason'] = "; ".join(reasons)
            schedule_defects.append(defect_row)

    df_schedule_defects = pd.DataFrame(schedule_defects)

    # ---------------------------------------------------------
    # 2. Audit Shift Interval vs DMD (Rest Day Mismatch)
    # ---------------------------------------------------------
    # Expected columns: Associate_ID, Date, Shift_Type (or Rest_Day flag)
    # Merging on Associate_ID and Date
    merged_shifts = pd.merge(
        df_dmd, 
        df_shift, 
        on=['Associate_ID', 'Date'], 
        suffixes=('_dmd', '_shift_interval'), 
        how='inner'
    )

    # Check where DMD indicates a rest day but shift interval doesn't match
    # Adjust 'Shift_Type' or status column name as per your exact files
    rest_day_mismatches = merged_shifts[
        (merged_shifts['Shift_Type_dmd'].astype(str).str.upper().str.contains("REST|OFF")) & 
        (merged_shifts['Shift_Type_shift_interval'].astype(str).str.upper() != merged_shifts['Shift_Type_dmd'].astype(str).str.upper())
    ].copy()

    if not rest_day_mismatches.empty:
        rest_day_mismatches['Defect_Reason'] = "Rest Day Mismatch: DMD shows Rest Day but Shift Interval does not match"

    # ---------------------------------------------------------
    # 3. Audit Tayseer File (Pending Leaves)
    # ---------------------------------------------------------
    # Expected columns: Associate_ID, Leave_Type, Approval_Status
    tayseer_pending = df_tayseer[
        df_tayseer['Approval_Status'].astype(str).str.upper().str.contains("PENDING")
    ].copy()

    if not tayseer_pending.empty:
        tayseer_pending['Defect_Reason'] = "Leave Approval Pending in Tayseer"

    # ---------------------------------------------------------
    # Export to Excel with separate tabs for easy actioning
    # ---------------------------------------------------------
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        if not df_schedule_defects.empty:
            df_schedule_defects.to_excel(writer, sheet_name='Schedule & Mispunch Defects', index=False)
        else:
            pd.DataFrame([{"Status": "No schedule defects found"}]).to_excel(writer, sheet_name='Schedule & Mispunch Defects', index=False)

        if not rest_day_mismatches.empty:
            rest_day_mismatches.to_excel(writer, sheet_name='Rest Day Mismatches', index=False)
        else:
            pd.DataFrame([{"Status": "All rest days match DMD"}]).to_excel(writer, sheet_name='Rest Day Mismatches', index=False)

        if not tayseer_pending.empty:
            tayseer_pending.to_excel(writer, sheet_name='Pending Tayseer Leaves', index=False)
        else:
            pd.DataFrame([{"Status": "No pending leaves found"}]).to_excel(writer, sheet_name='Pending Tayseer Leaves', index=False)

    print(f"Audit completed. Report saved to: {output_path}")

# Run the audit (replace with your file paths):
if __name__ == "__main__":
    audit_pay_defects(
        schedule_path="schedule.csv",
        shift_interval_path="shift_interval.csv",
        dmd_path="DMD.csv",
        tayseer_path="tayseer.csv"
    )
