# kdb.__init__.module

## Inputs

导入 kdb 包或请求 KnowledgeRepository、KnowledgeService、SearchDataInterface 公开导出。

## Outputs

包使用惰性 __getattr__ 从当前 services/forge_compat 与 retrieval/application 导出同一实现；未知名称抛 AttributeError。包内依赖与子进程模块入口均使用 kdb.*，配置/静态资源由 shared/config/paths 解析，不注入外部仓库或根业务别名。

## SQL

包导入不主动建立 SQL/ES 客户端；具体初始化由公开对象原有调用阶段执行。

## Source

`src/kdb/__init__.py`。所列 SQL 表字段来自此实现的参数化查询；未取得额外 DDL，不宣称完整表结构已核验。
