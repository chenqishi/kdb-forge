# extract_formatted_text_by_flat

## 所属文件
`web_batch_crawler.py` - `WebBatchCrawler` 静态方法（`@staticmethod`）

不依赖实例状态，可直接以 `WebBatchCrawler.extract_formatted_text_by_flat(html_file)` 调用，
无需实例化（实例化会启动 chromedriver）。`single_page_local_crawl.py` 依赖这一点复用 HTML 清洗规则。

## 功能
把本地 HTML 文件压平成「按 body 直接子元素分段」的格式化文本，供下游翻译 / QA 抽取按
`\n--------\n` 分隔符再切块。

## Inputs
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| html_file | str | 是 | 本地 HTML 文件路径，UTF-8 读取 |

## Outputs
| 类型 | 说明 |
|------|------|
| str | 各 body 直接子元素 `prettify()` 后用 `\n--------\n` 连接的文本；无 `<body>` 时返回 `""` |

## 逻辑说明
1. BeautifulSoup 解析，`decompose()` 掉所有 `<script>`
2. 清理所有标签属性，只保留 `href` 和 `src`
3. 取 `<body>` 的直接子元素，跳过纯空白文本节点
4. 每个子元素 `prettify()`（无该方法则 `str()`），非空则加入
5. 用 `\n--------\n` 连接返回

## 下游约定
- 该分隔符是 `knowledge_clear_tool/knowledge_html_clear_by_dify.py` 的 `text_segment_by_limit(sep=['\n--------\n'])`
  和 `knowledge_translate_by_dify.py` 的 `translate_content_by_segment(sep='\n--------\n')` 的切块依据，不要改
- 产物写入页面 JSON 的 `formatted_text` 字段

## SQL
无。
