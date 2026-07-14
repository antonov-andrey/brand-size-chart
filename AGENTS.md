# Repository Guidelines

## Scope
- This project owns the `brand-size-chart` workflow-container domain logic.
- Shared workflow-container ecosystem authoring and code quality rules belong to the `workflow-container-tools` plugin reference `references/workflow-container-authoring.md`.
- Generic workflow-container runtime code and generic prompt partials belong to `workflow-container-runtime`.
- Browser/VPN runtime behavior belongs to `browser-vpn-runtime`.
- This project must not depend on `workflow-container-tools` at runtime.

## Python
- Python code uses Python 3.14.
- Python code must be formatted with Black using target version `py314` and line length `120`.
- Tests must use `pytest`.
- Tests must not verify instruction artifacts by checking that specific prose, headings, phrases, examples, files, or placement rules exist or do not exist. Instruction artifacts are verified by semantic reread or semantic audit, not by pytest assertions over text or instruction artifact paths.

## DBOS Runtime
- Configure DBOS only inside `brand_size_chart.app.entrypoint.main`.
- Launch order must stay: build config, call `DBOS.listen_queues(...)`, call `DBOS.launch()`, register the queue, then start the root workflow.
- The browser/VPN runtime is an external runtime capability for this workflow process; `brand_size_chart.app.entrypoint.main` must receive the run-local browser capability values and pass them only through the typed runtime capability used by browser-backed DBOS steps.
- Production runtime must not depend on subagent protocol files, tracker files, Codex exec orchestration, or agent-pool state.
- The workflow process and Playwright must remain outside the OpenVPN network namespace; only the external `vpn-egress` gateway owns OpenVPN and `tun0`, and Playwright reaches it through SOCKS.
- Step code, step prompts, and step arguments must not customize browser/VPN runtime internals such as profile path, VPN path, MCP command, browser flags, locale, timezone, user agent, or stealth behavior.

## Artifacts
- Generated JSON schemas must come from Pydantic v2 models in `brand_size_chart.model`.
- Runtime chart output lives under `brand_size_chart/brand/<parsed_brand_key>/`.
- Workflow and step execution artifacts live in the runtime-owned workflow instance tree under the result root.
- Domain static prompts live under `brand_size_chart/prompt/template/`.
- Project-local prompt partials under `brand_size_chart/prompt/template/partial/` must contain only domain-owned fragments.
- Generic prompt partials must be loaded from `workflow-container-runtime` package resources.
- Root-level Markdown prompt copies under `brand_size_chart/prompt/*.md` are forbidden.
- Static prompts must not contain runtime tracker protocol.
