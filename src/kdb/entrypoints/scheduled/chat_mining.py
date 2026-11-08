from kdb.mining.tasks.submission.chat_batch import BatchChatQARequestRunner
import logging
import sys

def main():
    """主函数"""
    if len(sys.argv) != 6:
        print("用法: python -m kdb.entrypoints.scheduled.chat_mining <appid_record_file> <mysql_config_file> <start_time> <end_time> <flag>")
        print("示例: python -m kdb.entrypoints.scheduled.chat_mining data/chatknowledge/appid_record.txt config/mysql_conn_config.json 20250101000000 20250101235959 timing_v1_20250101")
        sys.exit(1)

    appid_record_file = sys.argv[1]
    mysql_config_file = sys.argv[2]
    start_time = sys.argv[3]
    end_time = sys.argv[4]
    flag = sys.argv[5]

    try:
        runner = BatchChatQARequestRunner(
            appid_record_file=appid_record_file,
            mysql_config_file=mysql_config_file,
            start_time=start_time,
            end_time=end_time,
            flag=flag
        )

        runner.run()

    except Exception as e:
        logging.error(f"运行批量任务时发生异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
