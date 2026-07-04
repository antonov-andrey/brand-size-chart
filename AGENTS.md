# Repository Guidelines

## Scope
- This project owns the `brand-size-chart` workflow-container domain logic.
- Shared workflow-container ecosystem authoring and code quality rules belong to the `workflow-container-developer` plugin reference `references/workflow-container-authoring.md`.
- Generic workflow-container runtime code and generic prompt partials belong to `workflow-container-runtime`.
- Browser/VPN runtime behavior belongs to `browser-vpn-runtime`.
- This project must not depend on `workflow-container-developer` at runtime.

## Python
- Python code uses Python 3.14.
- Python code must be formatted with Black using target version `py314` and line length `120`.
- Tests must use `pytest`.

## DBOS Runtime
- Configure DBOS only inside `brand_size_chart.app.entrypoint.main`.
- Launch order must stay: build config, call `DBOS.listen_queues(...)`, call `DBOS.launch()`, register the queue, then start the root workflow.
- The browser/VPN runtime is an external runtime capability for this workflow process; `brand_size_chart.app.entrypoint.main` must receive its MCP URL and pass only that URL into DBOS stages.
- Production runtime must not depend on subagent protocol files, tracker files, Codex exec orchestration, or agent-pool state.
- The workflow process must not run in the OpenVPN network namespace; only the browser runtime process may use the VPN network path.
- Stage code, stage prompts, and stage arguments must not customize browser/VPN runtime internals such as profile path, VPN path, MCP command, browser flags, locale, timezone, user agent, or stealth behavior.

## Artifacts
- Generated JSON schemas must come from Pydantic v2 models in `brand_size_chart.model`.
- Runtime chart output lives under `brand_size_chart/brand/<parsed_brand_key>/`.
- Audit output lives under `brand_size_chart_audit/brand/<parsed_brand_key>/`.
- Domain static prompts live under `brand_size_chart/prompt/template/`.
- Project-local prompt partials under `brand_size_chart/prompt/template/partial/` must contain only domain-owned fragments.
- Generic prompt partials must be loaded from `workflow-container-runtime` package resources.
- Root-level Markdown prompt copies under `brand_size_chart/prompt/*.md` are forbidden.
- Static prompts must not contain runtime tracker protocol.
