# 如何保存 API Token，避免每次都输入

## 方法1：使用 .env 文件（推荐）

1. 复制 `.env.example` 文件并重命名为 `.env`
   ```bash
   copy .env.example .env
   ```

2. 用记事本打开 `.env` 文件，填入你的 API 密钥：
   ```bash
   # 主API密钥（必填）
   GRSAI_API_KEY=sk-your-api-key-here
   
   # 备用API密钥（可选）
   GRSAI_BACKUP_KEYS=sk-your-backup-key-1
   GRSAI_BACKUP_KEYS=sk-your-backup-key-2
   ```

3. 保存文件后重启 WebUI，token 会自动加载

## 方法2：设置系统环境变量

### Windows:
1. 右键"此电脑" → "属性" → "高级系统设置" → "环境变量"
2. 在"用户变量"中点击"新建"
3. 变量名：`GRSAI_API_KEY`
4. 变量值：你的 API 密钥
5. 点击"确定"保存
6. 重启命令行和 WebUI

### 命令行临时设置（PowerShell）:
```powershell
$env:GRSAI_API_KEY="sk-your-api-key-here"
python webui.py
```

## 验证是否生效

启动 WebUI 后，检查配置区的"主API密钥"输入框是否已经有值（显示为密码点点）。如果有值，说明配置成功。

## 注意事项

- `.env` 文件不会被 git 提交（已在 .gitignore 中）
- 不要将 API 密钥分享给他人或提交到公开仓库
- 如果使用多账户，每个备用密钥写在单独一行
