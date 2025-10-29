#!/bin/bash

echo "🍌 Banana 图像生成工具 - 安装脚本"
echo "=================================="
echo

# 检查Python是否已安装
if ! command -v python3 &> /dev/null; then
    echo "❌ 未检测到Python3，请先安装Python3"
    echo "Ubuntu/Debian: sudo apt install python3 python3-pip"
    echo "macOS: brew install python3"
    echo "CentOS/RHEL: sudo yum install python3 python3-pip"
    exit 1
fi

echo "✅ 检测到Python3已安装"
python3 --version

# 检查pip是否可用
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3不可用，请安装pip3"
    exit 1
fi

echo "✅ pip3可用"
echo

# 创建.env文件（如果不存在）
if [ ! -f ".env" ]; then
    echo "📝 创建配置文件..."
    if [ -f ".env.example" ]; then
        cp ".env.example" ".env"
    else
        cat > .env << EOF
# GrsAI API Configuration
GRSAI_API_KEY=

# Backup API Keys (one per line)
GRSAI_BACKUP_KEYS=
EOF
    fi
    echo "✅ 配置文件已创建：.env"
fi

# 检查.env文件是否配置了API密钥
if ! grep -q "GRSAI_API_KEY=sk-" .env 2>/dev/null; then
    echo
    echo "⚠️  需要配置API密钥"
    echo "请编辑 .env 文件，填入您的API密钥："
    echo
    echo "GRSAI_API_KEY=your_main_api_key_here"
    echo "GRSAI_BACKUP_KEYS=your_backup_api_key_here"
    echo
    echo "配置完成后请重新运行此脚本"
    echo "编辑命令: nano .env 或 vim .env"
    exit 1
fi

echo "✅ API密钥已配置"
echo

# 安装Python依赖
echo "📦 正在安装依赖包..."
echo "这可能需要几分钟时间，请耐心等待..."
echo

# 创建requirements.txt（如果不存在）
if [ ! -f "requirements.txt" ]; then
    cat > requirements.txt << EOF
gradio>=4.0.0
requests>=2.25.0
pillow>=8.0.0
python-dotenv>=0.19.0
EOF
fi

pip3 install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "❌ 依赖安装失败，请检查网络连接"
    exit 1
fi

echo "✅ 依赖安装完成"
echo

# 创建必要的文件夹
mkdir -p batch_outputs input input_cache

echo "📁 工作目录已准备完成"
echo

# 启动程序
echo "🚀 正在启动程序..."
echo "程序启动后会自动在浏览器中打开Web界面"
echo "如果浏览器没有自动打开，请手动访问：http://localhost:7862"
echo
echo "按Ctrl+C可以停止程序"
echo

python3 webui.py