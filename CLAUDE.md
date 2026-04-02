# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Keboola component (extractor) that queries the Xray Cloud GraphQL API to retrieve test counts. It reads an input CSV table, calls the Xray API for each qualifying row (where `AUTE_DATA_AUTOMATICALLY = "Y"`), and writes results to an output CSV with two additional count columns.

## Development Guidelines

- Act as a senior software engineer — be critical, thorough, and direct
- When asked for an opinion or analysis, provide a proper expert assessment: identify real trade-offs, point out risks, recommend against bad ideas even if the user seems to want them
- Do not just validate what the user proposes — if there's a better approach or a hidden problem, say so clearly
- When something is not worth implementing (complexity > benefit), say so explicitly with reasoning
- Always provide a brief comment explaining what you're doing and why before each action, especially in approval mode where the user confirms each step
- Keep code clean and simple
- Comments should be concise and to the point, not verbose
- All comments must be in English - if you encounter Czech comments, convert them to English

## Build & Run

```bash
# Build and run the component locally
docker-compose build
docker-compose run --rm dev

# Run linting + unit tests
docker-compose run --rm test

# Or run directly (without Docker):
flake8 --config=flake8.cfg
python -m unittest discover
```

The component entrypoint is `python -u /code/src/component.py`. It expects `KBC_DATADIR` env var pointing to the data directory (default `./data`).

## Architecture

This is a standard **Keboola Python component** using `keboola.component` SDK:

- **`src/component.py`** — Main `Component` class extending `ComponentBase`. Handles the pipeline: load config → authenticate → read input CSV → call API per row → write output CSV + manifest.
- **`src/configuration.py`** — Pydantic model for config validation. Keboola encrypted params use `#` prefix aliases (e.g., `#xray_client_id`).
- **`src/xray_api.py`** — `XrayApiClient` handles Xray Cloud auth (bearer token via REST) and GraphQL queries with retry logic (status 429/503, up to 4 retries with 15s increments).
- **`component_config/configSchema.json`** — JSON schema for Keboola UI configuration form.
- **`data/`** — Local test data directory (`config.json`, `in/`, `out/`) used when running with `KBC_DATADIR=./data`.

## Key Conventions

- **Linting**: flake8 with max line length 120 (see `flake8.cfg`). Tests directory is excluded from linting. **No line may exceed 120 characters** — the CI/CD build will fail otherwise.
- **Python 3.11** (Docker base image).
- **Testing**: `unittest` framework with `mock` and `freezegun`. Tests live in `tests/test_component.py`. Test discovery via `python -m unittest discover`.
- Input rows are processed only when `AUTE_DATA_AUTOMATICALLY` column equals `"Y"` (note: this is the actual column name, not a typo — do not "fix" it).
- Each input column contains a JSON array of 3 elements: `[project_id, folder_path, jql_query]`.
- The component processes two independent column pairs (total tests + automated tests) per row.
