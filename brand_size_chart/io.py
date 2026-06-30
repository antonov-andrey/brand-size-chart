"""Filesystem and input boundaries for brand size-chart workflow artifacts."""

import json
import re
from pathlib import Path

from pydantic import BaseModel

from brand_size_chart.identifier import dbos_identifier_component
from brand_size_chart.model import BrandInput, BrandListParseResult, BrandListParseWarning

WHITESPACE_RE = re.compile(r"\s+")


def brand_list_parse(brand_list_text: str) -> BrandListParseResult:
    """Parse brand-list text into deduplicated brand inputs.

    Args:
        brand_list_text: Raw `brand_list` text.

    Returns:
        Parsed brand list and warnings.
    """
    brand_by_key_map: dict[str, BrandInput] = {}
    raw_name_list_by_key_map: dict[str, list[str]] = {}
    source_line_number_by_key_map: dict[str, int] = {}
    warning_list: list[BrandListParseWarning] = []

    for line_number, raw_line in enumerate(brand_list_text.splitlines(), start=1):
        brand_name = WHITESPACE_RE.sub(" ", raw_line.strip())
        if not brand_name:
            continue
        if brand_name.startswith("#"):
            continue

        try:
            parsed_brand_key = dbos_identifier_component(brand_name)
        except ValueError as exc:
            warning_list.append(
                BrandListParseWarning(
                    warning_type="invalid_brand",
                    message=str(exc),
                    raw_brand_name=brand_name,
                    source_line_number=line_number,
                )
            )
            continue

        raw_name_list_by_key_map.setdefault(parsed_brand_key, []).append(brand_name)
        if parsed_brand_key in brand_by_key_map:
            continue

        source_line_number_by_key_map[parsed_brand_key] = line_number
        brand_by_key_map[parsed_brand_key] = BrandInput(
            parsed_brand_key=parsed_brand_key,
            parsed_brand_name=brand_name,
            raw_brand_name=brand_name,
            source_line_number=line_number,
        )

    for parsed_brand_key, raw_name_list in raw_name_list_by_key_map.items():
        if len(raw_name_list) <= 1:
            continue
        warning_list.append(
            BrandListParseWarning(
                warning_type="duplicate_brand",
                message="Duplicate brand skipped after identifier normalization.",
                raw_brand_name=raw_name_list[0],
                raw_brand_name_list=raw_name_list,
                source_line_number=source_line_number_by_key_map[parsed_brand_key],
                parsed_brand_key=parsed_brand_key,
            )
        )

    return BrandListParseResult(brand_list=list(brand_by_key_map.values()), warning_list=warning_list)


def json_artifact_write(path: Path, payload: BaseModel | dict[str, object]) -> None:
    """Write one JSON artifact with deterministic formatting.

    Args:
        path: Artifact path to write.
        payload: Pydantic model or JSON-compatible dictionary payload.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, BaseModel):
        json_payload = payload.model_dump(mode="json")
    else:
        json_payload = payload
    path.write_text(json.dumps(json_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
