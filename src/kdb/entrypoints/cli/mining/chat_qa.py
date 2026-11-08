from kdb.mining.chat.pipeline import ChatQAMiningTaskController
import argparse
import json
import logging
import sys
import traceback

def main():
    """主函数"""
    # 先配置基础日志，确保早期日志能够输出
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True
    )

    parser = argparse.ArgumentParser(description='聊天QA挖掘任务控制脚本')
    parser.add_argument('--script-dir', required=True, help='脚本根目录路径')
    parser.add_argument('--task-id', required=True, help='任务ID')
    parser.add_argument('--task-info', required=True, help='任务信息JSON字符串')

    args = parser.parse_args()

    logging.info("=== 聊天QA挖掘任务脚本启动 ===")
    logging.info(f"脚本目录: {args.script_dir}")
    logging.info(f"任务ID: {args.task_id}")
    logging.info(f"任务信息: {args.task_info}")

    try:
        # 解析任务信息
        task_info = json.loads(args.task_info)
        logging.info("任务信息解析成功")

        # 创建任务控制器
        logging.info("正在创建任务控制器...")
        controller = ChatQAMiningTaskController(
            args.script_dir,
            args.task_id,
            task_info
        )
        logging.info("任务控制器创建成功")

        # 运行所有阶段
        logging.info("开始运行所有阶段...")
        success = controller.run_all_stages()

        if success:
            logging.info("=== 任务执行成功完成 ===")
        else:
            logging.error("=== 任务执行失败 ===")

        sys.exit(0 if success else 1)

    except json.JSONDecodeError as e:
        logging.error(f"任务信息JSON解析失败: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"脚本执行发生异常: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
