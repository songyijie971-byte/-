# -*- coding: utf-8 -*-
"""Generate defense PPT by duplicating template slides to preserve backgrounds."""
import os
import copy
from lxml import etree
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
TEMPLATE = os.path.join(BASE_DIR, "ppt", "5-中国石油大学（北京）PPT模板.pptx")
SCREENSHOTS = os.path.join(BASE_DIR, "ppt", "screenshots")
CHARTS = os.path.join(BASE_DIR, "ppt", "charts")
THUMBS = os.path.join(BASE_DIR, "samples", "demo_videos", "thumbs")
OUTPUT = os.path.join(BASE_DIR, "ppt", "毕业设计答辩.pptx")


def duplicate_slide(prs, slide_index):
    """Duplicate a slide preserving all formatting/backgrounds."""
    source = prs.slides[slide_index]
    # Get the slide layout
    layout = source.slide_layout
    # Create new slide with same layout
    new_slide = prs.slides.add_slide(layout)

    # Copy all shapes from source
    for shape in source.shapes:
        # Get the XML element of the shape
        elem = shape._element
        # Deep copy it
        new_elem = copy.deepcopy(elem)
        # Append to new slide's spTree
        new_slide.shapes._spTree.append(new_elem)

    # Copy slide-level properties (background etc.)
    if hasattr(source, '_element'):
        # Copy any background
        bg = source._element.find(qn('p:bg'))
        if bg is not None:
            # Remove existing bg on new slide
            existing_bg = new_slide._element.find(qn('p:bg'))
            if existing_bg is not None:
                new_slide._element.remove(existing_bg)
            new_slide._element.append(copy.deepcopy(bg))

    return new_slide


def set_text(shape, text, font_size=None, bold=None, alignment=None):
    """Set text content on a shape."""
    if shape is None:
        return
    tf = shape.text_frame
    # Clear existing
    for para in tf.paragraphs:
        for run in para.runs:
            run.text = ""
    if tf.paragraphs:
        tf.paragraphs[0].text = text
        if font_size:
            tf.paragraphs[0].font.size = Pt(font_size)
        if bold is not None:
            tf.paragraphs[0].font.bold = bold
        if alignment:
            tf.paragraphs[0].alignment = alignment


def set_bullet_text(shape, items, font_size=None):
    """Set bullet points on a shape's text frame."""
    if shape is None:
        return
    tf = shape.text_frame
    tf.clear()
    for i, item in enumerate(items):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = item
        if font_size:
            p.font.size = Pt(font_size)
        p.space_after = Pt(4)
        # Set bullet
        pPr = p._pPr
        if pPr is None:
            pPr = p._p.get_or_add_pPr()
        buChar = etree.SubElement(pPr, qn('a:buChar'))
        buChar.set('char', '•')


def insert_image(slide, image_path, x, y, width, height):
    """Insert an image at specified position."""
    if os.path.exists(image_path):
        slide.shapes.add_picture(image_path, x, y, width, height)


def get_shape_by_idx(slide, idx):
    """Get shape by placeholder index."""
    try:
        return slide.placeholders[idx]
    except (KeyError, IndexError):
        return None


def create_ppt():
    prs = Presentation(TEMPLATE)

    # Get layout indices
    # We'll use the first few slides as templates and duplicate them
    # Layout 0 = title slide, Layout 9 = title+text, Layout 8 = picture+caption

    # Store original slide count
    original_count = len(prs.slides)

    # We need to figure out which layouts have backgrounds
    # Let's just use add_slide with the layout but copy background from existing slides
    # Actually, let's just duplicate existing template slides

    # First, let's see what slides are already in the template and use them as base
    # Find slides by layout type
    layout_slides = {}
    for i, slide in enumerate(prs.slides):
        layout_name = slide.slide_layout.name
        if layout_name not in layout_slides:
            layout_slides[layout_name] = i

    print(f"Available layout slides: {layout_slides}")

    # Strategy: duplicate the first slide repeatedly, then change content
    # But actually, python-pptx add_slide DOES preserve backgrounds if the layout has them
    # The real issue might be that the template doesn't have slide-level backgrounds in layouts

    # Let's try a different approach: use VBA-style automation through win32com
    # This is the most reliable way to preserve formatting
    try:
        import win32com.client
        return create_ppt_win32com()
    except ImportError:
        print("win32com not available, falling back to python-pptx with duplicate approach")
        return create_ppt_python_pptx_fallback(prs)


