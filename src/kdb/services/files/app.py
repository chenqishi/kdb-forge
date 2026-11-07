from kdb.compat.layout import legacy_package_path as _legacy_package_path
#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
文件访问服务：提供统一的 MinIO/S3 对象访问接口，供前置的 Nginx 反向代理调用。
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('file_service/file_access_service.py')

import io
import json
import logging
import mimetypes
import os
import random
import uuid
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, Optional

import requests

from botocore.exceptions import ClientError
from flask import Flask, Response, abort, make_response, request, stream_with_context

from data_control_tools.minio_tools import MinioTools


logger = logging.getLogger(__name__)


BASE_DIR = Path(__legacy_source_file__).resolve().parents[1]
DEFAULT_CACHE_CONTROL = "public, max-age=31536000, immutable"
CONFIG_PATH: Optional[Path] = None
DEFAULT_CONFIG_CANDIDATES = [
    lambda: CONFIG_PATH,
    lambda: os.environ.get("MINIO_CONFIG_PATH"),
    lambda: BASE_DIR / "config" / "minio_config.json",
    lambda: BASE_DIR / "config" / "minio_config_default.json",
    lambda: BASE_DIR / "config" / "minio_config_default_aws_test.json",
]
CHUNK_SIZE = 1024 * 1024  # 1MB

# /upload_from_url 从外部源站下载文件的超时（秒）。
# 原来硬编码 30 秒且端点不透传，大文件或慢源站会直接超时失败。
# 读取超时按这个值；连接超时单独设小值，源站连不上时尽快失败而不是干等。
DEFAULT_DOWNLOAD_TIMEOUT = int(os.environ.get("FILE_SERVICE_DOWNLOAD_TIMEOUT", "180"))
CONNECT_TIMEOUT = int(os.environ.get("FILE_SERVICE_CONNECT_TIMEOUT", "10"))

app = Flask("Stone Fish File Access Service")


def _load_json_config(path: Path) -> Dict[str, str]:
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def _http_datetime_format(dt) -> Optional[str]:
    if not dt:
        return None
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")


def _iter_config_candidates():
    for candidate_fn in DEFAULT_CONFIG_CANDIDATES:
        try:
            candidate = candidate_fn()
        except Exception:
            continue

        if not candidate:
            continue

        path = Path(candidate).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if path.exists() and path.is_file():
            yield path


@lru_cache
def get_minio_tools() -> MinioTools:
    """
    通过 MinioTools 初始化 boto3 客户端，复用现有封装。
    """
    config_path = next(_iter_config_candidates(), None)
    if not config_path:
        raise RuntimeError("未找到可用的 MinIO 配置文件")

    config_map = _load_json_config(config_path)
    logger.info("加载 MinIO 配置文件: %s", config_path)
    return MinioTools(config=config_map)


@lru_cache
def get_s3_client():
    tools = get_minio_tools()
    if not tools.s3_client:
        raise RuntimeError("MinioTools 未成功初始化 S3 客户端")
    return tools.s3_client


def _guess_media_type(object_path: str, fallback: str = "application/octet-stream") -> str:
    mime_type, _ = mimetypes.guess_type(object_path)
    return mime_type or fallback


# S3 返回的时间字段转换为 HTTP 兼容格式


def _format_last_modified(value) -> Optional[str]:
    try:
        return _http_datetime_format(value)
    except AttributeError:
        return None


def _extract_common_headers(metadata: Dict[str, object]) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    cache_control = metadata.get("CacheControl") or DEFAULT_CACHE_CONTROL
    headers["Cache-Control"] = cache_control

    etag = metadata.get("ETag")
    if etag:
        headers["ETag"] = etag

    last_modified = _format_last_modified(metadata.get("LastModified"))
    if last_modified:
        headers["Last-Modified"] = last_modified

    content_length = metadata.get("ContentLength")
    if content_length is not None:
        headers["Content-Length"] = str(content_length)

    expires = metadata.get("Expires")
    if expires:
        expires_str = _format_last_modified(expires)
        if expires_str:
            headers["Expires"] = expires_str

    accept_ranges = metadata.get("AcceptRanges") or metadata.get("Accept-Ranges")
    if accept_ranges:
        headers["Accept-Ranges"] = accept_ranges
    else:
        headers["Accept-Ranges"] = "bytes"

    return headers


