from typing import Any
from typing import Dict
from urllib.parse import quote

def join_multimodal_contents(self, multimodal_contents: list[Dict[str, Any]]) -> str:
    """
    拼接多模态内容
    Args:
        data: 待拼接的多模态内容
    Returns:
        str: 拼接后的内容
    """
    content = ""
    for file_info in multimodal_contents:
        if file_info.get("type") == "text":
            content = f"{content}\n{file_info.get('content')}"  if content else file_info.get('content')
        elif file_info.get("type") in ["image", "video", "audio", "file"]:
            address = f'[multimodal_prefix]{file_info["path"]}' if file_info.get("path") else file_info.get("url")
            if not address:
                continue
            content = f"{content}\n{address}"  if content else address
    return content


def render_multimodal_urls(self, doc: Dict[str, Any]) -> None:
    """
    检索返回时把 content 里的 [multimodal_prefix] 占位符实时拼成真实 URL，
    并在内部存储的地址后面带上 filename 参数，供文件服务返回正确的下载文件名。
    形如: https://file.marsmind.cc/boot-admin/xxx/1234.xls?filename=test_name.xls
    只处理内部 path，外链（multimodal_contents 里只有 url 的条目）入库时就没有占位符，不受影响。
    Args:
        doc: 一条检索结果，原地修改 doc['content']
    """
    if not doc:
        return
    content = doc.get('content')
    if not isinstance(content, str) or '[multimodal_prefix]' not in content:
        return

    # 按 path 长度倒序替换，避免某个 path 是另一个 path 的前缀时先替短的把长的截断
    multimodal_contents = doc.get('multimodal_contents') or []
    path_name_pairs = []
    for file_info in multimodal_contents:
        if not isinstance(file_info, dict):
            continue
        path = file_info.get('path')
        file_name = file_info.get('fileName')
        if path and file_name:
            path_name_pairs.append((path, file_name))
    path_name_pairs.sort(key=lambda pair: len(pair[0]), reverse=True)

    for path, file_name in path_name_pairs:
        placeholder = f'[multimodal_prefix]{path}'
        if placeholder not in content:
            continue
        separator = '&' if '?' in path else '?'
        full_url = f'{self.multimodal_prefix}{path}{separator}filename={quote(file_name, safe="")}'
        content = content.replace(placeholder, full_url)

    # 兜底：multimodal_contents 里没登记、或没有 fileName 的占位符，仍然只替换前缀
    doc['content'] = content.replace('[multimodal_prefix]', self.multimodal_prefix)
