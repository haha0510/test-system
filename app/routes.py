# -*- coding: utf-8 -*-
"""路由定义"""
from functools import wraps
from datetime import datetime
from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for
from app import db
from app.models import User, SystemConfig

main_bp = Blueprint('main', __name__)

# 最大登录失败次数
MAX_LOGIN_ATTEMPTS = 5


def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'code': 401, 'msg': '请先登录'})
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """管理员权限装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'code': 401, 'msg': '请先登录'})
            return redirect(url_for('main.login'))
        if session.get('role') != 'admin':
            if request.is_json:
                return jsonify({'code': 403, 'msg': '无权限访问'})
            return render_template('403.html'), 403
        return f(*args, **kwargs)
    return decorated_function


# ============ 页面路由 ============

@main_bp.route('/')
def index():
    """首页重定向到登录"""
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('main.login'))


@main_bp.route('/login')
def login():
    """登录页面"""
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return render_template('login.html')


@main_bp.route('/admin/dashboard')
@login_required
def dashboard():
    """后台仪表盘"""
    return render_template('admin/dashboard.html')


@main_bp.route('/admin/news')
@login_required
def news_crawler():
    """新闻采集页面"""
    return render_template('admin/news.html')


@main_bp.route('/admin/users')
@admin_required
def user_manage():
    """用户管理页面"""
    return render_template('admin/users.html')


@main_bp.route('/admin/settings')
@admin_required
def system_settings():
    """系统设置页面"""
    return render_template('admin/settings.html')


# ============ API路由 ============

@main_bp.route('/api/health')
def health_check():
    """健康检查接口"""
    return jsonify({'code': 0, 'msg': '系统运行正常'})


@main_bp.route('/api/auth/login', methods=['POST'])
def api_login():
    """登录接口"""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'code': 1, 'msg': '请输入用户名和密码'})

    user = User.query.filter_by(username=username).first()

    if not user:
        return jsonify({'code': 1, 'msg': '用户名或密码不正确'})

    # 检查账户状态
    if user.status == 0:
        return jsonify({'code': 1, 'msg': '账户已被禁用，请联系管理员'})

    # 检查登录失败次数
    if user.login_attempts >= MAX_LOGIN_ATTEMPTS:
        return jsonify({'code': 1, 'msg': '登录失败次数过多，账户已锁定'})

    # 验证密码
    if not user.check_password(password):
        user.login_attempts += 1
        db.session.commit()
        remaining = MAX_LOGIN_ATTEMPTS - user.login_attempts
        if remaining > 0:
            return jsonify({'code': 1, 'msg': f'用户名或密码不正确，还可尝试{remaining}次'})
        else:
            return jsonify({'code': 1, 'msg': '登录失败次数过多，账户已锁定'})

    # 登录成功
    user.login_attempts = 0
    user.last_login = datetime.now()
    db.session.commit()

    # 设置会话
    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role

    return jsonify({
        'code': 0,
        'msg': '登录成功',
        'data': {
            'username': user.username,
            'role': user.role
        }
    })


@main_bp.route('/api/auth/logout', methods=['POST'])
@login_required
def api_logout():
    """退出登录"""
    session.clear()
    return jsonify({'code': 0, 'msg': '已退出登录'})


@main_bp.route('/api/auth/info')
@login_required
def api_user_info():
    """获取当前用户信息"""
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return jsonify({'code': 401, 'msg': '用户不存在'})
    return jsonify({'code': 0, 'data': user.to_dict()})


# ============ 用户管理API（管理员） ============

@main_bp.route('/api/users', methods=['GET'])
@admin_required
def api_get_users():
    """获取用户列表"""
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    username = request.args.get('username', '')

    query = User.query
    if username:
        query = query.filter(User.username.like(f'%{username}%'))

    pagination = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=limit, error_out=False
    )

    return jsonify({
        'code': 0,
        'count': pagination.total,
        'data': [u.to_dict() for u in pagination.items]
    })


@main_bp.route('/api/users', methods=['POST'])
@admin_required
def api_add_user():
    """新增用户"""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'user')

    if not username or not password:
        return jsonify({'code': 1, 'msg': '用户名和密码不能为空'})

    if User.query.filter_by(username=username).first():
        return jsonify({'code': 1, 'msg': '用户名已存在'})

    user = User(username=username, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({'code': 0, 'msg': '添加成功'})


@main_bp.route('/api/users/<int:user_id>', methods=['PUT'])
@admin_required
def api_update_user(user_id):
    """更新用户"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'code': 1, 'msg': '用户不存在'})

    data = request.get_json()

    # 更新角色
    if 'role' in data:
        user.role = data['role']

    # 重置密码
    if 'password' in data and data['password']:
        user.set_password(data['password'])

    # 更新状态
    if 'status' in data:
        user.status = data['status']
        if data['status'] == 1:
            user.login_attempts = 0  # 启用时重置登录失败次数

    db.session.commit()
    return jsonify({'code': 0, 'msg': '更新成功'})


