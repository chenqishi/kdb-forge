from kdb.shared.config.paths import subprocess_env
import logging
import os
import subprocess
import traceback

def _run_command(self, cmd, stage_name):
    """运行命令并记录日志。cmd 可以是字符串（shell=True）或参数列表（shell=False）。"""
    log_file = os.path.join(self.log_dir, f'{stage_name}.log')
    logging.info(f"执行阶段: {stage_name}")
    logging.info(f"工作目录: {self.script_dir}")
    logging.info("=" * 80)
    logging.info(f"执行命令: {cmd}")
    logging.info("=" * 80)

    use_shell = isinstance(cmd, str)

    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            result = subprocess.run(
                cmd,
                shell=use_shell,
                stdout=f,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.script_dir,
                env=subprocess_env(),
            )

        # 读取命令输出日志，打印一些关键信息
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.read(500)
                if log_content.strip():
                    logging.info(f"阶段 {stage_name} 命令输出（前500字符）:")
                    logging.info(log_content[:500])
                else:
                    logging.warning(f"阶段 {stage_name} 命令没有输出")

        if result.returncode == 0:
            logging.info(f"阶段 {stage_name} 执行成功，返回码: {result.returncode}")
            return True
        else:
            logging.error(f"阶段 {stage_name} 执行失败，返回码: {result.returncode}")
            # 如果有错误日志，显示更多信息
            if os.path.exists(log_file):
                with open(log_file, 'rb') as f:
                    f.seek(max(os.path.getsize(log_file) - 4000, 0))
                    error_content = f.read(4000).decode('utf-8', errors='replace')
                    if error_content.strip():
                        logging.error(f"错误详情: {error_content[-1000:]}")  # 显示最后1000字符
            return False

    except Exception as e:
        logging.error(f"执行阶段 {stage_name} 时发生异常: {e}")
        traceback.print_exc()
        return False
