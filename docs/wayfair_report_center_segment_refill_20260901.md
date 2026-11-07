# 报告中心文档补段落 2026-09-01

## 起因

问「如何导出链接流量数据」召不回。查下来知识库里其实有答案素材
（`基础运营_关于报告中心.docx`，帮助中心文章 2257 / 英文 Report Center 1777），
但这篇**只有 92 条碎 QA，一条 segment 都没有**。

## 排查结论：不是被删的，是阶段9 崩了

先确认没有知识被删：该文件在 ES 里共 99 条，**全是 `data_type=qa`**
（92 活跃 + 7 软删）。7 条软删都是入库去重打掉的近似重复，原文内容都还在活跃条目里
（唯一值得一提的是删掉的「平均**预估**送达天数」与保留的「平均**实际**送达天数」严格说是两个指标）。

任务 `74256b780370585cae399772cbdf9c49`（`document_qa_segment_mining`，2026-03-26，235 个文件）：

- MySQL `task_stage = error`
- 阶段 1–8 跑完，4957 条 QA 入库
- **阶段9 在第 21 个文件处抛异常整批退出**：

```
KeyError: '8'
  knowlege_segment_builder_by_dify.py:98  tmp_dict[page] = ori_data_json_dict[page]
```

老兜底逻辑用 `[1, len(data_json)]` 当页码查页字典，键对不上直接 KeyError，
异常穿透 `fire.Fire` 打死整个批次。

**影响是全任务级的**：`segment_knowledge.txt` 只留下崩溃前 20 个文件的 54 条段落，
而且**阶段10/11 从未执行** —— 这个任务的 **235 个文件全部没有 segment 入库**。

⚠️ 本次只按要求补了报告中心一篇，**其余 234 个文件仍然没有 segment**。

该 bug 后来已随代码重写消失（现在是 `build_page_chunks` + `fill_uncovered_segments_in_chunk`
硬窗口兜底），本次用现有代码重跑一次通过。

## 单篇补 segment 的做法

任务工作目录还在 main 上，`translated_mapping.txt` 和 `multimodal_data_info.json` 都在，
**不用重新下载解析**，直接从阶段9 接着跑：

```bash
ssh main && cd /root/knowledge_database_builder
export PYTHONPATH=/root/knowledge_database_builder     # 必须，否则 ModuleNotFoundError
PY=/root/miniconda3/envs/py38/bin/python
TID=74256b780370585cae399772cbdf9c49
D=data/off_task_data/$TID ; L=log/off_task_log/$TID

# 只取目标文件那一行（字段：platform \t file_name \t ext \t ... \t parsed_json）
grep -P "^wayfair\t基础运营_关于报告中心\.docx\t" $D/translated_mapping.txt > $D/translated_reportcenter.txt

# 阶段9 段落生成（位置参数含义：输入 flag from_file_name_field_num=1 platform_field_num=0 is_direct_output=1 use_image_content=1）
$PY knowledge_generate/knowlege_segment_builder_by_dify.py run_batch_get_segment_knowledge \
  $D/translated_reportcenter.txt $TID 1 0 1 1 \
  1>$D/segment_knowledge_reportcenter.txt 2>$L/segment_reportcenter.log

# 阶段10 转 ES schema
$PY commons/schema_trans.py trans_segment_to_search_data_for_file \
  --input_file=$D/segment_knowledge_reportcenter.txt \
  --output_file=$D/segment_knowledge_reportcenter_search_data.txt \
  --field_num=0 --task_id=$TID --category_id=1 --category_name="默认分组" \
  --multimodal_mapping_path=$D/multimodal_data_info.json

# 阶段11 入库
$PY knowledge_interface_tools/search_index_data_interface.py insert_data_to_search_index \
  --data_file=$D/segment_knowledge_reportcenter_search_data.txt \
  --config_path=config/config_for_search_index.json --index_name_assign=wayfair
```

**`export PYTHONPATH` 是必须的**：手工单跑时 `sys.path[0]` 是脚本所在目录
（`knowledge_generate/`）而不是仓库根，`from knowledge_clear_tool...` 直接 ModuleNotFoundError。
任务服务跑的时候环境里带了这个变量，所以正常流程看不出来。

## 结果

| 项 | 值 |
|---|---|
| Dify 生成 | 12 条（1 个硬窗口 pages=[1,10]，4041 字符） |
| 去重后入库 | **7 条 segment，全部 `quality_level=high`、indexes 与向量齐全** |
| 页覆盖 | p1-3 / p3-4 / p5-5 / p5-6 / p6-7 / p8-8 / p10-10 —— 1~10 页全覆盖 |
| QA | 保持 92 活跃不变 |

丢掉的 5 条：3 条是 Dify 对第 5 页吐了完全相同的三份（内容逐字相同），
2 条（原 #3 pages[3,4]、#9 pages[6,7]、#11 pages[7,8,9]）被入库去重判为近似重复，
其内容都被保留下来的相邻段落覆盖，无内容丢失。

## 两个顺带发现（未处理）

1. **入库去重对长段落会静默失效**：插入日志里 8 次
   `too_many_clauses: maxClauseCount is set to 1024` —— 去重用的混合检索把整段正文
   丢进 `multi_match`，段落一长子句数就爆掉，那一条就等于没查重直接插。
2. **补了段落也救不回原问题**：「如何导出链接流量数据」BM25 与向量都仍然召不到报告中心
   （向量 top100 都进不去）。原因是官方译法用「曝光量/会话/列表(listing)」，
   用户说的是「链接/流量」，词面和语义都对不上。
   换成「如何下载报告中心的报告」能排到 #2（0.946）。
   要真正答上这个问题，得补一条显式的「导出链接流量/曝光数据」QA。
