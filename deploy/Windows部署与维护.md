# Windows 部署与后续维护指南

目标机同样是 Windows 时的完整部署步骤 + 上线后更新维护流程。

本项目已改造为「单端口服务整站」：Flask 的 5000 端口同时对外提供
**前端页面（frontend/dist）** + **/api 接口** + **/uploads 上传文件**。
因此 Windows 上无需 Nginx / IIS，只需 MySQL + waitress + Flask 即可。

---

## 一、部署到另一台 Windows 电脑

### 0. 前置条件

| 需安装 | 说明 |
| --- | --- |
| Python 3.10+ | python.org 下载，安装时勾选 **Add to PATH** |
| MySQL 8.0 | 官方安装器，装后启动 Windows 服务，记住 root 密码 |
| Node.js 18+（可选） | 仅当要在目标机上构建前端时需要；否则在开发机构建好只拷 dist |

### 1. 拷贝项目

把整个 `三维科创3D` 目录拷到目标机（如 `D:\hust3d`）。

**不要拷**（体积大或不应跨机复制）：
- `frontend\node_modules`
- `backend\.venv`
- `backend\__pycache__`、`backend\instance`
- `backend\.env`（目标机必须自己新建，密钥/库密码环境不同）

**要保留 / 迁移数据的额外拷**：
- `backend\uploads`（用户上传的 STL、签名、反馈照片），需要迁移历史数据时一并拷。

### 2. 初始化数据库

`schema.sql` 自带 `CREATE DATABASE`，全新机器直接导即可：

```bat
cd /d D:\hust3d\backend\sql
mysql -uroot -p < schema.sql
```

创建独立账号（别用 root 跑应用），进 MySQL 执行：

```sql
CREATE USER 'hust3d'@'localhost' IDENTIFIED BY '改成强密码';
GRANT ALL PRIVILEGES ON hust_3d.* TO 'hust3d'@'localhost';
FLUSH PRIVILEGES;
```

> 迁移历史数据：开发机 `mysqldump -uroot -p hust_3d > hust_3d.sql`，
> 拷过去后 `mysql -uroot -p hust_3d < hust_3d.sql`（此时不必再导 schema.sql）。

### 3. 后端依赖（注意用 Windows 专用清单）

```bat
cd /d D:\hust3d\backend
python -m venv .venv
.venv\Scripts\pip install -r requirements-win.txt
```

> ⚠️ 必须用 `requirements-win.txt`。原 `requirements.txt` 里的 gunicorn
> 依赖 fcntl，Windows 装不上，会直接报错。

### 4. 配置环境变量

```bat
copy .env.example .env
notepad .env
```

关键项：

```ini
SECRET_KEY=<随机值：python -c "import secrets;print(secrets.token_hex(32))">
JWT_SECRET=<随机值：同上再生成一个>
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=hust3d
DB_PASSWORD=你的数据库密码
DB_NAME=hust_3d
CAS_MOCK=0
ADMIN_STUDENT_IDS=2504060306
FRONTEND_URL=http://127.0.0.1:5000
```

> ⚠️ 教务系统 `jwzx.hrbust.edu.cn` 是校内系统，目标机必须能访问它，
> 否则真实登录失败。放校内网段的机器最稳妥。

### 5. 前端构建产物

后端会去读 `..\frontend\dist`，所以 `dist` 必须存在。

- 方式 A（目标机有 Node）：`cd frontend && npm install && npm run build`
- 方式 B（推荐）：在开发机 `npm run build`，把 `frontend\dist` 整个拷到
  目标机 `D:\hust3d\frontend\dist`

### 6. 启动

快速验证：

```bat
cd /d D:\hust3d\backend
.venv\Scripts\python app.py
```

浏览器打开 `http://127.0.0.1:5000` 出登录页、
`http://127.0.0.1:5000/api/health` 返回 `{"code":0,"msg":"ok"}` 即成功。

正式运行用 waitress：

```bat
.venv\Scripts\waitress-serve.exe --listen=0.0.0.0:5000 app:app
```

### 7. 让外部访问

- **局域网（同校园网）**：查 `ipconfig` 的 IPv4，别人访问 `http://<IP>:5000`；
  放行防火墙：
  `netsh advfirewall firewall add rule name="hust3d" dir=in action=allow protocol=TCP localport=5000`
