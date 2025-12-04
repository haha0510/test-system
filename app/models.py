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
