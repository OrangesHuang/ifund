"""认证蓝图：注册 / 登录 / me / 个人访问令牌（PAT）。

PAT 用于机器/agent 长期调用：登录后创建 PAT（明文仅返回一次），
调用方用 PAT 经 ``/token/exchange`` 换取短期 JWT，业务端点继续用 JWT，无需改动。
"""
from __future__ import annotations

import datetime
import hashlib
import secrets

import bcrypt
from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from pydantic import ValidationError

from app import db as database
from app.schemas import Token, UserCreate

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _current_user():
    """按 JWT identity 取当前用户行（无则 None）。"""
    return database.select_one("users", {"username": f"eq.{get_jwt_identity()}"})


def _gen_pat() -> tuple[str, str, str]:
    """生成 (明文, sha256 摘要, 展示前缀)。明文只在创建时返回一次。"""
    raw = "ifd_" + secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return raw, digest, raw[:12]


def _bearer_token() -> str:
    """从 Authorization 头取 Bearer 值（无则空串）。"""
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


@bp.post("/register")
def register():
    """创建用户（username 唯一）。"""
    try:
        payload = UserCreate(**(request.get_json(silent=True) or {}))
    except ValidationError as exc:
        return jsonify({"detail": exc.errors()}), 422
    if database.select_one("users", {"username": f"eq.{payload.username}"}):
        return jsonify({"detail": "用户名已存在"}), 400
    hashed = bcrypt.hashpw(payload.password.encode(), bcrypt.gensalt()).decode()
    user = database.insert("users", {"username": payload.username, "hashed_password": hashed})
    return jsonify({"id": user["id"], "username": user["username"]}), 201


@bp.post("/login")
def login():
    """校验密码，返回 access_token。接受 JSON 或 form。"""
    data = request.get_json(silent=True) or request.form.to_dict()
    username = str(data.get("username", ""))
    password = str(data.get("password", ""))
    user = database.select_one("users", {"username": f"eq.{username}"})
    if not user or not bcrypt.checkpw(password.encode(), user["hashed_password"].encode()):
        return jsonify({"detail": "用户名或密码错误"}), 401
    token = create_access_token(identity=username)
    return jsonify(Token(access_token=token).model_dump())


@bp.get("/me")
@jwt_required()
def me():
    """返回当前 JWT 用户名。"""
    return jsonify({"username": get_jwt_identity()})


@bp.post("/tokens")
@jwt_required()
def create_token():
    """为当前用户创建 PAT，返回明文（仅此一次）。"""
    user = _current_user()
    if not user:
        return jsonify({"detail": "user not found"}), 404
    name = str((request.get_json(silent=True) or {}).get("name", ""))
    raw, digest, prefix = _gen_pat()
    row = database.insert("api_tokens", {
        "user_id": user["id"], "name": name,
        "token_hash": digest, "token_prefix": prefix,
    })
    return jsonify({"id": row["id"], "name": name, "token": raw, "prefix": prefix}), 201


@bp.get("/tokens")
@jwt_required()
def list_tokens():
    """列出当前用户的 PAT（不含明文）。"""
    user = _current_user()
    rows = database.select("api_tokens", {
        "user_id": f"eq.{user['id'] if user else 0}", "order": "created_at.desc",
    })
    return jsonify([{
        "id": r["id"], "name": r["name"], "prefix": r["token_prefix"],
        "revoked": bool(r["revoked"]), "last_used_at": r.get("last_used_at"),
        "created_at": r.get("created_at"),
    } for r in rows])


@bp.delete("/tokens/<int:token_id>")
@jwt_required()
def revoke_token(token_id):
    """吊销当前用户的某个 PAT（按 owner 隔离）。"""
    user = _current_user()
    database.update(
        "api_tokens",
        {"id": token_id, "user_id": user["id"] if user else 0},
        {"revoked": 1},
    )
    return jsonify({"ok": True})


@bp.post("/token/exchange")
def exchange_token():
    """用 PAT（Bearer）换取短期 JWT；PAT 无效/已吊销则 401。"""
    raw = _bearer_token()
    if not raw:
        return jsonify({"detail": "missing api token"}), 401
    digest = hashlib.sha256(raw.encode()).hexdigest()
    row = database.select_one("api_tokens", {"token_hash": f"eq.{digest}"})
    if not row or row.get("revoked"):
        return jsonify({"detail": "invalid api token"}), 401
    user = database.select_one("users", {"id": f"eq.{row['user_id']}"})
    if not user:
        return jsonify({"detail": "user not found"}), 401
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    database.update("api_tokens", {"id": row["id"]}, {"last_used_at": now})
    token = create_access_token(identity=user["username"])
    return jsonify(Token(access_token=token).model_dump())
