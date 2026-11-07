import json
import logging
import mimetypes
import os
import re
import sys
import uuid
import traceback
import hashlib
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
from urllib.parse import urlparse
from urllib.request import urlretrieve
from kdb.shared.text.common_utils import count_alaph_char, count_chinese_char
from kdb.shared.text.text_utils import cluster_by_edit_distance
try:
    from PIL import Image  # type: ignore
except ImportError:  # pragma: no cover
    Image = None

from kdb.shared.clients.dify_tools import DIfyWorkFlowMlutiVisionRequest
from kdb.integrations.data_control.minio_tools import MinioTools
from kdb.shared.text.text_utils import construct_multimodel_undestanding_content

logger = logging.getLogger(__name__)

A4_REFERENCE_DPI = 300
A4_WIDTH_INCH = 8.27
A4_HEIGHT_INCH = 11.69
A4_WIDTH_PX = int(A4_WIDTH_INCH * A4_REFERENCE_DPI)
A4_HEIGHT_PX = int(A4_HEIGHT_INCH * A4_REFERENCE_DPI)
A4_MIN_AREA_PX = (A4_WIDTH_PX * A4_HEIGHT_PX) // 3
FILE_SIZE_THRESHOLD_BYTES = 30 * 1024


def _config_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _config_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class MultimodalProcess(object):
    """多模态文档处理入口"""

    def __init__(self, config_path: Union[str, Dict[str, Any]]):
        self.config = self._load_config(config_path)

        self.enable_upload: bool = _config_bool(self.config.get("enable_upload"), True)
        self.enable_image_understanding: bool = _config_bool(
            self.config.get("enable_image_understanding"), False
        )
        self.enable_image_ocr: bool = _config_bool(
            self.config.get("enable_image_ocr"), False
        )
        self.enable_image_hash_blacklist: bool = _config_bool(
            self.config.get("enable_image_hash_blacklist"), True
        )
        self.image_hash_blacklist_threshold: int = max(
            0, _config_int(self.config.get("image_hash_blacklist_threshold"), 10)
        )
        self.image_hash_counts: Dict[str, int] = {}
        self.image_hash_by_path: Dict[str, str] = {}
        self.image_hash_blacklist = set()

        self.prefix_fileservice_url: str = (
            (self.config.get("prefix_fileservice_url") or "").rstrip("/")
        )

        # MinIO 初始化
        self.minio_config: Dict[str, Any] = {}
        self.minio_client: Optional[MinioTools] = None
        self.bucket_name: str = self.config.get("bucket_name", "")
        self.upload_prefix: str = (self.config.get("upload_prefix") or "").strip("/")

        if self.enable_upload:
            minio_config_ref = self.config.get("minio_config_path") or self.config.get(
                "minio_config"
            )
            self.minio_config = self._load_json_resource(minio_config_ref)
            if self.minio_config:
                self.minio_client = MinioTools(self.minio_config)
                if not self.bucket_name:
                    self.bucket_name = (
                        self.minio_config.get("bucket_name")
                        or self.minio_config.get("bucket")
                        or "boot-admin"
                    )
        if not self.bucket_name:
            self.bucket_name = "boot-admin"


        # 图像理解初始化
        self.image_understanding_config: Dict[str, Any] = {}
        self.dify_client: Optional[DIfyWorkFlowMlutiVisionRequest] = None
        self.image_understanding_paragraph: str = ""
        self.image_ocr_config: Dict[str, Any] = {}
        self.dify_ocr_client: Optional[DIfyWorkFlowMlutiVisionRequest] = None
        self.image_ocr_paragraph: str = ""

        if self.enable_image_understanding:
            iu_config_ref = self.config.get("image_understanding_config")
            self.image_understanding_config = self._load_json_resource(iu_config_ref)
            if not isinstance(self.image_understanding_config, dict):
                self.image_understanding_config = {}

            init_kwargs = {
                key: self.image_understanding_config.get(key)
                for key in ("api_base", "api_key", "user", "max_retries")
                if self.image_understanding_config.get(key) is not None
            }
            if init_kwargs.get("api_base") and init_kwargs.get("api_key"):
                self.dify_client = DIfyWorkFlowMlutiVisionRequest(**init_kwargs)
            else:
                logger.warning(
                    "图像理解配置缺少 api_base 或 api_key，已跳过初始化 Dify 客户端"
                )

            self.image_understanding_paragraph = self.image_understanding_config.get(
                "paragraph", ""
            )

        if self.enable_image_ocr:
            ocr_config_ref = self.config.get("image_ocr_config")
            self.image_ocr_config = self._load_json_resource(ocr_config_ref)
            if not isinstance(self.image_ocr_config, dict):
                self.image_ocr_config = {}

            ocr_init_kwargs = {
                key: self.image_ocr_config.get(key)
                for key in ("api_base", "api_key", "user", "max_retries")
                if self.image_ocr_config.get(key) is not None
            }
            if ocr_init_kwargs.get("api_base") and ocr_init_kwargs.get("api_key"):
                self.dify_ocr_client = DIfyWorkFlowMlutiVisionRequest(**ocr_init_kwargs)
            else:
                logger.warning(
                    "图像OCR配置缺少 api_base 或 api_key，已跳过初始化 Dify 客户端"
                )

            self.image_ocr_paragraph = self.image_ocr_config.get(
                "paragraph", self.config.get("image_ocr_paragraph", "")
            )

    @staticmethod
    def _load_config(config_path: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        if isinstance(config_path, dict):
            return config_path
        if isinstance(config_path, str):
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        raise TypeError("config_path 需要为 str 或 dict")

    @staticmethod
    def _load_json_resource(resource: Union[str, Dict[str, Any], None]) -> Dict[str, Any]:
        if resource is None:
            return {}
        if isinstance(resource, dict):
            return resource
        if isinstance(resource, str) and resource:
            if not os.path.exists(resource):
                logger.warning("配置文件不存在: %s", resource)
                return {}
            with open(resource, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    @staticmethod
    def _get_image_content_hash(image_path: str) -> Optional[str]:
        if not isinstance(image_path, str) or not image_path:
            return None
        if image_path.startswith(("http://", "https://")):
            return None
        if not os.path.exists(image_path):
            return None

        digest = hashlib.sha256()
        try:
            with open(image_path, "rb") as image_file:
                for chunk in iter(lambda: image_file.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        except OSError as exc:
            logger.warning("计算图片hash失败: %s, error: %s", image_path, exc)
            return None

    def _build_image_hash_blacklist(self, data_payload: Dict[str, Any]) -> Tuple[Dict[str, int], Dict[str, str], set]:
        if not self.enable_image_hash_blacklist or self.image_hash_blacklist_threshold <= 0:
            return {}, {}, set()
        if not isinstance(data_payload, dict):
            return {}, {}, set()

        threshold = self.image_hash_blacklist_threshold
        paths_by_size = defaultdict(list)

        for items in data_payload.values():
            if not isinstance(items, Iterable):
                continue
            for item in items:
                if not isinstance(item, dict) or item.get("type") != "image":
                    continue
                image_path = item.get("image_path")
                if not isinstance(image_path, str):
                    continue
                if image_path.startswith(("http://", "https://")) or not os.path.exists(image_path):
                    continue
                try:
                    paths_by_size[os.path.getsize(image_path)].append(image_path)
                except OSError as exc:
                    logger.warning("获取图片大小失败，跳过hash预扫描: %s, error: %s", image_path, exc)

        hash_counts = Counter()
        hash_by_path = {}
        hash_cache = {}
        for paths in paths_by_size.values():
            if len(paths) <= threshold:
                continue
            for image_path in paths:
                image_hash = hash_cache.get(image_path)
                if image_hash is None:
                    image_hash = self._get_image_content_hash(image_path)
                    if image_hash:
                        hash_cache[image_path] = image_hash
                if not image_hash:
                    continue
                hash_by_path[image_path] = image_hash
                hash_counts[image_hash] += 1

        blacklist = {
            image_hash for image_hash, count in hash_counts.items() if count > threshold
        }
        return dict(hash_counts), hash_by_path, blacklist

    def prepare_image_hash_blacklist(self, data_payload: Dict[str, Any]) -> None:
        hash_counts, hash_by_path, blacklist = self._build_image_hash_blacklist(data_payload)
        self.image_hash_counts = hash_counts
        self.image_hash_by_path = hash_by_path
        self.image_hash_blacklist = blacklist
        if self.enable_image_hash_blacklist:
            logger.info(
                "图片hash黑名单生成完成: threshold=%s, scanned_hashes=%s, blacklisted_hashes=%s, mapped_paths=%s",
                self.image_hash_blacklist_threshold,
                len(self.image_hash_counts),
                len(self.image_hash_blacklist),
                len(self.image_hash_by_path),
            )

    def _build_object_key(self, image_path: str, client_name: str="default") -> str:
        ext = os.path.splitext(image_path)[1] or ".png"
        date_part = datetime.now().strftime("%Y%m%d")
        uuid_part = uuid.uuid4().hex
        if self.upload_prefix:
            return f"{self.upload_prefix}/{client_name}/{date_part}/{uuid_part}{ext}".lstrip("/")
        return f"{client_name}/{date_part}/{uuid_part}{ext}".lstrip("/")

    def _build_public_url(self, object_key: str) -> Optional[str]:
        bucket = (self.bucket_name or "").strip("/")
        object_key = object_key.lstrip("/")

        if self.prefix_fileservice_url and bucket:
            return f"{self.prefix_fileservice_url.rstrip('/')}/{bucket}/{object_key}"
        if self.prefix_fileservice_url:
            return f"{self.prefix_fileservice_url.rstrip('/')}/{object_key}"
        if self.minio_client:
            return self.minio_client.generate_public_url(
                object_key, bucket_name=bucket or None, permanent=True
            )
        return None

    def _upload_image(self, image_path: str, client_name: str="default") -> Tuple[Optional[str], Optional[str]]:
        """
        上传图片到MinIO
        
        Args:
            image_path: 图片路径
            client_name: 客户端名称
            
        Returns:
            Tuple[Optional[str], Optional[str]]: (public_url, s3_path)
        """
        if not self.enable_upload:
            logger.debug("上传功能未开启，跳过上传: %s", image_path)
            return None, None
        if not self.minio_client:
            logger.warning("MinIO 客户端未初始化，无法上传: %s", image_path)
            return None, None
        if not os.path.exists(image_path):
            logger.warning("图片文件不存在，无法上传: %s", image_path)
            return None, None

        object_key = self._build_object_key(image_path, client_name)
        try:
            success = self.minio_client.upload_file(
                image_path, object_key, bucket_name=self.bucket_name
            )
            if not success:
                logger.error("图片上传失败: %s", image_path)
                return None, None
            public_url = self._build_public_url(object_key)
            # s3_path格式: bucket_name/object_key
            s3_path = f"{self.bucket_name}/{object_key}"
            return public_url, s3_path
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("上传图片时出现异常: %s", exc)
            return None, None

    def _is_valid_image(self, image_path: str, size_threshold: int = None, area_threshold: int = None) -> bool:
        if not isinstance(image_path, str) or not image_path:
            logger.warning("图片路径无效，无法校验")
            return False
        if not os.path.exists(image_path):
            logger.warning("图片不存在，无法校验: %s", image_path)
            return False

        try:
            file_size = os.path.getsize(image_path)
        except OSError as exc:  # pragma: no cover
            logger.warning("获取图片大小失败: %s, error: %s", image_path, exc)
            file_size = 0
        if size_threshold is None:
            size_threshold = FILE_SIZE_THRESHOLD_BYTES
        if area_threshold is None:
            area_threshold = A4_MIN_AREA_PX
        size_condition = file_size > size_threshold
        area_condition = False
        area_pixels = 0

        if Image is not None:
            try:
                with Image.open(image_path) as img:
                    width, height = img.size
                    area_pixels = width * height
                    area_condition = area_pixels > area_threshold
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("读取图片尺寸失败: %s, error: %s", image_path, exc)
        else:  # pragma: no cover
            logger.debug("Pillow 未安装，跳过图片尺寸校验，使用文件大小判断")

        if area_condition or size_condition:
            return True

        logger.info(
            "图片校验未通过，像素面积: %s, 面积条件: %s, 文件大小: %s bytes",
            area_pixels,
            "满足" if area_condition else "未满足",
            file_size,
        )
        return False

    def _is_valid_image_by_ocr(self, ocr_result: str, valid_num_threshold: int = 20) -> Tuple[bool, str]:
        """
        通过OCR结果判断图片是否有效（是否包含足够丰富的内容）
        
        判断逻辑：
        1. 如果去重后的单词数量超过阈值且去重率（去重单词数/总单词数）> 0.4，认为图片有效
        2. 如果去重后的中文字符数量超过阈值且去重中文字符率（去重中文字符数/总中文字符数）> 0.4，认为图片有效
        3. 否则认为图片无效
        
        Args:
            ocr_result: OCR识别结果文本
            valid_num_threshold: 有效内容数量阈值，默认10
            
        Returns:
            Tuple[bool, str]: (是否有效, 判断原因)
                - True: 图片有效，reason 包含判断类型和具体数据
                    - "content_rich: diff_words=X > threshold=Y, diff_rate=Z > 0.4, total_words=W"
                    - "chinese_content_rich: diff_chinese_chars=X > threshold=Y, diff_chinese_rate=Z > 0.4, total_chinese_chars=W"
                - False: 图片无效，reason 包含所有判断条件和数据
                    - "content_insufficient: diff_words=X (threshold=Y, diff_rate=Z), diff_chinese_chars=X (threshold=Y, diff_chinese_rate=Z, total_chinese_chars=W)"
        """
        # 将OCR结果转换为小写，按照所有空白字符（空格、制表符、换行符等）分割成单词列表
        ocr_words = re.split(r'\s+', ocr_result.lower())
        
        # 统计OCR结果中的中文字符总数
        chinese_num = count_chinese_char(ocr_result)
        
        # 统计去重后的单词集合中的中文字符数
        diff_chinese_num = count_chinese_char(set(ocr_result))

        cluster_words, cluster_num = cluster_by_edit_distance(ocr_words, max_abs_distance=1, max_ratio=0.3, normalize=True)
        
        # 因为ocr有很多小错误，所以使用聚类后的单词数作为去重后的单词数 
        ocr_diff_num = cluster_num
        
        # 计算去重率：去重单词数 / 总单词数
        total_words = len(ocr_words)
        diff_rate = ocr_diff_num / total_words if total_words > 0 else 0
        
        # 判断条件1：如果去重单词数超过阈值且去重率 > 0.4，认为内容丰富
        if ocr_diff_num > valid_num_threshold and diff_rate > 0.4: 
            reason = f"content_rich: diff_words={ocr_diff_num} > threshold={valid_num_threshold}, diff_rate={diff_rate:.2f} > 0.4, total_words={total_words}"
            return True, reason
        
        # 计算去重后的中文字符率：去重中文字符数 / 总中文字符数
        diff_chinese_rate = diff_chinese_num / chinese_num if chinese_num > 0 else 0
        chinese_wordnum_threshold = valid_num_threshold * 0.7

        # 判断条件2：如果去重中文字符数超过阈值且去重中文字符率 > 0.4，认为中文内容丰富
        if diff_chinese_num > chinese_wordnum_threshold and diff_chinese_rate > 0.4:
            reason = f"chinese_content_rich: diff_chinese_chars={diff_chinese_num} > threshold={chinese_wordnum_threshold}, diff_chinese_rate={diff_chinese_rate:.2f} > 0.4, total_chinese_chars={chinese_num}"
            return True, reason
        
        # 不满足任何条件，认为内容不足，包含所有判断数据
        reason = f"content_insufficient: diff_words={ocr_diff_num} (threshold={valid_num_threshold}, diff_rate={diff_rate:.2f}), diff_chinese_chars={diff_chinese_num} (threshold={chinese_wordnum_threshold}, diff_chinese_rate={diff_chinese_rate:.2f}, total_chinese_chars={chinese_num})"
        return False, reason


    def _clear_url_markdown(self, content: str) -> str:
        """
        清除 content 中 markdown 格式的图片链接，只提取 URL/文件路径部分，其他保留原样
        
        Args:
            content: 原始内容
            
        Returns:
            str: 清除 markdown 格式后的内容，URL/文件路径的 markdown 格式被替换为纯 URL
        """
        if not content or not isinstance(content, str):
            return content
        
        # Markdown 图片格式：![alt text](url) 或 ![](url) 或 ![](url "title")
        markdown_image_pattern = re.compile(
            r'!\[([^\]]*)\]\(([^\)]+)\)',  # 匹配 ![alt](url) 格式
            re.IGNORECASE
        )
        
        def is_url_or_file_path(text: str) -> bool:
            """判断是否是 URL 或文件路径"""
            text = text.strip().strip('"\'')  # 去除引号和空格
            # 检查是否是 HTTP/HTTPS URL
            if text.startswith(('http://', 'https://')):
                return True
            # 检查是否是文件路径（包含路径分隔符或有扩展名）
            if '/' in text or '\\' in text:
                # 检查是否有文件扩展名
                if '.' in text:
                    ext = text.split('.')[-1].lower()
                    if ext in {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'tiff', 
                              'mp4', 'mov', 'avi', 'mkv', 'mp3', 'wav', 'flac',
                              'pdf', 'doc', 'docx', 'ppt', 'pptx'}:
                        return True
            return False
        
        content_clear_md = content
        
        # 查找所有 markdown 格式的图片链接，只替换包含 URL/文件路径 的
        for match in markdown_image_pattern.finditer(content):
            markdown_str = match.group(0)  # 完整的 markdown 格式，如 ![alt](url)
            url_or_path = match.group(2).strip()  # 提取 URL 或路径
            
            # 处理可能包含的引号和空格（markdown 支持 ![alt](url "title") 格式）
            url_or_path = url_or_path.strip('"\'')  # 去除首尾的引号
            # 如果包含空格，取第一部分（标题会被忽略）
            url_or_path = url_or_path.split()[0] if url_or_path.split() else url_or_path
            
            # 只处理 URL 或文件路径，其他的保留 markdown 格式不变
            if is_url_or_file_path(url_or_path):
                # 将 markdown 格式替换为纯 URL
                content_clear_md = content_clear_md.replace(markdown_str, url_or_path)
                logger.info(f"清除 markdown 格式: {markdown_str} -> {url_or_path}")
            # 其他的 markdown 格式保持不变，不处理
        
        return content_clear_md
    
    def _extract_url_context(self, content: str, url: str) -> str:
        """
        提取 URL 所在位置前后的段落（以换行为单位的一段）作为上下文
        
        Args:
            content: 内容文本
            url: 要查找的 URL
            
        Returns:
            str: 上下文字符串，格式为 "{前一段}\\n{placeholder}\\n{后一段}"，如果找不到则返回空字符串
        """
        if not content or not url:
            return ""
        
        # 找到 URL 在内容中的位置
        url_index = content.find(url)
        if url_index == -1:
            logger.warning(f"在内容中未找到 URL: {url}")
            return ""
        
        # 将内容按行分割（换行符分割）
        lines = content.split('\n')
        
        # 找到 URL 所在的行索引：计算 URL 之前的换行符数量
        url_line_index = content[:url_index].count('\n')
        
        if url_line_index >= len(lines):
            logger.warning(f"URL 所在行索引超出范围: {url}")
            return ""
        
        # 向前查找第一个非空行作为"前一段"
        prev_paragraph = ""
        for i in range(url_line_index - 1, -1, -1):
            line = lines[i].strip()
            if line:  # 找到第一个非空行
                prev_paragraph = line
                break
        
        # 向后查找第一个非空行作为"后一段"
        next_paragraph = ""
        for i in range(url_line_index + 1, len(lines)):
            line = lines[i].strip()
            if line:  # 找到第一个非空行
                next_paragraph = line
                break
        
        # 构建 context 字符串
        # 格式: "{前一段}\n{placeholder}\n{后一段}"
        context_parts = []
        if prev_paragraph:
            context_parts.append(prev_paragraph)
        context_parts.append("{placeholder}")
        if next_paragraph:
            context_parts.append(next_paragraph)
        
        context = "\n".join(context_parts)
        logger.debug(f"提取 URL 上下文: {url}, content \n{content}\n, 前一段: {prev_paragraph[:50]}..., 后一段: {next_paragraph[:50]}...")
        return context
    
    def _infer_file_type(self, file_path: str) -> str:
        target_path = file_path

        # 如果 file_path 是 URL（包含查询参数），需要先解析 URL 提取路径部分
        if target_path.startswith(("http://", "https://")):
            try:
                parsed = urlparse(target_path)
                # 使用 URL 的路径部分（不包含查询参数和锚点）来推断文件类型
                target_path = parsed.path or ""
                # 对于 URL，也尝试使用完整 URL 的 mimetypes.guess_type
                mime_type, _ = mimetypes.guess_type(parsed.path)
                if mime_type:
                    # 检查是否为 SVG 格式（不处理）
                    if mime_type == "image/svg+xml":
                        return None
                    main_type = mime_type.split("/", 1)[0]
                    if main_type:
                        return main_type
            except Exception as exc:
                logger.warning(f"解析 URL 失败: {target_path}, error: {exc}")
                # 如果解析失败，继续使用原始路径
                pass

        # 对于本地文件路径，使用原始逻辑
        mime_type, _ = mimetypes.guess_type(target_path)
        if mime_type:
            # 检查是否为 SVG 格式（不处理）
            if mime_type == "image/svg+xml":
                return None
            main_type = mime_type.split("/", 1)[0]
            if main_type:
                return main_type
        
        # 从路径中提取扩展名（此时 target_path 已经是清理过的路径或本地路径）
        ext = os.path.splitext(target_path)[1].lower()
        # SVG 格式不处理
        if ext == ".svg":
            return None
        if ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"}:
            return "image"
        if ext in {".mp4", ".mov", ".avi", ".mkv"}:
            return "video"
        if ext in {".mp3", ".wav", ".flac"}:
            return "audio"
        if ext in {".pdf", ".doc", ".docx", ".ppt", ".pptx"}:
            return "document"
        return None

    def _image_understanding(self, image_path: str, file_type: Optional[str] = None, context: str="") -> Optional[Any]:
        """
        图像理解
        Args:
            image_path: 图片路径
            file_type: 文件类型
            context: 辅助图片理解的上下文, placeholder会被替换为资源的url
        Returns:
            Optional[Any]: 图像理解结果
        """
        if not self.enable_image_understanding:
            logger.debug("图像理解未开启，跳过: %s", image_path)
            return None
        if not self.dify_client:
            logger.warning("Dify 客户端未初始化，无法进行图像理解")
            return None
        if not image_path.startswith(("http://", "https://")) and not os.path.exists(image_path):
            logger.warning("图片文件不存在，无法进行图像理解: %s", image_path)
            return None

        try:
            logger.info(f"image_path: {image_path} context: {context}")
            if context and context != "{placeholder}":
                context = context.format(placeholder=image_path)
                paragraph = f"给你的图片是{image_path},请你根据图片的上下文理解该图片， {image_path}的上下文为:\n{context}\n请你据此进行图片理解，描述图片的内容"
            else:
                paragraph = self.image_understanding_paragraph or ""
            
            if file_type is None:
                file_type = self._infer_file_type(image_path)
            return self.dify_client.request_dify(
                paragraph=paragraph,
                input_file=image_path,
                file_type=file_type,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("图像理解调用异常: %s", exc)
            return None

    def _image_ocr(
        self,
        image_url: Optional[str],
        file_type: Optional[str] = None,
    ) -> Optional[Any]:

        if not self.enable_image_ocr:
            logger.debug("图像OCR未开启，跳过")
            return None
        if not self.dify_ocr_client:
            logger.warning("Dify OCR 客户端未初始化，无法进行图像OCR")
            return None
        if not image_url:
            logger.warning("未提供有效的图像URL，无法进行图像OCR")
            return None

        inferred_type = file_type or self._infer_file_type(image_url)
        if not inferred_type:
            inferred_type = "image"

        try:
            paragraph = self.image_ocr_paragraph or ""
            return self.dify_ocr_client.request_dify(
                paragraph=paragraph,
                input_file=image_url,
                file_type=inferred_type,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("图像OCR调用异常: %s", exc)
            return None

    def process_one_data(self, json_data: Dict[str, Any], client_name: str="default", context: str="", size_threshold: int = None, area_threshold: int = None, ocr_valid_num_threshold: int = 20) -> Dict[str, Any]:
        f"""处理单条多模态数据
        Args:
            json_data: 单条多模态数据
            client_name: 客户端名称
            context: 上下文,仅json_data为多模数据时使用，placeholder会被替换为资源的url
        Returns:
            Dict[str, Any]: 处理结果，包含以下字段：
                - type: 资源类型
                - public_url: 公开访问URL
                - image_understanding: 图像理解结果
                - image_ocr: 图像OCR结果
                - is_valid: 是否有效
                - s3_path: S3存储路径 (格式: bucket_name/object_key)
                - fileName: 文件名
                - extern_url: 外部链接URL（如果是外链）
        """
        result = {
            "type": None,
            "public_url": None,
            "image_understanding": None,
            "image_ocr": None,
            "is_valid": False,
            "s3_path": None,
            "fileName": None,
            "extern_url": None,
            "image_content_hash": None,
            "image_hash_occurrence_count": 0,
            "is_hash_blacklisted": False,
        }

        if not isinstance(json_data, dict):
            logger.warning("输入数据格式错误，期望 dict 实际 %s", type(json_data))
            return result

        data_type = json_data.get("type")
        result["type"] = data_type  # 添加 type 字段
        
        if data_type != "image":
            logger.debug("当前类型 %s 暂不处理", data_type)
            return result

        image_path = json_data.get("image_path")
        if not image_path:
            logger.warning("图片类型数据缺少 image_path 字段")
            return result

        # 提取文件名
        fileName = os.path.basename(image_path)
        result["fileName"] = fileName
        
        # 获取外部链接URL（如果有的话）
        extern_url = json_data.get("url")
        result["extern_url"] = extern_url

        image_content_hash = (
            json_data.get("image_content_hash")
            or json_data.get("_image_content_hash")
            or self.image_hash_by_path.get(image_path)
        )
        if image_content_hash:
            result["image_content_hash"] = image_content_hash
            result["image_hash_occurrence_count"] = self.image_hash_counts.get(
                image_content_hash, 0
            )
            if image_content_hash in self.image_hash_blacklist:
                result["is_hash_blacklisted"] = True
                logger.info(
                    "图片hash命中黑名单，跳过上传/OCR/图片理解: %s, count=%s, threshold=%s",
                    image_path,
                    result["image_hash_occurrence_count"],
                    self.image_hash_blacklist_threshold,
                )
                return result

        is_valid = self._is_valid_image(image_path, size_threshold=size_threshold, area_threshold=area_threshold)
        result["is_valid"] = is_valid
        result["is_valid_by_img_info"] = is_valid
        if not is_valid:
            logger.debug("图片未通过有效性校验，跳过处理: %s", image_path)
            # 即使无效，也要设置 public_url 和 s3_path（如果有的话）
            if json_data.get("public_url"):
                result["public_url"] = json_data.get("public_url")
                if json_data.get("s3_path"):
                    result["s3_path"] = json_data.get("s3_path")
            return result

        
        if json_data.get("public_url"):
            public_url = json_data.get("public_url")
            # 如果提供了public_url，尝试从json_data获取s3_path
            if json_data.get("s3_path"):
                s3_path = json_data.get("s3_path")
                result["s3_path"] = s3_path
        else:
            public_url, s3_path = self._upload_image(image_path, client_name)
            result["s3_path"] = s3_path
            
        result["public_url"] = public_url
        file_type = self._infer_file_type(image_path)
        
        ocr = self._image_ocr(public_url, file_type)
        if ocr is not None:
            result["image_ocr"] = ocr
            is_valid_by_ocr, reason = self._is_valid_image_by_ocr(ocr, valid_num_threshold=ocr_valid_num_threshold)
            if (not is_valid_by_ocr
                    and json_data.get("image_source") == "rendered_page"
                    and len(str(ocr).strip()) >= 40):
                # Tables repeat site / business-mode labels; that repetition
                # must not discard an otherwise readable source page.
                is_valid_by_ocr, reason = True, "rendered_page_readable_text"
            logger.info(f"image_path: {image_path} ocr 有效性校验结果: {is_valid_by_ocr}, 原因: {reason}")
            result["is_valid_by_ocr"] = is_valid_by_ocr
            result["is_valid"] = is_valid and is_valid_by_ocr
            if not is_valid_by_ocr:
                logger.warning(f"image_path: {image_path} ocr 有效性校验失败, 原因: {reason}")
                return result

        # Full-page slide renders already carry the source text in OCR. For
        # text-rich pages, index that text directly rather than generating a
        # second, speculative description of the same slide.
        if (json_data.get("image_source") == "rendered_page"
                and result.get("is_valid")
                and len(str(result.get("image_ocr") or "").strip()) >= 200):
            return result

        #context = context.format(placeholder=public_url)
        understanding = self._image_understanding(public_url, file_type, context=context)
        if understanding is not None:
            result["image_understanding"] = understanding

        return result

    def process_content(self, content: str, client_name: str="default", size_threshold: int = None, area_threshold: int = None, ocr_valid_num_threshold: int = 20) -> Dict[str, Any]:
        """
        处理 content 中的外链，若其多媒体数据则进行处理。
        
        1) 若其链接不是内部链接（匹配prefix_fileservice_url）则下载到临时文件（./data/tmp/{daytime}），
           并将其转为内部链接。并替换content中的所有外部链接生成new_content
        2) 初始化一个data_json, 使用process_one_data 进行处理
        3) 将process_one_data返回的结果与url（key）组成字典返回
        4) 返回new_content
        """
        # 初始化返回结果
        result = {
            "multimodal_results": {},  # url -> process_one_data 的结果
            "transfer_url_multimodal_results": {},  # transfer_url(inner_url) -> process_one_data 的结果
            "new_content": content,  # 替换后的内容
        }
        
        if not content or not isinstance(content, str):
            return result
        
        # 1. 清除 markdown 格式，将 markdown 图片链接中的 URL/文件路径提取出来
        content_clear_md = self._clear_url_markdown(content)
        
        # 2. 提取 content_clear_md 中所有的链接（支持鉴权参数等复杂情况）
        # 匹配更完整的 URL，包括查询参数、锚点等
        # 使用更宽松的匹配模式，确保捕获包含鉴权参数的完整 URL
        url_pattern = re.compile(
            r'(https?://'  # http:// or https://
            r'(?:[-\w.@])+'  # 域名部分（支持邮箱格式的域名）
            r'(?::[0-9]+)?'  # 可选端口
            r'(?:/(?:[^\s<>"\'`\]]*)?)?'  # 路径部分，匹配除空白和引号外的所有字符
            r'(?:\?[^\s<>"\'`\]\]]*)?'  # 查询字符串，包括鉴权参数（token、access_key 等）
            r'(?:#[^\s<>"\'`\]\]]*)?)'  # 锚点部分
            r'(?=[^\w\-./?#]|$)',  # 前瞻断言，确保 URL 结束
            re.IGNORECASE
        )
        urls = url_pattern.findall(content_clear_md)
        
        logger.info(f"找到的URL: {urls}")
        if not urls:
            return result
        
        # 去重，保持顺序，同时规范化 URL（确保参数被保留）
        seen_urls = set()
        unique_urls = []
        for url in urls:
            # 规范化 URL 以便比较，但保留原始 URL（因为可能包含鉴权参数）
            try:
                parsed = urlparse(url)
                # 构建规范化版本用于去重（保留所有参数）
                normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                if parsed.query:
                    normalized += f"?{parsed.query}"
                if parsed.fragment:
                    normalized += f"#{parsed.fragment}"
                
                if normalized not in seen_urls:
                    seen_urls.add(normalized)
                    unique_urls.append(url)  # 保留原始 URL（包含所有参数）
            except Exception as exc:
                logger.warning(f"解析 URL 失败: {url}, error: {exc}")
                # 如果解析失败，直接使用原始 URL 进行去重
                if url not in seen_urls:
                    seen_urls.add(url)
                    unique_urls.append(url)
        
        # 2. 判断是否是内部链接（匹配 prefix_fileservice_url）
        def is_internal_link(url: str) -> bool:
            if not self.prefix_fileservice_url:
                return False
            return url.startswith(self.prefix_fileservice_url)
        
        # 创建临时目录
        daytime = datetime.now().strftime("%Y%m%d_%H%M%S")
        tmp_dir = os.path.join("./data/tmp", daytime)
        os.makedirs(tmp_dir, exist_ok=True)
        
        new_content = content_clear_md
        url_mapping = {}  # 原始URL -> 新的内部URL
        
        # 3. 处理每个链接
        for url in unique_urls:
            try:
                # 判断是否是多媒体数据
                file_type = self._infer_file_type(url)
                logger.info(f"url: {url} 文件类型: {file_type}")
                if file_type not in {"image", "video", "audio"}:
                    continue  # 不是多媒体数据，跳过
                
                # 无论是内部还是外部 URL，都先下载到临时文件
                # 生成临时文件名
                parsed_url = urlparse(url)
                filename = os.path.basename(parsed_url.path)
                if not filename or '.' not in filename:
                    # 根据文件类型生成默认扩展名
                    ext_map = {
                        "image": ".png",
                        "video": ".mp4",
                        "audio": ".mp3"
                    }
                    ext = ext_map.get(file_type, ".bin")
                    filename = f"{uuid.uuid4().hex}{ext}"
                
                tmp_file_path = os.path.join(tmp_dir, filename)
                
                # 下载文件（保留完整的 URL，包括所有鉴权参数）
                try:
                    # urlretrieve 会自动处理 URL 中的所有参数（包括鉴权参数）
                    urlretrieve(url, tmp_file_path)
                    # 只记录 URL 的前缀，避免在日志中暴露鉴权参数
                    url_for_log = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                    if parsed_url.query:
                        url_for_log += f"?{parsed_url.query[:50]}..." if len(parsed_url.query) > 50 else f"?{parsed_url.query}"
                    logger.info(f"下载文件成功: {url_for_log} -> {tmp_file_path}")
                except Exception as exc:
                    # 记录详细的错误信息，但不暴露完整的鉴权参数
                    url_for_log = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                    if parsed_url.query:
                        url_for_log += f"?{parsed_url.query[:50]}..." if len(parsed_url.query) > 50 else f"?{parsed_url.query}"
                    logger.warning(f"下载文件失败: {url_for_log}, error: {exc}")
                    continue
                
                # 判断是否是内部链接
                is_internal = is_internal_link(url)
                s3_path = None
                if is_internal:
                    # 内部链接：不上传，直接使用原 URL 作为 public_url
                    internal_url = url
                    logger.debug(f"链接是内部链接，不上传: {url}")
                else:
                    # 外部链接：上传文件并获取内部链接
                    internal_url, s3_path = self._upload_image(tmp_file_path, client_name)
                    if not internal_url:
                        logger.warning(f"上传文件失败: {tmp_file_path}")
                        continue
                    
                    logger.info(f"外部文件已转换为内部链接: {url} -> {internal_url}, s3_path: {s3_path}")
                
                # 记录URL映射
                url_mapping[url] = internal_url
                
                # 提取 URL 所在位置的上下文（前后一段文字，以换行为单位）
                context = self._extract_url_context(content, url)
                
                # 4. 使用 process_one_data 处理多媒体数据（仅处理 image 类型）
                if file_type == "image":
                    # 使用本地下载的文件路径进行处理
                    data_json = {
                        "type": "image",
                        "image_path": tmp_file_path,
                        "public_url": internal_url,  # 传入 public_url，避免二次上传
                        "s3_path": s3_path,  # 传入 s3_path
                        "extern_url": url if not is_internal else None,  # 如果是外部链接，记录原始URL
                    }
                    
                    process_result = self.process_one_data(data_json, client_name, context=context, size_threshold=size_threshold, area_threshold=area_threshold, ocr_valid_num_threshold=ocr_valid_num_threshold)
                    result["multimodal_results"][url] = process_result
                    result["transfer_url_multimodal_results"][internal_url] = process_result
                    
                    # 如果处理结果中有新的 public_url，使用它作为内部链接
                    if process_result.get("public_url"):
                        url_mapping[url] = process_result["public_url"]
                        internal_url = process_result["public_url"]
                else:
                    # 对于 video 和 audio，只记录基本信息，不进行进一步处理
                    fileName = os.path.basename(tmp_file_path)
                    result["multimodal_results"][url] = {
                        "public_url": internal_url,
                        "type": file_type,
                        "is_valid": True,
                        "s3_path": s3_path,
                        "fileName": fileName,
                        "extern_url": url if not is_internal else None,
                    }
                    result["transfer_url_multimodal_results"][internal_url] = {
                        "public_url": internal_url,
                        "type": file_type,
                        "is_valid": True,
                        "s3_path": s3_path,
                        "fileName": fileName,
                        "extern_url": url if not is_internal else None,
                    }
                
            except Exception as exc:
                logger.exception(f"处理链接失败: {url}, error: {exc}")
                continue
        
        # 5. 替换 content_clear_md 中的所有外部链接生成 new_content
        # 按照 URL 长度降序排序，避免短 URL 替换长 URL 的一部分
        if url_mapping:
            new_content = content_clear_md
            # 按 URL 长度降序排序，确保先替换更长的 URL（可能包含更多参数）
            sorted_mappings = sorted(url_mapping.items(), key=lambda x: len(x[0]), reverse=True)
            for original_url, internal_url in sorted_mappings:
                # 替换所有出现的原始URL为内部URL（包括所有鉴权参数）
                new_content = new_content.replace(original_url, internal_url)
            result["new_content"] = new_content
        result["content_with_multimodal_unsderstanding"] = construct_multimodel_undestanding_content(result["new_content"], result["transfer_url_multimodal_results"])
        return result


def _load_process_data(process_data_path: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    if isinstance(process_data_path, dict):
        return process_data_path
    if isinstance(process_data_path, str):
        if not os.path.exists(process_data_path):
            raise FileNotFoundError(f"待处理数据文件不存在: {process_data_path}")
        with open(process_data_path, "r", encoding="utf-8") as f:
            return json.load(f)
    raise TypeError("process_data_path 需要为 str 或 dict")


def _ensure_parent_dir(path: str) -> None:
    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)


def process_multimodal_data_one_file(
    document_multidata_process: Union[str, MultimodalProcess],
    client_name: str,
    process_data_path: Union[str, Dict[str, Any]],
    multimodal_data_info_dict: Dict[str, Any], 
    output_path: Union[str, None],
) -> Dict[str, Any]:
    """
    document_multidata_process: 文档多模态处理对象
    client_name: 客户端名称
    process_data_path: 待处理数据文件路径
    multimodal_data_info_dict: 多模态数据信息字典, 为了方便后续将文本类型存储转为多模态信息存储的做法，打的补丁，后续要修正
    output_path: 输出文件路径, 
    """
    if isinstance(document_multidata_process, str):
        processor = MultimodalProcess(document_multidata_process)
    elif isinstance(document_multidata_process, MultimodalProcess):
        processor = document_multidata_process
    else:
        raise TypeError("document_multidata_process 需要为配置路径或 MultimodalProcess 实例")

    data_payload = _load_process_data(process_data_path)
    processor.prepare_image_hash_blacklist(data_payload)
    processed_data: Dict[str, List[Dict[str, Any]]] = {}

    def _get_pre_text(items_inner: List[Dict[str, Any]]) -> str:
        for i in range(-1, -len(items_inner), -1):
            if items_inner[i].get("type") == "text":
                return items_inner[i].get("text_content")
            if items_inner[i].get("type") == "image" and items_inner[i].get("is_valid"):
                return items_inner[i].get("image_understanding")
        return ""
    def _get_post_text(items_inner: List[Dict[str, Any]]) -> str:
        for i in range(len(items_inner)):
            if items_inner[i].get("type") == "text":
                return items_inner[i].get("text_content")
        return ""
    all_processed_items: List[Dict[str, Any]] = []
    for page, items in data_payload.items():
        if not isinstance(items, Iterable):
            logger.warning("页 %s 数据格式异常，已跳过", page)
            continue

        new_items: List[Dict[str, Any]] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                logger.warning("页 %s 存在非 dict 数据，已跳过", page)
                continue
            processed_item = dict(item)
            #上一页的数据也要考虑的
            pre_text = _get_pre_text(all_processed_items)
            post_items = items[index+1:] if index < len(items) - 1 else [] 
            post_items = post_items + processed_data.get(str(int(page)+1), []) 
            post_text = _get_post_text(post_items)
            context = "{placeholder}"
            if pre_text:
                context = f"{pre_text}" + "{placeholder}"
            if post_text:
                context = context + f"{post_text}"
            result = processor.process_one_data(item, context=context)
            processed_item.update(result)
            new_items.append(processed_item)
            all_processed_items.append(processed_item)
            if result.get("public_url"):
                multimodal_data_info_dict[result["public_url"]] = processed_item
        processed_data[page] = new_items

    if isinstance(output_path, str) and output_path:
        _ensure_parent_dir(output_path)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(processed_data, f, ensure_ascii=False, indent=2)

    return processed_data



def _build_output_json_path(content_json_path: str) -> str:
    base_dir = os.path.dirname(content_json_path)
    file_name = os.path.basename(content_json_path)
    name, ext = os.path.splitext(file_name)
    ext = ext or ".json"
    new_name = f"{name}_multimodal{ext}"
    return os.path.join(base_dir, new_name)


def batch_process_multimodal_data_file(
    config_path: Union[str, Dict[str, Any]],
    data_map_file: str,
    field_num: int = 0,
    new_mapfile_path: Optional[str] = None,
    multimodal_data_info_path: Optional[str] = None,
    is_local: bool = False, # 是否在本地修改结果
) -> List[str]:
    processor = MultimodalProcess(config_path)
    logger.info(f"处理映射文件: {data_map_file}")
    if not os.path.exists(data_map_file):
        logger.error(f"映射文件不存在: {data_map_file}")
        raise FileNotFoundError(f"映射文件不存在: {data_map_file}")

    with open(data_map_file, "r", encoding="utf-8") as f:
        raw_lines = [line.strip() for line in f if line.strip()]


    updated_lines: List[str] = []
    multimodal_data_info_dict = {}
    for line in raw_lines:
        parts = line.split("\t")
        client_name = parts[0]
        content_json_path = parts[field_num]
        output_json_path = (
            content_json_path if is_local else _build_output_json_path(content_json_path)
        )
        logger.info(f"处理文件: {content_json_path} 输出文件: {output_json_path}")
        try:
            process_multimodal_data_one_file(
                document_multidata_process=processor,
                client_name=client_name,
                process_data_path=content_json_path,
                multimodal_data_info_dict=multimodal_data_info_dict,
                output_path=output_json_path
            )
            parts.append(output_json_path)
            updated_lines.append("\t".join(parts))
        except Exception as exc:
            tb = traceback.format_exc() # pylint: disable=broad-except
            logger.error(f"处理文件失败: {line}")
            logger.error(tb)

    if not is_local and new_mapfile_path and updated_lines:
        _ensure_parent_dir(new_mapfile_path)
        with open(new_mapfile_path, "w", encoding="utf-8") as f:
            f.write("\n".join(updated_lines))
    if isinstance(multimodal_data_info_path, str) and multimodal_data_info_path:
        _ensure_parent_dir(multimodal_data_info_path)
        with open(multimodal_data_info_path, "w", encoding="utf-8") as f:
            json.dump(multimodal_data_info_dict, f, ensure_ascii=False, indent=2)
    return updated_lines 


def batch_process_html_file(
    config_path: Union[str, Dict[str, Any]],
    data_map_file: str,
    field_num: int = -1,
    process_key: str = 'firecrawl_content',
    new_mapfile_path: Optional[str] = None,
    multimodal_data_info_path: Optional[str] = None,
    is_local: bool = False,
) -> List[str]:
    """
    批量处理文件数据， client_name"\tcrawl_url"\tcontent_type"\tcrawler_degree"\thtml_local_file"\tdata_json_file
    
    Args:
        config_path: 配置路径或配置字典
        data_map_file: 数据映射文件路径，每行格式：client_name\tcrawl_url\tcontent_type\tcrawler_degree\thtml_local_file\tdata_json_file
        field_num: data_json_file 字段在行中的位置（从0开始，负数表示从后往前）
        process_key: JSON文件中要处理的content数据的key
        new_mapfile_path: 新映射文件路径（可选）
        multimodal_data_info_path: 多模态资源信息映射文件路径（可选）
        is_local: 是否在本地修改结果
    
    Returns:
        更新后的行列表
    """
    processor = MultimodalProcess(config_path)
    logger.info(f"处理映射文件: {data_map_file}")
    if not os.path.exists(data_map_file):
        logger.error(f"映射文件不存在: {data_map_file}")
        raise FileNotFoundError(f"映射文件不存在: {data_map_file}")

    with open(data_map_file, "r", encoding="utf-8") as f:
        raw_lines = [line.strip() for line in f if line.strip()]

    updated_lines: List[str] = []
    multimodal_data_info_dict: Dict[str, Any] = {}
    
    for line in raw_lines:
        parts = line.split("\t")
        
        # 验证字段数量
        if len(parts) <= abs(field_num) if field_num < 0 else field_num:
            logger.warning(f"行字段数量不足，跳过: {line}")
            updated_lines.append(line)
            continue
        
        # 获取字段值
        client_name = parts[0] if len(parts) > 0 else "default"
        data_json_path = parts[field_num]
        
        # 生成输出文件路径
        if is_local:
            output_json_path = data_json_path
        else:
            base_dir = os.path.dirname(data_json_path)
            file_name = os.path.basename(data_json_path)
            name, ext = os.path.splitext(file_name)
            ext = ext or ".json"
            output_json_path = os.path.join(base_dir, f"{name}_multimodal.txt")
        
        logger.info(f"处理文件: {data_json_path} -> {output_json_path}")
        
        try:
            # 读取 JSON 文件
            if not os.path.exists(data_json_path):
                logger.warning(f"JSON文件不存在: {data_json_path}")
                updated_lines.append(line)
                continue
            
            with open(data_json_path, "r", encoding="utf-8") as f:
                data_json = json.load(f)
            
            # 获取要处理的内容
            if not isinstance(data_json, dict):
                logger.warning(f"JSON文件格式错误，期望dict，实际{type(data_json)}: {data_json_path}")
                updated_lines.append(line)
                continue
            
            content = data_json.get(process_key)
            if not content:
                logger.warning(f"JSON文件中未找到key '{process_key}': {data_json_path}")
                updated_lines.append(line)
                continue
            
            if not isinstance(content, str):
                logger.warning(f"content字段不是字符串类型: {data_json_path}")
                updated_lines.append(line)
                continue
            
            # 使用 process_content 处理内容
            result = processor.process_content(content, client_name=client_name, size_threshold=8000, area_threshold=A4_MIN_AREA_PX / 5, ocr_valid_num_threshold=10) #  html 中图片比较少背景图，可以放松一点
            
            # 将处理结果写入 JSON 数据
            data_json["transfer_url_content"] = result.get("new_content", content)
            data_json["url_process_info"] = result.get("multimodal_results", {})
            data_json["content_with_multimodal_unsderstanding"] = result.get("content_with_multimodal_unsderstanding", "")
            data_json["transfer_url_multimodal_results"] = result.get("transfer_url_multimodal_results", {})
            
            # 合并 transfer_url_multimodal_results 到 multimodal_data_info_dict
            transfer_url_results = result.get("transfer_url_multimodal_results", {})
            for url, item_info in transfer_url_results.items():
                # 确保每个元素都有 s3_path, fileName, extern_url 字段
                if url not in multimodal_data_info_dict:
                    multimodal_data_info_dict[url] = item_info
            
            # 保存新 JSON 文件
            _ensure_parent_dir(output_json_path)
            with open(output_json_path, "w", encoding="utf-8") as f:
                logger.info(f"write_file: {output_json_path} data_json: {data_json}")
                json_str = json.dumps(data_json, ensure_ascii=False, indent=2)
                f.write(json_str)
                f.flush()  # 确保数据立即写入磁盘
            
            logger.info(f"处理完成: {data_json_path} -> {output_json_path}")
            
            # 构建新的行：原行数据 + 新的json数据地址
            parts.append(output_json_path)
            updated_lines.append("\t".join(parts))
            
        except Exception as exc:
            tb = traceback.format_exc()
            logger.error(f"处理文件失败: {line}")
            logger.error(tb)
            # 即使处理失败，也保留原行
            updated_lines.append(line)

    # 保存新的映射文件
    if new_mapfile_path and updated_lines:
        _ensure_parent_dir(new_mapfile_path)
        with open(new_mapfile_path, "w", encoding="utf-8") as f:
            f.write("\n".join(updated_lines))
        logger.info(f"保存新的映射文件: {new_mapfile_path}")

    # 保存多模态资源信息映射文件
    if multimodal_data_info_path and multimodal_data_info_dict:
        _ensure_parent_dir(multimodal_data_info_path)
        with open(multimodal_data_info_path, "w", encoding="utf-8") as f:
            json.dump(multimodal_data_info_dict, f, ensure_ascii=False, indent=2)
        logger.info(f"保存多模态资源信息映射文件: {multimodal_data_info_path}, 资源数量: {len(multimodal_data_info_dict)}")

    return updated_lines

if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()
