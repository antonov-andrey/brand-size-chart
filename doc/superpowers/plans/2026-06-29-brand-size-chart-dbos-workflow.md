# Реализация `brand-size-chart` DBOS Workflow Container

**Цель:** создать concrete workflow repo, который принимает `brand_list` и `secret`, запускает один DBOS process для одного `WorkflowRun`, обрабатывает список брендов и пишет canonical `brand_size_chart` plus `brand_size_chart_audit`.

## Файловая Структура

- Create: `AGENTS.md` — project-local rules, DBOS/Codex/browser boundaries.
- Create: `README.md`.
- Create: `workflow.yaml`, `versions.yaml`.
- Create: `pyproject.toml`, `requirements.txt`.
- Create: `brand_size_chart/identifier.py` — `dbos_identifier_component`, `dbos_identifier`, `workflow_project_name`.
- Create: `brand_size_chart/model.py` — Pydantic v2 result models and generated schema support.
- Create: `brand_size_chart/io.py` — input snapshot/output container filesystem boundary.
- Create: `brand_size_chart/source_type.py` — static source type registry and priorities.
- Create: `brand_size_chart/workflow.py` — DBOS workflows and steps.
- Create: `brand_size_chart/entrypoint.py` — `brand-size-chart-run`.
- Create: `brand_size_chart/prompt/*.md` — static Codex prompts for apply/verification/discovery/extraction/selection.
- Create: `brand_size_chart/schema/*.schema.json` — generated schemas from Pydantic models.
- Create: `test/test_identifier.py`, `test/test_brand_list.py`, `test/test_entrypoint.py`, `test/test_codex_browser_stage.py`, `test/test_models.py`, `test/test_workflow_contract.py`.
- Create: `doc/design/brand-size-chart.md`.

## Task 1: Stable Identity And Input Parsing

- [ ] Implement `dbos_identifier_component` using `Unidecode`.
- [ ] Implement `dbos_identifier`.
- [ ] Implement `brand_list.txt` parsing: trim, comments, empty lines, dedupe by normalized component, warning list.
- [ ] Cover idempotency and duplicate warnings with tests.

## Task 2: Result Models And Schemas

- [ ] Define Pydantic v2 models for prompt scope, stage verification, source discovery, source type summary, table extraction, coverage decision, canonical selection, brand result, and run result; result models carry `status`, `message`, and `error_list` directly.
- [ ] Generate JSON schemas from models; no handwritten schemas.
- [ ] Add tests that validate representative JSON artifacts through generated schemas.

## Task 3: DBOS Runtime Skeleton

- [ ] Implement entrypoint startup order: config, `listen_queues`, launch, register queue, root workflow start/resume.
- [ ] Use one queue name `dbos_identifier("queue", workflow_run_id)`.
- [ ] Use stable root id `dbos_identifier("workflow", workflow_run_id)`.
- [ ] Keep workflow functions deterministic and move filesystem/storage/Codex/browser work to steps.

## Task 4: Domain Workflow

- [ ] Implement `workflow_run_prompt_apply` and verification loop with static prompts.
- [ ] Implement source type loop and stop rules.
- [ ] Implement table extraction/verification loop with artifacts under required layout.
- [ ] Implement canonical selection and conflict reporting.
- [ ] Keep all source discovery and table extraction paths Codex/browser-owned; local sample source paths are forbidden.

## Task 5: Outputs And Verification

- [ ] Write canonical `brand_size_chart/brand/<parsed_brand_key>/manifest.json`.
- [ ] Write `brand_size_chart/brand/<parsed_brand_key>/size_chart/<size_group_key>.json`.
- [ ] Write audit artifacts after every successful stage.
- [ ] Run `python -m pytest -q`.
- [ ] Run `python -m compileall brand_size_chart`.
