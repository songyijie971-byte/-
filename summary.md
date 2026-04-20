# Project Summary

## 项目结构总览

- `app.py`
  - Flask 主程序
  - 摄像头读取
  - ONNX 模型加载
  - 实时推理
  - 简单后处理与统计接口
- `test_onnx.py`
  - 单张图片推理验证脚本
- `templates/index.html`
  - 前端监控页面
  - 视频流展示
  - 统计卡片展示
  - 静态历史记录与设置页
- `best.onnx`
  - 检测模型文件
- `requirements.txt`
  - Python 依赖声明
- `image.png`
  - 测试输入图片
- `result.jpg`
  - 测试输出图片
- `.venv/`
  - 本地虚拟环境，目前未安装业务依赖

## 核心模块说明

### 1. Web 与主流程

- 文件：`app.py`
- 使用 Flask 提供页面、视频流和统计接口。
- 主入口为 `python app.py`。

### 2. 摄像头输入

- 使用 `cv2.VideoCapture(0)` 从默认摄像头取流。
- 当前没有视频文件输入、RTSP 输入或多路输入支持。

### 3. 模型加载

- 使用 `ultralytics.YOLO("best.onnx", task="detect")` 加载 ONNX 模型。
- 模型加载写在模块顶层，程序启动时即初始化。

### 4. 模型推理

- 实时流中使用 `model.predict(frame, conf=0.35, iou=0.45, verbose=False)`。
- 静态图测试中使用 `model(img, conf=0.25)`。

### 5. 后处理

- 当前后处理非常轻量：
  - 遍历 `results[0].boxes.cls`
  - 依据类别 ID 计数
- 没有独立后处理模块，没有置信度二次筛选、NMS 自定义、ROI 过滤等逻辑。

### 6. 行为判定

- 当前行为判定等同于“检测类别归类统计”：
  - `0, 5 -> phone`
  - `8 -> sleep`
  - `4 -> hand`
  - `9 -> turn`
- 这是单帧规则，不包含连续时长、轨迹、身份跟踪等真实行为分析。

### 7. 可视化输出

- `results[0].plot()` 负责绘制检测框。
- 后端将图像编码为 JPG 后通过 `/video_feed` 推送。
- 前端通过 `/api/stats` 轮询刷新统计数字。

## 完整调用链

### 实时主链路

`摄像头输入 -> Ultralytics 内置预处理 -> ONNX 推理 -> 简单类别计数后处理 -> 基于类别 ID 的行为归类 -> 视频框图 + 前端数字统计输出`

对应关系：

- 摄像头输入
  - `cv2.VideoCapture(0)` 读取默认摄像头帧
- 预处理
  - 代码中没有显式预处理函数
  - 当前直接把 `frame` 传给 `ultralytics.YOLO.predict(...)`
  - resize / normalize / tensor 化由 Ultralytics 内部完成
- 模型推理
  - `YOLO("best.onnx", task="detect")`
  - `model.predict(frame, conf=0.35, iou=0.45, verbose=False)`
- 后处理
  - 遍历 `results[0].boxes.cls`
  - 基于类别 ID 做统计聚合
- 行为判定
  - `0, 5 -> phone`
  - `8 -> sleep`
  - `4 -> hand`
  - `9 -> turn`
- 可视化输出
  - `results[0].plot()` 画框
  - `/video_feed` 输出 MJPEG 视频流
  - `/api/stats` 输出统计 JSON
  - 前端每 500ms 轮询更新 4 个统计卡片

### 现有旁路线

- `test_onnx.py` 提供单张图片推理测试：
  - `image.png -> model(img, conf=0.25) -> 统计类别 -> results[0].plot() -> result.jpg`

## 当前运行方式

### Web 实时演示

1. 安装依赖
2. 运行 `python app.py`
3. 打开 `http://127.0.0.1:5000/`
4. 页面会自动加载视频流和统计数据

### 静态图片测试

1. 准备 `image.png`
2. 运行 `python test_onnx.py`
3. 查看终端类别统计和生成的 `result.jpg`

### 当前环境状态

- 仓库内有 `.venv`
- 但当前虚拟环境尚未安装 `flask`、`ultralytics`、`opencv-python` 等依赖
- 因此项目在当前机器上还不能直接启动

## 依赖项

### Python 依赖

- flask
- ultralytics
- opencv-python
- numpy
- werkzeug

### 其他依赖

- `best.onnx`
- Tailwind CDN

## 现阶段功能清单

### 已完成模块

- Flask Web 服务基础壳子
- 默认摄像头实时采集
- `best.onnx` 模型加载
- 实时目标检测推理
- 基于类别 ID 的简单计数
- 实时框图视频流输出
- 前端统计卡片刷新
- 单张图片推理验证脚本

### 未完成模块

- 本地视频文件输入
- 明确、可配置的预处理模块
- 独立的后处理模块
- 独立的行为判定模块
- 历史记录真实落库或落盘
- 告警机制
- 设置页与后端联动
- 类别配置与标签映射配置化
- 错误处理、日志、健康检查
- 多线程或多用户访问下的资源管理
- 启动脚本、README、部署说明

## 临时拼接与结构问题

- `app.py` 同时承担了模型加载、摄像头采集、推理、后处理、业务判定和 Web 路由。
- 行为规则直接硬编码在循环里，没有抽象层。
- `templates/index.html` 里的历史记录和设置页基本是静态展示，没有真实后端支撑。
- 页面里存在明显乱码，说明编码处理不统一。
- 前端使用 CDN Tailwind，适合演示，不适合离线或受限环境部署。
- `test_onnx.py` 是独立试验脚本，没有和主项目结构整合。

## 可能影响后续扩展的风险点

- 强绑定 Ultralytics `YOLO(...)` 封装，未来若切换纯 `onnxruntime`，改动面会较大。
- 类别 ID 被写死，模型一旦换版本或类目重排，业务判定会直接出错。
- 没有独立配置文件，`conf`、`iou`、类别映射、摄像头源都写死。
- 没有真正的时序行为分析，当前只有单帧检测计数。
- `current_stats` 是全局变量，未来多路视频或多客户端时会互相污染。
- 每次访问 `/video_feed` 都可能新开一个摄像头读取流程，存在资源争用风险。
- 前端轮询频率固定为 500ms，后续用户增多会放大无效请求。
- 当前 `.venv` 没有安装依赖，项目在这台机器上还不具备直接运行条件。
- 页面乱码说明编码链路不稳定，后续中文标签、告警文案、日志都可能受影响。

## 待办清单

- 拆分 `app.py`，按“输入 / 推理 / 后处理 / 业务规则 / Web”分层。
- 增加视频文件输入和可切换输入源。
- 抽离类别映射配置，避免写死类别 ID。
- 引入独立行为判定模块，支持时序分析。
- 接入历史记录存储。
- 接入截图和告警输出。
- 让设置页真正控制后端参数。
- 增加日志、异常处理、资源释放和健康检查。
- 统一编码，修复页面中文乱码。
- 补充 README 与启动说明。
