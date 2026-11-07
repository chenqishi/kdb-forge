# wayfair 任务 74256b78 段落重建 + 图片修复 2026-09-02

任务 `74256b780370585cae399772cbdf9c49`（`document_qa_segment_mining`，2026-03-26，235 个文件，
client=wayfair，index=wayfair）。

## 一、235 个文件的 segment 全军覆没，崩了两次

| 时间 | 崩溃点 | 死在第几个文件 | 产出 |
|---|---|---|---|
| 2026-03 | `KeyError: '8'`（旧兜底页码逻辑拿 `[1, len(data_json)]` 查页字典） | 21 | 54 条，阶段10/11 从未执行 |
| 2026-09-02 首次重跑 | `ValueError: inputs is empt`（只有图片的空页切出 chars=0 的段） | 7 | 26 条 |

两次都是**一条异常穿透 `fire.Fire` 打死整批**，而阶段日志只有一行 ERROR、任务状态照报成功。

修复（`knowledge_generate/knowlege_segment_builder_by_dify.py`）：

- 调 `dify_index.request_dify` 前判空，空段落记 warning 跳过
- 单个子段请求异常记 error 跳过，其余子段继续
- **`run_batch` 里单文件异常记 error 后 `continue`，不再中断整批**

回归测试 `tests/test_segment_builder_robustness.py`。main 上没有 pytest（py310 有 pytest
但缺 `openpyxl_image_loader`，py38 能跑代码但没 pytest），生产 python 下用
`/tmp/verify_seg_fix.py` 手工验证三项行为通过。

## 二、图片 bug：157/235 篇，冗余 9.7 倍

`page.get_images()` 返回的是**页面资源字典**，LibreOffice 转出的 PDF 会把全局图片资源
在每页重复列出，于是每一页都挂上了整篇文档的所有图。

判据不能只用「1 页 >5 张图」（只抓到 64 篇），要用复制签名
「每页图数相同 且 唯一图数 == 每页图数 且 总图数 == 页数 × 每页图数」：

```
受影响文件 157 / 235
图片条目 9097 → 实际唯一图 939（冗余 9.7 倍）
最严重：使用产品营销页面（PMP）.docx  22 页 × 44 张 = 968 条目，实际 44 张
```

**解析侧已在 `c52fd2d3c`（2026-07-29）修复**，改用 `page.get_text("dict")` 的
type=1 图片 block（`_extract_rendered_pdf_images`）。3 月那次解析早了 4 个月。

### 修复做法：按 md5 贴回，零 LLM 成本

实测新旧两条提取路径产出的**图片字节完全一致**（报告中心 13/13 md5 相同），
所以重解析后按内容 md5 把已有的 `public_url` / `s3_path` / `image_understanding` /
`image_ocr` / `is_valid*` 贴回去即可，**不需要重跑 VLM、也不需要重新上传**。

工具 `data_control_tools/refix_doc_images.py`（默认 dry-run）：

```bash
ssh main && cd /root/knowledge_database_builder
export PYTHONPATH=/root/knowledge_database_builder
/root/miniconda3/envs/py38/bin/python data_control_tools/refix_doc_images.py run \
  --task_id=74256b780370585cae399772cbdf9c49 --only_files=/tmp/dup_files.txt --execute=True
```

结果：

```
157/157 修复 | 失败 0 | 未命中 0
图片 9097 → 1124，按页正确分布
复用多模态结果 507 张；另 617 张旧解析里本来就没做多模态（判为无效的 logo/装饰图）
产物：各解析目录下 content_multimodal_fixed.json + 任务目录 translated_mapping_imgfixed.txt（235 行，157 行指向修复版）
```

原 `content.json` / `content_multimodal.json` 一律不覆盖，可回溯。

### 两个踩坑

1. **不能只查全局 `multimodal_data_info.json`**：它只收录上传成功的图，939 张唯一图里
   只有 503 张有 `public_url`，其余 436 张是多模态阶段判为无效的 logo/装饰图。
   只查全局表会把这 436 张全报成"未命中"（实测 3 个样本命中率 0）。
   改为**优先用文件自己的旧 `content_multimodal.json` 建映射**、全局表兜底。
2. **零文本页被丢掉不算分页变化**：旧解析里那些"零文本页"只是被 bug 挂了图才显得非空，
   新解析该页真没内容就被 `parse_pdf_to_json` 的 `if content:` 丢掉。原来的逐页比对要求
   页码集合完全相同，把 6 篇误判成分页不一致。现在的判定是三条同时成立：
   不能凭空多出页、丢掉的页本来就没文字、共有页文本逐页相同。

