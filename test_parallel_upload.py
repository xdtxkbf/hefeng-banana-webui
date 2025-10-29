#!/usr/bin/env python3
"""
测试并行上传功能
"""

import os
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from upload import upload_file_zh

# 加载环境变量
load_dotenv()
API_KEY = os.getenv('GRSAI_API_KEY')

def upload_single_file(file_path: str, task_id: int):
    """上传单个文件并记录时间"""
    start_time = time.time()
    filename = Path(file_path).name
    
    print(f"[{time.strftime('%H:%M:%S')}] 🚀 Task_{task_id}: 开始上传 {filename}")
    
    try:
        cdn_url = upload_file_zh(file_path, API_KEY)
        elapsed = time.time() - start_time
        print(f"[{time.strftime('%H:%M:%S')}] ✅ Task_{task_id}: 上传成功 {filename} | ⏱️ {elapsed:.2f}s")
        print(f"    📎 {cdn_url}")
        return {
            'task_id': task_id,
            'filename': filename,
            'cdn_url': cdn_url,
            'elapsed': elapsed,
            'success': True
        }
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"[{time.strftime('%H:%M:%S')}] ❌ Task_{task_id}: 上传失败 {filename} | ⏱️ {elapsed:.2f}s")
        print(f"    ⚠️ 错误: {e}")
        return {
            'task_id': task_id,
            'filename': filename,
            'error': str(e),
            'elapsed': elapsed,
            'success': False
        }

def main():
    print("=" * 60)
    print("🧪 并行上传测试")
    print("=" * 60)
    
    # 获取所有图像文件
    input_dir = Path("input/image")
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
    image_files = [
        f for f in input_dir.iterdir()
        if f.suffix.lower() in image_extensions
    ]
    
    if not image_files:
        print("❌ 未找到图像文件")
        return
    
    print(f"📁 找到 {len(image_files)} 个图像文件")
    for i, f in enumerate(image_files, 1):
        print(f"   {i}. {f.name}")
    
    # 设置并发数
    MAX_WORKERS = 10
    print(f"\n⚙️ 并发数: {MAX_WORKERS}")
    print(f"⏰ 开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 开始并行上传
    start_time = time.time()
    results = []
    completed_count = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交所有上传任务
        future_to_task = {
            executor.submit(upload_single_file, str(img_file), i): i
            for i, img_file in enumerate(image_files, 1)
        }
        
        print(f"✅ 已提交 {len(future_to_task)} 个上传任务到线程池\n")
        
        # 按完成顺序处理结果（哪个先完成哪个先处理）
        for future in as_completed(future_to_task):
            result = future.result()
            results.append(result)
            completed_count += 1
            print(f"[进度: {completed_count}/{len(image_files)}] 上传任务完成\n")
    
    # 统计结果
    total_time = time.time() - start_time
    success_count = sum(1 for r in results if r['success'])
    fail_count = len(results) - success_count
    
    print("=" * 60)
    print("📊 上传测试完成!")
    print("=" * 60)
    print(f"⏰ 完成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏱️ 总耗时: {total_time:.2f}s")
    print(f"✅ 成功: {success_count}/{len(results)}")
    print(f"❌ 失败: {fail_count}/{len(results)}")
    
    if success_count > 0:
        avg_time = sum(r['elapsed'] for r in results if r['success']) / success_count
        print(f"📈 平均上传时间: {avg_time:.2f}s")
        
        # 显示最快和最慢的上传
        success_results = [r for r in results if r['success']]
        fastest = min(success_results, key=lambda x: x['elapsed'])
        slowest = max(success_results, key=lambda x: x['elapsed'])
        print(f"🚀 最快: {fastest['filename']} ({fastest['elapsed']:.2f}s)")
        print(f"🐌 最慢: {slowest['filename']} ({slowest['elapsed']:.2f}s)")
    
    print("=" * 60)

if __name__ == "__main__":
    main()
