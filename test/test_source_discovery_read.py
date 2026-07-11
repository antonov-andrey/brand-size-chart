"""Behavior tests for read-only accepted source-discovery tables."""

from pathlib import Path
import json
import sqlite3

import pytest
from workflow_container_runtime.artifact import JsonArtifactWriter
from workflow_container_runtime.state import SqliteStateStore, state_database_path_get
import workflow_container_runtime.state.sqlite as state_sqlite

from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import (
    BrandSizeChart,
    BrandSizeChartMeasurement,
    BrandSizeChartRow,
    SourceDiscoveryResult,
    SourceDiscoveryTable,
    SourceTypeResult,
)
from brand_size_chart.source.discovery_database import (
    SOURCE_DISCOVERY_TABLE,
    SOURCE_DISCOVERY_TABLE_BY_NAME_MAP,
    SourceDiscoveryDatabaseReader,
)
from brand_size_chart.app.source_discovery_read import main
from brand_size_chart.model import BrandInput, BrandSourceTypeResultStepInput, BrandWorkflowInput, PromptScope


def _chart_get() -> BrandSizeChart:
    """Build one valid source chart.

    Returns:
        Valid source chart fixture.
    """

    return BrandSizeChart(
        description="Source chart.",
        row_list=[
            BrandSizeChartRow(
                measurement_list=[
                    BrandSizeChartMeasurement(max_value="M", min_value="M", name="Size", unit="size"),
                ],
                size_label="M",
            )
        ],
    )


def _source_type_result_get(result_dir: Path, step_dir: Path) -> SourceTypeResult:
    """Build one table-available source result.

    Args:
        result_dir: Absolute workflow result root.
        step_dir: Owning source-discovery step directory.

    Returns:
        Complete successful source-type result.
    """

    return SourceTypeResult(
        error_list=[],
        source_discovery_result=SourceDiscoveryResult(
            browsing_error_list=[],
            outcome="table_available",
            source_discovery_database_path=ArtifactLayout(result_dir).artifact_path(state_database_path_get(step_dir)),
        ),
        source_type="official_brand_size_guide",
        status="success",
        warning_list=[],
    )


def _state_write(result_dir: Path, step_dir: Path) -> SourceTypeResult:
    """Write one accepted source database and chart fixture.

    Args:
        result_dir: Absolute workflow result root.
        step_dir: Owning source-discovery step directory.

    Returns:
        Complete source result for the written database.
    """

    store = SqliteStateStore()
    database_path = state_database_path_get(step_dir)
    store.initialize(database_path, list(SOURCE_DISCOVERY_TABLE_BY_NAME_MAP.values()))
    for market_scope_key in ["eu", "tr"]:
        table = SourceDiscoveryTable(
            evidence_path_list=["workflow/run/source/evidence/table.json"],
            market_scope_key=market_scope_key,
            reason="Official source table.",
            size_group_key="women_dress",
            source_title="Women dress chart",
            source_url="https://brand.example/size",
            state="accepted",
        )
        store.upsert(database_path, SOURCE_DISCOVERY_TABLE, table)
        JsonArtifactWriter().write(
            ArtifactLayout(result_dir).source_discovery_chart_path(
                step_dir,
                table.size_group_key,
                table.market_scope_key,
            ),
            _chart_get(),
        )
    return _source_type_result_get(result_dir, step_dir)


def test_reader_returns_only_accepted_rows_in_primary_key_order_with_derived_chart_paths(tmp_path: Path) -> None:
    """Read accepted rows through the declared database handle without mutation.

    Args:
        tmp_path: Isolated result root.
    """

    step_dir = tmp_path / "workflow" / "run" / "source" / "source_discover"
    source_type_result = _state_write(tmp_path, step_dir)
    database_path = state_database_path_get(step_dir)
    database_bytes = database_path.read_bytes()
    database_mtime_ns = database_path.stat().st_mtime_ns

    accepted_table_list = SourceDiscoveryDatabaseReader().accepted_table_list_get(
        result_dir=tmp_path,
        source_type_result=source_type_result,
    )

    assert [
        (item.chart_path, item.source_priority, item.source_table.market_scope_key) for item in accepted_table_list
    ] == [
        ("workflow/run/source/source_discover/chart/women_dress__eu.json", 600, "eu"),
        ("workflow/run/source/source_discover/chart/women_dress__tr.json", 600, "tr"),
    ]
    assert database_path.read_bytes() == database_bytes
    assert database_path.stat().st_mtime_ns == database_mtime_ns


