#!/usr/bin/env python3
"""
测试图像上传和URL返回
简化版测试脚本，用于验证上传流程
"""

import os
import sys
from pathlib import Path

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

from upload import upload_file_zh, get_upload_token_zh, UploadError


def test_upload_single_image():
    """测试上传单个图像"""
    print("=" * 80)
    print("📤 测试图像上传功能")
    print("=" * 80)
    
    # 检查API密钥
    api_key = os.getenv("GRSAI_API_KEY", "")
    if not api_key:
        print("❌ 未找到API密钥")
        print("请在 .env 文件中设置 GRSAI_API_KEY")
        return False
    
    print(f"✅ API密钥已加载: {api_key[:10]}...")
    
    # 获取input/image目录中的第一个图像
    image_dir = os.path.join(os.path.dirname(__file__), "input", "image")
    
    if not os.path.exists(image_dir):
        print(f"❌ 图像目录不存在: {image_dir}")
        return False
    
    # 找到第一个图像文件
    image_files = []
    for file in os.listdir(image_dir):
        if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif')):
            image_files.append(os.path.join(image_dir, file))
    
    if not image_files:
        print(f"❌ 在 {image_dir} 中没有找到图像文件")
        return False
    
    # 使用第一个图像文件
    test_image = image_files[0]
    print(f"\n📷 测试图像: {os.path.basename(test_image)}")
    print(f"📂 文件大小: {os.path.getsize(test_image) / 1024:.2f} KB")
    
    # 上传图像
    print(f"\n{'='*80}")
    print("🚀 开始上传...")
    print(f"{'='*80}\n")
    
    try:
        print(f"📤 正在获取上传凭证...")
        result_url = upload_file_zh(test_image, api_key)
        
        print(f"\n{'='*80}")
        print("✅ 上传测试成功!")
        print(f"🔗 返回的URL: {result_url}")
        print(f"\n你可以在浏览器中打开这个URL查看图像:")
        print(f"   {result_url}")
        print("=" * 80)
        return True
        
    except UploadError as e:
        print(f"\n{'='*80}")
        print(f"❌ 上传失败: {e}")
        print("=" * 80)
        return False
    except Exception as e:
        print(f"\n{'='*80}")
        print(f"❌ 上传异常: {e}")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        return False


def test_upload_all_images():
    """测试上传所有图像"""
    print("\n" + "=" * 80)
    print("📤 测试批量上传所有图像")
    print("=" * 80)
    
    # 检查API密钥
    api_key = os.getenv("GRSAI_API_KEY", "")
    if not api_key:
        print("❌ 未找到API密钥")
        return False
    
    # 获取所有图像
    image_dir = os.path.join(os.path.dirname(__file__), "input", "image")
    image_files = []
    for file in os.listdir(image_dir):
        if file.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif')):
            image_files.append(os.path.join(image_dir, file))
    
    if not image_files:
        print(f"❌ 没有找到图像文件")
        return False
    
    print(f"\n找到 {len(image_files)} 个图像文件")
    
    # 上传所有图像
    results = []
    for idx, image_path in enumerate(image_files, 1):
        print(f"\n{'='*80}")
        print(f"📤 [{idx}/{len(image_files)}] 上传: {os.path.basename(image_path)}")
        print(f"{'='*80}")
        
        try:
            print(f"📤 正在获取上传凭证...")
            url = upload_file_zh(image_path, api_key)
            print(f"✅ 上传成功: {url}")
            results.append({
                'file': os.path.basename(image_path),
                'path': image_path,
                'url': url,
                'success': True
            })
        except Exception as e:
            print(f"❌ 上传失败: {e}")
            results.append({
                'file': os.path.basename(image_path),
                'path': image_path,
                'url': None,
                'success': False,
                'error': str(e)
            })
    
    # 输出统计
    print(f"\n{'='*80}")
    print("📊 批量上传结果统计")
    print(f"{'='*80}")
    
    success_count = sum(1 for r in results if r['success'])
    print(f"✅ 成功: {success_count}/{len(results)}")
    print(f"❌ 失败: {len(results) - success_count}/{len(results)}")
    
    # 显示所有URL
    print(f"\n📋 上传成功的图像URL:")
    print("-" * 80)
    for r in results:
        if r['success']:
            print(f"✅ {r['file']}")
            print(f"   {r['url']}")
        else:
            print(f"❌ {r['file']} - {r.get('error', '上传失败')}")
    
    print("=" * 80)
    return success_count == len(results)


def test_get_token():
    """仅测试获取上传token"""
    print("=" * 80)
    print("🔑 测试获取上传Token")
    print("=" * 80)
    
    api_key = os.getenv("GRSAI_API_KEY", "")
    if not api_key:
        print("❌ 未找到API密钥")
        return False
    
    print(f"✅ API密钥已加载: {api_key[:10]}...")
    print(f"\n正在获取上传token...")
    
    try:
        result = get_upload_token_zh(api_key, {"sux": "png"})
        
        if result and "data" in result:
            print(f"\n✅ Token获取成功!")
            data = result["data"]
            print(f"\n📋 Token信息:")
            print(f"   Token: {data.get('token', 'N/A')[:30]}...")
            print(f"   Key: {data.get('key', 'N/A')}")
            print(f"   Domain: {data.get('domain', 'N/A')}")
            return True
        else:
            print(f"\n❌ Token获取失败: 响应格式错误")
            return False
            
    except Exception as e:
        print(f"\n❌ Token获取失败: {e}")
        return False


def main():
    """主函数"""
    print("\n" + "🍌" * 40)
    print("  图像上传测试工具")
    print("🍌" * 40 + "\n")
    
    # 显示菜单
    print("请选择测试模式:")
    print("  1. 测试上传单个图像（快速测试）")
    print("  2. 测试上传所有图像（完整测试）")
    print("  3. 仅测试获取Token")
    print("  0. 退出")
    print()
    
    try:
        choice = input("请输入选项 [1]: ").strip() or "1"
        
        if choice == "1":
            success = test_upload_single_image()
        elif choice == "2":
            success = test_upload_all_images()
        elif choice == "3":
            success = test_get_token()
        elif choice == "0":
            print("👋 再见!")
            return 0
        else:
            print("❌ 无效的选项")
            return 1
        
        if success:
            print("\n🎉 测试完成!")
            return 0
        else:
            print("\n⚠️ 测试失败，请检查错误信息")
            return 1
            
    except KeyboardInterrupt:
        print("\n\n👋 测试被用户中断")
        return 1
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
