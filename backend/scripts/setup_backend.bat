@echo off
chcp 65001 >nul
rem ===============================================
rem 后端一键部署（Windows）：创建虚拟环境 + 安装依赖
rem 用法：双击运行，或在 backend\scripts 目录执行
rem ===============================================

cd /d %~dp0..

echo [1/3] 创建虚拟环境 .venv ...
python -m venv .venv
if errorlevel 1 (
  echo.
  echo [错误] 创建虚拟环境失败：请先安装 Python 3.10+ 并勾选 "Add to PATH"
  pause
  exit /b 1
)

echo.
echo [2/3] 安装依赖（使用清华镜像，约 1-2 分钟）...
.venv\Scripts\python.exe -m pip install -r requirements-win.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
  echo.
  echo [错误] 依赖安装失败：请检查网络后重试，或换用阿里镜像：
  echo   .venv\Scripts\python.exe -m pip install -r requirements-win.txt -i https://mirrors.aliyun.com/pypi/simple/
  pause
  exit /b 1
)

echo.
echo [3/3] 依赖安装完成！后续步骤：
echo   1. 检查 backend\.env 中数据库配置（DB_USER / DB_PASSWORD 与本机 MySQL 一致）
echo   2. 在 MySQL 中执行 sql\schema.sql 建库建表（命令见 deploy\新电脑部署指南.md）
echo   3. 启动后端：.venv\Scripts\python.exe app.py
echo.
pause
