"""Behavior tests for read-only accepted source-discovery tables."""

import json
import sqlite3
from pathlib import Path

import pytest
from workflow_container_runtime.artifact import JsonArtifactWriter
from workflow_container_runtime.state import SqliteStateStore, state_database_path_get
import workflow_container_runtime.state.sqlite as state_sqlite

from brand_size_chart.app.source_discovery_read import main
from brand_size_chart.artifact import ArtifactLayout
from brand_size_chart.model import (
    BrandSizeChart,
    BrandSizeChartMeasurement,
    BrandSizeChartRow,
    BrandSourceTypeResultStepInput,
    SourceDiscoveryResult,
    SourceDiscoveryTable,
    SourceTypeResult,
)
from brand_size_chart.source.discovery_database import (
    SOURCE_DISCOVERY_TABLE,
    SOURCE_DISCOVERY_TABLE_BY_NAME_MAP,
    SourceDiscoveryDatabaseReader,
)


def test_reader_returns_only_accepted_rows_in_primary_key_order_with_derived_chart_paths(tmp_path: Path) -> None:
    """Read accepted rows in primary-key order without changing SQLite state."""

    step_dir = tmp_path / "workflow" / "run" / "source" / "source_discover"
    source_type_result = _state_write(tmp_path, step_dir)
    database_path = state_database_path_get(step_dir)
    database_state = (database_path.read_bytes(), database_path.stat().st_mtime_ns)

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
    assert (database_path.read_bytes(), database_path.stat().st_mtime_ns) == database_state


def test_reader_aggregates_only_successful_table_available_source_results(tmp_path: Path) -> None:
    """Ignore failed and non-table final source results during aggregate reads."""

    available_result = _state_write(tmp_path, tmp_path / "workflow" / "run" / "source" / "source_discover")
    no_table_result = _source_type_result_get(
        source_type="official_seller_size_guide",
        status="success",
        outcome="no_table",
        database_path="workflow/run/no-table/source_discover/state.sqlite3",
    )
    failed_result = _source_type_result_get(
        source_type="official_brand_product_page",
        status="failed",
        outcome="table_available",
        database_path="workflow/run/source/source_discover/state.sqlite3",
    )

    accepted_table_list = SourceDiscoveryDatabaseReader().accepted_table_list_get_for_source_type_result_list(
        result_dir=tmp_path,
        source_type_result_list=[available_result, no_table_result, failed_result],
    )

    assert [item.chart_path for item in accepted_table_list] == [
        "workflow/run/source/source_discover/chart/women_dress__eu.json",
        "workflow/run/source/source_discover/chart/women_dress__tr.json",
    ]


@pytest.mark.parametrize("outcome", ["no_table", "market_conflict"])
def test_reader_rejects_source_result_without_table_available_outcome(tmp_path: Path, outcome: str) -> None:
    """Reject final handoffs that cannot own accepted table rows."""

    with pytest.raises(RuntimeError, match="table_available"):
        SourceDiscoveryDatabaseReader().accepted_table_list_get(
            result_dir=tmp_path,
            source_type_result=_source_type_result_get(
                source_type="official_brand_size_guide",
                status="success",
                outcome=outcome,
                database_path="workflow/run/source/source_discover/state.sqlite3",
            ),
        )


