# 3D 打印服务管理系统（第一阶段 MVP）

哈尔滨理工大学创新创业协会 3D 打印工作室的打印服务线上化系统。第一阶段为**纯网页端**、
**前后端分离**架构，登录采用**教务系统统一身份认证（CAS）**（学号 + 密码 + 图形验证码）。

- 后端：Python + Flask + SQLAlchemy + MySQL 8.0
- 前端：Vue 3 + Vant 4（响应式双端适配：移动端全宽、桌面端居中限宽）
- 部署：云服务器 + Nginx + Gunicorn（正式）｜内网穿透（快速对外，见 `deploy/内网穿透部署.md`）

## 项目目录结构

```
三维科创3D/
├── backend/                       # Flask 后端
│   ├── app.py                     # 应用入口
│   ├── config.py                  # 全局配置（读 .env）
│   ├── extensions.py              # db 等共享扩展
│   ├── models.py                  # ORM 模型（users / print_applications / operation_logs）
│   ├── requirements.txt           # 依赖
│   ├── .env.example               # 环境变量样例
│   ├── .gitignore
│   ├── sql/
│   │   ├── schema.sql             # 建表脚本（MySQL 8.0）
│   │   └── migration_drop_openid.sql  # 迁移脚本（去除旧微信 openid 字段）
│   ├── utils/
│   │   ├── response.py            # 统一响应格式
│   │   └── auth.py                # JWT 签发/校验 + 登录/管理员装饰器
│   ├── services/
│   │   ├── cas.py                 # 教务系统 CAS 模拟登录（含验证码中转 + 学籍信息解析）
│   │   ├── quota.py               # 学期计算 + 配额刷新
│   │   └── logger.py              # 操作日志
│   ├── blueprints/
│   │   ├── auth.py                # /api/auth/*（验证码 + CAS 登录 + 退出）
│   │   ├── user.py                # /api/user/*（信息 + 配额）
│   │   ├── application.py         # /api/application/*（提交/列表/详情）
│   │   └── admin.py               # /api/admin/*（审批 + 状态更新）
│   ├── scripts/
│   │   └── smoke_test.py          # 全链路冒烟测试（SQLite + CAS_MOCK）
│   └── uploads/                   # 上传文件（运行时自动创建，不入库）
├── frontend/                      # Vue 3 + Vant 4 前端（SPA）
│   ├── vite.config.js             # Vite 配置（开发代理 /api、/uploads 到后端）
│   ├── index.html
│   ├── package.json
│   └── src/
│       ├── main.js                # 入口
│       ├── App.vue
│       ├── router/index.js        # 路由 + 登录守卫
│       ├── store/auth.js          # Pinia 登录态
│       ├── api/                   # request.js + 各接口封装
│       ├── utils/constants.js     # 状态/用途/条款常量
│       ├── styles/global.css      # 全局样式 + 响应式断点
│       ├── components/
│       │   ├── TabBar.vue         # 底部导航
│       │   └── SignaturePad.vue   # 手写签名（signature_pad）
│       └── views/
│           ├── Login.vue          # 学号密码登录（CAS）
│           ├── Home.vue           # 首页（配额 + 快捷入口 + 通知）
│           ├── Apply.vue          # 打印申请表单
│           ├── MyApplications.vue # 我的申请（按状态分类）
│           ├── ApplicationDetail.vue # 详情 + 时间线
│           ├── Profile.vue        # 个人中心
│           └── admin/AdminPending.vue # 管理后台（审批 + 状态推进）
└── deploy/
    ├── nginx.conf                 # Nginx 配置示例
    └── README.md                  # 部署上线步骤
```

## 已实现接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/auth/captcha` | 获取教务系统登录图形验证码（返回 base64 图片） |
| POST | `/api/auth/cas-login` | 学号 + 密码 + 验证码登录，返回 token 与用户信息 |
| POST | `/api/auth/logout` | 退出登录 |
| GET | `/api/user/info` | 获取当前用户信息 |
| GET | `/api/user/quota` | 获取剩余打印次数 |
| POST | `/api/application/submit` | 提交申请（文件 + 签名上传 + 配额扣减） |
| GET | `/api/application/list` | 我的申请列表（可按状态筛选） |
| GET | `/api/application/detail/<id>` | 申请详情 |
| GET | `/api/admin/applications/pending` | 待审批列表（管理员） |
| GET | `/api/admin/applications` | 全部申请列表（管理员） |
| POST | `/api/admin/application/review` | 审批（通过/拒绝） |
| PUT | `/api/admin/application/status` | 更新打印状态 |

## 本地开发

### 后端

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # 按需修改
python app.py                                        # 默认 http://127.0.0.1:5000
```

> 默认 `CAS_MOCK=1`，无需真实教务系统即可跑通整条登录→提交→审批链路：
> CAS 登录任意非空密码可通过，返回模拟身份。

### 前端

```bash
cd frontend
npm install
npm run dev            # 默认 http://localhost:5173，已代理 /api、/uploads 到后端 5000
```

> 需先启动后端（`cd backend && python app.py`）。默认 `CAS_MOCK=1`，
> 打开 http://localhost:5173 输入任意学号（≥6 位）与任意密码即可登录联调。

## 进度

- [x] 模块 1：数据库建表 + Flask 后端（认证 / 申请 / 配额 / 管理员）+ 部署说明
- [x] 模块 2：Vue 3 + Vant 4 前端（登录 / 首页 / 申请 / 列表 / 详情 / 个人中心 / 管理员端）
- [x] 纯网页端改造：去除微信 H5/小程序依赖，改为教务系统 CAS 直接登录 + 前后端分离 + 响应式双端适配
- [ ] 模块 3（预留）：CAS 真实对接调优、反馈功能、验证码会话迁 Redis 等第二阶段能力
