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

    # 元数据
    collected_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # 采集人
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联用户
    collector = db.relationship('User', backref=db.backref('collected_news', lazy='dynamic'))

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
            'collected_by': self.collected_by,
            'collector_name': self.collector.username if self.collector else '-',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }
