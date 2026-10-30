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
| POST | `/api/application/withdraw/<id>` | 撤回申请（仅待审批；删除记录与文件并返还打印次数） |
| GET | `/api/application/todos` | 首页「待完成」清单：待取件 + 待反馈 |
| POST | `/api/application/pickup/<id>` | 学生自助标记已领取 |
| POST | `/api/admin/application/send-sms/<id>` | 手动（重发）取件短信给申请人（管理员） |
| GET | `/api/admin/sms/config` | 短信网关配置（脱敏，管理员） |
| POST | `/api/admin/sms/test` | 给指定手机号发测试短信（管理员） |
| GET | `/api/admin/applications/pending` | 待审批列表（管理员） |
| GET | `/api/admin/applications` | 全部申请列表（管理员，可用 `?status=` 筛选，含 `printing` / `expired`） |
| POST | `/api/admin/application/review` | 审批（通过/拒绝；拒绝返还打印次数） |
| PUT | `/api/admin/application/status` | 更新打印状态（`printing` 时用 `printer_id` 绑定打印机；记录打印操作人） |
| GET | `/api/printer/list` | 打印机清单（含实时状态与正在打印的申请） |
| GET | `/api/printer/<id>/status` | 单台打印机实时状态（含绑定申请的文件名与进度） |
| GET | `/api/notification/pickup` | 待确认的取件提醒（首页弹窗数据，含申请编号/文件名/完成时间） |
| POST | `/api/notification/pickup/ack` | 确认取件提醒（传 `ids` 只确认指定条目，不传则全部确认） |
| GET | `/api/app/latest` | 最新 App 版本（客户端检查更新用，登录即可查） |
| GET/POST | `/api/app/releases` | 发布历史 / 上传新 APK（仅管理员，multipart） |
| DELETE | `/api/app/releases/<id>` | 删除某次发布（仅管理员，同时删除 APK 文件） |
| GET | `/api/admin/applications/export` | 批量导出申请表（管理员，`start`/`end` 按提交时间筛，返回 ZIP，每个申请一个 Word） |

## 打印流程与次数规则

- **审批人留痕**：审批时保存 `reviewer_id` + 姓名/学号快照，详情页与时间线展示「审批人」。
- **打印人留痕**：管理员点「开始打印」时保存 `printed_by_id` + 姓名/学号快照。
- **次数扣减/返还**：提交申请扣 1 次；申请被拒绝、或在待审批阶段被本人撤回，均自动返还 1 次（不消耗打印次数）。
- **反馈有效期**：打印完成（`completed_at`）后 `FEEDBACK_EXPIRE_DAYS`（默认 7）天内未提交反馈，
  申请会被**标记为「已过期」**（写 `expired_at`）—— 注意状态**仍然是「已完成」**，
  只是此后不能再提交反馈、不再发放反馈奖励；列表与详情上显示「已完成」+「已过期」两个标签，
  详情页的反馈上传入口也会隐藏。
  未引入定时任务依赖，采用「读取列表/详情时惰性扫描并落库」实现。
- **审批管理分组**：待审批 / 待打印 / **正在打印** / 打印完成 / 未反馈 / **已过期**
  （= 已完成且反馈超时）/ 已反馈 / 全部申请；`?status=expired` 是伪状态筛选条件。

## 打印机绑定与「进度 100% 自动完成」

点「开始打印」时会先选择打印机，把该申请**指派**给这台打印机（`printer_id` / `printer_name`、
`printed_at`、`printed_by_*`）。但指派 ≠ 正在打印 —— 打印机当时很可能还在打别的文件，所以
进度与自动完成都按打印机**上报的真实文件名**来判定：

1. 从打印机上报的 `subtask_name` / `gcode_file` 里提取**所有**申请编号
   （拓竹的打印文件名形如 `丘馗HUST3D20261017005.stl`，即「姓名+申请编号」；
   一盘放多件时会用 `+` 拼起来，如
   `丘馗HUST3D20261017005 + 毛雨涵HUST3D20261017006 + 蒋昱昊HUST3D20261017007.stl`）；
