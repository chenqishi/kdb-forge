# Wayfair 开发者门户官方中文重爬 2026-08-08

## 任务

```
task_id   = 9e92dc27cd9efc6185ce3b06bb529c99
task_type = html_qa_segment_mining
client=wayfair  user=wayfair_test2  index_name=wayfair
```

payload 照抄旧任务 `1f47a2e7cff6defe869fe1280ec7a8b1`，**只改三处**：

| 字段 | 旧 | 新 |
|---|---|---|
| `is_need_translated` | `true` | **`false`**（用官方中文，不再机翻） |
| `auth_config` | 无 | **`{"cookie": "DEV-PORTAL-LANGUAGE=zh-CN"}`** |
| `knowledge_objective` | 描述文字 | 改为中文重爬说明 |

定义与产出存档：`output/wayfair_zh_recrawl_20260808/`

## 结果

| 项 | 数量 |
|---|---|
| 爬取 | 26/26 页，全中文 |
| QA 入 ES | 938（+ FAQs 补跑 24）= **962** |
| 段落知识入 ES | **178** |
| **活跃合计** | **1140，全部 `del_flag=0`** |
| URL 覆盖 | 26/26 |
| 旧机翻数据 | `1f47a2e7` 的 1082 条全部 `del_flag=1`，无混杂 |

耗时 2h37m，阶段9（段落生成）最慢，89 分钟。

## 为什么在本机跑而不是 main

Firecrawl 的 `headers`/`actions`/FIRE-1 **按请求 IP 做地区限制**，中国大陆 IP 调用带 `headers`
的 scrape 直接 403（`Use of headers ... is not allowed by default in your country`），v1/v2 都一样。
cookie 正是通过 `headers` 传的，所以 main（120.77.147.247，深圳阿里云）走不通。

出口 IP 实测：本机 103.62.49.178（香港）✅ / `sg` 47.237.29.108（新加坡）✅ /
`alijp` 8.216.25.208（日本）✅ / main（深圳）❌。

注意：**firecrawl 本身在中国机器上可用**，不带 headers 的 scrape 从 main 正常返回，
被限制的只是 headers 这个功能。详见 `docs/wayfair_developer_zh_content_20260807.md`。

## 本机跑任务的三个前置条件

1. **task_id 无法提前算**（`md5(task_type + task_info + 时间戳)`）。要自己建记录：

   ```python
   import control_service.off_task_control_service as svc
   svc.script_base_dir = os.path.abspath('.')     # 服务启动时由 --script-dir 设置
   svc.init_mysql_connector()
   task_id = svc.generate_task_id(task_type, task_info)
   svc.insert_task_record(task_id, task_type, task_info)
   ```

   然后直接跑控制器（绕开队列/信号量）：

   ```bash
   python control_service/html_kg_gen_task_control.py \
     --script-dir="$PWD" --task-id=<id> --task-info='<json>'
   ```

2. **各阶段是 `subprocess` 调 `python` 命令**，Mac 上没有这个名字，要造 shim：

   ```bash
   mkdir -p /tmp/pybin && ln -sf /opt/anaconda3/envs/py39/bin/python /tmp/pybin/python
   export PATH=/tmp/pybin:$PATH PYTHONPATH=$PWD
   ```

3. **chromedriver 必须与 Chrome 大版本一致**。本机已从 144 升到 151
   （旧版备份 `/usr/local/bin/chromedriver.bak.144`），下载地址
   `https://storage.googleapis.com/chrome-for-testing-public/<版本>/mac-arm64/chromedriver-mac-arm64.zip`，
   装完要 `xattr -d com.apple.quarantine`。这解决了 MEMORY 里长期记的"本机跑不了 WebBatchCrawler"。

## 修掉的 bug：全角冒号导致整页 QA 静默丢失

首轮 26 页只产出 25 页，FAQs 丢了。链条：

1. 模型输出用了**全角** `问题：`，而 `parse_answer` 的正则只认半角 `问题:`
2. 解析出空列表
3. `add_quality_info_to_qa_json` 拿空文本调 Dify → `dify_tools.py:37` 抛 `ValueError: inputs is empt`
4. 异常把整页产出带没，**日志只有一行 ERROR，阶段照报成功**

判据：该页日志「问题：」全角 24 次、半角 0 次，「无法解析问答对」恰好 1 次。

修复（`knowledge_clear_by_dify_model_longcontent.py`）：

- `parse_answer` 的中文正则与 `q:/a:` 回退正则改成 `[:：]`
- `parse_quality_result`（第 639 行）同样只认半角，一并改掉
- `add_quality_info_to_qa_json` 加空值保护：空 QA 直接返回，不再调 Dify

验证：FAQs 单页补跑，修复前 0 条 → 修复后 **24 条 high**，已入库。
测试 `tests/test_knowledge_clear_longcontent.py`（全角/半角/混排/空列表 4 项）。