def test_read_command_lists_one_selected_source_type_without_creating_artifacts(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Expose only accepted rows selected from the current persisted input."""

    source_type_result = _state_write(tmp_path, tmp_path / "workflow" / "run" / "source" / "source_discover")
    input_path = _input_path_write(tmp_path, [source_type_result])

    assert main([input_path.as_posix(), "official_brand_size_guide", "list-accepted"]) == 0

    assert [item["source_table"]["market_scope_key"] for item in json.loads(capsys.readouterr().out)] == ["eu", "tr"]


def test_reader_rejects_failed_complete_source_type_handoff(tmp_path: Path) -> None:
    """Reject a child handoff whose source-type workflow failed."""

    source_type_result = _state_write(tmp_path, tmp_path / "workflow" / "run" / "source" / "source_discover")
    failed_payload = source_type_result.model_dump()
    failed_payload["error_list"] = ["source failure"]
    failed_payload["status"] = "failed"
    failed_result = SourceTypeResult.model_validate(failed_payload)

    with pytest.raises(RuntimeError, match="successful complete SourceTypeResult"):
        SourceDiscoveryDatabaseReader().accepted_table_list_get(result_dir=tmp_path, source_type_result=failed_result)


def test_reader_rejects_table_available_handoff_without_accepted_rows(tmp_path: Path) -> None:
    """Reject contradictory available-table results with no accepted SQLite row."""

    step_dir = tmp_path / "workflow" / "run" / "source" / "source_discover"
    SqliteStateStore().initialize(state_database_path_get(step_dir), list(SOURCE_DISCOVERY_TABLE_BY_NAME_MAP.values()))

    with pytest.raises(RuntimeError, match="must contain accepted source tables"):
        SourceDiscoveryDatabaseReader().accepted_table_list_get(
            result_dir=tmp_path,
            source_type_result=_source_type_result_get(
                source_type="official_brand_size_guide",
                status="success",
                outcome="table_available",
                database_path=ArtifactLayout(tmp_path).artifact_path(state_database_path_get(step_dir)),
            ),
        )


@pytest.mark.parametrize("source_type", ["unknown_source", "official_brand_size_guide"])
def test_read_command_rejects_unknown_or_failed_source_handoff(tmp_path: Path, source_type: str) -> None:
    """Reject unselected and failed source handoffs through the console boundary."""

    source_type_result = _state_write(tmp_path, tmp_path / "workflow" / "run" / "source" / "source_discover")
    if source_type == "official_brand_size_guide":
        payload = source_type_result.model_dump()
        payload["error_list"] = ["source failure"]
        payload["status"] = "failed"
        source_type_result = SourceTypeResult.model_validate(payload)
    input_path = _input_path_write(tmp_path, [source_type_result])

    with pytest.raises(SystemExit):
        main([input_path.as_posix(), source_type, "list-accepted"])


def test_read_command_rejects_malformed_persisted_input(tmp_path: Path) -> None:
    """Reject an input artifact that does not satisfy the downstream schema."""

    input_path = tmp_path / "workflow" / "run" / "coverage" / "input.json"
    input_path.parent.mkdir(parents=True)
    input_path.write_text("{}", encoding="utf-8")

    with pytest.raises(SystemExit):
        main([input_path.as_posix(), "official_brand_size_guide", "list-accepted"])


@pytest.mark.parametrize("chart_state", ["missing", "invalid"])
def test_reader_rejects_missing_or_invalid_accepted_chart(tmp_path: Path, chart_state: str) -> None:
    """Reject accepted rows with a missing or malformed chart artifact."""

    step_dir = tmp_path / "workflow" / "run" / "source" / "source_discover"
    source_type_result = _state_write(tmp_path, step_dir)
    chart_path = ArtifactLayout(tmp_path).source_discovery_chart_path(step_dir, "women_dress", "eu")
    if chart_state == "missing":
        chart_path.unlink()
    else:
        chart_path.write_text("{}", encoding="utf-8")

    with pytest.raises(RuntimeError, match="missing or invalid"):
        SourceDiscoveryDatabaseReader().accepted_table_list_get(
            result_dir=tmp_path, source_type_result=source_type_result
        )


def test_reader_rejects_normalized_path_escape_and_incompatible_schema(tmp_path: Path) -> None:
    """Reject escaping database handles and incompatible declared SQLite artifacts."""

    step_dir = tmp_path / "workflow" / "run" / "source" / "source_discover"
    source_type_result = _state_write(tmp_path, step_dir)
    escaped_payload = source_type_result.model_dump()
    escaped_payload["source_discovery_result"][
        "source_discovery_database_path"
    ] = "workflow/run/source/../source/source_discover/state.sqlite3"
    with pytest.raises(RuntimeError, match="normalized"):
        SourceDiscoveryDatabaseReader().accepted_table_list_get(
            result_dir=tmp_path,
            source_type_result=SourceTypeResult.model_validate(escaped_payload),
        )

    database_path = state_database_path_get(step_dir)
    database_path.unlink()
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE source_table (size_group_key TEXT PRIMARY KEY)")
    with pytest.raises(RuntimeError):
        SourceDiscoveryDatabaseReader().accepted_table_list_get(
            result_dir=tmp_path, source_type_result=source_type_result
        )


def test_reader_and_cli_preserve_database_chart_and_input_bytes_and_mtimes(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Read through SQLite and CLI without changing input, database, or charts."""

    step_dir = tmp_path / "workflow" / "run" / "source" / "source_discover"
    source_type_result = _state_write(tmp_path, step_dir)
    input_path = _input_path_write(tmp_path, [source_type_result])
    artifact_path_list = [input_path, state_database_path_get(step_dir), *sorted((step_dir / "chart").glob("*.json"))]
    artifact_state_by_path = {
        artifact_path: (artifact_path.read_bytes(), artifact_path.stat().st_mtime_ns)
        for artifact_path in artifact_path_list
    }
    sqlite_connect = sqlite3.connect
    read_only_database_uri_list: list[str] = []

    def connection_get(database: str | Path, *args: object, **kwargs: object) -> sqlite3.Connection:
        """Confirm every URI-backed downstream connection rejects writes."""

        connection = sqlite_connect(database, *args, **kwargs)
        if kwargs.get("uri"):
            read_only_database_uri_list.append(str(database))
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                connection.execute("DELETE FROM source_table")
        return connection

    monkeypatch.setattr(state_sqlite.sqlite3, "connect", connection_get)
    SourceDiscoveryDatabaseReader().accepted_table_list_get(result_dir=tmp_path, source_type_result=source_type_result)
    assert main([input_path.as_posix(), "official_brand_size_guide", "list-accepted"]) == 0
    capsys.readouterr()

    assert {
        artifact_path: (artifact_path.read_bytes(), artifact_path.stat().st_mtime_ns)
        for artifact_path in artifact_path_list
    } == artifact_state_by_path
    assert read_only_database_uri_list
    assert all("mode=ro" in database_uri for database_uri in read_only_database_uri_list)


def test_read_command_rejects_duplicate_sources_missing_or_ambiguous_roots_and_extra_arguments(tmp_path: Path) -> None:
    """Reject duplicate persisted source results, root ambiguity, and extra CLI options."""

    step_dir = tmp_path / "workflow" / "run" / "source" / "source_discover"
    source_type_result = _state_write(tmp_path, step_dir)
    input_path = _input_path_write(tmp_path, [source_type_result])
    duplicate_payload = BrandSourceTypeResultStepInput(
        source_type_result_list=[source_type_result], workflow_input_path=Path("workflow/run/input.json")
    ).model_dump(mode="json")
    duplicate_payload["source_type_result_list"].append(source_type_result.model_dump())
    input_path.write_text(json.dumps(duplicate_payload), encoding="utf-8")
    with pytest.raises(SystemExit):
        main([input_path.as_posix(), "official_brand_size_guide", "list-accepted"])

    input_path = _input_path_write(tmp_path, [source_type_result])
    missing_root_path = tmp_path / "isolated" / "input.json"
    missing_root_path.parent.mkdir()
    missing_payload = source_type_result.model_dump()
    missing_payload["source_discovery_result"]["source_discovery_database_path"] = "missing/state.sqlite3"
    missing_root_path.write_text(
        BrandSourceTypeResultStepInput(
            source_type_result_list=[SourceTypeResult.model_validate(missing_payload)],
            workflow_input_path=Path("workflow/run/input.json"),
        ).model_dump_json(),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        main([missing_root_path.as_posix(), "official_brand_size_guide", "list-accepted"])

    ambiguous_path = input_path.parent / source_type_result.source_discovery_result.source_discovery_database_path
    ambiguous_path.parent.mkdir(parents=True)
    ambiguous_path.write_bytes(state_database_path_get(step_dir).read_bytes())
    with pytest.raises(SystemExit):
        main([input_path.as_posix(), "official_brand_size_guide", "list-accepted"])
    for extra_argument_list in (["--database", "x"], ["--filter", "accepted"], ["--write"]):
        with pytest.raises(SystemExit):
            main([input_path.as_posix(), "official_brand_size_guide", "list-accepted", *extra_argument_list])


def _chart_get() -> BrandSizeChart:
    """Build one valid source chart."""

    return BrandSizeChart(
        description="Source chart.",
        row_list=[
            BrandSizeChartRow(
                measurement_list=[BrandSizeChartMeasurement(max_value="M", min_value="M", name="Size", unit="size")],
                size_label="M",
            )
        ],
    )


def _input_path_write(result_dir: Path, source_type_result_list: list[SourceTypeResult]) -> Path:
    """Persist the current downstream handoff input under the result tree."""

    input_path = result_dir / "workflow" / "run" / "coverage" / "input.json"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text(
        BrandSourceTypeResultStepInput(
            source_type_result_list=source_type_result_list,
            workflow_input_path=Path("workflow/run/input.json"),
        ).model_dump_json(),
        encoding="utf-8",
    )
    return input_path


def _source_type_result_get(*, database_path: str, outcome: str, source_type: str, status: str) -> SourceTypeResult:
    """Build one complete source-type handoff with the supplied final outcome."""

    return SourceTypeResult(
        error_list=[] if status == "success" else ["source failure"],
        source_discovery_result=SourceDiscoveryResult(
            browsing_error_list=[], outcome=outcome, source_discovery_database_path=database_path
        ),
        source_type=source_type,
        status=status,
        warning_list=[],
    )


def _state_write(result_dir: Path, step_dir: Path) -> SourceTypeResult:
    """Write accepted rows and their valid chart artifacts."""

    store = SqliteStateStore()
    database_path = state_database_path_get(step_dir)
    store.initialize(database_path, list(SOURCE_DISCOVERY_TABLE_BY_NAME_MAP.values()))
    for market_scope_key in ["eu", "tr"]:
        source_table = SourceDiscoveryTable(
            evidence_path_list=["workflow/run/source/evidence/table.json"],
            market_scope_key=market_scope_key,
            reason="Official source table.",
            size_group_key="women_dress",
            source_title="Women dress chart",
            source_url="https://brand.example/size",
            state="accepted",
        )
        store.upsert(database_path, SOURCE_DISCOVERY_TABLE, source_table)
        JsonArtifactWriter().write(
            ArtifactLayout(result_dir).source_discovery_chart_path(
                step_dir, source_table.size_group_key, source_table.market_scope_key
            ),
            _chart_get(),
        )
    return _source_type_result_get(
        database_path=ArtifactLayout(result_dir).artifact_path(database_path),
        outcome="table_available",
        source_type="official_brand_size_guide",
        status="success",
    )
