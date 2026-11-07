# Mercado all kg 合并迁移

## 目标

将 `mercado` 和 `mercado_local` 的知识复制合并到 `mercado_all_kg`，源索引只读，不更新、不删除、不改 mapping。

## 迁移规则

- `mercado`：只迁移 `data_type=qa` 且 active 的知识。
- `mercado_local`：迁移全部 active 知识。
- active 定义：`del_flag=0` 或 `del_flag` 缺失。
- 向量字段原样保留，不重新计算 embedding。
- 只重写目标归属与类目字段：
  - `_id`
  - `client`
  - `platform`
  - `dataset`
  - `category_infos`
  - `primary_category`
  - `ext_info.migration_id/source_index/source_id`

## Mercado QA 地区分类

脚本只看 Q/title：

- 只包含墨西哥信号：`业务地区-墨西哥`
- 只包含巴西信号：`业务地区-巴西`
- 同时包含墨西哥和巴西，或都不包含：`业务地区-跨境CBT`

## 目标类目检查

2026-08-03 检查并清理后，`mercado_all_kg` 类目树目标节点为：

- `业务地区-墨西哥`: `2084129700306276354`
- `业务地区-跨境CBT`: `2084129700536963073`
- `业务地区-巴西`: `2084129700058812418`

脚本遇到重复类目路径会阻断，必须显式传 `--category-id-override`，避免静默绑错。正式执行前用户已删除一个重复的 `业务地区-巴西` 节点，因此本次执行未使用 override。

## Dry-run

本地默认 `python3` 没有 `elasticsearch==7.10`，应在项目运行环境或生产 `main` 机器的 conda 环境执行。

```bash
/root/miniconda3/envs/py38/bin/python \
  data_control_tools/merge_mercado_indexes_to_all_kg.py \
  --limit 100 \
  --batch-size 100 \
  --report-path output/mercado_all_kg_merge_dry_run_100.json
```

不带 `--execute` 时只读 ES 和类目服务，不写目标索引。

## 正式执行

确认 dry-run 的 `prepared`、`category_counts`、`skip_reasons` 后再执行：

```bash
/root/miniconda3/envs/py38/bin/python \
  data_control_tools/merge_mercado_indexes_to_all_kg.py \
  --batch-size 50 \
  --migration-id mercado_all_kg_merge_20260803 \
  --report-path output/mercado_all_kg_merge_20260803_execute.json \
  --execute
```

默认使用 ES `create` 写入，目标 `_id` 为 `md5(migration_id:source_index:source_id)`，重复执行会统计为 `write_skipped_existing`。如需覆盖同一批次目标文档，才加 `--overwrite`。

注意：2026-08-03 本地执行时 `--batch-size 500` 触发过 ES `413 Request Entity Too Large`，未产生部分写入；改为 `--batch-size 50` 后成功完成。

## 2026-08-03 执行结果

执行报告：`output/mercado_all_kg_merge_20260803_execute.json`

- `mercado`: scanned/prepared/written `10065/10065/10065`
- `mercado_local`: scanned/prepared/written `6645/6645/6645`
- 总写入：`16710`
- `write_errors`: `0`
- `write_skipped_existing`: `0`

类目分布：

- `业务地区-跨境CBT`: `9914`
- `业务地区-巴西`: `6076`
- `业务地区-墨西哥`: `720`

写后验证：

- `mercado_all_kg` 按 `ext_info.migration_id=mercado_all_kg_merge_20260803` count 为 `16710`。
- 按确定性 `_id` 对账，`mercado` 期望 `10065`、缺失 `0`；`mercado_local` 期望 `6645`、缺失 `0`。
- 抽样确认 `title_embedding`、`content_embedding`、`indexes.embedding` 保留为非空。

## 回滚

本脚本会给新增文档写：

```json
{
  "ext_info": {
    "migration_id": "mercado_all_kg_merge_20260803",
    "source_index": "mercado",
    "source_id": "old_id"
  }
}
```

如需撤销，只删除 `mercado_all_kg` 中 `ext_info.migration_id` 等于本批次 ID 的文档。源索引没有被修改。
