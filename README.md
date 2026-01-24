# SAKURA FRP 自动签到脚本

> 自动访问 `https://www.natfrp.com/user/` ，使用智谱API识别人机验证并完成每日签到；支持在本地直接运行，也支持在 **QingLong（青龙）** 定时任务中运行，以及Linux系统定时执行。
> 成功后会自动保存签到结果截图（默认：`checkin.png`），并在必要时自动处理滑块验证。

## 一、目录结构

```
.
├── main.py                    # 主程序
├── ai_service.py              # AI调用模块
├── logger.py                  # 日志记录模块
├── test.py                    # 测试脚本
├── run_scheduled.sh           # Linux定时执行脚本
├── env.example                 # 环境变量配置示例（需复制为.env）
├── requirements.txt           # Python依赖列表
├── .venv/                     # uv虚拟环境目录（使用uv时自动生成）
├── account.txt                # 账号文件（必填：第1行用户名；第2行密码）
├── .env                       # 环境变量配置文件（需自行创建）
├── state.json                 # 登录状态缓存文件（自动生成与更新）
├── checkin.png                # 成功时保存的签到区域截图（可选）
├── random_time_YYYY-MM-DD.txt # 每日随机时间文件（自动生成）
└── logs/                      # 日志目录（自动生成）
    └── checkin_YYYY-MM-DD.log # 每日日志文件
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
playwright install chromium
```

#### 方式二：使用传统 pip

```bash
pip install -r requirements.txt
playwright install chromium
```

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

# 视觉识别模型（用于识别验证码图片）
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

> **注意**：需要自己去智谱AI获取APIKey，使用的是免费的模型。

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

添加以下行（根据你的时间窗口调整）：
```bash
# 假设SCHEDULE_TIME设置为08:00，则时间窗口为07:00-09:00
# 在时间窗口内每分钟执行一次脚本
* 7-9 * * * /path/to/SakuraFRP_Auto_AI_check/run_scheduled.sh >> /path/to/logs/cron.log 2>&1
```

**说明**：
- `* 7-9 * * *` 表示7点到9点之间每分钟执行一次
- 如果 `SCHEDULE_TIME=08:00`，建议设置为 `* 7-9 * * *`（覆盖07:30-09:30的时间窗口）
- 脚本内部会检查当前时间是否匹配当天的随机时间，匹配才执行，否则静默退出

#### 2. 脚本执行逻辑

- 每天第一次运行时（在时间窗口内），脚本会生成当天的随机执行时间并保存到 `random_time_YYYY-MM-DD.txt`
- 每次被cron调用时，脚本检查当前时间是否匹配当天的随机时间（精确到秒）
- 如果匹配则执行签到脚本，否则静默退出
- 这样确保每天只在随机时间执行一次，且时间在指定时间±30分钟内

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
- 需要安装的Python包见 `requirements.txt`
- Linux系统需要安装cron（通常已预装）
- （可选）推荐使用 [uv](https://github.com/astral-sh/uv) 进行依赖管理，速度更快

## 六、常见问题

1. **提示账号文件不存在或格式错误**
   - 确认 `account.txt` 与 `main.py` 在同一目录；
   - 确认文件编码为 `UTF-8`，且只有两行：第一行用户名，第二行密码；
   - 不要包含多余空行或空格。

2. **提示未找到ZHIPU_API_KEY环境变量**
   - 确认已创建 `.env` 文件（复制自 `.env.example`）；
   - 确认 `.env` 文件中 `ZHIPU_API_KEY` 已正确配置；
   - 确认 `.env` 文件与 `main.py` 在同一目录。

3. **一直提示登录状态过期**
   - 删除同目录下旧的 `state.json` 后重跑；
   - 确认账号密码正确；
   - 网络/地区问题可能导致访问异常，可稍后再试。

4. **出现滑块但始终无法通过**
   - 目标站点的风控策略可能调整；
   - 可适当增加重试次数，或更换执行时间段；
   - 若长时间失败，建议手动登录一次，让站点信任度恢复。

5. **成功了但没有截图**
   - 程序以出现"今天已经签到过啦"的提示为成功判据；
   - 如果站点文案发生变化，可修改 `ALREADY_SIGNED_TEXT`；
   - 截图保存路径由 `SUCCESS_SCREENSHOT` 控制（默认 `checkin.png`）。

6. **Linux定时执行不工作**
   - 确认cron服务正在运行：`systemctl status cron`（Debian/Ubuntu）或 `systemctl status crond`（CentOS/RHEL）；
   - 确认 `run_scheduled.sh` 有执行权限：`chmod +x run_scheduled.sh`；
   - 确认cron任务中的路径是绝对路径；
   - 查看cron日志：`grep CRON /var/log/syslog`（Debian/Ubuntu）或 `grep CRON /var/log/cron`（CentOS/RHEL）。

7. **随机时间文件未生成**
   - 确认 `.env` 文件中 `SCHEDULE_TIME` 已正确配置；
   - 确认cron任务的时间窗口覆盖了 `SCHEDULE_TIME ± 30分钟` 的范围；
   - 手动运行一次 `run_scheduled.sh` 测试是否正常。

## 七、测试

运行测试脚本检查项目配置是否正确：

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

测试脚本会检查：
- ✓ 模块导入是否正常
- ✓ 必要文件是否存在
- ✓ 配置文件是否正确
- ✓ 日志模块功能
- ✓ AI服务模块初始化
- ✓ 定时执行脚本
- ✓ 依赖包安装情况

如果所有测试通过，说明项目配置正确，可以正常使用。

## 八、日志与产物

- **控制台输出**：执行时会输出每一步进度与判定结果，便于排查。
- **日志文件**：如果启用了日志记录，会在 `logs/` 目录下生成按日期分割的日志文件。
- **截图与状态**：
  - `checkin.png`：成功时的页面关键区域截图（如果启用了截图功能）；
  - `state.json`：登录状态缓存（自动生成/刷新）；
  - `random_time_YYYY-MM-DD.txt`：当天的随机执行时间（Linux定时执行时自动生成）。

---

**至此即可完成配置与使用。**

如需嵌入到你现有的青龙仓库，只要保证所有文件相对位置一致，并按上文的命令与定时规则召唤即可。祝签到愉快 🎯
