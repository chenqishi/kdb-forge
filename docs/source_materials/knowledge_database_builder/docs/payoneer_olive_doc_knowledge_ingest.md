# payoneer_olive 平台官方文档 → 知识库（带上下文增强的挖掘流程）

日期：2026-08-07

上游是 `docs/payoneer_olive_doc_crawl.md` 爬下来的 10 篇平台官方文档
（`data/payoneer_olive/<平台>/<站点>/`）。本篇讲怎么把它们变成知识库里的 QA/段落知识。

## 一、TikTok Shop 站点二级类目

`TikTok Shop` 原来是个没有子类目的一级类目，知识全平铺在下面没法按站点管理。
用仓库已有的批量建类目工具，把站点建成二级：

```bash
cd category_sys_manager
python category_sys_manager.py batch_insert_category_from_file \
    --category_file=data/payoneer_olive_tiktok_sites.txt \
    --client=payoneer_olive --userId=2073772203129200642
```

清单 `category_sys_manager/data/payoneer_olive_tiktok_sites.txt` 里每行是**完整路径**，
`-` 是层级分隔符：

```
TikTok Shop-美国ACCU
TikTok Shop-美国CCCU
TikTok Shop-英国
TikTok Shop-欧盟(西德意法)
TikTok Shop-东南亚
TikTok Shop-印尼
TikTok Shop-墨西哥
TikTok Shop-全托管
```

结果：成功 8 / 失败 0 / 跳过 1（跳过的是已存在的父类目 `TikTok Shop`）。

| 站点 | categoryId |
|---|---|
| 美国ACCU | 2085544341263683586 |
| 美国CCCU | 2085544342572306433 |
| 英国 | 2085544350205939713 |
| 欧盟(西德意法) | 2085544348935065601 |
| 东南亚 | 2085544343893512194 |
| 印尼 | 2085544346418483202 |
| 墨西哥 | 2085544345155997698 |
| 全托管 | 2085544347701940225 |

`欧洲12国` 没建：那篇飞书 CN wiki 账号无权限、还没有知识，先建会留一个空类目。

## 二、把本地文档投递成挖掘任务

新增 `data_control_tools/build_doc_mining_tasks.py`。

```bash
# 只上传 + 生成载荷，不投递（默认，先看看要投什么）
python3 data_control_tools/build_doc_mining_tasks.py \
  --manifest data/payoneer_olive/crawl_manifest.json \
  --client payoneer_olive --index-name payoneer_olive --user payoneer_olive_admin \
  --work-dir output/payoneer_olive_doc_mining_20260807 \
  --key-prefix payoneer_olive/doc_crawl/20260807

# 单篇试跑
... --only "美国ACCU" --submit

# 全量
... --submit
```

### 为什么必须过一遍 MinIO

`document_qa_segment_mining` 的阶段1固定用 `MinioDownloader`
（`control_service/document_qa_segment_mining.py:51`），**没有本地文件通道**；
而且任务跑在 `main` 上，本机的文件它看不到。MinIO 是这条链路设计好的输入口，不用改流程代码。

好消息是 `.md` 是原生支持的：`wordtotext.batch_map_files_trans` 会把 `.md/.txt`
分派给 `parse_txt_to_json`（`knowledge_clear_tool/wordtotext.py:436`），
输出结构和 `parse_pdf_to_json` 完全一致，后面的多模态/QA/段落阶段无感。

### 为什么一篇文档一个任务

`category_id` / `category_name` 是**任务级**字段（`document_qa_segment_mining.py:60-62`），
一个任务只能挂一个类目。这批文档要按站点分别挂到 `TikTok Shop-<站点>` 下，所以一篇一个任务。

### 「优化后的流程」具体是哪几个开关

```json
{
  "enable_context_enrichment": true,
  "enable_chat_query_context": true,
  "enable_web_context": false,
  "quality_profile": "business_task_knowledge",
  "knowledge_objective": "...",
  "business_context_text": "..."
}
```

- `enable_chat_query_context` → `business_context_builder` 从 `data_chat_history`
  提炼该客户真实高频意图（这就是「根据历史对话优化」），同时会读已有知识边界（「根据检索」）。
