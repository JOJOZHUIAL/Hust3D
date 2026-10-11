# -*- coding: utf-8 -*-
"""打印机管理：添加/删除拓竹打印机、查看实时打印状态（仅管理员）。"""
from flask import Blueprint, request, g

from extensions import db
from models import Printer
from services import bambu
from utils.response import ok, fail
from utils.auth import admin_required
from services.logger import log_action

bp = Blueprint("printer", __name__)


@bp.route("/list", methods=["GET"])
@admin_required
def list_printers():
    """打印机清单（含实时状态摘要）。"""
    rows = Printer.query.order_by(Printer.id.asc()).all()
    data = []
    for p in rows:
        snap = bambu.snapshot_for(p)
        data.append({
            **p.to_dict(),
            "online": snap["online"],
            "state_text": snap["state_text"],
            "state": snap["state"],
            "percent": snap["percent"],
            "print_file": snap.get("print_file"),
        })
    return ok(data)


@bp.route("/add", methods=["POST"])
@admin_required
def add_printer():
    """添加打印机（拓竹：填局域网 IP 和访问码，序列号连接后自动发现）。"""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    ip = (data.get("ip") or "").strip()
    access_code = (data.get("access_code") or "").strip()
    serial = (data.get("serial") or "").strip() or None

    if not name or len(name) > 64:
        return fail("请填写打印机名称（≤64字）", code=1002)
    if not ip or len(ip) > 64:
        return fail("请填写打印机 IP", code=1002)
    if not access_code or len(access_code) > 64:
        return fail("请填写访问码", code=1002)

    printer = Printer(name=name, ip=ip, access_code=access_code, serial=serial)
    db.session.add(printer)
    db.session.flush()
    log_action(g.user.id, "printer_add", f"添加打印机 {name}({ip})")
    db.session.commit()
    bambu.start_client(printer)
    return ok(printer.to_dict(), msg="添加成功，正在连接打印机")


@bp.route("/delete/<int:printer_id>", methods=["DELETE"])
@admin_required
def delete_printer(printer_id):
    """删除打印机。"""
    printer = db.session.get(Printer, printer_id)
    if printer is None:
        return fail("打印机不存在", code=404, http_status=404)
    name = printer.name
    bambu.stop_client(printer_id)
    db.session.delete(printer)
    log_action(g.user.id, "printer_delete", f"删除打印机 {name}")
    db.session.commit()
    return ok(msg="已删除")


@bp.route("/<int:printer_id>/status", methods=["GET"])
@admin_required
def printer_status(printer_id):
    """单台打印机实时状态（前端 5 秒轮询）。"""
    printer = db.session.get(Printer, printer_id)
    if printer is None:
        return fail("打印机不存在", code=404, http_status=404)
    return ok(bambu.snapshot_for(printer))
