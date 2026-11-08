# tests.mining.test_pdf_rendered_image_extraction.test_image_only_pdf_renders_pages_omitted_by_image_blocks

## Signature

`test_image_only_pdf_renders_pages_omitted_by_image_blocks(tmp_path, monkeypatch)`

## Inputs

原pytest参数/fixtures和测试数据结构不变。

## Outputs

保留业务断言与mock语义；仅把旧import、source定位、mock目标、入口argv映射到当前kdb模块及scripts目录。

## SQL

无真实SQL/网络/子进程。沿原规则将确需真实subprocess的两例在offline runner中显式排除。

## 最终当前模块位置

依赖移为generation.processing、generation.builders及mining.quality.qa_quality_tools；只换import/mock目标/argv模块，业务断言不变。

## Source

`tests/mining/test_pdf_rendered_image_extraction.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
