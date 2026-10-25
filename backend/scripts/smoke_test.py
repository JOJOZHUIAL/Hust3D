# -*- coding: utf-8 -*-
"""本地联调冒烟测试。

不依赖 MySQL、真实教务系统：用 SQLite + mock 模式跑通
「CAS 登录 → 查信息/配额 → 提交申请 → 列表/详情 →
管理员审批 → 状态推进 → 反馈（奖励配额）→ 退出登录」整条链路。

用法（在 backend 目录下）：
    ./.venv/Scripts/python.exe scripts/smoke_test.py
"""
import io
import json
import os
import sys

# 把 backend 目录加入 sys.path，使 `from app import app` 可导入
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

# 必须在 import app 之前设置环境变量（config 在导入时读取）
os.environ["DATABASE_URL"] = "sqlite:///./smoke.db"
os.environ["CAS_MOCK"] = "1"
os.environ["ADMIN_STUDENT_IDS"] = "20260001"
os.environ["SUPER_ADMIN_STUDENT_IDS"] = "20260001"
os.environ["FEEDBACK_REWARD_MODE"] = "auto"
# 关掉后台进度监视线程，改为在用例里手动调用 tick()，保证测试可重复
os.environ["PRINT_WATCH_ENABLED"] = "0"
# 管理端写回管理员学号时用的 .env —— 指向 backend/smoke.env，别动真实的 backend/.env
# 注意：不用 tempfile.gettempdir()，在受限环境下它可能回退到当前目录，导致落点不可控
SMOKE_ENV = os.path.join(BACKEND_DIR, "smoke.env")
os.environ["ENV_FILE"] = SMOKE_ENV

from app import app  # noqa: E402
from extensions import db  # noqa: E402
from models import PrintApplication  # noqa: E402

STUDENT_ID = "20260001"


