"""Shared model base classes, literals, and validation constants."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict

from brand_size_chart.identifier import dbos_identifier_component

APPLICABILITY_STATUS_CANONICAL_SET = {
    "priority_country_official",
    "official_global",
    "official_eu_consensus",
    "official_cross_locale_consensus",
}
ApplicabilityStatus = Literal[
    "priority_country_official",
    "official_global",
    "official_eu_consensus",
    "official_cross_locale_consensus",
    "duplicate_exact",
    "duplicate_units_only",
    "market_conflict",
    "unknown_blocked",
]
StageStatus = Literal["success", "failed", "skipped"]
COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")
SOURCE_COUNTRY_CODE_SPECIAL_SET = {"EU", "GLOBAL"}


def identifier_component_validate(value: str) -> str:
    """Validate one DBOS identifier component value.

    Args:
        value: Candidate identifier component.

    Returns:
        Validated identifier component.

    Raises:
        ValueError: If the value is not already a safe DBOS identifier component.
    """

    if dbos_identifier_component(value) != value:
        raise ValueError("value must already be a safe DBOS identifier component")
    return value


IdentifierComponent = Annotated[str, AfterValidator(identifier_component_validate)]


class StrictBaseModel(BaseModel):
    """Base model with strict validation for workflow artifacts."""

    model_config = ConfigDict(extra="forbid", strict=True)
