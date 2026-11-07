# CSAT 满意度报告 API

**接口地址**：`POST https://api.marsmind.cc/inner_csat_report`

---

## 请求参数

**Headers**
```
Content-Type: application/json
```

**Body**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| start_time | string | 是 | 查询起始时间，格式 `YYYY-MM-DD HH:MM:SS` |
| end_time | string | 是 | 查询结束时间，格式 `YYYY-MM-DD HH:MM:SS` |
| channel_type | string | 是 | 渠道类型，如 `wechatcom_service_substitute` |
| client | string | 是 | 租户标识，由服务方提供 |

### 请求示例

```json
{
  "start_time": "2026-03-19 00:00:00",
  "end_time": "2026-03-20 23:59:59",
  "channel_type": "wechatcom_service_substitute",
  "client": "mercado"
}
```

---

## 响应

### 成功（HTTP 200）

```json
{
  "code": 0,
  "message": "success",
  "data": [ ... ]
}
```

### 参数缺失（HTTP 400）

```json
{
  "code": 1,
  "message": "start_time, end_time, channel_type, client 均为必填项"
}
```

---

## 响应数据结构

`data` 数组每个元素字段如下：

| 字段 | 类型 | 说明 |
|---|---|---|
| survey_instance_id | string | 问卷实例 ID |
| query_session_id | string | 会话 ID |
| account_id | string \| null | 客服账号 ID |
| session_create_datetime | string \| null | 本次会话第一条消息时间，`YYYY-MM-DD HH:MM:SS` |
| escalated | string | 是否转人工：`Yes` / `No` |
| escalation_datetime | string \| null | 转人工时间，未转人工时为 `null` |
| satisfaction | string | 满意度：`satisfied` / `neutral` / `unsatisfied`，未回复时为空字符串 |

### 响应示例

```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "survey_instance_id": "04ef1c44d89be1aa94b3bcf95319d4a8",
      "query_session_id": "wm4bsROwAAK1Deq9CID3eNLqa3ksz9Wg",
      "session_create_datetime": "2026-03-19 10:06:41",
      "escalated": "Yes",
      "escalation_datetime": "2026-03-19 10:06:41",
      "satisfaction": "satisfied"
    }
  ]
}
```
