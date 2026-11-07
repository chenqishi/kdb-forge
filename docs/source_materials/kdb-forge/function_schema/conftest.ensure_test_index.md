# ensure_test_index

## 所属文件
`tests/conftest.py`

## Inputs
pytest session、`repo` fixture、测试索引名。
## Outputs
集成测试运行时确保测试索引存在并刷新；纯离线测试不建立 ES 连接。
## SQL
无。
