# -*- coding: utf-8 -*-
"""安卓 App 版本发布与更新检查。

- `GET  /api/app/latest`       客户端启动时查询最新版本（登录即可，非管理员也能查）
- `GET  /api/app/releases`     发布历史（管理员）
- `POST /api/app/releases`     上传新 APK（管理员，multipart）
- `DELETE /api/app/releases/<id>` 删除某次发布（管理员，同时删掉 APK 文件）

客户端把接口返回的 version_code 与自己已安装的 versionCode 比较，大于才提示更新。
"""
import os
import uuid

from flask import Blueprint, current_app, request, g

from extensions import db
from models import AppRelease
from utils.response import ok, fail
from utils.auth import login_required, admin_required
from services.logger import log_action

bp = Blueprint("app_release", __name__)

# 单个 APK 上限（防止误传巨大文件把磁盘打满）
APK_MAX_SIZE = 300 * 1024 * 1024


def _save_apk(file_storage, version_code):
    """把上传的 APK 落盘，返回 (相对 URL, 原始文件名, 字节数)。"""
    data_name = os.path.basename((file_storage.filename or "").replace("\\", "/"))[:255]
    sub = f"apk/{version_code}-{uuid.uuid4().hex[:8]}.apk"
    abs_path = os.path.join(current_app.config["UPLOAD_DIR"], sub)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    # FileStorage.save 会分块写盘，避免大文件整个读进内存
    file_storage.save(abs_path)
    size = os.path.getsize(abs_path)
    if size == 0:
        os.remove(abs_path)
        raise ValueError("APK 文件为空")
    if size > APK_MAX_SIZE:
        os.remove(abs_path)
        raise ValueError(f"APK 不能超过 {APK_MAX_SIZE // 1024 // 1024} MB")
    return "uploads/" + sub, data_name, size


def _latest():
    return (
        db.session.query(AppRelease)
        .order_by(AppRelease.version_code.desc())
        .first()
    )


@bp.route("/latest", methods=["GET"])
@login_required
def latest():
    """最新版本信息（没有发布过则返回 null）。"""
    row = _latest()
    return ok(row.to_dict() if row is not None else None)


@bp.route("/releases", methods=["GET"])
@admin_required
def list_releases():
    """发布历史（最新在前）。"""
    rows = (
        db.session.query(AppRelease)
        .order_by(AppRelease.version_code.desc())
        .all()
    )
    return ok([r.to_dict() for r in rows])


@bp.route("/releases", methods=["POST"])
@admin_required
def upload_release():
    """上传新 APK：multipart，字段 file / version_code / version_name / note。"""
    f = request.files.get("file")
    if f is None or not (f.filename or "").strip():
        return fail("请选择 APK 文件", code=1002)
    if not f.filename.lower().endswith(".apk"):
        return fail("只支持 .apk 文件", code=1002)

    raw_code = (request.form.get("version_code") or "").strip()
    if not raw_code.isdigit() or int(raw_code) <= 0:
        return fail("版本号必须是不小于 1 的整数（对应安卓 versionCode）", code=1002)
    version_code = int(raw_code)

    version_name = (request.form.get("version_name") or "").strip()[:32] or f"1.{version_code}"
    note = (request.form.get("note") or "").strip()

    if db.session.query(AppRelease).filter_by(version_code=version_code).first() is not None:
        return fail(f"版本号 {version_code} 已存在，请改用更大的版本号", code=1002)

    try:
        file_url, file_name, size = _save_apk(f, version_code)
    except ValueError as e:
        return fail(str(e), code=1002)
    except OSError:
        current_app.logger.warning("保存 APK 失败", exc_info=True)
        return fail("保存 APK 失败，请检查服务器磁盘权限", code=500, http_status=500)

    row = AppRelease(
        version_code=version_code,
        version_name=version_name,
        file_url=file_url,
        file_name=file_name,
        file_size=size,
        note=note or None,
        publisher_id=g.user.id,
    )
    db.session.add(row)
    log_action(g.user.id, "app_release_upload",
               f"上传 App 版本 {version_name}（versionCode={version_code}，{size / 1024 / 1024:.1f} MB）")
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("保存失败，请重试", code=500, http_status=500)

    return ok(row.to_dict(), msg=f"已发布版本 {version_name}")


@bp.route("/releases/<int:release_id>", methods=["DELETE"])
@admin_required
def delete_release(release_id):
    """删除某次发布，同时删掉磁盘上的 APK。"""
    row = db.session.get(AppRelease, release_id)
    if row is None:
        return fail("版本不存在", code=404, http_status=404)

    rel_path = row.file_url
    label = f"{row.version_name or ''}({row.version_code})"
    db.session.delete(row)
    log_action(g.user.id, "app_release_delete", f"删除 App 版本 {label}")
    db.session.commit()

    if rel_path:
        try:
            abs_path = os.path.join(
                current_app.config["UPLOAD_DIR"], rel_path.split("uploads/", 1)[-1]
            )
            if os.path.isfile(abs_path):
                os.remove(abs_path)
        except OSError:
            current_app.logger.warning("删除 APK 文件失败：%s", rel_path)

    return ok(msg="已删除")
