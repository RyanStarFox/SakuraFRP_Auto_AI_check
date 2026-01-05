import sys
import io
import time
import random
import base64
import json
import re
from pathlib import Path
from zhipuai import ZhipuAI
from PIL import Image
from playwright.sync_api import sync_playwright

# 强制 Windows 终端使用 UTF-8 编码
sys.stdout.reconfigure(encoding='utf-8')

# ========= 配置 =========
BASE_DIR = Path(__file__).resolve().parent
domain = "www.natfrp.com"
target_url = f"https://{domain}/user/"

ACCOUNT_FILE = BASE_DIR / "account.txt"  
API_KEY_FILE = BASE_DIR / "APIKey.txt"   
STATE_FILE = BASE_DIR / "state.json"     
SUCCESS_SCREENSHOT = BASE_DIR / "checkin.png"

ALREADY_SIGNED_TEXT = "今天已经签到过啦"       
SIGNED_ANCESTOR_LEVELS = 3                

# ---------------- 工具函数 ----------------
def load_file_content(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    return path.read_text(encoding="utf-8").strip()

def load_username_password(path: Path):
    content = load_file_content(path)
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    if len(lines) < 2:
        raise ValueError("account.txt 格式错误：需两行分别存放用户名和密码")
    return lines[0], lines[1]

def safe_parse_json(text):
    """强力解析 AI 返回的 JSON 列表"""
    try:
        # 尝试使用正则提取最近的一组方括号内容
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(text)
    except Exception:
        return None

# ---------------- AI 交互逻辑 ----------------
def call_zhipu_vision(image_bytes, prompt, api_key, model="glm-4v-flash"):
    """调用智谱多模态模型"""
    client = ZhipuAI(api_key=api_key)
    base64_data = base64.b64encode(image_bytes).decode('utf-8')
    try:
        response = client.chat.completions.create(
            model=model,
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

def step_2_3_4_identify_row(row_img_bytes, api_key, row_index):
    """分行识别逻辑"""
    prompt = "这是验证码的一行图片，包含3个格子。请从左到右识别这3个格子的物体名称，只返回一个 JSON 字符串数组，例如：[\"猫\", \"狗\", \"汽车\"]。不要有任何解释文字。"
    res = call_zhipu_vision(row_img_bytes, prompt, api_key)
    print(f"[AI] 第 {row_index} 行识别结果: {res}")
    
    parsed = safe_parse_json(res)
    if parsed and isinstance(parsed, list):
        # 确保返回 3 个元素
        while len(parsed) < 3: parsed.append("未知")
        return parsed[:3]
    return ["未知", "未知", "未知"]

def step_5_semantic_match(target, descriptions, api_key):
    """语义裁决逻辑"""
    items_text = "\n".join([f"{i+1}. {d}" for i, d in enumerate(descriptions)])
    prompt = f"题目是：找出图片中所有的【{target}】。\n当前 9 个格子的识别结果如下：\n{items_text}\n请根据描述，判断哪些序号（1-9）最符合题目要求？\n返回格式：只返回 JSON 数组，如 [1, 3, 5]。如果没有符合的，返回空数组 []。"
    
    print(f"[Debug] 正在进行语义裁决，描述列表：\n{items_text}")
    
    client = ZhipuAI(api_key=api_key)
    try:
        response = client.chat.completions.create(
            model="glm-4-flash", 
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content.strip()
        print(f"[AI] 语义裁决原始输出: {content}")
        parsed = safe_parse_json(content)
        return parsed if isinstance(parsed, list) else []
    except Exception as e:
        print(f"[ERROR] 语义匹配失败: {e}")
        return []

# ---------------- 验证码核心处理 ----------------
def solve_geetest_multistep(page, api_key):
    print("[INFO] 开始处理九宫格验证码...")
    
    img_container = page.locator(".geetest_table_box").first
    if not img_container.is_visible():
        return False
        
    # 步骤 1: 识别题目
    target_object = ""
    tip_img = page.locator(".geetest_tip_img").first
    if tip_img.is_visible():
        target_object = call_zhipu_vision(tip_img.screenshot(), "图中是什么物体？只回答物体名称，不要带标点。", api_key)
    else:
        tip_text_loc = page.locator(".geetest_tip_content").first
        if tip_text_loc.is_visible():
            target_object = tip_text_loc.inner_text()
    
    target_object = re.sub(r'[^\w]', '', target_object) # 过滤掉标点
    print(f">>> [Step 1] 识别题目为：【{target_object}】")

    # 步骤 2-4: 逐行抠图识别
    all_descriptions = []
    # 获取整个九宫格的截图并在内存中处理
    grid_bytes = img_container.screenshot()
    grid_img = Image.open(io.BytesIO(grid_bytes))
    w, h = grid_img.size
    row_h = h / 3
    
    for i in range(3):
        # 裁剪出每一行
        top = i * row_h
        bottom = (i + 1) * row_h
        row_crop = grid_img.crop((0, top, w, bottom))
        
        buf = io.BytesIO()
        row_crop.save(buf, format='PNG')
        row_res = step_2_3_4_identify_row(buf.getvalue(), api_key, i+1)
        all_descriptions.extend(row_res)

    # 步骤 5: 语义匹配并模拟点击
    click_indices = step_5_semantic_match(target_object, all_descriptions, api_key)
    print(f">>> [Final] 最终决定点击序号: {click_indices}")
    
    if not click_indices:
        print("[INFO] 未找到匹配项，刷新验证码...")
        page.locator(".geetest_refresh").first.click()
        time.sleep(2)
        return False

    box = img_container.bounding_box()
    cell_w, cell_h = box['width']/3, box['height']/3
    
    for idx in click_indices:
        try:
            val = int(idx)
            if 1 <= val <= 9:
                r, c = (val-1)//3, (val-1)%3
                # 点击格子的中心点
                target_x = box['x'] + c*cell_w + cell_w/2
                target_y = box['y'] + r*cell_h + cell_h/2
                page.mouse.click(target_x, target_y)
                time.sleep(random.uniform(0.3, 0.5))
        except: continue
            
    # 提交验证
    for sel in [".geetest_commit", "text=确认", ".geetest_submit"]:
        btn = page.locator(sel).first
        if btn.is_visible():
            btn.click()
            break
    return True

# ---------------- 主逻辑 ----------------
def find_signed_text_locator(page, timeout=3000):
    try:
        loc = page.get_by_text(ALREADY_SIGNED_TEXT).first
        if loc.is_visible(timeout=timeout):
            return loc
    except: pass
    return None

def main():
    username, password = load_username_password(ACCOUNT_FILE)
    api_key = load_file_content(API_KEY_FILE)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=100)
        context = browser.new_context(storage_state=STATE_FILE if STATE_FILE.exists() else None)
        page = context.new_page()
        page.set_viewport_size({"width": 1280, "height": 900})
        
        print(f"[INFO] 正在访问: {target_url}")
        page.goto(target_url)

        # 登录判断
        if "login" in page.url or page.locator("#username").is_visible():
            print("[INFO] 正在执行登录...")
            page.fill("#username", username)
            page.fill("#password", password)
            page.click("#login")
            try:
                page.wait_for_selector("text=账号信息", timeout=10000)
                context.storage_state(path=STATE_FILE)
            except:
                print("[ERROR] 登录超时或失败")

        # 18岁弹窗
        try:
            btn_18 = page.get_by_text("是，我已满18岁")
            if btn_18.is_visible(timeout=3000): btn_18.click()
        except: pass

        # 签到
        if find_signed_text_locator(page):
            print("[INFO] 今日已签到。")
        else:
            sign_btn = page.get_by_text("点击这里签到")
            if sign_btn.is_visible():
                sign_btn.click()
                # 循环检测验证码或成功状态
                for _ in range(15):
                    if find_signed_text_locator(page, timeout=1000):
                        print("[SUCCESS] 签到完成！")
                        break
                    if page.locator(".geetest_table_box").is_visible():
                        solve_geetest_multistep(page, api_key)
                        time.sleep(3)
                    time.sleep(1)

        # 截图存证
        success_loc = find_signed_text_locator(page)
        if success_loc:
            try:
                # 尝试截取父级区域，让截图更美观
                success_loc.locator(f"xpath=ancestor::*[{SIGNED_ANCESTOR_LEVELS}]").first.screenshot(path=SUCCESS_SCREENSHOT)
                print(f"[INFO] 截图已保存: {SUCCESS_SCREENSHOT}")
            except:
                page.screenshot(path=SUCCESS_SCREENSHOT)
        
        print("[INFO] 脚本运行结束。")
        browser.close()

if __name__ == "__main__":
    main()