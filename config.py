"""
GrsAI配置模块
"""

import os
from typing import Any, Optional


class GrsaiConfig:
    """配置类"""
    
    # 支持的Nano Banana宽高比
    SUPPORTED_NANO_BANANA_AR = [
        "auto", "1:1", "16:9", "9:16", "4:3", "3:4",
        "3:2", "2:3", "5:4", "4:5", "21:9"
    ]
    
    def __init__(self):
        self._config = {
            "api_base_url": "https://api.grsai.com",
            "timeout": 300,
            "max_retries": 3,
            "model": "nano-banana-fast",
        }
        self._api_key = os.getenv("GRSAI_API_KEY", "")
        self.api_key_error_message = (
            "❌ 未找到API密钥\n"
            "请在 .env 文件中设置 GRSAI_API_KEY=your_api_key"
        )
    
    def get_api_key(self) -> str:
        """获取API密钥"""
        return self._api_key
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self._config.get(key, default)
    
    def set_config(self, key: str, value: Any):
        """设置配置项"""
        self._config[key] = value
    
    def validate_nano_banana_aspect_ratio(self, aspect_ratio: str) -> bool:
        """验证Nano Banana宽高比"""
        return aspect_ratio in self.SUPPORTED_NANO_BANANA_AR


# 默认配置实例
default_config = GrsaiConfig()
