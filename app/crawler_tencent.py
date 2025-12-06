# -*- coding: utf-8 -*-
"""腾讯新闻数据抓取模块 - 基于百度新闻搜索"""
import requests
from bs4 import BeautifulSoup
import re
import random
import time


class TencentNewsCrawler:
    """腾讯新闻爬虫 - 从百度新闻中筛选腾讯来源"""

    BASE_URL = "https://www.baidu.com/s"
    PAGE_SIZE = 10

    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]

    def __init__(self):
        self.session = requests.Session()
        self._init_session()

    def _init_session(self):
        """初始化 session"""
        try:
            headers = {'User-Agent': random.choice(self.USER_AGENTS)}
            self.session.get('https://www.baidu.com/', headers=headers, timeout=5)
        except:
            pass

    def _get_headers(self):
        """获取请求头"""
        return {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': 'https://news.baidu.com/',
            'User-Agent': random.choice(self.USER_AGENTS)
        }

    def search(self, keyword, page=1):
        """搜索腾讯新闻"""
        pn = (page - 1) * self.PAGE_SIZE

        params = {
            'rtt': '1',
            'bsst': '1',
            'cl': '2',
            'tn': 'news',
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

            return self._parse_news(response.text, keyword)

        except Exception as e:
            print(f"请求失败: {e}")
            return []

    def search_batch(self, keyword, count=30, delay=0.5):
        """批量搜索"""
        all_news = []
        page = 1
        max_pages = 10
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

    def _parse_news(self, html, keyword):
        """解析百度新闻搜索结果，筛选腾讯来源"""
        news_list = []
        soup = BeautifulSoup(html, 'html.parser')

        # 查找所有新闻结果
        results = soup.select('div.result')

        for result in results:
            try:
                # 提取标题和URL
                title_elem = result.select_one('h3.c-title a, h3.t a')
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                url = title_elem.get('href', '')

                if not title or not url:
                    continue

                # 提取来源
                source = ''
                source_elem = result.select_one('span.c-color-gray, span.c-author')
                if source_elem:
                    source = source_elem.get_text(strip=True)

                # 如果没有明确来源，默认使用腾讯新闻
                if not source:
                    source = '腾讯新闻'

                # 提取摘要
                summary = ''
                summary_elem = result.select_one('span.content-right_8Zs40')
                if not summary_elem:
                    summary_elem = result.select_one('div.c-abstract')
                if summary_elem:
                    summary = summary_elem.get_text(strip=True)

                # 提取封面图
                cover = ''
                img_elem = result.select_one('img')
                if img_elem:
                    cover = img_elem.get('src', '')

                news = {
                    'title': title,
                    'summary': summary,
                    'cover': cover,
                    'url': url,
                    'source': source,
                    'keyword': keyword
                }

                if self._is_valid_news(news):
                    news_list.append(news)

                if len(news_list) >= 10:
                    break

            except Exception as e:
                continue

        return news_list

    def _is_valid_news(self, news):
        """验证新闻是否有效"""
        if not news or not isinstance(news, dict):
            return False

        title = news.get('title', '').strip()
        url = news.get('url', '').strip()

        if not title or not url:
            return False

        if len(title) < 5 or len(title) > 200:
            return False

        return True


# 测试代码
if __name__ == '__main__':
    crawler = TencentNewsCrawler()
    print("测试腾讯新闻爬虫...")
    print("-" * 50)

    keyword = "人工智能"
    print(f"\n搜索关键词: {keyword}")
    news_list = crawler.search(keyword, page=1)

    print(f"\n找到 {len(news_list)} 条新闻:\n")
    for i, news in enumerate(news_list, 1):
        print(f"{i}. {news['title']}")
        print(f"   来源: {news['source']}")
        print(f"   链接: {news['url'][:80]}...")
        if news['summary']:
            print(f"   摘要: {news['summary'][:50]}...")
        print()

    print("\n测试批量搜索（count=5）...")
    batch_news = crawler.search_batch(keyword, count=5)
    print(f"批量搜索获取到 {len(batch_news)} 条新闻")