def create_ppt_win32com():
    """Use win32com (PowerPoint COM automation) for perfect template preservation."""
    import win32com.client
    import pythoncom

    pythoncom.CoInitialize()
    ppt = win32com.client.Dispatch("PowerPoint.Application")
    ppt.Visible = True

    # Open template
    pres = ppt.Presentations.Open(TEMPLATE)

    # Delete existing slides (template placeholders)
    while pres.Slides.Count > 0:
        pres.Slides(1).Delete()

    # Layout constants
    ppLayoutTitle = 1
    ppLayoutText = 2
    ppLayoutTwoColumnText = 3
    ppLayoutTable = 4
    ppLayoutTextAndChart = 5
    ppLayoutChartAndText = 6
    ppLayoutTitleOnly = 11
    ppLayoutBlank = 12
    ppLayoutTextAndClipart = 13
    ppLayoutClipartAndText = 14
    ppLayoutTitle = 1  # Title slide

    def add_slide(layout):
        return pres.Slides.Add(pres.Slides.Count + 1, layout)

    def set_title(slide, text):
        if slide.Shapes.HasTitle:
            slide.Shapes.Title.TextFrame.TextRange.Text = text

    def set_body(slide, text):
        # Body is usually shape index 2
        for shape in slide.Shapes:
            try:
                if shape.HasTextFrame and shape.Name.startswith("Content"):
                    shape.TextFrame.TextRange.Text = text
                    return
            except:
                pass
        # Try by index
        try:
            if slide.Shapes.Count >= 2:
                slide.Shapes(2).TextFrame.TextRange.Text = text
        except:
            pass

    def add_picture(slide, image_path, left, top, width, height):
        if os.path.exists(image_path):
            slide.Shapes.AddPicture(image_path, False, True, left, top, width, height)

    # Slide 1: Title
    s = add_slide(ppLayoutTitle)
    set_title(s, "智慧课堂行为识别与分析系统的设计与实现")
    set_body(s, "毕业设计答辩\n计算机科学专业\n学号：2022015421\n指导教师：陈亮\n中国石油大学（北京）石油学院\n2026年5月")

    # Slide 2: 目录
    s = add_slide(ppLayoutText)
    set_title(s, "汇报提纲")
    set_body(s, "一、选题背景与意义\n二、系统总体设计\n三、核心功能与实现\n四、系统演示\n五、关键算法\n六、实验与测试\n七、总结与展望")

    # Slide 3: 选题背景
    s = add_slide(ppLayoutClipartAndText)
    set_title(s, "一、选题背景与意义")
    thumb = os.path.join(THUMBS, "01_mixed_classroom_lowhead_phone_raisinghand.jpg")
    if os.path.exists(thumb):
        add_picture(s, thumb, 400, 150, 400, 300)
    set_body(s, "背景问题：\n• 传统课堂观察依赖教师人工判断，效率低、主观性强\n• 大班授课中，教师难以实时关注每位学生状态\n\n发展趋势：\n• 智慧教育、AI辅助教学成为发展方向\n• YOLO系列目标检测模型为实时检测提供技术基础\n\n研究意义：\n• 将YOLO检测模型从单图原型扩展为完整Web监测分析系统\n• 实现课堂行为的自动识别、持续监测和智能报告生成")

    # Slide 4: 系统目标
    s = add_slide(ppLayoutText)
    set_title(s, "二、系统目标与功能需求")
    set_body(s, "系统目标：构建支持实时监控、离线分析、自动报告的课堂行为识别系统\n\n三大用户角色：\n  管理员 — 系统配置、健康检查、规则管理\n  教  师 — 实时监控、查看分析报告\n  普通用户 — 上传视频/图片、查看报告\n\n七大功能模块：\n  认证管理 → 实时监控 → 视频上传分析 → 历史记录\n  → 报告展示 → 规则配置 → 实验评估")

    # Slide 5: 系统架构
    s = add_slide(ppLayoutClipartAndText)
    set_title(s, "三、系统总体架构")
    dash = os.path.join(SCREENSHOTS, "02_dashboard.png")
    if os.path.exists(dash):
        add_picture(s, dash, 400, 150, 400, 300)
    set_body(s, "四层流水线：\n  输入（摄像头/上传）→ 模型预测（YOLO）→ 行为映射 → 页面展示\n\n分层架构：\n  表现层：Jinja2 模板 + HTML/CSS/JS\n  路由控制层：auth/analysis/config/report_routes\n  业务服务层：auth/analysis/report/config_service\n  核心算法层：behavior_core / camera_service / analysis_workflow\n  数据持久化层：database / storage / repositories\n\n技术栈：\n  Flask + SQLAlchemy + OpenCV + YOLO(ONNX) + Jinja2")

    # Slide 6: 实时监控
    s = add_slide(ppLayoutClipartAndText)
    set_title(s, "四、核心功能 — 实时监控")
    mon = os.path.join(SCREENSHOTS, "03_monitor.png")
    if os.path.exists(mon):
        add_picture(s, mon, 400, 150, 400, 300)
    set_body(s, "摄像头实时推理：\n• 双线程流水线：采集线程 + 推理线程\n• 可配置推理间隔、流帧率、图像尺寸\n\n行为检测叠加：\n• 实时标注低头、举手、睡觉、转头交谈等行为\n• 自动计算专注度评分\n\n降级机制：\n• 摄像头不可用时显示占位帧，给出诊断信息\n• 模型加载锁机制，防止并发冲突\n\n【答辩时现场打开浏览器实时演示】")

    # Slide 7: 离线分析
    s = add_slide(ppLayoutClipartAndText)
    set_title(s, "五、核心功能 — 离线视频分析与报告")
    anal = os.path.join(SCREENSHOTS, "04_analysis_view.png")
    if os.path.exists(anal):
        add_picture(s, anal, 400, 150, 400, 300)
    set_body(s, "上传分析流程：\n  文件验证 → 任务创建 → 后台执行 → 逐帧推理\n  → 行为映射 → 报告生成\n\n三种执行后端：\n• 线程池（默认）— 适合单机部署\n• 进程池 — 适合CPU密集场景\n• 文件队列 — 适合分布式部署\n\n自动分析报告包含：\n  风险等级（高/中/低）| 专注度评分 | 行为统计\n  教师评语与建议 | 关键截图证据 | 规则快照")

    # Slide 8: 系统演示
    s = add_slide(ppLayoutText)
    set_title(s, "六、系统演示")
    set_body(s, "（此处嵌入预录演示视频）\n\n演示内容：\n  1. 上传课堂视频，系统自动进行逐帧分析\n  2. 分析完成后自动生成报告\n     包含风险等级和行为统计\n  3. 管理员在线调整检测参数\n\n操作提示：\n  插入 → 视频 → 此设备上的视频 → 选择 defense_demo.mp4\n  设置为“单击时播放”，调整大小占页面60-70%")

    # Slide 9: 关键算法1
    s = add_slide(ppLayoutText)
    set_title(s, "七、关键算法 — 行为映射与时序分析")
    set_body(s, "检测标签标准化：\n• 30+ 变体映射（如 UsingPhone / phone / cell phone → phone）\n• CLASS_BEHAVIOR_MAP 将YOLO类别ID映射为6种课堂行为\n\n时序分析器 BehaviorTemporalAnalyzer：\n• 连续帧判断 → 稳定状态 → 持续时长 → 报警触发\n• 行为需连续N帧被检测到才算“稳定”，过滤偶发误检\n\n六种检测行为：\n  low_head（低头）| phone（玩手机）| hand_raise（举手）\n  sleep（睡觉）| turn_talk（转头交谈）| head_up（抬头）\n\n【预留位置：行为映射流程图 — 可用GPT生成】")

    # Slide 10: 关键算法2
    s = add_slide(ppLayoutText)
    set_title(s, "八、关键算法 — 专注度评分与报告生成")
    set_body(s, "专注度评分公式：\n  Score = 100 - 低头×12 - 玩手机×18 - 睡觉×20\n         - 转头交谈×15 + 举手×4\n\n评分等级：\n  高专注度：≥ 80  |  中专注度：60-79  |  低专注度：< 60\n\n自动报告生成：\n• 风险结论：基于行为模式和持续时长自动判定\n• 教师评语：根据行为模式自动生成教学建议\n• 证据收集：关键截图 + 时间线 + 规则快照\n\n【预留位置：报告生成流程图 — 可用GPT生成】")

    # Slide 11: 实验结果1
    s = add_slide(ppLayoutClipartAndText)
    set_title(s, "九、实验结果 — 行为识别效果")
    chart1 = os.path.join(CHARTS, "recognition_metrics.png")
    if os.path.exists(chart1):
        add_picture(s, chart1, 400, 150, 400, 300)
    set_body(s, "实验方式：\n  多段课堂短视频进行人工标注对照\n\n识别效果：\n  低头：    P=0.87  R=0.84  F1=0.85\n  睡觉：    P=0.92  R=0.88  F1=0.90\n  举手：    P=0.89  R=0.91  F1=0.90\n  转头交谈：P=0.83  R=0.80  F1=0.81\n\n模型配置：\n  默认置信度阈值：0.35\n  默认连续帧阈值：4-6")

    # Slide 12: 实验结果2
    s = add_slide(ppLayoutClipartAndText)
    set_title(s, "十、实验结果 — 性能与参数对比")
    chart2 = os.path.join(CHARTS, "parameter_comparison.png")
    if os.path.exists(chart2):
        add_picture(s, chart2, 400, 150, 400, 300)
    set_body(s, "系统性能：\n  实时视频处理：10-12 FPS\n  离线视频分析：0.4-0.8倍视频时长\n  报告生成：< 2秒\n  API响应：秒级刷新\n\n参数配置对比：\n  敏感档：连续帧3，置信度0.25，告警3s\n  默认档：连续帧4-6，置信度0.35，告警5s\n  稳定档：连续帧7-8，置信度0.45，告警8s\n\n功能测试：6项测试全部通过")

    # Slide 13: 总结
    s = add_slide(ppLayoutText)
    set_title(s, "十一、总结与展望")
    set_body(s, "主要成果：\n  1. 将YOLO原型扩展为完整的Web行为监测分析系统\n  2. 设计了检测→行为映射→时序分析→报警→报告的完整流水线\n  3. 实现了可配置规则引擎，支持管理员在线调参\n  4. 提供了Docker一键部署方案\n\n不足与展望：\n  1. 识别依赖best.onnx模型质量，可进一步优化训练数据\n  2. 暂未实现学生个体追踪\n  3. 光照和角度对识别精度有影响")

    # Slide 14: 致谢
    s = add_slide(ppLayoutTitle)
    set_title(s, "谢谢各位老师！")
    set_body(s, "请批评指正")

    pres.SaveAs(OUTPUT)
    pres.Close()
    ppt.Quit()
    pythoncom.CoUninitialize()
    print(f"PPT saved to: {OUTPUT}")
    print("Total slides: 14")


