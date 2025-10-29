# 🍌 Banana批量图像生成 - 快速开始

## 🚀 3步开始使用

### 步骤1: 准备文件
```
📁 input/image/          ← 放入你的图像文件（jpg, png等）
📄 input/text/text.txt   ← 编辑提示词（一行或多行）
```

### 步骤2: 配置API
编辑 `.env` 文件：
```
GRSAI_API_KEY=你的API密钥
```

### 步骤3: 运行
**Windows用户**: 双击 `run_batch.bat`

**命令行用户**:
```powershell
python batch_banana_concurrent.py
```

## 📊 预期输出

```
🚀 批量并发Banana图像生成任务
✅ API密钥已加载
📝 提示词: 换一个自然休闲优雅的pose...
🖼️ 找到 4 个图像文件

⏱️ 总耗时: 45.67s
✅ 成功: 4/4

💾 输出目录: batch_outputs/
```

生成的图像会保存在 `batch_outputs/` 目录中。

## ⚙️ 常用配置

在 `batch_banana_concurrent.py` 中修改：

```python
MAX_WORKERS = 5              # 并发数：建议3-8
MODEL = "nano-banana-fast"   # 模型：fast更快
ASPECT_RATIO = "auto"        # 宽高比：auto自动
```

## 📚 详细文档

- 📖 [完整使用说明](README_BATCH.md)
- ⚙️ [配置指南](CONFIG_GUIDE.md)

## ❓ 常见问题

**Q: 没有图像文件怎么办？**
A: 脚本会只使用提示词生成，不需要输入图像。

**Q: 可以使用不同的提示词吗？**
A: 当前版本使用统一提示词，如需不同提示词请修改代码或多次运行。

**Q: 处理失败怎么办？**
A: 检查网络连接和API密钥，降低并发数后重试。

**Q: 生成的图像在哪里？**
A: `batch_outputs/` 目录，自动创建。

## 💡 提示

- ✅ 先用1-2张图测试，确认效果后再批量处理
- ✅ 网络不稳定时降低并发数（2-3）
- ✅ 定期清理batch_outputs目录以节省空间
- ✅ 提示词要具体明确，避免模糊描述

## 🛠️ 依赖安装

如果运行出错，安装依赖：
```powershell
pip install requests pillow python-dotenv
```

---
🎉 祝使用愉快！如有问题请查看详细文档。
