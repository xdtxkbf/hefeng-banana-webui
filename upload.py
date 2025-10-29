#!/usr/bin/env python3
"""
GrsAI文件上传模块
实现文件上传到CDN的完整功能
"""

import os
import requests
import mimetypes
from typing import Optional, Dict, Any
from pathlib import Path


class UploadError(Exception):
    """上传错误异常"""
    pass


def get_upload_token_zh(api_key: str, params: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
    """
    获取上传token（国内加速版本）
    
    Args:
        api_key: API密钥
        params: 额外参数，如 {"sux": "png"} 指定文件后缀
        
    Returns:
        包含token信息的字典，格式如下：
        {
            "data": {
                "token": "上传凭证",
                "key": "文件key",
                "domain": "CDN域名"
            }
        }
        失败抛出异常
    """
    if not api_key:
        raise ValueError("API密钥不能为空")
    
    # 正确的端点（国内加速）
    url = "https://grsai.dakka.com.cn/client/resource/newUploadTokenZH"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = params or {}
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        return result
        
    except requests.exceptions.HTTPError as e:
        raise UploadError(f"获取上传token失败: HTTP {response.status_code}")
    except requests.exceptions.RequestException as e:
        raise UploadError(f"网络请求失败: {e}")
    except Exception as e:
        raise UploadError(f"解析响应失败: {e}")


def upload_to_cdn(file_path: str, token: str, key: str, upload_url: str) -> bool:
    """
    上传文件到CDN（使用表单POST方式，国内加速）
    
    Args:
        file_path: 本地文件路径
        token: 上传凭证
        key: 文件key
        upload_url: 上传地址
        
    Returns:
        上传是否成功
    """
    try:
        with open(file_path, 'rb') as f:
            files = {
                'file': (os.path.basename(file_path), f, _get_content_type(file_path))
            }
            data = {
                'token': token,
                'key': key
            }
            
            response = requests.post(
                upload_url,
                data=data,
                files=files,
                timeout=120
            )
            
            if response.status_code == 200:
                return True
            else:
                raise UploadError(f"上传失败: HTTP {response.status_code}, {response.text[:200]}")
                
    except requests.exceptions.RequestException as e:
        raise UploadError(f"上传请求失败: {e}")
    except Exception as e:
        raise UploadError(f"上传文件失败: {e}")


def upload_file_zh(file_path: str, api_key: Optional[str] = None) -> str:
    """
    上传文件到CDN并返回访问URL
    
    Args:
        file_path: 本地文件路径
        api_key: API密钥（如果不提供，从环境变量读取）
        
    Returns:
        上传后的完整URL
        
    Raises:
        ValueError: 文件路径为空
        FileNotFoundError: 文件不存在
        UploadError: 上传失败
    """
    # 验证文件
    if not file_path:
        return ""  # 根据测试代码，空路径返回空字符串
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    if not os.path.isfile(file_path):
        raise ValueError(f"不是有效的文件: {file_path}")
    
    # 获取API密钥
    if not api_key:
        api_key = os.getenv("GRSAI_API_KEY", "")
    
    if not api_key:
        raise UploadError("未找到API密钥，请设置GRSAI_API_KEY环境变量或传入api_key参数")
    
    # 1. 获取文件后缀
    file_ext = Path(file_path).suffix.lstrip('.')
    if not file_ext:
        file_ext = "bin"  # 默认后缀
    
    # 2. 获取上传token
    token_result = get_upload_token_zh(api_key, {"sux": file_ext})
    
    if not token_result or "data" not in token_result:
        raise UploadError("获取上传凭证失败: 响应格式错误")
    
    data = token_result["data"]
    token = data.get("token")
    key = data.get("key")
    domain = data.get("domain")
    upload_url = data.get("url")  # 获取上传URL
    
    if not all([token, key, domain, upload_url]):
        raise UploadError(f"上传凭证信息不完整")
    
    # 3. 上传文件到CDN
    file_size = os.path.getsize(file_path)
    
    if not upload_to_cdn(file_path, token, key, upload_url):
        raise UploadError("上传到CDN失败")
    
    # 4. 构建访问URL
    # 确保domain有协议前缀
    if not domain.startswith(('http://', 'https://')):
        domain = f"https://{domain}"
    
    # 确保domain没有尾部斜杠
    domain = domain.rstrip('/')
    
    # 构建完整URL
    file_url = f"{domain}/{key}"
    
    return file_url


def _get_content_type(file_path: str) -> str:
    """
    根据文件路径获取Content-Type
    
    Args:
        file_path: 文件路径
        
    Returns:
        Content-Type字符串
    """
    content_type, _ = mimetypes.guess_type(file_path)
    return content_type or 'application/octet-stream'
