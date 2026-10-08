@echo off
rem ===============================================
rem 3D Print Server - start (backend only)
rem Daily entry: http://127.0.0.1:5000 (also the Cloudflare tunnel target)
rem First run auto-creates LAN HTTPS cert for phone camera scanning.
rem ===============================================

cd /d %~dp0backend
if not exist "certs\cert.pem" (
  echo First run: generating LAN HTTPS certificate...
  .venv\Scripts\python.exe scripts\generate_cert.py
)

echo Starting backend on port 5000 ...
.venv\Scripts\python.exe app.py
pause
