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
        if g.user.role not in ("admin", "superadmin"):
            return fail("无权限访问", code=403, http_status=403)
        return fn(*args, **kwargs)
    return wrapper


def super_required(fn):
    """超级管理员权限校验（叠加在 admin_required 之上）。"""
    @wraps(fn)
    @admin_required
    def wrapper(*args, **kwargs):
        if g.user.role != "superadmin":
            return fail("仅超级管理员可操作", code=403, http_status=403)
        return fn(*args, **kwargs)
    return wrapper


def resolve_operator(data=None, required=True):
    """确定这次操作「实际由谁完成」，返回 (操作人, 错误响应)。

    - 普通管理员/超管：操作人就是当前登录用户；
    - 公共管理员（admin 共享号）：请求里必须带 operator_student_id，
      按学号找到对应账号，把他的身份记到审批人/打印人/拆封人上，
      这样多人用同一个公共号也能追溯到具体的人。
    """
    user = getattr(g, "user", None)
    if user is None:
        return None, fail("未登录", code=401, http_status=401)
    if not getattr(user, "is_shared_admin", False):
        return user, None

    sid = ((data or {}).get("operator_student_id") or "").strip()
    if not sid:
        if not required:
            return user, None
        return None, fail("请填写实际操作人的学号（公共管理员账号需要记录操作人）", code=1002)

    operator = db.session.query(User).filter_by(student_id=sid).first()
    if operator is None:
        return None, fail(f"未找到学号 {sid} 的账号，请让对方先登录一次系统", code=1002)
    return operator, None
