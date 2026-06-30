# brand-size-chart

Executable DBOS workflow for collecting brand-level size-chart artifacts.

The container accepts a `brand_list` input and a `secret` DataSource path, starts one DBOS process for one workflow run, and writes canonical `brand_size_chart` artifacts plus `brand_size_chart_audit` artifacts. Real source discovery and table extraction are Codex-owned browser stages: Codex opens source pages and source assets through the configured browser, writes evidence artifacts, and returns schema-valid stage JSON that references those artifacts.

## Run

```bash
export DBOS_SYSTEM_DATABASE_URL='postgresql://dbos:secret@localhost:5432/brand_size_chart'
brand-size-chart-run --workflow-run-id run-01 --brand-list brand_list.txt --secret /data-source/secret --output-dir out
```

`DBOS_SYSTEM_DATABASE_URL` is required. It may use `postgresql://`, `postgres://`, or `sqlite://`. SQLite is allowed only when configured explicitly through this environment variable; when the variable is absent, DBOS would fall back to a local SQLite system database and this workflow rejects that hidden fallback.

## Verification

```bash
python -m pytest -q
python -m compileall brand_size_chart
```
