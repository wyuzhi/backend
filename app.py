from flask import Flask, jsonify, request, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from dotenv import load_dotenv
import os
import random
import logging
import time
from datetime import datetime
import uuid
import sys
from werkzeug.utils import secure_filename
import urllib.request
import json

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('EternalPalBackend')

# 初始化Flask应用
app = Flask(__name__)
CORS(app)

# 增加Flask应用超时设置
app.config['TIMEOUT'] = 300  # 5分钟


# 配置数据库
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:////Users/yuzhi/miniprograms/EternalPal/backend/eternal_pal.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 配置上传文件夹
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 确保上传文件夹存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 初始化数据库
db = SQLAlchemy(app)

# 检查文件扩展名是否允许
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# 定义宠物模型
class Pet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    gender = db.Column(db.String(20))
    personality = db.Column(db.String(200))
    hobby = db.Column(db.String(200))
    story = db.Column(db.Text)
    generated_image = db.Column(db.String(255))
    model_url = db.Column(db.String(255))
    preview_url = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')  # 添加状态字段
    task_id = db.Column(db.String(100), nullable=True)    # 添加任务ID字段

# 定义用户模型
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    douyin_id = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    pets = db.relationship('Pet', backref='owner', lazy=True)

# 定义聊天记录模型
class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    is_user = db.Column(db.Boolean, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    pet_id = db.Column(db.Integer, db.ForeignKey('pet.id'), nullable=False)

# 健康检查路由
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'message': 'Backend service is running'})

# 抖音登录API - 根据code获取用户信息
@app.route('/api/users/login', methods=['POST'])
def douyin_login():
    try:
        data = request.json
        code = data.get('code')
        
        if not code:
            return jsonify({'error': 'Missing code parameter'}), 400
        
        # 尝试获取真实的抖音用户信息
        try:
            # 检查环境变量是否配置
            douyin_appid = os.getenv('DOUYIN_APPID')
            douyin_secret = os.getenv('DOUYIN_SECRET')
            
            if not douyin_appid or not douyin_secret:
                print('警告：抖音AppID或Secret未配置，使用模拟数据')
                raise ValueError('抖音配置缺失')
                
            # 调用抖音开放平台接口获取用户信息
            jscode2session_url = f"https://developer.toutiao.com/api/apps/jscode2session?appid={douyin_appid}&secret={douyin_secret}&code={code}"
            print(f'调用抖音接口: {jscode2session_url}')
            
            # 使用urllib.request替代requests
            with urllib.request.urlopen(jscode2session_url) as response:
                response_data = json.loads(response.read().decode())
            
            # 检查响应是否成功
            if 'openid' not in response_data:
                print(f'抖音接口返回错误: {response_data}')
                raise ValueError(f'抖音接口调用失败: {response_data.get("errmsg", "未知错误")}')
            
            # 获取用户信息
            douyin_id = response_data['openid']
            
            print(f'抖音登录成功，用户openid: {douyin_id}')
            
        except Exception as e:
            print(f'抖音接口调用异常: {str(e)}')
            # 如果调用失败，降级使用模拟数据
            douyin_id = 'douyin_' + str(hash(code))
            print(f'使用模拟数据，生成用户id: {douyin_id}')
        
        # 检查用户是否已存在
        user = User.query.filter_by(douyin_id=douyin_id).first()
        if not user:
            # 创建新用户
            user = User(douyin_id=douyin_id)
            db.session.add(user)
            db.session.commit()
            print(f"新用户创建成功，抖音ID: {douyin_id}")
        else:
            print(f"用户登录成功，抖音ID: {douyin_id}")
        
        return jsonify({
            'user_id': user.id,
            'douyin_id': user.douyin_id
        })
    except Exception as e:
        print(f"登录过程发生错误: {str(e)}")
        # 发生错误时，使用模拟数据确保小程序能正常运行
        douyin_id = 'douyin_' + str(hash(code))
        user = User.query.filter_by(douyin_id=douyin_id).first()
        if not user:
            user = User(douyin_id=douyin_id)
            db.session.add(user)
            db.session.commit()
        return jsonify({
            'user_id': user.id,
            'douyin_id': user.douyin_id
        })

