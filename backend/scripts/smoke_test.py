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
    check("user/info 角色为 admin", info.get("role") == "admin", info.get("role"))

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

    # 8. 退出登录
    r = c.post("/api/auth/logout", headers=headers)
    check("logout 返回成功", r.get_json().get("code") == 0)

    # 汇总
    passed = sum(checks)
    print(f"\n结果：{passed}/{len(checks)} 通过")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
