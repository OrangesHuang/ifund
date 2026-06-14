"""SQLAlchemy 全局实例：仅用于声明模型（文档化用途）。

本项目无 ORM 运行时——实际数据访问全部通过 ``app.db`` 的统一接口走原生 SQL。
此处的 ``db`` 不 ``init_app``、不建引擎、不执行查询。
"""
from __future__ import annotations

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
