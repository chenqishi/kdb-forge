# get_filename_from_url

## 所属文件
`web_batch_crawler.py` - `WebBatchCrawler` 静态方法（`@staticmethod`）

不依赖实例状态，可直接以 `WebBatchCrawler.get_filename_from_url(url, keep_attr_name)` 调用，
无需实例化（实例化会启动 chromedriver）。`single_page_local_crawl.py` 依赖这一点复用 slug 规则。

## 功能
根据URL生成唯一的文件名，通过域名、路径和可选的查询参数构建。

## Inputs
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| url | str | 是 | 待解析的URL |
| keep_attr_name | list[str] / str("all") / None | 否 | 需要保留到文件名中的查询参数名列表；若为 `"all"` 则保留所有查询参数；`None` 表示不保留任何查询参数 |

## Outputs
| 类型 | 说明 |
|------|------|
| str | 由域名、路径和可选查询参数拼接而成的文件名，仅包含字母数字、下划线和连字符。若拼接结果为空则返回 `"index"` |

## 逻辑说明
1. 解析URL，提取 `domain`（`.` 替换为 `_`）和 `path`（`/` 替换为 `_`）
2. 若 `keep_attr_name` 不为 `None` 且URL含查询参数：
   - 若 `keep_attr_name == "all"`：将所有查询参数追加到 path
   - 否则：仅保留名称匹配 `keep_attr_name` 列表中任一项的参数
3. 拼接 `domain_path`，过滤非法字符后返回
