# main
Inputs: --commit批准的40位目标SHA；默认仅检查，--execute才上线。
Outputs: 发布阶段与脱敏JSON记录，失败非零退出。
复用旧服务validate_services身份守卫；只从已知3aa4aad通过目标工作目录git pull
快进到包含旧历史的批准提交，保存配置/4脏文件哈希并拒绝路径碰撞。
仅精确检索父PID SIGTERM，等待子进程退出，原环境/命令/日志启动；保留挖掘。
检查OpenAPI、probe、配置/脏改动与日志，更新activation身份和backup记录。
不覆盖生产代码、不写ES、不变配置；不自动重复部署。详见 list_file_names_online_20261103.md。
