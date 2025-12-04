# -*- coding: utf-8 -*-
"""360新闻搜索数据抓取模块"""
import requests
from bs4 import BeautifulSoup
import re
import random
import time


class News360Crawler:
    """360新闻搜索爬虫"""

    # 使用360新闻搜索API
    BASE_URL = "https://news.so.com/ns"

    # User-Agent 列表
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    ]

    def __init__(self):
        self.session = requests.Session()
        self._init_session()

    def _init_session(self):
        """初始化 session"""
        try:
            headers = self._get_headers()
            # 访问360搜索首页获取cookie
            self.session.get('https://www.so.com/', headers=headers, timeout=10)
        except Exception as e:
            print(f"初始化session失败: {e}")

    def _get_headers(self):
        """获取请求头"""
        return {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Referer': 'https://www.so.com/',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': random.choice(self.USER_AGENTS)
        }

    def search(self, keyword, page=1):
        """
        根据关键字搜索360新闻

        Args:
            keyword: 搜索关键字
            page: 页码，默认第1页

        Returns:
            list: 新闻列表，每条包含 title, summary, cover, url, source
        """
        params = {
            'q': keyword,
            'pn': page,
            'src': 'srp',
            'fr': 'hao_360so'
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

            if len(response.text) < 1000:
                print(f"警告: 响应内容过短({len(response.text)}字节)")
                return []

            return self._parse_news(response.text)

        except requests.RequestException as e:
            print(f"请求失败: {e}")
            return []

    def search_batch(self, keyword, count=30, delay=0.5):
        """
        批量搜索（自动翻页）

        Args:
            keyword: 搜索关键字
            count: 目标获取数量，默认30条
            delay: 每次请求间隔（秒）

        Returns:
            list: 新闻列表
        """
        all_news = []
        page = 1
        max_pages = 5
        seen_urls = set()

        while len(all_news) < count and page <= max_pages:
            news_list = self.search(keyword, page)

            if not news_list:
                break

            for news in news_list:
                url = news.get('url', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_news.append(news)

                    if len(all_news) >= count:
                        break

            page += 1

            if len(all_news) < count and page <= max_pages:
                time.sleep(delay)

        return all_news[:count]

    def _parse_news(self, html):
        """
        解析360新闻搜索结果页面

        Args:
            html: 页面HTML内容

        Returns:
            list: 解析后的新闻列表
        """
        news_list = []
        soup = BeautifulSoup(html, 'html.parser')

        # 查找新闻列表项
        items = soup.select('li.res-list')

        for item in items:
            try:
                news = self._parse_news_item(item)
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

        title = news.get('title', '').strip()
        if not title or len(title) < 3:
            return False

        url = news.get('url', '').strip()
        if not url or not url.startswith('http'):
            return False

        cover = news.get('cover', '').strip()
        if not cover or not cover.startswith('http'):
            return False

        return True

    def _parse_news_item(self, item):
        """
        解析单条新闻

        Args:
            item: BeautifulSoup元素

        Returns:
            dict: 新闻数据
        """
        news = {
            'title': '',
            'summary': '',
            'cover': '',
            'url': '',
            'source': '360新闻'
        }

        # 提取URL（从data-url属性获取原始链接）
        news['url'] = item.get('data-url', '')

        # 提取标题
        title_elem = item.select_one('h3')
        if title_elem:
            # 移除HTML标签，保留纯文本
            title_text = title_elem.get_text(strip=True)
            news['title'] = title_text

        # 提取摘要
        summary_elem = item.select_one('.g-desc, .txt-info, p')
        if summary_elem:
            summary_text = summary_elem.get_text(strip=True)
            if summary_text and summary_text != news['title']:
                news['summary'] = summary_text[:200]

        if not news['summary']:
            news['summary'] = news['title']

        # 提取封面图片
        img_elem = item.select_one('img')
        if img_elem:
            cover = img_elem.get('src') or img_elem.get('data-src') or img_elem.get('data-original') or ''
            if cover:
                # 确保URL完整
                if cover.startswith('//'):
                    cover = 'https:' + cover
                news['cover'] = cover

        # 提取来源
        source_elem = item.select_one('.ns-site, .g-source-f, .source, .g-site, span[class*="site"]')
        if source_elem:
            source_text = source_elem.get_text(strip=True)
            if source_text and len(source_text) < 30:
                news['source'] = source_text

        return news


# 模块级别的便捷函数
def search_360kuai_news(keyword, page=1, count=None):
    """
    搜索360新闻

    Args:
        keyword: 搜索关键字
        page: 页码（当 count 为 None 时使用）
        count: 目标获取数量，设置后会自动翻页获取

    Returns:
        list: 新闻列表
    """
    crawler = News360Crawler()

    if count is not None:
        return crawler.search_batch(keyword, count=count)
    else:
        return crawler.search(keyword, page)


if __name__ == '__main__':
    # 测试
    print("测试360新闻爬虫...")
    results = search_360kuai_news("科技", count=10)
    print(f"获取到 {len(results)} 条新闻")
    print(f"有封面: {sum(1 for r in results if r.get('cover'))}")

    if results:
        print()
        for i, news in enumerate(results[:3], 1):
            print(f"--- 新闻 {i} ---")
            print(f"标题: {news['title'][:50]}")
            print(f"摘要: {news['summary'][:50]}..." if len(news['summary']) > 50 else f"摘要: {news['summary']}")
            print(f"封面: {news['cover'][:60]}..." if len(news['cover']) > 60 else f"封面: {news['cover']}")
            print(f"URL: {news['url'][:60]}..." if len(news['url']) > 60 else f"URL: {news['url']}")
            print(f"来源: {news['source']}")
            print()