def create_ppt_python_pptx_fallback(prs):
    """Fallback using python-pptx with duplicate slide approach."""
    print("Using python-pptx duplicate slide approach...")

    # Strategy: use the template's existing slides as bases, duplicate them
    # The template has 33 slides across 11 layouts
    # We need to find representative slides for each layout type

    # Find which existing slides correspond to which layouts
    title_slide_idx = None  # Layout 0
    text_slide_idx = None   # Layout 9 (标题文本)
    pic_text_slide_idx = None  # Layout 8 (图片标题) or Layout 7

    for i, slide in enumerate(prs.slides):
        layout_name = slide.slide_layout.name
        if "封面" in layout_name or "title" in layout_name.lower():
            if title_slide_idx is None:
                title_slide_idx = i
        elif "文本" in layout_name or "text" in layout_name.lower():
            if text_slide_idx is None:
                text_slide_idx = i
        elif "图片" in layout_name or "picture" in layout_name.lower():
            if pic_text_slide_idx is None:
                pic_text_slide_idx = i

    # Fallback: just use first slides of the template
    if title_slide_idx is None:
        title_slide_idx = 0
    if text_slide_idx is None:
        text_slide_idx = 1
    if pic_text_slide_idx is None:
        pic_text_slide_idx = 2

    print(f"Using slides: title={title_slide_idx}, text={text_slide_idx}, pic_text={pic_text_slide_idx}")

    # Remove all slides except the ones we'll use as templates
    keep_indices = {title_slide_idx, text_slide_idx, pic_text_slide_idx}
    # Sort in reverse to delete from end
    to_delete = sorted([i for i in range(len(prs.slides)) if i not in keep_indices], reverse=True)
    for idx in to_delete:
        rId = prs.slides._sldIdLst[idx].get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        prs.part.drop_rel(rId)
        prs.slides._sldIdLst.remove(prs.slides._sldIdLst[idx])

    # After deletion, indices shift. Re-find them.
    # Actually, since we only kept 3 slides, let's just work with what we have
    # and duplicate them

    # Now we have 3 slides. We need 14. We'll duplicate and modify.
    # First slide = title (layout 0), second = text (layout 9), third = pic+text (layout 8)

    def add_new_slide(prs, layout_idx):
        """Add a new slide using a layout from the template."""
        slide = prs.slides.add_slide(prs.slide_layouts[layout_idx])
        return slide

    # Just use add_slide with the original layouts
    # The backgrounds SHOULD be preserved since layouts contain background info
    # The previous issue was probably something else

    # Remove all slides to start fresh
    while len(prs.slides) > 0:
        rId = prs.slides._sldIdLst[0].get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        prs.part.drop_rel(rId)
        prs.slides._sldIdLst.remove(prs.slides._sldIdLst[0])

    # Map layouts
    layouts = {}
    for i, layout in enumerate(prs.slide_layouts):
        layouts[layout.name] = i

    print(f"Available layouts: {layouts}")

    # Find best layout indices
    def find_layout(keywords):
        for i, layout in enumerate(prs.slide_layouts):
            for kw in keywords:
                if kw in layout.name:
                    return i
        return 0  # fallback

    layout_title = find_layout(["封面", "title"])
    layout_text = find_layout(["文本", "text"])
    layout_pic = find_layout(["图片", "picture", "clipart"])
    layout_two = find_layout(["两个", "two", "比较", "compare"])

    print(f"Layouts: title={layout_title}, text={layout_text}, pic={layout_pic}, two={layout_two}")

    # Now create slides
    slides_data = [
        (layout_title, "智慧课堂行为识别与分析系统的设计与实现",
         "毕业设计答辩\n\n计算机科学专业\n学号：2022015421\n指导教师：陈亮\n\n中国石油大学（北京）石油学院\n2026年5月"),
        (layout_text, "汇报提纲",
         "一、选题背景与意义\n二、系统总体设计\n三、核心功能与实现\n四、系统演示\n五、关键算法\n六、实验与测试\n七、总结与展望"),
        (layout_pic, "一、选题背景与意义",
         "背景问题：\n• 传统课堂观察依赖教师人工判断，效率低\n• 大班授课中，教师难以实时关注每位学生\n\n发展趋势：\n• 智慧教育、AI辅助教学成为发展方向\n• YOLO系列模型为实时检测提供技术基础\n\n研究意义：\n• 将YOLO检测模型从单图原型扩展为完整Web系统\n• 实现课堂行为的自动识别、监测和报告生成"),
        (layout_text, "二、系统目标与功能需求",
         "系统目标：构建支持实时监控、离线分析、自动报告的课堂行为识别系统\n\n三大用户角色：\n  管理员 — 系统配置、健康检查、规则管理\n  教  师 — 实时监控、查看分析报告\n  普通用户 — 上传视频/图片、查看报告\n\n七大功能模块：\n  认证管理→实时监控→视频上传分析→历史记录\n  →报告展示→规则配置→实验评估"),
        (layout_pic, "三、系统总体架构",
         "四层流水线：\n  输入→模型预测→行为映射→页面展示\n\n分层架构：\n  表现层：Jinja2 + HTML/CSS/JS\n  路由控制层：4个routes模块\n  业务服务层：6个service模块\n  核心算法层：behavior_core/camera/analysis\n  数据持久化层：database/storage\n\n技术栈：Flask + SQLAlchemy + OpenCV + YOLO"),
        (layout_pic, "四、核心功能 — 实时监控",
         "双线程流水线：\n• 采集线程 + 推理线程\n• 可配置推理间隔、帧率、图像尺寸\n\n行为检测与专注度：\n• 实时标注低头、举手、睡觉等行为\n• 自动计算专注度评分\n\n降级机制：\n• 摄像头不可用时显示占位帧\n• 模型加载锁防止并发冲突\n\n【答辩时现场演示】"),
        (layout_pic, "五、核心功能 — 离线分析与报告",
         "上传分析流程：\n  文件验证→任务创建→后台执行→逐帧推理\n  →行为映射→报告生成\n\n三种执行后端：\n• 线程池（默认）• 进程池 • 文件队列\n\n自动报告内容：\n  风险等级 | 专注度评分 | 行为统计\n  教师评语 | 关键截图 | 规则快照"),
        (layout_text, "六、系统演示",
         "（此处嵌入预录演示视频）\n\n演示内容：\n  1. 上传课堂视频，自动逐帧分析\n  2. 自动生成报告（风险等级+行为统计）\n  3. 管理员在线调整检测参数\n\n操作：插入→视频→选择defense_demo.mp4\n设置为“单击时播放”"),
        (layout_text, "七、关键算法 — 行为映射与时序分析",
         "检测标签标准化：\n• 30+变体映射统一为6种行为\n• CLASS_BEHAVIOR_MAP：类别ID→行为键\n\n时序分析器 BehaviorTemporalAnalyzer：\n• 连续帧→稳定状态→持续时长→报警\n• N帧连续检测才算“稳定”，过滤偶发误检\n\n六种行为：\n  low_head|phone|hand_raise|sleep|turn_talk|head_up\n\n【预留：行为映射流程图位置】"),
        (layout_text, "八、关键算法 — 专注度评分与报告",
         "专注度公式：\n  100 - 低头×12 - 玩手机×18 - 睡觉×20\n       - 转头交谈×15 + 举手×4\n\n等级：≥80高 | 60-79中 | <60低\n\n自动报告：\n• 风险结论：行为模式+持续时长判定\n• 教师评语：行为模式自动生成建议\n• 证据：截图+时间线+规则快照\n\n【预留：报告生成流程图位置】"),
        (layout_pic, "九、实验结果 — 识别效果",
         "实验方式：多段课堂视频人工标注对照\n\n识别指标：\n  低头：    P=0.87 R=0.84 F1=0.85\n  睡觉：    P=0.92 R=0.88 F1=0.90\n  举手：    P=0.89 R=0.91 F1=0.90\n  转头交谈：P=0.83 R=0.80 F1=0.81\n\n配置：置信度0.35，连续帧4-6"),
        (layout_pic, "十、实验结果 — 性能与参数",
         "系统性能：\n  实时处理：10-12 FPS\n  离线分析：0.4-0.8倍视频时长\n  报告生成：<2秒\n\n参数对比：\n  敏感档：帧3/置信0.25/告警3s\n  默认档：帧4-6/置信0.35/告警5s\n  稳定档：帧7-8/置信0.45/告警8s\n\n功能测试：6项全部通过"),
        (layout_text, "十一、总结与展望",
         "主要成果：\n  1. 将YOLO原型扩展为完整Web监测分析系统\n  2. 设计检测→映射→时序→报警→报告流水线\n  3. 实现可配置规则引擎，支持在线调参\n  4. Docker一键部署方案\n\n不足与展望：\n  1. 依赖模型质量，可优化训练数据\n  2. 暂未实现个体追踪\n  3. 光照角度影响精度"),
        (layout_title, "谢谢各位老师！", "请批评指正"),
    ]

    # Image assignments for picture slides
    image_map = {
        2: os.path.join(THUMBS, "01_mixed_classroom_lowhead_phone_raisinghand.jpg"),
        4: os.path.join(SCREENSHOTS, "02_dashboard.png"),
        5: os.path.join(SCREENSHOTS, "03_monitor.png"),
        6: os.path.join(SCREENSHOTS, "04_analysis_view.png"),
        10: os.path.join(CHARTS, "recognition_metrics.png"),
        11: os.path.join(CHARTS, "parameter_comparison.png"),
    }

    for i, (layout_idx, title, body) in enumerate(slides_data):
        slide = prs.slides.add_slide(prs.slide_layouts[layout_idx])

        # Set title
        try:
            if 0 in slide.placeholders:
                ph = slide.placeholders[0]
                ph.text_frame.clear()
                p = ph.text_frame.paragraphs[0]
                p.text = title
                p.font.size = Pt(22)
                p.font.bold = True
        except (KeyError, IndexError):
            pass

        # Set body text
        try:
            # Try placeholder 1 (most common for body)
            body_idx = 1
            if body_idx in slide.placeholders:
                ph = slide.placeholders[body_idx]
                tf = ph.text_frame
                tf.clear()
                lines = body.split('\n')
                for j, line in enumerate(lines):
                    if j == 0:
                        p = tf.paragraphs[0]
                    else:
                        p = tf.add_paragraph()
                    p.text = line
                    p.font.size = Pt(14)
                    p.space_after = Pt(2)
        except (KeyError, IndexError):
            pass

        # Add image for picture slides
        if i in image_map:
            img_path = image_map[i]
            if os.path.exists(img_path):
                try:
                    # Try to add to placeholder 2 (picture placeholder)
                    if 2 in slide.placeholders:
                        slide.placeholders[2].insert_picture(img_path)
                    else:
                        # Add directly at specific position
                        # Slide width = 12192000, height = 6858000
                        # Right half of slide
                        left = Emu(7000000)
                        top = Emu(1500000)
                        width = Emu(4500000)
                        height = Emu(3400000)
                        slide.shapes.add_picture(img_path, left, top, width, height)
                except Exception as e:
                    print(f"  [!] Could not add image to slide {i}: {e}")

    # Save
    prs.save(OUTPUT)
    print(f"PPT saved to: {OUTPUT}")
    print(f"Total slides: {len(prs.slides)}")


if __name__ == "__main__":
    create_ppt()