@main_bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@admin_required
def api_delete_user(user_id):
    """删除用户"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'code': 1, 'msg': '用户不存在'})

    if user.id == session.get('user_id'):
        return jsonify({'code': 1, 'msg': '不能删除自己'})

    db.session.delete(user)
    db.session.commit()
    return jsonify({'code': 0, 'msg': '删除成功'})


# ============ 系统配置API（管理员） ============

@main_bp.route('/api/settings', methods=['GET'])
@admin_required
def api_get_settings():
    """获取系统配置"""
    return jsonify({
        'code': 0,
        'data': {
            'app_name': SystemConfig.get_config('app_name', '政企智能舆情分析系统'),
            'logo_url': SystemConfig.get_config('logo_url', '')
        }
    })


@main_bp.route('/api/settings', methods=['POST'])
@admin_required
def api_save_settings():
    """保存系统配置"""
    data = request.get_json()

    if 'app_name' in data:
        SystemConfig.set_config('app_name', data['app_name'])

    if 'logo_url' in data:
        SystemConfig.set_config('logo_url', data['logo_url'])

    return jsonify({'code': 0, 'msg': '保存成功'})


# ============ 新闻抓取API ============

@main_bp.route('/api/news/search', methods=['GET', 'POST'])
@login_required
def api_search_news():
    """
    搜索新闻接口

    GET请求参数:
        - keyword: 搜索关键字（必填）
        - page: 页码，默认1（与count二选一）
        - count: 目标获取数量，设置后自动翻页获取

    POST请求JSON:
        - keyword: 搜索关键字（必填）
        - page: 页码，默认1
        - count: 目标获取数量

    返回数据格式:
        {
            "code": 0,
            "msg": "success",
            "data": [
                {
                    "title": "新闻标题",
                    "summary": "新闻概要",
                    "cover": "封面图片URL",
                    "url": "原始URL",
                    "source": "来源"
                },
                ...
            ]
        }
    """
    from app.crawler import search_news

    # 支持GET和POST两种方式
    if request.method == 'POST':
        data = request.get_json() or {}
        keyword = data.get('keyword', '').strip()
        page = data.get('page', 1)
        count = data.get('count')  # 目标数量
    else:
        keyword = request.args.get('keyword', '').strip()
        page = request.args.get('page', 1, type=int)
        count = request.args.get('count', type=int)  # 目标数量

    if not keyword:
        return jsonify({'code': 1, 'msg': '请输入搜索关键字'})

    try:
        # 如果指定了 count，则批量获取；否则按页码获取
        if count is not None:
            news_list = search_news(keyword, count=count)
        else:
            news_list = search_news(keyword, page=page)

        return jsonify({
            'code': 0,
            'msg': 'success',
            'count': len(news_list),
            'data': news_list
        })
    except Exception as e:
        return jsonify({'code': 1, 'msg': f'抓取失败: {str(e)}'})
