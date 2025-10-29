#!/usr/bin/env python3
"""
快速启动脚本 - 批量Banana图像生成
"""

import subprocess
import sys
import os

def main():
    script_path = os.path.join(os.path.dirname(__file__), "batch_banana_concurrent.py")
    
    print("="*80)
    print("  🍌 Banana批量并发图像生成工具")
    print("="*80)
    print()
    print("📋 使用说明:")
    print("  1. 将图像文件放入 input/image/ 目录")
    print("  2. 编辑 input/text/text.txt 设置提示词")
    print("  3. 确保 .env 文件中配置了API密钥")
    print()
    print("📂 当前配置:")
    
    # 检查输入目录
    image_dir = os.path.join(os.path.dirname(__file__), "input", "image")
    text_file = os.path.join(os.path.dirname(__file__), "input", "text", "text.txt")
    
    if os.path.exists(image_dir):
        image_count = len([f for f in os.listdir(image_dir) 
                          if os.path.isfile(os.path.join(image_dir, f)) 
                          and f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'))])
        print(f"  🖼️  图像文件: {image_count} 个")
    else:
        print(f"  ⚠️  图像目录不存在")
    
    if os.path.exists(text_file):
        with open(text_file, 'r', encoding='utf-8') as f:
            prompt = f.read().strip()
            print(f"  📝 提示词: {prompt[:50]}{'...' if len(prompt) > 50 else ''}")
    else:
        print(f"  ⚠️  提示词文件不存在")
    
    print()
    print("="*80)
    
    # 运行主脚本
    try:
        subprocess.run([sys.executable, script_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"\n❌ 执行失败: {e}")
        return 1
    except KeyboardInterrupt:
        print(f"\n\n⚠️ 用户中断执行")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
