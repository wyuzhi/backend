import os
import sys
import time
import json
import logging
import requests
import zipfile
import shutil
from datetime import datetime

# 确保可以导入hunyuan_3d.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from hunyuan_3d import hunyuan_submit_job, hunyuan_query_job

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('3DModelGenerator')

# 配置文件存储路径
MODEL_STORAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')
MODEL_FILES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'model_files')
ZIP_FILES_PATH = os.path.join(MODEL_FILES_PATH, 'zips')
EXTRACTED_FILES_PATH = os.path.join(MODEL_FILES_PATH, 'extracted')
os.makedirs(MODEL_STORAGE_PATH, exist_ok=True)
os.makedirs(ZIP_FILES_PATH, exist_ok=True)
os.makedirs(EXTRACTED_FILES_PATH, exist_ok=True)

# 配置轮询间隔和超时时间
POLLING_INTERVAL = 10  # 秒
TIMEOUT = 300  # 5分钟

def download_file(url, save_path):
    """
    下载文件到指定路径
    
    Args:
        url (str): 文件下载URL
        save_path (str): 保存路径
    
    Returns:
        bool: 下载是否成功
    """
    try:
        logger.info(f"开始下载文件: {url}")
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        # 确保目录存在
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        # 写入文件
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        logger.info(f"文件下载完成: {save_path}")
        return True
    except Exception as e:
        logger.error(f"下载文件失败: {str(e)}")
        return False

def extract_obj_from_zip(zip_path, extract_dir):
    """
    从ZIP文件中提取OBJ格式文件
    
    Args:
        zip_path (str): ZIP文件路径
        extract_dir (str): 解压目录
    
    Returns:
        str: OBJ文件的路径，如果未找到则返回None
    """
    try:
        logger.info(f"开始解压ZIP文件: {zip_path}")
        
        # 创建解压目录
        os.makedirs(extract_dir, exist_ok=True)
        
        # 解压ZIP文件
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        logger.info(f"ZIP文件解压完成，解压目录: {extract_dir}")
        
        # 查找OBJ文件
        obj_file = None
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.lower().endswith('.obj'):
                    obj_file = os.path.join(root, file)
                    logger.info(f"找到OBJ文件: {obj_file}")
                    break
            if obj_file:
                break
        
        return obj_file
    except Exception as e:
        logger.error(f"解压ZIP文件或提取OBJ文件失败: {str(e)}")
        return None

