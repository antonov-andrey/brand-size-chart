"""Tests for the source-discovery incremental JSONL append command."""

import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from workflow_container_runtime.artifact import JsonlArtifactStore

from brand_size_chart.app.source_discovery_jsonl_append import main
from brand_size_chart.model.source import SourceDiscoveryState, SourceSurfaceDiscoveryQuery, SourceSurfaceProductTypeSex

DISCOVERY_QUERY_PAYLOAD = {
    "entity_id": "query:official-size-guide",
    "evidence_path_list": [],
    "query": "site:brand.example size guide",
    "reason": "Searched the official site.",
    "record_id": "query:official-size-guide:r1",
    "revision_index": 1,
    "state": "searched",
    "supersedes_record_id": None,
}
PRODUCT_TYPE_SEX_PAYLOAD = {
    "entity_id": "worklist:women-shoes",
    "evidence_path_list": [],
    "product_type": "shoes",
    "reason": "Requested coverage.",
    "record_id": "worklist:women-shoes:r1",
    "revision_index": 1,
    "sex": "women",
    "state": "pending",
    "supersedes_record_id": None,
    "worklist_key": "women_shoes",
}
TABLE_PAYLOAD = {
    "entity_id": "table:women-shoes",
    "reason": "Visible official table.",
    "record_id": "table:women-shoes:r1",
    "revision_index": 1,
    "source_discovery": {
        "country_code_list": ["TR"],
        "evidence_path_list": [],
        "size_group_key": "women_shoes",
        "source_title": "Women shoes",
        "source_url": "https://brand.example/size",
    },
    "state": "accepted",
    "supersedes_record_id": None,
}
URL_PAYLOAD = {
    "entity_id": "url:https://brand.example/size",
    "evidence_path_list": [],
    "reason": "Opened the official guide.",
    "record_id": "url:https://brand.example/size:r1",
    "revision_index": 1,
    "state": "opened",
    "supersedes_record_id": None,
    "url": "https://brand.example/size",
    "worklist_key_list": ["women_shoes"],
}


def _state_path_write(step_dir: Path, **path_override_by_field: str) -> Path:
    """Write one valid source-discovery state file.

    Args:
        step_dir: Current source-discovery step directory.
        **path_override_by_field: Optional JSONL path overrides keyed by state field.

    Returns:
        Written state file path.
    """

    step_dir.mkdir(parents=True, exist_ok=True)
    state = SourceDiscoveryState(attempt_index=1, state="ready", **path_override_by_field)
    state_path = step_dir / "state.json"
    state_path.write_text(state.model_dump_json(), encoding="utf-8")
    return state_path


def _command_run(state_path: Path, record_type: str, payload: dict[str, object]) -> int:
    """Run the append command with one JSON object supplied through stdin.

    Args:
        state_path: Current source-discovery state path.
        record_type: Explicit record type selector.
        payload: JSON object to validate and append.

    Returns:
        Process exit code.
    """

    with patch("sys.stdin", StringIO(json.dumps(payload))):
        return main([str(state_path), record_type])


@pytest.mark.parametrize(
    ("record_type", "state_path_field", "relative_jsonl_path", "payload"),
    [
        (
            "discovery-query",
            "discovery_query_jsonl_path",
            "inventory/query.jsonl",
            DISCOVERY_QUERY_PAYLOAD,
        ),
        (
            "product-type-sex",
            "product_type_sex_worklist_jsonl_path",
            "inventory/product_type_sex.jsonl",
            PRODUCT_TYPE_SEX_PAYLOAD,
        ),
        ("table", "table_jsonl_path", "inventory/table.jsonl", TABLE_PAYLOAD),
        ("url", "url_jsonl_path", "inventory/url.jsonl", URL_PAYLOAD),
    ],
)
def test_command_validates_and_appends_the_selected_exact_record_model(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    record_type: str,
    state_path_field: str,
    relative_jsonl_path: str,
    payload: dict[str, object],
) -> None:
    """Validate each explicit record type and append it to its state-owned path."""

    step_dir = tmp_path / "source_discover"
    state_path = _state_path_write(step_dir, **{state_path_field: relative_jsonl_path})

    assert _command_run(state_path, record_type, payload) == 0

    target_path = step_dir / relative_jsonl_path
    assert json.loads(target_path.read_text(encoding="utf-8")) == payload
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == f"Accepted {record_type} record {payload['record_id']} at {target_path.resolve()}.\n"


def test_command_replay_is_idempotent(tmp_path: Path) -> None:
    """Keep one JSONL line when an identical record identity is replayed."""

    state_path = _state_path_write(tmp_path / "source_discover")

    assert _command_run(state_path, "discovery-query", DISCOVERY_QUERY_PAYLOAD) == 0
    assert _command_run(state_path, "discovery-query", DISCOVERY_QUERY_PAYLOAD) == 0

    target_path = state_path.parent / "discovery_query.jsonl"
    assert target_path.read_text(encoding="utf-8").splitlines() == [
        json.dumps(DISCOVERY_QUERY_PAYLOAD, separators=(",", ":"), sort_keys=True)
    ]