2. 本申请的 `apply_no` 出现在这批编号里，才算"这台打印机正在打本申请"（`print_matched=1`），
   这时才回写 `print_state` / `print_progress`、才认可"已开始打印"、才会在 100% 时自动完成；
   **一盘多件时，盘里每份申请都会被同时跟踪、同时完成**；
3. 打印机在打别的文件、或文件名里没有申请编号时：不记进度（`print_progress=None`）、
   不判开始、**绝不自动完成**，界面显示打印机真实在打什么（`print_actual_file`）。

> 同一台打印机允许指派多个申请（一盘多件时它们会一起打印），是否真的在打某一单完全由
> 监视器按文件名判定，不再用"打印机已被占用"来拦截。

打印机状态页（`/admin/printers`、`/admin/printers/:id`）区分两件事：

- **打印机正在打印的申请** —— 按文件名匹配到的那一盘，列出盘里每一份申请（真实进度、
  到 100% 自动完成）；
- **已指派、等待开始打印** —— 管理员指派到本机、但打印机还没开始打它们的申请。

完成动作用「带 `status='printing'` 条件的批量更新」，`gunicorn -w 4` 多进程部署时不会重复完成、
重复通知；指派错了可以在申请详情里「更换打印机 / 重新指派」。

> 拓竹打印机只能打印切片后的 `.gcode.3mf`，不能直打 `.stl`；切片与开始打印仍由管理员在
> Bambu Studio 中操作。想让系统自动识别，**打印时保留系统下载的文件名（姓名+申请编号）**即可；
> 若是多模型拼盘或自己改了名，文件名里没有申请编号，就只能用「标记完成」人工处理。
> 可用 `PRINT_WATCH_ENABLED=0` 关闭自动完成。

## 首页取件弹窗

打印完成（自动或人工标记）时会给申请人发一条 `ntype=pickup` 的取件提醒：

- 学生打开首页（`/`）时自动检查，有待取件的申请就弹出「打印完成，请取件」弹窗，
  列出申请编号、STL 文件名、完成时间；进入首页后每 30 秒再查一次，打印刚完成时无需手动刷新；
- 弹窗三个动作：**去查看**（跳到申请详情）、**稍后提醒**（本次不再弹，下次进首页再提醒）、
  **我知道了，不再提醒**（把该提醒标记已读，之后不再弹）；
- 只针对「已完成且未领取」的申请；已领取 / 已取消 / 状态变化的提醒会被自动标记已读清理，
  不会出现关不掉的弹窗；
- 管理员「标记完成」时如果同时勾了「已领取」，则不发取件提醒（改发一条普通完成通知）。

未读数、消息中心、App 内的系统横幅通知与这套取件提醒共用同一份通知数据，互不冲突。

## 首页「待完成」模块

学生首页在「最新通知」上方新增 **待完成** 清单（同一屏内可滚动），把还需要用户动手的事项列出来：

| 类型 | 何时出现 | 行内按钮 | 点击后 |
| --- | --- | --- | --- |
| **待取件** | 申请已完成、还没标记领取（`picked_up=0`） | 已领取 | 写 `picked_up=1` + 领取时间，该条消失（取件弹窗也不再提醒） |
| **待反馈** | 申请已完成、未上传反馈、且未过期 | 上传反馈图 | 直接弹出文件选择，选中即上传到该申请，成功后该条消失并奖励次数 |

- 同一份申请如果既没取件也没反馈，会各出现一条（两条待办彼此独立）；
- 已过期的申请**只催取件、不催反馈**（反馈入口已关闭）；
- 右上角红色数字 = 当前待完成条数；进入首页拉取一次，之后每 30 秒刷新；
- **没有待办时整块隐藏**（不显示空列表），有新的待取件/待反馈出现时自动出现在首页；
- 快捷入口的「提交反馈」图标红点数字 = 其中待反馈的条数，点开弹窗也列出同一批待反馈项；
- 数据接口：`GET /api/application/todos`（返回 `count` / `pickup_count` / `feedback_count` / `items`），
  标记领取：`POST /api/application/pickup/<id>`，上传反馈沿用 `POST /api/application/feedback/<id>`。

> 管理员首页不显示该模块，反馈与审批在「审批管理」里处理。

## App 版本更新（APK）

