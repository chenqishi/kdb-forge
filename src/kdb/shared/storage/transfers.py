from datetime import datetime
from kdb.shared.storage.service_runtime import get_minio_tools
from typing import Optional
import kdb.shared.storage.runtime_state as runtime_state
import logging
import mimetypes
import os
import random
import requests
import uuid
logger = logging.getLogger('kdb.entrypoints.http.files.app')

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
        download_timeout = runtime_state.DEFAULT_DOWNLOAD_TIMEOUT if timeout is None else timeout
        response = requests.get(file_url, headers=headers,
                                timeout=(runtime_state.CONNECT_TIMEOUT, download_timeout), stream=True)
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