## 三、入库前闸门：整篇下架过的文章不再插入

`data_control_tools/skip_deleted_sources.py`。

判据是**活跃条数为 0 且有软删记录**。不能只看"有没有软删记录"——入库去重本身就会
打掉零星重复条目，235 篇里 103 篇都有这种零星软删，那不是下架。

```
全被软删（跳过）: 9 篇
从未入库        : 14 篇
部分软删（照插）: 103 篇
全部活跃        : 109 篇
```

9 篇下架文章（原本都是 `audit_result=2` + `quality_level=high` 的活跃知识，
其中 `托盘化.docx`、`订单导出.docx` 带批次标记 `flag='20260730'`）：

```
托盘化.docx / 托盘化指南.docx / 在 Partner Home 提交应收发票指南.docx
CastleGate_ CastleGate 支持服务.docx / Partner Home 后台中的条件性优惠.docx
订单导出.docx / Partner Home 产品链接状态与可查找性概览.docx
Partner Home 后台中的产品管理.docx / 通过 Partner Home (PH) 停产界面进行停产_重新上架.docx
```

用法（阶段10 之前插一刀）：

```bash
python data_control_tools/skip_deleted_sources.py split \
  --input_file=$D/segment_all235.txt          # 产出 .keep 与 .skipped
```

## 四、召回补强：给段落补卖家口语问法

段落自带 topics 用官方译法（曝光量/会话/列表(listing)/报告中心），卖家问的是
「链接流量数据怎么导出」。实测同一条段落：

| 问法 | 向量排名 |
|---|---|
| 如何下载报告中心的报告 | **#2**（0.946） |
| 如何导出链接流量数据 | **进不了 top100** |

`data_control_tools/augment_segment_topics.py`：按 task_id 圈段落，让模型写卖家口语问法，
生成 embedding 后**只追加** `indexes[]`，不动 `content` / `content_embedding` /
`keywords` / `tags` / `multimodal_contents`。默认 dry-run，带 `rollback` 子命令
（按文本 `removeIf` 剔除）。

## 五、单跑各阶段的命令与坑

**`export PYTHONPATH=/root/knowledge_database_builder` 是必须的**：手工单跑时
`sys.path[0]` 是脚本所在目录而不是仓库根，`from knowledge_clear_tool...` 直接
ModuleNotFoundError。任务服务的环境里带了这个变量，走正常流程看不出来。

```bash
PY=/root/miniconda3/envs/py38/bin/python
TID=74256b780370585cae399772cbdf9c49
D=data/off_task_data/$TID ; L=log/off_task_log/$TID

# 阶段9（位置参数：输入 flag from_file_name_field_num=1 platform_field_num=0 is_direct_output=1 use_image_content=1）
$PY knowledge_generate/knowlege_segment_builder_by_dify.py run_batch_get_segment_knowledge \
  $D/translated_mapping_imgfixed.txt $TID 1 0 1 1 1>$D/segment_all235.txt 2>$L/segment_all235.log

# 入库前闸门
$PY data_control_tools/skip_deleted_sources.py split --input_file=$D/segment_all235.txt

# 阶段10
$PY commons/schema_trans.py trans_segment_to_search_data_for_file \
  --input_file=$D/segment_all235.txt.keep --output_file=$D/segment_all235_search_data.txt \
  --field_num=0 --task_id=$TID --category_id=1 --category_name="默认分组" \
  --multimodal_mapping_path=$D/multimodal_data_info.json

# 阶段11
$PY knowledge_interface_tools/search_index_data_interface.py insert_data_to_search_index \
  --data_file=$D/segment_all235_search_data.txt \
  --config_path=config/config_for_search_index.json --index_name_assign=wayfair
```

## 六、其它

- 入库去重的混合检索对长段落会静默失效：`too_many_clauses: maxClauseCount is set to 1024`
  ——去重把整段正文丢进 `multi_match`，段落一长子句数就爆，那一条等于没查重直接插。
- ES 里该任务已有的 4957 条 QA 也带着同样的错图。按用户决定：本次**QA 重新生成但先不插入**，
  产物留盘评估；segment 直接入库。

## 补记：这轮暴露的全部 bug（2026-09-02）

