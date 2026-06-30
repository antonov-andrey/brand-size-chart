"""Tests for brand list parsing."""

from brand_size_chart.io import brand_list_parse


def test_brand_list_parse_trims_comments_and_dedupes_by_identifier_component() -> None:
    """Normalize brand text for search separately from the technical dedupe key."""
    result = brand_list_parse("""
        # source comments are ignored
        LC    Waikiki
        lc waikiki

        Mango # inline hash belongs to brand text
        MANGO
        """)

    assert [brand.parsed_brand_name for brand in result.brand_list] == [
        "LC Waikiki",
        "Mango # inline hash belongs to brand text",
        "MANGO",
    ]
    assert [brand.parsed_brand_key for brand in result.brand_list] == [
        "lc_waikiki",
        "mango_inline_hash_belongs_to_brand_text",
        "mango",
    ]
    assert [warning.warning_type for warning in result.warning_list] == ["duplicate_brand"]
    assert result.warning_list[0].parsed_brand_key == "lc_waikiki"
    assert result.warning_list[0].raw_brand_name_list == ["LC Waikiki", "lc waikiki"]


def test_brand_list_parse_rejects_invalid_identifier_component() -> None:
    """Surface invalid raw input instead of silently changing component boundaries."""
    result = brand_list_parse("Alpha/Beta\n")

    assert result.brand_list == []
    assert len(result.warning_list) == 1
    assert result.warning_list[0].warning_type == "invalid_brand"
