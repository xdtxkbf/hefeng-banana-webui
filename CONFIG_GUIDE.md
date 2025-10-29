# Banana批量处理配置示例

## 基本配置

### 1. 并发数量 (MAX_WORKERS)
控制同时处理的任务数量

```python
MAX_WORKERS = 5  # 推荐: 3-8
```

- **低配置 (2-3)**: 适合网络不稳定或API限制严格的情况
- **中等配置 (5-6)**: 平衡速度和稳定性，推荐大多数用户
- **高配置 (8-10)**: 适合网络良好且API配额充足的情况

### 2. 模型选择 (MODEL)

```python
MODEL = "nano-banana-fast"  # 快速模型
# MODEL = "nano-banana"     # 标准模型（更高质量）
```

- **nano-banana-fast**: 速度快，适合批量处理
- **nano-banana**: 质量更高，但速度较慢

### 3. 宽高比 (ASPECT_RATIO)

```python
ASPECT_RATIO = "auto"  # 自动检测
```

可选值：
- `"auto"` - 自动选择（推荐）
- `"1:1"` - 正方形 (1024x1024)
- `"16:9"` - 横向宽屏 (适合电脑壁纸)
- `"9:16"` - 竖向宽屏 (适合手机壁纸)
- `"4:3"` - 横向标准
- `"3:4"` - 竖向标准

## 高级配置

### 修改API超时时间

编辑 `config.py`:
```python
self._config = {
    "timeout": 300,      # 改为更长的超时时间（秒）
    "max_retries": 3,    # 失败重试次数
}
```

### 自定义输出目录

编辑 `batch_banana_concurrent.py`:
```python
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "my_outputs")
```

### 修改支持的图像格式

编辑 `batch_banana_concurrent.py`:
```python
SUPPORTED_IMAGE_FORMATS = {".jpg", ".jpeg", ".png", ".webp"}
```

## 使用场景示例

### 场景1: 大批量快速处理
适合需要快速生成大量图像的情况

```python
MAX_WORKERS = 8
MODEL = "nano-banana-fast"
ASPECT_RATIO = "auto"
```

### 场景2: 高质量精细处理
适合需要高质量输出的情况

```python
MAX_WORKERS = 3
MODEL = "nano-banana"
ASPECT_RATIO = "16:9"
```

### 场景3: 网络不稳定环境
适合网络条件较差的情况

```python
MAX_WORKERS = 2
MODEL = "nano-banana-fast"
ASPECT_RATIO = "auto"

# 同时修改config.py中的timeout
self._config = {
    "timeout": 600,      # 增加到10分钟
    "max_retries": 5,    # 增加重试次数
}
```

## 提示词优化建议

### 1. 具体描述
```
❌ 不好: "改变姿势"
✅ 好: "换一个自然休闲优雅的pose，保持面无表情，参考大品牌服装的商业拍摄"
```

### 2. 保持一致性
如果需要保持某些元素不变，明确说明：
```
"衣服和背景不变，只改变人物姿势和表情"
```

### 3. 多个要求分行
```
1. 换一个自然的pose
2. 保持面无表情
3. 衣服和背景不变
4. 参考时尚大片风格
```

## 批处理策略

### 策略1: 分批处理
如果有100张图像，建议分成多批处理：

1. 每次处理20-30张
2. 检查结果质量
3. 根据需要调整参数
4. 继续处理下一批

### 策略2: 测试后批量
1. 先用1-2张图像测试
2. 确认参数和提示词正确
3. 再进行大批量处理

### 策略3: 优先级处理
1. 将重要的图像先处理
2. 检查结果
3. 再处理其余图像

## 错误排查清单

- [ ] API密钥是否正确配置在.env文件中？
- [ ] input/image目录中是否有图像文件？
- [ ] input/text/text.txt文件是否存在且有内容？
- [ ] 网络连接是否正常？
- [ ] 磁盘空间是否充足？
- [ ] Python是否已安装所需依赖？
- [ ] 并发数是否设置过高？

## 性能优化建议

1. **并发数调优**: 从小到大逐步测试，找到最佳值
2. **使用fast模型**: 在质量可接受的情况下使用fast模型
3. **本地缓存**: 已处理的图像不要重复处理
4. **分时段处理**: 在API使用量较低的时段处理
5. **批量监控**: 定期检查处理进度和错误日志
