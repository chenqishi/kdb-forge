# 多语言识别服务

基于 fastText 语言识别模型构建的 RESTful API 服务，可以识别 176 种语言。

## 功能特性

- 支持 176 种语言识别
- 基于 Flask 框架，轻量高效
- RESTful API 接口
- 返回语言名称和置信度
- 健康检查接口

## 安装依赖

```bash
pip install flask fasttext requests
```

## 使用说明

### 1. 启动服务

默认配置启动（端口 8007）：
```bash
python multi_language_service.py
```

自定义配置启动：
```bash
python multi_language_service.py --host 0.0.0.0 --port 8080 --model_path /path/to/lid.176.ftz
```

参数说明：
- `--host`: 服务监听地址，默认 `0.0.0.0`
- `--port`: 服务端口号，默认 `8007`
- `--model_path`: fastText 模型文件路径，默认使用项目中的 `model/lid.176.ftz`

### 2. API 接口

#### 健康检查接口

**请求：**
```bash
GET http://localhost:8007/health
```

**响应：**
```json
{
    "status": "ok",
    "model_loaded": true
}
```

#### 语言预测接口

**请求：**
```bash
POST http://localhost:8007/lang_predict
Content-Type: application/json

{
    "text": "これはテストです。"
}
```

**响应：**
```json
{
    "lang": "japanese",
    "confidence": 0.9999,
    "label": "__label__ja"
}
```

返回参数说明：
- `lang`: 识别出的语言名称（如 "japanese"）
- `confidence`: 置信度（0-1之间）
- `label`: 原始 fastText 标签（如 "__label__ja"）

### 3. 使用示例

#### Python 请求示例

```python
import requests

# 语言预测
response = requests.post(
    "http://localhost:8007/lang_predict",
    json={"text": "これはテストです。"}
)

result = response.json()
print(f"语言: {result['lang']}")
print(f"置信度: {result['confidence']}")
```

#### cURL 请求示例

```bash
# 健康检查
curl http://localhost:8007/health

# 语言预测
curl -X POST http://localhost:8007/lang_predict \
  -H "Content-Type: application/json" \
  -d '{"text": "これはテストです。"}'
```

### 4. 运行测试

运行提供的测试脚本：
```bash
python test_multi_language_service.py
```

测试脚本会测试多种语言的识别效果，包括：
- 日语
- 英语
- 中文
- 法语
- 西班牙语
- 俄语
- 韩语
- 德语
- 意大利语
- 阿拉伯语
- 葡萄牙语
- 泰语

## 支持的语言

服务支持识别 176 种语言，包括但不限于：

| 语言代码 | 语言名称 | 语言代码 | 语言名称 |
|---------|---------|---------|---------|
| zh | Chinese | ja | Japanese |
| en | English | ko | Korean |
| es | Spanish | ar | Arabic |
| fr | French | ru | Russian |
| de | German | pt | Portuguese |
| it | Italian | th | Thai |

完整的语言列表请参见 `LANGUAGE_MAP` 字典。

## 错误处理

服务会返回以下错误：

### 400 错误 - 请求参数错误
```json
{
    "error": "缺少必需参数: text"
}
```

### 500 错误 - 服务错误
```json
{
    "error": "模型未加载"
}
```

## 模型说明

服务使用 fastText 官方预训练的语言识别模型 `lid.176.ftz`。

- 模型下载地址: https://fasttext.cc/docs/en/language-identification.html
- 模型文件: lid.176.ftz
- 支持语言数: 176
- 模型大小: 约 131 MB

## 注意事项

1. 确保模型文件 `lid.176.ftz` 存在于 `model/` 目录下
2. 文本长度建议不要过短（至少几个字符），以保证识别准确性
3. 对于混合语言文本，服务会返回主要语言
4. 置信度越高，识别结果越可靠

## 日志

服务会输出详细的日志信息，包括：
- 模型加载状态
- 请求预测信息
- 错误和异常信息

日志格式：
```
[INFO] [2024-01-01 12:00:00] 正在加载语言识别模型: /path/to/lid.176.ftz
[INFO] [2024-01-01 12:00:01] 模型加载成功
[INFO] [2024-01-01 12:00:02] 启动多语言识别服务 - 0.0.0.0:6000
```

## 性能

- 模型加载时间: ~1-2秒
- 单次预测时间: <10ms
- 支持并发请求

## 开发者

qishichen (263436967@qq.com)

## 许可证

Copyright (c) 2024 qishichen, Inc. All Rights Reserved

