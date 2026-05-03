# 智慧课堂行为识别与分析系统

本项目面向本科毕业设计场景，提供课堂行为实时监测、上传视频离线分析、自动生成风险报告、管理员规则配置和实验评估展示页面。

## 主要功能

- 实时监测：展示课堂专注度、稳定行为人数、活动告警、最新截图和摄像头健康状态。
- 上传分析：上传课堂录像后自动创建分析任务，持续反馈进度、失败上下文和时间节点。
- 分析报告：输出风险结论、触发依据、教师建议、关键截图、趋势时间线和规则快照。
- 规则配置：管理员可调整连续帧阈值、告警秒数和告警开关。
- 实验评估：集中展示效果指标、参数对比、性能指标、方法说明、局限性和答辩演示路径。
- 多角色权限：支持管理员、教师、普通用户三种角色，隔离各自数据。

## 环境依赖

- Python 3.10+
- MySQL 或 SQLite
- `best.onnx` 模型文件

安装依赖：

```bash
pip install -r requirements.txt
```

## 启动方式

默认情况下系统会优先使用环境变量拼接 MySQL 连接；若要快速演示，推荐先使用 SQLite：

```bash
set DATABASE_URL=sqlite:///classroom_demo.db
python app.py
```

PowerShell 一键脚本（推荐）：

```powershell
.\scripts\run_sqlite.ps1
.\scripts\test.ps1
```

如需验证 MySQL 双支持，可用：

```powershell
.\scripts\run_mysql.ps1 -Host 127.0.0.1 -Port 3306 -User root -Password "" -Database classroom_demo
```

可选环境变量：

- `YOLO_MODEL_PATH`：模型文件路径，默认 `best.onnx`
- `UPLOAD_DIR`：上传目录，默认 `data/uploads`
- `MAX_UPLOAD_SIZE_MB`：上传大小上限，默认 `200`
- `MAX_VIDEO_DURATION_SECONDS`：单个视频最大时长（秒），默认 `3600`
- `MAX_VIDEO_FRAMES`：单个视频最大帧数（用于快速拒绝超长视频），默认 `300000`
- `CAMERA_INDEX` / `CAMERA_BACKEND`：摄像头输入配置
- `STREAM_FPS` / `INFERENCE_EVERY_N_FRAMES`：实时链路采样与推理频率
- `FLASK_SECRET_KEY`：Flask 会话密钥；若未配置，系统会自动生成并持久化到 `data/runtime/flask_secret_key.txt`
- `FLASK_SECRET_KEY_FILE`：自定义会话密钥文件路径（优先级低于 `FLASK_SECRET_KEY`）
- `SESSION_COOKIE_SECURE`：是否启用 Secure Cookie（本机 HTTP 演示建议保持关闭；部署到 HTTPS 时可打开）
- `JOB_EXECUTOR_BACKEND`：后台执行器（`thread` / `process` / `queue`）
- `JOB_QUEUE_DIR` / `JOB_QUEUE_POLL_SECONDS`：文件队列目录与轮询间隔（当 `JOB_EXECUTOR_BACKEND=queue` 时生效）

启动后访问：

