# -*- coding: utf-8 -*-
"""基于规则库的深度采集模块"""
import requests
from lxml import etree
from bs4 import BeautifulSoup
import json
import re
import time
import random
import logging
from urllib.parse import urlparse

# 配置日志
logger = logging.getLogger(__name__)


class RuleBasedCrawler:
    """基于规则库的深度采集器"""

    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
    }

    # 移动端UA（更容易绕过反爬虫）
    MOBILE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'

    # 内置站点规则（针对常用新闻源）
    BUILTIN_RULES = {
        'baijiahao.baidu.com': {
            'name': '百度百家号',
            'title_xpath': '//h1//text() | //div[contains(@class,"article-title")]//text() | //title/text()',
            'content_xpath': '//div[contains(@class,"article-content")]//p//text() | //div[@id="article"]//p//text() | //div[contains(@class,"index-module_articleWrap")]//p//text() | //div[contains(@class,"_3YeQG")]//p//text() | //article//p//text()',
            'headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Referer': 'https://www.baidu.com/',
                'Connection': 'keep-alive',
                'Cache-Control': 'max-age=0',
            },
            'use_mobile': True,
            'use_session': True,
        },
        'mbd.baidu.com': {
            'name': '百度新闻',
            'title_xpath': '//h1//text() | //div[contains(@class,"article-title")]//text()',
            'content_xpath': '//div[contains(@class,"article-content")]//p//text() | //article//p//text()',
            'headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
                'Referer': 'https://www.baidu.com/',
            },
            'use_mobile': True,
            'use_session': True,
        },
        'www.360kuai.com': {
            'name': '360快资讯',
            'title_xpath': '//h1//text() | //div[contains(@class,"title")]//text() | //header//h1//text()',
            'content_xpath': '//div[contains(@class,"article")]//p//text() | //div[contains(@class,"content")]//p//text() | //div[contains(@class,"js-article")]//p//text() | //article//p//text()',
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.so.com/',
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

        # 1. 优先按URL域名匹配（域名匹配最准确）
        if url_domain and self.db:
            from app.models import CrawlRule

            rules = CrawlRule.query.filter(CrawlRule.status == 1).order_by(CrawlRule.priority.desc()).all()
            for rule in rules:
                if rule.site_domain:
                    # 清理规则中的域名
                    rule_domain = rule.site_domain.lower()
                    rule_domain = rule_domain.replace('https://', '').replace('http://', '').replace('www.', '')
                    rule_domain = rule_domain.split('/')[0].strip()

                    # 精确域名匹配
                    if (rule_domain == url_domain_no_www or
                        rule_domain == url_domain or
                        url_domain_no_www.endswith('.' + rule_domain) or
                        url_domain.endswith('.' + rule_domain)):
                        return {'type': 'db', 'rule': rule}

        # 2. 检查内置规则（基于URL域名）
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

        # 3. 按适用来源匹配（域名无法匹配时再用来源名）
        if self.db and source_name:
            from app.models import CrawlRule

            rules = CrawlRule.query.filter(
                CrawlRule.status == 1
            ).order_by(CrawlRule.priority.desc()).all()

            for rule in rules:
                sources = rule.get_applicable_sources()
                if source_name in sources:
                    return {'type': 'db', 'rule': rule}

            # 按站点名称精确匹配
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

        return None

    def deep_collect(self, url, source_name=None, rule=None):
        """
        深度采集单条数据

        Args:
            url: 目标URL
            source_name: 来源名称(用于匹配规则)
            rule: 直接指定的规则对象(可选)

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
            logger.warning(f"深度采集失败: {result['error']}")
            return result

        # 解析URL域名
        url_domain = ''
        try:
            parsed = urlparse(url)
            url_domain = parsed.netloc.lower()
            logger.info(f"开始深度采集 - URL: {url}, 域名: {url_domain}, 来源: {source_name}")
        except Exception as e:
            logger.error(f"URL解析失败: {e}")

        # 查找匹配的规则
        matched = None
        if rule:
            matched = {'type': 'db', 'rule': rule}
            logger.info(f"使用指定规则: {rule.site_name} (ID: {rule.id})")
        else:
            matched = self.find_matching_rule(source_name, url)
            if matched:
                if matched['type'] == 'db':
                    logger.info(f"匹配到数据库规则: {matched['rule'].site_name} (ID: {matched['rule'].id})")
                else:
                    logger.info(f"匹配到内置规则: {matched['rule']['name']}")
            else:
                logger.warning(f"未找到匹配规则,将使用通用解析 - 来源:{source_name}, 域名:{url_domain}")

        try:
            # 添加随机延迟(防止请求过快被封)
            time.sleep(random.uniform(0.5, 1.5))

            # 准备请求头
            headers = self.DEFAULT_HEADERS.copy()
            html = None

            # 百度系网站特殊处理
            if 'baidu.com' in url_domain:
                logger.info("检测到百度系网站,使用特殊采集方法")
                html = self._fetch_baidu_content(url)
                if html:
                    result['rule_used'] = '百度百家号'
                    logger.info(f"百度特殊方法获取成功,页面大小: {len(html)}")
                    # 检查是否被重定向到验证码
                    if 'captcha' in html.lower() or 'wappass' in html.lower() or len(html) < 2000:
                        logger.warning("检测到验证码或页面过小,尝试备用方法")
                        # 尝试使用备用方法
                        html = self._fetch_with_alternative_method(url)
                        if html:
                            logger.info(f"备用方法获取成功,页面大小: {len(html)}")
                else:
                    logger.warning("百度特殊方法失败,将使用普通方法")

            # 正常采集流程
            if not html:
                if matched:
                    if matched['type'] == 'builtin':
                        builtin_rule = matched['rule']
                        result['rule_used'] = builtin_rule['name']
                        logger.info(f"使用内置规则请求: {builtin_rule['name']}")

                        if builtin_rule.get('headers'):
                            headers.update(builtin_rule['headers'])

                        if builtin_rule.get('use_session'):
                            session = requests.Session()
                            session.headers.update(headers)
                            try:
                                session.get('https://www.baidu.com/', timeout=5)
                            except:
                                pass
                            response = session.get(url, timeout=15, allow_redirects=True)
                        else:
                            response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)

                        response.encoding = response.apparent_encoding or 'utf-8'
                        html = response.text
                        logger.info(f"内置规则请求成功,页面大小: {len(html)}, 状态码: {response.status_code}")

                    elif matched['type'] == 'db':
                        db_rule = matched['rule']
                        result['rule_used'] = db_rule.site_name
                        result['rule_id'] = db_rule.id
                        logger.info(f"使用数据库规则请求: {db_rule.site_name} (ID: {db_rule.id})")
                        logger.debug(f"规则详情 - 标题XPath: {db_rule.title_xpath}, 内容XPath: {db_rule.content_xpath}")

                        if db_rule.request_headers:
                            try:
                                custom_headers = json.loads(db_rule.request_headers)
                                headers.update(custom_headers)
                                logger.debug(f"使用自定义请求头: {custom_headers}")
                            except Exception as e:
                                logger.warning(f"解析自定义请求头失败: {e}")

                        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
                        response.encoding = response.apparent_encoding or 'utf-8'
                        html = response.text
                        logger.info(f"数据库规则请求成功,页面大小: {len(html)}, 状态码: {response.status_code}")
                else:
                    result['rule_used'] = '通用规则'
                    logger.info("使用通用规则请求")
                    response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
                    response.encoding = response.apparent_encoding or 'utf-8'
                    html = response.text
                    logger.info(f"通用规则请求成功,页面大小: {len(html)}, 状态码: {response.status_code}")

            # 检查是否获取到有效内容
            if not html or len(html) < 500:
                result['error'] = '页面内容为空或被拦截'
                logger.error(f"采集失败: {result['error']}, 页面大小: {len(html) if html else 0}")
                return result

            # 检查是否被重定向到验证码
            if 'captcha' in html.lower() or 'wappass' in html.lower():
                result['error'] = '触发了网站验证码保护'
                logger.error(f"采集失败: {result['error']}")
                return result

            # 解析内容
            logger.info("开始解析页面内容")
            if matched:
                if matched['type'] == 'builtin':
                    logger.debug("使用内置规则解析")
                    parsed = self._parse_with_builtin_rule(html, matched['rule'])
                elif matched['type'] == 'db':
                    logger.debug("使用数据库XPath规则解析")
                    parsed = self._parse_with_xpath(html, matched['rule'])
                else:
                    logger.debug("使用通用方法解析")
                    parsed = self._parse_generic(html)
            else:
                logger.debug("使用通用方法解析")
                parsed = self._parse_generic(html)

            result.update(parsed)

            # 记录解析结果
            logger.info(f"解析完成 - 标题: {result['title'][:50] if result['title'] else '无'}, "
                       f"内容长度: {len(result['content']) if result['content'] else 0}, "
                       f"发布时间: {result['publish_time'] or '无'}, "
                       f"作者: {result['author'] or '无'}")

            # 检查解析结果
            if result['content']:
                result['success'] = True
                logger.info(f"✓ 深度采集成功! 使用规则: {result['rule_used']}")
                if matched and matched['type'] == 'db':
                    self._update_rule_stats(matched['rule'].id, success=True)
            else:
                result['error'] = '未能提取到正文内容'
                logger.warning(f"× 解析失败: {result['error']}")
                if matched and matched['type'] == 'db':
                    self._update_rule_stats(matched['rule'].id, success=False)

        except requests.Timeout:
            result['error'] = '请求超时'
            logger.error(f"采集失败: {result['error']}")
            if matched and matched['type'] == 'db':
                self._update_rule_stats(matched['rule'].id, success=False)
        except requests.RequestException as e:
            result['error'] = f'请求失败: {str(e)}'
            logger.error(f"采集失败: {result['error']}")
            if matched and matched['type'] == 'db':
                self._update_rule_stats(matched['rule'].id, success=False)
        except Exception as e:
            result['error'] = f'解析失败: {str(e)}'
            logger.error(f"采集失败: {result['error']}", exc_info=True)
            if matched and matched['type'] == 'db':
                self._update_rule_stats(matched['rule'].id, success=False)

        return result

    def _fetch_baidu_content(self, url):
        """
        百度系网站特殊采集方法
        """
        try:
            # 提取百家号文章ID
            article_id = None
            if 'id=' in url:
                import re
                match = re.search(r'id=(\d+)', url)
                if match:
                    article_id = match.group(1)

            # 方法1: 使用移动端UA访问
            headers = {
                'User-Agent': self.MOBILE_UA,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Referer': 'https://m.baidu.com/',
                'Connection': 'keep-alive',
            }

            session = requests.Session()
            session.headers.update(headers)

            # 先访问移动版百度
            try:
                session.get('https://m.baidu.com/', timeout=5)
                time.sleep(0.3)
            except:
                pass

            # 如果有文章ID，尝试使用移动版URL
            if article_id:
                mobile_url = f'https://mbd.baidu.com/newspage/data/landingsuper?context=%7B%22nid%22%3A%22news_{article_id}%22%7D&n_type=1&p_from=4'
                try:
                    resp = session.get(mobile_url, timeout=15)
                    resp.encoding = 'utf-8'
                    if resp.status_code == 200 and len(resp.text) > 2000:
                        return resp.text
                except:
                    pass

            # 直接访问原URL
            resp = session.get(url, timeout=15, allow_redirects=True)
            resp.encoding = resp.apparent_encoding or 'utf-8'

            if resp.status_code == 200:
                return resp.text

        except Exception as e:
            print(f"百度采集异常: {e}")

        return None

    def _fetch_with_alternative_method(self, url):
        """
        备用采集方法
        """
        try:
            # 使用不同的User-Agent
            ua_list = [
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            ]

            headers = {
                'User-Agent': random.choice(ua_list),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            }

            time.sleep(random.uniform(1, 2))
            resp = requests.get(url, headers=headers, timeout=15)
            resp.encoding = resp.apparent_encoding or 'utf-8'

            if resp.status_code == 200 and len(resp.text) > 2000:
                return resp.text

        except:
            pass

        return None

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
            logger.debug(f"XPath解析 - 规则名称: {rule.site_name}")

            # 提取标题
            if rule.title_xpath:
                try:
                    logger.debug(f"尝试标题XPath: {rule.title_xpath}")
                    title_result = tree.xpath(rule.title_xpath)
                    logger.debug(f"标题XPath返回 {len(title_result) if title_result else 0} 个结果")
                    if title_result:
                        if isinstance(title_result[0], str):
                            result['title'] = title_result[0].strip()
                        else:
                            result['title'] = title_result[0].text_content().strip() if hasattr(title_result[0], 'text_content') else str(title_result[0]).strip()
                        logger.info(f"✓ 标题提取成功: {result['title'][:50]}")
                    else:
                        logger.warning("标题XPath未匹配到任何结果")
                except Exception as e:
                    logger.warning(f"标题XPath解析失败: {e}")
            else:
                logger.debug("规则未配置标题XPath")

            # 提取正文
            if rule.content_xpath:
                try:
                    logger.debug(f"尝试内容XPath: {rule.content_xpath}")
                    content_result = tree.xpath(rule.content_xpath)
                    logger.debug(f"内容XPath返回 {len(content_result) if content_result else 0} 个结果")
                    if content_result:
                        texts = []
                        for idx, item in enumerate(content_result):
                            if isinstance(item, str):
                                text = item.strip()
                            else:
                                text = item.text_content().strip() if hasattr(item, 'text_content') else str(item).strip()
                            if text:
                                texts.append(text)
                                if idx < 3:  # 只记录前3个段落的日志
                                    logger.debug(f"段落 {idx+1}: {text[:100]}...")

                        if texts:
                            result['content'] = '\n\n'.join(texts)
                            logger.info(f"✓ 内容提取成功: 共{len(texts)}个段落, 总长度{len(result['content'])}")
                        else:
                            logger.warning("XPath匹配到元素但提取内容为空")
                    else:
                        logger.warning("内容XPath未匹配到任何结果")
                except Exception as e:
                    logger.warning(f"内容XPath解析失败: {e}")
            else:
                logger.debug("规则未配置内容XPath")

            # 如果XPath没有提取到内容,使用通用方法补充
            if not result['content']:
                logger.info("XPath未提取到内容,尝试使用通用方法")
                generic = self._parse_generic(html)
                if generic['content']:
                    result['content'] = generic['content']
                    logger.info(f"通用方法提取成功: 长度{len(result['content'])}")
                else:
                    logger.warning("通用方法也未能提取到内容")

            # 提取时间和作者(通用方法)
            if not result['title'] or not result['publish_time'] or not result['author']:
                generic = self._parse_generic(html)
                if not result['title'] and generic.get('title'):
                    result['title'] = generic['title']
                    logger.debug(f"使用通用方法补充标题: {result['title'][:50]}")
                if not result['publish_time'] and generic.get('publish_time'):
                    result['publish_time'] = generic['publish_time']
                    logger.debug(f"使用通用方法提取时间: {result['publish_time']}")
                if not result['author'] and generic.get('author'):
                    result['author'] = generic['author']
                    logger.debug(f"使用通用方法提取作者: {result['author']}")

        except Exception as e:
            logger.error(f"XPath解析异常: {e}", exc_info=True)
            # 降级到通用解析
            logger.info("降级到通用解析")
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