段落生成脚本在这一轮里连续暴露三类崩溃，**每一类都会让整批任务阵亡**，而且日志只有一行
ERROR、任务状态照报成功：

| # | 异常 | 触发条件 | 修法 |
|---|---|---|---|
| 1 | `KeyError: '8'` | 页码不连续。既无文字也无图片的空白页被 `parse_pdf_to_json` 丢掉，`_get_segment_by_index` 却按 `len(dict)` 当上界并直接下标取值。实测 `欧盟 _ 英国阻燃要求.docx` 是 100 页但最大页号 113、中间缺 13 页 | 按**实际最大页号**算上界、取页时判存在；"前面多取一页"退到最近的已存在前页 |
| 2 | `ValueError: inputs is empt` | 只有图片没有文字的页切出 `chars=0` 的空段，`dify_tools` 对空 paragraph 直接抛 | 调 Dify 前判空跳过 |
| 3 | `AttributeError: 'NoneType' has no attribute 'replace'` | **短文档分支**（整篇 <2000 字符）一直没做 answer 判空，长文档分支早就有。Dify 偶发返回 None | 短文档分支补判空与异常兜底 |

最关键的一处修改是 **`run_batch` 里单文件异常 `continue` 而不是中断整批** —— 有了它才看得见
第 1、3 类的真面目；在此之前它们都表现为"整批 0 产出"。

### 空 index text 会让整条知识丢失

模型输出「[phrases]:」后面空着时，`''.split(',')` 得到 `['']`，一路带到 `indexes` 就是空 text。
DashScope embedding 对空输入返回 400，异常从 `process_one_data` 上抛，
**整条 segment 入库失败**——不是丢一个索引，是丢一条知识。772 条待插入里 21 条中招。

`schema_trans` 原本有防护但写的是 `if segment_info.get('phrases')` ——**列表非空 ≠ 元素非空**。

三层都补了：`parse_index_answer` 解析时滤空、`schema_trans` 构造 indexes 时逐项滤空、
`process_one_data` 生成 embedding 前剔掉空索引（兜底保护所有调用方）。

### 入库去重对长段落静默失效

插入日志里大量 `too_many_clauses: maxClauseCount is set to 1024`——去重用的混合检索把
**整段正文**丢进 `multi_match`，段落一长子句数就爆，那一条等于没查重直接插。
**本次未修**（会改变去重行为，需单独评估）。

### QA 重生成的图片问题（未解决，等决策）

用修图后的解析重跑 QA，结果图片引用几乎归零（旧 1351 → 新 1）。逐层追踪：

- 质检前（模型抽取产物）205 个图片 URL → 最终产物 3 个
- 逐条比对确认 QA 本身还在，**只有 URL 被剥掉**
- 剥它的是 `strip_hallucinated_image_urls`（前提是"占位符模式下模型不该输出裸 URL"）

**这个结论后来被推翻了，见下面"图片问题的真正原因"。**

已证实 `merge_segment_content` 的占位符分支本身正常（离线实测：传 map → 10 个 `[图N]`、
0 裸 URL；传 None → 反之），所以实跑时 map 是 None；**为什么是 None 尚未定位**。

`content_multimodal_fixed.json` 的 `text_content` 里内嵌图片 URL 数为 0（157 文件实测），
排除了"正文自带 URL"这个可能。

## 补记：772 条只落了 541 条，是被查重误杀（2026-09-02）

入库日志里没有一条技术性失败，全是 `插入数据失败: None, message: 数据重复`——205 条被判重。

### 机制

`commons/simility_tools.is_simility_knowledge`：

```python
if 'title_embedding' in doc_1 and 'title_embedding' in doc_2:  title_sim = cos(...)
elif 两边都没:                                                  title_sim = -1
...
min_sim_score = min(title_sim, content_sim)
if min_sim_score > title_basic_threshold:  return 1   # 数值规则
if is_need_llm:                            return LLM判断(doc_1, doc_2)
```

segment **没有 title**（日志里 `title:None`）→ `title_sim` 恒为 -1 → `min_sim_score`
恒为 -1 → **数值规则永远走不到**，判重 100% 由 LLM 决定。
机器上 `config/config_for_search_index.json` 是 `is_need_llm: true`（仓库里那份写的 false）。

放大器：查重召回用 `indexes[0].embedding`，而 segment 的 `indexes[0]` 是 keywords 拼接串，
top5 候选清一色同主题段落——正好是主题级 LLM 判官最容易判错的样本。

实测（每对 5 次）：

