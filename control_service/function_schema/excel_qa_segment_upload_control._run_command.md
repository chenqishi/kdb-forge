# excel_qa_segment_upload_control._run_command

## 描述
执行任务阶段命令并将 stdout/stderr 写入阶段日志文件，同时把阶段执行结果记录到主日志。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| cmd | str \| List[str] \| Tuple[str, ...] | 是 | 待执行命令。字符串命令按历史行为使用 shell 执行；列表/元组命令不经过 shell，避免路径空格等字符被拆分 |
| stage_name | str | 是 | 阶段名称，用于生成 `{stage_name}.log` |

## Outputs

| 类型 | 说明 |
|------|------|
| bool | 命令返回码为 0 时返回 True，否则返回 False |

## 逻辑

1. 根据 `stage_name` 在任务日志目录生成阶段日志路径。
2. 如果 `cmd` 是列表/元组，使用 `shlex.join` 格式化为可读日志；如果是字符串，直接记录。
3. 调用 `subprocess.run` 执行命令：
   - `cmd` 为字符串时使用 `shell=True`，兼容旧有调用。
   - `cmd` 为列表/元组时使用 `shell=False`，保证带空格路径作为单个参数传给子进程。
4. 读取阶段日志前 500 字符写入主日志。
5. 根据返回码返回成功/失败，失败时补充阶段日志末尾错误信息。

## SQL

无。
