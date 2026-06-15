from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
import yaml
import numpy as np


@dataclass
class AnalysisResult:
    cleaned_data: pd.DataFrame
    dashboard: pd.DataFrame
    indicator_summary: pd.DataFrame
    facility_analysis: pd.DataFrame
    data_quality_flags: pd.DataFrame
    top_facilities: pd.DataFrame
    missing_required_columns: List[str]
    period_name: str


def load_yaml(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def read_submitted_excel(uploaded_file) -> pd.DataFrame:
    """Read an uploaded Excel file. If it is an existing analysis workbook, use Raw Data."""
    xls = pd.ExcelFile(uploaded_file)
    target_sheet = "Raw Data" if "Raw Data" in xls.sheet_names else xls.sheet_names[0]
    return pd.read_excel(uploaded_file, sheet_name=target_sheet)


def _safe_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce").fillna(0)
    return pd.Series([0] * len(df), index=df.index, dtype="float64")


def _rate(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = pd.to_numeric(denominator, errors="coerce").replace(0, np.nan)
    numerator = pd.to_numeric(numerator, errors="coerce").fillna(0)
    return (numerator / denominator).astype("float64")


def clean_data(df: pd.DataFrame, rules: dict) -> Tuple[pd.DataFrame, List[str]]:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    required_id_columns = rules.get("required_id_columns", ["periodname", "organisationunitname"])
    missing_required_columns = [c for c in required_id_columns if c not in df.columns]

    for col in required_id_columns:
        if col not in df.columns:
            df[col] = "Unknown"
        df[col] = df[col].fillna("Unknown").astype(str).str.strip()

    numeric_cols = [c for c in df.columns if c not in required_id_columns]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        df.loc[df[col] < 0, col] = 0

    df = df.drop_duplicates(subset=required_id_columns, keep="last")
    return df, missing_required_columns


def build_indicator_summary(df: pd.DataFrame, rules: dict) -> pd.DataFrame:
    rows = []
    for label, col in rules.get("key_indicators", {}).items():
        total = _safe_col(df, col).sum()
        rows.append({
            "Indicator Key": label,
            "Indicator": col.replace("HF3_", ""),
            "Total": total,
            "Interpretation / Note": "National total across all facilities in the submitted dataset",
        })
    return pd.DataFrame(rows)


def build_facility_analysis(df: pd.DataFrame, rules: dict) -> pd.DataFrame:
    k = rules.get("key_indicators", {})
    period = df.get("periodname", pd.Series(["Unknown"] * len(df)))
    facility = df.get("organisationunitname", pd.Series(["Unknown"] * len(df)))

    numeric_cols = [c for c in df.columns if c not in ["periodname", "organisationunitname"]]
    out = pd.DataFrame({
        "Period": period,
        "Facility": facility,
        "Total reported values": df[numeric_cols].sum(axis=1) if numeric_cols else 0,
        "Normal deliveries": _safe_col(df, k.get("normal_delivery", "")),
        "Live births": _safe_col(df, k.get("live_births", "")),
        "Skilled births": _safe_col(df, k.get("skilled_births", "")),
        "CHO/CHT/Nurses/MCH deliveries": _safe_col(df, k.get("cho_cht_nurses_mch_deliveries", "")),
        "Breastfed within 1 hour": _safe_col(df, k.get("breastfed_1hr", "")),
        "Baby weighed within 1 hour": _safe_col(df, k.get("baby_weighed_1hr", "")),
        "ANC 1st contact facility": _safe_col(df, k.get("anc_1st_facility", "")),
        "ANC 1st contact outreach": _safe_col(df, k.get("anc_1st_outreach", "")),
        "LLIN at ANC facility": _safe_col(df, k.get("llin_anc_facility", "")),
        "HIV screened at ANC facility": _safe_col(df, k.get("hiv_screened_anc_facility", "")),
        "HepB screened at ANC facility": _safe_col(df, k.get("hep_b_screened_anc_facility", "")),
        "Syphilis screened at ANC facility": _safe_col(df, k.get("syphilis_screened_anc_facility", "")),
        "Stillbirths total": _safe_col(df, k.get("stillbirth_macerated", "")) + _safe_col(df, k.get("stillbirth_fresh", "")),
        "HIV cases": _safe_col(df, k.get("hiv_cases", "")),
    })

    out["Skilled birth attendance rate"] = _rate(out["Skilled births"], out["Live births"])
    out["Breastfed rate"] = _rate(out["Breastfed within 1 hour"], out["Live births"])
    out["Baby weighed rate"] = _rate(out["Baby weighed within 1 hour"], out["Live births"])
    out["LLIN coverage"] = _rate(out["LLIN at ANC facility"], out["ANC 1st contact facility"])
    out["HIV screening coverage"] = _rate(out["HIV screened at ANC facility"], out["ANC 1st contact facility"])
    out["HepB screening coverage"] = _rate(out["HepB screened at ANC facility"], out["ANC 1st contact facility"])
    out["Syphilis screening coverage"] = _rate(out["Syphilis screened at ANC facility"], out["ANC 1st contact facility"])
    return out


def build_quality_flags(df: pd.DataFrame, facility_analysis: pd.DataFrame, rules: dict) -> pd.DataFrame:
    k = rules.get("key_indicators", {})
    flags = []
    for idx, row in df.iterrows():
        period = row.get("periodname", "Unknown")
        facility = row.get("organisationunitname", "Unknown")

        total_reported = facility_analysis.loc[idx, "Total reported values"] if idx in facility_analysis.index else 0
        if total_reported == 0:
            flags.append({
                "Period": period,
                "Facility": facility,
                "Flag Category": "Completeness",
                "Issue": "No HF3 numeric data reported",
                "Reported Value": 0,
                "Expected / Comparator": 0,
                "Difference": 0,
                "Recommended Follow-up": "Follow up reporting completeness for this facility.",
            })

        for rule in rules.get("quality_rules", []):
            n_col = k.get(rule.get("numerator"), "")
            d_col = k.get(rule.get("denominator"), "")
            n_value = pd.to_numeric(row.get(n_col, 0), errors="coerce")
            d_value = pd.to_numeric(row.get(d_col, 0), errors="coerce")
            n_value = 0 if pd.isna(n_value) else n_value
            d_value = 0 if pd.isna(d_value) else d_value
            if n_value > d_value:
                flags.append({
                    "Period": period,
                    "Facility": facility,
                    "Flag Category": rule.get("category"),
                    "Issue": rule.get("issue"),
                    "Reported Value": n_value,
                    "Expected / Comparator": d_value,
                    "Difference": n_value - d_value,
                    "Recommended Follow-up": rule.get("follow_up"),
                })

    return pd.DataFrame(flags, columns=[
        "Period", "Facility", "Flag Category", "Issue", "Reported Value",
        "Expected / Comparator", "Difference", "Recommended Follow-up"
    ])


def build_dashboard(facility_analysis: pd.DataFrame, flags: pd.DataFrame, period_name: str) -> pd.DataFrame:
    facilities = len(facility_analysis)
    facilities_with_data = int((facility_analysis["Total reported values"] > 0).sum()) if facilities else 0
    no_data = facilities - facilities_with_data

    totals = {
        "Reporting period": period_name,
        "Facilities in dataset": facilities,
        "Facilities with reported data": facilities_with_data,
        "Facilities with no numeric data": no_data,
        "Normal deliveries": facility_analysis["Normal deliveries"].sum(),
        "Live births in facility": facility_analysis["Live births"].sum(),
        "ANC 1st contact in facility": facility_analysis["ANC 1st contact facility"].sum(),
        "HIV cases": facility_analysis["HIV cases"].sum(),
        "Data quality flags": len(flags),
    }
    rates = {
        "Skilled birth attendance rate": _divide(facility_analysis["Skilled births"].sum(), facility_analysis["Live births"].sum()),
        "Breastfed within 1 hour rate": _divide(facility_analysis["Breastfed within 1 hour"].sum(), facility_analysis["Live births"].sum()),
        "Baby weighed within 1 hour rate": _divide(facility_analysis["Baby weighed within 1 hour"].sum(), facility_analysis["Live births"].sum()),
        "LLIN at ANC coverage": _divide(facility_analysis["LLIN at ANC facility"].sum(), facility_analysis["ANC 1st contact facility"].sum()),
        "HIV screening coverage": _divide(facility_analysis["HIV screened at ANC facility"].sum(), facility_analysis["ANC 1st contact facility"].sum()),
        "HepB screening coverage": _divide(facility_analysis["HepB screened at ANC facility"].sum(), facility_analysis["ANC 1st contact facility"].sum()),
        "Syphilis screening coverage": _divide(facility_analysis["Syphilis screened at ANC facility"].sum(), facility_analysis["ANC 1st contact facility"].sum()),
    }
    rows = [{"Metric": k, "Value": v, "Type": "Count/Total"} for k, v in totals.items()]
    rows.extend({"Metric": k, "Value": v, "Type": "Rate"} for k, v in rates.items())
    return pd.DataFrame(rows)


def _divide(n: float, d: float) -> float | None:
    return None if d == 0 else n / d


def build_top_facilities(facility_analysis: pd.DataFrame) -> pd.DataFrame:
    blocks = []
    for metric in ["Live births", "ANC 1st contact facility", "HIV cases", "Data quality risk"]:
        if metric == "Data quality risk":
            continue
        temp = facility_analysis[["Period", "Facility", metric]].sort_values(metric, ascending=False).head(10)
        temp = temp.rename(columns={metric: "Value"})
        temp.insert(0, "Ranking Metric", metric)
        blocks.append(temp)
    return pd.concat(blocks, ignore_index=True) if blocks else pd.DataFrame()


def analyze_hf3(df: pd.DataFrame, rules_path: str | Path) -> AnalysisResult:
    rules = load_yaml(rules_path)
    cleaned, missing_required_columns = clean_data(df, rules)
    period_name = cleaned["periodname"].mode().iloc[0] if "periodname" in cleaned and not cleaned.empty else "Unknown"
    facility_analysis = build_facility_analysis(cleaned, rules)
    flags = build_quality_flags(cleaned, facility_analysis, rules)
    dashboard = build_dashboard(facility_analysis, flags, period_name)
    indicator_summary = build_indicator_summary(cleaned, rules)
    top_facilities = build_top_facilities(facility_analysis)
    return AnalysisResult(cleaned, dashboard, indicator_summary, facility_analysis, flags, top_facilities, missing_required_columns, period_name)


def export_excel_report(result: AnalysisResult) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        readme = pd.DataFrame({
            "Item": [
                "Report type", "Reporting period", "Facilities in dataset",
                "Facilities with reported data", "Data quality flags", "Generated by"
            ],
            "Value": [
                "Automated HF3 Data Analysis Report", result.period_name,
                len(result.facility_analysis),
                int((result.facility_analysis["Total reported values"] > 0).sum()),
                len(result.data_quality_flags),
                "HF3 Web Analysis System",
            ],
        })
        sheets = {
            "README": readme,
            "Dashboard": result.dashboard,
            "Indicator Summary": result.indicator_summary,
            "Facility Analysis": result.facility_analysis,
            "Data Quality Flags": result.data_quality_flags,
            "Top Facilities": result.top_facilities,
            "Raw Data": result.cleaned_data,
        }
        for name, data in sheets.items():
            data.to_excel(writer, sheet_name=name, index=False)
            worksheet = writer.sheets[name]
            workbook = writer.book
            header_format = workbook.add_format({
                "bold": True, "font_color": "white", "bg_color": "#0F766E",
                "border": 1, "text_wrap": True, "align": "center", "valign": "vcenter"
            })
            body_format = workbook.add_format({"border": 1})
            percent_format = workbook.add_format({"num_format": "0.0%", "border": 1})
            number_format = workbook.add_format({"num_format": "#,##0", "border": 1})
            for col_num, value in enumerate(data.columns):
                worksheet.write(0, col_num, value, header_format)
                width = min(max(len(str(value)) + 2, 12), 38)
                worksheet.set_column(col_num, col_num, width, body_format)
                if "rate" in str(value).lower() or "coverage" in str(value).lower():
                    worksheet.set_column(col_num, col_num, 18, percent_format)
                elif str(value).lower() in ["total", "value", "reported value", "difference", "expected / comparator"]:
                    worksheet.set_column(col_num, col_num, 16, number_format)
            worksheet.freeze_panes(1, 0)
            if len(data) > 0 and len(data.columns) > 0:
                worksheet.autofilter(0, 0, len(data), len(data.columns) - 1)
    return buffer.getvalue()
