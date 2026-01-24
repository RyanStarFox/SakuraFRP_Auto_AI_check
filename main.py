import sys
import io
import time
import random
import re
import argparse
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright
from ai_service import AIService
from logger import CheckinLogger

# 强制 Windows 终端使用 UTF-8 编码
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# ========= 配置 =========
BASE_DIR = Path(__file__).resolve().parent
domain = "www.natfrp.com"
target_url = f"https://{domain}/user/"

ACCOUNT_FILE = BASE_DIR / "account.txt"  
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

# ---------------- 验证码核心处理 ----------------
def solve_geetest_multistep(page, ai_service):
    """使用AI服务处理九宫格验证码"""
    print("[INFO] 开始处理九宫格验证码...")
    
    img_container = page.locator(".geetest_table_box").first
    if not img_container.is_visible():
        return False
        
    # 步骤 1: 识别题目
    target_object = ""
    tip_img = page.locator(".geetest_tip_img").first
    if tip_img.is_visible():
        target_object = ai_service.call_vision(tip_img.screenshot(), "图中是什么物体？只回答物体名称，不要带标点。")
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
        row_res = ai_service.identify_captcha_row(buf.getvalue(), i+1)
        all_descriptions.extend(row_res)

    # 步骤 5: 语义匹配并模拟点击
    click_indices = ai_service.semantic_match(target_object, all_descriptions)
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
        except: 
            continue
            
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
    except: 
        pass
    return None

def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='SakuraFRP自动签到脚本')
    parser.add_argument('--screenshot-only', action='store_true', help='仅记录截图，不记录日志')
    parser.add_argument('--log-only', action='store_true', help='仅记录日志，不保存截图')
    parser.add_argument('--both', action='store_true', help='同时记录截图和日志（默认）')
    args = parser.parse_args()
    
    # 确定记录模式
    if args.screenshot_only:
        save_screenshot = True
        save_log = False
    elif args.log_only:
        save_screenshot = False
        save_log = True
    else:
        # 默认或--both都是两者都要
        save_screenshot = True
        save_log = True
    
    # 初始化日志记录器（如果需要）
    logger = None
    if save_log:
        logger = CheckinLogger(BASE_DIR)
        logger.log_start()
    
    # 初始化AI服务
    try:
        ai_service = AIService()
    except Exception as e:
        error_msg = f"AI服务初始化失败: {e}"
        print(f"[ERROR] {error_msg}")
        if logger:
            logger.log_error(error_msg)
        return
    
    # 加载账号信息
    try:
        username, password = load_username_password(ACCOUNT_FILE)
    except Exception as e:
        error_msg = f"加载账号信息失败: {e}"
        print(f"[ERROR] {error_msg}")
        if logger:
            logger.log_error(error_msg)
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, slow_mo=100)
        context = browser.new_context(storage_state=STATE_FILE if STATE_FILE.exists() else None)
        page = context.new_page()
        page.set_viewport_size({"width": 1280, "height": 900})
        
        print(f"[INFO] 正在访问: {target_url}")
        if logger:
            logger.log_info(f"正在访问: {target_url}")
        
        page.goto(target_url)

        # 登录判断
        is_logged_in = True
        if "login" in page.url or page.locator("#username").is_visible():
            is_logged_in = False
            print("[INFO] 正在执行登录...")
            if logger:
                logger.log_login_status(False)
            
            page.fill("#username", username)
            page.fill("#password", password)
            page.click("#login")
            try:
                page.wait_for_selector("text=账号信息", timeout=10000)
                context.storage_state(path=STATE_FILE)
                is_logged_in = True
                if logger:
                    logger.log_login_status(True)
            except:
                error_msg = "登录超时或失败"
                print(f"[ERROR] {error_msg}")
                if logger:
                    logger.log_error(error_msg)
        else:
            if logger:
                logger.log_login_status(True)

        # 18岁弹窗
        try:
            btn_18 = page.get_by_text("是，我已满18岁")
            if btn_18.is_visible(timeout=3000): 
                btn_18.click()
        except: 
            pass

        # 签到
        if find_signed_text_locator(page):
            print("[INFO] 今日已签到。")
            if logger:
                logger.log_already_signed()
        else:
            sign_btn = page.get_by_text("点击这里签到")
            if sign_btn.is_visible():
                sign_btn.click()
                # 循环检测验证码或成功状态
                sign_success = False
                for _ in range(15):
                    if find_signed_text_locator(page, timeout=1000):
                        print("[SUCCESS] 签到完成！")
                        sign_success = True
                        if logger:
                            logger.log_sign_success()
                        break
                    if page.locator(".geetest_table_box").is_visible():
                        captcha_result = solve_geetest_multistep(page, ai_service)
                        if logger:
                            logger.log_captcha_result("成功" if captcha_result else "失败")
                        time.sleep(3)
                    time.sleep(1)
                
                if not sign_success:
                    error_msg = "签到失败：超时或验证码处理失败"
                    print(f"[ERROR] {error_msg}")
                    if logger:
                        logger.log_sign_failed(error_msg)
            else:
                error_msg = "未找到签到按钮"
                print(f"[ERROR] {error_msg}")
                if logger:
                    logger.log_sign_failed(error_msg)

        # 截图存证（如果需要）
        if save_screenshot:
            success_loc = find_signed_text_locator(page)
            if success_loc:
                try:
                    # 尝试截取父级区域，让截图更美观
                    success_loc.locator(f"xpath=ancestor::*[{SIGNED_ANCESTOR_LEVELS}]").first.screenshot(path=SUCCESS_SCREENSHOT)
                    print(f"[INFO] 截图已保存: {SUCCESS_SCREENSHOT}")
                except:
                    page.screenshot(path=SUCCESS_SCREENSHOT)
                    print(f"[INFO] 截图已保存: {SUCCESS_SCREENSHOT}")
        
        print("[INFO] 脚本运行结束。")
        browser.close()

if __name__ == "__main__":
    main()
