from datetime import datetime
from kdb.retrieval.categories.defaults import build_default_category_infos
from kdb.retrieval.categories.defaults import build_default_primary_category
from kdb.retrieval.categories.defaults import get_from_norm_type
from kdb.retrieval.ingestion.identifiers import gen_data_id
from kdb.shared.text.common_utils import clear_none_value
from kdb.shared.text.keywords_tools import gen_keyword_by_title_content
from typing import Any
from typing import Dict
import logging
import traceback

def process_one_data(self, data: Dict[str, Any], index_name: str = None) -> bool:
    """
    处理单条数据,为数据增加必要的embedding和提取关键词。
    Args:
        data: 待处理的数据
    Returns:
        bool: 处理是否成功
    """
    try:
        # 定义schema中的字段
        schema_fields = self.doc_schema_field

        # 初始化ext_info
        ext_info = data.get('ext_info', {})

        # 将非schema字段移动到ext_info
        for field in list(data.keys()):
            if field not in schema_fields:
                ext_info[field] = data.pop(field)

        # 更新ext_info
        data['ext_info'] = ext_info

        # 确保audit_result字段存在且值合法
        if 'is_audit' in data:  # 处理旧数据
            data['audit_result'] = data.pop('is_audit')
        if 'audit_result' not in data and '_id' not in data and not data.get('_id'):
            data['audit_result'] = -1  # 默认未审核
        if data.get('audit_result') is not None and data['audit_result'] not in [-1, 0, 1, 2]:
            logging.warning(f"数据{data.get('_id')}的audit_result值非法: {data['audit_result']}, 设置为默认值-1")
            data['audit_result'] = -1

        # 确保quality_level字段存在且值合法
        if 'quality_level' not in data and '_id' not in data:
            data['quality_level'] = 'mid'  # 默认中等质量
        elif '_id' not in data and data.get('quality_level') not in ['high', 'mid', 'low']:
            logging.warning(f"数据{data.get('_id')}的quality_level值非法: {data['quality_level']}, 设置为默认值mid")
            data['quality_level'] = 'mid'

        # 1. 处理indexes
        if 'indexes' not in data:
            data['indexes'] = []

        if 'image_indexes' not in data:
            data['image_indexes'] = []

        # image_indexes 的文本直接放到indexes中，进行数据冗余存储，todo：后续重构索引库时需要优化，避免重新存储
        for idx in data.get('image_indexes', []):
            if 'text' in idx:
                data['indexes'].append({'text': idx['text']})
        # 如果title不为空且不在indexes中，添加到indexes
        if data.get('title') and not any(idx.get('text') == data['title'] for idx in data.get('indexes', [])):
            data['indexes'].append({'text': data['title']})

        # 如果有同义title，也添加到indexes中
        if data.get('synonyms_title'):
            if not isinstance(data['synonyms_title'], list):
                logging.warning(f"数据{data.get('_id')}的synonyms_title不是列表格式，将被忽略")
                data['synonyms_title'] = []
            else:
                for syn_title in data['synonyms_title']:
                    if not isinstance(syn_title, str):
                        logging.warning(f"数据{data.get('_id')}的synonyms_title包含非字符串元素，将被忽略")
                        continue
                    if not any(idx.get('text') == syn_title for idx in data['indexes']):
                        data['indexes'].append({'text': syn_title})

        # 2. 为indexes中的每个text生成embedding。
        # 空 text 送 DashScope 会 400，异常一路上抛导致**整条数据**入库失败，
        # 所以这里跳过空索引并把它从 indexes 里剔掉，而不是拖垮整条。
        data['indexes'] = [idx for idx in data['indexes']
                           if not ('text' in idx and not str(idx.get('text') or '').strip())]
        for idx in data['indexes']:
            if 'text' in idx and 'embedding' not in idx:
                embedding = self.embedding_tools.text2embedding(idx['text'])
                if embedding is not None:
                    idx['embedding'] = embedding.tolist()

        data['image_indexes'] = [idx for idx in data['image_indexes']
                                 if not ('text' in idx and not str(idx.get('text') or '').strip())]
        for idx in data['image_indexes']:
            if 'text' in idx and 'embedding' not in idx:
                embedding = self.embedding_tools.text2embedding(idx['text'])
                if embedding is not None:
                    idx['embedding'] = embedding.tolist()

        if "multimodal_contents" in data and data.get('multimodal_contents'):
            data["content"] = self.join_multimodal_contents(data.get('multimodal_contents')) # 有多模态内容时，content为多模态内容拼接后的内容
        # 3. 分别处理title_embedding和content_embedding
        if data.get('title') and 'title_embedding' not in data:
            title_embedding = self.embedding_tools.text2embedding(data['title'])
            if title_embedding is not None:
                data['title_embedding'] = title_embedding.tolist()

        if data.get('content') and 'content_embedding' not in data:
            content_embedding = self.embedding_tools.text2embedding(data['content'])
            if content_embedding is not None:
                data['content_embedding'] = content_embedding.tolist()

        # 4. 处理keywords
        if not data.get('keywords') and (data.get('title') or data.get('content')):
            try:
                keywords = gen_keyword_by_title_content(data.get('title', ''), data.get('content', ''), topK=5)
                keywords = [word_info['word'] for word_info in keywords]
                if keywords:
                    data['keywords'] = keywords
            except ImportError:
                logging.warning("关键词生成工具未实现，跳过关键词生成")


        # indexes和image_indexes 不会允许在更新时清空，因为不能检索，只能是根据其它字段自动生成，或指定有的数据。后面最好的做法其实是招回旧数据进行合并，再生成新的indexes和image_indexes，现在会导致一些更新异常，todo:后续需要召回旧数据进行合并
        if "indexes" in data and not data.get('indexes'):
            del data['indexes']
        if "image_indexes" in data and not data.get('image_indexes'):
            del data['image_indexes']

        # 5. 确保data_type为qa或doc时才有title字段
        if data.get('data_type') == 'segment':
            data.pop('title', None)
            data.pop('synonyms_title', None)
        elif data.get('data_type') in ['qa', 'doc']:
            if not data.get('title'):
                logging.warning(f"数据{data.get('_id')}的data_type为{data.get('data_type')}，但缺少title字段")

        # 处理时间字段
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 处理insert_time
        # 三种情况分开：新数据没带就补当前时间；更新（有 _id）没带就不写，让 ES 保留原值；
        # 带了但不是字符串才纠正。注意不能写成 `if 'insert_time' not in data and '_id' not in data
        # ... elif not isinstance(data['insert_time'], str)` —— 「有 _id 且没带 insert_time」
        # 会走进 elif 直接 KeyError，整条数据处理失败。
        if 'insert_time' not in data:
            if '_id' not in data:
                data['insert_time'] = current_time
        elif not isinstance(data['insert_time'], str):
            logging.warning(f"数据{data.get('_id')}的insert_time格式错误，设置为当前时间")
            data['insert_time'] = current_time

        # 处理update_time
        data['update_time'] = current_time

        # 处理from_type
        if 'from_type' not in data and '_id' not in data:
            logging.warning(f"数据{data.get('_id')}缺少from_type字段")
            data['from_type'] = 'unknown'
        elif 'from_type' in data and not isinstance(data['from_type'], str):
            logging.warning(f"数据{data.get('_id')}的from_type不是字符串类型，将被转换")
            data['from_type'] = str(data['from_type'])
        if 'from_type_norm' not in data and '_id' not in data:
            data['from_type_norm'] = get_from_norm_type(data)
        if 'tags' not in data and '_id' not in data:
            data['tags'] = data.get('keywords', [])
        if 'del_flag' not in data and '_id' not in data: # 如果_id存在，则之前应该已经有数据了
            data['del_flag'] = 0
        else:
            logging.info(f"数据{data.get('_id')}的del_flag值非法: {data.get('del_flag')}, 设置为默认值0")
        logging.info(f"数据{data.get('_id')}的category_infos: {data.get('category_infos')}")
        valid_category_infos = []
        if 'category_infos' in data and data.get('category_infos'): # 多个类目来源应该获取旧数据合并后选取多个score > 0 的
            for category_info in data.get('category_infos', []):
                if not isinstance(category_info, dict):
                    continue
                category_info = dict(category_info)
                # webhook/模型可以只传平台名作为 category_name，
                # category_id 由当前 client 的类目树解析，不再强制上游同时传 ID。
                if category_info.get('category_id') in (None, '') and category_info.get('categoryId') not in (None, ''):
                    category_info['category_id'] = category_info.pop('categoryId')
                if category_info.get('category_name') in (None, '') and category_info.get('categoryName') not in (None, ''):
                    category_info['category_name'] = category_info.pop('categoryName')
                if category_info.get('category_id') not in (None, ''):
                    category_info['category_id'] = str(category_info['category_id'])
                if category_info.get('category_name') not in (None, ''):
                    category_info['category_name'] = str(category_info['category_name']).strip()
                if category_info.get('category_id') or category_info.get('category_name'):
                    valid_category_infos.append(category_info)
            data['category_infos'] = valid_category_infos
        # 获取client，优先从data中获取，否则从配置或platform获取。
        client = data.get('client') or data.get('ext_info', {}).get('client') or data.get('platform')
        primary_category_info = None
        parent_chain = []
        if client:
            # 不能只尝试最高分一项：模型可能先给一个不在类目树里的平台名，
            # 后续候选仍有可能有效。显式 category_id/name 仍按最高分优先。
            for category_info in sorted(
                    valid_category_infos, key=lambda x: x.get('score', 0), reverse=True):
                candidate_chain = self.get_category_parent_chain(
                    client,
                    cate_id=category_info.get('category_id'),
                    cate_name=category_info.get('category_name'),
                )
                if candidate_chain:
                    primary_category_info = category_info
                    parent_chain = candidate_chain
                    break

            model_sources = {'model_platform', 'model_tag', 'question_text'}
            has_manual_category = any(
                str(item.get('source') or 'manual') not in model_sources
                for item in valid_category_infos
            )
            if not parent_chain and not has_manual_category:
                parent_chain, inferred_info = self.infer_payoneer_olive_category(client, data)
                if parent_chain and inferred_info:
                    primary_category_info = inferred_info
                    # 走到这里说明原有模型候选均未命中类目树；不要把无效高分候选一同写入 ES。
                    valid_category_infos = [inferred_info]
                    data['category_infos'] = valid_category_infos

        if parent_chain and primary_category_info:
            leaf_category = parent_chain[-1]
            primary_category_info.setdefault('category_id', str(leaf_category.get('category_id') or ''))
            primary_category_info.setdefault('category_name', leaf_category.get('category_name'))
            category_names = [node['category_name'] for node in parent_chain]
            primary_category = {
                'category_path': '-'.join(category_names),
                'category_ids': [node['category_id'] for node in parent_chain],
            }
            for i, node in enumerate(parent_chain):
                level_num = i + 1
                primary_category[f'cate{level_num}_name'] = node['category_name']
                primary_category[f'cate{level_num}_id'] = node['category_id']
            data['primary_category'] = primary_category
            logging.debug(f"构造primary_category成功: {primary_category}")
        elif valid_category_infos:
            logging.warning(f"类目未在client={client}的类目树中找到, data_id: {data.get('_id')}")
            # 模型候选不存在时清掉无效值，让下面统一落默认分组；人工显式值保留便于排查。
            if not any(str(item.get('source') or 'manual') not in {'model_platform', 'model_tag', 'question_text'}
                       for item in valid_category_infos):
                data.pop('category_infos', None)



        # 没有任何类目来源时兜底到「默认分组」（category_id=1，各 client 类目树里都真实存在）。
        # 不补的话文档连 primary_category 字段都没有，前端按类目 ID/名称筛整批都筛不出来，
        # 也进不了任何分组统计（群聊自动学习 chat_auto 链路就是这样漏的）。
        # 只对新数据生效：更新旧数据不写，避免把已有真实类目覆盖成默认分组。
        if '_id' not in data and not data.get('primary_category'):
            data['primary_category'] = build_default_primary_category()
            if not data.get('category_infos'):
                data['category_infos'] = build_default_category_infos()

        if not data.get("dataset") and index_name:
            data['dataset'] = index_name
        if '_id'  in data: # 已有数据，更新清空None值，即不更新这些字段（indexes、image_indexes、primary_category不能指定清空）
            clear_none_value(data, is_local=True)
        if '_id' not in data: # 最后再确保_id存在
            data['_id'] = gen_data_id(data)

        return True

    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"traceback: {tb}")
        logging.error(f"处理数据失败: {str(e)}")
        return False
