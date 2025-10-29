#!/usr/bin/env python3
"""
批量并发提交banana图像生成任务
使用input目录中的图像和文本文件

运行: python batch_banana_concurrent.py
"""

import os
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional
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
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print("请确保 api_client.py 在当前目录中")
    sys.exit(1)

# 配置
API_KEY = os.getenv("GRSAI_API_KEY", "")
INPUT_IMAGE_DIR = os.path.join(os.path.dirname(__file__), "input", "image")
INPUT_TEXT_FILE = os.path.join(os.path.dirname(__file__), "input", "text", "text.txt")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "batch_outputs")
MAX_WORKERS = 10  # 并发数量，可根据需要调整
MODEL = "nano-banana-fast"  # 使用fast模型以加快处理速度
ASPECT_RATIO = "auto"  # 默认宽高比

# 支持的图像格式
SUPPORTED_IMAGE_FORMATS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def read_prompt_from_file(file_path: str) -> List[str]:
    """读取文本文件中的提示词（支持多行）"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            prompts = [line.strip() for line in f.readlines() if line.strip()]
        return prompts
    except Exception as e:
        print(f"⚠️ 读取提示词文件失败 {file_path}: {e}")
        return []


def get_image_files(directory: str) -> List[str]:
    """获取目录中的所有图像文件"""
    image_files = []
    try:
        for file in os.listdir(directory):
            file_path = os.path.join(directory, file)
            if os.path.isfile(file_path):
                ext = os.path.splitext(file)[1].lower()
                if ext in SUPPORTED_IMAGE_FORMATS:
                    image_files.append(file_path)
        return sorted(image_files)
    except Exception as e:
        print(f"⚠️ 读取图像目录失败 {directory}: {e}")
        return []


def upload_image_to_cdn(image_path: str) -> Optional[str]:
    """
    上传图像到CDN（需要实现upload功能）
    如果没有upload模块，返回None
    """
    try:
        # 尝试导入upload模块
        from upload import upload_file_zh
        print(f"📤 上传图像: {os.path.basename(image_path)}")
        url = upload_file_zh(image_path)
        if url:
            print(f"✅ 上传成功: {url}")
            return url
        else:
            print(f"❌ 上传失败: {image_path}")
            return None
    except ImportError:
        print(f"⚠️ 未找到upload模块，跳过图像上传")
        return None
    except Exception as e:
        print(f"❌ 上传图像失败 {image_path}: {e}")
        return None


def process_single_task(
    task_id: int,
    prompt: str,
    image_path: Optional[str],
    api_key: str,
    model: str,
    aspect_ratio: str,
    output_dir: str,
    prompt_idx: int = 1
) -> Tuple[int, bool, str]:
    """
    处理单个banana生成任务
    
    Args:
        task_id: 任务ID
        prompt: 提示词
        image_path: 输入图像路径（可选）
        api_key: API密钥
        model: 模型名称
        aspect_ratio: 宽高比
        output_dir: 输出目录
        prompt_idx: 提示词索引
        
    Returns:
        (task_id, success, message)
    """
    task_name = f"Task_{task_id}"
    if image_path:
        image_name = os.path.splitext(os.path.basename(image_path))[0]
        task_name += f"_{image_name}_prompt{prompt_idx}"
    else:
        task_name += f"_prompt{prompt_idx}"
    
    try:
        print(f"\n{'='*60}")
        print(f"🚀 开始处理: {task_name}")
        print(f"📝 提示词: {prompt[:50]}...")
        if image_path:
            print(f"🖼️ 输入图像: {os.path.basename(image_path)}")
        print(f"{'='*60}")
        
        # 如果有输入图像，先上传
        urls = []
        if image_path:
            uploaded_url = upload_image_to_cdn(image_path)
            if uploaded_url:
                urls = [uploaded_url]
            else:
                # 如果上传失败，继续不使用图像
                print(f"⚠️ 图像上传失败，将只使用提示词生成")
        
        # 调用banana API
        client = GrsaiAPI(api_key=api_key)
        start_time = time.time()
        
        pil_images, image_urls, errors = client.banana_generate_image(
            prompt=prompt,
            model=model,
            urls=urls,
            aspect_ratio=aspect_ratio
        )
        
        duration = time.time() - start_time
        
        # 检查是否有错误
        if errors:
            error_msg = f"API返回错误: {', '.join(errors)}"
            print(f"❌ {task_name} 失败: {error_msg}")
            return task_id, False, error_msg
        
        # 检查是否有生成的图像
        if not pil_images:
            error_msg = "未返回任何图像"
            print(f"❌ [{time.strftime('%H:%M:%S')}] {task_name} 失败: {error_msg}")
            return task_id, False, error_msg
        
        # 保存生成的图像
        print(f"✅ [{time.strftime('%H:%M:%S')}] {task_name} 成功生成 {len(pil_images)} 张图像 | ⏱️ {duration:.2f}s")
        
        saved_files = []
        for idx, img in enumerate(pil_images, start=1):
            output_filename = f"{task_name}_{idx}.png"
            output_path = os.path.join(output_dir, output_filename)
            
            try:
                img.save(output_path)
                saved_files.append(output_filename)
                print(f"💾 已保存: {output_filename}")
            except Exception as e:
                print(f"⚠️ 保存图像失败 {output_filename}: {e}")
        
        success_msg = f"成功生成并保存 {len(saved_files)} 张图像，耗时 {duration:.2f}s"
        return task_id, True, success_msg
        
    except GrsaiAPIError as e:
        error_msg = f"API错误: {str(e)}"
        print(f"❌ {task_name} 失败: {error_msg}")
        return task_id, False, error_msg
    except Exception as e:
        error_msg = f"未知异常: {str(e)}"
        print(f"❌ {task_name} 失败: {error_msg}")
        traceback.print_exc()
        return task_id, False, error_msg


def main():
    """主函数"""
    print("🚀 批量并发Banana图像生成任务")
    print("=" * 80)
    
    # 检查API密钥
    if not API_KEY:
        print("❌ 未找到API密钥")
        print("请在 .env 文件中设置 GRSAI_API_KEY")
        return 1
    
    print(f"✅ API密钥已加载: {API_KEY[:10]}...")
    
    # 创建输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"📁 输出目录: {OUTPUT_DIR}")
    
    # 读取提示词（支持多行）
    prompts = read_prompt_from_file(INPUT_TEXT_FILE)
    if not prompts:
        print("❌ 未找到有效的提示词")
        print(f"请检查文件: {INPUT_TEXT_FILE}")
        return 1
    
    print(f"📝 找到 {len(prompts)} 个提示词:")
    for idx, prompt in enumerate(prompts, 1):
        print(f"   {idx}. {prompt[:50]}{'...' if len(prompt) > 50 else ''}")
    
    # 获取所有图像文件
    image_files = get_image_files(INPUT_IMAGE_DIR)
    if not image_files:
        print(f"⚠️ 未找到图像文件，将只使用提示词生成")
        # 至少生成一次（每个提示词生成一张）
        image_files = [None] * len(prompts)
    else:
        print(f"🖼️ 找到 {len(image_files)} 个图像文件:")
        for img_file in image_files:
            print(f"   - {os.path.basename(img_file)}")
    
    print(f"\n⚙️ 配置:")
    print(f"   - 模型: {MODEL}")
    print(f"   - 宽高比: {ASPECT_RATIO}")
    print(f"   - 并发数: {MAX_WORKERS}")
    print(f"   - 图像数: {len([f for f in image_files if f])}")
    print(f"   - 提示词数: {len(prompts)}")
    
    # 计算总任务数
    total_tasks = len(image_files) * len(prompts)
    print(f"   - 任务总数: {total_tasks}")
    
    # 确认开始
    print(f"\n{'='*80}")
    print(f"⏰ 开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🚀 即将并发执行 {total_tasks} 个任务...")
    print(f"{'='*80}")
    input("按回车键开始批量处理...")
    
    # 开始计时
    overall_start = time.time()
    
    # 创建任务列表（每个图像 × 每个提示词）
    tasks = []
    task_id = 1
    for image_file in image_files:
        for prompt_idx, prompt in enumerate(prompts, 1):
            tasks.append((task_id, prompt, image_file, API_KEY, MODEL, ASPECT_RATIO, OUTPUT_DIR, prompt_idx))
            task_id += 1
    
    # 使用线程池并发执行
    results = []
    completed = 0
    print(f"\n{'='*80}")
    print(f"⚡ 并发执行中... (并发数: {MAX_WORKERS})")
    print(f"{'='*80}\n")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交所有任务
        future_to_task = {
            executor.submit(process_single_task, *task): task[0]
            for task in tasks
        }
        
        print(f"✅ 已提交 {len(tasks)} 个任务到线程池\n")
        
        # 获取结果
        for future in as_completed(future_to_task):
            completed += 1
            task_id = future_to_task[future]
            try:
                result = future.result()
                results.append(result)
                print(f"\n[进度: {completed}/{len(tasks)}] 任务完成\n")
            except Exception as e:
                print(f"❌ 任务 {task_id} 执行异常: {e}")
                results.append((task_id, False, str(e)))
    
    # 统计结果
    overall_duration = time.time() - overall_start
    success_count = sum(1 for _, success, _ in results if success)
    failed_count = len(results) - success_count
    
    # 计算理论串行时间（用于对比）
    individual_times = []
    for task_id, success, message in results:
        if success and "耗时" in message:
            try:
                time_str = message.split("耗时 ")[1].split("s")[0]
                individual_times.append(float(time_str))
            except:
                pass
    
    theoretical_serial_time = sum(individual_times) if individual_times else 0
    speedup = theoretical_serial_time / overall_duration if overall_duration > 0 else 0
    
    # 输出总结
    print(f"\n{'='*80}")
    print("📊 批量处理完成!")
    print(f"{'='*80}")
    print(f"⏰ 完成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⏱️ 实际总耗时: {overall_duration:.2f}s")
    if theoretical_serial_time > 0:
        print(f"📈 串行预计耗时: {theoretical_serial_time:.2f}s")
        print(f"🚀 加速比: {speedup:.2f}x (节省 {(1-1/speedup)*100:.1f}%时间)")
    print(f"✅ 成功: {success_count}/{len(results)}")
    print(f"❌ 失败: {failed_count}/{len(results)}")
    
    if failed_count > 0:
        print(f"\n失败的任务:")
        for task_id, success, message in results:
            if not success:
                print(f"   Task_{task_id}: {message}")
    
    print(f"\n💾 输出目录: {OUTPUT_DIR}")
    print("=" * 80)
    
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
