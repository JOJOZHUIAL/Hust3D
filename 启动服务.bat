@echo off
chcp 65001 >nul
rem ===============================================
rem 3D 打印服务系统 - 一键启动
rem 双击运行：会打开两个窗口分别跑后端和前端，关窗即停。
rem 日常使用只需访问 http://127.0.0.1:5000（后端窗口开着即可）。
rem ===============================================

cd /d %~dp0backend
start "3D打印-后端(5000)" cmd /k ".venv\Scripts\python.exe app.py"

cd /d %~dp0frontend
start "3D打印-前端(5173)" cmd /k "npm run dev"

echo.
echo 已在新窗口启动：
echo   后端  http://127.0.0.1:5000   （日常使用入口，窗口不要关）
echo   前端  http://localhost:5173   （开发模式，仅改代码时需要）
echo.
echo 关闭对应窗口即停止该服务。
pause
