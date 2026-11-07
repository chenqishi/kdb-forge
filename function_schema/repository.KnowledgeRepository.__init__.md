# KnowledgeRepository.__init__

## Inputs
`self, engine: Any=None, engine_config_path: Optional[str]=None, default_index: Optional[str]=None`. Retain the original forge protocol and defaults; see original contracts in function_schema/forge_protocol/.

## Outputs
Args:
    engine: ES8.17 `RoutedLegacyEngine` 或兼容鸭子类型实例。为 None 时用 engine_config_path 构造。
    engine_config_path: config_es_engine.json 路径（engine 为空时必填）。
    default_index: 默认索引名；方法未显式传 index_name 时使用。为空时取 engine 内部 index_name。

## SQL
No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source
`src/kdb/services/forge_compat/repository.py`; independent source proof is recorded in compat_source_proof.json for the restart.