| 新段落 | 被判给 | content 余弦 | LLM 5 次 |
|---|---|---|---|
| 广告活动管理常见问答 第2页 | **同一篇第1页** | 0.873 | 1,1,1,1,1 |
| 关于报告中心 第6页（客户反馈报告） | **同一篇第5页**（会话量/转化率） | 0.897 | 1,1,1,1,1 |
| 广告活动效果 第1页 | 同一篇第2页 | 0.947 | 1,1,1,1,1 |
| Cold Transfer 第4页 | 同一篇第4页（真重复，全文一致） | 1.000 | 1,0,1,1,1 |

最后一行说明判断还**不稳定**：全文完全一样的两段，5 次里投出过一次「不重复」。

`too_many_clauses` 不是丢数据的原因——它让候选检索直接失败，那些反而插进去了。

### 对账口径

只在同一 `from_file_name` 内比对会**低估**丢失量（查重是全库范围的，误判对象常在别的文件）。
拉全部活跃 segment、正文归一化后全库 difflib：

```
231 条未落库
  全库找不到相似段落(<0.70)  163   ← 真丢
  只有部分重叠(0.70~0.95)     21
  库里已有几乎同样的(≥0.95)   47   ← 去重正确
（同一批数据按文件内口径只算出 143）
```

### 补插

`d2637b2a9` 给 `insert_data_to_search_index` 加了 `check_duplicate` 开关。流程：

```bash
# 1) 全库比对，剔掉 ≥0.95 的真重复 → segment_dupfp_reinsert.txt（184 条 / 93 文件）
# 2) 下架闸门
python data_control_tools/skip_deleted_sources.py split --input_file=$D/segment_dupfp_reinsert.txt
# 3) 关查重插入（分 3 片并行）
python knowledge_interface_tools/search_index_data_interface.py insert_data_to_search_index \
  --data_file=$D/dupfp_shard_00 --config_path=config/config_for_search_index.json \
  --index_name_assign=wayfair --check_duplicate=False
```

**判重逻辑本身未修**：`min()` 被 -1 毒化、segment 不该走主题级 LLM，两处都会改变全线入库行为，需单独评估。

## 补问法执行结果与一个新发现（2026-09-02）

714 条段落 / 221 个文件，新增问法 **9156 条**，跳过 0，失败 0（3 分片并行，约 27 分钟）。
ES 里抽查确认到位，例如 `基础运营_关于报告中心.docx` 第7页段落的 `indexes` 里已有
「链接的流量数据怎么导出？」「产品链接的流量数据在哪看？」。

顺手修了个替换 bug：`在哪里查询` 被短模式 `在哪里查` 切成 `怎么导出询`
（`54dea71`，改成按模式长度降序匹配、命中即返回）。

### 效果：召回解决了，排序没解决

只检索 segment 时，`如何导出链接流量数据` 下报告中心第5页从**进不了 top100 → #5**。
但在 QA+segment 的混合检索里 segment 仍然出不来。原因在打分函数：

```python
# knowledge_interface_tools/search_index_data_interface.py  _cal_similarity
title_similarity = self._cal_title_similarity(...)   # 只看 title_embedding / synonyms_title
content_similarity = cos(query, doc['content_embedding'])
if search_type == 'qa':
    if doc.get('title'): similarity = title_similarity + 0.2 * content_similarity
    else:                similarity = content_similarity      # ← 无 title 的 segment 走这里
```

**`indexes[]` 完全不参与最终打分**。它只有一条路能进分数——`_cal_title_similarity` 里
`text in synonyms_title` 且调用方传 `use_synonyms=True`——而那条路算出来的东西塞进
`title_similarity`，对无 title 的数据又被上面的分支丢掉。

于是 segment 的 score 恒等于「整页正文 vs query」的余弦（实测 0.53~0.60），
QA 的 score 是 `title_sim + 0.2*content_sim`（实测 0.76~0.89）。段落结构性地打不过 QA。
实测混合检索候选池 18~20 条**全是 QA**，segment 连候选都进不去。

服务返回给机器人的 `score` 就是这个 similarity（`knowledge_database_search_es.py:340`）。

**要让补问法真正生效**，得改 `_cal_similarity`：无 title 的数据取
`max(content_similarity, 最佳 index_similarity)`。这会把 segment 分数从 ~0.55 抬到 ~0.98，
直接改变全线排序（QA 与 segment 的相对次序），**需要单独决策，本次未改**。

