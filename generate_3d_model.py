# 导入必要的模块
import os
import json
import time
import logging
import traceback
from datetime import datetime
import requests
from zipfile import ZipFile
from io import BytesIO
import sys

# 确保能导入app模块以访问数据库
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('3DModelGenerator')

# 配置文件存储路径
MODEL_STORAGE_PATH = os.path.join(current_dir, '../models')
IMAGE_STORAGE_PATH = os.path.join(current_dir, '../images')

# 创建存储目录（如果不存在）
os.makedirs(MODEL_STORAGE_PATH, exist_ok=True)
os.makedirs(IMAGE_STORAGE_PATH, exist_ok=True)

# 定义轮询间隔（秒）
POLLING_INTERVAL = 2

# 导入hunyuan_3d模块
from hunyuan_3d import *

# 导入app模块以访问数据库
from backend.app import db, Pet

# 下载文件函数
def download_file(url, save_path):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return True, save_path
    except Exception as e:
        logger.error(f"下载文件失败: {str(e)}")
        return False, str(e)

# 从ZIP文件中提取OBJ文件
def extract_obj_from_zip(zip_file_path, extract_dir):
    try:
        with ZipFile(zip_file_path, 'r') as zip_ref:
            # 创建解压目录
            os.makedirs(extract_dir, exist_ok=True)
            
            # 解压所有文件
            zip_ref.extractall(extract_dir)
            
            # 查找OBJ文件
            obj_files = []
            for root, dirs, files in os.walk(extract_dir):
                for file in files:
                    if file.lower().endswith('.obj'):
                        obj_files.append(os.path.join(root, file))
            
            if not obj_files:
                logger.warning("ZIP文件中未找到OBJ文件")
                # 查找其他3D模型文件格式
                for root, dirs, files in os.walk(extract_dir):
                    for file in files:
                        if file.lower().endswith(('.fbx', '.gltf', '.glb', '.stl')):
                            obj_files.append(os.path.join(root, file))
                
            return True, obj_files[0] if obj_files else None
    except Exception as e:
        logger.error(f"解压ZIP文件失败: {str(e)}")
        return False, str(e)

# 生成3D模型的主函数
def generate_3d_model(image_url=None, prompt=None, pet_id=None):
    logger.info(f"开始生成3D模型 - pet_id: {pet_id}, image_url: {'已提供' if image_url else '未提供'}, prompt: {'已提供' if prompt else '未提供'}")
    
    try:
        # 创建3D客户端
        client = Hunyuan3DClient()
        
        # 尝试使用图像生成3D模型（如果提供了图像）
        if image_url:
            try:
                logger.info(f"尝试通过图像生成3D模型，URL: {image_url}")
                result = client.generate_from_image(image_url)
                if result:
                    logger.info(f"通过图像生成3D模型成功，任务ID: {result.get('job_id', '未知')}")
                    return process_3d_model_result(result, pet_id)
            except Exception as e:
                logger.error(f"通过图像生成3D模型失败: {str(e)}")
                # 如果图像生成失败且提供了提示词，则尝试通过提示词生成
                if prompt:
                    logger.info("回退到通过提示词生成3D模型")
                else:
                    raise Exception("图像生成失败且未提供提示词")
        
        # 如果没有提供图像或图像生成失败，使用提示词生成
        if prompt:
            logger.info(f"通过提示词生成3D模型")
            result = client.generate_from_text(prompt)
            if result:
                logger.info(f"通过提示词生成3D模型成功，任务ID: {result.get('job_id', '未知')}")
                return process_3d_model_result(result, pet_id)
        
        # 如果都失败了
        logger.error("3D模型生成失败，没有可用的生成方式")
        return None
        
    except Exception as e:
        logger.error(f"生成3D模型时出错: {str(e)}")
        traceback.print_exc()
        return None

