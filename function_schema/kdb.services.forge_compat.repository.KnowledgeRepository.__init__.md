# kdb.services.forge_compat.repository.KnowledgeRepository.__init__

## Signature

`KnowledgeRepository.__init__(self, engine: Any=None, engine_config_path: Optional[str]=None, default_index: Optional[str]=None) -> None`

## Inputs

`self, engine: Any=None, engine_config_path: Optional[str]=None, default_index: Optional[str]=None`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

## Outputs

Args:
    engine: ES8.17 `RoutedLegacyEngine` 或兼容鸭子类型实例。为 None 时用 engine_config_path 构造。
    engine_config_path: config_es_engine.json 路径（engine 为空时必填）。
    default_index: 默认索引名；方法未显式传 index_name 时使用。为空时取 engine 内部 index_name。

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source

`src/kdb/services/forge_compat/repository.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
