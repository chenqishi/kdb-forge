# kdb.retrieval.presentation.multimodal.join_multimodal_contents

## Signature

`join_multimodal_contents(self, multimodal_contents: list[Dict[str, Any]]) -> str`

## Inputs

多模态内容列表，保持输入顺序。text 项使用 content；image/video/audio/file 优先使用 path 并加 `[multimodal_prefix]`，否则使用 url；媒体缺少地址时跳过，未知 type 不拼入。

## Outputs

按现有规则以换行连接内容，空列表返回空字符串，不修改输入列表。边界：仅有 content 为 None（或缺少 content）的 text 项时，当前实现返回 None，尽管返回注解为 str；本次仅记录行为，不改变实现。

维护工具 `kdb.retrieval.maintenance.prune_dead_urls.join_multimodal_contents` 最后使用 `content or ''`，因此同一空值输入返回空字符串。两者不能在未核对边界时机械合并。正式调用点在 `retrieval/ingestion/prepare.py`，内容拼接后才按既有条件生成 content_embedding；查询端的 URL 展示属于另一个函数。

直接行为回归见 `tests/retrieval/test_multimodal_content_assembly.py`；维护重建回归见 `tests/retrieval/maintenance/test_prune_dead_raw_urls.py`。

## SQL

无。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.join_multimodal_contents`

## Source

`src/kdb/retrieval/presentation/multimodal.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
