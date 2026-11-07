# main 检索故障只读检查（2026-10-30）

**最新状态：01:51 PaaS公网连接和实际检索均已恢复。** 公网域名与现有配置完全相同，解析出47.119.142.239、47.119.156.45，ES根接口HTTP200、版本8.17.0。payoneer_olive原始总文档62,057，payoneer为16,131；两个索引在原运行服务的分页和语义检索共4次均返回真实记录、无错误占位，两个语义查询首位均为抽样原记录。未修改配置或重启，恢复证据见[es_paas_recovered_20261030.json](es_paas_recovered_20261030.json)。下文保留01:12–01:43故障发生及复查的历史状态。

检查时间：北京时间01:12–01:17。用户反馈前端无法检索，要求检查PaaS和Serverless，并提到ES8.19。

## 结论

**PaaS当前配置的域名无法解析，导致payoneer_olive/payoneer无法访问；Serverless及其经过测试的检索服务链路正常。** 当前活动配置为8.17，Python客户端8.17.2；Serverless实际响应版本8.17.0。PaaS无法建立连接，不能确认其当前服务端版本和数据库存。

main检索服务父进程47173、4个worker及8003监听存在；OpenAPI HTTP200，挖掘6000健康接口HTTP200。main HEAD为3aa4aadc854fd8e8fc6f31555754799882fbabd8，ES8引擎/Router/HTTP服务源码哈希见[证据JSON](es_retrieval_health_20261030.json)。4处原业务dirty保留。

## PaaS：连接失败，不是有效查询得到0条

当前配置地址的主机名为：

`es-cn-mis4zbj2e0002q83l.public.elasticsearch.aliyuncs.com`

- main系统DNS解析失败：`[Errno -2] Name or service not known`。
- sg本机也解析失败。
- 在main分别查询阿里公共DNS223.5.5.5、223.6.6.6，均返回NXDOMAIN。
- 同样网络下Serverless域名正常解析并能访问，因此不是整个main无法访问ES，也不只是main单个DNS缓存异常。
- 实际服务日志2026-10-30 01:08:43记录PaaS连接失败、重试以及`web_search raw result is None`，随后访问日志仍为HTTP200。这是现有错误返回方式，HTTP200不能证明查询成功。
- `/get_from_type_count`对payoneer_olive、payoneer均返回HTTP200但`success=false, count=0, message=获取来源知识数量失败`；这里的0是失败返回值，不是库存统计。

尚未访问阿里云控制台或管理API，无法进一步确认是公网入口关闭、实例状态变化还是访问地址变更。恢复前应核对该实例的存在/运行状态、公网开关及当前连接地址，不能把域名问题误判为重排、source过滤或版本兼容错误。本轮未替换地址、修改DNS/hosts、重启服务或尝试写入。

## Serverless：实际数据与服务请求通过

| 索引 | `_count`总文档数 | 显式有效high QA条件计数 | `/web_search` | `/search` |
|---|---:|---:|---|---|
| mercado_local | 17,322 | 13,060 | 2条，115ms | 3条，466ms |
| mercado | 22,983 | 9,139 | 2条，41ms | 3条，292ms |
| wayfair | 67,168 | 18,629 | 2条，46ms | 3条，276ms |

显式QA条件为 `del_flag=0 AND quality_level=high AND audit_result IN [1,2,-1] AND data_type=qa`。总文档数没有排除软删除等记录，两者不要混用。

先用当前Router和真实ES8客户端确认这些索引存在并读取一条有效QA，再对运行中的8003服务调用空文本小页列表和该已有标题的语义检索（top_k=3，use_synonyms=true）。3次语义检索均把对应样本ID排在首位，全部6次返回真实数据且没有错误占位。仅请求小量数据，不是性能压测或完整召回质量验收。

另从sg通过main公网8003调用mercado_local的`/web_search`，HTTP200返回1条，约613ms；服务公网路径也可访问。未复现浏览器→前端后端→检索服务的完整链，用户具体前端索引、查询及过滤条件尚未提供。

分页响应中的total_count=10000沿用当前服务统计口径，不能拿它代替上表native `_count`。本轮未为此修改行为。

## 范围与操作记录

日志先stat，456,931,298字节的运行日志仅读取末尾160KB。读取配置时只输出版本、路径、provider主机名及必要元数据；没有保存凭据、原文内容或向量。

本轮只做Git/进程/配置元数据、DNS、健康、ES计数/小样搜索和现有服务只读接口检查。没有更新代码、配置、路由、别名或数据，没有部署、重启、commit/push；没有执行新的自动审核或迁移。测试覆盖3个Serverless索引和PaaS连接/2个计数请求，不能扩展为所有索引、所有类目条件或全部前端请求均正常。

## 01:40 PaaS再次检查

用户说明此前余额不足并要求重测。01:40:24 main实际DNS及ES连接仍失败；01:40:52分别查询223.5.5.5、223.6.6.6，两者仍返回同域名NXDOMAIN。运行服务对payoneer_olive的`/get_from_type_count`仍为HTTP200、success=false、count=0、获取来源知识数量失败。尚未恢复到可执行真实数据检索的状态；不能把失败返回的0解释成数据丢失，也未核实阿里云账单/实例恢复进度。本次仅复测，没有改配置或重启。

## 01:43 续费后控制台信息与连接核对

用户提供续费后控制台：实例ID仍为es-cn-mis4zbj2e0002q83l、版本8.17.0、状态正常、包年包月到期2026-12-01 00:00:00；公网地址栏为“请开启公网访问地址后使用”，私网地址为es-cn-mis4zbj2e0002q83l.elasticsearch.aliyuncs.com:9200。

01:43:44从main复核：线上配置仍使用原.public公网域名，DNS依旧失败；用户提供的私网域名现在可解析为10.0.0.250，但main至9200的4秒TCP连接探测超时。没有改服务配置、临时修改hosts或切路由。当前已明确公网入口未开启与现有应用使用公网地址不匹配；不能把“实例状态正常”等同于应用可达。私网超时不能单凭该探测确定是VPC不通还是访问策略限制；公网关闭是否由续费流程导致亦未经变更记录核实。
