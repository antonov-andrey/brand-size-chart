"""Source type registry for brand size-chart discovery."""

from types import MappingProxyType


class SourceTypeRegistry:
    """Own source type priority, product scope, and execution order."""

    def __init__(self) -> None:
        """Store source type lookup contracts."""

        self.source_type_priority_by_key_map = MappingProxyType(
            {
                "official_brand_size_guide": 600,
                "official_seller_size_guide": 550,
                "official_brand_product_page": 500,
                "official_marketplace_product_page": 300,
                "official_marketplace_store": 200,
            }
        )
        self.product_type_required_source_type_set = frozenset(
            {
                "official_brand_product_page",
                "official_marketplace_product_page",
                "official_marketplace_store",
            }
        )
        self.source_type_by_selector_map = MappingProxyType(
            {
                "brand": "official_brand_size_guide",
                "product": "official_brand_product_page",
            }
        )

    def source_type_list_get(self, *, have_product_type_request: bool, source_type_allow_list: list[str]) -> list[str]:
        """Return source types in priority order with product-type gating applied.

        Args:
            have_product_type_request: Whether the prompt has requested product types.
            source_type_allow_list: Prompt-selected source type allow list.

        Returns:
            Ordered source type key list.
        """

        source_type_list = [
            source_type
            for source_type, _priority in sorted(
                self.source_type_priority_by_key_map.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        ]
        if source_type_allow_list:
            source_type_allow_set = {
                self.source_type_by_selector_map.get(source_type, source_type) for source_type in source_type_allow_list
            }
            source_type_list = [source_type for source_type in source_type_list if source_type in source_type_allow_set]
        if have_product_type_request:
            return source_type_list
        filtered_source_type_list = [
            source_type
            for source_type in source_type_list
            if source_type not in self.product_type_required_source_type_set
        ]
        if not filtered_source_type_list:
            raise RuntimeError("No source types remain after applying product-type scope rules.")
        return filtered_source_type_list

    def source_type_priority_get(self, source_type: str) -> int:
        """Return priority for one source type.

        Args:
            source_type: Source type key.

        Returns:
            Source priority.
        """

        return self.source_type_priority_by_key_map[source_type]

    def source_type_requires_product_type(self, source_type: str) -> bool:
        """Return whether one source type requires product-type scope.

        Args:
            source_type: Source type key.

        Returns:
            Whether the source type requires product-type scope.
        """

        return source_type in self.product_type_required_source_type_set


SOURCE_TYPE_REGISTRY = SourceTypeRegistry()
