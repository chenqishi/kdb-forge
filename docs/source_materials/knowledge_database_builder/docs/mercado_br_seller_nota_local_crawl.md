# Mercado 巴西卖家页单页本地抓取 + QA 抽取

## 何时用这篇

需要**本地**抓一两个网页、抽 QA、只产审核文件不入 ES 时用这套。
典型场景：Mercado `vendedores.mercadolivre.com.br|.mx` 的 `/nota/`、`/aprender/` 卖家学习页补洞。

批量、要入库的正式任务仍走任务服务 `html_qa_segment_mining`，见 `docs/mercado_mx_help_crawl_task.md`。

## 为什么不用现有全链路（三个硬阻塞）

1. `control_service/html_kg_gen_task_control.py` 的 `__init__` 建 MySQL 连接池 + 调远程类目 API，
   本机跑必炸；且没有 stage 子集参数，stage 列表是硬编码 list，只能改副本。
2. `WebBatchCrawler.__init__` **无条件** `setup_driver()`，写死 `/usr/local/bin/chromedriver`。
   本机 ChromeDriver 144 vs Chrome 150，起不来 —— **连只做文本提取的 stage 2 也挂**
   （`process_crawled_content_json_format` 仅为提取文本就实例化了整个类）。
3. Mercado `vendedores.*/nota` 卖家页在 Selenium 下会卡住（`docs/mercado_mx_help_crawl_task.md` 已记录），
   但 **firecrawl 能稳定抓到正文** —— 所以正文源直接用 firecrawl，完全不碰浏览器。

## 方案

新增 `knowledge_crawler_tool/web_crawl/single_page_local_crawl.py`：
requests 直取 HTML + Dify firecrawl workflow 取正文，产出**与 stage 2 完全同构**的页面 JSON 和 TSV 映射。
后面翻译 / 抽 QA / 质量分级 **全部复用现有 CLI，零新逻辑**。

配套改动：`WebBatchCrawler.get_filename_from_url` 与 `extract_formatted_text_by_flat` 改 `@staticmethod`
（方法体本来就不用 `self`），这样新脚本能复用 slug 规则和 HTML 清洗规则而**不触发 chromedriver 初始化**。
原有 `self.xxx()` / `crawler.xxx()` 调用点行为不变。

## 完整命令

```bash
cd /Users/chenqishi/stone_fish/knowledge_database_builder
export PYTHONPATH=$PWD
PY=/opt/anaconda3/envs/py39/bin/python      # 本机唯一带 selenium/bs4/fire/requests 的解释器
DD=$PWD/data/mercado/local/html
FLAG=mlb_taxas_20260806
URL=https://vendedores.mercadolivre.com.br/nota/como-funcionam-as-taxas-do-mercado-livre

# 0. Dify 连通性（翻译/抽QA 的唯一后端，写死 app key，换不了模型）
curl -sS -m 15 -o /dev/null -w 'dify http=%{http_code}\n' http://120.77.147.247:5001/v1/workflows/run
# 405 = 服务在（GET 不允许），正常

# 1. 抓取
$PY knowledge_crawler_tool/web_crawl/single_page_local_crawl.py crawl_single_page \
  --url="$URL" --output_dir=$DD --flag=$FLAG \
  --client=mercado_local --platform=mercado_local \
  --content_type=normal --category_name=业务地区-巴西

# 2. 葡译中：firecrawl_content -> translated_text
$PY knowledge_clear_tool/knowledge_translate_by_dify.py run_batch_translate_html_json_content \
  --input_file=$DD/crawler_and_process_results_$FLAG.txt \
  --output_file=$DD/web_crawler_translated_$FLAG.txt \
  --field_num=-1 --process_field=firecrawl_content

# 3. 抽 QA（读 translated_text）
$PY knowledge_clear_tool/knowledge_html_clear_by_dify.py run_batch_clear_html_content \
  --input_file=$DD/web_crawler_translated_$FLAG.txt \
  --output_file=$DD/web_crawler_clear_qa_$FLAG.txt \
  --process_field_num=-1 --process_field=translated_text

# 4. 质量分级 high/mid/low
$PY quality_tools/qa_quality_tools.py run_batch_re_clear_qa_info \
  --input_file=$DD/web_crawler_clear_qa_$FLAG.txt \
  --output_file=$DD/web_crawler_reclear_qa_$FLAG.txt --process_field_num=-1

# 5. 汇总人工可读产物
$PY knowledge_crawler_tool/web_crawl/single_page_local_crawl.py export_local_qa_result \
  --reclear_map_file=$DD/web_crawler_reclear_qa_$FLAG.txt --output_dir=$DD --flag=$FLAG --source_url="$URL"
```

