@echo off
chcp 65001 >nul
title 中医药智慧康养系统
echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║    中医药智慧康养系统                            ║
echo  ║    基于多智能体协同与检索增强生成              ║
echo  ╚══════════════════════════════════════════════════╝
echo.

:: 设置环境变量
set TEMP=%~dp0.tmp
set TMP=%~dp0.tmp
set PYTHONIOENCODING=utf-8
if not exist "%~dp0.tmp" mkdir "%~dp0.tmp"

:: 复制 demo 配置（如无 .env）
if not exist "%~dp0.env" (
    copy "%~dp0.env.demo" "%~dp0.env" >nul
    echo  [√] 已使用演示配置（LLM=mock，完全离线）
)

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [!] 未找到 Python，请先安装 Python 3.10+
    echo      下载：https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 检查 Node
node --version >nul 2>&1
if errorlevel 1 (
    echo  [!] 未找到 Node.js，请先安装 Node.js 18+
    echo      下载：https://nodejs.org/
    pause
    exit /b 1
)

echo  [1/5] 创建 Python 环境...
if not exist "%~dp0.venv" (
    python -m venv "%~dp0.venv" 2>nul
    if errorlevel 1 (
        conda create -p "%~dp0.venv" python=3.11 -y >nul 2>&1
    )
)

echo  [2/5] 安装依赖...
"%~dp0.venv\Scripts\pip" install -r "%~dp0backend\requirements.txt" -q 2>nul
if errorlevel 1 (
    "%~dp0.venv\Scripts\python" -m pip install -r "%~dp0backend\requirements.txt" -q 2>nul
)

echo  [3/5] 初始化数据与知识库...
cd /d "%~dp0backend"
"%~dp0.venv\Scripts\python" scripts\import_data.py --reset >nul 2>&1
"%~dp0.venv\Scripts\python" scripts\build_kb.py >nul 2>&1
"%~dp0.venv\Scripts\python" scripts\build_index.py >nul 2>&1
cd /d "%~dp0"

echo  [4/5] 启动后端服务...
start "后端服务" /min cmd /c "cd /d %~dp0backend && %~dp0.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
echo       等待后端就绪...
:wait_backend
timeout /t 2 /nobreak >nul
curl -s http://127.0.0.1:8000/health >nul 2>&1
if errorlevel 1 goto wait_backend
echo       后端已就绪 ✓

echo  [5/5] 启动前端服务...
cd /d "%~dp0frontend"
start "前端服务" /min cmd /c "npm run dev -- --host 0.0.0.0"
cd /d "%~dp0"
timeout /t 3 /nobreak >nul

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║  ✅ 系统已启动！                                ║
echo  ║                                                  ║
echo  ║  📱 前端页面: http://localhost:5173              ║
echo  ║  📖 API 文档: http://127.0.0.1:8000/docs        ║
echo  ║                                                  ║
echo  ║  按任意键打开浏览器...                          ║
echo  ╚══════════════════════════════════════════════════╝
echo.
pause >nul
start http://localhost:5173
echo  系统运行中，关闭此窗口将停止所有服务。
echo  按 Ctrl+C 或关闭窗口退出。
pause >nul