# -*- coding: utf-8 -*-
"""
添加爬虫配置新字段

修订 ID: 20241205_add_crawler_config_fields
修订日期: 2024-12-05
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20241205_add_crawler_config_fields'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """升级数据库"""
    # 添加新字段
    op.add_column('crawler_configs', sa.Column('crawler_type', sa.String(length=20), nullable=False, server_default='html_parser'))
    op.add_column('crawler_configs', sa.Column('request_method', sa.String(length=10), nullable=False, server_default='GET'))
    op.add_column('crawler_configs', sa.Column('search_params_template', sa.Text(), nullable=True))
    op.add_column('crawler_configs', sa.Column('pagination_config', sa.Text(), nullable=True))
    op.add_column('crawler_configs', sa.Column('parse_config', sa.Text(), nullable=True))
    op.add_column('crawler_configs', sa.Column('analyzed_config', sa.Text(), nullable=True))
    op.add_column('crawler_configs', sa.Column('is_analyzed', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('crawler_configs', sa.Column('is_template', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('crawler_configs', sa.Column('page_size', sa.Integer(), nullable=False, server_default='10'))
    op.add_column('crawler_configs', sa.Column('last_error', sa.Text(), nullable=True))

    print("✅ 爬虫配置表升级完成")


def downgrade():
    """降级数据库"""
    # 删除新字段
    op.drop_column('crawler_configs', 'crawler_type')
    op.drop_column('crawler_configs', 'request_method')
    op.drop_column('crawler_configs', 'search_params_template')
    op.drop_column('crawler_configs', 'pagination_config')
    op.drop_column('crawler_configs', 'parse_config')
    op.drop_column('crawler_configs', 'analyzed_config')
    op.drop_column('crawler_configs', 'is_analyzed')
    op.drop_column('crawler_configs', 'is_template')
    op.drop_column('crawler_configs', 'page_size')
    op.drop_column('crawler_configs', 'last_error')

    print("✅ 爬虫配置表降级完成")


if __name__ == '__main__':
    print("请使用 flask db upgrade/downgrade 命令执行此迁移")
    print("升级: flask db upgrade 20241205_add_crawler_config_fields")
    print("降级: flask db downgrade 20241205_add_crawler_config_fields")
