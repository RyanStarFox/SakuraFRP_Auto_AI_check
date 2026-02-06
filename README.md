# SAKURA FRP 自动签到脚本

> 自动访问 `https://www.natfrp.com/user/` ，使用智谱AI + 专业验证码识别库完成每日签到；支持在本地直接运行，也支持在 **QingLong（青龙）** 定时任务中运行，以及Linux系统定时执行。
> 
> **功能亮点**：
> - ✅ 智能验证码识别：支持**九宫格点选**和**滑块拖动**两种验证码
> - ✅ 专业缺口识别：使用 [captcha-recognizer](https://github.com/chenwei-zhao/captcha-recognizer) 深度学习库，识别准确率高达 96%+
> - ✅ 人性化拖动：使用 PyAutoGUI 缓动函数，模拟真实人类操作轨迹（先加速后减速、随机抖动、超调回调）
> - ✅ 自动截图调试：保存验证码图片和拖动前后截图，方便问题排查
> - ✅ 详细日志记录：每日独立日志文件，记录完整操作流程

## 一、目录结构

```
.
├── main.py                    # 主程序
├── ai_service.py              # AI调用模块
├── logger.py                  # 日志记录模块
├── test.py                    # 测试脚本（包含项目配置和API测试）
├── generate_random_time.sh    # 抽签脚本（生成随机时间）
├── run_checkin.sh             # 执行脚本（检查并执行签到）
├── run_scheduled.sh           # 旧版定时执行脚本（已废弃，保留用于兼容）
├── env.example                 # 环境变量配置示例（需复制为.env）
├── requirements.txt           # Python依赖列表
├── .venv/                     # uv虚拟环境目录（使用uv时自动生成）
├── account.txt                # 账号文件（必填：第1行用户名；第2行密码）
├── .env                       # 环境变量配置文件（需自行创建）
├── state.json                 # 登录状态缓存文件（自动生成与更新）
├── checkin.png                # 成功时保存的签到区域截图（可选）
├── random_time_YYYY-MM-DD.txt # 每日随机时间文件（自动生成）
├── logs/                      # 日志目录（自动生成）
│   └── checkin_YYYY-MM-DD.log # 每日日志文件
└── [调试截图]                  # 验证码处理时自动生成（用于调试）
    ├── captcha_bg.png         # 验证码背景图
    ├── captcha_slice.png      # 验证码滑块图
    ├── captcha_full.png       # 完整验证码区域
    ├── slider_before_drag.png # 滑块拖动前截图
    ├── slider_after_drag.png  # 滑块拖动后截图
    ├── before_click.png       # 点击签到按钮前截图
    └── after_click.png        # 点击签到按钮后截图
```

> 说明：程序会优先尝试复用 `state.json` 中的登录状态；状态失效时会自动回退为账号密码登录。

## 二、准备工作

### 1. 安装依赖

#### 方式一：使用 uv（推荐，更快）

```bash
# 安装uv（如果尚未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 创建虚拟环境并安装依赖
uv venv
source .venv/bin/activate  # Linux/Mac
# 或 .venv\Scripts\activate  # Windows

# 安装依赖
uv pip install -r requirements.txt

# ⚠️ 重要：安装Playwright浏览器（必须执行）
# 方式1：使用uv run（推荐）
uv run playwright install chromium

# 方式2：激活虚拟环境后执行
source .venv/bin/activate
playwright install chromium

# 方式3：使用Python模块方式
uv run python -m playwright install chromium
```

#### 方式二：使用传统 pip

```bash
pip install -r requirements.txt

# ⚠️ 重要：安装Playwright浏览器（必须执行）
playwright install chromium
```

> **注意**：安装完Python依赖后，**必须**运行 `playwright install chromium` 来下载浏览器，否则运行脚本时会报错 `Executable doesn't exist`。

### 2. 创建账号文件 `account.txt`

- 第 1 行：用户名
- 第 2 行：密码
- 文件编码建议使用 `UTF-8`，不要多余空行或空格。

示例：
```
your_username
your_password
```

### 3. 配置环境变量

复制 `env.example` 为 `.env` 并填写配置：

```bash
cp env.example .env
```

编辑 `.env` 文件，配置以下内容：

```env
# 智谱AI API配置
# 请前往 https://open.bigmodel.cn/ 注册并获取API Key
# 免费模型无需付费即可使用
ZHIPU_API_KEY=your_api_key_here

# 视觉识别模型（用于识别九宫格验证码）
# 默认使用免费的 glm-4v-flash 模型
ZHIPU_MODEL_VISION=glm-4v-flash

# 文本模型（用于语义匹配）
# 默认使用免费的 glm-4-flash 模型
ZHIPU_MODEL_TEXT=glm-4-flash

# 定时执行时间（格式：HH:MM，如 08:00）
# 脚本会在指定时间±30分钟内随机选择一个秒级时间点执行
# 例如：设置为 08:00，则会在 07:30:00 到 08:30:00 之间随机执行
SCHEDULE_TIME=08:00
```

> **注意**：
> - 需要自己去智谱AI获取APIKey，使用的是**免费**的模型
> - **九宫格验证码**使用智谱AI视觉模型识别
> - **滑块验证码**使用本地的 `captcha-recognizer` 库识别，**不消耗API调用**

## 三、运行方式

### 方式一：手动运行

支持三种记录模式：

**如果使用uv虚拟环境：**
```bash
# 激活虚拟环境
source .venv/bin/activate  # Linux/Mac
# 或 .venv\Scripts\activate  # Windows

# 运行脚本
uv run main.py --both
# 或
python main.py --both
```

**如果使用传统Python环境：**

1. **仅记录截图**（不记录日志）：
```bash
python3 main.py --screenshot-only
```

2. **仅记录日志**（不保存截图）：
```bash
python3 main.py --log-only
```

3. **同时记录截图和日志**（默认）：
```bash
python3 main.py --both
# 或直接运行（默认就是both模式）
python3 main.py
```

### 方式二：Linux定时执行（推荐）

使用cron定时执行，脚本会在指定时间±30分钟内随机选择一个秒级时间点执行，避免被识别为机器行为。

#### 1. 配置cron任务

编辑crontab：
```bash
crontab -e
```

添加以下两行（根据你的时间窗口调整）：
```bash
# 假设SCHEDULE_TIME设置为08:30，则时间窗口为08:00-09:00
# 第一行：每天在时间窗口开始前30分钟抽签（生成随机时间）
30 7 * * * /path/to/SakuraFRP_Auto_AI_check/generate_random_time.sh >> /path/to/logs/cron.log 2>&1

# 第二行：在时间窗口内每分钟检查并执行（08:00-09:00）
* 8-9 * * * /path/to/SakuraFRP_Auto_AI_check/run_checkin.sh >> /path/to/logs/cron.log 2>&1
```

**说明**：
- 第一行：`30 7 * * *` 表示每天7:30执行抽签脚本，生成当天的随机执行时间
- 第二行：`* 8-9 * * *` 表示8点到9点之间每分钟执行检查脚本
- 如果 `SCHEDULE_TIME=08:30`，时间窗口为08:00-09:00，抽签在07:30执行
- 脚本内部会检查当前时间是否匹配当天的随机时间，匹配才执行，否则静默退出

#### 2. 脚本执行逻辑

**抽签阶段（`generate_random_time.sh`）：**
- 每天在时间窗口开始前30分钟执行（例如：如果签到时间是08:30，则在07:30执行）
- 在指定时间±30分钟内随机生成一个秒级时间点（例如：08:15:23）
- 将随机时间保存到 `random_time_YYYY-MM-DD.txt` 文件

**执行阶段（`run_checkin.sh`）：**
- 在时间窗口内每分钟被cron调用（例如：08:00-09:00每分钟执行一次）
- 读取当天的随机时间文件
- 检查当前时间是否匹配随机时间的分钟
- **秒级精确控制**：如果分钟匹配，检查当前秒数：
  - 如果当前秒数 < 目标秒数：使用 `sleep` 等待到目标秒数
  - 如果当前秒数 ≥ 目标秒数：立即执行（可能cron执行有延迟）
- 执行签到脚本，完成后创建锁文件防止重复执行

**秒级精确控制原理：**
- cron只能精确到分钟，在匹配分钟的第0秒执行脚本
- 脚本内部获取当前秒数，如果小于目标秒数，使用 `sleep` 等待
- 例如：随机时间是08:15:23，cron在08:15:00执行脚本，脚本sleep 23秒后在08:15:23执行签到

#### 3. 优势

- **逻辑清晰**：抽签和执行分离，职责明确
- **资源占用低**：抽签只执行一次，执行检查次数减半（从120次降到60次）
- **秒级精确**：通过sleep实现秒级精确控制
- **易于维护**：两个脚本各司其职，便于调试和修改

### 方式三：在 QingLong（青龙）中使用

> 适用于青龙面板 v2.XX 及以上版本（路径请以你面板的实际目录为准）。

#### 1）放置脚本与账号文件

方式 A：在面板「文件管理」中将所有文件上传到脚本目录，例如：
```
/ql/data/scripts/natfrp_checkin/
```

方式 B：通过仓库/订阅拉取（如你有自建仓库），确保最终能在脚本目录看到所有文件。

> **注意**：`account.txt` 和 `.env` 一定要跟 `main.py` 放在同一目录。

#### 2）创建定时任务

在青龙面板 ->「定时任务」->「新建任务」：

- **名称**：NATFRP 自动签到
- **命令**（按你的实际路径替换）：
  
  **如果使用uv虚拟环境：**
  ```bash
  cd /ql/data/scripts/natfrp_checkin && .venv/bin/python main.py --both
  ```
  
  **或使用传统Python：**
  ```bash
  python3 /ql/data/scripts/natfrp_checkin/main.py --both
  ```
- **定时规则（CRON）**：建议每日固定时间运行一次，例如每天 8:10：
  ```
  10 8 * * *
  ```

保存后即可生效。你也可以在任务列表中手动点击「运行」测试是否正常。

## 四、日志功能

脚本支持按日期分割的日志记录功能：

- **日志位置**：`logs/checkin_YYYY-MM-DD.log`
- **日志格式**：`[时间戳] [状态] 简要信息`
- **记录内容**：
  - 脚本启动时间
  - 登录状态（已登录/需要登录）
  - 签到状态（已签到/签到成功/签到失败）
  - 验证码处理结果
  - 错误信息

示例日志内容：
```
[2024-01-01 08:15:23] [INFO] 脚本启动
[2024-01-01 08:15:24] [INFO] 登录状态: 已登录
[2024-01-01 08:15:25] [SUCCESS] 签到完成
```

## 五、环境要求

- Python 3.7 及以上版本
- 需要安装的Python包见 `requirements.txt`：
  - `playwright>=1.40.0` - 浏览器自动化
  - `zhipuai>=2.0.0` - 智谱AI SDK
  - `pillow>=10.0.0` - 图像处理
  - `python-dotenv>=1.0.0` - 环境变量管理
  - `numpy>=1.24.0` - 数值计算（用于图像处理）
  - `captcha-recognizer>=1.0.2` - 专业滑块验证码识别库
  - `pyautogui>=0.9.54` - GUI自动化（提供缓动函数）
- Linux系统需要安装cron（通常已预装）
- （可选）推荐使用 [uv](https://github.com/astral-sh/uv) 进行依赖管理，速度更快

## 六、常见问题

1. **提示 `Executable doesn't exist` 或 `BrowserType.launch` 错误**
   - 这是因为没有安装Playwright浏览器；
   - **如果使用uv虚拟环境**：
     - 运行 `uv run playwright install chromium`（推荐）
     - 或 `uv run python -m playwright install chromium`
   - **如果使用传统pip虚拟环境**：
     - 激活虚拟环境：`source .venv/bin/activate`
     - 运行 `playwright install chromium`
   - **如果使用系统Python**：
     - 直接运行 `playwright install chromium`
   - 安装完成后重新运行脚本即可。

2. **提示账号文件不存在或格式错误**
   - 确认 `account.txt` 与 `main.py` 在同一目录；
   - 确认文件编码为 `UTF-8`，且只有两行：第一行用户名，第二行密码；
   - 不要包含多余空行或空格。

3. **提示未找到ZHIPU_API_KEY环境变量或API调用失败**
   - 确认已创建 `.env` 文件（复制自 `env.example`）；
   - 确认 `.env` 文件中 `ZHIPU_API_KEY` 已正确配置；
   - 确认 `.env` 文件与 `main.py` 在同一目录；
   - **运行 `python3 test.py` 测试 API 配置是否正确**；
   - 检查 API Key 是否有效，免费配额是否已用完。

4. **一直提示登录状态过期**
   - 删除同目录下旧的 `state.json` 后重跑；
   - 确认账号密码正确；
   - 网络/地区问题可能导致访问异常，可稍后再试。

5. **出现滑块但始终无法通过**
   - 程序已使用专业的 `captcha-recognizer` 库和 PyAutoGUI 缓动函数，识别准确率很高；
   - 查看调试截图（`captcha_bg.png`、`slider_before_drag.png`、`slider_after_drag.png`）确认拖动位置；
   - 如果缺口识别准确但仍失败，可能是风控策略调整；
   - 可适当增加重试次数，或更换执行时间段；
   - 若长时间失败，建议手动登录一次，让站点信任度恢复。

5.1. **验证码识别相关**
   - **九宫格验证码**：使用智谱AI视觉模型识别目标物体并点击对应格子；
   - **滑块验证码**：使用 `captcha-recognizer` 深度学习库识别缺口位置（准确率 96%+）；
   - **拖动轨迹**：使用 PyAutoGUI 缓动函数模拟真实人类操作：
     - 随机选择缓动函数（easeInOutQuad、easeOutQuad、easeInOutCubic）
     - 加入 ±5px 随机误差
     - 水平和垂直抖动（±1.5px、±2px）
     - 50% 概率出现超调效果（overshooting）
     - 根据速度阶段调整时间间隔（前期快、后期慢）
   - **调试截图**：所有验证码相关截图会自动保存到工作目录，方便问题排查。

6. **成功了但没有截图**
   - 程序以出现"今天已经签到过啦"的提示为成功判据；
   - 如果站点文案发生变化，可修改 `ALREADY_SIGNED_TEXT`；
   - 截图保存路径由 `SUCCESS_SCREENSHOT` 控制（默认 `checkin.png`）。

7. **Linux定时执行不工作**
   - 确认cron服务正在运行：`systemctl status cron`（Debian/Ubuntu）或 `systemctl status crond`（CentOS/RHEL）；
   - 确认脚本有执行权限：`chmod +x generate_random_time.sh run_checkin.sh`；
   - 确认cron任务中的路径是绝对路径；
   - 查看cron日志：`grep CRON /var/log/syslog`（Debian/Ubuntu）或 `grep CRON /var/log/cron`（CentOS/RHEL）；
   - 确认两个cron任务都已正确配置（抽签脚本和执行脚本）。

8. **随机时间文件未生成**
   - 确认 `.env` 文件中 `SCHEDULE_TIME` 已正确配置；
   - 确认抽签脚本的cron任务已配置（在时间窗口开始前30分钟执行）；
   - 手动运行一次 `generate_random_time.sh` 测试是否正常生成随机时间文件。

9. **秒级精确控制不工作**
   - 确认执行脚本 `run_checkin.sh` 中的sleep逻辑正常工作；
   - 检查系统时间是否准确：`date`；
   - 查看执行日志确认sleep时间是否正确。

## 七、测试

运行测试脚本检查项目配置和API是否正确：

**如果使用uv虚拟环境（推荐）：**
```bash
uv run test.py
```

**如果使用系统Python：**
```bash
python3 test.py
```

**如果已激活虚拟环境：**
```bash
source .venv/bin/activate
python test.py
```

> **注意**：如果在uv虚拟环境中安装了依赖，请使用 `uv run test.py` 运行测试，否则会提示找不到库。

### 测试项目

测试脚本会依次检查以下内容：

#### 1. 模块导入测试
- ✓ playwright 模块
- ✓ zhipuai 模块
- ✓ PIL (Pillow) 模块
- ✓ python-dotenv 模块
- ✓ ai_service 自定义模块
- ✓ logger 自定义模块

#### 2. 文件检查
- ✓ main.py（主程序）
- ✓ ai_service.py（AI服务模块）
- ✓ logger.py（日志模块）
- ✓ requirements.txt（依赖列表）
- ✓ generate_random_time.sh（抽签脚本）
- ✓ run_checkin.sh（执行脚本）
- ✓ env.example（环境变量示例）

#### 3. 配置文件检查
- ✓ .env 文件是否存在
- ✓ ZHIPU_API_KEY 是否配置
- ✓ account.txt 是否存在且格式正确

#### 4. 日志模块测试
- ✓ CheckinLogger 初始化
- ✓ 日志写入功能
- ✓ 日志文件创建

#### 5. AI服务模块测试
- ✓ AIService 初始化
- ✓ 模型配置显示
- ✓ JSON解析功能

#### 6. 智谱AI API 测试（实际调用）
- ✓ .env 配置检查
- ✓ zhipuai 和 Pillow 库安装
- ✓ 客户端初始化
- ✓ **文本模型测试**（glm-4-flash）- 发送测试消息
- ✓ **视觉模型测试**（glm-4v-flash）- 识别测试图片
- ✓ API Key 有效性验证

#### 7. 定时脚本检查
- ✓ 脚本文件存在性
- ✓ 执行权限检查
- ✓ 脚本内容验证

#### 8. 依赖检查
- ✓ 所有必需包是否已安装

### 测试输出示例

```
============================================================
测试: 智谱AI API 测试
============================================================
  配置信息:
    API Key: abcdefghij1234567890...xyz1234567
    视觉模型: glm-4v-flash
    文本模型: glm-4-flash
✓ 通过: zhipuai 库已安装
✓ 通过: Pillow 库已安装
✓ 通过: 客户端初始化成功

  测试文本模型: glm-4-flash
✓ 通过: 文本模型测试成功 - 测试成功

  测试视觉模型: glm-4v-flash
✓ 通过: 视觉模型测试成功 - 我看到了一张白色背景的图片，中间有一个黑色的方形...

  💡 提示: 如果所有测试都通过，说明 API 配置正确
  💡 免费模型额度有限，如果配额用完需要等待重置或充值

============================================================
测试总结
============================================================
✓ 通过: 模块导入
✓ 通过: 文件检查
✓ 通过: 配置文件
✓ 通过: 日志模块
✓ 通过: AI服务模块
✓ 通过: 智谱AI API
✓ 通过: 定时脚本
✓ 通过: 依赖检查

总计: 8/8 项测试通过

🎉 所有测试通过！项目配置正确。
```

### 常见测试问题

**如果 API 测试失败**：
1. 检查 API Key 是否正确复制（没有多余空格或换行）
2. 确认是否有网络连接
3. 检查免费配额是否已用完（可在 [智谱AI控制台](https://open.bigmodel.cn/) 查看）
4. 确认模型名称正确（glm-4-flash、glm-4v-flash）

**如果提示依赖未安装但实际已安装**：
- 可能是虚拟环境问题，请使用 `uv run test.py` 或激活虚拟环境后运行

## 八、日志与产物

- **控制台输出**：执行时会输出每一步进度与判定结果，便于排查。
- **日志文件**：如果启用了日志记录，会在 `logs/` 目录下生成按日期分割的日志文件。
- **截图与状态**：
  - `checkin.png`：成功时的页面关键区域截图（如果启用了截图功能）；
  - `state.json`：登录状态缓存（自动生成/刷新）；
  - `random_time_YYYY-MM-DD.txt`：当天的随机执行时间（Linux定时执行时自动生成）。

## 九、验证码处理技术详解

### 9.1 支持的验证码类型

#### **1. 九宫格点选验证码**
- **识别方式**：使用智谱AI视觉模型（glm-4v-flash）
- **处理流程**：
  1. 截取验证码图片
  2. 提取问题文本（例如："请依次点击：香蕉"）
  3. 使用AI识别9个格子中哪些包含目标物体
  4. 按顺序点击对应格子
  5. 点击确认按钮

#### **2. 滑块拖动验证码**
- **识别方式**：使用 [captcha-recognizer](https://github.com/chenwei-zhao/captcha-recognizer) 深度学习库
- **处理流程**：
  1. 截取验证码背景图和滑块图
  2. 使用 Slider 模型识别缺口位置（准确率 96%+）
  3. 计算滑块需要拖动的距离
  4. 使用 PyAutoGUI 缓动函数模拟人类拖动轨迹
  5. 等待验证结果

### 9.2 人性化拖动技术

使用 **PyAutoGUI 缓动函数** 模拟真实人类操作，避免被识别为机器人：

#### **缓动函数（Easing Functions）**
随机选择以下缓动函数之一：
- `easeInOutQuad`：先加速后减速（最常见的人类操作）
- `easeOutQuad`：快速启动，逐渐减速
- `easeInOutCubic`：更平滑的加速减速曲线

#### **随机误差**
- 目标位置添加 **±5px** 随机误差
- 避免每次都精确拖到同一位置

#### **轨迹抖动**
- 水平方向：**±1.5px** 随机抖动
- 垂直方向：**±2px** 随机抖动
- 模拟人手的自然抖动

#### **超调效果（Overshooting）**
- **50%** 概率出现超调
- 超调距离：**2-5px**
- 然后回调到精确位置
- 模拟人类操作的不精确性

#### **变速拖动**
- 前 30%：快速移动（0.005-0.015s 每步）
- 中间 40%：稳定移动（0.01-0.025s 每步）
- 后 30%：减速移动（0.02-0.04s 每步）
- 符合人类操作的加速-稳定-减速模式

#### **步数随机**
- 拖动步数：**20-30 步**（随机）
- 轨迹更平滑自然

### 9.3 调试与排查

所有验证码处理过程会自动保存以下截图，方便问题排查：

| 文件名 | 说明 | 用途 |
|--------|------|------|
| `captcha_bg.png` | 验证码背景图 | 查看缺口位置 |
| `captcha_slice.png` | 验证码滑块图 | 查看滑块形状 |
| `captcha_full.png` | 完整验证码区域 | 查看整体布局 |
| `slider_before_drag.png` | 拖动前页面截图 | 查看初始状态 |
| `slider_after_drag.png` | 拖动后页面截图 | 查看拖动结果 |
| `before_click.png` | 点击签到按钮前 | 查看页面状态 |
| `after_click.png` | 点击签到按钮后 | 查看是否出现验证码 |

**日志输出示例**：
```
[INFO] 滑块拖动预测信息:
  滑块按钮左边缘X: 504.0px (页面坐标)
  滑块按钮中心X: 537.0px (页面坐标)
  背景canvas X: 510.0px (页面坐标)
  滑块初始偏移: -6.0px
  缺口位置: 152px (图片坐标)
  缺口实际位置: 662.0px (页面坐标)
  滑动距离: 146.0px (含±5px人类误差)
  目标中心X: 683.0px (页面坐标)

[DEBUG] 使用缓动函数: easeInOutQuad, 步数: 25
[DEBUG] 模拟超调: +3.2px
[INFO] 拖动前截图已保存: slider_before_drag.png
[INFO] 拖动后截图已保存: slider_after_drag.png
```

### 9.4 技术栈

- **智谱AI（ZhipuAI）**：视觉模型识别九宫格验证码
- **captcha-recognizer**：深度学习识别滑块缺口（基于 YOLOv5）
- **PyAutoGUI**：提供专业的缓动函数
- **Playwright**：浏览器自动化和元素定位
- **Pillow + NumPy**：图像处理和数据转换

---

**至此即可完成配置与使用。**

如需嵌入到你现有的青龙仓库，只要保证所有文件相对位置一致，并按上文的命令与定时规则召唤即可。祝签到愉快 🎯