# 处理3D模型生成结果
def process_3d_model_result(result, pet_id=None):
    try:
        # 获取任务ID和状态
        job_id = result.get('job_id')
        status = result.get('status', 'pending')
        
        # 如果任务还在处理中，进行轮询
        if status == 'pending':
            logger.info(f"任务 {job_id} 正在处理中，开始轮询...")
            
            # 创建3D客户端用于轮询
            client = Hunyuan3DClient()
            
            # 轮询直到任务完成或超时
            start_time = time.time()
            max_wait_time = 300  # 最大等待时间5分钟
            
            while time.time() - start_time < max_wait_time:
                # 更新宠物状态为generating（如果提供了pet_id）
                if pet_id:
                    update_pet_status(pet_id, 'generating')
                    
                # 轮询任务状态
                result = client.query_job(job_id)
                if result:
                    status = result.get('status')
                    
                    if status == 'completed':
                        logger.info(f"任务 {job_id} 完成")
                        return save_and_process_model_files(result, pet_id)
                    elif status == 'failed':
                        logger.error(f"任务 {job_id} 失败: {result.get('error_message', '未知错误')}")
                        # 更新宠物状态为failed
                        if pet_id:
                            update_pet_status(pet_id, 'failed')
                        return None
                    
                # 等待一段时间后再次轮询
                time.sleep(POLLING_INTERVAL)
                
            logger.error(f"任务 {job_id} 超时")
            # 更新宠物状态为timeout
            if pet_id:
                update_pet_status(pet_id, 'timeout')
            return None
        
        # 如果任务已经完成，直接处理结果
        elif status == 'completed':
            logger.info(f"任务 {job_id} 已完成，开始处理结果")
            return save_and_process_model_files(result, pet_id)
        
        # 其他状态
        else:
            logger.error(f"任务 {job_id} 状态异常: {status}")
            # 更新宠物状态为failed
            if pet_id:
                update_pet_status(pet_id, 'failed')
            return None
            
    except Exception as e:
        logger.error(f"处理3D模型结果时出错: {str(e)}")
        traceback.print_exc()
        # 更新宠物状态为failed
        if pet_id:
            update_pet_status(pet_id, 'failed')
        return None

