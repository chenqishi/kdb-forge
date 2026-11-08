# kdb.__init__.module

## Inputs

导入 kdb 包或请求 SearchDataInterface 公开导出。

## Outputs

包使用惰性 __getattr__ 从 retrieval/application 导出同一 SearchDataInterface 实现；未知名称抛 AttributeError。仅保留原业务服务接口，不再导出 Forge 专用服务类。包内依赖与子进程模块入口均使用 kdb.*，不注入外部仓库或根业务别名。

## SQL

包导入不主动建立 SQL/ES 客户端；具体初始化由公开对象原有调用阶段执行。

## Source

`src/kdb/__init__.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
