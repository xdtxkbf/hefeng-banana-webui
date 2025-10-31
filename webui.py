#!/usr/bin/env python3
"""
Banana 图像生成 WebUI
支持：
1. 拖拽上传图片或选择文件夹
2. 多行提示词输入
3. 多账户并发配置
4. 实时进度显示
5. 自动重试失败任务
"""

import os
import sys
import time
import gradio as gr
from pathlib import Path
from typing import List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback
import threading
import uuid
from collections import defaultdict

# 保证可从当前目录导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
    sys.exit(1)

# 默认配置
DEFAULT_API_KEY = os.getenv("GRSAI_API_KEY", "")
DEFAULT_BACKUP_KEYS = os.getenv("GRSAI_BACKUP_KEYS", "")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "batch_outputs")
SUPPORTED_IMAGE_FORMATS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

# 全局状态管理
task_groups = defaultdict(dict)  # {group_id: {upload_progress, api_progress, status, results}}
task_groups_lock = threading.Lock()
all_output_files = []  # 所有任务组的输出文件累计 [(file_path, metadata)]
all_output_files_lock = threading.Lock()
image_metadata = {}  # {output_path: {source_image, prompt, model, aspect_ratio, ...}}
image_metadata_lock = threading.Lock()

# URL缓存：避免重复上传相同图像
upload_cache = {}  # {file_path: cdn_url}
upload_cache_lock = threading.Lock()


def get_api_key_for_task(task_id: int, all_keys: List[str]) -> str:
    """为任务分配API密钥（轮询分配）"""
    if not all_keys:
        raise ValueError("没有可用的API密钥")
    key_index = (task_id - 1) % len(all_keys)
    return all_keys[key_index]


def process_single_task(
    task_id: int,
    image_path: str,
    prompt: str,
    prompt_idx: int,
    api_key: str,
    model: str,
    aspect_ratio: str,
    output_dir: str
) -> Tuple[int, bool, str, float, Optional[str]]:
    """
    处理单个任务：上传图像 -> 调用API -> 保存结果
    
    Returns:
        (task_id, success, message, duration, output_file)
    """
    task_start_time = time.time()
    
    image_name = os.path.splitext(os.path.basename(image_path))[0]
    task_name = f"Task_{task_id}_{image_name}_prompt{prompt_idx}"
    
    try:
        # 上传图像
        cdn_url = upload_file_zh(image_path, api_key)
        if not cdn_url:
            return task_id, False, "上传失败", time.time() - task_start_time, None
        
        # 调用API
        client = GrsaiAPI(api_key=api_key)
        pil_images, image_urls, errors = client.banana_generate_image(
            prompt=prompt,
            model=model,
            urls=[cdn_url],
            aspect_ratio=aspect_ratio
        )
        
        if errors:
            error_msg = f"API错误: {', '.join(errors)}"
            return task_id, False, error_msg, time.time() - task_start_time, None
        
        if not pil_images:
            return task_id, False, "未返回图像", time.time() - task_start_time, None
        
        # 保存图像
        output_filename = f"{task_name}_1.png"
        output_path = os.path.join(output_dir, output_filename)
        pil_images[0].save(output_path)
        
        total_time = time.time() - task_start_time
        return task_id, True, f"成功", total_time, output_path
        
    except Exception as e:
        total_time = time.time() - task_start_time
        return task_id, False, f"异常: {str(e)}", total_time, None


def upload_single_image(task_id: int, image_path: str, api_key: str) -> Tuple[int, bool, str, Optional[str], float]:
    """上传单个图像（带缓存）"""
    start_time = time.time()
    try:
        # 检查缓存
        with upload_cache_lock:
            if image_path in upload_cache:
                cached_url = upload_cache[image_path]
                elapsed = time.time() - start_time
                return task_id, True, "使用缓存", cached_url, elapsed
        
        # 未缓存，执行上传
        cdn_url = upload_file_zh(image_path, api_key)
        elapsed = time.time() - start_time
        
        if cdn_url:
            # 保存到缓存
            with upload_cache_lock:
                upload_cache[image_path] = cdn_url
            return task_id, True, "上传成功", cdn_url, elapsed
        else:
            return task_id, False, "上传失败", None, elapsed
    except Exception as e:
        elapsed = time.time() - start_time
        return task_id, False, f"上传异常: {str(e)}", None, elapsed


def call_banana_api(task_id: int, cdn_url: str, prompt: str, api_key: str, 
                   model: str, aspect_ratio: str, output_dir: str, 
                   task_name: str, upload_time: float, source_image_path: str,
                   max_retries: int = 3) -> Tuple[int, bool, str, Optional[str], float, dict]:
    """调用 Banana API 生成图像（带重试机制）"""
    start_time = time.time()
    last_error = None
    
    for attempt in range(1, max_retries + 1):
        try:
            client = GrsaiAPI(api_key=api_key)
            pil_images, image_urls, errors = client.banana_generate_image(
                prompt=prompt,
                model=model,
                urls=[cdn_url],
                aspect_ratio=aspect_ratio
            )
            
            if errors:
                last_error = f"API错误: {', '.join(errors)}"
                if attempt < max_retries:
                    time.sleep(1 * attempt)  # 递增等待时间：1s, 2s, 3s
                    continue
                elapsed = time.time() - start_time
                return task_id, False, f"{last_error} (重试{attempt}次后失败)", None, elapsed, {}
            
            if not pil_images:
                last_error = "未返回图像"
                if attempt < max_retries:
                    time.sleep(1 * attempt)
                    continue
                elapsed = time.time() - start_time
                return task_id, False, f"{last_error} (重试{attempt}次后失败)", None, elapsed, {}
            
            # 保存图像
            output_filename = f"{task_name}_1.png"
            output_path = os.path.join(output_dir, output_filename)
            pil_images[0].save(output_path)
            
            elapsed = time.time() - start_time
            
            # 创建元数据（包含源图像路径和重试信息）
            metadata = {
                'source_image': source_image_path,
                'prompt': prompt,
                'upload_time': upload_time,
                'api_time': elapsed,
                'total_time': upload_time + elapsed,
                'model': model,
                'aspect_ratio': aspect_ratio,
                'task_name': task_name,
                'cdn_url': cdn_url,
                'retry_attempts': attempt  # 记录重试次数
            }
            
            # 保存到全局字典
            with image_metadata_lock:
                image_metadata[output_path] = metadata
            
            # 成功时显示是否重试过
            success_msg = "生成成功" if attempt == 1 else f"生成成功(重试{attempt}次)"
            return task_id, True, success_msg, output_path, elapsed, metadata
            
        except Exception as e:
            last_error = f"API异常: {str(e)}"
            if attempt < max_retries:
                time.sleep(1 * attempt)
                continue
            else:
                elapsed = time.time() - start_time
                return task_id, False, f"{last_error} (重试{attempt}次后失败)", None, elapsed, {}