- `enable_web_context` **保持关闭**：网络内容只能当业务背景，不能当文档事实写进答案。
- `quality_profile=business_task_knowledge` → 走通用质量后处理（悬空指代修复 + boilerplate 过滤）。

`knowledge_objective` 针对这批文档写死了拒绝项：社群招募话术（加群、领礼包、限时名额）、
目录导航式罗列、纯链接堆砌、协作留言、个案信息——这些是这批攻略里最主要的噪音。

## 三、坑

1. **图片必须改写成公网 URL**。`parse_txt_to_json` 只下载 `http(s)` 图片；
   相对路径 `images/x.png` 在任务机上不存在，会被降级成 `[图片: images/x.png]` 文本
   且**不报错**，截图里的后台路径/字段名就全丢了。
   md 走 S3 API 拉取不需要公开读，但图片是被 HTTP 下载的，**必须用 `https://file.marsmind.cc` 网关**：
   实测直连 `http://47.107.119.83:9000/boot-admin/...` 是 403，网关是 200。
2. **对象键 slug 别用固定兜底**。站点名纯中文时 ASCII slug 会被剥成空串
   （`英国`/`东南亚`/`印尼`/`墨西哥`/`全托管` 全中招），退回一个固定字符串会让它们
   共用同一个 MinIO 路径**互相覆盖**，而且上传全部"成功"。现在退回内容哈希。
3. **类目缺失要炸不要兜底**。找不到对应类目时直接 `KeyError`，
   不能默默落到默认分组——知识进了库但没归类，事后很难发现。
4. `files[].name` 会落到 `ext_info.from_file_name`，后续软删/对账按它匹配
   （见 `docs/wayfair_soft_delete_20260730.md`）。所以要去掉 " - 飞书云文档" 这种宿主尾巴，
   并在站点非「通用」时前缀站点名，保证唯一可读。
5. 同一份 `task_info` 重复投递会返回 **409 任务已存在**（task_id 由 task_info 哈希生成）。
   要重跑得改动 task_info 或先删任务记录。

## 四、执行记录

2026-08-07 全部 10 篇投递到 `http://120.77.147.247:6000`，一篇一个任务：

| 平台 | 站点 | 类目 | task_id |
|---|---|---|---|
| TikTok Shop | 美国ACCU | TikTok Shop-美国ACCU | `81d2cd15e6d693d05e59e84453507cfd`（试跑） |
| Mercado Libre | 通用 | Mercado Libre | `bc1c5e5d93c9d9cb5c5547ec0366c5db` |
| Noon | 通用 | Noon | `c2edc6b960209b59b2c434d401a92d3e` |
| TikTok Shop | 美国CCCU | TikTok Shop-美国CCCU | `fdd3f07a716a88ac8c4e4b7188734b4f` |
| TikTok Shop | 欧盟(西德意法) | TikTok Shop-欧盟(西德意法) | `72ef878077ef39174edc0b77eec4526e` |
| TikTok Shop | 英国 | TikTok Shop-英国 | `97223dcb2d3785642009224221a2a332` |
| TikTok Shop | 东南亚 | TikTok Shop-东南亚 | `a832208ccef0406c220f121cf0a457a5` |
| TikTok Shop | 印尼 | TikTok Shop-印尼 | `99ce3bb9f9ced006b9e70e174f435a81` |
| TikTok Shop | 墨西哥 | TikTok Shop-墨西哥 | `9df872c8e6d6c77ab227a23cb0341bf9` |
| TikTok Shop | 全托管 | TikTok Shop-全托管 | `f1d816f056383ee2c6b994746f3b01e7` |

### 本次产出（10 个任务全部 `运行完成`）

