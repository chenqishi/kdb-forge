from flask import Flask
from kdb.entrypoints.http.files.routes import register_routes
from kdb.shared.storage.service_runtime import set_config_path

app = Flask("Stone Fish File Access Service")


"""
文件访问服务：提供统一的 MinIO/S3 对象访问接口，供前置的 Nginx 反向代理调用。
"""


register_routes(app)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MinIO 图床访问服务（Flask）")
    parser.add_argument("--config", type=str, help="MinIO 配置文件路径（JSON）")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="服务监听地址")
    parser.add_argument("--port", type=int, default=8000, help="服务监听端口")
    parser.add_argument("--reload", action="store_true", help="启用代码热重载（Flask Debug）")

    args = parser.parse_args()

    if args.config:
        set_config_path(args.config)

    app.run(host=args.host, port=args.port, debug=args.reload, threaded=True)
