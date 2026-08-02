---
name: buffett-moat-screener-lavine-version
description: "PandaData-only, point-in-time A-share Buffett moat hard screener with ten-year return consistency, margin stability, capital intensity, debt and TTM valuation evidence. Use when an agent needs an auditable quality screen, historical signal reconstruction, or annual factor validation without future information."
quantSkills:
  organization: https://github.com/lavine888
  repository: lavine888/skill-buffett-moat-screener
  repository_url: https://github.com/lavine888/skill-buffett-moat-screener
  project_type: skill
  collection: liangshuyuan-q44
  license: GPL-3.0
  category: factor
  tags: [a-share, buffett, fundamental, point-in-time, screener]
  platforms: [claude-code, codex, openclaw]
  language: zh-en
  status: active
  validation_level: runnable
  maintainer_type: community
  requires: []
  summary_zh: 基于 PandaData 点时证据执行十年资本回报与护城河硬筛选。
  summary_en: PandaData-only point-in-time Buffett moat hard screener for A-shares.
---

```json qsh-form
{
  "version": 1,
  "task": {
    "placeholder": "例如：筛选贵州茅台和平安银行并解释每条规则",
    "required": true
  },
  "fields": [
    {
      "key": "as_of",
      "type": "date",
      "label": "决策日期"
    },
    {
      "key": "symbols",
      "type": "text",
      "label": "A股代码"
    }
  ],
  "prompt_template": "{{task}}；决策日：{{as_of}}；股票池：{{symbols}}。只使用当时可见的 PandaData 证据。附件：{{#attachments}}"
}
```

# Buffett Moat Screener - Lavine Version

Use this skill to run the original Q44 hard-conjunction screen with explicit point-in-time evidence. It rejects incomplete, conflicting, future-dated or non-PandaData inputs instead of filling missing values.

## Core Workflow

1. Resolve an explicit A-share list or the point-in-time full SH/SZ universe.
2. Download PandaData reports in windows of at most 20 quarters.
3. Keep only report versions announced on or before the decision date.
4. Require 11 consecutive annual balance-sheet observations to calculate 10 annual ROE/ROA values.
5. Calculate ten-year gross-margin population volatility (`ddof=0`) and point-in-time TTM PE.
6. Apply every applicable hard rule and emit `pass`, `fail` or `insufficient_data` with evidence.
7. Optionally materialize the versioned production Parquet result.

## Hard Rules

Ordinary companies must pass all rules:

- latest ROE >= 15%; every ROE in the latest ten-year window >= 12%;
- latest gross margin >= 40%; ten-year gross-margin volatility < 10 percentage points;
- positive net profit; absolute capital expenditure / net profit < 30%;
- long-term interest-bearing debt / net profit < 4;
- point-in-time TTM PE > 0 and < 25.

Lavine's bank branch uses net profit / average total assets: latest ROA >= 1% and every ten-year ROA >= 0.6%. Industrial gross margin, CapEx and long-term-debt gates are `N/A` for banks; positive profit and TTM PE remain mandatory.

## Run

```powershell
pip install -r requirements.txt
$env:PANDA_DATA_USERNAME = "your-account"
$env:PANDA_DATA_PASSWORD = "your-password"
python scripts/build.py --as-of 20251231 --symbols 600519.SH 000001.SZ
```

For a frozen universe, pass a CSV with a `symbol` column or a newline-delimited text file through `--symbols-file`.

Full A-share production run:

```powershell
python scripts/build.py --as-of 20251231 --all-a `
  --cache-dir output/panda-cache --request-interval 1.2 --workers 8 `
  --json-output output/screen-20251231.json `
  --parquet-output production/database.parquet
```

## Output Contract

Every symbol includes thresholds, applicable checks, normalized metrics, coverage years, announcement dates, report adjustment flags, valuation evidence dates and conflict/missing reasons. A selected symbol must have `status=pass` and every applicable check must equal `true`. Top-level diagnostics aggregate insufficient reasons, failed checks, industry coverage and price coverage. Run output also includes `run_id`, `dataset_version`, PandaData SDK version, source context and a deterministic rule-config hash.

## Validation

```powershell
pytest -q
python scripts/validate.py output/screen-20251231.json
python scripts/backtest.py --signal-dates 20221230 20231229 20241231 20251231 `
  --symbols 600519.SH 000001.SZ --output output/backtest.json
```

The annual diagnostic reports IC, Rank IC, quintile returns, turnover, costs, drawdown and an explicit chronological out-of-sample segment. It is research evidence, not an execution simulator.

The validated 2025-12-31 full SH/SZ 1.2.0 run contains 5,182 symbols. Seventeen pass all applicable rules; 1,779 are `insufficient_data`. Always inspect top-level diagnostics before interpreting the selected set.

## References

- `references/data_guide.md`
- `references/methodology.md`
- `references/source_boundary.md`

## Safety Boundary

Credentials are read from environment variables and removed from the process environment after loading. Never place credentials, raw private data or generated full-market datasets in Git.

This Community Project is for research and education only. It is not an official or verified QUANTSKILLS product and does not constitute investment advice.
