import urllib.parse
import re

DOCUMENT_TYPES = set(['pdf', 'docx', 'doc', 'txt', 'md', 'csv', 'xls', 'xlsx', 'ppt', 'pptx', 'excel'])

def extract_domain(url: str) -> str:
    """
    从URL中提取二级域名
    例如: https://www.example.com/path -> example.com
    """
    try:
        if not url:
            return '其他'
        
        # 如果不是完整URL，尝试添加协议
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower()
        
        # 去掉端口号
        if ':' in domain:
            domain = domain.split(':')[0]
            
        # 提取二级域名，去掉常见的子域名前缀
        domain_parts = domain.split('.')
        if len(domain_parts) >= 2:
            # 常见的子域名前缀
            common_subdomains = ['www', 'wap', 'm', 'mobile', 'api', 'blog', 'news']
            
            # 如果有3个或更多部分，且第一个是常见子域名，则去掉
            if len(domain_parts) >= 3 and domain_parts[0] in common_subdomains:
                return '.'.join(domain_parts[1:])
            # 如果有2个或更多部分，直接取后两个作为二级域名
            elif len(domain_parts) >= 2:
                return '.'.join(domain_parts[-2:])
        
        return domain or '其他'
    except Exception:
        return '其他'

def get_from_norm_type(knowledge_data: dict):
    """
    根据norm_type获取知识数据
    """
    from_type = knowledge_data.get('from_type')
    from_file_name = knowledge_data.get('ext_info',{}).get('from_file_name')
    from_norm_type = 'other'
    if from_type in DOCUMENT_TYPES and from_file_name:
        #from_file_name = from_file_name.split('/')[-1]
        #from_norm_type = from_file_name
        from_norm_type = "document"
        return from_norm_type
    elif from_type == 'chat_auto':
        #from_norm_type = '自动学习'
        from_norm_type = "auto_learning"
        return from_norm_type
    elif from_type == 'chat' or from_type == 'chat_forward_answer':
        #from_norm_type = '老师培训'
        from_norm_type = "teacher_training"
        return from_norm_type
    elif from_type == 'html':
        #from_norm_type = extract_domain(from_file_name)
        from_norm_type = "html"

        return from_norm_type
    elif from_type.find('handle') != -1 or from_type.find('manual') != -1:
        from_norm_type = "manual"
        return from_norm_type
    
    return from_norm_type




# ---------------------------------------------------------------------------
# 默认类目（「默认分组」）
#
# categoryId=1 / 名称「默认分组」在每个 client 的类目树里都真实存在
# （`GET .../knowledge/qaCategory/tree?client=<client>` 返回的第一个一级类目），
# 是前端可见、可筛、可管理的分组，不是占位符。
#
# 入库时不给类目的链路（如群聊自动学习 chat_auto）以前会让文档连
# `primary_category` 字段都没有，按类目 ID/名称过滤整批筛不出来，也进不了
# 任何分组统计；统一兜底到默认分组后至少能被看到和归档。
# ---------------------------------------------------------------------------
DEFAULT_CATEGORY_ID = "1"
DEFAULT_CATEGORY_NAME = "默认分组"


def build_default_category_infos() -> list:
    """默认类目的 `category_infos`，形状与前端手工选「默认分组」插入的数据一致。"""
    return [{
        'category_id': DEFAULT_CATEGORY_ID,
        'category_name': DEFAULT_CATEGORY_NAME,
        'score': 1.0,
        'source': 'default',
    }]


def build_default_primary_category() -> dict:
    """默认类目的 `primary_category`，字段与 process_one_data 构造的结构一致。"""
    return {
        'category_path': DEFAULT_CATEGORY_NAME,
        'category_ids': [DEFAULT_CATEGORY_ID],
        'cate1_name': DEFAULT_CATEGORY_NAME,
        'cate1_id': DEFAULT_CATEGORY_ID,
    }
