# 当前结构与后续收口项

这是对目标结构偏差的明确记录，不能据“兼容性通过”声称所有结构目标均已完成。本轮优先修复私有材料忽略、默认测试、launcher预检和证据时效；没有批量重写业务import、移动活动数据或改旧手工运维脚本行为。

## 正式模块与旧import

实际是`src/kdb`正式模块与原路径薄wrapper并存。静态盘点有253条正式模块指向旧兼容命名空间的import边；旧wrapper再委托同一canonical模块，没有第二份ES算法，但依赖图仍是混合的。具体边在本轮证据`dependency_import_inventory.json`。

这属于迁移过渡契约，旧路径不是新增代码的推荐canonical import。后续逐模块改成`kdb.shared`/`kdb.retrieval`等需要核对模块身份、循环依赖、脚本`__main__`、monkeypatch目标和反射路径，再做回归；不在本轮为了目录美观大范围机械替换。

## 旧绝对路径

逐文件逐行清单见`absolute_path_inventory.json`：33处旧项目根或macOS路径引用，包含注释、手工工具和有效模块的可选默认值。没有把它们一律当注释或已修复。

| 范围 | 本轮处置 | 独立执行状态 |
|---|---|---|
| retrieval私有配置中4个`/root/dify/...`指针 | 仅在候选原位重绑到确实存在的同名配置 | 检索本地预检通过；真实启动仍按启动说明 |
| `src/kdb/shared/clients/local_llm_adapter.py` | 保留原可选本机默认路径 | 使用该功能前需显式配置，不能算独立可运行 |
| `control_script/run_wayfair_unanswered_review.sh`、`review_excel_qa_to_dataset.sh`、`all_dataset_gen.sh` | 保留原调用/输入路径契约，列出待重绑项 | 手工业务脚本，未当启动smoke执行 |
| `scripts/recheck_key5_live_metadata_20261005.py` | 保留原默认配置路径 | 运维工具，运行前必须选实际配置 |
| `src/kdb/compat/legacy_ops`等手工/历史工具 | 保留来源和行为；禁止默认启用 | 待逐项确认用途、资源、数据副作用再归档或重绑 |

本轮没有为了让路径检查通过而生成假的资源、认证或业务输入。`absolute_path_inventory.json`是指定源码/脚本范围的盘点，不声称扫描了所有私有材料内容。

## 目录目标偏差

当前`scripts`子目录是`mining/ops/scheduled/services/testing`；计划中的`operations/data_migration/legacy_ops`尚未全部落地，旧forge迁移工具仍保留入口。计划命名的`jobs/chat_mining.py`与`jobs/reports.py`也尚不存在，现有逻辑经`jobs/legacy`及旧shell/兼容入口承接。`src/kdb/mining/pipelines/legacy`内手工测试与`compat/legacy_ops`中的未知脚本尚需人工分类。详见`layout_disposition.json`。

因此验收结论分开表述：ES检索行为已有同视图实证；安全测试和启动检查已补强；“全项目已完全达到目标目录/依赖图且所有工具可独立运行”仍不成立。目录收口是后续工作，不能靠空文件、空目录或删除旧入口宣称完成。