# 通过抖音ID获取或创建用户（保留原有接口，用于兼容）
@app.route('/api/users/douyin/<string:douyin_id>', methods=['GET'])
def get_or_create_user(douyin_id):
    # 检查用户是否已存在
    user = User.query.filter_by(douyin_id=douyin_id).first()
    if not user:
        # 创建新用户
        user = User(douyin_id=douyin_id)
        db.session.add(user)
        db.session.commit()
    return jsonify({'id': user.id, 'douyin_id': user.douyin_id})

# 图片上传API
@app.route('/api/upload', methods=['POST'])
def upload_file():
    # 检查是否有文件部分
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': '没有文件部分'}), 400
    
    file = request.files['file']
    
    # 检查文件名是否为空
    if file.filename == '':
        return jsonify({'status': 'error', 'message': '没有选择文件'}), 400
    
    # 检查文件类型是否允许
    if file and allowed_file(file.filename):
        # 生成安全的文件名
        filename = secure_filename(file.filename)
        # 添加唯一标识符以避免文件名冲突
        unique_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
        
        # 保存文件
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
        
        # 构建文件URL
        file_url = f"http://{request.host}/uploads/{unique_filename}"
        
        return jsonify({
            'status': 'success',
            'message': '文件上传成功',
            'file_url': file_url
        }), 201
    else:
        return jsonify({'status': 'error', 'message': '不支持的文件类型'}), 400

