"""Behavior tests for source-discovery step setup and public handoff."""

from pathlib import Path

from workflow_container_runtime.artifact import ArtifactMaterializationPolicy, ArtifactMaterializer, JsonArtifactWriter
from workflow_container_runtime.codex import CodexRunner
from workflow_container_runtime.prompt import PromptRenderer
from workflow_container_runtime.state import SqliteStateStore, state_database_path_get
from workflow_container_runtime.step import (
    CodexExecutionRetryPolicy,
    WorkflowStepCodexConfig,
    WorkflowStepCodexState,
    WorkflowStepExecutionContext,
)
from workflow_container_runtime.workflow import WorkflowRuntimeCapability

from brand_size_chart.model import (
    ArtifactWriteTarget,
    BrandInput,
    PromptScope,
    SourceDiscoveryInput,
    SourceTypeWorkflowInput,
)
from brand_size_chart.source.discovery_database import SOURCE_DISCOVERY_TABLE_BY_NAME_MAP
from brand_size_chart.step import SourceDiscoveryStep
from brand_size_chart.validator import SourceDiscoveryValidator


def _context_get(tmp_path: Path) -> WorkflowStepExecutionContext:
    """Return one isolated source-discovery execution context.

    Args:
        tmp_path: Isolated result root.

    Returns:
        Current step context.
    """

    return WorkflowStepExecutionContext(
        result_dir=tmp_path,
        runtime_capability=WorkflowRuntimeCapability(browser=None),
        step_instance_dir=tmp_path / "workflow" / "run" / "step" / "source_discover",
    )


def _input_get(tmp_path: Path) -> SourceDiscoveryInput:
    """Return one typed source-discovery input.

    Args:
        tmp_path: Isolated result root.

    Returns:
        Persisted input fixture.
    """

    return SourceDiscoveryInput(
        evidence_write_target=ArtifactWriteTarget(
            artifact_path="workflow/run/step/source_discover/evidence",
            filesystem_path=(tmp_path / ".playwright-mcp" / "current" / "evidence").as_posix(),
        ),
        workflow_input=SourceTypeWorkflowInput(
            brand_input=BrandInput(
                parsed_brand_key="brand",
                parsed_brand_name="Brand",
                raw_brand_name="Brand",
                source_line_number=1,
            ),
            prompt_scope=PromptScope(priority_country_code="TR"),
            source_type="official_brand_size_guide",
        ),
    )


def test_source_discovery_prepares_all_sqlite_schemas_and_uses_runtime_state_only(tmp_path: Path) -> None:
    """Initialize current state and schemas without domain fields in state.json.

    Args:
        tmp_path: Isolated result root.
    """

    context = _context_get(tmp_path)
    store = SqliteStateStore()
    step = SourceDiscoveryStep.__new__(SourceDiscoveryStep)
    step._artifact_writer = JsonArtifactWriter()
    step._sqlite_state_store = store

    SourceDiscoveryStep.artifact_prepare(step, context, _input_get(tmp_path))

    assert SourceDiscoveryStep.state_model is WorkflowStepCodexState
    assert state_database_path_get(context.step_instance_dir).is_file()
    for table in SOURCE_DISCOVERY_TABLE_BY_NAME_MAP.values():
        assert (context.step_instance_dir / f"{table.name}.schema.json").is_file()
        assert store.list(state_database_path_get(context.step_instance_dir), table) == []
    assert (context.step_instance_dir / "chart.schema.json").is_file()


def test_source_discovery_constructor_receives_one_shared_sqlite_store(tmp_path: Path) -> None:
    """Keep step and validator on the same injected store instance.

    Args:
        tmp_path: Isolated temporary directory.
    """

    store = SqliteStateStore()
    validator = SourceDiscoveryValidator(sqlite_state_store=store)
    step = SourceDiscoveryStep(
        artifact_materializer=ArtifactMaterializer(),
        artifact_writer=JsonArtifactWriter(),
        codex_runner=CodexRunner,
        config=WorkflowStepCodexConfig(
            artifact_materialization_policy=ArtifactMaterializationPolicy(artifact_root_tuple=()),
            attempt_limit=1,
            execution_retry_policy=CodexExecutionRetryPolicy(attempt_limit=1),
        ),
        prompt_renderer=PromptRenderer(template_dir=tmp_path),
        sqlite_state_store=store,
        validator=validator,
    )

    assert step._sqlite_state_store is store
    assert step._validator is validator
