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
                   task_name: str, upload_time: float, source_image_path: str) -> Tuple[int, bool, str, Optional[str], float, dict]:
    """调用 Banana API 生成图像"""
    start_time = time.time()
    try:
        client = GrsaiAPI(api_key=api_key)
        pil_images, image_urls, errors = client.banana_generate_image(
            prompt=prompt,
            model=model,
            urls=[cdn_url],
            aspect_ratio=aspect_ratio
        )
        
        if errors:
            elapsed = time.time() - start_time
            return task_id, False, f"API错误: {', '.join(errors)}", None, elapsed, {}
        
        if not pil_images:
            elapsed = time.time() - start_time
            return task_id, False, "未返回图像", None, elapsed, {}
        
        # 保存图像
        output_filename = f"{task_name}_1.png"
        output_path = os.path.join(output_dir, output_filename)
        pil_images[0].save(output_path)
        
        elapsed = time.time() - start_time
        
        # 创建元数据（包含源图像路径）
        metadata = {
            'source_image': source_image_path,  # 源图像路径
            'prompt': prompt,
            'upload_time': upload_time,
            'api_time': elapsed,
            'total_time': upload_time + elapsed,
            'model': model,
            'aspect_ratio': aspect_ratio,
            'task_name': task_name,
            'cdn_url': cdn_url
        }
        
        # 保存到全局字典
        with image_metadata_lock:
            image_metadata[output_path] = metadata
        
        return task_id, True, "生成成功", output_path, elapsed, metadata
        
    except Exception as e:
        elapsed = time.time() - start_time
        return task_id, False, f"API异常: {str(e)}", None, elapsed, {}


def process_task_group_async(
    group_id: str,
    images,
    prompts: List[str],
    all_api_keys: List[str],
    max_workers: int,
    model: str,
    aspect_ratio: str,
    max_retries: int
):
    """在后台线程中异步处理任务组"""
    
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
                    OUTPUT_DIR,
                    task['task_name'],
                    task['upload_time'],  # 传递上传时间
                    task['source_image']  # 传递源图像路径
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


