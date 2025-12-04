# -*- coding: utf-8 -*-
"""应用入口"""
import click
from app import create_app, db
from app.models import User, SystemConfig

app = create_app('development')


@app.shell_context_processor
def make_shell_context():
    """Flask shell 上下文"""
    return {'db': db, 'User': User, 'SystemConfig': SystemConfig}


@app.cli.command('init-db')
def init_db():
    """初始化数据库"""
    db.create_all()
    click.echo('数据库表创建成功！')


@app.cli.command('create-admin')
@click.option('--username', default='admin', help='管理员用户名')
@click.option('--password', default='admin123', help='管理员密码')
def create_admin(username, password):
    """创建管理员账户"""
    if User.query.filter_by(username=username).first():
        click.echo(f'用户 {username} 已存在！')
        return

    admin = User(username=username, role='admin')
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    click.echo(f'管理员账户创建成功！用户名: {username}, 密码: {password}')


def init_database():
    """初始化数据库和默认数据"""
    with app.app_context():
        # 创建所有表
        db.create_all()

        # 检查是否存在管理员
        if not User.query.filter_by(role='admin').first():
            admin = User(username='admin', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print('默认管理员账户已创建: admin / admin123')

        # 初始化系统配置
        if not SystemConfig.query.filter_by(key='app_name').first():
            SystemConfig.set_config('app_name', '政企智能舆情分析系统')
            print('系统配置已初始化')


if __name__ == '__main__':
    # 启动前初始化数据库
    init_database()
    app.run(host='0.0.0.0', port=5000, debug=True)
