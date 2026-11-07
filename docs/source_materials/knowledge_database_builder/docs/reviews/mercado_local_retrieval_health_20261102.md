# Mercado Local检索只读检查（2026-11-02）

北京时间18:40检查main的 `mercado_local`：**索引及抽查检索链路正常**。当前路由Serverless、服务端8.17.0，native总文档18,416条，计数分片失败0。显式 `del_flag=0 / quality_level=high / audit_result IN [1,2,-1] / data_type=qa` 下13,882条；这一计数包含待审，不等于所有入口默认可见量。

| 请求 | 返回结果 | 耗时 |
|---|---|---:|
| main `/web_search`空文本分页 | 3条真实记录 | 51ms |
| main `/web_search`关键词“墨西哥” | 返回3条，总匹配291 | 338ms |
| main `/search`已有产品展示/广告暂停问题 | 3条，原样本ID首位 | 388ms |
| main `/search`已有付款账单审核时间问题 | 3条，原样本ID首位 | 372ms |
| main `/search`美客多墨西哥本土店入驻资料问法 | 3条，包含注册文件/账户等知识 | 273ms |
| sg经main公网8003 `/search`产品展示问题 | 3条，ID和顺序与main同请求一致 | 421ms |

全部6次HTTP200且返回真实记录，无错误占位。两条精确标题样本从已审核high QA中选取；服务使用默认过滤、top_k=3、use_synonyms=true。语义问法仅为基本相关性和可用性抽查，不是固定query集质量评测或压测。

空文本分页的total_count=10000是现有接口口径，不能用来代替实际库存18,416。没有修改数据、代码、配置或重启服务；未覆盖其他mercado索引、所有类目过滤以及浏览器前端完整调用链。

main版本、配置SHA和脱敏请求结果见 [mercado_local_retrieval_health_20261102.json](mercado_local_retrieval_health_20261102.json)。
