# -*- coding: utf-8 -*-
"""登录态管理：JWT 签发/校验，以及登录、管理员权限装饰器。

采用无状态 JWT（存用户 id / role），前端把 token 放
Authorization: Bearer <token> 头里，随每次请求携带。
"""
import jwt
from functools import wraps
from time import time
from flask import request, g, current_app
from models import User
from extensions import db
from utils.response import fail


def _encode(payload):
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def _decode(token):
    return jwt.decode(token, current_app.config["JWT_SECRET"], algorithms=["HS256"])


def issue_token(user):
    """签发正式登录态 token（有效期见 JWT_EXPIRES）。"""
    return _encode({
        "uid": user.id,
        "role": user.role,
        "exp": int(time()) + current_app.config["JWT_EXPIRES"],
    })


def login_required(fn):
    """校验登录态，把当前用户挂到 g.user。"""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
        if not token:
            return fail("未登录", code=401, http_status=401)
        try:
            payload = _decode(token)
        except jwt.ExpiredSignatureError:
            return fail("登录已过期", code=401, http_status=401)
        except jwt.InvalidTokenError:
            return fail("无效的登录凭证", code=401, http_status=401)
        user = db.session.get(User, payload.get("uid"))
        if user is None:
            return fail("用户不存在", code=401, http_status=401)
        g.user = user
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    """管理员权限校验（叠加在 login_required 之上）。"""
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if g.user.role != "admin":
            return fail("无权限访问", code=403, http_status=403)
        return fn(*args, **kwargs)
    return wrapper
