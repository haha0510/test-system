# -*- coding: utf-8 -*-
"""路由定义"""
from functools import wraps
from datetime import datetime
from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for
from app import db
from app.models import User, SystemConfig, CollectedNews, CrawlRule, AIEngine

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


@main_bp.route('/admin/crawl-rules')
@login_required
def crawl_rules():
    """采集规则库页面"""
    return render_template('admin/crawl_rules.html')


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
    session.permanent = True  # 使用配置中的会话过期时间
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
    搜索新闻接口（支持动态爬虫配置）

    请求参数:
        - keyword: 搜索关键字（必填）
        - page: 页码，默认1
        - count: 目标获取数量，设置后自动翻页获取
        - source: 数据源代码（如 baidu, 360kuai）

    返回数据格式:
        {
            "code": 0,
            "msg": "success",
            "source": "baidu",
            "data": [...]
        }
    """
    from app.models import CrawlerConfig
    import importlib

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
        # 从数据库查找爬虫配置
        crawler_config = CrawlerConfig.query.filter_by(code=source, status=1).first()

        if crawler_config and crawler_config.crawler_module and crawler_config.crawler_class:
            # 动态加载爬虫
            module = importlib.import_module(crawler_config.crawler_module)
            crawler_cls = getattr(module, crawler_config.crawler_class)
            crawler_instance = crawler_cls()

            if count is not None:
                news_list = crawler_instance.search_batch(keyword, count=count)
            else:
                news_list = crawler_instance.search(keyword, page=page)

            source_name = crawler_config.name

            # 更新使用统计
            crawler_config.success_count = (crawler_config.success_count or 0) + 1
            crawler_config.last_used_at = datetime.now()
            db.session.commit()
        else:
            # 兼容旧逻辑：使用硬编码的爬虫
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
        # 更新失败统计
        try:
            if 'crawler_config' in locals() and crawler_config:
                crawler_config.fail_count = (crawler_config.fail_count or 0) + 1
                crawler_config.last_error = str(e)
                db.session.commit()
        except Exception as db_err:
            print(f"更新爬虫统计失败: {db_err}")

        # 记录详细错误信息
        import traceback
        print(f"数据采集失败: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'code': 1, 'msg': f'抓取失败: {str(e)}'})


@main_bp.route('/api/data/dynamic-collect', methods=['GET'])
@login_required
def api_dynamic_collect():
    """
    使用动态爬虫进行数据采集
    请求参数: keyword, crawler, count, timeout
    """
    from app.models import CrawlerConfig
    from app.crawler_dynamic import DynamicCrawlerEngine

    keyword = request.args.get('keyword', '').strip()
    crawler_code = request.args.get('crawler', '').strip()

    # 安全处理数值参数
    try:
        count = int(request.args.get('count', 30))
        timeout = int(request.args.get('timeout', 15))
    except ValueError:
        return jsonify({'code': 1, 'msg': '参数格式错误'})

    if not keyword:
        return jsonify({'code': 1, 'msg': '请输入搜索关键词'})

    if not crawler_code:
        return jsonify({'code': 1, 'msg': '请选择采集源'})

    try:
        crawler_config = CrawlerConfig.query.filter_by(code=crawler_code).first()
        if not crawler_config:
            return jsonify({'code': 1, 'msg': '爬虫配置不存在'})

        if crawler_config.status != 1:
            return jsonify({'code': 1, 'msg': '爬虫已被禁用'})

        print(f"动态采集: 爬虫={crawler_code}, 关键词={keyword}, 数量={count}")

        engine = DynamicCrawlerEngine(crawler_config.to_dict())
        results = engine.search_batch(keyword, count=count)

        print(f"动态采集: 成功获取 {len(results)} 条数据")

        # 更新爬虫统计
        crawler_config.success_count = (crawler_config.success_count or 0) + 1
        crawler_config.last_used_at = datetime.now()
        crawler_config.last_error = None
        db.session.commit()

        # 返回数据
        return jsonify({
            'code': 0,
            'msg': f'采集成功，获取到 {len(results)} 条数据',
            'data': {
                'keyword': keyword,
                'source': crawler_config.name,
                'count': len(results),
                'list': results
            }
        })

    except Exception as e:
        # 更新失败统计
        if 'crawler_config' in locals() and crawler_config:
            try:
                crawler_config.fail_count = (crawler_config.fail_count or 0) + 1
                crawler_config.last_used_at = datetime.now()
                crawler_config.last_error = str(e)
                db.session.commit()
            except Exception as db_err:
                print(f"更新爬虫统计失败: {db_err}")

        # 记录详细错误信息
        import traceback
        print(f"❌ 动态采集失败: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'code': 1, 'msg': f'采集失败: {str(e)}'})


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
        import traceback
        print(f"深度采集失败: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'code': 1, 'msg': f'深度采集失败: {str(e)}'})


@main_bp.route('/api/collect/save', methods=['POST'])
@login_required
def api_save_news():
    """
    保存单条采集数据到数据库（自动进行深度采集）
    """
    from app.deep_crawler import RuleBasedCrawler

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
        source = data.get('source', '')

        # 先进行深度采集
        crawler = RuleBasedCrawler(db)
        deep_result = crawler.deep_collect(url, source)

        # 创建新闻记录
        news = CollectedNews(
            title=deep_result.get('title') or title,  # 优先使用深度采集的标题
            summary=data.get('summary', ''),
            cover=data.get('cover', ''),
            url=url,
            source=source,
            keyword=data.get('keyword', ''),
            content=deep_result.get('content') or data.get('content', ''),
            publish_time=deep_result.get('publish_time') or data.get('publish_time', ''),
            author=deep_result.get('author') or data.get('author', ''),
            deep_collected=deep_result.get('success', False),
            deep_collected_at=datetime.now() if deep_result.get('success') else None,
            rule_used=deep_result.get('rule_used') if deep_result.get('success') else None,
            collected_by=session.get('user_id')
        )
        db.session.add(news)
        db.session.commit()

        msg = '保存成功'
        if deep_result.get('success'):
            msg += f'（已深度采集，规则：{deep_result.get("rule_used", "通用")}）'
        else:
            msg += '（深度采集失败，已保存基础信息）'

        return jsonify({'code': 0, 'msg': msg, 'data': news.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'保存失败: {str(e)}'})


@main_bp.route('/api/collect/save-batch', methods=['POST'])
@login_required
def api_save_news_batch():
    """
    批量保存采集数据到数据库（自动进行深度采集）
    请求参数: { items: [...] }
    """
    from app.deep_crawler import RuleBasedCrawler
    import time

    data = request.get_json() or {}
    items = data.get('items', [])

    if not items:
        return jsonify({'code': 1, 'msg': '没有要保存的数据'})

    crawler = RuleBasedCrawler(db)
    saved_count = 0
    skipped_count = 0
    deep_success_count = 0
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
            source = item.get('source', '')

            # 进行深度采集
            deep_result = crawler.deep_collect(url, source)

            news = CollectedNews(
                title=deep_result.get('title') or title,
                summary=item.get('summary', ''),
                cover=item.get('cover', ''),
                url=url,
                source=source,
                keyword=item.get('keyword', ''),
                content=deep_result.get('content') or item.get('content', ''),
                publish_time=deep_result.get('publish_time') or item.get('publish_time', ''),
                author=deep_result.get('author') or item.get('author', ''),
                deep_collected=deep_result.get('success', False),
                deep_collected_at=datetime.now() if deep_result.get('success') else None,
                rule_used=deep_result.get('rule_used') if deep_result.get('success') else None,
                collected_by=session.get('user_id')
            )
            db.session.add(news)
            saved_count += 1
            if deep_result.get('success'):
                deep_success_count += 1

            # 每次请求间隔，避免被封
            time.sleep(0.3)
        except Exception as e:
            errors.append(str(e))

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'批量保存失败: {str(e)}'})

    return jsonify({
        'code': 0,
        'msg': f'保存完成：成功 {saved_count} 条（深度采集成功 {deep_success_count} 条），跳过 {skipped_count} 条',
        'data': {
            'saved': saved_count,
            'deep_collected': deep_success_count,
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
    rule = request.args.get('rule', '').strip()  # 按规则名筛选

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

    # 按规则名筛选
    if rule:
        query = query.filter(CollectedNews.rule_used == rule)

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
    """AI分析新闻数据 - SSE流式响应"""
    import requests
    import json
    from flask import Response, stream_with_context
    from app.models import AIEngine

    data = request.get_json() or {}
    news_ids = data.get('ids', [])

    # 基本验证
    if not news_ids:
        return jsonify({'code': 1, 'msg': '请选择要分析的新闻'})

    # 获取新闻数据
    news_list = CollectedNews.query.filter(CollectedNews.id.in_(news_ids)).all()
    if not news_list:
        return jsonify({'code': 1, 'msg': '未找到选中的新闻'})

    # 获取默认AI引擎
    engine = AIEngine.query.filter_by(is_default=True, status=1).first()
    if not engine:
        engine = AIEngine.query.filter_by(status=1).first()

    if not engine:
        return jsonify({'code': 1, 'msg': '没有可用的AI引擎，请先配置AI引擎'})

    # 构建分析内容
    news_content = []
    for i, news in enumerate(news_list, 1):
        news_content.append(f"【新闻{i}】")
        news_content.append(f"标题: {news.title}")
        news_content.append(f"来源: {news.source}")
        news_content.append(f"发布时间: {news.publish_time or '未知'}")
        if news.summary:
            news_content.append(f"摘要: {news.summary}")
        news_content.append("")

    content_text = "\n".join(news_content)

    # 构建AI提示
    prompt = f"""请对以下{len(news_list)}条新闻进行深度分析：

{content_text}

请从以下几个维度进行分析：
1. **主题概括**: 这些新闻的共同主题和核心观点
2. **趋势分析**: 反映出的行业或社会趋势
3. **舆情态度**: 整体的舆论倾向（正面/中性/负面）
4. **关键信息**: 提取最重要的事实和数据
5. **影响评估**: 可能产生的影响和意义

