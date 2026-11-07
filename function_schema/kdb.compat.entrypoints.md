# legacy_entry / legacy_source_path

legacy_entry(name, target, namespace)：旧wrapper调用。普通import绑定同一正式模块；__main__沿用argv/cwd，在同进程执行搬后的原CLI，不捕获退出码。
显式module_from_spec未注册的隔离加载沿用原命名空间执行同一份正式源代码；已注册spec对象保留属性修改转发。
legacy_source_path(relative)：返回本候选项目根下的旧逻辑文件位置；用于原__file__路径计算，不进行跨仓sys.path注入或chdir。
无新增ES/SQL/任务子进程；被导入原模块既有初始化不被提前/延后。