def _streaming_body_iter(body, chunk_size: int) -> Iterable[bytes]:
    try:
        for chunk in body.iter_chunks(chunk_size=chunk_size):
            if chunk:
                yield chunk
    finally:
        body.close()


def upload_from_url(
    file_url: str,
    bucket: Optional[str] = None,
    object_key: Optional[str] = None,
    timeout: Optional[int] = None,
    allowed_content_type_prefix: Optional[str] = None,
) -> Optional[str]:
    """
    从 URL 下载文件并上传到 MinIO。支持任意类型的文件（图片、文档、音视频、压缩包等）。

    Args:
        file_url: 文件的 URL 地址
        bucket: 可选的 bucket 名称，如果不指定则使用默认 bucket
        object_key: 可选的对象键前缀，如果不指定则使用 default 前缀；最终路径形如 {prefix}/YYYYMMDD/{uuid}.{ext}
        timeout: 下载超时时间（秒）。不传则用 DEFAULT_DOWNLOAD_TIMEOUT
                 （可用环境变量 FILE_SERVICE_DOWNLOAD_TIMEOUT 覆盖）
        allowed_content_type_prefix: 可选的 Content-Type 前缀过滤（如 "image/"），不传则不限制类型

    Returns:
        上传成功返回 "{bucket}/{object_key}"，失败返回 None
    """
    try:
        # 下载文件
        logger.info(f"开始从 URL 下载文件: {file_url}")
        # 添加浏览器请求头，避免被CDN识别为爬虫（如阿里云CDN的420错误）
        # 使用随机版本号动态生成 User-Agent，无需定期维护
        chrome_version = random.randint(110, 135)  # Chrome 主版本号
        firefox_version = random.randint(115, 135)  # Firefox 主版本号
        safari_version = random.randint(16, 18)  # Safari 主版本号

        user_agents = [
            f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version}.0.0.0 Safari/537.36',
            f'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version}.0.0.0 Safari/537.36',
            f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(110, 135)}.0.0.0 Safari/537.36',
            f'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/{safari_version}.{random.randint(0, 2)} Safari/605.1.15',
            f'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{firefox_version}.0) Gecko/20100101 Firefox/{firefox_version}.0',
            f'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(110, 135)}.0.0.0 Safari/537.36',
            f'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version}.0.0.0 Safari/537.36',
            f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/{random.randint(110, 135)}.0.0.0 Safari/537.36',
        ]
        headers = {
            'User-Agent': random.choice(user_agents),
            'Accept': '*/*',
        }
        # 30 秒对大文件/慢源站不够用（实测有源站首字节就要十几秒），改为可配置。
        # 用 (连接超时, 读取超时) 二元组：连接卡住尽快失败，读取慢则按 download_timeout 等。
        download_timeout = DEFAULT_DOWNLOAD_TIMEOUT if timeout is None else timeout
        response = requests.get(file_url, headers=headers,
                                timeout=(CONNECT_TIMEOUT, download_timeout), stream=True)
        response.raise_for_status()

        # 可选的 Content-Type 前缀校验（例如只允许图片场景下传 "image/"）
        content_type = response.headers.get('Content-Type', '') or 'application/octet-stream'
        # Content-Type 可能带 charset 等参数，截掉
        content_type_main = content_type.split(';', 1)[0].strip().lower()
        if allowed_content_type_prefix and not content_type_main.startswith(allowed_content_type_prefix):
            logger.error(
                f"URL 返回的 Content-Type {content_type_main} 不满足前缀 {allowed_content_type_prefix}"
            )
            return None

        # 读取文件内容到内存
        file_data = response.content
        if not file_data:
            logger.error("下载的文件内容为空")
            return None

        # 推断文件扩展名：优先用 URL 路径中的后缀，再退化为 mimetypes 根据 Content-Type 猜测
        ext = None
        # 从 URL 路径中提取后缀（去掉 query / fragment）
        url_path = file_url.split('?', 1)[0].split('#', 1)[0]
        if '.' in url_path.rsplit('/', 1)[-1]:
            url_ext = url_path.rsplit('.', 1)[-1].lower()
            # 限制后缀长度，避免把奇怪的路径片段当成扩展名
            if 1 <= len(url_ext) <= 8 and url_ext.isalnum():
                ext = url_ext

        if not ext:
            guessed = mimetypes.guess_extension(content_type_main)
            if guessed:
                ext = guessed.lstrip('.')

        if not ext:
            ext = 'bin'

        # 生成路径
        # 如果传了 object_key，则路径为: object_key/YYYYMMDD/uuid.ext
        # 如果没传 object_key，则路径为: default/YYYYMMDD/uuid.ext
        now = datetime.now()
        date_str = now.strftime('%Y%m%d')
        unique_id = uuid.uuid4().hex

        if object_key:
            # 使用自定义前缀
            prefix = object_key.rstrip('/')
            object_key = f"{prefix}/{date_str}/{unique_id}.{ext}"
        else:
            # 使用默认前缀
            object_key = f"default/{date_str}/{unique_id}.{ext}"

        # 获取 MinioTools 实例
        minio_tools = get_minio_tools()

        # 如果没有指定 bucket，使用默认 bucket
        if not bucket:
            bucket = minio_tools.config.get('bucket_name', 'test')

        # 将文件数据写入临时文件
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{ext}') as tmp_file:
            tmp_file.write(file_data)
            tmp_file_path = tmp_file.name

        try:
            # 上传到 MinIO
            logger.info(f"开始上传文件到 MinIO: {bucket}/{object_key}")
            upload_success = minio_tools.upload_file(
                tmp_file_path,
                object_key,
                bucket_name=bucket,
                content_type=content_type_main,
            )

            if not upload_success:
                logger.error(f"上传到 MinIO 失败: {bucket}/{object_key}")
                return None

            logger.info(f"文件上传成功: {bucket}/{object_key}")
            return f"{bucket}/{object_key}"

        finally:
            # 删除临时文件
            try:
                os.unlink(tmp_file_path)
            except Exception as e:
                logger.warning(f"删除临时文件失败: {tmp_file_path}, 错误: {e}")

    except requests.exceptions.RequestException as e:
        logger.error(f"下载文件失败: {file_url}, 错误: {e}")
        return None
    except Exception as e:
        logger.exception(f"上传文件过程出错: {file_url}, 错误: {e}")
        return None