### 补跑单页的命令链

```bash
D=data/off_task_data/$TID
grep "posts_FAQs" $D/web_crawler_translated_$TID.txt > $D/translated_faqsfix.txt
python knowledge_clear_tool/knowledge_html_clear_by_dify.py run_batch_clear_html_content \
  --input_file=$D/translated_faqsfix.txt --output_file=$D/clear_qa_faqsfix.txt \
  --process_field_num=-1 --process_field=content_with_multimodal_unsderstanding
python quality_tools/qa_quality_tools.py run_batch_re_clear_qa_info \
  --input_file=$D/clear_qa_faqsfix.txt --output_file=$D/reclear_qa_faqsfix.txt --process_field_num=-1
python commons/schema_trans.py batch_trans_qa_to_search_data \
  --batch_file=$D/reclear_qa_faqsfix.txt --output_file=$D/reclear_qa_faqsfix_search_data.txt \
  --field_num=-1 --platform_field_num=0 --task_id=$TID --category_id=1 --category_name='默认分组' \
  --multimodal_mapping_path=$D/multimodal_data_info_$TID.json
python knowledge_interface_tools/search_index_data_interface.py insert_data_to_search_index \
  --data_file=$D/reclear_qa_faqsfix_search_data.txt --config_path=config/config_for_search_index.json \
  --index_name_assign=wayfair
```

## 已完成：剥离段落里的导航样板

178 条段落里有 27 条开头带 firecrawl markdown 自带的站点导航 + cookie 横幅。

**这些不是废数据，一条都没删**：导航前缀固定 764 字符，剥离后每条仍有 1473~3310 字符实质内容
（例如完整的沙盒测试三步操作指南）。做法是**剥离前缀**，工具
`data_control_tools/strip_nav_boilerplate.py`（默认 dry-run，带 `rollback` 子命令）。

```bash
# 先看对照
python data_control_tools/strip_nav_boilerplate.py run --task_id=<id>
# 确认后写库
python data_control_tools/strip_nav_boilerplate.py run --task_id=<id> --execute=True
```

结果：段落 178 条**仍含样板 0 条**，向量全部按新正文重算（抽查 `cos=1.000000`），
回滚文件 `output/strip_nav_boilerplate/rollback_*.jsonl`。

### 踩到并修正的三个判断错误

1. **不能用链接文字「词汇表」定位导航块结尾** —— 词汇表页面的正文标题本身就是 `**词汇表**`，
   `rfind` 会落到正文标题上把首行切掉。改用导航链接的 URL `posts/glossary)` 定位。
   **通则：定位样板边界要用只可能出现在样板里的特征（URL、结构标记），不要用正文也会出现的词。**
2. **`multimodal_contents` 不总是等于 `content`** —— 有 3 条是多段结构（文本+图片交替，3~5 段），
   样板只在第一段里。原先"两者相等才替换"的写法会漏改，改成**逐段剥离**。
3. **样板特征串不能取太宽** —— `所有主题`/`API 实验场` 正文里也有
   （如「所有主题 # Dropship Orders API」），一度误判 9 条正常段落。收紧到 cookie 横幅整句。

另：分段级要放宽占比安全阀（单个分段可能大部分是导航，实测 878 字符的段里 764 是导航），
整篇正文仍保持 0.5 的严格阀值。

### 要改哪些字段

| 字段 | 改 | 说明 |
|---|---|---|
| `content` | ✅ | 正文本体 |
| `multimodal_contents[].content` | ✅ | 逐段剥离 |
| `content_embedding` | ✅ | 按新正文重算，否则向量检索仍按旧文本匹配 |
| `indexes[]` | ❌ | 存的是关键词与衍生问题，不含样板，向量依旧有效 |
| `keywords` / `tags` | ❌ | 主题词，非原文 |

向量可确定性复现（重算与库存 `cos=1.000000`），所以**回滚备份只存文本**。

### 遗留：1 条纯样板 QA，保持 low 不删

有 1 条 QA 的问题和答案都是 cookie 横幅本身（103 字符，无可剥离内容），
已被质检打成 `quality_level=low`。检索侧默认只召回 `high`，所以它不会被召回，
按用户决定**保持现状不软删**。

## 其它踩到的点

- `data_type` 字段**没有 keyword 索引**，`data_type.keyword` 的 term/agg 查询返回空，
  要在客户端按 `_source` 过滤。
- 插入时 `ERROR: 更新索引mapping失败: 字段 indexes 的配置发生变化` 是索引已存在时的常规告警，
  不影响写入（实测 938 条全部落库）。
- 验收一律以 ES 实际 count 为准，不看任务的 `qa_num`（该值是入库前计数，不反映判重丢弃：
  本次 950 生成 → 938 入库）。
