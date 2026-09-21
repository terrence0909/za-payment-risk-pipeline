# ZA Payment Risk Streaming Pipeline

> Real-time cross-border payment compliance and SARB FinSurv reporting for South African financial institutions.

[![CI](https://github.com/tshepo-tau/za-payment-risk-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/tshepo-tau/za-payment-risk-pipeline/actions)
![Python](https://img.shields.io/badge/python-3.11-blue)
![Kafka](https://img.shields.io/badge/kafka-7.6.1-black)
![dbt](https://img.shields.io/badge/dbt-1.10-orange)
![Airflow](https://img.shields.io/badge/airflow-2.9.1-teal)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Why this exists

South African banks operating under SARB FinSurv regulations must report every cross-border payment within a **24-hour window**. Breaches — transactions that exceed the R1,000,000 Annual Discretionary Allowance, carry invalid BOP category codes, or route toward sanctioned corridors — must be caught *before* the reporting deadline, not discovered after.

This pipeline does exactly that. It ingests a continuous stream of cross-border payment events, scores each transaction for compliance risk the moment it arrives, lands clean and flagged records into a Delta Lake medallion architecture, runs dbt transformations for analytical reporting, and surfaces a live Streamlit dashboard showing breach patterns and ADA utilisation in real time.

The entire stack runs locally via Docker Compose. Every component maps 1:1 to an Azure production service — deploying to Azure is a configuration change, not a rearchitect.

This project is the natural evolution of the [SARB FinSurv Blockchain Compliance Pipeline](https://github.com/terrence0909/1FinSurv-Pipeline) — same domain, same regulatory rules, upgraded from batch to real-time streaming with a full lakehouse layer on top.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     LOCAL DOCKER ENVIRONMENT                         │
│                                                                       │
│  ┌──────────────┐     ┌─────────────┐     ┌─────────────────────┐  │
│  │   Payment     │     │    Kafka    │     │   Faust Stream      │  │
│  │   Producer    │────▶│   Broker   │────▶│   Processor         │  │
│  │               │     │            │     │                     │  │
│  │  Synthetic ZA │     │  Topics:   │     │  • ADA limit check  │  │
│  │  transactions │     │  raw       │     │  • BOP validation   │  │
│  │  BOP codes    │     │  scored    │     │  • Sanctions screen │  │
│  │  SWIFT BICs   │     │  alerts    │     │  • Risk score 0–100 │  │
│  │  ADA tracking │     │            │     │  • Delta Lake write │  │
│  └──────────────┘     └─────────────┘     └──────────┬──────────┘  │
│                                                        │             │
│                                           ┌────────────▼──────────┐ │
│                                           │   MinIO (S3-compat)   │ │
│                                           │   Delta Lake Bronze   │ │
│                                           └────────────┬──────────┘ │
│                                                        │             │
│                                           ┌────────────▼──────────┐ │
│                                           │   DuckDB + dbt Core   │ │
│                                           │                       │ │
│                                           │   staging/            │ │
│                                           │   marts/              │ │
│                                           │   Silver + Gold       │ │
│                                           └────────────┬──────────┘ │
│                                                        │             │
│              ┌──────────────────┐        ┌────────────▼──────────┐ │
│              │  Apache Airflow  │        │  Streamlit Dashboard  │ │
│              │  Daily 22:00SAST │        │                       │ │
│              │  1. Validate     │        │  Live risk feed       │ │
│              │  2. dbt run      │        │  Breach alerts        │ │
│              │  3. dbt test     │        │  ADA utilisation      │ │
│              │  4. Report gen   │        │  Corridor heatmap     │ │
│              │  5. SAR routing  │        │                       │ │
│              └──────────────────┘        └───────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘

Azure production equivalent (config change only):
  Kafka        → Azure Event Hubs
  MinIO        → Azure Data Lake Storage Gen2
  DuckDB       → Azure Synapse Analytics
  Airflow      → Azure Data Factory
  Docker net   → Azure Virtual Network + Private Endpoints
  GitHub CI    → Azure DevOps Pipelines
```

---

## Tech Stack

| Layer | Local Tool | Azure Production Equivalent |
|---|---|---|
| Event streaming | Apache Kafka | Azure Event Hubs |
| Stream processing | Python + Faust | Azure Stream Analytics |
| Object storage | MinIO | Azure Data Lake Storage Gen2 |
| Table format | Delta Lake | Delta Lake on ADLS Gen2 |
| Transformations | dbt Core + DuckDB | dbt on Azure Synapse |
| Orchestration | Apache Airflow | Azure Data Factory |
| Data quality | Great Expectations | — |
| Dashboard | Streamlit | Power BI / Azure Static Web Apps |
| IaC | Docker Compose + Terraform | Terraform on Azure |
| CI/CD | GitHub Actions | Azure DevOps Pipelines |

---

## Compliance Rules Engine

Ten rules implemented in `src/processor/rules_engine.py`, all independently tested:

| Rule | Logic | Severity |
|---|---|---|
| `ADA_LIMIT_BREACH` | `ada_ytd_used + amount_zar > R1,000,000` (individuals) | 🔴 CRITICAL |
| `ADA_APPROACH_WARNING` | ADA utilisation between 85–100% | 🟠 HIGH |
| `INVALID_BOP_CODE` | BOP code not in SARB-approved set | 🟠 HIGH |
| `INVALID_CURRENCY` | Currency not SARB-approved for FinSurv reporting | 🟠 HIGH |
| `SANCTIONED_CORRIDOR` | Destination on OFAC/UN sanctions list | 🔴 CRITICAL |
| `FATF_GREY_LIST` | Destination on FATF grey list | 🟡 MEDIUM |
| `LARGE_INDIVIDUAL_TRANSFER` | Individual transfer > R500,000 | 🟠 HIGH |
| `ROUND_AMOUNT_PATTERN` | Amount divisible by 10,000 — possible structuring | 🟡 MEDIUM |
| `MALFORMED_SWIFT_BIC` | BIC doesn't match BIC8/BIC11 format | 🟡 MEDIUM |
| `COMPANY_INDIVIDUAL_BOP_MISMATCH` | Company using individual-category BOP code | 🟡 MEDIUM |

### Risk Score Bands

| Score | Band | Action |
|---|---|---|
| 0–25 | 🟢 LOW | Pass — log to Delta Lake |
| 26–50 | 🟡 MEDIUM | Pass — flag for review |
| 51–75 | 🟠 HIGH | Hold — route to alerts topic |
| 76–100 | 🔴 CRITICAL | Block — mandatory SAR filing |

---

## dbt Medallion Architecture

```
Bronze  →  Raw Kafka events landed as-is into Delta Lake
           No transformation, append-only, immutable

Silver  →  stg_payments.sql
           Cast, rename, type, deduplicate
           Derive ada_utilisation_pct, is_ada_breached, is_critical

Gold    →  finsurvreport_daily.sql
           Daily aggregate per bank — compliance pass rate,
           risk distribution, ADA breach counts, SAR-required count

           corridor_exposure.sql
           ZAR volume and risk distribution by destination country
```

---

## Quick Start

### Prerequisites

- Docker Desktop (4GB RAM minimum)
- Python 3.9+
- Git

### Run locally

```bash
# Clone
git clone https://github.com/tshepo-tau/za-payment-risk-pipeline.git
cd za-payment-risk-pipeline

# Copy environment config
cp .env.example .env

# Start the full stack
make up

# In a new terminal — start producing synthetic transactions
make produce

# Run dbt transformations
cd dbt_project && dbt seed --profiles-dir . && dbt run --profiles-dir .

# Run dbt tests
dbt test --profiles-dir .
```

### Services

| Service | URL | Credentials |
|---|---|---|
| Kafka UI | http://localhost:8090 | — |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |
| Airflow | http://localhost:8081 | admin / admin |
| Streamlit Dashboard | http://localhost:8501 | — |

### Make targets

```bash
make up       # Start the full stack
make down     # Stop all services
make produce  # Start the synthetic payment producer
make logs     # Tail all service logs
make clean    # Remove volumes and reset state
```

---

## Project Structure

```
za-payment-risk-pipeline/
├── src/
│   ├── producer/
│   │   ├── generator.py        # Synthetic ZA payment factory
│   │   └── producer.py         # Kafka producer loop
│   ├── processor/
│   │   ├── app.py              # Faust stream processor
│   │   ├── rules_engine.py     # 10 SARB compliance rules
│   │   └── tests/
│   │       └── test_rules_engine.py  # 20 unit tests
│   └── dashboard/
│       └── app.py              # Streamlit live dashboard
├── dbt_project/
│   ├── models/
│   │   ├── staging/
│   │   │   └── stg_payments.sql
│   │   └── marts/
│   │       ├── finsurvreport_daily.sql
│   │       └── corridor_exposure.sql
│   ├── seeds/
│   │   └── sample_payments.csv
│   └── tests/
├── infra/
│   ├── docker-compose.yml
│   ├── airflow/dags/
│   │   └── za_payment_pipeline.py
│   └── terraform/              # Azure deployment (drop-in)
├── .github/workflows/
│   └── ci.yml
├── Makefile
└── .env.example
```

---

## Testing

### Unit tests — rules engine

```bash
python3 -m pytest src/processor/tests/test_rules_engine.py -v
```

20 tests covering every compliance rule — ADA breaches, BOP validation, sanctions screening, SWIFT BIC format, risk scoring bands.

### dbt tests

```bash
cd dbt_project && dbt test --profiles-dir .
```

5 schema tests: `unique`, `not_null`, `accepted_values` on source data.

---

## Azure Deployment

This project deploys to Azure with configuration changes only:

```bash
# Set Azure credentials
export ARM_CLIENT_ID=...
export ARM_CLIENT_SECRET=...
export ARM_TENANT_ID=...
export ARM_SUBSCRIPTION_ID=...

# Deploy infrastructure
cd infra/terraform
terraform init
terraform plan
terraform apply
```

Resources provisioned: Event Hubs namespace, ADLS Gen2, Synapse workspace, ADF pipeline, Key Vault for secrets, VNet with private endpoints.

---

## Compliance Context

This pipeline implements the following SARB Exchange Control rules:

- **Annual Discretionary Allowance (ADA):** South African residents may not transfer more than R1,000,000 offshore per calendar year without SARB approval. Transactions pushing a sender over this threshold are flagged CRITICAL and blocked.
- **BOP Category Codes:** Every cross-border payment must carry a valid Balance of Payments category code per the SARB Exchange Control Manual.
- **Currency Eligibility:** Only SARB-approved currencies are accepted for FinSurv reporting.
- **FATF Compliance:** Transactions to FATF grey-listed or OFAC-sanctioned destinations trigger enhanced due diligence or mandatory SAR filing.

> This pipeline implements FinSurv validation rules for portfolio demonstration purposes. Production deployments should be reviewed against the current SARB Exchange Control Manual.

---

## Related Projects

- [SARB FinSurv Blockchain Compliance Pipeline](https://github.com/terrence0909/1FinSurv-Pipeline) — the batch predecessor to this project. Same domain, same regulatory rules — upgraded here to real-time streaming with a full lakehouse layer.
- [Project ZAR — Cryptocurrency Compliance Platform](https://github.com/tshepo-tau) — multi-stage validation pipeline for crypto compliance with risk scoring and audit trails.

---

## Author

**Tshepo Tau** — Data & Cloud Engineer, Johannesburg  
AWS Certified Solutions Architect · KCNA · DataCamp Data Engineer

[GitHub](https://github.com/tshepo-tau) · [LinkedIn](https://linkedin.com/in/tshepo-tau)

---

> *Built to demonstrate production-grade data engineering on South African financial regulatory workloads.*