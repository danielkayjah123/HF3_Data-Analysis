from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text


def get_database_url() -> str:
    return os.getenv("DATABASE_URL") or "sqlite:///hf3_analysis.db"


def get_engine():
    return create_engine(get_database_url(), future=True)


def init_db() -> None:
    engine = get_engine()
    db_url = get_database_url().lower()
    id_def = "SERIAL PRIMARY KEY" if db_url.startswith("postgresql") else "INTEGER PRIMARY KEY AUTOINCREMENT"
    with engine.begin() as conn:
        conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS submissions (
            id {id_def},
            filename TEXT NOT NULL,
            reporting_period TEXT,
            facilities INTEGER,
            flags INTEGER,
            submitted_at TEXT NOT NULL
        )
        """))
        conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS helpdesk_issues (
            id {id_def},
            facility TEXT NOT NULL,
            reporting_period TEXT,
            issue_type TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT DEFAULT 'Open',
            created_at TEXT NOT NULL
        )
        """))


def save_submission(filename: str, period: str, facilities: int, flags: int) -> None:
    init_db()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO submissions(filename, reporting_period, facilities, flags, submitted_at)
            VALUES (:filename, :period, :facilities, :flags, :submitted_at)
        """), {
            "filename": filename,
            "period": period,
            "facilities": facilities,
            "flags": flags,
            "submitted_at": datetime.utcnow().isoformat(timespec="seconds"),
        })


def save_helpdesk_issue(facility: str, period: str, issue_type: str, description: str) -> None:
    init_db()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO helpdesk_issues(facility, reporting_period, issue_type, description, created_at)
            VALUES (:facility, :period, :issue_type, :description, :created_at)
        """), {
            "facility": facility,
            "period": period,
            "issue_type": issue_type,
            "description": description,
            "created_at": datetime.utcnow().isoformat(timespec="seconds"),
        })


def load_table(table_name: str) -> pd.DataFrame:
    init_db()
    engine = get_engine()
    try:
        return pd.read_sql_table(table_name, engine)
    except Exception:
        return pd.DataFrame()
