# 🔄 Banana批量处理完整流程

## 📋 当前工作流程

### 阶段1: 测试图像上传 ✅ **← 当前阶段**

在批量生成之前，需要先验证图像上传功能是否正常。

#### 1.1 测试上传功能

运行测试脚本：
```powershell
python test_upload_simple.py
```

测试内容：
- ✅ 测试获取上传Token
- ✅ 测试上传单个图像
- ✅ 验证返回的URL是否可访问
- ✅ （可选）测试批量上传所有图像

**预期结果：**
```
✅ Token获取成功
✅ 文件上传成功
🔗 返回的URL: https://cdn.grsai.com/xxxxx.jpg
```

如果上传失败，需要检查：
- [ ] API密钥是否正确
- [ ] 网络连接是否正常
- [ ] 文件格式是否支持
- [ ] API权限是否足够

---

### 阶段2: 测试Banana生成（使用上传的URL）

上传测试成功后，测试使用上传的图像URL进行banana生成。

#### 2.1 修改测试脚本

创建一个测试脚本，使用上传的URL：
```python
from api_client import GrsaiAPI

api_key = "your_api_key"
client = GrsaiAPI(api_key=api_key)

# 使用上传后的图像URL
image_url = "https://cdn.grsai.com/xxxxx.jpg"
prompt = "换一个自然休闲优雅的pose"

pil_images, urls, errors = client.banana_generate_image(
    prompt=prompt,
    model="nano-banana-fast",
    urls=[image_url],  # 传入上传的URL
    aspect_ratio="auto"
)
```

---

### 阶段3: 完整批量处理流程

确认单个图像测试成功后，运行完整的批量处理。

#### 3.1 批量处理流程

```
输入准备
    ├── input/image/*.jpg (4个图像文件)
    └── input/text/text.txt (提示词)
            ↓
【步骤1】批量上传图像到CDN
    ├── 并发上传（5个并发）
    ├── 获取每个图像的URL
    └── 记录上传结果
            ↓
【步骤2】批量调用Banana API
    ├── 每个任务使用对应的图像URL
    ├── 并发调用API（5个并发）
    └── 下载生成的图像
            ↓
【步骤3】保存结果
    └── batch_outputs/*.png (生成的图像)
```

#### 3.2 运行批量处理

```powershell
# 方式1: 使用批处理文件
run_batch.bat

# 方式2: 直接运行Python脚本
python batch_banana_concurrent.py
```

---

## 🎯 当前需要做的事情

### ✅ 第一步：测试上传功能（现在）

```powershell
python test_upload_simple.py
```

选择选项1：测试上传单个图像

**检查清单：**
- [ ] API密钥已配置（.env文件）
- [ ] input/image目录中有图像文件
- [ ] 网络连接正常
- [ ] 运行测试脚本
- [ ] 检查返回的URL是否有效

**成功标志：**
```
✅ 上传测试成功!
🔗 返回的URL: https://cdn.grsai.com/xxxxx.jpg
```

---

### ⏭️ 第二步：验证上传的URL

上传成功后，复制返回的URL并在浏览器中打开，确认：
- [ ] URL可以正常访问
- [ ] 图像显示正确
- [ ] 图像内容完整

---

### ⏭️ 第三步：测试Banana生成

创建测试脚本或修改现有测试：
```python
# 使用上传后的URL测试生成
python test_banana_with_url.py
```

---

### ⏭️ 第四步：运行完整批量处理

确认前面步骤都成功后：
```powershell
python batch_banana_concurrent.py
```

---

## 📊 流程图

```
┌─────────────────────────────────────────┐
│  准备阶段                                │
│  - 配置API密钥                           │
│  - 准备输入图像和提示词                   │
└────────────┬────────────────────────────┘
             ↓
┌─────────────────────────────────────────┐
│  阶段1: 测试上传 ← 当前在这里            │
│  python test_upload_simple.py           │
│  - 测试获取Token                        │
│  - 测试上传单个图像                      │
│  - 验证返回URL                          │
└────────────┬────────────────────────────┘
             ↓
        上传成功？
             ├─ 否 → 排查问题（API密钥、网络等）
             ↓ 是
┌─────────────────────────────────────────┐
│  阶段2: 测试Banana生成                   │
│  - 使用上传的URL                         │
│  - 测试单个图像生成                       │
│  - 验证生成结果                          │
└────────────┬────────────────────────────┘
             ↓
        生成成功？
             ├─ 否 → 排查问题（URL、提示词等）
             ↓ 是
┌─────────────────────────────────────────┐
│  阶段3: 批量处理                         │
│  python batch_banana_concurrent.py      │
│  - 批量上传所有图像                       │
│  - 批量调用Banana API                    │
│  - 保存所有生成结果                       │
└────────────┬────────────────────────────┘
             ↓
┌─────────────────────────────────────────┐
│  完成                                    │
│  - 查看 batch_outputs/ 目录              │
│  - 检查生成的图像质量                     │
└─────────────────────────────────────────┘
```

---

## 🔧 快速命令参考

```powershell
# 1. 测试上传单个图像（当前步骤）
python test_upload_simple.py

# 2. 测试上传所有图像
python test_upload_simple.py  # 选择选项2

# 3. 测试Banana生成（使用现有测试）
python test_banana.py

# 4. 运行完整批量处理
python batch_banana_concurrent.py

# 或使用批处理文件
run_batch.bat
```

---

## ❓ 常见问题

**Q: 上传失败怎么办？**
A: 检查以下几点：
1. API密钥是否正确
2. 网络是否可以访问 api.grsai.com
3. 文件格式是否支持（jpg, png等）
4. 文件大小是否超出限制

**Q: URL返回了但无法访问？**
A: 
1. 检查URL格式是否正确
2. 尝试在浏览器中直接打开URL
3. 检查CDN域名是否可访问

**Q: 批量处理时部分失败？**
A:
1. 检查失败的任务错误信息
2. 降低并发数（MAX_WORKERS）
3. 检查API配额是否用完

---

## 📝 当前进度

- [x] 创建批量处理脚本
- [x] 创建配置和工具模块
- [x] 实现完整的上传功能
- [x] 创建上传测试脚本
- [ ] **测试上传功能** ← **当前任务**
- [ ] 验证上传的URL可访问
- [ ] 测试Banana生成（使用上传的URL）
- [ ] 运行完整批量处理
- [ ] 验证最终结果

---

## 🎯 下一步操作

**立即执行：**
```powershell
cd C:\Users\1\Desktop\banana
python test_upload_simple.py
```

选择选项 1，测试上传单个图像。

根据测试结果：
- ✅ 成功 → 继续验证URL → 测试Banana生成 → 批量处理
- ❌ 失败 → 查看错误信息 → 排查问题 → 重新测试
