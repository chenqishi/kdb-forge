from kdb.retrieval.engines.factory import EsSearchInterface
from kdb.shared.config.private_values import private_value as _private_value
from typing import List
from typing import Union
import hashlib
import json
import logging

def test_es_insert_and_create(file_path: str,
                             hosts: Union[str, List[str]],
                             username: str,
                             password: str):
    """
    测试ES的插入和创建操作
    Args:
        file_path: 数据文件路径
        hosts: ES服务器地址
        username: ES用户名
        password: ES密码
    """
    try:
        # 初始化ES接口
        es_interface = EsSearchInterface(
            hosts=hosts,
            username=username,
            password=password,
            vector_fields={"embedding": 1024},  # 假设使用默认768维向量
            index_name="test_knowledge"  # 使用测试索引名
        )

        # 读取并处理数据
        with open(file_path, 'r', encoding='utf-8') as f:
            index = 0
            for line in f:
                try:
                    # 解析原始数据
                    raw_data = json.loads(line.strip())

                    # 生成文档ID
                    doc_id = hashlib.md5(line.strip().encode()).hexdigest()
                    embedding = [index * 0.01] * 1024
                    embedding[index] = 0.2
                    index += 1
                    # 转换为目标格式
                    doc_data = {
                        "_id": doc_id,  # 使用内容hash作为ID
                        "title": raw_data.get("title", ""),
                        "content": raw_data.get("content", ""),
                        "data_type": "qa",  # 根据数据格式判断为qa类型
                        "platform": raw_data.get("platform", ""),
                        "is_audit": 0,  # 默认未审核
                        "keywords": [],  # 暂时为空
                        "indexes": [
                            {
                                "text": raw_data.get("title", "") + " " + raw_data.get("content", ""),
                                "embedding": embedding
                            }
                        ],
                        "ext_info": {
                            "document_name": raw_data.get("document_name", "")
                        }
                    }

                    # 插入数据
                    success = es_interface.insert(doc_data, refresh_imm=False)
                    if success:
                        print(f"成功插入数据: {doc_id}")
                    else:
                        print(f"插入数据失败: {doc_id}")

                except json.JSONDecodeError:
                    print(f"解析JSON失败: {line.strip()}")
                except Exception as e:
                    print(f"处理数据失败: {str(e)}")

    except Exception as e:
        print(f"测试失败: {str(e)}")


def test_search(hosts: str,
                username: str,
                password: str,
                index_name: str = "test_knowledge"):
    """
    测试ES的各种检索功能
    Args:
        hosts: ES服务器地址
        username: ES用户名
        password: ES密码
        index_name: 索引名称
    """
    try:
        # 初始化ES接口
        es_interface = EsSearchInterface(
            hosts=hosts,
            username=username,
            password=password,
            vector_fields={"embedding": 1024},
            index_name=index_name
        )

        # 1. 测试文本检索
        print("\n=== 测试文本检索 ===")
        text_query = {
            "query": "IOSS码",  # 文本查询
        }
        text_results = es_interface.search(text_query, size=5)
        print(f"文本检索结果数量: {len(text_results)}")
        for result in text_results:
            print(f"文档ID: {result['_id']}")
            print(f"标题: {result['title']}")
            print(f"内容: {result['content']}")
            print(f"相关度分数: {result['score']}\n")

        # 2. 测试向量检索
        print("\n=== 测试向量检索 ===")
        embedding = [0.01] * 1024
        embedding[3] = 0.2
        vector_query = {
            "vector": {
                "value": embedding
            }
        }
        vector_results = es_interface.search(vector_query, size=5)
        print(f"向量检索结果数量: {len(vector_results)}")
        for result in vector_results:
            print(f"文档ID: {result['_id']}")
            print(f"标题: {result['title']}")
            print(f"相似度分数: {result['score']}\n")

        # 3. 测试属性检索
        print("\n=== 测试属性检索 ===")
        attribute_query = {
            "attribute": {
                "platform": "RakutenFrance",
                "data_type": "qa",
                "is_audit": 0
            }
        }
        attribute_results = es_interface.search(attribute_query, size=5)
        print(f"属性检索结果数量: {len(attribute_results)}")
        for result in attribute_results:
            print(f"文档ID: {result['_id']}")
            print(f"平台: {result['platform']}")
            print(f"类型: {result['data_type']}")
            print(f"标题: {result['title']}\n")

        # 4. 测试混合检索
        print("\n=== 测试混合检索 ===")
        mixed_query = {
            "query": "IOSS码",
            "attribute": {
                "platform": "RakutenFrance"
            },
            "vector": {
                "value": embedding
            }
        }
        mixed_results = es_interface.search(mixed_query, size=5)
        print(f"混合检索结果数量: {len(mixed_results)}")
        for result in mixed_results:
            print(f"文档ID: {result['_id']}")
            print(f"平台: {result['platform']}")
            print(f"标题: {result['title']}")
            print(f"相关度分数: {result['score']}\n")

    except Exception as e:
        print(f"测试检索失败: {str(e)}")