以前每次网页改动都要重新打包 APK 并手动传给人装；现在只要在后台发布一次，已装的 App 下次启动就会提示更新。

**打包**：双击 `build_apk.bat`（内部 `build_apk.py`）。脚本会自动把
`android/app/build.gradle` 的 `versionCode` **+1**、`versionName` 改成 `1.<新code>`，
并在结束时打印本次版本号 —— 上传时按它填即可。

**发布**：管理后台 → **应用更新**（仅管理员）：

1. 填「版本号」（= versionCode，必填且必须比线上最新的大）、「版本名称」、「更新说明』（会显示在弹窗里）；
2. 选择 `.apk`（上限 300MB）→ 上传并发布；
3. 下方可查看/删除历史版本（删除会同时删掉服务器上的 APK 文件）。

**客户端检查**：App 启动时（仅原生环境、且已配置服务器地址）调用 `GET /api/app/latest`，
用 `@capacitor/app` 的 `getInfo().build`（已安装的 versionCode）与服务器的 `version_code` 比较，
**服务器更大就弹「发现新版本」弹窗**：可选「立即更新 / 稍后」——
点「立即更新」会把 APK 下载地址交给系统浏览器下载安装。

> ⚠️ 重要：**当前手机上已安装的旧 APK 里没有这段检查代码**，所以需要先手动装一次包含本功能的
> 版本（versionCode ≥ 2）；从这以后就能靠弹窗提示更新了。

## 公共管理员账号（工作室共用）

工作室的电脑上大家共用一个登录账号，但操作记录必须能追溯到具体的人。

| 项 | 说明 |
| --- | --- |
| 账号 / 密码 | `admin` / `hust3d123456`（`.env` 的 `PUBLIC_ADMIN_USERNAME` / `PUBLIC_ADMIN_PASSWORD` 可改） |
| 权限 | 与普通管理员**完全一致**（不能管理管理员，那是超管权限） |
| 登录 | 登录页直接把学号填 `admin`，密码填上面的密码，**不需要教务系统验证码** |
| 操作人登记 | 审批申请、审核反馈、开始打印、拆封耗材时，**必须填写实际操作人学号**；系统按学号找到对应账号，把这次操作记到本人名下（审批人 / 打印人 / 拆封人），操作日志里也会带「公共账号操作，操作人：XXX」 |
| 学号要求 | 该学号必须已经登录过一次系统（否则没有账号）；找不到会提示「请让对方先登录一次系统」 |

> 普通管理员 / 超管账号不受影响，直接以自己的身份记录，不会弹操作人输入框。

## 反馈规则

| 规则 | 说明 |
| --- | --- |
| 谁能反馈 | **所有已完成**的申请都能上传反馈图，**已过期也可以补交** |
| 过期补交 | **仍然需要管理员审核**（会进入待审核队列），审核通过也**不发放奖励** |
| 是否奖励 | 每单**只发一次**（`feedback_rewarded` 保证）；过期补交一律 0 次 |
| 多张图片 | 一次可选多张（最多 9 张/次），存在 `application_feedback_images` 表；`feedback_url` 只存第一张作封面 |
| 追加/重传 | 不满意可以再次上传，**图片累加不覆盖**，也不会重复加打印次数 |
| 管理员拒绝 | 拒绝会清空该单的所有反馈图，回到「未反馈」状态，学生可重新上传 |
| 预计反馈时间 | 申请表单可选填「计划何时交反馈」，同时提示「打印完成后 N 天内为正常反馈期」 |
| 过期判定 | `FEEDBACK_EXPIRE_DAYS`（默认 7，0=关闭）。**改这个值重启后会自动重算历史数据**：放宽会撤销过期标记，收紧会补标 |

## 消息通知（短信 + 邮件，一个板块）

原来的「短信通知」「短信网关」两个入口已合并为 **管理后台 → 消息通知**（`/admin/notify`）。
界面是主平台自己的 Vue3 页面：**右侧竖排菜单（收件/发送/状态/设置），内容显示在左侧**。

### 1. 后端分层