def process_task_group_async(
    group_id: str,
    images,
    prompts: List[str],
    all_api_keys: List[str],
    max_workers: int,
    model: str,
    aspect_ratio: str,
    max_retries: int,
    output_dir: str = None
):
    """在后台线程中异步处理任务组"""
    
    # 使用指定的输出目录或默认目录
    if not output_dir:
        output_dir = OUTPUT_DIR
    
    # 初始化任务组状态
    with task_groups_lock:
        task_groups[group_id] = {
            'upload_progress': f"0/{len(images)}",
            'api_progress': "0/0",
            'status': "📤 正在上传图像...",
            'log': []
        }
    
    try:
        # 获取图像文件列表
        image_files = []
        for img in images:
            if isinstance(img, str):
                image_files.append(img)
            elif hasattr(img, 'name'):
                image_files.append(img.name)
        
        log_messages = []
        log_messages.append(f"🚀 任务组 {group_id[:8]}: {len(image_files)} 图像 × {len(prompts)} 提示词")
        
        # ========== 阶段1: 上传图像 ==========
        upload_results = {}  # {image_path: (cdn_url, upload_time)}
        upload_completed = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            upload_futures = {}
            
            for idx, image_path in enumerate(image_files, 1):
                assigned_key = get_api_key_for_task(idx, all_api_keys)
                future = executor.submit(upload_single_image, idx, image_path, assigned_key)
                upload_futures[future] = image_path
            
            for future in as_completed(upload_futures):
                image_path = upload_futures[future]
                task_id, success, message, cdn_url, duration = future.result()
                upload_completed += 1
                
                if success:
                    upload_results[image_path] = (cdn_url, duration)  # 保存上传时间
                    # 区分缓存和新上传
                    cache_mark = "💾" if message == "使用缓存" else "✅"
                    log_messages.append(f"{cache_mark} {message} {os.path.basename(image_path)} ({duration:.1f}s)")
                else:
                    log_messages.append(f"❌ 上传失败 {os.path.basename(image_path)}")
                
                # 更新进度
                with task_groups_lock:
                    task_groups[group_id]['upload_progress'] = f"{upload_completed}/{len(image_files)}"
                    task_groups[group_id]['log'] = log_messages.copy()
        
        if not upload_results:
            with task_groups_lock:
                task_groups[group_id]['status'] = "❌ 所有图像上传失败"
            return
        
        log_messages.append(f"✅ 上传完成: {len(upload_results)}/{len(image_files)}")
        
        # ========== 阶段2: 调用API ==========
        with task_groups_lock:
            task_groups[group_id]['status'] = "🍌 正在调用Banana API..."
        
        api_tasks = []
        task_id = 0
        for image_path, (cdn_url, upload_time) in upload_results.items():
            for prompt_idx, prompt in enumerate(prompts, 1):
                task_id += 1
                image_name = os.path.splitext(os.path.basename(image_path))[0]
                task_name = f"Task_{group_id[:8]}_{task_id}_{image_name}_p{prompt_idx}"
                api_tasks.append({
                    'task_id': task_id,
                    'cdn_url': cdn_url,
                    'prompt': prompt,
                    'task_name': task_name,
                    'upload_time': upload_time,
                    'source_image': image_path  # 添加源图像路径
                })
        
        total_api_tasks = len(api_tasks)
        api_results = []
        api_completed = 0
        
        with task_groups_lock:
            task_groups[group_id]['api_progress'] = f"0/{total_api_tasks}"
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            api_futures = {}
            
            for task in api_tasks:
                assigned_key = get_api_key_for_task(task['task_id'], all_api_keys)
                future = executor.submit(
                    call_banana_api,
                    task['task_id'],
                    task['cdn_url'],
                    task['prompt'],
                    assigned_key,
                    model,
                    aspect_ratio,
                    output_dir,  # 使用传入的输出目录
                    task['task_name'],
                    task['upload_time'],  # 传递上传时间
                    task['source_image'],  # 传递源图像路径
                    max_retries  # 传递重试次数
                )
                api_futures[future] = task
            
            for future in as_completed(api_futures):
                task = api_futures[future]
                task_id, success, message, output_file, duration, metadata = future.result()
                api_completed += 1
                
                api_results.append({
                    'task_id': task_id,
                    'success': success,
                    'output_file': output_file
                })
                
                if success and output_file:
                    # 添加到全局输出列表（包含元数据）
                    with all_output_files_lock:
                        all_output_files.append((output_file, metadata))
                    log_messages.append(f"✅ Task_{task_id}: {message} ({duration:.1f}s)")
                else:
                    log_messages.append(f"❌ Task_{task_id}: {message}")
                
                # 更新进度
                with task_groups_lock:
                    task_groups[group_id]['api_progress'] = f"{api_completed}/{total_api_tasks}"
                    task_groups[group_id]['log'] = log_messages.copy()
        
        # 统计结果
        success_count = sum(1 for r in api_results if r['success'])
        
        with task_groups_lock:
            task_groups[group_id]['status'] = f"✅ 完成: {success_count}/{total_api_tasks} 成功"
            task_groups[group_id]['log'] = log_messages
        
    except Exception as e:
        with task_groups_lock:
            task_groups[group_id]['status'] = f"❌ 异常: {str(e)}"
            task_groups[group_id]['log'].append(f"❌ 异常: {str(e)}")


def process_multi_group_async(
    group_id: str,
    page_images_dict: dict,  # {page_num: [image_paths]}
    prompts: List[str],
    all_api_keys: List[str],
    max_workers: int,
    model: str,
    aspect_ratio: str,
    max_retries: int,
    output_dir: str
):
    """多图分组模式：所有页面的图像组合成一个数组提交给API"""
    
    # 合并所有页面的图像
    all_images = []
    for page_num in sorted(page_images_dict.keys()):
        images = page_images_dict[page_num]
        if images:
            all_images.extend(images)
    
    if not all_images:
        with task_groups_lock:
            task_groups[group_id] = {
                'upload_progress': "0/0",
                'api_progress': "0/0",
                'status': "❌ 没有图像",
                'log': ["❌ 所有页面都没有图像"]
            }
        return
    
    total_images = len(all_images)
    
    # 初始化任务组状态
    with task_groups_lock:
        task_groups[group_id] = {
            'upload_progress': f"0/{total_images}",
            'api_progress': "0/0",
            'status': "📤 正在上传图像...",
            'log': []
        }
    
    try:
        log_messages = []
        log_messages.append(f"🚀 任务组 {group_id[:8]}: {total_images} 图像（来自{len(page_images_dict)}页）× {len(prompts)} 提示词")
        
        # ========== 阶段1: 上传所有图像 ==========
        
        upload_results = {}  # {image_path: (cdn_url, upload_time)}
        upload_completed = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            upload_futures = {}
            
            for idx, image_path in enumerate(all_images, 1):
                assigned_key = get_api_key_for_task(idx, all_api_keys)
                future = executor.submit(upload_single_image, idx, image_path, assigned_key)
                upload_futures[future] = image_path
            
            for future in as_completed(upload_futures):
                image_path = upload_futures[future]
                task_id, success, message, cdn_url, duration = future.result()
                upload_completed += 1
                
                if success:
                    upload_results[image_path] = (cdn_url, duration)
                    cache_mark = "💾" if message == "使用缓存" else "✅"
                    log_messages.append(f"{cache_mark} {message} {os.path.basename(image_path)} ({duration:.1f}s)")
                else:
                    log_messages.append(f"❌ 上传失败 {os.path.basename(image_path)}")
                
                with task_groups_lock:
                    task_groups[group_id]['upload_progress'] = f"{upload_completed}/{len(all_images)}"
                    task_groups[group_id]['log'] = log_messages.copy()
        
        if not upload_results:
            with task_groups_lock:
                task_groups[group_id]['status'] = "❌ 所有图像上传失败"
            return
        
        log_messages.append(f"✅ 上传完成: {len(upload_results)}/{len(all_images)}")
        
        # ========== 阶段2: 调用API（所有图像作为一组） ==========
        with task_groups_lock:
            task_groups[group_id]['status'] = "🍌 正在调用Banana API..."
        
        # 收集所有上传成功的图像URL
        all_cdn_urls = []
        all_source_images = []
        total_upload_time = 0
        
        for img_path in all_images:
            if img_path in upload_results:
                cdn_url, upload_time = upload_results[img_path]
                all_cdn_urls.append(cdn_url)
                all_source_images.append(img_path)
                total_upload_time += upload_time
        
        if not all_cdn_urls:
            with task_groups_lock:
                task_groups[group_id]['status'] = "❌ 所有图像上传失败"
            return
        
        avg_upload_time = total_upload_time / len(all_cdn_urls)
        
        # 为每个提示词创建任务（所有图像作为一组）
        api_tasks = []
        for prompt_idx, prompt in enumerate(prompts, 1):
            task_id = prompt_idx
            task_name = f"Task_{group_id[:8]}_{task_id}_multiimg{len(all_cdn_urls)}_p{prompt_idx}"
            api_tasks.append({
                'task_id': task_id,
                'cdn_urls': all_cdn_urls,  # 所有URL作为一个数组
                'source_images': all_source_images,  # 所有源图像
                'prompt': prompt,
                'task_name': task_name,
                'upload_time': avg_upload_time
            })
        
        total_api_tasks = len(api_tasks)
        api_results = []
        api_completed = 0
        
        with task_groups_lock:
            task_groups[group_id]['api_progress'] = f"0/{total_api_tasks}"
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            api_futures = {}
            
            for task in api_tasks:
                assigned_key = get_api_key_for_task(task['task_id'], all_api_keys)
                future = executor.submit(
                    call_banana_api_multi,  # 新的多图API调用函数
                    task['task_id'],
                    task['cdn_urls'],
                    task['prompt'],
                    assigned_key,
                    model,
                    aspect_ratio,
                    output_dir,
                    task['task_name'],
                    task['upload_time'],
                    task['source_images'],
                    max_retries
                )
                api_futures[future] = task
            
            for future in as_completed(api_futures):
                task = api_futures[future]
                task_id, success, message, output_file, duration, metadata = future.result()
                api_completed += 1
                
                api_results.append({
                    'task_id': task_id,
                    'success': success,
                    'output_file': output_file
                })
                
                if success and output_file:
                    with all_output_files_lock:
                        all_output_files.append((output_file, metadata))
                    log_messages.append(f"✅ Task_{task_id}: {message} ({duration:.1f}s)")
                else:
                    log_messages.append(f"❌ Task_{task_id}: {message}")
                
                with task_groups_lock:
                    task_groups[group_id]['api_progress'] = f"{api_completed}/{total_api_tasks}"
                    task_groups[group_id]['log'] = log_messages.copy()
        
        success_count = sum(1 for r in api_results if r['success'])
        
        with task_groups_lock:
            task_groups[group_id]['status'] = f"✅ 完成: {success_count}/{total_api_tasks} 成功"
            task_groups[group_id]['log'] = log_messages
        
    except Exception as e:
        with task_groups_lock:
            task_groups[group_id]['status'] = f"❌ 异常: {str(e)}"
            task_groups[group_id]['log'].append(f"❌ 异常: {str(e)}")


