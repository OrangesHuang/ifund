"""User 模型（声明用途；实际读写走 app.db 原生 SQL）。"""
from __future__ import annotations

from app.database import db


class User(db.Model):
    """账户表 users。"""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String, unique=True, nullable=False)
    hashed_password = db.Column(db.String, nullable=False)
    created_at = db.Column(db.String)