- 登录页：[http://127.0.0.1:5000/login](http://127.0.0.1:5000/login)
- 系统总览：[http://127.0.0.1:5000/](http://127.0.0.1:5000/)
- 规则配置中心：[http://127.0.0.1:5000/admin/rules](http://127.0.0.1:5000/admin/rules)
- 实验评估页：[http://127.0.0.1:5000/evaluation](http://127.0.0.1:5000/evaluation)
- 健康检查接口：[http://127.0.0.1:5000/api/health](http://127.0.0.1:5000/api/health)

## 运行与退化策略

- 模型文件缺失时，健康检查会明确提示错误，相关分析接口会返回可读错误信息。
- 摄像头不可用时，实时监测页会自动切换到占位画面，不影响规则配置、历史记录和报告展示。
- 上传任务会记录排队、开始、完成、删除时间，以及失败阶段和错误摘要。
- 专注度评分仅用于课堂状态可视化展示，不直接等同于教学质量评价。

## 默认账号

- 默认管理员用户名：`admin`
- 默认管理员密码：`admin123456`
- 生产环境建议设置 `APP_ENV=production`（默认将跳过创建默认管理员）；如需启用请显式设置 `SEED_DEFAULT_ADMIN=1`
- 可通过 `DISABLE_DEFAULT_ADMIN_SEED=1` 强制禁用默认管理员种子逻辑
- 可通过 `DEFAULT_ADMIN_PASSWORD` 指定强密码；若检测为弱口令将强制首次登录修改密码

首次使用默认管理员登录后，系统会强制要求修改密码。

### 默认账户安全说明

- 默认账号仅用于本机演示和答辩环境，不建议在公网或多人共享环境中保留。
- 演示前建议先用默认管理员登录并完成强制改密，避免评审老师看到弱口令停留页。
- 部署到生产环境时建议设置 `APP_ENV=production`、`FLASK_SECRET_KEY` 和强 `DEFAULT_ADMIN_PASSWORD`，并确认 `SESSION_COOKIE_SECURE=1` 运行在 HTTPS 下。
- 如需彻底关闭默认账号种子逻辑，设置 `DISABLE_DEFAULT_ADMIN_SEED=1`。

## 常见问题排查

- **模型文件缺失 / 预测报错**：检查 `YOLO_MODEL_PATH` 指向的 `best.onnx` 是否存在；健康检查接口会提示模型状态。
- **摄像头不可用**：调整 `CAMERA_INDEX` / `CAMERA_BACKEND`；系统会自动降级到占位画面，不影响离线分析演示。
- **MySQL 连接失败**：优先检查 `DATABASE_URL`；若使用 `MYSQL_USER`/`MYSQL_PASSWORD` 拼接，注意密码中包含特殊字符时应正确配置（系统会做 URL 编码）。
- **上传文件过大**：调整 `MAX_UPLOAD_SIZE_MB`，或在规则配置中心切换更适合演示的运行方案。
- **启用文件队列后任务不跑**：当 `JOB_EXECUTOR_BACKEND=queue` 时，需要另开终端运行 `python -m app_core.queue_worker` 消费队列文件。
- **删除任务后磁盘文件仍残留**：Windows 下文件可能被占用导致删除失败，可运行 `python -m app_core.maintenance cleanup-orphans` 清理状态为 `deleted` 的任务残留文件。

## 推荐答辩演示路径

1. **登录与安全边界**：使用管理员账号登录，说明首次登录强制改密、角色权限和数据隔离。
2. **系统总览**：打开首页，讲清楚实时监测、离线分析、报告生成和规则配置这四个闭环模块。
3. **规则配置**：进入规则配置中心，展示连续帧阈值、告警秒数和开关可调，强调系统不是写死规则。
4. **实时监测**：进入实时监测页，展示摄像头画面；若现场无摄像头，则展示占位退化提示，说明系统具备可解释降级。
5. **离线分析**：上传一段课堂视频，展示排队、处理中、生成报告等状态进度，以及失败阶段提示。
6. **分析报告**：打开报告页，按“风险结论 → 证据摘要 → 关键截图 → 教师建议 → 规则快照”的顺序讲。
7. **实验评估**：最后进入实验评估页，说明识别效果、参数选择、性能指标和方法局限，形成论文闭环。

### 演示前检查清单

- 确认 `best.onnx` 存在，或通过 `YOLO_MODEL_PATH` 指向正确模型文件。
- 运行 `.\scripts\run_sqlite.ps1` 后先打开 `/api/health`，确认数据库、模型、上传目录状态正常。
- 准备一段较短课堂样例视频，避免现场等待过长；如需快速演示，可优先使用 `samples/demo_videos/`。
- 提前用默认管理员完成首次改密，确保答辩时直接进入系统主界面。
- 如果现场摄像头不可用，按“系统自动降级到占位画面，离线分析和报告不受影响”解释即可。
- 演示报告页前先完成一次视频分析，保证 `/report/latest` 有可展示内容。

## 毕设写作建议

- 创新点可以聚焦：实时监测 + 离线分析 + 规则可配置 + 自动报告。
- 实验章节建议包含：效果指标、参数对比、系统性能、方法边界说明。
- 截图素材优先使用：首页总览、规则配置中心、分析报告、实验评估页。

## 代码结构

- `webapp.py`：主应用入口、统一配置装配、健康检查与错误处理。
- `app_config.py`：运行配置读取、默认值与启动摘要。
- `analysis_service.py`：离线分析任务、首页总览数据与统计拼装。
- `report_service.py`：分析报告生成所需的数据整理逻辑。
- `database.py`：数据库模型、初始化与配置持久化。
- `behavior_core.py`：行为映射、时序判定规则和分析器。
- `storage.py`：告警事件与截图存储。
- `experiment_data.py`：实验评估页所需的示例实验数据。
- `templates/`：前端页面模板。
- `static/`：样式与页面脚本。
