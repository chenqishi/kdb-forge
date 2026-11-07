# 致趣(Zhiqu/Bes) 企微外部联系人列表接口调用方法

> 接口：`POST /mochat/open-api/contact/list`（获取企业微信外部联系人基础信息）
> apifox：`api-322601955`
> 说明：该接口属于「企微联系人」域，**与活动(meeting)无关**，不走活动同步链路。
> 已于 2026-06-18 用新客户凭证实测调通（`code: 0`）。

## 基本信息

| 项 | 值 |
|---|---|
| Base URL | `https://openapi.beschannels.com` |
| Path | `/mochat/open-api/contact/list` |
| Method | `POST` |
| 鉴权 | `access_token` 放 **query string**（不是 header） |
| Body | **JSON**（注意：不是会议类接口的 form 表单） |
| 是否需要 wx_appid | **否** |

## 鉴权（换 token）

无签名/HMAC，纯凭证交换。`POST /api/get-access-token`，JSON body：

```json
{ "appId": "<appId>", "appSecret": "<appSecret>" }
```

返回 `{"code":0,"data":{"access_token":"...","expires":7200}}`，token 2 小时有效。

本次实测凭证（新客户）：
- `appId` = `zq_7ab44cae`
- `appSecret` = `8C2D31047F7DC9A04D706B8C18FE43AD`

## 请求参数

Query：
- `access_token`（必填）

JSON body：
- `page`（必填, int）页码
- `page_size`（必填, int）每页条数
- `contact_id`（可选, string）外部联系人 ID
- `wx_external_userid`（可选, string）第三方加密企微 ID
- `plaintext_external_userid`（可选, string）明文企微 ID
- `unionid`（可选, string）多个用逗号分隔

## 调用方式（独立实现，无外部框架依赖）

```python
import json
import urllib.parse
import urllib.request

BASE_URL = "https://openapi.beschannels.com"
APP_ID = "zq_7ab44cae"
APP_SECRET = "8C2D31047F7DC9A04D706B8C18FE43AD"


def _post_json(path, json_body=None, query=None, timeout=20):
    url = BASE_URL + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = json.dumps(json_body or {}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def get_access_token():
    resp = _post_json("/api/get-access-token",
                      json_body={"appId": APP_ID, "appSecret": APP_SECRET})
    if resp.get("code") != 0:
        raise RuntimeError(f"获取 token 失败: {resp}")
    return resp["data"]["access_token"]


def list_contacts(page=1, page_size=20, **extra):
    token = get_access_token()
    body = {"page": page, "page_size": page_size}
    body.update(extra)  # contact_id / wx_external_userid / plaintext_external_userid / unionid
    return _post_json("/mochat/open-api/contact/list",
                      json_body=body, query={"access_token": token})


if __name__ == "__main__":
    print(json.dumps(list_contacts(page=1, page_size=20), ensure_ascii=False))
```

要点：
- `access_token` 放在 query string，业务参数放在 **JSON body**。
- contact/list **不需要** `wx_appid`。
- token 2 小时有效；生产环境建议缓存 token，命中 `code=10003`（过期）时刷新重试一次。

## 成功返回示例

```json
{
  "code": 0,
  "msg": "成功",
  "data": {
    "list": [
      {
        "id": 2941417,
        "wx_external_userid": "wmswaxEAAACNp8bCaVWOnGtXDQxpKfJw",
        "name": "乡村音乐配普洱",
        "email": "",
        "unionid": "",
        "user_owner": [
          { "employee_id": 51671, "name": "美客多跨境小助手小唐", "is_primary": 0 }
        ]
      }
    ],
    "page": { "page": 1, "perPage": 20, "totalPage": 48, "total": 95 }
  }
}
```

## 排查

- token 阶段报错 → appId/appSecret 无效或未开通。
- `code == 10003` → token 过期，刷新后重试。
- 其它非 0 `code` → 该客户未开通 contact/list 权限或入参问题，按 `msg` 处理。