@app.route("/<bucket>/<path:object_path>", methods=["GET"])
def proxy_object(bucket: str, object_path: str):
    """
    获取 MinIO/S3 对象内容，并以流式响应返回。
    """
    client = get_s3_client()
    try:
        stat = client.head_object(Bucket=bucket, Key=object_path)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"404", "NoSuchKey", "NoSuchBucket"}:
            abort(404, description="对象不存在")
        logger.exception("获取对象元信息失败：bucket=%s, key=%s, error=%s", bucket, object_path, error_code)
        abort(502, description="远端存储访问失败")

    range_header = request.headers.get("Range")
    get_kwargs: Dict[str, str] = {"Bucket": bucket, "Key": object_path}
    if range_header:
        get_kwargs["Range"] = range_header

    try:
        obj = client.get_object(**get_kwargs)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"404", "NoSuchKey", "NoSuchBucket"}:
            abort(404, description="对象不存在")
        logger.exception("拉取对象失败：bucket=%s, key=%s, error=%s", bucket, object_path, error_code)
        abort(502, description="远端存储访问失败")

    body = obj["Body"]
    media_type = obj.get("ContentType") or stat.get("ContentType") or _guess_media_type(object_path)
    metadata_headers = _extract_common_headers(obj)

    if "Content-Length" not in metadata_headers:
        content_length = obj.get("ContentLength") or stat.get("ContentLength")
        if content_length is not None:
            metadata_headers["Content-Length"] = str(content_length)

    content_range = obj.get("ContentRange") or obj.get("Content-Range")
    status_code = 200
    if content_range:
        metadata_headers["Content-Range"] = content_range
        status_code = 206

    metadata_headers.setdefault("Content-Type", media_type)

    def stream_body() -> Iterable[bytes]:
        yield from _streaming_body_iter(body, CHUNK_SIZE)

    response = Response(
        stream_with_context(stream_body()),
        status=status_code,
        headers=metadata_headers,
    )
    response.direct_passthrough = False
    return response


