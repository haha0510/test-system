# -*- coding: utf-8 -*-
"""百度新闻数据抓取模块"""
import requests
from bs4 import BeautifulSoup, Comment
import re
import json
import random
import time


class BaiduNewsCrawler:
    """百度新闻爬虫"""

    BASE_URL = "https://www.baidu.com/s"
    PAGE_SIZE = 10  # 每页10条数据

    # User-Agent 列表，随机选择
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]

    def __init__(self):
        self.session = requests.Session()
        self._init_session()

    def _init_session(self):
        """初始化 session，访问百度首页获取 cookie"""
        try:
            headers = {
                'User-Agent': random.choice(self.USER_AGENTS),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
            }
            # 先访问百度首页获取基础 cookie
            self.session.get('https://www.baidu.com/', headers=headers, timeout=5)
        except:
            pass

    def _get_headers(self):
        """获取请求头"""
        return {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Referer': 'https://news.baidu.com/',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': random.choice(self.USER_AGENTS)
        }

    def search(self, keyword, page=1):
        """
        根据关键字搜索百度新闻（单页）

        Args:
            keyword: 搜索关键字
            page: 页码，默认第1页（从1开始）

        Returns:
            list: 新闻列表，每条包含 title, summary, cover, url, source
        """
        # pn参数: 0=第1页, 10=第2页, 20=第3页...
        pn = (page - 1) * self.PAGE_SIZE

        params = {
            'rtt': '1',
            'bsst': '1',
            'cl': '2',
            'tn': 'news',
            'rsv_dl': 'ns_pc',
            'word': keyword,
            'pn': pn
        }

        try:
            response = self.session.get(
                self.BASE_URL,
                params=params,
                headers=self._get_headers(),
                timeout=15
            )
            response.raise_for_status()
            response.encoding = 'utf-8'

            # 检查是否被拦截
            if len(response.text) < 10000:
                print(f"警告: 响应内容过短({len(response.text)}字节)，可能被限流")
                self.session = requests.Session()
                self._init_session()
                time.sleep(1)
                response = self.session.get(
                    self.BASE_URL,
                    params=params,
                    headers=self._get_headers(),
                    timeout=15
                )
                response.encoding = 'utf-8'

            return self._parse_news(response.text)

        except requests.RequestException as e:
            print(f"请求失败: {e}")
            return []

    def search_batch(self, keyword, count=30, delay=0.5):
        """
        批量搜索百度新闻（自动翻页）

        Args:
            keyword: 搜索关键字
            count: 目标获取数量，默认30条
            delay: 每次请求间隔（秒），默认0.5秒，避免被限流

        Returns:
            list: 新闻列表
        """
        all_news = []
        page = 1
        max_pages = 10  # 最大翻页数，避免无限循环
        seen_urls = set()  # 用于去重

        while len(all_news) < count and page <= max_pages:
            # 获取当前页数据
            news_list = self.search(keyword, page)

            if not news_list:
                # 当前页没有数据，停止翻页
                break

            # 去重添加
            for news in news_list:
                url = news.get('url', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_news.append(news)

                    # 达到目标数量则停止
                    if len(all_news) >= count:
                        break

            page += 1

            # 如果还需要继续翻页，添加延迟
            if len(all_news) < count and page <= max_pages:
                time.sleep(delay)

        return all_news[:count]  # 确保不超过目标数量

    def _parse_news(self, html):
        """
        解析百度新闻搜索结果页面

        Args:
            html: 页面HTML内容

        Returns:
            list: 解析后的新闻列表
        """
        news_list = []
        soup = BeautifulSoup(html, 'html.parser')

        # 百度新闻结果在 div.c-container 中
        containers = soup.select('div.c-container')

        for container in containers:
            try:
                news = self._parse_news_item(container)
                # 数据清洗：过滤掉标题、URL或图片为空的脏数据
                if self._is_valid_news(news):
                    news_list.append(news)
            except Exception as e:
                continue

        return news_list

    def _is_valid_news(self, news):
        """
        数据清洗：验证新闻数据是否有效

        Args:
            news: 新闻数据字典

        Returns:
            bool: 数据是否有效
        """
        if not news:
            return False

        # 标题不能为空
        title = news.get('title', '').strip()
        if not title:
            return False

        # URL不能为空
        url = news.get('url', '').strip()
        if not url:
            return False

        # 封面图片不能为空
        cover = news.get('cover', '').strip()
        if not cover:
            return False

        return True

    def _parse_news_item(self, container):
        """
        解析单条新闻

        Args:
            container: BeautifulSoup元素

        Returns:
            dict: 新闻数据
        """
        news = {
            'title': '',
            'summary': '',
            'cover': '',
            'url': '',
            'source': ''
        }

        # 方法1: 从 s-data 注释中提取 JSON 数据
        comments = container.find_all(string=lambda text: isinstance(text, Comment))
        for comment in comments:
            comment_str = str(comment).strip()
            if comment_str.startswith('s-data:'):
                try:
                    json_str = comment_str[7:]
                    data = json.loads(json_str)

                    # 提取标题（移除 <em> 标签）
                    title = data.get('title', '')
                    title = re.sub(r'</?em>', '', title)
                    news['title'] = title

                    # 提取URL
                    news['url'] = data.get('titleUrl', '')

                    # 提取摘要
                    summary = data.get('summary', '')
                    summary = re.sub(r'</?em>', '', summary)
                    news['summary'] = summary

                    # 提取封面图片
                    news['cover'] = data.get('leftImgSrc', '')

                    # 提取来源
                    news['source'] = data.get('sourceName', '')

                    return news
                except (json.JSONDecodeError, KeyError):
                    continue

        # 方法2: 从 HTML 元素中提取（兼容方案）
        title_elem = container.select_one('h3 a')
        if title_elem:
            news['title'] = title_elem.get_text(strip=True)
            news['url'] = title_elem.get('href', '')

        summary_elem = container.select_one('[class*="content"], [class*="summary"]')
        if summary_elem:
            news['summary'] = summary_elem.get_text(strip=True)

        img_elem = container.select_one('img[src*="http"]')
        if img_elem:
            news['cover'] = img_elem.get('src', '')

        source_elem = container.select_one('[class*="source"], [class*="author"]')
        if source_elem:
            news['source'] = source_elem.get_text(strip=True)

        return news


# 模块级别的便捷函数
def search_news(keyword, page=1, count=None):
    """
    搜索百度新闻

    Args:
        keyword: 搜索关键字
        page: 页码（当 count 为 None 时使用）
        count: 目标获取数量，设置后会自动翻页获取

    Returns:
        list: 新闻列表
    """
    crawler = BaiduNewsCrawler()

    if count is not None:
        # 批量获取指定数量
        return crawler.search_batch(keyword, count=count)
    else:
        # 获取单页
        return crawler.search(keyword, page)


def deep_collect(url):
    """
    深度采集：访问原始URL，提取文章正文、发布时间、作者等信息

    Args:
        url: 新闻原始URL

    Returns:
        dict: 包含 content, publish_time, author 的字典
    """
    result = {
        'content': '',
        'publish_time': '',
        'author': ''
    }

    if not url:
        return result

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
        }

        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        response.encoding = response.apparent_encoding or 'utf-8'

        soup = BeautifulSoup(response.text, 'html.parser')

        # 移除脚本和样式
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
            tag.decompose()

        # 尝试提取发布时间
        time_patterns = [
            r'\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?\s*\d{1,2}:\d{2}(:\d{2})?',
            r'\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?',
        ]
        page_text = soup.get_text()
        for pattern in time_patterns:
            match = re.search(pattern, page_text)
            if match:
                result['publish_time'] = match.group().strip()
                break

        # 尝试提取作者
        author_selectors = [
            '[class*="author"]', '[class*="writer"]', '[class*="editor"]',
            '[id*="author"]', '[class*="source"]', 'meta[name="author"]'
        ]
        for selector in author_selectors:
            elem = soup.select_one(selector)
            if elem:
                if elem.name == 'meta':
                    author = elem.get('content', '')
                else:
                    author = elem.get_text(strip=True)
                if author and len(author) < 50:
                    result['author'] = author
                    break

        # 提取正文内容
        content_selectors = [
            'article', '[class*="article"]', '[class*="content"]',
            '[class*="post"]', '[class*="news"]', '[class*="detail"]',
            '[id*="article"]', '[id*="content"]', 'main'
        ]

        content = ''
        for selector in content_selectors:
            elem = soup.select_one(selector)
            if elem:
                # 提取段落文本
                paragraphs = elem.find_all(['p', 'div'])
                texts = []
                for p in paragraphs:
                    text = p.get_text(strip=True)
                    if text and len(text) > 20:  # 过滤掉太短的内容
                        texts.append(text)
                if texts:
                    content = '\n\n'.join(texts)
                    break

        # 如果没找到，尝试从body提取
        if not content:
            body = soup.find('body')
            if body:
                paragraphs = body.find_all('p')
                texts = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20]
                content = '\n\n'.join(texts)

        result['content'] = content[:10000]  # 限制长度

    except Exception as e:
        print(f"深度采集失败: {e}")

    return result