def test_reader_aggregates_only_successful_table_available_source_results(tmp_path: Path) -> None:
    """Read accepted rows only from successful table-available source results.

    Args:
        tmp_path: Isolated result root.
    """

    table_available_result = _state_write(tmp_path, tmp_path / "workflow" / "run" / "source" / "source_discover")
    no_table_result = table_available_result.model_copy(
        update={
            "source_type": "official_seller_size_guide",
            "source_discovery_result": table_available_result.source_discovery_result.model_copy(
                update={"outcome": "no_table", "source_discovery_database_path": "workflow/run/no-table/state.sqlite3"}
            ),
        }
    )
    failed_result = table_available_result.model_copy(
        update={"source_type": "official_brand_product_page", "source_discovery_result": None, "status": "failed"}
    )

    accepted_table_list = SourceDiscoveryDatabaseReader().accepted_table_list_get_for_source_type_result_list(
        result_dir=tmp_path,
        source_type_result_list=[table_available_result, no_table_result, failed_result],
    )

    assert [accepted_table.chart_path for accepted_table in accepted_table_list] == [
        "workflow/run/source/source_discover/chart/women_dress__eu.json",
        "workflow/run/source/source_discover/chart/women_dress__tr.json",
    ]


@pytest.mark.parametrize("outcome", ["no_table", "market_conflict"])
def test_reader_rejects_source_result_without_table_available_outcome(tmp_path: Path, outcome: str) -> None:
    """Reject result handles that cannot provide accepted table rows.

    Args:
        tmp_path: Isolated result root.
        outcome: Non-readable terminal source-discovery outcome.
    """

    source_type_result = SourceTypeResult(
        error_list=[],
        source_discovery_result=SourceDiscoveryResult(
            browsing_error_list=[],
            outcome=outcome,
            source_discovery_database_path="workflow/run/source/source_discover/state.sqlite3",
        ),
        source_type="official_brand_size_guide",
        status="success",
        warning_list=[],
    )

    with pytest.raises(RuntimeError, match="table_available"):
        SourceDiscoveryDatabaseReader().accepted_table_list_get(
            result_dir=tmp_path,
            source_type_result=source_type_result,
        )