| 层 | 文件 | 说明 |
| --- | --- | --- |
| 硬件通信 | `backend/vendor/sms_hub/core/`（原样，MIT） | ESP32 心跳 `/hook`、收发队列、SIM 管理 |
| 数据读取 | `backend/services/native_sms.py` | **直接 SELECT** `sms.db` 的 messages/outbound/devices/sims/contacts |
| 发送 | 同上 → `sms_hub.send_text()` | 进程内 `enqueue_sms`，零 HTTP |
| 接口 | `backend/blueprints/native_sms.py` | 6 个端点，管理员鉴权 |
| 界面 | `frontend/src/views/admin/AdminNotify.vue` | Vue3 + Vant 原生页面 |

### 2. 六个接口

```
GET  /api/admin/native-sms/status     设备在线 / 信号 / 号码 / 自动识别的卡 / 两个开关
GET  /api/admin/native-sms/messages   收件箱（?keyword= 搜联系人/内容/备注）
GET  /api/admin/native-sms/outbound   发送记录
POST /api/admin/native-sms/send       发送短信
GET  /api/admin/native-sms/settings   自动短信 / 自动邮件开关
PUT  /api/admin/native-sms/settings   保存开关
```

### 3. 状态页（设备全量信息 + 固件日志）

「状态」标签页展示设备自报的全部信息，并支持直接拉固件日志：

| 区块 | 内容 |
| --- | --- |
| 状态卡 | 在线/离线、信号格、SIM 号码、最后见到时间 |
| 自动识别到的卡 | 每张卡的号码、运营商、在用/未接入 |
| 设备与网络 | MAC、IP、固件版本、模组型号、注册状态、信号 dBm、运营商、IMSI/ICCID 尾号、数据连接、WiFi SSID+信号、运行时长、可用内存、复位原因 |
| 同步与收发 | 本地已收/已发、设备 rx/tx、游标、设备缓冲占用、上次拉取、上次上报 |
| 固件日志 | 增量拉取设备日志（含 `[webhook] 连接失败` 这类历史误报可以直接看到），带「强制拉取」按钮 |

后端接口：`GET /native-sms/log?since=`、`POST /native-sms/pull`
（都是通过内嵌 DeviceManager 的 `rt.fetch_log()` / `poller.poll_device()` 调内核，不走 HTTP 中转）。

### 4. 自动识别卡（不再手动加网关）

插在设备上的卡由固件上报，平台读 `sims` 表就能列出来：

- `current_device_mac` = 在线设备 → 标记 **在用**（绿）
- 其它 启用卡 → 标记 **未接入**
- 号码优先取 `sims.msisdn`（`+8613362648430` → `133 6264 8430`），没有就用模组上报的号码
- 运营商代码中文化（CHINA MOBILE → 中国移动）

**没有任何「添加网关 / 通知渠道」的入口了** —— 插卡即识别。

### 5. 收件箱

- 搜索框同时匹配 **发送人号码、发送人备注、正文**
- 备注来源：`contacts.alias` 优先，其次主平台 `users.name`（按手机号关联，学生回复短信时能直接看到是谁）
- 每行显示 备注/号码、时间、正文；有验证码时自动识别（4~8 位，优先 6 位、优先靠前）并提示「点我复制」

### 6. 发送 + 发送记录

发送框填手机号 + 内容（实时校验 `^1\d{10}$`），走内部函数入队；
下方「发送记录」读 `outbound` 表：号码、状态（已发送/发送中/失败）、时间、正文、失败原因。

### 7. 发送模板（短信 + 邮件）

「设置」里可以直接编辑两种模板，保存写回 `.env` 并**立即生效**：

| 配置项 | 内容 |
| --- | --- |
| `NOTIFY_SMS_TEMPLATE` | 取件短信正文 |
| `NOTIFY_EMAIL_SUBJECT` | 邮件主题 |
| `NOTIFY_EMAIL_TEMPLATE` | 邮件正文（可多行） |

可用占位符：`{name}` `{apply_no}` `{file_name}` `{printer}` `{deadline}`

默认邮件正文：

```
{name} 同学：

你提交的申请（{apply_no}）已打印完成，请携带校园卡到创新创业协会工作室领取。

领取后欢迎上传实物图反馈，成功可奖励 1 次打印机会。

理工智造共享平台 · 大学生创新创业协会
```

