# -*- coding: utf-8 -*-
"""
动态爬虫引擎

功能说明：
- 根据 CrawlerConfig 配置动态执行数据采集
- 支持多种爬虫类型：HTML解析、JSON API、JSONP
- 支持模板变量替换（如 {keyword}, {page}, {offset}）
"""

import requests
import json
import re
import time
import random
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Any
import urllib.parse


class DynamicCrawlerEngine:
    """动态爬虫引擎"""

    def __init__(self, crawler_config: Dict):
        """
        初始化动态爬虫

        Args:
            crawler_config: 爬虫配置字典（来自 CrawlerConfig.to_dict()）
        """
        self.config = crawler_config
        self.session = requests.Session()
        self._init_session()

        # 提取关键配置
        self.crawler_type = crawler_config.get('crawler_type', 'html_parser')
        self.base_url = crawler_config.get('base_url', '')
        self.search_url = crawler_config.get('search_url', '')

        if not self.search_url:
            raise ValueError("search_url 配置不能为空")

        self.request_method = crawler_config.get('request_method', 'GET')

        # 安全解析JSON字段
        self.search_params = self._safe_parse_json(crawler_config.get('search_params_template'), {})
        self.pagination = self._safe_parse_json(crawler_config.get('pagination_config'), {})
        self.headers = self._safe_parse_json(crawler_config.get('default_headers'), {})
        self.parse_config = self._safe_parse_json(crawler_config.get('parse_config'), {})

        self.request_delay = float(crawler_config.get('request_delay', 0.5))
        self.timeout = int(crawler_config.get('timeout', 15))
        self.max_pages = int(crawler_config.get('max_pages', 10))
        self.page_size = int(crawler_config.get('page_size', 10))

        # 处理变量模板
        self.variable_patterns = {
            'keyword': re.compile(r'\{keyword\}'),
            'page': re.compile(r'\{page\}'),
            'offset': re.compile(r'\{offset\}'),
            'count': re.compile(r'\{count\}'),
            'start': re.compile(r'\{start\}')
        }

    def _safe_parse_json(self, value: Any, default: Any) -> Any:
        """
        安全解析JSON字符串

        Args:
            value: 待解析的值
            default: 默认值

        Returns:
            解析后的值或默认值
        """
        if value is None:
            return default

        if isinstance(value, dict) or isinstance(value, list):
            return value

        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                print(f"警告: JSON解析失败，使用默认值: {value}")
                return default

        return default

    def _init_session(self):
        """初始化 session"""
        if self.base_url:
            try:
                self.session.get(self.base_url, timeout=5)
                time.sleep(0.1)
            except Exception as e:
                print(f"初始化session失败: {e}")

    def search(self, keyword: str, page: int = 1, count: Optional[int] = None) -> List[Dict]:
        """
        根据关键词搜索

        Args:
            keyword: 搜索关键词
            page: 页码（从1开始）
            count: 目标获取数量（设置后会自动翻页）

        Returns:
            List[Dict]: 新闻列表
        """
        if count is not None:
            return self.search_batch(keyword, count=count)

        return self._search_single_page(keyword, page)

    def search_batch(self, keyword: str, count: int = 30) -> List[Dict]:
        """
        批量搜索（自动翻页）

        Args:
            keyword: 搜索关键词
            count: 目标获取数量

        Returns:
            List[Dict]: 新闻列表
        """
        if not keyword or not keyword.strip():
            print("动态爬虫: 关键词为空")
            return []

        if count <= 0:
            print("动态爬虫: 采集数量必须大于0")
            return []

        all_news = []
        page = 1
        seen_urls = set()
        consecutive_empty_pages = 0

        while len(all_news) < count and page <= self.max_pages:
            print(f"动态爬虫: 正在获取第 {page} 页...")

            try:
                news_list = self._search_single_page(keyword, page)
            except Exception as e:
                print(f"动态爬虫: 第 {page} 页请求失败: {e}")
                consecutive_empty_pages += 1
                if consecutive_empty_pages >= 3:
                    print("动态爬虫: 连续3页失败，停止采集")
                    break
                page += 1
                continue

            if not news_list:
                consecutive_empty_pages += 1
                print(f"动态爬虫: 第 {page} 页无数据（连续 {consecutive_empty_pages} 页）")
                if consecutive_empty_pages >= 3:
                    print("动态爬虫: 连续3页无数据，停止翻页")
                    break
                page += 1
                continue

            # 重置连续空页计数
            consecutive_empty_pages = 0

            # 去重添加
            new_count = 0
            for news in news_list:
                url = news.get('url', '')
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_news.append(news)
                    new_count += 1

                    if len(all_news) >= count:
                        break

            print(f"动态爬虫: 第 {page} 页获取 {new_count} 条新数据（已累计 {len(all_news)} 条）")

            page += 1

            if len(all_news) < count and page <= self.max_pages:
                delay = self.request_delay + random.uniform(0, 0.3)  # 随机延迟
                print(f"动态爬虫: 等待 {delay:.2f} 秒后继续...")
                time.sleep(delay)

        print(f"动态爬虫: 采集完成，共获取 {len(all_news)} 条数据")
        return all_news[:count]

    def _search_single_page(self, keyword: str, page: int) -> List[Dict]:
        """
        搜索单页

        Args:
            keyword: 搜索关键词
            page: 页码

        Returns:
            List[Dict]: 新闻列表
        """
        # 构建请求参数
        params = self._build_request_params(keyword, page)

        # 构建完整URL
        url = self.search_url
        if self.request_method == 'GET' and params:
            # GET请求，参数拼接在URL上
            separator = '&' if '?' in url else '?'
            url = url + separator + urllib.parse.urlencode(params)
            request_data = None
        else:
            # POST请求
            request_data = params

        try:
            print(f"动态爬虫: 请求URL: {url}")

            if self.request_method == 'POST':
                response = self.session.post(
                    url,
                    data=request_data,
                    headers=self.headers,
                    timeout=self.timeout
                )
            else:
                response = self.session.get(
                    url,
                    headers=self.headers,
                    timeout=self.timeout
                )

            response.raise_for_status()

            # 根据爬虫类型解析响应
            if self.crawler_type == 'json_api':
                return self._parse_json_response(response)
            elif self.crawler_type == 'jsonp_api':
                return self._parse_jsonp_response(response)
            else:
                # HTML解析
                response.encoding = response.apparent_encoding or 'utf-8'
                return self._parse_html_response(response.text)

        except Exception as e:
            print(f"动态爬虫: 请求失败: {e}")
            return []

    def _build_request_params(self, keyword: str, page: int) -> Dict:
        """
        构建请求参数，替换模板变量

        Args:
            keyword: 搜索关键词
            page: 页码

        Returns:
            Dict: 请求参数
        """
        params = {}

        # 计算分页值
        pagination = self.pagination or {}
        pagination_type = pagination.get('type', 'page_number')
        start = pagination.get('start', 1 if pagination_type == 'page_number' else 0)
        step = pagination.get('step', 1)

        if pagination_type == 'page_number':
            page_value = start + (page - 1) * step
            offset_value = (page - 1) * self.page_size
        else:  # offset
            offset_value = start + (page - 1) * step
            page_value = page

        # 替换模板变量
        for key, value in self.search_params.items():
            if isinstance(value, str):
                # 替换变量
                result = value
                result = self.variable_patterns['keyword'].sub(keyword, result)
                result = self.variable_patterns['page'].sub(str(page_value), result)
                result = self.variable_patterns['offset'].sub(str(offset_value), result)
                result = self.variable_patterns['count'].sub(str(self.page_size), result)
                result = self.variable_patterns['start'].sub(str(start), result)
                params[key] = result
            else:
                params[key] = value

        return params

    def _parse_html_response(self, html: str) -> List[Dict]:
        """
        解析HTML响应（通用）

        Args:
            html: HTML内容

        Returns:
            List[Dict]: 新闻列表
        """
        news_list = []

        if not html or not html.strip():
            print("动态爬虫: HTML内容为空")
            return news_list

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # 获取容器选择器
            container_selector = self.parse_config.get('container_selector', '')
            if not container_selector:
                print("动态爬虫: 未配置容器选择器，尝试智能推断")
                container_selector = self._guess_container_selector(soup)

            if not container_selector:
                print("动态爬虫: 无法确定容器选择器")
                return news_list

            containers = soup.select(container_selector)

            print(f"动态爬虫: 找到 {len(containers)} 个容器（选择器: {container_selector}）")

            if not containers:
                print("动态爬虫: 未找到匹配的容器，可能选择器配置错误")
                return news_list

            for idx, container in enumerate(containers):
                try:
                    news = self._extract_fields_from_container(container)
                    if self._is_valid_news(news):
                        news_list.append(news)
                    else:
                        print(f"动态爬虫: 第 {idx+1} 个容器数据无效，跳过")
                except Exception as e:
                    print(f"动态爬虫: 解析第 {idx+1} 个容器失败: {e}")
                    continue

        except Exception as e:
            print(f"动态爬虫: HTML解析失败: {e}")
            import traceback
            print(traceback.format_exc())

        return news_list

    def _guess_container_selector(self, soup: BeautifulSoup) -> str:
        """
        智能推断容器选择器

        Args:
            soup: BeautifulSoup对象

        Returns:
            str: 选择器
        """
        # 尝试常见的容器选择器
        common_selectors = [
            'div.item',
            'li.item',
            'div.news-item',
            'li.news-item',
            'div.result',
            'li.result',
            'div.c-container',
            'li.res-list',
            'article',
            'div.article'
        ]

        for selector in common_selectors:
            elements = soup.select(selector)
            if len(elements) >= 3:  # 至少找到3个
                print(f"动态爬虫: 自动选择容器: {selector} (找到 {len(elements)} 个)")
                return selector

        # 默认选择器
        return 'div'

    def _extract_fields_from_container(self, container) -> Dict:
        """
        从容器中提取字段

        Args:
            container: BeautifulSoup元素

        Returns:
            Dict: 新闻数据
        """
        news = {
            'title': '',
            'summary': '',
            'cover': '',
            'url': '',
            'source': ''
        }

        field_selectors = self.parse_config.get('field_selectors', {})

        # 提取标题
        if 'title' in field_selectors:
            selectors = field_selectors['title']
            if isinstance(selectors, str):
                selectors = [selectors]
            news['title'] = self._find_first_text(container, selectors)

        # 提取URL
        if 'url' in field_selectors:
            selectors = field_selectors['url']
            if isinstance(selectors, str):
                selectors = [selectors]
            news['url'] = self._find_first_attribute(container, selectors, 'href')

        # 提取摘要
        if 'summary' in field_selectors:
            selectors = field_selectors['summary']
            if isinstance(selectors, str):
                selectors = [selectors]
            news['summary'] = self._find_first_text(container, selectors)

        # 提取封面
        if 'cover' in field_selectors:
            selectors = field_selectors['cover']
            if isinstance(selectors, str):
                selectors = [selectors]
            news['cover'] = self._find_first_attribute(container, selectors, 'src')

        # 提取来源
        if 'source' in field_selectors:
            selectors = field_selectors['source']
            if isinstance(selectors, str):
                selectors = [selectors]
            news['source'] = self._find_first_text(container, selectors)

        # 如果没有解析到来源，使用默认值
        if not news['source'] and self.base_url:
            news['source'] = urllib.parse.urlparse(self.base_url).netloc

        return news

    def _find_first_text(self, container, selectors: List[str]) -> str:
        """
        查找第一个匹配的文本

        Args:
            container: BeautifulSoup元素
            selectors: 选择器列表

        Returns:
            str: 文本
        """
        for selector in selectors:
            try:
                # 去除属性提取部分
                if '@' in selector:
                    selector = selector.split('@')[0]

                element = container.select_one(selector)
                if element:
                    text = element.get_text(strip=True)
                    if text:
                        return text
            except:
                continue
        return ''

    def _find_first_attribute(self, container, selectors: List[str], attr: str) -> str:
        """
        查找第一个匹配的属性值

        Args:
            container: BeautifulSoup元素
            selectors: 选择器列表
            attr: 属性名

        Returns:
            str: 属性值
        """
        for selector in selectors:
            try:
                element = None

                # 如果包含属性提取语法
                if '@' in selector:
                    parts = selector.split('@')
                    selector_part = parts[0]
                    attr_part = parts[1] if len(parts) > 1 else attr

                    element = container.select_one(selector_part)
                    if element and attr_part in element.attrs:
                        return element.attrs[attr_part]
                else:
                    element = container.select_one(selector)
                    if element and attr in element.attrs:
                        return element.attrs[attr]
            except:
                continue
        return ''

    def _parse_json_response(self, response) -> List[Dict]:
        """
        解析JSON响应

        Args:
            response: requests.Response对象

        Returns:
            List[Dict]: 新闻列表
        """
        try:
            data = response.json()
            return self._extract_from_json(data)
        except Exception as e:
            print(f"动态爬虫: JSON解析失败: {e}")
            return []

    def _parse_jsonp_response(self, response) -> List[Dict]:
        """
        解析JSONP响应

        Args:
            response: requests.Response对象

        Returns:
            List[Dict]: 新闻列表
        """
        try:
            text = response.text.strip()

            # 去除JSONP包装
            if text.startswith('(') and text.endswith(')'):
                text = text[1:-1]
            elif text.startswith('callback(') and text.endswith(')'):
                text = text[9:-1]
            elif '({' in text and text.endswith(')'):
                start = text.find('({')
                text = text[start + 1:-1]

            data = json.loads(text)
            return self._extract_from_json(data)
        except Exception as e:
            print(f"动态爬虫: JSONP解析失败: {e}")
            return []

    def _extract_from_json(self, data: Any) -> List[Dict]:
        """
        从JSON数据中提取新闻列表

        Args:
            data: JSON数据

        Returns:
            List[Dict]: 新闻列表
        """
        news_list = []

        try:
            # 获取数据路径
            data_path = self.parse_config.get('data_path', '')

            # 根据路径提取数据
            items = data
            if data_path:
                for key in data_path.split('.'):
                    if isinstance(items, dict) and key in items:
                        items = items[key]
                    elif isinstance(items, list) and key.isdigit():
                        items = items[int(key)]
                    else:
                        items = []
                        break

            if not isinstance(items, list):
                print(f"动态爬虫: 数据路径 {data_path} 返回的不是列表")
                return []

            # 字段路径映射
            field_paths = self.parse_config.get('field_paths', {})

            for item in items:
                news = {}

                # 提取各个字段
                news['title'] = self._get_json_value(item, field_paths.get('title', 'title'))
                news['url'] = self._get_json_value(item, field_paths.get('url', 'url'))
                news['summary'] = self._get_json_value(item, field_paths.get('summary', 'summary'))
                news['cover'] = self._get_json_value(item, field_paths.get('cover', 'cover'))
                news['source'] = self._get_json_value(item, field_paths.get('source', 'source'))

                if news.get('title'):
                    news_list.append(news)

        except Exception as e:
            print(f"动态爬虫: JSON数据提取失败: {e}")

        return news_list

    def _get_json_value(self, data: Dict, path: str) -> str:
        """
        从JSON数据中提取值

        Args:
            data: JSON数据
            path: 路径（支持点语法和数组索引）

        Returns:
            str: 值
        """
        try:
            # 如果路径包含数组索引（如 items[0].title）
            current = data

            # 分割路径
            parts = re.split(r'\.|\[|\]', path)
            parts = [p for p in parts if p]

            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                elif isinstance(current, list) and part.isdigit():
                    index = int(part)
                    if index < len(current):
                        current = current[index]
                    else:
                        return ''
                else:
                    return ''

            return str(current) if current else ''

        except Exception as e:
            print(f"动态爬虫: JSON路径提取失败 {path}: {e}")
            return ''

    def _is_valid_news(self, news: Dict) -> bool:
        """
        验证新闻数据是否有效

        Args:
            news: 新闻数据

        Returns:
            bool: 是否有效
        """
        if not news:
            return False

        # 标题不能为空
        title = news.get('title', '').strip()
        if not title or len(title) < 3:
            return False

        # URL必须有效
        url = news.get('url', '').strip()
        if not url or not (url.startswith('http://') or url.startswith('https://')):
            return False

        return True


