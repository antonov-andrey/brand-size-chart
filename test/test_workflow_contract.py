"""Tests for cross-project workflow contract metadata."""

from pathlib import Path

import yaml

from brand_size_chart import workflow
from brand_size_chart.model import PromptScope
from brand_size_chart.model import PromptStageInstruction
from brand_size_chart.source_type import (
    PRODUCT_TYPE_REQUIRED_SOURCE_TYPE_SET,
    SOURCE_TYPE_DISCOVERY_INSTRUCTION_BY_KEY_MAP,
    SOURCE_TYPE_PRIORITY_BY_KEY_MAP,
)


def test_workflow_yaml_declares_required_cross_project_contract_keys() -> None:
    """Expose required input, output, and runtime keys in workflow metadata."""
    workflow = yaml.safe_load(Path("workflow.yaml").read_text(encoding="utf-8"))

    assert [source["name"] for source in workflow["data_source_list"]] == ["brand_list", "secret"]
    assert [container["name"] for container in workflow["data_container_list"]] == [
        "brand_size_chart",
        "brand_size_chart_audit",
    ]
    assert workflow["data_source_list"][1]["is_private"] is True
    assert workflow["data_source_list"][1]["mutable_prefix_list"] == ["playwright_profile/**"]
    assert workflow["runtime_capability_list"] == [
        {
            "data_source_name": "secret",
            "name": "browser_vpn_runtime",
        }
    ]


def test_project_secret_is_ignored_by_git() -> None:
    """Keep the local private DataSource out of git."""
    gitignore_text = Path(".gitignore").read_text(encoding="utf-8")

    assert ".secret/" in gitignore_text.splitlines()


def test_local_compose_declares_vpn_and_no_vpn_profiles() -> None:
    """Allow standalone local workflow runs with and without OpenVPN."""
    compose = yaml.safe_load(Path("compose.yaml").read_text(encoding="utf-8"))

    assert compose["services"]["workflow-no-vpn"]["profiles"] == ["no-vpn"]
    assert compose["services"]["workflow-vpn"]["profiles"] == ["vpn"]
    assert compose["services"]["workflow-vpn"]["network_mode"] == "service:openvpn"
    assert compose["services"]["workflow-no-vpn"]["environment"]["DBOS_SYSTEM_DATABASE_URL"].startswith("sqlite:///")
    assert compose["services"]["workflow-vpn"]["environment"]["DBOS_SYSTEM_DATABASE_URL"].startswith("sqlite:///")


def test_workflow_imports_dbos_eagerly_without_noop_decorator_fallback() -> None:
    """Keep workflow functions real DBOS workflow and step functions."""
    workflow_source = Path("brand_size_chart/workflow.py").read_text(encoding="utf-8")

    assert "except ModuleNotFoundError" not in workflow_source
    assert "DBOS = None" not in workflow_source
    assert "def _dbos_step" not in workflow_source
    assert "def _dbos_workflow" not in workflow_source


def test_source_type_registry_has_no_separate_official_brand_asset_stage() -> None:
    """Keep official PDFs, images, and assets inside the official brand size-guide source type."""
    source_type_source = Path("brand_size_chart/source_type.py").read_text(encoding="utf-8")

    assert "official_brand_asset" not in source_type_source
    assert "pdf" not in SOURCE_TYPE_DISCOVERY_INSTRUCTION_BY_KEY_MAP["official_brand_size_guide"].lower()
    assert "image" not in SOURCE_TYPE_DISCOVERY_INSTRUCTION_BY_KEY_MAP["official_brand_size_guide"].lower()


def test_source_type_registry_uses_authority_sources_without_seller_qa_stage() -> None:
    """Keep source types based on authority and location, not on evidence format."""
    assert SOURCE_TYPE_PRIORITY_BY_KEY_MAP == {
        "official_brand_size_guide": 600,
        "official_seller_size_guide": 550,
        "official_brand_product_page": 500,
        "official_marketplace_product_page": 300,
        "official_marketplace_store": 200,
    }
    assert "official_seller_qa" not in SOURCE_TYPE_DISCOVERY_INSTRUCTION_BY_KEY_MAP
    assert PRODUCT_TYPE_REQUIRED_SOURCE_TYPE_SET == {
        "official_brand_product_page",
        "official_marketplace_product_page",
        "official_marketplace_store",
    }


def test_source_type_selection_requires_product_types_for_product_page_source_types() -> None:
    """Run product-page source types only when product types are requested."""
    source_type_list_without_product_types = workflow._source_type_list_get(PromptScope())
    source_type_list_with_product_types = workflow._source_type_list_get(PromptScope(product_type_request_list=["bra"]))

    assert source_type_list_without_product_types == ["official_brand_size_guide", "official_seller_size_guide"]
    assert source_type_list_with_product_types == [
        "official_brand_size_guide",
        "official_seller_size_guide",
        "official_brand_product_page",
        "official_marketplace_product_page",
        "official_marketplace_store",
    ]


def test_prompt_scope_rejects_unknown_source_type_and_stage_key() -> None:
    """Reject unknown prompt-derived execution keys instead of silently dropping them."""
    try:
        workflow._prompt_scope_validate(PromptScope(source_type_allow_list=["unknown_source_type"]))
    except RuntimeError as exc:
        source_type_message = str(exc)
    else:
        source_type_message = ""

    try:
        workflow._prompt_scope_validate(
            PromptScope(stage_instruction_list=[PromptStageInstruction(stage_key="unknown_stage", instruction="x")])
        )
    except RuntimeError as exc:
        stage_key_message = str(exc)
    else:
        stage_key_message = ""

    assert "unknown_source_type" in source_type_message
    assert "unknown_stage" in stage_key_message


def test_source_discovery_prompt_makes_table_forms_universal() -> None:
    """Search every source type for size charts in any browser-visible form."""
    discovery_prompt = Path("brand_size_chart/prompt/discovery.md").read_text(encoding="utf-8").lower()

    assert "html table" in discovery_prompt
    assert "modal" in discovery_prompt
    assert "widget" in discovery_prompt
    assert "pdf" in discovery_prompt
    assert "image" in discovery_prompt
    assert "help" in discovery_prompt
    assert "faq" in discovery_prompt
    assert "q&a" in discovery_prompt
    assert "for `official_brand_size_guide`" not in discovery_prompt
