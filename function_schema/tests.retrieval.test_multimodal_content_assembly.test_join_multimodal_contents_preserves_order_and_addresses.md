# tests.retrieval.test_multimodal_content_assembly.test_join_multimodal_contents_preserves_order_and_addresses

## Signature

`test_join_multimodal_contents_preserves_order_and_addresses(parts, expected)`

## Inputs

参数化多模态项列表与预期文本：空列表、文本顺序、四种媒体、path 优先于 url、缺失地址和未知类型。

## Outputs

在不初始化客户端的 SearchDataInterface 裸实例上调用正式绑定方法，断言输出内容、顺序及输入未被修改；不是仅检查方法存在。

## SQL

无 SQL、网络、模型或子进程。

## Source

`tests/retrieval/test_multimodal_content_assembly.py`