## 新旧 QA 对比评测（2026-09-02，未插入，仅评估）

对象：157 个修图文件。新 = `content_multimodal_fixed_qa_add_quality_<TID>.txt`，
旧 = 同目录 `content_multimodal_qa_add_quality_<TID>.txt`（同一阶段，可比）。

### 规模与分级

| | 总数 | high | mid | low | 覆盖页次 | 答案URL |
|---|---|---|---|---|---|---|
| 新 | 5502 | 4382 (79.6%) | 1120 | 0 | 672 | 69 |
| 旧 | 5404 | 3519 (65.1%) | 1885 | 0 | 589 | 1163 |
| 旧(再清洗后) | 5404 | 3875 (71.7%) | 513 | 1016 (18.8%) | 589 | 1163 |

页覆盖 +14%：修图后页面切分正常了。旧产物完全没出 QA 的 2 个文件
（`订单管理_如何打印装运文件.docx`、`遵守木材法规.docx`）新的出了 46 / 67 条。
73/157 个文件新的条数少于旧的。

**注意**：新这轮没跑旧流程里的 `re_clear` 阶段（旧的靠它剔掉了 18.8% 的低质条目）。

### 覆盖率（148 个双方都有产出的文件，问题向量比对）

| 老问题在新产物里 | 占比 | | 新问题相对旧产物 | 占比 |
|---|---|---|---|---|
| ≥0.90 基本同一问题 | 54.0% | | ≥0.90 旧库已有 | 55.4% |
| 0.80~0.90 近似 | 27.1% | | 0.80~0.90 | 26.6% |
| 0.70~0.80 沾边 | 11.7% | | 0.70~0.80 | 12.7% |
| **<0.70 无对应（391 条）** | **7.2%** | | **<0.70 新增（277 条）** | **5.3%** |

### 那 391 条"没覆盖"拆开看

- 94 条判定无价值：纯元信息（"本文的类别是什么"/"最近更新时间"/"相关文章"/"图片的作用"）
- 272 条判定有价值，再查是否出现在文档正文里：
  - **176 条正文里确实有 → 真丢**（约占旧产物 3.3%）
  - 56 条部分在正文
  - **29 条正文里几乎没有 → 老解析每页挂全篇图片，从错图里编出来的**
    - 18 条是「蔚来/小鹏/理想/哪吒 造车新势力」，全部出自 `使用产品营销页面（PMP）.docx`
    - 另一批是 `品牌页创建与最佳实践.docx` 里凭空冒出的英文仓库/3PL/EDI 问答
    （这个文件在"有价值"口径下排第一 27 条，加上落地校验后**归零**）

真丢的分布很散，最多的文件也只有 15 条：CastleGate_多渠道订单履行服务管理 15、
如何利用客户反馈减少退货 13、EDI 设置 7、订单管理_标签打印故障排查指南 7、
如何为现有 SKU 添加新变体 7。而且 176 里仍混着"本文介绍什么主题？"这类元问题，
所以 176 是**上界**。

### 同一问题下的答案质量（2916 条匹配对）

- 917 对答案完全一致
- 盲评 103 对有差异的（A/B 顺序随机，判官不知道哪个是新的）：
  **新更好 32.0% / 旧更好 35.9% / 打平 32.0%** —— 在噪声范围内，判平手
- 答案长度：均值 134→84，但**中位数 55→55**；<10 字 4.0%→3.5%，
  <20 字 13.6%→13.3%，>200 字 4.8%→5.7%。均值差主要来自旧答案里的图片 URL 长尾，
  不是系统性变短
- 旧更好的典型失分点：新答案偶尔过简，例如
  「CPSC 采纳了哪项标准？」旧「…正式采纳 ASTM F2057-23 作为所有服装收纳家具的最新强制性能标准」
  新只有「ASTM F2057-23」；「如何撤销更改？」新只有「编辑」

### 结论

新 QA 更干净（high 占比 65%→80%，不再有错图幻觉，页覆盖 +14%），
答案质量与旧的持平，代价是丢了约 3% 的真知识点、新增约 5% 的知识点。

**插入前必须先解决图片问题**（答案里的图片引用从 1163 掉到 69），
另外要决定是否补跑 `re_clear` 阶段。

## 图片问题的真正原因（2026-09-02 复查，推翻前面的判断）

