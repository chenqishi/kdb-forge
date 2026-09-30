# LegacySearchDataInterfaceMixin.process_one_data

## Inputs
`data` 字典，`index_name` 可选。

## Outputs
原地补齐旧 process_one_data 的字段、向量、`_id`、时间、类目和多模态内容；成功返回
`True`，处理异常返回 `False`。
类目处理仅包含显式类目归一化、类目树解析和默认分组；不执行挖掘侧的 Payoneer Olive 推断。

## SQL
无；向量由注入的 embedding client 生成，类目可读取配置的 HTTP 服务。
