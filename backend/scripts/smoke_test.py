# -*- coding: utf-8 -*-
"""本地联调冒烟测试。

不依赖 MySQL、真实教务系统：用 SQLite + mock 模式跑通
「CAS 登录 → 查信息/配额 → 提交申请 → 列表/详情 →
管理员审批 → 状态推进 → 反馈（奖励配额）→ 退出登录」整条链路。

用法（在 backend 目录下）：
    ./.venv/Scripts/python.exe scripts/smoke_test.py
"""
import io
import os
import sys

# 把 backend 目录加入 sys.path，使 `from app import app` 可导入
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 必须在 import app 之前设置环境变量（config 在导入时读取）
os.environ["DATABASE_URL"] = "sqlite:///./smoke.db"
os.environ["CAS_MOCK"] = "1"
os.environ["ADMIN_STUDENT_IDS"] = "20260001"
os.environ["SUPER_ADMIN_STUDENT_IDS"] = "20260001"

from app import app  # noqa: E402
from extensions import db  # noqa: E402

STUDENT_ID = "20260001"


def main():
    # 用全新 SQLite 库跑，保证可重复
    with app.app_context():
        db.drop_all()
        db.create_all()

    c = app.test_client()
    checks = []

    def check(name, cond, extra=""):
        checks.append(bool(cond))
        mark = "[PASS]" if cond else "[FAIL]"
        print(f"{mark} {name}" + (f"  [{extra}]" if extra and not cond else ""))

    # 1. CAS 登录（mock 模式任意密码通过，无需验证码）
    r = c.post("/api/auth/cas-login", json={
        "student_id": STUDENT_ID, "password": "whatever",
    })
    body = r.get_json()
    token = (body or {}).get("data", {}).get("token")
    check("cas-login 返回 token", token is not None)
    headers = {"Authorization": f"Bearer {token}"}

    # 2. 用户信息 / 配额
    r = c.get("/api/user/info", headers=headers)
    info = r.get_json()["data"]
    check("user/info 返回学号", info.get("student_id") == STUDENT_ID, info)
    check("user/info 角色为 admin/superadmin", info.get("role") in ("admin", "superadmin"), info.get("role"))

    r = c.get("/api/user/quota", headers=headers)
    check("quota 初始为 2", r.get_json()["data"]["remaining"] == 2)

    # 3. 必填校验：联系方式 / 电子邮箱缺失时拦截
    #    每次请求都重新构造（BytesIO 只能被读一次）
    def make_data(**overrides):
        data = {
            "purpose": "course",
            "material": "PLA",
            "model_count": "1",
            "remark": "冒烟测试",
            "phone": "13800000000",
            "email": "student@example.com",
            "sign": "data:image/png;base64,aGVsbG8=",
            "file": (io.BytesIO(b"fake stl binary content"), "model.stl"),
        }
        data.update(overrides)
        for k in list(data):
            if k not in overrides and k in ("file",):
                data[k] = (io.BytesIO(b"fake stl binary content"), "model.stl")
        return data

    no_phone = make_data()
    no_phone.pop("phone")
    r = c.post("/api/application/submit", data=no_phone, headers=headers,
               content_type="multipart/form-data")
    check("缺少联系方式被拦截", r.get_json().get("code") == 1002, r.get_json())
    r = c.post("/api/application/submit", data=make_data(phone="12345"), headers=headers,
               content_type="multipart/form-data")
    check("手机号格式错误被拦截", r.get_json().get("code") == 1002, r.get_json())
    no_email = make_data()
    no_email.pop("email")
    r = c.post("/api/application/submit", data=no_email, headers=headers,
               content_type="multipart/form-data")
    check("缺少电子邮箱被拦截", r.get_json().get("code") == 1002, r.get_json())

    # 4. 提交申请（带假 STL 与签名）
    r = c.post("/api/application/submit", data=make_data(), headers=headers,
               content_type="multipart/form-data")
    sub = r.get_json()["data"]
    check("submit 返回申请编号", bool(sub and sub.get("apply_no", "").startswith("HUST3D")), sub)
    app_id = sub["id"]

    # 4. 配额已扣减
    r = c.get("/api/user/quota", headers=headers)
    check("提交后 quota 扣减为 1", r.get_json()["data"]["remaining"] == 1)

    # 4.5 导出 Word 申请表
    r = c.get(f"/api/application/export/{app_id}", headers=headers)
    body = r.data or b""
    check("导出接口返回 200", r.status_code == 200, r.status_code)
    check("导出为 docx（zip 魔数）", body[:2] == b"PK" and len(body) > 5000, len(body))
    check("导出 Content-Type 正确",
          r.headers.get("Content-Type", "").startswith(
              "application/vnd.openxmlformats-officedocument.wordprocessingml"))
    # 未登录导出应被拦截
    r = c.get(f"/api/application/export/{app_id}")
    check("未登录导出被拦截", r.status_code == 401, r.status_code)

    # 5. 列表与详情
    r = c.get("/api/application/list", headers=headers)
    check("list 返回 1 条", len(r.get_json()["data"]) == 1)
    r = c.get(f"/api/application/detail/{app_id}", headers=headers)
    check("detail 状态为 pending", r.get_json()["data"]["status"] == "pending")

    # 6. 管理员审批
    r = c.get("/api/admin/applications/pending", headers=headers)
    check("admin pending 返回 1 条", len(r.get_json()["data"]) == 1)
    r = c.post("/api/admin/application/review", headers=headers,
               json={"id": app_id, "action": "approve"})
    check("审批通过", r.get_json()["data"]["status"] == "approved")

    # 7. 状态推进
    r = c.put("/api/admin/application/status", headers=headers,
              json={"id": app_id, "status": "printing"})
    check("推进到打印中", r.get_json()["data"]["status"] == "printing")
    r = c.put("/api/admin/application/status", headers=headers,
              json={"id": app_id, "status": "completed", "picked_up": True})
    d = r.get_json()["data"]
    check("推进到已完成并领取", d["status"] == "completed" and d["picked_up"])

    # 7.5 反馈（上传实物图/现场照片，成功后奖励 1 次打印机会）
    r = c.get("/api/user/quota", headers=headers)
    check("反馈前 quota 为 1", r.get_json()["data"]["remaining"] == 1)
    r = c.post(f"/api/application/feedback/{app_id}", headers=headers,
               data={"file": (io.BytesIO(b"\x89PNG fake image"), "feedback.png")},
               content_type="multipart/form-data")
    fb = r.get_json()["data"]
    check("反馈成功返回 feedback_url", bool(fb.get("feedback_url")), fb)
    check("反馈后 quota 奖励为 2",
          c.get("/api/user/quota", headers=headers).get_json()["data"]["remaining"] == 2)
    r = c.post(f"/api/application/feedback/{app_id}", headers=headers,
               data={"file": (io.BytesIO(b"x"), "again.png")},
               content_type="multipart/form-data")
    check("重复反馈被拦截", r.get_json().get("code") == 1002, r.get_json())

    # 7.9 联系工作室（聊天）：学生发文字/文件 → 管理员回复 → 已读流转
    r = c.post("/api/auth/cas-login", json={"student_id": "20260002", "password": "x"})
    stu_token = (r.get_json() or {}).get("data", {}).get("token")
    check("学生 20260002 登录", bool(stu_token))
    stu_headers = {"Authorization": f"Bearer {stu_token}"}

    r = c.post("/api/chat/send", headers=stu_headers,
               data={"content_type": "text", "content": "请问工作室几点开门？"},
               content_type="multipart/form-data")
    check("学生发送文字消息", r.get_json().get("code") == 0, r.get_json())

    r = c.post("/api/chat/send", headers=stu_headers,
               data={"content_type": "file",
                     "file": (io.BytesIO(b"solid fake stl"), "model.stl")},
               content_type="multipart/form-data")
    check("学生发送文件消息", r.get_json().get("code") == 0, r.get_json())

    r = c.post("/api/chat/send", headers=stu_headers,
               data={"content_type": "image",
                     "file": (io.BytesIO(b"\x89PNG fake"), "pic.png")},
               content_type="multipart/form-data")
    check("学生发送图片消息", r.get_json().get("code") == 0, r.get_json())

    r = c.post("/api/chat/send", headers=stu_headers,
               data={"content_type": "voice",
                     "file": (io.BytesIO(b"fake audio"), "voice.webm"),
                     "duration": "5"},
               content_type="multipart/form-data")
    check("学生发送语音消息", r.get_json().get("code") == 0, r.get_json())

    r = c.get("/api/chat/conversations", headers=headers)
    convs = r.get_json().get("data") or []
    check("管理员会话列表包含该学生", len(convs) == 1 and convs[0]["user"]["student_id"] == "20260002", convs)
    check("管理员未读数为 4", convs and convs[0]["unread"] == 4, convs)

    r = c.post("/api/chat/send", headers=headers,
               data={"content_type": "text", "content": "工作日 9:00-21:00", "user_id": str(convs[0]["user"]["id"])},
               content_type="multipart/form-data")
    check("管理员回复消息", r.get_json().get("code") == 0, r.get_json())

    r = c.get("/api/chat/unread", headers=stu_headers)
    check("学生未读数为 1", (r.get_json().get("data") or {}).get("count") == 1, r.get_json())

    r = c.get("/api/chat/messages", headers=stu_headers)
    msgs = (r.get_json().get("data") or {}).get("messages") or []
    check("学生拉取到 5 条消息", len(msgs) == 5, len(msgs))
    r = c.get("/api/chat/unread", headers=stu_headers)
    check("拉取后学生未读清零", (r.get_json().get("data") or {}).get("count") == 0, r.get_json())

    r = c.get(f"/api/chat/messages?user_id={convs[0]['user']['id']}", headers=headers)
    msgs = (r.get_json().get("data") or {}).get("messages") or []
    check("管理员拉取到 5 条消息", len(msgs) == 5, len(msgs))
    r = c.get("/api/chat/conversations", headers=headers)
    convs = r.get_json().get("data") or []
    check("管理员未读清零", convs and convs[0]["unread"] == 0, convs)

    r = c.get("/api/chat/contacts", headers=headers)
    names = [u["student_id"] for u in (r.get_json().get("data") or [])]
    check("联系人名单含学生不含管理员", "20260002" in names and "20260001" not in names, names)

    # 7.10 公告：管理员发布/编辑/删除，学生可看列表与详情
    r = c.post("/api/notice/create", headers=headers,
               json={"title": "打印服务上线公告", "content": "每学期 2 次免费打印。\n请按时领取成品。"})
    nid = (r.get_json().get("data") or {}).get("id")
    check("管理员发布公告", r.get_json().get("code") == 0 and bool(nid), r.get_json())

    r = c.get("/api/notice/list", headers=stu_headers)
    rows = r.get_json().get("data") or []
    check("学生可看公告列表", any(x["title"] == "打印服务上线公告" for x in rows), rows)

    r = c.get(f"/api/notice/{nid}", headers=stu_headers)
    detail = r.get_json().get("data") or {}
    check("学生可看公告详情（含正文）", "免费打印" in (detail.get("content") or ""), detail)

    r = c.put("/api/notice/update", headers=headers,
              json={"id": nid, "title": "打印服务上线公告（修订）", "content": "内容已更新。"})
    check("管理员编辑公告", r.get_json().get("code") == 0, r.get_json())

    r = c.post("/api/notice/create", headers=stu_headers,
               json={"title": "x", "content": "y"})
    check("学生发布公告被拦截", r.get_json().get("code") == 403, r.get_json())

    r = c.delete(f"/api/notice/delete/{nid}", headers=headers)
    check("管理员删除公告", r.get_json().get("code") == 0, r.get_json())

    # 7.11 耗材管理：扫码入库 → 拆封扣减 → 流水；学生无权操作
    BC = "6901234567890"
    r = c.get(f"/api/consumable/scan?barcode={BC}", headers=headers)
    check("扫码查询未入库条码", (r.get_json().get("data") or {}).get("exists") is False, r.get_json())

    r = c.post("/api/consumable/stock-in", headers=headers,
               json={"barcode": BC, "name": "PLA 1.75mm", "material": "PLA", "color": "黑色",
                     "quantity": 5, "unit": "卷", "note": "2026秋季进货"})
    check("新耗材入库建档", r.get_json().get("code") == 0 and
          (r.get_json().get("data") or {}).get("quantity") == 5, r.get_json())

    r = c.post("/api/consumable/stock-in", headers=headers,
               json={"barcode": BC, "quantity": 3})
    check("已有耗材累加入库", (r.get_json().get("data") or {}).get("quantity") == 8, r.get_json())

    r = c.post("/api/consumable/open", headers=stu_headers, json={"barcode": BC})
    check("学生拆封被拦截", r.get_json().get("code") == 403, r.get_json())

    r = c.post("/api/consumable/open", headers=headers, json={"barcode": BC})
    check("拆封成功库存-1", (r.get_json().get("data") or {}).get("quantity") == 7, r.get_json())

    r = c.get("/api/consumable/logs?limit=10", headers=headers)
    log_rows = r.get_json().get("data") or []
    check("流水包含入库与拆封", {x["action"] for x in log_rows} >= {"in", "open"}, log_rows)
    check("流水记录操作人", any(x["action"] == "open" and x["operator"] for x in log_rows), log_rows)

    r = c.post("/api/consumable/open", headers=headers,
               json={"barcode": "9999999999999"})
    check("未入库条码拆封被拦截", r.get_json().get("code") == 1002, r.get_json())

    # 7.12 站内通知：审批/留言/新申请/耗材事件各自生成，学生与管理员各自可见
    r = c.get("/api/notification/unread-count", headers=stu_headers)
    n0 = (r.get_json().get("data") or {}).get("count")

    # 学生重新提交申请 → 管理员收到新申请通知
    r = c.post("/api/application/submit", data=make_data(purpose="research"), headers=stu_headers,
               content_type="multipart/form-data")
    check("学生再次提交申请", r.get_json().get("code") == 0, r.get_json())
    new_id = (r.get_json().get("data") or {}).get("id")
    after_rows = c.get("/api/notification/list", headers=headers).get_json().get("data") or []
    check("管理员收到新申请通知", any("新打印申请" in (x.get("title") or "") for x in after_rows), after_rows[:1])

    # 管理员拒绝新申请 → 学生收到通知
    r = c.post("/api/admin/application/review", headers=headers,
               json={"id": new_id, "action": "reject", "comment": "模型有破面"})
    check("审批拒绝成功", r.get_json().get("code") == 0, r.get_json())
    rows = c.get("/api/notification/list", headers=stu_headers).get_json().get("data") or []
    check("学生收到审批结果通知", any("未通过" in (x.get("title") or "") for x in rows), rows[:1])

    # 学生发留言 → 管理员收到通知
    before = len((c.get("/api/notification/list", headers=headers).get_json().get("data")) or [])
    r = c.post("/api/chat/send", headers=stu_headers,
               data={"content_type": "text", "content": "模型已修复，重新提交了申请"},
               content_type="multipart/form-data")
    after_rows = c.get("/api/notification/list", headers=headers).get_json().get("data") or []
    check("管理员收到新留言通知", len(after_rows) == before + 1 and "新留言" in after_rows[0]["title"], after_rows[:1])

    # 耗材拆封 → 管理员收到通知
    r = c.post("/api/consumable/open", headers=headers, json={"barcode": BC})
    check("耗材拆封成功", r.get_json().get("code") == 0, r.get_json())
    after_rows = c.get("/api/notification/list", headers=headers).get_json().get("data") or []
    check("管理员收到拆封通知", any("拆封" in (x.get("title") or "") for x in after_rows), after_rows[:1])

    # 学生未读数增加，全部已读后清零
    r = c.get("/api/notification/unread-count", headers=stu_headers)
    n1 = (r.get_json().get("data") or {}).get("count")
    check("学生未读数增加", (n1 or 0) > (n0 or 0), (n0, n1))
    r = c.post("/api/notification/read-all", headers=stu_headers)
    check("全部已读成功", r.get_json().get("code") == 0, r.get_json())
    r = c.get("/api/notification/unread-count", headers=stu_headers)
    check("已读后未读清零", (r.get_json().get("data") or {}).get("count") == 0, r.get_json())

    # 7.13 补充：管理员以工作室成员身份发消息 / 耗材编辑与搜索 / 按类型已读
    r = c.post("/api/chat/send", headers=headers,
               data={"content_type": "text", "content": "各位：新到一批黑色 PLA"},
               content_type="multipart/form-data")
    check("管理员免指定会话发消息", r.get_json().get("code") == 0, r.get_json())
    check("以用户角色入库", (r.get_json().get("data") or {}).get("sender_role") == "user", r.get_json())
    r = c.get("/api/chat/messages", headers=headers)
    msgs = (r.get_json().get("data") or {}).get("messages") or []
    check("管理员查自己会话", any("黑色 PLA" in (m.get("content") or "") for m in msgs), msgs)

    r = c.get("/api/consumable/list?keyword=黑色", headers=headers)
    hits = r.get_json().get("data") or []
    check("耗材按颜色搜索", len(hits) == 1 and hits[0]["color"] == "黑色", hits)
    r = c.get("/api/consumable/list?keyword=不存在的东西", headers=headers)
    check("耗材搜索无命中为空", (r.get_json().get("data") or []) == [], r.get_json())

    r = c.put("/api/consumable/update", headers=headers,
              json={"barcode": BC, "name": "PLA 1.75mm 哑光", "color": "磨砂黑"})
    check("编辑耗材信息", (r.get_json().get("data") or {}).get("name") == "PLA 1.75mm 哑光", r.get_json())

    # 管理员发消息生成 chat 通知（排除自己 → 其他管理员收；本例仅一名管理员 → 自己不收）
    r = c.get("/api/notification/unread-count", headers=headers)
    cnt_before = (r.get_json().get("data") or {}).get("count")
    r = c.post("/api/notification/read-type/chat", headers=headers)
    remain = (r.get_json().get("data") or {}).get("count")
    rows = c.get("/api/notification/list", headers=headers).get_json().get("data") or []
    chat_unread = [x for x in rows if x["ntype"] == "chat" and not x["is_read"]]
    check("按类型已读：chat 类通知清零", r.get_json().get("code") == 0 and not chat_unread, len(chat_unread))

    # 7.14 超级管理员：角色赋值 + 添加/移除管理员 + 防护规则
    r = c.get("/api/user/info", headers=headers)
    check("超级管理员角色生效", (r.get_json().get("data") or {}).get("role") == "superadmin", r.get_json())

    r = c.get("/api/admin/users/search?keyword=20260002", headers=headers)
    hits = r.get_json().get("data") or []
    check("搜索普通用户", len(hits) == 1 and hits[0]["student_id"] == "20260002", hits)

    r = c.post("/api/admin/set-role", headers=headers, json={"student_id": "20260002", "role": "admin"})
    check("添加管理员", (r.get_json().get("data") or {}).get("role") == "admin", r.get_json())
    r = c.get("/api/admin/admins", headers=headers)
    check("管理员清单含新人", any(u["student_id"] == "20260002" for u in (r.get_json().get("data") or [])), r.get_json())

    r = c.post("/api/admin/set-role", headers=headers, json={"student_id": "20260001", "role": "user"})
    check("不能修改自己", r.get_json().get("code") == 1002, r.get_json())

    r = c.post("/api/admin/set-role", headers=headers, json={"student_id": "20260002", "role": "user"})
    check("移除管理员", (r.get_json().get("data") or {}).get("role") == "user", r.get_json())

    r = c.post("/api/admin/set-role", headers=stu_headers, json={"student_id": "20260002", "role": "admin"})
    check("普通用户无权设置角色", r.get_json().get("code") == 403, r.get_json())

    # 7.15 耗材撤回与关键词搜索
    r = c.get("/api/consumable/list?keyword=PLA", headers=headers)
    pla_hits = r.get_json().get("data") or []
    check("关键词 PLA 命中耗材", any("PLA" in (x.get("name") or "") or (x.get("material") or "").startswith("PLA") for x in pla_hits), pla_hits)

    r = c.post("/api/consumable/open", headers=headers, json={"barcode": BC})
    check("拆封用于撤回测试", r.get_json().get("code") == 0, r.get_json())
    qty_after_open = (r.get_json().get("data") or {}).get("quantity")

    r = c.get("/api/consumable/logs?limit=5", headers=headers)
    logs = r.get_json().get("data") or []
    own_open = next((x for x in logs if x["action"] == "open" and x["operator_id"] == 1), None)
    check("流水含本人拆封记录", own_open is not None, logs[:1])

    r = c.delete(f"/api/consumable/logs/{own_open['id']}", headers=headers)
    check("撤回本人拆封记录", r.get_json().get("code") == 0 and
          (r.get_json().get("data") or {}).get("quantity") == qty_after_open + 1, r.get_json())

    # 8. 退出登录
    r = c.post("/api/auth/logout", headers=headers)
    check("logout 返回成功", r.get_json().get("code") == 0)

    # 汇总
    passed = sum(checks)
    print(f"\n结果：{passed}/{len(checks)} 通过")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
