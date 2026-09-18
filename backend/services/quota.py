# -*- coding: utf-8 -*-
"""配额与学期计算。

规则：每学期默认 2 次打印。学期切换（用户 semester 字段与当前学期不一致）时
自动把 remaining_quota 重置为默认值。
"""
from datetime import datetime
from flask import current_app


def current_semester():
    """计算当前学期字符串，形如 '2026-1'、'2026-2'。

    约定：春季学期（约 2~7 月）= 1，秋季学期（约 8 月~次年 1 月）= 2。
    """
    now = datetime.now()
    if 2 <= now.month <= 7:
        return f"{now.year}-1"
    return f"{now.year}-2"


def ensure_quota(user):
    """学期切换时自动重置配额，返回当前剩余次数。

    会就地修改 user 对象，是否落库由调用方决定（调用方最后统一 commit）。
    """
    sem = current_semester()
    if user.semester != sem:
        user.semester = sem
        user.remaining_quota = current_app.config["DEFAULT_QUOTA"]
    return user.remaining_quota
