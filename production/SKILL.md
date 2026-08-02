---
name: buffett-moat-screener-lavine-production
description: Read versioned PandaData-only Q44 Lavine screening results from database.parquet without downloading reports or recomputing factors.
---

# Production Result

Read `database.parquet` using the latest valid `trade_date`. The primary key is `trade_date + factor_id + symbol`.

Required fields include `factor_value`, `score`, `rank`, `signal`, `status`, `evidence_json`, `run_metadata_json`, `data_source`, `data_version`, `rules_version`, `rule_config_hash`, `run_id`, `source_snapshot`, `data_sdk_version`, `runtime_versions_json`, `schema_version` and `update_time`.

Only `status=pass` and `signal=buy` represent a hard-screen selection. `hold` is a research state, not a portfolio instruction. Never trigger a live full-market recomputation merely to answer a production-result query.

Writes use the primary key as an upsert and preserve other dates. Replacing the whole database requires an explicit reviewed operation; partial-universe runs cannot write the canonical `production/database.parquet`.

This result is for research and education and does not constitute investment advice.
