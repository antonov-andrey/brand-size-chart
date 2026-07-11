# brand-size-chart

Executable DBOS workflow for collecting brand-level size-chart artifacts.

The container accepts a `brand_list` input and a `secret` DataSource path, starts one DBOS process for one workflow run, and writes a typed workflow result tree plus canonical `brand_size_chart` artifacts. One browser-backed `source_discover` step opens source pages and assets through the configured browser, writes evidence and charts, and persists its declared SQLite inventory. Downstream typed coverage, canonical-selection, and publication boundaries read that declared artifact without copying its rows into workflow handoffs.

The application composition root configures every Codex action and verification call with model `gpt-5.6-terra` and reasoning effort `high`.

## Run

```bash
export DBOS_SYSTEM_DATABASE_URL='postgresql://dbos:secret@localhost:5432/brand_size_chart'
export BROWSER_RUNTIME_MCP_URL='http://browser-runtime:8931/mcp'
brand-size-chart-run \
  --workflow-run-id run-01 \
  --brand-list brand_list.txt \
  --output-dir out \
  --workflow-run-prompt 'Use Turkey as the priority country.'
```

The default local private DataSource path is `.secret` under the project root. Container runs mount that directory read-only at `/input/.secret`, copy it at startup into pod-local writable `/runtime/.secret`, and use only the runtime copy for `CODEX_HOME` and workflow secret access.

`DBOS_SYSTEM_DATABASE_URL` is required. It may use `postgresql://`, `postgres://`, or `sqlite://`. SQLite is allowed only when configured explicitly through this environment variable; when the variable is absent, DBOS would fall back to a local SQLite system database and this workflow rejects that hidden fallback.

`BROWSER_RUNTIME_MCP_URL` or `--browser-runtime-mcp-url` is required. The workflow process does not start a local browser runtime and does not run in the OpenVPN network namespace.

For standalone local execution with browser traffic through OpenVPN without `marketplace-automation`, put `openvpn/config.json` and the named `.ovpn` file under `.secret/openvpn/`, then run:

```bash
printf 'Defacto\n' > /tmp/brand-size-chart-brand-list.txt
export BRAND_LIST=/tmp/brand-size-chart-brand-list.txt
export WORKFLOW_RUN_PROMPT='Use Turkey as the priority country.'
docker compose --profile vpn up --build --abort-on-container-exit --exit-code-from workflow
```

The compose profile starts `vpn-egress` as a fail-closed OpenVPN SOCKS5 gateway. `playwright-mcp` runs only in the internal `browser-control` network and sends target traffic through `vpn-egress:1080`; it never shares the OpenVPN network namespace or observes `tun0` lifecycle changes. `workflow` uses `browser-control` for the MCP connection and `vpn-uplink` for its own required runtime traffic. The workflow process prepares each exact declared external artifact write directory for cross-process writes; the private DataSource and unrelated output paths retain their existing permissions. The workflow image contains the installed project package and does not bind-mount the checkout. It mounts `.secret` only as `/input/.secret:ro`, mounts the file selected by `BRAND_LIST` as `/input/brand_list.txt:ro`, writes output under `/output`, configures Playwright MCP with `/output/.playwright-mcp/current` as its writable artifact namespace so browser tools cannot write automatic page or console artifacts beside root workflow outputs, keeps the mutable browser profile in the named `browser-profile-runtime` volume, keeps generated MCP config under container-local `/runtime`, and sets `DBOS_SYSTEM_DATABASE_URL=sqlite:////runtime/dbos.sqlite`.

After the browser container has stopped, publish its profile back to the local DataSource explicitly:

```bash
HOST_UID="$(id -u)" HOST_GID="$(id -g)" \
  docker compose --profile writeback run --rm playwright-profile-writeback
```

Only this one-shot service receives a writable `.secret` mount. It reads the stopped runtime profile volume, prepares the complete replacement beside `.secret/playwright_profile`, applies the host owner before publication, and performs the atomic browser-runtime writeback contract. The workflow and long-lived browser services keep `.secret` read-only.

The local workflow image build uses `WORKFLOW_CONTAINER_CONTRACT_CONTEXT` and `WORKFLOW_CONTAINER_RUNTIME_CONTEXT`, defaulting to the sibling `../workflow-container-contract` and `../workflow-container-runtime` repositories. This keeps local standalone builds independent of SSH access while installing both shared packages separately.

## Verification

```bash
uv venv --python 3.14
source .venv/bin/activate
uv pip install -e ".[test]"
python -m pytest -q
python -m compileall brand_size_chart
```
