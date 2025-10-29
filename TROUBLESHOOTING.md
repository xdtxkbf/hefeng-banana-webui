# 🔧 故障排除指南

## 常见问题及解决方案

### 🐍 Python 相关问题

#### 问题：提示"python不是内部或外部命令"
**原因**：Python未安装或未添加到系统PATH

**解决方案**：
1. 重新安装Python，确保勾选"Add Python to PATH"
2. 或手动添加Python到环境变量
3. 重启命令行/PowerShell窗口

#### 问题：pip安装依赖失败
**原因**：网络问题或pip源问题

**解决方案**：
```bash
# 使用国内镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/

# 或者升级pip
python -m pip install --upgrade pip
```

### 🔑 API 相关问题

#### 问题：API密钥无效或过期
**症状**：上传失败，提示认证错误

**解决方案**：
1. 检查.env文件中的API密钥是否正确
2. 确认密钥没有过期
3. 联系API提供商确认密钥状态

#### 问题：API请求频率限制
**症状**：部分任务失败，提示"rate limit"

**解决方案**：
1. 降低并发数（调整为2-5）
2. 添加更多备用API密钥
3. 等待一段时间后重试

### 🌐 网络相关问题

#### 问题：无法连接到API服务器
**症状**：上传超时，连接失败

**解决方案**：
1. 检查网络连接
2. 尝试使用VPN或代理
3. 检查防火墙设置
4. 稍后重试

#### 问题：浏览器无法打开界面
**症状**：程序启动但浏览器显示无法访问

**解决方案**：
1. 手动访问 http://localhost:7862
2. 检查端口是否被占用
3. 尝试更换端口（修改webui.py中的server_port）

### 💾 文件相关问题

#### 问题：图片上传失败
**症状**：图片无法上传或格式不支持

**解决方案**：
1. 确认图片格式（支持jpg、png、webp等）
2. 检查图片文件大小（建议<10MB）
3. 确认图片文件没有损坏

#### 问题：输出文件夹权限错误
**症状**：无法保存生成的图片

**解决方案**：
1. 检查文件夹权限
2. 以管理员身份运行程序
3. 手动创建batch_outputs文件夹

### 🖥️ 界面相关问题

#### 问题：界面显示异常或卡死
**症状**：按钮不响应，界面布局错乱

**解决方案**：
1. 刷新浏览器页面
2. 清除浏览器缓存
3. 重启程序
4. 尝试其他浏览器

#### 问题：进度显示不更新
**症状**：任务在运行但进度不变

**解决方案**：
1. 等待一段时间，可能是网络延迟
2. 检查后台是否有错误信息
3. 重启程序重新提交任务

### 🔧 系统性能问题

#### 问题：程序运行缓慢
**原因**：系统资源不足或并发数过高

**解决方案**：
1. 降低并发数（调整为2-5）
2. 关闭其他占用内存的程序
3. 减少同时处理的图片数量

#### 问题：内存使用过高
**原因**：处理大量图片或图片尺寸过大

**解决方案**：
1. 分批处理图片
2. 压缩图片尺寸
3. 重启程序释放内存

## 🔍 调试方法

### 查看错误信息
1. **命令行错误**：查看启动程序的命令行窗口
2. **浏览器控制台**：F12打开开发者工具查看错误
3. **日志文件**：查看程序目录下的日志文件

### 测试环境
```bash
# 测试Python环境
python --version
pip --version

# 测试依赖包
python -c "import gradio; print('Gradio OK')"
python -c "import requests; print('Requests OK')"
python -c "import PIL; print('PIL OK')"

# 测试API连接
python -c "import requests; print(requests.get('https://httpbin.org/ip').status_code)"
```

### 获取系统信息
```bash
# Windows
systeminfo | findstr /C:"OS Name" /C:"OS Version"

# Linux/Mac
uname -a
python --version
```

## 🆘 获取帮助

### 自助排查
1. 按照上述指南逐步检查
2. 查看GitHub Issues中的类似问题
3. 重新安装Python和依赖包

### 寻求帮助
如果问题仍未解决，请在GitHub Issues中提供：
1. **操作系统**：Windows/Mac/Linux版本
2. **Python版本**：python --version输出
3. **错误信息**：完整的错误信息截图
4. **操作步骤**：详细的操作过程
5. **配置信息**：隐去敏感信息的配置文件内容

### 紧急联系
- GitHub Issues: https://github.com/xdtxkbf/hefeng-banana-webui/issues
- 邮箱: [根据实际情况填写]

---

**记住：大多数问题都有解决方案，耐心按步骤排查即可！** 🌟