> `.env` 是单行格式，所以多行正文在文件里存成字面量 `\n`，读取时还原成换行；
> 页面上正常换行编辑即可，无需关心转义。

### 8. 两个自动开关

「设置」里只有两个开关，保存后写回 `.env` 并**立即生效**：

| 开关 | 配置项 | 作用 |
| --- | --- | --- |
| 自动短信 | `NOTIFY_AUTO_SMS` | 打印完成时自动给申请人发取件短信 |
| 自动邮件 | `NOTIFY_AUTO_EMAIL` | 打印完成时自动发邮件（SMTP 配好才生效） |

> 邮件开关默认在 `.env` 里设成 `0`（之前退信较多），需要时在页面打开即可。

## 邮件通知与防退信

打印完成 / 审核结果 / 打印失败等事件会发邮件（`.env` 里配 `SMTP_*`）。之前退信爆炸的三个原因
和对应修复：

| 问题 | 修复 |
| --- | --- |
| 收件人是 `student@example.com` 这类占位地址（No MX Record Found） | `mailer.is_deliverable_address()` 直接跳过占位/内网域名（example.com、test.local、*.local 等） |
| 域名拼错或不存在，发出去必然退信 | 域名 MX/解析预检（带 6 小时缓存），查不到就不发 |
| 同一个坏地址每次事件都重发 | 连续失败 3 次自动拉黑 24 小时（`MAIL_MAX_FAILS` / `MAIL_BLOCK_HOURS`） |
| 退信里时间显示 `1970-01-01`（缺 Date 头，被判畸形邮件） | 补齐 `Date` / `Message-ID` / `MIME-Version` |
| 一次事件群发太多封 | 全局限流 `MAIL_RATE_PER_MIN`（默认 20 封/分钟） |

```ini
MAIL_CHECK_MX=1          # 域名可收信预检
MAIL_MAX_FAILS=3         # 连续失败几次拉黑
MAIL_BLOCK_HOURS=24
MAIL_RATE_PER_MIN=20
```

## 取件短信通知（sms-hub · ESP32C3 + 4G 模组）

> 早期用手机上的 SmsForwarder 代发（见下方「历史方案」），现已换成自建硬件网关 **sms-hub**：
> ESP32C3 + ML307R 4G 模组，局域网跑 FastAPI，`http://192.168.1.150:8025`。

### 1. 协议（已按源码确认，不是 `/hook/*`）

| 步骤 | 请求 |
| --- | --- |
| 取令牌 | `POST {base}/api/login` `{"user":"admin","password":"<WEBUI_PASS>"}` → `{"token":"..."}` |
| 发短信 | `POST {base}/api/send`，Header `Authorization: Bearer <token>`，body `{"sim_id":"...","to":"13x...","text":"..."}` → `{"ok":true,"queued":true,"id":12,"parts":1}` |
| 查记录 | `GET {base}/api/outbound?limit=20` |

> ⚠️ `/hook/{DEVICE_TOKEN}` 是 **ESP32 固件上报**用的 webhook，不能用来发短信（会 400/404）。
> `sim_id` 不传时 Hub 会自动推断；但如果有多张卡，必须显式指定 —— 我们的客户端会自动挑
> 「已绑定在线设备」的那张卡。

### 2. 配置

```ini
SMS_ENABLED=1
SMS_PROVIDER=smshub
SMSHUB_BASE_URL=http://192.168.1.150:8025
SMSHUB_USER=admin
SMSHUB_PASSWORD=hust3d123456     # = sms-hub 的 WEBUI_PASS
SMSHUB_SIM_ID=                   # 留空自动挑卡
SMSHUB_TIMEOUT=10
SMSHUB_RETRIES=3                 # 网络抖动重试（1s/2s/4s 退避）
```

### 3. 业务调用

打印完成（打印机 100% 自动完成 / 管理员点「标记完成」）→ `services/sms.py` 的
`notify_pickup_sms()` 写入 `sms_messages` 队列 → 后台线程调 `services/sms_hub.py`。

也可以直接调封装好的函数：

```python
from services.sms_hub import send_3d_print_notification

send_3d_print_notification("15718160158", "机械臂底座.stl", "HUST3D20261026001")
# 正文：您好，您的3D打印件（机械臂底座.stl）已打印完成，请取件。取件号：HUST3D20261026001。
```

