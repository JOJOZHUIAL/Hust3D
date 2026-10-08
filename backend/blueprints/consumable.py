# -*- coding: utf-8 -*-
"""耗材管理：条形码扫码入库 / 拆封扣减 / 进出流水（仅管理员，手机端操作为主）。

交互流程（前端扫码获得条形码数字后调用）：
  1. GET  /scan?barcode=xxx      → 返回 { exists, item }，前端据此预填表单或提示确认；
  2. POST /stock-in              → 入库：新条码建档（名称/材质/颜色/数量），已有条码累加库存；
  3. POST /open                  → 拆封：库存 -1，记录拆封人与时间；
  4. GET  /logs                  → 最近进出流水（含物品信息与操作人）。
"""
from flask import Blueprint, request, g
from sqlalchemy import desc, or_

from extensions import db
from models import Consumable, ConsumableLog
from utils.response import ok, fail
from utils.auth import admin_required
from services.logger import log_action
from services.notify import notify_admins

bp = Blueprint("consumable", __name__)

BARCODE_MAX = 64
NAME_MAX = 128
NOTE_MAX = 255


def _clean_barcode(raw):
    """条形码清洗：去空白，仅保留数字/字母/短横线，非法返回 None。"""
    bc = (raw or "").strip()
    if not bc or len(bc) > BARCODE_MAX:
        return None
    for ch in bc:
        if not (ch.isdigit() or ch.isalpha() or ch == "-"):
            return None
    return bc


def _write_log(item, action, change, note=None):
    db.session.add(ConsumableLog(
        consumable_id=item.id,
        action=action,
        quantity_change=change,
        quantity_after=item.quantity,
        operator_id=g.user.id,
        note=(note or None),
    ))


@bp.route("/scan", methods=["GET"])
@admin_required
def scan():
    """扫码查询：返回该条形码是否已入库及其台账信息。"""
    bc = _clean_barcode(request.args.get("barcode"))
    if bc is None:
        return fail("条形码格式不正确", code=1002)
    item = Consumable.query.filter_by(barcode=bc).first()
    return ok({"exists": item is not None, "item": item.to_dict() if item else None})


@bp.route("/stock-in", methods=["POST"])
@admin_required
def stock_in():
    """入库：新条码建档，已有条码累加库存；数量必须为正整数。"""
    data = request.get_json(silent=True) or {}
    bc = _clean_barcode(data.get("barcode"))
    if bc is None:
        return fail("条形码格式不正确", code=1002)

    try:
        quantity = int(data.get("quantity") or 0)
    except (TypeError, ValueError):
        quantity = 0
    if quantity < 1 or quantity > 9999:
        return fail("入库数量须为 1-9999 的整数", code=1002)

    name = (data.get("name") or "").strip()
    material = (data.get("material") or "").strip() or None
    color = (data.get("color") or "").strip() or None
    unit = (data.get("unit") or "卷").strip() or "卷"
    note = (data.get("note") or "").strip()[:NOTE_MAX] or None

    item = Consumable.query.filter_by(barcode=bc).first()
    if item is None:
        if not name:
            return fail("新耗材请填写名称", code=1002)
        if len(name) > NAME_MAX:
            return fail("名称过长", code=1002)
        item = Consumable(
            barcode=bc, name=name, material=material,
            color=color, unit=unit, quantity=quantity,
        )
        db.session.add(item)
        db.session.flush()
        _write_log(item, "in", quantity, note=note or "首次入库")
        notify_admins("consumable", f"耗材入库：{name}",
                      f"{g.user.name or g.user.student_id} 入库 {quantity} {unit}，条码 {bc}",
                      link="/admin/consumables")
        log_action(g.user.id, "consumable_in", f"新耗材 {name}({bc}) 入库 {quantity}")
    else:
        item.quantity += quantity
        if material:
            item.material = material
        if color:
            item.color = color
        _write_log(item, "in", quantity, note=note)
        notify_admins("consumable", f"耗材入库：{item.name}",
                      f"{g.user.name or g.user.student_id} 入库 {quantity}，现有 {item.quantity} {item.unit}",
                      link="/admin/consumables")
        log_action(g.user.id, "consumable_in", f"耗材 {item.name}({bc}) 入库 {quantity}")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("保存失败，请重试", code=500, http_status=500)
    return ok(item.to_dict(), msg=f"入库成功，当前库存 {item.quantity} {item.unit}")


