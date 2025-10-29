@echo off
chcp 65001 >nul
echo ============================================
echo 🍌 Banana 图像生成工具 - 一键安装脚本
echo ============================================
echo.

REM 检查Python是否已安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 未检测到Python，正在引导您安装...
    echo.
    echo 请按照以下步骤安装Python：
    echo 1. 浏览器会自动打开Python官网下载页面
    echo 2. 下载Python 3.8或更高版本
    echo 3. 安装时请勾选 "Add Python to PATH"
    echo 4. 安装完成后重新运行此脚本
    echo.
    pause
    start https://www.python.org/downloads/
    exit /b 1
)

echo ✅ 检测到Python已安装
python --version

REM 检查pip是否可用
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ pip不可用，请重新安装Python
    pause
    exit /b 1
)

echo ✅ pip可用
echo.

REM 创建.env文件（如果不存在）
if not exist ".env" (
    echo 📝 创建配置文件...
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
    ) else (
        echo # GrsAI API Configuration > .env
        echo GRSAI_API_KEY= >> .env
        echo. >> .env
        echo # Backup API Keys (one per line) >> .env
        echo GRSAI_BACKUP_KEYS= >> .env
    )
    echo ✅ 配置文件已创建：.env
)

REM 检查.env文件是否配置了API密钥
findstr /c:"GRSAI_API_KEY=" .env | findstr /v "GRSAI_API_KEY=$" >nul
if %errorlevel% neq 0 (
    echo.
    echo ⚠️  需要配置API密钥
    echo 请编辑 .env 文件，填入您的API密钥：
    echo.
    echo GRSAI_API_KEY=your_main_api_key_here
    echo GRSAI_BACKUP_KEYS=your_backup_api_key_here
    echo.
    echo 配置完成后请重新运行此脚本
    pause
    notepad .env
    exit /b 1
)

echo ✅ API密钥已配置
echo.

REM 安装Python依赖
echo 📦 正在安装依赖包...
echo 这可能需要几分钟时间，请耐心等待...
echo.

REM 创建requirements.txt（如果不存在）
if not exist "requirements.txt" (
    echo gradio>=4.0.0 > requirements.txt
    echo requests>=2.25.0 >> requirements.txt
    echo pillow>=8.0.0 >> requirements.txt
    echo python-dotenv>=0.19.0 >> requirements.txt
)

pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ❌ 依赖安装失败，请检查网络连接
    pause
    exit /b 1
)

echo ✅ 依赖安装完成
echo.

REM 创建必要的文件夹
if not exist "batch_outputs" mkdir batch_outputs
if not exist "input" mkdir input
if not exist "input_cache" mkdir input_cache

echo 📁 工作目录已准备完成
echo.

REM 启动程序
echo 🚀 正在启动程序...
echo 程序启动后会自动在浏览器中打开Web界面
echo 如果浏览器没有自动打开，请手动访问：http://localhost:7862
echo.
echo 按Ctrl+C可以停止程序
echo.

python webui.py
if %errorlevel% neq 0 (
    echo.
    echo ❌ 程序启动失败，请检查错误信息
    pause
)