def test_read_command_lists_one_selected_source_type_without_creating_artifacts(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Expose only accepted rows selected through current persisted input.

    Args:
        capsys: Captured console streams.
        tmp_path: Isolated result root.
    """

    source_type_result = _state_write(tmp_path, tmp_path / "workflow" / "run" / "source" / "source_discover")
    input_path = tmp_path / "workflow" / "run" / "coverage" / "input.json"
    input_path.parent.mkdir(parents=True)
    input_path.write_text(
        BrandSourceTypeResultStepInput(
            source_type_result_list=[source_type_result],
            workflow_input=BrandWorkflowInput(
                brand_input=BrandInput(
                    parsed_brand_key="brand",
                    parsed_brand_name="Brand",
                    raw_brand_name="Brand",
                    source_line_number=1,
                ),
                prompt_scope=PromptScope(),
            ),
        ).model_dump_json(),
        encoding="utf-8",
    )

    assert main([input_path.as_posix(), "official_brand_size_guide", "list-accepted"]) == 0

    assert [item["source_table"]["market_scope_key"] for item in json.loads(capsys.readouterr().out)] == ["eu", "tr"]


def test_reader_rejects_failed_complete_source_type_handoff(tmp_path: Path) -> None:
    """Reject a table handoff whose child workflow did not succeed.

    Args:
        tmp_path: Isolated result root.
    """

    source_type_result = _state_write(tmp_path, tmp_path / "workflow" / "run" / "source" / "source_discover")

    with pytest.raises(RuntimeError, match="successful complete SourceTypeResult"):
        SourceDiscoveryDatabaseReader().accepted_table_list_get(
            result_dir=tmp_path,
            source_type_result=source_type_result.model_copy(update={"status": "failed"}),
        )


def test_reader_rejects_table_available_handoff_without_accepted_rows(tmp_path: Path) -> None:
    """Reject a contradictory available-table result with no accepted database rows.

    Args:
        tmp_path: Isolated result root.
    """

    step_dir = tmp_path / "workflow" / "run" / "source" / "source_discover"
    database_path = state_database_path_get(step_dir)
    SqliteStateStore().initialize(database_path, list(SOURCE_DISCOVERY_TABLE_BY_NAME_MAP.values()))
    source_type_result = _source_type_result_get(tmp_path, step_dir)

    with pytest.raises(RuntimeError, match="must contain accepted source tables"):
        SourceDiscoveryDatabaseReader().accepted_table_list_get(
            result_dir=tmp_path,
            source_type_result=source_type_result,
        )


@pytest.mark.parametrize("source_type", ["unknown_source", "official_brand_size_guide"])
def test_read_command_rejects_unknown_or_failed_source_handoff(tmp_path: Path, source_type: str) -> None:
    """Fail the command for a non-selected source or failed selected result.

    Args:
        tmp_path: Isolated result root.
        source_type: Requested command source type.
    """

    source_type_result = _state_write(tmp_path, tmp_path / "workflow" / "run" / "source" / "source_discover")
    if source_type == "official_brand_size_guide":
        source_type_result = source_type_result.model_copy(update={"status": "failed"})
    input_path = tmp_path / "workflow" / "run" / "coverage" / "input.json"
    input_path.parent.mkdir(parents=True)
    input_path.write_text(
        BrandSourceTypeResultStepInput(
            source_type_result_list=[source_type_result],
            workflow_input=BrandWorkflowInput(
                brand_input=BrandInput(
                    parsed_brand_key="brand",
                    parsed_brand_name="Brand",
                    raw_brand_name="Brand",
                    source_line_number=1,
                ),
                prompt_scope=PromptScope(),
            ),
        ).model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit):
        main([input_path.as_posix(), source_type, "list-accepted"])


def test_read_command_rejects_malformed_persisted_input(tmp_path: Path) -> None:
    """Reject a current input artifact that does not satisfy the downstream schema.

    Args:
        tmp_path: Isolated result root.
    """

    input_path = tmp_path / "workflow" / "run" / "coverage" / "input.json"
    input_path.parent.mkdir(parents=True)
    input_path.write_text("{}", encoding="utf-8")

    with pytest.raises(SystemExit):
        main([input_path.as_posix(), "official_brand_size_guide", "list-accepted"])


@pytest.mark.parametrize("chart_state", ["missing", "invalid"])
def test_reader_rejects_missing_or_invalid_accepted_chart(tmp_path: Path, chart_state: str) -> None:
    """Reject an accepted database row without a valid chart artifact.

    Args:
        tmp_path: Isolated result root.
        chart_state: Chart failure to introduce.
    """

    step_dir = tmp_path / "workflow" / "run" / "source" / "source_discover"
    source_type_result = _state_write(tmp_path, step_dir)
    chart_path = ArtifactLayout(tmp_path).source_discovery_chart_path(step_dir, "women_dress", "eu")
    if chart_state == "missing":
        chart_path.unlink()
    else:
        chart_path.write_text("{}", encoding="utf-8")

    with pytest.raises(RuntimeError, match="missing or invalid"):
        SourceDiscoveryDatabaseReader().accepted_table_list_get(
            result_dir=tmp_path,
            source_type_result=source_type_result,
        )


def test_reader_rejects_normalized_path_escape_and_incompatible_schema(tmp_path: Path) -> None:
    """Reject escaped handles and a declared SQLite file with an incompatible schema.

    Args:
        tmp_path: Isolated result root.
    """

    step_dir = tmp_path / "workflow" / "run" / "source" / "source_discover"
    source_type_result = _state_write(tmp_path, step_dir)
    escaped_source_type_result = source_type_result.model_copy(
        update={
            "source_discovery_result": source_type_result.source_discovery_result.model_copy(
                update={"source_discovery_database_path": "workflow/run/source/../source/source_discover/state.sqlite3"}
            )
        }
    )
    with pytest.raises(RuntimeError, match="normalized"):
        SourceDiscoveryDatabaseReader().accepted_table_list_get(
            result_dir=tmp_path,
            source_type_result=escaped_source_type_result,
        )

    database_path = state_database_path_get(step_dir)
    database_path.unlink()
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE source_table (size_group_key TEXT PRIMARY KEY)")
    with pytest.raises(RuntimeError):
        SourceDiscoveryDatabaseReader().accepted_table_list_get(
            result_dir=tmp_path,
            source_type_result=source_type_result,
        )


def test_reader_and_cli_preserve_database_chart_and_input_bytes_and_mtimes(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Read accepted rows without changing any declared input, database, or chart artifact.

    Args:
        capsys: Captured console output.
        tmp_path: Isolated result root.
    """

    step_dir = tmp_path / "workflow" / "run" / "source" / "source_discover"
    source_type_result = _state_write(tmp_path, step_dir)
    input_path = tmp_path / "workflow" / "run" / "coverage" / "input.json"
    input_path.parent.mkdir(parents=True)
    input_path.write_text(
        BrandSourceTypeResultStepInput(
            source_type_result_list=[source_type_result],
            workflow_input=BrandWorkflowInput(
                brand_input=BrandInput(
                    parsed_brand_key="brand",
                    parsed_brand_name="Brand",
                    raw_brand_name="Brand",
                    source_line_number=1,
                ),
                prompt_scope=PromptScope(),
            ),
        ).model_dump_json(),
        encoding="utf-8",
    )
    artifact_path_list = [input_path, state_database_path_get(step_dir), *sorted((step_dir / "chart").glob("*.json"))]
    artifact_state_by_path = {
        artifact_path: (artifact_path.read_bytes(), artifact_path.stat().st_mtime_ns)
        for artifact_path in artifact_path_list
    }
    sqlite_connect = sqlite3.connect
    read_only_connection_uri_list: list[str] = []

    def connection_get(database: str | Path, *args: object, **kwargs: object) -> sqlite3.Connection:
        """Verify each downstream SQLite connection cannot write before continuing.

        Args:
            database: SQLite location passed by the state reader.
            args: Positional SQLite connection arguments.
            kwargs: Keyword SQLite connection arguments.

        Returns:
            Real SQLite connection after read-only write rejection.
        """

        connection = sqlite_connect(database, *args, **kwargs)
        if kwargs.get("uri"):
            read_only_connection_uri_list.append(str(database))
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                connection.execute("DELETE FROM source_table")
        return connection

    monkeypatch.setattr(state_sqlite.sqlite3, "connect", connection_get)

    SourceDiscoveryDatabaseReader().accepted_table_list_get(
        result_dir=tmp_path,
        source_type_result=source_type_result,
    )
    assert main([input_path.as_posix(), "official_brand_size_guide", "list-accepted"]) == 0
    capsys.readouterr()

    assert {
        artifact_path: (artifact_path.read_bytes(), artifact_path.stat().st_mtime_ns)
        for artifact_path in artifact_path_list
    } == artifact_state_by_path
    assert read_only_connection_uri_list
    assert all("mode=ro" in database_uri for database_uri in read_only_connection_uri_list)


def test_read_command_rejects_duplicate_sources_missing_or_ambiguous_roots_and_extra_arguments(tmp_path: Path) -> None:
    """Reject invalid selection inputs and unsupported command arguments without side effects.

    Args:
        tmp_path: Isolated result root.
    """

    step_dir = tmp_path / "workflow" / "run" / "source" / "source_discover"
    source_type_result = _state_write(tmp_path, step_dir)
    input_path = tmp_path / "workflow" / "run" / "coverage" / "input.json"
    input_path.parent.mkdir(parents=True)
    workflow_input = BrandWorkflowInput(
        brand_input=BrandInput(
            parsed_brand_key="brand",
            parsed_brand_name="Brand",
            raw_brand_name="Brand",
            source_line_number=1,
        ),
        prompt_scope=PromptScope(),
    )
    duplicate_payload = {
        "source_type_result_list": [source_type_result.model_dump(), source_type_result.model_dump()],
        "workflow_input": workflow_input.model_dump(),
    }
    input_path.write_text(json.dumps(duplicate_payload), encoding="utf-8")
    with pytest.raises(SystemExit):
        main([input_path.as_posix(), "official_brand_size_guide", "list-accepted"])

    input_path.write_text(
        BrandSourceTypeResultStepInput(
            source_type_result_list=[source_type_result], workflow_input=workflow_input
        ).model_dump_json(),
        encoding="utf-8",
    )
    missing_root_path = tmp_path / "isolated" / "input.json"
    missing_root_path.parent.mkdir()
    missing_root_path.write_text(
        BrandSourceTypeResultStepInput(
            source_type_result_list=[
                source_type_result.model_copy(
                    update={
                        "source_discovery_result": source_type_result.source_discovery_result.model_copy(
                            update={"source_discovery_database_path": "missing/state.sqlite3"}
                        )
                    }
                )
            ],
            workflow_input=workflow_input,
        ).model_dump_json(),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        main([missing_root_path.as_posix(), "official_brand_size_guide", "list-accepted"])

    ambiguous_database_path = (
        input_path.parent / source_type_result.source_discovery_result.source_discovery_database_path
    )
    ambiguous_database_path.parent.mkdir(parents=True)
    ambiguous_database_path.write_bytes(state_database_path_get(step_dir).read_bytes())
    with pytest.raises(SystemExit):
        main([input_path.as_posix(), "official_brand_size_guide", "list-accepted"])

    for extra_argument_list in (["--database", "x"], ["--filter", "accepted"], ["--write"]):
        with pytest.raises(SystemExit):
            main([input_path.as_posix(), "official_brand_size_guide", "list-accepted", *extra_argument_list])
