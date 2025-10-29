"""
工具函数模块
"""

import io
import requests
from typing import Optional
from PIL import Image


def format_error_message(error: Exception, context: str = "") -> str:
    """
    格式化错误消息
    
    Args:
        error: 异常对象
        context: 上下文信息
        
    Returns:
        格式化后的错误消息
    """
    if context:
        return f"{context}失败: {str(error)}"
    return str(error)


def download_image(url: str, timeout: int = 120) -> Optional[Image.Image]:
    """
    从URL下载图像
    
    Args:
        url: 图像URL
        timeout: 超时时间（秒）
        
    Returns:
        PIL图像对象，失败返回None
    """
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        image = Image.open(io.BytesIO(response.content))
        return image
    except Exception as e:
        print(f"下载图像失败: {e}")
        return None
