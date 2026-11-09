# 公开方法导航：下方均绑定到同一个 SearchDataInterface/self，不另建引擎或缓存。
# 查询：search_data / search_data_by_query / search_data_by_multi_query / web_search_data
#       → retrieval/search；相似度计算 → retrieval/ranking.py。
# 入库：insert_data / batch_insert_data / process_one_data / update_data / delete_data
#       → retrieval/ingestion；类目加载、映射与推断 → retrieval/categories。
# 文件操作：list_file_names / resolve_file_name / preview_delete_by_file / delete_by_file
#       → retrieval/file_operations.py；计数与聚合 → retrieval/statistics.py。
# 多模态展示 → retrieval/presentation；引擎构建 → retrieval/engines/bootstrap.py。
# 参数、返回与 SQL 契约见 function_schema/current_index.md 中的对应实现。

from kdb.retrieval.engines.protocol import SearchEngine
from kdb.shared.clients.embedding_tools import AliEmbedding as EmbeddingTools
import json
import kdb.retrieval.categories.inference as _categories_inference
import kdb.retrieval.categories.mapping as _categories_mapping
import kdb.retrieval.engines.bootstrap as _engines_bootstrap
import kdb.retrieval.file_operations as _retrieval_file_operations
import kdb.retrieval.ingestion.deduplication as _ingestion_deduplication
import kdb.retrieval.ingestion.prepare as _ingestion_prepare
import kdb.retrieval.ingestion.writes as _ingestion_writes
import kdb.retrieval.presentation.multimodal as _presentation_multimodal
import kdb.retrieval.ranking as _retrieval_ranking
import kdb.retrieval.search.multi_query as _search_multi_query
import kdb.retrieval.search.pagination as _search_pagination
import kdb.retrieval.search.queries as _search_queries
import kdb.retrieval.statistics as _retrieval_statistics
import kdb.shared.similarity.knowledge as simility_tools
import logging

logger = logging.getLogger(__name__)


