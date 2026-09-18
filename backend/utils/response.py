# -*- coding: utf-8 -*-
"""统一 API 响应格式。

所有接口返回 JSON：{"code": 0, "msg": "...", "data": ...}
  - code == 0：成功
  - code != 0：失败（前端弹 toast 显示 msg）

HTTP 状态码约定：
  - 200 + code!=0：业务错误
  - 401：未登录 / 登录失效（前端据此跳转登录页）
  - 403：无权限
"""
from flask import jsonify


def ok(data=None, msg="success"):
    """成功响应。"""
    return jsonify({"code": 0, "msg": msg, "data": data})


def fail(msg="操作失败", code=1, http_status=200):
    """失败响应。http_status 默认 200，业务错误不改变 HTTP 状态；认证/鉴权错误用 401/403。"""
    return jsonify({"code": code, "msg": msg, "data": None}), http_status