先前判断"送给模型的正文里有裸 URL，被 `strip_hallucinated_image_urls` 误判成幻觉"是**错的**。
读 `merge_segment_content` 可以确认：占位符模式下图片位置输出的是
`[图N]` + 「[图N]里的文字：OCR」+ 「[图N]的内容说明：图片理解」，**正文里一个 URL 都没有**，
所以剥裸 URL 是对的。

按阶段数了一遍才定位到真正的位置：

```
质检前 (content_multimodal_fixed_qa_*.txt)      6833 条 QA，[图N] 标记只有 10 个
质检后 (…_add_quality_*.txt)                    5502 条 QA，[图N] 残留 0，已还原 URL 10 个
```

占位符流程本身完全正常：日志里 102 个文件打了「图片占位符还原完成」，一共给模型提供了
398 张图的 `[图N]`。**问题是模型几乎不用这个标记** —— 6833 条里只写了 10 次。
没有任何东西被剥掉、被吃掉，10 个标记全部还原成功。

### 旧 QA 那 1095 个图片 URL 也不是好东西

| 校验方式 | 结果 |
|---|---|
| URL 是否存在于该文件的老解析产物 | **280 / 1095 = 26% 查无此图**（模型抄错） |
| 其余 815 个 | 指向的是「同一张图被重复上传出来的多个 URL」 |

以 `使用产品营销页面（PMP）.docx` 为例：老解析 968 个图条目里有 374 个**互不相同**的
`public_url` —— 因为多模态阶段把每个重复条目都当新图上传了一次，44 张真图被传成了 374 个地址。
修图后同一文件是 46 个条目 / 18 个 URL。

所以「1163 → 10」不是质量下降 26%，旧的那批本来就有四分之一是坏链、其余是冗余地址。

### 三个可选方案

| 方案 | 做法 | 代价 |
|---|---|---|
| A. 关占位符重跑 | `run_batch_clear_pdf_json_content --image_placeholder=0`，图片位置直接给裸 URL 让模型抄 | 约 1 小时。能拿回图片数量，但重新引入 26% 抄错的坏链，且模型看不到图里的内容 |
| B. 改提示词重跑 | 保持占位符，改 Dify QA 抽取应用的提示词让它真的用 `[图N]` | 要改 Dify 上的应用（仓库外），效果不确定，还要再跑一次 |
| C. 按页确定性挂图 | 入库时按 QA 的 `from_page` 区间，把该页的图直接写进 `multimodal_contents`，不经模型 | 需要新代码。零坏链、覆盖率最高，但图是"整页的图"而不是"模型挑的图" |

`multimodal_contents` 目前是 `add_multimodal_contents_to_content(content, map)` 从
**正文里已有的 URL** 反推出来的，所以方案 C 不是改配置能解决的，要动 `schema_trans`。

## 下架文章复核 + QA 侧补闸门（2026-09-03）

对方要求下架 5 篇：订单导出 / 托盘化 / 产品定价_如何在定价主页创建促销活动 (Archived) /
CastleGate_ CastleGate 支持服务 (Archived) / 商用级别标准概览。

### 库里现状：都已经删干净，本次重建也没带回来

| 文章 | 库里文件名 | 活跃 | 已软删 |
|---|---|---|---|
| 订单导出 | `订单导出.docx` | 0 | 18 (task 74256b78, flag=20260730) |
| 托盘化 | `托盘化.docx` / `托盘化指南.docx` | 0 | 10 / 33（同上） |
| 产品定价_如何在定价主页创建促销活动 | — | — | **全库 504 个文件名里没有** |
| CastleGate_ CastleGate 支持服务 | `CastleGate_ CastleGate 支持服务.docx` | 0 | 44（同上） |
| 商用级别标准概览 | `商用级别标准概览.docx` | 0 | 24 (task 508b09ae, 4/30 入库) |

segment 侧走了闸门，链路可追：

```
segment_final.txt                809 行
  ├─ .keep                       772 行   命中这5篇: 无
  └─ .skipped                     37 行   命中 19 条（托盘化指南 11 / CG支持服务 6 / 托盘化 1 / 订单导出 1）
segment_final_search_data.txt    772 行   无
segment_retry_insert.txt         231 行   无
segment_dupfp_reinsert.txt       184 行   无
```

**生成 19 条，插入 0 条。** ES 侧交叉验证：9/1 之后入库 721 条 / 221 个文件，无一来自这 5 篇。
补问法按 task_id 圈**活跃** segment，这几篇活跃数为 0，也碰不到。

