# LegacySearchDataInterfaceMixin._apply_category_defaults

## Inputs
- `data`: mutable document, optional upstream `category_infos` and `primary_category`.
- `is_new`: whether missing category fields should receive the default group.
- `client`, `ext_info.client`, or legacy `platform`: category-tree tenant identifier.

## Outputs
Returns `None`; normalizes explicit category aliases/IDs and resolves their parent
chain. Keeps explicit candidates when the tree cannot resolve them, regardless of
their `source`. Preserves an existing primary category unless an explicit candidate
resolves; new documents without a primary category receive the default group.
Does not infer categories from tenant-specific marketplace metadata, tags, or title.
Payoneer Olive inference belongs to upstream mining, outside CRUD compatibility.

## SQL
None. Explicit categories may read the configured category HTTP service; no ES writes.
