#!/usr/bin/env python3
"""
探测正确的上传API端点
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GRSAI_API_KEY", "")

# 可能的端点
endpoints = [
    "/v1/upload/uploadToken",
    "/v1/draw/uploadToken",
    "/v1/upload/token",
    "/v1/file/upload",
    "/v1/media/upload",
    "/v1/storage/token",
    "/upload/token",
    "/uploadToken",
]

base_url = "https://api.grsai.com"

print("🔍 探测正确的上传API端点...\n")
print(f"API密钥: {api_key[:10]}...\n")

for endpoint in endpoints:
    url = f"{base_url}{endpoint}"
    print(f"尝试: {endpoint}")
    
    try:
        response = requests.post(
            url,
            json={"sux": "png"},
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"  ✅ 成功! 状态码: {response.status_code}")
            print(f"  响应: {response.json()}")
            print(f"\n🎉 找到正确的端点: {endpoint}\n")
            break
        elif response.status_code == 404:
            print(f"  ❌ 404 Not Found")
        elif response.status_code == 401:
            print(f"  🔐 401 Unauthorized (端点可能存在，但密钥无效)")
        else:
            print(f"  ⚠️ 状态码: {response.status_code}")
            print(f"  响应: {response.text[:200]}")
            
    except Exception as e:
        print(f"  ❌ 错误: {e}")
    
    print()
