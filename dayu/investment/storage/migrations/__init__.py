"""Alembic 迁移子包。

承载 ``dayu_platform`` schema 的迁移真源：``env.py`` 负责 bootstrap
DSN 读取、superuser admission 预检与事务上下文；``versions/`` 存放
transactional upgrade/downgrade 脚本。schema 的唯一创建真源在本包，
任何其它 import 路径禁止 ``metadata.create_all()``。
"""
