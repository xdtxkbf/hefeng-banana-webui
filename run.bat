@echo off
chcp 65001 >nul
echo 🍌 启动 Banana 图像生成工具...
echo.

REM 检查配置文件
if not exist ".env" (
    echo ❌ 配置文件不存在，请先运行 install_and_run.bat 进行初始化
    pause
    exit /b 1
)

REM 检查Python和依赖
python -c "import gradio" >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 依赖未安装，请先运行 install_and_run.bat 进行安装
    pause
    exit /b 1
)

echo ✅ 环境检查完成，正在启动...
echo.
echo 程序启动后请在浏览器中访问：http://localhost:7862
echo 按Ctrl+C可以停止程序
echo.

python webui.py