def process_flexible_combinations_async(
    group_id: str,
    combinations: List[List[str]],  # [[image_path1, image_path2], [image_path3], ...]
    prompts: List[str],
    all_api_keys: List[str],
    max_workers: int,
    model: str,
    aspect_ratio: str,
    max_retries: int,
    output_dir: str
):
    """处理灵活组合模式的任务"""
    
    total_combinations = len(combinations)
    all_images = []
    for combo in combinations:
        all_images.extend(combo)
    all_images = list(set(all_images))  # 去重
    
    # 初始化任务组状态
    with task_groups_lock:
        task_groups[group_id] = {
            'upload_progress': f"0/{len(all_images)}",
            'api_progress': "0/0",
            'status': "📤 正在上传图像...",
            'log': []
        }
    
    try:
        log_messages = []
        log_messages.append(f"🚀 任务组 {group_id[:8]}: {total_combinations} 个组合 × {len(prompts)} 提示词")
        
        # ========== 阶段1: 上传所有图像 ==========
        upload_results = {}  # {image_path: (cdn_url, upload_time)}
        upload_completed = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            upload_futures = {}
            
            for idx, image_path in enumerate(all_images, 1):
                assigned_key = get_api_key_for_task(idx, all_api_keys)
                future = executor.submit(upload_single_image, idx, image_path, assigned_key)
                upload_futures[future] = image_path
            
            for future in as_completed(upload_futures):
                image_path = upload_futures[future]
                task_id, success, message, cdn_url, duration = future.result()
                upload_completed += 1
                
                if success:
                    upload_results[image_path] = (cdn_url, duration)
                    cache_mark = "💾" if message == "使用缓存" else "✅"
                    log_messages.append(f"{cache_mark} {message} {os.path.basename(image_path)} ({duration:.1f}s)")
                else:
                    log_messages.append(f"❌ 上传失败 {os.path.basename(image_path)}")
                
                with task_groups_lock:
                    task_groups[group_id]['upload_progress'] = f"{upload_completed}/{len(all_images)}"
                    task_groups[group_id]['log'] = log_messages.copy()
        
        if not upload_results:
            with task_groups_lock:
                task_groups[group_id]['status'] = "❌ 所有图像上传失败"
            return
        
        log_messages.append(f"✅ 上传完成: {len(upload_results)}/{len(all_images)}")
        
        # ========== 阶段2: 调用API（每个组合） ==========
        with task_groups_lock:
            task_groups[group_id]['status'] = "🍌 正在调用Banana API..."
        
        api_tasks = []
        task_id = 0
        
        for combo_idx, combo_images in enumerate(combinations, 1):
            # 获取该组合的所有URL
            combo_urls = []
            combo_upload_times = []
            all_uploaded = True
            
            for img_path in combo_images:
                if img_path in upload_results:
                    cdn_url, upload_time = upload_results[img_path]
                    combo_urls.append(cdn_url)
                    combo_upload_times.append(upload_time)
                else:
                    all_uploaded = False
                    break
            
            if not all_uploaded or not combo_urls:
                continue
            
            avg_upload_time = sum(combo_upload_times) / len(combo_upload_times)
            
            # 为每个提示词创建任务
            for prompt_idx, prompt in enumerate(prompts, 1):
                task_id += 1
                task_name = f"Task_{group_id[:8]}_{task_id}_combo{combo_idx}_p{prompt_idx}"
                api_tasks.append({
                    'task_id': task_id,
                    'cdn_urls': combo_urls,
                    'source_images': combo_images,
                    'prompt': prompt,
                    'task_name': task_name,
                    'upload_time': avg_upload_time
                })
        
        total_api_tasks = len(api_tasks)
        api_results = []
        api_completed = 0
        
        with task_groups_lock:
            task_groups[group_id]['api_progress'] = f"0/{total_api_tasks}"
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            api_futures = {}
            
            for task in api_tasks:
                assigned_key = get_api_key_for_task(task['task_id'], all_api_keys)
                future = executor.submit(
                    call_banana_api_multi,
                    task['task_id'],
                    task['cdn_urls'],
                    task['prompt'],
                    assigned_key,
                    model,
                    aspect_ratio,
                    output_dir,
                    task['task_name'],
                    task['upload_time'],
                    task['source_images'],
                    max_retries
                )
                api_futures[future] = task
            
            for future in as_completed(api_futures):
                task = api_futures[future]
                task_id, success, message, output_file, duration, metadata = future.result()
                api_completed += 1
                
                api_results.append({
                    'task_id': task_id,
                    'success': success,
                    'output_file': output_file
                })
                
                if success and output_file:
                    with all_output_files_lock:
                        all_output_files.append((output_file, metadata))
                    log_messages.append(f"✅ Task_{task_id}: {message} ({duration:.1f}s)")
                else:
                    log_messages.append(f"❌ Task_{task_id}: {message}")
                
                with task_groups_lock:
                    task_groups[group_id]['api_progress'] = f"{api_completed}/{total_api_tasks}"
                    task_groups[group_id]['log'] = log_messages.copy()
        
        success_count = sum(1 for r in api_results if r['success'])
        
        with task_groups_lock:
            task_groups[group_id]['status'] = f"✅ 完成: {success_count}/{total_api_tasks} 成功"
            task_groups[group_id]['log'] = log_messages
        
    except Exception as e:
        with task_groups_lock:
            task_groups[group_id]['status'] = f"❌ 异常: {str(e)}"
            task_groups[group_id]['log'].append(f"❌ 异常: {str(e)}")


def call_banana_api_multi(task_id: int, cdn_urls: List[str], prompt: str, api_key: str, 
                         model: str, aspect_ratio: str, output_dir: str, 
                         task_name: str, upload_time: float, source_images: List[str],
                         max_retries: int = 3) -> Tuple[int, bool, str, Optional[str], float, dict]:
    """调用 Banana API 生成图像（多图输入版本）"""
    start_time = time.time()
    last_error = None
    
    for attempt in range(1, max_retries + 1):
        try:
            client = GrsaiAPI(api_key=api_key)
            pil_images, image_urls, errors = client.banana_generate_image(
                prompt=prompt,
                model=model,
                urls=cdn_urls,  # 传递多个URL
                aspect_ratio=aspect_ratio
            )
            
            if errors:
                last_error = f"API错误: {', '.join(errors)}"
                if attempt < max_retries:
                    time.sleep(1 * attempt)
                    continue
                elapsed = time.time() - start_time
                return task_id, False, f"{last_error} (重试{attempt}次后失败)", None, elapsed, {}
            
            if not pil_images:
                last_error = "未返回图像"
                if attempt < max_retries:
                    time.sleep(1 * attempt)
                    continue
                elapsed = time.time() - start_time
                return task_id, False, f"{last_error} (重试{attempt}次后失败)", None, elapsed, {}
            
            # 保存图像
            output_filename = f"{task_name}_1.png"
            output_path = os.path.join(output_dir, output_filename)
            pil_images[0].save(output_path)
            
            elapsed = time.time() - start_time
            
            # 创建元数据（多源图像）
            metadata = {
                'source_images': source_images,  # 列表
                'source_image_count': len(source_images),
                'prompt': prompt,
                'upload_time': upload_time,
                'api_time': elapsed,
                'total_time': upload_time + elapsed,
                'model': model,
                'aspect_ratio': aspect_ratio,
                'task_name': task_name,
                'cdn_urls': cdn_urls,
                'retry_attempts': attempt,
                'mode': 'multi-group'
            }
            
            with image_metadata_lock:
                image_metadata[output_path] = metadata
            
            success_msg = "生成成功" if attempt == 1 else f"生成成功(重试{attempt}次)"
            return task_id, True, success_msg, output_path, elapsed, metadata
            
        except Exception as e:
            last_error = f"API异常: {str(e)}"
            if attempt < max_retries:
                time.sleep(1 * attempt)
                continue
            else:
                elapsed = time.time() - start_time
                return task_id, False, f"{last_error} (重试{attempt}次后失败)", None, elapsed, {}