def test_command_preserves_shell_sensitive_text_from_stdin(tmp_path: Path) -> None:
    """Append apostrophes and quotes without placing JSON in one shell argument."""

    state_path = _state_path_write(tmp_path / "source_discover")
    payload = {
        **DISCOVERY_QUERY_PAYLOAD,
        "reason": 'The product page\'s "Questions and answers" surface was inspected.',
    }

    assert _command_run(state_path, "discovery-query", payload) == 0

    target_path = state_path.parent / "discovery_query.jsonl"
    assert JsonlArtifactStore().recover(target_path, SourceSurfaceDiscoveryQuery) == [
        SourceSurfaceDiscoveryQuery.model_validate(payload)
    ]


def test_command_appends_correction_revision_and_recovers_only_latest_value(tmp_path: Path) -> None:
    """Append one correction without rewriting history and recover its current value."""

    state_path = _state_path_write(tmp_path / "source_discover")
    corrected_payload = {
        **DISCOVERY_QUERY_PAYLOAD,
        "reason": "The official guide was unavailable after opening the result.",
        "record_id": "query:official-size-guide:r2",
        "revision_index": 2,
        "state": "failed",
        "supersedes_record_id": DISCOVERY_QUERY_PAYLOAD["record_id"],
    }

    assert _command_run(state_path, "discovery-query", DISCOVERY_QUERY_PAYLOAD) == 0
    assert _command_run(state_path, "discovery-query", corrected_payload) == 0

    target_path = state_path.parent / "discovery_query.jsonl"
    assert len(target_path.read_text(encoding="utf-8").splitlines()) == 2
    assert JsonlArtifactStore().recover(target_path, SourceSurfaceDiscoveryQuery) == [
        SourceSurfaceDiscoveryQuery.model_validate(corrected_payload)
    ]


def test_command_appends_pending_to_searched_worklist_revision(tmp_path: Path) -> None:
    """Preserve the initial pending worklist row before its searched revision."""

    state_path = _state_path_write(tmp_path / "source_discover")
    searched_payload = {
        **PRODUCT_TYPE_SEX_PAYLOAD,
        "evidence_path_list": ["evidence/product.json"],
        "reason": "The product boundary was inspected.",
        "record_id": "worklist:women-shoes:r2",
        "revision_index": 2,
        "state": "searched",
        "supersedes_record_id": PRODUCT_TYPE_SEX_PAYLOAD["record_id"],
    }

    assert _command_run(state_path, "product-type-sex", PRODUCT_TYPE_SEX_PAYLOAD) == 0
    assert _command_run(state_path, "product-type-sex", searched_payload) == 0

    target_path = state_path.parent / "product_type_sex_worklist.jsonl"
    assert len(target_path.read_text(encoding="utf-8").splitlines()) == 2
    assert JsonlArtifactStore().recover(target_path, SourceSurfaceProductTypeSex) == [
        SourceSurfaceProductTypeSex.model_validate(searched_payload)
    ]


def test_command_rejects_conflicting_record_identity(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Reject changed data for a record identity that already exists."""

    state_path = _state_path_write(tmp_path / "source_discover")
    assert _command_run(state_path, "discovery-query", DISCOVERY_QUERY_PAYLOAD) == 0
    conflicting_payload = {**DISCOVERY_QUERY_PAYLOAD, "reason": "Changed reason."}

    with pytest.raises(SystemExit) as exc_info:
        _command_run(state_path, "discovery-query", conflicting_payload)

    assert exc_info.value.code == 2
    assert "conflicting JSONL record_id" in capsys.readouterr().err
    target_path = state_path.parent / "discovery_query.jsonl"
    assert len(target_path.read_text(encoding="utf-8").splitlines()) == 1


def test_command_rejects_payload_invalid_for_selected_record_type(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Reject JSON that does not validate as the explicitly selected model."""

    state_path = _state_path_write(tmp_path / "source_discover")

    with pytest.raises(SystemExit) as exc_info:
        _command_run(state_path, "url", DISCOVERY_QUERY_PAYLOAD)

    assert exc_info.value.code == 2
    assert "invalid url JSON payload" in capsys.readouterr().err
    assert not (state_path.parent / "url.jsonl").exists()


def test_command_rejects_unknown_record_type(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Expose only the four explicit source-discovery record choices."""

    state_path = _state_path_write(tmp_path / "source_discover")

    with pytest.raises(SystemExit) as exc_info:
        _command_run(state_path, "generic-model", DISCOVERY_QUERY_PAYLOAD)

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "invalid choice" in captured.err
    assert "discovery-query" in captured.err
    assert "product-type-sex" in captured.err
    assert "table" in captured.err
    assert "url" in captured.err


def test_command_rejects_jsonl_path_that_resolves_outside_current_step_directory(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Reject a state-relative path that escapes through a directory symlink."""

    step_dir = tmp_path / "source_discover"
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (step_dir / "escaped").parent.mkdir(parents=True)
    (step_dir / "escaped").symlink_to(outside_dir, target_is_directory=True)
    state_path = _state_path_write(step_dir, table_jsonl_path="escaped/table.jsonl")

    with pytest.raises(SystemExit) as exc_info:
        _command_run(state_path, "table", TABLE_PAYLOAD)

    assert exc_info.value.code == 2
    assert "must remain inside the current step directory" in capsys.readouterr().err
    assert not (outside_dir / "table.jsonl").exists()
