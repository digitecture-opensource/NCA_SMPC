# NCA SmPC & Orphan Designation Portal

An open-source reference implementation for **National Competent Authorities (NCAs)** to digitise their SmPC (Summary of Product Characteristics) libraries and manage Orphan Designation workflows — aligned to IDMP standards and deployable on any NCA's infrastructure.

The baseline dataset used here is sourced from **MHRA's public product portal**. Because the SmPC structure follows the globally agreed EU SmPC template, the same codebase can be adapted by **any NCA worldwide** with minimal changes.

Originally developed by [Digitecture Ltd](https://www.digitecture.co.uk). Contributions from the NCA community are welcome.

---

## Repository Structure

```
.
├── SMPC Digitization/          # ETL pipeline — converts SmPC PDFs into structured database records
├── Front end/                  # Django web application — surfaces digitised data as a public portal
├── config/                     # Django project settings, URL routing, DB backend
├── manage.py                   # Django management entry point
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Container definition for deployment
├── docker/                     # Docker Compose and deployment configuration
├── .env.example                # Template for environment variables (copy to .env)
└── .gitignore
```

---

## SMPC Digitization (`/SMPC Digitization`)

Python scripts that form an **ETL pipeline** to convert an NCA's existing SmPC PDF library into a structured, queryable database. The pipeline is designed to run once to populate the database, and again whenever new or revised SmPCs are published.

### Pipeline steps

| Script | Step | What it does |
|---|---|---|
| `run_pipeline.py` | Orchestrator | Reads `SMPC_STEPS` from `.env` and runs the selected steps in order |
| `Step_01_RIM_CV_setup.py` | Step 01 | Loads controlled vocabulary (codelists and terms) into the RIM schema |
| `PDF_extractor.py` | — | Extracts raw text from SmPC PDFs using PyMuPDF; maps content to standard SmPC section headings |
| `Step_10_Substance_map.py` | Step 10 | Uses OpenAI to match active substances in SmPCs to EMA SPOR substance records |
| `Step_20_Fetch_MP_MA.py` | Step 20 | Fetches Marketing Authorisation and Medicinal Product data from the NCA's source system |
| `Step_30_load_MHRA_orphan_register.py` | Step 30 | Loads the Orphan Designation register (current + expired) from CSV into the database |
| `SMPC_Meta_dataload.py` | — | Loads SmPC metadata (file paths, revision dates) |
| `Populate_SMPC_Substance.py` | — | Populates the substance-to-SmPC mapping table |
| `WebScrapperMHRAproduct portal.py` | — | Scrapes/downloads SmPC source files from the NCA product portal |

### Running the pipeline

```bash
cd "SMPC Digitization"
cp ../.env.example ../.env   # fill in your credentials
python run_pipeline.py
```

To run specific steps only, set `SMPC_STEPS=10,20` in your `.env`.

### Adapting for a different NCA

- Replace the web scraper with one that targets your NCA's product portal
- The PDF extraction logic targets standard EU SmPC section headings — these are consistent across all NCAs that follow the EMA guideline
- Update the `MHRA_ORPHAN_DIR` path and CSV column mappings in Step 30 to match your Orphan Designation register format

---

## Front End (`/Front end` and `/config`)

A **Django web application** that surfaces the digitised SmPC and Orphan Designation data as a searchable public portal, with built-in user authentication for restricted workflows.

### Key files

| File | What it does |
|---|---|
| `Front end/views.py` | URL handler functions — one per page/API endpoint |
| `Front end/services.py` | All database queries (read-only SELECT statements via SQLAlchemy) |
| `Front end/templates/orphan/` | HTML templates for each page |
| `Front end/middleware.py` | Login-required middleware for protected routes |
| `Front end/urls.py` | URL routing for the application |
| `config/settings.py` | Django settings — all secrets loaded from `.env` |
| `config/db_backends/` | Custom Django DB backend for Azure SQL with Entra token auth |

### Pages & routes

| URL | Auth required | Description |
|---|---|---|
| `/` | No | Home page — project overview and navigation |
| `/smpc/` | No | Searchable SmPC listing |
| `/smpc/<id>/` | No | Full SmPC detail with EMA substance matching and FDA cross-reference |
| `/smpc/<id1>/compare/<id2>/` | No | Side-by-side word-level diff of two SmPCs |
| `/idmp/product-master/` | No | IDMP-aligned product master (MA → MP → Administrable Product hierarchy) |
| `/orphan/` | No | Orphan Designation listing with filters |
| `/orphan/<id>/` | No | Orphan Designation detail with linked IDMP and SmPC data |
| `/od/apply/` | Yes | Orphan Designation application form (placeholder — persistence not yet wired) |
| `/login/` | — | Login page |

### Running locally

```bash
pip install -r requirements.txt
cp .env.example .env          # fill in your database credentials
python manage.py runserver
```

### Running with Docker

```bash
docker compose -f docker/docker-compose.yml up
```

---

## Database Schema

The application connects to a **SQL Server** database with two schemas:

- **`Staging`** — raw and lightly transformed SmPC data (`SMPC`, `SMPC_Active_Substance`, `Substance`, `Substance_Name`, `SMPC_Meta_data`)
- **`rim`** — IDMP-aligned relational model (`MA_Marketing_Authorisation`, `Medicinal_Products`, `Administrable_Product`, `Route_of_Administration`, `MHRA_OrphanDesignation`, `MA_MP_Association`)

DDL scripts for these schemas are maintained separately and must be applied before running the pipeline or the front end. See `SMPC Digitization/Step_01_RIM_CV_setup.py` for the controlled vocabulary setup.

---

## Prerequisites

- Python 3.11+
- SQL Server or Azure SQL with ODBC Driver 18
- OpenAI API key (for substance matching in the digitisation pipeline)
- ODBC Driver 18 for SQL Server ([download](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server))

---

## Configuration

All secrets and environment-specific settings are configured via `.env`. Copy `.env.example` to `.env` and fill in your values — see the comments in that file for guidance on each variable.

**Never commit `.env` to source control.**

---

## Contributing

This project is intended as a community resource for the NCA and regulatory informatics community. Issues and pull requests are welcome. Please ensure no credentials or PII are included in any contribution.

---

## Licence

To be confirmed. Intended for open-source release — licence will be added before the first public release.