内容级复核：把这 4 篇正文跟全库所有活跃文件逐一比对，最高相似度 0.26（无关文件），
没有换文件名还活着的副本。

`订单导出(3405) POC单独提供优先上传.docx`（活跃 37 条，task bd25d1d2，8/3 入库）
经确认是**替换版**，正常保留。跟已删的 `订单导出.docx` 正文相似度 0.31、问题零重合。

### QA 侧原来没有闸门，已补上

QA 产物是**按文件散在各解析目录**的（`content_multimodal_fixed_qa_add_quality_*.txt`），
没有逐条 JSON 可拆，原来的 `field_num` 用不上，等于这批 QA 从来没过闸门。

`92cbbf3` 给 `skip_deleted_sources.split` 加了 `name_field_num`，卡在阶段间的映射清单上：

```bash
cat $D/qa_regen_{0,1,2}.txt > $D/qa_regen_all.txt
python data_control_tools/skip_deleted_sources.py split \
  --input_file=$D/qa_regen_all.txt --name_field_num=1
```

结果：

```
157 个文件 5502 条 QA
  .keep      151 文件 / 5335 条（high 4230 / mid 1105）
  .skipped     6 文件 /  167 条（high 152 / mid 15）= 3.0%
     Partner Home 后台中的产品管理.docx                 59
     托盘化指南.docx                                   48
     Partner Home 产品链接状态与可查找性概览.docx          24
     订单导出.docx                                     14
     通过 Partner Home (PH) 停产界面进行停产_重新上架.docx   13
     在 Partner Home 提交应收发票指南.docx                 9
```

**以后插 QA 一律用 `qa_regen_all.txt.keep`。**

## 新 QA 上线：re_clear → 强制插入 → 自动审核 → 软删旧批次（2026-09-03）

用户决策：**不改图片方案，直接换新的**；为了不出现线上空窗，顺序是
**先强制插新的 → 跑自动审核 → 再软删旧的**；`re_clear` 补跑。

### 结果

| | 条数 | 文件 |
|---|---|---|
| 新 QA 活跃 | **4575**（high 4486 @audit=2，mid 89 @audit=0） | 151 |
| 旧 QA 软删 | **4772**（flag=`qa_regen_wayfair_20260903`） | 212 |
| 段落 | 714 活跃，本轮顺带从 audit=-1 审成 2 | 221 |
| 可检索总量 | 4607 → **5200**（+593） | |

回滚文件 `output/wayfair_qa_regen_20260903/rollback.jsonl`。

### re_clear 的实际效果

`quality_tools/qa_quality_tools.py run_batch_re_clear_qa_info`（纯本地 dice 去重，4.5 秒，无 LLM 成本）：

```
before: high 4230 / mid 1105 / low    0   = 5335
after : high 4509 / mid   89 / low  737   = 5335
```

high 反而涨了：`add_quality` 阶段按「`group_qa_count==1`」把一批打成 mid，
`re_clear` 用 `judge_qa_quality` 按质检标签重判，同时把组内重复挤进 low。
**low 不插**——线上现存 QA 里 low 为 0，且 low 全是组内重复条目。

### 命令

```bash
PY=/root/miniconda3/envs/py38/bin/python
TID=74256b780370585cae399772cbdf9c49; D=data/off_task_data/$TID
export PYTHONPATH=/root/knowledge_database_builder

# 0) 插入前必须先落 _id 快照，这是事后唯一能圈定「旧批次」的依据
#    （新旧两批 task_id / from_type / from_file_name 完全一样）

# 1) re_clear（输入是过完下架闸门的 .keep）
$PY quality_tools/qa_quality_tools.py run_batch_re_clear_qa_info \
  --input_file=$D/qa_regen_all.txt.keep --output_file=$D/qa_regen_reclear.txt --process_field_num=-1

# 2) schema 转换。re_clear 会追加一列，所以 field_num 用 -1，别沿用管线里写死的 9
$PY commons/schema_trans.py batch_trans_qa_to_search_data \
  --batch_file=$D/qa_regen_reclear.txt --output_file=$D/qa_regen_search_data_all.txt \
  --field_num=-1 --platform_field_num=0 --task_id=$TID \
  --category_id=1 --category_name="默认分组" \
  --multimodal_mapping_path=$D/multimodal_data_info.json
# 再滤掉 low → qa_regen_search_data.txt（4598 条）

# 3) 强制插入（必须关查重：新旧 QA 有 54% 是「基本同一个问题」，开着会成批打掉）
$PY knowledge_interface_tools/search_index_data_interface.py insert_data_to_search_index \
  --data_file=$D/qa_ins_$i --config_path=config/config_for_search_index.json \
  --index_name_assign=wayfair --check_duplicate=False       # 3 分片并行，约 30 分钟

# 4) 自动审核
$PY control_script/timing_auto_audit_kg.py --config config/config_es_engine.json \
  --index wayfair --from-type-norm "document,html" --minutes 10   # 先 --dry-run

# 5) 软删旧批次
$PY data_control_tools/retire_superseded_knowledge.py run \
  --config config/config_es_engine.json --index wayfair \
  --snapshot_file $D/old_qa_snapshot_20260903.json \
  --flag qa_regen_wayfair_20260903 --work_dir output/wayfair_qa_regen_20260903 \
  --new_since "2026-09-03 00:00:00" --execute
```