class SearchDataInterface(object):
    """检索数据接口类，用于管理检索库的数据操作"""
    
    def __init__(self, search_engine: SearchEngine=None, config_path: str=None, **kwargs):
        """
        初始化接口
        Args:
            search_engine: 实现了基本检索操作的搜索引擎实例
        """
        config = json.load(open(config_path, 'r', encoding='utf-8'))
        if not search_engine:
            search_engine = self.load_search_engine(config.get('search_engine_config_path', ''), **kwargs)
        self.simility_tools = simility_tools.SimilityTools(config.get('simility_config_path', ''))
        self.engine = search_engine
        self.embedding_tools = EmbeddingTools(config.get('embedding_config_path', ''))
        self.is_need_llm = config.get('is_need_llm', False)
        self.check_duplicate = config.get('check_duplicate', True)
        self.all_client_category_dict = {}
        self.category_service_url = config.get('category_service_url', '')
        
        self.category_update_time_interval = config.get('category_update_time_interval', 36000)
        self.category_update_time_dict = {} # 记录每个client的类目字典更新时间
        self.doc_schema_field = {
                'title', 'synonyms_title', 'content', 'data_type', 'platform',
                'audit_result', 'quality_level', 'keywords', 'tags', 'indexes',
                'insert_time', 'update_time', 'from_type', 'ext_info', '_id',
                'title_embedding', 'content_embedding', 'image_indexes', 'del_flag', 'from_type_norm', 'category_infos', "client", 'primary_category', 'dataset',
                'task_id', 'flag', 'multimodal_contents', 'index_name'   # 将embedding字段加入schema
            }
        self.multimodal_prefix = config.get('multimodal_prefix', '')
        
        # 如果配置中包含client，则初始化加载该client的类目字典
        if config.get('client'):
            self.load_category_map_dict(config['client'])

    load_search_engine = _engines_bootstrap.load_search_engine

    load_category_map_dict = _categories_mapping.load_category_map_dict


    map_cate_name_to_id = _categories_mapping.map_cate_name_to_id

    find_duplicates = _ingestion_deduplication.find_duplicates
    
    insert_data = _ingestion_writes.insert_data
    
    get_category_parent_chain = _categories_mapping.get_category_parent_chain

    _category_name_occurs = staticmethod(_categories_inference._category_name_occurs)

    infer_payoneer_olive_category = _categories_inference.infer_payoneer_olive_category
        


    join_multimodal_contents = _presentation_multimodal.join_multimodal_contents

    render_multimodal_urls = _presentation_multimodal.render_multimodal_urls

    process_one_data = _ingestion_prepare.process_one_data
    
    batch_insert_data = _ingestion_writes.batch_insert_data
    
    update_data = _ingestion_writes.update_data
    
    delete_data = _ingestion_writes.delete_data
    
    search_data = _search_queries.search_data
    
    update_data_value = _ingestion_writes.update_data_value
    
    get_unique_values = _retrieval_statistics.get_unique_values

    # ================= 按来源文件名批量下架知识 =================
    #
    # 设计与实测依据见 docs/按文件名删除知识服务_方案.md。三条硬约束：
    #   1) 只作用于非对话来源（FROM_TYPE_SCOPE 白名单），对话学来的知识不在范围内
    #   2) match_mode 严格二选一，exact 查不到不转模糊、fuzzy 不达阈值不退回精确
    #   3) 一律软删 del_flag=1，删前写快照

    # 只处理"来源于文件/网页/免审录入"的知识。
    # 必须用白名单而不是 must_not=auto_learning：存量里 auto_learning 还有中文旧写法
    # "自动学习"（实测 payoneer_olive 有 334 条），黑名单会让它漏网被删。
    FROM_TYPE_SCOPE = ["document", "html", "manual"]

    FILE_NAME_FIELD = "ext_info.from_file_name"
    FILE_NAME_KEYWORD = "ext_info.from_file_name.keyword"

    # 文档重跑后，新知识用新文件名入库，但它取代的是另一个名字的旧文档
    # （实测 wayfair：库里旧名带分类前缀「基础运营_管理我的团队页面.docx」，
    #   新包同一篇叫「管理"我的团队 (My Team)"页面.docx」，纯文件名对不上）。
    # 重跑入库时把前身文件名写进 ext_info.supersedes_file_name，
    # 删除时两个字段一起匹配 —— 这样前端删旧文件名能连新知识一起删掉，反之亦然。
    SUPERSEDES_FIELD_KEYWORD = "ext_info.supersedes_file_name.keyword"

    # .keyword 的 ignore_above，超过就不会被索引成 keyword，term 查询永远查不到且不报错
    KEYWORD_IGNORE_ABOVE = 256
    # index.max_wildcard_length，本集群为 50；留 2 个字符给前后的 *
    MAX_WILDCARD_FRAGMENT = 48
    # 模糊匹配采纳阈值
    DICE_THRESHOLD = 0.9

    _bigrams = staticmethod(_retrieval_file_operations._bigrams)

    dice_similarity = classmethod(_retrieval_file_operations.dice_similarity)

    _escape_wildcard = staticmethod(_retrieval_file_operations._escape_wildcard)

    _scope_filters = _retrieval_file_operations._scope_filters

    _build_file_query = _retrieval_file_operations._build_file_query

    get_from_type_count = _retrieval_statistics.get_from_type_count

    list_file_names = _retrieval_file_operations.list_file_names

    resolve_file_name = _retrieval_file_operations.resolve_file_name

    preview_delete_by_file = _retrieval_file_operations.preview_delete_by_file

    delete_by_file = _retrieval_file_operations.delete_by_file

    _dump_snapshot = _retrieval_file_operations._dump_snapshot
    
    get_data_by_id = _search_queries.get_data_by_id
    
    search_data_by_query = _search_queries.search_data_by_query

    search_data_by_multi_query = _search_multi_query.search_data_by_multi_query
    
    _search_data_by_multi_query_threading = _search_multi_query._search_data_by_multi_query_threading
        
    
    web_search_data = _search_pagination.web_search_data
    
    _cal_title_similarity = _retrieval_ranking._cal_title_similarity
            


    
    _cal_similarity = _retrieval_ranking._cal_similarity
