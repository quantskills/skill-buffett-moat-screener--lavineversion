# Source Boundary

Production inputs are restricted to PandaData A-share APIs:

- `get_stock_detail`
- `get_fina_reports`
- `get_stock_daily`
- `get_stock_daily_post`
- `get_industry_constituents`
- `get_industry_detail`

AkShare, Tushare, manually edited spreadsheets, current-only web values and caller-supplied financial snapshots are not accepted as production evidence.

The SDK's `get_stock_operating_*` and `get_stock_mktfin_*` endpoints are documented for Hong Kong and US symbols and reject A-share codes. This project therefore derives A-share ratios from PandaData statements and prices instead of mislabeling those endpoints as A-share sources.

PandaData is an online service, so reproducibility requires retaining the generated JSON/Parquet artifact. Version 1.2.0 cache namespaces bind the PandaData SDK version, hashed base URL, anonymous account hash and report-field contract. Each cached response has an atomic manifest with fetch time, schema, row count and normalized frame SHA-256. `source_snapshot` is the aggregate hash of every response actually used by a run; `dataset_version` also binds the sorted universe hash.
