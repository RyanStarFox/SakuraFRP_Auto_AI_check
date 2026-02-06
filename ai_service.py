import base64
import json
import re
import os
from dotenv import load_dotenv
from zhipuai import ZhipuAI

# 加载环境变量
load_dotenv()

class AIService:
    """AI服务类，封装所有AI调用逻辑"""
    
    def __init__(self):
        """初始化AI服务，从环境变量读取配置"""
        self.api_key = os.getenv("ZHIPU_API_KEY", "")
        self.model_vision = os.getenv("ZHIPU_MODEL_VISION", "glm-4v-flash")
        self.model_text = os.getenv("ZHIPU_MODEL_TEXT", "glm-4-flash")
        
        if not self.api_key:
            raise ValueError("未找到ZHIPU_API_KEY环境变量，请在.env文件中配置")
        
        self.client = ZhipuAI(api_key=self.api_key)
    
    def safe_parse_json(self, text):
        """强力解析 AI 返回的 JSON 列表"""
        try:
            # 尝试使用正则提取最近的一组方括号内容
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return json.loads(text)
        except Exception:
            return None
    
    def call_vision(self, image_bytes, prompt):
        """调用智谱多模态模型"""
        base64_data = base64.b64encode(image_bytes).decode('utf-8')
        try:
            response = self.client.chat.completions.create(
                model=self.model_vision,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": base64_data}}
                    ]
                }]
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[ERROR] AI API 调用失败: {e}")
            return ""
    
    def identify_captcha_row(self, row_img_bytes, row_index):
        """分行识别逻辑"""
        prompt = "这是验证码的一行图片，包含3个格子。请从左到右识别这3个格子的物体名称，只返回一个 JSON 字符串数组，例如：[\"猫\", \"狗\", \"汽车\"]。不要有任何解释文字。"
        res = self.call_vision(row_img_bytes, prompt)
        print(f"[AI] 第 {row_index} 行识别结果: {res}")
        
        parsed = self.safe_parse_json(res)
        if parsed and isinstance(parsed, list):
            # 确保返回 3 个元素
            while len(parsed) < 3:
                parsed.append("未知")
            return parsed[:3]
        return ["未知", "未知", "未知"]
    
    def semantic_match(self, target, descriptions):
        """语义裁决逻辑"""
        items_text = "\n".join([f"{i+1}. {d}" for i, d in enumerate(descriptions)])
        prompt = f"题目是：找出图片中所有的【{target}】。\n当前 9 个格子的识别结果如下：\n{items_text}\n请根据描述，判断哪些序号（1-9）最符合题目要求？\n返回格式：只返回 JSON 数组，如 [1, 3, 5]。如果没有符合的，返回空数组 []。"
        
        print(f"[Debug] 正在进行语义裁决，描述列表：\n{items_text}")
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_text,
                messages=[{"role": "user", "content": prompt}]
            )
            content = response.choices[0].message.content.strip()
            print(f"[AI] 语义裁决原始输出: {content}")
            parsed = self.safe_parse_json(content)
            return parsed if isinstance(parsed, list) else []
        except Exception as e:
            print(f"[ERROR] 语义匹配失败: {e}")
            return []
    
    def identify_slider_gap(self, bg_img_bytes, slice_img_bytes=None):
        """识别滑块验证码的缺口位置"""
        if slice_img_bytes:
            # 如果有缺口图，使用对比识别
            prompt = """这是滑块验证码的两张图片：
1. 第一张是完整的背景图
2. 第二张是带缺口的拼图块

请识别出缺口在背景图中的水平位置（x坐标，单位：像素）。
缺口位置是指拼图块应该放置的位置，即背景图中缺失的那部分对应的x坐标。

只返回一个数字，表示缺口位置的x坐标（像素值），不要有任何其他文字或解释。
例如：如果缺口在100像素的位置，只返回：100"""
            
            base64_bg = base64.b64encode(bg_img_bytes).decode('utf-8')
            base64_slice = base64.b64encode(slice_img_bytes).decode('utf-8')
            
            try:
                response = self.client.chat.completions.create(
                    model=self.model_vision,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": base64_bg}},
                            {"type": "image_url", "image_url": {"url": base64_slice}}
                        ]
                    }]
                )
                result_text = response.choices[0].message.content.strip()
                print(f"[AI] 滑块缺口识别结果（原始）: {result_text}")
                
                # 提取数字
                numbers = re.findall(r'\d+', result_text)
                if numbers:
                    gap_pos = int(numbers[0])
                    print(f"[AI] 识别到的缺口位置: {gap_pos}px")
                    return gap_pos
                else:
                    print(f"[WARNING] 无法从AI结果中提取数字: {result_text}")
                    return 0
            except Exception as e:
                print(f"[ERROR] AI识别滑块缺口失败: {e}")
                return 0
        else:
            # 如果只有背景图，尝试识别缺口特征
            prompt = """这是滑块验证码的背景图。请识别出图片中缺口的位置。
缺口通常是一个不规则的形状，与周围有明显的边缘差异。

请识别出缺口在图片中的水平位置（x坐标，单位：像素）。
只返回一个数字，表示缺口位置的x坐标（像素值），不要有任何其他文字或解释。
例如：如果缺口在100像素的位置，只返回：100"""
            
            base64_bg = base64.b64encode(bg_img_bytes).decode('utf-8')
            
            try:
                response = self.client.chat.completions.create(
                    model=self.model_vision,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": base64_bg}}
                        ]
                    }]
                )
                result_text = response.choices[0].message.content.strip()
                print(f"[AI] 滑块缺口识别结果（原始）: {result_text}")
                
                # 提取数字
                numbers = re.findall(r'\d+', result_text)
                if numbers:
                    gap_pos = int(numbers[0])
                    print(f"[AI] 识别到的缺口位置: {gap_pos}px")
                    return gap_pos
                else:
                    print(f"[WARNING] 无法从AI结果中提取数字: {result_text}")
                    return 0
            except Exception as e:
                print(f"[ERROR] AI识别滑块缺口失败: {e}")
                return 0