### 4598 送入 → 4575 落库，缺口全部有解释

- **9 条**：与同批另一条 `title`+`content` 完全相同 → 同 `_id` 互相覆盖，知识没丢。
- **14 条**：质检打了 `重复-N` 标签。`insert_data_to_search_index` 有一道显式闸门
  （`search_index_data_interface.py:1131`）`if '重复' in quality_info: continue`，
  是设计行为。**日志级别是 INFO，默认 WARNING 下完全看不见**，表现为静默丢数据。

### 同 _id 覆盖写：软删必须防的坑

`insert_data` 对内容完全相同的条目是**同 `_id` 覆盖写**，于是插入前的快照里
会有一部分 `_id` 已经被新数据占用（`insert_time` 变成本轮）。
本次 4957 条快照里有 **185 条**这样。按快照无脑软删 = 把刚插进去的新知识删掉。
`retire_superseded_knowledge.py` 用 `--new_since` 排除，带单测。

### 盘点口径纠正：别用「有没有 title」区分 QA 和 segment

入库管线会改写标题/正文，实测有 **72 条 segment 在 ES 里是带 title 的**。
按 title 分类会把它们算进 QA。**必须用 `data_type`**（`qa` / `segment`）。
这条如果搞错，软删快照里就会混进 segment。

## 本轮修掉的两个生产 bug（2026-09-03）

### 1. 自动审核脚本被异步 task 打死（`3d08a48e4`）

`timing_auto_audit_kg.py` 报 `'str' object has no attribute 'get'`，
表现为「待审 5289 条 / 成功 0 / 失败 1」，**一条都没更新**。

阿里云 ES Serverless 上两个坑连着出现：

1. `scroll_size=30` 时一批 24MB > `MAX_WRITE_SIZE_PER_REQUEST` 15MB 上限，整批被拒
   （返回 `{task:{status:{...}}, error:{...}}`，HTTP 200）；
2. 代码减半到 15 后，**单次运行超过 60 秒，Serverless 自动转异步**
   （即使传了 `wait_for_completion=true`），只回 `{"task": "<node>:<id>"}`——
   **`task` 是字符串**。`result.get("task", {}).get("status", result)` 当场 AttributeError。

脚本里本来就有 `_wait_for_task_result`，但**从来没被接上**。现在遇到字符串 task 就轮询；
同时修 `_wait_for_task_result`：任务带 error 时要原样返回整个结构，
只返回 `response` 会把 error 丢掉，让调用方失去减半重试的机会。
回归测试 `tests/test_auto_audit_update_by_query.py`（7 项）。

修好后一次跑完 5288 条：high 5199 → `audit_result=2`，mid 89 → `0`。

### 2. `EsHttpClient.bulk_update_doc` 一直没提交（`cf00c8b64`）

`filter_ad_knowledge_by_llm.apply_deletions` 早就在调它，但方法本身躺在工作区没提交，
机器 `git pull` 之后直接 `AttributeError`。补提交。

### 一个踩了两次的坑：`pgrep -f` 会自匹配 ssh 命令行

`ssh main 'pgrep -f "insert_data_to_search_index --data_file=..."'` —— ssh 远端那条
`bash -c` 的命令行里含同样的字符串，pgrep 匹配到它自己，于是「等插入结束」的循环
**永远不退出**，而且插入早就跑完了。memory 里记过 `pkill -f` 的同款问题，这次是 `pgrep`。
正确做法：把模式写进机器上的脚本文件，按路径调用（`/tmp/wf_ins_running.sh`）。