# 保存和处理模型文件
def save_and_process_model_files(result, pet_id=None):
    try:
        file_urls = result.get('file_urls', {})
        if not file_urls:
            logger.error("没有找到文件URL")
            # 更新宠物状态为failed
            if pet_id:
                update_pet_status(pet_id, 'failed')
            return None
        
        # 创建唯一的模型ID
        model_id = f"model_{int(time.time())}_{pet_id if pet_id else 'unknown'}"
        model_dir = os.path.join(MODEL_STORAGE_PATH, model_id)
        os.makedirs(model_dir, exist_ok=True)
        
        # 保存模型信息
        model_info = {
            'model_id': model_id,
            'creation_time': datetime.utcnow().isoformat(),
            'file_urls': {}
        }
        
        # 下载和处理模型文件
        for file_type, file_info in file_urls.items():
            if isinstance(file_info, dict) and 'url' in file_info:
                file_url = file_info['url']
                file_name = os.path.basename(file_url.split('?')[0])
                save_path = os.path.join(model_dir, file_name)
                
                # 下载文件
                success, result = download_file(file_url, save_path)
                if success:
                    logger.info(f"成功下载 {file_type} 文件到 {save_path}")
                    model_info['file_urls'][file_type] = {
                        'url': file_url,
                        'local_path': save_path
                    }
                    
                    # 如果是ZIP文件，尝试提取OBJ文件
                    if file_name.lower().endswith('.zip'):
                        success, obj_path = extract_obj_from_zip(save_path, os.path.join(model_dir, 'extracted'))
                        if success and obj_path:
                            logger.info(f"成功提取OBJ文件: {obj_path}")
                            model_info['file_urls']['OBJ'] = {
                                'url': file_url,  # 使用原始ZIP文件URL
                                'local_path': obj_path
                            }
                            # 添加预览图URL
                            if file_info.get('preview_image_url'):
                                model_info['file_urls']['OBJ']['preview_image_url'] = file_info['preview_image_url']
                else:
                    logger.error(f"下载 {file_type} 文件失败: {result}")
        
        # 保存模型信息到JSON文件
        json_path = os.path.join(model_dir, 'model_info.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(model_info, f, ensure_ascii=False, indent=2)
        
        logger.info(f"模型信息已保存到 {json_path}")
        
        # 更新宠物记录（如果提供了pet_id）
        if pet_id:
            update_pet_with_model_info(pet_id, model_info)
        
        return model_info
        
    except Exception as e:
        logger.error(f"保存和处理模型文件时出错: {str(e)}")
        traceback.print_exc()
        # 更新宠物状态为failed
        if pet_id:
            update_pet_status(pet_id, 'failed')
        return None

# 更新宠物状态
def update_pet_status(pet_id, status):
    try:
        # 获取宠物记录
        pet = Pet.query.get(pet_id)
        if pet:
            # 更新状态
            pet.status = status
            db.session.commit()
            logger.info(f"已更新宠物 {pet_id} 状态为 {status}")
        else:
            logger.error(f"未找到宠物记录，ID: {pet_id}")
    except Exception as e:
        logger.error(f"更新宠物状态时出错: {str(e)}")
        db.session.rollback()

# 更新宠物记录中的模型信息
def update_pet_with_model_info(pet_id, model_info):
    try:
        # 获取宠物记录
        pet = Pet.query.get(pet_id)
        if pet:
            # 获取OBJ文件路径（如果有）
            file_urls = model_info.get('file_urls', {})
            obj_file = file_urls.get('OBJ')
            
            if obj_file:
                # 使用本地路径优先
                pet.model_url = obj_file.get('local_path', '') or obj_file.get('url', '')
                pet.preview_url = obj_file.get('preview_image_url', '')
            
            # 更新状态为completed
            pet.status = 'completed'
            
            db.session.commit()
            logger.info(f"已更新宠物 {pet_id} 的模型信息")
        else:
            logger.error(f"未找到宠物记录，ID: {pet_id}")
    except Exception as e:
        logger.error(f"更新宠物模型信息时出错: {str(e)}")
        db.session.rollback()

# 根据宠物数据创建描述文本
def create_pet_description(pet_data):
    # 从宠物数据中提取信息
    name = pet_data.get('name', '宠物')
    pet_type = pet_data.get('type', '')
    gender = pet_data.get('gender', '')
    personality = pet_data.get('personality', '')
    hobby = pet_data.get('hobby', '')
    story = pet_data.get('story', '')
    stu
    # 构建描述文本
    description = f"这是一只名叫{name}的"
    
    if pet_type:
        description += f"{pet_type}"
    else:
        description += "小动物"
    
    if gender:
        description += f"，性别是{gender}"
    
    if personality:
        description += f"，性格{personality}"
    
    if hobby:
        description += f"，喜欢{hobby}"
    
    if story:
        description += f"。{story}"
    
    description += "。请根据这些信息生成一个可爱、生动的3D模型。"
    
    return description

# 测试代码（仅在直接运行此脚本时执行）
if __name__ == '__main__':
    # 测试创建宠物描述
    test_pet_data = {
        'name': '小白',
        'type': '小狗',
        'gender': '公',
        'personality': '活泼可爱',
        'hobby': '玩球',
        'story': '这是一只非常可爱的小狗，喜欢和主人一起玩耍。'
    }
    
    prompt = create_pet_description(test_pet_data)
    print(f"测试生成的描述文本: {prompt}")
    
    # 注意：运行实际的3D模型生成可能需要API密钥和网络连接
    # 如果需要测试完整流程，可以取消下面的注释
    # result = generate_3d_model(prompt=prompt)
    # print(f"测试结果: {result}")