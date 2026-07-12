"""SQLite-backed browser source-discovery step."""

import asyncio
from pathlib import Path
from typing import ClassVar

from dbos import DBOS
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
    StepResultValidationError,
    WorkflowStepCodexConcurrentBase,
    WorkflowStepCodexRuntimePolicy,
    WorkflowStepCodexState,
    WorkflowStepExecutionContext,
    WorkflowStepInvocation,
)

from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import (
    ArtifactWriteTarget,
    BrandSizeChart,
    SourceDiscoveryInput,
    SourceDiscoveryResult,
    SourceDiscoveryInputSource,
    SourceTypeResult,
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

    async def source_type_result_list_get(
        self,
        invocation_list: list[WorkflowStepInvocation[SourceDiscoveryInputSource]],
        workflow_step_config: WorkflowStepSourceDiscoverConfig,
    ) -> list[SourceTypeResult]:
        """Run independent discovery work and retain validation failures per source.

        Args:
            invocation_list: Registry-ordered independent source invocations.
            workflow_step_config: Exact concurrent configuration selected by the workflow.

        Returns:
            One source-type result per invocation in registry order.

        Raises:
            BaseException: The first non-validation invocation failure in registry order.
        """

        if not invocation_list:
            raise ValueError("invocation_list must not be empty")
        self._workflow_step_config_type_validate(workflow_step_config)
        semaphore = asyncio.Semaphore(workflow_step_config.concurrency)

        async def source_discovery_result_get(
            invocation: WorkflowStepInvocation[SourceDiscoveryInputSource],
        ) -> SourceDiscoveryResult:
            """Run one independent DBOS source-discovery step under the configured bound.

            Args:
                invocation: One source-specific execution context and stable input source.

            Returns:
                Accepted source-discovery result.
            """

            async with semaphore:
                return await DBOS.run_step_async(
                    {"name": f"{type(self).__name__}.run"},
                    self.run,
                    invocation.execution_context,
                    invocation.input_source,
                    workflow_step_config,
                )

        result_or_error_list = await asyncio.gather(
            *(asyncio.create_task(source_discovery_result_get(invocation)) for invocation in invocation_list),
            return_exceptions=True,
        )
        source_type_result_list: list[SourceTypeResult] = []
        for invocation, result_or_error in zip(invocation_list, result_or_error_list, strict=True):
            source_type = invocation.input_source.source_type
            if isinstance(result_or_error, StepResultValidationError):
                source_type_result_list.append(
                    SourceTypeResult(
                        error_list=[f"{type(result_or_error).__name__}: {result_or_error}"],
                        source_discovery_result=None,
                        source_type=source_type,
                        status="failed",
                        warning_list=[],
                    )
                )
                continue
            if isinstance(result_or_error, BaseException):
                raise result_or_error
            source_type_result_list.append(
                SourceTypeResult(
                    error_list=(
                        ["Source discovery market conflict."] if result_or_error.outcome == "market_conflict" else []
                    ),
                    source_discovery_result=result_or_error,
                    source_type=source_type,
                    status="failed" if result_or_error.outcome == "market_conflict" else "success",
                    warning_list=[],
                )
            )
        return source_type_result_list
