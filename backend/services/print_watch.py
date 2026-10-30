# -*- coding: utf-8 -*-
"""打印进度监视：按打印机上报的**真实文件名**匹配申请，并自动完成。

核心问题：管理员点「开始打印」只是把申请指派给某台打印机，但打印机当时很可能
正在打别的文件（别的申请、甚至私人模型）。所以不能拿"绑定关系"冒充"正在打印"，
否则那份文件打到 100% 会把本申请误判为完成。

判定规则：
  1. 从打印机上报的 task_name / gcode_file / print_file 里提取**所有**申请编号
     （拓竹的打印文件名是「姓名+申请编号.stl」；一盘放多件时会用 + 拼起来，如
     `丘馗HUST3D20261017005 + 毛雨涵HUST3D20261017006 + 蒋昱昊HUST3D20261017007.stl`）；
  2. 本申请的 apply_no 出现在这批编号里，才算"这台打印机正在打本申请"：
     这时才回写进度、才认可"已开始打印"、才会在 100% 时自动完成；
     一盘多件时，盘里每个申请都会被一起跟踪、一起完成；
  3. 打印机在打别的文件（或文件名里没有申请编号）时，不记进度、不判开始、
     绝不自动完成，界面上显示打印机真实在打什么。
"""
import re
import threading
from datetime import datetime

from flask import current_app

from models import PrintApplication, Printer, feedback_expire_days
from extensions import db
from services import bambu
from services.logger import log_action
from services.notify import notify_pickup
from services.sms import notify_pickup_sms as sms_send_pickup

# 视为「真的开始打印了」的状态机取值
RUNNING_STATES = {"RUNNING", "PAUSE", "PAUSED", "PREPARE", "SLICING"}
# 视为「打印结束」的状态机取值
FINISH_STATES = {"FINISH"}

# 申请编号：HUST3D + YYYYMMDD + 三位流水（如 HUST3D20261017005）
APPLY_NO_RE = re.compile(r"HUST3D\d{11}", re.IGNORECASE)

_stop_event = threading.Event()
_thread = None
_thread_lock = threading.Lock()


def _as_int(val):
    """把 MQTT 上报的字符串/浮点进度转成整数，非法值返回 None。"""
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return None


def snapshot_task(snap):
    """打印机当前任务的文件名：优先 subtask_name（真实文件名），再退回 gcode_file。"""
    for key in ("task_name", "gcode_file", "print_file"):
        val = (snap or {}).get(key)
        if val:
            return str(val)
    return None


def apply_nos_from_file(name):
    """从打印文件名里提取**全部**申请编号（一盘多件会是 A + B + C.stl）。

    返回去重后的有序列表（保持文件里的出现顺序），提取不到返回空列表。
    """
    seen = []
    for m in APPLY_NO_RE.finditer(str(name or "")):
        code = m.group(0).upper()
        if code not in seen:
            seen.append(code)
    return seen


def apply_no_from_file(name):
    """单个编号（兼容旧调用）：取文件名里的第一个申请编号。"""
    codes = apply_nos_from_file(name)
    return codes[0] if codes else None


def _brief(app_obj):
    """申请的精简信息（给打印机状态页展示用）。"""
    applicant = app_obj.user.name if app_obj.user is not None else None
    return {
        "id": app_obj.id,
        "apply_no": app_obj.apply_no,
        "file_name": app_obj.file_name,
        "applicant": applicant,
        "status": app_obj.status,
        "progress": app_obj.print_progress,
        "state": app_obj.print_state,
        "printed_at": app_obj.printed_at.strftime("%Y-%m-%d %H:%M:%S") if app_obj.printed_at else None,
    }


def job_info(printer_id, snap):
    """解析某台打印机当前任务（供打印机状态页展示）。

    返回：
      task        —— 打印机上报的原始文件名（可能是 A + B + C.stl）
      codes       —— 从文件名里解析出的申请编号列表
      actuals     —— 命中这些编号的申请列表（真正在打的那一盘，可能多份）
      assignments —— 指派到本机、但打印机还没开始打它们的申请列表
    """
    task = snapshot_task(snap)
    codes = apply_nos_from_file(task)

    actuals = []
    if codes:
        rows = (
            db.session.query(PrintApplication)
            .filter(PrintApplication.apply_no.in_(codes))
            .order_by(PrintApplication.apply_no.asc())
            .all()
        )
        for a in rows:
            item = _brief(a)
            item["tracked"] = a.status == "printing"
            actuals.append(item)

    assignments = []
    if printer_id:
        rows = (
            db.session.query(PrintApplication)
            .filter(
                PrintApplication.printer_id == printer_id,
                PrintApplication.status == "printing",
            )
            .order_by(PrintApplication.printed_at.desc(), PrintApplication.id.desc())
            .all()
        )
        matched_ids = {x["id"] for x in actuals}
        assignments = [_brief(a) for a in rows if a.id not in matched_ids]

    return {
        "task": task,
        "codes": codes,
        "actuals": actuals,
        "assignments": assignments,
        # 兼容旧前端字段
        "actual": actuals[0] if actuals else None,
        "bound": assignments[0] if assignments else None,
    }


