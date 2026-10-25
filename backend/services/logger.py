# -*- coding: utf-8 -*-
"""操作日志：把关键操作写入 operation_logs 表。

注意：log_action 只做 add，不 commit。由调用方在业务提交时一并 commit，
保证「业务变更」与「日志」同处一个事务，要么都成功、要么都回滚。

也支持在后台线程（没有 HTTP 请求）里调用：此时 ip 记为空。
"""
from flask import has_request_context, request
from models import OperationLog
from extensions import db


def _client_ip():
    """取真实 IP（优先 X-Forwarded-For）；无请求上下文时返回 None。"""
    if not has_request_context():
        return None
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()
    return ip or None


def log_action(user_id, action, detail=""):
    """记录一条操作日志。user_id 可为 None（系统/后台任务）。"""
    db.session.add(OperationLog(user_id=user_id, action=action, detail=detail, ip=_client_ip()))
