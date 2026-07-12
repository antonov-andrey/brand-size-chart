"""SQLite-backed browser source-discovery step."""

from pathlib import Path
from typing import ClassVar

from workflow_container_runtime.artifact import (
    ArtifactMaterializer,
    JsonArtifactWriter,
    shared_artifact_directory_prepare,
)
from workflow_container_runtime.codex import CodexRunner
from workflow_container_runtime.prompt import PromptRenderer
from workflow_container_runtime.state import SqliteStateStore, state_database_path_get
from workflow_container_runtime.step import (
    BrowserActionResult,
    WorkflowStepCodexConcurrentBase,
    WorkflowStepCodexRuntimePolicy,
    WorkflowStepCodexState,
    WorkflowStepExecutionContext,
)

from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import (
    ArtifactWriteTarget,
    BrandSizeChart,
    SourceDiscoveryInput,
    SourceDiscoveryResult,
    SourceDiscoveryInputSource,
    WorkflowStepSourceDiscoverConfig,
)
from brand_size_chart.source.discovery_database import SOURCE_DISCOVERY_TABLE, SOURCE_DISCOVERY_TABLE_BY_NAME_MAP
from brand_size_chart.validator import SourceDiscoveryValidator


class SourceDiscoveryStep(
    WorkflowStepCodexConcurrentBase[
        SourceDiscoveryInputSource,
        SourceDiscoveryInput,
        WorkflowStepSourceDiscoverConfig,
        BrowserActionResult,
        SourceDiscoveryResult,
    ]
):
    """Discover, extract, and finalize source tables in one current-state database."""

    action_output_model: ClassVar[type[BrowserActionResult]] = BrowserActionResult
    config_model: ClassVar[type[WorkflowStepSourceDiscoverConfig]] = WorkflowStepSourceDiscoverConfig
    result_model: ClassVar[type[SourceDiscoveryResult]] = SourceDiscoveryResult
    state_model: ClassVar[type[WorkflowStepCodexState]] = WorkflowStepCodexState
    step_key: ClassVar[str] = "source_discover"

    def __init__(
        self,
        *,
        artifact_materializer: ArtifactMaterializer,
        artifact_writer: JsonArtifactWriter,
        codex_runner: CodexRunner,
        prompt_renderer: PromptRenderer,
        runtime_policy: WorkflowStepCodexRuntimePolicy,
        sqlite_state_store: SqliteStateStore,
        validator: SourceDiscoveryValidator,
    ) -> None:
        """Store reusable runtime, SQLite, and validation dependencies.

        Args:
            artifact_materializer: External artifact tree materializer.
            artifact_writer: Atomic JSON artifact writer.
            codex_runner: Low-level Codex runner.
            prompt_renderer: Strict project prompt renderer.
            runtime_policy: Source-owned materialization and retry policy.
            sqlite_state_store: Shared current-state store.
            validator: Source-discovery mechanical validator.
        """

        super().__init__(
            artifact_materializer=artifact_materializer,
            artifact_writer=artifact_writer,
            codex_runner=codex_runner,
            prompt_renderer=prompt_renderer,
            runtime_policy=runtime_policy,
        )
        self._sqlite_state_store = sqlite_state_store
        self._validator = validator

    def artifact_prepare(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: SourceDiscoveryInput,
    ) -> None:
        """Prepare evidence, state tables, and exact action schemas.

        Args:
            execution_context: Current step context.
            step_input: Persisted source-discovery input.
        """

        shared_artifact_directory_prepare(Path(step_input.evidence_write_target.filesystem_path))
        state_database_path = state_database_path_get(execution_context.step_instance_dir)
        self._sqlite_state_store.initialize(state_database_path, list(SOURCE_DISCOVERY_TABLE_BY_NAME_MAP.values()))
        for table in SOURCE_DISCOVERY_TABLE_BY_NAME_MAP.values():
            self._artifact_writer.schema_write(
                execution_context.step_instance_dir / f"{table.name}.schema.json",
                table.record_model,
            )
        self._artifact_writer.schema_write(execution_context.step_instance_dir / "chart.schema.json", BrandSizeChart)

    def input_build(
        self,
        execution_context: WorkflowStepExecutionContext,
        input_source: SourceDiscoveryInputSource,
    ) -> SourceDiscoveryInput:
        """Build the immutable source-discovery input and evidence target.

        Args:
            execution_context: Current step context.
            input_source: Source-type workflow input.

        Returns:
            Persisted source-discovery input.
        """

        layout = ArtifactLayout(execution_context.result_dir)
        canonical_evidence_dir = layout.step_artifact_path(execution_context.step_instance_dir, Path("evidence"))
        external_evidence_dir = layout.external_step_artifact_dir(execution_context.step_instance_dir, Path("evidence"))
        return SourceDiscoveryInput(
            brand_input=input_source.brand_input,
            evidence_write_target=ArtifactWriteTarget(
                artifact_path=layout.artifact_path(canonical_evidence_dir),
                filesystem_path=layout.filesystem_path_get(external_evidence_dir),
            ),
            source_type=input_source.source_type,
            workflow_input_path=execution_context.workflow_input_path,
        )

    def result_from_action_build(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: SourceDiscoveryInput,
        action_output: BrowserActionResult,
    ) -> SourceDiscoveryResult:
        """Derive the public terminal outcome from finalized source-table rows.

        Args:
            execution_context: Current step context.
            step_input: Persisted source-discovery input.
            action_output: Browser action output.

        Returns:
            Public source-discovery handoff with its database handle.
        """

        _ = step_input
        table_list = self._sqlite_state_store.list(
            state_database_path_get(execution_context.step_instance_dir), SOURCE_DISCOVERY_TABLE
        )
        outcome = (
            "market_conflict"
            if any(table.state == "market_conflict" for table in table_list)
            else "table_available" if any(table.state == "accepted" for table in table_list) else "no_table"
        )
        return SourceDiscoveryResult(
            browsing_error_list=action_output.browsing_error_list,
            outcome=outcome,
            source_discovery_database_path=ArtifactLayout(execution_context.result_dir).artifact_path(
                state_database_path_get(execution_context.step_instance_dir)
            ),
        )

    def result_validate(
        self,
        execution_context: WorkflowStepExecutionContext,
        step_input: SourceDiscoveryInput,
        result: SourceDiscoveryResult,
    ) -> None:
        """Mechanically validate the public handoff against current SQLite state.

        Args:
            execution_context: Current step context.
            step_input: Persisted source-discovery input.
            result: Candidate public handoff.
        """

        self._validator.validate(execution_context=execution_context, step_input=step_input, result=result)
