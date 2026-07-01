# Size Group Key Contract

This contract applies to real size-chart tables in `SourceDiscovery`, `TableExtraction`, `CanonicalSelection`, and canonical chart output paths. A `size_group_key` is a stable table identifier, not a page name, product id, source type, coverage bucket, or diagnostic label.

Use exactly one of these forms:

- `{sex}_{product_group_or_type}`
- `{sex}_{sex_suffix}_{product_group_or_type}`

`sex` is a closed set:

- `women`
- `men`
- `girls`
- `boys`
- `unisex`
- `unisex_child`

Use no suffix when there is no objective chart-group qualifier. Do not add a default suffix.

Current approved `sex_suffix` terms from existing extracted chart groups:

- `plus`
- `baby`
- `child_3_8`
- `youth_8_14`

Current approved `product_group_or_type` terms from existing extracted chart groups and requested product types:

- `upper`
- `lower`
- `pants_skirts`
- `belts`
- `shoes`
- `clothing`
- `dresses`
- `outerwear`
- `underwear`
- `swimwear`
- `socks`
- `hosiery`
- `hats`
- `gloves`
- `bras`

Examples:

- `women_upper`
- `women_plus_lower`
- `men_shoes`
- `girls_child_3_8_clothing`
- `boys_youth_8_14_clothing`
- `girls_baby_clothing`
- `boys_baby_clothing`
- `unisex_socks`
- `unisex_child_hats`

Never use `size_chart`, `chart`, `product_measurement`, `product_measurements`, product ids, source-type names, brand names, `requested`, `uncovered`, `gap`, or `coverage` inside a real table `size_group_key`.

Product size labels such as `3-4-yas`, `6-9-ay`, `13-14-yas`, `80b`, `xl`, or similar source row values are not `sex_suffix` terms and must not become table-group suffixes.

Synonyms are forbidden. Use the approved term when the meaning is already covered by the approved list. If browser-visible source evidence proves a genuinely new table group that is not covered by this list, create one new clear snake_case term, explain the source wording in `source_note_list` or `applicability_description`, and let verification check that it is not a duplicate name for an existing approved meaning.
