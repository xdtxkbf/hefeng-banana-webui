#!/usr/bin/env python3
"""
批量并发提交banana图像生成任务 V2
完全并行架构：上传完成立即提交API，不等待其他任务

特性：
1. 图像上传并行执行
2. 哪个图像上传完成就立即调用Banana API
3. 10个并发worker同时处理上传+API调用
4. 支持多账号轮询分配，突破单账号限制

配置说明：
- USE_MULTIPLE_ACCOUNTS = False  # 单账号模式（默认）
- USE_MULTIPLE_ACCOUNTS = True   # 多账号模式（自动轮询分配）

运行: python batch_banana_concurrent_v2.py
"""

import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional, Dict
import traceback

# 保证可从当前目录导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 尝试加载 .env 中的环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from api_client import GrsaiAPI, GrsaiAPIError
    from upload import upload_file_zh
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print("请确保 api_client.py 和 upload.py 在当前目录中")
    sys.exit(1)

# 配置
API_KEY = os.getenv("GRSAI_API_KEY", "")

# ========== 多账号配置 ==========
# 是否启用多账号并发（True=启用多账号，False=只用主账号）
USE_MULTIPLE_ACCOUNTS = True

# 备用账号列表（当 USE_MULTIPLE_ACCOUNTS=True 时使用）
BACKUP_API_KEYS = [
    "sk-3c0ffe3c8cb44e46a89e96eabb01c707",
    # 可以继续添加更多账号...
]

# 所有可用的API密钥列表（运行时自动生成）
ALL_API_KEYS = []
# ========================================

INPUT_IMAGE_DIR = os.path.join(os.path.dirname(__file__), "input", "image")
INPUT_TEXT_FILE = os.path.join(os.path.dirname(__file__), "input", "text", "text.txt")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "batch_outputs")
MAX_WORKERS = 10  # 并发数量
MODEL = "nano-banana-fast"
ASPECT_RATIO = "auto"

# 支持的图像格式
SUPPORTED_IMAGE_FORMATS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def get_api_key_for_task(task_id: int, all_keys: List[str]) -> str:
    """
    为任务分配API密钥（轮询分配）
    
    Args:
        task_id: 任务ID
        all_keys: 所有可用的API密钥列表
        
    Returns:
        分配的API密钥
    """
    if not all_keys:
        raise ValueError("没有可用的API密钥")
    
    # 使用取模运算轮询分配
    key_index = (task_id - 1) % len(all_keys)
    return all_keys[key_index]


