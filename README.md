# brand-size-chart

Executable DBOS workflow for collecting brand-level size-chart artifacts.

The image implements `WorkflowSourceInterface` v1 through the optional platform base image. It reads one complete immutable workflow input, uses the declared browser/VPN runtime capability, keeps DBOS and implementation state below `/runtime`, writes working checkpoints below `/workspace`, and writes its typed result tree below `/result`.

The complete input selects the model and reasoning effort for each Codex-backed step through `config.step_map`. The application composition root owns only source-defined runtime policy such as low-level execution retries and artifact materialization.

## Runtime Interface

The source-owned command is exactly:

```bash
brand-size-chart-run
```

The process accepts no platform CLI arguments. It requires `WORKFLOW_RUN_ID`, `WORKFLOW_INPUT_PATH`, `WORKFLOW_RUNTIME_PATH`, `WORKFLOW_CONTROL_URL`, and `WORKFLOW_CAPABILITY_CONFIG_PATH`. The platform supplies `/input/input.json`, `/input/capability.json`, the read-only `/input/.secret` mount, private persistent `/runtime`, and the declared writable `/workspace` and `/result` mounts.

The process registers before DBOS starts. After each completed brand it sends one durable safepoint that atomically publishes that brand's result subtree and workspace marker. The root workflow sends one terminal intent containing the exact `RunResult` and terminal mount subtrees, then the process exits normally without more business work. A replacement execution receives the same run identity and `/runtime`, so DBOS resumes the same root workflow instead of starting a second logical run.

The read-only input secret is copied once to `/runtime/.secret`; a replacement execution preserves the existing runtime copy. `CODEX_HOME` uses `/runtime/.secret/codex_profile` when present. `DBOS_SYSTEM_DATABASE_URL` may explicitly select PostgreSQL or SQLite; when omitted, this implementation uses `/runtime/dbos.sqlite3` without requiring the platform to know DBOS.

## Standalone Compose

The Compose contour uses the same command, standard environment, filesystem roots, browser capability document, and runtime separation. It expects the platform base release at `127.0.0.1:5001/apwid-workflow-platform-base:0.5.3` unless `WORKFLOW_PLATFORM_BASE_IMAGE` overrides it. It also requires a reachable v1-compatible development control proxy through `WORKFLOW_CONTROL_URL`; standalone execution does not emulate persistent platform `DataSource` publication.

Put `openvpn/config.json` and the named `.ovpn` file under `.secret/openvpn/`, provide a complete input, and run:

```bash
export INPUT_JSON=/tmp/brand-size-chart-input.json
export WORKFLOW_CONTROL_URL=http://host.docker.internal:18080/v1/
export WORKFLOW_RUN_ID=local-defacto
export COMPOSE_PROJECT_NAME=brand-size-chart-$WORKFLOW_RUN_ID
docker compose --profile vpn up --build --abort-on-container-exit --exit-code-from workflow
```

`vpn-egress` alone owns OpenVPN and `tun0`. `playwright-mcp-router` reaches it through SOCKS and exposes only its MCP and candidate-staging HTTP surface to the workflow. The workflow remains outside the VPN namespace and has its ordinary network path. The exact Git tree is the only workflow image build context; the Dockerfile has no sibling or additional build contexts.

## Verification

```bash
uv venv --python 3.14
source .venv/bin/activate
uv pip install -e "../workflow-container-contract"
uv pip install -e "../workflow-container-runtime"
uv pip install -e ".[test]"
python -m pytest -q
python -m compileall brand_size_chart
```
