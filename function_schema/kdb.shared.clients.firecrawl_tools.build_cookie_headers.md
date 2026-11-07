# kdb.shared.clients.firecrawl_tools.build_cookie_headers

## Signature

`build_cookie_headers(cookie=None, user_agent=None, extra_headers=None)`

## 功能

把仓库里已有的 cookie 表示法归一成 Firecrawl `headers` 字典。

存在的理由：`auth_config['cookie']` 在本仓库一直是 `"k=v; k2=v2"` 这种**裸串**
（`WebBatchCrawler.set_cookies_for_domain` 就是这么解析的），
而 Firecrawl 的 `headers` 要的是 `{"Cookie": "k=v; k2=v2"}` 字典。
直接把裸串塞给 firecrawl 会被拒（Dify 插件报 `Invalid headers format`）。

## Inputs

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| cookie | str/dict/None | 否 | `None` | 见下表 |
| user_agent | str/None | 否 | `None` | 非空时加 `User-Agent` 头 |
| extra_headers | dict/None | 否 | `None` | 追加/覆盖其它头 |

`cookie` 的三种形态：

| 传入 | 处理 |
|---|---|
| `"DEV-PORTAL-LANGUAGE=zh-CN; a=b"` | → `{"Cookie": "DEV-PORTAL-LANGUAGE=zh-CN; a=b"}` |
| `{"DEV-PORTAL-LANGUAGE": "zh-CN"}` | 键值对拼成 `k=v; k2=v2` → `{"Cookie": "..."}`；**但若字典里已含 `Cookie`/`cookie` 键，则视为已经是 headers 字典，原样透传** |
| `None` / `''` | 不产生 `Cookie` 头 |

## Outputs

| 类型 | 说明 |
|------|------|
| dict | headers 字典；**没有任何头时返回 `{}`** |

返回空字典而不是 `None`，调用方据此判断要不要往请求体里放 `headers`
（Firecrawl 传空 `{}` 是安全的，但不放更干净）。

## 依赖的外部接口

无。

## SQL

无。

## Source

`src/kdb/shared/clients/firecrawl_tools.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
