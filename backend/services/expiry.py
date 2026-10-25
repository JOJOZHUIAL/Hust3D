# -*- coding: utf-8 -*-
"""反馈超时过期处理。

规则：申请被标记「打印完成」后 FEEDBACK_EXPIRE_DAYS 天（默认 7 天）内没有提交反馈，
就标记为**已过期** —— 注意状态仍然是「已完成」，只是多记一个 `expired_at` 时间：
此后不能再上传反馈、也不再发放反馈奖励，列表/详情上会显示「已过期」标记。

实现说明：项目未引入定时任务依赖，这里采用「读取时惰性扫描 + 落库」的方式，
在列表 / 详情 / 反馈等入口调用，保证任何时刻用户看到的状态都与规则一致。
"""
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy import func

from extensions import db
from models import PrintApplication, feedback_expire_days


def expire_stale_applications():
    """把超期未反馈的「已完成」申请标记为已过期，返回本次新过期的条数。

    只写 `expired_at`，不动 `status`（保持 completed）；计时基准与
    models.feedback_deadline() 保持一致：completed_at → printed_at → updated_at。
    """
    now = datetime.now()
    changed = 0

    # 兼容历史数据：旧版本把过期写成独立状态 expired，这里统一改回 completed + expired_at
    legacy = (
        db.session.query(PrintApplication)
        .filter(PrintApplication.status == "expired")
        .all()
    )
    for r in legacy:
        r.status = "completed"
        if r.expired_at is None:
            r.expired_at = now
        changed += 1

    days = feedback_expire_days()
    if days > 0:  # 0/负数表示关闭过期机制
        cutoff = now - timedelta(days=days)
        base = func.coalesce(
            PrintApplication.completed_at,
            PrintApplication.printed_at,
            PrintApplication.updated_at,
        )
        rows = (
            db.session.query(PrintApplication)
            .filter(
                PrintApplication.status == "completed",
                PrintApplication.feedback_url.is_(None),
                PrintApplication.expired_at.is_(None),
                base <= cutoff,
            )
            .all()
        )
        for r in rows:
            r.expired_at = now
            changed += 1

    if changed:
        db.session.commit()
    return changed


def expire_stale_silently():
    """安全包装：任何异常都不影响主流程（读接口不应因过期扫描失败而报错）。"""
    try:
        return expire_stale_applications()
    except Exception:
        db.session.rollback()
        current_app.logger.warning("反馈过期扫描失败", exc_info=True)
        return 0