- **外网（推荐）**：目标机装 cpolar 后 `cpolar.exe http 5000`，得
  `https://xxxxx.cpolar.top` 地址，任何人可访问，且无需开防火墙端口。

### 8. 开机自启（任务计划程序）

1. `Win+R` → `taskschd.msc`。
2. 新建任务：触发器「启动时」；操作「启动程序」：
   - 程序：`D:\hust3d\backend\.venv\Scripts\waitress-serve.exe`
   - 参数：`--listen=0.0.0.0:5000 app:app`
   - 起始于：`D:\hust3d\backend`
3. 勾选「不管用户是否登录都要运行」。
4. 确认 MySQL 已装成 Windows 服务且「自动」启动，否则后端可能起早连不上库。

---

## 二、后续更新 / 维护

### 更新总原则（改动类型 → 动作）

| 改了什么 | 需要做的 |
| --- | --- |
| 前端页面 / 样式 / 逻辑（frontend/src） | 重新 `npm run build`，然后**重启后端**（让它重新加载新 dist） |
| 后端代码（backend/*.py） | 替换对应 .py，然后**重启后端** |
| 数据库表结构（加字段/表） | 写迁移 SQL 并到目标机 `mysql -uroot -p hust_3d < 迁移文件.sql`，再重启后端 |
| 只有配置（.env） | 改完直接重启后端 |

### 1. 前端更新

```bat
cd /d D:\hust3d\frontend
npm run build
```

> 也可在开发机 build 好只拷 `dist` 过去，效果一样。

### 2. 后端更新

把改动的 `.py` 文件（或整个 backend 除了 `.venv`、`.env`、`uploads`）覆盖到目标机。

### 3. 重启后端（每次更新后必做）

waitress 不会自动加载新代码，必须手动重启：

```bat
:: 找到占用 5000 的 PID
netstat -ano | findstr :5000
:: 结束它（PID 换成上一步看到的数字，注意是最后一个 LISTENING 的 PID）
taskkill /F /PID <PID>
:: 重新启动
cd /d D:\hust3d\backend
.venv\Scripts\waitress-serve.exe --listen=0.0.0.0:5000 app:app
```

> 若配了任务计划程序自启，重启机器也会自动恢复，不必每次手动起。

### 4. 数据库变更（增列 / 建表）

以后加字段不要手改线上库，养成「写迁移文件 → 执行」的习惯。例如本项目反馈功能：

```sql
ALTER TABLE print_applications
  ADD COLUMN feedback_url VARCHAR(255) NULL COMMENT '反馈图片路径（实物图/现场照片）',
  ADD COLUMN feedback_at  DATETIME     NULL COMMENT '反馈时间';
```

保存为 `backend/sql/migration_xxx.sql`，目标机执行：

```bat
cd /d D:\hust3d\backend\sql
mysql -uroot -p hust_3d < migration_xxx.sql
```

> 加字段后要同步改 `backend/models.py` 和 `schema.sql`（保持三者一致）。

### 5. 数据备份（强烈建议定期做）

- **数据库**：`mysqldump -uroot -p --single-transaction hust_3d > 备份_日期.sql`
- **上传文件**：整个 `backend\uploads` 目录（STL、签名、反馈照片都在里面）
- 建议用任务计划程序每天跑一次 dump，并保留多份。

### 6. 建议：从「拷贝文件」改成 git

现在没有 git 的话，每次更新是靠覆盖文件，容易漏。强烈建议初始化一个仓库：

```bat
:: 开发机（一次）
git init
:: 写好 .gitignore：确保 .env、.venv、node_modules、__pycache__、instance、uploads 都被排除
git add . && git commit -m "init"
```

目标机更新就变成：

```bat
git pull
cd frontend && npm run build
:: 重启后端
```

这样代码更新可追溯、可回滚，比手拷可靠得多。

---

## 三、上线检查清单

- [ ] `.env` 的 `SECRET_KEY`/`JWT_SECRET` 已随机化
- [ ] 用 `requirements-win.txt` 装的依赖（waitress）
- [ ] `CAS_MOCK=0`、`ADMIN_STUDENT_IDS` 正确
- [ ] 目标机能访问 `jwzx.hrbust.edu.cn`
- [ ] `frontend\dist` 为最新构建
- [ ] uploads 目录可写
- [ ] 防火墙 5000 已放行（局域网直连）或用 cpolar（外网）
- [ ] 外网访问一律 `https://`，密码登录不走 http 明文