**不跑 stage 3 多模态**（`data_preprocess/multimodal_process.py`）—— 它是历史上 Mercado 任务反复卡死的环节，
纯文字 QA 用不上，直接跳过。跳过后翻译/抽 QA 的 `process_field` 就用 `firecrawl_content` / `translated_text`，
不要用默认的 `content_with_multimodal_unsderstanding`（那个字段不会存在，下游会**静默跳过**整页）。

## 目录约定 `data/mercado/local/html/`

`<客户族>/<库>/<数据类型>` —— mercado 客户族 / `mercado_local` 索引 / html 来源。
这是本次新起的约定，仓库里原本没有这种三段式（原有的是 `data/<client>/<YYYYMMDD>/`
和 `data/payoneer_olive/<平台>/<站点>/`）。后续 mercado 本地抓取沿用这个路径。

产物（`<slug>` = 域名+路径拍平）：

| 文件 | 说明 |
|---|---|
| `<slug>.html` | requests 取回的原始 HTML |
| `<slug>.firecrawl.txt` | firecrawl 正文 markdown（葡语），**QA 的真正正文源** |
| `<slug>.json` | stage2 同构页面 JSON |
| `<slug>.json_trans.json` | +`translated_text`（中文）、`is_translate=1` |
| `<slug>.json_trans.json_qa_quality.json` | `{high, mid}` |
| `<slug>_re_clear...._qa_quality_re_clear.json` | `{high, mid, low}` |
| `crawler_and_process_results_<FLAG>.txt` 等 4 个 TSV | 各阶段映射，每阶段追加一列，下游一律读最后一列 |
| `qa_result_<FLAG>.json` / `manifest_<FLAG>.json` | 人工可读汇总 |

`_trans.json` / `_qa_quality.json` 这种后缀叠加是现有管线的既有行为
（`knowledge_translate_by_dify.py:186`、`knowledge_html_clear_by_dify.py:180` 都是 `split('\.')`，
字面反斜杠点，实际不切分）。保持一致，别去"修"，否则和线上历史产物对不上。

## 2026-08-06 首次执行结果

URL：`https://vendedores.mercadolivre.com.br/nota/como-funcionam-as-taxas-do-mercado-livre`（平台佣金说明页）

- HTML 104847 字符 → firecrawl 正文 4360 字符 → 中文 2306 字符
- **QA 6 条，全部 high/优质，mid=low=0**
- 数字全部保真：经典 10%~14% / 高级 15%~19%、R$12.50 以下固定费用为单价 50%、
  R$12.50~R$79 三档、R$79 以上无固定费用、免运费补贴门槛 R$120
- firecrawl 原文尾部确实带 cookie 声明 / 登录提示 / "下一篇内容" 导航样板文案
  （`MEMORY.md` 记录的 vendedores 页已知问题），但**Dify 质量过滤全部滤掉了**，6 条 QA 无一污染

已知小瑕疵：QA 中「成本模拟器」丢了链接 `http://www.mercadolivre.com.br/simulador-de-custos`
（markdown 链接在抽取时被去掉）。若要入库，建议人工补回。

## 若要入库（本次未做）

用户本次只要原文 + QA，未做 schema 转换、未做段落知识、未入 ES。后续入库需：

1. `commons/schema_trans.py batch_trans_qa_to_search_data` 转 ES 行
2. 标题加 `巴西 ` 前缀（`mercado_local` 该索引的既有约定，全部巴西/墨西哥 QA 都有国别前缀）
3. 类目 `业务地区-巴西`，`category_id=2080246249920495618`（**仅限 `mercado_local`**；
   `mercado_all_kg` 的巴西 ID 是 `2084129700058812418`，两者不能混用）
4. `knowledge_interface_tools/search_index_data_interface.py insert_data_to_search_index`

## 失败预案

- **firecrawl 返回空**：脚本会直接 `RuntimeError` 中止，不产半成品。改用
  `knowledge_crawler_tool/web_crawl/login_doc_crawler.py` 的 playwright-CDP 方案
  （见 `docs/payoneer_olive_doc_crawl.md`，本机唯一能跑通的浏览器方案）取正文回填 `<slug>.html`，
  再从步骤 2 继续。
- **Dify 不通**：停下来，别自己换模型。HTML QA 链路 app key 写死在
  `knowledge_clear_tool/knowledge_html_clear_by_dify.py:121-125`，`llm_backend` 传非 dify 会被直接忽略。