@app.route("/<bucket>/<path:object_path>", methods=["HEAD"])
def head_object(bucket: str, object_path: str):
    """
    返回对象的头部信息，便于 Nginx 或 CDN 做缓存控制。
    """
    client = get_s3_client()
    try:
        stat = client.head_object(Bucket=bucket, Key=object_path)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code in {"404", "NoSuchKey", "NoSuchBucket"}:
            abort(404, description="对象不存在")
        logger.exception("HEAD 请求失败：bucket=%s, key=%s, error=%s", bucket, object_path, error_code)
        abort(502, description="远端存储访问失败")

    headers = _extract_common_headers(stat)
    headers["Content-Type"] = stat.get("ContentType") or _guess_media_type(object_path)

    response = make_response("", 200)
    response.headers.extend(headers)
    return response


@app.route("/upload_from_url", methods=["POST"])
def upload_file_from_url():
    """
    从 URL 上传文件到 MinIO，支持任意类型的文件（图片、文档、音视频、压缩包等）。

    请求 JSON 格式:
        {
            "url": "https://example.com/foo.pdf",
            "bucket": "可选的 bucket 名称",
            "object_key": "可选的对象路径前缀，如 custom/path",
            "content_type_prefix": "可选，限制下载内容的 Content-Type 前缀，如 'image/'"
        }

    响应 JSON 格式:
        成功:
        {
            "success": true,
            "file_path": "bucket/prefix/YYYYMMDD/{uuid}.ext",
            "message": "上传成功"
        }

        失败:
        {
            "success": false,
            "message": "错误信息"
        }
    """
    try:
        # 获取请求数据
        data = request.get_json()
        if not data:
            return {
                "success": False,
                "message": "请求体必须是 JSON 格式"
            }, 400

        # 检查必需参数
        file_url = data.get('url')
        if not file_url:
            return {
                "success": False,
                "message": "缺少必需参数: url"
            }, 400

        # 获取可选参数
        bucket = data.get('bucket')
        object_key = data.get('object_key')
        content_type_prefix = data.get('content_type_prefix')
        # 允许调用方按需放大超时（比如已知源站很慢的大文件）；不传则用服务默认值
        timeout = data.get('timeout')
        if timeout is not None:
            try:
                timeout = int(timeout)
                if timeout <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                return {"success": False, "message": "timeout 必须是正整数（秒）"}, 400

        # 调用辅助函数下载并上传文件
        file_path = upload_from_url(
            file_url,
            bucket,
            object_key,
            timeout=timeout,
            allowed_content_type_prefix=content_type_prefix,
        )

        if file_path:
            return {
                "success": True,
                "file_path": file_path,
                "message": "上传成功"
            }, 200
        else:
            return {
                "success": False,
                "message": "上传失败，请检查 URL 是否有效或查看服务器日志"
            }, 500

    except Exception as e:
        logger.exception(f"处理上传请求时出错: {e}")
        return {
            "success": False,
            "message": f"服务器内部错误: {str(e)}"
        }, 500


