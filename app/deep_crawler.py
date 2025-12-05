# -*- coding: utf-8 -*-
"""基于规则库的深度采集模块"""
import requests
from lxml import etree
from bs4 import BeautifulSoup
import json
import re
from urllib.parse import urlparse


class RuleBasedCrawler:
    """基于规则库的深度采集器"""

    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
    }

    # 内置站点规则（针对常用新闻源）
    BUILTIN_RULES = {
        'baijiahao.baidu.com': {
            'name': '百度百家号',
            'title_xpath': '//h1//text() | //div[contains(@class,"article-title")]//text() | //title/text()',
            'content_xpath': '//div[contains(@class,"article-content")]//p//text() | //div[@id="article"]//p//text() | //div[contains(@class,"index-module_articleWrap")]//p//text()',
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.162 Mobile Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Referer': 'https://www.baidu.com/',
                'Connection': 'keep-alive',
            },
            'use_session': True,  # 使用session维持cookie
        },
        'mbd.baidu.com': {
            'name': '百度新闻',
            'title_xpath': '//h1//text() | //div[contains(@class,"article-title")]//text()',
            'content_xpath': '//div[contains(@class,"article-content")]//p//text()',
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G981B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.162 Mobile Safari/537.36',
                'Referer': 'https://www.baidu.com/',
            },
            'use_session': True,
        },
        'www.360kuai.com': {
            'name': '360快资讯',
            'title_xpath': '//h1//text() | //div[contains(@class,"title")]//text()',
            'content_xpath': '//div[contains(@class,"article")]//p//text() | //div[contains(@class,"content")]//p//text() | //div[contains(@class,"js-article")]//p//text()',
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
        },
        '360kuai.com': {
            'name': '360快资讯',
            'title_xpath': '//h1//text() | //div[contains(@class,"title")]//text()',
            'content_xpath': '//div[contains(@class,"article")]//p//text() | //div[contains(@class,"content")]//p//text() | //div[contains(@class,"js-article")]//p//text()',
            'headers': {}
        },
    }

    def __init__(self, db_session=None):
        """
        初始化采集器

        Args:
            db_session: SQLAlchemy数据库会话，用于查询和更新规则
        """
        self.db = db_session

    def find_matching_rule(self, source_name, url):
        """
        根据来源名称或URL匹配采集规则

        Args:
            source_name: 数据来源名称
            url: 目标URL

        Returns:
            CrawlRule对象、内置规则dict或None
        """
        # 提取URL域名
        url_domain = ''
        url_domain_no_www = ''
        if url:
            try:
                parsed = urlparse(url)
                url_domain = parsed.netloc.lower()
                url_domain_no_www = url_domain.replace('www.', '')
            except:
                pass

        # 1. 优先检查数据库规则（用户自定义规则优先）
        if self.db:
            from app.models import CrawlRule

            # 1.1 按适用来源匹配（优先级最高）
            if source_name:
                rules = CrawlRule.query.filter(
                    CrawlRule.status == 1
                ).order_by(CrawlRule.priority.desc()).all()

                for rule in rules:
                    sources = rule.get_applicable_sources()
                    if source_name in sources:
                        return {'type': 'db', 'rule': rule}

            # 1.2 按URL域名匹配数据库规则
            if url_domain:
                rules = CrawlRule.query.filter(CrawlRule.status == 1).order_by(CrawlRule.priority.desc()).all()
                for rule in rules:
                    if rule.site_domain:
                        # 清理规则中的域名
                        rule_domain = rule.site_domain.lower()
                        rule_domain = rule_domain.replace('https://', '').replace('http://', '').replace('www.', '')
                        rule_domain = rule_domain.split('/')[0].strip()

                        # 多种匹配方式
                        if (rule_domain == url_domain_no_www or
                            rule_domain == url_domain or
                            url_domain_no_www.endswith('.' + rule_domain) or
                            url_domain.endswith('.' + rule_domain) or
                            rule_domain in url_domain_no_www or
                            url_domain_no_www in rule_domain):
                            return {'type': 'db', 'rule': rule}

            # 1.3 按站点名称精确匹配
            if source_name:
                rule = CrawlRule.query.filter(
                    CrawlRule.status == 1,
                    CrawlRule.site_name == source_name
                ).order_by(CrawlRule.priority.desc()).first()
                if rule:
                    return {'type': 'db', 'rule': rule}

                # 模糊匹配来源名称
                rule = CrawlRule.query.filter(
                    CrawlRule.status == 1,
                    CrawlRule.site_name.like(f'%{source_name}%')
                ).order_by(CrawlRule.priority.desc()).first()
                if rule:
                    return {'type': 'db', 'rule': rule}

        # 2. 如果没有数据库规则，检查内置规则（基于URL域名）
        if url_domain:
            # 完整域名匹配内置规则
            if url_domain in self.BUILTIN_RULES:
                return {'type': 'builtin', 'rule': self.BUILTIN_RULES[url_domain]}

            # 去掉www后匹配
            if url_domain_no_www in self.BUILTIN_RULES:
                return {'type': 'builtin', 'rule': self.BUILTIN_RULES[url_domain_no_www]}

            # 检查内置规则的域名是否包含在URL域名中
            for builtin_domain, builtin_rule in self.BUILTIN_RULES.items():
                if builtin_domain in url_domain or url_domain_no_www in builtin_domain:
                    return {'type': 'builtin', 'rule': builtin_rule}

        return None

    def deep_collect(self, url, source_name=None, rule=None):
        """
        深度采集单条数据

        Args:
            url: 目标URL
            source_name: 来源名称（用于匹配规则）
            rule: 直接指定的规则对象（可选）

        Returns:
            dict: {
                'success': bool,
                'title': str,
                'content': str,
                'publish_time': str,
                'author': str,
                'rule_used': str,  # 使用的规则名称
                'rule_id': int,    # 使用的规则ID
                'error': str       # 错误信息
            }
        """
        result = {
            'success': False,
            'title': '',
            'content': '',
            'publish_time': '',
            'author': '',
            'rule_used': None,
            'rule_id': None,
            'error': ''
        }

        if not url:
            result['error'] = 'URL不能为空'
            return result

        # 查找匹配的规则
        matched = None
        if rule:
            # 直接使用传入的规则对象
            matched = {'type': 'db', 'rule': rule}
        else:
            matched = self.find_matching_rule(source_name, url)

        try:
            # 准备请求头
            headers = self.DEFAULT_HEADERS.copy()

            # 根据规则类型处理
            if matched:
                if matched['type'] == 'builtin':
                    # 内置规则
                    builtin_rule = matched['rule']
                    result['rule_used'] = builtin_rule['name']
                    if builtin_rule.get('headers'):
                        headers.update(builtin_rule['headers'])

                    # 使用session发送请求（可维持cookie）
                    if builtin_rule.get('use_session'):
                        session = requests.Session()
                        session.headers.update(headers)
                        # 先访问百度首页获取cookie
                        try:
                            session.get('https://www.baidu.com/', timeout=5)
                        except:
                            pass
                        response = session.get(url, timeout=15, allow_redirects=True)
                    else:
                        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)

                    response.encoding = response.apparent_encoding or 'utf-8'
                    html = response.text

                    # 使用内置XPath解析
                    parsed = self._parse_with_builtin_rule(html, builtin_rule)
                    result.update(parsed)

                elif matched['type'] == 'db':
                    # 数据库规则
                    db_rule = matched['rule']
                    result['rule_used'] = db_rule.site_name
                    result['rule_id'] = db_rule.id

                    if db_rule.request_headers:
                        try:
                            custom_headers = json.loads(db_rule.request_headers)
                            headers.update(custom_headers)
                        except:
                            pass

                    # 发送请求
                    response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
                    response.encoding = response.apparent_encoding or 'utf-8'
                    html = response.text

                    # 使用数据库XPath解析
                    parsed = self._parse_with_xpath(html, db_rule)
                    result.update(parsed)
            else:
                # 无匹配规则，使用通用解析
                result['rule_used'] = '通用规则'
                response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
                response.encoding = response.apparent_encoding or 'utf-8'
                html = response.text
                parsed = self._parse_generic(html)
                result.update(parsed)

            # 检查解析结果
            if result['content']:
                result['success'] = True
                # 更新规则统计（成功）
                if matched and matched['type'] == 'db':
                    self._update_rule_stats(matched['rule'].id, success=True)
            else:
                result['error'] = '未能提取到正文内容'
                # 更新规则统计（失败）
                if matched and matched['type'] == 'db':
                    self._update_rule_stats(matched['rule'].id, success=False)

        except requests.Timeout:
            result['error'] = '请求超时'
            if matched and matched['type'] == 'db':
                self._update_rule_stats(matched['rule'].id, success=False)
        except requests.RequestException as e:
            result['error'] = f'请求失败: {str(e)}'
            if matched and matched['type'] == 'db':
                self._update_rule_stats(matched['rule'].id, success=False)
        except Exception as e:
            result['error'] = f'解析失败: {str(e)}'
            if matched and matched['type'] == 'db':
                self._update_rule_stats(matched['rule'].id, success=False)

        return result

    def _update_rule_stats(self, rule_id, success=True):
        """
        更新规则采集统计

        Args:
            rule_id: 规则ID
            success: 是否成功
        """
        if not self.db or not rule_id:
            return

        try:
            from app.models import CrawlRule
            rule = CrawlRule.query.get(rule_id)
            if rule:
                if success:
                    rule.success_count = (rule.success_count or 0) + 1
                else:
                    rule.fail_count = (rule.fail_count or 0) + 1
                self.db.session.commit()
        except Exception as e:
            print(f"更新规则统计失败: {e}")
            try:
                self.db.session.rollback()
            except:
                pass

    def _parse_with_builtin_rule(self, html, rule):
        """
        使用内置规则解析页面

        Args:
            html: 页面HTML
            rule: 内置规则dict

        Returns:
            dict: 解析结果
        """
        result = {
            'title': '',
            'content': '',
            'publish_time': '',
            'author': ''
        }

        try:
            tree = etree.HTML(html)

            # 提取标题
            if rule.get('title_xpath'):
                try:
                    title_result = tree.xpath(rule['title_xpath'])
                    if title_result:
                        titles = [t.strip() for t in title_result if isinstance(t, str) and t.strip()]
                        if titles:
                            result['title'] = titles[0]
                except Exception as e:
                    print(f"内置规则标题XPath解析失败: {e}")

            # 提取正文
            if rule.get('content_xpath'):
                try:
                    content_result = tree.xpath(rule['content_xpath'])
                    if content_result:
                        texts = [t.strip() for t in content_result if isinstance(t, str) and t.strip()]
                        result['content'] = '\n\n'.join(texts)
                except Exception as e:
                    print(f"内置规则内容XPath解析失败: {e}")

            # 如果XPath没有提取到内容，使用通用方法补充
            if not result['content']:
                generic = self._parse_generic(html)
                if generic['content']:
                    result['content'] = generic['content']

            # 提取时间和作者（通用方法）
            generic = self._parse_generic(html)
            if not result['title']:
                result['title'] = generic.get('title', '')
            if not result['publish_time']:
                result['publish_time'] = generic.get('publish_time', '')
            if not result['author']:
                result['author'] = generic.get('author', '')

        except Exception as e:
            print(f"内置规则解析异常: {e}")
            return self._parse_generic(html)

        return result

    def _parse_with_xpath(self, html, rule):
        """
        使用XPath规则解析页面

        Args:
            html: 页面HTML
            rule: CrawlRule对象

        Returns:
            dict: 解析结果
        """
        result = {
            'title': '',
            'content': '',
            'publish_time': '',
            'author': ''
        }

        try:
            # 使用lxml解析
            tree = etree.HTML(html)

            # 提取标题
            if rule.title_xpath:
                try:
                    title_result = tree.xpath(rule.title_xpath)
                    if title_result:
                        if isinstance(title_result[0], str):
                            result['title'] = title_result[0].strip()
                        else:
                            result['title'] = title_result[0].text_content().strip() if hasattr(title_result[0], 'text_content') else str(title_result[0]).strip()
                except Exception as e:
                    print(f"标题XPath解析失败: {e}")

            # 提取正文
            if rule.content_xpath:
                try:
                    content_result = tree.xpath(rule.content_xpath)
                    if content_result:
                        texts = []
                        for item in content_result:
                            if isinstance(item, str):
                                text = item.strip()
                            else:
                                text = item.text_content().strip() if hasattr(item, 'text_content') else str(item).strip()
                            if text:
                                texts.append(text)
                        result['content'] = '\n\n'.join(texts)
                except Exception as e:
                    print(f"内容XPath解析失败: {e}")

            # 如果XPath没有提取到内容，使用通用方法补充
            if not result['content']:
                generic = self._parse_generic(html)
                if generic['content']:
                    result['content'] = generic['content']

            # 提取时间和作者（通用方法）
            generic = self._parse_generic(html)
            if not result['publish_time']:
                result['publish_time'] = generic.get('publish_time', '')
            if not result['author']:
                result['author'] = generic.get('author', '')

        except Exception as e:
            print(f"XPath解析异常: {e}")
            # 降级到通用解析
            return self._parse_generic(html)

        return result

    def _parse_generic(self, html):
        """
        通用解析方法（不依赖规则）

        Args:
            html: 页面HTML

        Returns:
            dict: 解析结果
        """
        result = {
            'title': '',
            'content': '',
            'publish_time': '',
            'author': ''
        }

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # 移除脚本和样式
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe']):
                tag.decompose()

            # 提取标题
            title_elem = soup.find('h1') or soup.find('title')
            if title_elem:
                result['title'] = title_elem.get_text(strip=True)

            # 提取发布时间
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

            # 提取作者
            author_selectors = [
                '[class*="author"]', '[class*="writer"]', '[class*="editor"]',
                '[id*="author"]', 'meta[name="author"]'
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

            for selector in content_selectors:
                elem = soup.select_one(selector)
                if elem:
                    paragraphs = elem.find_all(['p', 'div'])
                    texts = []
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        if text and len(text) > 20:
                            texts.append(text)
                    if texts:
                        result['content'] = '\n\n'.join(texts)
                        break

            # 如果没找到，从body提取
            if not result['content']:
                body = soup.find('body')
                if body:
                    paragraphs = body.find_all('p')
                    texts = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20]
                    result['content'] = '\n\n'.join(texts)

            # 限制长度
            if result['content']:
                result['content'] = result['content'][:10000]

        except Exception as e:
            print(f"通用解析失败: {e}")

        return result

    def update_rule_if_needed(self, rule_id, new_title_xpath=None, new_content_xpath=None):
        """
        更新规则库中的XPath（如果发现变化）

        Args:
            rule_id: 规则ID
            new_title_xpath: 新的标题XPath
            new_content_xpath: 新的内容XPath

        Returns:
            bool: 是否更新成功
        """
        if not self.db or not rule_id:
            return False

        from app.models import CrawlRule

        rule = CrawlRule.query.get(rule_id)
        if not rule:
            return False

        updated = False

        if new_title_xpath and new_title_xpath != rule.title_xpath:
            rule.title_xpath = new_title_xpath
            updated = True

        if new_content_xpath and new_content_xpath != rule.content_xpath:
            rule.content_xpath = new_content_xpath
            updated = True

        if updated:
            try:
                self.db.session.commit()
                return True
            except:
                self.db.session.rollback()
                return False

        return False


def deep_collect_with_rule(url, source_name=None, db_session=None):
    """
    便捷函数：使用规则库进行深度采集

    Args:
        url: 目标URL
        source_name: 来源名称
        db_session: 数据库会话

    Returns:
        dict: 采集结果
    """
    crawler = RuleBasedCrawler(db_session)
    return crawler.deep_collect(url, source_name)
