# Repository Guidelines

## Required Standards
- `project-standards:project-foundation` applies to all work in this repository.
- `project-standards:project-instruction-developer` applies to instruction artifacts.
- `project-standards:project-documentation-developer` applies to `DESIGN.md`.
- `project-standards:python-developer`, `project-standards:python-cli-developer`, and `project-standards:pytest-developer` apply to Python code, entrypoints, and tests.
- `project-standards:runtime-config-developer` applies to environment-backed runtime configuration.
- `project-standards:docker-compose-developer` applies to `compose.yaml` and its runtime contour.
- `workflow-container-agent-tools:workflow-container-developer` applies to workflow-container code, contracts, prompts, and runtime integration.

If one required provider skill is unavailable, continue read-only discovery only and do not mutate this repository until the provider is restored.

Active task pairs live only under the ignored `.spec/` root.

## Scope
- This project owns the `brand-size-chart` workflow-container domain logic.
- Shared workflow-container ecosystem authoring and code quality rules belong to `workflow-container-agent-tools:workflow-container-developer`.
- Generic workflow-container runtime code and generic prompt partials belong to `workflow-container-runtime`.
- Browser runtime behavior belongs to `browser-runtime`.
- VPN gateway, SOCKS5, tunnel lifecycle, and VPN config validation belong to `vpn-runtime`.
- This project must not depend on agent plugins at runtime.

## Python
- Python code uses Python 3.14.
- Python code must be formatted with Black using target version `py314` and line length `120`.
- Tests must use `pytest`.
- Tests must not verify instruction artifacts by checking that specific prose, headings, phrases, examples, files, or placement rules exist or do not exist. Instruction artifacts are verified by semantic reread or semantic audit, not by pytest assertions over text or instruction artifact paths.

## DBOS Runtime
- Configure DBOS only inside `brand_size_chart.app.entrypoint.main`.
- Launch order must stay: build config, call `DBOS.listen_queues(...)`, call `DBOS.launch()`, register the queue, then start the root workflow.
- The browser runtime and network proxy map are external runtime capabilities for this workflow process; `brand_size_chart.app.entrypoint.main` must receive their safe values and pass them only through the typed runtime capability used by browser-backed DBOS steps.
- Production runtime must not depend on subagent protocol files, tracker files, Codex exec orchestration, or agent-pool state.
- The workflow process and Playwright must remain outside every VPN gateway network namespace and may reach a selected gateway only through its platform-provided SOCKS endpoint.
- Every browser-backed step must use only its exact `mcp_playwright_network_proxy_name` from the complete workflow input; project code must not add automatic proxy selection, distribution, routing indices, or fallback.
- Step code, step prompts, and step arguments must not customize browser or VPN runtime internals such as profile path, VPN path, MCP command, browser flags, locale, timezone, user agent, stealth behavior, tunnel protocol, or provider credentials.

## Artifacts
- Generated JSON schemas must come from Pydantic v2 models in `brand_size_chart.model`.
- User-visible chart and dataset output lives under `/result/<parsed_brand_key>/`.
- User-visible workflow state lives under `/workspace/<parsed_brand_key>/`.
- Workflow and step execution artifacts live in the runtime-owned workflow instance tree under `/runtime/result/`.
- Domain static prompts live under `brand_size_chart/prompt/template/`.
- Project-local prompt partials under `brand_size_chart/prompt/template/partial/` must contain only domain-owned fragments.
- Generic prompt partials must be loaded from `workflow-container-runtime` package resources.
- Root-level Markdown prompt copies under `brand_size_chart/prompt/*.md` are forbidden.
- Static prompts must not contain runtime tracker protocol.
