# -*- coding: utf-8 -*-
"""全局配置。

敏感信息（数据库密码、密钥等）一律从环境变量 / 同目录 .env 文件读取，
不要硬编码到代码里，更不要提交到版本库（已在 .gitignore 中排除 .env）。
"""
import os
from dotenv import load_dotenv

# 读取同目录 .env（若存在）；生产环境也可直接 export 环境变量
load_dotenv()

# 项目根目录（backend/ 所在位置）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    # —— 安全密钥（生产环境务必修改为随机值） ——
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    JWT_SECRET = os.getenv("JWT_SECRET", "dev-jwt-change-me")
    # 登录态有效期（秒），默认 7 天
    JWT_EXPIRES = int(os.getenv("JWT_EXPIRES", str(7 * 24 * 3600)))

    # —— 数据库 ——
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "hust_3d")
    # 支持 DATABASE_URL 整体覆盖（便于本地用 SQLite 跑冒烟测试 / CI），
    # 未设置时默认用 MySQL（pymysql）。
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 3600}

    # —— 文件上传 ——
    # 上传根目录：STL 文件、签名图片均存于此，路径以相对路径落库
    UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
    MAX_STL_SIZE = 50 * 1024 * 1024  # 50MB

    # —— 教务系统（jwzx.hrbust.edu.cn，Acegi 登录 + 图形验证码） ——
    # 本地开发开关：为 1 时不连学校系统，仅做格式校验
    CAS_MOCK = os.getenv("CAS_MOCK", "1") == "1"
    # ⚠️ 学校系统为 HTTP 明文，密码在「我方服务器 → 学校」链路上明文传输，属学校侧现状
    CAS_BASE_URL = os.getenv("CAS_BASE_URL", "http://jwzx.hrbust.edu.cn")
    # 建立会话用的首页（拿到 JSESSIONID）
    CAS_HOMEPAGE_URL = os.getenv("CAS_HOMEPAGE_URL", "/homepage/index.do")
    # 验证码图片地址
    CAS_CAPTCHA_URL = os.getenv("CAS_CAPTCHA_URL", "/academic/getCaptcha.do")
    # 登录提交地址（Acegi 统一认证）
    CAS_LOGIN_URL = os.getenv("CAS_LOGIN_URL", "/academic/j_acegi_security_check")
    # 登录成功后用于抓取姓名/学院的页面：学籍信息（<th>标签</th><td>值</td> 结构）
    CAS_INFO_URL = os.getenv("CAS_INFO_URL", "/academic/accessModule.do?moduleId=2060&groupId=")
    # 调试开关：为 1 时登录后打印学籍页的字段标签名（仅标签、不含值），用于定位学院字段
    CAS_DEBUG = os.getenv("CAS_DEBUG", "0") == "1"

    # —— 业务 ——
    DEFAULT_QUOTA = int(os.getenv("DEFAULT_QUOTA", "2"))  # 每学期默认打印次数
    # 管理员学号清单（逗号分隔），命中即视为管理员角色
    ADMIN_STUDENT_IDS = [s.strip() for s in os.getenv("ADMIN_STUDENT_IDS", "").split(",") if s.strip()]

    # —— 站点 ——
    # 前端地址，用于部署 / CORS 等场景（纯网页端，前端与后端分离部署）
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
