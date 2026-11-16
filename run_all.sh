#!/usr/bin/env bash
# Rebuild everything from scratch: download, contract checks, dbt models and tests, analyses.
set -euo pipefail
cd "$(dirname "$0")"
uv sync -q
uv run python -I scripts/download_data.py
uv run python -I scripts/data_contract.py
(cd dbt_project && ../.venv/bin/dbt build --profiles-dir .)
uv run python -I analysis/churn_backtest.py
uv run python -I analysis/month_end_forecast.py
echo "done: see results/"
