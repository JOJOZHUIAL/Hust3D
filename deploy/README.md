# 部署上线步骤

> 只想在**本机快速让外部访问**（无需云服务器/域名），请看
> [内网穿透部署.md](./内网穿透部署.md)。

本文按「云服务器 + Nginx」描述第一阶段纯网页端（前后端分离）的部署流程。
后端 Flask，前端 Vue 3 构建产物。

## 目录约定

| 路径 | 说明 |
| --- | --- |
| `/opt/hust3d/backend` | 后端代码 |
| `/opt/hust3d/backend/uploads` | 上传文件（STL、签名） |
| `/var/www/hust3d/dist` | 前端构建产物 |
| `/etc/nginx/sites-available/hust3d.conf` | Nginx 配置 |

---

## 1. 服务器环境准备

```bash
# 安装 MySQL 8.0、Python 3.10+、Node.js 18+、Nginx
sudo apt update
sudo apt install -y mysql-server python3 python3-venv python3-pip nginx git

# 如需 Node（前端构建），用 nvm 或官方安装脚本
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs
```

## 2. 数据库初始化

```bash
# 用 MySQL root 登录后导入建表脚本
mysql -uroot -p < backend/sql/schema.sql

# 建议创建独立数据库账号（不要用 root 跑应用）
mysql -uroot -p
CREATE USER 'hust3d'@'localhost' IDENTIFIED BY '你的密码';
GRANT ALL PRIVILEGES ON hust_3d.* TO 'hust3d'@'localhost';
FLUSH PRIVILEGES;
```

## 3. 后端部署

```bash
cd /opt/hust3d/backend

# 创建虚拟环境并安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 配置环境变量：复制 .env.example 为 .env 并填写真实值
cp .env.example .env
# 编辑 .env：数据库账号、CAS 教务系统配置等

# 用 gunicorn 启动（systemd 托管，见下）
gunicorn -w 4 -b 127.0.0.1:5000 app:app
```

用 systemd 托管，让后端开机自启、异常重启。新建
`/etc/systemd/system/hust3d.service`：

```ini
[Unit]
Description=HUST 3D Printing Backend
After=network.target mysql.service

[Service]
User=www-data
WorkingDirectory=/opt/hust3d/backend
EnvironmentFile=/opt/hust3d/backend/.env
ExecStart=/opt/hust3d/backend/.venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now hust3d
```

## 4. 前端部署

```bash
cd frontend
npm install
npm run build          # 产出 dist/
sudo mkdir -p /var/www/hust3d
sudo cp -r dist /var/www/hust3d/dist
```

> 静态资源缓存：前端打包时对资源加版本号（vite 默认 hash 文件名），配合
> Nginx 的长缓存规则即可，发版后客户端能及时拉取最新资源。

## 5. Nginx 配置

```bash
# 把 deploy/nginx.conf 复制为站点配置，并按实际域名/路径修改
sudo cp deploy/nginx.conf /etc/nginx/sites-available/hust3d.conf
sudo ln -s /etc/nginx/sites-available/hust3d.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## 6. 域名与 HTTPS

1. 域名解析：把 `3d.example.com` A 记录指向服务器公网 IP。
2. 申请证书（Let's Encrypt）：

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d 3d.example.com
```

certbot 会自动改 Nginx 配置并续期。

## 7. 教务系统 CAS 对接

登录走学校教务系统统一认证（学号 + 密码 + 图形验证码），无需任何微信相关配置。
在 `.env` 中按需调整：

- `CAS_MOCK`：本地联调设为 `1`（任意非空密码通过）；上线接入真实教务系统时设为 `0`。
- `CAS_INFO_URL`：学籍信息页地址，用于登录后解析姓名、院系；如学校页面结构变化需同步更新 `services/cas.py`。
- `ADMIN_STUDENT_IDS`：管理员学号列表（逗号分隔），登录时自动授予 `admin` 角色。

> 验证码会话当前存于进程内存，多 worker（`gunicorn -w 4`）部署时需迁移到 Redis，
> 否则验证码可能因请求落到不同 worker 而校验失败。

## 8. 上线前检查清单

- [ ] `.env` 中 `SECRET_KEY`、`JWT_SECRET` 已改为随机值
- [ ] `CAS_MOCK=0`（接入真实教务系统后）
- [ ] `ADMIN_STUDENT_IDS` 已配置正确的管理员学号
- [ ] `FRONTEND_URL` 指向正式域名
- [ ] 上传目录 `backend/uploads` 有写权限（systemd 的 User 可写）
- [ ] Nginx `client_max_body_size` ≥ 50MB
- [ ] 已启用 HTTPS（密码传输必须加密）