def batch_generate(
    images,
    prompts_text: str,
    main_api_key: str,
    backup_api_keys: str,
    use_multiple_accounts: bool,
    max_workers: int,
    model: str,
    aspect_ratio: str,
    max_retries: int,
    output_dir: str
):
    """立即提交任务组并返回"""
    
    # 验证输入
    if not images:
        return "❌ 请上传至少一张图像", None, ""
    
    if not prompts_text.strip():
        return "❌ 请输入提示词", None, ""
    
    if not main_api_key.strip():
        return "❌ 请输入主API密钥", None, ""
    
    # 验证并创建输出目录
    if not output_dir or not output_dir.strip():
        output_dir = OUTPUT_DIR
    else:
        output_dir = output_dir.strip()
    
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        return f"❌ 无法创建输出目录: {str(e)}", None, ""
    
    # 解析提示词
    prompts = [line.strip() for line in prompts_text.strip().split('\n') if line.strip()]
    if not prompts:
        return "❌ 请输入有效的提示词", None, ""
    
    # 准备API密钥列表
    all_api_keys = [main_api_key.strip()]
    if use_multiple_accounts and backup_api_keys.strip():
        backup_keys = [k.strip() for k in backup_api_keys.strip().split('\n') if k.strip()]
        all_api_keys.extend(backup_keys)
    
    # 生成任务组ID
    group_id = str(uuid.uuid4())
    
    # 在后台线程中启动任务处理
    thread = threading.Thread(
        target=process_task_group_async,
        args=(
            group_id,
            images,
            prompts,
            all_api_keys,
            max_workers,
            model,
            aspect_ratio,
            max_retries,
            output_dir  # 传递输出目录
        ),
        daemon=True
    )
    thread.start()
    
    # 立即返回
    image_count = len(images) if isinstance(images, list) else 1
    total_tasks = image_count * len(prompts)
    
    return (
        f"✅ 已提交任务组 {group_id[:8]}\n📊 {image_count} 图像 × {len(prompts)} 提示词 = {total_tasks} 任务\n⚡ 并发数: {max_workers} | 🔑 {len(all_api_keys)} 个账号\n上传: 0/{image_count} | API: 0/{total_tasks}",
        gr.update(),  # 保持图库不变，不清空
        f"任务组 {group_id[:8]} 已提交，正在后台执行..."
    )


def calculate_image_combinations(pages_data):
    """
    计算所有可能的图像组合
    
    Args:
        pages_data: [(images_list, mode), ...] 每页的图像列表和组合模式
    
    Returns:
        combinations: [([url1, url2, ...], metadata), ...] 所有可能的URL组合
    """
    from itertools import product
    
    # 过滤出有图像的页面
    valid_pages = [(imgs, mode) for imgs, mode in pages_data if imgs]
    
    if not valid_pages:
        return []
    
    # 为每个页面准备可能的组合
    page_combinations = []
    for images, mode in valid_pages:
        if mode == "相乘":
            # 相乘：每张图作为一个单独的选项
            page_combinations.append([[img] for img in images])
        else:  # 相加
            # 相加：所有图像作为一个整体
            page_combinations.append([images])
    
    # 计算笛卡尔积
    all_combinations = []
    for combo in product(*page_combinations):
        # combo是一个元组，每个元素是一个图像列表
        # 合并所有列表
        merged = []
        for img_list in combo:
            merged.extend(img_list)
        all_combinations.append(merged)
    
    return all_combinations


def batch_generate_flexible(
    # 每页的图像和模式
    page1_images, page1_mode,
    page2_images, page2_mode,
    page3_images, page3_mode,
    page4_images, page4_mode,
    page5_images, page5_mode,
    # 公共参数
    prompts_text: str,
    main_api_key: str,
    backup_api_keys: str,
    use_multiple_accounts: bool,
    max_workers: int,
    model: str,
    aspect_ratio: str,
    max_retries: int,
    output_dir: str,
    # 确认状态
    confirmed: bool
):
    """灵活组合模式的生成函数"""
    
    # 验证提示词
    if not prompts_text.strip():
        return "❌ 请输入提示词", None, "", False
    
    if not main_api_key.strip():
        return "❌ 请输入主API密钥", None, "", False
    
    # 验证并创建输出目录
    if not output_dir or not output_dir.strip():
        output_dir = OUTPUT_DIR
    else:
        output_dir = output_dir.strip()
    
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        return f"❌ 无法创建输出目录: {str(e)}", None, "", False
    
    # 解析提示词
    prompts = [line.strip() for line in prompts_text.strip().split('\n') if line.strip()]
    if not prompts:
        return "❌ 请输入有效的提示词", None, "", False
    
    # 收集所有页面数据
    pages_data = [
        (page1_images if page1_images else [], page1_mode),
        (page2_images if page2_images else [], page2_mode),
        (page3_images if page3_images else [], page3_mode),
        (page4_images if page4_images else [], page4_mode),
        (page5_images if page5_images else [], page5_mode),
    ]
    
    # 计算所有图像组合
    combinations = calculate_image_combinations(pages_data)
    
    if not combinations:
        return "❌ 请至少上传一张图像", None, "", False
    
    # 计算任务数
    total_combinations = len(combinations)
    total_tasks = total_combinations * len(prompts)
    
    # 检查是否需要二次确认（2个以上相乘页面）
    multiply_count = sum(1 for imgs, mode in pages_data if imgs and mode == "相乘")
    
    if multiply_count >= 2 and not confirmed:
        # 需要二次确认
        return (
            f"⚠️ 检测到{multiply_count}个相乘页面\n📊 将生成 {total_combinations} 个组合 × {len(prompts)} 个提示词 = {total_tasks} 个任务\n\n请再次点击【开始生成】确认执行",
            None,
            "等待确认...",
            True  # 设置确认状态为 True
        )
    
    # 准备API密钥列表
    all_api_keys = [main_api_key.strip()]
    if use_multiple_accounts and backup_api_keys.strip():
        backup_keys = [k.strip() for k in backup_api_keys.strip().split('\n') if k.strip()]
        all_api_keys.extend(backup_keys)
    
    # 生成任务组ID
    group_id = str(uuid.uuid4())
    
    # 启动后台任务（传递组合列表）
    thread = threading.Thread(
        target=process_flexible_combinations_async,
        args=(
            group_id,
            combinations,
            prompts,
            all_api_keys,
            max_workers,
            model,
            aspect_ratio,
            max_retries,
            output_dir
        ),
        daemon=True
    )
    thread.start()
    
    return (
        f"✅ 已提交任务组 {group_id[:8]}\n📊 {total_combinations} 个组合 × {len(prompts)} 个提示词 = {total_tasks} 个任务\n⚡ 并发数: {max_workers} | 🔑 {len(all_api_keys)} 个账号",
        gr.update(),
        f"任务组 {group_id[:8]} 已提交，正在后台执行...",
        False  # 重置确认状态
    )


