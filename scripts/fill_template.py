# -*- coding: utf-8 -*-
"""Fill defense PPT template with content, preserving all backgrounds.
Run this with PowerPoint already open and the template loaded.
Usage: python scripts/fill_template.py
"""
import win32com.client
import pythoncom, os

pythoncom.CoInitialize()
ppt = win32com.client.GetActiveObject('PowerPoint.Application')
pres = ppt.ActivePresentation

BASE_DIR = os.path.abspath('.')
SCREENSHOTS = os.path.join(BASE_DIR, 'ppt', 'screenshots')
CHARTS = os.path.join(BASE_DIR, 'ppt', 'charts')
THUMBS = os.path.join(BASE_DIR, 'samples', 'demo_videos', 'thumbs')


def set_text(shape, text, size=None, bold=None, color=None):
    """Set text on a shape, preserving formatting where possible."""
    try:
        if not shape.HasTextFrame:
            return
        tr = shape.TextFrame.TextRange
        tr.Text = text
        if size:
            tr.Font.Size = size
        if bold is not None:
            tr.Font.Bold = bold
        if color is not None:
            tr.Font.Color.RGB = color
    except Exception as e:
        print(f"  set_text error: {e}")


def get_title_shape(slide):
    """Find the title shape on a slide by placeholder type."""
    for j in range(1, slide.Shapes.Count + 1):
        sh = slide.Shapes(j)
        try:
            # Check placeholder type: ppPlaceholderTitle = 1, ppPlaceholderCenterTitle = 3
            if sh.PlaceholderFormat is not None:
                ptype = sh.PlaceholderFormat.Type
                if ptype in (1, 3):  # Title or Center Title
                    return sh
        except:
            pass
    # Fallback: search for common title placeholder text
    for j in range(1, slide.Shapes.Count + 1):
        sh = slide.Shapes(j)
        try:
            if sh.HasTextFrame:
                t = sh.TextFrame.TextRange.Text.strip()
                if '此处添加标题' in t or 'ADD YOUR TITLE' in t or '标题' in t:
                    return sh
        except:
            pass
    return None


def get_body_shapes(slide):
    """Find all body/content shapes on a slide."""
    results = []
    for j in range(1, slide.Shapes.Count + 1):
        sh = slide.Shapes(j)
        try:
            # Check placeholder type: ppPlaceholderBody = 2
            if sh.PlaceholderFormat is not None:
                ptype = sh.PlaceholderFormat.Type
                if ptype == 2:  # Body/Content
                    results.append(sh)
        except:
            pass
    if results:
        return results
    # Fallback: search for body placeholder text
    for j in range(1, slide.Shapes.Count + 1):
        sh = slide.Shapes(j)
        try:
            if sh.HasTextFrame:
                t = sh.TextFrame.TextRange.Text.strip()
                if ('此处添加' in t and '标题' not in t) or '在此输入内容' in t or '在此添加' in t:
                    results.append(sh)
        except:
            pass
    return results


def get_body_shape(slide, exclude=None):
    """Find the first body/content shape, excluding title."""
    for j in range(1, slide.Shapes.Count + 1):
        sh = slide.Shapes(j)
        try:
            if sh == exclude:
                continue
            if sh.PlaceholderFormat is not None:
                ptype = sh.PlaceholderFormat.Type
                if ptype == 2:  # Body
                    return sh
        except:
            pass
    # Fallback
    for j in range(1, slide.Shapes.Count + 1):
        sh = slide.Shapes(j)
        try:
            if sh == exclude:
                continue
            if sh.HasTextFrame:
                t = sh.TextFrame.TextRange.Text.strip()
                if t == '' or '此处' in t or '在此' in t or 'ADD' in t:
                    return sh
        except:
            pass
    return None


