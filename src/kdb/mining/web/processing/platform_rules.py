import json
import re
import logging
import sys
from bs4 import BeautifulSoup
import traceback
from kdb.shared.clients.dify_tools import DifyWorkFlowRequest
from kdb.shared.config.global_config import GLOBAL_CONFIG
def clear_esg_data(data_file):
    """
    """
    data_jsons = json.load(open(data_file, 'r', encoding='utf-8'))
    dedup_dict = dict()
    for data_json in data_jsons:
        title = data_json['title']
        content = data_json['html']
        title = title.replace('ESG跨境', '').replace('ESG', '')
        title = title.strip('-').strip()
        content = data_json['html'].replace('ESG跨境', '').replace('ESG', '')
        content = content.split('推荐阅读', )[0]
        content = content.split('特别声明', )[0]
        content = re.sub('[点赞|收藏]', '', content)
        content = content.replace(title, '')
        content = content.split('\n分享\n')[-1]
        content = content.strip()
        new_data_json = dict()
        new_data_json['title'] = title
        new_data_json['content'] = content
        if title in dedup_dict:
            continue
        dedup_dict[title] = 1
        print(json.dumps(new_data_json, ensure_ascii=False))



def clear_wordlist_data(html_file):
    """
    解析HTML文件中的特定元素并转换为字典格式
    
    Args:
        html_file: HTML文件路径
    
    Returns:
        dict: 包含解析结果的字典
    """
    # 读取HTML文件
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    html_content = html_content.replace('卖家资质要求', '开店要求')
    html_content = html_content.replace('优惠政策', '开店福利')
    soup = BeautifulSoup(html_content, 'html.parser')
    
    data_dict = {}
    
    # 解析开店要求
    requirements_section = soup.find('div', {'class': 'index_requirements__c1LD8'})
    if requirements_section and requirements_section.find('h4').text == '开店要求':
        requirements = []
        for li in requirements_section.find_all('li'):
            text = li.get_text().strip()
            if text:
                requirements.append(text)
        data_dict['开店要求'] = requirements

    # 解析开店福利  
    benefits_sections = soup.find_all('div', {'class': 'index_requirements__c1LD8'})
    for section in benefits_sections:
        if section.find('h4') and section.find('h4').text == '开店福利':
            benefits = []
            for li in section.find_all('li'):
                text = li.get_text().strip()
                if text:
                    benefits.append(text)
            data_dict['开店福利'] = benefits
            break

    # 解析平台概况
    platform_info = soup.find('section', {'id': 'marketplaceBackground'})
    if platform_info:
        info_dict = {}
        rows = platform_info.find_all('div', {'class': 'index_row__uPMiS'})
        for row in rows:
            title = row.find('div', {'class': 'index_rowTitle__0t3zy'})
            content = row.find('div', {'class': 'index_text__j9_LK'})
            if title and content:
                info_dict[title.text.strip()] = content.text.strip()
        data_dict['平台概况'] = info_dict

    # 解析结算收款
    settlement = soup.find('section', {'id': 'feesAndsettlement'})
    if settlement:
        settlement_dict = {}
        rows = settlement.find_all('div', {'class': 'index_row__uPMiS'})
        for row in rows:
            title = row.find('div', {'class': 'index_rowTitle__0t3zy'})
            content = row.find('div', {'class': 'index_text__j9_LK'})
            if title and content:
                settlement_dict[title.text.strip()] = content.text.strip()
            elif title and row.find('div', {'class': 'index_link__r4oo2'}):
                link = row.find('div', {'class': 'index_link__r4oo2'}).find('a')
                if link:
                    settlement_dict[title.text.strip()] = link.text.strip()
        data_dict['结算收款'] = settlement_dict

    # 解析平台物流
    logistics = soup.find('section', {'id': 'marketplaceLogistics'})
    if logistics:
        logistics_dict = {}
        rows = logistics.find_all('div', {'class': 'index_row__uPMiS'})
        for row in rows:
            title = row.find('div', {'class': 'index_rowTitle__0t3zy'})
            content = row.find('div', {'class': 'index_text__j9_LK'})
            if title and content:
                logistics_dict[title.text.strip()] = content.text.strip()
            elif title and row.find('div', {'class': 'index_link__r4oo2'}):
                link = row.find('div', {'class': 'index_link__r4oo2'}).find('a')
                if link:
                    logistics_dict[title.text.strip()] = link.text.strip()
        data_dict['平台物流'] = logistics_dict

    # 解析店铺运营
    operations = soup.find('section', {'id': 'shopOperations'})
    if operations:
        ops_dict = {}
        for card in operations.find_all('div', {'class': 'index_content__4eRwT'}):
            card_title = card.find('div', {'class': 'index_cardTitle__gugjj'})
            if card_title:
                card_dict = {}
                rows = card.find_all('div', {'class': 'index_row__uPMiS'})
                for row in rows:
                    title = row.find('div', {'class': 'index_rowTitle__0t3zy'})
                    content = row.find('div', {'class': 'index_text__j9_LK'})
                    if title and content:
                        card_dict[title.text.strip()] = content.text.strip()
                if card_dict:
                    ops_dict[card_title.text.strip()] = card_dict
        if ops_dict:
            data_dict['店铺运营'] = ops_dict

    return data_dict