失败会抛 `SmsHubError`；`retryable=True` 表示网络类问题（会自动重试 3 次）。

## 历史方案：SmsForwarder（已停用）

打印完成时（不管是打印机进度 100% 自动完成，还是管理员手动「标记完成」），服务器会自动给
申请人填写的手机号发一条取件短信。服务器本身不发短信，而是把请求交给一台装了
**SmsForwarder（短信转发器）** 的安卓手机代发，手机走自己的 SIM 卡，费用按运营商短信计费。

### 1. 手机端：开启「主动控制」

1. 在带 SIM 卡的安卓手机上安装 SmsForwarder，授予短信、后台常驻等权限；
2. 打开 App 里的 **「主动控制」/「远程控制」→ HttpServer**（不同版本菜单位置略有差异），
   记下 **监听端口** 和 **token**，并保持 App 在后台常驻（建议加电池优化白名单）；
3. 该页面通常会给出一个示例请求地址，把它改写成带占位符的模板。

### 2. 服务器端：`.env` 配置

短信通道有两种模式，按手机端接口的样子选：

**A. 通用 URL 参数模板**（`SMS_PROVIDER=template`，默认）

```ini
SMS_ENABLED=1
# {phone} 手机号、{msg} 正文、{token} 令牌 会被 URL 编码后代入
SMS_GATEWAY_URL=http://192.168.1.50:8080/send_sms?token={token}&phone={phone}&msg={msg}
SMS_GATEWAY_METHOD=GET
SMS_GATEWAY_TOKEN=你在App里设置的token
SMS_GATEWAY_TIMEOUT=8
SMS_TEMPLATE=【3D打印服务】{name}同学，您的打印件（{apply_no}）已打印完成，请携带校园卡到3D打印工作室领取。
```

**B. SmsForwarder「主动控制」**（`SMS_PROVIDER=json`）— 已实测可用

手机端：`主动控制服务端` → 记下 **HttpServer 端口**（默认 5000）/ 安全措施选 **不需要** / 打开 **远程发短信**。

```ini
SMS_ENABLED=1
SMS_PROVIDER=json
SMS_GATEWAY_URL=http://192.168.1.129:5000/sms/send
# 第二个监听窗口（多台手机/多个地址，按顺序挑第一个可用的）
SMS_GATEWAY_URL_2=http://192.168.1.130:5000/sms/send
SMS_JSON_TEMPLATE={"data":{"sim_slot":1,"phone_numbers":"{phone}","msg_content":"{msg}"}}
SMS_GATEWAY_TIMEOUT=15
SMS_TEMPLATE=【3D打印服务】{name}同学，您的打印件（{apply_no}）已打印完成，请携带校园卡到3D打印工作室领取。
```

**多个监听窗口**：`SMS_GATEWAY_URL`、`SMS_GATEWAY_URL_2` … `SMS_GATEWAY_URL_9`
（同一变量里用换行或 `;` 分隔也行）。发送时按书写顺序逐个尝试，**谁在线用谁**；
全部离线才进队列等重试。管理端「短信通知」页会把每个窗口的在线状态列出来。

报文格式取自其源码 `server/model/SmsSendData.kt` 与 `server/controller/SmsController.kt`：

| 字段 | 含义 |
| --- | --- |
| `sim_slot` | **1 = SIM1，2 = SIM2**（必须是实际插卡的槽位；填 0 会数组越界，请求直接挂死不返回） |
| `phone_numbers` | 手机号（字符串） |
| `msg_content` | 短信正文 |
| 外层 `data` | 即 `BaseRequest<T>{data, timestamp, sign}`，安全措施为「不需要」时 timestamp/sign 可省 |

> 实测返回 `{"code":200,"msg":"success","data":"success"}`；若手机没给发短信权限，它会返回一句提示（HTTP 200），
> 服务端已识别这种情况并按失败记录。

### 3. 验证

```bash
# 先确认服务器能连到手机（同一局域网 / 端口可达）
curl "http://192.168.1.50:8080/send_sms?token=你的token&phone=13800000000&msg=test"
```

