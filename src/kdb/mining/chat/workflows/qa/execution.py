from kdb.shared.config.paths import SOURCE_ROOT
from kdb.shared.config.paths import subprocess_env
import logging
import os
import shlex
import signal
import subprocess
import traceback

def _run_command(self, cmd, stage_name):
    """运行命令并记录日志"""
    log_file = os.path.join(self.log_dir, f'{stage_name}.log')
    llm_env_file = os.path.join(self.config_dir, 'chatknowledge_llm_env.sh')
    if os.path.exists(llm_env_file):
        cmd = f"set -a; . {shlex.quote(llm_env_file)}; set +a; {cmd}"
    cmd = f"export PYTHONPATH={shlex.quote(str(SOURCE_ROOT))}:$PYTHONPATH; {cmd}"
    logging.info(f"执行阶段: {stage_name}")
    logging.info(f"工作目录: {self.script_dir}")
    logging.info("=" * 80)
    logging.info(f"执行命令: {cmd}")
    logging.info("=" * 80)

    try:
        remaining_timeout = self._remaining_task_timeout_seconds()
        if remaining_timeout is not None and remaining_timeout <= 0:
            logging.error(
                "任务已超过总时限 %s 秒，拒绝启动阶段 %s",
                self.task_timeout_seconds,
                stage_name
            )
            return False
        with open(log_file, 'w', encoding='utf-8') as f:
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=f,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.script_dir,
                env=subprocess_env(),
                start_new_session=True,
            )
            try:
                process.wait(timeout=remaining_timeout)
            except subprocess.TimeoutExpired:
                logging.error("终止超时阶段 %s 的进程组 pid=%s", stage_name, process.pid)
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise

        # 读取命令输出日志，打印一些关键信息
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.read(500)
                if log_content.strip():
                    logging.info(f"阶段 {stage_name} 命令输出（前500字符）:")
                    logging.info(log_content[:500])
                else:
                    logging.warning(f"阶段 {stage_name} 命令没有输出")

        if process.returncode == 0:
            logging.info(f"阶段 {stage_name} 执行成功，返回码: {process.returncode}")
            return True
        else:
            logging.error(f"阶段 {stage_name} 执行失败，返回码: {process.returncode}")
            # 如果有错误日志，显示更多信息
            if os.path.exists(log_file):
                with open(log_file, 'rb') as f:
                    f.seek(max(os.path.getsize(log_file) - 4000, 0))
                    error_content = f.read(4000).decode('utf-8', errors='replace')
                    if error_content.strip():
                        logging.error(f"错误详情: {error_content[-1000:]}")  # 显示最后1000字符
            return False

    except subprocess.TimeoutExpired:
        logging.error(
            "阶段 %s 超时；任务总时限为 %s 秒",
            stage_name,
            getattr(self, 'task_timeout_seconds', '未配置')
        )
        return False
    except Exception as e:
        logging.error(f"执行阶段 {stage_name} 时发生异常: {e}")
        traceback.print_exc()
        return False