@bp.route("/open", methods=["POST"])
@admin_required
def open_item():
    """拆封：扫描已入库耗材的条形码，库存 -1 并记录拆封人与时间。"""
    data = request.get_json(silent=True) or {}
    bc = _clean_barcode(data.get("barcode"))
    if bc is None:
        return fail("条形码格式不正确", code=1002)

    item = Consumable.query.filter_by(barcode=bc).first()
    if item is None:
        return fail("该条形码尚未入库，请先在「入库」中登记", code=1002)
    if item.quantity < 1:
        return fail(f"「{item.name}」库存为 0，无法拆封", code=1002)

    note = (data.get("note") or "").strip()[:NOTE_MAX] or None
    item.quantity -= 1
    _write_log(item, "open", -1, note=note)
    notify_admins("consumable", f"耗材拆封：{item.name}",
                  f"{g.user.name or g.user.student_id} 拆封 1 {item.unit}，剩余 {item.quantity} {item.unit}",
                  link="/admin/consumables")
    log_action(g.user.id, "consumable_open", f"拆封 {item.name}({bc})，余 {item.quantity}")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("保存失败，请重试", code=500, http_status=500)
    return ok(item.to_dict(), msg=f"拆封成功，剩余 {item.quantity} {item.unit}")


@bp.route("/logs", methods=["GET"])
@admin_required
def logs():
    """最近进出流水（默认 100 条，含物品信息与操作人）。"""
    try:
        limit = min(max(int(request.args.get("limit", 100)), 1), 500)
    except (TypeError, ValueError):
        limit = 100
    rows = (
        db.session.query(ConsumableLog)
        .order_by(desc(ConsumableLog.id))
        .limit(limit)
        .all()
    )
    return ok([r.to_dict() for r in rows])


@bp.route("/logs/<int:log_id>", methods=["DELETE"])
@admin_required
def undo_log(log_id):
    """撤回一条本人的流水记录（误操作用）：删除该记录并回退库存。

    只能撤回本人操作的记录；撤回入库时若会导致库存为负则拒绝。
    """
    log = db.session.get(ConsumableLog, log_id)
    if log is None:
        return fail("记录不存在", code=404, http_status=404)
    if log.operator_id != g.user.id:
        return fail("只能撤回本人操作的记录", code=1002)

    item = log.consumable
    if log.action == "open":
        item.quantity += 1
    elif log.action == "in":
        if item.quantity < log.quantity_change:
            return fail(
                f"撤回后库存将为负（当前 {item.quantity}，该入库 {log.quantity_change:+d}），请先核对后续操作",
                code=1002,
            )
        item.quantity -= log.quantity_change
    else:
        return fail("该记录不支持撤回", code=1002)

    verb = "拆封" if log.action == "open" else "入库"
    log_action(g.user.id, "consumable_undo", f"撤回{verb}记录：{item.name}({item.barcode})，库存恢复为 {item.quantity}")
    db.session.delete(log)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("撤回失败，请重试", code=500, http_status=500)
    return ok(item.to_dict(), msg=f"已撤回{verb}记录，库存恢复为 {item.quantity} {item.unit}")


@bp.route("/list", methods=["GET"])
@admin_required
def list_items():
    """耗材台账列表（当前库存一览），支持按名称/材质/颜色/条码模糊筛选。"""
    kw = (request.args.get("keyword") or "").strip()
    q = Consumable.query
    if kw:
        like = f"%{kw}%"
        q = q.filter(or_(
            Consumable.name.like(like),
            Consumable.material.like(like),
            Consumable.color.like(like),
            Consumable.barcode.like(like),
        ))
    rows = q.order_by(Consumable.updated_at.desc()).all()
    return ok([r.to_dict() for r in rows])


@bp.route("/update", methods=["PUT"])
@admin_required
def update_item():
    """编辑耗材信息（条形码不变，名称/材质/颜色/单位随时可改）。"""
    data = request.get_json(silent=True) or {}
    bc = _clean_barcode(data.get("barcode"))
    if bc is None:
        return fail("条形码格式不正确", code=1002)
    item = Consumable.query.filter_by(barcode=bc).first()
    if item is None:
        return fail("耗材不存在", code=404, http_status=404)

    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name:
            return fail("名称不能为空", code=1002)
        item.name = name[:NAME_MAX]
    if "material" in data:
        item.material = (data.get("material") or "").strip()[:64] or None
    if "color" in data:
        item.color = (data.get("color") or "").strip()[:64] or None
    if "unit" in data:
        item.unit = (data.get("unit") or "").strip()[:16] or "卷"

    log_action(g.user.id, "consumable_update", f"编辑耗材 {item.name}({bc})")
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("保存失败，请重试", code=500, http_status=500)
    return ok(item.to_dict(), msg="保存成功")
