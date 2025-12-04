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
├── __init__.py     # 应用工厂 (create_app)，初始化扩展和注册蓝图
├── models.py       # 数据模型 (User, SystemConfig)
├── routes.py       # 路由和API定义 (main_bp 蓝图)
└── templates/      # Jinja2 模板
    ├── base.html           # 基础模板
    ├── login.html          # 登录页
    └── admin/              # 后台管理页面
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

## 配置

配置类在 `config.py` 中定义，通过环境变量或默认值配置：
- `SECRET_KEY`: 会话密钥
- `DATABASE_URL`: 数据库连接（默认 SQLite）