def clear_greenchannel_payoneer_data(html_file,):
    """
    """
    dify_workflow_request = DifyWorkFlowRequest(api_key=GLOBAL_CONFIG.get('dify_api_key_payoneer_clear'), api_base=GLOBAL_CONFIG.get('dify_api_base'))
    data_dict, platform = get_green_channel_payonner_parse_data(html_file)
    es_qa_results = list()
    for key, value in data_dict.items():
        if key == '平台资料':
            print(f'has_platform_article_result: {platform}\t{value}')
            continue
        if not value:
            continue

        html_content = value.get('html_content', '')
        if not html_content:
            continue
        model_result = dify_workflow_request.request_dify(paragraph=html_content)
        clear_result, indexes = model_result.split('\n------\n')
        
        title = f'{platform}{key}'
        content = clear_result
        indexes = indexes.split('\n')
        indexes = filter(lambda x: len(x) > 5, indexes)
        qa_info = dict()
        qa_info['title'] = title
        qa_info['content'] = content
        qa_info['platform'] = "payoneer"
        qa_info['from_type'] = "html"
        qa_info['from_file_name'] = html_file
        qa_info['ecommerce_platform'] = platform
        qa_info['quality_level'] = "high"
        qa_info['indexes'] = [{'text': index} for index in indexes]
        es_qa_results.append(qa_info)
    
    return es_qa_results