def insert_picture(slide, img_path, target_shape=None):
    """Insert a picture, replacing a target shape if provided."""
    if not os.path.exists(img_path):
        print(f"  Image not found: {img_path}")
        return None
    try:
        if target_shape:
            l, t, w, h = target_shape.Left, target_shape.Top, target_shape.Width, target_shape.Height
            target_shape.Delete()
            pic = slide.Shapes.AddPicture(img_path, False, True, l, t, w, h)
            return pic
        else:
            # Insert at default position (right side)
            pic = slide.Shapes.AddPicture(img_path, False, True,
                                          int(pres.PageSetup.SlideWidth * 0.55),
                                          int(pres.PageSetup.SlideHeight * 0.2),
                                          int(pres.PageSetup.SlideWidth * 0.4),
                                          int(pres.PageSetup.SlideHeight * 0.6))
            return pic
    except Exception as e:
        print(f"  insert_picture error: {e}")
        return None


# ===== Delete unwanted slides =====
# Keep slides: 1,2,4,5,6,12,14,18,20,21,27,31,32,33
keep = {1, 2, 4, 5, 6, 12, 14, 18, 20, 21, 27, 31, 32, 33}
total = pres.Slides.Count
to_delete = sorted([i for i in range(1, total + 1) if i not in keep], reverse=True)
for idx in to_delete:
    pres.Slides(idx).Delete()
print(f'After delete: {pres.Slides.Count} slides')

# Helper: list all shapes on a slide for debugging
def debug_shapes(slide, slide_num):
    print(f"\n--- Slide {slide_num} shapes ---")
    for j in range(1, slide.Shapes.Count + 1):
        sh = slide.Shapes(j)
        try:
            name = sh.Name
            ptype = -1
            try:
                ptype = sh.PlaceholderFormat.Type
            except:
                pass
            has_text = sh.HasTextFrame
            text_preview = ""
            if has_text:
                text_preview = sh.TextFrame.TextRange.Text[:40].replace('\n', '|')
            print(f"  [{j}] name='{name}' ptype={ptype} text='{text_preview}'")
        except Exception as e:
            print(f"  [{j}] error: {e}")


# ===== S1: Title slide =====
s = pres.Slides(1)
debug_shapes(s, 1)
ts = get_title_shape(s)
if ts:
    set_text(ts, '智慧课堂行为识别与分析系统的设计与实现', size=28, bold=True)
    print("S1: title set")
sub = get_body_shape(s, ts)
if sub:
    set_text(sub, '毕业设计答辩\n\n计算机科学专业 | 学号：2022015421\n指导教师：陈亮\n\n中国石油大学（北京）石油学院\n2026年5月', size=14)
    print("S1: subtitle set")
else:
    print("S1: WARNING - no body shape found")

# ===== S2: TOC slide =====
s = pres.Slides(2)
debug_shapes(s, 2)
ts = get_title_shape(s)
if ts:
    set_text(ts, '汇报提纲', size=32, bold=True)
sub = get_body_shape(s, ts)
if sub:
    set_text(sub, '一、选题背景与意义\n二、系统总体设计\n三、核心功能与实现\n四、系统演示\n五、关键算法\n六、实验与测试\n七、总结与展望', size=16)

# ===== S3: Background (选题背景与意义) =====
s = pres.Slides(3)
debug_shapes(s, 3)
ts = get_title_shape(s)
if ts:
    set_text(ts, '选题背景与意义', size=28, bold=True)
# Fill body shapes - template may have card-style layout
bodies = get_body_shapes(s)
print(f"S3: found {len(bodies)} body shapes")
card_texts = [
    '背景问题\n传统课堂观察依赖教师人工判断，效率低',
    '发展趋势\n智慧教育+AI辅助教学，YOLO提供技术基础',
    '研究意义\n将检测模型从单图原型扩展为完整Web系统',
]
for i, b in enumerate(bodies[:3]):
    if i < len(card_texts):
        set_text(b, card_texts[i], size=11)
