# -*- coding: utf-8 -*-
"""新华网新闻数据抓取模块"""
import requests
import json
import random
import time
import urllib3

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class XinhuaNewsCrawler:
    """新华网新闻爬虫 - 使用官方API"""

    # 新华网频道节点API
    API_URL = "http://qc.wa.news.cn/nodeart/list"

    # 频道节点ID
    CHANNEL_NODES = [
        11147664,  # 时政
        11147667,  # 科技
        11147668,  # 体育
        11147669,  # 娱乐
        11147670,  # 社会
    ]

    PAGE_SIZE = 10

    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]

    def __init__(self):
        self.session = requests.Session()

    def _get_headers(self):
        """获取请求头"""
        return {
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'User-Agent': random.choice(self.USER_AGENTS),
            'Referer': 'http://www.news.cn/'
        }

    def _fetch_node(self, node_id, page_num=1, count=20):
        """
        从指定节点获取新闻列表

        Args:
            node_id: 频道节点ID
            page_num: 页码
            count: 每页数量

        Returns:
            list: 新闻列表
        """
        news_list = []

        params = {
            'nid': node_id,
            'pgnum': page_num,
            'cnt': count,
            'tp': 1,
            'orderby': 1
        }

        try:
            response = self.session.get(
                self.API_URL,
                params=params,
                headers=self._get_headers(),
                timeout=15,
                verify=False
            )

            if response.status_code != 200:
                return []

            # 解析JSONP响应
            text = response.text.strip()
            if text.startswith('(') and text.endswith(')'):
                text = text[1:-1]

            data = json.loads(text)

            if data.get('status') != 0:
                return []

            items = data.get('data', {}).get('list', [])

            for item in items:
                # 提取封面图片
                cover = ''
                all_pics = item.get('allPics', [])
                if all_pics and isinstance(all_pics, list) and len(all_pics) > 0:
                    cover = all_pics[0]
                elif item.get('PicLinks'):
                    # 备用：使用PicLinks构建图片URL
                    pic_link = item.get('PicLinks', '')
                    if pic_link:
                        cover = f"http://www.xinhuanet.com/titlepic/{str(item.get('DocID', ''))[:6]}/{pic_link}"

                news = {
                    'title': item.get('Title', ''),
                    'summary': item.get('Abstract', '') or item.get('Title', ''),
                    'cover': cover,
                    'url': item.get('LinkUrl', ''),
                    'source': item.get('SourceName', '新华网') or '新华网'
                }

                # 验证数据有效性
                if news['title'] and news['url']:
                    news_list.append(news)

        except json.JSONDecodeError as e:
            print(f"JSON解析失败: {e}")
        except Exception as e:
            print(f"获取节点 {node_id} 数据失败: {e}")

        return news_list

    def search(self, keyword, page=1):
        """
        搜索新华网新闻

        Args:
            keyword: 搜索关键字
            page: 页码

        Returns:
            list: 新闻列表
        """
        all_news = []
        seen_urls = set()

        # 从各个频道节点获取新闻
        for node_id in self.CHANNEL_NODES:
            try:
                # 获取更多数据以便过滤
                news_list = self._fetch_node(node_id, page_num=1, count=50)

                for news in news_list:
                    # 关键词过滤
                    if keyword:
                        title = news.get('title', '')
                        summary = news.get('summary', '')
                        if keyword not in title and keyword not in summary:
                            continue

                    url = news.get('url', '')
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_news.append(news)

            except Exception as e:
                print(f"获取节点 {node_id} 失败: {e}")
                continue

            # 如果已经获取足够数据，停止
            if len(all_news) >= self.PAGE_SIZE * page:
                break

            time.sleep(0.2)

        # 分页返回
        start = (page - 1) * self.PAGE_SIZE
        end = start + self.PAGE_SIZE
        return all_news[start:end]

    def search_batch(self, keyword, count=30, delay=0.3):
        """
        批量搜索

        Args:
            keyword: 搜索关键字
            count: 目标数量
            delay: 请求间隔

        Returns:
            list: 新闻列表
        """
        all_news = []
        seen_urls = set()

        for node_id in self.CHANNEL_NODES:
            try:
                # 获取更多数据以便过滤
                news_list = self._fetch_node(node_id, page_num=1, count=100)

                for news in news_list:
                    # 关键词过滤
                    if keyword:
                        title = news.get('title', '')
                        summary = news.get('summary', '')
                        if keyword not in title and keyword not in summary:
                            continue

                    url = news.get('url', '')
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_news.append(news)

                        if len(all_news) >= count:
                            return all_news[:count]

            except Exception as e:
                continue

            time.sleep(delay)

        return all_news[:count]


# 模块级便捷函数
def search_xinhua_news(keyword, page=1, count=None):
    """
    搜索新华网新闻

    Args:
        keyword: 搜索关键字
        page: 页码
        count: 目标数量

    Returns:
        list: 新闻列表，格式与百度新闻一致
    """
    crawler = XinhuaNewsCrawler()

    if count is not None:
        return crawler.search_batch(keyword, count=count)
    else:
        return crawler.search(keyword, page)
