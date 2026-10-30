# -*- coding: utf-8 -*-
"""反馈超时过期处理。

规则：申请被标记「打印完成」后 FEEDBACK_EXPIRE_DAYS 天（默认 7 天，可在 .env 调整）
内没有提交反馈，就标记为**已过期** —— 状态仍然是「已完成」，只是多记一个
`expired_at` 时间；列表/详情上会显示「已过期」标记，补交反馈需要管理员审核且不发奖励。

实现说明：项目未引入定时任务依赖，这里采用「读取时惰性扫描 + 落库」的方式，
在列表 / 详情 / 反馈等入口调用，保证任何时刻用户看到的状态都与规则一致。

**双向校准**：改完 .env 的 FEEDBACK_EXPIRE_DAYS 重启后，之前被标记过期的记录会按新
天数重新判定 —— 期限变长（或关闭过期）时会把不该过期的记录恢复成未过期，
期限变短时会把新超期的记录补标上，不需要手动改数据库。
"""
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy import func

from extensions import db
from models import PrintApplication, feedback_expire_days


def _base_expr():
    """计时基准：completed_at → printed_at → updated_at。"""
    return func.coalesce(
        PrintApplication.completed_at,
        PrintApplication.printed_at,
        PrintApplication.updated_at,
    )


def expire_stale_applications():
    """按当前配置刷新过期标记（双向），返回本次变更的条数。

    只写 `expired_at`，不动 `status`（保持 completed）。
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

    if days <= 0:
        # 关闭过期机制：把之前标记过的一律恢复
        rows = (
            db.session.query(PrintApplication)
            .filter(PrintApplication.expired_at.isnot(None))
            .all()
        )
        for r in rows:
            r.expired_at = None
            changed += 1
        if changed:
            db.session.commit()
        return changed

    cutoff = now - timedelta(days=days)
    base = _base_expr()

    # ① 该过期但还没标记的
    stale = (
        db.session.query(PrintApplication)
        .filter(
            PrintApplication.status == "completed",
            PrintApplication.feedback_url.is_(None),
            PrintApplication.expired_at.is_(None),
            base <= cutoff,
        )
        .all()
    )
    for r in stale:
        r.expired_at = now
        changed += 1

    # ② 不该过期却已被标记的（改小了天数 / 之前误标的）→ 恢复
    revived = (
        db.session.query(PrintApplication)
        .filter(
            PrintApplication.status == "completed",
            PrintApplication.expired_at.isnot(None),
            base > cutoff,
        )
        .all()
    )
    for r in revived:
        r.expired_at = None
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