# ==================== 便捷函数 ====================

def create_dynamic_crawler(config: Dict) -> DynamicCrawlerEngine:
    """
    创建动态爬虫

    Args:
        config: 爬虫配置

    Returns:
        DynamicCrawlerEngine: 动态爬虫实例
    """
    return DynamicCrawlerEngine(config)


def search_with_dynamic_crawler(config: Dict, keyword: str, count: int = 30) -> List[Dict]:
    """
    使用动态爬虫搜索

    Args:
        config: 爬虫配置
        keyword: 搜索关键词
        count: 目标数量

    Returns:
        List[Dict]: 新闻列表
    """
    crawler = DynamicCrawlerEngine(config)
    return crawler.search_batch(keyword, count=count)


if __name__ == '__main__':
    # 测试动态爬虫
    print("=== 测试动态爬虫引擎 ===")

    # 加载示例配置
    with open('app/crawler_analyzer.py', 'r', encoding='utf-8') as f:
        exec(f.read())

    analyzer = CrawlerAnalyzer()
    config = analyzer.analyze(
        url='https://www.baidu.com/s?tn=news&word={keyword}&pn={offset}',
        request_headers='{"User-Agent": "Mozilla/5.0..."}'
    )

    print("\n配置:", json.dumps(config, indent=2, ensure_ascii=False))

    # 使用动态爬虫
    crawler = DynamicCrawlerEngine(config)
    results = crawler.search("人工智能", page=1)

    print(f"\n获取到 {len(results)} 条结果")
    if results:
        for i, news in enumerate(results[:3], 1):
            print(f"{i}. {news.get('title', '')[:50]}...")
