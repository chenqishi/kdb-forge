# kdb.retrieval.maintenance.prune_mismatched_images.plan_row

## Signature

`plan_row(content: str, images: Sequence[Dict[str, Any]], path_md5: Dict[str, str], allowed_md5: Set[str], window: int=DEFAULT_WINDOW, attach_candidates: Optional[Sequence[Dict[str, Any]]]=None, only_duplicate: bool=False, attach_when_no_text: bool=False) -> Dict[str, Any]`

## Description

算出单条知识该留哪些图、裁哪些图，以及被裁的图有没有话术指着。纯函数，可单测。

## Inputs

- `content` (str) — 答案正文，末尾追加着 `[multimodal_prefix]<s3_path>` 标记
- `images` (Sequence[Dict]) — `multimodal_contents` 里的图片项（目前只用于调用方重建）
- `path_md5` (Dict[str,str]) — `s3_path -> 图片内容 md5`，见 `build_path_md5_map`
- `allowed_md5` (Set[str]) — 本条知识页码区间内**真实**存在的图片 md5
- `window` (int, 默认 60) — 话术到图片标记的最大字符距离
- `attach_candidates` (Sequence[Dict], 可选) — 该页码区间内**上传过**的正确图，
  见 `page_items_for_range`；用于话术指着的图被裁光时把正确的图挂回去

## Outputs

`Dict`：
- `keep_paths` (List[str]) — 保留的标记路径，按原顺序
- `drop` (List[Dict]) — 每项 `{path, md5, reason, deictic}`，`reason` 为
  `page_mismatch`（不属于本页）或 `duplicate`（同一张图的另一个地址）
- `action` — `noop` / `prune` / `prune_with_deictic` / `prune_and_attach` / `review_deictic`
- `attach` (List[Dict]) — 要补挂的正确图（仅 `prune_and_attach`）
- `unknown_paths` (int) — md5 查不到的标记数（保守保留）
- `orphan_deictic` (List[str]) — 附近没有任何图的强话术

## 为什么必须按 md5 而不是按路径

同一张图在旧数据里被多模态阶段当成新图反复上传，一张图对应多个 `s3_path`
修复后的解析按 md5 只贴回其中一个地址，**按路径比对会把几乎所有图误判成「不属于本页」**。

## action 的含义

话术指着的图被裁光、这条知识一张图都不剩时，分两档（对应 2026-08-21 定下的既定规则，
但第一档现在是确定性的，不用人工找图）：

- `prune_and_attach`：该页**确实有**上传过的图 → 把正确的图挂回去。
- `review_deictic`：该页真没有可挂回的图（真图 0 张，或只有从未上传的 logo/装饰图）

另外两档：
- `prune_with_deictic`：有话术指着的图被裁，但还剩别的本页图 → 可自动处理。
- `prune`：没有话术指着被裁的图 → 正常裁。**不会**凭空补图，
  因为正文没许诺过有图。

## SQL / ES schema

纯函数不碰 ES。调用方写回 `content` / `multimodal_contents` / `content_embedding`。

## 测试

`tests/test_prune_page_mismatched_images.py`

## Source

`src/kdb/retrieval/maintenance/prune_mismatched_images.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