def generate_3d_model(image_url=None, prompt=None):
    """
    生成3D模型的主函数
    
    Args:
        image_url (str, optional): 图片URL（图生3D模式）
        prompt (str, optional): 3D内容描述（文生3D模式）
    
    Returns:
        dict: 包含模型文件信息的字典，失败返回None
    """
    try:
        original_prompt = prompt  # 保存原始提示词，用于失败回退
        
        # 确保不会同时使用图生3D和文生3D模式
        # 优先使用图生3D模式
        if image_url and prompt:
            logger.info("同时提供了图片URL和提示词，将优先使用图生3D模式")
            used_prompt = None  # 图生3D模式下不使用提示词
        elif not image_url and not prompt:
            logger.error("必须提供图片URL或提示词其中之一")
            return None
        else:
            used_prompt = prompt
        
        # 提交3D生成任务（图生3D模式）
        job_id = hunyuan_submit_job(prompt=used_prompt, image_url=image_url)
        
        # 如果图生3D模式失败，尝试回退到文生3D模式
        if not job_id and image_url and original_prompt:
            logger.warning("图生3D模式失败，尝试回退到文生3D模式")
            job_id = hunyuan_submit_job(prompt=original_prompt, image_url=None)
            
        if not job_id:
            logger.error("提交3D生成任务失败")
            return None
        
        logger.info(f"3D生成任务已提交，任务ID: {job_id}")
        
        # 轮询任务状态
        start_time = time.time()
        while time.time() - start_time < TIMEOUT:
            time.sleep(POLLING_INTERVAL)
            
            result = hunyuan_query_job(job_id)
            if not result:
                logger.warning(f"查询任务状态失败，任务ID: {job_id}")
                continue
            
            status = result.get('Status')
            if status == "DONE":
                logger.info(f"3D模型生成完成，任务ID: {job_id}")
                
                # 提取文件URL
                result_file_3ds = result.get('ResultFile3Ds', [])
                if not result_file_3ds or not isinstance(result_file_3ds, list) or len(result_file_3ds) == 0:
                    logger.error(f"未能提取到文件URL，任务ID: {job_id}")
                    return None
                
                # 处理模型文件URL
                file_urls = {}
                obj_file_local_path = None
                
                for file_info in result_file_3ds:
                    file_type = file_info.get('Type', 'unknown')
                    file_url = file_info.get('Url', '')
                    
                    # 只处理ZIP文件（根据示例数据，OBJ类型实际上是ZIP文件）
                    if file_url and (file_type == 'OBJ' or file_url.endswith('.zip')):
                        # 构建本地文件路径
                        zip_filename = f"{job_id}.zip"
                        zip_path = os.path.join(ZIP_FILES_PATH, zip_filename)
                        
                        # 下载ZIP文件
                        if download_file(file_url, zip_path):
                            # 解压并提取OBJ文件
                            extract_dir = os.path.join(EXTRACTED_FILES_PATH, job_id)
                            obj_file = extract_obj_from_zip(zip_path, extract_dir)
                            
                            if obj_file:
                                # 构建服务器可访问的路径
                                # 假设uploads目录是公开可访问的
                                # 我们将OBJ文件复制到uploads目录，以便前端访问
                                obj_filename = f"{job_id}_{os.path.basename(obj_file)}"
                                obj_public_path = os.path.join('uploads', obj_filename)
                                obj_dest_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), obj_public_path)
                                
                                # 确保uploads目录存在
                                os.makedirs(os.path.dirname(obj_dest_path), exist_ok=True)
                                
                                # 复制文件
                                shutil.copy2(obj_file, obj_dest_path)
                                
                                # 构建可访问的URL路径
                                # 假设服务器的静态文件根目录是backend目录
                                obj_file_local_path = f"/uploads/{obj_filename}"
                                logger.info(f"OBJ文件已处理完成，本地路径: {obj_file_local_path}")
                        
                        # 无论是否处理成功，都将原始URL和处理后的本地路径保存
                        file_urls[file_type] = {
                            'url': file_url,
                            'preview_image_url': file_info.get('PreviewImageUrl', ''),
                            'local_path': obj_file_local_path
                        }
                    else:
                        file_urls[file_type] = {
                            'url': file_url,
                            'preview_image_url': file_info.get('PreviewImageUrl', '')
                        }
                
                # 保存模型信息
                model_info = {
                    'job_id': job_id,
                    'created_at': datetime.now().isoformat(),
                    'file_urls': file_urls,
                    'prompt': prompt,
                    'image_url': image_url
                }
                
                # 将模型信息保存到文件
                model_info_file = os.path.join(MODEL_STORAGE_PATH, f"{job_id}.json")
                with open(model_info_file, 'w', encoding='utf-8') as f:
                    json.dump(model_info, f, ensure_ascii=False, indent=4)
                
                logger.info(f"模型信息已保存到: {model_info_file}")
                return model_info
                
            elif status == "FAILED":
                error_msg = result.get('ErrorMsg', '未知错误')
                logger.error(f"3D模型生成失败: {error_msg}")
                return None
                
            elif status == "RUNNING":
                progress = result.get('Progress', 0)
                logger.info(f"3D模型生成中... 进度: {progress}%")
                
            else:
                logger.info(f"任务状态: {status}")
        
        # 任务超时
        logger.error(f"3D模型生成超时，任务ID: {job_id}")
        return None
        
    except Exception as e:
        logger.exception(f"生成3D模型时发生错误: {str(e)}")
        return None

def create_pet_description(pet_data):
    """
    根据宠物信息创建3D模型生成的描述
    
    Args:
        pet_data (dict): 宠物信息
    
    Returns:
        str: 用于生成3D模型的描述文本
    """
    # 基础描述
    gender_text = '公' if pet_data.get('gender') == 'male' else '母'
    description = f"一只{gender_text}{pet_data.get('type', '狗狗')}"
    
    # 添加名称
    if pet_data.get('name'):
        description += f"，名叫{pet_data.get('name')}"
    
    # 添加性格
    personalities = pet_data.get('personality', '').split(',')
    if personalities and personalities[0]:
        description += f"，性格{('、').join(personalities)}"
    
    # 添加爱好
    hobbies = pet_data.get('hobby', '').split(',')
    if hobbies and hobbies[0]:
        description += f"，喜欢{('、').join(hobbies)}"
    
    # 添加故事元素
    if pet_data.get('story'):
        description += f"，{pet_data.get('story')[:50]}..."
    
    # 艺术风格描述
    description += "，高质量3D渲染，毛发细节清晰，色彩鲜明，表情可爱，充满活力，适合作为虚拟宠物伙伴。"
    
    return description

if __name__ == "__main__":
    # 测试代码
    test_pet_data = {
        'name': '小白',
        'type': '狗狗',
        'gender': 'male',
        'personality': '活泼,聪明',
        'hobby': '玩耍,进食',
        'story': '一只可爱的小白狗，总是充满活力'
    }
    
    prompt = create_pet_description(test_pet_data)
    print(f"测试提示词: {prompt}")
    
    # 测试生成3D模型
    # result = generate_3d_model(prompt=prompt)
    # if result:
    #     print(f"测试成功，生成结果: {result}")
    # else:
    #     print("测试失败")