@app.route("/upload", methods=["POST"])
def upload_file():
    """
    接收客户端上传的文件并保存到 MinIO/S3。
    
    请求格式：multipart/form-data
    参数：
    - file: 要上传的文件（必填）
    - remote_file_path: 远程路径，格式为 <bucket>/<path:object_path>（必填）
    
    响应 JSON 格式:
        成功:
        {
            "success": true,
            "message": "文件上传成功",
            "remote_path": "bucket/object_path",
            "bucket": "bucket",
            "object_path": "object_path"
        }
        
        失败:
        {
            "success": false,
            "message": "错误信息"
        }
    """
    try:
        # 检查是否包含文件
        if 'file' not in request.files:
            return {
                "success": False,
                "message": "缺少文件参数: file"
            }, 400
        
        file = request.files['file']
        
        # 检查文件是否为空
        if file.filename == '':
            return {
                "success": False,
                "message": "文件名为空"
            }, 400
        
        # 获取 remote_file_path 参数
        remote_file_path = request.form.get('remote_file_path')
        if not remote_file_path:
            return {
                "success": False,
                "message": "缺少参数: remote_file_path（格式: <bucket>/<path:object_path>）"
            }, 400
        
        # 解析 remote_file_path 为 bucket 和 object_path
        # 格式：bucket/path/to/file
        parts = remote_file_path.split("/", 1)
        if len(parts) < 2:
            return {
                "success": False,
                "message": "remote_file_path 格式错误，应为 <bucket>/<path:object_path>"
            }, 400
        
        bucket = parts[0]
        object_path = parts[1]
        
        # 获取文件内容类型
        content_type = file.content_type or _guess_media_type(file.filename)
        
        # 将文件保存到临时文件
        import tempfile
        file_ext = Path(file.filename).suffix or ''
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
            # 读取上传的文件内容并写入临时文件
            file_data = file.read()
            tmp_file.write(file_data)
            tmp_file_path = tmp_file.name
        
        try:
            # 获取 MinioTools 实例并上传文件
            tools = get_minio_tools()
            
            # 上传文件
            upload_success = tools.upload_file(
                local_file_path=tmp_file_path,
                object_key=object_path,
                bucket_name=bucket,
                content_type=content_type
            )
            
            if upload_success:
                logger.info("文件上传成功: %s -> %s/%s", file.filename, bucket, object_path)
                return {
                    "success": True,
                    "message": "文件上传成功",
                    "remote_path": remote_file_path,
                    "bucket": bucket,
                    "object_path": object_path,
                    "filename": file.filename
                }, 200
            else:
                logger.error("文件上传失败: %s -> %s/%s", file.filename, bucket, object_path)
                return {
                    "success": False,
                    "message": "文件上传失败，请查看服务器日志"
                }, 500
                
        finally:
            # 删除临时文件
            try:
                os.unlink(tmp_file_path)
            except Exception as e:
                logger.warning(f"删除临时文件失败: {tmp_file_path}, 错误: {e}")
                
    except Exception as e:
        logger.exception(f"处理文件上传请求时出错: {e}")
        return {
            "success": False,
            "message": f"服务器内部错误: {str(e)}"
        }, 500


@app.route("/health", methods=["GET"])
def health_check() -> Dict[str, str]:
    return {"status": "ok"}


# Flask 应用在被 gunicorn 等 WSGI 容器加载时会自动加载 app 实例。


def set_config_path(config_path: str) -> Path:
    """
    设置自定义配置文件路径，并清理客户端缓存。
    """
    global CONFIG_PATH
    resolved = Path(config_path).expanduser()
    if not resolved.is_absolute():
        resolved = (Path.cwd() / resolved).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"配置文件不存在: {resolved}")
    if not resolved.is_file():
        raise IsADirectoryError(f"配置路径不是文件: {resolved}")

    CONFIG_PATH = resolved
    get_minio_tools.cache_clear()
    get_s3_client.cache_clear()
    logger.info("使用自定义配置文件: %s", CONFIG_PATH)
    return CONFIG_PATH


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



