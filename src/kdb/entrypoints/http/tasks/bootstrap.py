

def parse_args():
    """解析命令行参数"""
    import argparse
    parser = argparse.ArgumentParser(description='任务控制服务')
    parser.add_argument('--script-dir',
                       help='运行配置、数据和日志根目录（不指定则使用当前项目根目录）',
                       default=None)
    parser.add_argument('--port',
                       type=int,
                       help='服务端口号',
                       default=6000)
    parser.add_argument('--host',
                       help='服务监听地址',
                       default='0.0.0.0')
    parser.add_argument('--resource-config',
                       help='任务资源配置文件路径',
                       default=None)
    parser.add_argument('--max-concurrency',
                       type=int,
                       help='最大并发数',
                       default=10)
    return parser.parse_args()
