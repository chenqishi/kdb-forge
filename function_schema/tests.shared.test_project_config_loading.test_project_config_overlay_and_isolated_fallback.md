# tests.shared.test_project_config_loading.test_project_config_overlay_and_isolated_fallback

## Signature

`test_project_config_overlay_and_isolated_fallback(tmp_path, content)`

## Inputs

合成数据、临时目录与 pytest 替身；不访问线上服务。

## Outputs

缺文件/非法 JSON 回退，合法配置浅覆盖；defaults 深复制且两个项目配置隔离。

## SQL

无直接 SQL；外部依赖在测试中由替身隔离。

## Source

`tests/shared/test_project_config_loading.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