def batch_generate_unified(
    mode: str,
    # 单图模式参数
    single_images,
    # 多图分组模式参数
    page1_images,
    page2_images,
    page3_images,
    page4_images,
    page5_images,
    # 公共参数
    prompts_text: str,
    main_api_key: str,
    backup_api_keys: str,
    use_multiple_accounts: bool,
    max_workers: int,
    model: str,
    aspect_ratio: str,
    max_retries: int,
    output_dir: str
):
    """统一的生成函数：根据模式调用不同的处理逻辑"""
    
    # 验证提示词
    if not prompts_text.strip():
        return "❌ 请输入提示词", None, ""
    
    if not main_api_key.strip():
        return "❌ 请输入主API密钥", None, ""
    
    # 验证并创建输出目录
    if not output_dir or not output_dir.strip():
        output_dir = OUTPUT_DIR
    else:
        output_dir = output_dir.strip()
    
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        return f"❌ 无法创建输出目录: {str(e)}", None, ""
    
    # 解析提示词
    prompts = [line.strip() for line in prompts_text.strip().split('\n') if line.strip()]
    if not prompts:
        return "❌ 请输入有效的提示词", None, ""
    
    # 准备API密钥列表
    all_api_keys = [main_api_key.strip()]
    if use_multiple_accounts and backup_api_keys.strip():
        backup_keys = [k.strip() for k in backup_api_keys.strip().split('\n') if k.strip()]
        all_api_keys.extend(backup_keys)
    
    # 生成任务组ID
    group_id = str(uuid.uuid4())
    
    if mode == "单图模式":
        # 单图模式
        if not single_images:
            return "❌ 请上传至少一张图像", None, ""
        
        thread = threading.Thread(
            target=process_task_group_async,
            args=(
                group_id,
                single_images,
                prompts,
                all_api_keys,
                max_workers,
                model,
                aspect_ratio,
                max_retries,
                output_dir
            ),
            daemon=True
        )
        thread.start()
        
        image_count = len(single_images) if isinstance(single_images, list) else 1
        total_tasks = image_count * len(prompts)
        
        return (
            f"✅ [单图模式] 已提交任务组 {group_id[:8]}\n📊 {image_count} 图像 × {len(prompts)} 提示词 = {total_tasks} 任务\n⚡ 并发数: {max_workers} | 🔑 {len(all_api_keys)} 个账号",
            gr.update(),
            f"任务组 {group_id[:8]} 已提交，正在后台执行..."
        )
    
    else:
        # 多图分组模式
        page_images_dict = {}
        if page1_images:
            page_images_dict[1] = page1_images
        if page2_images:
            page_images_dict[2] = page2_images
        if page3_images:
            page_images_dict[3] = page3_images
        if page4_images:
            page_images_dict[4] = page4_images
        if page5_images:
            page_images_dict[5] = page5_images
        
        if not page_images_dict:
            return "❌ 请至少在一个页面上传图像", None, ""
        
        thread = threading.Thread(
            target=process_multi_group_async,
            args=(
                group_id,
                page_images_dict,
                prompts,
                all_api_keys,
                max_workers,
                model,
                aspect_ratio,
                max_retries,
                output_dir
            ),
            daemon=True
        )
        thread.start()
        
        total_pages = len(page_images_dict)
        total_images = sum(len(imgs) for imgs in page_images_dict.values() if imgs)
        total_tasks = len(prompts)  # 只有提示词数量的任务
        
        return (
            f"✅ [多图分组模式] 已提交任务组 {group_id[:8]}\n📊 {total_images} 图像（{total_pages}页）× {len(prompts)} 提示词 = {total_tasks} 任务\n⚡ 并发数: {max_workers} | 🔑 {len(all_api_keys)} 个账号\n💡 所有图像将组合成一个数组提交",
            gr.update(),
            f"任务组 {group_id[:8]} 已提交，正在后台执行..."
        )


def get_current_status():
    """获取所有任务组的当前状态"""
    status_lines = []
    
    with task_groups_lock:
        if not task_groups:
            return "暂无任务", None, ""
        
        # 统计所有任务组（显示最近3个）
        for group_id, info in list(task_groups.items())[-3:]:
            status_lines.append(f"[{group_id[:8]}] {info['status']}")
            status_lines.append(f"上传: {info['upload_progress']} | API: {info['api_progress']}")
    
    # 获取所有输出文件（包含元数据）
    with all_output_files_lock:
        output_files_with_metadata = all_output_files.copy()
    
    # 构建带标题的图像列表（简化标题）
    # Gradio Gallery 格式: [(图像路径, 标题), ...]
    gallery_images = []
    for file_path, metadata in output_files_with_metadata:
        if metadata:
            upload_time = metadata.get('upload_time', 0)
            api_time = metadata.get('api_time', 0)
            total_time = metadata.get('total_time', 0)
            
            # 简化标题：只显示时间
            caption = f"上传: {upload_time:.1f}s | API: {api_time:.1f}s | 总计: {total_time:.1f}s"
            
            gallery_images.append((file_path, caption))
        else:
            gallery_images.append((file_path, ""))
    
    # 获取最后一个任务组的日志
    with task_groups_lock:
        if task_groups:
            last_log = list(task_groups.values())[-1].get('log', [])
            log_text = "\n".join(last_log[-50:])  # 最后50行
        else:
            log_text = ""
    
    return (
        "\n".join(status_lines),
        gallery_images if gallery_images else None,
        log_text
    )


