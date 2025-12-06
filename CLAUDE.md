# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个基于 Flask 的**政企智能舆情分析系统**，用于舆情数据采集、分析和管理。

## 常用命令

```bash
# 激活虚拟环境
.\venv\Scripts\activate   # Windows
source venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements.txt

# 运行应用（自动初始化数据库和创建默认管理员）
python manage.py

# Flask CLI 命令
flask init-db                              # 初始化数据库
flask create-admin --username=admin --password=admin123  # 创建管理员
flask db migrate -m "message"              # 生成迁移脚本
flask db upgrade                           # 应用迁移
```

默认访问地址: http://localhost:5000
默认管理员: admin / admin123

## 架构概述

### 技术栈
- **后端**: Flask 3.0 + Flask-SQLAlchemy + Flask-Migrate
- **前端**: Layui v2.13.2 (静态资源在 `static/layui-v2.13.2/`)
- **数据库**: SQLite (位于 `instance/app.db`)

### 核心结构
```
app/
├── __init__.py         # 应用工厂 (create_app)
├── models.py           # 数据模型
├── routes.py           # 路由和API定义 (main_bp 蓝图)
├── crawler.py          # 百度新闻爬虫 (BaiduNewsCrawler)
├── crawler_360kuai.py  # 360快资讯爬虫
├── crawler_xinhua.py   # 新华网爬虫
├── deep_crawler.py     # 深度采集模块 (RuleBasedCrawler)
└── templates/admin/    # 后台管理页面
```

### 关键设计模式
- **应用工厂模式**: `create_app()` 在 `app/__init__.py` 中创建应用实例
- **蓝图**: 使用 `main_bp` 蓝图组织路由
- **装饰器权限控制**: `@login_required` 和 `@admin_required` 在 `routes.py` 中定义

### API 规范
- JSON 响应格式: `{"code": 0, "msg": "...", "data": {...}}`
- code=0 表示成功，code=1 表示业务错误，code=401 表示未登录，code=403 表示无权限
- 分页接口返回: `{"code": 0, "count": total, "data": [...]}`

## 数据模型

| 模型 | 用途 |
|------|------|
| User | 用户账户，支持密码加密、登录锁定、角色权限 |
| SystemConfig | 键值对形式的系统配置存储 |
| CrawlRule | 采集规则库，XPath 规则配置 |
| CollectedNews | 采集的新闻数据 |
| AIEngine | AI引擎配置（API地址、密钥、模型参数） |
| CrawlerConfig | 爬虫配置，支持动态加载 |

## 采集系统架构

### 数据采集流程
1. **数据采集** (`data_collect.html`): 从配置的爬虫源搜索新闻，保存到 CollectedNews
2. **深度采集** (`deep_crawler.py`): 根据规则库获取新闻正文内容
3. **数据仓库** (`data_warehouse.html`): 管理已采集的数据

### 规则匹配优先级
1. 用户指定的规则（手动选择）
2. 数据库规则按适用来源匹配
3. 数据库规则按域名匹配
4. 内置规则 `BUILTIN_RULES`（针对常用新闻源）
5. 通用解析 `_parse_generic`（自动提取正文）

### 爬虫动态加载
爬虫通过 `CrawlerConfig` 配置，使用 `importlib` 动态加载：
```python
module = importlib.import_module(crawler_config.crawler_module)
crawler_cls = getattr(module, crawler_config.crawler_class)
```

## 前端开发注意事项

### Jinja2 与 laytpl 模板语法冲突
在 `<script type="text/html">` 模板中使用 laytpl 语法（`{{d.xxx}}`）时，必须用 `{% raw %}` 包裹：
```html
<script type="text/html" id="myTpl">
{% raw %}
<div>{{d.name}}</div>
{% endraw %}
</script>
```

### Layui jQuery 引用
在 `layui.use` 回调中使用 jQuery 需要显式引入：
```javascript
layui.use(['layer', 'table'], function(){
    var $ = layui.$;  // 必须显式引入
    // ...
});
```

## 配置

配置类在 `config.py` 中定义，通过环境变量或默认值配置：
- `SECRET_KEY`: 会话密钥
- `DATABASE_URL`: 数据库连接（默认 SQLite）
