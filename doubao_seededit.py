import os
# 通过 pip install 'volcengine-python-sdk[ark]' 安装方舟SDK
from volcenginesdkarkruntime import Ark

def generate_image_with_doubao(
        prompt: str,
        image_input: str,
        seed: int = 123,
        guidance_scale: float = 5.5,
        size: str = "adaptive",
        watermark: bool = True,
        api_key: str = "a8713c43-079c-4971-89db-b0ba6b41343f",
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    ):
        """
        使用豆包模型生成图片
        
        Args:
            prompt (str): 图片生成提示词
            image_input (str): 输入图片的URL或本地文件路径
            seed (int): 随机种子，默认为123
            guidance_scale (float): 引导比例，默认为5.5
            size (str): 图片尺寸，默认为"adaptive"
            watermark (bool): 是否添加水印，默认为True
            api_key (str): API密钥
            base_url (str): API基础URL
        
        Returns:
            str: 生成图片的URL
        """
        # 初始化Ark客户端
        client = Ark(
            base_url=base_url,
            api_key=api_key,
        )
        
        # 处理输入图片（URL或本地文件）
        if os.path.exists(image_input):
            # 本地文件，转换为base64
            import base64
            with open(image_input, "rb") as f:
                image_data = f.read()
                image_base64 = base64.b64encode(image_data).decode('utf-8')
                # 构造data URL
                image_url = f"data:image/jpeg;base64,{image_base64}"
        else:
            # 网络URL
            image_url = image_input
        
        system_prompt = '''
        基于参考照片动物，精准复刻特征，生成ip形象设计图。首先，让宠物处于宠物的站立姿势、每一个色块的颜色和具体位置要百分百还原。
        背景为纯白色（RGB 255,255,255），无杂色。结合用户描述特征【{}】，毛发还原毛色（含饱和度、渐变），完全还原毛发走势和质感（例如体现短毛颗粒感或长毛蓬松度），胡须保色泽韧性。
        五官复刻眼球颜色、瞳孔形状，眼周毛走向，鼻子质感，嘴唇弧度；耳朵还原大小、弧度及内侧绒毛。肢体按原图比例：颈、躯干、四肢骨骼，脚掌肉垫，尾巴形态。站姿符合习性，自然协调。
        3D 渲染达高精度，毛发用 PBR 材质，显光影细节；三点布光，明暗分明。形象保留原生特征，强化细节、增强亲和力。'''.format(prompt)
        
        # 生成图片
        imagesResponse = client.images.generate(
            model="doubao-seededit-3-0-i2i-250628",
            prompt=system_prompt,
            image=image_url,
            seed=seed,
            guidance_scale=guidance_scale,
            size=size,
            watermark=watermark 
        )
        
        return imagesResponse.data[0].url


# 示例使用
if __name__ == "__main__":
    # ”图+文“ ----> 图
    user_prompt = "这是一只猕猴，平时活奔乱跳，很喜欢到处爬，看到人的时候特别喜欢大喊大叫"
    result_url = generate_image_with_doubao(
        prompt=user_prompt,
        image_input="storage/test2.jpeg"
    )

    print(result_url)

    ''' result_url 示例
    https://ark-content-generation-v2-cn-beijing.tos-cn-beijing.volces.com/doubao-seededit-3-0-i2i/021755419250458d5bbc3e631479c4deb362d20ba806f7898fe59.jpeg?X-Tos-Algorithm=TOS4-HMAC-SHA256&X-T
    os-Credential=AKLTYWJkZTExNjA1ZDUyNDc3YzhjNTM5OGIyNjBhNDcyOTQ%2F20250817%2Fcn-
    beijing%2Ftos%2Frequest&X-Tos-Date=20250817T082741Z&X-Tos-Expires=86400&X-Tos-Sign
    ature=8eb7c27b5d7a3fb3ffc5ebf6c42aa7517b4fe79d7edcf3fd1dca0068cb91e4d4&X-Tos-Signed
    Headers=host&x-tos-process=image%2Fwatermark%2Cimage_YXNzZXRzL3dhdGVybWFyay5wbmc_eC1
    0b3MtcHJvY2Vzcz1pbWFnZS9yZXNpemUsUF8xNg%3D%3D
    '''
