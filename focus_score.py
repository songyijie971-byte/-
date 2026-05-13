from typing import Mapping


def calculate_focus_score(stable_counts: Mapping[str, int]) -> dict:
    penalties = (
        stable_counts.get("low_head", 0) * 12
        + stable_counts.get("phone", 0) * 18
        + stable_counts.get("sleep", 0) * 20
        + stable_counts.get("turn_talk", 0) * 15
    )
    rewards = stable_counts.get("hand_raise", 0) * 4
    score = max(0, min(100, 100 - penalties + rewards))

    if score >= 80:
        level = "高"
        summary_text = "当前课堂整体专注度较高，课堂状态较为稳定。"
    elif score >= 60:
        level = "中"
        summary_text = "当前课堂专注度处于中等区间，建议关注波动学生。"
    else:
        level = "低"
        summary_text = "当前课堂专注度偏低，建议及时进行干预。"

    return {
        "score": score,
        "level": level,
        "summary_text": summary_text,
        "rule_text": "100 - 低头×12 - 睡觉×20 - 转头交谈×15 + 举手×4",
        "limits_text": "该评分仅用于课堂状态可视化展示，不直接等同于教学质量评价。",
    }
