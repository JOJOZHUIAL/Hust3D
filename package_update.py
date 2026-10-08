# -*- coding: utf-8 -*-
"""生成服务器更新包 update_pack.zip（在开发机项目根目录运行）。

包含：后端全部代码、前端 dist 构建产物、数据库脚本、部署文档。
排除：.venv / node_modules / uploads（服务器本地数据）/ .env（服务器本地配置）/
      __pycache__ / *.db / certs（服务器自行生成或拷贝）/ .git
用法：python package_update.py
"""
import os
import zipfile
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, f"update_pack_{datetime.now().strftime('%Y%m%d')}.zip")

EXCLUDE_DIRS = {
    ".venv", "venv", "node_modules", "__pycache__", ".git", ".idea", ".vscode",
    "uploads", "instance", "certs", "build", "dist-Info", ".zcode",
}
EXCLUDE_FILES = {".env", ".env.example"}
EXCLUDE_EXT = {".db", ".pyc", ".log", ".apk"}


def wanted(rel_path, is_dir):
    parts = rel_path.replace("\\", "/").split("/")
    if is_dir:
        return not (set(parts) & EXCLUDE_DIRS)
    if set(parts) & EXCLUDE_DIRS:
        return False
    name = parts[-1]
    if name in EXCLUDE_FILES or os.path.splitext(name)[1] in EXCLUDE_EXT:
        return False
    return True


def main():
    count = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for base in ("backend", "frontend", "deploy"):
            base_dir = os.path.join(ROOT, base)
            for dirpath, dirnames, filenames in os.walk(base_dir):
                rel_dir = os.path.relpath(dirpath, ROOT)
                dirnames[:] = [d for d in dirnames if wanted(os.path.join(rel_dir, d), True)]
                for fn in filenames:
                    rel = os.path.normpath(os.path.join(rel_dir, fn))
                    if not wanted(rel, False):
                        continue
                    z.write(os.path.join(dirpath, fn), os.path.join("hust3d", rel))
                    count += 1
        # 根目录的一键脚本也带上
        for fn in ("启动服务.bat", "启动服务器.bat", "package_update.py", "README.md"):
            p = os.path.join(ROOT, fn)
            if os.path.isfile(p):
                z.write(p, os.path.join("hust3d", fn))
                count += 1
    size_mb = os.path.getsize(OUT) / 1024 / 1024
    print(f"更新包已生成：{OUT}")
    print(f"共 {count} 个文件，{size_mb:.1f} MB")
    print("排除项：.venv / node_modules / uploads / .env / 证书 —— 服务器本地的这些内容不会被覆盖")


if __name__ == "__main__":
    main()