# Also fill large text area
for j in range(1, s.Shapes.Count + 1):
    sh = s.Shapes(j)
    try:
        if sh.HasTextFrame:
            t = sh.TextFrame.TextRange.Text
            if '在此输入内容' in t:
                set_text(sh, '背景：传统课堂观察效率低，教师难以实时关注每位学生状态\n'
                         '趋势：智慧教育、AI辅助教学快速发展，YOLO系列模型提供技术基础\n'
                         '意义：将检测模型从单图原型扩展为完整的Web行为监测分析系统\n'
                         '实现课堂行为的自动识别、持续监测和智能报告生成', size=12)
    except:
        pass
# Insert classroom detection screenshot
classroom_img = os.path.join(THUMBS, '01_mixed_classroom_lowhead_phone_raisinghand.jpg')
for j in range(1, s.Shapes.Count + 1):
    sh = s.Shapes(j)
    try:
        if sh.Type == 13:  # Picture placeholder
            insert_picture(s, classroom_img, sh)
            print("S3: inserted classroom image")
            break
    except:
        pass

# ===== S4: Architecture (系统总体架构) =====
s = pres.Slides(4)
debug_shapes(s, 4)
ts = get_title_shape(s)
if ts:
    set_text(ts, '系统总体架构', size=28, bold=True)
body = get_body_shape(s, ts)
if body:
    set_text(body, '四层流水线：\n'
             '  输入（摄像头/上传）→ 模型预测（YOLO）→ 行为映射 → 页面展示\n\n'
             '分层架构：\n'
             '  表现层：Jinja2 模板 + HTML/CSS/JS\n'
             '  路由控制层：4个routes模块\n'
             '  业务服务层：6个service模块\n'
             '  核心算法层：behavior_core / camera_service / analysis_workflow\n'
             '  数据持久化层：database / storage\n\n'
             '技术栈：Flask + SQLAlchemy + OpenCV + YOLO(ONNX)', size=12)

# ===== S5: Feature overview (核心功能概览) =====
s = pres.Slides(5)
debug_shapes(s, 5)
ts = get_title_shape(s)
if ts:
    set_text(ts, '核心功能概览', size=28, bold=True)
# Insert 4 images into picture placeholders
imgs = [
    os.path.join(SCREENSHOTS, '02_dashboard.png'),
    os.path.join(SCREENSHOTS, '03_monitor.png'),
    os.path.join(SCREENSHOTS, '04_analysis_view.png'),
    os.path.join(THUMBS, '01_mixed_classroom_lowhead_phone_raisinghand.jpg'),
]
pic_idx = 0
for j in range(1, s.Shapes.Count + 1):
    sh = s.Shapes(j)
    try:
        if sh.Type == 13 and pic_idx < len(imgs):  # Picture
            insert_picture(s, imgs[pic_idx], sh)
            pic_idx += 1
            print(f"S5: inserted image {pic_idx}")
    except:
        pass

# ===== S6: Real-time monitor (核心功能 - 实时监控) =====
s = pres.Slides(6)
debug_shapes(s, 6)
ts = get_title_shape(s)
if ts:
    set_text(ts, '核心功能 — 实时监控', size=28, bold=True)
body = get_body_shape(s, ts)
if body:
    set_text(body, '双线程流水线：\n'
             '• 采集线程（capture_frames_loop）\n'
             '• 推理线程（inference_loop）\n'
             '• 可配置推理间隔、流帧率、图像尺寸\n\n'
             '行为检测与专注度：\n'
             '• 实时标注低头、举手、睡觉、转头交谈等行为\n'
             '• 自动计算专注度评分\n\n'
             '降级机制：\n'
             '• 摄像头不可用时显示占位帧\n'
             '• 模型加载锁防止并发冲突\n\n'
             '【答辩时现场打开浏览器实时演示】', size=14)

# ===== S7: Upload analysis (离线分析) =====
s = pres.Slides(7)
debug_shapes(s, 7)
ts = get_title_shape(s)
if ts:
    set_text(ts, '核心功能 — 离线视频分析与报告', size=28, bold=True)