def read_prompt_from_file(file_path: str) -> List[str]:
    """读取文本文件中的提示词（支持多行）"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
            return lines if lines else []
    except FileNotFoundError:
        print(f"⚠️ 未找到提示词文件: {file_path}")
        return []
    except Exception as e:
        print(f"⚠️ 读取提示词文件失败: {e}")
        return []


def get_image_files(directory: str) -> List[str]:
    """获取目录中的所有图像文件"""
    image_files = []
    try:
        for file_path in Path(directory).iterdir():
            if file_path.suffix.lower() in SUPPORTED_IMAGE_FORMATS:
                image_files.append(str(file_path))
    except Exception as e:
        print(f"⚠️ 读取图像目录失败: {e}")
    return sorted(image_files)


def process_task_with_upload(
    task_id: int,
    image_path: str,
    prompt: str,
    prompt_idx: int,
    api_key: str,
    model: str,
    aspect_ratio: str,
    output_dir: str
) -> Tuple[int, bool, str, float]:
    """
    完整处理单个任务：上传图像 -> 调用API -> 保存结果
    
    Returns:
        (task_id, success, message, total_time)
    """
    task_start_time = time.time()
    
    # 生成任务名称
    image_name = os.path.splitext(os.path.basename(image_path))[0]
    task_name = f"Task_{task_id}_{image_name}_prompt{prompt_idx}"
    filename = os.path.basename(image_path)
    
    try:
        # ========== 步骤1: 上传图像 ==========
        print(f"\n[{time.strftime('%H:%M:%S')}] 📤 {task_name}: 开始上传 {filename}")
        print(f"    🔑 使用账号: {api_key[:10]}...{api_key[-4:]}")
        upload_start = time.time()
        
        cdn_url = upload_file_zh(image_path, api_key)
        upload_time = time.time() - upload_start
        
        if not cdn_url:
            error_msg = f"上传失败"
            print(f"[{time.strftime('%H:%M:%S')}] ❌ {task_name}: {error_msg}")
            return task_id, False, error_msg, time.time() - task_start_time
        
        print(f"[{time.strftime('%H:%M:%S')}] ✅ {task_name}: 上传成功 | ⏱️ {upload_time:.2f}s")
        
        # ========== 步骤2: 立即调用Banana API ==========
        print(f"[{time.strftime('%H:%M:%S')}] 🍌 {task_name}: 开始调用Banana API")
        print(f"    📝 提示词: {prompt[:40]}...")
        
        api_start = time.time()
        client = GrsaiAPI(api_key=api_key)
        
        pil_images, image_urls, errors = client.banana_generate_image(
            prompt=prompt,
            model=model,
            urls=[cdn_url],
            aspect_ratio=aspect_ratio
        )
        
        api_time = time.time() - api_start
        
        # 检查错误
        if errors:
            error_msg = f"API返回错误: {', '.join(errors)}"
            print(f"[{time.strftime('%H:%M:%S')}] ❌ {task_name}: {error_msg}")
            return task_id, False, error_msg, time.time() - task_start_time
        
        if not pil_images:
            error_msg = "未返回任何图像"
            print(f"[{time.strftime('%H:%M:%S')}] ❌ {task_name}: {error_msg}")
            return task_id, False, error_msg, time.time() - task_start_time
        
        # ========== 步骤3: 保存生成的图像 ==========
        saved_files = []
        for idx, img in enumerate(pil_images, start=1):
            output_filename = f"{task_name}_{idx}.png"
            output_path = os.path.join(output_dir, output_filename)
            
            try:
                img.save(output_path)
                saved_files.append(output_filename)
            except Exception as e:
                print(f"⚠️ 保存图像失败 {output_filename}: {e}")
        
        total_time = time.time() - task_start_time
        
        print(f"[{time.strftime('%H:%M:%S')}] ✅ {task_name}: 完成!")
        print(f"    📊 上传: {upload_time:.2f}s | API: {api_time:.2f}s | 总计: {total_time:.2f}s")
        print(f"    💾 已保存: {', '.join(saved_files)}")
        
        success_msg = f"成功生成 {len(saved_files)} 张图像"
        return task_id, True, success_msg, total_time
        
    except Exception as e:
        total_time = time.time() - task_start_time
        error_msg = f"异常: {str(e)}"
        print(f"[{time.strftime('%H:%M:%S')}] ❌ {task_name}: {error_msg}")
        traceback.print_exc()
        return task_id, False, error_msg, total_time


def main():
    """主函数"""
    global ALL_API_KEYS
    
    print("🚀 批量并发Banana图像生成任务 V2")
    print("=" * 80)
    
    # 检查API密钥
    if not API_KEY:
        print("❌ 未找到API密钥")
        print("请在 .env 文件中设置 GRSAI_API_KEY")
        sys.exit(1)
    
    # ========== 初始化API密钥列表 ==========
    if USE_MULTIPLE_ACCOUNTS:
        # 多账号模式：主账号 + 备用账号
        ALL_API_KEYS = [API_KEY] + BACKUP_API_KEYS
        print(f"🔑 多账号模式已启用")
        print(f"   主账号: {API_KEY[:10]}...{API_KEY[-4:]}")
        for i, key in enumerate(BACKUP_API_KEYS, 1):
            print(f"   备用{i}: {key[:10]}...{key[-4:]}")
        print(f"   总计: {len(ALL_API_KEYS)} 个账号")
    else:
        # 单账号模式
        ALL_API_KEYS = [API_KEY]
        print(f"✅ 单账号模式: {API_KEY[:10]}...{API_KEY[-4:]}")
    
    # 创建输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"📁 输出目录: {OUTPUT_DIR}")
    
    # 读取提示词
    prompts = read_prompt_from_file(INPUT_TEXT_FILE)
    if not prompts:
        print("❌ 未找到有效的提示词")
        sys.exit(1)
    
    print(f"📝 找到 {len(prompts)} 个提示词:")
    for i, prompt in enumerate(prompts, 1):
        print(f"   {i}. {prompt[:60]}{'...' if len(prompt) > 60 else ''}")
    
    # 获取图像文件
    image_files = get_image_files(INPUT_IMAGE_DIR)
    if not image_files:
        print("❌ 未找到图像文件")
        sys.exit(1)
    
    print(f"🖼️ 找到 {len(image_files)} 个图像文件:")
    for img in image_files:
        print(f"   - {os.path.basename(img)}")
    
    # 计算任务总数
    total_tasks = len(image_files) * len(prompts)
    
    print(f"\n⚙️ 配置:")
    print(f"   - 模型: {MODEL}")
    print(f"   - 宽高比: {ASPECT_RATIO}")
    print(f"   - 并发数: {MAX_WORKERS}")
    print(f"   - 图像数: {len(image_files)}")
    print(f"   - 提示词数: {len(prompts)}")
    print(f"   - 任务总数: {total_tasks}")
    
    print("\n" + "=" * 80)
    print(f"⏰ 开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🚀 即将并发执行 {total_tasks} 个任务...")
    print("=" * 80)
    
    # 等待用户确认
    input("按回车键开始批量处理...")
    
    print("\n" + "=" * 80)
    print(f"⚡ 并发执行中... (并发数: {MAX_WORKERS})")
    print("=" * 80)
    
    # 记录开始时间
    batch_start_time = time.time()
    
    # 创建任务列表（存储所有任务的参数，用于重试）
    task_id = 0
    task_params = []  # 存储所有任务的参数
    results = []
    completed_count = 0
    
    # 生成所有任务参数
    for image_path in image_files:
        for prompt_idx, prompt in enumerate(prompts, 1):
            task_id += 1
            task_params.append({
                'task_id': task_id,
                'image_path': image_path,
                'prompt': prompt,
                'prompt_idx': prompt_idx
            })
    
    # 第一次执行所有任务
    print(f"\n{'='*80}")
    print(f"⚡ 第1轮：并发执行中... (并发数: {MAX_WORKERS})")
    print(f"{'='*80}")
    
    def execute_tasks(tasks_to_run, round_num=1):
        """执行一批任务"""
        local_results = []
        local_completed = 0
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {}
            
            for task_param in tasks_to_run:
                task_id = task_param['task_id']
                assigned_key = get_api_key_for_task(task_id, ALL_API_KEYS)
                
                future = executor.submit(
                    process_task_with_upload,
                    task_id,
                    task_param['image_path'],
                    task_param['prompt'],
                    task_param['prompt_idx'],
                    assigned_key,
                    MODEL,
                    ASPECT_RATIO,
                    OUTPUT_DIR
                )
                
                futures[future] = task_param
            
            if round_num == 1:
                print(f"✅ 已提交 {len(futures)} 个任务到线程池\n")
            
            # 按完成顺序处理结果
            for future in as_completed(futures):
                task_param = futures[future]
                task_id, success, message, duration = future.result()
                
                local_results.append({
                    'task_id': task_id,
                    'task_param': task_param,
                    'success': success,
                    'message': message,
                    'duration': duration
                })
                
                local_completed += 1
                print(f"[进度: {local_completed}/{len(tasks_to_run)}] 任务完成\n")
        
        return local_results
    
    # 执行第一轮
    results = execute_tasks(task_params, round_num=1)
    
    # ========== 重试失败的任务 ==========
    failed_tasks = [r for r in results if not r['success']]
    retry_round = 2
    max_retries = 3  # 最多重试3次
    
    while failed_tasks and retry_round <= max_retries:
        print(f"\n{'='*80}")
        print(f"⚠️ 发现 {len(failed_tasks)} 个失败任务，开始第 {retry_round} 轮重试...")
        print(f"{'='*80}")
        
        # 显示失败任务详情
        for idx, failed in enumerate(failed_tasks, 1):
            task_id = failed['task_id']
            message = failed['message']
            print(f"   {idx}. Task_{task_id}: {message}")
        
        print()
        
        # 提取失败任务的参数
        retry_task_params = [r['task_param'] for r in failed_tasks]
        
        # 重新执行失败的任务
        retry_results = execute_tasks(retry_task_params, round_num=retry_round)
        
        # 更新results：移除旧的失败结果，添加新的重试结果
        failed_task_ids = {r['task_id'] for r in failed_tasks}
        results = [r for r in results if r['task_id'] not in failed_task_ids]
        results.extend(retry_results)
        
        # 检查本轮是否还有失败
        failed_tasks = [r for r in retry_results if not r['success']]
        retry_round += 1
    
    # 最终失败任务提示
    if failed_tasks:
        print(f"\n{'='*80}")
        print(f"⚠️ 经过 {max_retries} 轮重试后，仍有 {len(failed_tasks)} 个任务失败")
        print(f"{'='*80}")
        for idx, failed in enumerate(failed_tasks, 1):
            task_id = failed['task_id']
            message = failed['message']
            print(f"   {idx}. Task_{task_id}: {message}")
    
    # 计算统计信息
    batch_duration = time.time() - batch_start_time
    success_count = sum(1 for r in results if r['success'])
    fail_count = total_tasks - success_count
    
    # 估算串行执行时间
    total_task_time = sum(r['duration'] for r in results)
    serial_estimate = total_task_time
    speedup = serial_estimate / batch_duration if batch_duration > 0 else 1
    time_saved = (serial_estimate - batch_duration) / serial_estimate * 100 if serial_estimate > 0 else 0
    
    # 打印结果
    print("\n" + "=" * 80)
    print("📊 批量处理完成!")
    print("=" * 80)
    print(f"⏰ 完成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏱️ 实际总耗时: {batch_duration:.2f}s")
    
    if retry_round > 2:
        print(f"🔄 重试轮次: {retry_round - 2} 轮")
    
    print(f"📈 串行预计耗时: {serial_estimate:.2f}s")
    print(f"🚀 加速比: {speedup:.2f}x (节省 {time_saved:.1f}%时间)")
    print(f"✅ 成功: {success_count}/{total_tasks}")
    print(f"❌ 失败: {fail_count}/{total_tasks}")
    print(f"\n💾 输出目录: {OUTPUT_DIR}")
    print("=" * 80)


if __name__ == "__main__":
    main()
