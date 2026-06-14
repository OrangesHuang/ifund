"""基金列表相关模型（声明用途；实际读写走 app.db）。"""
from __future__ import annotations

from app.database import db


class Fund(db.Model):
    """基金名单表 funds。"""

    __tablename__ = "funds"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String, unique=True, nullable=False)
    name = db.Column(db.String, nullable=False)
    type = db.Column(db.String, default="")
    fund_type = db.Column(db.String, default="")
    pinyin_abbr = db.Column(db.String, default="")
    pinyin_full = db.Column(db.String, default="")
    created_at = db.Column(db.String)
    updated_at = db.Column(db.String)


class FundType(db.Model):
    """基金分类派生表 fund_types。"""

    __tablename__ = "fund_types"

    id = db.Column(db.Integer, primary_key=True)
    type_name = db.Column(db.String, unique=True, nullable=False)
    category = db.Column(db.String, default="")


class QueryPreset(db.Model):
    """用户查询预设表 query_presets。"""

    __tablename__ = "query_presets"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String, nullable=False)
    filters_json = db.Column(db.String, default="{}")
    created_at = db.Column(db.String)
