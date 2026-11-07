# kdb.integrations.data_control.strip_nav_boilerplate.run

## Signature

`run(task_id, index_name='wayfair', execute=False, output_dir='output/strip_nav_boilerplate', es_config='config/config_es_engine.json', embedding_config='config/config_ali_embedding.json', boiler_markers=None)`

## 功能

把 ES 里段落知识开头的站点导航样板剥掉，并同步重算向量。**默认 dry-kdb.mining.generation.run。**

## Inputs

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| task_id | str | 是 | - | 只处理该任务产出的文档 |
| index_name | str | 否 | `'wayfair'` | ES 索引 |
| execute | bool | 否 | `False` | `False` 只出报告不写库 |
| output_dir | str | 否 | `output/strip_nav_boilerplate` | 报告与回滚文件目录 |
| es_config | str | 否 | `config/config_es_engine.json` | ES 连接配置 |
| embedding_config | str | 否 | `config/config_ali_embedding.json` | 向量配置，**必须与搜索服务同一份** |
| boiler_markers | list[str] | 否 | 见代码 | 判定"含样板"的特征串 |

## Outputs

| 类型 | 说明 |
|------|------|
| str | 报告文件路径 |

## 逻辑说明

1. `search_after` 翻页拉取 `task_id` + `del_flag=0` 的全部文档
   （**`data_type` 没有 keyword 索引**，`data_type.keyword` 查询返回空，必须在客户端按 `_source` 过滤）
2. 客户端筛出 `data_type == 'segment'` 且 `content` 命中 `boiler_markers` 的文档
3. 逐条 `find_nav_prefix_end`；返回 `None` 的记为 `skipped` 并写进报告，不做处理
4. dry-kdb.mining.generation.run：输出每条的剥离前后预览、前缀长度、剩余长度、占比；不调向量接口、不写 ES
5. execute：
   - 先把原始 `content` / `multimodal_contents` 写进 `rollback_<flag>.jsonl`
   - `text2embedding(新content)` 重算向量
   - `POST /{index}/_update/{_id}`，只改上表三个字段
6. 写报告 JSON：`total/stripped/skipped/failed` 与逐条明细

## 依赖的外部接口

- ES：`_search`（search_after 翻页）、`_update`
- 阿里云 DashScope 向量：经 `kdb.shared.clients.embedding_tools.AliEmbedding.text2embedding`

## SQL

无。不涉及 MySQL —— 这是 ES 文档级修订，任务表 `dops_task_kggen_info` 是任务级的，不需要动。

## Source

`src/kdb/integrations/data_control/strip_nav_boilerplate.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
