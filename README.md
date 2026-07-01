# brand-size-chart

Executable DBOS workflow for collecting brand-level size-chart artifacts.

The container accepts a `brand_list` input and a `secret` DataSource path, starts one DBOS process for one workflow run, and writes canonical `brand_size_chart` artifacts plus `brand_size_chart_audit` artifacts. Real source discovery and table extraction are Codex-owned browser stages: Codex opens source pages and source assets through the configured browser, writes evidence artifacts, and returns schema-valid stage JSON that references those artifacts.

## Run

```bash
export DBOS_SYSTEM_DATABASE_URL='postgresql://dbos:secret@localhost:5432/brand_size_chart'
export BROWSER_RUNTIME_MCP_URL='http://browser-runtime:8931/mcp'
brand-size-chart-run --workflow-run-id run-01 --brand-list brand_list.txt --output-dir out
```

The default local private DataSource path is `.secret` under the project root. Container runs mount that directory read-only at `/input/.secret`, copy it at startup into pod-local writable `/runtime/.secret`, and use only the runtime copy for `CODEX_HOME` and workflow secret access.

`DBOS_SYSTEM_DATABASE_URL` is required. It may use `postgresql://`, `postgres://`, or `sqlite://`. SQLite is allowed only when configured explicitly through this environment variable; when the variable is absent, DBOS would fall back to a local SQLite system database and this workflow rejects that hidden fallback.

`BROWSER_RUNTIME_MCP_URL` or `--browser-runtime-mcp-url` is required. The workflow process does not start a local browser runtime and does not run in the OpenVPN network namespace.

For standalone local execution with browser traffic through OpenVPN without `marketplace-automation`, put `openvpn/config.json` and the named `.ovpn` file under `.secret/openvpn/`, then run:

```bash
docker compose --profile vpn up --build --abort-on-container-exit --exit-code-from workflow
```

The compose profile starts `openvpn`, runs `playwright-mcp` in the OpenVPN network namespace, and runs `workflow` in the ordinary compose network. The workflow image contains the installed project package and does not bind-mount the checkout. It mounts `.secret` only as `/input/.secret:ro`, mounts `brand_list.txt` as `/input/brand_list.txt:ro`, writes output under `/output`, and sets `DBOS_SYSTEM_DATABASE_URL=sqlite:////runtime/dbos.sqlite`.

## Verification

```bash
python -m pytest -q
python -m compileall brand_size_chart
```