def main():
    # 用全新 SQLite 库跑，保证可重复
    with app.app_context():
        db.drop_all()
        db.create_all()

    # 管理端写回管理员学号需要一个受控的 .env
    with open(SMOKE_ENV, "w", encoding="utf-8") as f:
        f.write("# smoke test\nDB_NAME=hust_3d\n"
                "ADMIN_STUDENT_IDS=20260001\nSUPER_ADMIN_STUDENT_IDS=20260001\n")

    def env_text():
        try:
            with open(SMOKE_ENV, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def env_admin_ids():
        for line in env_text().splitlines():
            if line.strip().startswith("ADMIN_STUDENT_IDS="):
                return [x.strip() for x in line.split("=", 1)[1].split(",") if x.strip()]
        return []

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
    print("   [debug] feedback msg:", r.get_json().get("msg"), "| reviewed:", fb.get("feedback_reviewed"))
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

    # 耗材拆封 → 其他管理员收到通知（操作者本人不再自通知）
    r = c.post("/api/admin/set-role", headers=headers, json={"student_id": "20260002", "role": "admin"})
    check("临时提升第二管理员", r.get_json().get("code") == 0, r.get_json())
    r = c.post("/api/consumable/open", headers=headers, json={"barcode": BC})
    check("耗材拆封成功", r.get_json().get("code") == 0, r.get_json())
    after_rows = c.get("/api/notification/list", headers=stu_headers).get_json().get("data") or []
    check("其他管理员收到拆封通知", any("拆封" in (x.get("title") or "") for x in after_rows), after_rows[:1])
    r = c.get("/api/notification/list", headers=headers).get_json().get("data") or []
    check("操作者本人不收到拆封通知", not any("拆封" in (x.get("title") or "") for x in r), r[:1])
    r = c.post("/api/admin/set-role", headers=headers, json={"student_id": "20260002", "role": "user"})
    check("恢复学生角色", r.get_json().get("code") == 0, r.get_json())

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
    check("添加管理员时学号写入配置文件", "20260002" in env_admin_ids(), env_admin_ids())
    check("写入配置文件未破坏其他变量", "DB_NAME=hust_3d" in env_text(), env_text())
    check("内存中的管理员清单已同步",
          "20260002" in app.config["ADMIN_STUDENT_IDS"], app.config["ADMIN_STUDENT_IDS"])

    r = c.get("/api/admin/admins", headers=headers)
    check("管理员清单含新人", any(u["student_id"] == "20260002" for u in (r.get_json().get("data") or [])), r.get_json())

    r = c.post("/api/admin/set-role", headers=headers, json={"student_id": "20260001", "role": "user"})
    check("不能修改自己", r.get_json().get("code") == 1002, r.get_json())
    check("改超级管理员不会动配置", "20260001" in env_admin_ids(), env_admin_ids())

    r = c.post("/api/admin/set-role", headers=headers, json={"student_id": "20260002", "role": "user"})
    check("移除管理员", (r.get_json().get("data") or {}).get("role") == "user", r.get_json())
    check("移除管理员时学号从配置文件移除", "20260002" not in env_admin_ids(), env_admin_ids())

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

    # 7.16 反馈审核模式 + 打印机管理接口
    # 切到 review 模式
    app.config["FEEDBACK_REWARD_MODE"] = "review"

    # 学生重新提交申请 → 管理员审批 → 打印 → 完成 → 学生反馈（不自动 +1）
    r = c.post("/api/application/submit", data=make_data(purpose="club"), headers=stu_headers,
               content_type="multipart/form-data")
    check("review模式学生提交申请", r.get_json().get("code") == 0, r.get_json())
    rid = (r.get_json().get("data") or {}).get("id")
    c.post("/api/admin/application/review", headers=headers, json={"id": rid, "action": "approve"})
    c.put("/api/admin/application/status", headers=headers, json={"id": rid, "status": "printing"})
    c.put("/api/admin/application/status", headers=headers, json={"id": rid, "status": "completed"})

    r = c.get("/api/user/quota", headers=stu_headers)
    q_before = (r.get_json().get("data") or {}).get("remaining")
    r = c.post(f"/api/application/feedback/{rid}", headers=stu_headers,
               data={"file": (io.BytesIO(b"fake png bytes"), "r.png")},
               content_type="multipart/form-data")
    fb = r.get_json()
    check("review模式反馈提交成功不自动+1", fb.get("code") == 0 and fb["data"]["feedback_reviewed"] == False, fb)  # noqa: E712
    r = c.get("/api/user/quota", headers=stu_headers)
    check("review模式未自动奖励", (r.get_json().get("data") or {}).get("remaining") == q_before)

    r = c.post("/api/admin/feedback/review", headers=headers, json={"id": rid, "action": "approve"})
    check("管理员审核通过", r.get_json().get("code") == 0, r.get_json())
    r = c.get("/api/user/quota", headers=stu_headers)
    check("审核通过后奖励+1", (r.get_json().get("data") or {}).get("remaining") == q_before + 1, r.get_json())

    # 自定义奖励次数：新申请走完整流程，reward=3
    r = c.post("/api/application/submit", data=make_data(purpose="competition"), headers=stu_headers,
               content_type="multipart/form-data")
    check("review模式再次提交", r.get_json().get("code") == 0, r.get_json())
    rid2 = (r.get_json().get("data") or {}).get("id")
    c.post("/api/admin/application/review", headers=headers, json={"id": rid2, "action": "approve"})
    c.put("/api/admin/application/status", headers=headers, json={"id": rid2, "status": "printing"})
    c.put("/api/admin/application/status", headers=headers, json={"id": rid2, "status": "completed"})
    r = c.post(f"/api/application/feedback/{rid2}", headers=stu_headers,
               data={"file": (io.BytesIO(b"fake png 2"), "r2.png")},
               content_type="multipart/form-data")
    check("第二次反馈提交", r.get_json().get("code") == 0, r.get_json())
    r = c.get("/api/user/quota", headers=stu_headers)
    q2 = (r.get_json().get("data") or {}).get("remaining")
    r = c.post("/api/admin/feedback/review", headers=headers, json={"id": rid2, "action": "approve", "reward": 3})
    check("自定义奖励3次审核通过", r.get_json().get("code") == 0, r.get_json())
    r = c.get("/api/user/quota", headers=stu_headers)
    check("自定义奖励+3", (r.get_json().get("data") or {}).get("remaining") == q2 + 3, r.get_json())
    r = c.post("/api/admin/feedback/review", headers=headers, json={"id": rid2, "action": "approve", "reward": 99})
    check("奖励越界被拦截", r.get_json().get("code") == 1002, r.get_json())

    # 打印机接口：添加 → 列表 → 状态(离线快照) → 删除
    r = c.post("/api/printer/add", headers=headers,
               json={"name": "拓竹A1mini", "ip": "192.168.1.128", "access_code": "ed904e57"})
    check("添加打印机", r.get_json().get("code") == 0, r.get_json())
    pid = (r.get_json().get("data") or {}).get("id")

    r = c.get("/api/printer/list", headers=headers)
    plist = r.get_json().get("data") or []
    check("打印机清单含新机", any(x["name"] == "拓竹A1mini" for x in plist), plist)

    r = c.get(f"/api/printer/{pid}/status", headers=headers)
    snap = r.get_json().get("data") or {}
    check("打印机状态快照返回", r.get_json().get("code") == 0 and "online" in snap, snap)

    r = c.delete(f"/api/printer/delete/{pid}", headers=headers)
    check("删除打印机", r.get_json().get("code") == 0, r.get_json())
    r = c.get("/api/printer/list", headers=headers)
    check("删除后清单为空", (r.get_json().get("data") or []) == [], r.get_json())

    # 恢复 auto 模式
    app.config["FEEDBACK_REWARD_MODE"] = "auto"

    # 7.17 批量导出申请表（管理员，按时间范围 → ZIP，每个申请一个独立 Word）
    import zipfile as _zip
    from datetime import datetime as _dtm
    from docx import Document as _Doc
    from io import BytesIO as _BIO

    all_apps = (c.get("/api/admin/applications", headers=headers).get_json() or {}).get("data") or []

    r = c.get("/api/admin/applications/export", headers=headers)
    body = r.data or b""
    check("导出接口返回 200", r.status_code == 200, r.status_code)
    check("导出为 zip（zip 魔数）", body[:2] == b"PK", len(body))
    check("导出 Content-Type 为 zip",
          (r.headers.get("Content-Type") or "").startswith("application/zip"),
          r.headers.get("Content-Type"))

    zf = _zip.ZipFile(_BIO(body))
    names = zf.namelist()
    check("zip 内每个申请一个文件", len(names) == min(len(all_apps), 300), (len(names), len(all_apps)))
    check("zip 内文件都是 docx", all(n.endswith(".docx") for n in names), names[:3])
    known_nos = {app["apply_no"] for app in all_apps}
    check("文件名为姓名+申请编号",
          all(any(no in n for no in known_nos) for n in names), names[:3])
    d1 = _Doc(_BIO(zf.read(names[0])))
    check("单个 docx 只含一份申请表",
          sum(1 for p in d1.paragraphs if (p.text or "").startswith("申请日期")) == 1)
    zf.close()

    # 时间范围筛选（只导出今天创建的全部申请）
    today = _dtm.now().strftime("%Y-%m-%d")
    r = c.get("/api/admin/applications/export", headers=headers,
              query_string={"start": today, "end": today})
    zf2 = _zip.ZipFile(_BIO(r.data or b""))
    today_apps = [a for a in all_apps if (a.get("created_at") or "").startswith(today)]
    check("按时间范围导出", len(zf2.namelist()) == len(today_apps),
          (len(zf2.namelist()), len(today_apps)))
    zf2.close()

    r = c.get("/api/admin/applications/export", headers=headers,
              query_string={"start": "1990-01-01", "end": "1990-01-02"})
    check("空时间范围被拦截", r.get_json().get("code") == 404, r.get_json())
    r = c.get("/api/admin/applications/export", headers=headers,
              query_string={"start": "2026/01/01"})
    check("日期格式错误被拦截", r.get_json().get("code") == 1002, r.get_json())
    r = c.get("/api/admin/applications/export", headers=headers,
              query_string={"start": "2026-10-10", "end": "2026-10-01"})
    check("起止日期颠倒被拦截", r.get_json().get("code") == 1002, r.get_json())
    r = c.get("/api/admin/applications/export", headers=stu_headers)
    check("学生无权批量导出", r.status_code == 403, r.status_code)
    r = c.get("/api/application/export-batch?ids=1", headers=stu_headers)
    check("旧的合并导出接口已下线", r.status_code == 404, r.status_code)

    # 7.18 附件命名下载：STL 模型以 姓名+申请编号 命名
    r = c.get(f"/api/application/attachment/{app_id}", headers=headers)
    check("附件下载返回原内容", r.status_code == 200 and r.data == b"fake stl binary content", r.status_code)
    disp = r.headers.get("Content-Disposition", "")
    check("附件名为姓名+申请编号", "attachment" in disp and "HUST3D" in disp, disp)

    r = c.get(f"/api/application/attachment/{app_id}", headers=headers,
              query_string={"type": "feedback"})
    check("反馈图片附件可下载", r.status_code == 200, r.status_code)
    r = c.get(f"/api/application/attachment/{app_id}")
    check("未登录附件下载被拦截", r.status_code == 401, r.status_code)

    # 7.19 审批留痕 / 打印留痕 / 7 天未反馈过期 / 撤回与拒绝不消耗次数
    def quota_of(h):
        return (c.get("/api/user/quota", headers=h).get_json().get("data") or {}).get("remaining")

    def submit_as(h, **purpose):
        r = c.post("/api/application/submit", data=make_data(**purpose), headers=h,
                   content_type="multipart/form-data")
        return r.get_json().get("data") or {}

    def topup_quota(student_id, n=5):
        """测试辅助：次数不足时直接补配额，避免用例相互影响。"""
        from models import User
        with app.app_context():
            u = User.query.filter_by(student_id=student_id).first()
            if u is not None:
                u.remaining_quota += n
                db.session.commit()

    # —— 需求5：打印被拒绝不消耗打印次数 ——
    q0 = quota_of(stu_headers)
    rej = submit_as(stu_headers)
    check("拒绝场景：提交后扣 1 次", quota_of(stu_headers) == q0 - 1, (q0, quota_of(stu_headers)))
    r = c.post("/api/admin/application/review", headers=headers,
               json={"id": rej["id"], "action": "reject", "comment": "模型文件不完整"})
    check("审批拒绝成功", r.get_json().get("code") == 0, r.get_json())
    check("打印被拒绝不消耗打印次数", quota_of(stu_headers) == q0, quota_of(stu_headers))

    # —— 需求1：审批人的信息落库（含姓名/学号快照与时间线操作人） ——
    d = (c.get(f"/api/application/detail/{rej['id']}", headers=stu_headers).get_json() or {}).get("data") or {}
    rv = d.get("reviewer") or {}
    check("保存审批人学号", rv.get("student_id") == STUDENT_ID, rv)
    check("保存审批人姓名", bool(rv.get("name")), rv)
    check("时间线记录审批人（operator 字段）",
          any(s.get("title") == "审批驳回" and s.get("operator") for s in (d.get("timeline") or [])),
          d.get("timeline"))

    # —— 需求4：待审批申请可撤回（=删除记录与文件，且不消耗打印次数） ——
    q1 = quota_of(stu_headers)
    wd = submit_as(stu_headers, purpose="other", purpose_other="测试撤回")
    wd_id = wd["id"]
    upload_dir = app.config["UPLOAD_DIR"]
    wd_paths = [
        os.path.join(upload_dir, u.split("uploads/", 1)[-1])
        for u in (wd.get("file_url"), wd.get("sign_url")) if u
    ]
    check("撤回前 STL/签名已落盘", all(os.path.isfile(p) for p in wd_paths), wd_paths)
    check("撤回前已扣 1 次", quota_of(stu_headers) == q1 - 1, quota_of(stu_headers))

    r = c.post(f"/api/application/withdraw/{wd_id}", headers=stu_headers)
    check("撤回申请成功", r.get_json().get("code") == 0, r.get_json())
    check("撤回后打印次数返还（不消耗）", quota_of(stu_headers) == q1, quota_of(stu_headers))
    r = c.get(f"/api/application/detail/{wd_id}", headers=stu_headers)
    check("撤回后记录已删除", r.get_json().get("code") == 404, r.get_json())
    check("撤回后 STL/签名文件已清理", not any(os.path.isfile(p) for p in wd_paths), wd_paths)

    r = c.post(f"/api/application/withdraw/{rej['id']}", headers=stu_headers)
    check("已处理的申请不可撤回", r.get_json().get("code") == 1002, r.get_json())
    r = c.post(f"/api/application/withdraw/{app_id}", headers=stu_headers)
    check("不能撤回他人申请", r.get_json().get("code") == 403, r.get_json())

    # —— 需求2：开始打印记录打印人；需求6：「正在打印」分组可查 ——
    pr = submit_as(stu_headers, purpose="research")
    pr_id = pr["id"]
    c.post("/api/admin/application/review", headers=headers, json={"id": pr_id, "action": "approve"})
    r = c.put("/api/admin/application/status", headers=headers,
              json={"id": pr_id, "status": "printing"})
    pdata = (r.get_json() or {}).get("data") or {}
    pb = pdata.get("printed_by") or {}
    check("开始打印记录打印人学号", pb.get("student_id") == STUDENT_ID, pb)
    check("开始打印记录打印人姓名", bool(pb.get("name")), pb)
    check("时间线记录打印操作人（operator 字段）",
          any(s.get("title") == "开始打印" and s.get("operator") for s in (pdata.get("timeline") or [])),
          pdata.get("timeline"))

    r = c.get("/api/admin/applications?status=printing", headers=headers)
    printing_rows = (r.get_json() or {}).get("data") or []
    check("审批管理「正在打印」分组可查询",
          any(x["id"] == pr_id for x in printing_rows), printing_rows)

    # —— 需求3：打印完成 7 天未反馈自动过期，过期后不能再反馈 ——
    c.put("/api/admin/application/status", headers=headers,
          json={"id": pr_id, "status": "completed"})
    dd = (c.get(f"/api/application/detail/{pr_id}", headers=headers).get_json() or {}).get("data") or {}
    check("完成后返回反馈截止时间", bool(dd.get("feedback_deadline")), dd.get("feedback_deadline"))
    check("完成后可提交反馈", dd.get("can_feedback") is True, dd.get("can_feedback"))
    check("人工标记完成后打印状态统一为完成",
          dd.get("print_state") == "FINISH" and dd.get("print_progress") == 100,
          (dd.get("print_state"), dd.get("print_progress")))

    # 把完成时间往回拨 8 天，模拟超过 7 天没反馈
    from datetime import datetime as _dt, timedelta as _td
    with app.app_context():
        row = db.session.get(PrintApplication, pr_id)
        row.completed_at = _dt.now() - _td(days=8)
        db.session.commit()

    rows = (c.get("/api/application/list", headers=stu_headers).get_json() or {}).get("data") or []
    target = next((x for x in rows if x["id"] == pr_id), None)
    check("超过 7 天未反馈标记为已过期",
          (target or {}).get("expired") is True and bool((target or {}).get("expired_at")), target)
    check("过期后状态仍为已完成", (target or {}).get("status") == "completed", (target or {}).get("status"))
    check("过期后不可再反馈", (target or {}).get("can_feedback") is False, target)

    r = c.post(f"/api/application/feedback/{pr_id}", headers=stu_headers,
               data={"file": (io.BytesIO(b"late feedback"), "late.png")},
               content_type="multipart/form-data")
    check("过期申请反馈被拦截", r.get_json().get("code") == 1002, r.get_json())

    r = c.get("/api/admin/applications?status=expired", headers=headers)
    check("审批管理「已过期」分组可查询",
          any(x["id"] == pr_id for x in ((r.get_json() or {}).get("data") or [])), None)
    r = c.get("/api/admin/applications?status=completed", headers=headers)
    check("已过期仍归入「打印完成」分组",
          any(x["id"] == pr_id for x in ((r.get_json() or {}).get("data") or [])), None)
    r = c.get("/api/application/list?status=expired", headers=stu_headers)
    check("学生端「已过期」筛选可查",
          any(x["id"] == pr_id for x in ((r.get_json() or {}).get("data") or [])), None)

    # 7.20 打印机绑定 + 进度 100% 自动完成（用假 MQTT 快照模拟，无需真机）
    import services.bambu as bambu_mod
    from services import print_watch

    r = c.post("/api/printer/add", headers=headers,
               json={"name": "模拟A1", "ip": "10.0.0.9", "access_code": "1234"})
    sim_pid = (r.get_json() or {}).get("data", {}).get("id")
    check("添加模拟打印机", bool(sim_pid), r.get_json())

    # 用假快照替换 MQTT 实时状态
    real_snapshot_for = bambu_mod.snapshot_for
    fake = {"online": True, "state": None, "percent": None, "state_text": "空闲"}
    bambu_mod.snapshot_for = lambda p, _f=fake: {**real_snapshot_for(p), **_f}
    try:
        def detail_of(app_id):
            return (c.get(f"/api/application/detail/{app_id}", headers=headers).get_json() or {}).get("data") or {}

        def printer_job():
            r = c.get(f"/api/printer/{sim_pid}/status", headers=headers)
            return (((r.get_json() or {}).get("data")) or {}).get("job") or {}

        # 提交 → 审批通过 → 开始打印并绑定打印机
        sp = submit_as(stu_headers, purpose="course")
        sp_id = sp["id"]
        check("提交时保存 STL 原始文件名", bool(sp.get("file_name")), sp)
        c.post("/api/admin/application/review", headers=headers,
               json={"id": sp_id, "action": "approve"})
        r = c.put("/api/admin/application/status", headers=headers,
                  json={"id": sp_id, "status": "printing", "printer_id": sim_pid})
        sd = (r.get_json() or {}).get("data") or {}
        check("开始打印绑定打印机", (sd.get("printer") or {}).get("id") == sim_pid, sd.get("printer"))
        check("绑定后未确认已开始、未匹配",
              sd.get("print_progress") == 0 and sd.get("print_seen_running") is False
              and sd.get("print_matched") is False, sd)

        # 打印机此刻在打「别的文件」：既不能显示成本申请在打印，也不能算进度
        other_file = "毛雨涵HUST3D20261231999.stl"
        fake.update({"state": "RUNNING", "percent": 40, "state_text": "打印中",
                     "task_name": other_file})
        with app.app_context():
            print_watch.tick()
        sd = detail_of(sp_id)
        check("打印机在打别的文件时不记进度", sd.get("print_progress") is None, sd.get("print_progress"))
        check("未匹配到本申请时不认为已开始", sd.get("print_seen_running") is False, sd)
        check("记录打印机当前真实文件名",
              sd.get("print_actual_file") == other_file, sd.get("print_actual_file"))

        job = printer_job()
        check("打印机状态显示真实任务文件名", job.get("task") == other_file, job.get("task"))
        check("别的文件不会被认成本申请",
              (job.get("actual") or {}).get("apply_no") != sp["apply_no"], job.get("actual"))
        check("本申请出现在「已派单未开始」",
              (job.get("bound") or {}).get("apply_no") == sp["apply_no"], job.get("bound"))

        # 别的文件打到 100% 也不能把本申请标记完成（这是最关键的防误判）
        fake.update({"state": "FINISH", "percent": 100, "state_text": "打印完成"})
        with app.app_context():
            done = print_watch.tick()
        sd = detail_of(sp_id)
        check("别的文件打完不会误完成本申请",
              done == 0 and sd.get("status") == "printing", (done, sd.get("status")))

        # 文件名里没有申请编号（如 plate_1）同样不参与自动完成
        fake.update({"state": "RUNNING", "percent": 33, "state_text": "打印中", "task_name": "plate_1"})
        with app.app_context():
            print_watch.tick()
        sd = detail_of(sp_id)
        check("文件名无申请编号时不参与自动完成", sd.get("print_matched") is False, sd.get("print_matched"))

        # 同一台打印机允许指派多个申请（一盘多件时会一起打印）
        sp2 = submit_as(stu_headers, purpose="research")
        c.post("/api/admin/application/review", headers=headers,
               json={"id": sp2["id"], "action": "approve"})
        r = c.put("/api/admin/application/status", headers=headers,
                  json={"id": sp2["id"], "status": "printing", "printer_id": sim_pid})
        sd2 = (r.get_json() or {}).get("data") or {}
        check("同一台打印机可指派多个申请",
              r.get_json().get("code") == 0 and (sd2.get("printer") or {}).get("id") == sim_pid,
              r.get_json())

        # 打印机开始打「本申请」的文件（姓名+申请编号.stl）：这才算开始，回写进度但不完成
        my_file = f"丘馗{sp['apply_no']}.stl"
        fake.update({"state": "RUNNING", "percent": 12, "state_text": "打印中", "task_name": my_file})
        with app.app_context():
            print_watch.tick()
        sd = detail_of(sp_id)
        check("匹配到本申请后回写进度", sd.get("print_progress") == 12, sd.get("print_progress"))
        check("匹配后确认已开始打印", sd.get("print_seen_running") is True, sd)
        check("未到 100% 不自动完成", sd.get("status") == "printing", sd.get("status"))

        job = printer_job()
        check("打印机状态按文件名匹配到本申请",
              any(x["apply_no"] == sp["apply_no"] for x in (job.get("actuals") or [])),
              job.get("actuals"))
        check("匹配到本申请后它不再算「已派单未开始」",
              all(x["apply_no"] != sp["apply_no"] for x in (job.get("assignments") or [])),
              job.get("assignments"))

        # 打印机报告 FINISH 100%：自动标记完成
        fake.update({"state": "FINISH", "percent": 100, "state_text": "打印完成", "task_name": my_file})
        with app.app_context():
            done = print_watch.tick()
        check("进度 100% 触发自动完成", done == 1, done)
        sd = detail_of(sp_id)
        check("申请已自动标记完成", sd.get("status") == "completed", sd.get("status"))
        check("记录为自动完成", sd.get("completed_auto") is True, sd)
        check("自动完成写入完成时间", bool(sd.get("completed_at")), sd)
        check("自动完成进度的记录为 100%", sd.get("print_progress") == 100, sd.get("print_progress"))
        rows = (c.get("/api/notification/list", headers=stu_headers).get_json() or {}).get("data") or []
        check("自动完成后发取件提醒",
              any(x.get("ntype") == "pickup" and sp["apply_no"] in (x.get("title") or "")
                  for x in rows), rows[:3])

        # —— 一盘多件：文件名形如 A + B + C.stl，盘里每份申请都要被识别并一起完成 ——
        topup_quota("20260002", 5)
        m1 = submit_as(stu_headers, purpose="course")
        m2 = submit_as(stu_headers, purpose="research")
        for m in (m1, m2):
            c.post("/api/admin/application/review", headers=headers,
                   json={"id": m["id"], "action": "approve"})
            c.put("/api/admin/application/status", headers=headers,
                  json={"id": m["id"], "status": "printing", "printer_id": sim_pid})
        plate_file = f"丘馗{m1['apply_no']} + 毛雨涵{m2['apply_no']}.stl"
        fake.update({"state": "RUNNING", "percent": 45, "state_text": "打印中",
                     "task_name": plate_file})
        with app.app_context():
            print_watch.tick()
        dm1, dm2 = detail_of(m1["id"]), detail_of(m2["id"])
        check("一盘多件时多份申请同时匹配",
              dm1.get("print_matched") is True and dm2.get("print_matched") is True,
              (dm1.get("print_matched"), dm2.get("print_matched")))
        check("一盘多件时同步回写进度",
              dm1.get("print_progress") == 45 and dm2.get("print_progress") == 45,
              (dm1.get("print_progress"), dm2.get("print_progress")))

        job = printer_job()
        check("打印机状态列出盘里全部申请",
              sorted(x["apply_no"] for x in (job.get("actuals") or []))
              == sorted([m1["apply_no"], m2["apply_no"]]),
              [x["apply_no"] for x in (job.get("actuals") or [])])

        fake.update({"state": "FINISH", "percent": 100, "state_text": "打印完成",
                     "task_name": plate_file})
        with app.app_context():
            done = print_watch.tick()
        check("一盘多件打完时一起自动完成", done == 2, done)
        check("盘里两份申请都已完成",
              detail_of(m1["id"]).get("status") == "completed"
              and detail_of(m2["id"]).get("status") == "completed",
              (detail_of(m1["id"]).get("status"), detail_of(m2["id"]).get("status")))

        # 防误判：绑定后打印机已停在上一单的 FINISH/100%，不应立即完成
        sp3 = submit_as(stu_headers, purpose="club")
        c.post("/api/admin/application/review", headers=headers,
               json={"id": sp3["id"], "action": "approve"})
        c.put("/api/admin/application/status", headers=headers,
              json={"id": sp3["id"], "status": "printing", "printer_id": sim_pid})
        sp3_file = f"毛雨涵{sp3['apply_no']}.stl"
        fake.update({"state": "FINISH", "percent": 100, "state_text": "打印完成",
                     "task_name": sp3_file})
        with app.app_context():
            print_watch.tick()
        sd3 = detail_of(sp3["id"])
        check("打印机停在 100% 时不误判完成", sd3.get("status") == "printing", sd3.get("status"))

        # 中途暂停不算完成；恢复后到 100% 才完成
        fake.update({"state": "PAUSE", "percent": 55, "state_text": "已暂停", "task_name": sp3_file})
        with app.app_context():
            print_watch.tick()
        sd3 = detail_of(sp3["id"])
        check("暂停中不自动完成", sd3.get("status") == "printing", sd3.get("status"))
        fake.update({"state": "RUNNING", "percent": 99, "state_text": "打印中", "task_name": sp3_file})
        with app.app_context():
            print_watch.tick()
        fake.update({"state": "FINISH", "percent": 100, "state_text": "打印完成", "task_name": sp3_file})
        with app.app_context():
            print_watch.tick()
        sd3 = detail_of(sp3["id"])
        check("恢复后到 100% 自动完成", sd3.get("status") == "completed", sd3.get("status"))

        # 自动认领：申请没指派打印机（点开始打印时没选机器），但打印机在打它的文件
        topup_quota("20260002", 5)
        ad = submit_as(stu_headers, purpose="other", purpose_other="自动认领")
        check("认领用例：提交申请成功", bool(ad.get("id")), ad)
        c.post("/api/admin/application/review", headers=headers,
               json={"id": ad["id"], "action": "approve"})
        ad_d = (c.put("/api/admin/application/status", headers=headers,
                      json={"id": ad["id"], "status": "printing"}).get_json() or {}).get("data") or {}
        check("未指定打印机时不绑定", ad_d.get("printer") is None, ad_d.get("printer"))

        ad_file = f"某某{ad['apply_no']}.stl"
        fake.update({"state": "RUNNING", "percent": 8, "state_text": "打印中", "task_name": ad_file})
        with app.app_context():
            print_watch.tick()
        ad_d = detail_of(ad["id"])
        check("打印机在打该文件时自动认领打印机",
              (ad_d.get("printer") or {}).get("id") == sim_pid, ad_d.get("printer"))
        with app.app_context():
            print_watch.tick()
        ad_d = detail_of(ad["id"])
        check("认领后正常跟踪进度", ad_d.get("print_progress") == 8, ad_d.get("print_progress"))
        fake.update({"state": "FINISH", "percent": 100, "state_text": "打印完成", "task_name": ad_file})
        with app.app_context():
            print_watch.tick()
        ad_d = detail_of(ad["id"])
        check("认领的申请到 100% 自动完成", ad_d.get("status") == "completed", ad_d.get("status"))
    finally:
        bambu_mod.snapshot_for = real_snapshot_for
        c.delete(f"/api/printer/delete/{sim_pid}", headers=headers)

    # 7.21 首页取件提醒弹窗（打印完成 → 打开首页弹窗提示取件）
    def pickup_items(h):
        d = (c.get("/api/notification/pickup", headers=h).get_json() or {}).get("data") or {}
        return d, (d.get("items") or [])

    pk, items = pickup_items(stu_headers)
    check("取件提醒可拉取", pk.get("count", 0) >= 1, pk.get("count"))
    item = next((x for x in items
                 if (x.get("application") or {}).get("apply_no") == sp["apply_no"]), None) or {}
    check("取件提醒包含刚打印完成的申请", bool(item), [x.get("title") for x in items])
    check("取件提醒带申请编号", (item.get("application") or {}).get("apply_no") == sp["apply_no"], item)
    check("取件提醒带 STL 文件名",
          (item.get("application") or {}).get("file_name") == sp.get("file_name"), item)

    # 「我知道了」→ 只确认这一条，其余保留
    r = c.post("/api/notification/pickup/ack", headers=stu_headers, json={"ids": [item.get("id")]})
    check("确认取件提醒成功", r.get_json().get("code") == 0, r.get_json())
    _, left = pickup_items(stu_headers)
    check("确认后该条不再出现", all(x.get("id") != item.get("id") for x in left), left)

    # 不传 ids → 全部确认
    r = c.post("/api/notification/pickup/ack", headers=stu_headers, json={})
    check("全部确认取件提醒", r.get_json().get("code") == 0, r.get_json())
    _, left = pickup_items(stu_headers)
    check("全部确认后不再出现", left == [], left)

    # 人工「标记完成」且未领取时同样产生取件提醒
    topup_quota("20260002", 5)
    mp = submit_as(stu_headers, purpose="graduation")
    check("取件用例：提交申请成功", bool(mp.get("id")), mp)
    c.post("/api/admin/application/review", headers=headers,
           json={"id": mp["id"], "action": "approve"})
    c.put("/api/admin/application/status", headers=headers,
          json={"id": mp["id"], "status": "printing"})
    c.put("/api/admin/application/status", headers=headers,
          json={"id": mp["id"], "status": "completed"})
    _, items = pickup_items(stu_headers)
    check("人工标记完成也发取件提醒",
          any((x.get("application") or {}).get("apply_no") == mp["apply_no"] for x in items), items)

    # 取件提醒只发给申请人本人
    adm_pk, _ = pickup_items(headers)
    check("取件提醒仅申请人本人可见", adm_pk.get("count") == 0, adm_pk.get("count"))

    # 7.22 首页「待完成」清单：待取件（已领取按钮）+ 待反馈（上传反馈图按钮）
    def todos_of(h):
        return ((c.get("/api/application/todos", headers=h).get_json() or {}).get("data")) or {}

    def todo_kinds(h):
        return {(x["kind"], x["apply_no"]) for x in (todos_of(h).get("items") or [])}

    td = todos_of(stu_headers)
    items = td.get("items") or []
    kinds = {(x["kind"], x["apply_no"]) for x in items}
    check("待完成清单可拉取", td.get("count") == len(items), td.get("count"))
    check("待完成含待取件", ("pickup", sp["apply_no"]) in kinds, sorted(kinds))
    check("待完成含待反馈", ("feedback", sp["apply_no"]) in kinds, sorted(kinds))
    check("已过期申请只催取件、不催反馈",
          ("pickup", pr["apply_no"]) in kinds and ("feedback", pr["apply_no"]) not in kinds,
          sorted(kinds))

    # 「上传反馈图」→ 这条待反馈消失，待取件仍在
    r = c.post(f"/api/application/feedback/{sp_id}", headers=stu_headers,
               data={"file": (io.BytesIO(b"\x89PNG feed"), "fb.png")},
               content_type="multipart/form-data")
    check("待完成用例：上传反馈成功", r.get_json().get("code") == 0, r.get_json())
    kinds = todo_kinds(stu_headers)
    check("上传反馈后待反馈条消失", ("feedback", sp["apply_no"]) not in kinds, sorted(kinds))
    check("上传反馈后自动标记已领取（待取件条消失）", ("pickup", sp["apply_no"]) not in kinds, sorted(kinds))

    # 「已领取」→ 这条待取件消失，申请记录 picked_up
    r = c.post(f"/api/application/pickup/{sp_id}", headers=stu_headers)
    check("标记已领取成功", r.get_json().get("code") == 0, r.get_json())
    check("标记后 picked_up 为真",
          (r.get_json().get("data") or {}).get("picked_up") is True, r.get_json())
    kinds = todo_kinds(stu_headers)
    check("标记领取后待取件条消失", ("pickup", sp["apply_no"]) not in kinds, sorted(kinds))

    r = c.post(f"/api/application/pickup/{sp_id}", headers=stu_headers)
    check("重复标记已领取不报错", r.get_json().get("code") == 0, r.get_json())
    r = c.post(f"/api/application/pickup/{app_id}", headers=stu_headers)
    check("不能标记他人申请领取", r.get_json().get("code") == 403, r.get_json())

    admin_todos = todos_of(headers).get("items") or []
    check("待完成清单仅本人可见（管理员返回汇总待办）",
          all("apply_no" not in x for x in admin_todos) and all(x["kind"] in ("approve", "print", "chat", "feedback_review") for x in admin_todos),
          admin_todos)

    # 7.23 App 版本发布与客户端更新检查
    r = c.get("/api/app/latest", headers=stu_headers)
    check("App 版本接口可访问（普通用户）", r.get_json().get("code") == 0, r.get_json())
    check("未发布过时最新版本为 null", r.get_json().get("data") is None, r.get_json())

    r = c.post("/api/app/releases", headers=headers,
               data={"file": (io.BytesIO(b"PK\x03\x04 fake apk " * 200), "hust3d-1.3.apk"),
                     "version_code": "3", "version_name": "1.3",
                     "note": "修复若干问题\n新增首页待完成"},
               content_type="multipart/form-data")
    rel = (r.get_json() or {}).get("data") or {}
    check("管理员上传 APK 成功", r.get_json().get("code") == 0, r.get_json())
    check("上传返回版本信息",
          rel.get("version_code") == 3 and rel.get("version_name") == "1.3", rel)
    rel_id = rel.get("id")

    latest = ((c.get("/api/app/latest", headers=stu_headers).get_json() or {}).get("data")) or {}
    check("普通用户能查到最新版本", latest.get("version_code") == 3, latest)
    check("latest 带 APK 地址与大小",
          bool(latest.get("file_url")) and (latest.get("file_size") or 0) > 0, latest)

    r = c.post("/api/app/releases", headers=headers,
               data={"file": (io.BytesIO(b"x"), "x.apk"), "version_code": "3"},
               content_type="multipart/form-data")
    check("重复版本号被拦截", r.get_json().get("code") == 1002, r.get_json())
    r = c.post("/api/app/releases", headers=headers,
               data={"file": (io.BytesIO(b"x"), "x.zip"), "version_code": "4"},
               content_type="multipart/form-data")
    check("非 apk 文件被拦截", r.get_json().get("code") == 1002, r.get_json())
    r = c.post("/api/app/releases", headers=headers,
               data={"file": (io.BytesIO(b"x"), "x.apk"), "version_code": "abc"},
               content_type="multipart/form-data")
    check("非法版本号被拦截", r.get_json().get("code") == 1002, r.get_json())

    r = c.post("/api/app/releases", headers=stu_headers,
               data={"file": (io.BytesIO(b"x"), "x.apk"), "version_code": "5"},
               content_type="multipart/form-data")
    check("普通用户无权上传 APK", r.status_code == 403, r.status_code)
    r = c.get("/api/app/releases", headers=stu_headers)
    check("普通用户无权查看发布历史", r.status_code == 403, r.status_code)
    r = c.get("/api/app/releases", headers=headers)
    check("管理员可查看发布历史", len((r.get_json() or {}).get("data") or []) == 1, r.get_json())

    # 删除版本：latest 回到 null，APK 文件也被清理
    apk_path = os.path.join(app.config["UPLOAD_DIR"], (rel.get("file_url") or "").split("uploads/", 1)[-1])
    check("APK 文件已落盘", os.path.isfile(apk_path), apk_path)
    r = c.delete(f"/api/app/releases/{rel_id}", headers=headers)
    check("删除版本成功", r.get_json().get("code") == 0, r.get_json())
    check("删除后最新版本为 null",
          ((c.get("/api/app/latest", headers=stu_headers).get_json() or {}).get("data")) is None)
    check("删除后 APK 文件已清理", not os.path.isfile(apk_path), apk_path)

    # 7.24 取件短信通知（SmsForwarder 等手机网关）
    import services.sms as sms_mod

    class _FakeResp:
        def __init__(self, code):
            self.status_code = code
            self.text = ""

    sent_calls = []  # [(url, kwargs)]
    real_get, real_post = sms_mod._http_get, sms_mod._http_post
    cfg = app.config
    saved = {k: cfg.get(k) for k in (
        "SMS_ENABLED", "SMS_GATEWAY_URL", "SMS_GATEWAY_URLS", "SMS_GATEWAY_METHOD", "ENV_FILE",
        "SMS_GATEWAY_TOKEN", "SMS_TEMPLATE", "SMS_PROVIDER", "SMS_JSON_TEMPLATE",
    )}

    def _fake_get(url, **kw):
        sent_calls.append((url, kw))
        return _FakeResp(200)

    def _set_gateways(*urls):
        """设置短信网关列表（模拟 .env 里的 SMS_GATEWAY_URL / _2 / ...）。"""
        cfg["SMS_GATEWAY_URLS"] = list(urls)
        cfg["SMS_GATEWAY_URL"] = urls[0] if urls else ""

    try:
        sms_mod._http_get = _fake_get
        sms_mod._http_post = _fake_get
        cfg["SMS_ENABLED"] = True
        cfg["SMS_PROVIDER"] = "template"
        _set_gateways("http://sms.local:8080/send_sms?token={token}&phone={phone}&msg={msg}")
        cfg["SMS_GATEWAY_METHOD"] = "GET"
        cfg["SMS_GATEWAY_TOKEN"] = "tk123"
        cfg["SMS_TEMPLATE"] = "【3D打印】{name}，{apply_no} 已打印完成，请来领取。"

        r = c.post(f"/api/admin/application/send-sms/{mp['id']}", headers=headers)
        check("管理员手动发送取件短信", r.get_json().get("code") == 0, r.get_json())
        check("短信网关被调用一次", len(sent_calls) == 1, len(sent_calls))
        url = sent_calls[0][0] if sent_calls else ""
        check("短信地址带 token", "tk123" in url, url)
        check("短信地址带申请人手机号", "13800000000" in url, url)
        check("短信正文含申请编号", mp["apply_no"] in url, url)

        d = detail_of(mp["id"])
        check("短信发送时间已记录", bool(d.get("sms_sent_at")), d.get("sms_sent_at"))
        check("短信结果记录为成功", "已发送" in (d.get("sms_result") or ""), d.get("sms_result"))

        # 网关异常 → 接口报错，原因写入记录
        sms_mod._http_get = lambda url, **kw: _FakeResp(500)
        sms_mod._http_post = sms_mod._http_get
        r = c.post(f"/api/admin/application/send-sms/{mp['id']}", headers=headers)
        check("网关异常时返回失败", r.get_json().get("code") == 1002, r.get_json())
        d = detail_of(mp["id"])
        check("失败原因写入记录", "500" in (d.get("sms_result") or ""), d.get("sms_result"))

        # —— JSON 通道（SmsForwarder 主动控制 /sms/send 的真实报文）——
        sent_calls.clear()
        sms_mod._http_post = _fake_get
        cfg["SMS_PROVIDER"] = "json"
        _set_gateways("http://192.168.1.129:5000/sms/send")
        cfg["SMS_JSON_TEMPLATE"] = '{"data":{"sim_slot":1,"phone_numbers":"{phone}","msg_content":"{msg}"}}'
        r = c.post(f"/api/admin/application/send-sms/{mp['id']}", headers=headers)
        check("JSON 通道发送成功", r.get_json().get("code") == 0, r.get_json())
        check("JSON 通道调用了 /sms/send",
              bool(sent_calls) and sent_calls[0][0].endswith("/sms/send"), sent_calls[:1])
        raw = sent_calls[0][1].get("data", b"") if sent_calls else b""
        body_text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        check("JSON 报文是合法 JSON", isinstance(json.loads(body_text), dict), body_text)
        parsed = json.loads(body_text) if body_text else {}
        inner = parsed.get("data") or {}
        check("JSON 报文 phone_numbers 正确", inner.get("phone_numbers") == "13800000000", parsed)
        check("JSON 报文 sim_slot=1", inner.get("sim_slot") == 1, parsed)
        check("JSON 报文 msg_content 含申请编号", mp["apply_no"] in (inner.get("msg_content") or ""), parsed)
        check("JSON 请求带 Content-Type: application/json",
              "application/json" in (sent_calls[0][1].get("headers") or {}).get("Content-Type", ""),
              sent_calls[0][1].get("headers"))
        cfg["SMS_PROVIDER"] = "template"

        # 测试接口
        sms_mod._http_get = lambda url, **kw: _FakeResp(200)
        sms_mod._http_post = sms_mod._http_get
        r = c.post("/api/admin/sms/test", headers=headers, json={"phone": "13800000000"})
        check("测试短信用例可用", r.get_json().get("code") == 0, r.get_json())
        r = c.post("/api/admin/sms/test", headers=headers, json={"phone": ""})
        check("测试短信校验手机号", r.get_json().get("code") == 1002, r.get_json())

        # —— 多监听窗口：第一个不通就自动用第二个 ——
        sms_mod._http_post = _fake_get
        cfg["SMS_PROVIDER"] = "json"
        _set_gateways("http://192.168.1.129:5000/sms/send", "http://192.168.1.130:5000/sms/send")

        tried = []

        def _first_down(url, **kw):
            tried.append(url)
            if "192.168.1.129" in url:
                raise sms_mod.requests.exceptions.ConnectionError("第一个窗口离线")
            return _FakeResp(200)

        sms_mod._http_post = _first_down
        sms_mod._http_get = _first_down
        sent_calls.clear()
        r = c.post("/api/admin/sms/send", headers=headers,
                   json={"phone": "13900000009", "content": "多窗口自动切换测试"})
        j = r.get_json() or {}
        check("多窗口：一个离线仍能发送成功", j.get("code") == 0, j)
        check("多窗口：按顺序先试第一个", bool(tried) and "192.168.1.129" in tried[0], tried)
        check("多窗口：失败后切到第二个", any("192.168.1.130" in u for u in tried), tried)
        check("多窗口：记录里写的是实际使用的窗口",
              "192.168.1.130" in ((j.get("data") or {}).get("gateway") or ""),
              (j.get("data") or {}).get("gateway"))

        # 全部不可达 → 入队
        def _all_down(url, **kw):
            raise sms_mod.requests.exceptions.ConnectionError("全部离线")

        sms_mod._http_post = _all_down
        sms_mod._http_get = _all_down
        r = c.post("/api/admin/sms/send", headers=headers,
                   json={"phone": "13900000010", "content": "全部窗口离线"})
        j = r.get_json() or {}
        check("多窗口全部离线时仍返回并排队", j.get("code") == 0, j)
        check("多窗口全部离线时状态为 pending",
              (j.get("data") or {}).get("status") == "pending", (j.get("data") or {}).get("status"))
        check("多窗口失败原因包含两个窗口",
              "192.168.1.129" in ((j.get("data") or {}).get("last_error") or "")
              and "192.168.1.130" in ((j.get("data") or {}).get("last_error") or ""),
              (j.get("data") or {}).get("last_error"))

        # 状态接口返回每个窗口的可达性
        cfg["SMS_GATEWAY_URLS"] = ["http://127.0.0.1:1/x", "http://127.0.0.1:2/x"]
        r = c.get("/api/admin/sms/status", headers=headers)
        st = (r.get_json() or {}).get("data") or {}
        check("状态接口返回窗口列表", len(st.get("gateways") or []) == 2, st.get("gateways"))
        check("状态接口标记窗口不可达",
              all(g.get("reachable") is False for g in (st.get("gateways") or [])), st.get("gateways"))
        _set_gateways("http://192.168.1.129:5000/sms/send")

        # —— 监听窗口的增删（管理端 + 号）——
        import tempfile
        env_tmp = os.path.join(tempfile.gettempdir(), "smoke_sms_gateways.env")
        with open(env_tmp, "w", encoding="utf-8") as f:
            f.write("DB_HOST=127.0.0.1\nOTHER=1\n"
                    "SMS_GATEWAY_URL=http://192.168.1.129:5000/sms/send\n"
                    "SMS_GATEWAY_URL_2=http://192.168.1.130:5000/sms/send\n")
        cfg["ENV_FILE"] = env_tmp
        _set_gateways("http://192.168.1.129:5000/sms/send", "http://192.168.1.130:5000/sms/send")
        try:
            r = c.get("/api/admin/sms/gateways", headers=headers)
            gl = ((r.get_json() or {}).get("data") or {}).get("items") or []
            check("监听窗口列表可查", len(gl) == 2, gl)

            r = c.post("/api/admin/sms/gateways", headers=headers,
                       json={"url": "http://192.168.1.131:5000/sms/send"})
            check("新增监听窗口", r.get_json().get("code") == 0, r.get_json())
            after = ((r.get_json() or {}).get("data") or {}).get("items") or []
            check("新增后列表含新窗口",
                  "http://192.168.1.131:5000/sms/send" in after, after)
            check("新增后内存配置已更新",
                  "http://192.168.1.131:5000/sms/send" in (cfg.get("SMS_GATEWAY_URLS") or []),
                  cfg.get("SMS_GATEWAY_URLS"))
            env_text = open(env_tmp, encoding="utf-8").read()
            check("新增已写回 .env",
                  "SMS_GATEWAY_URL_3=http://192.168.1.131:5000/sms/send" in env_text, env_text)
            check("写回时保留其它配置", "DB_HOST=127.0.0.1" in env_text and "OTHER=1" in env_text, env_text)

            r = c.post("/api/admin/sms/gateways", headers=headers,
                       json={"url": "http://192.168.1.131:5000/sms/send"})
            check("重复窗口被拦截", r.get_json().get("code") == 1002, r.get_json())
            r = c.post("/api/admin/sms/gateways", headers=headers, json={"url": "ftp://x"})
            check("非法窗口地址被拦截", r.get_json().get("code") == 1002, r.get_json())
            r = c.post("/api/admin/sms/gateways", headers=headers, json={"url": ""})
            check("空地址被拦截", r.get_json().get("code") == 1002, r.get_json())

            r = c.delete("/api/admin/sms/gateways?url=http://192.168.1.131:5000/sms/send",
                         headers=headers)
            check("删除监听窗口", r.get_json().get("code") == 0, r.get_json())
            after = ((r.get_json() or {}).get("data") or {}).get("items") or []
            check("删除后列表不含该窗口",
                  "http://192.168.1.131:5000/sms/send" not in after, after)
            env_text = open(env_tmp, encoding="utf-8").read()
            check("删除已写回 .env", "192.168.1.131" not in env_text, env_text)
            check("删除后第一个窗口顺移",
                  "SMS_GATEWAY_URL=http://192.168.1.129:5000/sms/send" in env_text, env_text)

            r = c.delete("/api/admin/sms/gateways?url=http://192.168.1.199:1/x", headers=headers)
            check("删除不存在的窗口被拦截", r.get_json().get("code") == 1002, r.get_json())

            check("普通用户无权增删监听窗口",
                  c.post("/api/admin/sms/gateways", headers=stu_headers,
                         json={"url": "http://1.2.3.4:1/x"}).status_code == 403)
            check("普通用户无权看监听窗口",
                  c.get("/api/admin/sms/gateways", headers=stu_headers).status_code == 403)
        finally:
            cfg["ENV_FILE"] = saved.get("ENV_FILE")
            _set_gateways("http://192.168.1.129:5000/sms/send")
            try:
                os.remove(env_tmp)
            except OSError:
                pass

        # 配置查询（脱敏）
        r = c.get("/api/admin/sms/config", headers=headers)
        cf = (r.get_json() or {}).get("data") or {}
        check("短信配置可查且脱敏",
              cf.get("enabled") is True and cf.get("has_token") is True and "tk123" not in str(cf), cf)

        # 未启用时拒绝发送
        cfg["SMS_ENABLED"] = False
        r = c.post(f"/api/admin/application/send-sms/{mp['id']}", headers=headers)
        check("未启用短信时拒绝发送",
              r.get_json().get("code") == 1002 and "短信开关" in (r.get_json().get("msg") or ""),
              r.get_json())

        # 权限：普通用户不能发
        cfg["SMS_ENABLED"] = True
        r = c.post(f"/api/admin/application/send-sms/{mp['id']}", headers=stu_headers)
        check("普通用户无权发短信", r.status_code == 403, r.status_code)
        check("普通用户无权查短信配置",
              c.get("/api/admin/sms/config", headers=stu_headers).status_code == 403)

        # 手机号无效时不发
        with app.app_context():
            from models import User as _U
            u = _U.query.filter_by(student_id="20260002").first()
            old_phone = u.phone
            u.phone = ""
            db.session.commit()
        r = c.post(f"/api/admin/application/send-sms/{mp['id']}", headers=headers)
        check("申请人无手机号时拒绝发送", r.get_json().get("code") == 1002, r.get_json())
        with app.app_context():
            from models import User as _U2
            u2 = _U2.query.filter_by(student_id="20260002").first()
            u2.phone = old_phone
            db.session.commit()

        # —— 7.25 管理员自定义短信 ——
        r = c.post("/api/admin/sms/send", headers=headers,
                   json={"phone": "13900000001", "content": "同学你好，你的打印件已到工作室。"})
        check("管理员自定义发短信", r.get_json().get("code") == 0, r.get_json())
        custom_id = ((r.get_json() or {}).get("data") or {}).get("id")
        check("自定义短信记录已入库", bool(custom_id), r.get_json())

        r = c.post("/api/admin/sms/send", headers=headers,
                   json={"phone": "1390000000", "content": "x"})
        check("自定义短信校验手机号", r.get_json().get("code") == 1002, r.get_json())
        r = c.post("/api/admin/sms/send", headers=headers,
                   json={"phone": "13900000001", "content": "   "})
        check("自定义短信校验内容", r.get_json().get("code") == 1002, r.get_json())
        r = c.post("/api/admin/sms/send", headers=headers,
                   json={"phone": "13900000001", "content": "x" * 501})
        check("自定义短信校验长度", r.get_json().get("code") == 1002, r.get_json())

        # 记录列表
        r = c.get("/api/admin/sms/messages", headers=headers)
        lst = (r.get_json() or {}).get("data") or {}
        check("短信记录列表可查", lst.get("total", 0) >= 1, lst.get("total"))
        check("短信记录含状态统计",
              all(k in (lst.get("counts") or {}) for k in ("all", "sent", "pending", "failed")),
              lst.get("counts"))
        first = (lst.get("items") or [{}])[0]
        check("短信记录含手机号与内容", first.get("phone") and first.get("content"), first)

        r = c.get("/api/admin/sms/messages?status=sent", headers=headers)
        sent_list = (r.get_json() or {}).get("data") or {}
        check("按已发送过滤",
              all(i.get("status") == "sent" for i in (sent_list.get("items") or [])),
              [i.get("status") for i in (sent_list.get("items") or [])][:5])

        # 网关不可达 → 入队待发送
        def _conn_err(url, **kw):
            raise sms_mod.requests.exceptions.ConnectionError("gateway down")

        sms_mod._http_get = _conn_err
        sms_mod._http_post = _conn_err
        r = c.post("/api/admin/sms/send", headers=headers,
                   json={"phone": "13900000002", "content": "网关离线时的短信"})
        j = r.get_json() or {}
        check("网关不可达时仍返回成功并排队", j.get("code") == 0, j)
        check("排队提示文案正确", "队列" in (j.get("msg") or ""), j.get("msg"))
        queued = (j.get("data") or {})
        check("排队记录状态为 pending", queued.get("status") == "pending", queued.get("status"))
        check("排队记录记下失败原因", "不可达" in (queued.get("last_error") or ""), queued.get("last_error"))
        check("排队记录设置了重试时间", bool(queued.get("next_retry_at")), queued.get("next_retry_at"))

        # 网关恢复 → 重发成功
        sms_mod._http_get = _fake_get
        sms_mod._http_post = _fake_get
        with app.app_context():
            from models import SmsMessage as _Sms
            sms_mod.retry_pending()
            still = db.session.get(_Sms, queued.get("id")).status
        check("未到重试时间的记录不会被补发", still == "pending", still)
        r = c.post(f"/api/admin/sms/messages/{queued.get('id')}/retry", headers=headers)
        check("手动重发排队短信成功", r.get_json().get("code") == 0, r.get_json())
        check("重发后状态变已发送",
              ((r.get_json() or {}).get("data") or {}).get("status") == "sent",
              (r.get_json() or {}).get("data"))

        # 状态接口
        r = c.get("/api/admin/sms/status", headers=headers)
        st = (r.get_json() or {}).get("data") or {}
        check("短信状态接口可用", "reachable" in st and "pending" in st, st)

        # 删除记录
        r = c.delete(f"/api/admin/sms/messages/{custom_id}", headers=headers)
        check("删除短信记录", r.get_json().get("code") == 0, r.get_json())
        r = c.delete(f"/api/admin/sms/messages/{custom_id}", headers=headers)
        check("删除不存在的记录返回 404", r.status_code == 404, r.status_code)

        # 权限
        check("普通用户无权发自定义短信",
              c.post("/api/admin/sms/send", headers=stu_headers,
                     json={"phone": "13900000001", "content": "x"}).status_code == 403)
        check("普通用户无权看短信记录",
              c.get("/api/admin/sms/messages", headers=stu_headers).status_code == 403)
        check("普通用户无权看短信状态",
              c.get("/api/admin/sms/status", headers=stu_headers).status_code == 403)
    finally:
        sms_mod._http_get, sms_mod._http_post = real_get, real_post
        for k, v in saved.items():
            app.config[k] = v

    # 7.18 打印失败：返还次数 + 原因必填
    r = c.post("/api/application/submit", data=make_data(purpose="research"), headers=stu_headers,
               content_type="multipart/form-data")
    check("打印失败用例提交申请", r.get_json().get("code") == 0, r.get_json())
    fid = (r.get_json().get("data") or {}).get("id")
    c.post("/api/admin/application/review", headers=headers, json={"id": fid, "action": "approve"})
    r = c.get("/api/user/quota", headers=stu_headers)
    q_f0 = (r.get_json().get("data") or {}).get("remaining")

    r = c.put("/api/admin/application/status", headers=headers, json={"id": fid, "status": "failed"})
    check("缺原因标记失败被拦截", r.get_json().get("code") == 1002, r.get_json())
    r = c.put("/api/admin/application/status", headers=headers,
              json={"id": fid, "status": "failed", "reason": "打印机喷头堵塞，无法完成"})
    check("标记打印失败", r.get_json().get("code") == 0 and
          (r.get_json().get("data") or {}).get("status") == "failed", r.get_json())
    r = c.get("/api/user/quota", headers=stu_headers)
    check("失败后次数返还", (r.get_json().get("data") or {}).get("remaining") == q_f0 + 1, r.get_json())
    r = c.get(f"/api/application/detail/{fid}", headers=stu_headers)
    check("失败原因已记录", "喷头堵塞" in ((r.get_json().get("data") or {}).get("admin_comment") or ""), r.get_json())

    # 完成时邮件通知（SMTP 未配置 → 静默跳过，不报错）
    r = c.put("/api/admin/application/status", headers=headers, json={"id": fid, "status": "printing"})
    r = c.put("/api/admin/application/status", headers=headers, json={"id": fid, "status": "completed"})
    check("完成状态流转正常（邮件静默）", r.get_json().get("code") == 0, r.get_json())

    # 8. 退出登录
    r = c.post("/api/auth/logout", headers=headers)
    check("logout 返回成功", r.get_json().get("code") == 0)

    # 汇总
    passed = sum(checks)
    print(f"\n结果：{passed}/{len(checks)} 通过")

    # 清理测试用的临时 .env / SQLite
    for path in (SMOKE_ENV, os.path.join(BACKEND_DIR, "smoke.db")):
        try:
            os.remove(path)
        except OSError:
            pass

    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
