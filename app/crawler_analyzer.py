# -*- coding: utf-8 -*-
"""
智能爬虫分析器模块

功能说明：
- 根据用户提供的源地址和Request Headers智能分析出爬虫配置
- 自动推断爬虫引擎类型、搜索参数模板、分页配置等
- 减少用户手动配置的难度
"""

import json
import re
import urllib.parse
from typing import Dict, List, Optional, Tuple


class CrawlerAnalyzer:
    """智能爬虫分析器"""

    # 常见新闻站点的默认配置模板
    SITE_TEMPLATES = {
        'baidu_news': {
            'name': '百度新闻',
            'code': 'baidu_news',
            'crawler_type': 'html_parser',
            'base_url': 'https://www.baidu.com',
            'search_url': 'https://www.baidu.com/s',
            'request_method': 'GET',
            'search_params_template': {
                'rtt': '1',
                'bsst': '1',
                'cl': '2',
                'tn': 'news',
                'rsv_dl': 'ns_pc',
                'word': '{keyword}',
                'pn': '{offset}'  # 0, 10, 20...
            },
            'pagination_config': {
                'type': 'offset',
                'param': 'pn',
                'start': 0,
                'step': 10
            },
            'default_headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Cache-Control': 'no-cache',
                'Referer': 'https://www.baidu.com/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            },
            'parse_config': {
                'container_selector': 'div.c-container',
                'field_selectors': {
                    'title': ['h3 a', 'title'],
                    'url': ['h3 a@href', 'url'],
                    'summary': ['[class*="content"], [class*="summary"]', 'summary'],
                    'cover': ['img[src*="http"]@src', 'cover'],
                    'source': ['[class*="source"], [class*="author"]', 'source']
                }
            }
        },
        'news_360': {
            'name': '360新闻',
            'code': 'news_360',
            'crawler_type': 'html_parser',
            'base_url': 'https://www.so.com',
            'search_url': 'https://news.so.com/ns',
            'request_method': 'GET',
            'search_params_template': {
                'q': '{keyword}',
                'pn': '{page}',
                'src': 'srp',
                'fr': 'hao_360so'
            },
            'pagination_config': {
                'type': 'page_number',
                'param': 'pn',
                'start': 1,
                'step': 1
            },
            'default_headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Cache-Control': 'no-cache',
                'Referer': 'https://www.so.com/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            },
            'parse_config': {
                'container_selector': 'li.res-list',
                'field_selectors': {
                    'title': ['h3', 'title'],
                    'url': ['@data-url', 'url'],
                    'summary': ['.g-desc, .txt-info, p', 'summary'],
                    'cover': ['img@src', 'img@data-src', 'img@data-original', 'cover'],
                    'source': ['.ns-site, .g-source-f, .source', 'source']
                }
            }
        },
        'xinhua_news': {
            'name': '新华网',
            'code': 'xinhua_news',
            'crawler_type': 'jsonp_api',
            'base_url': 'http://www.news.cn',
            'search_url': 'http://qc.wa.news.cn/nodeart/list',
            'request_method': 'GET',
            'search_params_template': {
                'nid': '{channel_id}',
                'pgnum': '{page}',
                'cnt': '{count}',
                'tp': '1',
                'orderby': '1'
            },
            'pagination_config': {
                'type': 'page_number',
                'param': 'pgnum',
                'start': 1,
                'step': 1
            },
            'default_headers': {
                'Accept': '*/*',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Referer': 'http://www.news.cn/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            },
            'parse_config': {
                'response_type': 'jsonp',
                'data_path': 'data.list',
                'field_paths': {
                    'title': 'Title',
                    'url': 'LinkUrl',
                    'summary': 'Abstract',
                    'cover': 'allPics[0]',
                    'source': 'SourceName'
                }
            },
            'channel_nodes': [11147664, 11147667, 11147668, 11147669, 11147670]
        }
    }

    def __init__(self):
        self.analyzed_data = None

    def analyze(self, url: str, request_headers: Optional[str] = None, sample_html: Optional[str] = None) -> Dict:
        """
        智能分析URL和Headers，生成爬虫配置

        Args:
            url: 源地址（搜索URL或基础URL）
            request_headers: Request Headers（JSON格式字符串或Dict）
            sample_html: 示例HTML内容（用于分析选择器）

        Returns:
            Dict: 分析后的爬虫配置
        """
        self.analyzed_data = {
            'name': '',
            'code': '',
            'crawler_type': 'html_parser',
            'base_url': '',
            'search_url': '',
            'request_method': 'GET',
            'search_params_template': {},
            'pagination_config': {},
            'default_headers': {},
            'parse_config': {},
            'confidence': 0,  # 置信度 0-100
            'notes': []  # 分析备注
        }

        # 解析URL
        parsed_url = urllib.parse.urlparse(url)
        domain = parsed_url.netloc.lower()
        path = parsed_url.path
        query = parsed_url.query

        # Step 1: 识别站点类型
        site_type = self._identify_site_type(domain)
        if site_type and site_type in self.SITE_TEMPLATES:
            # 使用已知模板
            template = self.SITE_TEMPLATES[site_type].copy()
            template['confidence'] = 90
            template['notes'] = [f'识别为已知站点: {template["name"]}']

            # 合并自定义Headers
            if request_headers:
                headers_dict = self._parse_headers(request_headers)
                if headers_dict:
                    template['default_headers'].update(headers_dict)
                    template['notes'].append('已合并自定义请求头')

            self.analyzed_data = template
        else:
            # Step 2: 通用分析
            self._generic_analyze(url, parsed_url, request_headers, sample_html)

        # Step 3: 从Query参数推断搜索参数模板
        if query:
            self._analyze_query_params(query)

        # Step 4: 从Headers推断必要信息
        if request_headers:
            self._analyze_headers(request_headers)

        return self.analyzed_data

    def _identify_site_type(self, domain: str) -> Optional[str]:
        """识别站点类型"""
        domain_lower = domain.lower()

        if 'baidu.com' in domain_lower:
            return 'baidu_news'
        elif 'so.com' in domain_lower:
            return 'news_360'
        elif 'news.cn' in domain_lower or 'xinhuanet.com' in domain_lower:
            return 'xinhua_news'

        return None

    def _generic_analyze(self, url: str, parsed_url, request_headers=None, sample_html=None):
        """通用分析"""
        domain = parsed_url.netloc

        # 基础信息
        self.analyzed_data['name'] = f"自定义-{domain.replace('.', '_')}"
        self.analyzed_data['code'] = f"custom_{domain.replace('.', '_')}"
        self.analyzed_data['base_url'] = f"{parsed_url.scheme}://{domain}"
        self.analyzed_data['search_url'] = url
        self.analyzed_data['confidence'] = 50
        self.analyzed_data['notes'] = ['通用分析模式，需要手动优化配置']

        # 默认请求头
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        if request_headers:
            custom_headers = self._parse_headers(request_headers)
            headers.update(custom_headers)

        self.analyzed_data['default_headers'] = headers

        # 默认分页配置
        self.analyzed_data['pagination_config'] = {
            'type': 'page_number',
            'param': 'page',
            'start': 1,
            'step': 1
        }

        # 默认解析配置
        self.analyzed_data['parse_config'] = {
            'container_selector': 'div.item, li.item, .news-item',
            'field_selectors': {
                'title': ['h3, .title, h2', 'title'],
                'url': ['a@href', 'url'],
                'summary': ['.summary, .desc, p', 'summary'],
                'cover': ['img@src', '.cover@src', 'cover'],
                'source': ['.source, .author', 'source']
            }
        }

    def _parse_headers(self, headers) -> Dict:
        """解析Headers"""
        if isinstance(headers, str):
            try:
                return json.loads(headers)
            except:
                # 尝试解析原始格式
                return self._parse_raw_headers(headers)
        elif isinstance(headers, dict):
            return headers
        return {}

    def _parse_raw_headers(self, raw_headers: str) -> Dict:
        """解析原始Headers格式"""
        headers = {}
        lines = raw_headers.strip().split('\n')

        for line in lines:
            line = line.strip()
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()

                # 只保留重要Header
                if key.lower() in ['user-agent', 'accept', 'accept-language', 'referer', 'authorization']:
                    headers[key] = value

        return headers

    def _analyze_query_params(self, query: str):
        """分析Query参数"""
        params = urllib.parse.parse_qs(query)

        search_params = {}
        for key, values in params.items():
            value = values[0] if values else ''

            # 识别可能的搜索参数
            if any(k in key.lower() for k in ['q', 'query', 'search', 'word', 'keyword']):
                search_params[key] = '{keyword}'
            elif any(k in key.lower() for k in ['page', 'p', 'pn']):
                # 分页参数
                if value.isdigit():
                    num = int(value)
                    if num in [0, 1]:
                        search_params[key] = '{page_or_offset}'
                        self.analyzed_data['pagination_config']['param'] = key
            else:
                # 其他参数保留原始值
                search_params[key] = value

        if search_params:
            self.analyzed_data['search_params_template'] = search_params
            self.analyzed_data['notes'].append(f'从URL提取参数: {list(search_params.keys())}')

    def _analyze_headers(self, headers):
        """分析Headers"""
        headers_dict = self._parse_headers(headers)

        if 'User-Agent' in headers_dict:
            self.analyzed_data['default_headers']['User-Agent'] = headers_dict['User-Agent']

        if 'Referer' in headers_dict:
            self.analyzed_data['default_headers']['Referer'] = headers_dict['Referer']

        if 'Authorization' in headers_dict:
            self.analyzed_data['default_headers']['Authorization'] = headers_dict['Authorization']

    def analyze_html_for_selectors(self, html: str) -> Dict:
        """
        从HTML示例中分析选择器

        Args:
            html: HTML内容

        Returns:
            Dict: 解析配置
        """
        # 这里可以接入实际的HTML分析逻辑
        # 为简化，返回默认配置
        return {
            'container_selector': 'div.item, li.item, .news-item',
            'field_selectors': {
                'title': ['h3, .title, h2'],
                'url': ['a@href'],
                'summary': ['.summary, .desc, p'],
                'cover': ['img@src', 'img@data-src'],
                'source': ['.source, .author']
            }
        }

    @staticmethod
    def get_supported_sites() -> List[Dict]:
        """获取支持的站点列表"""
        analyzer = CrawlerAnalyzer()
        sites = []

        for code, config in analyzer.SITE_TEMPLATES.items():
            sites.append({
                'code': code,
                'name': config['name'],
                'base_url': config['base_url'],
                'crawler_type': config['crawler_type']
            })

        return sites


if __name__ == '__main__':
    # 测试智能分析器
    analyzer = CrawlerAnalyzer()

    # 测试百度新闻
    print("=== 测试百度新闻分析 ===")
    result = analyzer.analyze(
        url='https://www.baidu.com/s?rtt=1&bsst=1&cl=2&tn=news&word={keyword}&pn={offset}',
        request_headers='{"User-Agent": "Mozilla/5.0..."}'
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # 测试通用分析
    print("\n=== 测试通用站点分析 ===")
    result = analyzer.analyze(
        url='https://example.com/search?q={keyword}&page={page}',
        request_headers='''
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
Referer: https://example.com/
        '''
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