def tick():
    """扫描一次「打印中」的申请：按真实文件名确认后回写进度，必要时自动完成。

    返回本次自动完成的条数。必须在 Flask 应用上下文内调用。
    """
    rows = (
        db.session.query(PrintApplication)
        .filter(
            PrintApplication.status == "printing",
            PrintApplication.printer_id.isnot(None),
        )
        .all()
    )
    now = datetime.now()
    dirty = False
    done = 0
    sms_queue = []

    # —— 自动认领：打印机在打某个申请的文件，但该申请还没指派打印机 ——
    # （管理员点「开始打印」时没选打印机，或直接把一盘文件拿去 Bambu Studio 打了）
    for printer in db.session.query(Printer).all():
        snap = bambu.snapshot_for(printer)
        if not snap.get("online"):
            continue
        task = snapshot_task(snap)
        codes = apply_nos_from_file(task)
        if not codes:
            continue
        targets = (
            db.session.query(PrintApplication)
            .filter(
                PrintApplication.apply_no.in_(codes),
                PrintApplication.status == "printing",
                PrintApplication.printer_id.is_(None),
            )
            .all()
        )
        for target in targets:
            target.printer_id = printer.id
            target.printer_name = printer.name
            target.print_actual_file = task
            target.print_matched = True
            dirty = True
            log_action(None, "print_adopt",
                       f"打印机「{printer.name}」正在打印 {target.apply_no}，自动关联该申请")

    for app_obj in rows:
        printer = db.session.get(Printer, app_obj.printer_id)
        if printer is None:  # 打印机已被删除，退回手动完成
            continue
        # 拓竹空闲时上报稀疏：每轮主动要一次全量状态（内部有 5 秒节流），保证进度新鲜
        bambu.request_status(printer.id)
        snap = bambu.snapshot_for(printer)
        if not snap.get("online"):
            continue  # 离线时保持「打印中」，等恢复连接或人工处理

        state = (snap.get("state") or "").upper() or None
        percent = _as_int(snap.get("percent"))
        task = snapshot_task(snap)
        codes = apply_nos_from_file(task)
        matched = app_obj.apply_no in codes

        # 记录打印机当前真实在打什么（界面据此展示，避免把"已派单"显示成"正在打印"）
        if app_obj.print_actual_file != task:
            app_obj.print_actual_file = task
            dirty = True
        if bool(app_obj.print_matched) != matched:
            app_obj.print_matched = matched
            dirty = True

        if not matched:
            # 打印机在打别的文件 / 认不出文件名：不计进度、不判开始、绝不自动完成
            if app_obj.print_state is not None or app_obj.print_progress is not None:
                app_obj.print_state = None
                app_obj.print_progress = None
                dirty = True
            # 明确在打另一批申请（都不含本申请）→ 本申请之前"已确认开始"作废
            if codes and app_obj.print_seen_running:
                app_obj.print_seen_running = False
                dirty = True
            continue

        if app_obj.print_state != state or app_obj.print_progress != percent:
            app_obj.print_state = state
            app_obj.print_progress = percent
            dirty = True

        if state in RUNNING_STATES and (percent is None or percent < 100):
            if not app_obj.print_seen_running:
                app_obj.print_seen_running = True
                dirty = True

        finished = state in FINISH_STATES or (percent is not None and percent >= 100)
        if not (app_obj.print_seen_running and finished):
            continue

        # —— 自动完成 ——
        # 用「带 status 条件的批量更新」做幂等保护：生产上用 gunicorn -w 4 时会有
        # 多个进程各跑一个监视线程，只有抢到 status='printing' 的那一个才发通知。
        db.session.flush()
        affected = (
            db.session.query(PrintApplication)
            .filter(
                PrintApplication.id == app_obj.id,
                PrintApplication.status == "printing",
            )
            .update(
                {
                    PrintApplication.status: "completed",
                    PrintApplication.completed_at: now,
                    PrintApplication.completed_auto: True,
                    PrintApplication.print_state: "FINISH",
                    PrintApplication.print_progress: 100,
                },
                synchronize_session=False,
            )
        )
        if not affected:
            continue  # 已被别的 worker / 人工处理

        # 打印完成 → 取件提醒（首页弹窗）+ 邮件通知领取，并提示可上传反馈领奖励
        notify_pickup(app_obj, f"取件后可在 {feedback_expire_days()} 天内上传实物图/现场照片反馈，"
                               f"奖励 1 次打印机会")
        _user = app_obj.user
        if _user and _user.email:
            from services.mailer import send_mail_async
            from services import notify_templates
            _subj, _body = notify_templates.render_pickup_email(app_obj, printer.name)
            send_mail_async(_user.email, _subj, _body)
        sms_queue.append(app_obj.id)  # 短信在 commit 之后发，避免后台线程读到未提交的数据
        log_action(None, "auto_complete",
                   f"打印机「{printer.name}」打印完 {app_obj.apply_no}，自动标记完成")
        dirty = True
        done += 1

    if dirty:
        db.session.commit()

    # 提交后逐个发取件短信（后台线程，不阻塞监视线程）
    for app_id in sms_queue:
        row = db.session.get(PrintApplication, app_id)
        if row is not None:
            try:
                sms_send_pickup(row)
            except Exception:
                current_app.logger.warning("取件短信发送失败", exc_info=True)

    return done


def _loop(app, interval):
    """后台轮询主循环（daemon 线程，随进程退出自动结束）。"""
    while not _stop_event.is_set():
        try:
            with app.app_context():
                tick()
        except Exception:  # 单次异常不能把线程干掉
            app.logger.warning("打印进度监视失败", exc_info=True)
        try:
            db.session.remove()
        except Exception:
            pass
        _stop_event.wait(interval)


def start_watcher(app, interval=5):
    """启动打印进度监视线程（幂等，重复调用不会起多条）。"""
    global _thread
    with _thread_lock:
        if _thread is not None and _thread.is_alive():
            return
        _stop_event.clear()
        _thread = threading.Thread(
            target=_loop, args=(app, max(2, int(interval))),
            daemon=True, name="print-watch",
        )
        _thread.start()
        print(f" * 打印进度监视已启动：每 {max(2, int(interval))} 秒检查一次绑定打印机")


def stop_watcher():
    """停止监视线程（测试 / 优雅退出用）。"""
    _stop_event.set()