def get_green_channel_payonner_parse_data(html_file):
    """
    解析绿色通道HTML文件中的特定元素并转换为字典格式
    
    Args:
        html_file: HTML文件路径
    
    Returns:
        tuple: (data_dict, platform)
            - data_dict: 包含解析结果的字典
            - platform: 平台名称
    """
    # 定义需要过滤的广告关键词
    products_words = [
        "点击右上方",
        "加入橄榄枝计划会员",
        "立即解锁",
        "购买会员",
        "更多资讯请",
    ]
    
    # 读取HTML文件
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    data_dict = {}
    platform = ''
    
    # 提取平台名称
    platform_name = soup.find('span', {'class': 'heading5'})
    if platform_name:
        platform = platform_name.text.strip()
    
    # 提取平台简介
    platform_desc = soup.find('textarea', {'id': 'TextArea_platform_description'})
    if platform_desc:
        html_content = platform_desc.decode_contents().strip()
        text_content = platform_desc.get_text().strip()
        data_dict['平台简介'] = {
            'html_content': html_content,
            'text_content': text_content
        }
    
    # 定义需要提取的标签和对应的ID
    sections = {
        '入驻介绍': '',
        '平台特点': '',
        '热卖品类': '',
        '平台数据': '',
        '回款周期': '',
    }
    
    def filter_ad_content(soup_element):
        """过滤广告内容"""
        if not soup_element:
            return None
        
        # 创建新的BeautifulSoup对象来存储过滤后的内容
        filtered_content = BeautifulSoup('', 'html.parser')
        
        for element in soup_element.children:
            if isinstance(element, str):
                if not any(word in element for word in products_words):
                    filtered_content.append(element)
            else:
                # 检查元素的文本内容
                element_text = element.get_text()
                if not any(word in element_text for word in products_words):
                    filtered_content.append(element)
        
        return filtered_content
    
    # 遍历并提取每个部分的内容
    for section_name, section_id in sections.items():
        section = soup.find('div', {'id': section_id})
        if section:
            # 提取HTML内容
            content_div = section.find('div', {'class': 'html-font'})
            if content_div:
                # 过滤广告内容
                filtered_div = filter_ad_content(content_div)
                if filtered_div:
                    html_content = str(filtered_div).strip()
                    text_content = filtered_div.get_text().strip()
                    
                    section_data = {
                        'html_content': html_content,
                        'text_content': text_content
                    }
                    data_dict[section_name] = section_data
    
    # 提取平台资料
    platform_files = []
    free_file_section = soup.find('div', {'id': 'FreeFile'})
    if free_file_section:
        file_list = free_file_section.find_all('div', {'class': 'columns3'})
        for file_item in file_list:
            file_info = {}
            
            # 提取文件名和下载链接
            file_link = file_item.find('a')
            if file_link:
                file_info['name'] = file_link.find('span').text.strip()
                file_info['url'] = file_link.get('href', '')
            
            # 提取文件大小
            size_column = file_item.find('div', {'id': lambda x: x and x.endswith('-Column2')})
            if size_column:
                file_info['size'] = size_column.text.strip()
            
            # 提取文件日期
            date_column = file_item.find('div', {'id': lambda x: x and x.endswith('-Column3')})
            if date_column:
                file_info['date'] = date_column.text.strip()
            
            if file_info:
                platform_files.append(file_info)
    
    if platform_files:
        data_dict['平台资料'] = platform_files
    
    return data_dict, platform

