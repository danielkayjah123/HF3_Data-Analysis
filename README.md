# Automated HF3 Data Analysis System

A web-based Streamlit application for Ministry of Health HF3 data analysis. It uploads HF3 Excel reports, cleans data, calculates indicators, detects data quality issues, displays dashboards, exports Excel reports, stores submission logs, and includes a help desk issue form.

## Main Features

- Excel upload interface
- Automatic reading of raw HF3 data
- Data cleaning with Pandas
- YAML-based indicator and quality-rule configuration
- Automated indicator totals and facility-level analysis
- Data quality flags for inconsistent values
- Web dashboard with charts and KPI cards
- Excel report export
- Database logging using PostgreSQL or local SQLite fallback
- Simple password login using `APP_PASSWORD`
- Help desk issue submission form

## Project Structure

```text
hf3_web_analysis_system/
├── app.py
├── analysis_engine.py
├── database.py
├── requirements.txt
├── .env.example
├── Dockerfile
├── config/
│   ├── indicator_rules.yaml
│   └── updated_sierra_leone.yaml
├── sample_data/
│   └── HF3_April_2026_Data_Analysis_Report.xlsx
└── output/
```

## Run Locally

1. Create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate      # Mac/Linux
# .venv\Scripts\activate       # Windows
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create your environment file:

```bash
cp .env.example .env
```

4. Start the web app:

```bash
streamlit run app.py
```

5. Open the local web link shown by Streamlit, usually:

```text
http://localhost:8501
```

## Database Setup

The app works locally even without PostgreSQL. If `DATABASE_URL` is empty, it uses SQLite.

For PostgreSQL, create a database and set `DATABASE_URL` in `.env`:

```text
DATABASE_URL=postgresql+psycopg2://username:password@localhost:5432/hf3_analysis
APP_PASSWORD=your_secure_password
```

## Deploy Online

### Option 1: Streamlit Community Cloud

1. Upload this project to GitHub.
2. Go to Streamlit Community Cloud.
3. Create a new app from your GitHub repository.
4. Set the main file path to:

```text
app.py
```

5. Add secrets for:

```text
APP_PASSWORD="your_secure_password"
DATABASE_URL="postgresql+psycopg2://..."
```

### Option 2: Render / Railway / Heroku-style hosting

Use the included `Dockerfile` and set these environment variables:

```text
APP_PASSWORD=your_secure_password
DATABASE_URL=postgresql+psycopg2://username:password@host:5432/dbname
```

## How to Update Indicators and Rules

Edit:

```text
config/indicator_rules.yaml
```

Add new HF3 indicators under `key_indicators`, then add validation rules under `quality_rules`.

Example rule:

```yaml
- category: ANC/LLIN
  numerator: llin_anc_facility
  denominator: anc_1st_facility
  issue: LLIN given in facility exceeds ANC 1st contact in facility
  follow_up: Verify ANC register and LLIN distribution record.
```

## Recommended Next Upgrades

- Role-based login for national, district, and facility users
- District and chiefdom filters
- Automated email feedback to facilities
- DHIS2 API import instead of manual Excel upload
- Power BI connection to PostgreSQL
- Scheduled monthly data quality reports