| 类目 | QA | segment | high |
|---|---:|---:|---:|
| Mercado Libre | 552 | 1 | 386 |
| TikTok Shop-印尼 | 288 | 14 | 62 |
| Noon | 236 | 1 | 224 |
| TikTok Shop-墨西哥 | 93 | 5 | 78 |
| TikTok Shop-东南亚 | 60 | 6 | 37 |
| TikTok Shop-全托管 | 58 | 1 | 59 |
| TikTok Shop-欧盟(西德意法) | 57 | 3 | 40 |
| TikTok Shop-美国ACCU | 31 | 1 | 27 |
| TikTok Shop-美国CCCU | 30 | 1 | 13 |
| TikTok Shop-英国 | 17 | 2 | 2 |
| **合计** | **1422** | **35** | **928** |

## 五、已知质量天花板：截图里的知识拿不到

英国那篇任务级 `qa_num=0`（ES 里只有 2 条 high），是这个问题最直接的证据。

### 链条

1. **QA 生成看不到 OCR**。`commons/schema_trans.py:590-606` 里，
   只有 `add_image_context=1` 才会把 `<image_ocr>` / `<image_understanding>` 拼进喂给模型的正文；
   而 QA 生成的所有调用方（`knowledge_clear_by_dify_model_longcontent.py:182/264/370/423/429`）
   **都写死 `add_image_context=0`**，注释是「image_context 改为在检索时加入」。
   于是模型在图片位置只看到一个裸 URL。
2. **模型把 URL 当答案，还抄错了**。逐阶段比对同一张图：
   多模态输入 `content_multimodal_all_content.txt` 里是 `default/20260807/`（16 次，全对）；
   到 **QA 生成产物** `..._qa_<flag>.txt` 就出现了 `default/20260807/20260807/20260807/`。
   segment 链路全程正确（它不经模型改写正文）。这个 URL 是 404 的。
3. **检索侧兜底也失效**。`add_multimodal_contents_to_content`（`commons/schema_trans.py:222`）
   是用 URL **精确匹配** `multimodal_map_dict` 的，抄错的 URL 匹配不上 →
   退化成 `{"type":"text","content":"<坏URL>"}`，`multimodal_contents` 里既没 OCR 也没图片理解。

### OCR 本身是好的

直接对那张图调 `MultimodalProcess._image_ocr` 返回：
`©9大专属社群福利 / 爆单运营指南 / 保姆级开店教程 / 官方小助理 / 周五直播课 / 开店训练营 /
下载飞书APP / 店铺诊断 / 选品工具 / ERP工具 / 官方极速入驻通道`。
`multimodal_data_info.json` 里 18 张图的 `image_ocr` / `image_understanding` / `is_valid:true` 齐全，
日志里 OCR 有效性校验只有 2 张没过，其余都是 `content_rich`。**是生成环节没用上，不是没识别出来。**

### 影响面和图文比强相关

| 站点 | 每张图对应的纯文字量 | 入库 QA |
|---|---:|---:|
| 东南亚 | 676 字 | 60 |
| 美国ACCU | 199 字 | 31 |
| 英国 | 144 字 | 17（2 high） |
| 全托管 | 117 字 | 58 |

图越密、文字越少，产出越差。这批平台攻略大量关键信息（后台路径、字段名、材料样例）在截图里。

### 两种修法

| | 做法 | 代价 |
|---|---|---|
| 根治 | QA 生成改成 `add_image_context=1`，把 OCR/图片理解喂给模型 | 改共用模块，影响所有文档挖掘任务，需部署到 main |
| 兜底 | `generic_knowledge_quality` 新增 `image_only_no_text` 拒绝原因 | 只拦住「答案=图片链接」的废行，拿不到图里的知识；同样需部署 |

兜底已在本地实现（含 4 个测试），根治**未动**，等确认。


## 相关文件

| 文件 | 说明 |
|---|---|
| `data_control_tools/build_doc_mining_tasks.py` | 上传 + 投递 |
| `category_sys_manager/data/payoneer_olive_tiktok_sites.txt` | 站点二级类目清单 |
| `tests/test_build_doc_mining_tasks.py` | 离线单测（19 个） |
| `function_schema/build_doc_mining_tasks.run.md` | 函数 schema |
| `output/payoneer_olive_doc_mining_20260807/tasks.json` | 本次任务载荷 + task_id |
