import sys
from kdb.mining.web.processing.mercado import extract_knowledge_hub_children
from kdb.mining.web.processing.mercado import is_knowledge_hub_url
import logging
from bs4 import BeautifulSoup
import os
import json
import requests
from urllib.parse import urljoin
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import fire
from collections import deque
from kdb.shared.clients.firecrawl_tools import fetch_firecrawl_content

class WebBatchCrawler:
    def __init__(self, output_dir, auth_config=None, browser_enabled=True):
        """
        初始化WebBatchCrawler
        
        Args:
            output_dir: 输出目录
            auth_config: 认证配置字典，可包含以下字段:
                - cookie: cookie字符串
                - user_agent: 自定义User-Agent
                - referer: Referer头
                - headers: 其他自定义headers字典
                - domain: cookie所属的域名（用于设置cookie）
        """
        self.output_dir = output_dir
        self.auth_config = auth_config or {}
        self.driver = self.setup_driver() if browser_enabled else None
        self.processed_urls = set()

    def setup_driver(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument('--log-level=3')
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--headless")
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        # 设置自定义User-Agent
        user_agent = self.auth_config.get('user_agent')
        if user_agent:
            options.add_argument(f'--user-agent={user_agent}')
        else:
            # 默认使用一个常见的User-Agent
            options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36')
        
        service = Service('/usr/local/bin/chromedriver')
        driver = webdriver.Chrome(options=options, service=service)
        try:
            page_load_timeout = float(self.auth_config.get('page_load_timeout', 30))
        except (TypeError, ValueError):
            page_load_timeout = 30
        driver.set_page_load_timeout(max(1, page_load_timeout))
        
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return driver
    
    def set_cookies_for_domain(self, url):
        """
        为指定URL的域名设置cookie
        
        Args:
            url: 目标URL，用于提取域名并设置cookie
        """
        cookie_str = self.auth_config.get('cookie')
        if not cookie_str:
            return
        
        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        domain = parsed_url.netloc
        
        # 先访问目标域名（selenium需要先访问域名才能设置该域名的cookie）
        # 访问一个简单的页面来初始化域名
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        try:
            self.driver.get(base_url)
            time.sleep(1)
        except Exception as e:
            logging.warning(f"Failed to load base URL {base_url}: {e}")
        
        # 删除现有的cookies
        self.driver.delete_all_cookies()
        
        # 解析cookie字符串并添加cookies
        cookies = self._parse_cookie_string(cookie_str)
        for cookie in cookies:
            try:
                cookie_dict = {
                    'name': cookie['name'],
                    'value': cookie['value'],
                    'domain': domain if not domain.startswith('.') else domain,
                }
                self.driver.add_cookie(cookie_dict)
                logging.debug(f"Added cookie: {cookie['name']}")
            except Exception as e:
                logging.warning(f"Failed to add cookie {cookie['name']}: {e}")
    
    def _parse_cookie_string(self, cookie_str):
        """
        解析cookie字符串为cookie列表
        
        Args:
            cookie_str: 如 "key1=value1; key2=value2" 格式的cookie字符串
            
        Returns:
            列表，每个元素为 {'name': key, 'value': value}
        """
        cookies = []
        if not cookie_str:
            return cookies
        
        pairs = cookie_str.split(';')
        for pair in pairs:
            pair = pair.strip()
            if '=' in pair:
                # 只在第一个=处分割，因为value中可能包含=
                idx = pair.index('=')
                name = pair[:idx].strip()
                value = pair[idx+1:].strip()
                if name:
                    cookies.append({'name': name, 'value': value})
        
        return cookies

    def safe_get(self, url, max_retries=3):
        if self.driver is None:
            raise RuntimeError("Browser rendering is disabled for this crawler")

        # 如果有cookie配置且尚未设置cookies，先设置cookies
        if self.auth_config.get('cookie') and not getattr(self, '_cookies_set', False):
            self.set_cookies_for_domain(url)
            self._cookies_set = True
        
        for attempt in range(max_retries):
            try:
                self.driver.get(url)
                time.sleep(5)
                
                self.driver.execute_script("return document.readyState") == "complete"
                
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                
                return self.driver.page_source
            except (TimeoutException, WebDriverException) as e:
                if isinstance(e, TimeoutException):
                    logging.warning(f"Page load timed out for {url}; stopping the browser load")
                    try:
                        self.driver.execute_script("window.stop();")
                        html_content = self.driver.page_source
                        if html_content and html_content.strip():
                            return html_content
                    except WebDriverException:
                        pass
                logging.warning(f"WebDriverException on attempt {attempt + 1}: {str(e)}")
                if attempt < max_retries - 1:
                    if self.driver:
                        self.driver.quit()
                    self.driver = self.setup_driver()
                    # 重新设置cookies
                    if self.auth_config.get('cookie'):
                        self.set_cookies_for_domain(url)
                    time.sleep(2)
                else:
                    raise

    def fetch_html_without_browser(self, url):
        headers = dict(self.auth_config.get('headers') or {})
        headers.setdefault(
            'User-Agent',
            self.auth_config.get('user_agent')
            or 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
               'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36')
        if self.auth_config.get('cookie'):
            headers.setdefault('Cookie', self.auth_config['cookie'])
        if self.auth_config.get('referer'):
            headers.setdefault('Referer', self.auth_config['referer'])
        try:
            timeout = float(self.auth_config.get('http_timeout', 30))
        except (TypeError, ValueError):
            timeout = 30
        response = requests.get(url, headers=headers, timeout=max(1, timeout))
        response.raise_for_status()
        return response.text

    @staticmethod
    def get_filename_from_url(url, keep_attr_name=None):
        from urllib.parse import urlparse
        from urllib.parse import parse_qs
        logging.info(f"url: {url}, keep_attr_name: {keep_attr_name}")
        # 解析URL
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.replace('.', '_')
        path = parsed_url.path.strip('/').replace('/', '_')
        
        # 处理查询参数
        if keep_attr_name and parsed_url.query:
            query_params = parse_qs(parsed_url.query)
            kept_params = []
            for param_name, param_values in query_params.items():
                if keep_attr_name == "all" or any(attr in param_name.lower() for attr in keep_attr_name):
                    kept_params.append(f"{param_name}_{param_values[0]}")
            
            if kept_params:
                path = f"{path}_{'_'.join(kept_params)}"
        
        filename = f"{domain}_{path}"
        filename = ''.join(c for c in filename if c.isalnum() or c in ['_', '-'])
        return filename if filename else 'index'

    def get_html_content_type(self, url, root_content_type):
        # 当前版本直接返回根链接的content_type
        return root_content_type

    def extract_formatted_text(self, html_file):
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 移除所有script标签
        for script in soup.find_all('script'):
            script.decompose()
            
        body = soup.find('body')
        
        if not body:
            return ""
        
        def format_element(element):
            text_parts = []
            elements_queue = deque([(element, 0)])  # (element, level)
            
            while elements_queue:
                current_element, level = elements_queue.popleft()


                #处理文本节点

                # 处理表格元素
                if current_element.name == 'table':                    
                    formatted_table = str(current_element)
                    text_parts.append("  " * level + formatted_table)
                    continue
                
                if hasattr(current_element, 'children'):
                    children = list(current_element.children)
                    if len(children) == 1 and isinstance(children[0], str):
                        text = str(current_element)
                        if text:
                            text_parts.append("  " * level + text)
                        continue
                
                if isinstance(current_element, str):
                    text = current_element.strip()
                    if text:
                       text_parts.append("  " * level + text)
                    continue
                
                # 处理其他元素节点
                if hasattr(current_element, 'children'):
                    # 将子元素加入队列
                    for child in current_element.children:
                        elements_queue.append((child, level + 1))
            logging.info(f'html 文本{str(element)} \n格式化后文本: {text_parts}')
            return "\n".join(text_parts)
        
        return format_element(body)

    @staticmethod
    def extract_formatted_text_by_flat(html_file):
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 移除所有script标签
        for script in soup.find_all('script'):
            script.decompose()
        
        # 清理非必要属性
        for tag in soup.find_all():
            attrs = dict(tag.attrs)  # 创建属性的副本
            for attr in attrs:
                # 只保留href和src属性
                if attr not in ['href', 'src']:
                    del tag.attrs[attr]
        
        body = soup.find('body')
        
        if not body:
            return ""
        
        # 获取body的直接子元素
        children = list(body.children)
        text_parts = []
        
        for child in children:
            # 跳过纯空白文本节点
            if isinstance(child, str) and not child.strip():
                continue
                
            # 对每个子元素进行格式化
            if hasattr(child, 'prettify'):
                text = child.prettify()
            else:
                text = str(child)
                
            if text.strip():  # 只添加非空内容
                text_parts.append(text)
        
        # 使用分隔符连接所有直接子元素
        return '\n--------\n'.join(text_parts)

    def process_crawl_url(self, url, platform, content_type, crawler_degree, keywords, keep_attr_name=None, current_depth=1, limit_page_numbs=None, use_firecrawl=False, firecrawl_only=False):
        if firecrawl_only and (not use_firecrawl or crawler_degree != 1):
            raise ValueError("firecrawl_only requires use_firecrawl=true and crawler_degree=1")

        results = []
        filename_dict = {}
        # 使用队列存储待处理的URL和深度
        url_queue = deque([(url, current_depth)])
        craled_nums = 0
        while url_queue:
            current_url, depth = url_queue.popleft()
            
            if current_url in self.processed_urls or depth > crawler_degree:
                logging.info(f"Crawled {craled_nums} pages, current url: {current_url}, reached the limit {crawler_degree}, stop crawling")
                continue
                
            self.processed_urls.add(current_url)
            craled_nums += 1
            logging.info(f"Crawled {craled_nums} pages, current url: {current_url}")
            if limit_page_numbs and len(filename_dict) >= limit_page_numbs:
                logging.info(f"Crawled {craled_nums} pages, unique url limit {len(filename_dict)} reached the limit {limit_page_numbs}, stop crawling")
                break
            try:
                # 生成文件名并检查文件是否存在
                filename = self.get_filename_from_url(current_url, keep_attr_name=keep_attr_name)
                html_local_file = os.path.join(self.output_dir, f"{filename}.html")
                
                if filename in filename_dict:
                    logging.info(f"HTML file already exists for URL {current_url}, save in {filename} skipping crawl")
                    continue
                else:
                    filename_dict[filename] = 1
                    
                # 检查HTML文件是否已存在
                firecrawl_content_file = None
                firecrawl_content = None
                if use_firecrawl:
                    firecrawl_content_file = os.path.join(self.output_dir, f"{filename}.firecrawl.txt")
                    if os.path.exists(firecrawl_content_file):
                        with open(firecrawl_content_file, 'r', encoding='utf-8') as f:
                            firecrawl_content = f.read()
                    if firecrawl_only and not firecrawl_content:
                        firecrawl_content = fetch_firecrawl_content(
                            current_url,
                            cookie=self.auth_config.get('cookie'),
                            user_agent=self.auth_config.get('user_agent'),
                            wait_for=self.auth_config.get('firecrawl_wait_for', 0))
                        if not firecrawl_content:
                            raise RuntimeError(f"firecrawl 未取到正文: {current_url}")

                if os.path.exists(html_local_file):
                    logging.info(f"HTML file already exists for URL {current_url}, skipping crawl")
                    with open(html_local_file, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                else:
                    if firecrawl_only:
                        try:
                            html_content = self.fetch_html_without_browser(current_url)
                        except requests.RequestException as e:
                            logging.warning(f"HTTP HTML fallback failed for {current_url}: {e}")
                            html_content = '<!doctype html><html><body></body></html>'
                    else:
                        html_content = self.safe_get(current_url)
                    with open(html_local_file, 'w', encoding='utf-8') as f:
                        f.write(html_content)
                    logging.info(f"Crawled and saved new HTML file for URL {current_url}")
                if use_firecrawl:
                    if not firecrawl_content:
                        # 直连 Firecrawl（原 Dify 插件 headers 已坏，cookie 传不进去），
                        # 把 auth_config 的 cookie/UA 一并透传，多语言站点靠它切语言
                        firecrawl_content = fetch_firecrawl_content(
                            current_url,
                            cookie=self.auth_config.get('cookie'),
                            user_agent=self.auth_config.get('user_agent'),
                            wait_for=self.auth_config.get('firecrawl_wait_for', 0))
                    # 空正文别写盘：写了会被当成"已抓过"缓存住，下游拿到空内容整页静默跳过
                    if firecrawl_content:
                        with open(firecrawl_content_file, 'w', encoding='utf-8') as f:
                            f.write(firecrawl_content)
                    else:
                        logging.warning(f"firecrawl 未取到正文，不写空文件: {current_url}")
                    
    

                # 记录当前URL的信息
                current_info = {
                    'platform': platform,
                    'crawl_url': current_url,
                    'content_type': content_type,
                    'crawler_degree': crawler_degree,
                    'html_local_file': html_local_file
                }
                if use_firecrawl:
                    current_info['firecrawl_content_file'] = firecrawl_content_file
                results.append(current_info)

                # 解析子链接
                if depth < crawler_degree:
                    soup = BeautifulSoup(html_content, 'html.parser')
                    for link in soup.find_all('a', href=True):
                        href = link['href']
                        if not href.startswith(('http://', 'https://')):
                            # 获取当前URL的根域名
                            from urllib.parse import urlparse
                            parsed_current = urlparse(current_url)
                            base_url = f"{parsed_current.scheme}://{parsed_current.netloc}"
                            
                            # 如果href以/开头，使用根域名拼接
                            if href.startswith('/'):
                                href = urljoin(base_url, href)
                            else:
                                # 对于相对路径，使用完整的current_url拼接
                                href = urljoin(current_url, href)
                        
                        link_text = link.get_text(strip=True)
                        
                        # 检查URL或文本是否匹配关键词，keywords为空时不过滤，所有子链接都入队
                        if not keywords or any(keyword in href.lower() or keyword in link_text.lower() 
                              for keyword in keywords):
                            # 将新的URL添加到队列中
                            url_queue.append((href, depth + 1))
                    
                    # 特殊处理：仅 knowledge-hub 页面从嵌入式 JSON 状态中提取子链接
                    if is_knowledge_hub_url(current_url):
                        kb_children = extract_knowledge_hub_children(html_content, current_url)
                        for child in kb_children:
                            child_url = child['url']
                            child_title = child.get('title', '')
                            # 检查URL或标题是否匹配关键词
                            if not keywords or any(keyword in child_url.lower() or keyword in child_title.lower()
                                  for keyword in keywords):
                                url_queue.append((child_url, depth + 1))

            except Exception as e:
                logging.error(f"Error processing URL {current_url}: {str(e)}")

        return results

def crawl_batch_urls(input_file, output_dir, flag=''):
    """第一阶段：批量爬取网页"""
    logging.info(f"Running batch crawler with input file: {input_file} and output directory: {output_dir}")
    os.makedirs(output_dir, exist_ok=True)
    crawler = WebBatchCrawler(output_dir)
    
    # 创建输出文件
    crawler_url_info_file = os.path.join(output_dir, f"crawler_url_info_{flag}.txt")
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f, open(crawler_url_info_file, 'w', encoding='utf-8') as out:
            for line in f:
                fields = line.strip().split('\t')
                if len(fields) == 5:
                    platform, crawl_url, content_type, crawler_degree, keywords_str = fields
                    limit_page_numbs = None
                elif len(fields) == 6:
                    platform, crawl_url, content_type, crawler_degree, keywords_str, limit_page_numbs = fields
                else:
                    raise ValueError(f"Invalid line format: {line}")
                if '|' in keywords_str:
                    keywords_str, keep_attr_name = keywords_str.split('|')
                    keep_attr_name = keep_attr_name.strip().split(',')
                    keep_attr_name = [k.strip().lower() for k in keep_attr_name]
                else:
                    keep_attr_name = None
                logging.info(f"url: {crawl_url}, keywords: {keywords_str}, keep_attr_name: {keep_attr_name}, limit_page_numbs: {limit_page_numbs}")
                limit_page_numbs = int(limit_page_numbs) if limit_page_numbs else None
                keywords = [k.strip().lower() for k in keywords_str.split(',')]
                crawler_degree = int(crawler_degree)
                
                results = crawler.process_crawl_url(
                    crawl_url, platform, content_type, crawler_degree, keywords, keep_attr_name, limit_page_numbs=limit_page_numbs
                )
                
                for result in results:
                    out.write(f"{result['platform']}\t{result['crawl_url']}\t"
                            f"{result['content_type']}\t{result['crawler_degree']}\t"
                            f"{result['html_local_file']}\n")
    finally:
        if crawler.driver:
            crawler.driver.quit()
    
    return crawler_url_info_file

def process_crawled_content(crawler_url_info_file, output_dir, flag=''):
    """第二阶段：处理已爬取的网页内容"""
    process_url_info_file = os.path.join(output_dir, f"crawler_and_process_results_{flag}.txt")
    crawler = WebBatchCrawler(output_dir)  # 仅用于文本提取功能
    
    with open(crawler_url_info_file, 'r', encoding='utf-8') as f, open(process_url_info_file, 'w', encoding='utf-8') as out_f:
        for line in f:
            platform, crawl_url, content_type, crawler_degree, html_local_file = line.strip().split('\t')
            
            # 读取HTML内容
            with open(html_local_file, 'r', encoding='utf-8') as html_f:
                html_content = html_f.read()
            
            # 获取格式化文本
            #formatted_text = crawler.extract_formatted_text(html_local_file)
            formatted_text = crawler.extract_formatted_text_by_flat(html_local_file)
            # 构建结果字典
            result_dict = {
                'platform': platform,
                'crawl_url': crawl_url,
                'content_type': content_type,
                'crawler_degree': int(crawler_degree),
                'html_local_file': html_local_file,
                'html_content': html_content,
                'formatted_text': formatted_text
            }
            
            data_json_file = html_local_file.replace('.html', '.json')
            with open(data_json_file, 'w', encoding='utf-8') as f:
                json.dump(result_dict, f, ensure_ascii=False, indent=4)
            
            print_field = [platform, crawl_url, content_type, crawler_degree, html_local_file, data_json_file]
            out_f.write('\t'.join(map(str, print_field)) + '\n')
    
    return process_url_info_file


def run_batch_crawler(input_file, output_dir, flag=''):
    """保持原有接口，但内部分两阶段执行"""
    crawler_url_info_file = crawl_batch_urls(input_file, output_dir, flag)
    process_url_info_file = process_crawled_content(crawler_url_info_file, output_dir, flag)
    return process_url_info_file

def run_crawl_task_info(task_id, task_info, output_file):
    """
    根据task_info参数批量爬取网页
    
    Args:
        task_id: 任务ID
        task_info: JSON格式的任务信息，包含：
            - url_infos: 数组，每个元素包含 url, content_type, crawler_degree, keywords, keep_attr_name, limit_page_num
            - client: 平台名称 (platform)
            - index_name: 索引名称
            - is_use_firecrawl: 是否使用firecrawl
            - auth_config: 可选，认证配置，包含:
                - cookie: cookie字符串
                - user_agent: 自定义User-Agent
        output_file: 输出文件路径，每行为一个JSON格式的结果
    
    Example:
        task_info = {
            "url_infos": [
                {
                    "url": "https://example.com/page1",
                    "content_type": "normal",
                    "crawler_degree": 2,
                    "keywords": "product,detail,info",
                    "keep_attr_name": "id,class",
                    "limit_page_num": 10
                },
                {
                    "url": "https://example.com/page2",
                    "content_type": "qa",
                    "crawler_degree": 1,
                    "keywords": "article,blog",
                    "keep_attr_name": None,
                    "limit_page_num": 5
                }
            ],
            "client": "example_platform",
            "index_name": "example_index",
            "is_use_firecrawl": false,
            "auth_config": {
                "cookie": "key1=value1; key2=value2",
                "user_agent": "Mozilla/5.0 ..."
            }
        }
    """
    # 解析task_info
    if isinstance(task_info, str):
        task_info = json.loads(task_info)
    
    # 提取任务信息
    url_infos = task_info.get('url_infos', [])
    platform = task_info.get('client', '')
    client = task_info.get('client', '')
    index_name = task_info.get('index_name', '')
    is_use_firecrawl = task_info.get('is_use_firecrawl', False)
    firecrawl_only = task_info.get('firecrawl_only', False)
    auth_config = task_info.get('auth_config', None)

    if firecrawl_only:
        if not is_use_firecrawl:
            raise ValueError("firecrawl_only requires is_use_firecrawl=true")
        invalid_depth_urls = [
            info.get('url', '') for info in url_infos
            if int(info.get('crawler_degree', 1)) != 1
        ]
        if invalid_depth_urls:
            raise ValueError(
                "firecrawl_only supports explicit depth-1 URLs only: "
                + ", ".join(invalid_depth_urls[:3]))
    
    # 创建输出目录
    output_dir = os.path.dirname(os.path.abspath(output_file))
    if not output_dir:
        output_dir = './output'
    os.makedirs(output_dir, exist_ok=True)
    
    # 初始化爬虫（如果有auth_config则使用）
    crawler = WebBatchCrawler(
        output_dir,
        auth_config=auth_config,
        browser_enabled=not firecrawl_only)
    
    if auth_config:
        logging.info(f"Using auth_config for crawling: cookie={'[SET]' if auth_config.get('cookie') else '[NOT SET]'}, user_agent={'[SET]' if auth_config.get('user_agent') else '[DEFAULT]'}")
    
    try:
        with open(output_file, 'w', encoding='utf-8') as out:
            # 遍历每个URL信息
            for url_info in url_infos:
                url = url_info.get('url', '')
                content_type = url_info.get('content_type', '')
                crawler_degree = int(url_info.get('crawler_degree', 1))
                keywords_str = url_info.get('keywords', '')
                keep_attr_name = url_info.get('keep_attr_name', None)
                limit_page_numbs = url_info.get('limit_page_num', None)
                
                # 处理keywords
                if isinstance(keywords_str, str):
                    keywords = [k.strip().lower() for k in keywords_str.split(',') if k.strip()]
                elif isinstance(keywords_str, list):
                    keywords = [str(k).strip().lower() for k in keywords_str if k]
                else:
                    keywords = []
                
                # 处理keep_attr_name
                if isinstance(keep_attr_name, str):
                    keep_attr_name = [k.strip().lower() for k in keep_attr_name.split(',') if k.strip()]
                elif not isinstance(keep_attr_name, list):
                    keep_attr_name = None
                
                # 处理limit_page_numbs
                if limit_page_numbs:
                    try:
                        limit_page_numbs = int(limit_page_numbs)
                    except (ValueError, TypeError):
                        limit_page_numbs = None
                else:
                    limit_page_numbs = None
                
                logging.info(f"Processing URL: {url}, platform: {platform}, content_type: {content_type}, "
                            f"crawler_degree: {crawler_degree}, keywords: {keywords}, "
                            f"keep_attr_name: {keep_attr_name}, limit_page_num: {limit_page_numbs}")
                
                # 调用爬取方法
                results = crawler.process_crawl_url(
                    url, platform, content_type, crawler_degree, keywords, 
                    keep_attr_name=keep_attr_name, 
                    limit_page_numbs=limit_page_numbs,
                    use_firecrawl=is_use_firecrawl,
                    firecrawl_only=firecrawl_only
                )
                category_id = url_info.get('category_id', '')
                category_name = url_info.get('category_name', '')
                # 将每个结果写入输出文件（每行一个JSON）
                for result in results:
                    # 构建输出JSON，包含task_id和index_name
                    result['task_id'] = task_id
                    result['index_name'] = index_name
                    result['original_url'] = url # 起始URL
                    result['client'] = client
                    if category_id:
                        result['category_id'] = category_id
                    if category_name:
                        result['category_name'] = category_name
                    out.write(json.dumps(result, ensure_ascii=False) + '\n')
                    
    finally:
        if crawler.driver:
            crawler.driver.quit()
    
    logging.info(f"Crawl task {task_id} completed, results saved to {output_file}")
    return output_file


def process_crawled_content_json_format(input_file, output_dir, flag=''):
    """
    第二阶段：处理已爬取的网页内容（JSON格式输入）
    
    Args:
        input_file: 输入文件路径，run_crawl_task_info中产出的JSON格式文件（每行一个JSON）
        output_dir: 输出目录
        flag: 标志(task_id)
    
    Returns:
        process_url_info_file: 处理后的结果文件路径（TSV格式）
    """
    process_url_info_file = os.path.join(output_dir, f"crawler_and_process_results_{flag}.txt")
    with open(input_file, 'r', encoding='utf-8') as f, open(process_url_info_file, 'w', encoding='utf-8') as out_f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            # 解析JSON行
            try:
                result_data = json.loads(line)
            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse JSON line: {line}, error: {str(e)}")
                continue
            
            # 提取字段
            platform = result_data.get('platform', '')
            client = result_data.get('client', '')
            crawl_url = result_data.get('crawl_url', '')
            content_type = result_data.get('content_type', '')
            crawler_degree = result_data.get('crawler_degree', 1)
            html_local_file = result_data.get('html_local_file', '')
            task_id = result_data.get('task_id', '')
            index_name = result_data.get('index_name', '')
            firecrawl_content_file = result_data.get('firecrawl_content_file', None)
            original_url = result_data.get('original_url', '')
            category_id = result_data.get('category_id', '')
            category_name = result_data.get('category_name', '')
            
            
            if not html_local_file or not os.path.exists(html_local_file):
                logging.warning(f"HTML file not found: {html_local_file}, skipping")
                continue
            
            # 读取HTML内容
            with open(html_local_file, 'r', encoding='utf-8') as html_f:
                html_content = html_f.read()
            
            # 获取格式化文本
            formatted_text = WebBatchCrawler.extract_formatted_text_by_flat(html_local_file)
            
            # 构建结果字典
            result_dict = {
                'platform': platform,
                'crawl_url': crawl_url,
                'content_type': content_type,
                'crawler_degree': int(crawler_degree),
                'html_local_file': html_local_file,
                'html_content': html_content,
                'formatted_text': formatted_text
            }
            
            # 如果存在task_id和index_name，添加到结果中
            if task_id:
                result_dict['task_id'] = task_id
            if index_name:
                result_dict['index_name'] = index_name
            if firecrawl_content_file:
                result_dict['firecrawl_content_file'] = firecrawl_content_file
                firecrawl_content = None
                with open(firecrawl_content_file, 'r', encoding='utf-8') as f:
                    firecrawl_content = f.read()
                if firecrawl_content:
                    result_dict['firecrawl_content'] = firecrawl_content
            if client:
                result_dict['client'] = client
            if original_url:
                result_dict['original_url'] = original_url
            if category_id:
                result_dict['category_id'] = category_id
            if category_name:
                result_dict['category_name'] = category_name
            # 保存JSON文件
            data_json_file = html_local_file.replace('.html', '.json')
            with open(data_json_file, 'w', encoding='utf-8') as json_f:
                json.dump(result_dict, json_f, ensure_ascii=False, indent=4)
            
            # 输出TSV格式（与process_crawled_content保持一致）
            print_field = [platform, crawl_url, content_type, crawler_degree, html_local_file, data_json_file]
            out_f.write('\t'.join(map(str, print_field)) + '\n')
    
    return process_url_info_file


def test_crawl(url, cookie=None, user_agent=None, referer=None, output_dir='./test_crawl_output', 
               wait_timeout=20, wait_for_text=None, wait_for_selector=None):
    """
    测试爬取需要登录的网页，使用显式等待确保JS渲染完成
    
    Args:
        url: 要爬取的URL
        cookie: cookie字符串，格式如 "key1=value1; key2=value2"
        user_agent: 自定义User-Agent字符串
        referer: Referer请求头
        output_dir: 输出目录，默认为 ./test_crawl_output
        wait_timeout: 等待超时时间（秒），默认20秒
        wait_for_text: 等待包含此文本的元素出现（用于判断页面加载完成）
        wait_for_selector: 等待此CSS选择器匹配的元素出现
    
    Returns:
        爬取结果信息字典
    
    Example:
        # 使用文本等待
        python -m kdb.mining.web.crawlers.batch test_crawl \\
            --url="https://global-selling.mercadolibre.com/help/allowed-listing-prices_22799" \\
            --cookie="your_cookie_string_here" \\
            --referer="https://global-selling.mercadolibre.com/help/16616" \\
            --wait_for_text="What can we help you with"
        
        # 使用CSS选择器等待
        python -m kdb.mining.web.crawlers.batch test_crawl \\
            --url="https://example.com" \\
            --wait_for_selector="div.content-loaded"
    """
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 构建认证配置
    auth_config = {}
    if cookie:
        auth_config['cookie'] = cookie
    if user_agent:
        auth_config['user_agent'] = user_agent
    else:
        # 使用默认的User-Agent
        auth_config['user_agent'] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
    if referer:
        auth_config['referer'] = referer
    
    logging.info(f"Starting test crawl for URL: {url}")
    logging.info(f"Auth config: cookie={'[SET]' if cookie else '[NOT SET]'}, user_agent={'[SET]' if user_agent else '[DEFAULT]'}, referer={'[SET]' if referer else '[NOT SET]'}")
    logging.info(f"Wait timeout: {wait_timeout}s, wait_for_text: {wait_for_text}, wait_for_selector: {wait_for_selector}")
    
    # 初始化爬虫（带认证配置）
    crawler = WebBatchCrawler(output_dir, auth_config=auth_config)
    
    try:
        # 如果有cookie配置，先设置cookies
        if auth_config.get('cookie'):
            crawler.set_cookies_for_domain(url)
            crawler._cookies_set = True
        
        # 使用CDP设置额外的HTTP头（如Referer）
        if referer:
            logging.info(f"Setting Referer header via CDP: {referer}")
            crawler.driver.execute_cdp_cmd('Network.enable', {})
            crawler.driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {
                'headers': {'Referer': referer}
            })
        
        # 访问目标URL
        crawler.driver.get(url)
        logging.info(f"Page loaded, using WebDriverWait for content...")
        
        # 创建WebDriverWait对象
        wait = WebDriverWait(crawler.driver, wait_timeout)
        
        # 使用显式等待来确保页面内容加载完成
        if wait_for_text:
            # 等待包含指定文本的元素出现
            logging.info(f"Waiting for element with text: '{wait_for_text}'")
            try:
                wait.until(EC.presence_of_element_located(
                    (By.XPATH, f"//*[contains(text(),'{wait_for_text}')]")
                ))
                logging.info(f"Found element with text: '{wait_for_text}'")
            except TimeoutException:
                logging.warning(f"Timeout waiting for text: '{wait_for_text}', continuing anyway...")
        
        if wait_for_selector:
            # 等待CSS选择器匹配的元素出现
            logging.info(f"Waiting for element matching selector: '{wait_for_selector}'")
            try:
                wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, wait_for_selector)
                ))
                logging.info(f"Found element matching selector: '{wait_for_selector}'")
            except TimeoutException:
                logging.warning(f"Timeout waiting for selector: '{wait_for_selector}', continuing anyway...")
        
        # 如果没有指定等待条件，使用默认等待策略
        if not wait_for_text and not wait_for_selector:
            logging.info("No specific wait condition, using default wait strategy...")
            # 等待页面完全加载
            try:
                wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
            except TimeoutException:
                logging.warning("Timeout waiting for document.readyState, continuing...")
            # 额外等待一下让JS执行
            time.sleep(3)
        
        # 滚动页面以触发懒加载
        crawler.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        # 再滚动回顶部
        crawler.driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        
        # 获取页面内容
        html_content = crawler.driver.page_source
        
        # 生成文件名
        filename = crawler.get_filename_from_url(url)
        html_file = os.path.join(output_dir, f"{filename}.html")
        
        # 保存HTML内容
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logging.info(f"Successfully crawled URL: {url}")
        logging.info(f"HTML saved to: {html_file}")
        logging.info(f"Content length: {len(html_content)} characters")
        
        result = {
            'success': True,
            'url': url,
            'html_file': html_file,
            'content_length': len(html_content)
        }
        
        print(f"\n{'='*60}")
        print(f"Test Crawl Result")
        print(f"{'='*60}")
        print(f"URL: {url}")
        print(f"Status: SUCCESS")
        print(f"Output File: {html_file}")
        print(f"Content Length: {len(html_content)} characters")
        print(f"{'='*60}\n")
        
        return result
        
    except Exception as e:
        logging.error(f"Failed to crawl URL: {url}, error: {str(e)}")
        result = {
            'success': False,
            'url': url,
            'error': str(e)
        }
        
        print(f"\n{'='*60}")
        print(f"Test Crawl Result")
        print(f"{'='*60}")
        print(f"URL: {url}")
        print(f"Status: FAILED")
        print(f"Error: {str(e)}")
        print(f"{'='*60}\n")
        
        return result
        
    finally:
        if crawler.driver:
            crawler.driver.quit()


if __name__ == "__main__":
    logging.basicConfig(
        stream=sys.stderr, 
        level=logging.INFO,
        format='[%(levelname)s] [%(asctime)s] [%(name)s] [%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
    )
    # 将整个类和新函数暴露给命令行
    fire.Fire({
        'run_batch_crawler': run_batch_crawler,
        'crawl_batch_urls': crawl_batch_urls,
        'process_crawled_content': process_crawled_content,
        'extract_text': lambda html_file: WebBatchCrawler("./output").extract_formatted_text(html_file),
        'extract_text_flat': lambda html_file: WebBatchCrawler("./output").extract_formatted_text_by_flat(html_file),
        'crawler': WebBatchCrawler,
        'process_crawled_content_json_format': process_crawled_content_json_format,
        'run_crawl_task_info': run_crawl_task_info,
        'test_crawl': test_crawl
    }) 
