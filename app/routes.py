# -*- coding: utf-8 -*-
"""路由定义"""
from functools import wraps
from datetime import datetime
from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for
from app import db
from app.models import User, SystemConfig, CollectedNews

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


@main_bp.route('/admin/data-collect')
@login_required
def data_collect():
    """数据采集管理页面"""
    return render_template('admin/data_collect.html')


@main_bp.route('/admin/data-warehouse')
@login_required
def data_warehouse():
    """数据仓库管理页面"""
    return render_template('admin/data_warehouse.html')


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
    搜索新闻接口（支持多数据源）

    请求参数:
        - keyword: 搜索关键字（必填）
        - page: 页码，默认1
        - count: 目标获取数量，设置后自动翻页获取
        - source: 数据源，可选值: baidu(默认), 360kuai

    返回数据格式:
        {
            "code": 0,
            "msg": "success",
            "source": "baidu",
            "data": [...]
        }
    """
    # 支持GET和POST两种方式
    if request.method == 'POST':
        data = request.get_json() or {}
        keyword = data.get('keyword', '').strip()
        page = data.get('page', 1)
        count = data.get('count')
        source = data.get('source', 'baidu')
    else:
        keyword = request.args.get('keyword', '').strip()
        page = request.args.get('page', 1, type=int)
        count = request.args.get('count', type=int)
        source = request.args.get('source', 'baidu')

    if not keyword:
        return jsonify({'code': 1, 'msg': '请输入搜索关键字'})

    try:
        # 根据数据源选择爬虫
        if source == '360kuai':
            from app.crawler_360kuai import search_360kuai_news
            if count is not None:
                news_list = search_360kuai_news(keyword, count=count)
            else:
                news_list = search_360kuai_news(keyword, page=page)
            source_name = '360新闻'
        else:
            from app.crawler import search_news
            if count is not None:
                news_list = search_news(keyword, count=count)
            else:
                news_list = search_news(keyword, page=page)
            source_name = '百度新闻'

        return jsonify({
            'code': 0,
            'msg': 'success',
            'source': source,
            'source_name': source_name,
            'count': len(news_list),
            'data': news_list
        })
    except Exception as e:
        return jsonify({'code': 1, 'msg': f'抓取失败: {str(e)}'})


# ============ 数据采集管理API ============

@main_bp.route('/api/collect/deep', methods=['POST'])
@login_required
def api_deep_collect():
    """
    深度采集单条新闻
    请求参数: { url: "新闻原始URL" }
    """
    from app.crawler import deep_collect

    data = request.get_json() or {}
    url = data.get('url', '').strip()

    if not url:
        return jsonify({'code': 1, 'msg': '请提供新闻URL'})

    try:
        result = deep_collect(url)
        return jsonify({
            'code': 0,
            'msg': 'success',
            'data': result
        })
    except Exception as e:
        return jsonify({'code': 1, 'msg': f'深度采集失败: {str(e)}'})


@main_bp.route('/api/collect/save', methods=['POST'])
@login_required
def api_save_news():
    """
    保存单条采集数据到数据库
    """
    data = request.get_json() or {}

    # 必填字段验证
    title = data.get('title', '').strip()
    url = data.get('url', '').strip()

    if not title or not url:
        return jsonify({'code': 1, 'msg': '标题和URL不能为空'})

    # 检查是否已存在
    existing = CollectedNews.query.filter_by(url=url).first()
    if existing:
        return jsonify({'code': 1, 'msg': '该新闻已存在于数据库中'})

    try:
        news = CollectedNews(
            title=title,
            summary=data.get('summary', ''),
            cover=data.get('cover', ''),
            url=url,
            source=data.get('source', ''),
            keyword=data.get('keyword', ''),
            content=data.get('content', ''),
            publish_time=data.get('publish_time', ''),
            author=data.get('author', ''),
            deep_collected=data.get('deep_collected', False),
            collected_by=session.get('user_id')
        )
        db.session.add(news)
        db.session.commit()

        return jsonify({'code': 0, 'msg': '保存成功', 'data': news.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'保存失败: {str(e)}'})


@main_bp.route('/api/collect/save-batch', methods=['POST'])
@login_required
def api_save_news_batch():
    """
    批量保存采集数据到数据库
    请求参数: { items: [...] }
    """
    data = request.get_json() or {}
    items = data.get('items', [])

    if not items:
        return jsonify({'code': 1, 'msg': '没有要保存的数据'})

    saved_count = 0
    skipped_count = 0
    errors = []

    for item in items:
        title = item.get('title', '').strip()
        url = item.get('url', '').strip()

        if not title or not url:
            skipped_count += 1
            continue

        # 检查是否已存在
        if CollectedNews.query.filter_by(url=url).first():
            skipped_count += 1
            continue

        try:
            news = CollectedNews(
                title=title,
                summary=item.get('summary', ''),
                cover=item.get('cover', ''),
                url=url,
                source=item.get('source', ''),
                keyword=item.get('keyword', ''),
                content=item.get('content', ''),
                publish_time=item.get('publish_time', ''),
                author=item.get('author', ''),
                deep_collected=item.get('deep_collected', False),
                collected_by=session.get('user_id')
            )
            db.session.add(news)
            saved_count += 1
        except Exception as e:
            errors.append(str(e))

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'批量保存失败: {str(e)}'})

    return jsonify({
        'code': 0,
        'msg': f'保存完成：成功 {saved_count} 条，跳过 {skipped_count} 条',
        'data': {
            'saved': saved_count,
            'skipped': skipped_count
        }
    })


@main_bp.route('/api/collect/list', methods=['GET'])
@login_required
def api_get_collected_news():
    """
    获取已保存的采集数据列表
    """
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    keyword = request.args.get('keyword', '')

    query = CollectedNews.query

    if keyword:
        query = query.filter(
            db.or_(
                CollectedNews.title.like(f'%{keyword}%'),
                CollectedNews.keyword.like(f'%{keyword}%')
            )
        )

    pagination = query.order_by(CollectedNews.created_at.desc()).paginate(
        page=page, per_page=limit, error_out=False
    )

    return jsonify({
        'code': 0,
        'count': pagination.total,
        'data': [n.to_dict() for n in pagination.items]
    })


@main_bp.route('/api/collect/<int:news_id>', methods=['DELETE'])
@login_required
def api_delete_collected_news(news_id):
    """
    删除已保存的采集数据
    """
    news = CollectedNews.query.get(news_id)
    if not news:
        return jsonify({'code': 1, 'msg': '数据不存在'})

    try:
        db.session.delete(news)
        db.session.commit()
        return jsonify({'code': 0, 'msg': '删除成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'删除失败: {str(e)}'})


@main_bp.route('/api/collect/<int:news_id>', methods=['GET'])
@login_required
def api_get_collected_news_detail(news_id):
    """
    获取单条采集数据详情
    """
    news = CollectedNews.query.get(news_id)
    if not news:
        return jsonify({'code': 1, 'msg': '数据不存在'})

    return jsonify({'code': 0, 'data': news.to_dict()})


# ============ 数据仓库管理API ============

@main_bp.route('/api/warehouse/list', methods=['GET'])
@login_required
def api_warehouse_list():
    """
    获取数据仓库列表（支持分页、搜索、筛选）
    """
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    keyword = request.args.get('keyword', '').strip()
    source = request.args.get('source', '').strip()
    deep_collected = request.args.get('deep_collected', '').strip()

    query = CollectedNews.query

    # 关键词搜索
    if keyword:
        query = query.filter(
            db.or_(
                CollectedNews.title.like(f'%{keyword}%'),
                CollectedNews.keyword.like(f'%{keyword}%'),
                CollectedNews.summary.like(f'%{keyword}%')
            )
        )

    # 来源筛选
    if source:
        query = query.filter(CollectedNews.source == source)

    # 深度采集状态筛选
    if deep_collected:
        query = query.filter(CollectedNews.deep_collected == (deep_collected == '1'))

    # 分页
    pagination = query.order_by(CollectedNews.created_at.desc()).paginate(
        page=page, per_page=limit, error_out=False
    )

    return jsonify({
        'code': 0,
        'count': pagination.total,
        'data': [n.to_dict() for n in pagination.items]
    })


@main_bp.route('/api/warehouse/stats', methods=['GET'])
@login_required
def api_warehouse_stats():
    """
    获取数据仓库统计信息
    """
    from sqlalchemy import func
    from datetime import datetime, timedelta

    # 总数
    total = CollectedNews.query.count()

    # 已深度采集数
    deep_collected = CollectedNews.query.filter_by(deep_collected=True).count()

    # 今日新增
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = CollectedNews.query.filter(CollectedNews.created_at >= today).count()

    # 数据来源数量
    sources = db.session.query(func.count(func.distinct(CollectedNews.source))).scalar() or 0

    return jsonify({
        'code': 0,
        'data': {
            'total': total,
            'deep_collected': deep_collected,
            'today': today_count,
            'sources': sources
        }
    })


@main_bp.route('/api/warehouse/update', methods=['POST'])
@login_required
def api_warehouse_update():
    """
    更新数据仓库中的记录
    """
    data = request.get_json() or {}
    news_id = data.get('id')

    if not news_id:
        return jsonify({'code': 1, 'msg': '缺少数据ID'})

    news = CollectedNews.query.get(news_id)
    if not news:
        return jsonify({'code': 1, 'msg': '数据不存在'})

    try:
        # 更新字段
        if 'title' in data:
            news.title = data['title'].strip()
        if 'summary' in data:
            news.summary = data['summary'].strip()
        if 'source' in data:
            news.source = data['source'].strip()
        if 'keyword' in data:
            news.keyword = data['keyword'].strip()
        if 'cover' in data:
            news.cover = data['cover'].strip()
        if 'url' in data:
            news.url = data['url'].strip()
        if 'content' in data:
            news.content = data['content'].strip()

        db.session.commit()
        return jsonify({'code': 0, 'msg': '更新成功', 'data': news.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'更新失败: {str(e)}'})


@main_bp.route('/api/warehouse/delete-batch', methods=['POST'])
@login_required
def api_warehouse_delete_batch():
    """
    批量删除数据
    """
    data = request.get_json() or {}
    ids = data.get('ids', [])

    if not ids:
        return jsonify({'code': 1, 'msg': '请选择要删除的数据'})

    try:
        deleted = CollectedNews.query.filter(CollectedNews.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({'code': 0, 'msg': f'成功删除 {deleted} 条数据'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'删除失败: {str(e)}'})


@main_bp.route('/api/warehouse/ai-analyze', methods=['POST'])
@login_required
def api_warehouse_ai_analyze():
    """
    AI分析接口（预留）
    """
    data = request.get_json() or {}
    news_ids = data.get('ids', [])

    # TODO: 实现AI分析功能
    return jsonify({
        'code': 1,
        'msg': 'AI分析功能即将上线，敬请期待...'
    })

