@echo off
chcp 65001 >nul
rem 生成局域网 HTTPS 自签名证书（手机扫码摄像头用）
cd /d %~dp0..
.venv\Scripts\python.exe scripts\generate_cert.py
pause
