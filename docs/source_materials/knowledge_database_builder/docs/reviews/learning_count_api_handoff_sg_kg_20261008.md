任务标记：LEARNING-COUNT-API-20261008。目标是既有sg-kg检索重构会话，已知thread ID 01a0f061-f2ad-7b10-985c-cd856ca8a7bd、工作目录/root/kdb-forge；勿新开替代会话或重复任务。

用户最新要求：在旧、新两套检索服务中封装Java统计逻辑，原getLearningCount(indexName,start,end)使用默认口径；接口改名为 `POST /get_from_type_count`，增加字符串参数from_type，省略默认chat_auto。用户现已明确授权实施旧、新两版接口，新项目部分由该既有会话负责。保留已有任务标记，不因改名重复建任务。共同方案位于 `/root/knowledge_database_builder/docs/reviews/learning_count_api_plan_20261008.md`，请先阅读，请检查同任务标记防重，直接在隔离checkout实施、测试、补schema和交付报告；不等待再次确认。

拟POST /get_from_type_count，index_name（可兼容indexName）、from_type（默认chat_auto）、start/end；返回success/count/message。条件quality_level=high AND from_type=请求值；仅时间都提供时insert_time gte/lte，不能附加del_flag/audit/data_type/category或用from_type_norm代替。默认chat_auto时保留原学习量筛选口径，其他来源值精确匹配。原物理名，不自动拼公私库，不建缺库。建议native _count；相对Java默认_search可能截断10000的数值差异已明确列为方案事项。空名/正常0成功；异常/缺库/不完整分片失败但count0，保留原Java归0行为且错误可观测。

遵守新项目规则、函数schema、API/Service/Engine Router边界及隔离开发。不要修改旧项目；不要部署、重启、切配置/路由/别名、干扰迁移、真实ES写入或擅自commit/push。本通知不扩展早先迁移/重启权限。旧项目由原知识库检索以及挖掘会话负责。

已有只读可行性证据：Olive计数旧新均4939，9月1日至10月8日均2378；Local旧388/新387，时间窗口旧51/新50，缺额为10月7日源端新记录24522b3f0f2566e6606121d75920ad3e、新端不存在，不以接口改条件掩盖数据差异。新HTTP接口尚未实现，不可声称已经验收。