def test_update(file_path: str,
                hosts: Union[str, List[str]],
                username: str,
                password: str):
    """
    测试ES的更新操作
    Args:
        file_path: 数据文件路径
        hosts: ES服务器地址
        username: ES用户名
        password: ES密码
    """
    try:
        # 初始化ES接口
        es_interface = EsSearchInterface(
            hosts=hosts,
            username=username,
            password=password,
            vector_fields={"embedding": 1024},
            index_name="test_knowledge"
        )

        # 读取并处理数据
        with open(file_path, 'r', encoding='utf-8') as f:
            index = 0
            for line in f:
                try:
                    # 解析原始数据
                    raw_data = json.loads(line.strip())

                    # 生成文档ID
                    doc_id = hashlib.md5(line.strip().encode()).hexdigest()
                    embedding = [ 0.01] * 1024
                    embedding[index] = 0.2
                    index += 1

                    # 转换为目标格式
                    doc_data = {
                        "title": raw_data.get("title", ""),
                        "content": raw_data.get("content", ""),
                        "data_type": "qa",
                        "platform": raw_data.get("platform", ""),
                        "is_audit": 0,
                        "keywords": [],
                        "indexes": [
                            {
                                "text": raw_data.get("title", "") + " " + raw_data.get("content", ""),
                                "embedding": embedding
                            }
                        ],
                        "ext_info": {
                            "document_name": raw_data.get("document_name", "")
                        }
                    }

                    # 更新数据
                    success = es_interface.update(doc_id, doc_data)
                    if success:
                        print(f"成功更新数据: {doc_id}")
                    else:
                        print(f"更新数据失败: {doc_id}")

                except json.JSONDecodeError:
                    print(f"解析JSON失败: {line.strip()}")
                except Exception as e:
                    print(f"处理数据失败: {str(e)}")

    except Exception as e:
        print(f"测试失败: {str(e)}")


if __name__ == "__main__":
    import logging
    import sys
    import fire

    # 配置日志
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '
               '[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
    )

    # ES配置
    ES_CONFIG = {
        "hosts": "http://for-kuajing-bot-a4d.public.cn-shenzhen.es-serverless.aliyuncs.com:9200",
        "username": "for-kuajing-bot-a4d",
        "password": _private_value('86eba6bfcdaf942a9797462b')
    }

    def search():
        """测试ES的各种检索功能"""
        ES_CONFIG["index_name"] = "test_knowledge"
        test_search(**ES_CONFIG)

    def insert(file_path: str):
        """
        测试ES的插入和创建操作
        Args:
            file_path: 数据文件路径
        """
        test_es_insert_and_create(file_path=file_path, **ES_CONFIG)

    def update(file_path: str):
        """
        测试ES的更新操作
        Args:
            file_path: 数据文件路径
        """
        test_update(file_path=file_path, **ES_CONFIG)

    # 使用fire注册命令
    fire.Fire({
        "search": search,
        "insert": insert,
        "update": update
    })
