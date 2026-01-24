#!/usr/bin/env python3
"""
测试脚本 - 检查项目运行情况
运行方式: 
  python3 test.py          # 使用系统Python
  uv run test.py           # 使用uv虚拟环境（推荐）
  .venv/bin/python test.py # 直接使用虚拟环境Python
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到路径
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

def check_python_environment():
    """检查Python环境并给出提示"""
    python_path = Path(sys.executable)
    venv_path = BASE_DIR / ".venv"
    
    # 检查是否在虚拟环境中
    is_in_venv = ".venv" in str(python_path) or "venv" in str(python_path)
    
    # 检查是否存在.venv目录
    venv_exists = venv_path.exists()
    
    if venv_exists and not is_in_venv:
        print("\n⚠️  检测到 .venv 目录，但当前未使用虚拟环境！")
        print(f"   当前Python路径: {python_path}")
        print(f"   建议使用以下方式运行测试：")
        print(f"   - uv run test.py")
        print(f"   - .venv/bin/python test.py")
        print(f"   - source .venv/bin/activate && python test.py")
        print()
    
    return is_in_venv, venv_exists

def print_test_header(test_name):
    """打印测试标题"""
    print(f"\n{'='*60}")
    print(f"测试: {test_name}")
    print(f"{'='*60}")

def print_result(success, message):
    """打印测试结果"""
    status = "✓ 通过" if success else "✗ 失败"
    print(f"{status}: {message}")

def test_imports():
    """测试模块导入"""
    print_test_header("模块导入测试")
    
    try:
        import playwright
        print_result(True, "playwright 模块导入成功")
    except ImportError as e:
        print_result(False, f"playwright 模块导入失败: {e}")
        return False
    
    try:
        import zhipuai
        print_result(True, "zhipuai 模块导入成功")
    except ImportError as e:
        print_result(False, f"zhipuai 模块导入失败: {e}")
        return False
    
    try:
        from PIL import Image
        print_result(True, "PIL 模块导入成功")
    except ImportError as e:
        print_result(False, f"PIL 模块导入失败: {e}")
        return False
    
    try:
        from dotenv import load_dotenv
        print_result(True, "python-dotenv 模块导入成功")
    except ImportError as e:
        print_result(False, f"python-dotenv 模块导入失败: {e}")
        return False
    
    try:
        from ai_service import AIService
        print_result(True, "ai_service 模块导入成功")
    except ImportError as e:
        print_result(False, f"ai_service 模块导入失败: {e}")
        return False
    
    try:
        from logger import CheckinLogger
        print_result(True, "logger 模块导入成功")
    except ImportError as e:
        print_result(False, f"logger 模块导入失败: {e}")
        return False
    
    return True

def test_files():
    """测试必要文件是否存在"""
    print_test_header("文件检查")
    
    files_to_check = {
        "main.py": "主程序文件",
        "ai_service.py": "AI服务模块",
        "logger.py": "日志模块",
        "requirements.txt": "依赖列表",
        "run_scheduled.sh": "定时执行脚本",
        "env.example": "环境变量示例",
    }
    
    all_exist = True
    for filename, description in files_to_check.items():
        filepath = BASE_DIR / filename
        if filepath.exists():
            print_result(True, f"{description} ({filename}) 存在")
        else:
            print_result(False, f"{description} ({filename}) 不存在")
            all_exist = False
    
    return all_exist

def test_config_files():
    """测试配置文件"""
    print_test_header("配置文件检查")
    
    # 检查 .env 文件
    env_file = BASE_DIR / ".env"
    env_example = BASE_DIR / "env.example"
    
    if env_file.exists():
        print_result(True, ".env 文件存在")
        # 检查必要的配置项
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
            api_key = os.getenv("ZHIPU_API_KEY", "")
            if api_key and api_key != "your_api_key_here":
                print_result(True, "ZHIPU_API_KEY 已配置")
            else:
                print_result(False, "ZHIPU_API_KEY 未配置或使用默认值")
        except Exception as e:
            print_result(False, f"读取 .env 文件失败: {e}")
    else:
        print_result(False, ".env 文件不存在（请复制 env.example 为 .env）")
        if env_example.exists():
            print(f"  提示: 可以运行 'cp env.example .env' 创建配置文件")
    
    # 检查 account.txt
    account_file = BASE_DIR / "account.txt"
    if account_file.exists():
        print_result(True, "account.txt 文件存在")
        try:
            content = account_file.read_text(encoding="utf-8").strip()
            lines = [l.strip() for l in content.splitlines() if l.strip()]
            if len(lines) >= 2:
                print_result(True, "account.txt 格式正确（包含用户名和密码）")
            else:
                print_result(False, "account.txt 格式错误（需要至少两行：用户名和密码）")
        except Exception as e:
            print_result(False, f"读取 account.txt 失败: {e}")
    else:
        print_result(False, "account.txt 文件不存在")
    
    return True

def test_logger():
    """测试日志模块"""
    print_test_header("日志模块测试")
    
    try:
        from logger import CheckinLogger
        
        # 创建测试日志目录
        test_dir = BASE_DIR / "test_logs"
        test_dir.mkdir(exist_ok=True)  # 确保父目录存在
        logger = CheckinLogger(test_dir)
        print_result(True, "CheckinLogger 初始化成功")
        
        # 测试日志写入
        logger.log_start()
        logger.log_info("测试日志信息")
        logger.log_error("测试错误信息")
        print_result(True, "日志写入功能正常")
        
        # 检查日志文件是否存在
        if logger.log_file.exists():
            print_result(True, f"日志文件已创建: {logger.log_file}")
        else:
            print_result(False, "日志文件未创建")
        
        # 清理测试目录（可选）
        # import shutil
        # if test_dir.exists():
        #     shutil.rmtree(test_dir)
        
        return True
    except Exception as e:
        print_result(False, f"日志模块测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ai_service():
    """测试AI服务模块（不实际调用API）"""
    print_test_header("AI服务模块测试")
    
    try:
        from ai_service import AIService
        
        # 检查环境变量
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("ZHIPU_API_KEY", "")
        
        if not api_key or api_key == "your_api_key_here":
            print_result(False, "ZHIPU_API_KEY 未配置，跳过AI服务初始化测试")
            print("  提示: 请在 .env 文件中配置 ZHIPU_API_KEY")
            return True  # 不算作失败，只是跳过
        
        # 尝试初始化（会实际连接API，但不会调用）
        try:
            ai_service = AIService()
            print_result(True, "AIService 初始化成功")
            print_result(True, f"视觉模型: {ai_service.model_vision}")
            print_result(True, f"文本模型: {ai_service.model_text}")
            
            # 测试JSON解析功能（不需要API调用）
            test_json = '["猫", "狗", "汽车"]'
            parsed = ai_service.safe_parse_json(test_json)
            if parsed == ["猫", "狗", "汽车"]:
                print_result(True, "JSON解析功能正常")
            else:
                print_result(False, f"JSON解析结果不正确: {parsed}")
            
            return True
        except ValueError as e:
            print_result(False, f"AIService 初始化失败: {e}")
            return False
        except Exception as e:
            print_result(False, f"AIService 初始化异常: {e}")
            import traceback
            traceback.print_exc()
            return False
    except Exception as e:
        print_result(False, f"AI服务模块测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_scheduled_script():
    """测试定时执行脚本"""
    print_test_header("定时执行脚本检查")
    
    script_file = BASE_DIR / "run_scheduled.sh"
    if not script_file.exists():
        print_result(False, "run_scheduled.sh 不存在")
        return False
    
    # 检查文件权限
    import stat
    file_stat = script_file.stat()
    is_executable = bool(file_stat.st_mode & stat.S_IEXEC)
    
    if is_executable:
        print_result(True, "run_scheduled.sh 具有执行权限")
    else:
        print_result(False, "run_scheduled.sh 没有执行权限")
        print("  提示: 可以运行 'chmod +x run_scheduled.sh' 添加执行权限")
    
    # 检查脚本内容
    try:
        content = script_file.read_text(encoding="utf-8")
        if "SCHEDULE_TIME" in content:
            print_result(True, "脚本包含 SCHEDULE_TIME 配置检查")
        if "random_time" in content:
            print_result(True, "脚本包含随机时间生成逻辑")
        if ".venv" in content or "uv run" in content:
            print_result(True, "脚本支持uv虚拟环境")
    except Exception as e:
        print_result(False, f"读取脚本文件失败: {e}")
    
    return True

def test_dependencies():
    """测试依赖安装"""
    print_test_header("依赖检查")
    
    venv_path = BASE_DIR / ".venv"
    venv_exists = venv_path.exists()
    python_path = Path(sys.executable)
    is_in_venv = ".venv" in str(python_path) or "venv" in str(python_path)
    
    # 如果存在.venv但不在虚拟环境中，给出提示
    if venv_exists and not is_in_venv:
        print("⚠️  检测到依赖可能安装在虚拟环境中，但当前使用系统Python")
        print("   建议使用 'uv run test.py' 或激活虚拟环境后运行")
        print()
    
    try:
        import subprocess
        
        # 尝试使用uv pip list（如果可用）
        use_uv = False
        if venv_exists:
            try:
                result = subprocess.run(
                    ["uv", "pip", "list"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    cwd=str(BASE_DIR)
                )
                if result.returncode == 0:
                    installed_packages = result.stdout.lower()
                    use_uv = True
                    print_result(True, "使用uv pip list检查依赖")
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
        
        # 如果uv不可用，使用标准pip
        if not use_uv:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list"],
                capture_output=True,
                text=True,
                timeout=10
            )
            installed_packages = result.stdout.lower()
        
        required_packages = {
            "playwright": "playwright",
            "zhipuai": "zhipuai",
            "pillow": "PIL",
            "python-dotenv": "dotenv"
        }
        
        all_installed = True
        for package_name, import_name in required_packages.items():
            if package_name.lower() in installed_packages:
                print_result(True, f"{package_name} 已安装")
            else:
                print_result(False, f"{package_name} 未安装")
                if venv_exists and not is_in_venv:
                    print(f"   提示: 如果使用uv虚拟环境，请运行 'uv run test.py'")
                all_installed = False
        
        return all_installed
    except Exception as e:
        print_result(False, f"依赖检查失败: {e}")
        return False

def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("SakuraFRP 自动签到脚本 - 测试套件")
    print("="*60)
    
    # 检查Python环境
    is_in_venv, venv_exists = check_python_environment()
    
    # 显示当前Python信息
    python_version = sys.version.split()[0]
    python_path = sys.executable
    print(f"\n当前Python环境:")
    print(f"  Python版本: {python_version}")
    print(f"  Python路径: {python_path}")
    if is_in_venv:
        print(f"  环境类型: 虚拟环境")
    elif venv_exists:
        print(f"  环境类型: 系统Python（检测到.venv但未使用）")
    else:
        print(f"  环境类型: 系统Python")
    
    tests = [
        ("模块导入", test_imports),
        ("文件检查", test_files),
        ("配置文件", test_config_files),
        ("日志模块", test_logger),
        ("AI服务模块", test_ai_service),
        ("定时脚本", test_scheduled_script),
        ("依赖检查", test_dependencies),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ 测试 '{test_name}' 执行异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    # 打印总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status}: {test_name}")
    
    print(f"\n总计: {passed}/{total} 项测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！项目配置正确。")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 项测试失败，请检查上述错误信息。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
