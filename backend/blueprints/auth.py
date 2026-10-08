# -*- coding: utf-8 -*-
"""认证模块：教务系统统一认证（CAS）登录 → 签发 token。

整体流程（纯网页端，教务统一认证）：
  1. 前端请求 /api/auth/captcha 获取图形验证码（后端同时建立验证码会话）；
  2. 用户输入学号、密码、验证码，前端调 /api/auth/cas-login；
  3. 后端用同一会话向教务系统提交登录，成功后按学号查/建用户并签发 JWT。
"""
import jwt
from flask import Blueprint, request, current_app
from extensions import db
from models import User
from utils.response import ok, fail
from utils.auth import issue_token
from services import cas
from services.quota import ensure_quota
from services.logger import log_action

bp = Blueprint("auth", __name__)


@bp.route("/captcha", methods=["GET"])
def captcha():
    """获取教务系统登录验证码（真实模式）。

    返回 { captcha_required, captcha_id, captcha_img }，其中 captcha_img 为 base64 图片。
    mock 模式下 captcha_required=False，前端不展示验证码。
    """
    if current_app.config["CAS_MOCK"]:
        return ok({"captcha_required": False, "captcha_id": None, "captcha_img": None, "captcha_type": None})
    try:
        captcha_id, img_b64, mime = cas.fetch_captcha()
    except cas.CasError as e:
        return fail(str(e), code=1004)
    return ok({"captcha_required": True, "captcha_id": captcha_id,
               "captcha_img": img_b64, "captcha_type": mime})


@bp.route("/cas-login", methods=["POST"])
def cas_login():
    """教务系统学号密码登录：校验 → 按学号查/建用户 → 返回正式 token。"""
    data = request.get_json(silent=True) or {}
    student_id = (data.get("student_id") or "").strip()
    password = data.get("password") or ""
    captcha_id = data.get("captcha_id") or ""
    captcha_code = (data.get("captcha_code") or "").strip()

    if not student_id or not password:
        return fail("请输入学号和密码", code=1002)

    # 先查本地用户，判断是否已缓存完整姓名+学院；有则本次登录只做密码校验，
    # 跳过教务系统个人信息抓取（减少对学校系统的访问，也规避其网络不稳定）
    user = db.session.query(User).filter_by(student_id=student_id).first()
    need_profile = (user is None) or not (user.name and user.college)

    # 对接教务系统校验（password 仅用于向学校提交，不落库不记录）
    try:
        name, college = cas.cas_login(
            student_id, password, captcha_id, captcha_code, need_profile=need_profile
        )
    except cas.CasError as e:
        return fail(str(e), code=1003)

    if user is None:
        user = User(student_id=student_id)
        db.session.add(user)
        # 立即 flush 生成主键，供日志与 token 使用
        db.session.flush()

    user.name = name or user.name
    user.college = college or user.college
    # 配额只在学期切换（含首次建号）时重置，避免同学期重复登录清空剩余次数
    ensure_quota(user)
    # 角色判定：超级管理员 > 管理员 > 普通用户（每次登录按配置刷新）
    if student_id in current_app.config.get("SUPER_ADMIN_STUDENT_IDS", []):
        user.role = "superadmin"
    elif student_id in current_app.config["ADMIN_STUDENT_IDS"]:
        user.role = "admin"
    else:
        user.role = "user"

    log_action(user.id, "cas_login", f"学号 {student_id} 登录成功")
    db.session.commit()

    token = issue_token(user)
    return ok({"token": token, "user": user.to_dict()}, msg="登录成功")


@bp.route("/logout", methods=["POST"])
def logout():
    """退出登录。

    JWT 无状态，退出由前端丢弃 token 完成；这里仅尽力解析用户并记一条日志。
    """
    token = request.headers.get("Authorization", "")
    uid = None
    if token:
        try:
            payload = jwt.decode(
                token.replace("Bearer ", ""), current_app.config["JWT_SECRET"], algorithms=["HS256"]
            )
            uid = payload.get("uid")
        except jwt.InvalidTokenError:
            pass
    if uid:
        log_action(uid, "logout", "退出登录")
        db.session.commit()
    return ok(msg="已退出登录")
