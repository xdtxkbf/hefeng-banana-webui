# 🍌 Banana 图像生成 WebUI

一个简单易用的图像生成工具，支持批量处理、多账户并发、实时进度显示。

## 📖 项目简介

这是一个基于 Gradio 的 Web 界面工具，让您可以：
- 🖼️ 批量上传图像进行AI处理
- 📝 使用多行提示词批量生成
- 🔄 多账户并发，提高处理速度
- ⏱️ 实时查看处理进度
- 💾 自动缓存，避免重复上传
- 🔄 失败重试，确保任务完成

## 🚀 快速开始（适合小白用户）

### 方法一：一键安装脚本（推荐）

1. **下载项目**
   - 点击绿色的 "Code" 按钮
   - 选择 "Download ZIP"
   - 解压到任意文件夹

2. **双击运行安装脚本**
   - 双击 `install_and_run.bat` 文件
   - 脚本会自动安装 Python 和所需依赖
   - 安装完成后会自动启动程序

3. **配置API密钥**
   - 首次运行会提示输入API密钥
   - 按提示输入您的主API密钥和备用密钥

4. **开始使用**
   - 浏览器会自动打开 Web 界面
   - 按照界面提示上传图片和输入提示词即可

### 方法二：手动安装

#### 步骤1：安装 Python
1. 访问 [Python官网](https://www.python.org/downloads/)
2. 下载 Python 3.8 或更高版本
3. 安装时**勾选** "Add Python to PATH"

#### 步骤2：下载项目
```bash
git clone https://github.com/xdtxkbf/hefeng-banana-webui.git
cd hefeng-banana-webui
```

#### 步骤3：安装依赖
```bash
pip install -r requirements.txt
```

#### 步骤4：配置环境
1. 复制 `.env.example` 为 `.env`
2. 编辑 `.env` 文件，填入您的API密钥：
```
GRSAI_API_KEY=your_main_api_key_here
GRSAI_BACKUP_KEYS=your_backup_api_key_here
```

#### 步骤5：启动程序
```bash
python webui.py
```

## 🎯 使用说明

### 基本操作流程
1. **上传图像**: 拖拽图片到上传区域，或点击选择文件
2. **输入提示词**: 在文本框中输入提示词，每行一个
3. **配置参数**: 在折叠的配置区域调整并发数、模型等参数
4. **开始生成**: 点击"🚀 开始生成"按钮
5. **查看结果**: 在右侧查看生成进度和结果图像

### 界面说明
- **📤 输入区域**: 上传图像和输入提示词
- **⚙️ 配置区域**: API密钥、模型、并发参数设置
- **📊 输出区域**: 实时进度、结果图像、详细日志

### 高级功能
- **🔄 重做图像**: 点击结果图像后可重新生成
- **📋 重排参数**: 将选中图像的参数填回表单进行修改
- **💾 缓存管理**: 自动缓存上传的图像，避免重复上传
- **🔑 多账户**: 支持多个API密钥轮流使用，提高并发

## 🛠️ 配置说明

### 环境变量配置 (.env 文件)
```env
# 主API密钥（必填）
GRSAI_API_KEY=sk-your-main-api-key

# 备用API密钥（可选，多个密钥用换行分隔）
GRSAI_BACKUP_KEYS=sk-your-backup-key-1
```

### 参数说明
- **并发数**: 同时处理的任务数量，建议5-15
- **模型选择**: 
  - `nano-banana-fast`: 速度快，质量较好
  - `nano-banana`: 速度较慢，质量更高
- **宽高比**: 控制生成图像的尺寸比例

## 📋 系统要求

- **操作系统**: Windows 10+, macOS 10.14+, Linux
- **Python**: 3.8 或更高版本
- **内存**: 建议 4GB 以上
- **网络**: 稳定的互联网连接

## ❓ 常见问题

### Q: 提示"没有安装Python"怎么办？
A: 请按照上面的步骤安装Python，或者使用一键安装脚本。

### Q: 上传图像失败怎么办？
A: 检查网络连接和API密钥是否正确，也可以尝试使用备用密钥。

### Q: 生成速度很慢怎么办？
A: 可以增加并发数，或者配置多个API密钥进行并发处理。

### Q: 如何获取API密钥？
A: 请联系API服务提供商获取密钥。

### Q: 程序崩溃怎么办？
A: 查看终端错误信息，通常是网络或配置问题。可以重启程序重试。

## 🔧 开发说明

### 项目结构
```
hefeng-banana-webui/
├── webui.py              # 主程序文件
├── api_client.py         # API客户端
├── upload.py            # 文件上传功能
├── requirements.txt     # Python依赖
├── install_and_run.bat  # 一键安装脚本
├── .env.example         # 环境变量模板
├── .gitignore          # Git忽略文件
└── README.md           # 说明文档
```

### 技术栈
- **前端**: Gradio (Python Web UI框架)
- **后端**: Python + requests
- **并发**: ThreadPoolExecutor
- **图像处理**: PIL (Pillow)

## 📄 许可证

本项目使用 MIT 许可证。详见 LICENSE 文件。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📞 支持

如有问题，请在 GitHub Issues 中提出，或联系项目维护者。

---

**祝您使用愉快！🎉**