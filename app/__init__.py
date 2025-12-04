# -*- coding: utf-8 -*-
"""应用工厂"""
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from config import config

db = SQLAlchemy()
migrate = Migrate()


def create_app(config_name='default'):
    """创建应用实例"""
    app = Flask(__name__,
                static_folder='../static',
                template_folder='templates')

    app.config.from_object(config[config_name])

    # 初始化扩展
    db.init_app(app)
    migrate.init_app(app, db)

    # 注册蓝图
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    return app
