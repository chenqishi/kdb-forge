import sys
import requests
import logging  
from bs4 import BeautifulSoup
import os
import json
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import WebDriverException
import time
from collections import deque
import urllib.parse
import fire

class WebDeepCrawler:
    def __init__(self, base_url, article_url_file, output_dir):
        self.base_url = base_url
        self.article_url_file = article_url_file
        self.output_dir = output_dir
        self.driver = self.setup_driver()
        self.processed_urls = set()  # 新添加的属性

    def setup_driver(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument('--log-level=3')
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        service = Service('/usr/local/bin/chromedriver')
        return webdriver.Chrome(options=options, service=service)

    def reset_driver(self):
        if self.driver:
            self.driver.quit()
        self.driver = self.setup_driver()

    def safe_get(self, url, max_retries=3):
        for attempt in range(max_retries):
            try:
                self.driver.get(url)
                self.wait_for_page_load()
                return
            except WebDriverException as e:
                logging.warning(f"WebDriverException on attempt {attempt + 1}: {str(e)}")
                if attempt < max_retries - 1:
                    self.reset_driver()
                    time.sleep(2)
                else:
                    raise

    def wait_for_page_load(self, timeout=30):
        try:
            # 等待页面加载完成
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            
            # 等待特定元素出现，这里假设页面加载完成后会有一个特的元素
            # 您需要根据实际网页结构调整这个选择器
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".some-specific-class"))
            )
            
            # 如果页面有 AJAX 加载，可以等待 jQuery 加载完成（如果网站使用 jQuery）
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script('return (typeof jQuery !== "undefined" && jQuery.active == 0)')
            )
        except TimeoutException:
            logging.warning(f"Page load timeout for URL: {self.driver.current_url}")

    def get_filename_from_url(self, url):
        # 解析URL
        parsed_url = urllib.parse.urlparse(url)
        # 获取域名和路径
        domain = parsed_url.netloc.replace('.', '')
        path = parsed_url.path.strip('/')
        # 组合域名和路径
        filename = f"{domain}_{path}"
        # 去除不规则符号
        filename = ''.join(c for c in filename if c.isalnum() or c in ['_', '-'])
        # 如果文件名为空，使用'index'
        if not filename:
            filename = 'index'
        return filename

    def crawl_topic(self, url, topic_road):
        url = self.get_full_url(url)  # 确保 URL 包含正确的语言参数
        topic_filename = self.get_filename_from_url(url)
        topic_path = os.path.join(self.output_dir, f"{topic_filename}.html")

        if os.path.exists(topic_path):
            logging.info(f"Loading topic page from local file: {topic_path}")
            with open(topic_path, 'r', encoding='utf-8') as f:
                topic_html = f.read()
        else:
            try:
                self.safe_get(url)
                topic_html = self.driver.page_source
                logging.info(f"Saving topic page: {url} {topic_filename}")
                with open(topic_path, 'w', encoding='utf-8') as f:
                    f.write(topic_html)
            except WebDriverException as e:
                logging.error(f"Failed to crawl topic {url}: {str(e)}")
                return []

        # 解析 HTML 内容
        soup = BeautifulSoup(topic_html, 'html.parser')
        
        # 爬取子主题和文章
        new_topics = []
        articles = []

        for link in soup.find_all('a', href=True):
            href = link['href']
            if '/topic/' in href:
                # 这是一个topic链接
                subtopic_title = self.extract_topic_title(link)
                subtopic_url = self.get_full_url(href)
                new_topic_road = topic_road + [subtopic_title]
                new_topics.append((subtopic_url, new_topic_road))
            elif '/article/' in href:
                # 这是一个article链接
                article_url = self.get_full_url(href)
                article_title = self.extract_article_title(link)
                articles.append((article_url, article_title))

        # 保存文章URL和标题
        with open(self.article_url_file, 'a', encoding='utf-8') as f:
            for article_url, article_title in articles:
                f.write(f"{'|'.join(topic_road)}\t{article_url}\t{article_title}\n")

        return new_topics

    def get_full_url(self, href):
        full_url = href if href.startswith('http') else urljoin(self.base_url, href)
        
        # 解析 URL
        parsed_url = urllib.parse.urlparse(full_url)
        
        # 获取现有的查询参数
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        # 添加或更新 language 参数
        query_params['language'] = ['en_US']
        
        # 重新构建查询字符串
        new_query = urllib.parse.urlencode(query_params, doseq=True)
        
        # 重新组合 URL
        new_url = urllib.parse.urlunparse((
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.params,
            new_query,
            parsed_url.fragment
        ))
        
        return new_url

    def crawl_all_topics(self):
        initial_url = self.get_full_url(self.base_url)
        topic_queue = deque([(initial_url, [])])

        while topic_queue:
            current_url, current_topic_road = topic_queue.popleft()
            
            if current_url in self.processed_urls:
                continue
            
            new_topics = self.crawl_topic(current_url, current_topic_road)
            self.processed_urls.add(current_url)
            
            for new_url, new_road in new_topics:
                if new_url not in self.processed_urls:
                    topic_queue.append((new_url, new_road))

        logging.info(f"Total processed topics: {len(self.processed_urls)}")

    def extract_article_title(self, link_element):
        # 获取所有文本节点
        text_nodes = link_element.find_all(text=True, recursive=False)
        
        # 过滤掉空白文本
        text_nodes = [node.strip() for node in text_nodes if node.strip()]
        
        if text_nodes:
            return ' '.join(text_nodes)
        
        # 如果没有直接的文本节点，尝试获取所有子元素的文本
        all_text = link_element.get_text(strip=True)
        return all_text if all_text else "NULL"

    def process_article(self, url, topic_roads, existing_title):
        url = self.get_full_url(url)  # 确保 URL 包含正确的语言参数
        filename = self.get_filename_from_url(url)
        raw_path = os.path.join(self.output_dir, f"{filename}.html")
        processed_path = os.path.join(self.output_dir, f"{filename}.json")

        if os.path.exists(raw_path):
            logging.info(f"Loading article from local file: {raw_path}")
            with open(raw_path, 'r', encoding='utf-8') as f:
                raw_content = f.read()
        else:
            try:
                self.safe_get(url)
                raw_content = self.driver.page_source
                with open(raw_path, 'w', encoding='utf-8') as f:
                    f.write(raw_content)
            except WebDriverException as e:
                logging.error(f"Failed to process article {url}: {str(e)}")
                return None

        # 重新处理 HTML 内容
        soup = BeautifulSoup(raw_content, 'html.parser')
        title = existing_title if existing_title.strip()  else soup.title.string if soup.title else "No Title"
        content = soup.get_text(strip=True)

        # 选择最长的 topic_road
        longest_topic_road = max(topic_roads, key=len)

        processed_content = {
            'title': title,
            'content': content,
            'topic_road': longest_topic_road
        }

        # 总是重新写入处理后的内容
        with open(processed_path, 'w', encoding='utf-8') as f:
            json.dump(processed_content, f, ensure_ascii=False, indent=2)

        return processed_content

    def save_content(self, url, raw_content, processed_content):
        filename = self.get_filename_from_url(url)
        
        raw_path = os.path.join(self.output_dir, f"{filename}.html")
        processed_path = os.path.join(self.output_dir, f"{filename}.json")
        
        with open(raw_path, 'w', encoding='utf-8') as f:
            f.write(raw_content)
        
        with open(processed_path, 'w', encoding='utf-8') as f:
            json.dump(processed_content, f, ensure_ascii=False, indent=2)
        
        return raw_path, processed_path

    def crawl_articles(self):
        output_file = os.path.join(self.output_dir, 'article_map.txt')
        
        # 创建一个字典来存储每个 URL 的所有 topic_roads
        article_topic_roads = {}
        exiting_title_map = {}
        # 首先收集所有的 topic_roads
        with open(self.article_url_file, 'r', encoding='utf-8') as f:
            for line in f:
                topic_road, url, existing_title = line.strip('\n').split('\t')
                if url not in article_topic_roads:
                    article_topic_roads[url] = []
                article_topic_roads[url].append(topic_road.split('|'))
                if existing_title.strip() and existing_title != 'NULL':
                    exiting_title_map[url] = existing_title

        # 然后处理每个文章
        with open(output_file, 'a+', encoding='utf-8') as out:
            for url, topic_roads in article_topic_roads.items():
                existing_title = exiting_title_map.get(url, '')
                processed_content = self.process_article(url, topic_roads, existing_title)
                raw_path = os.path.join(self.output_dir, f"{self.get_filename_from_url(url)}.html")
                processed_path = os.path.join(self.output_dir, f"{self.get_filename_from_url(url)}.json")
                out.write(f"{url}\t{raw_path}\t{processed_path}\t{processed_content['title']}\n")


    def extract_topic_title(self, link_element):
        # 获取所有文本节点
        text_nodes = link_element.find_all(text=True, recursive=False)
        
        # 过滤掉空白文本
        text_nodes = [node.strip() for node in text_nodes if node.strip()]
        
        if text_nodes:
            return ' '.join(text_nodes)
        
        # 如果没有直接的文本节点，尝试获取所有子元素的文本
        all_text = link_element.get_text(strip=True)
        return all_text if all_text else "No Title"

    def run_all(self):
        try:
            # 清空 article_url_file
            open(self.article_url_file, 'w').close()
            
            self.crawl_all_topics()
            self.crawl_articles()
        finally:
            if self.driver:
                self.driver.quit()

    def run_article(self):
        try:
            self.crawl_articles()
        finally:
            if self.driver:
                self.driver.quit()

def run_all(base_url, output_dir):
    article_url_file = f"{output_dir}/article_urls.txt"
    os.makedirs(output_dir, exist_ok=True)
    crawler = WebDeepCrawler(base_url, article_url_file, output_dir)
    crawler.run_all()

def run_article(base_url, output_dir):
    article_url_file = f"{output_dir}/article_urls.txt"
    os.makedirs(output_dir, exist_ok=True)
    crawler = WebDeepCrawler(base_url, article_url_file, output_dir)
    crawler.run_article()

if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')    
    fire.Fire({
        'run_all': run_all,
        'run_article': run_article
    })