请用清晰的中文回复，使用Markdown格式。"""

    messages = [
        {'role': 'system', 'content': '你是一个专业的舆情分析师，擅长从多条新闻中提取关键信息、分析趋势和评估影响。'},
        {'role': 'user', 'content': prompt}
    ]

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {engine.api_key}'
    }

    payload = {
        'model': engine.model_name,
        'messages': messages,
        'max_tokens': engine.max_tokens or 2000,
        'temperature': engine.temperature or 0.7,
        'stream': True  # 启用流式响应
    }

    def generate():
        """SSE生成器函数"""
        try:
            # 发送开始事件
            yield f"data: {json.dumps({'type': 'start', 'news_count': len(news_list), 'engine': engine.name}, ensure_ascii=False)}\n\n"

            # 发起流式请求
            response = requests.post(
                engine.api_url,
                headers=headers,
                json=payload,
                stream=True,
                timeout=120
            )

            if response.status_code != 200:
                # 错误处理
                error_msg = f'AI服务响应错误 (HTTP {response.status_code})'
                try:
                    error_data = response.json()
                    if 'error' in error_data:
                        error_obj = error_data['error']
                        if isinstance(error_obj, dict):
                            error_msg = error_obj.get('message', error_msg)
                        else:
                            error_msg = str(error_obj)

                    # 友好的错误提示
                    error_msg_lower = error_msg.lower()
                    if 'balance' in error_msg_lower or 'insufficient' in error_msg_lower or 'paid' in error_msg_lower:
                        error_msg = 'API余额不足，请充值后再试。'
                    elif 'api key' in error_msg_lower or 'authentication' in error_msg_lower:
                        error_msg = 'API密钥无效，请检查AI引擎配置。'
                    elif 'rate limit' in error_msg_lower:
                        error_msg = 'API请求频繁，请稍后再试。'
                except:
                    pass
                yield f"data: {json.dumps({'type': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"
                return

            # 处理流式响应
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith('data: '):
                        chunk_data = line_str[6:]  # 移除 'data: ' 前缀

                        if chunk_data == '[DONE]':
                            # 发送完成事件
                            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                            break

                        try:
                            chunk_json = json.loads(chunk_data)
                            # 提取内容
                            if 'choices' in chunk_json and len(chunk_json['choices']) > 0:
                                delta = chunk_json['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    # 发送内容块
                                    yield f"data: {json.dumps({'type': 'content', 'content': content}, ensure_ascii=False)}\n\n"
                        except json.JSONDecodeError:
                            continue

        except requests.Timeout:
            yield f"data: {json.dumps({'type': 'error', 'message': 'AI分析超时，请稍后重试'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': f'发生错误: {str(e)}'}, ensure_ascii=False)}\n\n"

    # 返回SSE响应
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


# ============ 采集规则库API ============

@main_bp.route('/api/rules/list', methods=['GET'])
@login_required
def api_rules_list():
    """
    获取采集规则列表（支持分页、搜索）
    """
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 10, type=int)
    keyword = request.args.get('keyword', '').strip()
    status = request.args.get('status', '').strip()

    query = CrawlRule.query

    # 关键词搜索
    if keyword:
        query = query.filter(
            db.or_(
                CrawlRule.site_name.like(f'%{keyword}%'),
                CrawlRule.site_domain.like(f'%{keyword}%')
            )
        )

    # 状态筛选
    if status:
        query = query.filter(CrawlRule.status == int(status))

    # 分页
    pagination = query.order_by(CrawlRule.created_at.desc()).paginate(
        page=page, per_page=limit, error_out=False
    )

    return jsonify({
        'code': 0,
        'count': pagination.total,
        'data': [r.to_dict() for r in pagination.items]
    })


@main_bp.route('/api/rules/all', methods=['GET'])
@login_required
def api_rules_all():
    """
    获取所有启用的采集规则（下拉选择用）
    """
    rules = CrawlRule.query.filter_by(status=1).order_by(CrawlRule.site_name).all()
    return jsonify({
        'code': 0,
        'data': [r.to_dict() for r in rules]
    })


@main_bp.route('/api/rules/stats', methods=['GET'])
@login_required
def api_rules_stats():
    """
    获取采集规则统计信息
    """
    from sqlalchemy import func

    # 总数
    total = CrawlRule.query.count()

    # 已启用
    enabled = CrawlRule.query.filter_by(status=1).count()

    # 计算平均成功率
    stats = db.session.query(
        func.sum(CrawlRule.success_count).label('total_success'),
        func.sum(CrawlRule.fail_count).label('total_fail')
    ).first()

    total_attempts = (stats.total_success or 0) + (stats.total_fail or 0)
    if total_attempts > 0:
        success_rate = f"{(stats.total_success or 0) / total_attempts * 100:.1f}%"
    else:
        success_rate = '-'

    return jsonify({
        'code': 0,
        'data': {
            'total': total,
            'enabled': enabled,
            'success_rate': success_rate
        }
    })


@main_bp.route('/api/rules/test', methods=['POST'])
@login_required
def api_rules_test():
    """
    测试采集规则
    """
    from app.deep_crawler import RuleBasedCrawler

    data = request.get_json() or {}
    rule_id = data.get('rule_id')
    url = data.get('url', '').strip()

    if not url:
        return jsonify({'code': 1, 'msg': '请提供测试URL'})

    # 获取规则
    rule = None
    if rule_id:
        rule = CrawlRule.query.get(rule_id)

    # 执行采集
    crawler = RuleBasedCrawler(db)

    if rule:
        # 使用指定规则测试
        result = crawler.deep_collect(url, source_name=rule.site_name)
    else:
        # 自动匹配规则
        result = crawler.deep_collect(url)

    if result['success']:
        return jsonify({
            'code': 0,
            'msg': '采集成功',
            'data': {
                'title': result['title'],
                'content': result['content'],
                'publish_time': result['publish_time'],
                'author': result['author'],
                'rule_used': result['rule_used']
            }
        })
    else:
        return jsonify({
            'code': 1,
            'msg': result.get('error', '采集失败')
        })


@main_bp.route('/api/rules/add', methods=['POST'])
@login_required
def api_rules_add():
    """
    新增采集规则
    """
    import json
    data = request.get_json() or {}

    # 验证必填字段
    site_name = data.get('site_name', '').strip()
    site_domain = data.get('site_domain', '').strip()

    if not site_name or not site_domain:
        return jsonify({'code': 1, 'msg': '站点名称和域名不能为空'})

    # 检查域名是否已存在
    existing = CrawlRule.query.filter_by(site_domain=site_domain).first()
    if existing:
        return jsonify({'code': 1, 'msg': '该站点域名已存在规则'})

    # 处理request_headers
    headers_str = ''
    headers_data = data.get('request_headers', '')
    if headers_data:
        if isinstance(headers_data, dict):
            headers_str = json.dumps(headers_data, ensure_ascii=False)
        else:
            # 验证JSON格式
            try:
                json.loads(headers_data)
                headers_str = headers_data
            except:
                return jsonify({'code': 1, 'msg': 'Request Headers必须是有效的JSON格式'})

    # 处理适用来源
    applicable_sources = data.get('applicable_sources', [])
    sources_str = ''
    if applicable_sources:
        if isinstance(applicable_sources, list):
            sources_str = json.dumps(applicable_sources, ensure_ascii=False)
        elif isinstance(applicable_sources, str):
            sources_str = applicable_sources

    try:
        rule = CrawlRule(
            site_name=site_name,
            site_domain=site_domain,
            applicable_sources=sources_str,
            title_xpath=data.get('title_xpath', '').strip(),
            content_xpath=data.get('content_xpath', '').strip(),
            request_headers=headers_str,
            priority=int(data.get('priority', 0)),
            status=data.get('status', 1),
            description=data.get('description', '').strip()
        )
        db.session.add(rule)
        db.session.commit()

        return jsonify({'code': 0, 'msg': '添加成功', 'data': rule.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'添加失败: {str(e)}'})


@main_bp.route('/api/rules/update', methods=['POST'])
@login_required
def api_rules_update():
    """
    更新采集规则
    """
    import json
    data = request.get_json() or {}
    rule_id = data.get('id')

    if not rule_id:
        return jsonify({'code': 1, 'msg': '缺少规则ID'})

    rule = CrawlRule.query.get(rule_id)
    if not rule:
        return jsonify({'code': 1, 'msg': '规则不存在'})

    try:
        # 更新字段
        if 'site_name' in data:
            rule.site_name = data['site_name'].strip()
        if 'site_domain' in data:
            # 检查域名是否被其他规则使用
            new_domain = data['site_domain'].strip()
            existing = CrawlRule.query.filter(
                CrawlRule.site_domain == new_domain,
                CrawlRule.id != rule_id
            ).first()
            if existing:
                return jsonify({'code': 1, 'msg': '该站点域名已被其他规则使用'})
            rule.site_domain = new_domain
        if 'applicable_sources' in data:
            sources = data['applicable_sources']
            if isinstance(sources, list):
                rule.applicable_sources = json.dumps(sources, ensure_ascii=False)
            elif isinstance(sources, str):
                rule.applicable_sources = sources
            else:
                rule.applicable_sources = ''
        if 'priority' in data:
            rule.priority = int(data['priority'])
        if 'title_xpath' in data:
            rule.title_xpath = data['title_xpath'].strip()
        if 'content_xpath' in data:
            rule.content_xpath = data['content_xpath'].strip()
        if 'request_headers' in data:
            headers_data = data['request_headers']
            if headers_data:
                if isinstance(headers_data, dict):
                    rule.request_headers = json.dumps(headers_data, ensure_ascii=False)
                else:
                    try:
                        json.loads(headers_data)
                        rule.request_headers = headers_data
                    except:
                        return jsonify({'code': 1, 'msg': 'Request Headers必须是有效的JSON格式'})
            else:
                rule.request_headers = ''
        if 'status' in data:
            rule.status = data['status']
        if 'description' in data:
            rule.description = data['description'].strip()

        db.session.commit()
        return jsonify({'code': 0, 'msg': '更新成功', 'data': rule.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'更新失败: {str(e)}'})


@main_bp.route('/api/rules/delete', methods=['POST'])
@login_required
def api_rules_delete():
    """
    删除采集规则
    """
    data = request.get_json() or {}
    rule_id = data.get('id')

    if not rule_id:
        return jsonify({'code': 1, 'msg': '缺少规则ID'})

    rule = CrawlRule.query.get(rule_id)
    if not rule:
        return jsonify({'code': 1, 'msg': '规则不存在'})

    try:
        db.session.delete(rule)
        db.session.commit()
        return jsonify({'code': 0, 'msg': '删除成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'删除失败: {str(e)}'})


@main_bp.route('/api/rules/delete-batch', methods=['POST'])
@login_required
def api_rules_delete_batch():
    """
    批量删除采集规则
    """
    data = request.get_json() or {}
    ids = data.get('ids', [])

    if not ids:
        return jsonify({'code': 1, 'msg': '请选择要删除的规则'})

    try:
        deleted = CrawlRule.query.filter(CrawlRule.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({'code': 0, 'msg': f'成功删除 {deleted} 条规则'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'删除失败: {str(e)}'})


@main_bp.route('/api/rules/<int:rule_id>', methods=['GET'])
@login_required
def api_rules_detail(rule_id):
    """
    获取单条采集规则详情
    """
    rule = CrawlRule.query.get(rule_id)
    if not rule:
        return jsonify({'code': 1, 'msg': '规则不存在'})

    return jsonify({'code': 0, 'data': rule.to_dict()})


@main_bp.route('/api/rules/copy', methods=['POST'])
@login_required
def api_rules_copy():
    """
    复制采集规则
    """
    import json
    data = request.get_json() or {}
    rule_id = data.get('id')

    if not rule_id:
        return jsonify({'code': 1, 'msg': '缺少规则ID'})

    # 获取原规则
    source_rule = CrawlRule.query.get(rule_id)
    if not source_rule:
        return jsonify({'code': 1, 'msg': '原规则不存在'})

    try:
        # 生成新规则名称
        base_name = source_rule.site_name
        copy_count = 1
        new_name = f"{base_name}_副本"
        while CrawlRule.query.filter_by(site_name=new_name).first():
            copy_count += 1
            new_name = f"{base_name}_副本{copy_count}"

        # 生成新域名（添加后缀避免重复）
        new_domain = source_rule.site_domain
        domain_count = 1
        temp_domain = new_domain
        while CrawlRule.query.filter_by(site_domain=temp_domain).first():
            domain_count += 1
            temp_domain = f"{new_domain}_{domain_count}"
        new_domain = temp_domain

        # 创建新规则
        new_rule = CrawlRule(
            site_name=new_name,
            site_domain=new_domain,
            applicable_sources=source_rule.applicable_sources,
            title_xpath=source_rule.title_xpath,
            content_xpath=source_rule.content_xpath,
            request_headers=source_rule.request_headers,
            priority=source_rule.priority,
            status=0,  # 新复制的规则默认禁用
            description=f"复制自: {source_rule.site_name}"
        )

        db.session.add(new_rule)
        db.session.commit()

        return jsonify({
            'code': 0,
            'msg': f'复制成功，新规则：{new_name}',
            'data': new_rule.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'复制失败: {str(e)}'})


@main_bp.route('/api/rules/by-source', methods=['GET'])
@login_required
def api_rules_by_source():
    """
    按来源获取匹配的规则列表

    请求参数:
        - source: 来源名称（如"百度新闻"）
        - url: 目标URL（可选，用于域名匹配）

    返回匹配的规则列表，按优先级排序
    """
    import json
    from urllib.parse import urlparse

    source = request.args.get('source', '').strip()
    url = request.args.get('url', '').strip()

    if not source and not url:
        return jsonify({'code': 1, 'msg': '请提供来源名称或URL'})

    # 获取所有启用的规则
    rules = CrawlRule.query.filter_by(status=1).order_by(CrawlRule.priority.desc()).all()

    matched_rules = []

    # 提取URL域名用于匹配
    url_domain = ''
    url_domain_no_www = ''
    if url:
        try:
            parsed = urlparse(url)
            url_domain = parsed.netloc.lower()
            url_domain_no_www = url_domain.replace('www.', '')
        except:
            pass

    for rule in rules:
        is_matched = False
        match_reason = ''

        # 1. 检查来源名称匹配（优先）
        if source and rule.applicable_sources:
            try:
                sources_list = json.loads(rule.applicable_sources)
                if source in sources_list:
                    is_matched = True
                    match_reason = '来源匹配'
            except:
                pass

        # 2. 检查URL域名匹配
        if url_domain and rule.site_domain:
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
                if is_matched:
                    match_reason = '来源+域名匹配'
                else:
                    is_matched = True
                    match_reason = '域名匹配'

        if is_matched:
            rule_dict = rule.to_dict()
            rule_dict['match_reason'] = match_reason
            matched_rules.append(rule_dict)

    return jsonify({
        'code': 0,
        'data': matched_rules,
        'count': len(matched_rules)
    })


@main_bp.route('/api/rules/<int:rule_id>/related-data', methods=['GET'])
@login_required
def api_rules_related_data(rule_id):
    """
    获取规则关联的数据统计

    返回使用该规则采集的数据数量和列表
    """
    rule = CrawlRule.query.get(rule_id)
    if not rule:
        return jsonify({'code': 1, 'msg': '规则不存在'})

    # 统计使用该规则的数据
    usage_count = CollectedNews.query.filter_by(rule_id=rule_id).count()

    # 统计通过规则名匹配的数据（兼容旧数据）
    rule_name_count = CollectedNews.query.filter(
        CollectedNews.rule_used == rule.site_name,
        CollectedNews.rule_id.is_(None)
    ).count()

    total_count = usage_count + rule_name_count

    return jsonify({
        'code': 0,
        'data': {
            'rule_id': rule_id,
            'rule_name': rule.site_name,
            'usage_count': total_count,
            'success_count': rule.success_count,
            'fail_count': rule.fail_count
        }
    })


@main_bp.route('/api/warehouse/source-stats', methods=['GET'])
@login_required
def api_warehouse_source_stats():
    """
    获取数据仓库来源统计（含匹配规则数）
    使用与 api_rules_by_source 一致的匹配逻辑
    """
    import json
    from sqlalchemy import func

    # 获取所有来源及其数据量，同时获取一个示例URL用于域名匹配
    source_stats = db.session.query(
        CollectedNews.source,
        func.count(CollectedNews.id).label('count')
    ).group_by(CollectedNews.source).all()

    # 获取每个来源的示例URL（用于域名匹配）
    source_urls = {}
    for source, _ in source_stats:
        if source:
            sample = CollectedNews.query.filter_by(source=source).first()
            if sample and sample.url:
                source_urls[source] = sample.url

    # 获取所有启用的规则
    rules = CrawlRule.query.filter_by(status=1).all()

    result = []
    for source, count in source_stats:
        if not source:
            continue

        # 统计匹配该来源的规则数量（使用与api_rules_by_source一致的逻辑）
        matched_rules = 0
        sample_url = source_urls.get(source, '')

        # 提取示例URL的域名
        url_domain = ''
        url_domain_no_www = ''
        if sample_url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(sample_url)
                url_domain = parsed.netloc.lower()
                url_domain_no_www = url_domain.replace('www.', '')
            except:
                pass

        for rule in rules:
            is_matched = False

            # 1. 检查来源名称匹配
            if rule.applicable_sources:
                try:
                    sources_list = json.loads(rule.applicable_sources)
                    if source in sources_list:
                        is_matched = True
                except:
                    pass

            # 2. 检查URL域名匹配
            if not is_matched and url_domain and rule.site_domain:
                rule_domain = rule.site_domain.lower()
                rule_domain = rule_domain.replace('https://', '').replace('http://', '').replace('www.', '')
                rule_domain = rule_domain.split('/')[0].strip()

                if (rule_domain == url_domain_no_www or
                    rule_domain == url_domain or
                    url_domain_no_www.endswith('.' + rule_domain) or
                    url_domain.endswith('.' + rule_domain) or
                    rule_domain in url_domain_no_www or
                    url_domain_no_www in rule_domain):
                    is_matched = True

            if is_matched:
                matched_rules += 1

        result.append({
            'source': source,
            'data_count': count,
            'matched_rules': matched_rules
        })

    return jsonify({
        'code': 0,
        'data': sorted(result, key=lambda x: x['data_count'], reverse=True)
    })


# ============ 深度采集API（基于规则库） ============

@main_bp.route('/api/warehouse/deep-collect', methods=['POST'])
@login_required
def api_warehouse_deep_collect():
    """
    基于规则库的深度采集（单条）

    请求参数:
        - id: 数据ID
        - rule_id: 指定规则ID（可选，单个）
        - rule_ids: 指定规则ID列表（可选，多个，优先级依次尝试）
    """
    from app.deep_crawler import RuleBasedCrawler

    data = request.get_json() or {}
    news_id = data.get('id')
    rule_id = data.get('rule_id')
    rule_ids = data.get('rule_ids', [])

    if not news_id:
        return jsonify({'code': 1, 'msg': '缺少数据ID'})

    # 获取数据
    news = CollectedNews.query.get(news_id)
    if not news:
        return jsonify({'code': 1, 'msg': '数据不存在'})

    if not news.url:
        return jsonify({'code': 1, 'msg': '数据缺少URL，无法采集'})

    # 处理规则ID列表
    if rule_id and not rule_ids:
        rule_ids = [rule_id]

    crawler = RuleBasedCrawler(db)
    result = None
    tried_rules = []

    if rule_ids:
        # 依次尝试指定的规则
        for rid in rule_ids:
            rule = CrawlRule.query.get(rid)
            if not rule:
                continue
            tried_rules.append(rule.site_name)
            # 直接传入规则对象，让采集器使用这个规则
            result = crawler.deep_collect(news.url, source_name=news.source, rule=rule)
            if result['success']:
                break
    else:
        # 自动匹配规则
        result = crawler.deep_collect(news.url, news.source)

    if result and result['success']:
        # 更新数据库
        try:
            if result['title']:
                news.title = result['title']
            if result['content']:
                news.content = result['content']
            if result['publish_time']:
                news.publish_time = result['publish_time']
            if result['author']:
                news.author = result['author']
            news.deep_collected = True
            news.deep_collected_at = datetime.now()
            news.rule_used = result.get('rule_used', '通用规则')
            news.rule_id = result.get('rule_id')

            db.session.commit()

            return jsonify({
                'code': 0,
                'msg': '采集成功',
                'data': {
                    'id': news.id,
                    'title': news.title,
                    'content': news.content[:200] + '...' if news.content and len(news.content) > 200 else news.content,
                    'publish_time': news.publish_time,
                    'author': news.author,
                    'rule_used': result['rule_used'],
                    'tried_rules': tried_rules
                }
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({'code': 1, 'msg': f'保存失败: {str(e)}'})
    else:
        error_msg = result.get('error', '采集失败') if result else '没有找到可用规则'
        if tried_rules:
            error_msg += f'（已尝试规则: {", ".join(tried_rules)}）'
        return jsonify({'code': 1, 'msg': error_msg})


@main_bp.route('/api/warehouse/deep-collect-batch', methods=['POST'])
@login_required
def api_warehouse_deep_collect_batch():
    """
    基于规则库的批量深度采集

    请求参数:
        - ids: 数据ID列表
        - rule_id: 指定规则ID（可选，单个）
        - rule_ids: 指定规则ID列表（可选，多个，优先级依次尝试）
    """
    from app.deep_crawler import RuleBasedCrawler
    import time

    data = request.get_json() or {}
    ids = data.get('ids', [])
    rule_id = data.get('rule_id')
    rule_ids = data.get('rule_ids', [])

    if not ids:
        return jsonify({'code': 1, 'msg': '请选择要采集的数据'})

    # 获取数据列表
    news_list = CollectedNews.query.filter(CollectedNews.id.in_(ids)).all()
    if not news_list:
        return jsonify({'code': 1, 'msg': '未找到要采集的数据'})

    # 处理规则ID列表
    if rule_id and not rule_ids:
        rule_ids = [rule_id]

    # 获取指定的规则列表
    specified_rules = []
    if rule_ids:
        for rid in rule_ids:
            rule = CrawlRule.query.get(rid)
            if rule:
                specified_rules.append(rule)

    crawler = RuleBasedCrawler(db)

    success_count = 0
    failed_count = 0
    results = []

    for news in news_list:
        if not news.url:
            failed_count += 1
            results.append({
                'id': news.id,
                'title': news.title,
                'success': False,
                'error': '缺少URL'
            })
            continue

        try:
            result = None
            tried_rules = []

            if specified_rules:
                # 依次尝试指定的规则
                for rule in specified_rules:
                    tried_rules.append(rule.site_name)
                    # 直接传入规则对象，让采集器使用这个规则
                    result = crawler.deep_collect(news.url, source_name=news.source, rule=rule)
                    if result['success']:
                        break
            else:
                # 自动匹配规则
                result = crawler.deep_collect(news.url, news.source)

            if result and result['success']:
                # 更新数据
                if result['title']:
                    news.title = result['title']
                if result['content']:
                    news.content = result['content']
                if result['publish_time']:
                    news.publish_time = result['publish_time']
                if result['author']:
                    news.author = result['author']
                news.deep_collected = True
                news.deep_collected_at = datetime.now()
                news.rule_used = result.get('rule_used', '通用规则')
                news.rule_id = result.get('rule_id')

                success_count += 1
                results.append({
                    'id': news.id,
                    'title': news.title,
                    'success': True,
                    'rule_used': result['rule_used'],
                    'tried_rules': tried_rules
                })
            else:
                failed_count += 1
                error_msg = result.get('error', '采集失败') if result else '没有可用规则'
                results.append({
                    'id': news.id,
                    'title': news.title,
                    'success': False,
                    'error': error_msg,
                    'tried_rules': tried_rules
                })

            # 每次请求间隔，避免被封
            time.sleep(0.3)

        except Exception as e:
            failed_count += 1
            results.append({
                'id': news.id,
                'title': news.title,
                'success': False,
                'error': str(e)
            })

    # 提交所有更改
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'保存失败: {str(e)}'})

    return jsonify({
        'code': 0,
        'msg': f'采集完成：成功 {success_count} 条，失败 {failed_count} 条',
        'data': {
            'success': success_count,
            'failed': failed_count,
            'details': results
        }
    })


@main_bp.route('/api/warehouse/preview-collect', methods=['POST'])
@login_required
def api_warehouse_preview_collect():
    """
    预览采集结果（不保存）

    请求参数:
        - url: 目标URL
        - source: 来源名称（可选）
    """
    from app.deep_crawler import RuleBasedCrawler

    data = request.get_json() or {}
    url = data.get('url', '').strip()
    source = data.get('source', '').strip()

    if not url:
        return jsonify({'code': 1, 'msg': '请提供URL'})

    crawler = RuleBasedCrawler(db)
    result = crawler.deep_collect(url, source)

    if result['success']:
        return jsonify({
            'code': 0,
            'msg': '预览成功',
            'data': {
                'title': result['title'],
                'content': result['content'],
                'publish_time': result['publish_time'],
                'author': result['author'],
                'rule_used': result['rule_used'],
                'rule_id': result['rule_id']
            }
        })
    else:
        return jsonify({
            'code': 1,
            'msg': result.get('error', '采集失败'),
            'data': {
                'rule_used': result.get('rule_used'),
                'rule_id': result.get('rule_id')
            }
        })


@main_bp.route('/api/warehouse/auto-collect', methods=['POST'])
@login_required
def api_warehouse_auto_collect():
    """
    一键自动采集API

    自动查找所有未深度采集的数据，根据每条数据的URL和来源自动匹配规则进行采集。
    相比前端判断，后端可以基于每条数据的实际URL进行更准确的规则匹配。

    请求参数（可选）:
        - limit: 最大采集数量，默认100，防止一次采集太多
    """
    from app.deep_crawler import RuleBasedCrawler
    import time

    data = request.get_json() or {}
    limit = data.get('limit', 100)

    # 获取所有未深度采集的数据
    uncollected_news = CollectedNews.query.filter_by(deep_collected=False).limit(limit).all()

    if not uncollected_news:
        return jsonify({'code': 0, 'msg': '所有数据已完成深度采集', 'data': {'success': 0, 'failed': 0, 'skipped': 0}})

    crawler = RuleBasedCrawler(db)

    success_count = 0
    failed_count = 0
    skipped_count = 0  # 无匹配规则被跳过的数量
    results = []

    for news in uncollected_news:
        if not news.url:
            skipped_count += 1
            results.append({
                'id': news.id,
                'title': news.title[:30] + '...' if len(news.title) > 30 else news.title,
                'success': False,
                'skipped': True,
                'error': '缺少URL'
            })
            continue

        try:
            # 先检查是否有匹配的规则
            matched = crawler.find_matching_rule(news.source, news.url)

            if not matched:
                # 无匹配规则，跳过
                skipped_count += 1
                results.append({
                    'id': news.id,
                    'title': news.title[:30] + '...' if len(news.title) > 30 else news.title,
                    'success': False,
                    'skipped': True,
                    'error': '无匹配规则'
                })
                continue

            # 有规则，执行采集
            result = crawler.deep_collect(news.url, news.source)

            if result and result['success']:
                # 更新数据
                if result['title']:
                    news.title = result['title']
                if result['content']:
                    news.content = result['content']
                if result['publish_time']:
                    news.publish_time = result['publish_time']
                if result['author']:
                    news.author = result['author']
                news.deep_collected = True
                news.deep_collected_at = datetime.now()
                news.rule_used = result.get('rule_used', '通用规则')
                news.rule_id = result.get('rule_id')

                success_count += 1
                results.append({
                    'id': news.id,
                    'title': news.title[:30] + '...' if len(news.title) > 30 else news.title,
                    'success': True,
                    'rule_used': result['rule_used']
                })
            else:
                failed_count += 1
                results.append({
                    'id': news.id,
                    'title': news.title[:30] + '...' if len(news.title) > 30 else news.title,
                    'success': False,
                    'error': result.get('error', '采集失败') if result else '采集失败'
                })

            # 每次请求间隔，避免被封
            time.sleep(0.3)

        except Exception as e:
            failed_count += 1
            results.append({
                'id': news.id,
                'title': news.title[:30] + '...' if len(news.title) > 30 else news.title,
                'success': False,
                'error': str(e)[:50]
            })

    # 提交所有更改
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'保存失败: {str(e)}'})

    return jsonify({
        'code': 0,
        'msg': f'自动采集完成：成功 {success_count} 条，失败 {failed_count} 条，跳过 {skipped_count} 条',
        'data': {
            'success': success_count,
            'failed': failed_count,
            'skipped': skipped_count,
            'total': len(uncollected_news),
            'details': results[:50]  # 只返回前50条详情，避免响应过大
        }
    })


# ============ AI引擎管理 ============

@main_bp.route('/admin/ai-engines')
@login_required
def ai_engines():
    """AI引擎管理页面"""
    return render_template('admin/ai_engines.html')


@main_bp.route('/api/ai-engines/list', methods=['GET'])
@login_required
def api_ai_engines_list():
    """获取AI引擎列表"""
    engines = AIEngine.query.order_by(AIEngine.is_default.desc(), AIEngine.created_at.desc()).all()
    return jsonify({
        'code': 0,
        'data': [e.to_dict() for e in engines]
    })


@main_bp.route('/api/ai-engines/<int:engine_id>', methods=['GET'])
@login_required
def api_ai_engine_detail(engine_id):
    """获取单个AI引擎详情（包含完整密钥）"""
    engine = AIEngine.query.get(engine_id)
    if not engine:
        return jsonify({'code': 1, 'msg': '引擎不存在'})

    return jsonify({
        'code': 0,
        'data': engine.to_dict(hide_key=False)
    })


@main_bp.route('/api/ai-engines/add', methods=['POST'])
@login_required
def api_ai_engines_add():
    """新增AI引擎"""
    data = request.get_json() or {}

    # 验证必填字段
    required = ['name', 'provider', 'api_url', 'api_key', 'model_name']
    for field in required:
        if not data.get(field, '').strip():
            return jsonify({'code': 1, 'msg': f'{field}不能为空'})

    try:
        engine = AIEngine(
            name=data['name'].strip(),
            provider=data['provider'].strip(),
            api_url=data['api_url'].strip(),
            api_key=data['api_key'].strip(),
            model_name=data['model_name'].strip(),
            description=data.get('description', '').strip(),
            icon=data.get('icon', 'layui-icon-auz'),
            color=data.get('color', '#667eea'),
            status=int(data.get('status', 1)),
            max_tokens=int(data.get('max_tokens', 4096)),
            temperature=float(data.get('temperature', 0.7))
        )

        # 如果是第一个引擎，设为默认
        if AIEngine.query.count() == 0:
            engine.is_default = True

        db.session.add(engine)
        db.session.commit()

        return jsonify({'code': 0, 'msg': '添加成功', 'data': engine.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'添加失败: {str(e)}'})


@main_bp.route('/api/ai-engines/update', methods=['POST'])
@login_required
def api_ai_engines_update():
    """更新AI引擎"""
    data = request.get_json() or {}
    engine_id = data.get('id')

    if not engine_id:
        return jsonify({'code': 1, 'msg': '缺少引擎ID'})

    engine = AIEngine.query.get(engine_id)
    if not engine:
        return jsonify({'code': 1, 'msg': '引擎不存在'})

    try:
        if 'name' in data:
            engine.name = data['name'].strip()
        if 'provider' in data:
            engine.provider = data['provider'].strip()
        if 'api_url' in data:
            engine.api_url = data['api_url'].strip()
        if 'api_key' in data and data['api_key'].strip():
            engine.api_key = data['api_key'].strip()
        if 'model_name' in data:
            engine.model_name = data['model_name'].strip()
        if 'description' in data:
            engine.description = data['description'].strip()
        if 'icon' in data:
            engine.icon = data['icon']
        if 'color' in data:
            engine.color = data['color']
        if 'status' in data:
            engine.status = int(data['status'])
        if 'max_tokens' in data:
            engine.max_tokens = int(data['max_tokens'])
        if 'temperature' in data:
            engine.temperature = float(data['temperature'])

        db.session.commit()
        return jsonify({'code': 0, 'msg': '更新成功', 'data': engine.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'更新失败: {str(e)}'})


@main_bp.route('/api/ai-engines/delete', methods=['POST'])
@login_required
def api_ai_engines_delete():
    """删除AI引擎"""
    data = request.get_json() or {}
    engine_id = data.get('id')

    if not engine_id:
        return jsonify({'code': 1, 'msg': '缺少引擎ID'})

    engine = AIEngine.query.get(engine_id)
    if not engine:
        return jsonify({'code': 1, 'msg': '引擎不存在'})

    try:
        was_default = engine.is_default
        db.session.delete(engine)
        db.session.commit()

        # 如果删除的是默认引擎，将第一个引擎设为默认
        if was_default:
            first_engine = AIEngine.query.first()
            if first_engine:
                first_engine.is_default = True
                db.session.commit()

        return jsonify({'code': 0, 'msg': '删除成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'删除失败: {str(e)}'})


@main_bp.route('/api/ai-engines/set-default', methods=['POST'])
@login_required
def api_ai_engines_set_default():
    """设置默认引擎"""
    data = request.get_json() or {}
    engine_id = data.get('id')

    if not engine_id:
        return jsonify({'code': 1, 'msg': '缺少引擎ID'})

    engine = AIEngine.query.get(engine_id)
    if not engine:
        return jsonify({'code': 1, 'msg': '引擎不存在'})

    try:
        # 取消其他默认
        AIEngine.query.update({AIEngine.is_default: False})
        # 设置新默认
        engine.is_default = True
        db.session.commit()

        return jsonify({'code': 0, 'msg': '设置成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'设置失败: {str(e)}'})


@main_bp.route('/api/ai-engines/test', methods=['POST'])
@login_required
def api_ai_engines_test():
    """测试AI引擎连接"""
    import requests
    import time

    data = request.get_json() or {}
    engine_id = data.get('id')

    if not engine_id:
        return jsonify({'code': 1, 'msg': '缺少引擎ID'})

    engine = AIEngine.query.get(engine_id)
    if not engine:
        return jsonify({'code': 1, 'msg': '引擎不存在'})

    # 构建测试请求
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {engine.api_key}'
    }

    payload = {
        'model': engine.model_name,
        'messages': [
            {'role': 'user', 'content': '你好，请简短回复，测试连接是否正常。'}
        ],
        'max_tokens': 50,
        'temperature': 0.7
    }

    try:
        start_time = time.time()
        response = requests.post(
            engine.api_url,
            headers=headers,
            json=payload,
            timeout=60,
            verify=True  # SSL验证
        )
        end_time = time.time()
        response_time = f'{(end_time - start_time) * 1000:.0f}ms'

        if response.status_code == 200:
            result = response.json()
            reply = ''
            if 'choices' in result and len(result['choices']) > 0:
                choice = result['choices'][0]
                if 'message' in choice:
                    reply = choice['message'].get('content', '')
                elif 'text' in choice:
                    reply = choice['text']

            return jsonify({
                'code': 0,
                'msg': '连接成功',
                'data': {
                    'response_time': response_time,
                    'model': result.get('model', engine.model_name),
                    'reply': reply
                }
            })
        else:
            error_msg = f'HTTP {response.status_code}'
            error_detail = ''
            try:
                error_data = response.json()
                if 'error' in error_data:
                    error_obj = error_data['error']
                    if isinstance(error_obj, dict):
                        error_msg = error_obj.get('message', error_msg)
                        error_detail = error_obj.get('type', '')
                    else:
                        error_msg = str(error_obj)
                elif 'message' in error_data:
                    error_msg = error_data['message']
            except:
                error_msg = f'HTTP {response.status_code}: {response.text[:200]}'

            full_msg = f'{error_msg}' + (f' ({error_detail})' if error_detail else '')
            return jsonify({'code': 1, 'msg': full_msg})

    except requests.Timeout:
        return jsonify({'code': 1, 'msg': '请求超时(60秒)，请检查API地址和网络连接'})
    except requests.exceptions.SSLError as e:
        return jsonify({'code': 1, 'msg': f'SSL证书错误: {str(e)[:100]}'})
    except requests.exceptions.ConnectionError as e:
        return jsonify({'code': 1, 'msg': f'连接失败，请检查API地址是否正确: {str(e)[:100]}'})
    except requests.RequestException as e:
        return jsonify({'code': 1, 'msg': f'网络错误: {str(e)[:100]}'})
    except Exception as e:
        return jsonify({'code': 1, 'msg': f'测试失败: {str(e)[:100]}'})


# ============ 爬虫管理 ============

@main_bp.route('/admin/crawlers')
@login_required
def crawlers():
    """爬虫管理页面"""
    return render_template('admin/crawlers.html')


@main_bp.route('/api/crawlers/list', methods=['GET'])
@login_required
def api_crawlers_list():
    """获取爬虫列表"""
    from app.models import CrawlerConfig
    crawlers = CrawlerConfig.query.order_by(CrawlerConfig.sort_order.asc(), CrawlerConfig.created_at.asc()).all()
    return jsonify({
        'code': 0,
        'data': [c.to_dict() for c in crawlers]
    })


@main_bp.route('/api/crawlers/active', methods=['GET'])
@login_required
def api_crawlers_active():
    """获取启用的爬虫列表（用于数据采集页面）"""
    from app.models import CrawlerConfig
    crawlers = CrawlerConfig.query.filter_by(status=1).order_by(CrawlerConfig.sort_order.asc()).all()
    return jsonify({
        'code': 0,
        'data': [{'code': c.code, 'name': c.name, 'icon': c.icon, 'color': c.color} for c in crawlers]
    })


@main_bp.route('/api/crawlers/<int:crawler_id>', methods=['GET'])
@login_required
def api_crawler_detail(crawler_id):
    """获取单个爬虫详情"""
    from app.models import CrawlerConfig
    crawler = CrawlerConfig.query.get(crawler_id)
    if not crawler:
        return jsonify({'code': 1, 'msg': '爬虫不存在'})

    return jsonify({
        'code': 0,
        'data': crawler.to_dict()
    })


@main_bp.route('/api/crawlers/add', methods=['POST'])
@login_required
def api_crawlers_add():
    """新增爬虫"""
    from app.models import CrawlerConfig

    data = request.get_json() or {}

    # 验证必填字段
    required = ['name', 'code']
    for field in required:
        if not data.get(field, '').strip():
            return jsonify({'code': 1, 'msg': f'{field}不能为空'})

    # 检查code是否已存在
    if CrawlerConfig.query.filter_by(code=data['code'].strip()).first():
        return jsonify({'code': 1, 'msg': '爬虫代码已存在'})

    try:
        crawler = CrawlerConfig(
            name=data['name'].strip(),
            code=data['code'].strip(),
            description=data.get('description', '').strip(),
            icon=data.get('icon', 'layui-icon-website'),
            color=data.get('color', '#667eea'),
            base_url=data.get('base_url', '').strip(),
            search_url=data.get('search_url', '').strip(),
            crawler_class=data.get('crawler_class', '').strip(),
            crawler_module=data.get('crawler_module', '').strip(),
            default_headers=data.get('default_headers', '').strip(),
            request_delay=float(data.get('request_delay', 0.5)),
            timeout=int(data.get('timeout', 15)),
            max_pages=int(data.get('max_pages', 10)),
            status=int(data.get('status', 1)),
            is_builtin=False,
            sort_order=int(data.get('sort_order', 0))
        )

        db.session.add(crawler)
        db.session.commit()

        return jsonify({'code': 0, 'msg': '添加成功', 'data': crawler.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'添加失败: {str(e)}'})


@main_bp.route('/api/crawlers/update', methods=['POST'])
@login_required
def api_crawlers_update():
    """更新爬虫"""
    from app.models import CrawlerConfig

    data = request.get_json() or {}
    crawler_id = data.get('id')

    if not crawler_id:
        return jsonify({'code': 1, 'msg': '缺少爬虫ID'})

    crawler = CrawlerConfig.query.get(crawler_id)
    if not crawler:
        return jsonify({'code': 1, 'msg': '爬虫不存在'})

    try:
        if 'name' in data:
            crawler.name = data['name'].strip()
        if 'code' in data and data['code'].strip() != crawler.code:
            # 检查新code是否已存在
            if CrawlerConfig.query.filter(CrawlerConfig.code == data['code'].strip(), CrawlerConfig.id != crawler_id).first():
                return jsonify({'code': 1, 'msg': '爬虫代码已存在'})
            crawler.code = data['code'].strip()
        if 'description' in data:
            crawler.description = data['description'].strip()
        if 'icon' in data:
            crawler.icon = data['icon']
        if 'color' in data:
            crawler.color = data['color']
        if 'base_url' in data:
            crawler.base_url = data['base_url'].strip()
        if 'search_url' in data:
            crawler.search_url = data['search_url'].strip()
        if 'crawler_class' in data:
            crawler.crawler_class = data['crawler_class'].strip()
        if 'crawler_module' in data:
            crawler.crawler_module = data['crawler_module'].strip()
        if 'default_headers' in data:
            crawler.default_headers = data['default_headers'].strip()
        if 'request_delay' in data:
            crawler.request_delay = float(data['request_delay'])
        if 'timeout' in data:
            crawler.timeout = int(data['timeout'])
        if 'max_pages' in data:
            crawler.max_pages = int(data['max_pages'])
        if 'status' in data:
            crawler.status = int(data['status'])
        if 'sort_order' in data:
            crawler.sort_order = int(data['sort_order'])

        db.session.commit()
        return jsonify({'code': 0, 'msg': '更新成功', 'data': crawler.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'更新失败: {str(e)}'})


@main_bp.route('/api/crawlers/delete', methods=['POST'])
@login_required
def api_crawlers_delete():
    """删除爬虫"""
    from app.models import CrawlerConfig

    data = request.get_json() or {}
    crawler_id = data.get('id')

    if not crawler_id:
        return jsonify({'code': 1, 'msg': '缺少爬虫ID'})

    crawler = CrawlerConfig.query.get(crawler_id)
    if not crawler:
        return jsonify({'code': 1, 'msg': '爬虫不存在'})

    if crawler.is_builtin:
        return jsonify({'code': 1, 'msg': '内置爬虫不能删除'})

    try:
        db.session.delete(crawler)
        db.session.commit()
        return jsonify({'code': 0, 'msg': '删除成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'删除失败: {str(e)}'})


@main_bp.route('/api/crawlers/toggle-status', methods=['POST'])
@login_required
def api_crawlers_toggle_status():
    """切换爬虫状态"""
    from app.models import CrawlerConfig

    data = request.get_json() or {}
    crawler_id = data.get('id')

    if not crawler_id:
        return jsonify({'code': 1, 'msg': '缺少爬虫ID'})

    crawler = CrawlerConfig.query.get(crawler_id)
    if not crawler:
        return jsonify({'code': 1, 'msg': '爬虫不存在'})

    try:
        crawler.status = 0 if crawler.status == 1 else 1
        db.session.commit()
        return jsonify({'code': 0, 'msg': '状态已更新', 'data': {'status': crawler.status}})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'更新失败: {str(e)}'})


@main_bp.route('/api/crawlers/test', methods=['POST'])
@login_required
def api_crawlers_test():
    """测试爬虫"""
    from app.models import CrawlerConfig
    import importlib

    data = request.get_json() or {}
    crawler_id = data.get('id')
    keyword = data.get('keyword', '测试')

    if not crawler_id:
        return jsonify({'code': 1, 'msg': '缺少爬虫ID'})

    crawler = CrawlerConfig.query.get(crawler_id)
    if not crawler:
        return jsonify({'code': 1, 'msg': '爬虫不存在'})

    try:
        # 动态加载爬虫模块
        if crawler.crawler_module and crawler.crawler_class:
            module = importlib.import_module(crawler.crawler_module)
            crawler_cls = getattr(module, crawler.crawler_class)
            crawler_instance = crawler_cls()

            # 测试采集
            results = crawler_instance.search(keyword, page=1)

            # 更新统计
            if results:
                crawler.success_count = (crawler.success_count or 0) + 1
            else:
                crawler.fail_count = (crawler.fail_count or 0) + 1
            crawler.last_used_at = datetime.now()
            db.session.commit()

            return jsonify({
                'code': 0,
                'msg': f'测试成功，获取到 {len(results)} 条数据',
                'data': {
                    'count': len(results),
                    'sample': results[0] if results else None
                }
            })
        else:
            return jsonify({'code': 1, 'msg': '爬虫未配置模块和类名'})
    except Exception as e:
        # 更新失败统计
        crawler.fail_count = (crawler.fail_count or 0) + 1
        db.session.commit()
        return jsonify({'code': 1, 'msg': f'测试失败: {str(e)}'})


# ============ 智能爬虫分析API ============

@main_bp.route('/api/crawlers/analyze', methods=['POST'])
@login_required
@admin_required
def api_crawlers_analyze():
    """智能分析爬虫配置"""
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    request_headers = data.get('request_headers', '[]').strip()
    sample_html = data.get('sample_html', '').strip()

    if not url:
        return jsonify({'code': 1, 'msg': '请输入源地址'})

    try:
        from app.crawler_analyzer import CrawlerAnalyzer

        analyzer = CrawlerAnalyzer()
        result = analyzer.analyze(url=url, request_headers=request_headers, sample_html=sample_html)

        return jsonify({
            'code': 0,
            'msg': f'分析完成，置信度: {result.get("confidence", 0)}%',
            'data': result
        })
    except Exception as e:
        return jsonify({'code': 1, 'msg': f'分析失败: {str(e)}'})


@main_bp.route('/api/crawlers/create-from-analysis', methods=['POST'])
@login_required
@admin_required
def api_crawlers_create_from_analysis():
    """从分析结果创建爬虫"""
    from app.models import CrawlerConfig
    import json

    data = request.get_json() or {}

    # 必填字段
    name = data.get('name', '').strip()
    code = data.get('code', '').strip()

    if not name or not code:
        return jsonify({'code': 1, 'msg': '名称和代码不能为空'})

    # 检查code是否已存在
    if CrawlerConfig.query.filter_by(code=code).first():
        return jsonify({'code': 1, 'msg': '爬虫代码已存在'})

    # 解析分析配置
    try:
        config = data.get('analyzed_config', {})
        if isinstance(config, str):
            config = json.loads(config)

        # 创建爬虫配置
        crawler = CrawlerConfig(
            name=name,
            code=code,
            description=config.get('description', ''),
            icon=config.get('icon', 'layui-icon-website'),
            color=config.get('color', '#667eea'),
            crawler_type=config.get('crawler_type', 'html_parser'),
            base_url=config.get('base_url', ''),
            search_url=config.get('search_url', ''),
            request_method=config.get('request_method', 'GET'),
            search_params_template=json.dumps(config.get('search_params_template', {}), ensure_ascii=False),
            pagination_config=json.dumps(config.get('pagination_config', {}), ensure_ascii=False),
            parse_config=json.dumps(config.get('parse_config', {}), ensure_ascii=False),
            analyzed_config=json.dumps(config, ensure_ascii=False),
            is_analyzed=True,
            default_headers=json.dumps(config.get('default_headers', {}), ensure_ascii=False),
            request_delay=float(config.get('request_delay', 0.5)),
            timeout=int(config.get('timeout', 15)),
            max_pages=int(config.get('max_pages', 10)),
            page_size=int(config.get('page_size', 10)),
            status=1,
            is_builtin=False,
            is_template=False
        )

        db.session.add(crawler)
        db.session.commit()

        return jsonify({'code': 0, 'msg': '创建成功', 'data': crawler.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 1, 'msg': f'创建失败: {str(e)}'})


@main_bp.route('/api/crawlers/test-dynamic', methods=['POST'])
@login_required
def api_crawlers_test_dynamic():
    """测试动态爬虫"""
    from app.models import CrawlerConfig
    from app.crawler_dynamic import DynamicCrawlerEngine

    data = request.get_json() or {}
    crawler_id = data.get('id')
    keyword = data.get('keyword', '测试')

    if not crawler_id:
        return jsonify({'code': 1, 'msg': '缺少爬虫ID'})

    crawler = CrawlerConfig.query.get(crawler_id)
    if not crawler:
        return jsonify({'code': 1, 'msg': '爬虫不存在'})

    try:
        # 使用动态爬虫引擎测试
        crawler_engine = DynamicCrawlerEngine(crawler.to_dict())
        results = crawler_engine.search_batch(keyword, count=20)

        # 更新统计
        if results:
            crawler.success_count = (crawler.success_count or 0) + 1
        else:
            crawler.fail_count = (crawler.fail_count or 0) + 1
        crawler.last_used_at = datetime.now()
        crawler.last_error = None
        db.session.commit()

        return jsonify({
            'code': 0,
            'msg': f'动态爬虫测试成功，获取到 {len(results)} 条数据',
            'data': {
                'count': len(results),
                'sample': results[:5] if results else []
            }
        })
    except Exception as e:
        # 更新失败统计
        crawler.fail_count = (crawler.fail_count or 0) + 1
        crawler.last_used_at = datetime.now()
        crawler.last_error = str(e)
        db.session.commit()

        return jsonify({'code': 1, 'msg': f'动态爬虫测试失败: {str(e)}'})


@main_bp.route('/api/crawlers/init-builtin', methods=['POST'])
@login_required
def api_crawlers_init_builtin():
    """初始化内置爬虫"""
    from app.models import CrawlerConfig

    builtin_crawlers = [
        {
            'name': '百度新闻',
            'code': 'baidu',
            'description': '从百度新闻搜索采集新闻数据',
            'icon': 'layui-icon-read',
            'color': '#2932e1',
            'base_url': 'https://www.baidu.com',
            'search_url': 'https://www.baidu.com/s',
            'crawler_class': 'BaiduNewsCrawler',
            'crawler_module': 'app.crawler',
            'request_delay': 0.5,
            'timeout': 15,
            'max_pages': 10,
            'sort_order': 1
        },
        {
            'name': '360新闻',
            'code': '360kuai',
            'description': '从360新闻搜索采集新闻数据',
            'icon': 'layui-icon-website',
            'color': '#00b050',
            'base_url': 'https://www.so.com',
            'search_url': 'https://news.so.com/ns',
            'crawler_class': 'News360Crawler',
            'crawler_module': 'app.crawler_360kuai',
            'request_delay': 0.5,
            'timeout': 15,
            'max_pages': 5,
            'sort_order': 2
        },
        {
            'name': '腾讯新闻',
            'code': 'tencent',
            'description': '从腾讯新闻搜索采集新闻数据',
            'icon': 'layui-icon-templeate-1',
            'color': '#ff6b00',
            'base_url': 'https://new.qq.com',
            'search_url': 'https://new.qq.com/search',
            'crawler_class': 'TencentNewsCrawler',
            'crawler_module': 'app.crawler_tencent',
            'request_delay': 0.5,
            'timeout': 15,
            'max_pages': 5,
            'sort_order': 3
        },
        {
            'name': '网易新闻',
            'code': 'netease',
            'description': '从网易新闻搜索采集新闻数据',
            'icon': 'layui-icon-app',
            'color': '#d71a1a',
            'base_url': 'https://news.163.com',
            'search_url': 'https://search.news.163.com/search',
            'crawler_class': 'NeteaseNewsCrawler',
            'crawler_module': 'app.crawler_netease',
            'request_delay': 0.5,
            'timeout': 15,
            'max_pages': 5,
            'sort_order': 4
        },
        {
            'name': '搜狐新闻',
            'code': 'sohu',
            'description': '从搜狐新闻搜索采集新闻数据',
            'icon': 'layui-icon-survey',
            'color': '#ff7a00',
            'base_url': 'https://www.sohu.com',
            'search_url': 'https://search.sohu.com/',
            'crawler_class': 'SohuNewsCrawler',
            'crawler_module': 'app.crawler_sohu',
            'request_delay': 0.5,
            'timeout': 15,
            'max_pages': 5,
            'sort_order': 5
        }
    ]

    added = 0
    for cfg in builtin_crawlers:
        if not CrawlerConfig.query.filter_by(code=cfg['code']).first():
            crawler = CrawlerConfig(
                name=cfg['name'],
                code=cfg['code'],
                description=cfg['description'],
                icon=cfg['icon'],
                color=cfg['color'],
                base_url=cfg['base_url'],
                search_url=cfg['search_url'],
                crawler_class=cfg['crawler_class'],
                crawler_module=cfg['crawler_module'],
                request_delay=cfg['request_delay'],
                timeout=cfg['timeout'],
                max_pages=cfg['max_pages'],
                status=1,
                is_builtin=True,
                sort_order=cfg['sort_order']
            )
            db.session.add(crawler)
            added += 1

    if added > 0:
        db.session.commit()
        return jsonify({'code': 0, 'msg': f'成功初始化 {added} 个内置爬虫'})
    else:
        return jsonify({'code': 0, 'msg': '内置爬虫已存在，无需初始化'})


@main_bp.route('/api/ai/chat', methods=['POST'])
@login_required
def api_ai_chat():
    """AI对话接口"""
    import requests

    data = request.get_json() or {}
    message = data.get('message', '').strip()
    engine_id = data.get('engine_id')
    history = data.get('history', [])  # 对话历史

    if not message:
        return jsonify({'code': 1, 'msg': '请输入消息内容'})

    # 获取指定引擎或默认引擎
    if engine_id:
        engine = AIEngine.query.get(engine_id)
    else:
        engine = AIEngine.query.filter_by(is_default=True, status=1).first()
        if not engine:
            engine = AIEngine.query.filter_by(status=1).first()

    if not engine:
        return jsonify({'code': 1, 'msg': '没有可用的AI引擎，请先配置AI引擎'})

    if engine.status != 1:
        return jsonify({'code': 1, 'msg': '该AI引擎已禁用'})

    # 构建消息
    messages = []
    # 添加系统提示
    messages.append({
        'role': 'system',
        'content': '你是一个智能舆情分析助手，专门帮助用户分析新闻、舆情信息，提供专业的见解和建议。请用简洁清晰的中文回复。'
    })
    # 添加历史对话
    for h in history[-10:]:  # 最多保留10轮历史
        messages.append({'role': h.get('role', 'user'), 'content': h.get('content', '')})
    # 添加当前消息
    messages.append({'role': 'user', 'content': message})

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {engine.api_key}'
    }

    payload = {
        'model': engine.model_name,
        'messages': messages,
        'max_tokens': engine.max_tokens,
        'temperature': engine.temperature
    }

    try:
        response = requests.post(
            engine.api_url,
            headers=headers,
            json=payload,
            timeout=120
        )

        # 确保正确的编码
        response.encoding = 'utf-8'

        if response.status_code == 200:
            result = response.json()
            reply = ''
            if 'choices' in result and len(result['choices']) > 0:
                choice = result['choices'][0]
                if 'message' in choice:
                    reply = choice['message'].get('content', '')
                elif 'text' in choice:
                    reply = choice['text']

            return jsonify({
                'code': 0,
                'data': {
                    'reply': reply,
                    'engine': engine.name,
                    'model': result.get('model', engine.model_name)
                }
            })
        else:
            error_msg = f'AI服务响应错误 (HTTP {response.status_code})'
            try:
                error_data = response.json()
                if 'error' in error_data:
                    error_obj = error_data['error']
                    if isinstance(error_obj, dict):
                        error_msg = error_obj.get('message', error_msg)
                    else:
                        error_msg = str(error_obj)

                # 友好的错误提示
                error_msg_lower = error_msg.lower()
                if 'balance' in error_msg_lower or 'insufficient' in error_msg_lower or 'paid' in error_msg_lower:
                    error_msg = 'API余额不足，请充值后再试。如果您使用的是免费API，请切换到已充值的API密钥。'
                elif 'api key' in error_msg_lower or 'authentication' in error_msg_lower or 'unauthorized' in error_msg_lower:
                    error_msg = 'API密钥无效或未授权，请检查AI引擎配置中的API密钥是否正确。'
                elif 'rate limit' in error_msg_lower or 'too many' in error_msg_lower:
                    error_msg = 'API请求过于频繁，请稍后再试。'
                elif 'model' in error_msg_lower and 'not found' in error_msg_lower:
                    error_msg = '指定的模型不存在，请检查AI引擎配置中的模型名称。'
            except:
                pass
            return jsonify({'code': 1, 'msg': error_msg})

    except requests.Timeout:
        return jsonify({'code': 1, 'msg': 'AI响应超时，请稍后重试'})
    except requests.RequestException as e:
        return jsonify({'code': 1, 'msg': f'网络错误: {str(e)[:100]}'})
    except Exception as e:
        return jsonify({'code': 1, 'msg': f'请求失败: {str(e)[:100]}'})


# ============ 设置 API ============

@main_bp.route('/api/settings/dashboard-bg', methods=['GET'])
@login_required
def get_dashboard_bg():
    """获取仪表盘背景设置"""
    bg_url = SystemConfig.get_config('dashboard_bg_url', '')
    return jsonify({
        'code': 0,
        'data': {'bg_url': bg_url}
    })


@main_bp.route('/api/settings/dashboard-bg', methods=['POST'])
@login_required
def set_dashboard_bg():
    """设置仪表盘背景"""
    data = request.get_json()
    if data is None:
        return jsonify({'code': 1, 'msg': '无效的请求数据'})

    bg_url = data.get('bg_url', '')

    try:
        SystemConfig.set_config('dashboard_bg_url', bg_url)
        return jsonify({'code': 0, 'msg': '设置成功'})
    except Exception as e:
        return jsonify({'code': 1, 'msg': f'设置失败: {str(e)}'})


@main_bp.route('/api/dashboard/stats', methods=['GET'])
@login_required
def api_dashboard_stats():
    """获取仪表盘统计数据"""
    from datetime import datetime, timedelta
    from sqlalchemy import func

    try:
        # 数据总量
        total_count = CollectedNews.query.count()

        # 已深度采集数量（修复字段名）
        deep_collected = CollectedNews.query.filter(CollectedNews.deep_collected == True).count()

        # 今日新增（最近24小时）
        today_start = datetime.now() - timedelta(hours=24)
        today_count = CollectedNews.query.filter(CollectedNews.created_at >= today_start).count()

        # 数据来源统计
        sources_count = db.session.query(func.count(func.distinct(CollectedNews.source))).scalar()

        # 最近采集的5条数据
        recent_news = CollectedNews.query.order_by(CollectedNews.created_at.desc()).limit(5).all()

        return jsonify({
            'code': 0,
            'data': {
                'total_count': total_count,
                'deep_collected': deep_collected,
                'today_count': today_count,
                'sources_count': sources_count or 0,
                'recent_news': [news.to_dict() for news in recent_news]
            }
        })
    except Exception as e:
        return jsonify({'code': 1, 'msg': f'获取统计数据失败: {str(e)}'})


@main_bp.route('/api/dashboard/system-status', methods=['GET'])
@login_required
def api_dashboard_system_status():
    """获取系统状态"""
    from app.models import CrawlerConfig, AIEngine

    try:
        status_items = []

        # 系统状态
        status_items.append({
            'label': '系统状态',
            'status': 'success',
            'text': '运行正常'
        })

        # 数据库连接
        try:
            db.session.execute('SELECT 1')
            status_items.append({
                'label': '数据库连接',
                'status': 'success',
                'text': '已连接'
            })
        except:
            status_items.append({
                'label': '数据库连接',
                'status': 'error',
                'text': '连接失败'
            })

        # 爬虫状态（检查启用的爬虫）
        crawlers = CrawlerConfig.query.filter_by(status=1).all()
        for crawler in crawlers[:3]:  # 只显示前3个
            status_items.append({
                'label': crawler.name,
                'status': 'success',
                'text': '可用'
            })

        # AI引擎状态
        ai_engines = AIEngine.query.filter_by(status=1).count()
        if ai_engines > 0:
            status_items.append({
                'label': f'AI引擎 ({ai_engines}个)',
                'status': 'success',
                'text': '已配置'
            })
        else:
            status_items.append({
                'label': 'AI引擎',
                'status': 'warning',
                'text': '未配置'
            })

        return jsonify({
            'code': 0,
            'data': [{'label': item['label'], 'status': item['status'], 'text': item['text']} for item in status_items]
        })
    except Exception as e:
        return jsonify({'code': 1, 'msg': f'获取系统状态失败: {str(e)}'})


# ============ AI数据分析 ============

@main_bp.route('/admin/ai-data-analysis')
@login_required
def ai_data_analysis():
    """AI数据分析页面"""
    return render_template('admin/ai_data_analysis.html')


# AI数据分析工具定义
AI_DATA_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_table_list",
            "description": "获取数据库中所有表的列表，用于了解数据库有哪些数据表",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_table_schema",
            "description": "获取指定表的结构信息，包括列名、数据类型、是否为主键等，以及表中的数据行数",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "要查询的表名"
                    }
                },
                "required": ["table_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_sql_query",
            "description": "执行SQL查询语句（仅支持SELECT），用于查询和分析数据。注意：只能执行SELECT查询，不能执行增删改操作",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "要执行的SQL SELECT语句"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最大返回行数，默认100",
                        "default": 100
                    }
                },
                "required": ["sql"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_data_statistics",
            "description": "获取表或指定列的统计信息，如行数、非空值数量、唯一值数量、最大最小值等",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "要统计的表名"
                    },
                    "column_name": {
                        "type": "string",
                        "description": "要统计的列名（可选），如果不指定则只统计表的行数"
                    }
                },
                "required": ["table_name"]
            }
        }
    }
]


def get_database_path():
    """获取数据库路径"""
    import os
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), 'instance', 'app.db')


def tool_get_table_list():
    """获取数据库中所有表的列表"""
    import sqlite3
    db_path = get_database_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    return {"tables": tables}


def tool_get_table_schema(table_name: str):
    """获取指定表的结构信息"""
    import sqlite3
    db_path = get_database_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 检查表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    if not cursor.fetchone():
        conn.close()
        return {"error": f"表 '{table_name}' 不存在"}

    # 获取表结构
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = []
    for row in cursor.fetchall():
        columns.append({
            "cid": row[0],
            "name": row[1],
            "type": row[2],
            "notnull": row[3],
            "default": row[4],
            "pk": row[5]
        })

    # 获取行数
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    row_count = cursor.fetchone()[0]

    conn.close()
    return {
        "table_name": table_name,
        "columns": columns,
        "row_count": row_count
    }


def tool_execute_sql_query(sql: str, limit: int = 100):
    """执行只读SQL查询"""
    import sqlite3
    db_path = get_database_path()

    # 安全检查：只允许SELECT语句
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith('SELECT'):
        return {"error": "只允许执行SELECT查询语句，不支持增删改操作"}

    # 禁止危险操作
    dangerous_keywords = ['DROP', 'DELETE', 'UPDATE', 'INSERT', 'ALTER', 'CREATE', 'TRUNCATE']
    for keyword in dangerous_keywords:
        if keyword in sql_upper:
            return {"error": f"SQL语句包含不允许的操作: {keyword}"}

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 添加LIMIT限制
        if 'LIMIT' not in sql_upper:
            sql = f"{sql.rstrip(';')} LIMIT {limit}"

        cursor.execute(sql)
        rows = cursor.fetchall()

        result = [dict(row) for row in rows]
        column_names = [description[0] for description in cursor.description] if cursor.description else []

        conn.close()
        return {
            "columns": column_names,
            "data": result,
            "row_count": len(result),
            "sql": sql
        }
    except Exception as e:
        return {"error": f"SQL执行错误: {str(e)}"}


def tool_get_data_statistics(table_name: str, column_name: str = None):
    """获取表或列的统计信息"""
    import sqlite3
    db_path = get_database_path()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 检查表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    if not cursor.fetchone():
        conn.close()
        return {"error": f"表 '{table_name}' 不存在"}

    stats = {"table_name": table_name}

    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    stats["total_rows"] = cursor.fetchone()[0]

    if column_name:
        try:
            cursor.execute(f"SELECT COUNT({column_name}) FROM {table_name} WHERE {column_name} IS NOT NULL")
            stats["non_null_count"] = cursor.fetchone()[0]

            cursor.execute(f"SELECT COUNT(DISTINCT {column_name}) FROM {table_name}")
            stats["distinct_count"] = cursor.fetchone()[0]

            try:
                cursor.execute(f"SELECT MIN({column_name}), MAX({column_name}), AVG({column_name}) FROM {table_name}")
                row = cursor.fetchone()
                stats["min"] = row[0]
                stats["max"] = row[1]
                stats["avg"] = row[2]
            except:
                pass
        except Exception as e:
            stats["column_error"] = str(e)

    conn.close()
    return stats


def execute_ai_tool(tool_name: str, arguments: dict):
    """执行AI工具调用"""
    tool_functions = {
        "get_table_list": tool_get_table_list,
        "get_table_schema": tool_get_table_schema,
        "execute_sql_query": tool_execute_sql_query,
        "get_data_statistics": tool_get_data_statistics
    }

    if tool_name not in tool_functions:
        return {"error": f"未知的工具: {tool_name}"}

    try:
        return tool_functions[tool_name](**arguments)
    except Exception as e:
        return {"error": f"工具执行失败: {str(e)}"}


@main_bp.route('/api/ai-data-analysis/tables', methods=['GET'])
@login_required
def api_ai_data_tables():
    """获取数据库表信息"""
    result = tool_get_table_list()
    tables_info = []

    for table_name in result.get('tables', []):
        schema = tool_get_table_schema(table_name)
        tables_info.append({
            'name': table_name,
            'columns': len(schema.get('columns', [])),
            'rows': schema.get('row_count', 0)
        })

    return jsonify({
        'code': 0,
        'data': tables_info
    })


@main_bp.route('/api/ai-data-analysis/chat', methods=['POST'])
@login_required
def api_ai_data_analysis_chat():
    """AI数据分析对话接口（支持工具调用）"""
    import requests as http_requests
    import json

    data = request.get_json() or {}
    message = data.get('message', '').strip()
    engine_id = data.get('engine_id')
    history = data.get('history', [])

    if not message:
        return jsonify({'code': 1, 'msg': '请输入消息内容'})

    # 获取AI引擎
    if engine_id:
        engine = AIEngine.query.get(engine_id)
    else:
        engine = AIEngine.query.filter_by(is_default=True, status=1).first()
        if not engine:
            engine = AIEngine.query.filter_by(status=1).first()

    if not engine:
        return jsonify({'code': 1, 'msg': '没有可用的AI引擎，请先配置AI引擎'})

    if engine.status != 1:
        return jsonify({'code': 1, 'msg': '该AI引擎已禁用'})

    # 构建系统提示
    system_prompt = """你是一个专业的数据分析助手，负责帮助用户分析和理解SQLite数据库中的数据。