def clear_payonner_data(html_file):
    """
    解析Payoneer HTML文件中的特定元素并转换为字典格式
    
    Args:
        html_file: HTML文件路径
    
    Returns:
        dict: 包含解析结果的字典
    """
    # 读取HTML文件
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    data_dict = {}
    
    # 查找所有h2标签
    h2_tags = soup.find_all('h2')
    
    # 定义字段映射关系
    field_mapping = {
        '平台介绍': ['平台介绍', '平台简介', '关于平台'],
        '平台数据': ['平台数据', '平台规模', '平台概况'],
        '热卖品类': ['热卖品类', '主营品类', '主要品类'],
        '物流方式': ['物流方式', '配送方式', '物流服务'],
        '回款周期': ['回款周期', '结算周期', '付款方式'],
        '入驻要求': ['入驻要求', '开店要求', '商家要求']
    }
    
    def extract_content(elements, field_type):
        """提取元素中的内容"""
        if not elements:
            return None
            
        if field_type == 'list':
            items = []
            for element in elements:
                if element.name in ['ul', 'ol']:
                    for li in element.find_all('li'):
                        text = li.get_text().strip()
                        if text:
                            items.append(text)
                elif element.name == 'p':
                    text = element.get_text().strip()
                    if text:
                        items.append(text)
            return items if items else None
            
        elif field_type == 'dict':
            items_dict = {}
            for element in elements:
                if element.name in ['ul', 'ol']:
                    for li in element.find_all('li'):
                        text = li.get_text().strip()
                        if ':' in text or '：' in text:
                            key, value = text.replace('：', ':').split(':', 1)
                            items_dict[key.strip()] = value.strip()
                        else:
                            items_dict[text] = text
                elif element.name == 'p':
                    text = element.get_text().strip()
                    if ':' in text or '：' in text:
                        key, value = text.replace('：', ':').split(':', 1)
                        items_dict[key.strip()] = value.strip()
                    else:
                        items_dict[text] = text
            return items_dict if items_dict else None
            
        else:  # text
            texts = []
            for element in elements:
                if element.name in ['ul', 'ol']:
                    for li in element.find_all('li'):
                        text = li.get_text().strip()
                        if text:
                            texts.append(text)
                elif element.name == 'p':
                    text = element.get_text().strip()
                    if text:
                        texts.append(text)
            return ' '.join(texts) if texts else None

    # 遍历h2标签
    for i, h2 in enumerate(h2_tags):
        h2_text = h2.get_text().strip()
        
        # 确定当前h2对应的字段
        current_field = None
        for field, patterns in field_mapping.items():
            if any(pattern in h2_text for pattern in patterns):
                current_field = field
                break
        
        if not current_field:
            continue
            
        # 获取当前h2到下一个h2之间的所有元素
        content_elements = []
        current = h2.find_next_sibling()
        
        # 如果是最后一个h2
        if i == len(h2_tags) - 1:
            # 获取到父div的结尾
            parent_div = h2.find_parent('div')
            if parent_div:
                while current and current != parent_div:
                    if current.name in ['p', 'ul', 'ol', 'div']:
                        content_elements.append(current)
                    current = current.find_next_sibling()
        else:
            # 获取到下一个h2之前的元素
            next_h2 = h2_tags[i + 1]
            while current and current != next_h2:
                if current.name in ['p', 'ul', 'ol', 'div']:
                    content_elements.append(current)
                current = current.find_next_sibling()
        
        # 确定字段类型
        field_type = 'list' if current_field in ['入驻要求'] else \
                    'dict' if current_field in ['平台数据', '物流方式', '回款周期'] else \
                    'text'
        
        # 提取内容
        content = extract_content(content_elements, field_type)
        if content:
            data_dict[current_field] = content
    
    # 如果平台介绍还没有找到,尝试从meta description获取
    if '平台介绍' not in data_dict:
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc:
            intro_text = meta_desc.get('content', '').strip()
            if intro_text:
                data_dict['平台介绍'] = intro_text
    
    return data_dict

