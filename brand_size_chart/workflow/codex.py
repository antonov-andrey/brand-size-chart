"""Shared Codex-backed DBOS workflow owner."""

from dbos import DBOSConfiguredInstance

from workflow_container_runtime.codex import CodexStageRunner


class BrandSizeChartCodexWorkflow(DBOSConfiguredInstance):
    """Own shared DBOS and Codex dependencies for brand size-chart workflows."""

    def __init__(self) -> None:
        """Register stable DBOS workflow dependencies."""

        super().__init__("default")
        self._codex_stage_runner = CodexStageRunner(workflow_container_name="brand-size-chart")