body = get_body_shape(s, ts)
if body:
    set_text(body, '上传分析流程：\n'
             '  文件验证 → 任务创建 → 后台执行 → 逐帧推理\n'
             '  → 行为映射 → 报告生成\n\n'
             '三种执行后端：\n'
             '• 线程池（默认）— 适合单机部署\n'
             '• 进程池 — 适合CPU密集场景\n'
             '• 文件队列 — 适合分布式部署\n\n'
             '自动分析报告包含：\n'
             '  风险等级（高/中/低）| 专注度评分 | 行为统计\n'
             '  教师评语与建议 | 关键截图证据 | 规则快照', size=14)

# ===== S8: Demo (系统演示) =====
s = pres.Slides(8)
debug_shapes(s, 8)
ts = get_title_shape(s)
if ts:
    set_text(ts, '系统演示', size=28, bold=True)
body = get_body_shape(s, ts)
if body:
    set_text(body, '（此处嵌入预录演示视频）\n\n'
             '演示内容：\n'
             '  1. 上传课堂视频，系统自动进行逐帧分析\n'
             '  2. 分析完成后自动生成报告\n'
             '     包含风险等级和行为统计\n'
             '  3. 管理员在线调整检测参数\n\n'
             '操作提示：\n'
             '  插入 → 视频 → 此设备上的视频 → 选择 defense_demo.mp4\n'
             '  设置为"单击时播放"，调整大小占页面60-70%', size=14)

# ===== S9: Algorithm 1 (关键算法 - 行为映射) =====
s = pres.Slides(9)
debug_shapes(s, 9)
ts = get_title_shape(s)
if ts:
    set_text(ts, '关键算法 — 行为映射与时序分析', size=28, bold=True)
# Template has a table-like layout; find and fill cells
for j in range(1, s.Shapes.Count + 1):
    sh = s.Shapes(j)
    try:
        if sh.HasTextFrame:
            t = sh.TextFrame.TextRange.Text.strip()
            if '此处' in t or '在本' in t or len(t) < 20:
                # Try to identify which cell this is and fill accordingly
                set_text(sh, '详见正文', size=10)
    except:
        pass
# Set the main content area
body = get_body_shape(s, ts)
if body:
    set_text(body, '检测标签标准化：\n'
             '  30+变体映射统一为6种行为\n'
             '  CLASS_BEHAVIOR_MAP：将YOLO类别ID映射为6种课堂行为\n\n'
             '时序分析器 BehaviorTemporalAnalyzer：\n'
             '  连续帧判断 → 稳定状态 → 持续时长 → 报警触发\n\n'
             '六种检测行为：\n'
             '  low_head（低头）| phone（玩手机）| hand_raise（举手）\n'
             '  sleep（睡觉）| turn_talk（转头交谈）| head_up（抬头）\n\n'
             '（预留位置：行为映射流程图 — 待GPT生成）', size=12)

# ===== S10: Algorithm 2 (关键算法 - 专注度评分) =====
s = pres.Slides(10)
debug_shapes(s, 10)
ts = get_title_shape(s)
if ts:
    set_text(ts, '关键算法 — 专注度评分与报告生成', size=28, bold=True)
body = get_body_shape(s, ts)
if body:
    set_text(body, '专注度评分公式：\n'
             '  Score = 100 - 低头×12 - 玩手机×18 - 睡觉×20\n'
             '         - 转头交谈×15 + 举手×4\n\n'
             '评分等级：\n'
             '  高专注度：≥ 80  |  中专注度：60-79  |  低专注度：< 60\n\n'
             '自动报告生成：\n'
             '  风险结论：基于行为模式和持续时长自动判定\n'
             '  教师评语：根据行为模式自动生成教学建议\n'
             '  证据收集：关键截图 + 时间线 + 规则快照\n\n'
             '（预留位置：报告生成流程图 — 待GPT生成）', size=12)

