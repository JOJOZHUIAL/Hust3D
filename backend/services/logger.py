# -*- coding: utf-8 -*-
"""操作日志：把关键操作写入 operation_logs 表。

注意：log_action 只做 add，不 commit。由调用方在业务提交时一并 commit，
保证「业务变更」与「日志」同处一个事务，要么都成功、要么都回滚。
"""
from flask import request
from models import OperationLog
from extensions import db


def log_action(user_id, action, detail=""):
    """记录一条操作日志。user_id 可为 None。"""
    # 从反向代理头里取真实 IP，优先 X-Forwarded-For
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()
    db.session.add(OperationLog(user_id=user_id, action=action, detail=detail, ip=ip))
