# tests.offline.test_document_links.test_current_document_relative_links_exist

## Signature

`test_current_document_relative_links_exist()`

## Inputs

仓库 README.md、AGENTS.md、MEMORY.md 及 docs 下所有 Markdown。按行读取，解析当前维护文档使用的行内 Markdown 链接，支持普通路径及尖括号路径。

## Outputs

检查相对链接本地目标存在且解析后位于仓库内，错误包含来源文件、行号、目标；断言实际检查到链接。跳过代码围栏、带 scheme/host 的外部链接及纯锚点；带锚点的文件链接仍检查文件。不是完整 Markdown 解析器，不检查引用式链接、标题锚点或外网可用性。

## SQL

仅本地只读扫描；无 SQL、网络、子进程或 Git 命令。随默认离线套件运行，不要求检出目录存在 .git。

## Source

`tests/offline/test_document_links.py`
