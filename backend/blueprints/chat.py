# -*- coding: utf-8 -*-
"""联系工作室（留言聊天）：发送文字/图片/视频/语音/文件、历史记录、已读、会话列表。

刷新策略为前端轮询（无 WebSocket 依赖），接口幂等且轻量：
  - 学生：固定以自己 id 为会话（user_id = g.user.id）
  - 管理员：通过 user_id 参数指定与某个学生的会话
拉取历史即顺带把对方发来的消息置为已读。
"""
import os
import uuid
from datetime import datetime

from flask import Blueprint, request, g, current_app
from sqlalchemy import case, func

from extensions import db
from models import User, ChatMessage
from utils.response import ok, fail
from utils.auth import login_required, admin_required
from services.logger import log_action

bp = Blueprint("chat", __name__)

# 消息类型与对应限制
TYPE_SET = {"text", "image", "video", "voice", "file"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
VIDEO_EXT = {".mp4", ".webm", ".mov", ".m4v", ".3gp"}
VOICE_EXT = {".webm", ".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".amr"}
SIZE_LIMIT = {
    "image": 10 * 1024 * 1024,   # 10MB
    "video": 50 * 1024 * 1024,   # 50MB
    "voice": 10 * 1024 * 1024,   # 10MB
    "file": 50 * 1024 * 1024,    # 50MB
}
MAX_TEXT_LEN = 2000


def _save_chat_file(file_storage, subdir):
    """保存聊天附件，返回（相对 URL, 字节数）；空文件抛 ValueError。"""
    if file_storage is None or file_storage.filename == "":
        raise ValueError("请选择文件")
    data = file_storage.read()
    if len(data) == 0:
        raise ValueError("文件为空")
    sub = f"chat/{subdir}/{datetime.now().strftime('%Y%m')}/{uuid.uuid4().hex}{os.path.splitext(file_storage.filename)[1].lower()}"
    abs_path = os.path.join(current_app.config["UPLOAD_DIR"], sub)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as f:
        f.write(data)
    return "uploads/" + sub, len(data)


def _peer_brief(user):
    return {
        "id": user.id,
        "name": user.name,
        "student_id": user.student_id,
        "college": user.college,
    }


@bp.route("/send", methods=["POST"])
@login_required
def send():
    """发送消息（multipart/form-data；管理员需带 user_id 指定会话学生）。"""
    ctype = request.form.get("content_type", "text")
    if ctype not in TYPE_SET:
        return fail("不支持的消息类型", code=1002)

    # 会话归属与发送方角色
    if g.user.role == "admin":
        target = db.session.get(User, request.form.get("user_id", type=int))
        if target is None:
            return fail("请指定会话学生", code=1002)
        owner_id, sender_role = target.id, "admin"
    else:
        owner_id, sender_role = g.user.id, "user"

    content = (request.form.get("content") or "").strip()
    duration = request.form.get("duration", type=int)

    if ctype == "text":
        if not content:
            return fail("消息内容不能为空", code=1002)
        if len(content) > MAX_TEXT_LEN:
            return fail(f"消息不能超过 {MAX_TEXT_LEN} 字", code=1002)
        file_url = file_name = None
        file_size = duration = None
    else:
        # 媒体/文件消息：按类型校验扩展名与大小
        file = request.files.get("file")
        if file is None or file.filename == "":
            return fail("请选择要发送的文件", code=1002)
        ext = os.path.splitext(file.filename)[1].lower()
        if ctype == "image" and ext not in IMAGE_EXT:
            return fail("仅支持 jpg/png/webp/gif/bmp 图片", code=1002)
        if ctype == "video" and ext not in VIDEO_EXT:
            return fail("仅支持 mp4/webm/mov 等视频格式", code=1002)
        if ctype == "voice" and ext not in VOICE_EXT:
            return fail("不支持的录音格式", code=1002)
        try:
            file_url, file_size = _save_chat_file(file, {"voice": "voice"}.get(ctype, ctype))
        except ValueError as e:
            return fail(str(e), code=1002)
        if file_size > SIZE_LIMIT[ctype]:
            os.remove(os.path.join(current_app.config["UPLOAD_DIR"], file_url[len("uploads/"):]))
            return fail("文件超过大小限制", code=1002)
        file_name = file.filename
        duration = max(0, duration or 0) if ctype in ("voice", "video") else None

    msg = ChatMessage(
        user_id=owner_id,
        sender_role=sender_role,
        sender_id=g.user.id,
        content_type=ctype,
        content=content if ctype == "text" else None,
        file_url=file_url,
        file_name=file_name,
        file_size=file_size,
        duration=duration,
    )
    db.session.add(msg)
    log_action(g.user.id, "chat_send", f"发送{ctype}消息")
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("发送失败，请重试", code=500, http_status=500)
    return ok(msg.to_dict(), msg="已发送")


@bp.route("/messages", methods=["GET"])
@login_required
def messages():
    """拉取会话历史（最新 200 条，升序），并顺带把对方消息置为已读。"""
    peer = None
    if g.user.role == "admin":
        uid = request.args.get("user_id", type=int)
        target = db.session.get(User, uid) if uid else None
        if target is None:
            return fail("请指定会话学生", code=1002)
        q = ChatMessage.query.filter_by(user_id=uid)
        peer = _peer_brief(target)
        # 管理员读 → 学生的消息已读
        ChatMessage.query.filter_by(user_id=uid, sender_role="user", is_read=False) \
            .update({"is_read": True}, synchronize_session=False)
    else:
        q = ChatMessage.query.filter_by(user_id=g.user.id)
        # 学生读 → 管理员的消息已读
        ChatMessage.query.filter_by(user_id=g.user.id, sender_role="admin", is_read=False) \
            .update({"is_read": True}, synchronize_session=False)

    rows = q.order_by(ChatMessage.id.asc()).limit(200).all()
    db.session.commit()
    return ok({"peer": peer, "messages": [m.to_dict() for m in rows]})


@bp.route("/conversations", methods=["GET"])
@admin_required
def conversations():
    """管理员：会话列表（每个学生最近一条消息 + 未读数），按最近消息倒序。"""
    last = (
        db.session.query(
            ChatMessage.user_id.label("uid"),
            func.max(ChatMessage.id).label("last_id"),
        )
        .group_by(ChatMessage.user_id)
        .subquery()
    )
    unread_agg = (
        db.session.query(
            ChatMessage.user_id.label("uid"),
            func.count(ChatMessage.id).label("unread"),
        )
        .filter_by(sender_role="user", is_read=False)
        .group_by(ChatMessage.user_id)
        .subquery()
    )
    rows = (
        db.session.query(User, ChatMessage, func.coalesce(unread_agg.c.unread, 0))
        .join(last, User.id == last.c.uid)
        .join(ChatMessage, ChatMessage.id == last.c.last_id)
        .outerjoin(unread_agg, User.id == unread_agg.c.uid)
        .order_by(ChatMessage.created_at.desc())
        .all()
    )
    data = [
        {
            "user": _peer_brief(user),
            "last_message": msg.to_dict(),
            "unread": int(unread or 0),
        }
        for user, msg, unread in rows
    ]
    return ok(data)


@bp.route("/contacts", methods=["GET"])
@admin_required
def contacts():
    """管理员：可发起会话的联系人名单（全部非管理员用户，按学号排序）。

    多管理员共用一个收件箱：任何管理员都可主动联系任意学生，
    会话内容对所有管理员可见。
    """
    rows = User.query.filter(User.role != "admin").order_by(User.student_id.asc()).all()
    return ok([_peer_brief(u) for u in rows])


@bp.route("/unread", methods=["GET"])
@login_required
def unread():
    """未读消息数：学生看管理员发来的未读；管理员看所有学生的未读。"""
    if g.user.role == "admin":
        cnt = ChatMessage.query.filter_by(sender_role="user", is_read=False).count()
    else:
        cnt = ChatMessage.query.filter_by(user_id=g.user.id, sender_role="admin", is_read=False).count()
    return ok({"count": cnt})
