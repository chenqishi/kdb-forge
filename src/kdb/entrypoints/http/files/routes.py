from botocore.exceptions import ClientError
from flask import Response
from flask import abort
from flask import make_response
from flask import request
from flask import stream_with_context
from kdb.entrypoints.http.files.responses import _extract_common_headers
from kdb.entrypoints.http.files.responses import _guess_media_type
from kdb.entrypoints.http.files.responses import _streaming_body_iter
from kdb.shared.storage.service_runtime import get_minio_tools
from kdb.shared.storage.service_runtime import get_s3_client
from kdb.shared.storage.transfers import upload_from_url
from pathlib import Path
from typing import Dict
from typing import Iterable
import kdb.shared.storage.runtime_state as runtime_state
import logging
import os
logger = logging.getLogger('kdb.entrypoints.http.files.app')

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
        yield from _streaming_body_iter(body, runtime_state.CHUNK_SIZE)

    response = Response(
        stream_with_context(stream_body()),
        status=status_code,
        headers=metadata_headers,
    )
    response.direct_passthrough = False
    return response


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


def health_check() -> Dict[str, str]:
    return {"status": "ok"}


def register_routes(app):
    """Register the original handlers on the single entrypoint app."""
    app.route('/<bucket>/<path:object_path>', methods=['GET'])(proxy_object)
    app.route('/<bucket>/<path:object_path>', methods=['HEAD'])(head_object)
    app.route('/upload_from_url', methods=['POST'])(upload_file_from_url)
    app.route('/upload', methods=['POST'])(upload_file)
    app.route('/health', methods=['GET'])(health_check)
