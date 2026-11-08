

def parse_args():
    """解析命令行参数"""
    import argparse
    parser = argparse.ArgumentParser(description='多语言识别服务')
    parser.add_argument('--port',
                       type=int,
                       help='服务端口号',
                       default=8007)
    parser.add_argument('--host',
                       help='服务监听地址',
                       default='0.0.0.0')
    parser.add_argument('--model_path',
                       help='fastText 模型文件路径',
                       default=None)

    return parser.parse_args()