# ===== S11: Results 1 (实验结果 - 行为识别效果) =====
s = pres.Slides(11)
debug_shapes(s, 11)
ts = get_title_shape(s)
if ts:
    set_text(ts, '实验结果 — 行为识别效果', size=28, bold=True)
body = get_body_shape(s, ts)
if body:
    set_text(body, '实验方式：多段课堂视频人工标注对照\n\n'
             '识别指标：\n'
             '  低头：    P=0.87  R=0.84  F1=0.85\n'
             '  睡觉：    P=0.92  R=0.88  F1=0.90\n'
             '  举手：    P=0.89  R=0.91  F1=0.90\n'
             '  转头交谈：P=0.83  R=0.80  F1=0.81\n\n'
             '模型配置：默认置信度阈值 0.35，连续帧阈值 4-6', size=13)
# Insert recognition metrics chart
chart1 = os.path.join(CHARTS, 'recognition_metrics.png')
for j in range(1, s.Shapes.Count + 1):
    sh = s.Shapes(j)
    try:
        if sh.Type == 13:  # Picture
            insert_picture(s, chart1, sh)
            print("S11: inserted recognition chart")
            break
    except:
        pass

# ===== S12: Results 2 (实验结果 - 性能与参数对比) =====
s = pres.Slides(12)
debug_shapes(s, 12)
ts = get_title_shape(s)
if ts:
    set_text(ts, '实验结果 — 性能与参数对比', size=28, bold=True)
body = get_body_shape(s, ts)
if body:
    set_text(body, '系统性能：\n'
             '  实时视频处理：10-12 FPS\n'
             '  离线视频分析：0.4-0.8倍视频时长\n'
             '  报告生成：< 2秒\n'
             '  API响应：秒级刷新\n\n'
             '参数配置对比：\n'
             '  敏感档：连续帧3，置信度0.25，告警3s\n'
             '  默认档：连续帧4-6，置信度0.35，告警5s\n'
             '  稳定档：连续帧7-8，置信度0.45，告警8s\n\n'
             '功能测试：6项全部通过', size=12)
# Insert parameter comparison chart
chart2 = os.path.join(CHARTS, 'parameter_comparison.png')
for j in range(1, s.Shapes.Count + 1):
    sh = s.Shapes(j)
    try:
        if sh.Type == 13:  # Picture
            insert_picture(s, chart2, sh)
            print("S12: inserted parameter chart")
            break
    except:
        pass

# ===== S13: Summary (总结与展望) =====
s = pres.Slides(13)
debug_shapes(s, 13)
ts = get_title_shape(s)
if ts:
    set_text(ts, '总结与展望', size=28, bold=True)
body = get_body_shape(s, ts)
if body:
    set_text(body, '主要成果：\n'
             '  1. 将YOLO原型扩展为完整的Web行为监测分析系统\n'
             '  2. 设计了检测→行为映射→时序分析→报警→报告的完整流水线\n'
             '  3. 实现了可配置规则引擎，支持管理员在线调参\n'
             '  4. 提供了Docker一键部署方案\n\n'
             '不足与展望：\n'
             '  1. 识别依赖best.onnx模型质量，可进一步优化训练数据\n'
             '  2. 暂未实现学生个体追踪\n'
             '  3. 光照和角度对识别精度有影响', size=14)

# ===== S14: Thank you (致谢) =====
s = pres.Slides(14)
debug_shapes(s, 14)
ts = get_title_shape(s)
if ts:
    set_text(ts, '谢谢各位老师！请批评指正', size=32, bold=True)
# Find the subtitle/author text
for j in range(1, s.Shapes.Count + 1):
    sh = s.Shapes(j)
    try:
        if sh.HasTextFrame and sh != ts:
            t = sh.TextFrame.TextRange.Text
            if 'JUNE' in t or '汇报人' in t or 'THANKS' in t or t.strip():
                set_text(sh, '汇报人：XXX | 2026年5月', size=12)
    except:
        pass

print(f'\nDone! Total slides: {pres.Slides.Count}')
print('Please save manually: Ctrl+S')