# 提供上传文件的访问
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# 检查用户是否有宠物
@app.route('/api/users/<int:user_id>/has_pets', methods=['GET'])
def check_user_has_pets(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    # 检查用户是否有宠物
    has_pets = len(user.pets) > 0
    return jsonify({'has_pets': has_pets})

# 获取用户的最新宠物信息
@app.route('/api/users/<int:user_id>/latest_pet', methods=['GET'])
def get_user_latest_pet(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # 获取用户的最新宠物（按创建时间排序）
    latest_pet = Pet.query.filter_by(user_id=user_id).order_by(Pet.created_at.desc()).first()
    
    if not latest_pet:
        return jsonify({'error': 'No pets found for this user'}), 404
    
    pet_data = {
        'id': latest_pet.id,
        'name': latest_pet.name,
        'type': latest_pet.type,
        'gender': latest_pet.gender,
        'personality': latest_pet.personality,
        'hobby': latest_pet.hobby,
        'story': latest_pet.story,
        'generated_image': latest_pet.generated_image,
        'model_url': latest_pet.model_url,
        'preview_url': latest_pet.preview_url,
        'created_at': latest_pet.created_at.isoformat()
    }
    
    return jsonify({'status': 'success', 'data': pet_data})

# 创建宠物路由(保留以兼容旧版本，建议使用新的集成API)
@app.route('/api/pets', methods=['POST'])
def create_pet():
    data = request.json
    try:
        new_pet = Pet(
            name=data.get('name'),
            type=data.get('type'),
            gender=data.get('gender'),
            personality=data.get('personality'),
            hobby=data.get('hobby'),
            story=data.get('story'),
            generated_image=data.get('generated_image'),
            model_url=data.get('model_url'),
            user_id=data.get('user_id')
        )
        db.session.add(new_pet)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Pet created successfully', 'pet_id': new_pet.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

# 导入任务管理器
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from task_manager import submit_3d_model_task

# 集成创建宠物和生成3D模型的API
@app.route('/api/pets/create-with-3d', methods=['POST'])
def create_pet_with_3d_model():
    try:
        # 记录请求开始时间
        start_time = time.time()
        logger.info(f"接收到创建宠物和3D模型的请求，用户ID: {request.json.get('user_id') if request.json else '未知'}")
        
        data = request.json
        # 验证必要数据
        if not data or not data.get('name') or not data.get('user_id'):
            logger.error("无效的请求数据")
            return jsonify({'status': 'error', 'message': '缺少必要参数'}), 400
        
        # 创建宠物描述
        pet_data = {
            'name': data.get('name'),
            'type': data.get('type'),
            'gender': data.get('gender'),
            'personality': data.get('personality'),
            'hobby': data.get('hobby'),
            'story': data.get('story')
        }
        
        # 导入3D模型生成模块中的create_pet_description函数
        from generate_3d_model import create_pet_description
        prompt = create_pet_description(pet_data)
        logger.info(f"生成3D模型的提示词: {prompt}")
        
        # 使用图片URL（如果有）
        generated_image = data.get('generated_image')
        image_url = generated_image if generated_image and isinstance(generated_image, str) and generated_image.startswith('http') else None
        
        # 先创建宠物记录（初始状态为pending）
        new_pet = Pet(
            name=data.get('name'),
            type=data.get('type'),
            gender=data.get('gender'),
            personality=data.get('personality'),
            hobby=data.get('hobby'),
            story=data.get('story'),
            generated_image=data.get('generated_image'),
            model_url=None,  # 初始为None，等待异步任务完成后更新
            preview_url=None,  # 初始为None
            user_id=data.get('user_id'),
            status='pending'  # 设置初始状态为pending
        )
        
        db.session.add(new_pet)
        db.session.commit()
        
        # 提交异步3D模型生成任务
        task_id = submit_3d_model_task(image_url=image_url, prompt=prompt, pet_id=new_pet.id)
        
        # 更新宠物记录的任务ID
        new_pet.task_id = task_id
        db.session.commit()
        
        # 记录请求完成时间
        elapsed_time = time.time() - start_time
        logger.info(f"创建宠物和提交3D模型生成任务完成，耗时: {elapsed_time:.2f}秒")
        
        # 立即返回响应，不等待任务完成
        return jsonify({
            'status': 'success',
            'message': '宠物创建成功，3D模型生成任务已提交',
            'pet_id': new_pet.id,
            'task_id': task_id,
            'status': 'pending'
        }), 202
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"创建宠物时出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

# 获取宠物详情路由
@app.route('/api/pets/<int:pet_id>', methods=['GET'])
def get_pet(pet_id):
    pet = Pet.query.get_or_404(pet_id)
    # 添加宠物状态信息，用于前端轮询判断3D模型生成状态
    pet_data = {
        'id': pet.id,
        'name': pet.name,
        'type': pet.type,
        'gender': pet.gender,
        'personality': pet.personality,
        'hobby': pet.hobby,
        'story': pet.story,
        'generated_image': pet.generated_image,
        'model_url': pet.model_url,
        'preview_url': pet.preview_url,
        'created_at': pet.created_at.isoformat(),
        'status': pet.status,  # 包含宠物状态信息
        'task_id': pet.task_id  # 包含任务ID
    }
    # 直接在根级别返回状态信息，方便前端直接获取
    return jsonify({'status': pet.status, **pet_data})

# 添加聊天记录路由
@app.route('/api/pets/<int:pet_id>/chats', methods=['POST'])
def add_chat(pet_id):
    data = request.json
    try:
        new_chat = Chat(
            content=data.get('content'),
            is_user=data.get('is_user'),
            pet_id=pet_id
        )
        db.session.add(new_chat)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Chat added successfully'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500

# 获取聊天记录路由
@app.route('/api/pets/<int:pet_id>/chats', methods=['GET'])
def get_chats(pet_id):
    chats = Chat.query.filter_by(pet_id=pet_id).order_by(Chat.created_at).all()
    chat_data = [{
        'id': chat.id,
        'content': chat.content,
        'is_user': chat.is_user,
        'created_at': chat.created_at.isoformat()
    } for chat in chats]
    return jsonify({'status': 'success', 'data': chat_data})

# 导入聊天模块
from chat import chat_with_ai, init_pet_profile

# 获取AI回复路由
@app.route('/api/pets/<int:pet_id>/reply', methods=['POST'])
def get_ai_reply(pet_id):
    data = request.json
    user_message = data.get('content', '')
    user_id = data.get('user_id', 99)  # 默认使用测试用户ID
    
    # 获取宠物信息
    pet = Pet.query.get_or_404(pet_id)
    
    # 构建宠物档案
    pet_profile = init_pet_profile()
    pet_profile.update({
        'pet_name': pet.name,
        'species_breed': pet.type,
        'gender': pet.gender,
        'birthday': '2023-01-01',  # 默认生日
        'appearance': pet.story or '可爱的宠物',
        'core_personality': pet.personality or '友好',
        'likes': pet.hobby or '和主人玩耍',
        'system_current_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'local_weather_data': {
            'weather': '晴朗',
            'temperature': '25℃',
            'wind': '微风'
        }
    })
    
    try:
        # 调用AI聊天功能
        ai_response = chat_with_ai(user_id, pet_profile, user_message)
        
        if isinstance(ai_response, dict):
            # 格式化返回数据
            result = {
                'id': datetime.now().timestamp(),
                'content': ai_response.get('main_reply', '我现在有点忙，稍后再和你聊吧~'),
                'mood_level': ai_response.get('intimacy_level', 3)
            }
            
            # 保存AI回复到数据库
            new_chat = Chat(
                content=result['content'],
                is_user=False,
                pet_id=pet_id
            )
            db.session.add(new_chat)
            db.session.commit()
            
            return jsonify({'status': 'success', 'data': result})
        else:
            # 如果返回的是错误信息
            return jsonify({'status': 'error', 'message': ai_response}), 500
    except Exception as e:
        print(f"获取AI回复时发生错误: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# 聊天API（兼容前端companion.js的调用路径）
@app.route('/api/pets/<int:pet_id>/chat', methods=['POST'])
def chat_with_pet(pet_id):
    data = request.json
    user_message = data.get('message', '')
    user_id = data.get('user_id', 99)
    
    # 先保存用户消息到数据库
    try:
        new_chat = Chat(
            content=user_message,
            is_user=True,
            pet_id=pet_id
        )
        db.session.add(new_chat)
        db.session.commit()
    except Exception as e:
        print(f"保存用户消息时发生错误: {str(e)}")
        # 即使保存失败，也继续获取AI回复
    
    try:
        # 获取宠物信息
        pet = Pet.query.get_or_404(pet_id)
        
        # 构建宠物档案
        pet_profile = init_pet_profile()
        pet_profile.update({
            'pet_name': pet.name,
            'species_breed': pet.type,
            'gender': pet.gender,
            'birthday': '2023-01-01',  # 默认生日
            'appearance': pet.story or '可爱的宠物',
            'core_personality': pet.personality or '友好',
            'likes': pet.hobby or '和主人玩耍',
            'system_current_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'local_weather_data': {
                'weather': '晴朗',
                'temperature': '25℃',
                'wind': '微风'
            }
        })
        
        # 直接调用AI聊天功能
        ai_response = chat_with_ai(user_id, pet_profile, user_message)
        
        if isinstance(ai_response, dict):
            # 格式化返回数据
            result = {
                'id': datetime.now().timestamp(),
                'content': ai_response.get('main_reply', '我现在有点忙，稍后再和你聊吧~'),
                'mood_level': ai_response.get('intimacy_level', 3),
                'text': ai_response.get('main_reply', '我现在有点忙，稍后再和你聊吧~')  # 兼容前端的text字段
            }
            
            # 保存AI回复到数据库
            new_chat = Chat(
                content=result['content'],
                is_user=False,
                pet_id=pet_id
            )
            db.session.add(new_chat)
            db.session.commit()
            
            from flask import make_response, json
            return make_response(json.dumps({'status': 'success', 'data': result}), 200, {'Content-Type': 'application/json'})
        else:
            # 如果返回的是错误信息
            from flask import make_response, json
            return make_response(json.dumps({'status': 'error', 'message': ai_response}), 500, {'Content-Type': 'application/json'})
    except Exception as e:
        print(f"获取AI回复时发生错误: {str(e)}")
        from flask import make_response, json
        return make_response(json.dumps({'status': 'error', 'message': str(e)}), 500, {'Content-Type': 'application/json'})

# 聊天历史API（兼容前端companion.js的调用路径）
@app.route('/api/pets/<int:pet_id>/chat_history', methods=['GET'])
def get_pet_chat_history(pet_id):
    # 调用现有的get_chats函数
    from flask import make_response, json
    response = get_chats(pet_id)
    
    # 转换为字典格式以便处理
    if isinstance(response, tuple):
        response_data, status_code = response
        response_data = json.loads(response_data.data)
    else:
        response_data = json.loads(response.data)
        status_code = 200
    
    # 确保返回格式符合前端期望
    if response_data.get('status') == 'success' and response_data.get('data'):
        # 格式化聊天记录以兼容前端
        formatted_messages = []
        for chat in response_data['data']:
            formatted_messages.append({
                'id': chat['id'],
                'text': chat['content'],
                'isUser': chat['is_user'],
                'timestamp': datetime.fromisoformat(chat['created_at']).timestamp()
            })
        response_data['data'] = formatted_messages
    
    return make_response(json.dumps(response_data), status_code, {'Content-Type': 'application/json'})

# 创建数据库表


# 生成3D模型API
@app.route('/api/pets/<int:pet_id>/generate-3d-model', methods=['POST'])
def generate_pet_3d_model(pet_id):
    try:
        # 检查宠物是否存在
        pet = Pet.query.get(pet_id)
        if not pet:
            return jsonify({'status': 'error', 'message': '宠物不存在'}), 404
        
        # 导入3D模型生成模块
        import sys
        from generate_3d_model import generate_3d_model, create_pet_description
        
        # 创建宠物描述
        pet_data = {
            'name': pet.name,
            'type': pet.type,
            'gender': pet.gender,
            'personality': pet.personality,
            'hobby': pet.hobby,
            'story': pet.story
        }
        
        prompt = create_pet_description(pet_data)
        print(f"生成3D模型的提示词: {prompt}")
        
        # 使用图片URL（如果有）或使用描述来生成3D模型
        image_url = None
        if pet.generated_image and pet.generated_image.startswith('http'):
            image_url = pet.generated_image
        
        # 调用3D模型生成函数
        result = generate_3d_model(image_url=image_url, prompt=prompt)
        
        if not result:
            return jsonify({'status': 'error', 'message': '3D模型生成失败'}), 500
        
        # 获取OBJ文件信息（3D模型主要文件）
        file_urls = result.get('file_urls', {})
        model_file = file_urls.get('OBJ') or file_urls.get('GIF')  # 优先使用OBJ，没有则使用GIF
        
        if not model_file:
            return jsonify({'status': 'error', 'message': '未能获取到模型文件URL'}), 500
        
        # 优先使用处理后的本地OBJ文件路径，如果没有则使用原始URL
        model_url = model_file.get('local_path', '') or model_file.get('url', '')
        
        if not model_url:
            return jsonify({'status': 'error', 'message': '未能提取到模型文件URL'}), 500
        
        # 更新数据库中的模型URL
        pet.model_url = model_url
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': '3D模型生成成功',
            'model_url': model_url,
            'file_urls': file_urls
        }), 200
        
    except Exception as e:
        print(f"生成3D模型时发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f'生成3D模型时发生错误: {str(e)}'}), 500

# 查询3D模型生成任务状态
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from task_manager import get_task_status

@app.route('/api/pets/<int:pet_id>/task-status', methods=['GET'])
def get_pet_task_status(pet_id):
    try:
        # 首先检查宠物是否存在
        pet = Pet.query.get(pet_id)
        if not pet:
            return jsonify({'status': 'error', 'message': '宠物不存在'}), 404
        
        # 获取宠物的状态和任务ID
        pet_status = pet.status
        task_id = pet.task_id
        
        # 如果任务ID存在，尝试从任务管理器获取详细状态
        if task_id:
            task_status = get_task_status(task_id)
            
            # 构建响应数据
            response = {
                'status': 'success',
                'pet_id': pet_id,
                'pet_status': pet_status,
                'task_id': task_id,
                'task_progress': task_status.get('progress', 0),
                'task_details': task_status.get('details', {})
            }
            
            # 如果任务已完成，包含模型URL
            if pet_status == 'completed' and pet.model_url:
                response['model_url'] = pet.model_url
                response['preview_url'] = pet.preview_url
            
            return jsonify(response), 200
        else:
            # 如果没有任务ID，仅返回宠物状态
            response = {
                'status': 'success',
                'pet_id': pet_id,
                'pet_status': pet_status,
                'message': '没有关联的任务ID'
            }
            return jsonify(response), 200
            
    except Exception as e:
        logger.error(f"查询任务状态时出错: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)