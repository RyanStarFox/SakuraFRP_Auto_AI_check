import os
from datetime import datetime
from pathlib import Path

class CheckinLogger:
    """签到日志记录器，按日期分割日志文件"""
    
    def __init__(self, base_dir=None):
        """初始化日志记录器"""
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent
        else:
            base_dir = Path(base_dir)
        
        self.base_dir = base_dir
        self.logs_dir = base_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # 获取今天的日志文件路径
        today = datetime.now().strftime("%Y-%m-%d")
        self.log_file = self.logs_dir / f"checkin_{today}.log"
    
    def _get_timestamp(self):
        """获取当前时间戳字符串"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def _write_log(self, status, message):
        """写入日志到文件"""
        timestamp = self._get_timestamp()
        log_entry = f"[{timestamp}] [{status}] {message}\n"
        
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            print(f"[ERROR] 写入日志失败: {e}")
    
    def log_start(self):
        """记录脚本启动"""
        self._write_log("INFO", "脚本启动")
    
    def log_login_status(self, is_logged_in):
        """记录登录状态"""
        status = "已登录" if is_logged_in else "需要登录"
        self._write_log("INFO", f"登录状态: {status}")
    
    def log_already_signed(self):
        """记录已签到状态"""
        self._write_log("SUCCESS", "今日已签到")
    
    def log_sign_success(self):
        """记录签到成功"""
        self._write_log("SUCCESS", "签到完成")
    
    def log_sign_failed(self, reason=""):
        """记录签到失败"""
        message = f"签到失败"
        if reason:
            message += f": {reason}"
        self._write_log("ERROR", message)
    
    def log_captcha_result(self, result):
        """记录验证码处理结果"""
        self._write_log("INFO", f"验证码处理: {result}")
    
    def log_error(self, error_message):
        """记录错误信息"""
        self._write_log("ERROR", error_message)
    
    def log_info(self, message):
        """记录一般信息"""
        self._write_log("INFO", message)
    
    def log_debug(self, message):
        """记录调试信息"""
        self._write_log("DEBUG", message)
    
    def log_page_url(self, url):
        """记录页面URL"""
        self._write_log("DEBUG", f"当前页面URL: {url}")
    
    def log_element_status(self, element_name, is_visible, details=""):
        """记录元素状态"""
        status = "可见" if is_visible else "不可见"
        msg = f"元素 '{element_name}' 状态: {status}"
        if details:
            msg += f" ({details})"
        self._write_log("DEBUG", msg)
    
    def log_captcha_step(self, step, details=""):
        """记录验证码处理步骤"""
        msg = f"验证码处理步骤 {step}"
        if details:
            msg += f": {details}"
        self._write_log("DEBUG", msg)
    
    def log_wait_timeout(self, timeout_type, elapsed_time, max_time):
        """记录等待超时信息"""
        self._write_log("DEBUG", f"等待超时 - 类型: {timeout_type}, 已等待: {elapsed_time}秒, 最大等待: {max_time}秒")
    
    def log_exception(self, exception_type, exception_message, traceback_info=""):
        """记录异常信息"""
        msg = f"异常类型: {exception_type}, 错误信息: {exception_message}"
        if traceback_info:
            msg += f"\n堆栈信息: {traceback_info}"
        self._write_log("ERROR", msg)
