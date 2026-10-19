@echo off
chcp 65001 >nul
title 中医药智慧康养系统
echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║    中医药智慧康养系统                            ║
echo  ║    基于多智能体协同与检索增强生成              ║
echo  ╚══════════════════════════════════════════════════╝
echo.

:: 检查 Docker
docker --version >nul 2>&1
if errorlevel 1 (
    echo  [错误] 未找到 Docker
    echo  请先安装 Docker Desktop：https://www.docker.com/products/docker-desktop/
    echo.
    pause
    exit /b 1
)

echo  [1/2] 启动服务（首次需要构建镜像，约 3-5 分钟）...
docker compose up -d --build

echo.
echo  [2/2] 等待服务就绪...
:wait
timeout /t 3 /nobreak >nul
curl -s http://localhost/health >nul 2>&1
if errorlevel 1 goto wait

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║  ✅ 系统已启动！                                ║
echo  ║                                                  ║
echo  ║  📱 打开浏览器访问：http://localhost            ║
echo  ║                                                  ║
echo  ║  按任意键打开浏览器...                          ║
echo  ╚══════════════════════════════════════════════════╝
echo.
pause >nul
start http://localhost
echo.
echo  按任意键停止服务并退出...
pause >nul
docker compose down
echo  已停止。
pause >nul