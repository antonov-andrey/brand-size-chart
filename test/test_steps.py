"""Behavior tests for source-discovery step preparation and shared state."""

from datetime import UTC, datetime
from pathlib import Path

from workflow_container_contract import WorkflowRunContext
from workflow_container_runtime.artifact import JsonArtifactWriter
from workflow_container_runtime.state import SqliteStateStore, state_database_path_get
from workflow_container_runtime.step import WorkflowStepExecutionContext
from workflow_container_runtime.workflow import (
    NetworkProxyRuntimeCapability,
    WorkflowDataPath,
    WorkflowRuntimeCapability,
)

from brand_size_chart.model import (
    ArtifactWriteTarget,
    BrandInput,
    BrandSourceTypeResultInputSource,
    BrandSourceTypeResultStepInput,
    SourceDiscoveryInput,
)
from brand_size_chart.source.discovery_database import SOURCE_DISCOVERY_TABLE_BY_NAME_MAP
from brand_size_chart.step import (
    CanonicalSelectionDefaultStep,
    CanonicalSelectionStep,
    CoverageDecisionDefaultStep,
    CoverageDecisionStep,
    SourceDiscoveryStep,
)
from brand_size_chart.validator import SourceDiscoveryValidator


def test_source_discovery_prepares_all_sqlite_schemas_and_uses_runtime_state_only(tmp_path: Path) -> None:
    """Initialize every declared SQLite table and schema before source discovery starts."""

    context = _context_get(tmp_path)
    store = SqliteStateStore()
    step = SourceDiscoveryStep.__new__(SourceDiscoveryStep)
    step._artifact_writer = JsonArtifactWriter()
    step._sqlite_state_store = store

    SourceDiscoveryStep.artifact_prepare(step, context, _input_get(context))

    database_path = state_database_path_get(context.step_instance_dir)
    assert database_path.is_file()
    for table in SOURCE_DISCOVERY_TABLE_BY_NAME_MAP.values():
        assert (context.step_instance_dir / f"{table.name}.schema.json").is_file()
        assert store.list(database_path, table) == []
    assert (context.step_instance_dir / "chart.schema.json").is_file()


def test_source_discovery_step_and_validator_share_one_sqlite_store(tmp_path: Path) -> None:
    """Keep the injected state owner identical for step writes and validation reads."""

    context = _context_get(tmp_path)
    store = SqliteStateStore()
    validator = SourceDiscoveryValidator(sqlite_state_store=store)
    step = SourceDiscoveryStep.__new__(SourceDiscoveryStep)
    step._sqlite_state_store = store
    step._validator = validator
    step._artifact_writer = JsonArtifactWriter()

    SourceDiscoveryStep.artifact_prepare(step, context, _input_get(context))
    assert (
        step._sqlite_state_store.list(
            state_database_path_get(context.step_instance_dir), SOURCE_DISCOVERY_TABLE_BY_NAME_MAP["source_table"]
        )
        == []
    )


def test_downstream_steps_build_source_result_input_from_the_model_owner(tmp_path: Path) -> None:
    """Build the same persisted handoff through each downstream step boundary."""

    context = _context_get(tmp_path)
    input_source = BrandSourceTypeResultInputSource(source_type_result_list=[])
    expected_input = BrandSourceTypeResultStepInput.from_execution_context_input_source(context, input_source)

    for step_class in (
        CanonicalSelectionDefaultStep,
        CanonicalSelectionStep,
        CoverageDecisionDefaultStep,
        CoverageDecisionStep,
    ):
        step = step_class.__new__(step_class)

        assert step.input_build(context, input_source) == expected_input


def _context_get(tmp_path: Path) -> WorkflowStepExecutionContext:
    """Build one isolated source-discovery execution context."""

    return WorkflowStepExecutionContext(
        data_path=WorkflowDataPath(
            result_path=(tmp_path / "data-result").resolve(),
            workspace_path=(tmp_path / "data-workspace").resolve(),
        ),
        result_dir=tmp_path,
        run_context=WorkflowRunContext(
            interface_major_version=2,
            version=1,
            workflow_id="workflow-id",
            workflow_name="brand_size_chart",
            workflow_run_id="20260719123456789",
            workflow_run_timestamp=datetime(2026, 7, 19, 12, 34, 56, 789000, tzinfo=UTC),
            workflow_source_id="source-id",
            workflow_source_version_id="source-version-id",
        ),
        runtime_capability=WorkflowRuntimeCapability(
            browser=None,
            network_proxy=NetworkProxyRuntimeCapability(proxy_by_name_map={}),
        ),
        step_instance_dir=tmp_path / "workflow" / "run" / "step" / "source_discover",
        workflow_input_path=Path("workflow/run/input.json"),
    )


def _input_get(context: WorkflowStepExecutionContext) -> SourceDiscoveryInput:
    """Build a source-discovery input carrying its complete workflow-input identity."""

    return SourceDiscoveryInput(
        brand_input=BrandInput(parsed_brand_key="brand", parsed_brand_name="Brand"),
        evidence_write_target=ArtifactWriteTarget(
            artifact_path="workflow/run/step/source_discover/evidence",
            filesystem_path=(context.result_dir / ".playwright-mcp" / "evidence").as_posix(),
        ),
        source_type="official_brand_size_guide",
        workflow_input_path=context.workflow_input_path,
    )
