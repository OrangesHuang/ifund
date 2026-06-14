"""Flask 应用工厂：注册蓝图、JWT、SQLite 建表、SPA fallback。"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_jwt_extended import JWTManager


def create_app() -> Flask:
    """创建并配置 Flask 应用。"""
    # pylint: disable=import-outside-toplevel
    load_dotenv()
    backend_dir = Path(__file__).resolve().parents[1]
    static_dir = backend_dir / "static"

    app = Flask(__name__, static_folder=str(static_dir), static_url_path="")
    secret_key = os.getenv("SECRET_KEY", "dev-secret")
    if len(secret_key) < 32:
        logging.warning(
            "SECRET_KEY 过弱（<32 字节）。对外暴露 API / 启用 PAT 前请在 .env 设置"
            "强随机密钥（如 python -c \"import secrets;print(secrets.token_hex(32))\"），"
            "否则 JWT 可被伪造。"
        )
    app.config["JWT_SECRET_KEY"] = secret_key
    app.config["JWT_TOKEN_LOCATION"] = ["headers"]
    app.config["JWT_HEADER_TYPE"] = "Bearer"
    JWTManager(app)

    # SQLite 后端：启动时自动建表（幂等）
    from app import db as database
    if os.getenv("DB_BACKEND", "sqlite").lower() == "sqlite":
        schema_sql = (backend_dir / "schema_sqlite.sql").read_text(encoding="utf-8")
        database.init_db(schema_sql)

    # 注册蓝图
    from app.routers.auth import bp as auth_bp
    from app.fund.api.router import bp as fund_bp
    from app.fund_detail.api.router import bp as fund_detail_bp
    from app.fund_holdings.api.router import bp as holdings_bp
    from app.fund_nav.api.router import bp as nav_bp
    from app.trade_calendar.api.router import bp as calendar_bp
    for blueprint in (auth_bp, fund_bp, fund_detail_bp, holdings_bp, nav_bp, calendar_bp):
        app.register_blueprint(blueprint)

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.errorhandler(404)
    def spa_fallback(_err):
        if request.path.startswith("/api"):
            return jsonify({"detail": "not found"}), 404
        index = static_dir / "index.html"
        if index.exists():
            return send_from_directory(str(static_dir), "index.html")
        return jsonify({"detail": "frontend not built"}), 404

    return app
