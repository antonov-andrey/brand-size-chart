"""Composition root for reusable workflow, step, and runtime owners."""

from pathlib import Path

from workflow_container_runtime import WorkflowControlClient, WorkflowControlRequestBuilder
from workflow_container_runtime.artifact import (
    ArtifactMaterializationPolicy,
    ArtifactMaterializer,
    JsonArtifactWriter,
    JsonLinesArtifactWriter,
)
from workflow_container_runtime.codex import CodexRunner
from workflow_container_runtime.mcp_playwright_profile import McpPlaywrightProfileRuntime
from workflow_container_runtime.prompt import PromptRenderer
from workflow_container_runtime.state import SqliteStateStore
from workflow_container_runtime.step import CodexExecutionRetryPolicy, WorkflowStepCodexRuntimePolicy

from brand_size_chart.step import (
    BrandOutputStep,
    CanonicalSelectionDefaultStep,
    CanonicalSelectionStep,
    CoverageDecisionDefaultStep,
    CoverageDecisionStep,
    SourceDiscoveryStep,
)
from brand_size_chart.source.discovery_database import SourceDiscoveryDatabaseReader
from brand_size_chart.validator import (
    BrandOutputValidator,
    CanonicalSelectionValidator,
    CoverageDecisionValidator,
    SourceDiscoveryValidator,
)
from brand_size_chart.workflow import (
    BrandSizeChartBrandWorkflow,
    BrandSizeChartRunWorkflow,
)


class BrandSizeChartApplication:
    """Construct the complete stateless workflow object graph once."""

    def __init__(
        self,
        *,
        control_client: WorkflowControlClient,
        control_request_builder: WorkflowControlRequestBuilder,
    ) -> None:
        """Build shared runtime services, concrete steps, and DBOS workflows.

        Args:
            control_client: Current execution-local platform control adapter.
            control_request_builder: Exact source-declared control request builder.
        """

        artifact_materializer = ArtifactMaterializer()
        artifact_writer = JsonArtifactWriter()
        json_lines_artifact_writer = JsonLinesArtifactWriter()
        prompt_renderer = PromptRenderer(
            template_dir=Path(__file__).resolve().parents[1] / "prompt" / "template",
        )
        codex_runner = CodexRunner(
            artifact_writer=artifact_writer,
            prompt_renderer=prompt_renderer,
            workflow_container_name="brand-size-chart",
        )
        mcp_playwright_profile_runtime = McpPlaywrightProfileRuntime(
            workflow_control_client=control_client,
            workflow_control_request_builder=control_request_builder,
        )
        browser_step_runtime_policy = WorkflowStepCodexRuntimePolicy(
            artifact_materialization_policy=ArtifactMaterializationPolicy(
                artifact_root_tuple=(Path(".playwright-mcp/current"),),
            ),
            execution_retry_policy=CodexExecutionRetryPolicy(attempt_limit=2),
        )
        local_step_runtime_policy = WorkflowStepCodexRuntimePolicy(
            artifact_materialization_policy=ArtifactMaterializationPolicy(artifact_root_tuple=()),
            execution_retry_policy=CodexExecutionRetryPolicy(attempt_limit=2),
        )

        sqlite_state_store = SqliteStateStore()
        source_discovery_database_reader = SourceDiscoveryDatabaseReader()
        source_discovery_step = SourceDiscoveryStep(
            artifact_materializer=artifact_materializer,
            artifact_writer=artifact_writer,
            codex_runner=codex_runner,
            mcp_playwright_profile_runtime=mcp_playwright_profile_runtime,
            prompt_renderer=prompt_renderer,
            runtime_policy=browser_step_runtime_policy,
            sqlite_state_store=sqlite_state_store,
            validator=SourceDiscoveryValidator(sqlite_state_store=sqlite_state_store),
        )
        canonical_selection_validator = CanonicalSelectionValidator(
            source_discovery_database_reader=source_discovery_database_reader,
        )
        coverage_decision_validator = CoverageDecisionValidator(
            source_discovery_database_reader=source_discovery_database_reader,
        )
        brand_workflow = BrandSizeChartBrandWorkflow(
            artifact_writer=artifact_writer,
            brand_output_step=BrandOutputStep(
                artifact_writer=artifact_writer,
                json_lines_artifact_writer=json_lines_artifact_writer,
                source_discovery_database_reader=source_discovery_database_reader,
                validator=BrandOutputValidator(),
            ),
            canonical_selection_default_step=CanonicalSelectionDefaultStep(
                artifact_writer=artifact_writer,
                validator=canonical_selection_validator,
            ),
            canonical_selection_step=CanonicalSelectionStep(
                artifact_materializer=artifact_materializer,
                artifact_writer=artifact_writer,
                codex_runner=codex_runner,
                mcp_playwright_profile_runtime=mcp_playwright_profile_runtime,
                prompt_renderer=prompt_renderer,
                runtime_policy=local_step_runtime_policy,
                source_discovery_database_reader=source_discovery_database_reader,
                validator=canonical_selection_validator,
            ),
            config_name="brand",
            coverage_decision_default_step=CoverageDecisionDefaultStep(
                artifact_writer=artifact_writer,
                validator=coverage_decision_validator,
            ),
            coverage_decision_step=CoverageDecisionStep(
                artifact_materializer=artifact_materializer,
                artifact_writer=artifact_writer,
                codex_runner=codex_runner,
                mcp_playwright_profile_runtime=mcp_playwright_profile_runtime,
                prompt_renderer=prompt_renderer,
                runtime_policy=local_step_runtime_policy,
                validator=coverage_decision_validator,
            ),
            source_discovery_step=source_discovery_step,
        )
        self.root_workflow = BrandSizeChartRunWorkflow(
            artifact_writer=artifact_writer,
            brand_workflow=brand_workflow,
            config_name="run",
            control_client=control_client,
            control_request_builder=control_request_builder,
        )
