# payoneer_olive 私人知识库：按来源文件重新分组（2026-08-21）

脚本：`data_control_tools/recategorize_by_source_file.py`
本次工作目录：`output/recategorize_mercado_20260821/`（`plans.jsonl` + `rollback.jsonl` 220 条）

## 需求

用户反馈私人知识库（索引 `payoneer_olive_payoneer_olive`）里两份美客多文档分错组，
要挪到 `Mercado Libre`：

- `美客多全站点 入驻资料提交指南.pdf`
- `11.13  美客多0-1运营模式解析及半托管 - Libby v1.pdf`

## 根因：类目是**任务级**字段，一个任务混投了两个平台的文件

`document_qa_segment_mining` 的 `category_id` / `category_name` 是任务级的
（见 `docs/payoneer_olive_doc_knowledge_ingest.md`「为什么一篇文档一个任务」），
所以一个任务里投多份文件时，整批知识跟着任务挂同一个组：

| task_id | 组 | 文件构成 |
|---|---|---|
| `ce1171aeb0408a6d804c873def66eb4a` | Noon | noon 入驻指南 43 条（对）+ **11.13 美客多 200 条（错）** |
| `25ec54865188614f978c0eb71acd1ad8` | Mercado Libre | 11.11&12 物流 151 条 + 11.13 美客多 118 条（都对）|
| `09c536c84a0dcb07eef664a5e180cf56` | 默认分组 | 美客多全站点入驻资料提交指南 20 条（漏填 category）|

**这类错误 title 里没有任何信号**，`assign_platform_category`（从 title 猜平台）救不了，
所以新写了按「来源文件名」圈定、由人指定目标类目的脚本。

## 做法

```bash
# dry-run
python3 data_control_tools/recategorize_by_source_file.py \
  --index payoneer_olive_payoneer_olive --client payoneer_olive \
  --category "Mercado Libre" \
  --file-name "美客多全站点 入驻资料提交指南.pdf" \
  --file-name "11.13  美客多0-1运营模式解析及半托管 - Libby v1.pdf" \
  --work-dir output/recategorize_mercado_20260821

# 写回（写前自动落 rollback.jsonl）
... --execute

# 回滚
... --rollback output/recategorize_mercado_20260821/rollback.jsonl --execute
```

结果：圈定 338 条存活知识，改 220 条（Noon 200 + 默认分组 20），
118 条本来就在 Mercado Libre 未动，失败 0。

改后私人库存活 1259 条：Amazon 634 / Mercado Libre 489 / Noon 86 / TikTok Shop 50 / 无类目 0。
Noon 只剩 noon 入驻指南那 86 条，没误伤。

## 坑

1. **`ext_info.from_file_name` 是 text，term 过滤必须用 `.keyword`**；
   而 **`task_id` 本身就是 keyword，没有 `.keyword` 子字段**——
   用 `task_id.keyword` 聚合会静默返回空桶（一开始就这么翻车过，误以为文档没有 task_id）。
2. **别按 task_id 整批改组**：任务里混了别的平台的文件，按 task 改会把 noon 入驻指南
   那 43 条一起挪走。按 `from_file_name` 圈才准。
3. 只改 `del_flag=0` 的；软删的 34 条没动（前端不展示），需要时加 `--include-deleted`。
4. 阿里云 ES Serverless 写完立刻聚合可能读到旧值，核对前先 `_refresh` 或轮询。
5. 二级类目（如 `Mercado Libre-入驻指引`）暂不支持：复用的 `build_category_fields`
   只写 `cate1_*`。私人库目前只用一级；公共库 `payoneer_olive` 里有 270 条挂在
   `Mercado Libre-入驻指引` 下。

## 遗留：11.13 这份 PDF 被跑了两遍

同一份 `11.13 美客多0-1运营模式解析及半托管 - Libby v1.pdf` 在两个任务里各生成了一批知识
（200 条 + 118 条，标题交集只有 5 条，说明是两次独立生成而非重复写入），
改组后 318 条全在 Mercado Libre 下。**内容层面大概率重复**，需要业务确认删哪一批
（`--task-id` 可以精确圈出某一批）。本次没动。
