# legacy_bridge（接线层）

## 所属文件
`src/kdb/legacy_bridge.py`

## 功能描述
把旧项目 `knowledge_database_builder` 以 sys.path 注入方式接入，并 re-export 复用对象，不修改旧代码、不要求打包安装。

## 关键成员
- `LEGACY_ROOT` (str)：旧项目根目录，环境变量 `KDB_LEGACY_ROOT` 可覆盖。
- `ensure_legacy_on_path(root=None) -> str`：幂等地把旧根插入 sys.path，返回生效路径。
- `EsSearchInterface`：re-export 旧底层 ES 适配工厂（硬依赖）。
- `cosine_similarity(vec1, vec2) -> float`：复用旧实现，失败退回等价实现（公式相同）。
- `legacy_gen_data_id` / `HAS_LEGACY_GEN_DATA_ID`：旧 _id 生成（软依赖，可兜底）。
- `build_legacy_engine(config_path=None, index_name=None, **kwargs)`：构造旧 `EsSearchInterface`。
- `load_legacy_search_interface(config_path, index_name=None)`：按需构造旧 `SearchDataInterface`（仅对齐测试用，避免在生产路径触发重 import 链）。

## 风险
import `legacy_gen_data_id` 会触发 `search_index_data_interface` 顶层 import 链（dify/keywords/simility，可能触达 `config_tools/config.py` 的 import 期 json.load）。已实测可正常导入（约 1.4s）；失败时由 `kdb.crud.ids` 兜底。

## SQL
无（接线层）。