def run_batch_clear_html_wordlist_and_payonner_data(data_file, html_file_field):
    """
    """
    with open(data_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            fields = line.split('\t')
            html_file = fields[html_file_field]
            html_url = fields[1]
            try:
                if 'marketplace=' in html_url:
                    platfrom = html_url.split('marketplace=')[-1]
                    data_dict = clear_wordlist_data(html_file)
                    print(f'{platfrom}\twordlist\t{json.dumps(data_dict, ensure_ascii=False)}\t{line}')
                elif 'greenchannel.payoneer' in html_url:
                    datas = clear_greenchannel_payoneer_data(html_file)
                    #print(f'{platfrom}\tgreenchannel\t{json.dumps(data_dict, ensure_ascii=False)}\t{line}')
                    for data in datas:
                        print(json.dumps(data, ensure_ascii=False))
                elif 'payoneer' in html_url:
                    data_dict = clear_payonner_data(html_file)
                    platfrom = html_url.strip('/').split('/')[-1]
                    print(f'{platfrom}\tpayoneer\t{json.dumps(data_dict, ensure_ascii=False)}\t{line}')
            except Exception as e:
                tb = traceback.format_exc()
                logging.error(f'{tb}')
                logging.error(f'error line:  {line}')
                exit(1)



def trans_level_dict_to_str(data_dict):
    """
    """
    result_str = ''
    if isinstance(data_dict, str):
        return data_dict
    if isinstance(data_dict, list):
        result_str = '\n'.join(data_dict)
        return result_str
    
    for key, value in data_dict.items():
        if not isinstance(value, dict):
            if isinstance(value, list) and value:
                joined_values = '\n'.join(value)
                result_str = f'{result_str}{key}:{joined_values}\n'
            elif isinstance(value, str) and value and value not in ['无', '-']:
                result_str = f'{result_str}{key}:{value}\n'
            else:
                result_str += trans_level_dict_to_str(value)
    result_str = result_str.strip()
    return result_str

def load_payonner_data(data_file):
    """
    """
    platform_data_dict = dict()
    with open(data_file, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                line = line.strip()
                fields = line.split('\t')
                if fields[1] != 'payoneer':
                    continue

                platform = fields[0]
                if platform == "seller-green-channel":
                    continue
                
                # 清理所有可能的零宽空格形式
                fields[2] = fields[2].replace('<200b>', '')\
                                   .replace('\u200b', '')\
                                   .replace('&#8203;', '')\
                                   .replace('&zwsp;', '')
                
                data_json = json.loads(fields[2])
                new_dict = dict()
                new_dict['开店要求'] = trans_level_dict_to_str(data_json['入驻要求'])
                new_dict['平台介绍'] = trans_level_dict_to_str(data_json['平台介绍'])
                new_dict['平台物流'] = trans_level_dict_to_str(data_json.get('物流方式', ''))
                new_dict['platform'] = platform
                platform_data_dict[platform.lower()] = new_dict
            except:
                tb = traceback.format_exc()
                logging.error(f'{tb}')
                logging.error(f'error line:  {line}')
                exit(1)
    return platform_data_dict
            

def load_wordlist_data(data_file):
    """
    """
    platform_data_dict = dict()
    with open(data_file, 'r', encoding='utf-8') as f:        
        for line in f:
            try:
                line = line.strip()
                fields = line.split('\t')
                if fields[1] != 'wordlist':
                    continue
                platform = fields[0]
                data_json = json.loads(fields[2])
                new_dict = dict()
                if '开店要求' not in data_json:
                    logging.error('not contan 开店要求 %s', line)
                    continue
                new_dict['开店要求'] = trans_level_dict_to_str(data_json['开店要求'])
                if '万里汇' in new_dict['开店要求']:
                    new_dict['开店要求'] = ''
                new_dict['平台介绍'] = trans_level_dict_to_str(data_json['平台概况'])
                new_dict['平台物流'] = trans_level_dict_to_str(data_json.get('平台物流', ''))
                new_dict['platform'] = platform
                platform_data_dict[platform.lower()] = new_dict
            except:
                tb = traceback.format_exc()
                logging.error(f'{tb}')
                logging.error(f'error line:  {line}')
                exit(1)
    return platform_data_dict
            

def merge_payonner_and_wordlist_data(payonner_data_file, wordlist_data_file):
    """
    """
    payonner_data_dict = load_payonner_data(payonner_data_file)
    wordlist_data_dict = load_wordlist_data(wordlist_data_file)
    all_platforms = set(payonner_data_dict.keys()) | set(wordlist_data_dict.keys())
    merge_fields = ['开店要求', '平台介绍', '平台物流']
    title_map = {
        '开店要求': '开店要求',
        '平台介绍': '平台介绍',
        '平台物流': '平台物流介绍'
    }
    for platfrom in all_platforms:
        
        
        wordlist_dict  = wordlist_data_dict.get(platfrom, {})
        payonner_dict = payonner_data_dict.get(platfrom, {})
        platform_show = payonner_dict.get('platform') if payonner_dict else wordlist_dict.get('platform')
        for name in merge_fields:
            knowledge_info_dict = dict()
            payonner_value = payonner_dict.get(name)
            wordlist_value = wordlist_dict.get(name)
            final_value = payonner_value if payonner_value else wordlist_value
            
            title = f'{platform_show} {title_map.get(name)}'
            if not final_value or final_value in ['-', '无', '无无']:
                continue
            knowledge_info_dict['title'] = title
            knowledge_info_dict['content'] = final_value
            knowledge_info_dict['platform'] = platform_show
            
            print(json.dumps(knowledge_info_dict, ensure_ascii=False))
        
    

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()
   
