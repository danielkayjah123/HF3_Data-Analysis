from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from analysis_engine import analyze_hf3, export_excel_report, read_submitted_excel
from database import init_db, load_table, save_helpdesk_issue, save_submission

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
RULES_PATH = BASE_DIR / "config" / "indicator_rules.yaml"
APP_PASSWORD = os.getenv("APP_PASSWORD", "")

st.set_page_config(
    page_title="HF3 Data Analysis System",
    page_icon="🏥",
    layout="wide",
)


def require_login() -> bool:
    st.sidebar.header("User Access")
    if not APP_PASSWORD:
        st.sidebar.info("Login disabled. Set APP_PASSWORD in .env to enable access control.")
        return True
    password = st.sidebar.text_input("Password", type="password")
    if password == APP_PASSWORD:
        st.sidebar.success("Logged in")
        return True
    st.sidebar.warning("Enter password to continue.")
    return False


def format_rate(value):
    if pd.isna(value):
        return "N/A"
    return f"{value:.1%}"


def main():
    st.title("🏥 Automated HF3 Data Analysis System")
    st.caption("Upload HF3 reports, validate data, generate dashboards, export Excel analysis, and log help desk issues.")

    if not require_login():
        st.stop()

    init_db()
    menu = st.sidebar.radio(
        "Navigation",
        ["Upload & Analyze", "Submission History", "Help Desk"],
    )

    if menu == "Upload & Analyze":
        upload_and_analyze()
    elif menu == "Submission History":
        show_submission_history()
    else:
        show_helpdesk()


def upload_and_analyze():
    st.header("Upload HF3 Excel Report")
    uploaded_file = st.file_uploader("Choose an HF3 Excel file", type=["xlsx", "xls"])

    if uploaded_file is None:
        st.info("Upload a submitted HF3 file or an existing HF3 analysis workbook. The system will use the `Raw Data` sheet when available.")
        st.markdown("**Expected ID columns:** `periodname`, `organisationunitname`")
        return

    try:
        df = read_submitted_excel(uploaded_file)
        result = analyze_hf3(df, RULES_PATH)
        save_submission(uploaded_file.name, result.period_name, len(result.facility_analysis), len(result.data_quality_flags))
    except Exception as exc:
        st.error(f"Could not analyze this file: {exc}")
        st.stop()

    if result.missing_required_columns:
        st.warning("Missing required columns: " + ", ".join(result.missing_required_columns))

    st.success("Analysis completed.")

    kpi = result.dashboard.set_index("Metric")["Value"].to_dict()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Reporting period", str(kpi.get("Reporting period", result.period_name)))
    c2.metric("Facilities", int(kpi.get("Facilities in dataset", 0)))
    c3.metric("Reported data", int(kpi.get("Facilities with reported data", 0)))
    c4.metric("No numeric data", int(kpi.get("Facilities with no numeric data", 0)))
    c5.metric("DQ flags", int(kpi.get("Data quality flags", 0)))

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("LLIN coverage", format_rate(kpi.get("LLIN at ANC coverage")))
    r2.metric("HIV screening", format_rate(kpi.get("HIV screening coverage")))
    r3.metric("HepB screening", format_rate(kpi.get("HepB screening coverage")))
    r4.metric("Syphilis screening", format_rate(kpi.get("Syphilis screening coverage")))

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Dashboard", "Indicator Summary", "Facility Analysis", "Data Quality Flags", "Export"
    ])

    with tab1:
        st.subheader("National Indicator Totals")
        chart_data = result.indicator_summary.sort_values("Total", ascending=False).head(15)
        fig = px.bar(chart_data, x="Indicator", y="Total", title="Top HF3 Indicator Totals")
        fig.update_layout(xaxis_tickangle=-35)
        st.plotly_chart(fig, use_container_width=True)

        if not result.data_quality_flags.empty:
            flag_counts = result.data_quality_flags["Flag Category"].value_counts().reset_index()
            flag_counts.columns = ["Flag Category", "Count"]
            fig2 = px.bar(flag_counts, x="Flag Category", y="Count", title="Data Quality Flags by Category")
            st.plotly_chart(fig2, use_container_width=True)

    with tab2:
        st.dataframe(result.indicator_summary, use_container_width=True)

    with tab3:
        st.dataframe(result.facility_analysis, use_container_width=True)
        st.download_button(
            "Download Facility Analysis CSV",
            result.facility_analysis.to_csv(index=False).encode("utf-8"),
            file_name="facility_analysis.csv",
            mime="text/csv",
        )

    with tab4:
        if result.data_quality_flags.empty:
            st.success("No data quality flags found.")
        else:
            st.dataframe(result.data_quality_flags, use_container_width=True)
            st.download_button(
                "Download Data Quality Flags CSV",
                result.data_quality_flags.to_csv(index=False).encode("utf-8"),
                file_name="data_quality_flags.csv",
                mime="text/csv",
            )

    with tab5:
        excel_bytes = export_excel_report(result)
        st.download_button(
            "Download Full Excel Analysis Report",
            excel_bytes,
            file_name=f"HF3_Automated_Analysis_{result.period_name.replace(' ', '_')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.write("The exported workbook includes README, Dashboard, Indicator Summary, Facility Analysis, Data Quality Flags, Top Facilities, and Raw Data sheets.")


def show_submission_history():
    st.header("Submission History")
    data = load_table("submissions")
    if data.empty:
        st.info("No submissions recorded yet.")
    else:
        st.dataframe(data.sort_values("submitted_at", ascending=False), use_container_width=True)


def show_helpdesk():
    st.header("Help Desk")
    st.write("Facilities can report data submission, missing indicator, or correction issues here.")
    with st.form("helpdesk_form"):
        facility = st.text_input("Facility name")
        period = st.text_input("Reporting period", placeholder="Example: April 2026")
        issue_type = st.selectbox("Issue type", [
            "Upload problem", "Missing data", "Wrong value", "Duplicate record", "Facility name issue", "Other"
        ])
        description = st.text_area("Describe the issue")
        submitted = st.form_submit_button("Submit Help Desk Issue")
        if submitted:
            if not facility or not description:
                st.error("Facility name and description are required.")
            else:
                save_helpdesk_issue(facility, period, issue_type, description)
                st.success("Help desk issue submitted.")

    st.subheader("Open Help Desk Log")
    issues = load_table("helpdesk_issues")
    if issues.empty:
        st.info("No help desk issues yet.")
    else:
        st.dataframe(issues.sort_values("created_at", ascending=False), use_container_width=True)


if __name__ == "__main__":
    main()
