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

## 取件短信通知（SmsForwarder）

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
