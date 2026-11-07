# render_multimodal_urls

## 所属文件
`knowledge_interface_tools/search_index_data_interface.py`

## 背景

多模态附件的地址在**入库时**由 `join_multimodal_contents` 写成占位符形式存进 `content`：

```
[multimodal_prefix]boot-admin/mercado/20260807/2085635537046671362.xls
```

真实域名（`config.multimodal_prefix`，如 `https://file.marsmind.cc/`）是**检索返回时实时拼**的，
所以改拼接规则只需要动检索侧，存量数据自动生效，不需要重刷 ES。

原来的实现是一句 `content.replace('[multimodal_prefix]', self.multimodal_prefix)`。
现在要求在拼出来的 URL 后面再带上 `?filename=<文件名>`，供文件服务返回正确的下载文件名：

```
https://file.marsmind.cc/boot-admin/mercado/20260807/2085635537046671362.xls?filename=test_name.xls
```

## 作用范围（已与用户确认）

- **只对内部 path 形式**（`[multimodal_prefix]{path}`）追加 `filename`。
- **外链不动**：`multimodal_contents[].path` 为空、只有 `url` 的条目，入库时 `content` 里存的就是
  原始外链，不含占位符，因此天然不受影响 —— 避免给第三方签名 URL 塞多余参数导致签名失效。
- `image / video / audio / file` 四种类型一视同仁。
- 文件名来源是 `multimodal_contents[].fileName`；该字段为空、或 doc 没有 `multimodal_contents`
  时，退化成只替换前缀的旧行为（不会拼出 `?filename=`）。

## Inputs
| 参数 | 类型 | 说明 |
|------|------|------|
| doc | Dict[str, Any] | 一条 ES 检索结果，需要 `content`（str）和可选的 `multimodal_contents`（list） |

## Outputs

无返回值，**原地修改** `doc['content']`。`content` 不是字符串或 doc 为空时直接返回。

## 实现要点

- path → fileName 的映射从 `doc['multimodal_contents']` 里取，**按 path 长度倒序**替换，
  避免一个 path 是另一个 path 前缀时（`a/b.png` vs `a/b.png.thumb`）先替短的把长的截断。
- 文件名用 `urllib.parse.quote(name, safe='')` 编码，中文/空格文件名不会破坏 URL。
- path 本身已带 `?` 时用 `&` 拼接。
- 逐条精确替换完成后，再兜底 `replace('[multimodal_prefix]', self.multimodal_prefix)`，
  处理 `multimodal_contents` 里没登记、或没有 fileName 的残留占位符。

## 调用点

| 位置 | 说明 |
|------|------|
| `search_data_by_query` | 单 query 检索 |
| `search_data_by_multi_query` | 多 query 检索 —— **原来漏了前缀替换**，本次一并补上 |
| `web_search_data` | `/web_search` |

## SQL
无。读 ES 检索结果，不写库。
