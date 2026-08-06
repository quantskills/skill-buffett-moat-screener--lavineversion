# Changelog

## 2.0.0 - 2026-08-06

- Document the purpose of both dependency manifests in-file and in the READMEs.
- Remove stale nested duplicate cache directories from the working tree and guard the release package against nested project directories.
- Add an offline integration smoke test that runs build, JSON and Parquet materialization, and both strict validators.
- Keep the rule and schema contract at `1.2.0`; no rule thresholds changed.

## 1.2.0 - 2026-08-02

- Correct the one-year-due debt field to `bs_ncl_due_1y`; all-null debt evidence now fails closed.
- Separate known nonpositive-profit/EPS failures from genuinely missing evidence.
- Bind cache namespaces and dataset versions to provider/runtime, field contract, universe and response hashes.
- Add atomic response manifests and lock one-time authentication for concurrent requests.
- Upsert production data by primary key, guard canonical output from partial runs and add explicit replace semantics.
- Add run-level metadata to production rows and strict JSON/Parquet validators.
- Include initial equity in maximum drawdown and reject overlapping industry assignments.
- Rebuild and validate the 2025-12-31 full SH/SZ production artifact.

## 1.1.0 - 2026-08-02

- Fail closed on invalid evidence dates, missing industry and missing/invalid `if_adjusted` values.
- Preserve report adjustment flags in per-symbol evidence.
- Add run ID, dataset version, PandaData SDK version, source context and rule-config hash.
- Add top-level data-quality and failed-rule diagnostics.
- Add reproducible `--symbols-file` CLI input and automatic output-directory creation.
- Add throttled, atomic and resumable PandaData response caching for full-market runs.
- Parallelize cached report-window requests under a global start-rate throttle and group reports by symbol for linear full-market evaluation.
- Validate the 2025-12-31 full SH/SZ universe and materialize the matching production database.
- Replace Jaccard turnover with equal-weight one-way turnover.
- Fail annual diagnostics when a selected symbol lacks a finite forward return.
- Add PandaData provider, service, materialization, validator and CLI contract tests.

## 1.0.0

- Initial PandaData-only point-in-time Q44 Lavine implementation.
