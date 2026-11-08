# kdb.mining.chat.media.get_chat_image_minio_runtime

## Signature

`get_chat_image_minio_runtime()`

## Inputs

原聊天图片开关、环境变量、多模态与 MinIO 配置。

## Outputs

缓存同一运行字典；禁用/缺配置/客户端初始化失败时沿用空字典，保留 bucket、上传前缀和 URL 优先级。

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Source

`src/kdb/mining/chat/media.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
