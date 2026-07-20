# brand-size-chart

Executable DBOS workflow for collecting brand-level size-chart artifacts.

The image implements `WorkflowSourceInterface` major 2 through the optional platform base image. It reads one complete immutable workflow input and immutable run context, uses the declared browser/VPN runtime capability, keeps DBOS and implementation state below `/runtime`, writes workflow Data below `/workspace`, and writes user-visible results below `/result`.

The complete input selects the model and reasoning effort for each Codex-backed step through `config.step_map`. The application composition root owns only source-defined runtime policy such as low-level execution retries and artifact materialization.

## Runtime Interface

The source-owned command is exactly:

```bash
brand-size-chart-run
```

The process accepts no platform CLI arguments. It requires `WORKFLOW_RUN_ID`, `WORKFLOW_INPUT_PATH`, `WORKFLOW_RUN_CONTEXT_PATH`, `WORKFLOW_RUNTIME_PATH`, `WORKFLOW_CONTROL_URL`, and `WORKFLOW_CAPABILITY_CONFIG_PATH`. The platform supplies `/input/input.json`, `/input/run-context.json`, `/input/capability.json`, the read-only `/input/.secret` tree, private persistent `/runtime`, and the writable `/workspace` and `/result` Data roots.

The process registers before DBOS starts. After each completed brand it sends one durable `brand_complete` safepoint that atomically accepts `result/{brand_key}`, `workspace/{brand_key}`, the complete `/runtime` checkpoint, and the step transition. The root workflow then sends one final request containing the exact `RunResult`; the already accepted brand manifests are not requested again. After the durable receipt, the process exits normally without more business work. A replacement execution receives the same immutable run context and accepted `/runtime`, so DBOS resumes the same logical workflow instead of starting another one.

The exact read-only `codex_profile` secret is copied to attempt-local `/tmp/codex_profile`; `CODEX_HOME` uses only that writable copy. It is recreated from the immutable secret snapshot for every replacement execution and never enters `/runtime`, `/workspace`, `/result`, or an ordinary Data checkpoint. `DBOS_SYSTEM_DATABASE_URL` may explicitly select PostgreSQL or SQLite; when omitted, this implementation uses `/runtime/dbos.sqlite3` without requiring the platform to know DBOS.

## Standalone Compose

The Compose contour uses the same command, standard environment, filesystem roots, browser capability document, and runtime separation. It expects the platform base release at `127.0.0.1:5001/apwid-workflow-platform-base:0.6.3` unless `WORKFLOW_PLATFORM_BASE_IMAGE` overrides it. It also requires a complete `WorkflowRunContext` JSON file and a reachable major-2 development control proxy through `WORKFLOW_CONTROL_URL`; standalone execution does not emulate platform Data acceptance.

The current source version declares `browser_vpn_runtime.config.is_vpn_enabled: false`. Ensure `.secret/codex_profile/` contains the Codex credentials and `.secret/playwright_profile/` exists; the profile directory may be empty. Provide a complete input and run:

```bash
export INPUT_JSON=/tmp/brand-size-chart-input.json
export RUN_CONTEXT_JSON=/tmp/brand-size-chart-run-context.json
export WORKFLOW_CONTROL_URL=http://host.docker.internal:18080/v2/
export WORKFLOW_RUN_ID=20260719123456789
export COMPOSE_PROJECT_NAME=brand-size-chart-$WORKFLOW_RUN_ID
docker compose up --build --abort-on-container-exit --exit-code-from workflow
```

Compose therefore creates no OpenVPN service, does not mount `.secret/openvpn/`, and launches the browser router without a proxy. The workflow and browser retain ordinary direct egress while sharing only the internal browser-control network. A future source version that enables VPN must update `workflow.yaml` and its Compose contour together. The exact Git tree is the only workflow image build context; the Dockerfile has no sibling or additional build contexts.

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