def batch_generate(
    images,
    prompts_text: str,
    main_api_key: str,
    backup_api_keys: str,
    use_multiple_accounts: bool,
    max_workers: int,
    model: str,
    aspect_ratio: str,
    max_retries: int
):
    """立即提交任务组并返回"""
    
    # 验证输入
    if not images:
        return "❌ 请上传至少一张图像", None, ""
    
    if not prompts_text.strip():
        return "❌ 请输入提示词", None, ""
    
    if not main_api_key.strip():
        return "❌ 请输入主API密钥", None, ""
    
    # 解析提示词
    prompts = [line.strip() for line in prompts_text.strip().split('\n') if line.strip()]
    if not prompts:
        return "❌ 请输入有效的提示词", None, ""
    
    # 准备API密钥列表
    all_api_keys = [main_api_key.strip()]
    if use_multiple_accounts and backup_api_keys.strip():
        backup_keys = [k.strip() for k in backup_api_keys.strip().split('\n') if k.strip()]
        all_api_keys.extend(backup_keys)
    
    # 创建输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
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
            max_retries
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
    gr.Markdown("# 🍌 Banana 图像生成 WebUI")
    
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
            gr.Markdown("### 📤 输入")
            
            # 图像上传区域（正方形小框）
            images_input = gr.File(
                label="",
                file_count="multiple",
                file_types=["image"],
                type="filepath",
                height=120
            )
            
            # 预览缩略图（固定大小，不自适应填充）
            images_preview = gr.Gallery(
                label="已上传图像",
                columns=6,
                rows=4,
                height=600,
                object_fit="scale-down",
                show_label=True,
                interactive=False,
                container=True,
                allow_preview=True,
                show_fullscreen_button=False
            )
            
            # 按钮放在预览下方
            with gr.Row():
                delete_selected_btn = gr.Button("❌ 删除所选", size="sm", scale=1)
                clear_all_btn = gr.Button("🗑️ 清空所有", size="sm", scale=1)
            
            # 提示词输入
            prompts_input = gr.Textbox(
                label="提示词（每行一个）",
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
    uploaded_files = gr.State([])  # 存储所有已上传的文件路径
    
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
    
    # 绑定图像管理事件
    images_input.upload(
        fn=add_images,
        inputs=[uploaded_files, images_input],
        outputs=[uploaded_files, images_preview, images_input]
    )
    
    clear_all_btn.click(
        fn=clear_all_images,
        outputs=[uploaded_files, images_preview, images_input]
    )
    
    images_preview.select(
        fn=on_preview_select,
        inputs=[uploaded_files],
        outputs=[selected_preview_index]
    )
    
    delete_selected_btn.click(
        fn=delete_selected_from_preview,
        inputs=[selected_preview_index, uploaded_files],
        outputs=[uploaded_files, images_preview, selected_preview_index]
    )
    
    # 绑定事件
    generate_btn.click(
        fn=batch_generate,
        inputs=[
            uploaded_files,  # 使用状态中的文件列表
            prompts_input,
            main_key_input,
            backup_keys_input,
            use_multi_acc,
            workers_input,
            model_input,
            aspect_ratio_input,
            retries_input
        ],
        outputs=[
            summary_output, 
            gallery_output, log_output
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
                
                # 格式化信息显示
                info_text = f"""📸 源图像: {os.path.basename(metadata.get('source_image', 'N/A'))}
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
    def redo_selected_image(image_path, main_key, backup_keys, use_multi, workers, retries):
        """重做选中的图像"""
        if not image_path or image_path not in image_metadata:
            return "❌ 未选择有效图像", None, "❌ 未选择有效图像"
        
        metadata = image_metadata[image_path]
        source_image = metadata.get('source_image')
        
        if not source_image or not os.path.exists(source_image):
            return "❌ 源图像不存在", None, f"❌ 源图像不存在: {source_image}"
        
        # 使用相同参数重新生成（按位置传参）
        return batch_generate(
            [source_image],                              # images
            metadata.get('prompt', ''),                  # prompts_text
            main_key,                                     # main_api_key
            backup_keys,                                  # backup_api_keys
            use_multi,                                    # use_multiple_accounts
            int(workers),                                 # max_workers
            metadata.get('model', 'nano-banana-fast'),   # model
            metadata.get('aspect_ratio', 'auto'),        # aspect_ratio
            int(retries)                                  # max_retries
        )
    
    redo_selected_btn.click(
        fn=redo_selected_image,
        inputs=[
            selected_image_path,
            main_key_input,
            backup_keys_input,
            use_multi_acc,
            workers_input,
            retries_input
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
            return gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update(), gr.update()
        
        metadata = image_metadata[image_path]
        source_image = metadata.get('source_image')
        
        # 准备图像文件列表
        image_files = [source_image] if source_image and os.path.exists(source_image) else []
        
        return (
            image_files,                                 # uploaded_files 状态
            image_files,                                 # images_preview
            metadata.get('prompt', ''),
            gr.update(),  # main_key 保持不变
            gr.update(),  # backup_keys 保持不变
            gr.update(),  # use_multi 保持不变
            gr.update(),  # workers 保持不变
            metadata.get('model', 'nano-banana-fast'),
            metadata.get('aspect_ratio', 'auto'),
            gr.update()   # retries 保持不变
        )
    
    refill_selected_btn.click(
        fn=refill_selected_image,
        inputs=[selected_image_path],
        outputs=[
            uploaded_files, images_preview,
            prompts_input, main_key_input,
            backup_keys_input, use_multi_acc, workers_input,
            model_input, aspect_ratio_input, retries_input
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
    1. **上传图像**: 拖拽或点击上传多张图像
    2. **输入提示词**: 每行一个提示词，支持多行
    3. **配置API**: 输入主密钥，可选启用多账户模式
    4. **调整参数**: 设置并发数和重试次数
    5. **开始生成**: 点击"🚀 开始生成"提交任务
    6. **查看详情**: 点击图库中的图像查看详细信息
    7. **重做图像**: 选中图像后点击"🔄 重做此图"使用相同参数重新生成
    8. **重排参数**: 选中图像后点击"📋 重排此图"将参数填回表单进行修改
    
    ### 📌 特性
    - ✅ **自动刷新**: 进度每2秒自动更新（无需手动刷新）
    - ✅ **URL缓存**: 已上传图像自动缓存，避免重复上传（💾标记）
    - ✅ **分阶段执行**: 先并发上传所有图像，再并发调用API
    - ✅ **多组并行**: 每次点击提交一组新任务，多组之间并行执行
    - ✅ **实时进度**: 分别显示上传进度和API进度
    - ✅ **多账户轮询**: 自动分配账号，突破单账号限制
    - ✅ **自动重试**: 失败任务自动重试（最多3次）
    - ✅ **图像元数据**: 点击图像查看提示词、耗时等详细信息
    - ✅ **单图重做**: 针对选中图像重新生成或修改参数
    
    ### 📊 进度说明
    - **上传进度**: 显示当前组图像上传完成数
    - **API进度**: 显示当前组API调用完成数
    - **图像画廊**: 累计显示所有已完成的图像（点击查看详情）
    
    ### 🔘 按钮说明
    - **🚀 开始生成**: 提交新的任务组
    - **🔄 刷新状态**: 手动立即刷新进度（也会自动每2秒刷新）
    - **�️ 清空上传缓存**: 清空已缓存的上传URL（需要重新上传所有图像时使用）
    - **�🔄 重做此图**: 对选中图像使用相同参数重新生成
    - **📋 重排此图**: 将选中图像的参数填回表单进行修改
    """)
    
    # 初始加载
    demo.load(
        fn=get_current_status,
        inputs=None,
        outputs=[summary_output, gallery_output, log_output]
    )


if __name__ == "__main__":
    demo.queue()  # 启用队列以支持进度条
    demo.launch(
        server_name="0.0.0.0",
        server_port=7862,
        share=False,
        show_error=True
    )