# 创建 Gradio 界面
with gr.Blocks(title="Banana 图像生成", theme=gr.themes.Soft()) as demo:
    # 标题栏（带输出目录设置）
    with gr.Row():
        with gr.Column(scale=3):
            gr.Markdown("# 🍌 Banana 图像生成 WebUI")
        with gr.Column(scale=1):
            output_dir_input = gr.Textbox(
                label="📁 输出目录",
                value=os.path.join(os.path.dirname(__file__), "outputs"),
                placeholder="输入保存目录路径",
                scale=1
            )
    
    # 自动刷新定时器（每2秒）
    auto_refresh = gr.Timer(value=2)
    
    # 低频配置区（折叠）
    with gr.Accordion("⚙️ 配置（API、模型、并发参数）", open=False):
        with gr.Row():
            main_key_input = gr.Textbox(
                label="主API密钥",
                value=DEFAULT_API_KEY,
                type="password",
                scale=2
            )
            
            use_multi_acc = gr.Checkbox(
                label="启用多账户",
                value=False,
                scale=1
            )
        
        backup_keys_input = gr.Textbox(
            label="备用API密钥（每行一个）",
            value=DEFAULT_BACKUP_KEYS,
            lines=2,
            visible=False
        )
        
        with gr.Row():
            workers_input = gr.Slider(
                label="并发数",
                minimum=1,
                maximum=20,
                value=10,
                step=1
            )
            
            retries_input = gr.Slider(
                label="最大重试次数",
                minimum=1,
                maximum=5,
                value=3,
                step=1
            )
        
        with gr.Row():
            model_input = gr.Dropdown(
                label="模型",
                choices=["nano-banana-fast", "nano-banana"],
                value="nano-banana-fast"
            )
            
            aspect_ratio_input = gr.Dropdown(
                label="宽高比",
                choices=["auto", "1:1", "16:9", "9:16", "4:3", "3:4"],
                value="auto"
            )
    
    # 多账户切换显示备用密钥输入框
    def toggle_backup_keys(use_multi):
        return gr.update(visible=use_multi)
    
    use_multi_acc.change(
        toggle_backup_keys,
        inputs=[use_multi_acc],
        outputs=[backup_keys_input]
    )
    
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 📤 图像上传与组合")
            
            # 多页面图像上传区域
            with gr.Tabs() as image_tabs:
                # 页面1（默认相乘）
                with gr.Tab("📄 页面1", id=1) as tab1:
                    with gr.Row():
                        page1_mode = gr.Radio(
                            choices=["相乘", "相加"],
                            value="相乘",
                            label="🔧 组合方式",
                            info="相乘：每张图单独 | 相加：合并为一组"
                        )
                    page1_upload = gr.File(
                        label="上传图像到页面1",
                        file_count="multiple",
                        file_types=["image"],
                        type="filepath",
                        height=100
                    )
                    page1_gallery = gr.Gallery(
                        label="页面1 - 已上传图像",
                        columns=4,
                        rows=2,
                        height=300,
                        object_fit="scale-down"
                    )
                    with gr.Row():
                        page1_delete_btn = gr.Button("❌ 删除所选", size="sm")
                        page1_clear_btn = gr.Button("🗑️ 清空", size="sm")
                
                # 页面2（默认相加）
                with gr.Tab("📄 页面2", id=2) as tab2:
                    with gr.Row():
                        page2_mode = gr.Radio(
                            choices=["相乘", "相加"],
                            value="相加",
                            label="🔧 组合方式",
                            info="相乘：每张图单独 | 相加：合并为一组"
                        )
                    page2_upload = gr.File(
                        label="上传图像到页面2",
                        file_count="multiple",
                        file_types=["image"],
                        type="filepath",
                        height=100
                    )
                    page2_gallery = gr.Gallery(
                        label="页面2 - 已上传图像",
                        columns=4,
                        rows=2,
                        height=300,
                        object_fit="scale-down"
                    )
                    with gr.Row():
                        page2_delete_btn = gr.Button("❌ 删除所选", size="sm")
                        page2_clear_btn = gr.Button("🗑️ 清空", size="sm")
                
                # 页面3（默认相加）
                with gr.Tab("📄 页面3", id=3) as tab3:
                    with gr.Row():
                        page3_mode = gr.Radio(
                            choices=["相乘", "相加"],
                            value="相加",
                            label="🔧 组合方式",
                            info="相乘：每张图单独 | 相加：合并为一组"
                        )
                    page3_upload = gr.File(
                        label="上传图像到页面3",
                        file_count="multiple",
                        file_types=["image"],
                        type="filepath",
                        height=100
                    )
                    page3_gallery = gr.Gallery(
                        label="页面3 - 已上传图像",
                        columns=4,
                        rows=2,
                        height=300,
                        object_fit="scale-down"
                    )
                    with gr.Row():
                        page3_delete_btn = gr.Button("❌ 删除所选", size="sm")
                        page3_clear_btn = gr.Button("🗑️ 清空", size="sm")
                
                # 页面4（默认相加）
                with gr.Tab("📄 页面4", id=4) as tab4:
                    with gr.Row():
                        page4_mode = gr.Radio(
                            choices=["相乘", "相加"],
                            value="相加",
                            label="🔧 组合方式",
                            info="相乘：每张图单独 | 相加：合并为一组"
                        )
                    page4_upload = gr.File(
                        label="上传图像到页面4",
                        file_count="multiple",
                        file_types=["image"],
                        type="filepath",
                        height=100
                    )
                    page4_gallery = gr.Gallery(
                        label="页面4 - 已上传图像",
                        columns=4,
                        rows=2,
                        height=300,
                        object_fit="scale-down"
                    )
                    with gr.Row():
                        page4_delete_btn = gr.Button("❌ 删除所选", size="sm")
                        page4_clear_btn = gr.Button("🗑️ 清空", size="sm")
                
                # 页面5（默认相加）
                with gr.Tab("📄 页面5", id=5) as tab5:
                    with gr.Row():
                        page5_mode = gr.Radio(
                            choices=["相乘", "相加"],
                            value="相加",
                            label="🔧 组合方式",
                            info="相乘：每张图单独 | 相加：合并为一组"
                        )
                    page5_upload = gr.File(
                        label="上传图像到页面5",
                        file_count="multiple",
                        file_types=["image"],
                        type="filepath",
                        height=100
                    )
                    page5_gallery = gr.Gallery(
                        label="页面5 - 已上传图像",
                        columns=4,
                        rows=2,
                        height=300,
                        object_fit="scale-down"
                    )
                    with gr.Row():
                        page5_delete_btn = gr.Button("❌ 删除所选", size="sm")
                        page5_clear_btn = gr.Button("🗑️ 清空", size="sm")
            
            # 任务数预估
            with gr.Row():
                task_estimate = gr.Textbox(
                    label="📊 预估任务数",
                    value="等待上传图像...",
                    interactive=False,
                    scale=1
                )
            
            # 隐藏的确认状态（用于二次确认逻辑）
            confirmation_state = gr.State(value=False)
            
            # ========== 提示词区域（独立，两种模式共享） ==========
            prompts_input = gr.Textbox(
                label="📝 提示词（每行一个）",
                placeholder="换一个自然休闲优雅的pose，保持面无表情\n换成坐姿，表情微笑，眼神看向镜头",
                lines=6
            )
            
            # 操作按钮
            with gr.Row():
                generate_btn = gr.Button("🚀 开始生成", variant="primary", size="lg")
                refresh_btn = gr.Button("🔄 刷新状态", variant="secondary")
            
            with gr.Row():
                clear_cache_btn = gr.Button("🗑️ 清空上传缓存", variant="secondary", size="sm")
        
        with gr.Column(scale=1):
            gr.Markdown("### 📊 输出结果")
            
            # 结果摘要（包含进度信息）
            summary_output = gr.Textbox(
                label="任务状态",
                lines=3
            )
            
            # 生成的图像
            gallery_output = gr.Gallery(
                label="生成的图像（点击查看详情）",
                columns=4,
                rows=2,
                height=400,
                object_fit="contain"
            )
            
            # 选中图像的信息和操作
            with gr.Row():
                image_info = gr.Textbox(
                    label="图像信息（点击图像查看）",
                    lines=6,
                    interactive=False,
                    value="请点击上方图像查看详情"
                )
            
            with gr.Row():
                redo_selected_btn = gr.Button("🔄 重做此图", variant="primary", scale=1)
                refill_selected_btn = gr.Button("📋 重排此图", variant="secondary", scale=1)
                clear_output_btn = gr.Button("🗑️", variant="secondary", scale=0, min_width=50)
            
            # 详细日志
            with gr.Accordion("📝 详细日志", open=False):
                log_output = gr.Textbox(
                    label="处理日志",
                    lines=20,
                    max_lines=30
                )
    
    # 隐藏状态
    selected_image_path = gr.State(None)
    selected_preview_index = gr.State(None)  # 记录预览选中的索引
    
    # 多图分组模式状态
    page1_files = gr.State([])  # 页面1的图像列表
    page2_files = gr.State([])  # 页面2的图像列表
    page3_files = gr.State([])  # 页面3的图像列表
    page4_files = gr.State([])  # 页面4的图像列表
    page5_files = gr.State([])  # 页面5的图像列表
    page1_selected_idx = gr.State(None)
    page2_selected_idx = gr.State(None)
    page3_selected_idx = gr.State(None)
    page4_selected_idx = gr.State(None)
    page5_selected_idx = gr.State(None)
    
    # 预估任务数计算函数
    def calculate_task_estimate(
        p1_imgs, p1_mode, p2_imgs, p2_mode, p3_imgs, p3_mode,
        p4_imgs, p4_mode, p5_imgs, p5_mode, prompts_text
    ):
        """实时计算预估任务数"""
        pages_data = [
            (p1_imgs if p1_imgs else [], p1_mode),
            (p2_imgs if p2_imgs else [], p2_mode),
            (p3_imgs if p3_imgs else [], p3_mode),
            (p4_imgs if p4_imgs else [], p4_mode),
            (p5_imgs if p5_imgs else [], p5_mode),
        ]
        
        combinations = calculate_image_combinations(pages_data)
        
        if not combinations:
            return "等待上传图像..."
        
        prompts = [line.strip() for line in prompts_text.strip().split('\n') if line.strip()]
        prompt_count = len(prompts) if prompts else 1
        
        total_combos = len(combinations)
        total_tasks = total_combos * prompt_count
        
        # 检查相乘页面数
        multiply_count = sum(1 for imgs, mode in pages_data if imgs and mode == "相乘")
        
        if multiply_count >= 2:
            warning = f"⚠️ {multiply_count}个相乘页面 | "
        else:
            warning = ""
        
        return f"{warning}{total_combos} 组合 × {prompt_count} 提示词 = {total_tasks} 任务"
    
    # 添加图像到列表（追加模式）
    def add_images(existing_files, new_files):
        """追加新图像到列表"""
        if existing_files is None:
            existing_files = []
        
        if not new_files:
            return existing_files, existing_files, None
        
        # 处理新上传的文件
        for f in new_files:
            file_path = None
            if isinstance(f, str):
                file_path = f
            elif hasattr(f, 'name'):
                file_path = f.name
            
            # 避免重复
            if file_path and file_path not in existing_files:
                existing_files.append(file_path)
        
        # 返回：更新状态，更新预览，清空输入框（允许继续上传）
        return existing_files, existing_files, None
    
    def clear_all_images():
        """清空所有图像"""
        return [], [], None
    
    def on_preview_select(evt: gr.SelectData, files_list):
        """记录预览中选中的图像索引"""
        if evt.index is not None and files_list and evt.index < len(files_list):
            return evt.index
        return None
    
    def delete_selected_from_preview(selected_idx, files_list):
        """删除预览中选中的图像，并智能更新选中索引"""
        if selected_idx is None or not files_list or selected_idx >= len(files_list):
            return files_list, files_list, None
        
        # 删除选中的图像
        new_list = files_list[:selected_idx] + files_list[selected_idx + 1:]
        
        # 智能更新选中索引：
        # 如果删除后还有图像，选中下一张（或最后一张）
        if new_list:
            # 如果删除的不是最后一张，保持当前索引（指向下一张）
            # 如果删除的是最后一张，选中新的最后一张
            new_selected_idx = selected_idx if selected_idx < len(new_list) else len(new_list) - 1
        else:
            # 列表为空，清空选中
            new_selected_idx = None
        
        return new_list, new_list, new_selected_idx
    
    # ========== 多页面图像管理函数 ==========
    def add_images_to_page(existing_files, new_files):
        """为某个页面添加图像"""
        if existing_files is None:
            existing_files = []
        
        if not new_files:
            return existing_files, existing_files, None
        
        for f in new_files:
            file_path = None
            if isinstance(f, str):
                file_path = f
            elif hasattr(f, 'name'):
                file_path = f.name
            
            if file_path and file_path not in existing_files:
                existing_files.append(file_path)
        
        return existing_files, existing_files, None
    
    def clear_page_images():
        """清空某页的所有图像"""
        return [], [], None
    
    def on_page_select(evt: gr.SelectData, files_list):
        """记录页面中选中的图像索引"""
        if evt.index is not None and files_list and evt.index < len(files_list):
            return evt.index
        return None
    
    def delete_selected_from_page(selected_idx, files_list):
        """从页面删除选中的图像"""
        if selected_idx is None or not files_list or selected_idx >= len(files_list):
            return files_list, files_list, None
        
        new_list = files_list[:selected_idx] + files_list[selected_idx + 1:]
        
        if new_list:
            new_selected_idx = selected_idx if selected_idx < len(new_list) else len(new_list) - 1
        else:
            new_selected_idx = None
        
        return new_list, new_list, new_selected_idx
    
    # ========== 多图分组模式事件绑定 ==========
    # 页面1
    page1_upload.upload(
        fn=add_images_to_page,
        inputs=[page1_files, page1_upload],
        outputs=[page1_files, page1_gallery, page1_upload]
    )
    
    page1_gallery.select(
        fn=on_page_select,
        inputs=[page1_files],
        outputs=[page1_selected_idx]
    )
    
    page1_delete_btn.click(
        fn=delete_selected_from_page,
        inputs=[page1_selected_idx, page1_files],
        outputs=[page1_files, page1_gallery, page1_selected_idx]
    )
    
    page1_clear_btn.click(
        fn=clear_page_images,
        outputs=[page1_files, page1_gallery, page1_upload]
    )
    
    # 页面2
    page2_upload.upload(
        fn=add_images_to_page,
        inputs=[page2_files, page2_upload],
        outputs=[page2_files, page2_gallery, page2_upload]
    )
    
    page2_gallery.select(
        fn=on_page_select,
        inputs=[page2_files],
        outputs=[page2_selected_idx]
    )
    
    page2_delete_btn.click(
        fn=delete_selected_from_page,
        inputs=[page2_selected_idx, page2_files],
        outputs=[page2_files, page2_gallery, page2_selected_idx]
    )
    
    page2_clear_btn.click(
        fn=clear_page_images,
        outputs=[page2_files, page2_gallery, page2_upload]
    )
    
    # 页面3
    page3_upload.upload(
        fn=add_images_to_page,
        inputs=[page3_files, page3_upload],
        outputs=[page3_files, page3_gallery, page3_upload]
    )
    
    page3_gallery.select(
        fn=on_page_select,
        inputs=[page3_files],
        outputs=[page3_selected_idx]
    )
    
    page3_delete_btn.click(
        fn=delete_selected_from_page,
        inputs=[page3_selected_idx, page3_files],
        outputs=[page3_files, page3_gallery, page3_selected_idx]
    )
    
    page3_clear_btn.click(
        fn=clear_page_images,
        outputs=[page3_files, page3_gallery, page3_upload]
    )
    
    # 页面4
    page4_upload.upload(
        fn=add_images_to_page,
        inputs=[page4_files, page4_upload],
        outputs=[page4_files, page4_gallery, page4_upload]
    )
    
    page4_gallery.select(
        fn=on_page_select,
        inputs=[page4_files],
        outputs=[page4_selected_idx]
    )
    
    page4_delete_btn.click(
        fn=delete_selected_from_page,
        inputs=[page4_selected_idx, page4_files],
        outputs=[page4_files, page4_gallery, page4_selected_idx]
    )
    
    page4_clear_btn.click(
        fn=clear_page_images,
        outputs=[page4_files, page4_gallery, page4_upload]
    )
    
    # 页面5
    page5_upload.upload(
        fn=add_images_to_page,
        inputs=[page5_files, page5_upload],
        outputs=[page5_files, page5_gallery, page5_upload]
    )
    
    page5_gallery.select(
        fn=on_page_select,
        inputs=[page5_files],
        outputs=[page5_selected_idx]
    )
    
    page5_delete_btn.click(
        fn=delete_selected_from_page,
        inputs=[page5_selected_idx, page5_files],
        outputs=[page5_files, page5_gallery, page5_selected_idx]
    )
    
    page5_clear_btn.click(
        fn=clear_page_images,
        outputs=[page5_files, page5_gallery, page5_upload]
    )
    
    # ========== 实时任务数预估 ==========
    # 绑定所有影响任务数的输入
    for page_files, page_mode in [
        (page1_files, page1_mode), (page2_files, page2_mode),
        (page3_files, page3_mode), (page4_files, page4_mode),
        (page5_files, page5_mode)
    ]:
        page_files.change(
            fn=calculate_task_estimate,
            inputs=[
                page1_files, page1_mode, page2_files, page2_mode,
                page3_files, page3_mode, page4_files, page4_mode,
                page5_files, page5_mode, prompts_input
            ],
            outputs=[task_estimate]
        )
        page_mode.change(
            fn=calculate_task_estimate,
            inputs=[
                page1_files, page1_mode, page2_files, page2_mode,
                page3_files, page3_mode, page4_files, page4_mode,
                page5_files, page5_mode, prompts_input
            ],
            outputs=[task_estimate]
        )
    
    prompts_input.change(
        fn=calculate_task_estimate,
        inputs=[
            page1_files, page1_mode, page2_files, page2_mode,
            page3_files, page3_mode, page4_files, page4_mode,
            page5_files, page5_mode, prompts_input
        ],
        outputs=[task_estimate]
    )
    
    # ========== 生成按钮事件 ==========
    generate_btn.click(
        fn=batch_generate_flexible,
        inputs=[
            # 每页的图像和模式
            page1_files, page1_mode,
            page2_files, page2_mode,
            page3_files, page3_mode,
            page4_files, page4_mode,
            page5_files, page5_mode,
            # 公共参数
            prompts_input,
            main_key_input,
            backup_keys_input,
            use_multi_acc,
            workers_input,
            model_input,
            aspect_ratio_input,
            retries_input,
            output_dir_input,
            # 确认状态
            confirmation_state
        ],
        outputs=[
            summary_output, 
            gallery_output,
            log_output,
            confirmation_state  # 更新确认状态
        ]
    )
    
    # 刷新按钮（手动刷新）
    refresh_btn.click(
        fn=get_current_status,
        outputs=[summary_output, gallery_output, log_output]
    )
    
    # 自动刷新（每2秒触发一次）
    auto_refresh.tick(
        fn=get_current_status,
        outputs=[summary_output, gallery_output, log_output]
    )
    
    # 清空上传缓存
    def clear_upload_cache():
        """清空上传URL缓存"""
        with upload_cache_lock:
            count = len(upload_cache)
            upload_cache.clear()
        return f"✅ 已清空 {count} 个缓存的上传URL"
    
    clear_cache_btn.click(
        fn=clear_upload_cache,
        outputs=[summary_output]
    )
    
    # 图库选择事件：点击图像显示详情
    def on_select_image(evt: gr.SelectData):
        """当用户点击图库中的图像时"""
        if evt.index is not None and all_output_files:
            if evt.index < len(all_output_files):
                file_path, metadata = all_output_files[evt.index]
                
                # 判断是单图还是多图模式
                mode = metadata.get('mode', 'single')
                
                if mode == 'multi-group':
                    # 多图模式
                    source_images = metadata.get('source_images', [])
                    source_names = [os.path.basename(img) for img in source_images]
                    info_text = f"""🔢 模式: 多图分组
📸 源图像 ({len(source_images)}张):
   {', '.join(source_names)}
📝 提示词: {metadata.get('prompt', 'N/A')}
🤖 模型: {metadata.get('model', 'N/A')}
📐 宽高比: {metadata.get('aspect_ratio', 'N/A')}
⏱️ 上传耗时: {metadata.get('upload_time', 0):.1f}秒
⏱️ API耗时: {metadata.get('api_time', 0):.1f}秒
⏱️ 总耗时: {metadata.get('total_time', 0):.1f}秒"""
                else:
                    # 单图模式
                    info_text = f"""🔢 模式: 单图
📸 源图像: {os.path.basename(metadata.get('source_image', 'N/A'))}
📝 提示词: {metadata.get('prompt', 'N/A')}
🤖 模型: {metadata.get('model', 'N/A')}
📐 宽高比: {metadata.get('aspect_ratio', 'N/A')}
⏱️ 上传耗时: {metadata.get('upload_time', 0):.1f}秒
⏱️ API耗时: {metadata.get('api_time', 0):.1f}秒
⏱️ 总耗时: {metadata.get('total_time', 0):.1f}秒"""
                
                return info_text, file_path
        return "未选择图像", None
    
    gallery_output.select(
        fn=on_select_image,
        outputs=[image_info, selected_image_path]
    )
    
    # 重做选中图像
    def redo_selected_image(image_path, main_key, backup_keys, use_multi, workers, retries, output_dir):
        """重做选中的图像，使用相同的参数重新生成"""
        if not image_path or image_path not in image_metadata:
            return "❌ 未选择有效图像", None, "❌ 未选择有效图像"
        
        # 获取元数据
        metadata = image_metadata[image_path]
        source_images = metadata.get('source_images', [])
        prompt = metadata.get('prompt', '')
        model = metadata.get('model', 'flux1-dev-fp8')
        aspect_ratio = metadata.get('aspect_ratio', '1:1')
        
        # 验证源图像
        valid_images = [img for img in source_images if os.path.exists(img)]
        if not valid_images:
            return "❌ 源图像文件不存在", None, "❌ 源图像文件不存在"
        
        if not prompt:
            return "❌ 未找到提示词信息", None, "❌ 未找到提示词信息"
        
        if not main_key.strip():
            return "❌ 请输入主API密钥", None, "❌ 请输入主API密钥"
        
        # 验证输出目录
        if not output_dir or not output_dir.strip():
            output_dir = OUTPUT_DIR
        else:
            output_dir = output_dir.strip()
        
        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception as e:
            return f"❌ 无法创建输出目录: {str(e)}", None, f"❌ 无法创建输出目录: {str(e)}"
        
        # 准备API密钥
        all_api_keys = [main_key.strip()]
        if use_multi and backup_keys.strip():
            backup_list = [k.strip() for k in backup_keys.strip().split('\n') if k.strip()]
            all_api_keys.extend(backup_list)
        
        # 生成任务组ID
        group_id = str(uuid.uuid4())
        
        # 创建组合（单个组合，包含所有源图像）
        combinations = [valid_images]
        prompts = [prompt]
        
        # 启动后台任务
        thread = threading.Thread(
            target=process_flexible_combinations_async,
            args=(
                group_id,
                combinations,
                prompts,
                all_api_keys,
                workers,
                model,
                aspect_ratio,
                retries,
                output_dir
            ),
            daemon=True
        )
        thread.start()
        
        return (
            f"✅ 已提交重做任务 {group_id[:8]}\n📷 源图: {len(valid_images)} 张\n💬 提示词: {prompt[:50]}...\n🎨 模型: {model} | 📐 比例: {aspect_ratio}",
            gr.update(),
            f"重做任务 {group_id[:8]} 已提交，正在后台执行..."
        )
    
    redo_selected_btn.click(
        fn=redo_selected_image,
        inputs=[
            selected_image_path,
            main_key_input,
            backup_keys_input,
            use_multi_acc,
            workers_input,
            retries_input,
            output_dir_input
        ],
        outputs=[
            summary_output,
            gallery_output, log_output
        ]
    )
    
    # 重排选中图像（填充参数到表单）
    def refill_selected_image(image_path):
        """将选中图像的参数填充到表单"""
        if not image_path or image_path not in image_metadata:
            # 返回足够数量的gr.update()
            return [gr.update()] * 15
        
        metadata = image_metadata[image_path]
        source_images = metadata.get('source_images', [])
        
        # 验证文件存在
        valid_images = [img for img in source_images if os.path.exists(img)]
        
        if not valid_images:
            return [gr.update()] * 15
        
        return (
            valid_images,                             # page1_files（填充到页面1）
            valid_images,                             # page1_gallery
            [],                                       # page2_files（清空）
            [],                                       # page2_gallery（清空）
            [],                                       # page3_files（清空）
            [],                                       # page3_gallery（清空）
            [],                                       # page4_files（清空）
            [],                                       # page4_gallery（清空）
            [],                                       # page5_files（清空）
            [],                                       # page5_gallery（清空）
            metadata.get('prompt', ''),               # prompts_input
            gr.update(),                              # main_key 保持不变
            gr.update(),                              # backup_keys 保持不变
            metadata.get('model', 'nano-banana-fast'), # model_input
            metadata.get('aspect_ratio', 'auto')      # aspect_ratio_input
        )
    
    refill_selected_btn.click(
        fn=refill_selected_image,
        inputs=[selected_image_path],
        outputs=[
            page1_files,
            page1_gallery,
            page2_files,
            page2_gallery,
            page3_files,
            page3_gallery,
            page4_files,
            page4_gallery,
            page5_files,
            page5_gallery,
            prompts_input,
            main_key_input,
            backup_keys_input,
            model_input,
            aspect_ratio_input
        ]
    )
    
    # 清空输出
    def clear_all_outputs():
        """清空所有输出结果"""
        global all_output_files, image_metadata, task_groups
        
        with all_output_files_lock:
            all_output_files.clear()
        
        with image_metadata_lock:
            image_metadata.clear()
        
        with task_groups_lock:
            task_groups.clear()
        
        return "✅ 已清空所有输出", None, ""
    
    clear_output_btn.click(
        fn=clear_all_outputs,
        outputs=[summary_output, gallery_output, log_output]
    )
    
    gr.Markdown("""
    ---
    ### 💡 使用说明
    
    #### 🔧 两种处理模式
    **单图模式（默认）**:
    - 每张图像单独处理
    - N张图 × M个提示词 = N×M个任务
    - 适合批量处理不同图像
    
    **多图分组模式（新）**:
    - 支持最多5个页面，每页独立上传图像
    - **所有页面的图像会组合成一个数组提交给API**
    - 例如：页面1有2张图，页面2有3张图 → API接收5张图的URL数组
    - K个提示词 = K个任务（所有图像一起处理）
    - 适合需要组合多张图像的场景
    
    #### 📝 基本流程
    1. **上传图像**: 在5个页面中上传图像，每个页面选择组合模式（相乘/相加）
    2. **输入提示词**: 每行一个提示词，支持多行
    3. **配置API**: 输入主密钥，可选启用多账户模式
    4. **调整参数**: 设置并发数、模型、宽高比、重试次数
    5. **开始生成**: 点击"🚀 开始生成"提交任务
    6. **查看详情**: 点击图库中的图像查看详细信息
    7. **重做图像**: 选中图像后点击"🔄 重做此图"使用相同参数重新生成
    8. **重排参数**: 选中图像后点击"📋 重排此图"将参数填回表单进行修改
    
    ### 📌 特性
    - ✅ **灵活组合**: 每个页面独立选择"相乘"或"相加"组合模式
    - ✅ **5个页面**: 支持5个页面，方便分批上传管理
    - ✅ **智能计算**: 实时显示当前组合将产生的API调用次数
    - ✅ **安全确认**: 多页面相乘时需要二次确认（防止意外大量任务）
    - ✅ **自动刷新**: 进度每2秒自动更新（无需手动刷新）
    - ✅ **URL缓存**: 已上传图像自动缓存，避免重复上传（💾标记）
    - ✅ **分阶段执行**: 先并发上传所有图像，再并发调用API
    - ✅ **多组并行**: 每次点击提交一组新任务，多组之间并行执行
    - ✅ **实时进度**: 分别显示上传进度和API进度
    - ✅ **多账户轮询**: 自动分配账号，突破单账号限制
    - ✅ **自动重试**: 失败任务自动重试（默认3次）
    - ✅ **图像元数据**: 点击图像查看提示词、耗时等详细信息
    - ✅ **单图重做**: 针对选中图像重新生成或修改参数
    
    ### 📊 进度说明
    - **上传进度**: 显示当前组图像上传完成数
    - **API进度**: 显示当前组API调用完成数
    - **图像画廊**: 累计显示所有已完成的图像（点击查看详情）
    
    ### 🔘 按钮说明
    - **🚀 开始生成**: 提交新的任务组
    - **🔄 刷新状态**: 手动立即刷新进度（也会自动每2秒刷新）
    - **🗑️ 清空上传缓存**: 清空已缓存的上传URL（需要重新上传所有图像时使用）
    - **🔄 重做此图**: 对选中图像使用相同参数重新生成
    - **📋 重排此图**: 将选中图像的参数填回表单进行修改
    
    ### 🆕 灵活组合模式说明
    - **相乘模式**: 该页面每张图单独作为一个选项，与其他页面笛卡尔积组合
      - 示例：页面1[图1,图2](相乘) + 页面2[图a,图b](相乘) = 4个组合
        * 组合1: [图1, 图a]
        * 组合2: [图1, 图b]
        * 组合3: [图2, 图a]
        * 组合4: [图2, 图b]
    - **相加模式**: 该页面所有图合并为一组，不增加组合数
      - 示例：页面1[图1,图2](相乘) + 页面2[图a,图b](相加) = 2个组合
        * 组合1: [图1, 图a, 图b]
        * 组合2: [图2, 图a, 图b]
    - **默认行为**: 页面1默认"相乘"，其他页面默认"相加"
    - **任务计算**: 图像组合数 × 提示词数量 = 总API调用次数
    """)


if __name__ == "__main__":
    demo.queue()  # 启用队列以支持进度条
    demo.launch(
        server_name="0.0.0.0",
        server_port=7861,  # 临时更改端口避免冲突
        share=False,
        show_error=True,
        allowed_paths=[OUTPUT_DIR, os.path.join(os.path.dirname(__file__), "outputs")]
    )