登录管理后台 → 打开某条**已完成**的申请详情 → 「取件短信」卡片：
- 点 **测试网关**：给该申请人手机号发一条测试短信，立刻能看到成功/失败原因；
- 点 **发送取件短信**：正式（重新）发送，结果写入 `sms_sent_at` / `sms_result`。

### 4. 行为说明

- 只在申请进入「已完成」时自动发送，**同一申请只自动发一次**（已有 `sms_sent_at` 就跳过），失败可在详情页手动重发；
- 走后台线程发送，**不会拖慢**「标记完成」接口和打印机监视线程；
- 申请人手机号取 `users.phone`（提交申请时会同步更新）；没填或格式不对则跳过并记录；
- **手机网关不在线也不会丢消息**：所有短信先写入 `sms_messages` 表，立即尝试发送；
  连不上网关就留在 `pending`，后台线程每 `SMS_RETRY_INTERVAL`（默认 60 秒）按 1/3/5/10/20/30/60 分钟退避重试，
  手机回到局域网后自动补发。配置错误、号码错误这类不可恢复的失败直接标记 `failed`，不浪费重试。
- 手机不在服务器可达的网络里（比如服务器在云上、手机用 4G）就发不出去 —— 需要让手机和服务器在同一局域网，
  或给手机做内网穿透。

### 5. 管理端「短信通知」

管理后台 → 短信通知（`/admin/sms`）：

- 顶部显示网关状态（在线/离线）与**待发送条数**；
- **右上角「+」可以添加/删除监听窗口**（多台手机的短信网关）：新窗口直接写回 `.env`
  （`SMS_GATEWAY_URL`、`SMS_GATEWAY_URL_2`…）并**立即生效**，不需要重启后端；
- 可自定义填手机号 + 内容发送（网关离线时自动进队列，恢复后补发）；
- 下方是全部发送记录，可按 **全部 / 待发送 / 已发送 / 失败** 过滤，每条可**重发**或**删除**；
- 申请详情页的「取件短信」卡片仍可单独重发某单的取件短信。

接口：`GET/POST/DELETE /api/admin/sms/gateways`、`GET /api/admin/sms/messages`、
`POST /api/admin/sms/send`、`POST /api/admin/sms/messages/<id>/retry`、
`DELETE /api/admin/sms/messages/<id>`、`GET /api/admin/sms/status`。


## 批量导出申请表（管理员）

入口在 **管理后台 → 审批管理** 页面右上角的「导出」小按钮：

- 可选时间范围（本月 / 上月 / 近七天 / 近30天 / 全部 / 日历自定义），按**申请提交时间**筛选，
  面板上实时显示该范围内的份数；
- 导出为一个 **ZIP 压缩包**，解压后**每个申请一个独立 Word**（不是把所有申请塞进一个文档），
  文件名形如 `张三HUST3D20261017001.docx`，内容为官方版式申请表；
- 单次上限 300 份；没有数据时给出提示而不会下载空包；操作写入操作日志。

> 学生端「我的申请」不再提供批量导出（避免与管理员出口重复），单个申请仍可在详情页
> 「导出申请表（Word）」下载。

## 管理员管理（学号与配置文件同步）

登录时角色是按 `.env` 里的清单重新判定的（数据库 `role` 只是缓存）：

```
ADMIN_STUDENT_IDS=2504060306,...        # 管理员
SUPER_ADMIN_STUDENT_IDS=2504060306      # 超级管理员（只能在配置文件里维护）
```

所以在管理后台「管理员管理」里**设为管理员 / 移除管理员**时，后端会同时：

1. 修改数据库里的 `role`；
2. 把该学号写入/移出 `.env` 的 `ADMIN_STUDENT_IDS`（只改这一行，注释与其它变量原样保留，
   先写临时文件再原子替换）；
3. 同步更新当前进程内存里的清单，**无需重启**即生效。

写文件失败时不会只改一半：接口直接报错、数据库角色保持不变；数据库提交失败时会把配置文件回滚。
超级管理员的学号受保护，接口不允许通过这个入口修改。

> 注意：如果用 `gunicorn -w N` 多进程部署，改动只会同步到处理该请求的 worker 的内存，
> 其它 worker 要重启后才生效（配置文件本身已更新，重启即一致）。


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
