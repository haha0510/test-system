# -*- coding: utf-8 -*-
"""数据模型"""
from app import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


class User(db.Model):
    """用户模型"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='user')  # admin / user
    status = db.Column(db.Integer, default=1)  # 1:启用 0:禁用
    login_attempts = db.Column(db.Integer, default=0)  # 登录失败次数
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def set_password(self, password):
        """设置密码（加密存储）"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """验证密码"""
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        """是否为管理员"""
        return self.role == 'admin'

    def __repr__(self):
        return f'<User {self.username}>'

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'role_name': '管理员' if self.role == 'admin' else '普通用户',
            'status': self.status,
            'status_name': '启用' if self.status == 1 else '禁用',
            'last_login': self.last_login.strftime('%Y-%m-%d %H:%M:%S') if self.last_login else '-',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }


class SystemConfig(db.Model):
    """系统配置"""
    __tablename__ = 'system_config'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    @staticmethod
    def get_config(key, default=None):
        """获取配置值"""
        config = SystemConfig.query.filter_by(key=key).first()
        return config.value if config else default

    @staticmethod
    def set_config(key, value):
        """设置配置值"""
        config = SystemConfig.query.filter_by(key=key).first()
        if config:
            config.value = value
        else:
            config = SystemConfig(key=key, value=value)
            db.session.add(config)
        db.session.commit()


class CrawlRule(db.Model):
    """采集规则库"""
    __tablename__ = 'crawl_rules'

    id = db.Column(db.Integer, primary_key=True)
    site_name = db.Column(db.String(100), nullable=False)  # 规则名称
    site_domain = db.Column(db.String(200), nullable=False)  # 站点域名
    applicable_sources = db.Column(db.Text)  # 适用来源列表（JSON数组格式，如["百度新闻","360新闻"]）
    title_xpath = db.Column(db.String(500))  # 标题xpath
    content_xpath = db.Column(db.String(500))  # 详细内容xpath
    request_headers = db.Column(db.Text)  # request headers (JSON格式存储)
    priority = db.Column(db.Integer, default=0)  # 优先级，数字越大优先级越高
    success_count = db.Column(db.Integer, default=0)  # 成功采集次数
    fail_count = db.Column(db.Integer, default=0)  # 失败采集次数
    status = db.Column(db.Integer, default=1)  # 1:启用 0:禁用
    description = db.Column(db.Text)  # 规则描述/备注
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f'<CrawlRule {self.site_name}>'

    def get_applicable_sources(self):
        """获取适用来源列表"""
        import json
        if self.applicable_sources:
            try:
                return json.loads(self.applicable_sources)
            except:
                return []
        return []

    def set_applicable_sources(self, sources):
        """设置适用来源列表"""
        import json
        if isinstance(sources, list):
            self.applicable_sources = json.dumps(sources, ensure_ascii=False)
        elif isinstance(sources, str):
            self.applicable_sources = sources

    def to_dict(self):
        import json
        headers = {}
        if self.request_headers:
            try:
                headers = json.loads(self.request_headers)
            except:
                headers = {}

        sources = self.get_applicable_sources()

        return {
            'id': self.id,
            'site_name': self.site_name,
            'site_domain': self.site_domain,
            'applicable_sources': sources,
            'applicable_sources_str': ', '.join(sources) if sources else '未配置',
            'title_xpath': self.title_xpath,
            'content_xpath': self.content_xpath,
            'request_headers': headers,
            'request_headers_str': self.request_headers or '',
            'priority': self.priority,
            'success_count': self.success_count,
            'fail_count': self.fail_count,
            'success_rate': f"{self.success_count / (self.success_count + self.fail_count) * 100:.1f}%" if (self.success_count + self.fail_count) > 0 else '-',
            'status': self.status,
            'status_name': '启用' if self.status == 1 else '禁用',
            'description': self.description,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        }


class CollectedNews(db.Model):
    """采集的新闻数据"""
    __tablename__ = 'collected_news'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)  # 新闻标题
    summary = db.Column(db.Text)  # 新闻概要
    cover = db.Column(db.String(1000))  # 封面图片URL
    url = db.Column(db.String(1000), nullable=False)  # 原始URL
    source = db.Column(db.String(100))  # 来源
    keyword = db.Column(db.String(100))  # 采集关键词

    # 深度采集数据
    content = db.Column(db.Text)  # 正文内容
    publish_time = db.Column(db.String(50))  # 发布时间
    author = db.Column(db.String(100))  # 作者
    deep_collected = db.Column(db.Boolean, default=False)  # 是否已深度采集
    deep_collected_at = db.Column(db.DateTime)  # 深度采集时间
    rule_id = db.Column(db.Integer, db.ForeignKey('crawl_rules.id'))  # 使用的采集规则ID
    rule_used = db.Column(db.String(100))  # 使用的采集规则名称

    # 元数据
    collected_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # 采集人
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联
    collector = db.relationship('User', backref=db.backref('collected_news', lazy='dynamic'))
    rule = db.relationship('CrawlRule', backref=db.backref('collected_news', lazy='dynamic'))

    def __repr__(self):
        return f'<CollectedNews {self.title[:20]}...>'

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'summary': self.summary,
            'cover': self.cover,
            'url': self.url,
            'source': self.source,
            'keyword': self.keyword,
            'content': self.content,
            'publish_time': self.publish_time,
            'author': self.author,
            'deep_collected': self.deep_collected,
            'deep_collected_at': self.deep_collected_at.strftime('%Y-%m-%d %H:%M:%S') if self.deep_collected_at else None,
            'rule_id': self.rule_id,
            'rule_used': self.rule_used,
            'collected_by': self.collected_by,
            'collector_name': self.collector.username if self.collector else '-',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }


class AIEngine(db.Model):
    """AI引擎配置"""
    __tablename__ = 'ai_engines'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # 引擎名称
    provider = db.Column(db.String(100), nullable=False)  # 服务商名称
    api_url = db.Column(db.String(500), nullable=False)  # API地址
    api_key = db.Column(db.String(500), nullable=False)  # API密钥
    model_name = db.Column(db.String(100), nullable=False)  # 模型名称
    description = db.Column(db.Text)  # 描述
    icon = db.Column(db.String(50))  # 图标（用于展示）
    color = db.Column(db.String(50))  # 主题色
    status = db.Column(db.Integer, default=1)  # 1:启用 0:禁用
    is_default = db.Column(db.Boolean, default=False)  # 是否默认引擎
    max_tokens = db.Column(db.Integer, default=4096)  # 最大token数
    temperature = db.Column(db.Float, default=0.7)  # 温度参数
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f'<AIEngine {self.name}>'

    def to_dict(self, hide_key=True):
        return {
            'id': self.id,
            'name': self.name,
            'provider': self.provider,
            'api_url': self.api_url,
            'api_key': self.api_key[:8] + '****' + self.api_key[-4:] if hide_key and self.api_key and len(self.api_key) > 12 else ('****' if hide_key else self.api_key),
            'api_key_full': self.api_key if not hide_key else None,
            'model_name': self.model_name,
            'description': self.description,
            'icon': self.icon or 'layui-icon-auz',
            'color': self.color or '#667eea',
            'status': self.status,
            'status_name': '启用' if self.status == 1 else '禁用',
            'is_default': self.is_default,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        }


class CrawlerConfig(db.Model):
    """爬虫配置"""
    __tablename__ = 'crawler_configs'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # 爬虫名称（显示名）
    code = db.Column(db.String(50), unique=True, nullable=False)  # 爬虫代码标识（如 baidu, 360kuai）
    description = db.Column(db.Text)  # 描述
    icon = db.Column(db.String(50))  # 图标
    color = db.Column(db.String(50))  # 主题色

    # 爬虫配置
    base_url = db.Column(db.String(500))  # 基础URL
    search_url = db.Column(db.String(500))  # 搜索接口URL
    crawler_class = db.Column(db.String(100))  # 爬虫类名（如 BaiduNewsCrawler）
    crawler_module = db.Column(db.String(100))  # 爬虫模块名（如 app.crawler）

    # 请求配置
    default_headers = db.Column(db.Text)  # 默认请求头（JSON格式）
    request_delay = db.Column(db.Float, default=0.5)  # 请求间隔（秒）
    timeout = db.Column(db.Integer, default=15)  # 超时时间（秒）
    max_pages = db.Column(db.Integer, default=10)  # 最大翻页数

    # 状态
    status = db.Column(db.Integer, default=1)  # 1:启用 0:禁用
    is_builtin = db.Column(db.Boolean, default=False)  # 是否内置爬虫
    sort_order = db.Column(db.Integer, default=0)  # 排序顺序

    # 统计
    success_count = db.Column(db.Integer, default=0)  # 成功采集次数
    fail_count = db.Column(db.Integer, default=0)  # 失败次数
    last_used_at = db.Column(db.DateTime)  # 最后使用时间

    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f'<CrawlerConfig {self.name}>'

    def to_dict(self):
        import json
        headers = {}
        if self.default_headers:
            try:
                headers = json.loads(self.default_headers)
            except:
                headers = {}

        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'description': self.description,
            'icon': self.icon or 'layui-icon-website',
            'color': self.color or '#667eea',
            'base_url': self.base_url,
            'search_url': self.search_url,
            'crawler_class': self.crawler_class,
            'crawler_module': self.crawler_module,
            'default_headers': headers,
            'default_headers_str': self.default_headers or '',
            'request_delay': self.request_delay,
            'timeout': self.timeout,
            'max_pages': self.max_pages,
            'status': self.status,
            'status_name': '启用' if self.status == 1 else '禁用',
            'is_builtin': self.is_builtin,
            'sort_order': self.sort_order,
            'success_count': self.success_count,
            'fail_count': self.fail_count,
            'success_rate': f"{self.success_count / (self.success_count + self.fail_count) * 100:.1f}%" if (self.success_count + self.fail_count) > 0 else '-',
            'last_used_at': self.last_used_at.strftime('%Y-%m-%d %H:%M:%S') if self.last_used_at else '-',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        }
