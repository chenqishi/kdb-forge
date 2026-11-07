import json

from commons.dify_tools import DIfyWorkFlowMlutiVisionRequest
from config_tools.config import GLOBAL_CONFIG

def process_search_data_image_file(data_file, image_dify_api_key, api_base=None):
    """
    处理搜索数据中的图片文件
    
    Args:
        data_file: 包含图片路径的数据文件
        image_dify_api: Dify API实例
        api_base: API基础URL
        
    Returns:
        处理后的数据列表
    """
    if api_base is None:
        api_base = GLOBAL_CONFIG['dify_api_base']
    processed_data = []
    image_dify_api = DIfyWorkFlowMlutiVisionRequest(api_base=api_base, api_key=image_dify_api_key)
    demand = '请对图片做内容理解，仅描述图片本身的内容，不要做任何推测'
    with open(data_file, 'rb') as f:
        for line in f:
            data_json = json.loads(line)
            image_paths = data_json.get('ori_image_path', [])
            
            # 处理每个图片路径
            image_indexes = []
            for image_path in image_paths:
                # 调用Dify API处理图片
                result = image_dify_api.request_dify(demand, input_file=image_path)
                if result:
                    image_indexes.append({"text": result})
            
            # 更新数据
            if image_indexes:
                data_json['image_indexes'] = image_indexes
            
            # 删除原始图片路径
            if 'ori_image_path' in data_json:
                del data_json['ori_image_path']
            print(json.dumps(data_json, ensure_ascii=False))

# 在主函数中添加测试调用
if __name__ == "__main__":
    import logging
    import sys    
    import fire
    
    # 配置日志
    logging.basicConfig(
        stream=sys.stderr, 
        level=logging.DEBUG, 
        format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '
               '[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
    )
    
    fire.Fire()
        