你有以下工具可以使用：
1. get_table_list - 获取数据库中所有表的列表
2. get_table_schema - 获取指定表的结构信息
3. execute_sql_query - 执行SQL查询（仅支持SELECT）
4. get_data_statistics - 获取表或列的统计信息

请根据用户的问题，主动使用这些工具来获取信息，然后给出专业的分析结果。
回复时请使用中文，格式清晰易读。对于数据分析结果，可以使用markdown表格来展示数据。"""

    # 构建消息
    messages = [{'role': 'system', 'content': system_prompt}]
    for h in history[-10:]:
        messages.append({'role': h.get('role', 'user'), 'content': h.get('content', '')})
    messages.append({'role': 'user', 'content': message})

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {engine.api_key}'
    }

    # 工具调用循环
    max_iterations = 10
    tool_calls_log = []

    for iteration in range(max_iterations):
        payload = {
            'model': engine.model_name,
            'messages': messages,
            'max_tokens': engine.max_tokens,
            'temperature': 0.1,
            'tools': AI_DATA_TOOLS,
            'tool_choice': 'auto'
        }

        try:
            response = http_requests.post(
                engine.api_url,
                headers=headers,
                json=payload,
                timeout=120
            )

            if response.status_code != 200:
                error_msg = f'AI服务响应错误 (HTTP {response.status_code})'
                try:
                    error_data = response.json()
                    if 'error' in error_data:
                        error_obj = error_data['error']
                        if isinstance(error_obj, dict):
                            error_msg = error_obj.get('message', error_msg)
                        else:
                            error_msg = str(error_obj)
                except:
                    pass
                return jsonify({'code': 1, 'msg': error_msg})

            result = response.json()

            if 'choices' not in result or len(result['choices']) == 0:
                return jsonify({'code': 1, 'msg': 'AI返回格式错误'})

            choice = result['choices'][0]
            ai_message = choice.get('message', {})
            tool_calls = ai_message.get('tool_calls', [])

            if tool_calls:
                # 有工具调用
                messages.append(ai_message)

                for tool_call in tool_calls:
                    tool_id = tool_call.get('id', '')
                    function = tool_call.get('function', {})
                    tool_name = function.get('name', '')
                    arguments_str = function.get('arguments', '{}')

                    try:
                        arguments = json.loads(arguments_str)
                    except:
                        arguments = {}

                    # 执行工具
                    tool_result = execute_ai_tool(tool_name, arguments)
                    tool_calls_log.append({
                        'tool': tool_name,
                        'args': arguments,
                        'result_preview': str(tool_result)[:200]
                    })

                    messages.append({
                        'role': 'tool',
                        'tool_call_id': tool_id,
                        'content': json.dumps(tool_result, ensure_ascii=False)
                    })

                continue
            else:
                # 没有工具调用，返回最终回复
                content = ai_message.get('content', '')
                return jsonify({
                    'code': 0,
                    'data': {
                        'reply': content,
                        'engine': engine.name,
                        'model': result.get('model', engine.model_name),
                        'tool_calls': tool_calls_log
                    }
                })

        except http_requests.Timeout:
            return jsonify({'code': 1, 'msg': 'AI响应超时，请稍后重试'})
        except http_requests.RequestException as e:
            return jsonify({'code': 1, 'msg': f'网络错误: {str(e)[:100]}'})
        except Exception as e:
            return jsonify({'code': 1, 'msg': f'请求失败: {str(e)[:100]}'})

    return jsonify({'code': 1, 'msg': '达到最大迭代次数'})



