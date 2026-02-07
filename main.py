import sys
import io
import time
import random
import re
import argparse
import traceback
from pathlib import Path
from datetime import datetime, timedelta
from PIL import Image
from playwright.sync_api import sync_playwright
from ai_service import AIService
from logger import CheckinLogger
import pytweening  # 用于缓动函数（无GUI依赖）

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

def clean_old_logs(base_dir: Path, days: int = 30):
    """清理指定天数前的日志文件"""
    logs_dir = base_dir / "logs"
    if not logs_dir.exists():
        return
    
    # 计算截止日期（30天前）
    cutoff_date = datetime.now() - timedelta(days=days)
    
    # 遍历logs目录下的所有文件
    deleted_count = 0
    for log_file in logs_dir.iterdir():
        if not log_file.is_file():
            continue
        
        # 检查是否是日志文件（格式：checkin_YYYY-MM-DD.log）
        if log_file.name.startswith("checkin_") and log_file.name.endswith(".log"):
            try:
                # 从文件名提取日期（checkin_YYYY-MM-DD.log）
                date_str = log_file.name.replace("checkin_", "").replace(".log", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                
                # 如果文件日期早于截止日期，删除文件
                if file_date < cutoff_date:
                    log_file.unlink()
                    deleted_count += 1
                    print(f"[INFO] 已删除旧日志文件: {log_file.name} (日期: {date_str})")
            except ValueError:
                # 如果文件名格式不正确，跳过
                continue
    
    if deleted_count > 0:
        print(f"[INFO] 清理完成，共删除 {deleted_count} 个30天前的日志文件")

# ---------------- 使用专业库识别缺口 ----------------
def identify_gap_with_library(bg_img_bytes, logger=None):
    """使用 captcha-recognizer 库识别滑块验证码缺口位置"""
    try:
        from captcha_recognizer.slider import Slider
        import numpy as np
        from PIL import Image
        
        # 将字节数据转换为 numpy 数组（库支持这种格式）
        bg_img = Image.open(io.BytesIO(bg_img_bytes))
        bg_arr = np.array(bg_img)
        
        # 使用 captcha-recognizer 库识别缺口
        # box 格式: [x1, y1, x2, y2] 对应缺口的左上角和右下角坐标
        # confidence: 置信度
        box, confidence = Slider().identify(source=bg_arr, show=False)
        
        if box and len(box) >= 4:
            x1, y1, x2, y2 = box
            gap_position = int(x1)  # 使用左上角的x坐标作为缺口位置
            print(f"[DEBUG] captcha-recognizer 识别结果: 缺口位置={gap_position}px, 置信度={confidence:.2f}")
            print(f"[DEBUG] 缺口完整坐标: 左上角({x1}, {y1}), 右下角({x2}, {y2})")
            
            if logger:
                logger.log_debug(f"captcha-recognizer: 缺口={gap_position}px, 置信度={confidence:.2f}")
            
            return gap_position
        else:
            print("[WARNING] captcha-recognizer 未识别到缺口")
            return 0
        
    except ImportError as e:
        print(f"[WARNING] captcha-recognizer 库未安装: {e}")
        print("[INFO] 请运行: pip install captcha-recognizer")
        return 0
    except Exception as e:
        print(f"[ERROR] captcha-recognizer 识别异常: {e}")
        import traceback
        traceback.print_exc()
        return 0

def identify_gap_local(bg_img_bytes):
    """备用方案：使用简单的边缘检测识别缺口位置"""
    try:
        import numpy as np
        from PIL import Image
        
        # 读取背景图
        bg_img = Image.open(io.BytesIO(bg_img_bytes))
        bg_arr = np.array(bg_img.convert('RGB'))
        
        # 转换为灰度图
        if len(bg_arr.shape) == 3:
            gray = np.mean(bg_arr, axis=2).astype(np.uint8)
        else:
            gray = bg_arr
        
        height, width = gray.shape
        
        # 计算每列的边缘强度
        edge_strength = np.zeros(width)
        for x in range(1, width - 1):
            gradient = np.abs(gray[:, x+1].astype(int) - gray[:, x-1].astype(int))
            edge_strength[x] = np.sum(gradient)
        
        # 找到边缘强度最大的位置
        margin = width // 10
        search_range = edge_strength[margin:width-margin]
        if len(search_range) > 0:
            max_idx = np.argmax(search_range) + margin
            print(f"[DEBUG] 简单边缘检测找到位置: {max_idx}px")
            return max_idx
        
        # 默认返回中间偏右位置
        return int(width * 0.6)
        
    except Exception as e:
        print(f"[ERROR] 简单边缘检测异常: {e}")
        return 0

# ---------------- 验证码类型检测 ----------------
def detect_captcha_type(page, logger=None):
    """检测验证码类型：九宫格或滑块"""
    # 先检查是否有验证码弹窗出现
    captcha_popup_visible = False
    try:
        # 检查多种可能的验证码弹窗选择器
        popup_selectors = [
            ".geetest_popup",
            ".geetest_wrap",
            ".geetest_panel",
            "[class*='geetest'][class*='popup']",
            "[class*='geetest'][class*='wrap']"
        ]
        for selector in popup_selectors:
            try:
                if page.locator(selector).is_visible(timeout=500):
                    captcha_popup_visible = True
                    print(f"[DEBUG] 检测到验证码弹窗: {selector}")
                    break
            except:
                continue
    except:
        pass
    
    if not captcha_popup_visible:
        # 不打印，避免日志过多
        pass
    
    # 检查九宫格验证码（增加超时时间）
    grid_visible = False
    grid_selectors = [
        ".geetest_table_box",
        ".geetest_grid",
        "[class*='table'][class*='box']"
    ]
    for selector in grid_selectors:
        try:
            if page.locator(selector).is_visible(timeout=2000):
                grid_visible = True
                print(f"[DEBUG] 检测到九宫格验证码元素: {selector}")
                break
        except:
            continue
    
    # 检查滑块验证码（增加超时时间和更多选择器）
    slider_visible = False
    slider_button_visible = False
    slider_selectors = [
        ".geetest_slider",
        ".geetest_slider_button",
        ".geetest_slider_track",
        ".geetest_canvas_bg",
        ".geetest_canvas_slice",
        "[class*='slider']",
        "[class*='canvas'][class*='bg']"
    ]
    
    for selector in slider_selectors:
        try:
            if page.locator(selector).is_visible(timeout=2000):
                if "button" in selector or "knob" in selector:
                    slider_button_visible = True
                    print(f"[DEBUG] 检测到滑块按钮: {selector}")
                elif "canvas" in selector or "bg" in selector:
                    slider_visible = True
                    print(f"[DEBUG] 检测到滑块canvas: {selector}")
                else:
                    slider_visible = True
                    print(f"[DEBUG] 检测到滑块元素: {selector}")
        except:
            continue
    
    # 打印所有geetest相关元素（用于调试）- 只在未检测到验证码时打印
    if not grid_visible and not slider_visible and not slider_button_visible:
        try:
            all_geetest = page.locator("[class*='geetest']").count()
            if all_geetest > 0:
                print(f"[DEBUG] 页面上共有 {all_geetest} 个包含'geetest'的元素")
                # 检查前几个元素的可见性
                visible_count = 0
                for i in range(min(10, all_geetest)):
                    try:
                        elem = page.locator("[class*='geetest']").nth(i)
                        class_name = elem.get_attribute("class") or ""
                        is_visible = elem.is_visible(timeout=500)
                        if is_visible:
                            visible_count += 1
                            print(f"[DEBUG]   可见元素 {visible_count}: class='{class_name[:80]}'")
                    except:
                        pass
                if visible_count == 0:
                    print(f"[DEBUG]   所有 {all_geetest} 个geetest元素都不可见")
        except Exception as e:
            print(f"[DEBUG] 检查geetest元素时出错: {e}")
    
    if grid_visible:
        print("[DEBUG] 检测到九宫格验证码")
        if logger:
            logger.log_debug("检测到九宫格验证码")
        return "grid"
    elif slider_visible or slider_button_visible:
        print("[DEBUG] 检测到滑块验证码")
        if logger:
            logger.log_debug("检测到滑块验证码")
        return "slider"
    else:
        print("[DEBUG] 未检测到已知的验证码类型")
        if logger:
            logger.log_debug("未检测到已知的验证码类型")
        return "unknown"

# ---------------- 验证码核心处理 ----------------
def solve_geetest_multistep(page, ai_service, logger=None):
    """使用AI服务处理九宫格验证码"""
    print("[INFO] 开始处理九宫格验证码...")
    if logger:
        logger.log_captcha_step("开始", "初始化验证码处理")
    
    img_container = page.locator(".geetest_table_box").first
    container_visible = False
    try:
        container_visible = img_container.is_visible(timeout=3000)
    except:
        pass
    
    if not container_visible:
        print("[DEBUG] 验证码容器不可见")
        if logger:
            logger.log_element_status("验证码容器", False)
        return False
    
    if logger:
        logger.log_element_status("验证码容器", True)
        
    # 步骤 1: 识别题目
    target_object = ""
    tip_img = page.locator(".geetest_tip_img").first
    tip_img_visible = False
    try:
        tip_img_visible = tip_img.is_visible(timeout=2000)
    except:
        pass
    
    if tip_img_visible:
        print("[DEBUG] 检测到图片提示，使用AI识别...")
        if logger:
            logger.log_captcha_step("步骤1", "检测到图片提示，使用AI识别")
        try:
            target_object = ai_service.call_vision(tip_img.screenshot(), "图中是什么物体？只回答物体名称，不要带标点。")
            print(f"[DEBUG] AI识别结果（原始）: {target_object}")
        except Exception as e:
            print(f"[ERROR] AI识别图片提示失败: {e}")
            if logger:
                logger.log_exception(type(e).__name__, str(e), traceback.format_exc())
    else:
        tip_text_loc = page.locator(".geetest_tip_content").first
        tip_text_visible = False
        try:
            tip_text_visible = tip_text_loc.is_visible(timeout=2000)
        except:
            pass
        
        if tip_text_visible:
            print("[DEBUG] 检测到文本提示，读取文本...")
            if logger:
                logger.log_captcha_step("步骤1", "检测到文本提示，读取文本")
            try:
                target_object = tip_text_loc.inner_text()
                print(f"[DEBUG] 文本提示内容: {target_object}")
            except Exception as e:
                print(f"[ERROR] 读取文本提示失败: {e}")
                if logger:
                    logger.log_exception(type(e).__name__, str(e), traceback.format_exc())
        else:
            print("[WARNING] 未找到题目提示（图片或文本）")
            if logger:
                logger.log_captcha_step("步骤1", "未找到题目提示")
    
    target_object = re.sub(r'[^\w]', '', target_object) # 过滤掉标点
    print(f">>> [Step 1] 识别题目为：【{target_object}】")
    if logger:
        logger.log_captcha_step("步骤1完成", f"识别题目: {target_object}")

    # 步骤 2-4: 逐行抠图识别
    print("[DEBUG] 开始逐行识别九宫格...")
    if logger:
        logger.log_captcha_step("步骤2-4", "开始逐行识别九宫格")
    
    all_descriptions = []
    try:
        # 获取整个九宫格的截图并在内存中处理
        grid_bytes = img_container.screenshot()
        grid_img = Image.open(io.BytesIO(grid_bytes))
        w, h = grid_img.size
        row_h = h / 3
        print(f"[DEBUG] 九宫格尺寸: {w}x{h}, 每行高度: {row_h}")
        if logger:
            logger.log_captcha_step("步骤2-4", f"九宫格尺寸: {w}x{h}")
        
        for i in range(3):
            print(f"[DEBUG] 正在识别第 {i+1} 行...")
            if logger:
                logger.log_captcha_step(f"步骤{i+2}", f"识别第 {i+1} 行")
            
            # 裁剪出每一行
            top = i * row_h
            bottom = (i + 1) * row_h
            row_crop = grid_img.crop((0, top, w, bottom))
            
            buf = io.BytesIO()
            row_crop.save(buf, format='PNG')
            row_res = ai_service.identify_captcha_row(buf.getvalue(), i+1)
            print(f"[DEBUG] 第 {i+1} 行识别结果: {row_res}")
            if logger:
                logger.log_captcha_step(f"步骤{i+2}完成", f"第 {i+1} 行: {row_res}")
            all_descriptions.extend(row_res)
    except Exception as e:
        print(f"[ERROR] 九宫格识别过程出错: {e}")
        if logger:
            logger.log_exception(type(e).__name__, str(e), traceback.format_exc())
        return False

    # 步骤 5: 语义匹配并模拟点击
    print(f"[DEBUG] 开始语义匹配，目标: {target_object}, 描述列表: {all_descriptions}")
    if logger:
        logger.log_captcha_step("步骤5", f"语义匹配 - 目标: {target_object}")
    
    try:
        click_indices = ai_service.semantic_match(target_object, all_descriptions)
        print(f">>> [Final] 最终决定点击序号: {click_indices}")
        if logger:
            logger.log_captcha_step("步骤5完成", f"匹配结果: {click_indices}")
    except Exception as e:
        print(f"[ERROR] 语义匹配失败: {e}")
        if logger:
            logger.log_exception(type(e).__name__, str(e), traceback.format_exc())
        return False
    
    if not click_indices:
        print("[INFO] 未找到匹配项，刷新验证码...")
        if logger:
            logger.log_captcha_step("步骤5", "未找到匹配项，刷新验证码")
        try:
            refresh_btn = page.locator(".geetest_refresh").first
            if refresh_btn.is_visible():
                refresh_btn.click()
                time.sleep(2)
        except Exception as e:
            print(f"[ERROR] 刷新验证码失败: {e}")
            if logger:
                logger.log_exception(type(e).__name__, str(e), traceback.format_exc())
        return False

    try:
        box = img_container.bounding_box()
        cell_w, cell_h = box['width']/3, box['height']/3
        print(f"[DEBUG] 验证码容器位置: x={box['x']}, y={box['y']}, 宽度={box['width']}, 高度={box['height']}")
        print(f"[DEBUG] 每个格子尺寸: {cell_w}x{cell_h}")
        if logger:
            logger.log_captcha_step("点击", f"容器位置: ({box['x']}, {box['y']}), 格子尺寸: {cell_w}x{cell_h}")
        
        click_count = 0
        for idx in click_indices:
            try:
                val = int(idx)
                if 1 <= val <= 9:
                    r, c = (val-1)//3, (val-1)%3
                    # 点击格子的中心点
                    target_x = box['x'] + c*cell_w + cell_w/2
                    target_y = box['y'] + r*cell_h + cell_h/2
                    print(f"[DEBUG] 点击格子 {val} (行{r+1}, 列{c+1}), 坐标: ({target_x}, {target_y})")
                    if logger:
                        logger.log_captcha_step("点击", f"格子 {val} (行{r+1}, 列{c+1})")
                    page.mouse.click(target_x, target_y)
                    click_count += 1
                    time.sleep(random.uniform(0.3, 0.5))
            except Exception as e:
                print(f"[ERROR] 点击格子 {idx} 失败: {e}")
                if logger:
                    logger.log_exception(type(e).__name__, str(e), traceback.format_exc())
                continue
        
        print(f"[DEBUG] 共点击了 {click_count} 个格子")
        if logger:
            logger.log_captcha_step("点击完成", f"共点击 {click_count} 个格子")
    except Exception as e:
        print(f"[ERROR] 获取验证码容器位置失败: {e}")
        if logger:
            logger.log_exception(type(e).__name__, str(e), traceback.format_exc())
        return False
            
    # 提交验证
    print("[DEBUG] 查找提交按钮...")
    if logger:
        logger.log_captcha_step("提交", "查找提交按钮")
    
    submit_success = False
    for sel in [".geetest_commit", "text=确认", ".geetest_submit"]:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                print(f"[DEBUG] 找到提交按钮: {sel}")
                if logger:
                    logger.log_captcha_step("提交", f"找到按钮: {sel}")
                btn.click()
                submit_success = True
                break
        except:
            continue
    
    if not submit_success:
        print("[WARNING] 未找到提交按钮")
        if logger:
            logger.log_captcha_step("提交", "未找到提交按钮")
        return False
    
    print("[DEBUG] 验证码处理完成")
    if logger:
        logger.log_captcha_step("完成", "验证码处理完成")
    return True

def solve_geetest_slider(page, ai_service, logger=None):
    """使用AI服务处理滑块验证码"""
    print("[INFO] 开始处理滑块验证码...")
    if logger:
        logger.log_captcha_step("开始", "初始化滑块验证码处理")
    
    # 查找滑块相关元素
    slider_button = None
    slider_track = None
    
    # 尝试多种选择器找到滑块按钮
    slider_selectors = [
        ".geetest_slider_button",
        ".geetest_slider_knob",
        ".geetest_btn",
        "[class*='slider'][class*='button']"
    ]
    
    for selector in slider_selectors:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=1000):
                slider_button = btn
                print(f"[DEBUG] 找到滑块按钮: {selector}")
                if logger:
                    logger.log_element_status("滑块按钮", True, f"选择器: {selector}")
                break
        except:
            continue
    
    if not slider_button:
        print("[ERROR] 未找到滑块按钮")
        if logger:
            logger.log_element_status("滑块按钮", False)
        return False
    
    # 获取滑块按钮的初始位置（用于计算偏移量）
    button_box = slider_button.bounding_box()
    if not button_box:
        print("[ERROR] 无法获取滑块按钮位置")
        if logger:
            logger.log_element_status("滑块按钮", False, "无法获取位置")
        return False
    
    button_initial_x = button_box['x']
    print(f"[DEBUG] 滑块按钮初始x坐标: {button_initial_x:.1f}")
    if logger:
        logger.log_debug(f"滑块按钮初始x坐标: {button_initial_x:.1f}")
    
    # 查找滑块轨道
    track_selectors = [
        ".geetest_slider_track",
        ".geetest_slider",
        "[class*='slider'][class*='track']"
    ]
    
    for selector in track_selectors:
        try:
            track = page.locator(selector).first
            if track.is_visible(timeout=1000):
                slider_track = track
                print(f"[DEBUG] 找到滑块轨道: {selector}")
                if logger:
                    logger.log_element_status("滑块轨道", True, f"选择器: {selector}")
                break
        except:
            continue
    
    # 获取验证码图片
    print("[DEBUG] 正在获取验证码图片...")
    if logger:
        logger.log_captcha_step("步骤1", "获取验证码图片")
    
    # 打印验证码相关的所有元素信息（用于调试）
    try:
        print("[DEBUG] 查找所有验证码相关元素...")
        all_geetest_elements = page.locator("[class*='geetest']").all()
        print(f"[DEBUG] 找到 {len(all_geetest_elements)} 个包含'geetest'的元素")
        for i, elem in enumerate(all_geetest_elements[:10]):  # 只打印前10个
            try:
                class_name = elem.get_attribute("class") or ""
                tag_name = elem.evaluate("el => el.tagName")
                is_visible = elem.is_visible(timeout=500)
                print(f"[DEBUG]   元素 {i+1}: <{tag_name}> class='{class_name}' visible={is_visible}")
            except:
                pass
    except Exception as e:
        print(f"[DEBUG] 获取元素信息失败（非关键）: {e}")
    
    # 尝试获取背景图和缺口图
    bg_img_bytes = None
    slice_img_bytes = None
    
    # 方法1: 从canvas获取
    canvas_selectors = [
        ".geetest_canvas_bg",
        ".geetest_canvas_slice",
        "canvas.geetest_canvas_bg",
        "canvas.geetest_canvas_slice"
    ]
    
    bg_canvas = None
    slice_canvas = None
    
    for selector in canvas_selectors:
        try:
            canvas = page.locator(selector).first
            if canvas.is_visible(timeout=1000):
                try:
                    box = canvas.bounding_box()
                    size_info = f"位置: ({box['x']:.0f}, {box['y']:.0f}), 尺寸: {box['width']:.0f}x{box['height']:.0f}" if box else "无法获取位置"
                    if "bg" in selector or "background" in selector.lower():
                        bg_canvas = canvas
                        print(f"[DEBUG] 找到背景canvas: {selector}, {size_info}")
                    elif "slice" in selector or "puzzle" in selector.lower():
                        slice_canvas = canvas
                        print(f"[DEBUG] 找到缺口canvas: {selector}, {size_info}")
                except:
                    if "bg" in selector or "background" in selector.lower():
                        bg_canvas = canvas
                        print(f"[DEBUG] 找到背景canvas: {selector}")
                    elif "slice" in selector or "puzzle" in selector.lower():
                        slice_canvas = canvas
                        print(f"[DEBUG] 找到缺口canvas: {selector}")
        except:
            continue
    
    # 如果找到canvas，截图
    if bg_canvas:
        try:
            bg_img_bytes = bg_canvas.screenshot()
            print("[DEBUG] 成功获取背景图")
            # 保存背景图到文件
            bg_img_path = BASE_DIR / "captcha_bg.png"
            with open(bg_img_path, "wb") as f:
                f.write(bg_img_bytes)
            print(f"[DEBUG] 背景图已保存到: {bg_img_path}")
            if logger:
                logger.log_captcha_step("步骤1", f"成功获取背景图，已保存到: {bg_img_path}")
        except Exception as e:
            print(f"[ERROR] 获取背景图失败: {e}")
            if logger:
                logger.log_exception(type(e).__name__, str(e), traceback.format_exc())
    
    if slice_canvas:
        try:
            slice_img_bytes = slice_canvas.screenshot()
            print("[DEBUG] 成功获取缺口图")
            # 保存缺口图到文件
            slice_img_path = BASE_DIR / "captcha_slice.png"
            with open(slice_img_path, "wb") as f:
                f.write(slice_img_bytes)
            print(f"[DEBUG] 缺口图已保存到: {slice_img_path}")
            if logger:
                logger.log_captcha_step("步骤1", f"成功获取缺口图，已保存到: {slice_img_path}")
        except Exception as e:
            print(f"[ERROR] 获取缺口图失败: {e}")
            if logger:
                logger.log_exception(type(e).__name__, str(e), traceback.format_exc())
    
    # 方法2: 如果canvas不可用，尝试从img标签获取
    if not bg_img_bytes:
        img_selectors = [
            ".geetest_bg img",
            ".geetest_slice_bg img",
            "[class*='bg'] img"
        ]
        for selector in img_selectors:
            try:
                img = page.locator(selector).first
                if img.is_visible(timeout=1000):
                    bg_img_bytes = img.screenshot()
                    print(f"[DEBUG] 从img标签获取背景图: {selector}")
                    # 保存从img标签获取的背景图
                    bg_img_path = BASE_DIR / "captcha_bg.png"
                    with open(bg_img_path, "wb") as f:
                        f.write(bg_img_bytes)
                    print(f"[DEBUG] 背景图已保存到: {bg_img_path}")
                    break
            except:
                continue
    
    if not bg_img_bytes:
        print("[WARNING] 无法获取验证码图片，尝试截图整个验证码区域")
        if logger:
            logger.log_captcha_step("步骤1", "无法获取图片，尝试截图整个区域")
        try:
            # 尝试截图整个验证码容器
            captcha_container = page.locator(".geetest_popup, .geetest_wrap, [class*='geetest']").first
            if captcha_container.is_visible(timeout=2000):
                bg_img_bytes = captcha_container.screenshot()
                print("[DEBUG] 成功截图验证码容器")
                # 保存整个验证码区域截图
                container_img_path = BASE_DIR / "captcha_container.png"
                with open(container_img_path, "wb") as f:
                    f.write(bg_img_bytes)
                print(f"[DEBUG] 验证码容器截图已保存到: {container_img_path}")
                if logger:
                    logger.log_captcha_step("步骤1", f"验证码容器截图已保存到: {container_img_path}")
        except Exception as e:
            print(f"[ERROR] 截图验证码容器失败: {e}")
            if logger:
                logger.log_exception(type(e).__name__, str(e), traceback.format_exc())
            return False
    
    # 查找缺口块元素（拼图块）
    slice_element = None
    slice_element_selectors = [
        ".geetest_slice",
        ".geetest_slice_box",
        "[class*='slice']",
        "[class*='puzzle']"
    ]
    
    for selector in slice_element_selectors:
        try:
            elem = page.locator(selector).first
            if elem.is_visible(timeout=1000):
                slice_element = elem
                try:
                    box = elem.bounding_box()
                    if box:
                        print(f"[DEBUG] 找到缺口块元素: {selector}, 位置: ({box['x']:.0f}, {box['y']:.0f}), 尺寸: {box['width']:.0f}x{box['height']:.0f}")
                        if logger:
                            logger.log_element_status("缺口块元素", True, f"位置: ({box['x']:.0f}, {box['y']:.0f})")
                except:
                    print(f"[DEBUG] 找到缺口块元素: {selector}")
                break
        except:
            continue
    
    # 额外保存整个页面的验证码区域截图（用于调试）
    try:
        full_captcha_path = BASE_DIR / "captcha_full.png"
        # 尝试找到验证码弹窗并截图
        captcha_popup = page.locator(".geetest_popup, .geetest_wrap").first
        if captcha_popup.is_visible(timeout=1000):
            full_captcha_bytes = captcha_popup.screenshot()
            with open(full_captcha_path, "wb") as f:
                f.write(full_captcha_bytes)
            print(f"[DEBUG] 完整验证码区域已保存到: {full_captcha_path}")
            if logger:
                logger.log_debug(f"完整验证码区域已保存到: {full_captcha_path}")
    except Exception as e:
        print(f"[DEBUG] 保存完整验证码区域失败（非关键错误）: {e}")
    
    # 使用 captcha-recognizer 专业库识别缺口位置
    print("[DEBUG] 使用 captcha-recognizer 库识别缺口位置...")
    if logger:
        logger.log_captcha_step("步骤2", "使用 captcha-recognizer 库识别缺口")
    
    gap_position = 0
    
    try:
        gap_position = identify_gap_with_library(bg_img_bytes, logger)
        if gap_position > 0:
            print(f"[INFO] captcha-recognizer 识别成功: 缺口位置={gap_position}px")
            if logger:
                logger.log_captcha_step("步骤2完成", f"识别成功: {gap_position}px")
        else:
            print("[ERROR] captcha-recognizer 未识别到缺口")
            if logger:
                logger.log_captcha_step("步骤2", "未识别到缺口")
            return False
    except Exception as e:
        error_msg = f"captcha-recognizer 识别失败: {e}"
        print(f"[ERROR] {error_msg}")
        if logger:
            logger.log_exception(type(e).__name__, str(e), traceback.format_exc())
        return False
    
    if gap_position <= 0:
        print("[ERROR] 识别到的缺口位置无效")
        if logger:
            logger.log_captcha_step("步骤2", "识别到的缺口位置无效")
        return False
    
    # 获取背景canvas的位置（用于计算偏移量和缺口实际位置）
    bg_canvas_box = None
    if bg_canvas:
        try:
            bg_canvas_box = bg_canvas.bounding_box()
            if bg_canvas_box:
                print(f"[DEBUG] 背景canvas位置: x={bg_canvas_box['x']:.1f}, y={bg_canvas_box['y']:.1f}, 尺寸={bg_canvas_box['width']:.1f}x{bg_canvas_box['height']:.1f}")
                if logger:
                    logger.log_debug(f"背景canvas: x={bg_canvas_box['x']:.1f}, 宽={bg_canvas_box['width']:.1f}")
        except Exception as e:
            print(f"[DEBUG] 获取背景canvas位置失败: {e}")
    
    # 计算坐标转换
    # gap_position 是缺口在背景图中的x坐标（图片坐标系，相对于图片左边缘）
    # 需要转换为页面坐标系，然后计算滑动距离
    
    button_x = button_box['x'] + button_box['width'] / 2
    button_y = button_box['y'] + button_box['height'] / 2
    button_width = button_box['width']
    
    print(f"[DEBUG] 滑块按钮: 左边缘x={button_box['x']:.1f}, 中心x={button_x:.1f}, 宽度={button_width:.1f}")
    if logger:
        logger.log_captcha_step("步骤3", f"滑块按钮中心: ({button_x:.1f}, {button_y:.1f})")
    
    # 计算滑动距离
    gap_x_in_page = None  # 初始化变量
    offset = None  # 初始化变量
    
    if bg_canvas_box:
        # 使用背景canvas位置进行坐标转换
        bg_canvas_x = bg_canvas_box['x']
        
        # 计算滑块初始位置相对于背景图的偏移量
        # offset = 滑块按钮左边缘x - 背景canvas的x
        offset = button_initial_x - bg_canvas_x
        print(f"[DEBUG] 计算偏移量: 滑块初始x({button_initial_x:.1f}) - 背景canvas x({bg_canvas_x:.1f}) = {offset:.1f}px")
        
        # 实际滑动距离 = 缺口位置 + 偏移量
        drag_distance_base = gap_position + offset
        print(f"[DEBUG] 基础滑动距离: 缺口位置({gap_position}px) + 偏移量({offset:.1f}px) = {drag_distance_base:.1f}px")
        
        # 添加随机误差，模拟人类操作（-5.0 到 +5.0 像素）
        human_error = random.uniform(-5.0, 5.0)
        drag_distance = drag_distance_base + human_error
        print(f"[DEBUG] 添加人类误差: {drag_distance_base:.1f}px + {human_error:.2f}px = {drag_distance:.1f}px")
        
        # 计算缺口在页面中的位置（用于显示）
        gap_x_in_page = bg_canvas_x + gap_position
        
        # 目标位置 = 当前按钮中心 + 滑动距离
        target_x = button_x + drag_distance
        
        if logger:
            logger.log_captcha_step("步骤3", f"偏移量={offset:.1f}, 滑动距离={drag_distance:.1f} (含误差{human_error:.2f}), 目标={target_x:.1f}")
    else:
        # 方法2: 如果没有背景canvas信息，直接使用gap_position作为滑动距离
        drag_distance_base = gap_position
        
        # 添加随机误差，模拟人类操作（-5.0 到 +5.0 像素）
        human_error = random.uniform(-5.0, 5.0)
        drag_distance = drag_distance_base + human_error
        
        target_x = button_x + drag_distance
        print(f"[DEBUG] 无背景canvas信息，直接滑动: {drag_distance_base}px + 误差{human_error:.2f}px = {drag_distance:.1f}px，目标位置: {target_x:.1f}")
        if logger:
            logger.log_captcha_step("步骤3", f"直接滑动距离={drag_distance:.1f}px (含误差{human_error:.2f})")
    
    # ===== 详细打印滑块起点和终点信息 =====
    print("\n" + "="*60)
    print(f"[INFO] 滑块拖动预测信息:")
    print(f"  滑块按钮左边缘X: {button_initial_x:.1f}px (页面坐标)")
    print(f"  滑块按钮中心X: {button_x:.1f}px (页面坐标)")
    if bg_canvas_box and offset is not None:
        print(f"  背景canvas X: {bg_canvas_box['x']:.1f}px (页面坐标)")
        print(f"  滑块初始偏移: {offset:.1f}px")
    print(f"  缺口位置: {gap_position}px (图片坐标)")
    if gap_x_in_page is not None:
        print(f"  缺口实际位置: {gap_x_in_page:.1f}px (页面坐标)")
    print(f"  滑动距离: {drag_distance:.1f}px (含±5px人类误差)")
    print(f"  目标中心X: {target_x:.1f}px (页面坐标)")
    print("="*60 + "\n")
    
    if logger:
        logger.log_captcha_step("步骤3完成", f"起点={button_x:.1f}, 终点={target_x:.1f}, 距离={drag_distance:.1f}")
    
    # ===== 拖动前截图 =====
    try:
        before_drag_path = BASE_DIR / "slider_before_drag.png"
        page.screenshot(path=str(before_drag_path))
        print(f"[INFO] 拖动前截图已保存: {before_drag_path}")
        if logger:
            logger.log_debug(f"拖动前截图已保存: {before_drag_path}")
    except Exception as e:
        print(f"[WARNING] 保存拖动前截图失败: {e}")
    
    # 执行拖动
    try:
        print(f"[DEBUG] 开始拖动滑块...")
        if logger:
            logger.log_captcha_step("步骤4", f"拖动: {button_x:.1f} -> {target_x:.1f}")
        
        # 先移动到按钮位置
        page.mouse.move(button_x, button_y)
        time.sleep(random.uniform(0.1, 0.2))
        
        # 按下鼠标
        page.mouse.down()
        time.sleep(random.uniform(0.1, 0.2))
        
        # 模拟人类拖动轨迹（使用 pytweening 缓动函数）
        steps = random.randint(20, 30)  # 增加步数，轨迹更平滑
        
        # 随机选择一个缓动函数，模拟不同人的操作习惯
        easing_functions = [
            pytweening.easeInOutQuad,    # 先加速后减速（最常见）
            pytweening.easeOutQuad,      # 快速启动，逐渐减速
            pytweening.easeInOutCubic,   # 更平滑的加速减速
        ]
        easing_func = random.choice(easing_functions)
        
        print(f"[DEBUG] 使用缓动函数: {easing_func.__name__}, 步数: {steps}")
        
        for i in range(steps):
            # 使用 pytweening 的缓动函数计算进度
            progress = easing_func(i / steps)
            
            # 添加随机抖动（水平和垂直）
            jitter_x = random.uniform(-1.5, 1.5)
            jitter_y = random.uniform(-2, 2)
            
            current_x = button_x + drag_distance * progress + jitter_x
            current_y = button_y + jitter_y
            
            page.mouse.move(current_x, current_y)
            
            # 根据速度调整时间间隔（移动快的时候间隔短，移动慢的时候间隔长）
            if i < steps * 0.3:  # 前30%，快速移动
                time.sleep(random.uniform(0.005, 0.015))
            elif i > steps * 0.7:  # 后30%，减速
                time.sleep(random.uniform(0.02, 0.04))
            else:  # 中间阶段
                time.sleep(random.uniform(0.01, 0.025))
        
        # 添加轻微的超调和回调（模拟人类操作的不精确性）
        if random.random() > 0.5:  # 50% 概率出现超调
            overshoot = random.uniform(2, 5)  # 超调2-5像素
            page.mouse.move(target_x + overshoot, button_y + random.uniform(-1, 1))
            time.sleep(random.uniform(0.05, 0.1))
            print(f"[DEBUG] 模拟超调: +{overshoot:.1f}px")
        
        # 最后精确移动到目标位置
        page.mouse.move(target_x, button_y)
        time.sleep(random.uniform(0.15, 0.25))
        
        # 释放鼠标
        page.mouse.up()
        time.sleep(random.uniform(0.5, 1.0))
        
        print("[DEBUG] 滑块拖动完成")
        if logger:
            logger.log_captcha_step("步骤4完成", "滑块拖动完成")
        
        # ===== 拖动后截图 =====
        try:
            after_drag_path = BASE_DIR / "slider_after_drag.png"
            page.screenshot(path=str(after_drag_path))
            print(f"[INFO] 拖动后截图已保存: {after_drag_path}")
            if logger:
                logger.log_debug(f"拖动后截图已保存: {after_drag_path}")
        except Exception as e:
            print(f"[WARNING] 保存拖动后截图失败: {e}")
        
        # 等待验证结果
        time.sleep(2)
        
        # 检查是否验证成功（验证码消失或出现成功提示）
        captcha_gone = True
        try:
            # 检查验证码是否还存在
            if page.locator(".geetest_slider").is_visible(timeout=1000):
                captcha_gone = False
        except:
            pass
        
        if captcha_gone:
            print("[DEBUG] 验证码已消失，可能验证成功")
            if logger:
                logger.log_captcha_step("完成", "验证码已消失")
            return True
        else:
            print("[DEBUG] 验证码仍存在，可能验证失败")
            if logger:
                logger.log_captcha_step("完成", "验证码仍存在，可能失败")
            return False
        
    except Exception as e:
        print(f"[ERROR] 拖动滑块失败: {e}")
        if logger:
            logger.log_exception(type(e).__name__, str(e), traceback.format_exc())
        return False

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
    
    # 清理30天前的旧日志
    clean_old_logs(BASE_DIR, days=30)
    
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
        
        try:
            page.goto(target_url, timeout=30000)
            current_url = page.url
            print(f"[DEBUG] 页面加载完成，当前URL: {current_url}")
            if logger:
                logger.log_page_url(current_url)
        except Exception as e:
            error_msg = f"页面访问失败: {e}"
            print(f"[ERROR] {error_msg}")
            if logger:
                logger.log_exception(type(e).__name__, str(e), traceback.format_exc())
            browser.close()
            return

        # 登录判断
        current_url_after_load = page.url
        print(f"[DEBUG] 登录检查前URL: {current_url_after_load}")
        if logger:
            logger.log_page_url(current_url_after_load)
        
        is_logged_in = True
        username_input_visible = False
        try:
            username_input_visible = page.locator("#username").is_visible(timeout=2000)
        except:
            pass
        
        if "login" in current_url_after_load or username_input_visible:
            is_logged_in = False
            print("[INFO] 检测到需要登录")
            print(f"[DEBUG] URL包含'login': {'login' in current_url_after_load}, 用户名输入框可见: {username_input_visible}")
            if logger:
                logger.log_login_status(False)
                logger.log_element_status("用户名输入框", username_input_visible, f"URL包含login: {'login' in current_url_after_load}")
            
            try:
                print("[INFO] 正在填写登录信息...")
                page.fill("#username", username)
                page.fill("#password", password)
                print("[INFO] 正在点击登录按钮...")
                page.click("#login")
                
                print("[DEBUG] 等待登录完成，检查'账号信息'文本...")
                if logger:
                    logger.log_debug("等待登录完成，检查'账号信息'文本...")
                
                try:
                    page.wait_for_selector("text=账号信息", timeout=10000)
                    context.storage_state(path=STATE_FILE)
                    is_logged_in = True
                    print("[SUCCESS] 登录成功")
                    if logger:
                        logger.log_login_status(True)
                        logger.log_page_url(page.url)
                except Exception as e:
                    error_msg = f"登录超时或失败: {e}"
                    print(f"[ERROR] {error_msg}")
                    print(f"[DEBUG] 登录后URL: {page.url}")
                    if logger:
                        logger.log_error(error_msg)
                        logger.log_exception(type(e).__name__, str(e), traceback.format_exc())
                        logger.log_page_url(page.url)
            except Exception as e:
                error_msg = f"登录过程出错: {e}"
                print(f"[ERROR] {error_msg}")
                if logger:
                    logger.log_exception(type(e).__name__, str(e), traceback.format_exc())
        else:
            print("[INFO] 已登录状态")
            if logger:
                logger.log_login_status(True)

        # 18岁弹窗
        try:
            btn_18 = page.get_by_text("是，我已满18岁")
            if btn_18.is_visible(timeout=3000): 
                print("[DEBUG] 检测到18岁确认弹窗，正在点击...")
                if logger:
                    logger.log_debug("检测到18岁确认弹窗，正在点击...")
                btn_18.click()
                time.sleep(1)
        except Exception as e:
            if logger:
                logger.log_debug(f"18岁弹窗处理: {e}")
            pass

        # 签到
        print("[DEBUG] 开始检查签到状态...")
        if logger:
            logger.log_debug("开始检查签到状态...")
        
        signed_locator = find_signed_text_locator(page)
        if signed_locator:
            print("[INFO] 今日已签到。")
            if logger:
                logger.log_already_signed()
        else:
            print("[DEBUG] 未检测到已签到状态，查找签到按钮...")
            if logger:
                logger.log_debug("未检测到已签到状态，查找签到按钮...")
            
            sign_btn = page.get_by_text("点击这里签到")
            sign_btn_visible = False
            try:
                sign_btn_visible = sign_btn.is_visible(timeout=3000)
            except:
                pass
            
            print(f"[DEBUG] 签到按钮可见性: {sign_btn_visible}")
            if logger:
                logger.log_element_status("签到按钮", sign_btn_visible)
            
            if sign_btn_visible:
                print("[INFO] 点击签到按钮...")
                if logger:
                    logger.log_info("点击签到按钮...")
                
                # 初始化签到成功标志
                sign_success = False
                
                try:
                    sign_btn.click()
                    print("[DEBUG] 已点击签到按钮，等待验证码加载...")
                    if logger:
                        logger.log_debug("已点击签到按钮，等待验证码加载")
                    
                    # 保存点击前的页面状态（用于对比）
                    try:
                        before_screenshot = BASE_DIR / "before_click.png"
                        page.screenshot(path=str(before_screenshot))
                        print(f"[DEBUG] 点击前页面截图已保存: {before_screenshot}")
                    except:
                        pass
                    
                    # 获取点击后的URL
                    current_url = page.url
                    print(f"[DEBUG] 点击后当前URL: {current_url}")
                    
                    # 第一次等待：等待15秒后进行第一次检查
                    print("[INFO] 等待15秒让验证码完全加载...")
                    captcha_appeared = False
                    for i in range(30):  # 30次，每次0.5秒，总共15秒
                        time.sleep(0.5)
                        
                        # 每5秒打印一次进度
                        if (i + 1) % 10 == 0:
                            print(f"[DEBUG] 已等待 {(i+1)*0.5:.1f} 秒...")
                        
                        # 检查是否已经签到成功（不需要验证码）
                        signed_check = find_signed_text_locator(page, timeout=500)
                        if signed_check:
                            print(f"[SUCCESS] 签到完成（无需验证码，等待了 {(i+1)*0.5:.1f} 秒）！")
                            sign_success = True
                            if logger:
                                logger.log_sign_success()
                            break
                    
                    if not sign_success:
                        # 第一次检查验证码
                        print("[DEBUG] 15秒等待结束，开始第一次检查验证码...")
                        captcha_type_check = detect_captcha_type(page, logger)
                        if captcha_type_check != "unknown":
                            captcha_appeared = True
                            print(f"[INFO] 验证码已出现（类型: {captcha_type_check}）")
                        else:
                            # 继续等待，每5秒检查一次，最多再等15秒（总共30秒）
                            print("[DEBUG] 未检测到验证码，继续等待...")
                            for check_round in range(3):  # 3轮，每轮5秒
                                print(f"[DEBUG] 等待第 {check_round + 1} 轮（5秒）...")
                                time.sleep(5)
                                
                                # 检查是否已经签到成功
                                signed_check = find_signed_text_locator(page, timeout=500)
                                if signed_check:
                                    print(f"[SUCCESS] 签到完成（无需验证码）！")
                                    sign_success = True
                                    if logger:
                                        logger.log_sign_success()
                                    break
                                
                                # 检查验证码
                                captcha_type_check = detect_captcha_type(page, logger)
                                if captcha_type_check != "unknown":
                                    captcha_appeared = True
                                    print(f"[INFO] 验证码已出现（类型: {captcha_type_check}，总等待时间: {15 + (check_round + 1) * 5} 秒）")
                                    break
                                else:
                                    print(f"[DEBUG] 第 {check_round + 1} 轮检查：仍未检测到验证码")
                    
                    # 保存点击后的页面状态
                    try:
                        after_screenshot = BASE_DIR / "after_click.png"
                        page.screenshot(path=str(after_screenshot))
                        print(f"[DEBUG] 点击后页面截图已保存: {after_screenshot}")
                    except:
                        pass
                    
                    if sign_success:
                        # 如果已经签到成功，不需要继续处理验证码
                        pass
                    elif not captcha_appeared and not sign_success:
                        print("[WARNING] 点击签到按钮后30秒内未检测到验证码")
                        if logger:
                            logger.log_debug("点击签到按钮后30秒内未检测到验证码")
                    
                except Exception as e:
                    error_msg = f"点击签到按钮失败: {e}"
                    print(f"[ERROR] {error_msg}")
                    if logger:
                        logger.log_exception(type(e).__name__, str(e), traceback.format_exc())
                
                # 如果已经签到成功，跳过验证码处理
                if not sign_success:
                    # 如果检测到验证码，进入处理流程；否则再尝试检查
                    if captcha_appeared:
                        max_attempts = 3
                        print("[DEBUG] 验证码已出现，开始处理...")
                    else:
                        # 30秒后仍未检测到验证码，再给最后2次机会（每次2秒）
                        max_attempts = 2
                        print("[DEBUG] 验证码未出现，再尝试检测2次...")
                    print(f"[DEBUG] 开始签到循环检测，最多尝试 {max_attempts} 次...")
                    if logger:
                        logger.log_debug(f"开始签到循环检测，最多尝试 {max_attempts} 次...")
                    
                    for attempt in range(1, max_attempts + 1):
                        print(f"[DEBUG] 第 {attempt}/{max_attempts} 次检查...")
                        if logger:
                            logger.log_debug(f"第 {attempt}/{max_attempts} 次检查...")
                        
                        # 检查是否已签到成功
                        signed_check = find_signed_text_locator(page, timeout=1000)
                        if signed_check:
                            print("[SUCCESS] 签到完成！")
                            sign_success = True
                            if logger:
                                logger.log_sign_success()
                                logger.log_debug(f"在第 {attempt} 次检查时检测到签到成功")
                            break
                        
                        # 检查是否有验证码（增加等待时间）
                        print(f"[DEBUG] 第 {attempt} 次检查：检测验证码类型...")
                        captcha_type = detect_captcha_type(page, logger)
                        
                        if captcha_type != "unknown":
                            print(f"[DEBUG] 第 {attempt} 次检查：检测到{('九宫格' if captcha_type == 'grid' else '滑块')}验证码")
                            if logger:
                                logger.log_captcha_step(f"第 {attempt} 次", f"检测到{('九宫格' if captcha_type == 'grid' else '滑块')}验证码")
                            
                            try:
                                if captcha_type == "grid":
                                    captcha_result = solve_geetest_multistep(page, ai_service, logger)
                                elif captcha_type == "slider":
                                    captcha_result = solve_geetest_slider(page, ai_service, logger)
                                else:
                                    captcha_result = False
                                
                                result_text = "成功" if captcha_result else "失败"
                                print(f"[DEBUG] 验证码处理结果: {result_text}")
                                if logger:
                                    logger.log_captcha_result(result_text)
                                    logger.log_captcha_step(f"第 {attempt} 次", f"处理结果: {result_text}")
                                
                                if captcha_result:
                                    time.sleep(3)  # 等待验证码处理后的页面响应
                                else:
                                    print("[DEBUG] 验证码处理失败，继续等待...")
                                    if logger:
                                        logger.log_debug("验证码处理失败，继续等待...")
                            except Exception as e:
                                error_msg = f"验证码处理异常: {e}"
                                print(f"[ERROR] {error_msg}")
                                if logger:
                                    logger.log_exception(type(e).__name__, str(e), traceback.format_exc())
                        else:
                            print(f"[DEBUG] 第 {attempt} 次检查：未检测到验证码，当前URL: {page.url}")
                            if logger:
                                logger.log_debug(f"第 {attempt} 次检查：未检测到验证码")
                                logger.log_page_url(page.url)
                            
                            # 如果未检测到验证码，等待更长时间再检查（验证码可能需要时间加载）
                            if attempt < max_attempts:
                                wait_time = 2  # 等待2秒
                                print(f"[DEBUG] 等待 {wait_time} 秒后再次检查...")
                                time.sleep(wait_time)
                            else:
                                time.sleep(1)
                    
                    if not sign_success:
                        final_url = page.url
                        error_msg = f"签到失败：超时或验证码处理失败（已尝试 {max_attempts} 次）"
                        print(f"[ERROR] {error_msg}")
                        print(f"[DEBUG] 最终URL: {final_url}")
                        if logger:
                            logger.log_sign_failed(error_msg)
                            logger.log_wait_timeout("签到循环", max_attempts, max_attempts)
                            logger.log_page_url(final_url)
                            
                            # 检查最终状态
                            final_signed = find_signed_text_locator(page, timeout=1000)
                            final_captcha = False
                            try:
                                final_captcha = page.locator(".geetest_table_box").is_visible(timeout=1000)
                            except:
                                pass
                            logger.log_debug(f"最终状态检查 - 已签到: {final_signed is not None}, 验证码可见: {final_captcha}")
            else:
                current_url_final = page.url
                error_msg = "未找到签到按钮"
                print(f"[ERROR] {error_msg}")
                print(f"[DEBUG] 当前URL: {current_url_final}")
                if logger:
                    logger.log_sign_failed(error_msg)
                    logger.log_page_url(current_url_final)
                    logger.log_debug("尝试查找其他可能的签到相关元素...")
                    
                    # 尝试查找其他可能的签到文本
                    try:
                        all_text = page.locator("body").inner_text()
                        if "签到" in all_text:
                            logger.log_debug("页面中包含'签到'文本，但未找到签到按钮")
                    except:
                        pass

        # 截图存证（如果需要）
        if save_screenshot:
            success_loc = find_signed_text_locator(page)
            if success_loc:
                try:
                    # 尝试截取父级区域，让截图更美观
                    success_loc.locator(f"xpath=ancestor::*[{SIGNED_ANCESTOR_LEVELS}]").first.screenshot(path=str(SUCCESS_SCREENSHOT))
                    print(f"[INFO] 截图已保存: {SUCCESS_SCREENSHOT}")
                except:
                    page.screenshot(path=str(SUCCESS_SCREENSHOT))
                    print(f"[INFO] 截图已保存: {SUCCESS_SCREENSHOT}")
        
        print("[INFO] 脚本运行结束。")
        browser.close()

if __name__ == "__main__":
    main()
